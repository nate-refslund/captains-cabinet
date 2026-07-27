# cp8 — independent verification of the two-agent round (renderer + capture bridge)

Verifier: fresh session, own clone-free scratch worktree, no priors from either
authoring agent. Everything below was re-measured this session; nothing is
carried over from either agent's report. Where an agent's claim survived my
re-measurement I say so; where it did not, the correction is stated.

Tip verified: `a541034aea062e72edf1f4769fc3a1a8fb30d788` (local == remote,
working tree clean).

---

## 1. Did the two agents clash? No.

Zero file overlap.

    comm -12 <(git show --name-only --format="" b658fe72 | sort -u) \
             <(git show --name-only --format="" 00beeb80 | sort -u)
    -> empty

b658fe72 (capture bridge) touched 25 paths; 00beeb80 (renderer) touched 16.
Neither set intersects. The three follow-up commits (f3705c46, 5447c81d,
6b6784e2) touch only CI-red fixes and review artifacts — no revert of either
agent's files. Every path from both commits is present at HEAD, including the
atlas (`cabinet/dashboard/public/world-assets/originals/iso/atlas-0.png`,
committed by the capture agent) and its manifest row (committed by the
renderer). The manifest/atlas split the capture agent flagged as a landing
hazard did not bite: both landed.

## 2. Suites at the tip — all green, re-run by me

| battery | result |
|---|---|
| `npm test` (dashboard vitest) | 2552 passed, 1 skipped, 133 files |
| `npx vitest run src/lib/world src/components/world` | 695 passed, 44 files |
| `npx tsc --noEmit` | exit 0 |
| `python3.12 -m pytest cabinet/scripts/tests -q` | 4781 passed, 28 skipped |
| `python3.12 -m pytest cabinet/scripts/world-capture/tests -q` | 6 passed |
| `sync-checks.py --check` | 4/4 mirrored files identical |
| CI run 30264672004 @ a541034a, per job | 8/8 success, 0 non-success |

## 3. The top-down bake-off — CONFIRMED, and strengthened

The renderer's own bake-off is real but was measured on a frame that draws
**zero sprites**: on this machine every LimeZu sheet is absent, so `/world`
top-down renders ground, coastline, camera and HUD and nothing else. A
pixel-identical diff over that frame says nothing about the 150
`TILE -> TOPDOWN_TILE` substitutions in sprite placement — the exact code that
changed. That is the class-11 trap: the test environment guarantees something
production does not.

So I ran it twice, against a true baseline.

**Method.** `git worktree add --detach` at 73c516ba (the last commit before any
iso work), hard-linked node_modules (package.json and lock are byte-identical
across 73c516ba..HEAD), two dev servers on 3200/3201, headless Chromium,
1600x1000, deterministic waits. Control first: same server captured twice =
**0 differing pixels**, so a cross-server diff is meaningful.

| capture | z=1 | z=3 |
|---|---|---|
| baseline 73c516ba vs HEAD, no art (as the renderer measured) | 0 px, max delta 0 | 0 px, max delta 0 |
| baseline vs HEAD, **67 synthesized stub sheets so sprites draw** | 0 px, max delta 0 | 0 px, max delta 0 |

For the second row I generated deterministic stand-in PNGs at each manifest
asset's exact `w`/`h`, so every sheet cut has distinct pixels and any placement
or source-rect drift shows. Engine render issues fell 76 -> 9 and the frame
fills with hundreds of placed sprites, buildings, props and characters. The
diff is still exactly zero at both zooms. **The whole top-down draw path —
ground sampling, sprite placement, depth sort, LOD, HUD — is byte-identical
before and after the refactor.** Stubs were removed afterwards; the tree is
clean.

Also checked: under `?iso=1`, with and without the LimeZu stubs present, the
canvas region is pixel-identical — the only differing pixels (1536, all in
y40-79 and y920-999) are the two issue-count badges. The iso path genuinely
draws nothing from those sheets.

## 4. `checks/verify.py` — run by me, from the ORIGINAL, not the mirror

Both frames captured fresh this session, `__pycache__` purged,
`PYTHONDONTWRITEBYTECODE=1`, then judged with
`/Users/nate/cabinet-meta/checks/verify.py` directly (capture.py uses the
in-repo mirror; I used the source of truth as a cross-check on the mirror).

**camp — GREEN 12/12, 0 surfaces unchecked.**

      PASS  on_road            0 sprites stand on a lane: []
      PASS  stacking           0 structure-on-structure: []; 2 distinct structure names recognised in this frame
      PASS  sprite_opacity     0 sprite BODIES part-transparent: []
      PASS  sprite_cutoff      0 sprites cut flat: []
      PASS  palette            0 sprites off-palette: []
      PASS  state_traceable    0 sprites with no state justification: []
      PASS  paint_fidelity     judged 181/250 sprites (72%); 0 left no mark []; 0 tied-depth structure pairs []; undeclared paint 0.00%; draw order NOT verified (see docstring); undeclared paint blind below ~100x100px
      PASS  era                era=camp: 0 future-rung, 0 stale-camp, 0 ahead-of-rung []; rung arm: 0 of 4 ladders judged, 1 unmapped (['lighthouse_lamp'])
      PASS  light              grade mean 155 sd 27 sat 0.40 span 168; lamp: state 'dark' — no lighthouse drawn; shadows NOT checked
      PASS  terrain            beach 100%; no plaza declared — square UNJUDGED; no fields declared — UNJUDGED
      PASS  depth_order        draw order correct on all 12164 contested pixels
      PASS  shadows            34/48 large sprites darken the ground at their foot (71%)

      every registered surface has a check

      GREEN · 12/12 checks pass · 0 surfaces unchecked

**hamlet — GREEN 12/12, 1 surface unchecked (`era`, structural).**

      PASS  on_road            0 sprites stand on a lane: []
      PASS  stacking           0 structure-on-structure: []; 13 distinct structure names recognised in this frame
      PASS  sprite_opacity     0 sprite BODIES part-transparent: []
      PASS  sprite_cutoff      0 sprites cut flat: []
      PASS  palette            0 sprites off-palette: []
      PASS  state_traceable    0 sprites with no state justification: []
      PASS  paint_fidelity     judged 137/177 sprites (77%); 0 left no mark []; 0 tied-depth structure pairs []; undeclared paint 0.00%; draw order NOT verified (see docstring); undeclared paint blind below ~100x100px
      PASS  era                era=hamlet: 0 future-rung, 0 stale-camp, 0 ahead-of-rung []; rung arm: 10 of 17 ladders judged, 7 unmapped (['berths', 'field_plots', 'harbor_boat', 'lighthouse_lamp']); NO vocabulary floor exists above hamlet — future-rung vocabulary UNVERIFIED at this era (era surface not claimed); camp-shelter ceiling covers 5 enumerated names only
      PASS  light              grade mean 155 sd 26 sat 0.40 span 164; lamp: state 'lit' — core L231 white 0.62 warm 53, halo warm 76; shadows NOT checked
      PASS  terrain            beach 88%; square paved 88% vs 17% outside
      PASS  depth_order        draw order correct on all 10887 contested pixels
      PASS  shadows            39/56 large sprites darken the ground at their foot (70%)

      NOT CHECKED — no check claims these surfaces:
         era        vocabulary matches the era; nothing from a future rung

      GREEN · 12/12 checks pass · 1 surfaces unchecked

No red arm. The mirror's output is byte-identical to the original's, so the
in-repo copy CI runs is honest.

## 5. Mutation testing — done by me, not taken on trust

**The six raster mutations**, each run through the ORIGINAL verify.py:

| mutation | red arm | exit |
|---|---|---|
| orphan-sprite | `state_traceable` only — `1 sprites with no state justification: ['bench']` | 1 |
| sprite-on-lane | `on_road` only — `1 sprites stand on a lane: ['great_house@1201,1142']` | 1 |
| no-shadows | `shadows` only — `26/56 large sprites darken the ground at their foot (46%)` | 1 |
| reverse-depth | `depth_order` only — `10790 of 10887 contested pixels won by the FARTHER layer` | 1 |
| unpaved-square | `terrain` only — `square paving 30% no denser than its surroundings 17%` | 1 |
| ghost-sprite | `paint_fidelity` only — `1 left no mark ['great_house@1096,829 0%']` | 1 |

**Seven code mutations of my own choosing**, applied in an isolated worktree at
the tip, each running only the owning test file — all KILLED:

    KILLED  engine-canvas re-declares its own tile constant      -> ratchets.test.ts
    KILLED  ?iso=0 no longer forces top-down                     -> projection.test.ts
    KILLED  the iso grid is no longer 2:1                        -> projection.test.ts
    KILLED  ISO_BASE stops re-basing the zoom                    -> projection.test.ts
    KILLED  the sea patch stops tiling (period: SEA_CELLS -> 0)  -> iso-terrain.test.ts
    KILLED  sprites are depth-sorted backwards                   -> iso-scene.test.ts
    KILLED  an absent rung is no longer honest zero              -> iso-pack.test.ts

My own first attempt at the sea mutant injected `periodic: false` — not a field
on `FieldOptions` (it is `period`), so the mutant was a no-op and "survived"
for my reason, not theirs. Worth recording as a harness note: **vitest
transpiles without typechecking, so a mutation that adds a bogus object key is
silently inert and reads as a surviving mutant.** Re-anchored on the real
constant it dies immediately.

## 6. The repo's aesthetic gate CANNOT judge this frame. It is not a pass.

`cabinet/scripts/world-aesthetic/world-aesthetic-gate.py --mechanical --render`
runs **2 of 6** gates. Four skip for want of inputs the iso still renderer does
not emit:

    edge_continuity  skipped: needs --map
    connectivity     skipped: needs --map
    scale_lint       skipped: needs --map
    label_overlap    skipped: needs --labels

and `gates/scale_lint.py:24` hardcodes `GRID = 16` with
`ENTITY_BAND = (16, 32)`, so even given a map it would reject the iso pack by
construction — the pack is not on a 16px grid.

Of the two that ran, `palette_coherence` goes RED on my frames (hamlet 86.7%,
camp 92.3% foreign-colour mass against a 5% limit). **That is not a finding
about the frames.** The decisive control: the same gate, same calibration, run
on the Captain's own APPROVED stills —

    cabinet-world-state-today-2026-07-26.png   ok=False  59.8% foreign mass
    cabinet-world-state-hatch-2026-07-26.png   ok=False  66.8% foreign mass

The gate fails the approved look. Its palette is fit to the 16px LimeZu
top-down corpus and has no authority over this art set. `clustering` ran and
tripped no bound (hamlet flat=0.051 dominant=0.222 busy_cv=1.104; approved
still flat=0.045 dominant=0.210 busy_cv=1.192 — comparable).

**One real lead survives that.** On the identical, miscalibrated axis my frames
sit ~26-27 points further from the corpus than the approved stills do
(86.7 vs 59.8; 92.3 vs 66.8). That gap is most plausibly the large flat
procedural-ground regions, not the sprite art. Worth a look; not a verdict.

## 7. What it actually looks like

Both frames judged against the approved stills at full size.

**Right, and not by luck:**

- Coastline, beach ring and surf edge read correctly at both states; the
  silhouette is close to the reference.
- **Buildings sit on the ground.** Every structure's foot is in ground contact,
  base-centre anchoring is correct, and trees in front of buildings occlude
  correctly. This is the thing most likely to be wrong in an iso port and it
  is right.
- **The harbour is attached to the shore.** The jetty meets the beach, the
  crane stands on the jetty, the packet is in water beside it, crates on the
  deck.
- **The lamp is lit and reads from across the island** — the white core is
  legible at full-frame scale, and `check_light` measures it (core L231,
  warm halo 76).
- **The camp reads as a camp**: one tent, one fire, one worn track to the
  shore, wild treeline, unlit cairn on the SE point. Not a thin village.
- At z=2 the native pack pixels are genuinely good — individual trees, bushes,
  flower clumps, tufts, rocks, a pond with lilies.

**Wrong, specifically:**

1. **Meadow shading draws as hard-edged ellipses.** Eight-plus flat darker-green
   ovals with razor edges across the open ground, worst on the camp meadow and
   around the plaza. The reference blurs its mask. This is the single most
   artificial tell in the frame and the first thing the Captain will see.
2. **The field plots are ellipses too.** The ploughed and crop plots are perfect
   ovals with a hard edge against grass. Furrows are correct and on the iso
   axis; the plot *outline* is not a shape anyone ploughed. The reference uses
   irregular fenced rectangles.
3. **The belt frames N/W/E and opens across the whole S/SE.** Defensible (the
   harbour is south) but the opening is much wider than the reference, which
   keeps tree cover down the left flank and around the harbour approach. As
   drawn it reads as a bald patch, not a deliberate harbour mouth.
4. **The village is under-furnished.** 13 distinct structure names in the hamlet
   frame against roughly 20 building types plus dense props in the approved
   still — no market stall, noticeboard, flagpole, benches, lamp posts, barrels,
   planters, fences, scarecrows or fowl. Empty grass dominates mid-left and
   mid-right. This is the eight measured-but-never-drawn ladders, and it is
   visible, not theoretical.
5. **At camp the shore is empty.** The approved hatch still has a log pile, a
   crate cairn, a rowing boat, a sailboat and two mooring buoys at the water
   line — the whole "someone landed here" story. Mine runs the worn track down
   to the beach and stops. `berths` / `harbor_boat` / `cargo_stacks` emit no
   anchors.
6. **The camp group is scattered, not composed.** Tent at ~(680,655), fire at
   ~(1000,800), track running from the fire. In the reference the cabin,
   noticeboard, fire and track are one group on the central axis. Nothing in
   the rules is violated; it just doesn't compose.
7. **The plaza is a small pale-grey blob**, not the reference's large warm
   flagstone square, and the lanes approach it without resolving into it.
   Several lanes dead-end in open grass (E and NW).
8. **Framing sits high.** Measured content bbox against the 2400x1760 canvas:

    | frame | fills height | bottom margin |
    |---|---|---|
    | approved hamlet | 91.2% | 153 px |
    | rendered hamlet | 81.8% | 319 px |
    | approved hatch | 86.4% | 239 px |
    | rendered camp | 81.6% | 293 px |

   Both the approved stills and my captures clip at the top (top margin 0), so
   that is house style, not a defect. The real difference is ~10 points of
   height and roughly double the dead sea below — the island is a little small
   and a little high in frame.

9. Minor: no blossom/colour-accent trees (reference has two); the sea texture
   is softer than the reference's finer ripple, consistent with the capture
   agent's note that the sea fbm is computed at 1/block resolution.

## 8. Confirmed open items (both agents disclosed these; I verified them)

- **The iso hit-test is deliberately inert** — `engine-canvas.tsx:1981`
  `if (isIso) return { kind: 'ground', id: 'ground' }`. Inspect cards, the
  mailbox, the chart table, deep-link selection and the Library entrance are
  all unreachable under `?iso=1`. The comment above it is honest about why.
  `pick.ts` is the fix and should be the next step, not a deferred one.
- **`market_stall` is gated on a ladder that does not exist.**
  `iso-layout/index.ts:644` calls `isBuilt(state, 'market_stall')`;
  `grep market_stall cabinet/world/growth-ladders.yml` returns nothing. With an
  honest state the stall can never appear. Content decision, unfixed.
- `?iso=1` survives the client's URL rewrite: the URL resolves to
  `?z=1.00&x=56.7&y=6.7&iso=1`, and `?x`/`?y` name a different place in the two
  kernels, as disclosed.
- Zero iso-pack issues in the console under `?iso=1`; all 23 engine issues are
  LimeZu-sheet absences belonging to the top-down path.

## 9. Process finding — mine, not theirs

While clearing ports I ran `pkill -f "next dev --port 3100"` to clean up my own
failed server start. Port 3100 was held by **another session's** dev server
(cwd `/Users/nate/cabinet-worktrees/world-frame-ci/cabinet/dashboard`, pid
14068) and I killed it. No files, git state or work were touched — but a
concurrent writer's dev server is down and they did not ask for that. The
lesson generalises with the two-agents-one-worktree lesson already recorded:
**a shared machine has shared ports; check what holds a port before killing by
pattern, and pick a port nobody else is on.** I used 3200/3201 afterwards.

---

## Verdict: PASS

The two agents did not clash, nothing was reverted, every battery is green at
the tip, CI is green per job, the twelve invariants pass on both states from
the original checks, all thirteen mutations I ran die on exactly their arm, and
the top-down bake-off holds at zero differing pixels under a far harder test
than the one that was reported.

The renderer's and the capture agent's own reports are accurate. Where either
hedged — the empty-frame bake-off, the unchecked `era` surface, the inert
hit-test, the undrawn ladders — the hedge was correct and understated rather
than overstated.

The world is not finished. It is measurably correct and it is under-furnished:
the rules hold, the art is good, and the composition is thinner and flatter
than the approved look, in the specific ways listed in §7. The two that will
read as *wrong* rather than *early* are the hard-edged ellipses (meadow shading
and field plots) and the empty camp shore.
