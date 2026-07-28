# Cognitive Core & Evolutionary Foundry — Living Masterplan

**Date:** 2026-07-19  
**Status:** Captain-authorized implementation program; phases advance only on measured exit gates  
**Baseline:** `8f9c555d2064d55a159a53fcedd6df33434a9291`  
**Baseline CI:** run `29687917451`, seven of seven jobs green  
**Extends:** `evolution-engine-spec-2026-07-05.md`, the evidence/self-improvement program, the authority membrane, and the source-adapter/layer-separation contracts. It does not create replacements for them.

## 1. Verdict and target

The Cabinet is not at a perfect terminal architecture. Its enforcement and evidence systems are unusually strong, but its intelligence is still distributed across hard-coded vocabularies, periodic services, narrow compilers, activity-weighted measurement, and several stores that each partly describe the same world.

The correct refactor is not a larger central orchestrator. It is a smaller logical constitutional membrane around a more adaptive cognitive system. “Logical” is load-bearing: the existing hook, `schg`, Seatbelt, broker, and evidence boundaries remain physically independent so one userspace defect cannot unlock the estate.

1. a tiny reference monitor for authority, provenance, privacy, effects, and promotion;
2. domain-owned transactional state and outboxes joined by one versioned language, not one physical database or bus;
3. a temporal epistemic world model that is disposable and rebuildable;
4. a causal objective graph that represents intended value, hypotheses, evidence, and trade-offs;
5. cognitive organs selected by need and measured marginal value rather than a permanent one-service-per-idea fleet;
6. an isolated evolutionary Foundry that manufactures and tests better text genomes first, then earns more structural search;
7. atomic champion selection, canaries, instant rollback, and permanent exclusion of Ring-0 from the search space;
8. eventual deletion and composition of superseded machinery after shadow parity proves it safe.

The optimization target is verified mission value per unit of Captain attention, time, cost, and risk. “Alien intelligence,” autonomy, activity, event volume, and code size are never success metrics by themselves.

This is a consolidation-and-arming program, not permission to recreate machinery under new names. Every phase begins by mapping its contract onto the existing evidence, learning, authority, attention, mission, extension, and service surfaces. If an existing mechanism already satisfies the contract, the phase adopts it. If two mechanisms overlap, the phase composes or retires one after parity. A new subsystem is justified only by a contract the current estate demonstrably cannot satisfy.

## 2. Ground truth at the baseline

| Surface | Measured state | Architectural meaning |
|---|---:|---|
| Central organizational event vocabulary | 91 types | New domains must stop growing one global enum. |
| Central action vocabulary | 30 types | Effects should become declared capabilities, while the classifier remains the constitutional enforcement join. |
| Fleet manifest | 57 rows, 44 enabled | New cognition should consolidate or activate on demand, not add permanent daemons without a retirement path. |
| Layer coupling | 24 debt + 19 ratified allowlist entries; 0 new | The framework/instance boundary is improving but unfinished. |
| Framework production Python | 206 non-test modules; 60,067 non-comment lines | Phase 0 may consume only its explicit 2-module/1,256-line temporary allowance; later additions offset or sunset. |
| Named production compiler modules | 1 (`framework/missions/compiler.py`) | Common semantics must not turn one compiler into a mega-compiler or multiply product compilers. |
| Event-emitter authoritative fan-out | 3 writer sinks from `emit` (`_write_to_log`, `_write_to_db`, `_write_to_store`) | The known duplicate-authority family is now counted and must collapse during compaction. |
| Targeted compatibility suite | 2,050 passed, 5 skipped (2,040 compatibility + 10 extension-gate) | Reproduced on the pinned baseline; this is the first behavioral floor, not proof of intelligence. |
| Evolution package | absent | The ratified Foundry specification is still an IOU. |

The current event emitter writes JSONL, optional Postgres, and a SQLite mirror while calling the result a single source of truth. The current outbox replays that event estate rather than sharing a transaction with domain state. The migration must remove this ambiguity one domain at a time; a universal event store would only centralize the same failure.

## 3. Constitutional invariants

These hold in every phase and every Cabinet:

- **One logical authority membrane, multiple enforcers.** Ring-0, germline, action classification, posture, grants, vetoes, the Gate, evidence policy, and the kill switch remain the reference-monitor contract. The hook, filesystem lock, OS sandbox, and brokers stay separate failure domains. The Foundry has no alternate promotion path.
- **Domain authority, projected cognition.** A domain transaction owns its state. Events, world models, dashboards, OVI, and cross-cabinet views are projections unless explicitly named as the domain authority. The consequence/autonomy ledger is itself one safety-critical domain and is not split across stores while its readers depend on one ordered supersession stream.
- **No distributed transaction fiction.** A business mutation and its outbox row commit together in the same local transaction. Relays are at-least-once; consumers are idempotent.
- **Common language, federated physics.** Domains share envelope and effect schemas. They need not share a database, queue, deployment, or failure domain.
- **Cabinet is the trust domain.** Every envelope carries an explicit hierarchical scope: `cabinet_id` is always required; `scope_kind` is `cabinet | lane | project`; `lane_id` is required for lane/project scope; and `project_id` is required only for project scope. Missing levels are absent, never inferred or filled with sentinel ids. Cross-cabinet traffic is signed, minimized, and propose-only; raw authority, human labels, secrets, and earned autonomy do not transfer.
- **World model is epistemic, not sovereign.** It preserves source time, observation time, confidence, provenance, contradiction, and supersession. Dropping it cannot lose authoritative state.
- **Evidence is fuel, never a score.** Machine outcomes and human/judge observations stay separate. Promotion requires the existing evidence and holdout protections.
- **Trajectories are observation-only.** A trajectory may name content-addressed receipts but cannot assert authenticity, graduation credit, eligibility, or fitness. Every objective resolves through an authenticated Captain-direction root; every effect separately records classification and the actual allow/deny decision; only fresh, causally linked intervention measurements can count as candidate evidence. Denials and violations remain observable but can never mint positive credit. The existing evidence/consequence plane and Gate resolve receipts and decide admission outside the candidate-controlled record.
- **Effects precede tools.** Organs extend the existing `action_types × risk_classes × undo_contract` joint with permissions, idempotency, cost, inputs, outputs, and health. Tool names and officer identities are bindings, not architecture; a second advisory “effect algebra” is forbidden.
- **Domain operations are not constitutional vocabulary.** A namespaced domain operation remains granular for execution and learning, but resolves through one declared capability into the existing enforcement joint. Phase-0 `action_type` records the current compatibility classification; Phase 4 evolves that classifier output into a smaller stable constitutional effect/risk/undo descriptor and makes legacy `ACTION_TYPES` an adapter, never a co-authority or a second algebra.
- **Text genome first.** Prompts, retrieval, memory policy, skills, and model routing evolve before role counts or delegation topology. Architecture search stays locked until at least three generations reproduce gains on the frozen holdout within the declared tolerance.
- **Modular monolith first.** Federated ownership does not imply microservices. A Cabinet runs as one deployable cognitive runtime by default. A component becomes a separate service only for a real security, ownership, latency, or fault-isolation boundary.
- **Shadow before authority.** New projections and decisions run shadow/mirror first. Cutover is a pointer or adapter flip with a tested rollback; destructive migration is forbidden.
- **Deletion requires evidence.** No legacy surface retires until all readers are inventoried, shadow parity holds over representative histories, rollback is rehearsed, and a release/soak window shows no fallback use.

## 4. Target architecture

### 4.1 Logical constitutional membrane

The existing enforcement planes collectively decide only:

- who/what is acting and for which Cabinet/lane/project;
- whether the requested effect is permitted;
- what evidence and provenance are required before and after the effect;
- whether a candidate may enter an arena, canary, or champion slot;
- whether the system must refuse, freeze, demote, or roll back.

No refactor folds them into one same-uid process. The logical membrane does not own planning, memory, task state, attention ranking, product logic, world beliefs, benchmark generation, or role topology.

### 4.2 Federated substrate

Each authoritative domain owns a transaction boundary and an outbox. A shared envelope v2 carries at least:

`schema_version`, `event_id`, `event_type`, `occurred_at`, `recorded_at`, `cabinet_id`, `scope_kind`, the conditionally required `lane_id`/`project_id`, `producer`, `correlation_id`, `causation_id`, `idempotency_key`, `classification`, `payload_schema`, and payload or payload reference.

Legacy v1 remains accepted during migration. New v2 domains register their schemas locally; they do not extend the 91-type central registry. Transport may be in-process, SQLite/Postgres relay, Redis Streams, or signed federation. The envelope contract is independent of the transport. Safety-critical ordered ledgers stay single-domain; “federated” never means fragmenting one reader's required supersession history.

### 4.3 Temporal epistemic world model

The Cortex projection joins domain envelopes into bitemporal beliefs:

- entities, relationships, resources, capabilities, commitments, constraints, risks, hypotheses, and observations;
- valid time and recorded time;
- confidence and source trust;
- supporting and contradicting evidence;
- supersession without erasing history;
- as-of queries and counterfactual branches.

It is rebuilt from authoritative domains plus evidence. It never grants authority and never becomes the only copy of business state.

### 4.4 Causal objective/value graph

The objective graph replaces activity as the principal intelligence target. Captain-authored directions and constraints are immutable roots from the org's perspective: the Cabinet may propose interpretations and outcomes, but it never authors or hill-climbs its own direction. The graph represents:

- outcomes and constraints;
- causal hypotheses linking interventions to outcomes;
- leading and lagging evidence;
- dependencies, conflicts, opportunity cost, uncertainty, reversibility, and Captain-attention cost;
- observed results and counterfactual expectations.

Every causal edge is explicitly `hypothesized | observationally_supported | intervention_supported | falsified`, with confounding/selection assumptions and uncertainty. Observation may strengthen an association but cannot mark an intervention effective. A counterfactual is a prediction, never evidence of itself. No irreversible autonomous effect may rely solely on an observational edge.

OVI becomes one backward-compatible projection from this graph. Instruments remain trend evidence, never targets. The common objective IR is a small versioned semantic schema; existing mission/product compilers remain independent executables and adapters. There is no shared mega-compiler whose compromise can poison unrelated outputs.

### 4.5 Cognitive organs and scheduler

An organ package declares a universal contract: accepted inputs, produced outputs, namespaced domain operations, the single resolved constitutional effect/risk/undo descriptor, permissions, idempotency, state ownership, cost model, freshness needs, trigger policy, health proof, fallback, version, dependencies, and sunset. Domain operation ids live in the organ/domain manifest and never extend a central enum. During migration the current `ACTION_TYPES` classifier is a compatibility translator into the same enforcement result; after shadow parity it is retired or compressed, not kept as a parallel authority.

The cognitive scheduler is a pure planner over a versioned snapshot. It chooses proposed organ work using uncertainty, expected value of information, urgency, dependency readiness, marginal cost, failure history, and starvation bounds. Externally supplied hard ceilings bound compute, tool use, spend, Captain attention, and exploration. The scheduler cannot create objectives, grant capabilities, alter authority, execute effects, mutate its own weights, or declare its work successful. A separate dispatcher rechecks authority, idempotency, snapshot freshness, and remaining resource budget immediately before dispatch.

launchd remains the OS supervisor with fixed wakes and mechanically derived freshness floors; the scheduler never dynamically loads launchd jobs. It selects work inside those observed wakes, while real isolation boundaries remain separate services. Missing or corrupt scheduler state falls back to the fixed safe schedule and never implies permission.

### 4.6 Evolutionary Foundry

The Foundry consumes immutable trajectories, builds living public/private benchmarks, invokes a read-isolated frozen holdout, generates candidates, executes them in credential-free arenas, archives every lineage and failure, and submits eligible winners to the existing Gate.

Machine outcomes dominate LLM judgments. The live Cabinet is always a pinned champion; experiments never mutate the live champion in place.

### 4.7 Federation

Multiple Cabinets exchange signed summaries and proposals through explicit trust contracts. Federation defaults off. Messages are scope-minimized and replay-protected. Receiving Cabinets re-evaluate proposals under their own objectives, evidence, and authority. No Cabinet can inherit another Cabinet's Captain labels, grants, posture, trust ladder, or autonomy state.

## 5. Phase protocol — repeated for every implementation plan

Every phase is a separately landed program increment:

1. **Ground:** pin exact master SHA and CI; inventory current readers/writers, active waves, locks, and rollback paths.
2. **Plan:** write an exact implementation plan with invariants, file surfaces, tests, migration, observability, rollback, and deletions explicitly out of scope.
3. **Attack the plan:** independent architecture, adversarial, operations, and product-agnostic reviews; resolve every blocker or narrow scope.
4. **Tests first where the contract is new:** include a negative control or mutant proving each gate detects the intended defect.
5. **Implement in a clean worktree/clone:** never the live checkout; no germline workaround; docs track code.
6. **Review the implementation:** independent fresh-context review against the plan and masterplan, then fix and re-run the focused suite.
7. **Integrate:** merge current master without force, run tree-reading gates after commit, push, and inspect every CI job.
8. **Prove reality:** run crash/replay/simulation or live shadow tests appropriate to the phase. Record measured evidence and rollback rehearsal.
9. **Advance or stop:** the next phase opens only when every exit gate is green. A failed gate causes a fix or a rollback, never a lowered threshold.

Each phase review must include a `reuse | extend | compose | retire | new` disposition for every proposed component. A `new` disposition carries evidence that no existing joint can meet the contract without violating a boundary. This prevents architectural synonym churn from masquerading as progress.

That disposition is machine-forced rather than remembered. `cabinet/config/cognitive-architecture-contract.yml` carries an `expansions` list beside its temporary allowances, and the census holds it to a bijection against the member sets in `cabinet/config/architecture-baseline-sets.yml`: per class, `observed - baseline` must equal the registered members exactly and disjointly. A net-new member needs an expansion row, which is schema-refused unless it carries the member id, the gate date, at least two distinct blind arms, the written adjudication, the merge it refuted as a resolvable `path::symbol`, the consumer that will read the output, and its provenance. Nothing in it asks merely whether a file exists, because `touch` passes that.

This paragraph used to end by claiming that an allowance "cannot buy a net-new member of any set the census can name". That was false, and an adversarial review falsified it by execution on 2026-07-27: a genuinely net-new production module landed at `ok=True` with no expansion row, paid for with one line in the baseline file plus an ordinary allowance row. Membership and count are two separate costs and the sentence named only the count. Since that date no `temporary_allowances` row may name a bijection class at all — it is refused when the contract loads, with the rows already live grandfathered by exact `(phase, budget, additional)` triple in the census source so none of them can be edited upward or copied. A bijection class's count now grows only by raising its `maximum` visibly. A baseline name the tree does not carry is also red, so an inventory cannot be pre-loaded in one commit and consumed in a later one. The channel this paragraph named as still open until 2026-07-28 — a baseline line added in the same commit as the file it names, which removes that file from the surplus where the bijection cannot tell the difference — is machine-refused since that date, by a different instrument, because the census is gitless and can never have a "before" to compare against: `cabinet/scripts/baseline-set-ratchet.py` reads the baseline as committed at the merge-base and at HEAD and refuses a net addition (added beyond *credited* removals, per class) and any path addition git does not score as a rename of something removed in the same diff, so a paired rename stays green and the purchase goes red. What that ratchet does *not* close, named rather than left to read as covered: a same-commit swap inside a symbol-shaped class (an event type, an action type, a service row), where the member is an edit inside a file and git has no rename to score — it costs deleting a live member, it cannot grow the count, and it is caught by reading the diff.

Each detailed plan must define a maximum acceptable regression relative to a freshly measured baseline. No phase may borrow a future phase's promised mitigation to declare itself safe. Every additive runtime component also names the permanent surface it composes/retires in the same phase or carries a dated temporary allowance and deletion gate; structural compaction is incremental, not deferred wholesale.

The program also has a capacity law: it may not pre-empt fresh-hatch/public-launch blockers, live evidence generation, or the Captain-label cadence that calibrates existing autonomy. Architecture work proceeds in isolated lanes and earns continuation through measured value.

## 6. Phases and exit gates

### Phase 0 — Executable architecture and intelligence contract

Land the masterplan, a machine-readable architecture contract, a deterministic census, and an immutable trajectory contract. Runtime behavior remains unchanged.

**Exit:** census reproduces the pinned baseline and makes the Phase-0 2-module/1,256-line allowance explicit; over-budget mutants fail across central vocabularies, services, coupling, production modules/lines, named compilers, and duplicate event writers; malformed/Goodhart-prone trajectories fail; gitless and Linux-compatible tests pass; the measured 2,050-test targeted floor (2,040 compatibility plus 10 extension-gate tests, with five skips) is preserved; layer separation, docs sweep, golden evals, export/null-hatch, and CI are green. Rollback follows an explicit inverse manifest: new implementation files are removed, while operative ledger/plan rows remain append-only with a supersession/rollback note; compatibility gates remain unchanged.

### Phase 1 — Envelope v2 and one transactional-outbox pilot

Implement the transport-independent envelope v2, schema registry interface, domain transaction/outbox primitive, and relay semantics. Select one unlocked, low-blast authoritative domain only after its phase plan compares at least two candidates, including the canonical tasks domain and one local-only alternative. Run the pilot in mirror mode before cutover. Do not split the consequence/autonomy ledger in this phase; separately harden its append/torn-tail behavior if the detailed plan confirms that defect.

**Required simulations:** crash before commit; crash after state+outbox commit; relay death before send; external success before ACK; duplicate delivery; 100 concurrent idempotent writers; stale/out-of-order replay; transport partition; poison payload; tenant/cabinet spoof.

**Exit:** no lost acknowledged mutation, no externally duplicated effect under the adapter's idempotency contract, deterministic replay hash, legacy behavior parity, bounded p95 regression measured against the pilot baseline, and a one-command pointer/adapter rollback. No other domain migrates in this phase.

### Phase 2 — Shadow temporal world model

Build a disposable Cortex projection from v2 plus explicit legacy adapters. It supports as-of queries, contradictions, supersession, provenance, uncertainty, and Cabinet/lane/project fences. It has no action or authority dependency.

**Required simulations:** delete/rebuild from zero; replay shuffled/duplicated input; late-arriving correction; conflicting sources; source deletion/purge; cross-Cabinet injection; as-of fence; corrupt projection recovery; event gap.

**Exit:** identical canonical hash after three rebuilds; correct as-of answers on seeded histories; contradictions are preserved; unknown remains unknown; cross-Cabinet reads fail closed; projection loss cannot lose authoritative data; zero calls from authority/action code; shadow query latency and storage envelope measured.

### Phase 3 — Causal objective graph and compiler federation

Define the common objective IR schema and causal/value graph. Compile existing outcomes, work graph, product specs, and mission inputs through separate, blast-isolated adapters. Keep current mission output byte-stable until parity is established. Recast OVI as a compatibility view. The graph cannot edit Captain directions, feed a scalar optimizer, or treat an instrument as a target.

**Required simulations:** cyclic dependencies; mutually exclusive goals; impossible constraint; stale evidence; intervention that improves a proxy but harms the objective; confounded correlation; Simpson's paradox; confident counterfactual without intervention evidence; missing product adapter; generic non-software Cabinet; counterfactual replay.

**Exit:** three heterogeneous fixture Cabinets compile without product/person tokens in framework code; current mission fixtures preserve behavior; seeded proxy gaming is rejected; every recommendation cites objective/evidence/uncertainty; OVI compatibility view matches baseline where inputs overlap; graph can be rebuilt from authorities.

### Phase 4 — Organ contract and need-driven cognition

Extend extension/capability packaging into a universal organ contract by building on the existing action/risk/undo enforcement joint. Introduce namespaced domain operations that resolve through declared capabilities into a smaller constitutional effect/risk/undo descriptor; keep legacy `ACTION_TYPES` only as a shadowed compatibility translator until parity permits retirement. Version the trajectory schema so it preserves the namespaced domain-operation identity separately from the constitutional enforcement descriptor; never overload `action_type` or create a second authority algebra. Introduce a deterministic scheduler in shadow, then pilot it over a bounded set of existing periodic cognitive services. OS/security boundaries and fixed watchdog floors stay separate; reasoning habits compose inside the modular runtime.

**Required simulations:** burst load; quiet period; stale organ; cost spike; organ crash; dependency failure; starvation; contradictory organs; unavailable MCP; unauthorized effect; forged scheduler decision; budget overflow; self-prioritization; stale-snapshot dispatch; scheduler restart/replay.

**Exit:** shadow decisions are deterministic from the same snapshot; no high-urgency starvation; forged or stale decisions and budget overflow fail at dispatch; unauthorized effects never dispatch; three non-software fixture Cabinets declare granular operations without adding a central action type and resolve to the same single enforcement decision; versioned trajectories retain both operation identity and the one enforcement descriptor without granting operation names authority; the legacy classifier is demonstrably only a compatibility adapter; outcome/evidence parity holds; total tool/MCP activation, latency, and cost do not regress beyond the measured bound; at least one permanent service is retired or composed for every new enabled scheduler component.

### Phase 5 — Foundry E1/E2/E3 in shadow

First make the existing Gate capable of an honest PASS without weakening it: land the unprivileged sandbox verify harness, wire the existing regression corpus into admission, and prove credential-free isolation. Only then implement the ratified evolution package: trajectory archive, candidates, generator, arena, scorers, league, benchmark factory, and frozen holdout interface. Private benchmarks expose aggregate results, not cases; the frozen holdout exposes only an oracle-attested aggregate receipt, never cases, reusable fingerprints, or per-case results. Start with prompt/retrieval/skill/memory-policy candidates. No live promotion.

The league does not open merely because its code exists. It requires a declared minimum corpus of real, cutoff-fenced trajectories and Captain labels for every promoted stratum, with the minimum derived from the existing fidelity/evolution contract and recorded in the Phase-5 plan. Synthetic cases can test plumbing and known mutants; they cannot establish live fitness.

**Required simulations:** at least 20 candidates; known-bad candidate; known-good small improvement; judge-only winner; proxy-overfit winner; holdout leakage attempt; credential/network escape; nondeterministic scorer; corrupt archive; lineage rollback; cost explosion.

**Exit:** ranked archive preserves every lineage/failure; known-bad loses; judge-only cannot promote; proxy-overfit is caught by private/holdout divergence; arena has no live credentials or writes; machine outcomes dominate; benchmark cases carry cutoff/leakage metadata; E1 produces no live mutation.

### Phase 6 — Champion membrane, canary, and earned promotion

Add an atomic champion pointer, immutable candidate artifacts, canary allocation, breaker, rollback, and the thin promotion shim into the existing Gate. Begin with a reversible text-genome class only.

**Required simulations:** power loss during pointer swap; canary crash; evidence verifier red; regression after promotion; concurrent promotions; stale candidate; Ring-0 diff; holdout regression; Captain veto; rollback under load.

**Exit:** no partial champion state; old champion remains runnable; first regression automatically returns traffic to the incumbent; Ring-0 and architecture changes are refused; every promotion has evidence/lineage/cost/rollback receipts; at least three text-genome generations reproduce public gains on the frozen holdout before architecture search can unlock.

### Phase 7 — Mandatory structural compaction

Remove superseded central registries, duplicate authoritative writers, permanent services, compatibility adapters, and unnecessary framework surface only from a proven deletion ledger. Collapse the three-sink event-emitter authority ambiguity one domain at a time; retire/compress legacy `ACTION_TYPES` after operation-to-effect shadow parity; preserve every real security/fault boundary.

**Required simulations:** zero-reader falsifier; fallback-use injection; parity mismatch; restore after deletion; event-writer crash/replay; legacy action-adapter rollback; compiler removal with heterogeneous fixtures; service retirement under missed wake; layer-debt reintroduction; clean-room hatch from the compacted tree.

**Exit:** each deletion has zero-reader evidence, shadow parity, fallback telemetry quiet for the declared window, and a rehearsed restore; the Phase-0 temporary allowances are gone; central event/action vocabularies, enabled services, coupling debt, production modules/lines, named compilers, and duplicate event-writer sinks all end below their base maxima; the public egg remains generic and every retained permanent service has a named fault/security justification.

### Phase 8 — Optional capability-safe federation

Only after the single-Cabinet architecture is smaller and proven, enable signed, proposal-only cross-Cabinet summaries behind explicit opt-in. Federation is an optional distribution capability, not a prerequisite for an intelligent Cabinet or an excuse to delay compaction.

**Required simulations:** forged peer; replayed message; peer compromise; schema skew; network partition; conflicting Cabinets; attempted autonomy/grant transfer; compatibility rollback; clean-room multi-Cabinet hatch.

**Exit:** spoof/replay/isolation tests fail closed; receiving Cabinets independently evaluate every proposal; no autonomy state, Captain label, private memory, grant, or holdout case transfers; every peer link is independently revocable; local authority and operation continue through partition.

## 7. Anti-Goodhart scorecard

No scalar score may promote a candidate or phase. The scorecard is a vector:

- mission/outcome evidence and counterfactual delta;
- correctness, calibration, and uncertainty honesty;
- Captain edits, reversals, vetoes, and attention consumed;
- independent machine outcomes and failure recovery;
- latency, token/tool cost, and external spend;
- safety/refusal accuracy and blast radius;
- cross-domain reuse and launcher/product leakage;
- proxy-vs-private-vs-holdout divergence;
- coverage, freshness, and missing-evidence rate;
- complexity: enabled services, central vocabularies, coupling debt, duplicated authoritative writes, and compatibility surface.

Promotion requires independent floors on all applicable dimensions. Easy work cannot compensate for a failure in a high-risk stratum. Missing evidence is `unknown`, never success.

## 8. Migration and deletion law

Every migrated domain moves through:

`legacy authority -> v2 mirror -> parity monitor -> new authority with legacy projection -> compatibility soak -> legacy reader deletion -> legacy writer deletion`.

The deletion ledger for each surface records owner, readers, writers, baseline, mirror hash, cutover pointer, rollback command, last fallback use, and retained archive. No big-bang migration and no dual-authority period are allowed.

## 9. Program-level stop conditions

Stop and repair before continuing if any phase:

- weakens Ring-0, evidence, privacy, or authority boundaries;
- requires a single global database/bus/compiler to proceed;
- changes live behavior before its shadow gate;
- cannot rebuild projections from named authorities;
- collapses independent hook, filesystem, OS-sandbox, or broker enforcers into one failure domain;
- cannot roll back without data surgery;
- improves a proxy while independent outcome evidence regresses;
- increases Captain attention, cost, or permanent-service count without a measured outcome gain and an explicit sunset;
- hardcodes a Captain, product, industry, project, officer, or machine into framework code.

The program is complete when the Cabinet learns faster and generalizes farther while owning fewer permanent concepts and services—not when every box in this document has produced more code.
