# FW-019 checkpoint review — feat/cog5-w1 cp1 (wave landing)

COG-5 W1 wave landing: units **u0** + **u1** integrated onto master and shipped
as one reviewed batch. Landing branch `feat/cog5-w1` = u1 tip + a clean merge of
origin/master. >300 lines in the batch ⇒ this artifact (FW-019).

## Chain

- Base `90bf31d9` (COG-5 phase contract of record, #190) — both units built on it.
- **u0** `450e0e46` — "COG-5 W0-obligations unit u0: contract editorial fixes +
  S0 baseline landed + COG-1 park refresh".
- **u1** `8b346517` — "COG-5 W1 u1: Foundry boundary rows + AST pins + Stage-A
  holdout freeze + foundry gitignore" (contains u0; ancestry verified).
- Master moved past the base while the units built: `90bf31d9 → 21df33c9` (the
  doc-hygiene pair: `cabinet/cron/role-evals-weekly.sh` + the cross-officer-retro
  skill twins). File-disjoint from the units' whole surface (verified: zero
  overlapping paths) ⇒ merged origin/master INTO the branch: `a18ad9a3`.
- Integrator re-bind commit `d5134c94` (COG-4 §15 digest, below), then this
  artifact.

## Unit verdicts (adversarial review, Fable panel)

- **u0 — SHIP, first pass.** The W0 editorial+baseline unit: contract pointer
  fixes to the landed germline-amendment filename, F-2/F-3 applied for real, the
  **changelog-truth correction** (§ changelog now states honestly that only F-1
  changed bytes at the W0 landing; F-2/F-3 were no-op'd there), the S0 baseline
  of record (`docs/plans/cog5-s0-baseline-2026-07-24.md`, NEW), and the COG-1
  park-marker refresh (PARK CONTINUES 2026-07-24; marker only). Zero obligation
  bytes, zero code.
- **u1 — SHIP, first pass.** Boundary-manifest ROWs 8/9/10 (holdout_gen
  module sweep / foundry-archive data-plane / evolution reverse), ROW 6
  byte-untouched (the deliberate non-extension), 3 vacuity-armed sibling AST
  pins + the Stage-A holdout content pin, the egg delete/expect-absent
  exclusion pair, and the `shared/interfaces/foundry/` gitignore row + test.
  **NOTHING in this unit claims Ring-0** — the Stage-A freeze is honestly an
  INTERIM CI tripwire (`test_cog5_holdout_pin.py` docstring + egg-manifest
  comments state it; Ring-0 lands at a Captain germline-unlock window, §7.5
  Stage B). Unit detail: `shared/interfaces/reviews/feat-cog5-w1-u1-cp1.md`.

## Integrator obligation — COG-4 §15 frozen-review digest re-bind

u1's sanctioned §10 rows extension moved `cabinet/config/boundary-manifest.yml`,
which sits in the COG-4 frozen-review digest scope. The established mechanical-
delta ceremony (the COG-4 W3-landing/cp3 precedent) was performed:

- **(a) Delta audit:** diffing the resolved 85-entry scope over the last
  binding (`70bca2ae`) → HEAD shows EXACTLY two moved paths, both rows-only
  insertions: `cabinet/config/boundary-manifest.yml` (+103: ROWs 8/9/10) and
  `cabinet/scripts/egg-export-manifest.txt` (+15: the Stage-A vacuity-armed
  holdout delete/expect-absent pair). The COG-5 contract doc and the operative
  ledger are OUTSIDE phase-4 scope; the parallel master doc-hygiene pair
  (`21df33c9`) moved ZERO in-scope paths. Zero engine/behavior bytes.
- **(b) Claim surface re-run on the merged bytes:** boundary harness
  `test_cog4_boundary_rows.py` (generic per-row mutant generator — a biting
  mutant auto-generated per NEW row) + `test_cog5_boundary_rows.py` (content
  pins): **113 passed**; `cog2-import-gate.py` **rc 0**; full `test_cog4_*`
  battery **702 passed, 2 declared skips**; armed `cog4-measure --check`
  within bound.
- **(c) Re-bind:** `cognitive-phase4-review-scope.py --print` →
  `95e6ea8bf1288655a488342ea2675e515d7332829c2ff623664db5cd23a10c42` →
  `093e586636ea40716d353508429439d099adc54e48b574aa1efa6860debe0ff6`; embedded
  + dated administrative note appended in the frozen review; `--verify` **rc 0**.
  Verdict unchanged **PASS** (a re-bind, never a restamp).
- **(d) Twin:** `verify-cognitive-phase4.sh` **FULL GREEN** end-to-end after
  the re-bind (armed measure leg, review binding, pointer tripwire,
  architecture gate + golden evals 29/29, battery, census, import gate, A13,
  egg battery, rollback rehearsal PASS with the compose-revert arm ARMED),
  closing READY_FOR_CI.

## Landing verification (this clone, python3.12)

- **Full sweep, integration branch:** `cabinet/scripts/tests` **3399 passed,
  12 skipped, 0 failed, rc 0**.
- **Full sweep, pristine master (`21df33c9`), same environment:** **3319
  passed, 12 skipped, 0 failed, rc 0**. Delta = +80 collected, fully
  explained: 67 tests in the six new `test_cog5_*` files + 13 auto-generated
  per-row cases in `test_cog4_boundary_rows.py` from ROWs 8/9/10 (689 → 702
  matches the W6 frozen-review battery count). **Zero unexplained.**
- **The 2 pre-existing environment failures u1 documented** (its hermetic
  clone: `test_observe_only.py::test_native_secret_reads_block_direct_and_realpath_aliases`
  FAILED; `test_world_asset_{forge,intake}.py` collection errors, missing PIL)
  **reproduce on NEITHER tree in this landing environment** — both sweeps
  fully green here. Confirmed environment-local exactly as u1 recorded (green
  in the S0 baseline on the launching instance and on master CI 30110130410).
  Recorded; nothing fixed.
- Census **PASS**, all 10 budgets **observed==max UNCHANGED** (91/30/52/40/
  24/19/236/66548/1/3 — test files + config rows only, zero framework delta).
- `check-layer-separation.sh` **new=0**; `ledger-status-parity.sh` **GREEN
  (ids=352 md_rows=352 findings=0)**; A13 heredoc **OK, 352 rows exact**;
  HEAD-bytes ledger YAML **parses** (352 entries).
- Egg battery `test_egg_export.py` **58 passed, 1 declared skip** — the
  exporter lands u1's EXCLUDE/expect-absent rows green (vacuity-armed until
  W5).

Provenance: per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 W1 landing integrator).
