# Durable Adaptive Role System: Research Report for Captain's Cabinet

**Date:** 2026-05-26
**Method:** Background general-purpose agent (Sonnet 4.6) with WebSearch / WebFetch
**Scope:** Multi-agent frameworks, organizational theory, durability patterns, mission compilation, OVI design, self-improvement loops, 24/7 resilience

---

## Executive Summary

The multi-agent landscape in 2026 is rich but fragmented: most frameworks treat roles as configuration bags (CrewAI, Swarm) rather than persistent organizational entities, and none fully solve durable identity, role lineage, eval-driven evolution, or mission-conferred authority. The Cabinet's architectural vision — roles as first-class persistent entities with charters, hats, lineage, eval history, and memory ownership — is architecturally ahead of what any off-the-shelf framework ships today. This report surveys the landscape, identifies the best-in-class patterns across each domain, and closes with a concrete reference architecture.

---

## A. Multi-Agent Framework Comparison

### Framework Role Models

| Framework | Role Model | Persistence | State | Long-lived Agents? |
|---|---|---|---|---|
| **AutoGen / MS Agent Framework** | Agent = class instance; GroupChat routes between them | Checkpointed (MS AF); in-memory only (AutoGen) | Session-scoped + checkpoint | Yes (AF has durable sessions) |
| **CrewAI** | Role + Goal + Backstory triplet; "members of a crew" | None across sessions | Within-session context | No |
| **LangGraph** | Graph nodes; agents are node functions | Checkpointing to any store (Redis, Postgres) | Reducer-driven shared state; rebuildable snapshots | Yes, with persistence layer |
| **MetaGPT** | SOPs encoded as roles; assembly line | None | In-memory per run | No |
| **OpenAI Swarm / Agents SDK** | Agent = instructions + tools; handoffs transfer control | None (Swarm); session log (Managed Agents) | Stateless per turn | No (Swarm); Yes (Managed Agents) |
| **Anthropic Agent SDK + Managed Agents** | Claude session + role injected via CLAUDE.md | Session ID resumable; event log in Managed Agents | JSONL on filesystem or hosted event log | Yes |
| **Devin / Manus** | Single persistent engineer / planner-executor-validator triad | Persistent codebase state; DeepWiki index | Stateful per project | Yes |

### Key Findings

**AutoGen / Microsoft Agent Framework (2025–2026)**: AutoGen started as a research prototype for GroupChat-style multi-agent conversations. Microsoft Agent Framework, released in 2025, is its production successor. It adds superstep-boundary checkpointing (automatic, no manual state management), distributed process execution, and middleware/telemetry. Roles are Python class instances with instructions and tools. State isolation is explicit between executor-local and shared state. Source: [Microsoft Agent Framework overview](https://learn.microsoft.com/en-us/agent-framework/overview/).

**CrewAI**: The most widely adopted framework (60% of Fortune 500, ~2 billion executions per year). Its agent model is a *Role–Goal–Backstory* triplet that shapes LLM behavior. There are Manager, Worker, and Researcher archetype roles. Processes are Sequential or Hierarchical. Critically, **there is no cross-session persistence** — state is in-memory per crew execution. Roles are configuration, not entities. Source: [CrewAI agent docs](https://docs.crewai.com/en/concepts/agents).

**LangGraph**: Graph nodes with typed, reducer-driven shared state. The checkpointing API serializes to any backend (Redis, Postgres, SQLite), enabling time-travel debugging and crash recovery. Human-in-the-loop pauses are a first-class feature. Roles are not explicit — they are patterns the developer imposes on nodes. LangGraph gives the best **execution substrate** but provides no native role model. Source: [LangGraph orchestration guide](https://latenode.com/blog/langgraph-ai-framework-2025-complete-architecture-guide-multi-agent-orchestration-analysis).

**MetaGPT**: Software-company simulation with fixed SOPs. Five roles (PM, Architect, Project Manager, Engineer, QA) follow a strictly ordered pipeline. The key insight is **SOP as the primary coordination mechanism** — roles encode process knowledge, not just capabilities. Addresses the cascading hallucination problem that plagues free-form multi-agent systems. Source: [MetaGPT paper (arXiv:2308.00352)](https://arxiv.org/pdf/2308.00352).

**OpenAI Swarm / Agents SDK**: Swarm distills agents to instructions + tools + handoffs. The handoff mechanism (returning an Agent object to transfer control while preserving conversation history) is clean and auditable. It deliberately trades opaque automation for clarity. The production Agents SDK (March 2025) added guardrails, tracing, and TypeScript support. Source: [VentureBeat: Swarm routines and handoffs](https://venturebeat.com/ai/openais-swarm-ai-agent-framework-routines-and-handoffs).

**Anthropic Agent SDK + Managed Agents**: The Agent SDK is what powers Claude Code today. Sessions are resumable via session ID; conversation history persists as JSONL. Managed Agents (April 2026) adds a hosted event log — a durable context object that survives connection drops and harness crashes, recoverable via `wake(sessionId)`. Subagents are first-class via the `Agent` tool. Hooks (PreToolUse, PostToolUse, SessionStart, SessionEnd) enable lifecycle enforcement. The Cabinet already runs on this substrate. **Note for Cabinet: Managed Agents requires an Anthropic API key; with OAuth-only access via Max x20 subscription, this pathway is unavailable. Stay on standard Claude Code sessions.** Sources: [Agent SDK docs](https://code.claude.com/docs/en/agent-sdk/overview), [Managed Agents guide](https://www.vibecodingacademy.ai/blog/claude-managed-agents-guide).

**Devin / Manus**: Both implement a Planner–Executor–Validator triad with persistent project-level state (DeepWiki codebase index for Devin; CodeAct paradigm for Manus where actions are Python scripts). The insight: **executable code as the universal action format** reduces ambiguity. The plan is injected into context as a structured artifact, not hidden in the model's working memory. Source: [Manus technical investigation (GitHub Gist)](https://gist.github.com/renschni/4fbc70b31bad8dd57f3370239dccd58f).

### Cabinet Recommendation on Frameworks

The Cabinet should continue on **Anthropic Agent SDK + standard Claude Code sessions** for officer execution. For mission execution DAGs, adopt **LangGraph-style checkpoint patterns** (implemented directly in Postgres/Redis, not LangGraph itself). Do not adopt CrewAI or MetaGPT — their role models are too shallow and their persistence story is absent.

---

## B. Organizational Theory Applied to AI Orgs

### Holacracy: The Closest Human Analog

Holacracy's core distinction — **roles are organizational entities, people fill them** — is the most applicable human org theory to the Cabinet. Key Holacracy mechanisms that translate directly:

- **Role as accountabilities + domain**: each role owns explicit accountabilities (what it must do) and a domain (what it has exclusive authority over). This maps directly to Cabinet officer charters.
- **Governance meetings**: structured process to create/update roles and policies. In the Cabinet this is the 24h evolution loop.
- **Circles**: roles nested in circles, with cross-linking (double-link) for coordination. Maps to officer groups owning work domains.
- **No title authority**: authority flows from the role's current accountabilities, not from seniority. Maps perfectly to mission-conferred authority.

A 2024 arXiv paper ([2408.11826](https://arxiv.org/html/2408.11826v1)) simulates LLM-based autonomous agents in a Holacratic structure and demonstrates that role-based authority assignment reduces inter-agent conflicts and increases task completion rate.

**DACI over RACI for the Cabinet**: DACI (Driver, Approver, Contributor, Informed) better models how the Cabinet makes decisions. The Captain is always the Approver on boundary-crossing decisions; the responsible officer is the Driver; other officers are Contributors. RACI is adequate for task-level work execution.

### Teal Organizations: Evolutionary Purpose + Self-Management

Laloux's Teal model ([Reinventing Organizations](https://en.wikipedia.org/wiki/Teal_organisation)) adds three principles that apply to the Cabinet:
- **Self-management**: roles self-organize around missions, no permanent hierarchy beyond the Captain.
- **Wholeness**: roles persist their full history, not just current state.
- **Evolutionary purpose**: the org has a mission that evolves as signals arrive.

The key Teal insight for AI orgs: **purpose evolves as the system learns, not just as humans decree**. The OVI and role evolution loops embody this.

### Mintzberg: The Cabinet is an Adhocracy

Among Mintzberg's five configurations (Simple Structure, Machine Bureaucracy, Professional Bureaucracy, Divisionalized Form, Adhocracy), the Cabinet most resembles an **Adhocracy** — highly organic, minimal formalization, teams assemble around projects, expertise drives coordination. The standing officer roster provides the stability layer; missions provide the dynamic task structure.

### Succession and Role Retirement in Human Orgs

Human organizations handle role succession through: documented handover notes, explicit knowledge transfer periods, successor identification before retirement, and archive preservation (history remains readable). All four of these should be Cabinet primitives: a `superseded_by` field in the role record, handover artifacts committed before retirement, the lineage DAG remaining queryable after retirement.

---

## C. Durability Patterns

### Event Sourcing as Organizational Truth

The single most important durability pattern for the Cabinet role system is **event sourcing**. Rather than storing current role state, store every governance event as an immutable append to a log:

```
role_created(role_id, charter, timestamp)
hat_added(role_id, hat_id, rationale, timestamp)
mission_assigned(role_id, mission_id, timestamp)
eval_recorded(role_id, scenario_id, score, findings, timestamp)
role_evolved(role_id, old_charter, new_charter, trigger, timestamp)
role_retired(role_id, reason, superseded_by, timestamp)
```

Roles are then **projections** over this event stream — queryable read models that can be rebuilt at any point. This gives:
- Full audit trail of role evolution
- Time-travel: what did this role look like on date X?
- Conflict resolution: event timestamps resolve concurrent writes
- Crash recovery: replay events to reconstruct current state

The CQRS separation (event store = write model; role snapshots = read model) maps cleanly to Postgres (append-only governance_events table) + Redis (hot read cache of current role state). Sources: [Mia-Platform: Event Sourcing and CQRS](https://mia-platform.eu/blog/understanding-event-sourcing-and-cqrs-pattern/), [DistributedSystemAuthority: CQRS](https://distributedsystemauthority.com/cqrs-and-event-sourcing).

### Role Lineage as a DAG

Lineage is richer than a chain — a role can be created from a merge of two predecessor roles, or split into two successors. Model it as a DAG:

```sql
role_lineage_edges(
  predecessor_id  UUID,
  successor_id    UUID,
  relationship    ENUM('split', 'merge', 'evolved', 'spawned'),
  rationale       TEXT,
  effective_at    TIMESTAMPTZ
)
```

This enables queries like "what is the full ancestral chain of the current CTO role?" and "which roles contributed memory to this one?"

### Temporal / Durable Execution for Missions

Temporal's event-history model maps directly onto mission lifecycle: every mission step is a durable event, activities are idempotent, failures retry automatically without losing progress. The "replay the workflow from the beginning but skip completed activities" pattern is exactly what mission execution needs. For Cabinet purposes, a lighter implementation in Postgres (mission step events + idempotent step functions) achieves the same durability without Temporal's operational overhead. Source: [Temporal durable execution](https://temporal.io/).

### Supervisor Trees for 24/7 Officers

Apply Erlang OTP's supervisor tree model to officer sessions:
- **one-for-one**: each officer session restarts independently on crash (default)
- **one-for-all**: CoS + any officer it depends on for current mission restart together
- **rest-for-one**: if the orchestrating officer crashes, downstream subagents it spawned also restart

The "let it crash" discipline — keeping fault-handling logic out of business logic — means officer code should never catch and suppress errors; let them surface to the supervisor. Recovery state is in Redis (heartbeat, last-run timestamps) and Postgres (session JSONL, mission step events). Source: [Zylos AI: Supervisor trees for AI agents](https://zylos.ai/research/2026-03-16-supervisor-trees-fault-tolerance-ai-agent-systems).

### Transactional Outbox for Cross-System Writes

When an officer writes to both Postgres and Notion (or Redis and Linear), use the **transactional outbox pattern**: write both the business update and the outbound event to Postgres in a single ACID transaction; a relay process publishes the event to the downstream system. This eliminates the dual-write failure mode where one write succeeds and the other fails. For the Cabinet: every time a mission step completes and needs to update both the internal task table and Notion, use an outbox table. Source: [AWS: Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).

---

## D. Mission Compilation Patterns

### Goal → Mission Graph Pipeline

The best-validated pattern in the research is a two-phase planner:

**Phase 1: Hierarchical Task Decomposition (HTN-inspired)**
The Captain's goal (natural language) enters a Planner agent that:
1. Extracts the stated goal + inferred WHY (5th loop intent inference)
2. Decomposes into ordered sub-goals using HTN-style method library
3. Resolves dependencies and produces a DAG of tasks with owners (roles) and verification criteria

The LLM-generated plan is then serialized as a structured artifact (not kept in working memory) — exactly Manus's approach of injecting the plan as a "Plan event" into context. Recent research shows LLM-generated HTN heuristics nearly match the coverage of the best symbolic HTN planners while reducing search effort by 83% on shared problems. Source: [HTN Planning with LLM-Generated Heuristics (arXiv:2605.07707)](https://arxiv.org/html/2605.07707v1).

**Phase 2: Plan-and-Act Execution (with ReAct loops per step)**
Each mission step is executed via a ReAct loop (Reason → Act → Observe → Repeat) within a single officer session. The Planner module produces a high-level sequence; the Executor translates each step into tool calls. The plan is a DAG; the execution is a step-by-step ReAct trace. Source: [Plan-and-Act: Improving Planning for Long-Horizon Tasks (arXiv:2503.09572)](https://arxiv.org/html/2503.09572v3).

**Stable artifacts at each compilation stage:**

| Stage | Artifact | Owner | Stored In |
|---|---|---|---|
| Goal | `captain_outcomes` row | Captain | Postgres |
| Compiled plan | `missions` row + `mission_steps` DAG | CoS / CPO | Postgres |
| Assigned work | `officer_tasks` rows with `mission_id` FK | Assigned officer | Postgres |
| Execution trace | Session JSONL + tool call log | Executing officer | Filesystem + Postgres |
| Verification | `mission_steps.verified_at` + evidence | Validator officer | Postgres |
| Learning | `experience_records` row | All officers | Postgres |

---

## E. Outcome Value Measurement

### Why OVI Needs Multiple Components

Goodhart's Law is the central risk: optimize a single metric and the system games it. The Cabinet's OVI must be a **multi-component composite** with orthogonal dimensions. Research on Goodhart mitigations identifies four failure modes (regressive, extremal, causal, adversarial) — multi-component metrics address all four by making it harder to optimize any single dimension without genuine value creation. Source: [Categorizing Variants of Goodhart's Law (arXiv:1803.04585)](https://arxiv.org/pdf/1803.04585).

### Recommended OVI Components for the Cabinet

| Dimension | Signal | Goodhart Risk | Mitigation |
|---|---|---|---|
| **Mission completion rate** | % missions reaching `verified` state | Gaming easy verification | Human spot-check sample |
| **Time-to-verified** | Hours from assignment to verified | Rushing without quality | Paired with defect rate |
| **Captain satisfaction** | Explicit rating + implicit (re-open rate) | Optimizing for approval | Also track re-open rate |
| **Proactive value** | Unsolicited improvements Captain accepts | Over-generating noise | Acceptance rate, not volume |
| **Eval scenario pass rate** | % of scenario evals passing per role | Teaching to the test | Rotate evals, use held-out set |
| **Coverage** | % of Captain's outcomes with active missions | Cherry-picking easy work | Weighted by outcome priority |

North Star: "Fraction of the Captain's outcomes progressing at AI speed without Captain intervention." This is measurable, causal, and hard to game without genuine performance.

---

## F. Self-Improvement Loops

### Three Research Foundations

**Reflexion (Shinn et al., NeurIPS 2023)**: Agents verbally reflect on task feedback signals and maintain reflective text in an episodic memory buffer. Key result: +22% improvement over baseline in sequential decision-making within 12 iterations; 91% pass@1 on HumanEval (vs GPT-4's 80%). The mechanism: failures generate linguistic self-evaluation that is prepended to the next attempt's context. The Cabinet's per-task experience records implement Reflexion — the key upgrade is to make reflection **structured** (lesson type, trigger signal, scope) and queryable. Source: [arXiv:2303.11366](https://arxiv.org/abs/2303.11366).

**Voyager (Wang et al., NeurIPS 2023)**: Lifelong learning via an ever-growing skill library of executable code. Three components: automatic curriculum (maximizes exploration), skill library (stores and retrieves complex behaviors), iterative prompting (incorporates environment feedback + self-verification). Results: 3.3x more unique items acquired, 15.3x faster tech tree progression vs. prior SOTA. The Cabinet's `memory/skills/` directory is a manual Voyager skill library — the upgrade is automatic skill induction from experience records, with validation before promotion. Source: [arXiv:2305.16291](https://arxiv.org/abs/2305.16291).

**Generative Agents (Park et al., UIST 2023)**: Memory stream → reflection → planning architecture. The reflection module synthesizes higher-level inferences from raw memory, enabling agents to "draw conclusions about itself and others." The Cabinet's reflection loop is inspired by this; the upgrade is making reflections queryable (pgvector) so past reflections inform future ones. Source: [arXiv:2304.03442](https://arxiv.org/abs/2304.03442).

### Eval-Driven Role Evolution

The self-improvement loop that is most critical and most absent in the current Cabinet is **closed-loop eval-driven role definition changes**:

1. Scenario evals (golden evals in `memory/golden-evals/`) are run against each officer session.
2. Eval failures annotated with failure type (missing skill, wrong authority, scope confusion, quality gap).
3. Failure pattern detection: same failure type 3+ times in N sessions → flag for role evolution.
4. Proposed role change is drafted, reviewed by a fresh-context agent (Voyager-style validation), and presented to Captain for approval.
5. Approved change is applied as a `role_evolved` governance event.

The key constraint to prevent runaway drift: **evals must be human-authored or cryptographically signed** (a held-out set the system cannot read during training). Rotate 20% of the eval set quarterly. Never let the system generate its own evals without human review.

---

## G. Resilience Patterns for 24/7 Runtime

### Layered Health Model

Classify all officer dependencies into three tiers:

| Tier | Examples | Failure Response |
|---|---|---|
| **Critical** | Anthropic API, Postgres | Fail fast, page supervisor, enter pause state |
| **Important** | Redis, Notion, Linear | Cache locally, queue writes, drain on recovery |
| **Optional** | Analytics, webhook delivery | Ignore failure, log for later review |

### Key Patterns to Implement

**Heartbeat + Dead-Man's Switch**: Every officer writes a heartbeat to Redis with a 15-minute TTL. The CoS officer monitors heartbeat absence and restarts dead officers via `start-officer.sh`. Current implementation exists; formalize the monitoring circuit.

**Idempotent Operations**: Every officer action that writes external state must be idempotent — safe to replay after a crash. Use idempotency keys (mission_step_id + attempt_number) on all external writes. The transactional outbox enforces this.

**Circuit Breakers on LLM API**: Wrap all Anthropic API calls in a circuit breaker with exponential backoff + jitter. After 3 consecutive failures in 60 seconds, open the circuit for 5 minutes before retry. This prevents the cascade where one degraded officer hammers the API and affects the whole fleet.

**Graceful Session Handoff**: Before a session ends (compact, timeout, restart), commit: (a) current mission step state, (b) any pending outbox events, (c) updated tier2 working notes. The next session reads these and resumes without briefing from the Captain. This is the **officer-session contract** (see design question 7).

---

## Design Question Answers

### 1. Role Data Model

A role is an organizational entity, not a session configuration. Recommended fields:

```sql
-- Core entity
roles (
  id              UUID PRIMARY KEY,
  slug            TEXT UNIQUE,          -- e.g., 'cto', 'cos'
  display_name    TEXT,
  charter         JSONB,                -- {mission, scope, success_criteria, authority_boundaries}
  created_at      TIMESTAMPTZ,
  retired_at      TIMESTAMPTZ,
  retired_reason  TEXT,
  superseded_by   UUID REFERENCES roles(id)
)

-- Hats: capability bags, not inheritance
role_hats (
  id              UUID PRIMARY KEY,
  role_id         UUID REFERENCES roles(id),
  hat_slug        TEXT,                 -- e.g., 'code-review', 'architecture', 'bugfix'
  description     TEXT,
  context_trigger TEXT,                 -- when does this hat activate?
  tools_granted   TEXT[],               -- additional tools this hat unlocks
  active          BOOLEAN DEFAULT TRUE
)

-- Lineage DAG
role_lineage_edges (
  predecessor_id  UUID REFERENCES roles(id),
  successor_id    UUID REFERENCES roles(id),
  relationship    TEXT,                 -- 'evolved'|'split'|'merge'|'spawned'
  rationale       TEXT,
  effective_at    TIMESTAMPTZ
)

-- Eval history
role_evals (
  id              UUID PRIMARY KEY,
  role_id         UUID REFERENCES roles(id),
  scenario_id     TEXT,
  session_id      TEXT,
  score           NUMERIC(3,2),         -- 0.00-1.00
  passed          BOOLEAN,
  findings        JSONB,                -- {failure_type, description, evidence}
  evaluated_at    TIMESTAMPTZ
)

-- Memory ownership
role_memory_artifacts (
  id              UUID PRIMARY KEY,
  role_id         UUID REFERENCES roles(id),
  artifact_path   TEXT,                 -- e.g., 'shared/interfaces/captain-decisions.md'
  artifact_type   TEXT,                 -- 'spec'|'brief'|'decision_log'|'runbook'
  write_access    UUID[],               -- other role IDs that may write
  owned_since     TIMESTAMPTZ
)

-- Governance event log (event sourcing)
governance_events (
  id              UUID PRIMARY KEY,
  event_type      TEXT,                 -- 'role_created'|'hat_added'|'eval_recorded'|...
  role_id         UUID REFERENCES roles(id),
  payload         JSONB,
  actor           TEXT,                 -- 'captain'|'cos'|'evolution-loop'
  timestamp       TIMESTAMPTZ DEFAULT NOW()
)
```

**Hats are modeled as a capability bag** (composition, not inheritance). A hat grants additional tools and activates when a specific context trigger is met (e.g., the CTO's "production-bugfix" hat activates when a Sev1 alert fires). This is more flexible than inheritance and avoids the diamond problem.

**Lineage is a DAG** because merges create multiple-predecessor edges. A simple chain (superseded_by FK) cannot represent a merge. The DAG traversal answers: "what is the complete provenance of this role's charter?"

### 2. Mission Lifecycle

Goal arrives → **Captain** creates `captain_outcomes` row with outcome text, success criteria, priority.

Compile → **CoS/CPO** spawns a Planner session that: (a) runs the 5th-loop WHY scan, (b) decomposes into task DAG using HTN-style method library, (c) writes `missions` row + `mission_steps` DAG to Postgres, (d) flags any Captain decisions needed.

Assign → **CoS** matches each mission step to the role with the best-fit hat, writes `officer_tasks` rows with `mission_id` FK.

Execute → **Assigned officer** runs ReAct loop per step, writes execution trace to session JSONL, marks steps complete via outbox.

Verify → **Validator officer** (role with `validates_deployments` or `reviews_implementations` capability) checks step outputs against success criteria, marks `verified_at`.

Learn → **All involved officers** write experience records; CoS extracts patterns in 24h retro.

### 3. Authority

**Two types:**
- **Standing authority**: derived from role charter. The CTO has standing authority over all architectural decisions and production deploys. This is defined in `charter.authority_boundaries` and evaluated before any officer action via pre-tool-use hook.
- **Mission-conferred authority**: a specific mission grants temporary elevated authority. The CTO role, assigned a mission to migrate the database, has elevated authority to run migrations that it would not normally have for routine sessions. This authority expires when the mission closes.

**Least-privilege enforcement**: The pre-tool-use hook checks whether the current action falls within (a) standing authority from the role charter OR (b) mission-conferred authority from any active mission assigned to this session. Actions outside both are blocked and escalated. This directly mirrors the OWASP Agentic Top 10 recommendations and the Aethelgard framework's dynamic capability scoping. Sources: [Agent Authority Least Privilege Framework (FINOS)](https://air-governance-framework.finos.org/mitigations/mi-18_agent-authority-least-privilege-framework.html), [Beyond Static Sandboxing (arXiv:2604.11839)](https://arxiv.org/abs/2604.11839).

### 4. Memory Ownership

**Role-owned, with explicit write grants.** Each memory artifact has a primary owner role and an optional list of roles with write access. Conflicting writes are resolved by: (a) the owning role's write always wins if the owning role is active, (b) if the owning role is inactive, the CoS arbitrates, (c) all writes are governance events (append-only log resolves disputes via timestamp).

Documents like `captain-decisions.md` have ownership semantics: the CoS owns it (primary write), but any officer with `logs_captain_decisions` capability has write access (append only). This is analogous to Git ownership — the owner can merge/revert; contributors can submit.

### 5. Role Evolution Triggers

| Signal | Action | Who Decides |
|---|---|---|
| OVI < threshold for 3 consecutive cycles | Trigger reflection + draft evolution proposal | Evolution loop → Captain approval |
| Eval failure rate > 30% on scenario category | Draft targeted charter amendment | CoS proposes → Captain approves |
| 90th-percentile context usage > 80% consistently | Consider splitting role (reducing scope) | CoS proposes → Captain approves |
| Zero missions assigned in 30 days | Flag as candidate for retirement or merge | CoS presents → Captain decides |
| New mission type with no current role fit | Propose new role creation | CoS proposes → Captain approves |
| Captain explicit directive | Apply immediately | Captain authority |

The signals are all observable from existing data (Redis cost counters, eval history, mission assignment table). The evolution loop queries these on its 24h cadence.

### 6. Eval-Driven Evolution (Closed Loop)

The closed-loop design to prevent runaway drift:

1. **Human-authored, held-out eval set**: The Captain (or a human reviewer) authors scenario evals. The system never generates its own evals without review.
2. **Eval rotation**: 20% of evals are replaced each quarter with new scenarios. The system cannot "teach to the test" on a static set.
3. **Failure pattern detection**: Three failures of the same type trigger a proposal, not an automatic change. The proposal is a concrete charter amendment diff, not a free-form suggestion.
4. **Review gate**: A fresh-context Sonnet agent reviews the proposal for consistency with the constitution and safety boundaries before it reaches the Captain.
5. **Captain approval**: All charter changes require explicit Captain approval. The approval is a governance event, not a config file edit.
6. **Post-change re-eval**: The first 5 missions after a charter change use the full eval set, not just the held-out portion, to verify the change had the intended effect.

### 7. Officer-Session Contract

**On session start, the officer inherits from its role:**
- Role charter (mission, scope, authority boundaries)
- Active hat(s) relevant to current context
- Tier-2 working notes (instance memory)
- Active mission assignments (from `officer_tasks`)
- Pending triggers (from Redis stream)
- Latest `captain-patterns.md` and `captain-intents.md`

**On session end, the officer commits back:**
- Updated tier-2 working notes (any new knowledge)
- Mission step completions (to `mission_steps` table via outbox)
- Experience record (if significant work was done)
- Pending outbox events (flushed before termination)
- Heartbeat cleared (allows supervisor to detect clean exit vs crash)

The session is an **ephemeral execution surface** — it reads role state at start and writes execution artifacts at end. Everything in between is in the Claude context window + session JSONL. If the session crashes mid-execution, the supervisor starts a new session; the new session reads the last committed mission step state and resumes from there.

### 8. Captain Interface

The minimum UX for the Captain's authority surface:

**`set_outcome(text, priority, success_criteria)`**: Captain states what they want accomplished. The system handles decomposition. The Captain does not write tasks, assign officers, or specify process.

**`set_boundary(type, rule, scope)`**: Captain adds a constraint. Types: `never_do`, `always_require_approval`, `budget_limit`, `timeline_constraint`. Boundaries are stored in the role charter and enforced by the pre-tool-use hook.

**`review_dashboard()`**: Captain sees: (a) active missions with status, (b) OVI trend (last 7 days), (c) pending decisions/approvals (DACI Driver/Approver queue), (d) overdue founder-action items, (e) recent role evolution proposals awaiting approval.

**Implicit signals**: The 4th loop (captain-patterns.md) and 5th loop (captain-intents.md) capture everything the Captain expresses implicitly. The Captain does not need to manage the org — the Cabinet extracts preferences from normal conversation.

---

## Reference Architecture: Durable Adaptive Roles

### Data Model Summary

```
captain_outcomes (id, text, priority, success_criteria, created_at, closed_at)
    ↓ compiled into
missions (id, outcome_id, plan_dag JSONB, status, compiled_at, verified_at)
    ↓ decomposed into
mission_steps (id, mission_id, step_order, description, assigned_role_id,
               depends_on UUID[], status, started_at, completed_at, verified_at, evidence JSONB)
    ↓ assigned to
officer_tasks (id, role_id, session_id, mission_step_id, status, created_at, completed_at)
    ↓ executed by
roles (id, slug, display_name, charter JSONB, created_at, retired_at, superseded_by)
    ↕ composed of
role_hats (id, role_id, hat_slug, context_trigger, tools_granted[], active)
    ↕ linked by
role_lineage_edges (predecessor_id, successor_id, relationship, rationale, effective_at)
    ↕ evaluated by
role_evals (id, role_id, scenario_id, score, passed, findings JSONB, evaluated_at)
    ↕ owning
role_memory_artifacts (id, role_id, artifact_path, artifact_type, write_access UUID[])
    ↕ all changes captured in
governance_events (id, event_type, role_id, payload JSONB, actor, timestamp)
```

### Lifecycle Diagram (text representation)

```
CAPTAIN
  │ set_outcome()
  ▼
captain_outcomes
  │ CoS/CPO compile
  ▼
missions + mission_steps (DAG)
  │ CoS assign
  ▼
officer_tasks → [officer session starts]
                      │ inherits role charter + hats + tier2 memory
                      │ executes ReAct loop
                      │ writes outbox events (idempotent)
                      │
              [session ends / crashes]
                      │
              supervisor restarts if crashed
                      │ resumes from last committed mission_step
                      │
              mission_steps.verified_at set by validator
                      │
              experience_record written
                      ▼
              evolution_loop (24h) reads:
                - eval scores
                - OVI components
                - experience records
                      │
              if signals → draft role charter amendment
                      │
              Captain approves → governance_event('role_evolved')
                      │
              roles projection updated
```

---

## Priority Recommendations for the Cabinet

These are the five highest-leverage changes, ranked:

**1. Formalize the role as a Postgres entity (not just a file).** The `roles`, `role_hats`, `role_lineage_edges`, and `governance_events` tables transform role management from "editing .md files" to a queryable, auditable, event-sourced system. This is the architectural foundation everything else builds on. Estimated effort: 1–2 days.

**2. Implement the transactional outbox for cross-system writes.** Eliminates the class of bugs where a mission step is marked complete internally but the external system (Notion, Linear) was not updated. Estimated effort: 1 day.

**3. Formalize the officer-session contract as explicit commit/restore operations.** The `start-officer.sh` and `post-compact.sh` hooks already do parts of this; make it explicit and complete (mission step state, outbox flush, working notes update). Estimated effort: 0.5 days.

**4. Stand up the eval infrastructure.** Start with 10 scenario evals per officer, human-authored by the Captain. Run them on a weekly cron; feed scores into `role_evals`. The evolution loop can then use data rather than heuristics. Estimated effort: 2–3 days to author evals + 1 day for infrastructure.

**5. Implement capability-governed authority (pre-tool-use hat/charter check).** The pre-tool-use hook already has a kill switch and spend limit check; extend it to check actions against role charter + active mission authority. This closes the principle-of-least-privilege gap. Estimated effort: 1 day.

---

## Sources

- [Microsoft Agent Framework overview (Microsoft Learn)](https://learn.microsoft.com/en-us/agent-framework/overview/)
- [AutoGen vs Microsoft Agent Framework (createaiagent.net)](https://createaiagent.net/autogen-vs-microsoft-agent-framework/)
- [CrewAI agent documentation](https://docs.crewai.com/en/concepts/agents)
- [CrewAI GitHub](https://github.com/crewaiinc/crewai)
- [LangGraph 2025 architecture guide (Latenode)](https://latenode.com/blog/langgraph-ai-framework-2025-complete-architecture-guide-multi-agent-orchestration-analysis)
- [MetaGPT paper (arXiv:2308.00352)](https://arxiv.org/pdf/2308.00352)
- [MetaGPT docs (DeepWisdom)](https://docs.deepwisdom.ai/main/en/guide/get_started/introduction.html)
- [OpenAI Swarm: Routines and Handoffs (VentureBeat)](https://venturebeat.com/ai/openais-swarm-ai-agent-framework-routines-and-handoffs)
- [Claude Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)
- [Claude Managed Agents guide](https://www.vibecodingacademy.ai/blog/claude-managed-agents-guide)
- [Anthropic engineering: Building agents with the Agent SDK](https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk)
- [Devin AI guide 2026 (Singularity Moments)](https://singularitymoments.com/devin-ai-coding-agent-guide/)
- [Manus AI architecture (arXiv:2505.02024)](https://arxiv.org/html/2505.02024v1)
- [Manus technical investigation (GitHub Gist)](https://gist.github.com/renschni/4fbc70b31bad8dd57f3370239dccd58f)
- [Holacracy Wikipedia](https://en.wikipedia.org/wiki/Holacracy)
- [Generative AI Holacracy simulation (arXiv:2408.11826)](https://arxiv.org/html/2408.11826v1)
- [Teal organisation Wikipedia](https://en.wikipedia.org/wiki/Teal_organisation)
- [DACI framework (Atlassian)](https://www.atlassian.com/team-playbook/plays/daci)
- [Event Sourcing and CQRS (Mia-Platform)](https://mia-platform.eu/blog/understanding-event-sourcing-and-cqrs-pattern/)
- [CQRS in distributed systems (DistributedSystemAuthority)](https://distributedsystemauthority.com/cqrs-and-event-sourcing)
- [Supervisor trees for AI agent systems (Zylos AI)](https://zylos.ai/research/2026-03-16-supervisor-trees-fault-tolerance-ai-agent-systems)
- [Transactional outbox pattern (AWS)](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
- [Temporal durable execution](https://temporal.io/)
- [HTN Planning with LLM heuristics (arXiv:2605.07707)](https://arxiv.org/html/2605.07707v1)
- [Plan-and-Act framework (arXiv:2503.09572)](https://arxiv.org/html/2503.09572v3)
- [Reflexion paper (arXiv:2303.11366)](https://arxiv.org/abs/2303.11366)
- [Voyager paper (arXiv:2305.16291)](https://arxiv.org/abs/2305.16291)
- [Generative Agents paper (arXiv:2304.03442)](https://arxiv.org/abs/2304.03442)
- [Goodhart's Law categorization (arXiv:1803.04585)](https://arxiv.org/pdf/1803.04585)
- [Agent Authority Least Privilege Framework (FINOS)](https://air-governance-framework.finos.org/mitigations/mi-18_agent-authority-least-privilege-framework.html)
- [Beyond Static Sandboxing (arXiv:2604.11839)](https://arxiv.org/abs/2604.11839)
- [OWASP Agentic Top 10 guide](https://1337skills.com/blog/2026-04-04-securing-autonomous-ai-agents-owasp-agentic-top-10-governance-toolkit/)
- [Langfuse agent evaluation](https://langfuse.com/guides/cookbook/example_pydantic_ai_mcp_agent_evaluation)
