# Review — iso-port step 1: `projection.ts` + `projection.test.ts`

**Branch:** `iso-port-projection` · **Worktree:** `/Users/nate/cabinet-worktrees/iso-port-projection`
**Base:** `f07787faa861f429626a75bfa0c04ff690d6f2f9` · **Staged:** 2 new files, 586 added lines
(`cabinet/dashboard/src/lib/world/projection.ts` 317, `…/projection.test.ts` 269)
**Reviewer:** fresh-context subagent, Opus 5 (1M), 2026-07-27
**Review of:** `git diff --cached` only. Nothing committed, nothing pushed by this review.

## Verdict: **APPROVE_WITH_FIXES**

The load-bearing claim of this commit is true and I verified it independently, bitwise, at
every one of the five legacy sites: **the top-down kernel reproduces the existing inline
arithmetic bit for bit**, including fractional and negative tiles, across 7 zoom levels and
several viewports. The inverse is a true inverse in **both** kernels (worst error 1.1e-13
tiles over the real world extent). The ground diamond is **bit-identical to
`checks/world_checks.py`** across every case I could construct, including the 6px depth
floor and the degenerate zero-size sprite — so this is not a fourth definition of where a
sprite stands, it is the same one. The camera stays a pure scale+translate, and I proved
the property that makes that safe (both kernels are linear, so container-transform and
per-point projection agree to 7.3e-12 px).

What is wrong is the **claim surface**, and it is wrong in the exact shape this program
keeps paying for. Three docstrings assert that controls guard this code. Two of those
controls do not exist. The one that matters: **`ISO_TILE` — the single calibrated constant
the whole port rests on — is pinned by nothing.** I set it to `16×8`, the value the
calibration *rejected* (15–18 stacked structure pairs per the plan), and all 23 tests
stayed green.

Nothing here blocks landing the code as-is (the module is unwired, `DEFAULT_PROJECTION` is
`'topdown'`, full suite and typecheck are green). The fixes are to the words, plus two
assertions, plus one API gap that will otherwise be filled by a hand-rolled sixth copy at
step 5.

---

## Findings

Severity: **HIGH** = fix before this lands · **MEDIUM** = fix before the step that depends
on it · **LOW** = nit / follow-up.

### H1 — `ISO_TILE` is unpinned, and its docstring cites a test that does not exist
`cabinet/dashboard/src/lib/world/projection.ts:61-67`

> "The isometric grid. 48×24 is MEASURED, not chosen: iso-layout.test.ts projects every
> authored anchor × every era × every rung through world-pack.json and reports the smallest
> tile size at which no two ground diamonds overlap. See that test for the table this
> number comes from."

There is no `iso-layout.test.ts` in `src/lib/world/` (it is step 2 of the plan). The only
in-repo constraints on `ISO_TILE` are `w % 2 === 0`, `h % 2 === 0`
(`projection.test.ts:54-58`) and `w === 2*h` (`projection.test.ts:60-62`).

Measured — mutation sweep, cache purged, suite re-run each time:

| `ISO_TILE` | suite result |
|---|---|
| `{w:48,h:24}` (as staged) | 23 passed |
| `{w:64,h:32}` | **23 passed** |
| `{w:16,h:8}` — the value the calibration REJECTED | **23 passed** |
| `{w:50,h:24}` | 1 failed (the 2:1 arm) |

A docstring that names a sensor which is not wired is the defect class this program has
found ten ways in two days. Worse than an unpinned constant is an unpinned constant
*labelled* "MEASURED".

**Fix (either):** (a) land the calibration test in this commit — which is what the plan's
own step 1/2 wording demands ("This calibration must be a TEST that runs before any pixels,
not a number someone picks"); or (b) minimum honest fix: change the docstring to say the
number is PROVISIONAL pending `iso-layout.test.ts`, and add a `TODO` that step 2 replaces
it. Do not leave the present-tense sentence.

Related, and why this matters more than it looks: `world_checks.py:127-157` shows the
`STRUCTURES` list was corrected *after* the original 48×24 sweep was run (the comment
credits an adversarial review of this very plan). The premise-check
(`iso-engine-port-premise-check-2026-07-27.md` D3) says the plan's quoted stacking numbers
reproduce as neither the filtered nor the unfiltered figures. So 48×24 currently rests on a
re-run that no artifact in this repo demonstrates.

### H2 — `groundDiamond`'s docstring claims a cross-artifact pin that does not exist
`cabinet/dashboard/src/lib/world/projection.ts:197-200`

> "iso-pack.test.ts pins this function against the note string parsed out of the SHIPPED
> pack, so the engine and the offline checks can never drift apart silently."

There is no `iso-pack.test.ts` (step 3), and `world-pack.json` is not in the dashboard tree
yet, so no in-repo test *can* parse that note today. What actually pins the formula is the
hardcoded `0.42` at `projection.test.ts:209` — real (mutation-confirmed: `0.42 → 0.45`
fails 1 test), but it pins the **constant**, not **parity** with the Python or the pack.

The code itself is correct — I verified parity cross-language myself (see Evidence). The
sentence is the defect. **Fix:** state what guards it today (the pinned constant + the
verbatim note quote at `:191-195`, which I confirmed is byte-verbatim against the shipped
`world-pack.json`), and mark the pack-parity test as step 3 work.

### M1 — "both tile sizes are powers of two" is false
`cabinet/dashboard/src/lib/world/projection.ts:29-34`

48 and 24 are not powers of two. This is the same shape as the powers-of-two assertion
already caught and removed from the test file (`projection.test.ts:49-53`) — it survived in
the module header.

The argument it supports is *correct and load-bearing for the top-down kernel*, which is
what the paragraph is justifying, and I measured that it does **not** carry to iso:

```
distributive (a+b)*T == a*T + b*T, 100 fractional pairs:  T=16 → 0 mismatches
                                                          T=48 → 36 mismatches
                                                          T=24 → 36 mismatches
associative   (a*T)*z == a*(T*z), 70 pairs:               T=16 → 0
                                                          T=48 → 8
```

**Fix:** "the top-down tile is a power of two…", and add the corollary that matters
downstream: **iso arithmetic is not bit-exact, so no iso rewire may ever claim
byte-identical output.** That sentence is worth more than the one it replaces.

### M2 — nothing tests the property that makes the camera safe
`projection.ts:270-292` (`cameraTranslation`, `worldToScreen`); no covering test.

The header's central architectural claim — "THE CAMERA STAYS A PURE SCALE+TRANSLATE… iso is
applied PER-OBJECT at placement" (`projection.ts:23-27`) — is only sound because both
kernels are **linear** (no offset term). That is what makes
`container.position + project(p)*z` equal `worldToScreen(p)`, i.e. what keeps the DOM label
path (`engine-client.tsx:688-694`, which will call `worldToScreen`) glued to the sprite path
(the container transform, which will call `cameraTranslation` + `project`). If a future
kernel ever gains an offset, labels silently slide off every sprite and all 23 tests stay
green.

I measured it (max disagreement 7.3e-12 px, both kernels, 7 zooms, 169 points) — the
property holds. It just isn't asserted anywhere.

**Fix:** two assertions, both cheap:
`project(a+b) == project(a) + project(b)` for both kernels, and
`|cameraTranslation(cam).x + project(p).x*z − worldToScreen(p).x| < 1e-6`.

### M3 — `lod.ts`'s `screenRect` has no single replacement, and the obvious port is wrong under iso
`cabinet/dashboard/src/lib/world/lod.ts:132-147` (consumer: `lod.ts:169`, `cutawayCandidate`)

`screenRect` needs the **screen-px AABB of a tile box under a camera**. The module offers
`screenAABB(box)` (world px, no camera) and `worldToScreen(point)` (camera, but a point).
The correct port is a composition the module never states —
`cameraTranslation(...)` plus `screenAABB(box)` scaled by `z`. The port that looks natural,
`worldToScreen(x0,y0)` + `worldToScreen(x1+w, y1+h)`, is **correct under top-down and
silently wrong under iso**: it returns two of the four diamond corners, which is precisely
the bug the iso branch of `screenAABB` (`projection.ts:161-176`) exists to prevent — and
every `lod.test.ts` fixture would stay green, because `DEFAULT_PROJECTION` is `'topdown'`.

**Fix:** export one obvious call, e.g.
`screenAABBUnderCamera(proj, box, cam, vp): PxBox`, or give `screenAABB` an optional camera.
This is the "sixth copy" the module exists to prevent, and it is one function away.

### M4 — the canvas hit-test cannot be fully expressed: no drawn-sprite rect
`cabinet/dashboard/src/components/world/engine-canvas.tsx:1553`

```ts
if (wx >= b.x - 0.3 && wx <= b.x + b.w + 0.3 && wy >= b.y - 1 && wy <= b.y + b.h + 0.3)
```

That padding is **asymmetric** (`b.y - 1`): today you can click a building's drawn BODY, not
just its footprint. The module exports only `pointInGround` (the foot diamond). Under iso a
`great_house` is `dw=196 dh=174` — a click anywhere on the tower would miss the ground
diamond, fall through the priority chain, and return `{kind:'ground'}`: a silent dead click,
which is the named top risk of this port ("THE HIT TEST IS THE SILENT FAILURE").

`checks/world_checks.py:314-318 _drawn_rect` already defines the drawn rect
(`x−w/2, y−h, x+w/2, y`). **Fix:** export the TS twin here, so step 5 picks bodies with the
existing definition instead of hand-rolling a fifth footprint. (MEDIUM, not HIGH: step 5
owns the hit test — the point is it should not have to invent this.)

### M5 — the "no sub-pixel placement" test records a false reason
`cabinet/dashboard/src/lib/world/projection.test.ts:49-58`

> "an iso projection adds tile/2 terms, and a fractional half-tile would put sprites on
> sub-pixel positions and destroy the very pixel grid the integer display scale exists to
> protect."

Sub-pixel positions come from **fractional tile coordinates**, not from an odd tile size —
the file's own fixture grid uses `3.1, 16.5, 120.75, 150.25`, LIFE emits floats, and
`project(3.1, …).x = 49.6` under the top-down kernel *today*, with `TILE=16`. The actual
pixel-grid protection is `roundPixels: true` (`engine-canvas.tsx:216`).

The assertion is harmless and does pin the constants; the **reason recorded in the test body
is wrong**, and the reason is what the next person acts on. Same shape as the powers-of-two
assertion this very test block was written to replace.

**Fix:** rename to what it actually pins ("both grids have an integer half-tile, so the iso
±W/2 terms land on whole pixels") and drop the sub-pixel claim, or cite `roundPixels`.

### L1 — `DEFAULT_PROJECTION`'s docstring describes a flag that does not exist
`projection.ts:44-50`: "?iso=1 / ?iso=0 select explicitly in both directions from day one".
`src/app/(authenticated)/world/page.tsx` reads `searchParams` (`:31-37`) but has zero `iso`
references, as does `engine-client.tsx`. Step-4 machinery in the present tense. Mark planned.

### L2 — "frozen singletons" is not true, and `TileSize` is mutable
`projection.ts:180` says "frozen singletons — no per-call alloc". They are module-level
singletons but nothing is `Object.freeze`d, and `TileSize.w/h` (`projection.ts:53-56`) are
not `readonly` — `readonly tile: TileSize` (`:104`) freezes the reference, not the fields, so
any consumer can write `proj.tile.w = 32` and re-scale the world at runtime. Given the
determinism ratchets, make the fields `readonly` and/or freeze the two constants.

### L3 — return-shape inconsistency for the same space
`unproject → {tx,ty}` (`:110`), `screenToWorld → {x,y}` (`:294`),
`screenDeltaToTiles → TilePoint` (`:310`). All three are world-TILE values. TS catches a
mix-up, but across ~105 call sites it is an avoidable papercut. (`screenToWorld`'s `{x,y}` is
defensible — it matches `CameraLike`.)

### L4 — round-trip coverage is a single camera
`projection.test.ts:165-176` tests `screenToWorld(worldToScreen(p))` at exactly one camera,
`{z:1.75, x:120, y:96}`. I widened it to 7 zooms × 12 camera centres × 169 points in both
kernels: worst absolute error 5.7e-14 tiles (top-down), 1.1e-13 (iso). The property holds far
beyond what the test proves; widening is 3 lines.

### L5 — one cited line range is loose; all others verified exact
`projection.test.ts:112` cites `engine-client.tsx:689-693` for `project()`; the arithmetic is
at `:690-691` (the `useCallback` spans `:688-694`). Verified **exact**: `engine-canvas.tsx:987`
(footprint rect), `:1482-1485` (camera), `:1509-1510` (hit-test inverse),
`engine-client.tsx:605-606` (pan), `lod.ts:140-146` (`screenRect`). The header's "the
transform existed FIVE times" is accurate — I found those five and no sixth in the two
components + `lod.ts`. (`terrain-pattern.ts:29` carries its own `TILE_PX` with four per-tile
emitters — the plan's "hidden sixth site", correctly out of scope for this diff.)

### L6 — degenerate ends untested
`pointInGround` (`:237-252`) divides by `g.hw` and `g.depth/2`; at `dw=0` that is a division
by zero → `dx = Infinity` → returns `false` (fails closed, which is right, but nothing
asserts it). `screenToWorld`/`screenDeltaToTiles` divide by `cam.z` with no guard.
`groundDiamond(0,0) = {hw:0, depth:6}` and matches the Python exactly (verified). One
degenerate-end test would cover all three.

---

## What I actually ran

All commands from `/Users/nate/cabinet-worktrees/iso-port-projection/cabinet/dashboard`
unless noted. `node_modules` present; vitest 4.1.5.

**1. The staged suite.**
```
npx vitest run src/lib/world/projection.test.ts
→ Test Files 1 passed (1) · Tests 23 passed (23) · 216ms
```

**2. Full suite (the gate's battery, not a hand-picked subset).**
```
npx vitest run
→ Test Files 121 passed | 1 skipped (122) · Tests 2227 passed | 1 skipped (2228) · 2.32s
npx tsc --noEmit   → exit 0, no output
```
The 1 skip is pre-existing; this diff adds none. `ratchets.test.ts:36-55` scans
`src/lib/world` recursively, so `projection.ts` is inside ratchets 1/3/4 (no `use server`, no
`innerHTML`, no `Math.random`/`Date.now`) and passes.

**3. Independent bit-exactness harness** (my own transcription of the legacy expressions,
read from the source files — *not* copied from `projection.test.ts`), comparing IEEE-754 bit
patterns via `BigUint64Array(new Float64Array([n]).buffer)`, over 15 values including
negatives, fractions, `1e-9`, `1e7`, `0.30000000000000004`, and 8 zoom levels:

| legacy site | transcribed expression | result |
|---|---|---|
| the 91 inline `* TILE` sites | `tx*TILE`, `ty*TILE` | **bit-identical** (225 pairs) |
| `engine-canvas.tsx:1482-1485` | `vw/2 - cam.x*TILE*z` | **bit-identical** (3 viewports × 8 z × 225) |
| `engine-client.tsx:690-691` | `w/2 + (wx-cam.x)*TILE*z` | **bit-identical** |
| `lod.ts:140-146` | `s = TILE_PX*z; w/2 + (b.x-cam.x)*s` | **bit-identical** |
| `engine-canvas.tsx:1509-1510` | `(sx - w/2)/(TILE*z) + cam.x` | **bit-identical** |
| `engine-client.tsx:605-606` | `dx/(TILE*z)` | **bit-identical** |
| `engine-canvas.tsx:987` `g.rect(x*T,y*T,w*T,h*T)` | `x1 == x*T + w*T` for **fractional** boxes | **bit-identical** (0 drift) |

The last row is worth naming: `screenAABB` computes `(box.x + box.w) * tile.w` while the
legacy computes `x*T + w*T`. Those are equal bit-for-bit *only because 16 is a power of two*
— I measured that the same identity fails 36/100 times at 48 and at 24. The exactness
argument is real and it is exactly as narrow as M1 says.

**4. Inverse, both kernels, over the REAL world extent** (canvas 240×192 + the ±24 clamp
margin), 7 zooms × 12 camera centres × 169 points:
```
ABS round-trip error — topdown: 5.68e-14 tiles   iso: 1.14e-13 tiles
```
(At an absurd `1e7`-tile coordinate the relative error reaches 2.7e-9 — catastrophic
cancellation, ~0.027 tiles absolute, and unreachable in a 240×192 world. Recorded so nobody
re-discovers it as a bug.)

**5. Camera purity.**
```
max |cameraTranslation + project*z − worldToScreen| = 7.28e-12 px   (both kernels, 7 zooms)
project(a+b) == project(a)+project(b)                                (both kernels)
```

**6. Ground geometry, cross-language against the actual Python** (imported
`/Users/nate/cabinet-meta/checks/world_checks.py`, PIL present, ran its real `ground_box` /
`overlap_frac` — not a re-transcription):
```
ground_box   : NONE — all 8 cases bit-identical  (incl. the 6px floor, w=0/h=0, 1×200 sliver)
overlap_frac : NONE — all 6 cases bit-identical  (incl. edge-touching → 0, and the max(1,area) clamp)
```
And the pack note quoted at `projection.ts:191-195` is **byte-verbatim** against
`designs/world-pack/world-pack.json`'s `note` (checked programmatically, whitespace-normalised
for the comment wrap).

**7. Mutation sweep** — does the suite FAIL against broken code? 12 mutations, each applied to
a copy, suite re-run, file restored and SHA-256 verified identical afterwards:

| mutation | caught |
|---|---|
| `TOPDOWN_TILE.h 16→15` | 9 tests failed |
| `groundDiamond hw 0.42→0.45` | 1 failed |
| drop the `max(6, …)` depth floor | 1 failed |
| iso `unproject` swap `tx`/`ty` | 2 failed |
| iso `depthOf` drops the `tx` term | 2 failed |
| `DEFAULT_PROJECTION → 'iso'` | 1 failed |
| iso `screenAABB` uses 2 corners not 4 | 1 failed |
| top-down `screenAABB` x1 off by one tile | 1 failed |
| `pointInGround` becomes a RECT | 1 failed |
| `cameraTranslation` sign flip | 1 failed |
| `ISO_TILE → {50,24}` | 1 failed |
| **`ISO_TILE → {64,32}`** | **NOT caught — 23 passed** |
| **`ISO_TILE → {16,8}` (the rejected value)** | **NOT caught — 23 passed** |

11 of 12 shapes caught. The one hole is H1.

**8. Wiring / scope.**
```
grep -rn "world/projection|from './projection'" src   → only projection.test.ts
```
Confirmed unwired: `DEFAULT_PROJECTION = 'topdown'`, zero importers, so "nothing visible
changed" is true **by construction** at this commit. `grep -c '\* TILE\b' engine-canvas.tsx
→ 91` inline sites still to rewire.

---

## What I could NOT verify

- **That 48×24 is the right calibration.** I did not re-run the anchor × era × rung overlap
  sweep. The plan and the premise-check both claim it, and the premise-check says it
  replicated independently — but nothing in this diff or this repo demonstrates it, and
  `world_checks.py`'s `STRUCTURES` list was corrected *after* the original sweep. See H1.
- **Anything visual.** No render, no screenshot, no pixel diff. Not possible from this diff
  (unwired module), and not claimed by it. The plan's step-1 "screenshot /world before and
  after at z=0.5/1/3 and diff — must be pixel-identical" is still owed by the rewire commit.
- **The rest of plan step 1**, deliberately not in this diff and therefore not reviewed: the
  ~105 call-site rewire (91 bare `* TILE` in `engine-canvas.tsx` alone), deleting three of the
  building's four footprints, `terrain-pattern.ts`'s four `TILE_PX` emitters, the
  one-viewport-source-of-truth decision (`hitTarget` still mixes
  `getBoundingClientRect()` with `app.renderer.width` at `engine-canvas.tsx:1506-1510`), and
  **ratchet #10** (no bare `* TILE` outside `projection.ts`). Without ratchet #10 a sixth copy
  can still be born while the port is being written — the plan says so itself.
- **Cross-repo pack parity in CI.** `world-pack.json` is not in the dashboard tree (step 3), so
  no in-repo test can parse its note today. My parity check (item 6) is a reviewer measurement,
  not a standing control.
- **Commit-time gates.** I did not commit or push. Not run: FW-019, FW-025/025b golden evals,
  the layer-separation gate, CI per-job.

---

## Landing notes

- The diff is **586 added lines**, over FW-019's 300-line commit-time threshold, so this
  artifact is required and its filename must contain the branch name — it does
  (`iso-port-projection-cp1.md`, branch `iso-port-projection`).
- **`shared/interfaces/**/*.md` is gitignored** (`.gitignore:179`, confirmed with
  `git check-ignore -v`). This file must be staged with **`git add -f`**:
  ```
  git add -f shared/interfaces/reviews/iso-port-projection-cp1.md
  ```
- Stage exact paths only; the worktree is otherwise clean (verified: the two staged files and
  nothing else, after my scratch tests were removed and `projection.ts` restored — SHA-256
  matched the pre-mutation copy).

---

## cp1 findings — disposition (orchestrator, 2026-07-27)

**H1 — ISO_TILE pinned by nothing. FIXED.** The docstring cited `iso-layout.test.ts`,
which does not exist; the constant could be set to the value the calibration had
REJECTED with the suite still green. A calibration block now reads the SHIPPED
`world-pack.json`, measures the widest frame's ground diamond against the tile step, and
asserts 48×24 fits while 16×8 does not. **Verified by mutation**: setting `ISO_TILE` to
`{16,8}` now fails `48x24 fits the structures; the rejected 16x8 does not`, and the file
was restored afterwards. A guard that cannot fail is not a guard.

**H2 — groundDiamond's claimed pack guard did not exist. FIXED.** Three assertions now
read the pack itself: the note still states the formula (so a wording or number change
in the contract forces a reconciliation), every one of the 163 frames anchors at its base
centre, and the implementation reproduces the note for real frames. Critically these read
the pack rather than restating the code — a check that agrees with the thing it checks
guards nothing, which is the rule this whole harness exists to enforce.

**M1 — the exactness reasoning was false. FIXED.** "Both tile sizes are powers of two"
is untrue of 48×24, and the reviewer measured the distributive identity failing on ~36%
of inputs at those sizes. The docstring now says what is actually true: the TOP-DOWN
tile is a power of two, which is what makes the rewire bit-for-bit and the existing suite
a valid proof of "nothing changed"; the iso tile is not, which is harmless because the
iso path has no legacy arithmetic to reproduce, and what it does need — half a tile being
a whole pixel — is stated and pinned.

**M2 — camera linearity asserted in prose only. FIXED.** A test now proves
`worldToScreen == cameraTranslation + project·z` in both kernels across several cameras
and tile points. This is the property that makes "iso is applied per object, never to the
container" safe.

**M5 — the test's stated reason was wrong. FIXED** as part of M1.

**M3 (lod.ts has no single replacement) and M4 (the hit-test picks the drawn body, not
the foot diamond) are ACCEPTED AS OPEN** and belong to the steps that own those files.
M4 is the more dangerous: under iso a click on a tall building would silently return
ground, and every lod and interaction test would stay green. It is recorded on the port
plan as the reason the hit-test step must not be deferred past first pixels.

32 tests pass. The module remains unwired, which is the point: the rewire of ~105 call
sites is a separate commit whose proof is that nothing changes.
