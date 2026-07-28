# cp11 — the lectern, the meadow, and the world that was drawing yesterday's org

Branch `iso-port-composition`. Three defects the Captain named on 2026-07-27,
each with the measurement that found it and the mutation that proves the arm
guarding it can fail. Written before the commit, per FW-019.

## 1. A LECTERN STANDING IN OPEN GRASS

**Symptom.** The consequence ledger — an open book on a stand — alone in a field
beside three fence posts and a rock, with no law plot around it.

**Root cause.** Every district in `iso-layout/dressing.ts` is anchored at a fixed
compass point and its props were placed at fixed offsets from that anchor, gated
on the ERA alone (`life`). So a district whose measured structure had never been
built still drew its whole yard, and a district built at a LOW RUNG drew a yard
sized for a full one. Reproduced offline on the org's real state (hamlet 0.439,
`law_plot` at rung `wood_fence` = 2 runs): the plot is two fence sections, the
posts stand three abreast over 148px, and the ledger sat at a fixed `LAW.x + 104`
— a clear 100px past the last fence.

**THE FULL AUDIT the Captain asked for.** Every object placed at a fixed offset
from a district anchor, and whether its district gates it:

| district | anchor | drawn with NO district gate (before) | now |
|---|---|---|---|
| CENTRE | `ctx.great` (placed) | — already gated on the great house | unchanged |
| SQUARE | fixed `SQUARE` | stall, goods, signpost, barrow, barrel, crate, chicken, bench ring, bush ring | **unchanged, deliberately** — the square is PAVED by the paint stage whenever `village`, so these props have ground that exists; ladder items (noticeboard, journal desk, flagpole, lamp posts) were already rung-gated |
| LAW | fixed (1010,392) | `law_post` ×3, `consequence_ledger` | gated on `law_plot`; posts capped to the plot's runs; ledger walks to the plot's far end |
| MEMORY | `ctx.lib` (placed) | — already gated on the library | unchanged |
| WORKS | `ctx.works ?? fixed(1830,800)` | `wood_pile`×2, `crate_single`×3, `barrel_single`×2, `wheelbarrow`, `water_trough` | gated on the workshop being placed; the LADDER items (water store, composter, pens) keep the fallback anchor — each is entitled by its own rung |
| FIELDS | `ctx.fields ?? fixed(1620,1180)` | `chicken`×2, `cart`, `scarecrow`, `veg_garden`, 3 fence runs | gated on the outbuildings being placed (`haystack` was already count-gated) |
| RESIDENTIAL | fixed spine (742,742)→(712,1050) | fence run, lamp line, `laundry_line`, `beehives` | gated on at least one dwelling being placed |
| OBSERVATORY | fixed (960,372) | `bench` | gated on the observatory ladder |
| TRAINING | fixed (760,470) | `scarecrow`, fence run | **left era-entitled and REPORTED** |
| SIGNALS | fixed (840,1226) | `mailbox`, `signpost`, `lamp_dark`, `bench` | **left era-entitled and REPORTED** |

TRAINING and SIGNALS have **no ladder at all** — `cabinet/world/growth-ladders.yml`
measures no `dojo`, `mailbox` or `signals`. Gating them on an invented name would
be a switch wired to the empty set, which is the exact defect the market-stall
comment in the same file records paying for. They stay as they are and the
missing ladder is named here rather than papered over.

**Why `check_state_traceable` never caught any of it:** `consequence_ledger` is
in `VILLAGE_LIFE_FRAMES`, and blueprint.ts justifies that whole class at hamlet
and above. The check asks "is this frame entitled by the state" and the answer
was honestly yes. It has no notion of a district, so it cannot ask the question
the Captain's eye asked. The new arms live in `iso-layout/dressing.test.ts`.

**Mutations (7/7 fire).** `law-ungated`, `ledger-fixed-off`, `law-postcap-off`,
`works-ungated`, `fields-ungated`, `homes-ungated`, `obs-ungated` — each reverts
exactly one rule; each turns the arm that guards it RED.
`law-postcap-off` **came back GREEN on the first round** and is recorded in the
test file's own header: every other arm builds a three-run plot where
`Math.min(3, lawRuns)` is a no-op, so nothing could see the cap. The fix was a
sensor (assert 1 post on a 1-run plot), not a loosened claim.

## 2. THE MEADOW READ AS HARD DARK ELLIPSES

**Root cause.** compose.py:149 draws its 70 patches into one mask and blurs the
WHOLE mask by 26px before pasting the dark grass through it. This port replaced
that blur with an irregular OUTLINE (a lobed rim instead of an oval one) — and a
lobed edge is still an edge. Neither renderer blurred anything.

**Fix.** `PAINT_FEATHER` in `iso-layout/paint.ts` owns the number; blueprint.ts
ships it in the draw list beside `lane_squash`; `raster.py` reads it from there
and blurs the union; `engine-canvas.tsx` builds ONE feathered alpha mask per
region (the per-blob strength is carried in the mask's own alpha via the same
weakest-first incremental-alpha identity the bucket loop used, so `max(w)` is
preserved) and paints the dark grass through it with `setMask({channel:'alpha'})`
— the default `'red'` channel would square the ramp and turn the feather back
into a shoulder.

**Measured** on the org's real state, meadow mask, largest one-pixel step:
`204/255 → 3/255`; samples stepping ≥8/255: `1509 → 0`.

**Mutations (4/4 fire).** `feather-zero`, `raster-ignores-feather`,
`raster-blur-off`, `canvas-drops-constant`. Two of them —
`raster-ignores-feather` and `canvas-drops-constant` — **came back GREEN on the
first round**, and both were the same class: the arms were wired to the helper
(`_blob_mask`) and to the import, not to the CALL SITE. Fixed by rendering the
real ground layer twice (with and without the shipped key) and requiring the
outputs to differ, and by asserting the lookup `PAINT_FEATHER.meadow_dark`
rather than the mere presence of the identifier.

## 3. THE LIVE WORLD RENDERED THE CAMP ERA

**Measured, both causes, 2026-07-27:**

1. `/api/world/engine` 401s without the `cabinet_session` cookie
   (`route.ts:181`), `engine-client`'s `if (!r.ok) return` swallows it, and
   `resolution` stays null. **This is the one that produced the Captain's frame**
   — a logged-out browser renders a hatch. Measured: `curl` without the cookie →
   401; with it → 200 and a full eval.
2. The route reads `shared/interfaces/world-chronicle.jsonl` under
   `CABINET_ROOT` (default: the repo the server runs from). That file is a
   gitignored RUNTIME artifact, so a dev server in this worktree has no
   keyframes at all and `eval` is undefined.

With both satisfied, `/world?iso=1` renders **era hamlet @ 0.439**, four
officers, seven berths, cobbled road, three lamp posts with one lit, the
lighthouse lamp lit — the org's actual state.

**The code defect underneath.** `layoutStateFrom(null)` returns era `camp` with
no rungs, which is a perfectly valid hatch state — so an unfed renderer and a
day-zero cabinet paint the IDENTICAL island and the frame said nothing. The
baseline is right (an unmeasured metric renders its baseline); the silence was
not. `UNMEASURED_STATE_ISSUE` now goes out on the issues channel the canvas
already badges, before the scene is composed, naming both causes.
Arms in `lib/world/unmeasured-state.test.ts`, including a positive control that
pins the two states as identical — if they ever diverge, that test says so.

**Mutations (4/4 fire).** `no-announcement`, `announce-after-compose`,
`issue-drops-the-causes`, `baseline-invents-a-hamlet`.

## Open, NOT fixed here — reported with evidence

**`check_on_road` goes RED on the org's real state; both shipped fixtures are
green.** `market_goods@1390,1056` and `bush_flowering@1284,1113`. Measured: both
are ~2.5 radii clear of the reserved lane band (normalised distance² 6.46 and
6.17 against the same squashed-ellipse field the clearance rules use), so the
layout is not putting them on a road. They stand on the plaza's COBBLE, in a
lobe of the 26-blob painted union that falls outside the single fitted ellipse
`bp["plaza"] = [1233,1019,161,99]` the check exempts. The exemption is a smooth
ellipse; the painted square is lobed. That is a sensor whose shape does not
match the artifact it guards — and it lives in the MIRRORED checks
(`mirror/checks/world_checks.py`), whose authority is the private meta
workspace, so changing it is a gate change and not composition work. Identical
before and after this commit; not caused by it.

**TRAINING and SIGNALS have no ladder** (above). A district that is nothing but
its own dressing cannot be state-traceable in the sense the rest of the island
now is.

**The engine's meadow feather is verified by eye and by the offline twin, not by
a pixel gate.** There is still no headless browser in this repo, so the engine
half of the feather is evidenced by a browser capture
(`designs/defect-2-meadow-engine-before-after-2026-07-27.png`) rather than by
CI. The offline half is gated.

## Batteries run (this session, on a scratch tree at HEAD + these files only,
because another agent holds planting/scatter/ring in the same worktree)

- `tsc --noEmit` — clean.
- `vitest run` (whole dashboard) — 2569 passed, 1 skipped (a pre-existing live
  smoke needing a real store).
- `pytest cabinet/scripts/world-capture/tests/` — 13 passed.
- `sync-checks.py --check` — 4/4 mirrored files identical.
- `capture.py --state live` — 11/12; the twelfth is the `check_on_road` finding
  above, unchanged by this commit.
