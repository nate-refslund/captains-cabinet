"""Captain/operator CLI for read, verify, export, control, and typed purge.

There is intentionally no generic ``emit`` command. Product components call
the germline recorder from their bounded integration seam; officers receive
only the read-only redacted projection.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .recorder import EvidenceError, EvidenceRecorder
from .verifier import verify_store, verify_trial


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="framework.evidence")
    parser.add_argument("--store", type=Path, help="Evidence store override")
    commands = parser.add_subparsers(dest="command", required=True)

    verify = commands.add_parser("verify")
    verify.add_argument("--trial")

    project = commands.add_parser("project")
    project.add_argument("trial")
    project.add_argument("--limit", type=int, default=200)

    export = commands.add_parser("export")
    export.add_argument("trial")
    export.add_argument("--output", type=Path)

    control = commands.add_parser("control")
    control.add_argument("--retention-days", type=int)
    control.add_argument("--forever", action="store_true")
    control.add_argument("--diagnostic", choices=["on", "off"])
    control.add_argument("--diagnostic-until")

    purge = commands.add_parser("purge")
    purge.add_argument("trial")
    purge.add_argument("--confirmation", required=True)

    commands.add_parser("retain")
    return parser


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
                result = recorder.cabinet_projection(args.trial, limit=args.limit)
            elif args.command == "export":
                result = recorder.export_bundle(args.trial, args.output)
            elif args.command == "control":
                current = recorder.control()
                if args.retention_days is None and not args.forever and args.diagnostic is None:
                    result = current
                else:
                    result = recorder.configure(
                        actor="captain",
                        retention_days=None if args.forever else (
                            args.retention_days if args.retention_days is not None else current.get("retention_days")
                        ),
                        diagnostic_mode=(args.diagnostic == "on") if args.diagnostic is not None else bool(current.get("diagnostic_mode")),
                        diagnostic_until=args.diagnostic_until or current.get("diagnostic_until"),
                    )
            elif args.command == "purge":
                result = recorder.purge_trial(args.trial, confirmation=args.confirmation, actor="captain")
            elif args.command == "retain":
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
