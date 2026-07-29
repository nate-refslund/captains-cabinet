# Checkpoint review — fix/veil-luminance-law-2026-07-29 (cp1)

Two fresh-context reviewers, own clones off the branch, no session priors, both
Opus 5. Neither saw the other's output. Both returned **approve-with-fixes** on
the fix and **no blocking finding on the renderer change**; both found real
defects in the SENSORS, which is where a review of this change was always going
to earn its keep, since the sensors are the deliverable.

## Reviewer A — adversarial, sensors only

Ran the suites itself (vitest 2849 pass, tsc clean, world-capture 43 pass at the
time), then ran 19 source mutations with caches purged. Findings, all fixed in
this branch:

| severity | finding | fix |
|---|---|---|
| P1 | `live-frame-probe.py` selected the window with the MOST sea. Unlawful pixels are by definition not sea, so the rule preferred the window with the LEAST defect — a frame with the veil over half its ocean returned OK | reports the WORST window; arm `test_red_when_only_PART_of_the_ocean_is_defective` |
| P1 | a frame of one flat colour returned OK | `MIN_TONES`; arm `test_a_flat_frame_is_unjudged_not_ok` |
| P1 | a green could not distinguish "veil lawful" from "no veil / wrong clock captured" | the probe now NAMES the veil it judged (`veil=dusk`); arm `test_a_green_says_when_there_was_no_veil_to_judge` |
| P1 | the wiring arm was a name grep with 5 bypasses: `const VEIL_TABLE` (no `\b` before `_`), `const veilTable` (case), a ternary at the draw call declaring no table at all, a COMMENT satisfying the must-call half, and a `'/*'` string literal defeating the comment stripper | the arm is STRUCTURAL: exactly one `veilTexture(` call site, its arguments literally `veil.colors, veil.coverage`, exactly one `const veil =` bound to `ambientVeil(bucket)`, the import pinned, and no `colors: [` literal anywhere in the canvas |
| P2 | `NON_SEA_TONES <= 8` let a cobbled quay judge as water — sharpened by the fix itself, since the dusk hues were cobble tones | replaced by two shape questions: per-tone scatter, and quadrant uniformity |
| P2 | the same qualifier false-RED'd a sand beach | same fix; arm `test_a_sand_beach_is_not_a_violation` |
| P2 | the chroma arm had no `colors.length > 0` guard, so an empty table passed it | guard added |
| P2 | coverage was unbounded — `dusk 0.95` kept 13/13 green | bounded `< 0.5` with its reason |
| P2 | the "composing the veil" arm composed nothing: `dots` was consumed for `.length` only | it now resolves every hue index and asserts the rotation does not collapse |
| P2 | `_VEILS` in `world-growth-backtest.py` was a prose "change one, change both" contract in the very commit proving prose contracts drift | `test_veil_table_mirror.py` parses the TypeScript and pins hues AND coverage |
| P3 | `getcolors(maxcolors=1<<24)` returns None above 4096px windows | guarded |
| P3 | `ambientTint` still returned the banned apricot with a green test asserting it | deleted (below) |

Reviewer A also noted `veilDots`' hue rotation had no arm anywhere: setting
`hue: 0` kept the whole 2849-test suite green. Now covered by the rotation
assertion in the composition arm.

## Reviewer B — correctness and doctrine

Independently recomputed every number in the law doc block; all matched.
Confirmed: no import cycle (`lighting → terrain-pattern → hash`, a DAG),
`ambientVeil` total over `DayBucket`, the `NIGHT_VEIL_HUES` import removal broke
nothing, `check-layer-separation.sh` new=0, docs sweep 0 findings, no guarded
token in any changed file, no test writing a live safety switch, and that
`docs/plans/world-direction-surface-2026-07-17.md:88` already reserved 0xffc890
for `adrift` only — so this change brings code into line with an existing
direction rather than inventing one.

Blocking: none. Fixed from its list:

- **`ambientTint` was a live-looking trap.** Dead (on the ratchet baseline), yet
  it returned `0xffc890` for dusk and `lighting.test.ts:102` green-asserted that
  value, while the new `veil.test.ts` bans the same hue — two green tests in one
  directory disagreeing about whether a colour is reserved. Deleted with its
  interface, its assertion and its baseline row; the reserved-salience arm now
  reads the veil's own hues.
- **The doc named two dead functions** (`lampGlow`, `WINDOW_SKY`) as what carries
  dusk. Rewritten to name the live path: the lamps and lit windows drawn on
  `fxG`, which sits above the veil.
- **The aesthetic finding, and it changed the shipped hues.** Reviewer B measured
  the first fix's cobble greys as moving mean water luminance **+2.9** — dusk very
  slightly *brightened* the ocean, against night's −33.0 and the defect's +12.3.
  Re-derived from the fitted palette's own bins rather than the terrain ramps
  (the ramps have no dark low-chroma grey) and shipped
  `[0x7c7c84, 0x6c6c74, 0x4c7c6c]`, which measures **−2.5**. Confirmed by eye at
  1:1 against day and night.
- Named, not fixed: law 2 would reject a genuinely moon-tinted night. Recorded in
  the law's own doc block as the known edge to argue with deliberately.

## Residual, filed not fixed

`BACKLOG.md` 2026-07-29 carries both: the twelve invariants cannot see the
composited frame at all (the probe covers open water only — land, sprites,
weather and the killswitch wash remain unsensed), and `PALETTE_FOREIGN_MASS`
asks a per-pixel question where the defect was a neighbour-plausibility one.

## Verification after every fix above

`npx tsc --noEmit` clean · vitest 140 files / 2848 pass, 1 pre-existing skip ·
`pytest cabinet/scripts/world-capture/tests -q` 61 pass · every new arm proven
red under mutation with caches purged (6 probe/twin mutations, 2 hue mutations) ·
the probe red on the shipped frames at zoom 0.35/0.50/0.60/1.00 and green on the
re-captured frames in all four day buckets at the same zooms.
