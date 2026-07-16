---
name: cross-officer-retro
description: "48-hour cross-officer retro driven by CoS. Use when the retro trigger fires (event-driven floor of 5 reflections or 48h ceiling): handoff quality + trigger responsiveness + role evolution proposals. Ends in Part 5 consolidation: 3–5 consolidated_belief rows (incl. failure-patterns) queued to Cabinet Memory."
sunset: '2026-10-05'
---

# Skill: Cross-Officer Retrospective (Evolved)
<!-- single-source (egg R138): the canonical skill body lives HERE (memory/skills/, Captain-applied). .claude/skills/cross-officer-retro/SKILL.md is the on-trigger wrapper — trigger frontmatter + a pointer to this file only, no duplicated body (wrapper side enforced by R155). -->

**Status:** promoted
**Created by:** foundation (evolved by CoS per Captain directive 2026-04-04)
**Date:** 2026-04-04
**Validated against:** coordination pattern detection, improvement proposal cycle, opportunity scanning
**Usage count:** 6

## When to Use

CoS runs this event-triggered: at 5 accumulated reflections across officers (`cabinet:reflections:count >= 5`) OR 48 hours since the last retro — whichever first. Tracked via Redis: `cabinet:schedule:last-run:cos:retrospective`

## Procedure

### Part 1: Experience Record Review (existing)

1. **Gather all experience records since last retro:**
   ```bash
   ls -lt memory/tier3/experience-records/ | head -50
   ```
   Read each record. Group by Officer and by outcome.

2. **Analyze cross-Officer coordination patterns:**
   - **Handoff quality:** Are specs clear enough for CTO? Are research briefs actionable for CPO?
   - **Trigger responsiveness:** Are Officers acting on triggers promptly? Any SLA violations?
   - **Communication gaps:** Is work getting stuck between Officers? Are outputs sitting unread?
   - **Quality pyramid compliance:** Is each layer being followed? Any layers being skipped?

3. **Analyze individual patterns** (supplement to Officers' own 6h reflection):
   - Same failure happening twice → note it
   - Same failure happening 3+ times → propose a change

#### Part 1b: Anomaly-seeking on our own telemetry (Layer 2 — DETECT)

This is the "the cabinet notices what's off about itself" capability (`framework/docs/meta-cognition-direction-2026-06-25.md`). After the record/coordination review, read the already-emitted telemetry and ask: **"what violates what I'd predict?"** — the question that *would have autonomously surfaced this session's stale-index bug*.

```bash
bash cabinet/scripts/meta-cognition/anomaly-scan.sh        # factual telemetry snapshot
```
This reads real streams (tool-call volume by officer, stuck-loop repeats, hook-fire counts, `reflections:count`, overdue scheduled tasks, per-officer cost) — adding NO always-loaded loop. For each number, predict-then-compare: is an officer running far more/less than its baseline? A gate firing on ~everything (false-positive storm) or never (dead)? Reflections flatlined while work continued? A scheduled task overdue past its cadence? A decision the cabinet keeps re-litigating (a rule isn't propagating)?

**Apply the CONFIDENCE FLOOR (the hard selector — `shared/interfaces/anomaly-ledger.md`).** A surprise graduates to a proposal ONLY if ALL hold: (1) it is a **measured** deviation, not a vibe; (2) it implies a falsifiable hypothesis ("X because Y — testable by Z") or a probable defect ("this looks broken: <evidence>"); (3) it is actionable. Modeled on the brain's `context_lib` min_score=0.4 — it can't spam.

- **Graduated** surprise → write it to `anomaly-ledger.md` `## Active` AND emit a proposal:
  ```bash
  source cabinet/scripts/meta-cognition/lib.sh
  mc_emit_proposal detect "<anomaly: what's off + the hypothesis/defect>" "<evidence (the measured numbers) + the one testable next step>"
  ```
- **Below-floor** surprise → a silent counter line under `anomaly-ledger.md` `## Counters` (recurrence across retros is itself a signal). Never pinged.

### Part 2: Opportunity Scan (NEW)

4. **Tool & feature scan:**
   - What new tools, APIs, or platform features launched this week?
   - Check: Claude Code changelog, Vercel updates, Neon features, ElevenLabs models, Linear updates
   - Would any of these improve our product or workflow?

5. **Competitive lateral scan:**
   - What are competitors doing that we should steal or avoid?
   - Any adjacent-space innovations we could adapt?
   - Cross-reference with CRO's latest briefs

6. **Workflow automation check:**
   - Is any Officer doing something manually that could be automated?
   - Are there repeated steps that should become a hook, script, or skill?

### Part 3: "How Could We Do This Smarter?" (NEW)

7. **Pick ONE process and challenge it:**
   - Choose one current process, workflow, or convention
   - Ask: "If we were starting fresh today, would we do it this way?"
   - Not everything — just one thing per retro. Focused kaizen.
   - Examples:
     - "Is the 5min poll loop the right cadence?"
     - "Should CRO briefs be shorter?"
     - "Is the experience record format too verbose?"
     - "Are we over-engineering the retro itself?"
   - If the answer is "yes, we'd do it the same" — record that and move on
   - If the answer is "no" — draft a proposal

7b. **Accretion-counter check → fire the principle-harvester if due (Layer 3 BACKSTOP → Layer 2 HARVEST).**
   The highest-value meta-work (collapse-to-principle) fires on **accretion**, not this clock — but the retro is the floor that catches a threshold crossed while no harvest ran. Check it:
   ```bash
   bash cabinet/scripts/meta-cognition/harvest-check.sh --status
   ```
   - If it prints `HARVEST DUE` → run the **principle-harvester** now (`memory/skills/evolved/principle-harvester.md`): fan out the 3 fresh-context finders (behavioral/governance/execution), red-team each collapse candidate, emit survivors as proposals, then `harvest-check.sh --mark`. This is the design's "Part 3 explicitly checks the harvester's accretion counters and fires Layer 2 if the threshold was crossed but the harvest hadn't run."
   - If it prints `no harvest` → nothing meaningful accreted; skip (do not fan out finders — that would be idea-spam).

7c. **Cross-pollination (the portfolio's unique advantage).**
   Scan for a pattern/fix/principle proven in ONE lane that should transfer to another (one product lane → another) — something the single-product cabinets structurally can't do. If you find one, emit it as a proposal:
   ```bash
   source cabinet/scripts/meta-cognition/lib.sh
   mc_emit_proposal backstop "Cross-pollinate: <pattern> from <lane A> to <lane B>" "<what worked in A + why it applies to B + the concrete transfer step>"
   ```
   One candidate per retro at most; skip if none is genuine.

### Part 4: Proposals & Recording (existing)

8. **Draft improvement proposals:**
   Write to Notion Cabinet Operations (Improvement Proposals DB). Each proposal must include:
   - What pattern/opportunity was identified
   - What change is proposed
   - How to validate the change
   - Rollback plan

9. **CRO research effectiveness review:**
   - Check `usage_status` on recent CRO briefs
   - What % were actioned vs declined?
   - Are there patterns in what gets used vs what doesn't?
   - Feed back to CRO: "more of X, less of Y"

9b. **Surface the meta-cognition proposal ledger into the briefing decision-queue (the ONE sink).**
    All four meta-cognition layers (Layer 1 encode-gate, Layer 2 harvest + detect, Layer 3 cross-pollination, counterfactual-replay) write proposal-only, per-item Captain-gated entries to `shared/interfaces/meta-cognition-proposals.md`. The retro is where they reach the Captain — the same "stale proposals auto-expire into the briefing" pattern as courses-of-action. Read the open entries:
    ```bash
    grep -A6 'status: open' shared/interfaces/meta-cognition-proposals.md
    ```
    **Red-team checkpoint (mandatory before any Layer-2 collapse reaches the Captain).** For each open `layer: harvest` (or any collapse) proposal, confirm a fresh-context review agent has attacked it (per `principle-harvester.md` step 3 / `engineering-development-loop`) — over-reach is the main risk. Drop or downgrade any that fails. (Layer-1 `prevent`, `detect`, `backstop`, and `counterfactual` entries already carry their own selector and don't need a second review unless they propose a collapse.)
    Fold each survivor into the briefing decision-queue as ONE line (with its `MC-id`), per-item gated (apply | edit | skip). On the Captain's decision, mark it resolved — never hand-edit `status:`:
    ```bash
    source cabinet/scripts/meta-cognition/lib.sh
    mc_resolve_proposal <MC-id> applied   # or: skipped | folded | decided
    ```

10. **Submit to Captain:**
    DM the Captain with a summary of proposals (process improvements + the meta-cognition ledger survivors from 9b). Wait for approval before promoting changes.

11. **Record:**
    - Write an experience record for the retro itself
    - Record the timestamp:
    ```bash
    redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" SET "cabinet:schedule:last-run:cos:retrospective" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    ```

### Part 5: Consolidation — distilled beliefs (terminal step, NEW)

12. **Distill the retro into durable cross-officer beliefs (grow by distillation, not accretion):**
    The retro reads dozens of records and reflections; without this step that reading
    evaporates when the session ends. Close every retro by emitting **3–5 distilled
    beliefs** — durable, transferable rules about how THIS cabinet coordinates ("X
    because Y"), not meeting minutes. At least ONE must be a **failure-pattern
    belief**: a cross-officer error pattern to AVOID, stated contrastively ("handing
    off X without Y fails — do Z instead"). Failure-patterns are the retro's unique
    yield — individual reflections see their own errors, only the retro sees the
    errors that live BETWEEN officers. Queue each through the memory seam:
    ```bash
    . "${CABINET_ROOT:-/opt/founders-cabinet}/cabinet/scripts/lib/memory.sh"
    BELIEF="$(cat <<'BELIEF_EOF'
    <ONE belief — the durable coordination rule + why, 1–3 sentences>
    BELIEF_EOF
    )"
    META=$(jq -nc --arg trust "reflection" --arg writer "cos" \
      --arg kind "failure-pattern" --arg via "cross-officer-retro" \
      '{trust: $trust, writer: $writer, kind: $kind, via: $via}')  # kind: success-pattern | failure-pattern
    memory_queue_embed "consolidated_belief" \
      "cb-cos-$(date -u +%Y-%m-%d)-<kebab-slug-naming-the-belief>" \
      "cos" "" "$BELIEF" "$META"
    ```
    Rules: belief text enters ONLY via the quoted heredoc (data, never command text —
    `memory_queue_embed` forwards it through `jq --arg`). `trust` is ALWAYS
    `reflection` — **NEVER `captain`**: a retro-distilled belief is the cabinet's own
    inference and must never masquerade as Captain law. Stable `source_id`
    (role+day+slug) makes re-emission an upsert, not a duplicate. Fewer than 3 real
    beliefs → emit only the real ones; padded beliefs poison recall.

13. **Boot-pack freshness tell (only when the captain-law digest is in use):**
    ```bash
    python3.12 "${CABINET_ROOT:-/opt/founders-cabinet}/cabinet/scripts/memory-distill.py" --check
    ```
    Read-only; exit 0 = fresh, 4 = not in use (skip silently), 3 = STALE — the
    boot-injected law index no longer matches the grown ledgers, so older law is
    going boot-invisible again. On stale: run the distiller's DEFAULT pass (writes
    `shared/interfaces/captain-law-digest.proposal.md` only) and hand the proposal
    to the Captain for review — promotion is `--apply` AFTER that review (standing
    handback; never self-ratify). Detection is this retro's job; scheduling any
    automatic regeneration stays a Captain decision. cabinet-doctor runs the same
    tell daily (WARN/AMBER) — this step is what ACTS on it.

## Expected Outcome

Cross-Officer coordination problems caught within 24h. Opportunities for improvement surfaced proactively. One process challenged per cycle. CRO research effectiveness tracked. The Cabinet gets measurably better — not just by fixing failures, but by finding better ways to work. Every retro terminates in 3–5 `consolidated_belief` rows (success- AND failure-patterns) in Cabinet Memory, so what the retro learned is recallable by every future session instead of buried in records.

## Known Pitfalls

- Reviewing records without looking for cross-Officer patterns — that's just individual reflection
- Skipping the opportunity scan because "nothing new happened" — something always changed
- Picking the same process to challenge every retro — rotate
- Over-engineering the "smarter" section — keep it to one focused question, not a redesign
- Proposing changes without validation scenarios
- Running the retro mechanically — if there are no patterns, say so and move on
- Ending the retro without Part 5 consolidation — an undistilled retro is accretion, not learning
- Distilling only what worked — the failure-pattern belief (what to avoid) is mandatory, not optional
- Stamping a distilled belief `trust: captain` — forbidden; retro inferences stay `trust: reflection`

## Validation Scenarios

- Scenario 1: Retro finds CTO is skipping Layer 1 reviews → proposes enforcement mechanism
- Scenario 2: Opportunity scan finds new Vercel feature → proposes adoption to CTO
- Scenario 3: "Smarter?" section challenges poll cadence → proposes 10min instead of 5min → validates token savings
- Scenario 4: CRO brief tracking shows 80% actioned rate → CRO doing well, no change needed
- Scenario 5: Clean retro with no failures → opportunity scan still produces one finding

## Origin

Foundation skill — evolved per Captain directive 2026-04-04. Added: Opportunity Scan (Part 2), "How Could We Do This Smarter?" (Part 3), CRO research effectiveness review (step 9).
2026-07-15 (memwave3 lane BC): Consolidation (Part 5) added — every retro terminates by
distilling 3–5 durable beliefs (incl. failure-patterns) into Cabinet Memory as
`consolidated_belief` / `trust: reflection` rows.
