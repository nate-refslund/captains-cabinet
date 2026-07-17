"""Judging-frozen marker for the evidence plane (Phase 4 tamper response).

When the external anchor check (``framework/evidence_anchor.check_anchor``)
finds that the evidence store no longer matches its last exported anchor
record, the sanctioned response (design 2026-07-16 section 2.4) is: freeze
evidence judging, page the Chair, and hand triage to the Captain.  This
module owns the ONE truth for the "judging frozen" marker every Phase-4
shadow service consults.

The marker
----------
``<root>/instance/state/evidence-judging-freeze.json`` where ``root`` is an
EXPLICIT repo-root argument (never an env var: no officer-influenceable
variable can steer where the marker lives — A10 posture, the
``evidence_anchor`` precedent).  ``instance/state/`` is runtime-only and
gitignored; the marker deliberately does NOT live inside the evidence store
(``instance/evidence/``), whose tree must stay byte-stable.

Fail direction — INVERTED from ``observe-only.sh`` on purpose
-------------------------------------------------------------
``observe-only.sh`` treats an invalid marker as an error to reject.  Here,
ANY presence at the marker path — valid JSON, garbage bytes, a symlink, a
directory, an unreadable entry, a stat error — reads FROZEN.  Only a
provable absence reads unfrozen.  Otherwise corrupting the marker would be
an unfreeze primitive.

Posture asymmetry (design section 2.6)
--------------------------------------
Setting the marker is a pure NARROWING: any process may call
:func:`freeze` (first-freeze-wins; an existing marker is never
overwritten).  Clearing is Captain-only: :func:`captain_clear` demands the
store's Captain capability token, verified by REUSING the existing gate in
``framework/evidence/__main__.py`` (HMAC of the store's signing key — no
second auth scheme, no second constant).  When the store itself is too
broken to verify a token, the manual clear steps live in
``docs/runbooks/tamper-drill.md`` (``chflags nouchg`` + ``rm``).

Consumer contract (Phase-4 shadow services: detectors, calibration,
fuel-integrity reporter)::

    from framework.evidence_freeze import is_frozen
    if is_frozen(repo_root):
        print("evidence judging is frozen - refusing to run")
        return 0

Shadow law: in this batch the marker gates only the shadow services' OWN
runs (self-restraint).  Nothing downstream consumes it to gate, block,
score, or act on officer work — the enforce flip is a later Captain-only
ceremony.

This module is intentionally NOT inside the germline ``framework/evidence``
package (that directory is schg-locked recursively); it is a top-level
sibling per the ``evidence_anchor.py`` / ``evidence_mirror.py`` precedent.
Import-safe on 3.9 (stdlib only; the Captain-clear verb lazily imports the
3.11+ recorder and is 3.12-context only).
"""
from __future__ import annotations

import json
import os
import stat as _stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

FREEZE_SCHEMA = "cabinet.evidence-judging-freeze/v1"


class FreezeError(RuntimeError):
    """Typed refusal from the freeze/clear surface (mirrors EvidenceError's
    ``code`` + message shape so CLI callers can treat both uniformly)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def marker_path(root: "Path | str") -> Path:
    """The marker location under an explicit repo root. No env fallback.

    This function is the SINGLE expression of the marker location.  The
    instance-relative path below is a ratified by-design framework->instance
    runtime-state coupling — `.layer-separation-allowlist` row
    ``framework/evidence_freeze.py:FRAMEWORK_PATH_INSTANCE`` (2026-07-17,
    the needs.py class); it stays spelled out here so the layer-separation
    scanner SEES it rather than having it aliased through a fused string.
    """
    return Path(root) / "instance" / "state" / "evidence-judging-freeze.json"


def is_frozen(root: "Path | str") -> bool:
    """FAIL-CLOSED presence check.

    Only ``ENOENT`` — the marker path (or a missing parent chain) simply
    not existing — reads unfrozen.  Every other state — regular file with
    any content, symlink (dangling included), directory, permission error,
    a parent path component replaced by a file (``ENOTDIR``: swapping the
    state dir for a file must never become an unfreeze primitive that
    bypasses the marker's own immutable flag), any exotic stat failure —
    reads FROZEN, so no corruption of the marker OR its parents can ever
    unfreeze judging.
    """
    path = marker_path(root)
    try:
        os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _set_immutable(path: Path) -> None:
    """Best-effort user-immutable flag (macOS uchg). Defense in depth only."""
    chflags = getattr(os, "chflags", None)
    flag = getattr(_stat, "UF_IMMUTABLE", None)
    if chflags is None or flag is None:
        return
    try:
        chflags(path, flag)
    except OSError:
        pass


def _lift_immutable(path: Path) -> None:
    """Best-effort removal of the user-immutable flag.

    Private on purpose: sanctioned callers are :func:`captain_clear` (after
    the token check) and drill-harness cleanup of a SCRATCH marker.  Calling
    this against the live marker outside those paths is a doctrine
    violation, not a capability the module offers.
    """
    chflags = getattr(os, "chflags", None)
    if chflags is None:
        return
    try:
        chflags(path, 0)
    except OSError:
        pass


def freeze(
    root: "Path | str",
    reason: str,
    *,
    finding_kinds: Iterable[str] = (),
    set_by: str = "",
    drill: bool = False,
) -> Path:
    """Set the judging-frozen marker. First-freeze-wins; atomic; 0600.

    Content is content-free by construction: a schema id, a UTC timestamp,
    a short reason string, finding KIND names (never event payloads, never
    trial content), the setter's name, and the drill flag.
    """
    path = marker_path(root)
    if is_frozen(root):
        return path  # first-freeze-wins: never overwrite an existing marker
    payload: Dict[str, Any] = {
        "schema": FREEZE_SCHEMA,
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reason": str(reason)[:200],
        "finding_kinds": sorted({str(kind)[:64] for kind in finding_kinds}),
        "set_by": str(set_by)[:64],
        "drill": bool(drill),
        "clear": (
            "Captain-only: cabinet/scripts/evidence-tamper-drill.py unfreeze "
            "(token-gated) or the manual steps in docs/runbooks/tamper-drill.md"
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp." + str(os.getpid()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(tmp, path)
        except OSError:
            # A concurrent freeze (or an already-immutable marker) beat us to
            # it.  Frozen is frozen — first-freeze-wins, so a surviving
            # marker means success; anything else is a real failure.
            if not is_frozen(root):
                raise
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    _set_immutable(path)
    return path


def status(root: "Path | str") -> Dict[str, Any]:
    """Marker status without ever raising: {frozen, path, content, error}."""
    path = marker_path(root)
    info: Dict[str, Any] = {
        "frozen": is_frozen(root),
        "path": str(path),
        "content": None,
        "error": None,
    }
    if not info["frozen"]:
        return info
    try:
        if path.is_symlink():
            info["error"] = "marker_symlink"
            return info
        if not path.is_file():
            info["error"] = "marker_not_regular_file"
            return info
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            info["content"] = value
        else:
            info["error"] = "marker_not_json_object"
    except (OSError, ValueError) as exc:
        info["error"] = "marker_unreadable:" + type(exc).__name__
    return info


def captain_clear(
    root: "Path | str",
    store_root: "Path | str",
    captain_token_file: "Optional[Path | str]" = None,
) -> Dict[str, Any]:
    """Clear the marker — Captain capability token required.

    Reuses the EXISTING gate from ``framework/evidence/__main__.py``
    verbatim (lazy import): the presented token file must contain
    ``HMAC(store-signing-key, CAPTAIN_TOKEN_PURPOSE)`` and satisfy the same
    file-hygiene rules (regular file, no symlink, no group/other bits).
    ``captain_token_file=None`` falls back to ``CABINET_CAPTAIN_TOKEN_FILE``
    exactly like the germline CLI.  A wrong or absent token raises the
    germline typed ``EvidenceError`` and the marker is untouched.

    Refuses when ``store_root`` is not an existing directory so the
    recorder can never side-effect-create a store during an unfreeze; in
    that state (store destroyed or corrupted beyond verification) the
    manual runbook steps apply instead.
    """
    path = marker_path(root)
    if not is_frozen(root):
        return {
            "ok": True,
            "cleared": False,
            "path": str(path),
            "note": "no freeze marker present",
        }
    store = Path(store_root)
    if not store.is_dir():
        raise FreezeError(
            "captain_clear_no_store",
            "No evidence store directory at "
            + str(store)
            + "; the token cannot be verified. Clear the marker manually per "
            "docs/runbooks/tamper-drill.md (Captain-only).",
        )
    # Lazy imports: 3.11+ recorder territory, and read-only reuse of the
    # germline CLI's captain-capability gate (no second auth scheme).
    import argparse

    from framework.evidence import __main__ as evidence_cli
    from framework.evidence.recorder import EvidenceRecorder

    recorder = EvidenceRecorder(store)
    namespace = argparse.Namespace(
        captain_token_file=Path(captain_token_file) if captain_token_file else None
    )
    evidence_cli._require_captain_capability(recorder, namespace)
    _lift_immutable(path)
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise FreezeError(
            "captain_clear_unlink_failed",
            "The freeze marker could not be removed: " + str(exc),
        ) from exc
    return {
        "ok": True,
        "cleared": True,
        "path": str(path),
        "store": str(recorder.root),
    }
