# flip/world-owned-cast — cp1 review (2026-07-28)

Reviewed-Scope-Digest: c3936ac2b09a2d73a3239acd17cafb3bdbb5978a653c1de0b685b7cc1a7ad277

Captain ruling 2026-07-28: shown the island owned-vs-licensed comparison at true
zoom plus the full 20-person cast, "flip now". Accepted soft spot: the walk reads
as a sway rather than a stride, improvable in place.

## What changed

1. `sprites.ts` — `CHARACTER_DIR` `'characters'` → `'originals/characters'`. It is
   the only reader: `characterSheetFor`, `requiredSheets`, the resolver's
   dimension arm, and `sprites-outdoor`'s `ENGINE_CHARACTER_SHEETS` and its own
   dimension arm all derive from it. `git grep -n "characters/"` finds no other
   constructed path — only manifest rows (both sets stay listed) and the
   `--committed-only` asset-gate test's own fixture copy.
2. `lib/world/credit.ts` (new) + `credit.test.ts` — the art credit is now derived
   from the manifest's `license` column over what each mounted surface binds.
3. Both world shells render the credit inside `{creditSurfaces.length > 0 && …}`
   and carry `data-credit-surfaces` so a live page can be asked why the line is
   there. `portrait-rail` counts its own LimeZu portraits and reports them up.
4. Three stale comments that called the cast "LimeZu" now say what is true.

## The finding that changed the design

The dispatch's premise — "with owned characters drawn under iso, iso draws ZERO
LimeZu" — is **incomplete**, and implementing it as written would have been false
attribution in the opposite direction. The portrait rail is chrome, not world: it
mounts under BOTH projections, and its portraits are manifest rows licensed
`LimeZu commercial — derived pixels, do not redistribute`
(`world-compose-portraits.py` compositions of the Portrait Generator pieces). A
credit rule keyed on projection alone would have gone dark over a screen full of
LimeZu-derived faces.

So the canvas arm is derived too, not hardcoded: under iso the kernel binds only
`originals/iso/atlas-0` (owned) plus the cast, so the canvas owes credit under iso
iff the cast's rows are LimeZu-licensed. Reverting `CHARACTER_DIR` therefore
restores the iso credit by itself — the revert stays one line.

Verified live (production build, real page):

| projection | rail | `data-credit-surfaces` |
|---|---|---|
| top-down | open | `world canvas,portrait rail` |
| iso | open | `portrait rail` |
| iso | hidden (P) | element **absent** |
| iso | re-opened | `portrait rail` |

The iso/rail-open row is itself the proof that the world canvas draws zero LimeZu
under iso after the flip: the canvas contributes nothing to that list.

## Known and deliberate imprecision

The predicate measures BINDING, not photons. A manifest row whose PNG is absent
(a hatched cabinet ships the whole manifest but only the owned binaries) counts as
bound, and the surface draws a loud placeholder. The credit is therefore
conservative — shown where nothing LimeZu actually loaded, never hidden where
something did. Gating a licence notice on image load would let a slow network or a
404 suppress a credit that IS owed, which is the failure that costs something.
This is stated in the module docstring, not just here.

## Evidence

- Live page, production build, real Redis-backed officers, LimeZu packs installed:
  20 character-sheet requests, **all** `/world-assets/originals/characters/`,
  **zero** `/world-assets/characters/`, in both projections. The licensed paths
  return 200 on the same server, so the zero is a real negative, not a missing
  file.
- `cos → Premade_Character_05` (rust red), `comms-officer → 06` (teal),
  `newsletter-ceo → 03` (forest green), `bakery-ceo → 18` (coral) — the drawn
  figures match the owned fleet sheet, in an iso roof-off cutaway and in the
  top-down great-house yard.
- `npm test` 2751 passed / 1 skipped (140 files); `tsc --noEmit` clean.
- Six mutants, each caught: revert the flip · credit ignores projection · credit
  ignores the rail · credit keys on projection alone · engine-client renders the
  credit unconditionally · world-client stops asking the predicate.
- `sprites.test.ts:87` interpolates `CHARACTER_DIR` into its own regex, so it
  follows the constant and is not evidence the flip took effect. `credit.test.ts`
  adds the arm that reads the LICENCE of the row the world actually binds, which
  goes red on a revert.
- world captures GREEN 12/12 at camp and hamlet; mechanical aesthetic gate ok,
  `palette_coherence` foreign-colour share 0.10% (camp) / 0.30% (hamlet).
- `world-asset-gate.py --committed-only` GREEN (21 of 2428 rows tracked, floor 20);
  layer separation OK, new=0; docs-track-code GREEN.
