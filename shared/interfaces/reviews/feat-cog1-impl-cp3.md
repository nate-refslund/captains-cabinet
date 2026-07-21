# Review artifact — feat/cog1-impl checkpoint 3 (W3: relay table-drain)

Branch: feat/cog1-impl · Base: 0bf60e69 (origin/master merge of #165)
Plan: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §6 (table-drain
relay: claim → committed-id → token → adapter → record), §8.3 (per-cycle parity
freshness), §9.2 (adapter proof seam), §9.4 (lazy driver import / driver-less
collection), §10.1 (census allowance), §12.2 items 2-5/8-10b (sims battery).
S0 pin: production work store is PostgreSQL 17 — sims ran real PG 17.10, no skips.

## Verdict: APPROVE (independent adversarial review, Fable 5, fresh context)

FW-019 batch artifact for a >300-line commit: framework/outbox/relay.py is
+592/-87 (679 changed) — over the 300-line threshold, so this artifact is owed
at commit time (W1/W2 filed cp1/cp2).

File-set (this wave):
- framework/outbox/relay.py (MODIFY — table-drain path: claim/committed-id
  fencing, effective-status mapping, dispatch-field builder, table-adapter
  registry sibling `register_table_adapter()`/`_TABLE_ADAPTERS`, per-cycle
  shadow-stream mirror to `cabinet:tasks:events:shadow`, per-cycle parity
  sample; driver import stays LAZY inside the drain path).
- framework/outbox/tests/ (NEW — table-drain sims + effective-mapping +
  fencing + wrapper preflight): lib_relay_harness.py, test_relay_table_drain.py,
  test_effective_mapping.py, test_relay_fencing.py, test_outbox_relay_wrapper.py.
- cabinet/cron/outbox-relay.sh (MODIFY — relay drain wrapper).

## Commit-step obligations discharged in THIS commit (outside the wave file-set)

1. Census allowance (plan §10.1, LANDING GATE): the COG-1
   `framework_production_noncomment_lines` temporary_allowances row in
   cabinet/config/cognitive-architecture-contract.yml raised 517 → **916** —
   the census-measured EXACT total COG-1 delta (measured 62239 − pre-COG-1
   baseline 61323 = 916), no padding, no undersizing. Updated (not appended) so
   the effective maximum is exactly 62239; a duplicate row would over-budget.
   owner/sunset/deletion_gate unchanged. §10.3 gate-flip note already landed in
   W1 (95f3a10f, the first contract edit) — not re-added.
2. Docs-track-the-code (plan §9.2 wording): line 247 renamed the sanctioned
   harness seam `relay.register_adapter()` → `relay.register_table_adapter()`
   with the sibling-split rationale (table-drain signature
   `(fields, *, idempotency_key) -> None` ≠ legacy `AdapterFn` `(payload) -> None`
   — an internal registry split, never a second outbox). Grep of the plan for the
   bare old name is clean.

## Design dispositions (carried, non-blocking)

- Registry split is one table, one drain path — the "never a second outbox"
  invariant holds; the sibling seam disambiguates two incompatible signatures.
- Per-cycle parity: relay writes exactly one JSONL line per cycle (even a 0-row
  cycle), so a dead/never-armed relay writes zero lines = the intended fail-safe
  breach. Cross-wave note for the falsifier reader (task-sync-drift-falsifier.py,
  §12.2 item 7): the freshness floor must count parity LINES (one per cycle), not
  sum the per-line row-count field. Reconcile when that reader lands. Emission
  stays shadow-only regardless.

## Evidence re-run by the reviewer (house interpreter python3.12)

- framework/outbox/tests/ = **61 passed in 5.00s** (real PG 17.10 + redis
  sandbox, no skips): 17 table-drain sims + mutants, 15 effective-mapping +
  envelope round-trip, DB-backed fencing incl. zero-central-ledger-emit, 7
  wrapper preflight/python3.12-pin, 12 legacy test_relay.py backward-compat
  (unmodified).
- W3 explicit paths (table_drain + effective_mapping + fencing + wrapper) =
  **49 passed in 4.87s**.
- check-layer-separation.sh: baseline=24 allowlist=19 current=43 **new=0**.
- census --check: **PASS** — framework_production_noncomment_lines 62239 <= 62239
  (exact); duplicate_event_writer_sinks 3/3, central enums 91/91 & 30/30,
  framework_production_modules 209/209 all hold.
- Shadow-only emission: grep of relay.py for a BARE `cabinet:tasks:events`
  (not `:shadow`) = NONE; SHADOW_STREAM = `cabinet:tasks:events:shadow`.
- RED-before: all 6 new public symbols (register_table_adapter, SHADOW_STREAM,
  QUEUED_BY_MARKER, build_dispatch_fields, effective_old_status,
  _foreign_ledger_rows) absent at HEAD a091009c (grep -c = 0).
- Boundary: wave paths not in the germline set; ls -lO on relay.py +
  outbox-relay.sh clean (no schg).
