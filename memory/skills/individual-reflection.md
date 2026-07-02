# Skill: Individual Reflection (Evolved)

**Status:** promoted
**Created by:** foundation (evolved by CoS per Captain directive 2026-04-04)
**Date:** 2026-04-04
**Validated against:** experience record review, pattern detection, value maximization
**Usage count:** 0

## When to Use

Event-triggered — reflection fires when there's something worth reflecting on, not on a clock: after compaction (`post-compact.sh` injects the prompt), after a material completion milestone, or on explicit nudge from CoS (your self-wake loop also runs a `reflection_due` gate so a reflection fires once new work has accumulated). Skip if idle with no new work since last reflection. Stamp + feed the retro counter via the shared sink at the end of each pass — `. cabinet/scripts/lib/reflection.sh && reflection_stamp <role>` — which writes `cabinet:schedule:last-run:<role>:reflection` AND `INCR cabinet:reflections:count` against the host that actually resolves here (never the old `-h redis` that silently failed on Mac). The retro-trigger watches the count.

## Procedure

1. **Read your recent experience records:**
   ```bash
   ls -lt memory/tier3/experience-records/$(date -u +%Y-%m-%d)-<your-role>-*.md | head -10
   ```
   Also check yesterday's if the 6h window spans midnight. If you have ZERO records since last reflection, that's a red flag — you were idle.

2. **Self-assess with SPECIFIC answers (not "all clear"):**
   - "What did I actually produce in the last 6 hours?" — name concrete outputs (PRs, specs, briefs, tests, audits)
   - "What went wrong or was harder than expected?" — name at least one friction point
   - "What did I learn that I didn't know before?" — name one thing
   - If you can't answer these, you weren't doing enough real work.

3. **Detect patterns — adapt at reversibility-gated speed (NOT a blunt count):**
   How fast you act on a pattern is gated by **how expensive it is to be wrong**, not by
   how many times you've seen it (Nate's A1 reversibility principle). A flat "wait for 3
   occurrences" kills the fast loop where it's cheapest and safest:
   - **Cheap + reversible — adjust your OWN behavior NOW (1 occurrence).** If the fix is
     something you control and a wrong call self-corrects next cycle at near-zero cost
     (how you sequence a sweep, which context you gather first, a default you pick), change
     it immediately and note it in `instance/memory/tier2/<your-role>/patterns.md`. Don't
     wait to see it twice — immediate+reversible adaptation **compounds** (adapt → observe →
     adapt is a faster learning loop). Observe the result next cycle; if it was wrong, revert.
   - **Expensive / harder-to-reverse — gate on "reversible + evidenced", not on a count.**
     A draft skill others will load, a shared-infra change, anything that affects other
     officers: write the draft to `memory/skills/evolved/` with the **evidence** (what you
     saw, why it generalizes) and let the evolution-loop validate it before promotion.
   - **Irreversible / germline / spends Captain attention** (a `.claude/rules` rule, a
     Captain-attention proposal, a tool to build): always propose-first with evidence —
     never self-apply. Surface to CoS; CoS routes to the Captain.

4. **Value maximization — produce at least ONE actionable idea:**
   - "What's the highest-value thing I could do RIGHT NOW that nobody asked me to?"
   - "What gap exists in the product/process that my skills could fill?"
   - "What did another officer produce that I should build on?"
   - You MUST produce at least one concrete idea or proposal. "All clear" is not acceptable.
   - Send proposals to CoS via `notify-officer.sh cos "..."`. CoS routes to Captain if it requires approval.

4b. **Counterfactual-replay (cross-cutting — one change → 10x):**
   - Ask of your most significant task this cycle: **"what ONE change would have made this 10x better?"** — a missing tool, a different approach, an absent piece of context, a process that should exist. Name it in one sentence.
   - Pass it on the experience record (step 6) via the `COUNTERFACTUAL` env so it is captured AND counted. The escalation tier follows the same reversibility logic as step 3: if the counterfactual names a **cheap, reversible change you own**, just make it next cycle — don't wait for it to recur. The auto-escalation in the sink is reserved for the **expensive/irreversible** wall (a tool the cabinet must *build*, which spends Captain attention): a single such counterfactual is a note; recurrence of the SAME one (tracked by slug in Redis) auto-escalates to a capability-gap proposal — proposal-only, Captain-gated. That gate is correctly conservative *because the action it guards is expensive and hard to reverse*. (The recurrence-count threshold itself lives in code at `cabinet/scripts/record-experience.sh`; tuning it to the reversibility tier is a Captain-gated change, not a self-applied one.) See `docs/meta-cognition-direction-2026-06-25.md`.

5. **Update Tier 2 working notes:**
   - Any new knowledge about the codebase, product, or domain
   - Any corrections to existing notes
   - What you plan to work on in the next 6 hours

6. **Write an experience record for the reflection itself:**
   Include: what you produced, what you learned, your next action, and (cross-cutting) the counterfactual via the `COUNTERFACTUAL` env.
   ```bash
   COUNTERFACTUAL="<the one change that would have made the cycle's key task 10x better>" \
   bash /opt/founders-cabinet/cabinet/scripts/record-experience.sh <role> success "6h reflection" "Produced: [list]. Learned: [what]. Next: [action]." "Friction: [what]. Idea: [proposal]." "reflection"
   ```

7. **Record the reflection (stamp last-run + feed the retro counter):**
   Use the shared sink — it writes both `cabinet:schedule:last-run:<your-role>:reflection`
   AND `INCR cabinet:reflections:count` against the host that actually resolves on this
   deployment (Mac-native `localhost` or Docker `redis-<slug>`). Do NOT hand-write the
   `redis-cli` (the old `-h redis` form silently failed on Mac and the stamp never landed):
   ```bash
   . "${CABINET_ROOT:-/opt/founders-cabinet}/cabinet/scripts/lib/reflection.sh"
   reflection_stamp <your-role>   # SET last-run + INCR reflections:count, host-correct
   ```
   This is what feeds the cross-officer-retro trigger (`reflections:count >= 5`) and keeps
   the meta-cognition anomaly-scan's overdue detector accurate.

## Expected Outcome

Each Officer catches their own patterns before CoS's retro does. Tier 2 memory stays current. Draft skills emerge from repeated procedures. Officers proactively surface ideas for increasing their value — the Cabinet continuously improves from within, not just from Captain direction.

## Known Pitfalls

- Reflecting without reading the actual records — just doing it from memory is unreliable
- Writing "everything went well" when records show friction — be honest with yourself
- Not updating Tier 2 notes — next session starts with stale context
- Forgetting to record the timestamp — leads to double-running or skipping
- Skipping the value maximization step — this is how the Cabinet grows smarter

## Validation Scenarios

- Scenario 1: Officer notices a 3-time failure pattern → writes draft skill → CoS picks it up in next retro
- Scenario 2: Officer updates Tier 2 with new codebase knowledge → next session starts faster
- Scenario 3: Reflection finds no patterns → records timestamp → moves on (not every reflection produces output)
- Scenario 4: CRO realizes specs are shipping without research input → proposes tighter CPO integration → CoS approves

## Origin

Foundation skill — evolved per Captain directive to add proactive value maximization.
