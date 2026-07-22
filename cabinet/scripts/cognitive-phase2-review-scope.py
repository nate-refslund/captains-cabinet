#!/usr/bin/env python3
"""Bind the frozen COG-2 review to the exact implementation bytes.

Phase-local twin of cabinet/scripts/cognitive-phase1-review-scope.py (§12.3 —
the Phase-0/1 instances are digest-frozen historical and stay untouched;
parameterizing them would edit frozen gate archaeology, so COG-2 clones the
pattern instead). Shared-routine extraction stays deferred (recorded debt,
owner cognitive-core-program).

Scope = (manifest.remove MINUS the review artifact) UNION manifest.restore_from_baseline
= the COG-2 implementation path set. Excludes the review artifact (records the
digest -> non-self-referential) and the two append-only operative ledgers (they
take the later COG-2 status flips). Everything else that can change COG-2
behavior — including the manifest and THIS tool — is bound.
Digest = SHA-256 over sorted newline-joined "<mode> <sha> <path>" from
`git ls-tree HEAD` (committed tree; mode-bearing; never working tree or index).
  --print              print the digest over HEAD
  --verify <artifact>  recompute over HEAD, compare to the single Reviewed-Scope-Digest line
Read-only, fail-closed, requires a git work tree. Private-side (egg-excluded).
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "docs/plans/cognitive-core-phase-2-rollback-manifest-2026-07-22.yml"
REVIEW_ARTIFACT = "shared/interfaces/reviews/cognitive-core-phase-2-review.md"
EXPECTED_SCOPE = frozenset({
    # remove (committed units 1-4, baseline_sha..HEAD "A")
    "cabinet/config/cortex-source-trust.v1.yml",
    "cabinet/scripts/cog2-belief-hash.py",
    "cabinet/scripts/cog2-parity-falsifier.py",
    "cabinet/scripts/cog2-rebuild.py",
    "cabinet/scripts/cog2-verifier.py",
    "cabinet/scripts/tests/lib_cog2_envelope.py",
    "cabinet/scripts/tests/test_cog2_asof_fence.py",
    "cabinet/scripts/tests/test_cog2_consequence_seam.py",
    "cabinet/scripts/tests/test_cog2_contradiction.py",
    "cabinet/scripts/tests/test_cog2_corruption.py",
    "cabinet/scripts/tests/test_cog2_fencing.py",
    "cabinet/scripts/tests/test_cog2_parity.py",
    "cabinet/scripts/tests/test_cog2_provenance.py",
    "cabinet/scripts/tests/test_cog2_rebuild_determinism.py",
    "framework/cortex/__init__.py",
    "framework/cortex/adapters.py",
    "framework/cortex/belief.py",
    "framework/cortex/engine.py",
    "framework/cortex/query.py",
    "framework/schemas/domains/cortex/belief.v1.json",
    "framework/schemas/domains/cortex/source-trust.v1.json",
    "framework/schemas/domains/observations/observation.v1.json",
    "shared/interfaces/reviews/feat-cog2-unit1-rebuild-core-cp1.md",
    "shared/interfaces/reviews/feat-cog2-unit2-query-fence-cp1.md",
    "shared/interfaces/reviews/feat-cog2-unit3-consequence-cp1.md",
    "shared/interfaces/reviews/feat-cog2-unit5-complete-cp1.md",
    # remove (unit-5 landing wave new files) MINUS the review artifact
    "cabinet/scripts/cog2-import-gate.py",
    "cabinet/scripts/tests/test_cog2_import_gate.py",
    "cabinet/scripts/tests/test_cog2_parity_wiring.py",
    "cabinet/scripts/verify-cognitive-phase2.sh",
    "cabinet/scripts/cognitive-phase2-review-scope.py",
    "cabinet/scripts/cognitive-phase2-rollback-rehearsal.py",
    "cabinet/scripts/tests/test_cognitive_phase2_rollback.py",
    "docs/plans/cognitive-core-phase-2-rollback-manifest-2026-07-22.yml",
    # restore_from_baseline (the extended files)
    "cabinet/config/cognitive-architecture-contract.yml",
    "cabinet/scripts/evidence-coverage.py",
    "framework/fidelity/consequence.py",
    "cabinet/scripts/cabinet-doctor.sh",
    "cabinet/scripts/task-sync-drift-falsifier.py",
    "cabinet/scripts/egg-export-manifest.txt",
    "cabinet/scripts/tests/test_egg_export.py",
    "cabinet/scripts/tests/test_task_sync_drift_falsifier.py",
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
    out = _git("ls-tree", "-z", "HEAD", "--", *scope)
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
    missing = sorted(set(scope) - set(entries))
    if missing:
        raise ScopeError(f"scope path(s) absent from the committed tree (HEAD); freeze the candidate commit before binding: {missing}")
    lines = [f"{entries[p][0]} {entries[p][1]} {p}\n" for p in sorted(entries)]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def recorded_digest(artifact: Path) -> str:
    matches = _DIGEST_RE.findall(artifact.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise ScopeError(f"artifact must carry exactly one 'Reviewed-Scope-Digest: <64-hex>' line (found {len(matches)})")
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="COG-2 review-to-bytes binding")
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
            print("COG-2 review binding: BLOCK — reviewed bytes != tested bytes\n"
                  f"  recorded Reviewed-Scope-Digest: {recorded}\n"
                  f"  recomputed over HEAD:           {digest}", file=sys.stderr)
            return 1
        print(f"COG-2 review binding: OK — tested bytes match the reviewed scope digest ({digest})")
        return 0
    except ScopeError as exc:
        print(f"COG-2 review binding: BLOCK — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
