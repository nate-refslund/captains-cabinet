#!/usr/bin/env python3.12
"""evidence-tamper-drill.py — Phase-4 tamper game-day drill (design 2026-07-16
section 2.4 rehearsal; section 3 Phase 4).

Proves, end to end and against a SACRIFICIAL SCRATCH STORE ONLY, that the
whole-store restore-to-earlier tamper class the in-store verifier cannot see
is (a) invisible to ``verify_store`` (the blindness exhibit) and (b) caught
by the production external-anchor path (``evidence-anchor.py --check`` exit
2), and then rehearses the sanctioned response: set the judging-frozen
marker (``framework/evidence_freeze``) and page the CHAIR (never the
Captain directly — P-Alerts-To-Chair).

Modes
-----
``--mode test`` (default): everything happens against scratch — the store,
the anchor file, and the freeze marker all live in a throwaway temp dir
that is removed on exit; the Chair page is a WOULD-PAGE report line only.
The only traces are the two sanctioned Captain-facing report surfaces under
``--out-root`` (default: this repo):

  * ``cabinet/logs/tamper-drills.jsonl``           (one row per run)
  * ``shared/interfaces/tamper-drills/<stamp>.md`` (rendered outcome doc)

``--mode live --confirm-live``: the full game day. Same scratch store and
catch proof, but the freeze marker is set at the REAL repo root (shadow
services refuse to run until the Captain clears it — that Captain-clear is
part of the rehearsal) and the Chair is REALLY paged through the same Redis
trigger mechanism the outcome watchdog uses (message via env var, chair id
from ``CABINET_CHAIR_OFFICER``, default ``cos``). The message is clearly
labelled a drill.

Hard guarantees
---------------
* There is deliberately NO ``--store`` option: the harness only ever
  operates on a scratch store it created itself. The live store
  (``instance/evidence/``) is never read, written, or verified.
* ``verify_store`` runs only against scratch (verification advances
  watermarks — the sanctioned side effect stays inside the sandbox).
* No org events, no receipts, no Telegram: the drill outcome is
  Captain-facing report files only (shadow law).
* Bytecode caches are suppressed so the repo tree stays untouched.

Shadow law: every output is a report. Nothing consumes these files to
gate, block, score, or act. The honest claim (printed in every report):
the anchor check detects retroactive single-plane tamper and INCONSISTENT
forgery only; consistent same-user forgery of both planes stays open until
HP-1 — necessary, not sufficient.

Subcommands: run | freeze-status | unfreeze (Captain-token gated; reuses
the framework/evidence __main__ capability mechanism — no new auth scheme).

Runbook + outcome template: docs/runbooks/tamper-drill.md.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework import evidence_freeze  # noqa: E402
from framework.evidence_anchor import check_anchor, collect_anchor  # noqa: E402

DRILL_SCHEMA = "cabinet.tamper-drill/v1"
SENDER = "evidence-tamper-drill"
SCRATCH_PREFIX = "cabinet-tamper-drill-"
ANCHOR_CLI = _REPO_ROOT / "cabinet" / "scripts" / "evidence-anchor.py"
TRIGGERS_LIB = _REPO_ROOT / "cabinet" / "scripts" / "lib" / "triggers.sh"
RUNBOOK = "docs/runbooks/tamper-drill.md"

HONEST_CLAIM = (
    "The external-anchor check detects retroactive single-plane tamper and "
    "INCONSISTENT forgery only; consistent same-user forgery of both planes "
    "(the same OS user rewrites ledger and store together, key file readable) "
    "stays open until HP-1 (OS-user/key isolation) lands - necessary, not "
    "sufficient."
)
RESIDUAL_NOTE = (
    "Known residual, concrete form of the claim above: check_anchor excuses "
    "a missing trial when any purge-receipts/ file NAME matches "
    "sha256(trial_id)[:16], and a receipt appearing after the last anchor is "
    "not itself a finding - a same-user forger can mask a deletion by "
    "planting a receipt-shaped file."
)
CORE_KINDS = {"trial_rollback", "trial_missing", "watermark_regression"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra:
        env.update(extra)
    return env


def _refuse_evidence_path(path: Path, what: str) -> None:
    """No drill output may ever land inside an evidence store tree."""
    resolved = path.resolve()
    parts = resolved.parts
    for index in range(len(parts) - 1):
        if parts[index] == "instance" and parts[index + 1] == "evidence":
            raise SystemExit(
                f"evidence-tamper-drill: REFUSING {what} inside an evidence "
                f"store tree: {resolved}"
            )


def _store_census(store: Path) -> dict[str, int]:
    """Cheap byte-level census of the SCRATCH store (trials + event lines)."""
    trials = 0
    events = 0
    trials_dir = store / "trials"
    if trials_dir.is_dir():
        for path in sorted(trials_dir.iterdir()):
            if not path.is_dir():
                continue
            trials += 1
            ledger = path / "events.jsonl"
            try:
                events += ledger.read_bytes().count(b"\n")
            except OSError:
                pass
    return {"trials": trials, "events": events}


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def _drill_message(kinds: list[str], mode: str, marker: Path, doc: Path) -> str:
    return (
        "TAMPER GAME-DAY DRILL (rehearsal, not a real alert; mode="
        + mode
        + "). The external evidence anchor check caught a simulated "
        "restore-to-earlier of a sacrificial scratch copy of the evidence "
        "record (findings: "
        + ", ".join(kinds)
        + "). The store's own verifier stayed green - only the external "
        "anchor caught it. Evidence judging is frozen (marker: "
        + str(marker)
        + "). If this were real: do not modify the evidence store, leave the "
        "freeze in place, and bring this to the Captain for triage - "
        "clearing the freeze is Captain-only (" + RUNBOOK + "). "
        "Outcome report: " + str(doc)
    )


def _page_chair(message: str) -> tuple[str, str]:
    """LIVE page via the exact outcome-watchdog mechanism: bash sources
    triggers.sh and calls trigger_send; the message AND the chair id ride
    env vars (never interpolated into the shell string); chair defaults to
    ``cos`` via CABINET_CHAIR_OFFICER; success = rc 0 and empty stderr."""
    chair = os.environ.get("CABINET_CHAIR_OFFICER", "cos")
    script = (
        f'. "{TRIGGERS_LIB}" && '
        f'OFFICER_NAME={SENDER} trigger_send "$DRILL_CHAIR" "$DRILL_MSG"'
    )
    env = _child_env({"DRILL_MSG": message, "DRILL_CHAIR": chair})
    env["PATH"] = "/opt/homebrew/bin:" + env.get("PATH", "")
    try:
        result = subprocess.run(
            ["/bin/bash", "-c", script],
            capture_output=True, text=True, timeout=20, env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return "page-failed", str(exc)
    if result.returncode == 0 and not (result.stderr or "").strip():
        return "paged", chair
    return "page-failed", (result.stderr or result.stdout or "").strip()[:200]


def _render_doc(row: dict, checks: list[dict], doc_path: Path) -> None:
    lines = [
        "# Tamper game-day drill — " + row["ts"],
        "",
        "Mode: " + row["mode"],
        "Scratch store: " + row["scratch"] + " (removed after the run unless kept)",
        "Runbook: " + RUNBOOK,
        "",
        "## What was simulated",
        "",
        "A whole-store restore-to-earlier: a byte-for-byte copy of the",
        "sacrificial scratch evidence store was taken, more trials and events",
        "were appended and verified, a real external anchor record was",
        "exported, and then the store was replaced with the earlier copy",
        "(events, tip anchors, and watermark sidecar together) — exactly the",
        "class the in-store verifier cannot prove.",
        "",
        f"- Trials/events at anchor time: {row['trials_at_anchor']} trials, "
        f"{row['events_at_anchor']} events",
        f"- Trials/events after restore: {row['trials_after_restore']} trials, "
        f"{row['events_after_restore']} events",
        f"- Anchor record digest: {row['anchor_record_digest']}",
        "",
        "## What caught it",
        "",
        "The production path: `python3.12 cabinet/scripts/evidence-anchor.py "
        "--store <scratch> --check <scratch-anchors.jsonl>` — exit 2 with "
        "findings; the in-process `check_anchor` agreed.",
        "",
        f"- Caught: {row['caught']}",
        f"- Finding kinds: {', '.join(row['finding_kinds']) or 'none'}",
        f"- First-run vacuous-pass guard held (first_run is False): "
        f"{not row['first_run']}",
        f"- Time to catch (restore -> check exit): {row['time_to_catch_s']} s",
        "",
        "## Local verifier blindness (why the external anchor exists)",
        "",
        f"- verify_store on the RESTORED store returned ok=True: "
        f"{row['verifier_blind']}",
        "",
        "## Response steps taken",
        "",
    ]
    for check in checks:
        mark = "ok" if check["ok"] else "FAILED"
        lines.append(f"- [{mark}] {check['step']}: {check['note']}")
    lines += [
        "",
        f"- Judging-frozen marker: {row['froze']} (scope: {row['freeze_scope']})",
        f"- Chair page: {row['paged']} (chair: {row['chair']})",
        "",
        "## Captain clear",
        "",
        (
            "Live mode: the marker at the repo root stays until the Captain "
            "clears it — `python3.12 cabinet/scripts/evidence-tamper-drill.py "
            "unfreeze --captain-token-file <file>` (token-gated), or the "
            "manual steps in the runbook. That clear IS part of the rehearsal."
            if row["mode"] == "live"
            else "Test mode: the marker lived under scratch and was removed "
                 "with it; no real judging was frozen. Captain clear: n/a."
        ),
        "",
        "## Gaps found",
        "",
    ]
    if row["gaps"]:
        lines += [f"- {gap}" for gap in row["gaps"]]
    else:
        lines.append("- none: every drill check passed")
    lines += [
        "",
        "## Known residuals (honest claim)",
        "",
        HONEST_CLAIM,
        "",
        RESIDUAL_NOTE,
        "",
    ]
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("\n".join(lines), encoding="utf-8")


def run_drill(args: argparse.Namespace) -> int:
    mode = args.mode
    if mode == "live" and not args.confirm_live:
        print(
            "evidence-tamper-drill: --mode live sets the REAL freeze marker "
            "and REALLY pages the Chair; re-run with --confirm-live.",
            file=sys.stderr,
        )
        return 64
    if mode == "live" and evidence_freeze.is_frozen(_REPO_ROOT):
        print(
            "evidence-tamper-drill: judging is ALREADY frozen at "
            + str(evidence_freeze.marker_path(_REPO_ROOT))
            + " - refusing a live drill over a real freeze; Captain clears "
            "first (" + RUNBOOK + ").",
            file=sys.stderr,
        )
        return 64

    out_root = Path(args.out_root).resolve()
    _refuse_evidence_path(out_root, "--out-root")
    row_path = out_root / "cabinet" / "logs" / "tamper-drills.jsonl"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    doc_path = out_root / "shared" / "interfaces" / "tamper-drills" / (
        "tamper-drill-" + stamp + ".md"
    )

    # Producer identity: fixed at process start, never payload-derived.
    from framework.evidence import (
        attest_process_identity,
        attestation_detail,
        attested_actor,
        attested_component,
        verify_store,
    )
    from framework.evidence.recorder import EvidenceRecorder

    attest_process_identity("system", SENDER, SENDER)

    scratch = Path(tempfile.mkdtemp(prefix=SCRATCH_PREFIX)).resolve()
    store = scratch / "store"
    snapshot = scratch / "store-before-tamper"
    anchors = scratch / "evidence-anchors.jsonl"
    freeze_root = scratch / "freeze-root" if mode == "test" else _REPO_ROOT
    checks: list[dict] = []
    t_start = time.monotonic()

    def check(step: str, ok: bool, note: str) -> bool:
        checks.append({"step": step, "ok": bool(ok), "note": note})
        return bool(ok)

    try:
        # The harness only ever touches the scratch store it just created.
        assert str(store).startswith(str(scratch))
        _refuse_evidence_path(scratch, "scratch dir")

        # 1) Build the sacrificial store: two trials, real recorder events.
        recorder = EvidenceRecorder(store)
        for trial_id in ("drill-alpha-001", "drill-beta-001"):
            context = recorder.trace(trial_id, surface="system")
            detail = {"action": "tamper_drill_seed", **attestation_detail()}
            recorder.append(
                context, phase="intent", status="started",
                actor=attested_actor(), component=attested_component(),
                detail=detail, links=[],
            )
            recorder.append(
                context, phase="execution", status="succeeded",
                actor=attested_actor(), component=attested_component(),
                detail=detail, links=[],
            )
        first_verify = verify_store(store)
        check(
            "build sacrificial scratch store", bool(first_verify.get("ok")),
            f"2 trials seeded, verify_store ok={first_verify.get('ok')} "
            "(watermarks advanced - sanctioned, scratch only)",
        )

        # 2) Byte-level snapshot of the WHOLE store (real dir copy — a
        #    symlink swap would raise AnchorError, not findings).
        shutil.copytree(store, snapshot, symlinks=True)
        census_snapshot = _store_census(store)

        # 3) Progress after the snapshot: new events + a new trial, verified.
        context = recorder.trace("drill-alpha-001", surface="system")
        recorder.append(
            context, phase="outcome", status="succeeded",
            actor=attested_actor(), component=attested_component(),
            detail={"action": "tamper_drill_progress", **attestation_detail()},
            links=[],
        )
        context = recorder.trace("drill-gamma-001", surface="system")
        recorder.append(
            context, phase="intent", status="started",
            actor=attested_actor(), component=attested_component(),
            detail={"action": "tamper_drill_progress", **attestation_detail()},
            links=[],
        )
        second_verify = verify_store(store)
        census_at_anchor = _store_census(store)

        # 4) Export a REAL anchor record (the production record shape).
        record = collect_anchor(store)
        _append_jsonl(anchors, record)
        check(
            "export external anchor record",
            bool(second_verify.get("ok")) and bool(record.get("record_digest")),
            f"record_digest={str(record.get('record_digest'))[:16]}..., "
            f"{census_at_anchor['trials']} trials / "
            f"{census_at_anchor['events']} events anchored",
        )

        # 5) Simulate the tamper: whole-store restore-to-earlier.
        shutil.rmtree(store)
        shutil.copytree(snapshot, store, symlinks=True)
        t_restored = time.monotonic()
        census_after = _store_census(store)
        check(
            "simulate whole-store restore-to-earlier",
            census_after["events"] < census_at_anchor["events"],
            f"store replaced with earlier byte-copy: {census_after['events']} "
            f"events now vs {census_at_anchor['events']} anchored",
        )

        # 6) Blindness proof: the in-store verifier is GREEN on the
        #    restored store — this is the drill's core exhibit.
        blind = verify_store(store)
        verifier_blind = bool(blind.get("ok"))
        check(
            "local verifier blindness proof", verifier_blind,
            "verify_store(restored) ok=" + str(blind.get("ok"))
            + " - the rollback is locally invisible",
        )

        # 7) Catch proof through the PRODUCTION path (evidence-anchor --check).
        proc = subprocess.run(
            [sys.executable, str(ANCHOR_CLI),
             "--store", str(store), "--check", str(anchors)],
            capture_output=True, text=True, timeout=120,
            cwd=str(_REPO_ROOT), env=_child_env(),
        )
        t_caught = time.monotonic()
        try:
            cli_result = json.loads(proc.stdout.strip() or "{}")
        except ValueError:
            cli_result = {}
        cli_kinds = sorted({
            str(f.get("kind")) for f in cli_result.get("findings", [])
        })
        caught = proc.returncode == 2 and cli_result.get("ok") is False
        check(
            "catch via production anchor --check", caught,
            f"exit={proc.returncode} (2 expected), findings="
            + (", ".join(cli_kinds) or "none"),
        )
        first_run = bool(cli_result.get("first_run", True))
        check(
            "first-run vacuous-pass guard", not first_run,
            "first_run=" + str(cli_result.get("first_run"))
            + " (must be False - an anchor exported before the restore)",
        )
        inproc = check_anchor(store, record)
        inproc_kinds = sorted({str(f.get("kind")) for f in inproc["findings"]})
        check(
            "in-process check agrees with CLI",
            set(inproc_kinds) == set(cli_kinds) and inproc["first_run"] is False,
            "in-process kinds=" + (", ".join(inproc_kinds) or "none"),
        )
        check(
            "expected finding kinds present", CORE_KINDS <= set(cli_kinds),
            "require trial_rollback + trial_missing + watermark_regression",
        )

        # 8) Respond: freeze judging (scratch pseudo-root in test mode; the
        #    REAL repo root in live mode), then page the Chair.
        marker = evidence_freeze.freeze(
            freeze_root,
            "tamper-drill: external anchor integrity findings",
            finding_kinds=cli_kinds, set_by=SENDER, drill=True,
        )
        froze_ok = evidence_freeze.is_frozen(freeze_root)
        check(
            "set judging-frozen marker", froze_ok,
            f"marker={marker} (scope: "
            + ("scratch pseudo-root" if mode == "test" else "REAL repo root")
            + ")",
        )

        message = _drill_message(cli_kinds, mode, marker, doc_path)
        chair = os.environ.get("CABINET_CHAIR_OFFICER", "cos")
        if mode == "test":
            paged, page_note = "would-page", chair
            print(f"WOULD PAGE Chair ({chair}): {message}")
            check("page the Chair", True,
                  "test mode: would-page line only (no trigger sent)")
        else:
            paged, page_note = _page_chair(message)
            check("page the Chair", paged == "paged",
                  f"{paged}: {page_note}")

        gaps = [
            f"{c['step']} - {c['note']}" for c in checks if not c["ok"]
        ]
        row = {
            "schema": DRILL_SCHEMA,
            "ts": _utc_now(),
            "mode": mode,
            "scratch": str(scratch),
            "caught": caught,
            "first_run": first_run,
            "finding_kinds": cli_kinds,
            "verifier_blind": verifier_blind,
            "time_to_catch_s": round(t_caught - t_restored, 3),
            "duration_s": round(time.monotonic() - t_start, 3),
            "trials_at_anchor": census_at_anchor["trials"],
            "events_at_anchor": census_at_anchor["events"],
            "trials_after_restore": census_after["trials"],
            "events_after_restore": census_after["events"],
            "events_at_snapshot": census_snapshot["events"],
            "anchor_record_digest": str(record.get("record_digest"))[:16],
            "froze": str(marker),
            "freeze_scope": "scratch" if mode == "test" else "repo",
            "paged": paged,
            "chair": chair,
            "outcome_doc": str(doc_path),
            "gaps": gaps,
            "honest_claim": HONEST_CLAIM,
        }
        _render_doc(row, checks, doc_path)
        _append_jsonl(row_path, row)

        ok = all(c["ok"] for c in checks)
        print(
            "evidence-tamper-drill: "
            + ("PASS" if ok else "FAIL")
            + f" mode={mode} caught={caught} kinds={','.join(cli_kinds)} "
            f"blind_verifier={verifier_blind} froze={froze_ok} paged={paged} "
            f"time_to_catch={row['time_to_catch_s']}s"
        )
        print(f"evidence-tamper-drill: outcome doc {doc_path}")
        print(f"evidence-tamper-drill: report row appended {row_path}")
        return 0 if ok else 1
    finally:
        if args.keep_scratch:
            print(f"evidence-tamper-drill: scratch kept at {scratch}")
        else:
            # The scratch marker may carry the immutable flag - lift it (a
            # SCRATCH marker only; the sanctioned cleanup named in
            # evidence_freeze._lift_immutable's contract), then remove.
            if mode == "test":
                evidence_freeze._lift_immutable(
                    evidence_freeze.marker_path(scratch / "freeze-root")
                )
            try:
                shutil.rmtree(scratch)
            except OSError as exc:
                print(
                    f"evidence-tamper-drill: WARN scratch cleanup failed "
                    f"({exc}); remove {scratch} manually",
                    file=sys.stderr,
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence-tamper-drill")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run", help="Run the tamper game-day drill against a scratch store",
    )
    run.add_argument("--mode", choices=["test", "live"], default="test")
    run.add_argument(
        "--confirm-live", action="store_true",
        help="Required with --mode live (real freeze marker + real Chair page)",
    )
    run.add_argument(
        "--out-root", type=Path, default=_REPO_ROOT,
        help="Root for the report surfaces (default: this repo)",
    )
    run.add_argument("--keep-scratch", action="store_true")

    freeze_status = commands.add_parser(
        "freeze-status", help="Print the judging-frozen marker status",
    )
    freeze_status.add_argument("--root", type=Path, default=_REPO_ROOT)

    unfreeze = commands.add_parser(
        "unfreeze",
        help="Captain-only: clear the judging-frozen marker (token-gated)",
    )
    unfreeze.add_argument("--root", type=Path, default=_REPO_ROOT)
    unfreeze.add_argument(
        "--store", type=Path, default=None,
        help="Evidence store the token binds to (default <root>/instance/evidence/v1)",
    )
    unfreeze.add_argument(
        "--captain-token-file", type=Path, default=None,
        help="Captain capability token file (falls back to $CABINET_CAPTAIN_TOKEN_FILE)",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        return run_drill(args)
    if args.command == "freeze-status":
        print(json.dumps(
            evidence_freeze.status(args.root), ensure_ascii=False, sort_keys=True,
        ))
        return 0
    if args.command == "unfreeze":
        store = args.store or (Path(args.root) / "instance" / "evidence" / "v1")
        try:
            result = evidence_freeze.captain_clear(
                args.root, store, captain_token_file=args.captain_token_file,
            )
        except Exception as exc:  # typed refusals: EvidenceError / FreezeError
            code = getattr(exc, "code", type(exc).__name__)
            print(json.dumps(
                {"ok": False, "code": code, "error": str(exc)},
                ensure_ascii=False,
            ))
            return 3
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    sys.exit(main())
