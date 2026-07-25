# FW-019 checkpoint review — feat/counterparty-commitment cp1

The **counterparty** noun landed as code; the **commitment** noun landed as a
Captain-gated proposal. Branch `feat/counterparty-commitment` from master
`05871f128da8e2be9e94e50ff531f35f6f9bd719`. >300 lines ⇒ this artifact (FW-019).

## Premise check (measured at 05871f12, 24 commits past the assessor's 138a2532)

Every file:line claim in the brief re-confirmed UNCHANGED on current master:

| claim | status |
|---|---|
| `framework/channels/contract.py:363` — `def send(self, recipient: str, ...)`, recipient is one bare string | CONFIRMED, same line |
| `framework/channels/contract.py:260` — `classify_recipient(recipient, org_domains) -> internal\|external` is the seam | CONFIRMED, same line |
| `framework/schemas/evidence-event.schema.json:37` — actor `kind` enum `["captain","system","surface","officer","verifier"]`, no non-Captain human | CONFIRMED, same line |
| `instance/config/act-first-surfaces.yml:87-90` — `create-not-mention-people` bans people\|person\|assignee\|subscriber\|owner keys | CONFIRMED, same lines |
| no `commitment` action_type / risk_class / ceiling category / config key | CONFIRMED (`ACTION_TYPES`=30, `RISK_CLASSES`=13, `HARD_CEILING_TOUCHES`=6) |

**Two premise REFINEMENTS** — the brief's "ZERO representation anywhere in the
tree" is too strong in both halves, and both corrections helped:

1. **`instance/config/peers.yml{,.example}` IS a non-Captain-party registry** —
   for peer *cabinets*, with `id / role / capacity / trust_level /
   consented_by_captain / allowed_tools`. That is exactly the shape asked for,
   already proven for machines and never applied to people. The registry below
   is deliberately that schema, not a new invention.
2. **`framework/cortex/belief.py:48` already carries `commitment`** in the
   closed epistemic `KINDS` frozenset (beside `entity` and `relationship`). So
   the noun exists in the *shadow world model*; the brief's narrower claim — no
   action type, risk class, ceiling category, classifier branch or config key —
   is the one that holds, and is what the proposal addresses.

## What landed (code)

- **`framework/channels/counterparty.py`** (NEW, the only new module) — closed
  `CONSENT_STATES`/`KINDS`/`RELATIONSHIPS` vocabularies, a frozen
  `Counterparty`, a realpath-contained fail-closed YAML loader, and the pure
  predicates `resolve` / `consent_of` / `outbound_permitted` / `journal_fields`.
  Every malformation resolves to the EMPTY registry; one bad entry or a
  duplicate handle corrupts the WHOLE file so a typo can never
  best-effort-consent its siblings. No wildcard scope exists.
- **`framework/channels/contract.py`** (+33 non-comment lines) — the registry
  resolves once beside `org_domains`, a `counterparty()` accessor, and three
  closed-vocabulary keys stamped into the audit payload `_base_payload` already
  writes per send attempt. `classify()` / `action_type_for()` / `send()`
  behaviour is byte-identical.
- **`instance/config/counterparties.yml.example`** (NEW, tracked twin) —
  placeholder only, `consent: pending`, `channels: []`. No real party enters the
  repo; the live `counterparties.yml` is deployment-created and untracked.
- **`cabinet/config/cognitive-architecture-contract.yml`** — two temporary
  allowances at the EXACT measured totals (see budget note below).

## What did NOT land, and why (the honest half)

`docs/proposals/germline-amendment-commitment-ceiling-2026-07-25.md` carries the
`commitment` risk class as a Captain-gated amendment rather than code. Four
independent walls, any one sufficient:

1. **Germline `schg`** — `classifier.py`, `matrix.py`, `policy_engine.py`,
   `grants.py` are in the locked `FILES` set; `framework/policies/` (holding
   `authority-matrix.yml`) is a locked `DIRS` entry.
2. **Three deliberate enum-growth pins in shipped tests** would have to move:
   `test_matrix.py:164` (`len(HARD_CEILING_TOUCHES)==6`),
   `test_cog4_exit_fixtures.py:533` (`len(RISK_CLASSES)==13`),
   `test_cog4_organ_manifest.py:570` + `test_cog4_trajectory_v2.py:339`
   (`len(ACTION_TYPES)==30`). The COG-4 contract names these "kept enum-growth
   mutants" — moving them IS the ceremony, and no build wave may edit tests.
3. **Zero-headroom vocabulary budget** — `central_action_types.maximum: 30` with
   `observed == max` by design.
4. **A structural design gap the brief itself named**: today's `hard_ceiling` is
   NOT hard by construction. `authority-matrix.yml:233-238` maps every ceiling
   row to `standing_grant` under sovereign and
   `policy_engine.py:1566-1585` resolves that into an attributed allow.
   Delivering "no posture and no standing grant may auto-resolve it" needs a
   NEW ungrantable-ceiling tier — a validator invariant plus a runtime branch —
   which is a constitutional change, not a scaffold.

## Budget consumed — flagged deliberately

The cognitive-architecture census is a zero-headroom growth gate, and this
branch is the first non-COG phase to consume it after `captain-contact-liveness`.
Declared at the exact measured totals, never a pre-allocated ceiling:
`framework_production_modules` +1 (239 observed, 239 effective) and
`framework_production_noncomment_lines` +356 (67290 / 67290), fully accounted as
323 (new module) + 33 (contract wiring). Two speculative read helpers
(`consented_ids`, `handles_of`) were REMOVED before measuring — no consumer, and
the standing bias is that machinery must not outrun value.

## Both-directions evidence

- **Against pre-change `contract.py`** (HEAD version restored, new files kept):
  6 arms RED — the five `TestTheDeliveredProperty` arms plus
  `test_journal_wiring_is_live`. Green after. This is the wiring proof.
- **The module is NEW, so absence-failure is worthless.** Ten targeted SOURCE
  MUTANTS in `TestMutantsBite` each re-exec the module with exactly one guard
  disabled and assert the property FLIPS: consent guard, scope guard,
  duplicate-handle guard, realpath containment, declared-`unknown` consent,
  whole-file corruption, free-text exclusion, handle normalization, id slug, and
  the contract-side journal wiring. `_mutant` asserts its anchor matched exactly
  ONCE, so a silently no-op mutation cannot certify an arm (verified: a bogus
  anchor and a 10-occurrence anchor are both refused).
- **Positive controls** throughout — a good registry loading non-empty, a
  granted+in-scope send permitted — so the refusal battery cannot pass
  vacuously against a loader that returns empty for everything.

## Gate deltas (serial, `python3.12`, `__pycache__` purged + `PYTHONDONTWRITEBYTECODE=1` before every run)

| gate | baseline @05871f12 | after | delta |
|---|---|---|---|
| `pytest framework/` | 1 failed / 6489 passed / 25 skipped | 1 failed / 6584 passed / 25 skipped | +95 passed |
| collection census | 6515 | 6610 | +95 |
| `pytest cabinet/scripts/tests` | 4543 passed / 28 skipped | 4543 passed / 28 skipped | 0 |
| `pytest cabinet/scripts/lib/tests` | — | 236 passed | — |
| `pytest cabinet/scripts/task_adapters/tests` | — | 38 passed | — |
| `check-layer-separation.sh` | baseline=24 allowlist=19 current=43 new=0 | identical | 0 |
| `cog2-import-gate.py` | OK | OK | 0 |
| `cognitive-architecture-census.py` | PASS | PASS (observed==max both) | 0 |
| `verify-cognitive-architecture.sh` | — | PASS | — |
| `run-golden-evals.sh` | — | 29/29 PASS | 0 |
| `test_no_launcher_hardcode` + `test_clean_room` | — | 24 passed | — |

The single `framework/` failure is the KNOWN pre-existing red
`test_retro_shim.py::TestRetroShim::test_reexports_constants` (out-of-repo
screenpipe retrodiction library; CI never collects it) — present identically in
the re-measured baseline.

One full-suite run showed 26 skips instead of 25; the extra was
`test_run_e2e_smoke.py:222 live deps unavailable: ['oauth: claude -p did not
return AUTH_OK']` — an external auth probe. Re-run 3× on the changed tree: 9
passed each time. Environment-driven, not this diff.

## Review notes / residual

- **The layer-separation gate initially flagged the TEST file**, not the module
  (`FRAMEWORK_PATH_INSTANCE`). Fixed by composition, not by a baseline bump: the
  test now derives its config segments from `C._INST_CFG`, so it cannot drift
  from the real path and the guarded token never appears. Baseline untouched.
- **`outbound_permitted` has no caller by design.** Wiring it into `send()`
  would silence every outbound path on any cabinet without a registry. Stated in
  the module docstring, and it is proposal §6 question 3.
- **The loader does not detect a Captain handle.** "The Captain is never a
  counterparty" is doctrine this code does not enforce; the docstring says so
  rather than implying a wall that isn't there.
- **`display_name`/`notes` never reach the ledger** (Corridor guidance: audit
  fields derived from config stay static identifiers). Mutant-armed.
