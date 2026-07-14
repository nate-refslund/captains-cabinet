# Self-Improving Cabinet — Meta-Cognition Direction (2026-06-25)

Captain asked: how can the cabinet become more creative and generate meta-level insights *itself* — like the "principles over specifics" observation — instead of relying on the Captain to spot them? Three unbiased subagents brainstormed independently (reverse-engineer the Captain's move / the mechanisms of machine creativity / where it should live). **Proposal only — Captain's call on what to build.**

## The headline — all three lenses converged
The cabinet has rich loops for **executing** and **recording**, but **zero loop that abstracts upward**. Every loop runs at the altitude of the work: reflection reviews records, the retro reviews handoffs, the encoder writes the Captain's words down at the exact specificity he said them. **Nothing ever asks "is this a specific instance of something bigger?"** That single missing operator is why the cabinet had all the evidence for "principles over specifics" (17 patterns, a stale index, duplicated charset maps) and never connected the dots — the Captain did.

- **Lens 1** named the move: `generalize-the-instance` (+ notice-the-recurrence, question-the-mechanism, seek-the-better-alternative, trace-the-second-order-effect). Top pick: wire it into the **encode chokepoint**.
- **Lens 2** independently landed on the same move (`five-whys-upward`) as its #2, and added a complement as its #1: **anomaly-seeking on the cabinet's own telemetry** — "what in our logs violates what I'd predict?" — which *would have autonomously surfaced this session's stale-index bug*.
- **Lens 3** adjudicated *where*: a **layered combination**, because the highest-value meta-work fires on **accretion** (a content signal), not on the retro's clock.

## Why the cabinet waits for the Captain (the diagnosis)
Three structural absences: (1) no upward-abstraction step anywhere; (2) no recurrence memory across instances (it counts an officer's own execution failures, never meta-recurrences like "the 10th time" or "a rule keeps getting forgotten"); (3) the loops are reactive + same-altitude by design — they fire *after* work, on records that already exist, never *proactively to abstract*. The abstraction muscle already exists in the org (it's what review agents do) — it's just never pointed at the cabinet's own rules.

## Recommended direction — a layered combination, fastest-signal-first, ONE sink
Mirrors the architecture the cabinet already uses for *Captain-signal* meta-cognition (inline 4th/5th loops → ledgers → CoS audits in the retro). Apply the same shape to *system* meta-cognition. Each layer fires on a **distinct signal**, all emit **proposal-only, per-item Captain-gated** entries into the **one** existing briefing decision queue, and **none adds an always-loaded loop** (honoring the audit's own G-1 finding).

### Layer 1 — PREVENT (encode-time, inline, cheap, net-negative tokens)
The anti-accretion gate. When any officer is about to write a new pattern/rule/skill, one beat: *"Does an existing principle already cover this? Should this be written as a principle, not a case?"* If yes → generalize instead of adding row N+1. This stops accretion **at the source** — the single highest-leverage insertion, because it prevents the debt the harvester later pays down. Would have caught the colleague-a cluster (audit B-1) at encode-time instead of weeks later. Lives as **one line in `holistic-thinking.md`** (already every officer's L3 duty) + the encode step of the pattern/intent skills — **zero new CLAUDE.md prose.**

### Layer 2 — HARVEST + DETECT (accretion-triggered, deep, the engine)
Two complementary engines, CoS-owned, **triggered by content signals not a clock**:
- **Principle-harvester** — what this session's audit did by hand, made standing. When the patterns ledger / CLAUDE.md / rules set grows past a threshold since the last harvest, CoS fans out fresh-context finders (the audit used three: behavioral / governance / execution) to mine specifics for collapse-to-principle. Guarded by a hard **LEAVE-AS-IS allow-list** (safety-boundaries, authority-matrix, NATE_EMAILS, board/model IDs, SECRET_PATTERNS) so it never collapses genuine facts. Proposal-only, per-item gated.
- **Anomaly-seeking on own telemetry** — folds into the 48h retro's first phase. Reads the already-emitted streams (org_events, logs, reflection/cost counters, decisions) and asks "what violates what I'd predict?" Grounded in *measured* prediction-error, with a confidence floor (like the brain's `context_lib` min_score=0.4) so it can't spam. This is the "the cabinet notices what's off about itself" capability.
Both live as **trigger-loaded evolved skills**, not in always-loaded context.

### Layer 3 — BACKSTOP (the retro, as-is + one tweak) — the Captain's idea, placed right
The Captain's retro-idea is **~60% already built**: `cross-officer-retro.md` already has Part 2 (Opportunity Scan) + Part 3 ("How could we do this smarter?" kaizen). Keep the retro as the **periodic synthesis floor** — catch un-triggered Layer-1/2 candidates, run one focused kaizen, fold stale proposals into the briefing (the same "stale proposals auto-expire into the briefing" pattern as courses-of-action). One change: Part 3 explicitly **checks the harvester's accretion counters** and fires Layer 2 if the threshold was crossed but the harvest hadn't run. Plus opportunistic: **cross-pollination** (PolAds→STEPhie pattern transfer — the portfolio's unique advantage) rides here.

### Cross-cutting rules
- **Every generator is paired with a hard selector** (confidence floor / recurrence gate / evidence requirement / fresh-context judge). Creativity here is *generate-many-then-ruthlessly-cull*, never generate-and-surface. Idea-spam is **negative value** — it taxes the scarcest resources (Captain attention + Opus quota).
- **Devil's-advocate as a checkpoint, not a role:** require the existing fresh-context review agent on any Layer-2 collapse proposal (over-reach is the main risk). Reuse `engineering-development-loop` — no new officer.
- **Counterfactual-replay** (trivial reflection upgrade: "what one change would've made this 10x better?" → 3×-recurrence escalates to a capability-gap) is worth adopting alongside, near-zero cost.

## Where the Captain's retro-idea is right / where an alternative beats it
- **RIGHT:** a *periodic* pass is the correct home for the **synthesis/backstop** role, and "review without improve is incomplete" is sound — but the retro *already* improves + ideates, so the gap isn't there.
- **BEATEN:** the highest-value meta-work (collapse-to-principle) should fire on **accretion**, not 48h/5-reflections — the two are uncorrelated, so a clock-coupled retro either misses the moment debt crosses the threshold or wastes a pass when nothing accreted. And the **cheapest** win is **encode-time prevention** (Layer 1), which a periodic loop structurally can't deliver (by retro-time the specific is already written and rotting). Periodic-deep and inline-cheap are *different instruments*.

## Hard prerequisite (do first, or it's all inert)
**Repair `captain-rules-index.yaml` + its freshness hook** (audit BUG #1) — it indexes 48 dead anchors and **zero** of the 17 live patterns, so officers' trigger-word lookup silently misses every encoded pattern *and* would miss every harvested principle. No meta-cognition home produces value until propagation is fixed. **(Already in progress — the audit's behavioral subagent is regenerating it now.)**

## Recommended build sequence
1. **Fix the index** (the prerequisite — in flight).
2. **Layer 1** (encode-time gate) — cheapest, highest-leverage, net-negative tokens, one line in an existing skill.
3. **Layer 2 harvester** — the deep engine; the audit proved it works (run once by hand).
4. **Anomaly-seeking + retro tweak (Layer 3)** + counterfactual-replay — fold into the existing retro/reflection.
5. Red-team checkpoint + cross-pollination — opportunistic.

Net effect: the cabinet keeps its rule-base **lean and principled going in** (Layer 1), **catches what's surprising or broken once running** (Layer 2 anomaly), and **harvests accreted debt into principles** (Layer 2 harvester) — all feeding one Captain-gated queue, all paying for themselves in the currency the Captain cares about: outcome per unit of Captain attention.
