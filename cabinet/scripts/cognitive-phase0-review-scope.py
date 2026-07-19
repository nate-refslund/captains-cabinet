#!/usr/bin/env python3
"""Bind the frozen COG-0 review to the exact candidate bytes.

Scope = (manifest.remove MINUS the review artifact) UNION manifest.restore_from_baseline
= 20 Phase-0 paths. Excludes the review artifact (records the digest -> non-self-referential)
and the two append-only operative ledgers (receive the later COG-0=done flip). Everything else
that can change Phase-0 behavior — including the manifest and THIS tool — is bound.
Digest = SHA-256 over sorted newline-joined "<mode> <sha> <path>" from `git ls-tree HEAD`
(committed tree; mode-bearing; never working tree or index).
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
MANIFEST = ROOT / "docs/plans/cognitive-core-phase-0-rollback-manifest-2026-07-19.yml"
REVIEW_ARTIFACT = "shared/interfaces/reviews/codex-cognitive-foundry-masterplan-cp1.md"
EXPECTED_SCOPE = frozenset({
    "cabinet/config/cognitive-architecture-contract.yml",
    "cabinet/scripts/cognitive-architecture-census.py",
    "cabinet/scripts/cognitive-phase0-review-scope.py",
    "cabinet/scripts/cognitive-phase0-rollback-rehearsal.py",
    "cabinet/scripts/tests/test_cognitive_architecture_census.py",
    "cabinet/scripts/tests/test_cognitive_phase0_rollback.py",
    "cabinet/scripts/verify-cognitive-architecture.sh",
    "cabinet/scripts/verify-cognitive-phase0.sh",
    "docs/cognitive-core-foundry.md",
    "docs/plans/cognitive-core-phase-0-contract-2026-07-19.md",
    "docs/plans/cognitive-core-phase-0-rollback-manifest-2026-07-19.yml",
    "framework/evolution/__init__.py",
    "framework/evolution/contracts.py",
    "framework/evolution/tests/__init__.py",
    "framework/evolution/tests/test_contracts.py",
    "framework/schemas/cognitive-trajectory.schema.json",
    "framework/schemas/holdout-evaluation-receipt.schema.json",
    "cabinet/scripts/egg-export-manifest.txt",
    "cabinet/scripts/null-hatch.sh",
    "cabinet/scripts/tests/test_egg_export.py",
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
    parser = argparse.ArgumentParser(description="COG-0 review-to-bytes binding")
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
            print("COG-0 review binding: BLOCK — reviewed bytes != tested bytes\n"
                  f"  recorded Reviewed-Scope-Digest: {recorded}\n"
                  f"  recomputed over HEAD:           {digest}", file=sys.stderr)
            return 1
        print(f"COG-0 review binding: OK — tested bytes match the reviewed scope digest ({digest})")
        return 0
    except ScopeError as exc:
        print(f"COG-0 review binding: BLOCK — {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
