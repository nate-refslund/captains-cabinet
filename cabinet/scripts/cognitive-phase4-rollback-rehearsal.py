#!/usr/bin/env python3
"""Rehearse the COG-4 CODE inverse in a disposable git worktree.

Phase-local twin of cabinet/scripts/cognitive-phase3-rollback-rehearsal.py
(contract §16; the Phase-0/1/2/3 instances stay untouched — each phase owns its
own rehearsal). The landed tree is never modified. The rehearsal removes
additive COG-4 files, restores the extended files from the pinned baseline
(which also removes the COG-4 temporary_allowances rows via the contract yml
restore — proven by the census arm below), retains the append-only operative
rows with simulated rollback notes, proves the remaining diff is exactly those
two ledgers PLUS the manifest's declared out-of-phase residue, and runs the
pre-phase safety/compatibility gates against that inverse tree.

Like COG-2/3, COG-4 is SHADOW-ONLY: there is no authority cutover to rehearse.
The single runtime inverse is safe by construction — the scheduler cache is a
pure rebuildable function of DECLARED versioned inputs (delete is lossless bar
the shadow decision log, expendable in shadow by declaration), there is NO
pointer file this phase (its mere existence is a verify-cognitive-phase4.sh
tripwire, §7.3) and no Postgres role change — so this rehearsal covers the CODE
inverse plus the two phase-specific arms below.

C1 CLOSED-RANGE ANCHOR (born-closed; the BACKLOG :1551-1555 defect never
inherited): the rehearsal reconstructs the tree AS IT STOOD AT THE COG-4
DONE-FLIP, not at HEAD. While the manifest's done_flip_sha is the
PENDING-DONE-FLIP sentinel (the phase has not flipped), the rehearsal anchors
at HEAD and SAYS SO LOUDLY — RETIREMENT CONDITION: the landing integrator pins
the real flip SHA into the manifest at the ledger flip; this script then
anchors there with no edit here.

OUT-OF-PHASE RESIDUE (the closed range contains non-phase work): the WR rider
lane (0d8a74d4 — contract §18, zero COG-4 dependency) and the W1 prior-phase
C1-retrofit/re-freeze (cee6741e — reverting it would RE-OPEN the fixed
open-range defect) are RETAINED by a COG-4 rollback. The inverse-diff assertion
is therefore a STRICT EQUALITY against EXPECTED_RETAINED plus the manifest's
out_of_phase_in_range paths — which doubles as the phase's completeness
ratchet: a sibling W6 landing (e2 compose, e3 measurement, integrator surgery)
that is not folded into the manifest leaves residue and FAILS LOUDLY here (the
phase-3 closure-ratchet role, held by this script until a phase-4 closure test
lands).

PRE-ADOPTION REFOLD ARM (the phase-3 pre-bump lesson, byte-compat analog):
COG-4's W3 routed framework/cortex belief.py + engine.py through the
projection kernel UNDER THE BYTE-COMPAT GATE (no ENGINE_VERSION/epoch bump —
store hashes byte-identical, contract §6.4). The code inverse restores both to
baseline (the PRE-adoption fold) and deletes framework/projection; running the
UNMODIFIED-in-range cortex determinism suite on the inverse tree proves the
pre-adoption fold still reproduces the identical hash lineage (deterministic
across the seed triple + delete->rebuild-from-zero) — asserted by the
baseline's own suite, exactly the phase-3 REFOLD_DETERMINISM_TEST discharge
shape. Hard-fails red (run() raises on non-zero).

COMPOSE-REVERT ROUND-TRIP ARM (§16 fleet inverse) — VACUITY-ARMED. RETIREMENT
CONDITION: the arm arms ITSELF when the W6-e2 compose lands — i.e. when
cabinet/services.yml at the rehearsal anchor differs from baseline OR
cabinet/scripts/cog4-organ-runner.py exists at the anchor. Armed, it proves the
round-trip: the restored services.yml + watchdog registry are byte-identical to
baseline in the scratch tree, the runner CLI is removed by the manifest, and
the three superseding services.yml protections (fleet-truth,
floor-conservation, census --check — the §16 carve-out's named gates) run green
on the FORWARD tree. Unarmed it NOTE-skips loudly (never silently).

The A13 check below is the universal operative-ledger parity (ledger-id
uniqueness + plan_ids == set(ids)) — the SAME source the phase-0/1/2/3 gates
run via their `<<'PY'` heredocs, and verify-cognitive-phase4.sh carries the
byte-identical heredoc too. It is run here on the inverse tree.
Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-4 W6 unit e1).
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/plans/cognitive-core-phase-4-rollback-manifest-2026-07-24.yml"
DONE_FLIP_SENTINEL = "PENDING-DONE-FLIP"
EXPECTED_RETAINED = {
    "docs/plans/operative-egg-ledger-2026-07-07.yml",
    "docs/plans/operative-egg-plan-2026-07-07.md",
}
ROLLBACK_SUFFIX = (
    " | ROLLBACK-REHEARSAL 2026-07-24: simulated supersession; "
    "COG-4 implementation bytes removed and history retained."
)

# The pre-adoption refold arm's vehicle (module docstring): UNMODIFIED in the
# COG-4 range, so on the inverse tree it is the baseline suite folding against
# the RESTORED pre-kernel belief.py/engine.py. Green == "the pre-adoption fold
# reproduces the prior hash lineage" (byte-compat both ways, §6.4).
REFOLD_DETERMINISM_TEST = "cabinet/scripts/tests/test_cog2_rebuild_determinism.py"
# The restored-contracts arm: the evolution contracts suite is UNMODIFIED in
# range (trajectory-v2 tests live in the removed corpus), so it proves the
# RESTORED v1-only contracts.py green under its own baseline suite.
CONTRACTS_SUITE = "framework/evolution/tests/test_contracts.py"
# The §16 carve-out's three superseding services.yml protections (forward tree).
FLEET_TRUTH_TEST = "cabinet/scripts/tests/test_cog4_fleet_truth.py"
FLOOR_CONSERVATION_TEST = "cabinet/scripts/tests/test_cog4_floor_conservation.py"
# The W6-e2 compose vehicle — its existence at the anchor arms the round-trip.
RUNNER_CLI_REL = "cabinet/scripts/cog4-organ-runner.py"

# The UNIVERSAL A13 assertion (ledger-id uniqueness + plan_ids==set(ids) parity)
# — the SAME check the phase-0/1/2/3 verify gates run via their `<<'PY'`
# heredocs. This copy is byte-identical to verify-cognitive-phase4.sh's heredoc
# and is the source run on the inverse tree; the raw string keeps the `\|`
# regex escape and is executed via `python3.12 -c` with cwd=scratch.
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
    unlink). An ABSENT declared path is NOTED and skipped (returns False)
    rather than raising — the frozen review (created only at landing, §15) is
    legitimately absent here; the strict inverse-diff assertion is the teeth
    that catches a genuinely-un-removed COG-4 file."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return True
    if path.exists() or path.is_symlink():
        path.unlink()
        return True
    print(f"[cog4-rollback-rehearsal] NOTE — declared remove path absent, skipping: {rel}")
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
        "\n<!-- ROLLBACK-REHEARSAL 2026-07-24: "
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
    done_flip = manifest["done_flip_sha"]
    # SHA-resolvability probe (the closure-test `cat-file -e` idiom) BEFORE any
    # `git diff --quiet` loop: a bad/absent object makes diff exit non-zero for
    # a NON-diff reason, which would otherwise mis-diagnose as "modified
    # protected surface" (paid at W6-e1 authoring: a mistyped full baseline SHA
    # produced exactly that wrong message). Shallow checkouts fail here HONESTLY.
    probe = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", baseline + "^{commit}"],
        capture_output=True, text=True, check=False)
    if probe.returncode != 0:
        raise RuntimeError(
            f"baseline_sha does not resolve to a commit in this clone: {baseline} "
            "(full clone required; verify the manifest pin)")
    if done_flip == DONE_FLIP_SENTINEL:
        anchor = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True).stdout.strip()
        print("[cog4-rollback-rehearsal] NOTE — done_flip_sha is the C1 sentinel "
              f"({DONE_FLIP_SENTINEL}): the phase has NOT flipped; anchoring at HEAD "
              f"({anchor[:12]}). The landing integrator pins the real flip SHA into "
              "the manifest at the ledger flip (retirement condition).")
    else:
        probe = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", done_flip + "^{commit}"],
            capture_output=True, text=True, check=False)
        if probe.returncode != 0:
            raise RuntimeError(
                f"done_flip_sha does not resolve to a commit in this clone: {done_flip} "
                "(full clone required; verify the manifest pin)")
        anchor = done_flip
    retained_rows = manifest["retain_append_only"][0]["rows"]
    retained_paths = {entry["path"] for entry in manifest["retain_append_only"]}
    if retained_paths != EXPECTED_RETAINED:
        raise RuntimeError(f"unexpected append-only surfaces: {sorted(retained_paths)}")

    remove_set = set(manifest["remove"])
    restore_set = set(manifest["restore_from_baseline"])
    out_of_phase = {row["path"] for row in manifest.get("out_of_phase_in_range", [])}
    # consistency: out-of-phase paths are RETAINED — they may not also be phase
    # remove/restore entries (the two recorded rider OVERLAP files ride
    # restore_from_baseline and are deliberately NOT out-of-phase rows).
    clash = out_of_phase & (remove_set | restore_set)
    if clash:
        raise RuntimeError(f"out_of_phase_in_range paths clash with remove/restore: {sorted(clash)}")

    for rel in manifest["must_remain_unchanged"]:
        result = subprocess.run(
            ["git", "diff", "--quiet", baseline, anchor, "--", rel],
            cwd=ROOT,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"COG-4 modified protected surface: {rel}")

    scratch = Path(tempfile.mkdtemp(prefix="cog4-rollback-")) / "tree"
    try:
        run(["git", "worktree", "add", "--detach", str(scratch), anchor], cwd=ROOT)
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
        # STRICT closed-range accounting: exactly the two retained ledgers plus
        # the declared out-of-phase residue — nothing else. Any sibling landing
        # not yet folded into the manifest surfaces HERE (module docstring:
        # this equality is the phase's completeness ratchet).
        expected = EXPECTED_RETAINED | out_of_phase
        if actual != expected:
            unexplained = sorted(actual - expected)
            missing = sorted(expected - actual)
            raise RuntimeError(
                "inverse diff is not append-only-plus-declared-residue: "
                f"unexplained={unexplained} missing={missing}")

        # rollback-manifest ("ledger id uniqueness, A13 parity"): the SAME
        # universal assertion the phase-0/1/2/3 gates run, here on the inverse
        # tree AFTER the append-only notes. Unconditional (structural), so
        # --skip-compatibility keeps it.
        run(["python3.12", "-c", A13_ASSERTION], cwd=scratch)

        run(["bash", "cabinet/scripts/ledger-status-parity.sh"], cwd=scratch)
        run(["bash", "cabinet/scripts/check-layer-separation.sh"], cwd=scratch)
        run(["bash", "cabinet/scripts/docs-track-code-sweep.sh"], cwd=scratch)
        # allowance_removal validity (§11/§16): with the COG-4 packages deleted
        # and the contract yml restored, the census must be green on the
        # inverse tree — the allowance rows are gone AND so are the deltas.
        # Structural (cheap, deterministic), so --skip-compatibility keeps it.
        run(["python3.12", "cabinet/scripts/cognitive-architecture-census.py", "--check"], cwd=scratch)

        # --- compose-revert round-trip arm (§16 fleet inverse; module docstring
        # names the retirement condition) ---------------------------------------
        services_rel = "cabinet/services.yml"
        services_differs = subprocess.run(
            ["git", "diff", "--quiet", baseline, anchor, "--", services_rel],
            cwd=ROOT, check=False).returncode != 0
        runner_at_anchor = subprocess.run(
            ["git", "cat-file", "-e", f"{anchor}:{RUNNER_CLI_REL}"],
            cwd=ROOT, check=False, capture_output=True).returncode == 0
        if services_differs or runner_at_anchor:
            baseline_services = run(
                ["git", "show", f"{baseline}:{services_rel}"], cwd=ROOT, capture=True).stdout
            if (scratch / services_rel).read_text() != baseline_services:
                raise RuntimeError("compose-revert round-trip: restored services.yml != baseline bytes")
            baseline_registry = run(
                ["git", "show", f"{baseline}:framework/watchdog/registry.py"], cwd=ROOT, capture=True).stdout
            if (scratch / "framework/watchdog/registry.py").read_text() != baseline_registry:
                raise RuntimeError("compose-revert round-trip: restored watchdog registry != baseline bytes")
            if (scratch / RUNNER_CLI_REL).exists():
                raise RuntimeError(
                    f"compose-revert round-trip: {RUNNER_CLI_REL} survived the inverse — "
                    "extend the manifest remove list (sibling_landing_note)")
            # the three superseding services.yml protections, FORWARD tree
            run(["python3.12", "-m", "pytest", FLEET_TRUTH_TEST, FLOOR_CONSERVATION_TEST, "-q"], cwd=ROOT)
            run(["python3.12", "cabinet/scripts/cognitive-architecture-census.py", "--check"], cwd=ROOT)
            print("[cog4-rollback-rehearsal] compose-revert round-trip arm: ARMED and green")
        else:
            print("[cog4-rollback-rehearsal] NOTE — compose-revert round-trip arm VACUOUS: "
                  "the W6-e2 compose has not landed (services.yml at the anchor is "
                  f"baseline-identical and {RUNNER_CLI_REL} does not exist). RETIREMENT "
                  "CONDITION: the arm arms itself the commit the compose lands; nothing to "
                  "retire by hand.")

        if not args.skip_compatibility:
            # PRE-ADOPTION REFOLD arm (module docstring): the code inverse above
            # restored belief.py/engine.py to the PRE-kernel baseline and deleted
            # framework/projection; the unmodified-in-range determinism suite on
            # the inverse tree proves the pre-adoption fold reproduces its hash
            # lineage (byte-compat law §6.4). run() raises on red -> hard fail.
            run(["python3.12", "-m", "pytest", REFOLD_DETERMINISM_TEST, "-q"], cwd=scratch)
            # restored-contracts arm: the v1-only contracts.py under its own
            # unmodified baseline suite.
            run(["python3.12", "-m", "pytest", CONTRACTS_SUITE, "-q"], cwd=scratch)
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
        print("COG-4 rollback rehearsal: PASS (only append-only operative history + the declared out-of-phase residue remain)")
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
