# Checkpoint review — feat/iso-scale-contract cp1

Reviewed-Scope-Digest: 2f182c7e784f21eb63a72cbeac9d2d3c5a45e865411c2b9ff31c304d141e3d7d

Scope: the four staged paths (the two pack JSONs and the two world tests), based on
origin/master `761c3f8ceb3fb1b091edcf32be9d18696f98f06c`.

**Rebased, not merged.** The first cut of this change was derived against
`3126cfacb3a1c07ae1e43df573e2109fe1abdb4c`; PR #251 then re-cut the atlas ("the roof-off
floors were see-through"), moving 175 frames' atlas positions and changing 7 frames' native
size. Merging would have mixed new atlas rects with classes derived from the old ones, so
the branch was reset to origin/master and every class re-derived from the metre table
against the NEW pack. The result is identical in shape — 87 re-classed, the same
44 (/2→/3), 24 (/1→/2), 6 (/2→/1), 13 (/1→/3) split — which is itself evidence the
derivation does not depend on the atlas cut. The rendered hamlet frame is byte-identical
before and after the re-cut, so nothing outdoors moved.

## What the change is

Every frame in the isometric pack now declares its real-world size in metres, and its
integer scale class is checked against what the projection derives from that size. The
world is 2:1 iso on a 48x24 tile at 2.0 m/tile, so `dw = 12*(plan_w+plan_d)`,
`dh = 12*height + 6*(plan_w+plan_d)`, and a 1.75 m adult is 21 px of drawn height.
87 of 182 frames re-class: 57 to /3, 24 to /2, 6 promoted back to /1.

The Captain's complaint — *"characters are too small compared to tables, bench, the well,
flowers"* — was a measurement, not a preference, and it was not the characters. Before /
after, against intended:

| frame | before | after |
|---|---|---|
| chart_table | 3.33 x 3.98 | 1.11 x 1.33 |
| well | 2.33 x 2.23 | 1.17 x 1.11 |
| firepit | 1.96 x 2.58 | 0.97 x 1.29 |
| flowerbed | 1.41 x 1.67 | 0.93 x 1.11 |
| bench | 1.38 x 1.30 | 0.91 x 0.85 |
| great_house | 1.02 x 0.88 | 1.02 x 0.88 (untouched) |

## Verification, re-run in this worktree rather than inherited

| battery | result |
|---|---|
| `npm test` (vitest) | 139 files passed / 1 skipped · **2730 tests passed** / 1 skipped |
| `npx tsc --noEmit` | exit 0 |
| `capture.py --state hamlet` | **GREEN 12/12**, 1 surface unchecked |
| `capture.py --state camp` | **GREEN 12/12**, 3 surfaces unchecked |
| `pytest cabinet/scripts/tests` | 4992 passed, 34 skipped |
| `pytest cabinet/scripts/world-capture/tests` | 34 passed |
| `pytest cabinet/scripts/world-aesthetic/tests` | 87 passed, 5 skipped |

Structural, computed directly off the blobs: **atlas rects (`x`,`y`,`w`,`h`,`atlas`) changed
on 0 of 182 frames** in both files; only `scale`/`dw`/`dh` moved; `dw == w//scale` and
`dh == h//scale` hold on all 182 in both revisions; the two JSONs are byte-identical; no
top-level key changed. An independent reviewer re-derived all 182 classes from a fresh
implementation of the projection maths (not an import) and agreed on 182 of 182.

`palette_coherence` is **RED, before and after, and that is quoted rather than absorbed**:
the hamlet frame measures **85.83%** foreign-colour mass on the pre-change pack and
**86.13%** on this one, against a 5% limit. It is a pre-existing corpus-vs-art mismatch
already on the backlog, it is the only failing arm of `--mechanical`, and **no threshold
was touched.**

## What the adversarial review found, and what was done

A fresh-context reviewer returned **block** on three findings. All three were reproduced
here before acting on any of them, and all three are in the SENSOR, not in these four files
— the reviewer's own words: *"Nothing in the four staged files needs to change."*

1. **The sensor could not fail.** `scale_audit.py` ended `return 0 if not changed else 0` —
   a dead ternary. Reproduced: forcing all 182 frames to /1 printed *"110 of 182 frames
   change class"* and exited **0**. Fixed, and the fix is proven in both directions —
   fixpoint 0 · pre-change pack 1 · all-forced-to-/1 1 · negative native dims 1 · `dw`/`dh`
   divorced from `w//scale` 1 · undeclared frame 1 · empty pack 1 · missing path 2.
2. **Its documented default invocation crashed**, pointing into a checkout that runs days
   behind master and does not carry the pack. Now exits 2 with the path to pass instead.
3. **`manifest.scale_of()` is three set memberships, not a derivation**, and the first
   landing's commit message and board row both said otherwise. The wording is corrected in
   place: the sets are a cache that the sensor verifies, which is legitimate only because
   the exit code now works. That it is a manual run and not a CI gate is filed.

Non-blocking findings acted on in this diff: the `iso-scene.test.ts` comment justified
44x63 with *"a cairn is a chest-high pile of stones"*, which contradicts the metre table
this change installs (1.6 x 1.6 x 3.0 m, generated as a tapering tower) — rewritten to the
real reason, that at /1 it drew 88x126 against `camp_log_cabin` at 128x120. And
`pick.test.ts`'s sweep expectation now carries an explicit note that it encodes "these two
props are small", with the instruction to move the frame out of the expectation rather than
raise the sample count if a future class change reds it.

On the sweep split itself the reviewer's verdict was **legitimate fix, proven by mutation**:
dropping `STATIONS` from `isoWants`, deleting `chart_table` from the stations map, and
making the pick skip any sprite under 40 px each turn this test red — three independent
ways a real unreachability regression is still caught.

Filed rather than fixed (BACKLOG, cabinet-meta): no CI gate on the contract; the second
pack JSON has no tracked consumer and no drift detector; 22 frames still >1.4x at their
best class (a generation-size problem, list derived by the sensor, never hand-kept); the
largest structures run 0.62-0.70x because `no_background` dies above 200x200 and they are
already at /1, which needs a 400 px chroma-key regeneration pass; and `camp_leanto` vs
`camp_tent`, two same-size shelters now 1.65x apart through integer-ladder granularity.

**Verdict: approve.** The pack half was independently re-derived and is exact; the blocking
findings were all in the sensor and are all closed with failing-arm proofs.
