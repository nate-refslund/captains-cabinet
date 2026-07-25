# PR — World Direction Surface (lane A, Wave 1, 2026-07-17)

Branch `feat/world-direction-surface` → master. **Grammar-law PR: the
Captain merges — nothing here auto-merges** (morphology v4 + show-grammar v4
ride this branch). Provenance: per Captain ratifications 2026-07-17 +
full-autonomy grant 2026-07-07 (recorded in
`shared/interfaces/captain-decisions.md`; that runtime ledger is not touched
by this PR). Design record: `docs/plans/world-direction-surface-2026-07-17.md`.

## One-click ask

Merge the branch. Then run once on the live box:
`python3.12 cabinet/scripts/world-port-calls.py` — it writes the gitignored
port-calls read-model so the two artifact-bound grammar entries go live
(until then they render honest absence: no stamps, moored boat, and the
binding validator hard-fails live / SKIPs under `CABINET_WORLD_DATA_OPTIONAL=1`,
the same class as `lane_reef_buoys`).

## What renders (all read-only; the killswitch lever stays THE one actuator)

| Surface | Where | Truth source |
|---|---|---|
| Chart table (small bound prop, mailbox precedent) | authored tile `CHART_TABLE_LOCAL` (33,8 main-island local — manor NE curtilage) | `instance/config/directions.yml` |
| Plotted course lines (hue+shape dual-coded per state) | quay → each berthed direction lane's isle | `laneCourseState()` over directions + outcomes + port calls |
| Port-call chalk count-marks (dates card-only) | at the berth | `shared/interfaces/world/port-calls.json` (git-derived) |
| Voyage boat (moored / on the course line) | quay / course line | same artifact; position = pure f(flip date, server today) |
| Direction-chart card (`?sel=chart-table` deep-link) | authed inspect card | engine payload `{directions, courses, portCalls, todayISO}` |

No world-space text anywhere — mission text, lane names, dates live ONLY in
the authed card (source-scan vitest pins it).

## Every new binding + its truth source (morphology v4, validator green)

| Entry | source_binding | live value 2026-07-17 | replay |
|---|---|---|---|
| `manor_chart_table` | `grep -c -e 'mission:' instance/config/directions.yml` | 4 (apex + 3 lanes) | git |
| `harbor_port_calls` | `jq -r '.port_calls_total' shared/interfaces/world/port-calls.json` | 2 | git |
| `lane_course_state` | `grep -c -e 'status: active' instance/config/outcomes.yml` | 8 | git |
| `harbor_boat_voyage` | `jq -r '.last_port_call_date' shared/interfaces/world/port-calls.json` | 2026-07-02 | git |

show-grammar v4 adds `chart_table_view` (mailbox_view law clone: read-only,
deep-link, never actuate) and `voyage` (construction's pure-function T0
arrival + the three stall-state render laws). The `law:` block and every
v1/v2/v3 entry in both files are byte-untouched (diff shows only the version
line + appended blocks). `growth-ladders.yml` untouched. `grammar.ts`
ignores unknown top-level keys; consumption rides new dedicated lib modules
(`directions.ts`, `course.ts`) — the v3 weather precedent.

## Decisions the Captain is ratifying by merging (re-ratification touchpoints)

1. **The TRACKED `instance/config/directions.yml` carries the REAL apex
   text** (ratified choice — the text is deliberately generic, no
   personal/product data). It lives as a NEW top-level `org:` key, sibling
   of `directions:` (never inside it: framework consumers fold only
   `doc["directions"]`, `framework/acting/action_lane.py:232,297,541` —
   additive-safe). The file's public-tree-scrub header now records the
   exception. Deployments whose untracked overlay lacks `org:` degrade to
   an honest grey **uncharted** card — never an invented apex.
2. **Zero civic anchors minted** (`civic_anchor_exception` budget stays
   0/3): the manor anchor is morphology law and the `great_house` element
   IS the manor structure; the chart table is a small bound element in its
   curtilage on the mailbox precedent.
3. **Course states are ledger-state semantics ONLY** (the reduced honest
   set): `docked_refitting` = ≥1 active outcome (a ledger claim, never a
   work claim) · `tacking` = achieved flip ≤14 d (inclusive) + active
   successor · `adrift` = direction present, zero active, not retired (the
   renewal-loop gap made visible). "Is crew actually working this lane this
   week" is **UNMEASURED** and never rendered as a state.
4. **The drift gauge renders grey "unmeasured"** with the missing emitter
   NAMED on the card: `org_events.lane_slug` exists and is indexed but
   carries only `{captains-cabinet, default}` — no lane slug has ever been
   stamped; the census keyframe has no per-lane field; lane work lives in
   external repos. **Future emitter:** work-routing emitters stamp real
   lane slugs into the already-indexed `lane_slug` column, then
   `world-census.py` gains per-lane int keys (int-only keys satisfy the
   census PII fence). Until then: grey, honest, named.
5. **Replay stance = `git`** for the port-call stamps (the tasking text
   said "ledger"; file convention for outcomes-git-derived entries is git —
   `lane_reef_buoys` precedent, morphology). The artifact is a rebuildable
   runtime read-model in the ALREADY-gitignored `shared/interfaces/world/`
   directory; regenerate-and-diff IS the replay.
6. **Commissioning copy (ruling 3) — minimal true scope**: the only live
   display strings were two `hatch-dialog.tsx` aria-labels (now
   "commissioning dialog") + the new `COMMISSIONING_STAGES` display ladder
   (keel-laying → launch → christening → sea trials → commissioning →
   maiden voyage) exported from `lib/world/hatch-dialog.ts`. FROZEN machine
   identifiers, deliberately untouched: `DialogMode 'hatching'`, the
   `HatchButton` set, `hatch.sh`/`null-hatch.sh`/`hatch-lib`, every `egg-*`
   script/ledger/manifest name, hatch route paths, README/CONTRIBUTING
   install-flow "hatch" prose (install authority doc unchanged), and
   `decision-queue-card.tsx` "HQ Chair" (ruling 4 = another lane's surface).
7. **No fleet/runtime touches**: no services.yml row, no launchd, no redis
   writes; the engine route stays GET-only. A future scheduled-service row
   for `world-port-calls.py` (cheap, read-only, cron-class) is noted for a
   later wave; until then the card's as-of line (`generated_at` +
   `source_git_head`) makes staleness honest.

## Reality notes (where the ground disagreed with the tasking)

- `.gitignore`, `docs/plans/operative-egg-ledger-2026-07-07.yml`,
  `docs/plans/operative-egg-plan-2026-07-07.md` were DIRTY in the live tree
  (another wave's staged work) — excluded per dirty-guard. Consequences:
  the artifact moved into the already-ignored `shared/interfaces/world/`
  (zero `.gitignore` edit needed), and **no ledger row lands in this PR**
  — the integrator appends `WORLD-DIRECTION-SURFACE` + the A13 plan-table
  row after the owning wave lands. The A13 parity gate is green on the
  branch as-is (pair untouched here; gate run pre- and post-commit).
- `grep -c 'status: active'` = 8 today (7 rows + 1 header comment), not
  the tasking's 6 — liveness binding, value not rendered; noted.
- The backtest's `outcome_flip_dates` lists EVERY date outcomes.yml changed
  (5 dates), not achieved-flips only; the honest cross-check passed: both
  port-call dates (2026-07-02) ∈ flip dates AND the `outcomes_achieved`
  daily series steps 0→2 exactly on 2026-07-02.
- **Composition fix found by live render probe**: the first chart-table
  tile (33,10) sat under seeded east-hedge dressing sprites (hedge anchors
  at local ly 11.6/13.5 overdraw ly 10). Moved to (33,8) — open grass, NE
  curtilage, verified visibly rendering + hit-testable live. Composition
  fixed, never thresholds.

## Validation transcript (all run in the worktree, 2026-07-17)

- `python3.12 cabinet/scripts/world-binding-validator.py` — **GREEN**
  (entries=32, fails=0, data-skips=0; all 4 new bindings executed live).
- CI parity: artifact moved aside + `CABINET_WORLD_DATA_OPTIONAL=1` →
  `harbor_port_calls` + `harbor_boat_voyage` **SKIP** (data absent), run
  stays GREEN (data-skips=2) — validator itself untouched.
- `python3.12 -m pytest cabinet/scripts/tests/test_world_port_calls.py -q`
  — **13 passed** (pure fold functions, fixture blobs, no live git).
- `python3.12 cabinet/scripts/world-growth-validate.py` — **OK** (29
  ladders; growth-ladders.yml deliberately untouched).
- `python3.12 cabinet/scripts/world-growth-backtest.py` — replay sane:
  calibrated `[balanced]` winner reproduces (hamlet @ 0.434, egg exit day
  34, transition 2026-06-28); port-call dates corroborated (above).
- `python3.12 cabinet/scripts/world-port-calls.py` — artifact written:
  total=2, last=2026-07-02, lanes polads/stephie; `jq .` clean.
- Dashboard: `npm run test` **1809 passed (104 files)** · `npm run
  typecheck` clean · `npm run build` succeeds (/world in route table).
- `python3.12 -m pytest framework/tests -q` — **796 passed, 1 skipped**.
- `bash cabinet/scripts/check-layer-separation.sh` — **OK, new=0**
  (baseline 24, allowlist 18).
- A13 parity gate (ledger gate_cmd verbatim) — **green** pre- and
  post-commit; pair untouched by this branch.
- Aesthetic harness: self-tests **87 passed, 5 skipped**;
  `world-preview.py --gate` on regenerated egg (2026-05-25) + today
  (2026-07-16) fixtures — **mechanical GREEN** both (the PIL compositor is
  untouched by this branch). Live functional verification on a dev server
  (worktree, port 3210, live fleet untouched): engine payload carries
  apex/courses/portCalls/todayISO; chart table renders + hit-tests at
  (33,8); course-line dashes verified on-sea; card NOW/PROOF tabs show
  apex verbatim, course rows, the grey drift line, dated port calls + the
  as-of provenance; `?sel=chart-table` deep-link restores the card.
  NOTE (pre-existing, not this delta): raw live-browser frames fail the
  palette gate (~44–58% foreign, top color = the live water hue
  68,124,180) — a control frame containing ZERO direction-surface elements
  fails identically, so the mismatch is the browser-frame class vs the
  compositor-calibrated corpus, recorded here honestly. No screenshot
  ships to the Captain in this PR; any future Captain-facing frame runs
  the full harness (mechanical + calibrated judge ≥7) first, per doctrine.

## Files

New: `cabinet/scripts/world-port-calls.py`,
`cabinet/scripts/tests/test_world_port_calls.py`,
`cabinet/dashboard/src/lib/world/directions.ts` (+ test),
`cabinet/dashboard/src/lib/world/course.ts` (+ test),
`docs/plans/world-direction-surface-2026-07-17.md`, this proposal, and the
FW-019 review artifact
`shared/interfaces/reviews/feat-world-direction-surface-cp1.md`.
Modified: `cabinet/world/morphology.yml` (v4), `cabinet/world/show-grammar.yml`
(v4), `instance/config/directions.yml` (org apex + scrub-header note),
engine route + engine-canvas + engine-client + inspect-card +
world-geo (chart-table tile), hatch-dialog display copy (+ tests).
