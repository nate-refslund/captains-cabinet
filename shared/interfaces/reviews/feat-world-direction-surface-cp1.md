# Checkpoint review — feat/world-direction-surface cp1 (FW-019)

Reviewer: lane-A build agent (Fable 5), full-diff review + live behavioral
verification, 2026-07-17. Scope: the whole branch batch (grammar v4 pair,
org apex block, port-calls extractor + tests, dashboard direction surface
libs/render/card + tests, commissioning display copy, docs). ~1,760 changed
lines total across the batch.

## Method

1. Every diff hunk read against origin/master (6e9460f5).
2. Every referenced symbol existence-checked in the real tree
   (`MAIN_ISLAND_LANE`/`LaneRecord` era-engine.ts:67/70, `outcomeLanes`/
   `declaredLanes` instance-lanes.ts:79/140, `toWorld` world-geo.ts:141,
   corpus color imports engine-canvas.tsx:85-98, `InspectTarget.kind
   'station'` inspect-card.tsx:18, `gateButtons`/`HATCH_BUTTON_ORDER`
   hatch-dialog.ts:117/53).
3. Grammar byte-untouched law proven mechanically: the ONLY deleted line in
   each of morphology.yml / show-grammar.yml is `version: 3` (git diff
   deletions grep).
4. Framework-consumer safety proven: `yaml.safe_load` of the edited
   directions.yml → top keys `{directions, org}`; `directions:` keys
   unchanged (polads/stephie/system-self) so the `direction_fit` id
   universe is untouched; framework pytest 796 passed.
5. Live behavioral run (dev server on :3210 from THIS worktree; live fleet
   dashboard on :3100 untouched — an accidental IPv6 dual-bind on :3100 by
   the pinned dev script was caught within seconds and killed; lesson noted
   below): engine payload shape, chart-table render + hit-test + deep-link,
   course-line dashes on-sea, card NOW/PROOF content verified verbatim.
6. Full validation battery re-run after the one fix (transcript in the PR
   proposal doc).

## Findings

1. **DEFECT (fixed in-branch): chart-table tile buried under dressing.**
   First-pick `CHART_TABLE_LOCAL` (33,10) sat under the manor's seeded
   east-hedge sprites (`dress:hedge:e0` anchors at local ly 11.6 with
   anchor(0.5,1) — overdraws ly 10; zone probe over the real dressing fold
   listed the collision). The prop drew correctly but was invisible.
   FIX: moved to (33,8) — NE curtilage open grass, clear of house bbox
   (ends lx 32), library lot (lx 35+, staged corner barrier lx 34), hedge
   line (ly 11.6+), journal desk (33,13). Verified live: prop visible
   (white chart + plank top + legs + shadow), canvas click at the tile
   opens the card, `?sel=chart-table` deep-link restores it. Composition
   fixed, never thresholds. Residual risk accepted + recorded: dressing is
   seeded scatter — a future dressing change could re-collide; the honest
   structural fix (dressing pass takes authored-prop exclusion tiles) is
   left to the dressing surface's owner rather than smuggled in here.
2. **Pre-existing, recorded, not fixed here: live browser frames vs the
   compositor-calibrated palette.** Raw canvas screenshots fail
   `palette_coherence` (~44–58% foreign; top foreign color 68,124,180 =
   the live water hue). CONTROL PROOF: a frame with ZERO direction-surface
   elements fails identically → the mismatch class is browser-frame vs
   PIL-corpus calibration, not this delta. The branch's own render delta
   uses only corpus constants (FOOT_SLATE_2 / PLANK_BROWN / FOAM_WHITE /
   INK_BLACK / amber 0xffc890 per the reserved-palette law). Mechanical
   gate GREEN on both regenerated compositor fixtures (egg + today).
3. **Checked, sound: hit-test precedence.** `chart_table` resolves before
   buildings in `onPrimary`; zone (±1.1/±1.2 tiles) overlaps no building
   hit slop at (33,8) (house slop ends 122.3 < 122.4 zone start; library
   slop starts 124.7 > 124.6 zone end).
4. **Checked, sound: fail-honest folds.** `readDirections` degrades to
   uncharted on missing file / missing org / malformed YAML (tests pin all
   three); `readPortCalls` returns null on absent/malformed artifact and
   skips malformed rows; engine route wraps both in the payload with no
   new auth surface (cookie-presence gate unchanged); no redis writes,
   GET-only ratchet holds.
5. **Checked, sound: purity + determinism.** `laneCourseState`/
   `voyageRender` are clock-free and IO-free (todayISO injected server-side
   — the route is the sanctioned clock door, same as the heartbeat age);
   canvas statics key carries the course/voyage signature so replay
   renders arrivals, no per-tick motion; no world-space text (source-scan
   vitest).
6. **Checked, sound: extractor security posture.** List-argv subprocess
   only (git log/show/rev-parse), no shell, fixed repo-relative paths,
   yaml.safe_load, atomic tmp+replace write into the ALREADY-gitignored
   `shared/interfaces/world/` (check-ignore verified). Corridor guardrails
   (non-shell exec, fixed paths, safe YAML schema) all satisfied; secret
   scan of every new file clean.
7. **Checked, sound: tacking boundary semantics.** `daysBetween` inclusive
   14-day edge tested (14 in / 15 out); today's real data honestly reads
   docked_refitting (15 days since the 2026-07-02 flips) — the live card
   agreed.
8. **Process note (lesson): the dashboard `npm run dev` script pins
   `--port 3100`** (the live dashboard's port). Running it from a worktree
   dual-binds IPv6 :3100 next to the live IPv4 listener and can intercept
   localhost traffic. Always `npx next dev --port <spare>` from worktrees.

## Verdict

Ship as a Captain-merge PR. All gates green post-fix (binding validator 32
entries 0 fails; CI-parity SKIP proof; vitest 1809; tsc; next build;
framework 796; layer-sep new=0; A13 parity green with the pair untouched;
extractor pytest 13; aesthetic self-tests 87 + compositor fixtures GREEN).
Ledger row + A13 plan-table row deferred to the integrator (files
blocked-dirty by another wave — dirty-guard).
