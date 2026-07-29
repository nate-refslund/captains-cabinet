# Review — iso/step13-legacy-delete-and-p0, checkpoint 1

Branch: `iso/step13-legacy-delete-and-p0` · base `a1589996` · 2026-07-29

## What this checkpoint deletes, and how completeness was PROVED

The legacy three-scene shell (`?legacy=1`) and everything only it referenced.
Completeness is not asserted — it is measured three ways:

1. **Module reachability.** A closure walk from every app route and every test
   file, before and after: 399 files / 4 orphans → 386 files / 4 orphans. The
   four orphans are the SAME four that were orphaned before this change
   (`kill-switch.tsx`, `hatch-dialog.tsx`, two `.d.ts`), so the deletion left
   nothing newly unreachable and no dangling import.
2. **`tsc --noEmit`** clean.
3. **Per-file test-count diff** against `a1589996` via the vitest JSON
   reporter: the sum of per-file deltas equals the total delta exactly (−46),
   and every file that moved is one this commit edits on purpose. Nothing
   stopped running quietly.

## Every test that no longer executes — 60 removed, 14 added, net −46

| tests | file | why it lost its subject |
|---|---|---|
| 16 | `behavior.test.ts` | the wardroom scene director's behaviour vocabulary; `director.ts` is deleted. The LIVE behaviour layer is `lib/world/life/` — 7 suites, 91 tests, untouched and still green. |
| 8 | `director.test.ts` | same subject. |
| 8 | `path.test.ts` | `path.ts`, wardroom room pathfinding — deleted; the engine has no room to path across. |
| 9 | `set-dressing.test.ts` | `set-dressing.ts`, the wardroom cozy pass — deleted. Its outdoor twin `outdoor-dressing.test.ts` is live and untouched. |
| 15 | `outdoor.test.ts` | the `street layout (Z1)` and `island layout (Z0)` describes, over the two deleted placement modules. The product LAWS they pinned keep live sensors elsewhere, each named in the file's new header: dark beacon → `growth.test.ts` + `era-engine.test.ts`; day-0 honesty → `pick.test.ts` + `unmeasured-state.test.ts`; placement determinism → the iso-layout and blueprint suites. |
| 4 | `sprites.test.ts` | three arms over `resolveWorldSprites` (the WARDROOM resolver, whose only caller was the deleted `world-canvas.tsx`) and the wardroom station-map arm. The silent-black law they guarded is enforced on the live path by `resolveOutdoorSprites` and pinned in `outdoor.test.ts` — and the dimension-invalid arm was **moved** there rather than dropped, so the sensor count over that class is unchanged. |

Added: 5 (`iso-cutaway.test.ts`), 6 (`projection.test.ts`), 3 (`ratchets.test.ts`).

## Filename-pinned ratchets — the vacuous-green trap

`ratchets.test.ts` 8/9/10 and its ratchet 6 hardcoded
`['world-canvas.tsx','outdoor-canvas.tsx','engine-canvas.tsx']` and
`['world-client.tsx','engine-client.tsx']`. Left alone they would have thrown
or passed over files that no longer exist. They are now **derived from the
tree** (a `.tsx` under `components/world/` that imports pixi is a renderer; a
`*-client.tsx` is a shell), with two floor arms asserting the derived sets are
non-empty and contain the engine — because an empty `for` loop passes every
assertion inside it. A third arm asserts the deleted files do not come back and
that `page.tsx` has no `params.legacy`.

## Art credit — resolved ADDITIVELY, never by deleting the assertion

`ui-layer.test.ts` asserted the literal `Art: LimeZu — limezu.itch.io` in BOTH
shells. One shell is gone, so the list is one row. **The assertion itself is
unchanged**: LimeZu pixels remain on /world under both projections (the
portrait rail is chrome, mounts under either kernel, and its portraits are
`LimeZu commercial — derived pixels`), so the line is still owed. Whether it
RENDERS is decided by `credit.ts` from the manifest's own `license` column over
what each mounted surface binds, and that decision has its own behavioural
suite.

## Two P0 defects closed first (previous commit, `ace121c3`)

The iso roof cutaway drew no room at all (PixiJS 8.19 labels every `Sprite`
"Sprite", so the pooled floor was swept invisible), and `?iso=0` survived
exactly one page view once the default flips. Both carry arms watched failing
against the code they replace.

## What this checkpoint deliberately does NOT do

`DEFAULT_PROJECTION` is **still `'topdown'`**. The bake-off found capability
losses under iso that this run cannot close — the whole product-lane surface
and the whole LIFE draw layer have no iso representation. Flipping over them
would ship a default view that stops showing which products exist and what work
is visibly happening. Recorded in the handback rather than flipped past.
