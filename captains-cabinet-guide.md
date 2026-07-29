# Captain's Cabinet — The Guide

*The operating doctrine for autonomous AI organizations that ship, learn, and evolve.*

**By Nathaniel Refslund**
**Version 2.0 — July 2026**

---

## Purpose of This Guide

Captain's Cabinet is a framework for organizing autonomous AI agents into a self-improving workforce that operates continuously under human direction. This guide is the doctrine: the principles the machine is built on, and how its parts fit together — for a Captain running one.

It is written to be durable. It states principles and points at the artifacts that implement them (`framework/`, `docs/plans/`, `instance/config/`); it avoids file-level detail that rots. One convention throughout: where the live estate has not yet caught up to doctrine, the item is marked *(target state — migration per `docs/plans/`)*. The plans' `EXECUTION-STATUS.md` is always the truth of what runs today. Doctrine leads; wiring follows; the gap is tracked, never hidden.

## Definition

A **Captain's Cabinet** is a continuously running organization of AI agents that builds, ships, and operates the Captain's work — a product, a practice, an operation — under the strategic direction of the human Captain. It operates autonomously within enforced boundaries, earns wider autonomy through recorded evidence, compounds institutional knowledge, and improves its own processes through a gate it cannot edit.

The Cabinet is not a chatbot. It is not a pipeline. It is not a script. It is an organization — with roles, memory, judgment, and the capacity to reorganize itself. The operator running it is its **Captain**. The agents are its **Officers** and **Crew**.

**Officers** are the domain owners: persistent Claude Code sessions, each with a defined area of responsibility and the authority to decide within it. **Crew** are ephemeral execution agents spawned by Officers for specific work, dissolving when it is done. Officers set direction within their domain; Crew do the work; permissions flow downward, never upward.

Two flavors of Cabinet exist on the same framework. **Flavor A** is the personal clone org: it senses the Captain's world (screen, messages, meetings, a personal knowledge vault) and acts as their clone, with human verdicts as its only honest ground truth. **Flavor B** is the standalone product org on a dedicated Mac Mini: it owns one software product end-to-end and feeds primarily on machine-checkable truth — CI verdicts, deploy states, error budgets, support resolutions. Everything in this guide applies to both unless a flavor is named.

---

## 1. Philosophy

### The operator becomes the Captain

In a traditional organization the operator does the work, delegates the work, or manages the people who do it. In a Cabinet the operator does none of these. They set direction, make the decisions that genuinely require human judgment, and review outcomes. The Cabinet determines *how*; the Captain determines *what matters and why*.

This is not a delegation framework. Delegation implies the Captain knows how the work should be done and instructs others to do it. Officers determine execution within their domains. The Captain's scarcest resource is not time — it is judgment, and the whole machine is engineered to spend it precisely.

### Leader-leader, not leader-follower

The Cabinet's command model is Marquet's leader-leader: don't move information to authority — move authority to the information. But moving authority safely requires two preconditions Marquet named and this framework mechanizes: **competence** and **clarity**.

- **Clarity** is supplied by the intent hierarchy (§2): Captain-authored directions, ratified outcomes, a constitution loaded into every session. Officers act on "I intend to…" proposals, not on awaiting orders.
- **Competence** is not asserted — it is *measured*. The evidence engine (§3) watches every action class, and trust runs demotion-first (the earn-demotion ruling, 2026-07-03): reversible classes are trusted from day one — act with undo, journaled, reported after — and that trust is *lost* on evidence (undo rates, explicit vetoes, failed verifications demote a cell to propose-only instantly). Nothing is pre-earned rung by rung; nothing decays silently either.

The result is intent-based execution with mechanical, evidence-based demotion underneath it — and hard ceilings above it. Outbound comms, production deploys, spend, and secrets stay Captain-gated at any confidence, forever: nobody — not an officer with a persuasive argument, not a graduated cell with a spotless record — talks the machine out of a ceiling.

### Outcome per unit of Captain attention

The north star metric is **verified outcomes per Captain-minute**. Not tasks completed, not messages sent, not ceremony performed — ledger-verified outcomes, divided by the human attention consumed producing them. Every design choice bends toward this ratio: machine probes answer what machines can check so the Captain answers only what they cannot; proposals batch into briefings instead of fragmenting attention; one card carries a whole course of action instead of five pings carrying five steps. When in doubt between more process and less Captain attention, choose less attention.

### Asymmetric autonomy is correct

Machine-verifiable action classes (CI-gated commits, preview deploys, board moves) graduate in weeks at product-traffic volume. Judgment classes (external comms tone, prioritization, compliance wording) stay Captain-gated for months — possibly forever on a compliance product. This asymmetry is the evidence engine *working*. The failure mode to watch is never "judgment lanes still gated" — it is a machine-verifiable lane still unmeasured, which means a probe or a join is broken. Never equalize the two by weakening a gate.

### Built = scheduled + fed + watched

The estate's most instructive historical failure: sophisticated machinery built, tested — and never scheduled, never fed, never watched. Nothing noticed, because process-health is not outcome-health. Doctrine, therefore: **a component does not exist until it is scheduled (a manifest-registered job), fed (its inputs asserted fresh and non-empty), and watched (a liveness/throughput expectation registered with a watchdog that pages on starvation).** Code-written-only is not done. Every consumer of data asserts its inputs are fresh before trusting them, and hard-fails loudly otherwise.

### The Twelve Principles

These survive any implementation churn — the org's constitution-of-constitutions. Violations are defects, not style choices.

1. **The gate is the mechanism.** Proposal machinery contributes almost nothing; the acceptance gate (balanced probe, regression budget, hidden holdout, repeated passes) separates compounding from thrashing. Invest there.
2. **Whoever owns the approval surface owns label capture, atomically.** The verdict is recorded in-process with the act itself; presenting a proposal, delivering the decision, and writing the ledger rows are ONE component that migrates together. Evidence starvation must revoke autonomy *(target state — the dead-man pages today; the auto-demote wiring joins when graduation goes live, §3)*.
3. **No loop may edit its own judge — and the judge must be read-isolated, not just write-protected.** Germline protection for judge code; split germline for eval fixtures; the holdout lives in a scope the optimizer cannot read; logs are immutable.
4. **Machine truth first, human judgment reserved.** Fill evidence denominators with adversary-resistant probes; spend Captain attention only where machines cannot check; treat every verifier as a proxy that must co-evolve with what it measures.
5. **Never trust the actor's narrative.** Agents write claims; tools write logs; a verifier reads both and writes neither. Fabrication demotes. Failure reporting must be cheap and unpunished.
6. **Fail closed, degrade honestly.** Unmeasured means propose-only *for the earn-up rows*, and always-gated for the six ceiling rows; since the earn-demotion ruling (2026-07-03/04) the reversible/undo-backed rows sit *above* propose-only in the table and are demoted on evidence (§3) — fail-closed there is meant to be the demotion path rather than a propose-only floor. **As shipped that column is dormant**: `run_action_lane` gates every act-first branch on `instance/config/act-first-enabled` / `CABINET_ACT_FIRST=1`, neither of which the export carries, so the floor a fresh deployment actually gets *is* propose-only until the Captain flips it. Credit exhaustion halts self-improvement rather than skipping gates. Veto windows hold when the Captain is unreachable. Probes report could-not-observe rather than guessing.
7. **Built = scheduled + fed + watched.** A component isn't done until a watchdog would page on its starvation. Data-freshness assertions on every consumer.
8. **One joint per function.** Every severed wire in this estate's history was cut at a duplicated joint during a migration. Before any migration: enumerate duplicates, assign one owner, run both joints in observed parallel, verify evidence continuity, then delete with a tripwire.
9. **Episodic execution over durable state.** Fresh sessions re-reading files and databases beat marathon contexts; capsule, handoff, and progress files; restart is the default recovery.
10. **The Captain is a metered, two-way resource.** Escalation budgets and rubber-stamp detection on one side; a debt queue with ageing on the other. Batch, dedupe, expire.
11. **Asymmetric autonomy is correct.** Machine-verifiable lanes graduate in weeks; judgment lanes may stay gated for months. Don't equalize by weakening the gate.
12. **Reversibility prices everything.** Reversible and cheap: act and log. Expensive: evidence threshold. Irreversible: ceiling, forever.

---

## 2. The Intent Hierarchy

Intent flows down through four layers, each more concrete than the last. The Captain owns the top; the org derives everything below it and carries proposals back up for ratification.

```
DIRECTIONS   (Captain-authored, durable, few)
   └─► OUTCOMES   (AI-derived, Captain-ratified, bounded + verifiable)
          └─► WORK MODEL   (stream / missions / intake)
                 └─► EXECUTION   (claims, episodic runs, verification)
```

### Directions — the layer the org may never author

A **direction** is a Captain-owned statement of where a lane is going: a mission sentence, a small set of **instruments** (trend metrics — instruments, not targets), the current **bets**, and explicit **not-goals**. Directions are few, durable, and revised roughly quarterly. They live in `instance/config/directions.yml`.

Two rules are absolute. First, **the org derives outcomes from directions; it never authors directions** — not even for its own self-improvement lane, which is governed by a Captain-owned direction like any product lane. Second, **instruments are trend instruments for drift detection, not deadline targets** — the moment an instrument becomes a quota, Goodhart owns it.

### Outcomes — bounded, verifiable, ratified

An **outcome** is a bounded, verifiable state change: a verifier can look at evidence and say *the world changed from X to Y*. Outcomes are AI-derived and Captain-ratified; every proposed outcome must cite the direction bet it serves and the instrument delta it expects. Lifecycle: `draft → active (ratified) → achieved → retired`.

Each lane holds a rolling window of **1–2 active outcomes — a cap, not a quota**. A lane with zero active outcomes is healthy; silence is a valid state. The **renewal loop** keeps the window honest: when an outcome's criteria all carry verified evidence, the coordinating role proposes `achieved`; the freed slot triggers the lane's product-owner role to draft a successor from stream pressure and the epic queue; the Captain ratifies. At AI speed these are gates, not calendars.

The retro adds a **direction-drift check**: outcomes achieving while the direction's instruments stay flat means the org is winning the wrong game — regenerate the outcomes, don't celebrate them.

### The work model — Stream / Missions / Intake

Every piece of work in a lane is exactly one of three classes (full contract: `framework/docs/work-model.md`):

- **STREAM** — continuous product work: bugs, tasks, small features. Lives on the **local task board** (the canonical work store; external PM tools mirror via adapters — §6). Claim → execute → close; never ends. Standing quality bars ("critical items triaged within 24h") are **stream SLOs** — control loops monitored by briefings, never outcomes.
- **MISSIONS** — the outcomes above, when work needs orchestration structure the stream cannot give: ordering, verification gates, risk-tiered approvals, cross-role handoffs. Two-prong test: verifiable state change (not an activity) AND genuine campaign shape. A batch of stream items with a bow on it is not a mission. Expect a handful per product per year.
- **INTAKE** — the classification machinery feeding the other two: sweep sources, classify to a lane, gather-then-decide, propose-only. Intake runs forever and is never itself an outcome.

Never collapse the classes. Stream wrapped in outcomes produces zombie missions; intake wrapped in an outcome produces a mission that can never achieve. Products are **lanes**, not outcomes — a product never finishes; only outcomes do.

### Execution

Officers claim work from the board, run it episodically (§7), verify independently (the agent that built a thing is not the agent that confirms it works), record an experience entry, and close the item the moment it is known done — board state must reflect reality the same turn, because a drifting board poisons briefings, retros, and priority math.

---

## 3. The Evidence Engine

Autonomy in a Cabinet is a computed, demotable property of one ledger. This section is the machine that computes it.

### One ledger, three writers — none of them narrative

The **consequence ledger** is an append-only store of consequence events, one normalized schema (`framework/schemas/consequence-event.schema.json`) covering every acting surface, with proposal, outcome, and review phases joined by correlation IDs. Three independent writers:

1. **Officers** emit proposals, each minting a correlation ID.
2. **The verdict binder** records Captain decisions — mechanically (below).
3. **Outcome probes** — deterministic daemons polling machine truth (PR checks and merge/revert state, deploy status and rollbacks, error-budget burn, CI runs, support-thread resolution) — write outcome status and reviewed verdicts. *(target state — probes land per plan phase B2, `docs/plans/`)*

Correlation IDs are minted at proposal time and **propagated into the artifacts themselves** — commit trailers, deploy metadata, thread tags — so probes attribute by exact read-back, never by time-and-author guessing. Unattributable artifacts count for no one. Every probe event carries `observed` vs `could-not-observe`; an unreachable upstream never counts as anyone's failure.

### Mechanical verdict capture — the founding lesson

The estate's signature historical failure, paid twice: an approval surface moved, the label ledger didn't move with it, and every autonomy lane silently starved at n=0 while the org kept working. The lesson is principle 2, made structural: **the inbound decision path writes the superseding approve/edit/skip event in-process, before delivery — the coordinating officer reads results but is never the recorder.** Presenting the proposal, delivering the decision, and writing both ledger rows are one component, germline-protected, that migrates together or not at all. *(live — the binder wire shipped in the shared foundation phase (F0.5), flag-gated and hardened against pid-spoofing and truncation; it now carries proactive-action verdicts, not just reply drafts, per the 2026-07-03 pivot; `docs/plans/EXECUTION-STATUS.md`)*

### Verdict supply per flavor

- **Flavor B — machine probes are the primary verdict supply.** A product org has abundant, adversary-resistant, machine-checkable ground truth; probes fill graduation denominators at product-traffic volume instead of human-reply volume. One valve must be closed for this to be safe (§below: test-diff).
- **Flavor A — human verdicts only.** For "is this what the Captain would do," the only honest signal is the Captain's approve/edit/skip, quiz picks, and observed subsequent actions. Bars stay conservative; months at propose-only is honest, not slow.
- Both flavors: batched one-tap approvals carry reduced label weight — a rubber-stamp is not evidence.

The shared rule: **promotion reads the most trustworthy verdict source available for that lane's ground truth.**

### Graduation cells

Autonomy is assigned **per action class, never per agent**. Each (action class × context) cell accumulates verdicts; graduation math computes ratios (fitness = outcome held × review confirmed) against per-cell bars — minimum sample counts, agreement rates, clean-day dwell. The **authority matrix** (`framework/policies/authority-matrix.yml`) maps risk class × confidence state to a verdict: auto, propose, or gated. The fail-safe spine: **unmeasured always resolves to propose-only.** Graduated auto actions execute behind a **veto window** — an `execute_after` timestamp the Captain can cancel within, which holds (fails closed) if the Captain's channel is unreachable.

### Demotion — trust that cannot ratchet down is not trust

Demotion is automatic and drilled, not discretionary:

- A wrong verdict or cancelled auto-action drops the cell.
- **Verifier-detected fabrication demotes directly** — an officer claiming success against contradicting tool logs is a trust event, not a style note. Honest self-flagging is penalty-free and counts *toward* graduation calibration.
- **Model upgrades demote graduated cells one level pending re-proof** — graduation history is stamped with the model baseline it was earned on. *(target state — evidence events carry a `model_id`, but no model-baseline comparison or upgrade-demotion exists in the tree; `framework/fidelity/graduation.py` never reads it.)*
- Error-budget burn throttles new-feature autonomy while **pre-approved incident remediation stays fast** — never route rollbacks to the Captain mid-incident.
- A **synthetic wrong verdict is injected before any cell is trusted** — demotion is proven live, chaos-engineering the trust loop itself.

### The ledger-liveness dead-man

A standing watchdog: if a lane emits proposals while Captain replies are visibly arriving and **zero verdicts land on the ledger for N hours → critical page.** Automatic demotion to propose-only is the design and is *not yet wired* — today the page is the whole response, so evidence starvation is detected, not self-neutralizing. (The check is also not in the germline set: `cabinet/scripts/ledger-liveness-check.py` is officer-writable, as are `framework/watchdog/*.py`.) Staleness is loss of proof, not preservation of it. It converts the estate's twice-paid failure into a self-neutralizing one only once that demotion lands; today it converts it into a *detected* one. *(live — the check is armed and pages hourly via the off-machine healthchecks path over an unwindowed ledger read; it caught a real starvation on its first hour. Automatic demotion lands with the graduation wiring (B2.9+); until then the page is the response. `docs/plans/EXECUTION-STATUS.md`)*

### The test-diff valve — closing Goodhart on machine truth

CI verdicts are adversary-resistant only if the builder cannot move the goalposts. Mechanically enforced: test-touching diffs (coverage deltas, assertion-count drops, skip/xfail additions) are a **ceiling risk class** — a PR that touches tests can never advance graduation from CI-green alone; it routes to Captain review or an independent verification lane, backed by a coverage-ratchet probe the builder cannot author. This is a blocking precondition for enforcement, not a later hardening.

### The Gate — self-modification's one door

Every durable change to the org's own behavior — playbook deltas, skills, policy values, tool descriptions, memory promotions — is admitted through **the Gate**, the most protected asset in the estate *(target state — gate-runner lands per plan phase B5)*:

- **Balanced probe:** previously-failing AND previously-passing cases — a change must fix something without breaking anything.
- **Zero-regression budget** on the passing set; **pass^k (k=3)** on behavioral cases — single lucky passes don't count.
- **Read-isolated holdout:** a rotated eval set living in a scope the org cannot read, because a proxy the optimizer can see is a proxy it will eventually hack. Proxy-vs-holdout divergence alarms.
- **Cost gate:** changes that inflate tokens-per-task beyond budget are rejected regardless of quality.
- **Split germline:** judge and policy *code* changes are Captain-only; the eval-fixture *corpus* is append-only with additive cases auto-admitted — eval refresh runs at machine speed while the judge stays human-held.
- **Trace→test flywheel:** every escalation, wrong verdict, and rollback becomes a probe case. The suite grows from real failures, not imagination.
- **Judge discipline:** pinned judge contracts (model ID + rubric version + prompt hash) in git; position-swapped comparisons; a monthly Captain-labeled calibration batch; full re-baseline on any judge or model swap.

The Gate is live only when it has demonstrably **rejected** something. A gate that admits everything is a rubber stamp with extra steps.

---

## 4. Governance & Safety

### Three enforcement strata

Safety is enforced at three independent layers, so no single failure — and no single persuasive argument — can unlock the estate:

1. **The tool-use hook** — deterministic checks before every tool call: kill-switch state, germline write-protection, prohibited actions. The reflex layer; it asks no model's opinion.
2. **The typed policy engine + authority matrix** — the judgment layer: classifies each act's risk class, reads the cell's measured confidence, resolves auto/propose/gated. CI-asserted invariants guarantee no ceiling cell can ever resolve to auto. The hook remains as belt-and-suspenders through every migration — the old gate is never deleted in the same motion that enables the new one.
3. **The executor + hash-locked outbox** — the physics layer *(target state — plan phase B4)*: one deterministic process holds all send/deploy credentials. Officers physically cannot send; they write proposal rows; the executor executes only rows carrying a fresh approval token whose payload hash matches exactly what the Captain saw. Every external side effect becomes a ledger row by construction — every send is a label. Veto windows are `execute_after` timestamps; the executor fails closed when the Captain channel is down.

### The hard ceiling — six classes, never lifted

**External communications, production deploys, spend, secrets, network writes, and credential grants remain Captain-gated at every confidence level, in every phase, forever.** No graduation evidence lifts them. Narrow carve-outs (a receipt auto-forward, an incident rollback) are implemented as enumerated conditions inside the executor — never by lifting a ceiling row. CI asserts the invariant continuously.

### Germline — no loop may edit its own judge

The components that judge the org — the policy engine, authority matrix, golden evals, graduation math, the trust ladder, the evidence plane, the enforcer hooks, the courses-of-action rule — are **germline**: write-protected against every officer and every loop, enforced at the hook. The set is exactly the 73 files + 7 directories enumerated in `cabinet/scripts/germline-lock.sh`; **the dead-man watchdogs are not in it** — `framework/watchdog/*.py`, `cabinet/scripts/killswitch-watchdog.py` and `cabinet/scripts/ledger-liveness-check.py` are officer-writable, so the alarm plane is *not* yet held to the same standard as the judge plane. Officers propose germline changes to the Captain; only the Captain applies them. Since 2026-07-04 the boundary is also **physical**, not just string-matched: `cabinet/scripts/germline-lock.sh` stamps the enforcer + judge plane macOS system-immutable (`schg` — only root can set or clear it, and officers have no passwordless sudo), so a Turing-complete officer shell cannot forge the enforcer that judges it; the hook remains as defense-in-depth inside the locked set (Captain ruling 2026-07-04: harden the hook + filesystem lock, stop string-whack-a-mole). Germline edits become a deliberate Captain `sudo … unlock → edit/commit → lock` window. The split-germline refinement (§3) keeps eval *fixtures* flowing at machine speed while judge *code* stays human-held. This is a non-negotiable architectural invariant: a self-improving system that can weaken its own examiner will, eventually, and the logs of the field's best-known self-modifying systems show exactly that.

### The kill switch

**Anyone can stop the fleet — any officer, any watchdog, the Captain. Only the Captain resumes it.** There is no typed resume token; the enforced mechanism is that while the switch is active the pre-tool-use hook refuses *every* tool call from a hooked officer session (including the redis `DEL` that would clear the key), and the two disarm paths — `cabinet/scripts/kill-switch.sh deactivate` and the dashboard governance toggle — run outside officer hooks. A same-uid process outside the hooks is the honest residual (RES-016). The switch is designed **fail-closed**: if its state store is unreachable, work halts rather than proceeding blind. Halting is always safe and always reversible by exactly one person.

### Accounts, credentials, and the human wall

The Captain-ruled boundary (2026-07-02): **the org may autonomously create accounts on low-risk services** (a monitoring endpoint, a status page) when a plan requires it; **the human gate is reserved for what is legally or financially binding** — payments, contracts, OAuth consent to sensitive scopes, identity ceremonies. Credential entry always flows through the sanctioned executor path with secrets referenced from the keychain — an officer never types a secret into an arbitrary surface, and files carry names of secrets, never values.

A pre-enumerated **Captain-required action registry** (payments, OAuth, DNS, 2FA, legal signatures) lets officers park-and-batch when they hit the human wall instead of stalling or improvising. The org cannot legally sign, pay, consent, or appear — its job is to make every arrival at that wall batched and fully briefed.

---

## 5. The Captain Interface

### Monitor-and-intervene, not approve-everything

Per-action permission prompts train humans to approve unread (the measured field number is 93%). The Cabinet's interface is therefore monitor-and-intervene: a streamed activity digest, cheap interrupts, inline approve/edit/skip — with hard gates reserved for the ceiling classes and genuine escalations. The system watches its own approval latency as a **rubber-stamp detector**: sustained sub-10-second approvals on judgment items trigger a batching review, never a gate weakening.

### One voice

The coordinating officer (the Chair) is the **sole Telegram voice**. Officers never fragment the Captain's phone with parallel threads; internal coordination rides internal channels; one relationship surface stays clean. Symmetrically, there is **one send path** in code — a single choke point every outbound message flows through, tripwired in CI.

### Proposal hygiene

The measured failure that produced these rules: one-card-per-*action* proposals created a 51% unanswered backlog — attention died of fragmentation, not volume.

- **Investigation bar:** gather-then-propose. Full thread and audience, counterparty intel, open commitments, board state, the indexed codebase when technical. If the bar cannot be met, name the gap instead of proposing.
- **One card per situation, carrying the whole course of action** — the full chain (reply → task → follow-up → close commitment) with per-step gates, never step 1 with the rest planned silently.
- **Urgency tiers:** `ping-now` (would be wrong by tomorrow) · `batch-into-next-briefing` (the default) · `FYI-digest`.
- **Auto-expiry:** unanswered proposals fold into the next briefing's decision queue as one line — never re-pinged as fresh.
- **Never re-ask answered questions.** The decision trail is checked first; a Captain answer in any channel is applied and cited.

### Briefings and the decision queue

Scheduled briefings (morning and evening) are the org's pulse: headline, calendar, overdue and due, in-flight work, stale items, the decision queue, and one recommended starting point. Everything that can batch, batches here.

### The Captain-debt reverse queue

The Captain is a bottleneck in both directions, and the second direction is usually unmodeled: **what the Captain owes the org** — pending ratifications, germline applies, tokens, OAuth clicks, calibration batches. The Cabinet tracks these as a first-class queue with age, *what-it-blocks*, and effort estimate, surfaced in every briefing, cleared in scheduled batched sessions (one sit-down, N pre-verified diffs). Measured history is blunt: approved one-liners rotting for days stall the whole loop at the last mile. The debt queue is the mechanism that prevents it.

### The escalation budget

Target: **escalations under 10% of actions.** Over-escalation reduces realized safety — it trains inattention. Breaches alert; a queue growing faster than it clears is treated as miscalibration or attack, and the response is better batching or better evidence, never a weaker gate.

### The L0–L3 ladder

Every action class sits at a dispatcher level: **L0** auto + audit trail · **L1** auto above a measured confidence bar (graduated cells, veto window) · **L2** one-tap approval · **L3** dual-confirm + cooldown (credentials, payments, germline diffs). Ceiling classes cap at L2/L3 forever. Levels are assigned per action class on evidence — never per officer, never on charisma.

---

## 6. Memory & Knowledge

### One synthesis destination

Everything the org learns, derives, or synthesizes is born in **one knowledge corpus** — flavor A: the captain's personal vault; flavor B: the cabinet vault, `vault/` in the repo (architecture, incidents, decisions, support KB, deploy history — the directory formerly named product-brain; Captain-ratified rename 2026-07-16) — as markdown with provenance and content timestamps, indexed for hybrid semantic search. External tools are not synthesis destinations. The historical alternative — synthesis scattered across a PM tool, chat threads, and six decision stores — produced two-hop staleness and split-brain truth; the ruling (2026-07-02) ended it: **the corpus is the one synthesis destination; every other system keeps only its own function.**

### Where a document lives

Knowledge, designs, plans — any captain/org document — go in **`vault/`** (plain markdown, `[[wikilinks]]` welcome, Obsidian-compatible but never required; local git history only — no remote or account needed). Framework reference — specs, plans/proposals, Captain-ceremony runbooks — lives in **`docs/`**. **Officer-executable procedures live in `memory/skills/`; Captain ceremonies stay runbooks** — a runbook whose steps an officer actually runs graduates to the skill library with a pointer stub left behind. Deployment-specific config and captain-personal material live in **`instance/`**. The full placement one-pager is in [`vault/README.md`](./vault/README.md).

### Memory vs source of truth

Not everything belongs in memory. Every connected source is classified: **knowledge-sync** (synthesized knowledge → the corpus, with provenance and content time) vs **live-adapter** (operational state stays in the tool and is queried at question time — a board's current status, a database row) vs **ignore**. Memory holds what informs judgment; live state stays live. Confusing the two produces confidently-stale answers.

### The Estate Mapper and the Source Map

When a tool connects, the org runs read-only **discovery** over its estate (boards, channels, drives, folders), proposes a **classification** per surface, and records the result as a **Source Map** (`instance/config/sources/<tool>.yml` + a corpus note) — durable environment knowledge that replaces hardcoded IDs forever. A one-card **sync plan** (mode, cadence, backfill depth and cost, destination) gets Captain approval; a **sync compiler** then generates the jobs, registered in the services manifest with freshness floors and watchdog expectations — scheduled, fed, and watched by construction. Low-cadence re-exploration diffs the estate over time; offboarding a source disables its adapters and marks its history source-defunct rather than deleting it. *(target state — Captain-ratified workstream, sequenced per `docs/plans/`)*

### Federated gather

Every adapter exposes `search` as an auto-registered second-tier fetcher for the org's gather step — so a surface that isn't synced is still not invisible. Un-synced ≠ unknown; it is just slower to reach.

### Work tracking — the TaskAdapter

The canonical work store is a **local task board**: the append-only org-runtime event ledger in a local SQLite file (`cabinet/cache/org-runtime.sqlite3`, overridable via `ORG_RUNTIME_DB`) with `officer_tasks` / `mission_steps` as the task model. Concurrency is a per-`(context, officer)` WIP cap enforced by a Postgres trigger taking `pg_advisory_xact_lock` (`cabinet/sql/038-officer-tasks.sql`) — *not* compare-and-swap claiming with expiring leases: that design (`task-board.sqlite3`, `lease_until`, heartbeat + reclaim) was planned and never built, and no lease machinery exists in the tree. External PM tools — Monday, Jira, Linear — are optional **TaskAdapter** plugins: pull backlog, push status, mirror state. **Local wins; the adapter mirrors.** The foundation runs with zero PM dependency; a deployment plugs in its team's PM tool for collaboration visibility, or none. A CI ratchet keeps PM imports out of the framework. *(adapter cutover per `docs/plans/`)*

### The tier model

- **Tier 1 — operating law**, loaded into every session: constitution, safety boundaries, role definition, the Captain-facing ledgers. Short, accurate, ruthlessly maintained.
- **Tier 2 — working notes**, per officer: corrections, preferences, accumulated context. Read at session start, written after significant work.
- **Tier 3 — episodic memory**: the full corpus of experience records, decisions, research. Retrieved on demand, never bulk-loaded.

Only Tier 1 is always loaded. Memory flows upward by consolidation: a pattern observed repeatedly becomes an instruction; a procedure that works repeatedly becomes a skill. A nightly consolidation job proposes the promotions — through the Gate, like every durable change.

### Bi-temporal facts and content time

Facts that can silently invalidate (deploy states, decisions, commitments) are stored **bi-temporally** — valid-from/valid-until, superseded, never deleted — so the org can answer both "what is true" and "what did we believe then," and a high-relevance fact cannot become confidently wrong. All measurement and retrieval fencing uses **content time** (when the event happened), never file mtime; a chunk whose content time cannot be derived is excluded, never guessed.

### Provenance and quarantine

Content from untrusted external channels — inbound support mail, web pages, external PR comments — is **data, not instructions**. It is quarantined at ingestion: it may inform a Captain-gated draft, but it can never be promoted to durable memory, a skill, or a policy delta without Captain authentication. This guards the poisoning path the Gate cannot see: a subtly poisoned "lesson" shows no behavioral regression until it is load-bearing. Inferred knowledge (reconstructed links, derived relations) carries `provenance: inferred` with confidence — never laundered into fact.

---

## 7. Officers & Runtime

### Thin personas, thick SOPs

Officers are differentiated by **tool scopes and procedures, not persona prose** — elaborate character sheets measurably degrade performance; crisp SOPs and clean interfaces improve it. A role definition carries identity, domain of ownership, autonomy boundaries, and shared interfaces. Step-by-step procedures live in the skill library where the loops can improve them; fixed interaction patterns are deliberately absent — officers with clear ownership find their own collaboration paths, and proactive notification of peers is a duty, not a workflow.

### The officer ceiling

**Three to four officers, maximum.** Coordination overhead is real physics: error amplification grows with every coordinating member, and adding agents to a task class a single agent handles poorly makes it worse, not better. The flavor-B roster is deliberately minimal — a **Chair** (sole Captain voice: triage, synthesis, briefings; never in the verdict-recording path), a **Builder** (single writer on the product repo), and a **Support-Drafter** (propose-only external comms, activated only after enforcement and provenance gates are live). Everything else — probes, verifier, gate-runner, executor, watchdogs — is a **deterministic daemon, not an officer**. A new officer is added only when a task class's measured single-agent success is below threshold, never for throughput.

### Episodic execution

Marathon sessions are the anti-pattern: multi-day contexts accumulate noise until agents act on corrupted assumptions, and models don't recover from their own wrong turns in-thread. Officers therefore run **episodically**: bounded runs in fresh sessions, resumed from durable state — a capsule file (who am I, what is the mission), a handoff file (exact next actions), a progress file, commit-on-stop. Restart is the default recovery, not the exception. Crew for parallel spikes run in isolated worktrees. Fresh-session-from-durable-state beats in-thread correction; this is the operational precondition for self-improvement to matter at all.

### Crew and delegation

Crew inherit the spawning Officer's boundaries, narrowed — never widened; enforced at infrastructure level. Delegation is **artifact-first**: objective, output format, tool guidance, boundaries, and full context in a brief — chat-relay handoffs measurably lose intent. Returns are condensed artifacts, not transcripts. Before decomposing work at all, the spawn gate asks whether one agent clears the bar alone.

### The substrate

One Mac, one dedicated auto-login user, **everything a user-session LaunchAgent** (subscription auth, keychain, and OS permissions live in the user session — never cron, never daemons). Sleep disabled; OS auto-updates scheduled within watchdog-aware windows. Officers live in tmux panes; deterministic services run headless. **The entire fleet is declared in one services manifest** (`cabinet/services.yml`) from which every launchd plist is generated — no hand-authored plists, no machine-specific hardcodes, and the manifest is diffable against what is actually installed and firing *(live — the manifest (`cabinet/services.yml`) and generator (`generate-plists.py --check`) shipped in the shared foundation phase; `docs/plans/EXECUTION-STATUS.md`)*. **The machine must be rebuildable from git alone.** Durable state lives in git and SQLite (WAL, backed up by snapshot — never raw-copied); Redis is an ephemeral trigger bus, never the only home of anything durable. Secrets are keychain-referenced: names in files, values never.

### The watchdog stack

Multiple independent, simple observers beat one sophisticated supervisor:

- **Outcome watchdog** — verifies *outcomes*, not process exit codes (a job can run green and deliver nothing).
- **Ledger-liveness dead-man** (§3) — evidence starvation pages and demotes.
- **Heartbeat watchdog** — progress-aware (monotonic step counters), distinguishing healthy-idle from wedged; a waiting agent may be doing exactly what it should. Tiered recovery: re-inject → compact-and-restart → fresh session + page.
- **External dead-man** — an off-machine check the estate cannot take down with itself.
- **Data-freshness assertions** on every consumer — gates, briefings, and probes hard-fail on stale or empty inputs.
- **Weekly synthetic-kill drills** — deliberately stop one job and assert the page arrives. An alarm that has never fired in a drill is a hope, not an alarm.

---

## 8. Self-Improvement Loops

### The loop family

Improvement runs at several cadences at once; the fastest loop that can catch a signal owns it.

- **Task loop** (every task): plan → execute → verify independently → record an experience entry. Enforced — a task without a record is not complete.
- **Individual reflection** (event-triggered: compaction, completion milestones — never a clock, never on idle): each officer reviews its own records; three repeats of a pattern drafts a skill.
- **Cross-officer retro** (event floor with a time ceiling): handoff quality, trigger responsiveness, coordination drift, the direction-drift check (§2), one focused improvement.
- **Evolution loop**: validates and promotes draft skills, proposes role amendments, refreshes golden evals.
- **Inline meta-loops**: the **pattern listener** (scans every Captain message for standing-preference signals and offers to encode them) and **intent inference** (hypothesizes the Captain's latent WHY before any Captain-facing reply) — because in-conversation signals arrive faster than any scheduled loop.
- **Reasoning review**: officers log expectations with their actions; a scheduled pass compares expectations to what actually happened and mints lessons from the misses.

One discipline binds them all: **every reflection must cite an external signal** — a CI result, an eval, Captain feedback, a production metric. Intrinsic self-critique without external signal is drift with good posture.

### Everything durable rides the Gate

Reflection produces *candidates*. Only the Gate (§3) turns a candidate into doctrine: balanced probe, regression budget, repeated passes, holdout, cost check. Skills have a full lifecycle — drafted in `evolved/`, validated, promoted, and eventually **archived with reason notes** when superseded or unused: a library that only grows becomes noisy and contradictory, and archival is what keeps it trustworthy. Foundation skills are never edited in place; improved versions land in the overlay and take precedence.

### Earned auto-apply

Even *applying* improvements is graduated, per change-class: a class earns silent auto-apply only after repeated confirmed applications with zero wrong ones, and only for reversible changes — everything else stays one-tap Captain ratification. Playbook edits are **itemized deltas with helpful/harmful counters, never monolithic rewrites** — wholesale self-rewriting of accumulated context is how systems collapse their own memory.

### Curation

Standing hygiene jobs, all Gate-bound: a **nightly consolidation** over transcripts and records proposing memory promotions; a **weekly drift replay** of sampled real traffic against the current system; a **monthly Captain calibration batch** (10–20 labeled cases) keeping judges honest; a **harness-debt review on every model upgrade**, because scaffolding encodes assumptions about model weaknesses that expire. Changes carry lineage tags so downstream outcomes attribute to the change that caused them, and underperforming lineages get reverted on evidence, not sentiment.

### Bounded pressure

Optimization pressure against any proxy grows reward hacking with iteration count. Hence: iteration caps per improvement cycle; a hidden holdout with divergence alarms; hard budget stops — **self-improvement halts fail-closed on credit exhaustion; no change auto-applies without a completed gate run; autonomy never widens on a skipped gate.**

---

## 9. Onboarding a Product

Trusting the org with a new product is never ad-hoc. It is a staged SOP with machine-checked gates — the same ramp every time, which is what makes the org a reusable machine rather than a bespoke build. *(SOP artifacts land per plan phase B6; the stages below are the ratified contract.)*

**Stage -1 — Generate the deployment.** The `cabinet-init` skill gathers purpose, profile, lanes, org shape, autonomy destination, and integrations. It generates `instance/` configuration and prints activation steps. **Nothing it generates activates by itself.**

**Stage 0 — First Window and First Dividend.** Dashboard `/onboarding`, Telegram `/onboard`, and the World overlay render one canonical card from `framework/onboarding/journey.py`. The Captain chooses one folder and purpose, reviews a hash-bound read-only Charter, and receives one deterministic source-cited finding. Entering a folder is not consent to inspect it; the exact Charter hash must be ratified first. Relationship destination is recorded but grants zero authority. Revoke, event-backed undo, and typed purge work on every surface. Design: `docs/plans/onboarding-v2-design-of-record-2026-07-14.md`.

**Stage 1 — Read-only shadow week.** The org watches and maps, writing nothing. Output: a product dossier — architecture map, operational runbook, a machine-readable deploy policy (canary %, rollback triggers, blast-radius caps), an **oracle inventory** (which machine-truth probes apply to this product, with the queries), and this product's Captain-required registry entries. The Estate Mapper (§6) runs here: discovery → classification → Source Map → approved sync plan.

**Stage 2 — Propose-only.** Every action proposed, every verdict recorded, until the ledger holds **at least ~20 consequence events** for the product with measured escalation precision above the bar. Probes live; evidence accruing; nothing auto.

**Stage 3 — Per-cell graduation.** Standard bars apply per action class. Compliance- or judgment-heavy lanes are pinned Captain-gated per the dossier, deliberately and indefinitely where the product warrants it.

**Product is a parameter, not a fork.** A second product onboards with **zero framework code changes** — CI greps assert no product slug ever appears in `framework/`. Product specifics live in the instance layer and the dossier.

**Federation** — spawning a whole new cabinet instance for a product — is permanently the highest-consequence act: propose-only, dual-confirm with cooldown, full dossier required, fresh ledger and model stamp on the new instance (autonomy evidence never transfers between orgs, because it was earned against a different ground-truth distribution), and excluded from graduation forever.

---

## 10. Glossary

| Term | Meaning |
|---|---|
| **Captain** | The human. Sets directions, ratifies outcomes, holds the ceiling keys. |
| **Officer** | A persistent Claude Code session owning a domain (Chair, Builder, Support-Drafter…). |
| **Chair** | The coordinating officer; the sole Telegram voice; never the verdict recorder. |
| **Crew** | Ephemeral subagents spawned by an officer; permissions inherited downward only. |
| **Flavor A / B** | Personal clone org (human verdicts, sensing stack) / standalone product org (machine probes, Mac Mini). |
| **Direction** | Captain-authored durable intent for a lane: mission, instruments, bets, not-goals. Never AI-authored. |
| **Instrument** | A trend metric on a direction — drift detector, never a deadline target. |
| **Outcome** | AI-derived, Captain-ratified, bounded verifiable state change. Window-capped per lane. |
| **Lane** | A product or standing domain. Lanes never finish; outcomes do. |
| **Stream / Missions / Intake** | The three work classes: continuous work / ratified campaigns / classification machinery. |
| **Renewal loop** | Achieved-outcome confirmation → successor derivation → Captain ratification. |
| **Direction-drift check** | Retro test: outcomes achieving while instruments stay flat ⇒ regenerate outcomes. |
| **Consequence ledger** | Append-only store of proposals, verdicts, and outcomes — the org's single evidence plane. |
| **Correlation ID** | Minted at proposal, propagated into artifacts, joined by probes. The evidence join. |
| **Verdict** | A recorded judgment on a proposal: approve/edit/skip (human) or probe-verified outcome (machine). |
| **Verdict binder** | The mechanical component recording verdicts in-process with delivery. |
| **Graduation cell** | (Action class × context) unit that accumulates evidence and earns autonomy. Never per-agent. |
| **Authority matrix** | Risk class × confidence → auto/propose/gated. Unmeasured ⇒ propose-only. |
| **Hard ceiling** | Six classes gated at every confidence forever: external comms, prod deploys, spend, secrets, network writes, credential grants. |
| **Veto window** | Delay (`execute_after`) before a graduated auto-action fires; Captain can cancel; holds if the channel is down. |
| **Demotion** | Automatic autonomy reduction: wrong verdict, fabrication, model bump, starvation, budget burn. |
| **Ledger-liveness dead-man** | Watchdog: proposals flowing + replies visible + no verdicts landing ⇒ page + auto-demote. |
| **Test-diff valve** | Test-touching changes never earn graduation credit from CI-green alone. |
| **The Gate** | The eval-gated admission path for all self-modification: balanced probe, regression budget, pass^k, holdout, cost gate. |
| **Holdout** | Read-isolated eval set the org cannot see; divergence from the visible proxy alarms. |
| **Germline** | Officer-unwritable judge components; Captain-only changes. "No loop may edit its own judge." |
| **Split germline** | Judge code Captain-only; additive eval fixtures auto-admitted at machine speed. |
| **Executor / outbox** | Sole credential holder executing hash-locked approved rows; every send a label by construction. |
| **Kill switch** | Anyone stops; only the Captain resumes; fails closed. |
| **Captain-required registry** | Pre-enumerated human-only actions (payments, OAuth, DNS, legal) — officers park-and-batch. |
| **Captain-debt queue** | What the Captain owes the org: ratifications, applies, tokens — aged, blocking-annotated, batched. |
| **Escalation budget** | <10% of actions escalate; breach alarms; latency watched as a rubber-stamp detector. |
| **L0–L3 ladder** | Auto+audit / auto-above-bar / one-tap / dual-confirm+cooldown — per action class. |
| **One voice / one send path** | Single Captain-facing officer; single code path for outbound, CI-tripwired. |
| **Course of action** | One proposal card carrying a situation's full chain with per-step gates. |
| **Source Map** | Durable per-tool estate map: surfaces, classifications, sync decisions (`instance/config/sources/`). |
| **Estate Mapper** | Discovery → classification → Source Map → sync-plan proposal → compiled, watched sync jobs. |
| **Knowledge-sync vs live-adapter** | Synthesized knowledge enters the corpus; operational state stays in its tool, queried live. |
| **Federated gather** | Every adapter's `search` auto-registers as a retrieval fetcher — un-synced ≠ invisible. |
| **TaskAdapter** | Optional PM-tool mirror over the canonical local task board. Local wins. |
| **Bi-temporal fact** | valid-from/valid-until, superseded never deleted — "what is true" and "what did we believe then." |
| **content_ts** | Content time (when it happened), never mtime — the only clock for fencing and measurement. |
| **Provenance quarantine** | Untrusted inbound content is data-not-instructions; never promoted to memory/skills/policy without the Captain. |
| **Episodic execution** | Bounded fresh-session runs from durable state: capsule, handoff, progress files; restart as default recovery. |
| **services.yml** | The single deployment manifest; every scheduled component generated from it; machine rebuildable from git. |
| **Built = scheduled + fed + watched** | Existence criterion for any component (principle 7). |
| **Shadow parity** | A replacement runs alongside the incumbent on real traffic and must match before the incumbent retires. |
| **Experience record** | Per-task log entry: attempted, succeeded/failed, do-differently. Mandatory. |
| **Golden evals** | Known-good validation scenarios every promoted change must pass. |
| **Scorecard** | The ledger-derived raw metric vector (no composites) in the weekly brief. |
| **North star** | Verified outcomes per Captain-minute, trending up. |
| **Staged onboarding SOP** | Generate → First Window + cited dividend → deep orientation dossier → Strategy Mirror/Formation → propose-only evidence → per-cell commissioning and graduation. |
| **Federation** | Spawning a new cabinet instance — permanently the highest-consequence, propose-only act. |

---

## End Note

The models will change. The tools will change. The capabilities will expand. What will not change is the dynamic this guide encodes: a Captain setting direction, Officers owning domains, Crew executing work, evidence deciding trust, a gate deciding change — and a memory system ensuring that every lesson learned is a lesson kept.

The Cabinet is always in session.

---

*Captain's Cabinet is authored by Nathaniel Refslund. This is a living document, amended through the org's own gated loops with Captain ratification.*

*© 2026 Nathaniel Refslund. Released under the [MIT License](./LICENSE).*
