#!/usr/bin/env python3
"""Rehearse the COG-0 inverse in a disposable git worktree.

The landed tree is never modified. The rehearsal removes additive Phase-0
files, restores the three pre-existing hatch/export files from the pinned
baseline, retains the append-only operative rows with simulated rollback
notes, proves the remaining diff is exactly those two ledgers, and runs the
pre-phase safety/compatibility gates against that inverse tree.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/plans/cognitive-core-phase-0-rollback-manifest-2026-07-19.yml"
EXPECTED_RETAINED = {
    "docs/plans/operative-egg-ledger-2026-07-07.yml",
    "docs/plans/operative-egg-plan-2026-07-07.md",
}
ROLLBACK_SUFFIX = (
    " | ROLLBACK-REHEARSAL 2026-07-19: simulated supersession; "
    "Phase-0 implementation bytes removed and history retained."
)

# Byte-identical to the A13 assertion in verify-cognitive-phase0.sh's heredoc
# (ledger-id uniqueness + plan_ids==set(ids) parity). Raw string keeps the `\|`
# regex escape; executed via `python3.12 -c` with cwd=scratch so the SAME check
# runs on the inverse tree. LOAD-BEARING: if either copy is edited the other must
# move in lockstep (pinned by test_rehearsal_runs_identical_a13_assertion_on_inverse_tree).
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


def remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()
    else:
        raise RuntimeError(f"declared rollback removal path is absent: {path}")


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
        "\n<!-- ROLLBACK-REHEARSAL 2026-07-19: "
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
            raise RuntimeError(f"Phase 0 modified protected surface: {rel}")

    scratch = Path(tempfile.mkdtemp(prefix="cog0-rollback-")) / "tree"
    try:
        run(["git", "worktree", "add", "--detach", str(scratch), "HEAD"], cwd=ROOT)
        for rel in manifest["remove"]:
            remove_path(confined(scratch, rel))
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

        # rollback-manifest line 50 ("ledger id uniqueness, A13 parity"): the SAME
        # assertion verify-cognitive-phase0.sh runs on the committed tree, here on the
        # inverse tree AFTER the append-only notes. Unconditional (structural), so
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
        print("COG-0 rollback rehearsal: PASS (only append-only operative history remains)")
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
