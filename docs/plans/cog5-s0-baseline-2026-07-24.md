# COG-5 S0 GROUND RE-PIN — the §12.1.1 dated baseline of record (LANDED)

**Landed:** 2026-07-24 · **Unit:** COG-5 W1 u0 (the W0-obligations unit) · **Branch:** `feat/cog5-w1-u0` · **Model:** Opus 4.8 1M (execution tier) · **Ground tip:** `90bf31d9077a5500b58f4c3b3b8c98ac1507801a` (master; unchanged since the S0 pin) · **Provenance:** per the 2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan grant.

This document is the tracked, dated **§12.1.1 baseline of record** required by the COG-5 contract's §12.1 step 1 (`docs/plans/cognitive-core-phase-5-contract-2026-07-24.md`). Everything below the "S0 REPORT — VERBATIM BODY" marker is the S0 re-pin synthesis report reproduced **byte-for-byte** from the S0 unit's report. This landing header supersedes exactly ONE measurement in that body — the PROVISIONAL wall-clock bound — and records the W0 follow-ups the report parked; it changes NO other value and weakens no obligation.

## Wall-clock backfill — §12.1(c), n≥5 DISCHARGED (supersedes the body's PROVISIONAL n=3 bound)

The body's §5(c)/§9.1 recorded a PROVISIONAL bound over n=3 (the 6-run S0 loop was SIGTERM'd). W0 backfilled two more clean foreground runs of `verify-cognitive-phase4.sh` on the same clean tree at `90bf31d9` (python3.12 `time.sleep(15)` between; each run rc=0, tree clean before AND after, zero rollback-worktree leak):

| run | source | wall-clock (s) | rc |
|---|---|---|---|
| 1 | S0 | 181.4 | 0 |
| 2 | S0 | 181.8 | 0 |
| 3 | S0 | 183.0 | 0 |
| 4 | W0 backfill (2026-07-24) | 180.3 | 0 |
| 5 | W0 backfill (2026-07-24) | 180.9 | 0 |

Pooled n=5, sorted: `[180.3, 180.9, 181.4, 181.8, 183.0]`. **p95 = 182.76 s** (numpy `linear` interpolation — the same method that produced the body's 182.9 s at n=3). Floor-aware bound = **max(p95×1.25, p95+5s) = max(228.45, 187.76) = 228.4 s** (×1.25 dominates; the +5s floor is inert at this magnitude, as the body notes).

**FINAL BOUND (non-provisional): 228.4 s.** This SUPERSEDES the body's provisional 228.6 s. The delta is within noise (σ < 1 s across all five samples); the ≥5-run requirement (body §3 B-2) is now MET, so the bound is no longer PROVISIONAL. Downstream: the bound artifact + its arming flag are consumed by `verify-cognitive-phase5.sh` in the SAME commit that introduces them (the §12.1.3 anti-phantom law — a later-wave W7 act); this baseline only RECORDS the final value.

## Stray worktree cleanup — S0 §9 item 5 (NOTE only; do not rm)

The two SIGTERM'd S0 verify runs (body anomaly 13) leaked `cog4-rollback-*` rehearsal worktrees under `$TMPDIR`. They are OUTSIDE this unit's clone and were deliberately NOT removed here (a NOTE-only obligation). Paths, recorded for manual cleanup (`rm -rf` the dir + `git worktree prune` in whatever clone registered them, if it survives):
- `/var/folders/0d/crvcc7f51wl289dcgphkg5h40000gn/T/cog4-rollback-5hyu5qxq`
- `/var/folders/0d/crvcc7f51wl289dcgphkg5h40000gn/T/cog4-rollback-97n4rald`

The two W0 backfill runs above added NO new strays (complete runs self-clean; before/after checked each run).

## W0 obligation status (body §9)

Discharged in THIS unit (COG-5 W1 u0): item 1 (wall-clock backfill — above), item 3 (COG-1 park-marker refresh — in the operative ledger), item 4 (contract editorial fixes — B-1 / header staleness / F-2 / F-3 / changelog honesty; see the contract's own dated "W0 editorial pass" appendix), item 5 (stray-worktree NOTE — above), item 6 (this artifact, landed tracked). **NOT in u0's assigned scope:** item 2 — the E1-substrate baseline (case counts, corpus size) — was not assigned to this unit and is NOT measured here; it remains an open W0 obligation for its owning unit. This baseline does not claim W0 fully closed.

---

## S0 REPORT — VERBATIM BODY

*The remainder of this file is the S0 re-pin synthesis report, reproduced byte-for-byte from the S0 unit's `COG5-S0-REPORT.md`. Its own section numbering (§1–§11, anomalies, etc.) is what this header's cross-references point at.*

# COG-5 S0 GROUND RE-PIN — SYNTHESIS REPORT (addendum of record)

**Date:** 2026-07-24 · **Synthesis:** Fable 5 (S0, five-verifier fan-in) · **Phase:** COG-5 (Evolutionary Foundry E1/E2/E3 in shadow), contract `docs/plans/cognitive-core-phase-5-contract-2026-07-24.md` rev 1
**Verdict:** **DRIFT** — 2 BROKEN cites, 6 SHIFTED, anomalies recorded. **No contract obligation invalidated. GO for W1** (conditions in §9/§11).

---

## 1. Ground pin

| item | value |
|---|---|
| Landed tip (S0 pin) | `90bf31d9077a5500b58f4c3b3b8c98ac1507801a` (ground clone re-pinned; porcelain clean before and after every verifier run) |
| Landing PR / CI | PR **#190**; master CI run **30110130410** — all **7 jobs green** (given by orchestrator, per-JOB verified upstream) |
| Contract self-grounding tip | `70bca2ae` (pre-landing). Every cited anchor RE-verified at `90bf31d9`; only landing-induced deltas found (ledger row flip + plan-twin off-by-one, §8) |
| Program anchor | contract YAML `baseline_sha` = `8f9c555d2064d55a159a53fcedd6df33434a9291`; census actuals identical at 70bca2ae and 90bf31d9 — SHAs reconcile |
| Ledger row | COG-5 `operative-egg-ledger-2026-07-07.yml:3373-3382`, `status: in-flight`, `last_update: 2026-07-24` (the only unparked in-flight row); A13 plan twin present at `operative-egg-plan-2026-07-07.md:1053` |
| CG-34 | captain-gated, present in BOTH ledger (`:3438-3449`) and plan doc (`:866`); proposal doc landed as `docs/proposals/germline-amendment-immutable-core-holdout-2026-07-24.md` |

## 2. Verifier fan-in (anchor table)

| verifier | matches | shifted | broken | headline |
|---|---|---|---|---|
| contract-anchors | ~141 distinct anchors byte-TRUE | 2 | **1** | full sweep of every `:NN` cite incl. all task-named ones; out-of-tree BACKLOG/HANDBACKS anchors (11) verified against live cabinet-meta |
| census-projection | 5 | 0 | 0 | census GREEN at tip (all 10 budgets observed==max); module-RED class proven by experiment |
| baselines-12-1 | 4 | 3 | **1** | all four §12.1 baselines measured fresh at tip; wall-clock sample count short (n=3 < ≥5) |
| fleet-organ-snapshot | 7 | 1 | 0 | 52/40 fleet, 5 composed organs, rowless-9 match, foundry/ absent as expected, gate-apply dark lane intact |
| hygiene | 17 | 0 | 0 | import gate, layer-sep, A13 (352 ids), ledger parity, verify-phase4 full green, egg export, pointer-file absence, PARK markers — all green |

## 3. Adjudication — the two BROKEN

**B-1 (cite class — contract body names a nonexistent path).** §7.5.1 (`:155`) and §14.1 (`:249`) reference `docs/proposals/germline-amendment-holdout-ring0-2026-07-24.md`. No such file. The landed file is `docs/proposals/germline-amendment-immutable-core-holdout-2026-07-24.md`, which is the name the CG-34 ledger row (`:3449`) and its A13 plan twin (`:866`) use consistently. **Obligation intact:** the §7.5 deliverable (amendment proposal doc with the complete `immutable-core.yml` diff + CG-class row + A13 twin, filed at landing) IS discharged under the real name — the contract body's two pointers are stale, the deliverable is not missing. Discharge: W0 editorial fix (zero obligation bytes) — or this report stands as the of-record correction until then. **The real filename `germline-amendment-immutable-core-holdout-2026-07-24.md` is authoritative.**

**B-2 (measurement shortfall — §12.1.1(c)).** The contract requires wall-clock p95 over **≥5** runs; S0 captured **3** clean samples (the 6-run loop was SIGTERM'd to prioritize pass-state baselines; run 4 died at the Bash cap). Samples 181.4/181.8/183.0s are tightly clustered (σ<1s), so p95=182.9s / bound=228.6s is robust — but the ≥5 requirement is genuinely unmet. **Obligation partially discharged; not W1-blocking:** the bound artifact is consumed by `verify-cognitive-phase5.sh` in the SAME commit it lands (§12.1.3 anti-phantom law — a later-wave act); W0 backfills ≥2 clean runs and re-fixes p95/bound before that artifact lands tracked. Bound status until then: **PROVISIONAL**.

Rule applied: ALL-MATCH iff zero BROKEN cites → **DRIFT**. Neither BROKEN invalidates an obligation, and no anomaly does either → **GO for W1** stands.

## 4. Census — the two expected-RED classes (§11.1 evidence)

**GREEN at tip.** Census PASS, exit 0, observed==max on ALL 10 budgets at `90bf31d9`:
`central_event_types` 91 · `central_action_types` 30 · `services_total` 52 · `services_enabled` 40 · `layer_debt_entries` 24 · `layer_allowlist_entries` 19 · `framework_production_modules` **236** · `framework_production_noncomment_lines` **66548** · `named_compiler_modules` 1 · `duplicate_event_writer_sinks` 3.
No COG-5 `temporary_allowances` rows exist yet (phases present: COG-0, COG-1, relaunch-killswitch, relaunch-ci-tolerance, COG-2, COG-3, COG-4; module effective max = 206 base + 30 allowances = 236).

**RED class 1 — modules (proven by experiment).** Scratch copy (`cog4-contract/cog5-census-scratch`, cp -R minus .git); created the 9 contract-projected modules `framework/evolution/{sandbox,archive,candidate,generator,arena,scorers,bench_factory,holdout_gen,league}.py` as empty files → census **FAIL exit 1**: `BLOCK framework_production_modules: budget exceeded (245 > 236)`; JSON `{budget: framework_production_modules, observed: 245, maximum: 236, reason: budget exceeded}`. Every other budget stayed GREEN — the RED is cleanly isolated to the module budget. The 9 names match §11.1/§14.1/§16 byte-for-byte (a conditional 10th, `emitter.py`, only if archive.py warrants the split — W4 decides).

**RED class 2 — lines (isolated, reasoned).** Empty files add 0 non-comment lines (66548==66548 stayed green), so the experiment proves the module class specifically. A real COG-5 net-add trips BOTH; §11.1 binds both allowance rows to bump to the EXACT measured running totals in the SAME commit (COG-2/3/4 idiom).

**S0 discrimination of record:** census RED on `framework_production_modules` and/or `framework_production_noncomment_lines` from COG-5 net-adds = the EXPECTED allowance path (fix = same-commit allowance rows, sunset 2027-01-24, shrink-only tighten at done-flip). RED on ANY other budget = **STOP** (never an allowance).

## 5. §12.1 BASELINE TABLE — measured values + declared tolerances (THE S0 addendum the W0 landing commits)

All measured fresh on the S0-pinned tree `90bf31d9` (never borrowed); tolerances are the contract's §12.1.2 declarations (declared before measurement).

| # | metric | measured at 90bf31d9 | declared tolerance | status |
|---|---|---|---|---|
| (a) | Armed COG-4 battery pass state | `test_cog4_*.py` subset = **691 tests, all green** under `COG4_ENFORCE_BOUND=1` (verify-phase4 rc=0; armed real-pilot check vs `fixtures/cog4/cog4-measure-baseline-2026-07-24.json` live). Full `pytest cabinet/scripts/tests` = **3320 passed / 11 skipped / rc=0** (skips = env/redis-gated; skip vector part of the baseline). Note: ledger's "690-green" headline resolves to 691 collected — the 691 figure is of record. | **ZERO regression** — stays green through every COG-5 wave. The §11.1 expected-allowance census RED is a census signal, never a battery RED, and is not exempted. | GREEN |
| (b) | Golden-eval pass state | **29/29 pass, 0 fail, 0 skip** over the **25 bodies** (`eval-001..eval-026`, no `eval-023`; 24 EVAL blocks; multi-assertion runner — the baseline is the 29-assert pass/fail VECTOR, not a per-body 1:1 count). Runner report-only; scalar jsonl gitignored (re-runs never dirty the tree). Model unspecified on this run. | **ZERO** — the pass/fail vector stays green; the scalar is never a gate/floor (`run-golden-evals.sh:10-17` law, tripwired §11.3). | GREEN |
| (c) | `verify-cognitive-phase4.sh` wall-clock | **n=3** clean samples: 181.4 / 181.8 / 183.0 s (all rc=0, tree clean each). p95 = **182.9 s** → bound = **max(p95×1.25, p95+5s) = 228.6 s** (×1.25 dominates; the +5s floor is inert at this magnitude — the floor-aware design binds only for sub-~20s baselines). | Bound as declared: max(p95×1.25, p95+5s). | **PROVISIONAL** — contract requires **≥5 runs**; W0 backfills ≥2 clean runs and re-fixes p95 + bound BEFORE the tracked bound artifact lands (B-2, §3). |
| (d) | Boundary-engine full-sweep | **955 files** swept across **13 SWEEP_TREES** (framework, shared, instance, presets, cabinet/scripts, cabinet/admin-bot, cabinet/mcp-server, cabinet/adapters, cabinet/channels, cabinet/companion, cabinet/evals, cabinet/fixtures, conftest.py); **violations = 0**. | Violations stay **0**; files-swept moves ONLY by the phase's own added files (exact-integer `census_delta` accounting, §13). | GREEN |

**Not yet captured (W0 completion item):** the **E1-substrate baseline** (case counts, corpus size) named alongside these in §14.2 W0 — no verifier measured it this pass. Must be measured and recorded before W0 closes.

## 6. Fleet / organ pins (at 90bf31d9)

- `cabinet/services.yml` YAML-parses to **52 rows / 40 enabled / 12 disabled** — matches the post-COG-4 pin exactly. (Naive `grep -c "name:"` returns 53 — an over-count; the parse is authoritative.)
- **5 composed organ manifests** under `cabinet/config/organs/`: charter-shadow, judge-calibration, prediction-calibration, preference-pairs, world-census — each with top-level `freshness_needs` (max_staleness_seconds 90000 + expected_output `cabinet/cache/organs/<name>/last-run.json`) AND `starvation_bound` (max_wakes 6). The `cog4-organ-runner` row (kind cron, interval_s 43200) lists exactly those 5 paths. SHIFTED-of-record: these 5 cadences relocated OUT of services.yml rows into the composed runner at COG-4 W6-e2 (net −4 rows; old sunsets moved into manifest headers; watchdog derives per-organ freshness floors via `registry._parse_organ_manifests`). **This runner is the §11.2 composition target for any COG-5 periodic foundry organ — services_total/enabled do NOT grow.**
- **Rowless organ set = the pinned 9** (chrome-profile, cost-summary, dashboard-kiosk, egress-proxy, heartbeat-watchdog, outbox-relay, ovi-weekly, role-evals-weekly, worktree-listener); `test_cog4_fleet_truth.py` live-derivation MATCHES (15 template stems = 5 paired + 1 roster + 9 rowless).
- `shared/interfaces/foundry/` **does not exist** and has **no .gitignore row** — correct pre-W1 state (the row LANDS in W1 per §5.4/SF-2; this is the §14.2 W0 "verify the archive-root ignore STATE" check, done).
- `shared/interfaces/gate-evidence/` is runtime-created (gate.py `evidence_dir()`), absent in the clone, untracked, **NOT gitignored** — matches the contract's own SF-2 refutation-of-record. **W1 adds ONLY the `shared/interfaces/foundry/` row, never a gate-evidence row.**
- **gate-apply dark lane intact:** no service row; plist `cabinet/launchd/com.cabinet.gate-apply.plist` present but un-rowed and unreferenced by generate-plists.py — Captain `sudo launchctl load` only (§17 tripwire: any unit touching plist/row REDs).
- Tolerated instance leakage: 3 concrete officer plists (`com.cabinet.officer.{cos,cos-inbound,comms-officer}.plist`) — fleet-truth tolerates present-or-absent; removal is slated (unit u3), still present at this tip.

## 7. Hygiene battery — 17/17 green

`cog2-import-gate.py` exit 0 (shadow boundary intact) · `check-layer-separation.sh` green (new=0; baseline 24 / allowlist 19 / current 43) · A13 parity exit 0 (**352 ids**, 1:1 plan coverage, run via python3.12) · `ledger-status-parity.sh` GREEN (ids=352, md_rows=352, findings=0) · `verify-cognitive-phase4.sh` FULL green at tip (exit 0; 29/29 evals; cog4 rollback rehearsal PASS; READY_FOR_CI) · `test_egg_export.py` exit 0 (58 passed + 1 by-design CI-shape skip at :1103) · pointer files ALL absent (cog1-authority, cog3-read-pointer, cog4-dispatch-pointer, cog5-*, `$HOME/.cabinet/state`) · phase-4 tripwire green · four PARK markers present + tracked · ledger parses 352 entries · boundary-manifest parses (schema/sweep_trees/rows) · clone clean after all runs. Row shape: COG-5 the only unparked in-flight; 14 in-flight total (13 parked, 0 stale); COG-4 done; CG-34 captain-gated in both surfaces.

## 8. Drift register (full — SHIFTED + anomalies; all recorded, none obligation-invalidating)

**SHIFTED (6):**
1. Plan-twin pointer: contract header cites `operative-egg-plan-2026-07-07.md:1052` for the COG-5 twin → actually **:1053** (1050=COG-2, 1051=COG-3, 1052=COG-4, 1053=COG-5, 1054=COG-6; a landing-time line insertion). A13-by-ID holds.
2. `boundary-manifest.yml` ROW 6 (`framework.projection`): cited `:316-339` → actual span **:316-345**; the cited endpoint stops at the `allowlist_globs:` header, excluding the cortex/objectives/scheduler globs (:340-342) the citation's own prose invokes. Substantive claim TRUE. Row authors in W1 use **:316-345**.
3. "690-green" battery headline → **691** tests in the `test_cog4_*.py` subset; full-dir = 3320 passed / 11 skipped.
4. Golden baseline = the **29-assert vector** over 25 bodies / 24 EVAL blocks (multi-assertion runner), not per-body 1:1.
5. Boundary sweep composition = **955 files / 13 trees** (named in §5(d)).
6. Five organ cadences relocated from services.yml rows into composed manifests (COG-4 W6-e2; net −4 rows; freshness floors preserved) — see §6.

**Anomalies (recorded):**
7. Contract header `:3-:4` point-in-time STALE: says ledger row "todo, last_update 2026-07-19" + twin ":1052"; landed row is in-flight / 2026-07-24 / twin :1053. Pre-landing snapshot drift; line RANGE :3373-3382 correct.
8. **Landing-pass changelog (line 347) overclaims 2 of 3 fixes:** F-2 (header ls-claim gains `__init__.py`) NOT applied — line 3 still reads "`contracts.py` + tests only"; F-3 (egg-manifest cite gains its `cabinet/scripts/` path) NOT applied — :117/:331 still bare basename (unique basename still resolves; no broken cite). Only F-1 (cog2-import-gate re-anchor :53-54/:342/:368-375) genuinely applied — verified TRUE. The claim "zero obligation bytes changed" is TRUE. W0: apply F-2/F-3 or correct the changelog honestly.
9. Out-of-tree cite class: BACKLOG anchors (`:1551-1555/:1560/:1562/:1563/:1564/:1568/:1572/:1573/:1574/:1575` — cited WITHOUT the `~/cabinet-meta/` prefix) + HANDBACKS `:319-327` (prefixed) resolve only against live cabinet-meta, not the repo tree. All 11 verified TRUE today (BACKLOG.md 1587 lines; item 19 = CG-33 COG-4 extension window; :1574=C7 / :1575=C8 per the rev-1 N-2 correction).
10. Grounding-tip note: contract self-grounds at 70bca2ae; landed tree is 90bf31d9. All anchors re-verified at 90bf31d9; no content drift beyond items 1/7.
11. `test_cog4_fleet_truth.py:3` docstring stale ("57 rows / 44 enabled", tip de5d16c4) vs actual 52/40 at 90bf31d9. Logic unaffected — test green.
12. **COG-1 park rationale stale** ("COG-3 in-flight"; COG-3 done 2026-07-23). §14.2 W0 explicitly owns the refresh — NOT yet done; carried as W0 obligation.
13. Two SIGTERM'd verify runs leaked `cog4-rollback-*` rehearsal worktrees under `$TMPDIR` (completed runs self-clean; main tree stayed clean throughout; HEAD pinned). Prune at W0 (outside the clone; no-mutating-git honored during S0).
14. A13 ledger row's stored `gate_cmd` invokes bare `python3` vs house `python3.12` — pre-existing nit, out of COG-5 scope (S0 ran it with python3.12; both pass).
15. Full-dir battery carries 11 env/redis-gated skips — skip vector recorded in baseline (a).
16. Golden runner Model=unspecified; scalar jsonl gitignored — safe to re-run at W0.
17. §11.1 conditional 10th module (`emitter.py` only if archive.py warrants the split) — contingency, W4 decides; the 9-module experiment matched the unconditional set.

## 9. W0 remaining obligations (close before/with the addendum landing)

1. **Backfill wall-clock runs** to n≥5; re-fix p95 + bound in the tracked baseline artifact (discharges B-2; bound PROVISIONAL until then).
2. **Measure the E1-substrate baseline** (case counts, corpus size) — §14.2 W0; not captured this pass.
3. **Refresh COG-1's stale park marker** (dated) — §14.2 W0.
4. **Contract editorial fixes** (zero obligation bytes): B-1's two `holdout-ring0` → `immutable-core-holdout` references (:155/:249); header :3-:4 point-in-time (todo→in-flight, :1052→:1053); the line-347 changelog correction (apply F-2/F-3 or restate honestly).
5. **Prune** the two stray `$TMPDIR/cog4-rollback-*` worktrees.
6. **Land this report** (or its derived artifact) as the dated tracked §12.1.1 baseline artifact in the W0 landing commit.

## 10. W1 SCOPE — stated from the landed contract §14.2 (:254) for the wave launch

> **W1 — boundaries + interim freeze:** §10 rows + AST pins + per-row mutants; §7.5 interim content-pin + egg exclusion lines; the §5.4 `.gitignore` row (`shared/interfaces/foundry/`) + `git check-ignore` assertion; A13 parity green.

Expanded against S0 ground:
- **§10 boundary rows:** `cabinet/config/boundary-manifest.yml` rows + AST pins + a biting per-row mutant each — ROWS ONLY, zero engine code (C2 engine deferred). ROW 6 true span :316-345 stays byte-untouched (SF-4 deliberate non-extension).
- **§7.5 interim freeze (Stage A — honestly NOT Ring-0):** content-pin sibling test (sha256 of `holdout_gen.py` bytes; drift REDs CI) + egg-export EXCLUDE + expect-absent line for `holdout_gen.py` (O-B3 precedent; retired when the Ring-0 listing lands at the Captain window). Arming record will carry `holdout_freeze: pending-captain-window` (§7.5.5).
- **§5.4 ignore row:** add `.gitignore` row `shared/interfaces/foundry/` + `git check-ignore` twin assertion. S0 verified the pre-state: dir absent, no row (§6). Do NOT add a gate-evidence/ row.
- **A13 parity green** after the wave's ledger/plan touches.
- Per-unit discipline (§14.2 header): dirty-guard per file; clean worktree off current origin/master; exact-path `git add`; FW-019 review artifact for >300-line commits; per-JOB CI verification after every push. Tests-first per §13 (batteries land failing-for-the-right-reason). Census: any net module/line add takes the §4-of-this-report allowance path same-commit.
- Model routing (§14.3): W1 is execution-tier mechanical → Opus 4.8 1M default, pins EXPLICIT on every agent; Fable-for-execution allowed where judged beneficial; judgment/review stays Fable-pinned.
- Parallel WG lane state at S0: proposal doc + CG-34 row + A13 twin already LANDED with the contract; the Captain-window handback stands (batched offer with HANDBACKS item 19 — window state re-checked at WG per §7.5.3/N-4). Freeze-verification units PARK with dated markers if the window is unopened.

## 11. GO/NO-GO

**GO for W1.** Zero obligation-invalidating findings: hygiene 17/17 green; census GREEN with the expected-RED allowance path experimentally proven and discriminated from STOP; all four §12.1 baselines measured fresh (one PROVISIONAL pending n≥5 backfill); fleet/organ surface pinned and matching; both BROKEN findings are W0-side dischargeable (an editorial filename pointer; a sample-count backfill) and touch no W1 surface. Conditions: the §9 W0 obligations travel with the landing; the wall-clock bound stays PROVISIONAL until n≥5; the real proposal filename (§3 B-1) is authoritative over the contract body's two stale pointers.
