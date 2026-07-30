# Checkpoint review — feat/companion-desk-pet (cp1)

Reviewed-Scope-Digest: 2b504497841ef018c9ce0fd98edad117d9682c90d6a24fe380aba4d144a9b51b

**Reviewer:** fresh-context adversarial subagent, Opus 5, its own clone of
origin/master `363c9fa2abab9a95705536e320070b8a01b712e9` with this change
staged. It built the bundle itself, ran the suite itself with the bytecode
cache purged, exercised the binary directly, and mutation-tested every new
arm. Its verdict on the first pass was **changes-requested** with two blockers,
both reproduced from a running binary, not from reading.

**Author:** builder session, Opus 5.

## What the change is

`cabinet/companion/pet.swift` — a floating always-on-top window holding one
officer's 16x32 sprite, standing on the Dock's top edge, rendering the
five-state ladder that `CompanionCore.poll()` already computes. A body for an
existing brain: no new Redis read, no new data source, no new daemon, no new
dependency and (measured) no new permission.

## Blockers found, and what was done

**B1 — a sheet that DECODES but is degenerate rendered an EMPTY pet.**
`PetPixels.load` never compared the decoded image's pixel size to the requested
384x96; it drew whatever it got into that rect, and `bodyPixels` treated
`sheet != nil` as "the art is good". Proven by halving the bytes of a shipped
PNG — the most ordinary corruption there is: `--pet-render GREEN` exited 0,
logged nothing, and produced a canvas with **ten visible pixels** (the contact
shadow, nothing else). On the live path that is an empty floating window, which
is precisely what this file's own header forbids and what the README asserted
as fact.

Fixed two ways, because the input class has two shapes: `load` now refuses any
sheet whose decoded pixel size is not the expected one (a broken sheet is not a
small one), and `bodyPixels` falls back to the loud MISSING box when the cell
it cut carries no ink. Both paths log. Two new arms supply the inputs —
synthetic sheets written by a stdlib PNG writer in the test file, because no
arm in the suite had ever fed this class and that is exactly why it was green.

**B2 — `UInt8` overflow trap killed the whole app in AMBER and RED.**
The desaturation's cosmetic gamma lift can raise a premultiplied channel above
its own alpha for a light low-alpha pixel; compositing that over the keyline
underneath overflowed an unchecked `UInt8(...)` and Swift trapped. Reviewer
measured `--pet-render AMBER` exiting **133 (SIGTRAP)** with the crash frames.
Latent, not live: 13 of the 20 owned sheets already carry semi-transparent
pixels, but every one is a dark outline whose luminance is ~0. One art
re-export with a highlight and the menu-bar app dies in the two states that
mean "I do not know" and "it is bad".

Fixed at both ends — the desaturation caps at the pixel's own alpha, and the
compositor clamps. **Either alone is sufficient**, so the new arm goes red only
when both are removed (which is the pre-change code, and is the mutation that
matters). Neither guard has an independent sensor and the test says so in
plain words rather than implying coverage it does not have.

*A note on how the B2 arm was reached, because it is the more useful finding:*
the first version of that fixture — a uniformly translucent sheet — **passed
against the original unfixed code**. The overflow needs a light low-alpha pixel
drawn over an ALREADY-PAINTED destination, and the only thing painted
underneath is the keyline, which exists only where a low-alpha pixel sits next
to an opaque one. A uniformly translucent sheet produces no keyline at all and
never reaches the defect. The fixture is now an opaque core with an
anti-aliased fringe — ordinary art — and it goes red against the original.
A companion arm asserting the premultiplied invariant on the rendered PNG was
written, measured, and **deleted**: PNG stores STRAIGHT alpha, so the property
cannot survive the encode and the arm passed for the wrong reason.

## Should-fix, all taken

- The `--pet-demo` marker lived only inside the open menu, while the tray icon
  and tooltip carried the synthetic state unmarked — and the menu bar is in
  every screenshot that flag exists to produce. The tooltip now leads with
  `DEMO (synthetic, not a reading)`.
- Demo suppressed the status poll only. The same menu that said "the cabinet is
  NOT being read" still ran the loopback dashboard probe, still offered the
  real Doctor and the fleet wrappers, and derived the kill-switch lever's VERB
  and enablement from the synthetic snapshot — so `--pet-demo PAUSED` offered
  "▶ Resume Officers…". Actuation was always safe (the lever re-reads Redis
  before arming); the label was not. Every acting item is now disabled in demo,
  the probe does not run, and the README's overclaim is corrected.
- The pixel-arm fixture skipped on the binary's error TEXT, so a broken-sheet
  failure could have converted itself into a green skip. It now skips only when
  the art is genuinely absent from the checkout.
- The display link retained the controller and kept running against a hidden
  window (0.3% of a core drawing frames nobody can see). `setVisible(false)`
  now stops the clock, which also releases the link's strong hold; the dead
  `close()` is gone.

## Nits taken

Guarded bitmap reps instead of force-unwraps · bounds guard moved before the
index computation in `cell()`, with lower bounds · wrapping `&+` on the
`&+`-advanced tick · the constant-0 offset in `place()` replaced by a
precondition that states the invariant it encodes · dead `silhouette()`
removed · the world's per-slug animation `phase` is now carried rather than
silently dropped while claiming "the same cadence" · `--pet-tick` added so the
pixel gate can sample more than one frame of the strip, with an arm proving the
walk cycle advances · the union arm's dropped `assert calls` restored · a
source pin added for the demo suppression, which nothing else in the suite
could see.

## Evidence

- `cabinet/scripts/tests/test_build_companion.py` — 21 passed, 0 skipped, cache
  purged, on the fixed tree.
- Every new arm mutation-proved able to fail, cache purged each time: forbidden
  literal, click-through pin flipped, atlas geometry drift, cast-count drift,
  two states made identical, OFF made to walk, degraded GREEN allowed to walk,
  AMBER left in colour, GREEN desaturated, OFF filled in, GREEN given a chip,
  dimension check removed, inkless-cell fallback removed, walk frame frozen,
  demo poll-suppression deleted, demo menu lockout deleted, and both overflow
  guards removed together.
- `cabinet/scripts/tests` (excluding the egg suite): 5071 passed, 33 skipped.
- `check-layer-separation.sh`: `new=0 fixed=0 — OK`.
- `docs-track-code-sweep.sh`: `DOCS_SWEEP GREEN (files=64 findings=0)`.
- shellcheck + `bash -n` on `build-companion.sh`: clean.
- The egg suite is red until this commit exists — `egg-export.sh` cuts
  `git archive HEAD`, and the new `expect-present cabinet/companion/pet.swift`
  row cannot resolve against a tree that does not yet carry the file. Re-run
  after the commit, not before.

## Not reviewed here

How it LOOKS. That is the Captain's eye, and it is in
`designs/dock-pet-live-proof-2026-07-30.png` (meta workspace): the pet in his
real Dock at true size in every state, plus a zoom.
