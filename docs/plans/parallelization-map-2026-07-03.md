# Parallelization Map — 2026-07-03

## Honest posture

The two plans are **not** two parallel tracks right now — they share **one trunk**: the evidence plane / capture→action spine that survived the 2026-07-03 pivot (F0 foundation is done; the binder gate, consequence ledger, and courses-of-action rule are being re-aimed from draft-replies to proactive actions). Plan A (personal-clone pipes) and Plan B (Mac-Mini clean-room product org) only **diverge later**, after `executor-outcome-truth` proves the whole spine on one capture source. So "run both plans with 20 agents tonight" is the wrong shape: the early trunk is **dependency-sequential** — `B2.1 correlation-id` is the join key every downstream probe/adapter needs and it is still in-flight, and the first adapter is **Nate-gated** on the 07:30 lane-build confirm (Q1/Q2/Q3) plus `A3.1` disposition-table ratify. The genuine big fan-out moments are still ahead of us: the **probe fleet** (`B2.3–B2.7`, each independent the moment `B2.1`/`B2.2` land) and the **A3 execution sweep** (after Nate ratifies the disposition table). Everything in Plan B from `B4.1` onward is **hardware-gated** on the physical Mini plus a literal 72h unattended soak. What *is* safe to fan out tonight is the ring of isolated, read-only / low-blast work that does **not** touch the live binder/ledger/poller spine and is neither Nate- nor hardware-gated — doc restructure, config extraction, embeddings backfill, skill/boot hygiene, and design-only spec drafting.

---

## Bucket 1 — Ready now, parallelizable tonight

Independent, ungated, low-blast, do **not** touch the live binder/ledger/poller spine, `safe_overnight=true`.

| id | title | plan | depends_on (all satisfied) | why safe tonight |
|----|-------|------|-----------------------------|------------------|
| A3.8 | Path/config extraction (SCREENPIPE_ROOT etc) | A | — | isolated refactor, CI-covered, no spine touch |
| A4.1 | Vault architecture affirmation + gaps note | A | — | read-only analysis, writes a note only |
| A4.2 | content_ts coverage 64%→≥80% | A | — | embeddings backfill, additive, no re-embed |
| A4.11 | 0-Self fences pinned | A | — | provenance fences, isolated config |
| A6.4 | Skill dedup — one canonical copy | A | F0.1 ✅ | filesystem hygiene, no runtime path |
| A6.8 | Boot assertions — TUI scrape + version pin | A | F0.4 ✅ | additive assertions, isolated |
| F0.14 | Cost writer wired to a real hook event | B | F0.4 ✅ | additive telemetry, low blast |
| B2.13 | Captain-debt reverse queue + registry | B | F0.7 ✅ | ledger-**read** only, no write path |
| A1.10 | Captain-debt reverse queue | A | F0.5 ✅ | same reverse-queue read, Plan-A framing |
| docs-refresh | README + guide refresh to pivot arch | status | F0-foundation ✅ | docs-only |
| plan-restructure-docs | Restructure Plan A/B to the pivot | status | capture-action-design-note ✅ | docs-only |

**Unlocks the instant `A1.2` (binder bind) lands** (currently in-flight — treat as ready-next, not ready-now): `A2.9` rubber-stamp detector, `A4.6` nightly Dreams consolidation, `A4.7` nate-model layer hygiene, `A4.8` reply_enrichment continuation, `A4.12` taint/provenance 80/20, `A5.1` never-lie Stage 1, `A6.1` experience records.

---

## Bucket 2 — Sequential chain (the reason we can't just fan out)

The ordered trunk. Each row waits on the row(s) above. This is the spine both plans share until the divergence point.

| order | id | title | plan | blocks on | note |
|-------|----|-------|------|-----------|------|
| 1 | A1.1 | Inline-keyboard tap point on poller | A | F0.5 ✅ | in-flight; poller spine |
| 2 | A1.2 | reply_binder.bind = single fan-out | A | A1.1 | in-flight; unlocks the A4/A5/A6 ring |
| 3 | B2.1 | Correlation-id propagation standard | B/shared | F0.6, F0.7 | **in-flight — THE join key everything downstream needs** |
| 4 | action-proposal-schema | Extend proposal_event/action_type enum | shared | B2.1 | hard ceiling never lifts |
| 5 | commitment-ledger-adapter | First capture adapter end-to-end | shared | action-proposal-schema, **lane-build-captain-confirm (Nate)** | prove spine on ONE source |
| 6 | executor-outcome-truth | Executor + superseding outcome truth | shared | commitment-ledger-adapter | **divergence point** — Plan A & B branch after this |
| 7 | graduation-wiring | Cells start propose-first, graduate on evidence | shared | executor-outcome-truth | gate: real-world-signal |
| — | A1.5 | One canonical ledger; freeze archives | A | A1.2 | authority sub-chain |
| — | A1.6 | Migrate 7 autonomy lanes → graduation engine | A | A1.5 | |
| — | A1.8 | Ledger-liveness dead-man for flavor-A lanes | A | A1.6, F0.7 | |
| — | A2.1 | Harness merge — fidelity absorbs retrodiction | A | A1.5 | fidelity sub-chain |
| — | A2.2 / A2.3 / A2.5 / A2.7 | fidelity run / judge v2 / decompose / shadow-parity | A | A2.1 | |
| — | A2.4 | Frozen auto-minted regression suite | A | A1.2, A1.5 | gates A2.6, A5.2, A6.5, A6.10, A4.13 |
| — | A7.1 → A7.3 → A7.4 → A7.5/A7.6/A7.7 | authority enforce chain | A | A1.6, A2-exit | real-world-signal burn-in |
| — | B2.2 | Probe framework lib | B | B2.1 | gates the whole probe fleet |
| — | B2.8 / B2.9 | Dual-source verifier / measure→gate wire | B | B2.3–B2.6 | |
| — | B2.14 | Parity re-run protocol v2 (7d fresh traffic) | B | B2.9 | real-world-signal |
| — | B3.2 → B3.3 → B3.6 | enforce flip → veto window → first cell graduates | B | B2.14, B2.10, F0.9 | real-world-signal + Nate |
| — | fan-out-capture-adapters | meeting-intel, decisions, audio follow-up | shared | commitment-ledger-adapter, executor-outcome-truth | the *second* real fan-out |

**Probe fleet (the big Plan-B fan-out, blocked on B2.2 tonight):** `B2.3` GitHub, `B2.4` Vercel, `B2.5` Sentry, `B2.6` CI-runs, `B2.7` Support-thread — each `parallelizable=true` and mutually independent the moment `B2.2` lands. Not fannable tonight (B2.1 still in-flight).

---

## Bucket 3 — Nate-gated (need a Captain decision before they can start)

| id | title | plan | gate reason |
|----|-------|------|-------------|
| lane-build-captain-confirm | 07:30 — Q1 task store of record, Q2 impl autonomy floor, Q3 first capture source | status | **blocks commitment-ledger-adapter** |
| A3.1 | Ratify the disposition table | A | **NATE-ONLY; gates the entire A3 execution sweep** |
| F0.8 | One Telegram send path + token split | B | send-path policy |
| F0.10 | Killswitch fail-closed + resume authority | B | authority |
| F0.11 | Backups + remotes for everything durable | B | Captain-deferred Q11 |
| A1.4 | Expiry fold-in + pre-era retirement | A | retirement policy |
| A1.12a | EventKit account + self-sanction | A | calendar auth |
| B2.9 | Measure→gate wire (shadow) + autonomy.yml | B | autonomy instantiation |
| B2.10 | Test-diff ceiling risk-class + coverage-ratchet | B | blocks B3.2 flip |
| B2.11 | Narrow captain_auto_ratified THEN learning crons | B | ratify scope |
| A2.6 | Weekly blind self-pick quiz | A | |
| B3.2 | Flip CABINET_AUTHORITY_ENFORCING=1 (L0/L1) | B | the enforce flip |
| B3.7 | L0–L3 ladder + L3 dual-confirm tier | B | |
| A5.5a | Apply receipt germline carve-out | A | |
| A5.9 / A5.10 | Endorsement axis / quarterly shadow-Nate week | A | |
| A6.5a | Reconcile brain-bridge germline contradiction | A | |
| A7.0a | Create the broker macOS user | A | |
| A7.1a | Flip CABINET_AUTHORITY_ENFORCING=1 | A | |
| A7.2 | Author autonomy.yml *(trust-ladder half SUPERSEDED 2026-07-04 — earn-demotion ruling; module removed)* | A | |
| A7.4a | Ratify first auto scope + undo window | A | |
| B4.8 | Micro-VPS webhook catcher | B | provisioning decision |
| B5.3 | Split germline: fixtures at machine speed | B | |
| B5.7 | Judge contract pinning + monthly calibration | B | |
| B6.8 | Federation posture (cabinet_spawn = L3 ceiling) | B | |

---

## Bucket 4 — Hardware-gated (need the physical Mini + soak)

| id | title | plan | gate reason |
|----|-------|------|-------------|
| A1.13 | Restore DRILL (vault/estate/db from Mini) | A | needs Mini |
| B4.1 | Mini hardware/OS checklist (clean room) | B | the Mini |
| B4.2 | cabinet-init → generate-instance.py for PolAds | B | on Mini |
| B4.3 | Fresh graduation ledger + model-baseline stamp | B | on Mini |
| B4.4 | Product adapters on find_threads/gather/draft_fn | B | on Mini |
| B4.7 | Executor + hash-locked outbox (cabinet-exec user) | B | on Mini |
| B4.9 | No computer-use on the Mini (dissolve TCC gate) | B | on Mini |
| B4.10 | Mission-supervisor + first real routed task | B | on Mini |
| B4.13 | Fleet from services.yml on the Mini | B | on Mini |
| B4.17 | 72h unattended soak protocol (Gate-4 exit) | B | **literal 72h soak** |
| B4.18 | Sandbox tier (/sandbox Seatbelt) for Builder | B | on Mini |
| B5.1 | Gate-runner core (balanced probe, pass^k) | B | on Mini; gates all B5/B6 |
| B5.2 / B5.6 | hidden holdout / weekly drift replay | B | on Mini |
| B6.2 | Support-Drafter activation (3rd officer) | B | on Mini |
| B6.7 | Product #2 staged onboarding SOP | B | on Mini |
| plan-b-later-divergence | Estate Mapper + Mini bring-up + Evidence Engine | status | on Mini |

**Transitively hardware-gated** (gate=none but blocked behind `B5.1`, which is on the Mini): `B5.4`, `B5.5`, `B5.8`, `B5.9`, `B5.10`, `B6.1`, `B6.3`, `B6.4`, `B6.5`, `B6.6`, `B6.9`.

---

## Recommended immediate fan-out (safe tonight)

Five independent workstreams, none touching the live binder/ledger/poller spine, none Nate- or hardware-gated. Each line is an agent brief.

1. **Doc-staleness sweep** — Execute `docs-refresh` + `plan-restructure-docs`: refresh README, top-level docs, and `captains-cabinet-guide.md` to the ratified/pivot architecture; restructure Plan A/B docs (A5 re-aim, action-lane as shared trunk, capture-adapter sequencing). Docs only, no code.
2. **Config extraction (A3.8)** — Extract hardcoded paths to `SCREENPIPE_ROOT`/config across pipes; isolated refactor behind existing CI (`pytest framework/`); must not modify binder/ledger/poller modules.
3. **Vault content_ts backfill + gaps note (A4.2 + A4.1)** — Lift content_ts coverage 64%→≥80% via in-place backfill (no re-embed), and write the vault-architecture affirmation + gaps note. Read-mostly; additive DB column only.
4. **Hygiene + boot hardening (A6.4 + A6.8)** — Deduplicate skills to one canonical copy; add boot assertions (TUI scrape + Claude version pin). Filesystem/scaffolding only, no runtime spine.
5. **Design-only spec drafting for `action-proposal-schema`** — Draft (do NOT wire) the extended `proposal_event`/`action_type` enum spec as a markdown design doc — task-create/update, feature-impl, followup-schedule, commitment-close — pinning the hard ceiling (external_comms/deploy/spend/secrets never lifts, no external_comms action at all). Unblocks the morning without touching live code; implementation waits on `B2.1`.

**Explicitly NOT fanned out tonight:** anything on the sequential trunk (`A1.1`, `A1.2`, `B2.1`, adapters, executor), the probe fleet (blocked on `B2.2`), all Nate-gated items (esp. `A3.1`, `lane-build-captain-confirm`), and all Mini/soak work.

---

## Orchestrator judgment — what I actually fanned out tonight (2026-07-03)

The map recommended 5 workstreams. Applying critical judgment (the Captain asked
for it): **3 of the 5 touch LIVE personal infrastructure and are held for Nate**,
not because they're gated in the depends_on sense but because doing them unattended
at night is beyond the safe envelope:

| # | Workstream | Decision | Why |
|---|---|---|---|
| 5 | action-proposal-schema design spec | **LAUNCHED** (fork) | Pure markdown design doc; zero live-data/code touch; advances trunk step 4 so it's ready when B2.1 lands. |
| 1 | Doc-staleness refresh (README + guide) | **LAUNCHED** (fork, stage-only) | Docs only, git-reversible, CI-visible; Nate explicitly asked for the guide to be updated. Scoped to a staleness pass, not a rewrite; I review the holy-bible edits before they land. |
| 2 | Config extraction A3.8 (~40 live pipes) | **HELD** | Rewrites Nate's LIVE screenpipe pipes (his running digital clone); NOT covered by cabinet CI; belongs with the A3.1 disposition ratify (NATE-ONLY). A path bug would break his morning brief/commitment-ledger overnight. |
| 3 | Vault content_ts backfill A4.2 | **HELD** | Writes his LIVE brain index at 1am; his own rule keeps officers out of vault writes. Additive but not worth the unattended risk. |
| 4 | Skill dedup + boot A6.4/A6.8 | **HELD** | A6.4 removes skill copies (blast radius); reversible but better reviewed. A6.8 (boot assertions) can ride a later batch. |

**Principle applied:** for actions that touch live personal data/infra or are hard
to reverse, confirm with Nate rather than fan out unattended. Two pure-additive,
reversible workstreams launched; three held for the morning with their unlock noted
(A3.1 ratify unlocks #2; explicit go unlocks #3/#4).
