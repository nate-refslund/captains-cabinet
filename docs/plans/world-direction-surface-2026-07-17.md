# World Direction Surface — design record (2026-07-17)

Lane A, Wave 1 — per Captain ratifications 2026-07-17 + full-autonomy grant
2026-07-07 (both recorded in `shared/interfaces/captain-decisions.md`).
Grammar-law PR: **nothing here auto-merges** — the Captain merges the branch
(`feat/world-direction-surface`).

The org's direction layer becomes a world surface: the **apex direction**
ratified 2026-07-17 renders at a **chart table** in the Captain structure's
curtilage, each direction lane gets a **plotted course** with an honest
course state, achieved-outcome flips become dated **port calls** at the
quay, and the harbor boat is elevated to a **voyage** surface.

## What renders

| Surface | Where | Truth source |
|---|---|---|
| Chart table (small bound prop) | fixed authored tile `CHART_TABLE_LOCAL` (33,8 main-island local — great_house NE curtilage; first pick 33,10 sat under the seeded east-hedge dressing, caught on a live render probe and moved — composition fixed, never thresholds) | `instance/config/directions.yml` (morphology `manor_chart_table`) |
| Plotted course lines | quay → each berthed direction lane's isle slot | `laneCourseState()` fold over directions + outcomes + port calls |
| Port-call chalk count-marks | at the berth (dates card-only) | `shared/interfaces/world/port-calls.json` (git-derived artifact) |
| Voyage boat | moored at quay / on the course line (tacking) | same artifact + course fold; position pure f(flip date, server today) |
| Direction-chart card | authed inspect card (`?sel=chart-table` deep-link) | engine payload `{directions, courses, portCalls}` |

No world-space text anywhere: mission text, lane names and dates live ONLY
in the authed card (pinned by a source-scan vitest in `course.test.ts`).

## Decisions

1. **Apex placement** — a NEW top-level `org: apex:` block in the TRACKED
   `instance/config/directions.yml`, sibling of `directions:` (never inside
   it: every `directions:` key is a valid `direction_fit` id —
   `framework/acting/action_lane.py:232,297,541` fold only
   `doc["directions"]`, so the addition is additive-safe). The ratified text
   is deliberately generic, so the tracked file carries the REAL text — the
   scrub header now records that exception. Deployments whose untracked
   overlay lacks `org:` degrade to a grey **uncharted** card (fail-honest
   reader).
2. **No civic anchor minted** — the manor anchor is morphology law
   (`anchors: manor: N-beyond-law`, morphology law block) and the
   `great_house` element IS the manor structure; the chart table is a small
   bound element in its curtilage on the mailbox precedent (morphology entry
   + engine payload + render + card). `civic_anchor_exception` budget stays
   0/3.
3. **Port calls replay = git** — flip dates are exactly recoverable from
   `instance/config/outcomes.yml` git history (the calibrated backtest's
   proven extraction, `world-growth-backtest.py` step 3).
   `cabinet/scripts/world-port-calls.py` materializes them into a
   rebuildable runtime read-model; regenerate-and-diff IS the replay. The
   tasking text suggested `replay: ledger`; file convention for
   outcomes-git-derived entries is `git` (`lane_reef_buoys` precedent) —
   deviation recorded here and in the PR.
4. **Artifact path adaptation (blocked-dirty)** — the work order wanted
   `shared/interfaces/world-port-calls.json` + a `.gitignore` line, but
   `.gitignore` is DIRTY in the live tree (another wave owns it). The
   artifact lives at `shared/interfaces/world/port-calls.json` instead —
   inside the ALREADY-gitignored `shared/interfaces/world/` runtime
   read-model directory — achieving the same class of protection with zero
   `.gitignore` edit.
5. **Course states — the reduced honest set** (ledger-state semantics ONLY):
   - `docked_refitting` — ≥1 active outcome: an open WINDOW in the ledger.
     A ledger claim, never a work claim.
   - `tacking` — an achieved flip within `TACKING_WINDOW_DAYS = 14`
     (inclusive) AND an active successor window.
   - `adrift` — direction present, zero active outcomes, not retired —
     exactly the renewal-loop gap the directions contract header names.
   Join universe: (direction lanes ∪ outcome lanes) ∩ declared context
   lanes, minus `system-self` (its course IS the main island / chart
   table), minus retired + instance-test lanes (already reef buoys).
   Undeclared pseudo-lanes (e.g. `world-onboarding-v1b`) get no course.
6. **Honest drift verdict: MISSING** — "is crew actually working this lane
   this week" is NOT claimable: `org_events.lane_slug` exists and is
   indexed but carries only `{captains-cabinet, default}` (no lane slug has
   ever been stamped; zero 7d `work_item_completed` rows per lane), the
   census keyframe has no per-lane field, and lane work lives in external
   repos. The drift gauge renders **grey "unmeasured"** with the exact copy
   pinned in `DRIFT_UNMEASURED_COPY`; the named future emitter: work-routing
   emitters stamp real lane slugs into the already-indexed
   `org_events.lane_slug` column, then `world-census.py` gains per-lane
   int keys (int-only keys satisfy the census PII fence).
7. **Voyage** — boat position is a pure function of (course state, last
   port-call date, server-stamped `todayISO` from the engine route — the
   sanctioned clock door). No random motion; underway renders only for a
   tacking lane (newest port call, deterministic lane-name tie-break),
   out-and-back triangle over the 14-day window. Boat SIZE/vocab stay the
   `harbor_boat` ladder's — `growth-ladders.yml` is deliberately untouched
   (no new ladder keys, no schema change, era-vocab contract untouched by
   construction).
8. **Reserved palette held** — amber (`0xffc890`, the verified in-bin warm
   hue) marks `adrift` ONLY, dual-coded with the slack/sagging dash shape;
   grey stays unmeasured-only; red never. Tacking/docked course lines ride
   neutral corpus hues (`PLANK_BROWN` / `FOOT_SLATE_2`) with dash-cadence
   shape coding.
9. **Chart-table sprite** — no pack ships a chart table; the render is a
   derived own-pixel composition in proven corpus hues (the audited fish
   precedent), never a wrong-object sprite substitution (the v1a review
   class).
10. **Commissioning copy (ruling 3) — minimal true scope**: the only live
    display strings were two `hatch-dialog.tsx` aria-labels (now
    "commissioning dialog"); `COMMISSIONING_STAGES` (keel-laying → launch →
    christening → sea trials → commissioning → maiden voyage) exported from
    `lib/world/hatch-dialog.ts` as the display ladder. FROZEN machine ids:
    `DialogMode 'hatching'`, the `HatchButton` set, `hatch.sh` /
    `null-hatch.sh` / `hatch-lib` and every `egg-*` script/ledger/manifest
    name, hatch route paths, README/CONTRIBUTING install-flow "hatch" prose
    (install authority doc unchanged), and `decision-queue-card.tsx`
    "HQ Chair" (ruling 4 = another lane's surface).

## Grammar deltas (v4)

- `cabinet/world/morphology.yml` → version 4; law block + every v1/v2/v3
  entry byte-untouched (verified: the only deleted line in the diff is
  `version: 3`). New entries: `manor_chart_table`, `harbor_port_calls`,
  `lane_course_state`, `harbor_boat_voyage` — all validator-green live
  (values today: 4 / 2 / 8 / 2026-07-02).
- `cabinet/world/show-grammar.yml` → version 4; same byte-untouched law.
  New blocks: `chart_table_view` (mailbox_view law clone — read-only,
  deep-link, never actuate) and `voyage` (construction's pure-function T0
  arrival pattern + the three stall-state render laws). `grammar.ts`
  ignores unknown top-level keys (additive-safe); consumption rides
  dedicated lib modules (`directions.ts`, `course.ts`) per the v3 weather
  precedent.

## Reality notes (where the tasking and the ground disagreed)

- `grep -c -e 'status: active' instance/config/outcomes.yml` returns **8**
  today (7 active outcome rows + 1 header comment line), not the tasking's
  6. The binding is a mechanism-liveness proof, not a rendered number — the
  engine folds outcomes.yml properly; noted for the record.
- `.gitignore`, `docs/plans/operative-egg-ledger-2026-07-07.yml` and
  `docs/plans/operative-egg-plan-2026-07-07.md` are DIRTY in the live tree
  (another wave owns them) — excluded per dirty-guard. Consequences: the
  artifact path adaptation above, and **no ledger row lands in this PR**
  — the integrator appends `WORLD-DIRECTION-SURFACE` + the A13 plan-table
  row once the owning wave lands (the A13 parity gate is green pre-existing
  on this branch: the pair as checked out parses 1:1).

## Validation battery (all green before PR)

See the PR body draft (`docs/proposals/world-direction-surface-pr-2026-07-17.md`)
for the exact transcript list: binding validator live + CI-parity SKIP
proof, growth validate + backtest replay (port-call dates match
`outcome_flip_dates`), the port-calls pytest suite, dashboard
vitest/typecheck/build, framework pytest, layer-separation gate, aesthetic
harness on regenerated fixtures.
