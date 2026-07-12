<!-- DRAFT — NOT FOR PUBLICATION. Publishing is CG-7 Captain-gated. -->

**DRAFT — NOT FOR PUBLICATION. Publishing is CG-7 Captain-gated.**

# Quickstart GIF — shot-by-shot script (~45 s)

One terminal GIF for the README / Show HN post: hatch → proofs green →
first briefing → receipt anatomy → `/receipts`. Total runtime target
**45 s** (hard max 50 s; loops, so the last frame must be readable).

## Ground rules (binding)

- **Synthetic estates only.** Record against a scratch hatch (throwaway
  clone, fresh `instance/`) and the Testburg fixture — never the live
  deployment. The hero-demo runbook's review gate applies to every frame
  (`docs/runbooks/hero-demo-2026-07-10.md` §A6).
- **Honest clocks.** Shots 1–2 show real wall-clock output from the flight
  log. The measured numbers today: clean-room hatch **~8 s with
  dependencies already present**; **TTFR 1–2 s** (proofs-done → first
  receipt). The full ≤90-minute stranger-hatch bar is ratified but **not
  yet timed on a bare Mac** — see the handback section before captioning
  any total-setup-time claim.
- **No caption may say or imply a five-minute install.** The honest claim
  is "first receipt in minutes once hatched".

## LIMEZU CREDIT RULES (Captain-ratified license conditions, 2026-07-12)

Binding on every published visual from this script or any other launch
material:

- Any published image/GIF containing Cabinet World scenes carries
  **"Art: LimeZu — limezu.itch.io"** nearby (caption, post body, or the
  hosting README). The in-product bottom-bar credit satisfies this when it
  is legible in frame; otherwise add the caption.
- **NEVER publish raw or near-raw tilesheets or 1:1 sprite grids** — only
  composed, product-zoom scenes. No NFT use of the art, ever.
- The non-commercial **Modern tiles_Free pack must never enter the
  pipeline** (asset dirs, manifest, renders, or captures).

(This script's shots 1–5 are terminal/dashboard surfaces and never open
`/world`, so today's shot list publishes no world scenes — the rules bind
any future world footage.)

## Pre-flight (before recording)

- Terminal ~100×30, dark theme, font ≥15 pt, plain prompt (`PS1='$ '`),
  shell history off for the session.
- Fresh clone of the public repo in a scratch dir; dependencies present
  (Homebrew, python3.12, Claude Code logged in) — this is the "prepped
  box" premise and the GIF must caption it (see Shot 1).
- Dashboard shot: browser window ~1360×900, content region only — the
  nav's project selector stays OUT of frame (runbook A6 gate 2).
- Any screen recorder that exports GIF/MP4 works; record shots separately
  and cut — do not try one continuous take.

## Shot list

| # | Time | Surface | One-line content |
|---|------|---------|------------------|
| 1 | 0:00–0:08 | terminal | `hatch.sh --defaults` runs the chain |
| 2 | 0:08–0:16 | terminal | proof gates green + flight summary (TTFR) |
| 3 | 0:16–0:28 | terminal | first briefing — three proposed cards |
| 4 | 0:28–0:36 | terminal | demo receipt anatomy (what/why/cost/undo) |
| 5 | 0:36–0:45 | browser | `/receipts` on the Testburg demo server |

---

### Shot 1 — the hatch (0:00–0:08, 8 s)

Command (typed on screen, then run):

```bash
bash cabinet/scripts/hatch.sh --defaults
```

Expected screen: the numbered chain scrolling — host bootstrap → instance
generation → activation (preset load) → proofs — with per-step flight-log
lines. On a deps-present box the clean-room-shaped hatch completes in ~8 s,
so this shot can run in real time; if the recorded run is slower, speed the
scroll (2×) rather than cutting steps.

Caption (burned in, bottom): `one command — deps preinstalled`.

> HANDBACK GATE: if the caption instead claims a total setup time (e.g.
> "fresh Mac to org in N min"), Shot 1 is BLOCKED until the bare-Mac
> timing handback (below) is done.

### Shot 2 — proofs green + flight summary (0:08–0:16, 8 s)

No new command — the tail of the same run. Expected screen: the proof
gates reporting green — null-hatch (P-a), the clean-room pytest subset
(P-b), dry renders (P-c) — then the printed flight summary table with
per-step timings and the **TTFR** line (proofs-done → first receipt,
measured 1–2 s), plus the numbered errand notes (the human-only steps the
hatch refuses to automate: bot token, germline scope lines, TCC grants).

Hold 2 s on the summary table so the TTFR line is readable.

Caption: `proof gates, then your first receipt — TTFR is real output`.

### Shot 3 — the first briefing, three proposed cards (0:16–0:28, 12 s)

Command (the hatch prints the exact path; substitute the real date):

```bash
cat instance/memory/first-briefing-<date>.md
```

Expected screen: the briefing header (`# First briefing — <date>
(LOCAL-FIRST receipt)`), then proposed cards. Scroll slowly and stop after
the **first three cards** — each rendered WHAT / WHY / PROOF-expected with
`captain_ratified: false` visible. That flag is the money-frame: the org
proposed; nothing self-activated.

Caption: `the org proposes — nothing activates without you`.

### Shot 4 — receipt anatomy (0:28–0:36, 8 s)

Command:

```bash
cat instance/memory/demo-receipt.md
```

Expected screen: the seeded, clearly-labeled DEMO receipt showing the four
fields in order — **what** (the exact content), **why**, **cost** (the
demo row's honest shape), **undo** (inverse `none` with the demo reason —
a receipt never claims an undo it does not have). The DEMO label must be
in frame the whole shot.

Caption: `every act leaves this: what / why / cost / undo`.

### Shot 5 — `/receipts` (0:36–0:45, 9 s)

Commands (run before recording the browser):

```bash
bash cabinet/scripts/demo-dashboard.sh      # serves 127.0.0.1:3199
# afterwards: bash cabinet/scripts/demo-dashboard.sh --stop
```

Browser: `http://127.0.0.1:3199/receipts`, login `testburg-demo`. Expected
screen: the six Testburg receipts — plain-language what/why, one attributed
cost (`~$0.0148 — 1930 in / 210 out tokens (lane-metered)`) and one honest
`cost: unattributed`, undo badges in three states (active with hours left,
one `undone at …`, one `DEMO`-badged row). Slow scroll top to bottom.
Badge states are time-of-day dependent: under the default rebase the
earliest undo horizon is `<demo-day>T06:10Z` — record before the rebased
horizons pass, or expect `expired` badges instead of `active` (see the
runbook's A5 badge-timing note).

Framing rules (runbook A6, mandatory): content region only, nav out of
frame; never open `/world`; if a `/governance` bonus frame is wanted, top
cards only. Caption: `synthetic demo data (Testburg) — day one on a real
org starts honestly empty`.

---

## Bare-Mac timing handback (required before public use)

The ≤90-minute full-hatch bar has **not** been timed on a bare Mac. Before
the GIF (or its captions/alt text) ships anywhere public:

1. **Blocked-without-handback:** any caption or alt text stating total
   setup time, and any Shot 1 framing that hides the deps-present premise.
   Needed: one timed `hatch.sh --defaults` run on a bare (or freshly
   wiped) Apple-silicon Mac, flight log kept as the artifact. This is a
   named handback to the Captain — it needs a machine this wave does not
   have.
2. **Usable now (deps-present premise captioned):** Shots 1–4 exactly as
   scripted — the 8 s / TTFR 1–2 s numbers are measured, provided the
   `deps preinstalled` caption stays.
3. **Usable now (review-gated):** Shot 5, after the A6 review gate on the
   captured frames (Testburg vocabulary check, banned-pattern re-read,
   nav out of frame).
4. The finished GIF itself is launch material: **CG-7 — Captain approves
   before it is attached anywhere public.**

## Suggested alt text (honest)

> Terminal: one hatch command runs setup, proof gates report green, and a
> first briefing renders proposed cards marked captain_ratified: false.
> Then a receipt with what/why/cost/undo fields, and a dashboard receipts
> page (synthetic demo data) showing undo badges.
