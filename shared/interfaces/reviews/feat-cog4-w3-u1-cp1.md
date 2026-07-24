# FW-019 review artifact — feat/cog4-w3-u1 cp1 (C3 projection-kernel extraction)

Unit: COG-4 W3 u1 (contract cognitive-core-phase-4-contract-2026-07-23
§6.1-§6.2; Fable-for-execution named unit). EXTRACTION, not invention: the
eight already-law-identical parts of the two shipped instantiations
(framework/cortex fold + framework/objectives graph) become
`framework/projection/kernel.py`, parameterized so BOTH shipped hash algebras
and manifest shapes stay expressible byte-identically. Cortex/objectives do
NOT adopt the kernel in this unit (u3/u4 own adoption, §6.4).

## Batch contents (1070 insertions, 5 files + this artifact)
- `framework/projection/__init__.py` (new, import-inert): package root imports
  nothing; `__all__ = []` (the cortex/objectives idiom).
- `framework/projection/kernel.py` (new, stdlib-only): (a) recorder-dialect
  canonical_bytes/digest (replicated stdlib — the tree may not import the
  recorder, §8.3 row 6); (b) identity_digest — content-excluded identity law;
  (c) chained_rows_hash parameterized by algebra (sha256-chain | digest-list)
  + seed + total-order + domain normalize — cortex (domain seed, id-order)
  and objectives (empty seed, canonical-bytes order) both expressible;
  (d) manifest_envelope {schema_version, epoch, <store-hash>, counts, extra}
  with collision/emptiness fail-louds; (e) atomic_write — O_EXCL 0o600 tmp +
  fsync + os.replace (engine.py:434-442 shape); (f) verified_single_read —
  F4 no-window single read, rows-hash key MANDATORY-PRESENT (absent key
  REFUSES — the objectives query.py:214-215 skip-hole closed for adopters),
  parameterized refuse factory + ordered extra-limb runner; (g) canonical-
  cutoff validator (the cortex/query.py:66 + objectives/graph.py:43 replica,
  now one definition); (h) rollback_delete — cache-delete
  reversible-by-rebuild, traversal-jailed.
- `cabinet/scripts/tests/test_cog4_kernel_parity.py` (new, 18 tests):
  byte-compat vs REAL stores — cortex store built by a tmp subprocess driver
  through the shipped fold/writer (engine.fold/build_manifest/
  write_projection; the DSN CLI needs live PostgreSQL, and §12 pins suites
  file-seeded/no-DSN — this file holds no framework.cortex import, per
  boundary row 1 allowlists); objectives graph built by the REAL
  cog3-rebuild.py CLI (file-seeded). Proven: store JSONL lines byte-equal
  kernel canonical bytes (both stores); belief_id/node_id equal
  identity_digest of the identity tuples; BOTH algebras reproduce
  belief_store_hash and graph_rows_hash exactly (+ tampered-row and
  wrong-algebra negative controls, shuffle invariance, seed-type fail-louds);
  manifest_envelope reconstructs both shipped manifests dict-equal;
  delete→rebuild restores both stores byte-identically (rollback grammar).
- `cabinet/scripts/tests/test_cog4_kernel_store.py` (new, 29 tests): atomic
  write crash-safety (subprocess dies at fsync / at replace → target keeps
  old bytes EXACTLY; O_EXCL squatter collision fails loud, target untouched;
  0o600 debris); verified single-read (exactly ONE store read, counted; rows
  stay bound after post-serve tamper; absent/null/empty/non-string hash key
  REFUSES; unreadable/non-dict manifest, malformed store, row-shape breaks
  all refuse via the domain factory; extra limbs run in declared order only
  AFTER the hash binding); cutoff validator (pattern literal equals BOTH
  shipped replicas by text-scan + accept/reject arms); kernel boundary
  (import-inert root; subprocess closure = exactly {framework,
  framework.projection, framework.projection.kernel}, forbidden planes
  empty; static AST pin — every import in the tree is stdlib).
- `cabinet/config/cognitive-architecture-contract.yml`: the FIRST COG-4
  temporary_allowances rows — modules +2 (228 vs 226), lines +295 (65307 vs
  65012) — EXACT measured running totals via cognitive-architecture-census.py
  (§11 zero-headroom law; observed==max on both after the rows; em-dash
  reasons; thresholds never raised).

## Review evidence (2026-07-24, scratch clone off origin/master 3ed25b11)
- New kernel batteries: 47/47 green (twice; durations show the subprocess
  fixtures + crash drivers really ran).
- FULL `cabinet/scripts/tests` sweep: 3057 passed / 44 skipped / 1 failed —
  the ONE failure is the DESIGNED companion trip
  `test_cog4_scheduler_ast_pin.py::TestSchedulerTransitiveClosure::
  test_real_trees_are_armed_and_absent` ("framework/projection/ has LANDED —
  retire this vacuity skip..."): its retirement is corpus surgery owned by
  the integrator (§13 corpus-immutable law — builders never edit tests).
  Armed-scan evidence for the integrator: subprocess closure of
  framework.projection AND framework.projection.kernel = zero forbidden-plane
  modules (rc=0, []); framework.scheduler / framework.organs still
  ModuleNotFound (their guards untouched). Zero unexplained failures.
- `cog2-import-gate.py`: exit 0 (row 6 fences the kernel; the new test files
  ride the test_cog4_* allowlist globs; no cortex/objectives import anywhere
  in the batch).
- `check-layer-separation.sh`: exit 0 (no instance literals in the new tree).
- Census `--check`: ok=true; modules 228/228, lines 65307/65307 (zero
  headroom, observed==max); duplicate-YAML-key scan clean (L1108).
- Corpus untouched: `git diff --stat` over cabinet/scripts/tests shows ONLY
  the two NEW test_cog4_kernel_*.py files — no existing test/lib edited.
