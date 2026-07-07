# Skill: Captain-Intent Inference (5th improvement loop — WHY before WHAT)

**Status:** promoted
**Created by:** foundation (relocated from CLAUDE.md by the principles-over-specifics collapse, 2026-06-25 — mechanics were inline in CLAUDE.md §"Captain-Intent Inference"; moved here so CLAUDE.md carries the principle + pointer and nothing is lost)
**Date:** 2026-06-25
**Validated against:** live use — `shared/interfaces/captain-intents.md` is populated by this loop
**Usage count:** (carried — in continuous use)

## When to Use

The 4th loop (pattern listening) is reactive — it needs a Captain meta-signal to fire. **The 5th loop is proactive: hypothesize the Captain's latent WHY before every Captain-facing outbound, and shape the message around the WHY, not just the surface WHAT.** Officers are *intent servers*, not prompt executors — the stated ask is the tip of the iceberg. Run before any Captain-facing outbound (DM reply, proactive DM, briefing — **NOT** officer-to-officer triggers). Universal Cabinet rule — every officer, every Captain-facing outbound, every deployment. CoS owns the ledger's integrity and audits in retros.

## Procedure

1. **Pre-reply WHY scan** (two-step mental pass):
   1. **Read `shared/interfaces/captain-intents.md`** — which inferred intents apply to this context?
   2. **Hypothesize the latent goal** behind the surface ask. What would make this response *delight* vs. *frustrate*? What unstated concern does the Captain likely have?
   Then shape the reply around the WHY, with the surface ask addressed as part of it — not separately.

   **Example.** Captain asks *"how's COO doing?"*
   - WHAT = status report
   - WHY = is the trim working? is cost under control? is launch risk rising from reduced coverage?
   - Reply addresses all three, not just the surface.

2. **Act vs. ask.** If confidence in the inferred WHY is high, act on it. If the inferred WHY would meaningfully change the reply *and* confidence is low, ASK before composing — one short clarifier is cheaper than a misaligned reply.

3. **Intent ledger maintenance.** `shared/interfaces/captain-intents.md` holds the inferred latent goals, each with evidence + confidence. Unlike `captain-patterns.md` (which requires explicit Captain feedback to populate), intents are *inferred from behavior*. **All appends go through the sanctioned interface** (2026-07-07: the captain-law ledgers are append-only; direct Write/Edit and bash redirects are hook-blocked): `cabinet/scripts/append-interface.sh captain-intents` with the entry on stdin (heredoc/pipe; landed under a provenance-stamped `### officer-note` heading — use `###`-or-deeper headings inside the entry). Growth paths:
   - **48h retro (CoS-owned):** scan `captain-decisions.md` entries since last retro; extract latent-goal patterns; append new intents with evidence.
   - **Ad-hoc:** any officer observing a candidate intent in a Captain DM proposes via `notify-officer.sh cos "...candidate intent..."`.
   - **Never overwrite.** Append-only; confidence may be revised up/down over time via supersession.
   - **Anti-accretion gate (Layer 1).** Before appending a NEW intent, run `bash cabinet/scripts/meta-cognition/encode-gate.sh "<intent text>"` — if it flags a close existing principle/intent, prefer revising that one's confidence over adding a near-duplicate row. Proposal-only, Captain-gated; never blocks. See `framework/docs/meta-cognition-direction-2026-06-25.md`.

4. **Relationship to review agents.** The "spawn review agent before commit" discipline handles dry-runs for specs + major artifacts *after* drafting (reactive). The 5th loop adds the intent lens *before* drafting (proactive). Both are required for major outputs; intent scan alone suffices for routine Captain replies.

5. **Session-start discipline.** `captain-intents.md` is Tier 1 required reading. Always read at session start — that's how inferred intents propagate across sessions.

## Expected Outcome

Captain-facing outbound is shaped around the latent goal, not just the literal ask — responses delight rather than technically-answer-and-frustrate. The intent ledger grows from observed behavior.

## Known Pitfalls

- Answering the surface WHAT and ignoring the WHY — the failure this loop exists to prevent.
- Acting on a low-confidence WHY that would materially change the reply, instead of asking one clarifier.
- Overwriting intents instead of appending with revised confidence.

## Origin

Relocated from CLAUDE.md §"Captain-Intent Inference (5th improvement loop)" during the 2026-06-25 principles-over-specifics collapse (audit G-1). The mechanics are unchanged; CLAUDE.md now carries the principle and points here.
