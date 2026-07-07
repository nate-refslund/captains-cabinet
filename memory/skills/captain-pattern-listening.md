# Skill: Captain Pattern Listening (4th improvement loop — inline on Captain DMs)

**Status:** promoted
**Created by:** foundation (relocated from CLAUDE.md by the principles-over-specifics collapse, 2026-06-25 — mechanics were inline in CLAUDE.md §"Captain Pattern Listening"; moved here so CLAUDE.md carries the principle + pointer and nothing is lost)
**Date:** 2026-06-25
**Validated against:** live use — `shared/interfaces/captain-patterns.md` is populated by this loop
**Usage count:** (carried — in continuous use)

## When to Use

The three self-improvement loops (per-task reflection, event-triggered reflection, 48h retro) are reactive and cycle slower than the Captain's in-conversation signals arrive, so implicit preferences and hints get lost between loops. **The 4th loop fixes that by listening inline.** Run it on **every Captain DM**, before composing the reply. Universal Cabinet rule — every officer, every Captain DM, every deployment. The coordinating officer (Chair/CoS) owns `captain-patterns.md` integrity and audits it in retros.

## Procedure

1. **Pre-reply meta-signal scan.** Before composing the reply, scan the Captain's message for any of these signals:
   - Process questions: "should we…", "can we start doing X", "is there a way to…"
   - Memory/tracking hints: "so we don't forget", "let's track this", "remember to Y", "make a note", "as I said before", "like last time"
   - Preference declarations: "always X", "never Y", "I prefer", "let's start", "let's stop"
   - Implicit frustration: "we keep forgetting", "this keeps happening"
   - Repeated phrasings you've seen before from the Captain (cross-session memory applies)

2. **If detected, inline encode-offer.** Append a short offer at the end of the reply: *"Want me to encode this as standing behavior for all officers?"* — not a paragraph, one sentence. If the Captain confirms, proceed to encoding.

3. **Two-count rule.** If the same meta-pattern has appeared twice (count tracked in Redis at `cabinet:patterns:seen:<pattern-slug>`), **skip the question** and just encode it + mention the pattern in the reply: *"Noticed this is the second time — I'm encoding as standing behavior."*

4. **Post-confirm encoding.** Encode the pattern into `shared/interfaces/captain-patterns.md` **via the sanctioned append interface** (2026-07-07: the three captain-law ledgers are append-only; direct Write/Edit and bash redirects are hook-blocked so officer text never becomes standing law without provenance):
   ```bash
   cabinet/scripts/append-interface.sh captain-patterns <<'EOF'
   <the pattern entry text>
   EOF
   ```
   The interface stamps your entry under a `### officer-note — appended by <officer> @ <UTC> [trust:officer]` heading (use `###`-or-deeper headings inside the entry — `## ` is the Captain-entry format and is refused). Include the Captain evidence (quoted message + date) and the underlying principle.

   **Anti-accretion gate (Layer 1 — run BEFORE you add the row).** Ask: *"is this a specific instance of an existing principle? Should this be a principle, not a case?"* Run the gate on the candidate text:
   ```bash
   bash cabinet/scripts/meta-cognition/encode-gate.sh "<the pattern text you are about to encode>"
   ```
   If it prints a proposal id, it found a close existing principle and emitted a collapse proposal (proposal-only, Captain-gated → `meta-cognition-proposals.md`). The gate never blocks — you still encode — but prefer generalizing the existing principle over adding row N+1 when the overlap is real. Concrete facts/IDs are exempt (the gate stays silent on them). See `framework/docs/meta-cognition-direction-2026-06-25.md`.

   Then broadcast to active officers (roster-derived, preset-agnostic — iterate the seeded roles, not a hardcoded officer list):
   ```bash
   for role_yml in "${CABINET_ROOT:-/opt/founders-cabinet}"/instance/roles/active/*.yml; do
     [ -f "$role_yml" ] || continue
     o="$(basename "$role_yml" .yml)"
     [ "$o" = "<self>" ] && continue
     bash /opt/founders-cabinet/cabinet/scripts/notify-officer.sh "$o" "New Captain pattern encoded in shared/interfaces/captain-patterns.md: <pattern-name>. Re-read the file before your next Captain reply."
   done
   ```

5. **Session-start discipline.** `captain-patterns.md` is in Tier 1 required reading. Always read it at session start — that's how patterns propagate across sessions.

## Expected Outcome

Implicit Captain preferences and hints are captured inline at the moment they surface — not lost between the slower reflection loops — and propagate to every officer via `captain-patterns.md`.

## Known Pitfalls

- Encoding without Captain confirmation (unless the two-count rule fired) — that's putting words in the Captain's mouth.
- Turning the encode-offer into a paragraph — it is one sentence at the end of the reply.
- Not reading `captain-patterns.md` at session start — newly encoded patterns then don't reach you.

## Origin

Relocated from CLAUDE.md §"Captain Pattern Listening (4th improvement loop)" during the 2026-06-25 principles-over-specifics collapse (audit G-1). The mechanics are unchanged; CLAUDE.md now carries the principle and points here.
