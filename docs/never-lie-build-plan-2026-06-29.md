# Never-lie + inbox-zero — BUILD PLAN + receipt germline carve-out spec (2026-06-29)

Status: PLAN for cos review (Nate's #1 priority, forks green-lit). Reports the
build before any auto-send, per cos's instruction. Grounds every component in
code that exists today + the calendar-guard pattern shipped 2026-06-28.
Design refs: `never-lie-deep-investigate-design-notes-2026-06-28.md` (§A–F) +
`never-lie-demo-tomas-kristoffer-2026-06-28.md`.

## Nate's fork answers → concrete policy (relayed by cos)
- **Fork 1 (ask-vs-decide) = ask-more + LEARN.** Truthfulness gate runs at the
  LOW HOLD-AND-ASK threshold (any load-bearing unbacked claim → ask Nate). PLUS
  a rule-learning loop: Nate's one-liner on a shown item ("just archive" / "let
  me know then move" / "investigate then recommend") is ENCODED as a durable
  per-sender/per-type rule (persisted) → asks once, applies forever. Graduating
  autonomy by learning him (design §E "start low, graduate").
- **Fork 2 (inbox-zero autonomy) = show-me-first + named auto-act carve-outs.**
  Default show-first + learn; newsletters auto-move; receipts auto-forward only
  HIGH-CONFIDENCE + only after a show-first proving batch; everything-else
  show-first.

## What already exists (verified — the gap is NOT retrieval)
draft_lib: search_brain, person_intel, open_commitments, conversation_history,
audience_of/should_nate_reply, Monday boards, query_live_data (RO Neon),
search_codebase, web_research, voice.md. Shipped 2026-06-28: `email_lib.calendar_busy`
+ draft_lib `has_meeting_time_ask`/`CAL_GUARD`/`CALENDAR_COMPLETE` (the proven
detector→if-unbacked→propose-don't-assert guard). email_lib write path:
`MSGRAPH_WRITE_WEBHOOK` (Captain-approved folder-WRITE, 2026-06-24).

---

## STAGE 1 — Truthfulness gate + mandatory dossier (existing draft pipeline)
Biggest safety win, smallest surface, **approve-only (queue_draft) — NO auto-send,
needs NO germline carve-out. Safe to ship now.**

- **1a. Mandatory dossier** (design §B): in `build_draft`, replace the *optional*
  RESEARCH planner with a REQUIRED dossier step that fills the §B slots from the
  EXISTING functions (thread+audience, person_intel+trajectory, why-now/workstream
  via search_brain+Monday+search_codebase, open_commitments both directions, board
  state, query_live_data when technical, nate_model+captain-decisions/patterns,
  calendar_busy, vision_lib). Output = one structured dossier object → input to
  BOTH the gate (1b) and composition. The fix is making it non-optional, not new tools.
- **1b. Truthfulness gate** (design §A — the never-lie core): a NEW post-composition
  pass, same shape as the calendar guard. After `cl.call_llm` returns the draft:
  CLAIM-EXTRACTION (list every assertion — a time works, X done/shipped, I'll do Y
  by Z, "we decided", a number/price, a person's position) → map each to dossier
  evidence or NONE → DISPOSITION: STRIP / SOFTEN(→question/"let me confirm") /
  HOLD-AND-ASK. Severity: slot/commitment/price/"decided"/"done" = HOLD-AND-ASK
  (never emit unbacked); soft courtesy = SOFTEN. Per fork-1: threshold LOW.
  Generalises `has_meeting_time_ask` from meeting-times to ALL claims. Code, not vibes.
- **1c. Represent-Nate's-stance** (design §C, anti-sycophancy): before composing,
  derive Nate's actual stance from the dossier (nate_model + decisions + commitments)
  — agree / push-back / question / decline — and compose THAT. A just-agree draft
  when the dossier says push-back is a FAILURE, surfaced like an unbacked claim.
- **Verify:** run on the real Tomás+Kristoffer demo thread + a battery; confirm it
  yields the informed/truthful reply (convene-the-slot, names #2 Pro-spinner +
  credits bug, reflects the 1-week deadline) NOT blind "passer fint"; confirm
  load-bearing unbacked claims get HELD. nate_model/voice never leave the machine
  (brain-bridge). Outbound stays queue_draft.

## STAGE 2 — Inbox-zero triage, show-me-first + rule-learning (read-only)
Classification touches nothing; proposes per-email.

- **2a. Cheap classifier on ALL inbound** (state machine §D): info→archive ·
  needs-action→task-by-when · do-now→surface · belongs-in-folder→move ·
  awaiting-reply→hand to Stage-1 reply pipeline. Tiering: cheap classify on all;
  the expensive §B dossier fires ONLY on the awaiting-reply/real-person branch.
- **2b. Rule-learning store** (fork-1, the key NEW mechanism): a persisted
  per-sender/per-type → action store (JSON/YAML in `instance/` — cabinet repo, not
  vault, so officer-writable; keyed by sender/domain+type). Consulted BEFORE every
  proposal; Nate's one-liner encodes a durable rule → ask once, apply forever.
- **2c. Newsletters** (rule 2): → propose auto-move to a Newsletters folder + fold
  into the morning-briefing digest. Show-first first → auto once proven.
- **2d. Receipts** (rule 3): → propose forward-to-`ulkri@stepnetwork.dk` + move to
  a Receipts folder, in SHOW-FIRST to PROVE classification on the first batch.
  Auto-forward stays gated behind Stage 2.5 (germline) and only engages after the
  proving batch hits 100% precision. Folder create/move uses MSGRAPH_WRITE_WEBHOOK.
- **2e. Everything-else** (rule 4): show-first + learn.
- **Verify:** ~1 week show-me-first; measure per-category precision; graduate a
  category to auto only at proven 100%.

## STAGE 2.5 — Receipt auto-forward germline carve-out (BLOCKED on Nate)
The ONLY outbound-without-per-item-approval path. Spec below. Engages only after
Stage-2 proving. Implemented IN the brain server (sanctioned path), never officer Graph.

## STAGE 3 — Migrate reply intelligence into the Comms Officer
The thin scheduled draft-reply pipe is the wrong executor for officer-grade
reasoning (design §29); comms-officer becomes the executor — converges 1+2.

## STAGE 4 — Graduate autonomy per the fork choices as each layer earns trust
Low-threshold gate → confident gate; show-first → auto per proven category.

---

## RECEIPT GERMLINE CARVE-OUT SPEC (flag to Nate — do NOT self-apply)
Brain-bridge forbids outbound except via `queue_draft` (per-item Telegram approval).
Auto-forwarding receipts to Ulrik without per-item approval needs a NARROW,
Nate-applied germline carve-out. Proposed exact spec:

**Permit the BRAIN SERVER to forward an email to exactly `ulkri@stepnetwork.dk`,
without per-item Telegram approval, IFF ALL hold:**
1. **Classification:** message classified RECEIPT at confidence ≥ HIGH bar by ≥2
   independent signals (e.g. sender-domain known-vendor + body markers
   invoice/kvittering/total/order#). Anything below → normal queue_draft show-first.
2. **Proven:** the Stage-2 show-first proving batch has completed at 100% precision
   on a first batch Nate reviewed (the carve-out stays DORMANT until then).
3. **Record-only:** the original is forwarded VERBATIM — no new claims composed
   (forwarding ≠ drafting; the never-lie gate is N/A because nothing is asserted).
4. **Single fixed recipient:** ulkri only; the carve-out cannot send anywhere else.
5. **Implemented in the sanctioned send path** (a new brain-server capability, e.g.
   `forward_receipt(message_id)`), NOT a raw Graph/Make call from officer code. The
   officer REQUESTS; the brain server ENFORCES conditions 1–4 and sends.
6. **Auditable + reversible:** every auto-forward → `log_reasoning` + a receipts
   ledger + folded into the morning digest (Nate sees post-hoc what was forwarded
   even without pre-approval); a single killswitch disables it instantly.

**What it does NOT permit:** composing/replying, any recipient other than ulkri,
forwarding an ambiguous/below-bar message, or any send before the proving batch.
A misclassified email can NEVER wrongly reach Ulrik: below-bar OR unproven →
falls back to queue_draft show-first (Nate approves).

---

## Safe-now vs gated
- **Stage 1 = safe to start now** (approve-only, no auto-send, no germline, no folder
  mechanics) on cos's go.
- **Stage 2 folder mechanics** (Newsletters/Receipts folder create+move) partially
  gated on the make-MCP re-auth / proxy slow-query fix: folder ENUMERATION/create is
  a collection query that currently flaps. Classification + show-first proposals are
  unaffected and can run read-only meanwhile.
- **Stage 2.5 auto-forward** gated on Nate applying the germline carve-out above.

## Ask to cos
(1) Go to start Stage 1? (2) Any threshold/sequencing prefs from Nate (HOLD-AND-ASK
severity tiers, the receipt HIGH-confidence bar, show-first batch size before
graduating)? (3) Relay the germline carve-out spec to Nate for application.
