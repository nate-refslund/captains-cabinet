#!/usr/bin/env python3
"""Bind the frozen COG-4 review to the exact implementation bytes.

Phase-local twin of cabinet/scripts/cognitive-phase3-review-scope.py (contract
§15 review-to-bytes; the Phase-0/1/2/3 instances are digest-frozen historical
and stay untouched — parameterizing them would edit frozen gate archaeology, so
COG-4 clones the pattern instead; shared-routine extraction stays recorded debt,
owner cognitive-core-program, per §14.1 "extraction to C6 stays recorded debt").

Scope = (manifest.remove MINUS the review artifact) UNION
manifest.restore_from_baseline = the COG-4 implementation path set. Excludes the
review artifact (records the digest -> non-self-referential), the two
append-only operative ledgers (they take the later COG-4 status flips), and the
manifest's out_of_phase_in_range block (WR rider lane + W1 prior-phase C1
hardening — landed inside the closed range but NOT phase bytes; the review does
not bind them). Everything else that can change COG-4 behavior — including the
manifest and THIS tool — is bound.

DIR-WHOLESALE ENTRIES: `framework/projection`, `framework/scheduler`,
`framework/organs` and `cabinet/scripts/tests/fixtures/cog4` are named as
DIRECTORIES in the manifest. The digest resolves each scope entry with
`git ls-tree -r` — a DIR entry expands to every committed blob beneath it, a
FILE entry to itself — so a file landing under a bound dir is bound
automatically, with no scope-list edit.

SIBLING-LANDING LAW (W6): the e2 compose (cog4-organ-runner.py, runner plist)
and e3 measurement (cog4-measure.py, S0 baseline artifact) surfaces land in
sibling units of this same wave. The landing integrator extends the manifest
AND EXPECTED_SCOPE here in the SAME commit — resolve_scope() fails closed on
any one-sided edit ("scope drift"), which is the designed forcing function.

Digest = SHA-256 over sorted newline-joined "<mode> <sha> <path>" from
`git ls-tree -r HEAD` (committed tree; mode-bearing; never working tree or index).
  --print              print the digest over HEAD
  --verify <artifact>  recompute over HEAD, compare to the single Reviewed-Scope-Digest line
Read-only, fail-closed, requires a git work tree. Private-side (egg-excluded).
Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-4 W6 unit e1).
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/plans/cognitive-core-phase-4-rollback-manifest-2026-07-24.yml"
REVIEW_ARTIFACT = "shared/interfaces/reviews/cognitive-core-phase-4-review.md"
EXPECTED_SCOPE = frozenset({
    # remove — framework surface DIRS (wholesale)
    "framework/projection",
    "framework/scheduler",
    "framework/organs",
    # remove — the v2 trajectory schema (v1 stays, byte-untouched)
    "framework/schemas/cognitive-trajectory.v2.schema.json",
    # remove — C2 boundary rows (the engine file is a restore below)
    "cabinet/config/boundary-manifest.yml",
    # remove — committed COG-4 CLIs (W3/W4/W5)
    "cabinet/scripts/cog4-snapshot.py",
    "cabinet/scripts/cog4-schedule.py",
    "cabinet/scripts/cog4-dispatch-shadow.py",
    "cabinet/scripts/cog4-parity.py",
    # remove — the corpus fixture DIR (wholesale: fold seeds, pilot manifests,
    # the three non-software cabinets, the tracked N9 parity record)
    "cabinet/scripts/tests/fixtures/cog4",
    # remove — committed COG-4 tests-first corpus (W2) + libs
    "cabinet/scripts/tests/lib_cog4_ast_pins.py",
    "cabinet/scripts/tests/lib_cog4_corpus.py",
    "cabinet/scripts/tests/lib_cog4_dispatch_adapter.py",
    "cabinet/scripts/tests/lib_cog4_floors.py",
    "cabinet/scripts/tests/lib_cog4_parity_set.py",
    "cabinet/scripts/tests/test_cog4_boundary_rows.py",
    "cabinet/scripts/tests/test_cog4_dispatch_ast_pin.py",
    "cabinet/scripts/tests/test_cog4_dispatch_cli.py",
    "cabinet/scripts/tests/test_cog4_exit_fixtures.py",
    "cabinet/scripts/tests/test_cog4_fleet_truth.py",
    "cabinet/scripts/tests/test_cog4_floor_conservation.py",
    "cabinet/scripts/tests/test_cog4_kernel_parity.py",
    "cabinet/scripts/tests/test_cog4_kernel_store.py",
    "cabinet/scripts/tests/test_cog4_measurement.py",
    "cabinet/scripts/tests/test_cog4_organ_manifest.py",
    "cabinet/scripts/tests/test_cog4_organ_runner.py",
    "cabinet/scripts/tests/test_cog4_organs_package.py",
    "cabinet/scripts/tests/test_cog4_parity.py",
    "cabinet/scripts/tests/test_cog4_parity_ast_pin.py",
    "cabinet/scripts/tests/test_cog4_parity_cli.py",
    "cabinet/scripts/tests/test_cog4_parity_record.py",
    "cabinet/scripts/tests/test_cog4_scheduler_ast_pin.py",
    "cabinet/scripts/tests/test_cog4_scheduler_surface.py",
    "cabinet/scripts/tests/test_cog4_sim_dispatch.py",
    "cabinet/scripts/tests/test_cog4_sim_fold.py",
    "cabinet/scripts/tests/test_cog4_trajectory_v2.py",
    # remove — COG-4 PARK markers
    "docs/plans/cog4-w1-u3-officer-plist-cleanup-PARKED-2026-07-23.md",
    "docs/plans/cog4-w3-u3-cortex-serve-adoption-park-2026-07-24.md",
    "docs/plans/cog4-w3-u4-objectives-kernel-adoption-PARKED-2026-07-24.md",
    "docs/plans/cog4-w4-u1-organ-schema-validation-PARKED-2026-07-24.md",
    # remove — COG-4 wave FW-019 batch proofs (WR rider proofs excluded:
    # out_of_phase_in_range, retained on rollback, unbound here)
    "shared/interfaces/reviews/feat-cog4-w1-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w1-u1-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w1-u2-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w2-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w2-t1-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w2-t2-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w2-t3-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w3-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w3-u1-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w3-u2-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w4-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w4-v1-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w4-v2-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w4-v3-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w5-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w5-x1-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w5-x2-cp1.md",
    "shared/interfaces/reviews/feat-cog4-w5-x3-cp1.md",
    # remove — W6-e1 phase twins + FW-019 proof + the manifest, MINUS the
    # frozen review artifact (excluded: records the digest)
    "cabinet/scripts/verify-cognitive-phase4.sh",
    "cabinet/scripts/cognitive-phase4-review-scope.py",
    "cabinet/scripts/cognitive-phase4-rollback-rehearsal.py",
    "shared/interfaces/reviews/feat-cog4-w6-e1-cp1.md",
    "docs/plans/cognitive-core-phase-4-rollback-manifest-2026-07-24.yml",
    # restore_from_baseline (the extended files)
    "cabinet/scripts/cog2-import-gate.py",
    "cabinet/config/cognitive-architecture-contract.yml",
    "framework/cortex/belief.py",
    "framework/cortex/engine.py",
    "framework/evolution/contracts.py",
    ".gitleaksignore",
    "cabinet/scripts/egg-export-manifest.txt",
    "cabinet/scripts/tests/test_egg_export.py",
    "cabinet/services.yml",
    "framework/watchdog/registry.py",
})
_DIGEST_RE = re.compile(r"^Reviewed-Scope-Digest: ([0-9a-f]{64})$", re.M)


class ScopeError(RuntimeError):
    pass


def _git(*args: str) -> str:
    proc = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ScopeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _require_work_tree() -> None:
    proc = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True, check=False)
    if proc.returncode != 0 or proc.stdout.strip() != "true":
        raise ScopeError("not a git work tree (this tool is source-instance only)")


def resolve_scope() -> list[str]:
    import yaml
    manifest = yaml.safe_load(MANIFEST.read_text())
    remove = manifest.get("remove"); restore = manifest.get("restore_from_baseline")
    if not isinstance(remove, list) or not isinstance(restore, list):
        raise ScopeError("manifest remove/restore_from_baseline must be lists")
    scope = (set(remove) - {REVIEW_ARTIFACT}) | set(restore)
    for rel in scope:
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts:
            raise ScopeError(f"scope path is not confined: {rel}")
    if REVIEW_ARTIFACT in scope:
        raise ScopeError("review artifact must be excluded from its own digest")
    if scope != set(EXPECTED_SCOPE):
        extra = sorted(scope - set(EXPECTED_SCOPE)); missing = sorted(set(EXPECTED_SCOPE) - scope)
        raise ScopeError(f"scope drift between the manifest and the tool's expected set (manifest-only={extra}, expected-only={missing}); a deliberate scope change must update BOTH and be re-reviewed")
    return sorted(scope)


def compute_digest() -> str:
    _require_work_tree()
    scope = resolve_scope()
    # `-r` resolves each scope entry to its committed BLOBS: a DIR entry expands
    # to every blob beneath it, a FILE entry to itself. mode-bearing, committed
    # tree only.
    out = _git("ls-tree", "-r", "-z", "HEAD", "--", *scope)
    entries: dict[str, tuple[str, str]] = {}
    for record in out.split("\0"):
        if not record:
            continue
        meta, _, path = record.partition("\t")
        parts = meta.split()
        if len(parts) != 3:
            raise ScopeError(f"unparseable ls-tree record: {record!r}")
        mode, obj_type, sha = parts
        if obj_type != "blob":
            raise ScopeError(f"scope path is not a blob in the committed tree: {path} ({obj_type})")
        if path in entries:
            raise ScopeError(f"duplicate committed-tree entry for {path}")
        entries[path] = (mode, sha)
    # every scope entry must resolve to >=1 committed blob: a file entry to
    # itself, a dir entry to at least one blob beneath it (the review artifact
    # is already excluded upstream, so absence here is a genuine
    # unfrozen-candidate error — e.g. a sibling-landed surface added to the
    # manifest before the sibling's commit is merged).
    for spec in scope:
        if spec not in entries and not any(p.startswith(spec + "/") for p in entries):
            raise ScopeError(f"scope entry absent from the committed tree (HEAD); freeze the candidate commit before binding: {spec}")
    lines = [f"{entries[p][0]} {entries[p][1]} {p}\n" for p in sorted(entries)]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def recorded_digest(artifact: Path) -> str:
    matches = _DIGEST_RE.findall(artifact.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise ScopeError(f"artifact must carry exactly one 'Reviewed-Scope-Digest: <64-hex>' line (found {len(matches)})")
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="COG-4 review-to-bytes binding")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--print", action="store_true", dest="do_print", help="print the scope digest over HEAD")
    group.add_argument("--verify", metavar="ARTIFACT", help="recompute over HEAD and compare to the recorded digest")
    args = parser.parse_args(argv)
    try:
        digest = compute_digest()
        if args.do_print:
            print(digest); return 0
        artifact = Path(args.verify)
        if not artifact.is_absolute():
            artifact = ROOT / artifact
        recorded = recorded_digest(artifact)
        if recorded != digest:
            print("COG-4 review binding: BLOCK — reviewed bytes != tested bytes\n"
                  f"  recorded Reviewed-Scope-Digest: {recorded}\n"
                  f"  recomputed over HEAD:           {digest}", file=sys.stderr)
            return 1
        print(f"COG-4 review binding: OK — tested bytes match the reviewed scope digest ({digest})")
        return 0
    except ScopeError as exc:
        print(f"COG-4 review binding: BLOCK — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
