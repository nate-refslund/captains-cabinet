# Review artifact — feat/cog2-unit2-query-fence cp1 (COG-2 unit 2)

FW-019 batch review for COG-2 UNIT 2 of the Cortex shadow temporal world model:
the AS-OF QUERY API + TEMPORAL-FENCE + CONTRADICTION/UNKNOWN, tests-first,
built on the landed unit-1 core (origin/master `7f44a3ed`). Diff vs base ≈ 1,255
changed lines (1,207 insertions / 48 deletions) — mostly the two new gate suites
(574) + query.py (243) + the envelope-file adapter (132) → FW-019 artifact
required at commit time; this is it. Authored per the 2026-07-07 full-autonomy
grant + the 2026-07-20 cognitive-masterplan continuous grant.

Plan of record: `docs/plans/cognitive-core-phase-2-contract-2026-07-22.md`
(§4 belief record, §5.2a envelope-file adapter, §5.5/§5.6 query + contradiction/
unknown law, §8 sim 2 temporal-fence, §8 sim 3 contradiction+unknown).

## What changed (6 files framework/config + 3 tests + 1 schema)

- **`framework/cortex/query.py` (NEW, 243)** — the as-of query API. `as_of()`
  fences on observation_time and/or source_time (inclusive-≤; leak predicate
  `ts > cutoff`, C-F8), RE-DERIVES status/superseded_by/contradicts PER CUTOFF
  over the fenced sub-history via `engine.resolve_relationships` (C-F7 — never
  reads back the stored full-history status). Returns ONLY the full-tuple
  `BeliefView` (belief_id, value?, source_trust, provenance, status,
  conflict_set; confidence bundled with source_trust — **no bare-scalar
  confidence accessor**, G-F3 SHAPE guard). The unknown/purged/denied triad is
  explicit: zero-evidence → `AsOfResult.is_unknown()`; source_purged-only → a
  status-bearing view (never unknown); missing/foreign/unresolvable scope →
  `ScopeError` (HARD ERROR, never empty-success — §7.4). `load_beliefs()` reads a
  stored `beliefs.jsonl` read-only (serve-time store-hash binding C-F15 is a
  later unit, stated).

- **`framework/cortex/adapters.py` (+132)** — the §5.2a envelope-file adapter:
  `read_envelope_file()` reads a v2 envelope JSONL read-only; every line is
  `validate_any`-gated AND cabinet-scoped FAIL-CLOSED (invalid / absent-or-
  foreign cabinet_id / payload_ref-without-inline-subject / malformed-JSON →
  QUARANTINED with a receipt, never a silent skip — C-F19). Each valid envelope
  → one observation proto with `source_time := occurred_at`,
  `observation_time := recorded_at` (the only real two-clock path in the slice).
  Derivation pinned mechanically (never heuristic content comparison, §4):
  subject_key = `<schema domain>/<payload.subject>`, dimension = the
  payload_schema `<domain>/<name>`, kind = `observation`,
  intra_stream_seq = file line index (deterministic source order).

- **`framework/cortex/engine.py` (net +~90)** — extracted the SHARED pure
  `resolve_relationships()` (supersession WITHIN a producer lineage by source
  order; independent current lineages on one subject+dimension cross-link — the
  contradiction post-pass) and `derive_status()`. `fold()` now USES them (the
  `len(heads) > 1` branch unit-1 left DEAD is now LIVE — a two-producer group
  reaches it) and gains a `lineage=` param. The query re-runs the SAME
  derivation per cutoff, so fold and query cannot drift.

- **`framework/cortex/belief.py` (+26)** — `belief_from_row()`, the inverse of
  `to_canonical_dict()` for the query/serve load path.

- **`framework/schemas/domains/observations/observation.v1.json` (NEW)** — the
  envelope-file belief-seam payload schema (closed Draft-2020-12 subset; requires
  `subject` + `state`). The two-axis + two-producer proof seam AND the shape a
  future envelope-durable source declares; no production feed this phase.

- **`framework/schemas/domains/cortex/source-trust.v1.json` + `cabinet/config/
  cortex-source-trust.v1.yml`** — ADDITIVE envelope-file producers
  (`observations/primary` 800000, `observations/secondary` 500000): component
  identities, never officer identities (G-F4 latch). `table_version` stays 1 —
  additive keys change no existing belief's confidence, so the outbox's hash
  lineage is untouched (not an epoch bump in effect; stated at the edit site).

- **`cabinet/config/cognitive-architecture-contract.yml`** — COG-2 allowances
  bumped to EXACT running totals, zero headroom: modules 4→5 (query.py),
  noncomment-lines 492→832 (+340 measured). observed==max.

- **Two gate suites (NEW, 574) + `lib_cog2_envelope.py` (NEW, 97)** — see below.

## Verification (python3.12; pg17 on PATH for the unit-1 tier)

- **`test_cog2_asof_fence.py` + `test_cog2_contradiction.py`: 32 passed.**
  - Fence (§8 sim 2): as-of(observation=T2)=pre-correction "open",
    as-of(observation=T4)=corrected "closed"; as-of(source=S1, observation=now)
    distinguishes axes; DERIVED state re-derived per cutoff (T2 shows asserted,
    empty conflict, no superseded_by) with a CLOSURE assertion at every cutoff;
    inclusive-≤ same-second seed. Two-axis runs THROUGH the envelope-file adapter
    (production tasks-outbox is single-clock — declared openly).
  - Contradiction (§8 sim 3): two producers coexist cross-linked with per-side
    provenance + confidence; unknown-stays-unknown → explicit `unknown`;
    purged-only → source_purged (never unknown); scope-mismatch → `ScopeError`.
  - **Mutants that bite in-suite:** source_time-only fence LEAKS the correction;
    stored-final-status server fails the T2 assert; silent-LWW (`lineage="merged"`)
    drops a contradiction side; correlation-keyed lineage wrongly contradicts the
    same-producer disjoint-correlation pair (pinned verdict = supersedes);
    default-for-unknown returns a non-unknown; lenient-scope masquerades denial
    as ignorance; the never-a-score ratchet flags a synthetic bare-scalar accessor.
- **`test_cog2_rebuild_determinism.py` (unit 1): 40 passed** — no regression from
  the fold refactor (single-producer groups are byte-identical: one producer =
  one lineage = the old single chain). Combined COG-2 run: **72 passed.**
- **Census GREEN, zero headroom:** `cognitive-architecture-census.py --check` →
  PASS (modules 214<=214, noncomment-lines 63129<=63129). `test_cognitive_
  architecture_census.py` + `test_evidence_coverage.py`: 41 passed.
- **Evidence-coverage clean:** only `framework/cortex/belief.py` imports
  `framework.evidence` (query.py + the adapter do NOT), so the existing
  `cortex-projection-shadow` row is unchanged and `evidence-coverage.py`
  reconciles (exit 0, unenumerated []).
- **Shadow boundary:** grep confirms ZERO references to `framework.cortex` from
  any .py outside the cortex package and the cog2 tooling — no authority/action
  importer. query.py/adapter import only own-package + (adapter) the allowlisted
  `framework.triggers.{envelope,schema_registry}`; import-inert at package level.

## Honesty declarations (per the foundry's own law)

- **Two-axis fence is proven through the envelope-file adapter, not a production
  feed** (§1 M2 / A-B1): the outbox is single-clock; the envelope-file adapter is
  the real two-clock fold/query path with no production source this phase. No
  test-only ingest seam — the sims write a JSONL the production `read_envelope_
  file` reads (C-F4/C-F9).
- **Contradiction is a declared FIXTURE-proof through production code** (§1 M3 /
  C-F10): no production pair in this slice can contradict; the first
  contradiction-capable source pairing is a named next-phase obligation.
- **Envelope producers are additive** to the version-1 trust table + enum (the
  contract sanctions "later units extend the enum as adapters land").

## What UNIT 2 does NOT cover (later COG-2 units)

- The SQLite query index + serve-time store-hash binding (C-F15, sim 5).
- The consequence adapter + `iter_ledger_rows()` (unit 3 / §5.4).
- The full cross-cabinet suite: sentinel ids, `classification: cross_cabinet`,
  quarantine-receipt-to-file (sim 7) — the adapter ships the fail-closed CORE.
- The net-new AST import gate + grep/data-plane sweep + `cortex_ro` role
  provisioning (§7.1/§7.2, sim 7); the standing bare-scalar ratchet lives as an
  in-suite test here and graduates to a permanent CI gate in that unit.
- Source purge (§5.4b, sim 4) is exercised at the QUERY level only (a purged
  proto → source_purged, never unknown); the outbox tombstone path is sim 4.
- M6 latency/storage measurement.
