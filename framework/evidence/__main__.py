"""Captain/operator CLI for read, verify, export, control, and typed purge.

There is intentionally no generic ``emit`` command. Product components call
the germline recorder from their bounded integration seam; officers receive
only the read-only redacted projection.

Captain capability gate
-----------------------
Mutating commands (``control`` changes, ``purge``, ``retain``, ``export``)
never execute on the caller's say-so. The caller must present a Captain
capability token: a value derived from the store's private signing key
(``HMAC(signing-key, purpose)``), minted once with ``grant-token`` and kept
in a file outside the officer tool surface. The CLI verifies the presented
token against the store before performing any Captain mutation and refuses
otherwise, so merely asserting a Captain identity string grants nothing.

Honest limits: this is defense-in-depth, not a complete boundary. In a
same-UID deployment any process that can read the store's signing key can
derive the same token, so full closure comes from the separate-UID
deployment boundary (officer processes cannot read the Captain's key or
token files) together with the officer hook layer that structurally blocks
importing this module. Read-only commands (``verify``, ``project``, and
``control`` without changes) intentionally require no token.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import query
from .recorder import EvidenceError, EvidenceRecorder
from .verifier import verify_store, verify_trial

# Versioned domain-separation label for the Captain capability token. The
# token is HMAC(store-signing-key, this label) and therefore binds to one
# evidence store; it never collides with event/control/anchor/purge
# signature domains.
CAPTAIN_TOKEN_PURPOSE = "cabinet.evidence-captain-capability/v1"
_TOKEN_FILE_MAX_BYTES = 4096


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="framework.evidence")
    parser.add_argument("--store", type=Path, help="Evidence store override")
    parser.add_argument(
        "--captain-token-file",
        type=Path,
        help=(
            "File holding the Captain capability token required by mutating "
            "commands (falls back to $CABINET_CAPTAIN_TOKEN_FILE)"
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--trial")

    project = commands.add_parser(
        "project",
        description=(
            "Read-only redacted projection. Pass a trial id, or ONE reserved "
            "cross-trial selector token (selectors take precedence over trial "
            "ids): by-actor:<id|kind:id> | by-component:<name> | "
            "by-status:<status> | by-time:<yyyymmdd>-<yyyymmdd>."
        ),
    )
    project.add_argument("trial")
    project.add_argument("--limit", type=int, default=200)

    export = commands.add_parser("export")
    export.add_argument("trial")
    export.add_argument("--output", type=Path)

    control = commands.add_parser("control")
    control.add_argument("--retention-days", type=int)
    control.add_argument("--forever", action="store_true")
    control.add_argument(
        "--retention-class",
        action="append",
        metavar="NAME=DAYS",
        help=(
            "Per-class retention for day-bounded taxonomy trials "
            "(evt-<class>-<yyyymmdd>). Repeatable; when given, the flags "
            "REPLACE the whole stored map. Unset classes fall back to "
            "--retention-days."
        ),
    )
    control.add_argument(
        "--clear-retention-classes",
        action="store_true",
        help="Remove every per-class retention override (back to the scalar dial).",
    )
    control.add_argument("--diagnostic", choices=["on", "off"])
    control.add_argument("--diagnostic-until")

    purge = commands.add_parser("purge")
    purge.add_argument("trial")
    purge.add_argument("--confirmation", required=True)

    commands.add_parser("retain")

    grant = commands.add_parser(
        "grant-token",
        description=(
            "Mint the Captain capability token file for this store. Minting "
            "requires read access to the store's private signing key; keep "
            "the output outside the officer tool surface."
        ),
    )
    grant.add_argument("--output", type=Path, required=True)
    return parser


def _expected_captain_token(recorder: EvidenceRecorder) -> str:
    return hmac.new(
        recorder._key, CAPTAIN_TOKEN_PURPOSE.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _presented_token_path(args: argparse.Namespace) -> Path | None:
    if args.captain_token_file is not None:
        return args.captain_token_file
    env = os.environ.get("CABINET_CAPTAIN_TOKEN_FILE")
    return Path(env) if env else None


def _read_captain_token(path: Path) -> str:
    if path.is_symlink():
        raise EvidenceError(
            "captain_capability_invalid",
            "The Captain capability token file must not be a symbolic link.",
        )
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise EvidenceError(
            "captain_capability_required",
            "The Captain capability token file is unavailable.",
        ) from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise EvidenceError(
                "captain_capability_invalid",
                "The Captain capability token file must be a regular file.",
            )
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise EvidenceError(
                "captain_capability_invalid",
                "The Captain capability token file permissions are unsafe.",
            )
        if info.st_size > _TOKEN_FILE_MAX_BYTES:
            raise EvidenceError(
                "captain_capability_invalid",
                "The Captain capability token file is not a valid token.",
            )
        data = os.read(fd, _TOKEN_FILE_MAX_BYTES)
    except OSError as exc:
        raise EvidenceError(
            "captain_capability_required",
            "The Captain capability token file is unavailable.",
        ) from exc
    finally:
        os.close(fd)
    try:
        token = data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise EvidenceError(
            "captain_capability_invalid",
            "The Captain capability token file is not a valid token.",
        ) from exc
    if not token.isascii():
        # A capability token is a 64-char ASCII hex HMAC digest, so any
        # non-ASCII content is definitionally not a token. Refuse with the
        # typed error here: hmac.compare_digest raises TypeError on a
        # non-ASCII str, which would crash the gate with a traceback
        # instead of the fail-closed exit-3 refusal.
        raise EvidenceError(
            "captain_capability_invalid",
            "The Captain capability token file is not a valid token.",
        )
    return token


def _require_captain_capability(recorder: EvidenceRecorder, args: argparse.Namespace) -> None:
    """Fail closed unless the caller presents this store's Captain token.

    A bare ``actor="captain"`` string is an assertion, not authority; this
    check demands material derived from the store's private signing key.
    Same-UID residual risk is documented in the module docstring.
    """
    path = _presented_token_path(args)
    if path is None:
        raise EvidenceError(
            "captain_capability_required",
            "This is a Captain-only command. Provide the Captain capability "
            "token file via --captain-token-file or CABINET_CAPTAIN_TOKEN_FILE.",
        )
    presented = _read_captain_token(path)
    expected = _expected_captain_token(recorder)
    # Compare as UTF-8 bytes: encoding is injective so equality is
    # unchanged, but compare_digest(str, str) raises TypeError on any
    # non-ASCII input — this gate must always refuse, never crash.
    if not hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8")):
        raise EvidenceError(
            "captain_capability_invalid",
            "The presented Captain capability token does not authorize this evidence store.",
        )


def _grant_token(recorder: EvidenceRecorder, output: Path) -> dict[str, object]:
    token = _expected_captain_token(recorder)
    if output.is_symlink():
        raise EvidenceError(
            "grant_output_invalid",
            "The Captain capability token output must not be a symbolic link.",
        )
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(
            output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
    except FileExistsError as exc:
        raise EvidenceError(
            "grant_output_exists",
            "That Captain capability token file already exists.",
        ) from exc
    except OSError as exc:
        raise EvidenceError(
            "grant_output_invalid",
            "The Captain capability token could not be written.",
        ) from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "ok": True,
        "schema": "cabinet.evidence-captain-capability/v1",
        "path": str(output),
        "store": str(recorder.root),
    }


def _diagnostic_window_live(value: object) -> bool:
    """True only for a well-formed, timezone-aware expiry in the future.

    Mirrors the recorder's own effective-state rule: a missing, malformed,
    naive, or lapsed expiry means diagnostic mode is already off in effect.
    """
    if not isinstance(value, str):
        return False
    try:
        expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return expiry.tzinfo is not None and expiry > datetime.now(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            root = args.store or Path(
                os.environ.get("CABINET_EVIDENCE_DIR")
                or os.path.expanduser("~/Library/Application Support/cabinet/evidence/v1")
            )
            result = verify_trial(root, args.trial) if args.trial else verify_store(root)
        else:
            recorder = EvidenceRecorder(args.store)
            if args.command == "project":
                if query.is_selector_token(args.trial):
                    result = query.selector_projection(recorder, args.trial, limit=args.limit)
                else:
                    result = recorder.cabinet_projection(args.trial, limit=args.limit)
            elif args.command == "grant-token":
                result = _grant_token(recorder, args.output)
            elif args.command == "export":
                _require_captain_capability(recorder, args)
                result = recorder.export_bundle(args.trial, args.output)
            elif args.command == "control":
                current = recorder.control()
                if (
                    args.retention_days is None
                    and not args.forever
                    and args.diagnostic is None
                    and not args.retention_class
                    and not args.clear_retention_classes
                ):
                    result = current
                else:
                    _require_captain_capability(recorder, args)
                    if args.clear_retention_classes:
                        retention_classes = None
                    elif args.retention_class:
                        retention_classes = {}
                        for item in args.retention_class:
                            name, sep, days_text = str(item).partition("=")
                            try:
                                class_days = int(days_text)
                            except ValueError:
                                class_days = None
                            if not sep or not name or class_days is None:
                                raise EvidenceError(
                                    "retention_class_invalid",
                                    "Use --retention-class NAME=DAYS (e.g. transport=45).",
                                )
                            retention_classes[name] = class_days
                    else:
                        preserved_classes = current.get("retention_classes")
                        retention_classes = (
                            preserved_classes if isinstance(preserved_classes, dict) else None
                        )
                    preserved_until = current.get("diagnostic_until")
                    if args.diagnostic is not None:
                        diagnostic_mode = args.diagnostic == "on"
                    else:
                        diagnostic_mode = bool(current.get("diagnostic_mode"))
                    diagnostic_until = args.diagnostic_until or preserved_until
                    if (
                        args.diagnostic_until is None
                        and diagnostic_mode
                        and not _diagnostic_window_live(preserved_until)
                    ):
                        # The stored expiry already lapsed (or never parsed),
                        # so diagnostic mode is off in effect. Never replay a
                        # stale expiry: preserving an untouched setting keeps
                        # the effective off state, and an explicit
                        # ``--diagnostic on`` mints a fresh default window.
                        if args.diagnostic == "on":
                            diagnostic_until = None
                        else:
                            diagnostic_mode = False
                            diagnostic_until = None
                    result = recorder.configure(
                        actor="captain",
                        retention_days=None if args.forever else (
                            args.retention_days if args.retention_days is not None else current.get("retention_days")
                        ),
                        diagnostic_mode=diagnostic_mode,
                        diagnostic_until=diagnostic_until,
                        retention_classes=retention_classes,
                    )
            elif args.command == "purge":
                _require_captain_capability(recorder, args)
                result = recorder.purge_trial(args.trial, confirmation=args.confirmation, actor="captain")
            elif args.command == "retain":
                _require_captain_capability(recorder, args)
                result = recorder.enforce_retention(actor="captain")
            else:  # pragma: no cover - argparse owns the vocabulary
                raise AssertionError(args.command)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("ok", True) else 4
    except EvidenceError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "error": str(exc)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
