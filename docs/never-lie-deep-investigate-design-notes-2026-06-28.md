# Never-lie + deep-investigate draft system — grounded design notes (2026-06-28)

Status: BRAINSTORM (Nate-gated). Do NOT implement until Nate answers the 2 forks
(ask-vs-decide threshold; inbox-zero autonomy level). These notes ground the
design in what the pipeline ACTUALLY does today, so the design isn't built on
assumptions (the exact shallowness Nate is criticizing).

## Grounded reality — what draft_lib ALREADY has (verified in code)
The retrieval capability is NOT the gap. draft_lib already exposes:
- search_brain (vault), person_intel, open_commitments, conversation_history
- Monday work context (meta-board → boards → dev-tasks), query_live_data (read-only Neon)
- search_codebase (indexed product pillar), web_research (3 engines)
- voice.md, should_nate_reply gate (audience-aware: direct/group/list)
- NEW today: calendar_busy (Outlook) + has_meeting_time_ask propose-don't-commit guard

## So the REAL gaps (not retrieval)
1. INVESTIGATION IS OPTIONAL, NOT MANDATED. The RESEARCH planner *offers* tools; for
   an "easy" reply (agreeing to a meeting) it skips the deep dive → blind "passer fint".
   Fix: a MANDATORY pre-draft dossier for every real-person reply — workstream/plan,
   why-now, counterparty goals + trajectory, open commitments, board state, prior thread,
   Nate's stance. Not optional, not planner's discretion.
2. NO TRUTHFULNESS GATE. Nothing checks "is each factual claim in the draft BACKED?"
   before it's presented/sent. Fix: a claim-check pass — every assertion (a time works,
   X done, I'll do Y) must map to dossier evidence; unbacked → strip / turn to question /
   ask Nate. This is the "NEVER lie" piece, enforceable in code (like the calendar guard).
3. AGREE-BY-DEFAULT (sycophancy). The drafter reaches for "yes 👍". Fix: derive Nate's
   ACTUAL stance from nate_model + decisions + commitments BEFORE composing; represent it,
   including pushback/decline/questions. Not a generic agreeable reply.
4. The thin SCHEDULED pipe is the wrong executor for officer-grade reasoning → move this
   to the Comms Officer (converges with inbox-zero).

## The 2 Nate-forks (awaiting his answer)
- Ask-vs-decide: when key claims can't be backed → err toward asking (safe/more pings)
  vs investigate-then-draft-confidently (smoother/riskier)?
- Inbox-zero autonomy: act on safe stuff (archive/file/task-create) + surface judgment
  calls, vs show-me-first until trust calibrated?

## Inbox-zero shape (the email ask)
Every email → classify (info→archive, action→task-by-when, do-now→surface, →folder) →
drive to 0; deep-dossier reserved for real-people-needing-reply (newsletter ≠ Tomás treatment).
First version in show-me-first mode (proposes per-email, touches nothing) → graduate to acting.

## Tiering (efficiency — deep dossier is expensive)
Cheap classify on ALL inbound (inbox-zero). Deep dossier ONLY on real-person messages
needing a considered reply. "from real people" is Nate's exact qualifier.

---

# Mechanism design (deepened 2026-06-28, overnight) — decision-ready, still Nate-gated

## A. The truthfulness gate (the "NEVER lie" core — enforceable, like the calendar guard)
Model it on the calendar guard that shipped tonight (has_meeting_time_ask → propose-don't-commit):
a SEPARATE pass over the composed draft, not a hope baked into the drafting prompt.
- CLAIM EXTRACTION: pass the draft + the dossier to a checker that lists every factual
  assertion (a time works, X is done/shipped, I'll do Y by Z, "we decided", a number/price,
  a person's position). Each claim → tagged with its dossier evidence-source or NONE.
- DISPOSITION per unbacked claim (load-bearing): STRIP (drop it), SOFTEN (→ a question or
  "let me confirm"), or HOLD-AND-ASK Nate. Severity tiers: a slot/commitment/price/"decided"
  = HOLD-AND-ASK (never emit unbacked); a soft courtesy phrase = SOFTEN.
- This is the generalisation of the calendar guard from "meeting times" to ALL claims.
  Same shape: detector → if-unbacked → propose-don't-assert. Code, not vibes.

## B. The mandatory dossier (deep-dive — maps each slot to an EXISTING tool)
For every real-person message warranting a reply, build (not optionally — required):
| Dossier slot | Filled by (already exists) |
|---|---|
| Full thread + audience | conversation_history + audience_of |
| Counterparty intel + trajectory | person_intel + search_brain(recent interactions) |
| WHY now / the workstream / next week's plan | search_brain(project) + Monday boards + search_codebase |
| Open commitments both directions | open_commitments |
| Board/task state the topic touches | Monday meta-board → boards |
| Live data when technical | query_live_data (read-only) |
| Nate's stance/interests | nate_model + captain-decisions.md + captain-patterns.md |
| Calendar (for time asks) | calendar_busy (shipped) |
| Images/screenshots | vision_lib (shipped) |
The gap was never the tools — it's that build_draft makes this OPTIONAL. Fix: a required
dossier step whose OUTPUT is the input to both the truthfulness gate and composition.

## C. Represent Nate's stance (anti-sycophancy)
Before composing, answer explicitly from the dossier: "what is Nate's actual interest here,
and would he agree / push back / question / decline?" Compose THAT. The should_nate_reply
gate already knows Nate rarely replies to groups; extend the same judgment to CONTENT
(not just whether-to-reply): a reply that just agrees when the dossier says Nate would
push back is a FAILURE, surfaced like an unbacked claim.

## D. Inbox-zero triage state machine (the email ask)
Per inbound email: CLASSIFY → {info-only→archive · needs-action→create task w/ due · do-now→surface ·
belongs-in-folder→move · awaiting-reply→hand to the reply pipeline above}. Cheap classify on ALL;
the deep dossier (B) only fires on the awaiting-reply / real-person branch. Drive inbox→0.

## E. The two forks → design implications (so either choice is ready)
- ASK-vs-DECIDE:
  · "err toward asking" → truthfulness gate's HOLD-AND-ASK threshold is LOW (any load-bearing
    unbacked claim → ask Nate). More pings, max safety. Good for the trust-building phase.
  · "investigate-then-draft-confidently" → gate tries HARD to back claims from the dossier
    first; only asks when the dossier genuinely can't resolve it. Fewer pings, needs the
    dossier to be strong. Recommended AFTER the dossier proves reliable.
  · Suggest: START low-threshold (ask more), graduate as the dossier earns trust.
- INBOX-ZERO AUTONOMY:
  · "show-me-first" → triage proposes per-email, touches nothing; Nate sees its judgment.
  · "act on safe" → archive newsletters / file receipts / create tasks autonomously; surface
    only judgment calls.
  · Suggest: show-me-first for ~1 week → auto-act on the categories that proved 100% right →
    keep surfacing the genuinely-ambiguous. Graduated autonomy, same as the cabinet's posture.

## F. Staged rollout (safe, trust-calibrated — not a big-bang)
1. Truthfulness gate + mandatory dossier on the EXISTING draft pipeline (biggest safety win, smallest surface).
2. Inbox-zero triage in show-me-first mode (read-only, learns Nate's filing).
3. Migrate the reply intelligence into the Comms Officer (officer-grade reasoning; converges 1+2).
4. Graduate autonomy per the fork choices as each layer earns trust.
Each stage independently verifiable; nothing irreversible; matches Nate's stage-gate philosophy.

## Open for the morning
Nate's two forks (E) are the only blockers to speccing stage 1. Everything above is grounded
in tools that exist + guards already shipped tonight. Demo offer stands: run dossier (B) on the
real Tomás+Kristoffer thread to show what it surfaces vs the blind "passer fint".
