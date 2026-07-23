#!/usr/bin/env python3
"""Rehearse the COG-3 CODE inverse in a disposable git worktree.

Phase-local twin of cabinet/scripts/cognitive-phase2-rollback-rehearsal.py
(§12.4; the Phase-0/1/2 instances stay untouched — each phase owns its own
rehearsal). The landed tree is never modified. The rehearsal removes additive
COG-3 files, restores the extended files from the pinned baseline (which also
removes the COG-3 temporary_allowances rows via the contract yml restore),
retains the append-only operative rows with simulated rollback notes, proves the
remaining diff is exactly those two ledgers, and runs the pre-phase
safety/compatibility gates against that inverse tree.

Like COG-2, COG-3 is SHADOW-ONLY: there is no authority cutover to rehearse. The
single runtime inverse is safe by construction — the objectives projection cache
is a lossless rebuildable function of the roots + cortex store (§7.3), there is
NO read pointer this phase (§7.4) and NO Postgres role change (§2.1) — so this
rehearsal covers the CODE inverse only (the manifest names the runtime inverse; it
needs no harness).

DIR-WHOLESALE + ABSENCE TOLERANCE (§12.4, wave-4 brief): `framework/objectives`
and `framework/schemas/domains/objectives` are removed as DIRECTORIES (rmtree),
so the sibling-built adapters/ subtree goes with them post-integration. A declared
remove path that is ABSENT at rehearsal time is NOTED and skipped rather than
raising — this covers (a) the frozen review artifact (created only at landing,
§12.3) and (b) an adapters/ package not yet present in this clone. The inverse-diff
assertion at the end is the real teeth: any COG-3 file that failed to be removed
(and differs from baseline) would surface in the diff and fail.

The A13 check below is the universal operative-ledger parity (ledger-id
uniqueness + plan_ids == set(ids)) — the SAME source the phase-0/1/2 gates run
via their `<<'PY'` heredocs, and verify-cognitive-phase3.sh carries the
byte-identical heredoc too. It is run here on the inverse tree; the rollback test
pins this A13_ASSERTION byte-identical against the verify script's heredoc
(the verify-side twin), and its drift teeth are covered by the rollback test's
test_a13_assertion_has_teeth_on_id_set_drift.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/plans/cognitive-core-phase-3-rollback-manifest-2026-07-22.yml"
EXPECTED_RETAINED = {
    "docs/plans/operative-egg-ledger-2026-07-07.yml",
    "docs/plans/operative-egg-plan-2026-07-07.md",
}
ROLLBACK_SUFFIX = (
    " | ROLLBACK-REHEARSAL 2026-07-22: simulated supersession; "
    "COG-3 implementation bytes removed and history retained."
)

# The UNIVERSAL A13 assertion (ledger-id uniqueness + plan_ids==set(ids) parity)
# — the SAME check the phase-0/1/2 verify gates run via their `<<'PY'` heredocs.
# This copy is byte-identical to verify-cognitive-phase3.sh's heredoc (the
# rollback test pins them equal) and is the source run on the inverse tree; the
# raw string keeps the `\|` regex escape and is executed via `python3.12 -c`
# with cwd=scratch.
A13_ASSERTION = r'''import re
import yaml

ledger = yaml.safe_load(open("docs/plans/operative-egg-ledger-2026-07-07.yml"))["entries"]
ids = [entry["id"] for entry in ledger]
assert len(ids) == len(set(ids)), "duplicate operative ledger ids"
plan = open("docs/plans/operative-egg-plan-2026-07-07.md").read()
plan_ids = set(re.findall(r"^\| ([A-Z][A-Z0-9-]*[0-9-][A-Z0-9-]*) ", plan, re.M))
assert plan_ids == set(ids), sorted(plan_ids ^ set(ids))
'''


def run(argv: list[str], *, cwd: Path, capture: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=capture,
        check=False,
    )
    if result.returncode:
        detail = (result.stdout or "") + (result.stderr or "")
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(argv)}\n{detail}")
    return result


def confined(root: Path, rel: str) -> Path:
    pure = Path(rel)
    if pure.is_absolute() or ".." in pure.parts:
        raise RuntimeError(f"rollback path is not confined: {rel}")
    target = (root / pure).resolve()
    if not target.is_relative_to(root.resolve()):
        raise RuntimeError(f"rollback path escapes scratch root: {rel}")
    return target


def remove_path(path: Path, rel: str) -> bool:
    """Remove one declared inverse path (a DIR subtree via rmtree, a file via
    unlink). An ABSENT declared path is NOTED and skipped (returns False) rather
    than raising — the frozen review (created only at landing) and a not-yet-built
    adapters/ package are legitimately absent here; the inverse-diff assertion is
    the teeth that catches a genuinely-un-removed COG-3 file."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return True
    if path.exists() or path.is_symlink():
        path.unlink()
        return True
    print(f"[cog3-rollback-rehearsal] NOTE — declared remove path absent, skipping: {rel}")
    return False


def add_simulated_append_only_notes(scratch: Path, rows: list[str]) -> None:
    ledger = scratch / "docs/plans/operative-egg-ledger-2026-07-07.yml"
    before_text = ledger.read_text()
    before = yaml.safe_load(before_text)
    body = before_text
    for row in rows:
        marker = f'  - id: "{row}"\n'
        start = body.find(marker)
        if start < 0:
            raise RuntimeError(f"rollback row missing from ledger: {row}")
        next_row = body.find('\n  - id: "', start + len(marker))
        stop = len(body) if next_row < 0 else next_row
        note_start = body.find('\n    note: "', start, stop)
        if note_start < 0:
            raise RuntimeError(f"rollback row has no single-line note: {row}")
        note_start += 1
        note_end = body.find("\n", note_start)
        line = body[note_start:note_end]
        if not line.endswith('"'):
            raise RuntimeError(f"rollback row note is not a closed YAML string: {row}")
        body = body[:note_start] + line[:-1] + ROLLBACK_SUFFIX + '"' + body[note_end:]
    ledger.write_text(body)

    after = yaml.safe_load(body)
    before_rows = {entry["id"]: entry for entry in before["entries"]}
    after_rows = {entry["id"]: entry for entry in after["entries"]}
    if set(before_rows) != set(after_rows):
        raise RuntimeError("rollback rehearsal changed ledger row identity")
    for row_id, before_row in before_rows.items():
        expected = dict(before_row)
        if row_id in rows:
            expected["note"] += ROLLBACK_SUFFIX
        if after_rows[row_id] != expected:
            raise RuntimeError(f"rollback rehearsal changed more than the note for {row_id}")

    plan = scratch / "docs/plans/operative-egg-plan-2026-07-07.md"
    before_plan = plan.read_text()
    for row in rows:
        if f"| {row} |" not in before_plan:
            raise RuntimeError(f"rollback row missing from plan: {row}")
    plan_note = (
        "\n<!-- ROLLBACK-REHEARSAL 2026-07-22: "
        + ", ".join(rows)
        + " retained with simulated supersession notes. -->\n"
    )
    plan.write_text(before_plan + plan_note)
    if plan.read_text() != before_plan + plan_note:
        raise RuntimeError("rollback rehearsal did not append the exact plan note")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-compatibility", action="store_true", help="structure-only developer probe")
    args = parser.parse_args()
    manifest = yaml.safe_load(MANIFEST.read_text())
    baseline = manifest["baseline_sha"]
    retained_rows = manifest["retain_append_only"][0]["rows"]
    retained_paths = {entry["path"] for entry in manifest["retain_append_only"]}
    if retained_paths != EXPECTED_RETAINED:
        raise RuntimeError(f"unexpected append-only surfaces: {sorted(retained_paths)}")

    for rel in manifest["must_remain_unchanged"]:
        result = subprocess.run(
            ["git", "diff", "--quiet", baseline, "HEAD", "--", rel],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"COG-3 modified protected surface: {rel}")

    scratch = Path(tempfile.mkdtemp(prefix="cog3-rollback-")) / "tree"
    try:
        run(["git", "worktree", "add", "--detach", str(scratch), "HEAD"], cwd=ROOT)
        for rel in manifest["remove"]:
            remove_path(confined(scratch, rel), rel)
        for rel in manifest["restore_from_baseline"]:
            run(["git", "checkout", baseline, "--", rel], cwd=scratch)
        add_simulated_append_only_notes(scratch, retained_rows)

        changed = run(
            ["git", "diff", "--name-only", baseline, "--"],
            cwd=scratch,
            capture=True,
        )
        actual = {line for line in changed.stdout.splitlines() if line}
        if actual != EXPECTED_RETAINED:
            raise RuntimeError(f"inverse diff is not append-only-only: {sorted(actual)}")

        # rollback-manifest ("ledger id uniqueness, A13 parity"): the SAME
        # universal assertion the phase-0/1/2 gates run, here on the inverse tree
        # AFTER the append-only notes. Unconditional (structural), so
        # --skip-compatibility keeps it.
        run(["python3.12", "-c", A13_ASSERTION], cwd=scratch)

        run(["bash", "cabinet/scripts/ledger-status-parity.sh"], cwd=scratch)
        run(["bash", "cabinet/scripts/check-layer-separation.sh"], cwd=scratch)
        run(["bash", "cabinet/scripts/docs-track-code-sweep.sh"], cwd=scratch)
        if not args.skip_compatibility:
            run(
                [
                    "python3.12", "-m", "pytest",
                    "framework/authority/tests", "framework/acting/tests",
                    "framework/attention/tests", "framework/events/tests",
                    "framework/outbox/tests", "framework/missions/tests",
                    "framework/sources/tests", "framework/ovi/tests",
                    "framework/triggers/tests", "-q",
                ],
                cwd=scratch,
            )
            run(
                ["python3.12", "-m", "pytest", "cabinet/scripts/lib/tests/test_install_extensions_gate.py", "-q"],
                cwd=scratch,
            )
            run(["bash", "cabinet/scripts/run-golden-evals.sh"], cwd=scratch)
        print("COG-3 rollback rehearsal: PASS (only append-only operative history remains)")
        return 0
    finally:
        if scratch.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(scratch)],
                cwd=ROOT,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        shutil.rmtree(scratch.parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
