#!/usr/bin/env python3
"""Action-mode eval harness — EVAL-026 (autonomy-graded action seam).

Mechanical PASS/FAIL law for the AUTONOMY-GRADED ACTION SEAM golden eval
(eval body: memory/golden-evals/eval-026-action-mode-autonomy-seam.md —
staged via docs/proposals/germline-amendment-action-mode-eval-2026-07-17.md;
that directory is schg-locked on the live checkout, so the runnable half
lives here, non-germline, wired into cabinet/scripts/run-golden-evals.sh as
section EVAL-026-ACTION-MODE).

The law it enforces, verbatim from the Captain ruling (2026-07-17):

  Every autonomous mutation's mode is a FUNCTION of the posture level —
  propose-first/earn-trust → ASK; act-then-tell → ACT with proven undo +
  receipt; sovereign → GO; Ring-0 ALWAYS Captain regardless.

Deterministic by design — no LLM, no network, no subprocess, no Redis. The
pinned matrix lives in fixtures/matrix.json beside this file: one arm per
posture × ring × reversibility cell that matters, every fail-closed arm,
the undo-handle-required rule, and the Ring-0 category enumeration pinned
by EQUALITY (a widened OR shrunk Captain-only plane is a mismatch). Every
arm passes its posture EXPLICITLY, so the harness never reads the live
instance ruling — hermetic on any box, any posture.

Checks:

  C1  matrix arms         action_decision(arm.action, arm.posture) returns
                          exactly the pinned (mode, captain_card) — any
                          drift, in either direction, is a MISMATCH.
  C2  ring-0 enumeration  framework.authority.action_mode.RING0_CATEGORIES
                          equals the fixture's pinned set exactly.
  C3  mode vocabulary     the seam's MODES set is exactly
                          {propose, act_tell, go} — no new mode can appear
                          without deliberately updating this eval.

Fail-closed: a missing/malformed fixture, an unimportable seam module, or a
raising arm is a FAIL, never a skip.

SECURITY: --repo-root/--fixtures are operator-supplied, read-only, and
never interpolated into a shell. Fixture content is inert data — compared,
never executed.

Usage:
  python3.12 harness.py --self-test [--fixtures DIR] [--repo-root DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_FIXTURES_DIR = _HERE / "fixtures"
_REPO_ROOT = _HERE.parents[2]


def _fail(msg: str) -> int:
    print(f"MISMATCH: {msg}")
    return 1


def run_self_test(fixtures_dir: Path, repo_root: Path) -> int:
    fixture_path = fixtures_dir / "matrix.json"
    try:
        doc = json.loads(fixture_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return _fail(f"fixture unreadable: {fixture_path}: {exc}")
    if not isinstance(doc, dict):
        return _fail("fixture root must be an object")

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from framework.authority import action_mode as AM
    except Exception as exc:  # noqa: BLE001 — unimportable seam is a FAIL
        return _fail(f"seam module unimportable: {exc}")

    failures = 0

    # C2 — ring-0 category enumeration pinned by equality.
    pinned = doc.get("ring0_categories")
    if (not isinstance(pinned, list) or not pinned
            or not all(isinstance(c, str) for c in pinned)):
        return _fail("fixture ring0_categories missing/malformed")
    if frozenset(pinned) != AM.RING0_CATEGORIES:
        failures += _fail(
            "RING0_CATEGORIES drifted: "
            f"pinned={sorted(pinned)} live={sorted(AM.RING0_CATEGORIES)}")

    # C3 — mode vocabulary closed.
    if AM.MODES != frozenset({"propose", "act_tell", "go"}):
        failures += _fail(f"MODES vocabulary drifted: {sorted(AM.MODES)}")

    # C1 — the matrix arms.
    arms = doc.get("arms")
    if not isinstance(arms, list) or not arms:
        return _fail("fixture arms missing/empty")
    held = 0
    for i, arm in enumerate(arms):
        if not isinstance(arm, dict):
            failures += _fail(f"arm[{i}] is not an object")
            continue
        name = str(arm.get("name") or f"arm-{i}")
        expect = arm.get("expect")
        if (not isinstance(expect, dict) or "mode" not in expect
                or "captain_card" not in expect):
            failures += _fail(f"{name}: expect{{mode,captain_card}} missing")
            continue
        try:
            decision = AM.action_decision(arm.get("action"), arm.get("posture"))
        except Exception as exc:  # noqa: BLE001 — the seam must never raise
            failures += _fail(f"{name}: seam RAISED: {exc!r}")
            continue
        got = {"mode": decision.mode, "captain_card": decision.captain_card}
        want = {"mode": expect["mode"], "captain_card": expect["captain_card"]}
        if got != want:
            failures += _fail(f"{name}: want {want} got {got} "
                              f"(reason={decision.reason})")
        else:
            held += 1

    print(f"ACTION-MODE-EVAL: {held}/{len(arms)} matrix arms hold; "
          f"ring0 enumeration + mode vocabulary pinned")
    return 1 if failures else 0


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(prog="action-mode-eval-harness")
    parser.add_argument("--self-test", action="store_true", required=True)
    parser.add_argument("--fixtures", default=str(_FIXTURES_DIR))
    parser.add_argument("--repo-root", default=str(_REPO_ROOT))
    args = parser.parse_args(argv)
    return run_self_test(Path(args.fixtures), Path(args.repo_root))


if __name__ == "__main__":
    sys.exit(main())
