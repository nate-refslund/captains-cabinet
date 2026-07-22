# Checkpoint review — feat/cog2-unit3-consequence, cp1 (COG-2 unit 3: consequence seam + provenance/purge)

**Scope:** COG-2 (Cortex shadow temporal world model) UNIT 3 — the
consequence-ledger adapter (the "seam" proof, plan §2/§3/§5.4) plus the
provenance + purge sim (§8 sim 4), tests-first. Branch off `origin/master`
`e8c99eef`. Batch ~769 changed lines → FW-019 artifact required at commit time;
this is it. Seven files:

| file | change | production? |
|---|---|---|
| `cabinet/scripts/tests/test_cog2_consequence_seam.py` | NEW — the seam gate (equivalence, synthetic provenance, legacy validation, env-free fold, ts parse-or-absent) | test (excluded from census) |
| `cabinet/scripts/tests/test_cog2_provenance.py` | NEW — §8 sim 4 (universal provenance minimum, purge→delete→rebuild, mutants) | test |
| `framework/fidelity/consequence.py` | +51 lines — ADDITIVE `iter_ledger_rows()` only | framework |
| `framework/cortex/adapters.py` | +134/−9 — consequence adapter + tasks-adapter tombstone path | framework |
| `framework/schemas/domains/cortex/source-trust.v1.json` | +1 enum member (`framework/fidelity/consequence`) | schema |
| `cabinet/config/cortex-source-trust.v1.yml` | +1 producer (0.85 ppm, additive) | config |
| `cabinet/config/cognitive-architecture-contract.yml` | COG-2 line allowance 856→991 (exact +135) | config |

Production (non-test) framework/config lines changed: 202. Framework
non-comment line delta measured by the census: **+135** (adapters.py + the
additive iter_ledger_rows in consequence.py); no new module.

## What this unit proves (and what it deliberately does NOT)

**The SEAM (§2/§3/A-m12), not "hardest translation" (withdrawn) and not
cross-time supersession:**

1. **Translation-vs-collapse equivalence (§3 A-M6/C-F5):** the additive
   `iter_ledger_rows()` carries EVERY row `read_ledger()`'s last-write-wins
   collapse needs — the consequence adapter's per-identity chain HEADS equal
   `read_ledger()`'s survivors, on a fixture that includes multi-day files,
   same-ts enrichment pairs, a sim row, and a symlink escaping the ledger dir.
2. **Deterministic synthetic provenance (§5.4):** a legacy row has no
   `event_id`, so the adapter mints one deterministically —
   `digest("consequence:" + canonical row bytes)` — pinned byte-for-byte in the
   test; `producer=framework/fidelity/consequence`, `stream_rank=1`.
3. **Legacy-regime belief validation (A-M7):** the consequence-derived belief
   validates at the BELIEF level (`cortex/belief@1` + `cortex/source-trust@1`);
   the row is NEVER forced through `validate_any`.
4. **Env-free fold (O-B2 / §5.1):** `iter_ledger_rows` drops sim rows
   UNCONDITIONALLY (never reads `CABINET_SIM_MODE`), contrasted in-test against
   `read_ledger`'s env-sensitive drop — no environment variable is a fold input.
5. **ts parse-or-absent (C-F6):** fractional/offset ts canonicalize to the single
   UTC-second spelling; garbage yields honest absence, never passthrough.
6. **Provenance + purge (§8 sim 4):** universal provenance minimum on every
   belief; empty provenance is a validation error; a source-side tombstone
   (payload NULL'd) flips the belief to `source_purged` with lineage intact and
   survives projection delete + rebuild-from-zero (identity survives content loss
   because `belief_id` never embeds claim bytes — A-B3/C-F12).

**Out of scope (units 4-5, unchanged by this batch):** the verifier/parity
(`cog2-parity-falsifier.py`), corruption+gap and cross-cabinet+boundary sims, the
net-new AST import gate, the two-regime provenance-laundering enforcement (C-F13 —
`belief.v1.json` still defers it by its own note), serve-time hash binding, the
`cortex_ro` role seam, and the M6 measurement harness. Consequence-side purge is
also out of scope (§5.4b — a consequence day-file deletion is a GAP, sim 5); the
purge arm here runs on the OUTBOX stream only.

## Safety / boundary verification

- **Additive, shadow-only:** `iter_ledger_rows()` is a pure new reader —
  `read_ledger()` and every existing consequence function are byte-unchanged
  (`git diff` shows 51 insertions, 0 deletions on consequence.py). Verified.
- **Reverse-import allowlist (§7.1 G-F1) respected:** the consequence adapter
  imports ONLY `iter_ledger_rows` from `framework.fidelity.consequence`; it reuses
  the domain's OWN fences (`_safe_ledger_files` symlink fence, `_is_consequence_row`
  shape filter) rather than cloning them. The ts-inclusive identity tuple is
  reconstructed inline (mirroring `consequence._identity`) with the seam
  equivalence test as the standing drift tripwire.
- **Zero authority/action reach:** grep confirms no `framework.cortex` import from
  `framework/{authority,acting,frontdoor,learning,roles,missions}`.
- **Evidence-coverage clean (exit 0):** adapters.py trips no evidence-import /
  `emit_consequence` detector (it routes hashing through `framework.cortex.belief`,
  not `framework.evidence`), so the `cortex-projection-shadow` enumeration is
  unchanged; consequence.py stays enumerated under `consequence-mirror`.
- **No germline path touched;** no `services.yml` / emitter / classifier /
  authority-matrix change.

## Gate evidence (python3.12, PostgreSQL 17 on PATH)

- `test_cog2_consequence_seam.py` + `test_cog2_provenance.py`: **25 passed**.
- Full COG-2 regression (unit-1 determinism + unit-2 fence/contradiction +
  unit-3): **108 passed** — determinism, temporal fence, and contradiction
  properties still hold (a belief-shape change is a within-unit hash change; the
  PROPERTY holds).
- `cognitive-architecture-census.py --check`: **PASS** — modules 214≤214, lines
  63288≤63288 (observed==max, zero headroom on both budgets).
- Structural-compaction census gate (`test_cognitive_architecture_census.py`):
  **29 passed**.
- `evidence-coverage.py`: **exit 0** (no drift).

Provenance: authored + self-ratified per the 2026-07-07 full-autonomy grant + the
2026-07-20 cognitive-masterplan continuous grant.
