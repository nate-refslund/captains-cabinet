# cp9 — repairing what the cp8 verifier found

Branch `iso-port-composition`. Base of this round: `bbbe537a` (the cp8 addendum).
Every number below was produced by a command run in this session, in this
worktree, and the command is named beside it.

---

## 0. What this round was asked to do

The cp8 verification PASSED the work and listed, in its own words: one blocking
landing problem, two confirmed-open code defects, eight visual findings, and a
gate that "cannot judge this frame". This round repairs them or says why not.

| # | cp8 finding | state |
|---|---|---|
| B | PR #223 CONFLICTING on the frozen COG-4 review digest | **fixed** — and a NEW conflict has since appeared (§7) |
| 1 | meadow shading draws as hard-edged ellipses | **fixed** |
| 2 | the field plots are ellipses too | **fixed** |
| 3 | the belt opens across the whole S/SE | **not fixed** — measured, §6 |
| 4 | under-furnished; eight undrawn ladders | **fixed** |
| 5 | at camp the shore is empty | **fixed** (partly — §5) |
| 6 | the camp group is scattered, not composed | **not fixed** — §6 |
| 7 | the plaza is a small pale-grey blob | **not fixed** — root cause found, §6 |
| 8 | framing sits high | **not fixed** — measured, §6 |
| H | hit-test deliberately inert (`engine-canvas.tsx:1981`) | **fixed** |
| H | `market_stall` gated on a ladder that does not exist | **fixed** |
| A | the aesthetic gate cannot judge this frame | **not fixed** — §6 |

---

## 1. The blocking landing problem

`git merge-tree --write-tree origin/master HEAD` exited 1 on
`shared/interfaces/reviews/cognitive-core-phase-4-review.md`: master (PR #229)
and this branch (6b6784e2) had each legitimately re-bound the same
`Reviewed-Scope-Digest` line. The two sides' *notes* merged cleanly; only the
digest conflicted, which is what made the PR read CONFLICTING while nothing
about the two changes actually disagreed.

Resolved by taking **neither** side's value. Master had moved
`framework/authority/{classifier,grants,policy_engine}.py`; this branch had
moved `cabinet/scripts/egg-export-manifest.txt`. Different in-scope paths, so
the only value that describes the bytes that now exist is one recomputed over
the merged tree:

```
$ python3.12 cabinet/scripts/cognitive-phase4-review-scope.py --print
807bad894caab9a4dc1ed9239dbe6cd19ef59d5c900949a2e8c155ed9469d709
$ python3.12 cabinet/scripts/cognitive-phase4-review-scope.py --verify \
      shared/interfaces/reviews/cognitive-core-phase-4-review.md
COG-4 review binding: OK — tested bytes match the reviewed scope digest (807bad89…)
```

All three re-bind notes are kept. The world/iso work touches no COG-4 scope
path — checked, not assumed: the 85-entry `EXPECTED_SCOPE` contains zero
`world` or `dashboard` entries.

---

## 2. The two code defects

**`market_stall` was gated on a switch wired to nothing.**
`iso-layout/index.ts` asked `isBuilt(state, 'market_stall')`.
`cabinet/world/growth-ladders.yml` has 29 ladders and no `market_stall`
(enumerated), so the predicate was false on every state that has ever existed
and the stall could not draw at any era. `blueprint.ts` justified it through the
same dead predicate, so both halves agreed about a thing neither could produce.
compose.py:966 gates it on the era alone; it now does too, and the arm that
proves it composes a hamlet with **no stages at all** and requires a market.

**The iso hit test was a constant.** `engine-canvas.tsx` opened with
`if (isIso) return { kind: 'ground', id: 'ground' }` under a docstring saying
the iso world "carries no data" — true only because nothing had been written to
answer. `pickIsoSprite` (iso-scene.ts, pure, four arms in iso-scene.test.ts)
walks the scene's own sprites front to back on the SHARED ground diamond from
`../projection`. Decoration is transparent to it. A ladder role becomes a card
by `WorldBuilding.element`, never by id.

---

## 3. The dressing stage — why the island was empty

`composeLayout` emitted eleven building roles and nothing else. **Ten ladders
that the growth file MEASURES had no placement rule at all**, so a rung change
on any of them moved nothing on the island: `law_plot`, `pens`, `water_store`,
`composter`, `noticeboard`, `flagpole`, `veto_plinth`, `observatory`,
`journal_desk`, `lantern_posts`. That is not a cosmetic gap — a world whose
measured state cannot reach the frame is a dashboard that does not report.

`iso-layout/dressing.ts` ports compose.py:944-1115 and its helpers. Three
classes, and the difference decides what may draw:

- **LADDER** — each on its own rung, emitted under its OBJECT name so the pack's
  `(object, era, rung)` table picks the art.
- **VILLAGE LIFE** — entitled by the ERA and nothing finer (compose.py:523).
  EMPTY at camp.
- **LANDING** — the boats and the buoys, at every era, because the org's own
  existence is the rule: the hatch frame is the arrival.

Every item goes through `placeOnGround` against lanes, coastline, tilled plots
and neighbours, and is DROPPED when it cannot settle.

| | before | after |
|---|---|---|
| hamlet sprites | 177 | 299 |
| distinct structure names recognised | 13 | 18 |
| ladders the era arm could judge | 10 of 17 | 16 of 28 |
| camp sprites | ~250 | 254, with a landing at the waterline |

---

## 4. Every arm proven to fail, including the new one

`cabinet/dashboard/src/lib/world/capture.test.ts`, 10/10:

```
✓ camp: all twelve invariants pass on a real frame
✓ hamlet: all twelve invariants pass on a real frame
✓ orphan-sprite turns state_traceable red on hamlet, and nothing else
✓ sprite-on-lane turns on_road red on hamlet, and nothing else
✓ no-shadows turns shadows red on hamlet, and nothing else
✓ reverse-depth turns depth_order red on hamlet, and nothing else
✓ unpaved-square turns terrain red on hamlet, and nothing else
✓ ghost-sprite turns paint_fidelity red on hamlet, and nothing else
✓ camp-bench turns state_traceable + era red on camp, and nothing else
✓ camp-bench is NOT a defect at hamlet, where a bench is entitled
```

Two sensor problems were found and fixed in the process:

1. **`orphan-sprite` had stopped being a defect.** It added a BENCH; the day the
   dressing stage landed, a bench at hamlet became a real entitlement, so this
   arm would have gone quietly green while still printing that orphans are
   caught. It now uses `posture_banner`, which nothing justifies at any era.
2. **The last row is the INVERSE control.** Every mutation row is satisfied by
   *a* red, and a frame can go red for reasons unrelated to the rule under
   test. `camp-bench` at hamlet must leave the frame GREEN.

Three mid-round reds were the checks doing their job and are worth recording
because each was a real defect in new code, caught by a sensor rather than by
eye: `chart_table`/`dog_sleeping` unlisted (state_traceable), the chicken coop
31% inside the watermill kiln (stacking), and a log pile + crate cairn on the
camp shore (era — see §5).

---

## 5. One rule won against new content

The landing kit briefly carried a log pile and a crate cairn onto the camp
shore, because the approved hatch still has cargo at its waterline.
`check_era`'s `ERA_MIN` table floors both `wood_pile` and `crate_single` at
hamlet, and the camp frame went red immediately.

**The table is right and the content was wrong.** Sawn timber stacked in a pile
and a made crate are a settlement's output, not an arrival's — and compose.py
agrees from the other side: both names are in its `AMBIENT` set, which it
refuses to draw at camp. The content moved; the floor did not. The camp landing
is the boats and the buoys, which is exactly compose.py:1158-1161's own
unconditional set.

---

## 6. Not fixed, and why — each one stated rather than left silent

**The plaza is grey (cp8 #7). Root cause found; the fix is not mine to make.**
Measured on the sprites-free ground layer against the approved still:

| | our square | approved square | our road N | approved road N |
|---|---|---|---|---|
| mean RGB | (161,151,136) | (214,186,139) | (139,134,85) | (208,197,144) |

The approved still paves its ROADS and its SQUARE in the same warm pale stone.
That is compose.py:345-350: at the `cobbled_road` rung the reference swaps the
road texture to COBBLE **warmed 34% toward DIRT** and — because it reassigns the
variable — the square is warmed with it. **This port implements no road-rung
texture rule at all: it paints `dirt` at every rung.** That is a real gap and it
is named here rather than fixed, for two reasons: neither shipped fixture
reaches `cobbled_road` (both are at or below `gravel_road`, where the reference
also paints dirt and a grey square, so no shipped frame would change), and the
faithful implementation is a per-pixel blend of two rendered fields, which
produces colours outside every ramp and would need a stated carve-out in
`test_every_surface_emits_only_its_own_ramp` — a palette-purity decision, not a
rendering fix. Recorded as a gap, not closed.

**Framing (cp8 #8).** Measured content bbox on the 2400×1760 canvas, sea-masked:
approved 90.6% of height / 154px bottom margin; ours 84.4% / 274px. The island
RADII are already byte-identical to the reference (`ISLAND_RADII = {hw: 962,
vh: 784}` against compose.py:60 `HWr, VHr = 962, 784`), so the delta is not the
island: it is the coastline wobble plus the quay rung. The approved still has a
stone quay wall wrapping the cove; the hamlet fixture is at `timber_jetty`,
which builds a much smaller deck. Changing the fixture to make the picture fill
the frame would be fixture-fiddling, and changing the radii would put the layout
out of step with the reference it is a port of.

**The belt opens across the S/SE (cp8 #3).** The south-east is where the tilled
plots are, and the plots now cover the ground the belt would have taken. A bald
SE with three worked fields in it is not the same defect as a bald SE with
nothing in it. Not fudged; if the Captain wants cover down that flank it is a
deliberate change to `ring.ts`'s angular gate, not a bug fix.

**The camp group is scattered (cp8 #6).** True, and unchanged: the tent, the
fire and the track are at their authored compass anchors. Composing them is an
authored-layout decision, and this round's budget went to the ten ladders that
could not draw at all.

**The aesthetic gate cannot judge an iso frame (cp8 §5).** Confirmed and NOT
repaired. Four of six gates need a `--map` the iso world does not have, and
`scale_lint` is a 16px-LimeZu-grid gate. cp8 already showed `palette_coherence`
fails the Captain's OWN approved stills at 59.8% and 66.8% — so the suite has no
authority over these frames, and building an iso profile for it now would be
more substrate with no consumer. The twelve invariants in `checks/` DO judge
this frame, and every one of them is proven to fail.

---

## 7. The landing is blocked again — and a second session is in this worktree

`gh pr view 223`: `"mergeable":"CONFLICTING","mergeStateStatus":"DIRTY"`. The
COG-4 digest conflict is GONE; this is a new one. Master moved to `0ab0cc2b`
(PR #212, "one projection module — collapse the five copies of the transform")
after the cp8 round closed, and that is the same work this branch already
carries. `git merge-tree` reports an **add/add** conflict on exactly two paths:

```
cabinet/dashboard/src/lib/world/projection.ts
cabinet/dashboard/src/lib/world/projection.test.ts
```

Measured, so whoever resolves it does not have to rediscover it:

- **`projection.ts`: this branch is a functional superset.** Master's copy has
  no `ISO_BASE` and no `worldScale`; its camera math multiplies by `cam.z`
  directly. Taking master's would break the iso camera.
- **`projection.test.ts`: neither side is a superset.** Master has 32 `it(` arms,
  this branch 15 — two independent rewrites of the same properties, renamed and
  renumbered. Master's names include arms this branch does not have by any name
  (`48x24 fits the structures; the rejected 16x8 does not`, `the pack is real
  and non-trivial`, `the origin is the origin (no hidden offset)`). A blind
  "take ours" LOSES those. The union has to be built by hand.

**I did not resolve it, deliberately.** A second Claude session is working in
this same worktree: at 15:34 it ran `git merge origin/master` here, hit these
two conflicts, and then aborted — and the abort destroyed this session's
in-flight uncommitted work, which had been swept into its merge commit
(`bf5cbc9f`, now dangling; recovered from it file by file). Two agents
resolving the same add/add conflict on the same branch at the same time
produces a mess, and that merge is a judgment call about two rewrites, not a
mechanical re-bind. It needs one owner.

Consequence, and it is the same one cp8 recorded: GitHub will not run a
`pull_request` workflow while the PR is DIRTY, so the commits below have no CI
run of their own. Everything in §8 was measured locally on the committed tree.

---

## 8. The batteries, on the committed tree

```
$ npx tsc --noEmit                      exit 0
$ npm test (vitest)                     132 passed | 1 skipped (133 files)
                                        2558 passed | 1 skipped (2559 tests)
$ npx vitest run src/lib/world src/components/world
                                        44 files, 701 passed  (was 695 — six new arms)
$ pytest cabinet/scripts/tests -q       4785 passed, 28 skipped
$ pytest cabinet/scripts/world-capture/tests -q   6 passed
$ sync-checks.py --check                4/4 mirrored files identical
```

`__pycache__` purged and `PYTHONDONTWRITEBYTECODE=1` set for every python run.

### verify.py, verbatim, both eras

**camp — GREEN 12/12, 0 surfaces unchecked**

```
  PASS  on_road            0 sprites stand on a lane: []
  PASS  stacking           0 structure-on-structure: []; 2 distinct structure names recognised in this frame
  PASS  sprite_opacity     0 sprite BODIES part-transparent: []
  PASS  sprite_cutoff      0 sprites cut flat: []
  PASS  palette            0 sprites off-palette: []
  PASS  state_traceable    0 sprites with no state justification: []
  PASS  paint_fidelity     judged 185/254 sprites (73%); 0 left no mark []; 0 tied-depth structure pairs []; undeclared paint 0.00%; draw order NOT verified (see docstring); undeclared paint blind below ~100x100px
  PASS  era                era=camp: 0 future-rung, 0 stale-camp, 0 ahead-of-rung []; rung arm: 0 of 4 ladders judged, 1 unmapped (['lighthouse_lamp'])
  PASS  light              grade mean 155 sd 27 sat 0.40 span 168; lamp: state 'dark' — no lighthouse drawn; shadows NOT checked
  PASS  terrain            beach 100%; no plaza declared — square UNJUDGED; no fields declared — UNJUDGED
  PASS  depth_order        draw order correct on all 12164 contested pixels
  PASS  shadows            36/50 large sprites darken the ground at their foot (72%)

every registered surface has a check

GREEN · 12/12 checks pass · 0 surfaces unchecked
emit camp: 254 sprites, 1 lane runs, 0 fields, justified 6
audit: onLane 0, stacked 0, inWater 0, outsideHarbour 0
```

**hamlet — GREEN 12/12, 1 surface unchecked**

```
  PASS  on_road            0 sprites stand on a lane: []
  PASS  stacking           0 structure-on-structure: []; 18 distinct structure names recognised in this frame
  PASS  sprite_opacity     0 sprite BODIES part-transparent: []
  PASS  sprite_cutoff      0 sprites cut flat: []
  PASS  palette            0 sprites off-palette: []
  PASS  state_traceable    0 sprites with no state justification: []
  PASS  paint_fidelity     judged 192/299 sprites (64%); 0 left no mark []; 0 tied-depth structure pairs []; undeclared paint 0.00%; draw order NOT verified (see docstring); undeclared paint blind below ~100x100px
  PASS  era                era=hamlet: 0 future-rung, 0 stale-camp, 0 ahead-of-rung []; rung arm: 16 of 28 ladders judged, 10 unmapped (['berths', 'field_plots', 'harbor_boat', 'law_plot']); NO vocabulary floor exists above hamlet — future-rung vocabulary UNVERIFIED at this era (era surface not claimed); camp-shelter ceiling covers 5 enumerated names only
  PASS  light              grade mean 155 sd 27 sat 0.41 span 165; lamp: state 'lit' — core L232 white 0.62 warm 53, halo warm 86
  PASS  terrain            beach 88%; square paved 88% vs 17% outside
  PASS  depth_order        draw order correct on all 10045 contested pixels
  PASS  shadows            42/61 large sprites darken the ground at their foot (69%)

NOT CHECKED — no check claims these surfaces:
   era        vocabulary matches the era; nothing from a future rung

GREEN · 12/12 checks pass · 1 surfaces unchecked
emit hamlet: 299 sprites, 19 lane runs, 3 fields, justified 66
audit: onLane 0, stacked 0, inWater 0, outsideHarbour 0
```

### The top-down path is unchanged — how that is known

`engine-canvas.tsx` is the only file this round touched that the top-down path
reads at all; everything else changed is under `iso-layout/`, `iso-scene.ts`,
`blueprint.ts` or `world-capture/`, none of which the top-down render reaches.
`git diff bbbe537a..HEAD -- cabinet/dashboard/src/components/world/engine-canvas.tsx`
is five hunks and every one is iso-only:

| hunk | what | reachable from top-down? |
|---|---|---|
| `@@ -47` | `pickIsoSprite` added to an import list | no behaviour |
| `@@ -1252` | meadow alpha bucketing, inside `buildIsoTerrain` | no — called only when `isIso` |
| `@@ -1957` | `isoHitTarget`, a new function | no — called only from the `isIso` branch |
| `@@ -1967` | a comment above `if (isIso) …` | no |
| `@@ -1976` | `if (isIso) return { kind:'ground' }` → `return isoHitTarget(wx, wy)` | no — the top-down branch below is byte-identical |

**Stated plainly: I did NOT re-run the browser pixel bake-off this round.** cp8
ran it (two servers, headless Chromium, 1600×1000, with and without 67
synthesized stub sheets, 0 differing pixels at z=1 and z=3) against the same
top-down code, and the diff above shows that code is byte-identical since. What
is proven here is a diff and a full suite, not a fresh frame comparison.

---

## 9. What is still absent under `?iso=1`

Named because silence about a known absence is the failure mode this project has
paid for repeatedly.

| surface | state |
|---|---|
| **hit-test / pick** | **LANDED this round.** `pickIsoSprite` + the building/mailbox/chart-table mapping. |
| **roof cutaway** | **ABSENT.** `cutaway` is threaded into the canvas props and consumed only by the top-down path. Under iso no roof lifts and no interior renders — the Great House wardroom is unreachable. |
| **characters / officers** | **ABSENT.** `officerPositions()` is tile-space and top-down-only; `LOD_RULES[...].officers` is never consulted under iso. No officer, no commuter, no crew figure draws. The 163-frame pack ships no character art at all — this is an ASSET gap before it is a code gap. |
| **the LIFE layer** | **ABSENT.** `p.life` (commuters, construction sites, their progress) is read only inside the top-down branch. Construction scaffolds, walkers and site signs do not exist under iso, and `isoHitTarget` therefore cannot return `{kind:'site'}`. |
| **weather / dynamics** | partial. `drawIsoDynamics()` composites the lighthouse lamp onto `fxG`; the rest of the top-down dynamic layer is not ported. |
| **road-rung texture** | ABSENT — see §6. `cobbled_road` paints dirt like every lower rung. |
| **LOD** | ABSENT under iso by design this round: the statics key deliberately omits the tier, so zoom changes level of detail for nothing. |

---

*Provenance: per the 2026-07-07 full-autonomy grant + the 2026-07-21
ownership-on-GO ruling.*
