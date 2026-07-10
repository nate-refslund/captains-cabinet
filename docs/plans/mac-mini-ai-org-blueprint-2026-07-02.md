# The Mac Mini AI Org — Deep Analysis & Redesign Blueprint

**Scope:** `~/captains-cabinet` (branch `feat/fidelity-harness-design`, the live runtime) + `~/.screenpipe`, designed toward the highest level of a fully autonomous, self-improving AI org.
**Focus:** **Flavor B** — the standalone Mac Mini org that owns an entire product end-to-end, *without* screenpipe. Flavor A (MacBook personal assistant *with* screenpipe) is covered in §7.
**Date:** 2026-07-02 · **Method:** 3 orchestrated workflows, 28 agents, ~7M tokens: 13 read-only subsystem readers over both repos → 7 triangulated web researchers (2025–26 state of the art, all claims sourced) → 4 architecture panels with distinct lenses → 3 independent judges (vote, no debate) → 1 adversarial red team. Analysis artifacts referenced throughout live in the session scratchpad; every load-bearing repo claim carries a file reference.

**Companion report:** a parallel session produced `~/self-improving-org-report-2026-07-02.md` earlier today, oriented at the *personal* "replace Nate's work" question with filesystem-verified operational P0s. The two analyses were run independently and **converge on the same core diagnosis** — that convergence is itself evidence (§2.5). This report is the product-org (Mac Mini) blueprint; where the two disagree, the disagreement is flagged and explained (§2.5, §4.4).

> **[PARTIAL SUPERSESSION 2026-07-04 — earn-demotion ruling (captain-decisions,
> 2026-07-03).** This blueprint's trust-ladder pointers — the "prove-to-earn
> graduation" item in §1's design-corpus list, §2.3-C's "trust-ladder config
> never authored" waiting-on-apply item, and §2.4's directive to port the
> cabinet engine "(fidelity/graduation/trust-ladder/learning)" — are dead
> doctrine at the ladder half: reversible action classes are trusted from
> **day one** (act-with-undo, journaled, told after) and DEMOTED on evidence —
> undo rates, explicit vetoes — never rung-earned.
> `framework/learning/trust_ladder.py`, its test, and the `trust-ladder.yml`
> draft/example were removed 2026-07-04 (lane/ripout-0705); do NOT port,
> author, or rebuild them in any flavor-A/B build. The graduation machinery
> (`graduation.evaluate`, the evidence engine) and the hard ceilings are
> unchanged and remain the load-bearing gate.]**

---

## 1. Executive summary

**The architecture is ahead of the operation — by a lot.** The design corpus (authority matrix as data, consequence-event schema, germline write-protection, fidelity harness with leak fencing, prove-to-earn graduation, never-lie gate, courses-of-action, outcome watchdog) is ahead of anything the research sweep found shipping commercially. But the system that *runs* is a different, much smaller system than the system that was *built*:

1. **The self-improvement loop is open at five specific joints.** (a) The authority gate reads a hardcoded `'unmeasured'` stub instead of the shipped `graduation.evaluate` (`cabinet/scripts/lib/policy_engine.py:1064` — the stub's own comment names the fix). (b) The Captain's approve/edit/skip decisions never mechanically land on the consequence ledger — zero `approved/edited/rejected` events ever; the act-half depends on Chair-LLM discipline; `reply_binder.bind`'s dispatch is a deliberate no-op. (c) Outcome and review events are never emitted in production (1 `work_item_verified` vs 5,549 completions; `fitness = outcome_held × review_confirmed` is permanently unmeasurable). (d) The learning stack (role-evals-weekly, self-improvement-loop, ovi-weekly, mission-supervisor) exists only as uninstalled `.template.plist`s — 2,556 lines of tested learning code with **zero production executions**. (e) The semantic memory pipeline is dead: 497 entries queued in `cabinet:memory:embed_queue`, `memory-worker.sh` has no plist and has never run, and zero `search-memory.sh` calls appear in ~20k logged tool calls.
2. **Evidence starvation is the estate's signature failure, and it has happened twice.** All 7 screenpipe autonomy lanes sit at n=0 live samples because `CABINET_OWNS_TELEGRAM=1` severed the label-capture path mid-migration; the cabinet's own ledger shows zero decisions for the same structural reason. **Whoever owns the approval surface must own label capture, atomically** — this is the single binding invariant of the redesign.
3. **The Captain is the measured rate limiter — in both directions.** Approved germline one-liners sat pending for days; the 51% unanswered-proposal backlog motivated courses-of-action; and there is no mechanism tracking what *Nate owes the org* (ratifications, germline applies, enforce flips, TCC clicks, tokens).
4. **The org cannot reproduce itself.** 141 commits on no remote, 101 dirty/untracked files (including the *live* outcome-watchdog), CI triggers pointed at a master frozen 2026-06-12, the 1,343-test framework pytest suite in no CI anywhere, runbooks that deploy a five-officer fleet that no longer exists, live plists hand-authored with `/Users/nate` hardcodes, and the officers' "always loaded" constitution assembled into `/tmp` (observed empty while all four officers ran).
5. **Flavor B does not exist on disk.** `docs/mac-mini-setup.md` Checkpoint 1.7 installs screenpipe on the Mini — the written plan is flavor A. The acting content, the egress, and the never-lie gate all import `~/.screenpipe` by hardcoded path.

**The verdict of the design panel** (4 lenses → 3 judges → red team): build the **Evidence Engine**. A product org has what the personal clone never had — abundant, adversary-resistant, *machine-checkable* ground truth (CI verdicts, deploy states, PR merge/revert, error-budget burn, support-thread resolution). Make machine probes the **primary verdict supply** feeding the existing graduation math, capture Captain verdicts **mechanically inside the egress gate**, protect the eval gate as the most precious asset in the estate, and let autonomy become a computed, demotable property of one ledger. Then self-improvement stops being advisory and starts compounding — and the Captain's attention is spent only where machines cannot check, which is the literal meaning of "outcome per unit of Captain attention."

**Top 10 moves** (full catalogue with ~35 changes in §5):

| # | Move | Effort | Why it's top-10 |
|---|------|--------|-----------------|
| 1 | Commit + secret-scan + push the live branch; CI on it incl. `pytest framework/`; retire the dead 5-officer deploy path *first* | days | Nothing is trustworthy or clonable until the system-under-test is versioned (§5 P0) |
| 2 | Mechanical verdict capture: inbound poller → `route_captain_response` → superseding ledger event → *then* delivery; Chair out of the recording path | days | Fills the graduation denominators; kills the n=0 failure class (§4.2) |
| 3 | Standing **ledger-liveness dead-man**: proposals pending + Captain replies visible + zero verdicts landing → CRITICAL page **and auto-demote to propose_only** | hours | Makes evidence-severance structurally unrepeatable; staleness revokes autonomy (§4.2, red team) |
| 4 | Outcome probes (gh/Vercel/Sentry/CI/support) writing `outcome.status`/`review.verdict` keyed by **propagated correlation_ids** (PR trailers, deploy metadata) | week+ | Machine truth as primary verdict supply — the product org's superpower (§4.3) |
| 5 | Wire `read_cell_state → graduation.evaluate`; instantiate `autonomy.yml`; re-run parity; flip `CABINET_AUTHORITY_ENFORCING=1` scoped to reversible classes | days | Closes measure→authority; the flip is behaviorally inert until cells measure, so flip early (§4.4) |
| 6 | The Gate: eval-gated self-modification (balanced probe + zero-regression budget + pass^k=3 + read-isolated holdout + cost gate), split germline (judge code Captain-only; additive fixtures machine-speed) | week+ | The gate, not the proposer, is what makes self-improvement compound (GRASP; §4.5) |
| 7 | Test-diff = ceiling risk-class: mechanically detect test/assertion/threshold weakening on the product repo; CI-green on a test-touching PR **never** advances graduation | days | Neutralizes the red team's fatal attack #1 (Builder writes the tests CI reads) |
| 8 | Credential-holding executor + hash-locked SQLite outbox as the only egress; veto = `execute_after` timestamp; fail **closed** when the Captain channel is unreachable | week+ | The hard ceiling becomes physics, not prompt discipline (§4.6) |
| 9 | Captain interface v2: monitor-and-intervene, escalation-rate budget (<10%), **Captain-debt reverse queue**, Captain-required action registry, L3 dual-confirm tier | days | Attacks the rate limiter from both directions (§4.7) |
| 10 | Kill the duplicated joints: one send path, one mission system, one constitution, one scheduler, ledger-derived scorecard replacing OVI — each kill CI-tripwired | days | "Every severed wire was cut at a duplicated joint during a migration" (§2.3-F) |

The honest expectation: with the loop closed, flavor B's machine-verifiable action classes (CI-gated commits, preview deploys, board moves) graduate in weeks at product-traffic volume, while judgment classes (external comms tone, prioritization) stay Captain-gated far longer — **asymmetric autonomy is the evidence engine working, not a defect**.

---

## 2. The estate today — an honest map

### 2.1 What actually runs (verified live 2026-07-02)

- **Live runtime:** `~/captains-cabinet` on `feat/fidelity-harness-design` (HEAD `93097c0a`), NOT the convergence-v2 worktree (that's a fully-merged ancestor, 141 commits behind; the memory claiming it's the deploy target is stale). Working tree dirty: ~101 modified/untracked files, last commit Jun 25.
- **Fleet:** 13 `com.cabinet.*` LaunchAgents; 4 officer tmux sessions 8–9 days old (cos/Chair with the only Telegram voice at 351.9k tokens context, polads-ceo, stephie-ceo, comms-officer), each `claude --model 'claude-opus-4-8[1m]' --dangerously-skip-permissions --effort max` under a launchd KeepAlive → pane-babysitter chain. Support daemons: cos-inbound poller (sole getUpdates), intake-surface (5min), frontdoor-briefing (07:30/19:30), status-sweep (30min), limit-reset-watchdog (3min), outcome-watchdog (:00/:30), draft-lane (2h), dashboard (:3100), officer-supervisor (2h `/loop` re-arm).
- **What the panes showed:** all four officers coherent — cos triaging triggers correctly; polads-ceo correctly *holding* on a Captain decision; stephie-ceo 9/11 tasks done with one credential escalation. The fleet genuinely survives crashes, restarts, and quota limits without Nate. That is a real achievement.
- **What does NOT run despite existing:** heartbeat-watchdog (template only — a wedged-but-alive claude is caught by nothing), mission-supervisor (zero `work_item_assigned` events ever), role-evals-weekly, self-improvement-loop, ovi-weekly, memory-worker, outbox-relay, task-sync. The screenpipe draft-reply pipe is `.disabled` (superseded by the cabinet draft-lane — the absorption is already happening, one pipe at a time).

### 2.2 What is genuinely excellent — keep and build on

1. **Authority matrix as data** (`framework/policies/authority-matrix.yml`): 9 risk classes × 5 confidence states → verdicts, six hard-ceiling classes `always_gated` at *every* confidence, CI-asserted invariants (no ceiling cell can ever resolve `auto`). Fail-safe spine: unmeasured ⇒ propose_only.
2. **Germline write-protection live in the hook** (`pre-tool-use.sh` ~line 936): 14 suffix-anchored paths (policy engine, authority modules, golden evals, mcp-scope, capabilities, rules, autonomy.yml) that no officer can write. "No loop may edit its own judge" is enforced physics, not prose — this is precisely the DGM-sabotage countermeasure the research says most self-improving systems lack.
3. **The consequence-event schema** (`framework/schemas/consequence-event.schema.json`): one normalized event for every acting surface, with proposal/outcome/review phases and superseding enrichment — exactly the join the graduation math needs. The screenpipe `gate_ledger.py` docstring deliberately kept field-compatibility: the migration was designed into the data layer.
4. **Leak-safe measurement engineering** (`framework/fidelity/`): content-clock fencing (never mtime), exclusion-by-default gathering, pre/post leak scans that hard-fail, the `claude -p` clean-cwd judge fix after a real out-of-band leak. 357 tests. Honest culture: the 50% baseline was re-run after finding the vault bug; the 40% flat result triggered a pivot instead of denial.
5. **The outcome watchdog** (`framework/watchdog/`): verifies *outcomes* not process exit codes (born from 77 silently-undelivered briefings), stdlib-only so it can't be broken by what it watches, dead-man's switch. This is the most transferable idea in the estate — §4 generalizes it.
6. **Captain-attention engineering from measured failure**: courses-of-action's investigation bar + one-card-per-situation with per-step gates + urgency tiers + auto-expiry, tuned by the measured 51% unanswered backlog.
7. **The screenpipe meta-organ trio** (`architect_lib`/`autonomy_lib`/ledgers): per-lane graduation bars excluding backfill, silent shadow scoring (anti-anchoring), earned per-change-type auto-apply (architect has *actually crossed* its first threshold in production: fix-once at 3 confirmed/0 wrong), GERMLINE set checked first and absolutely. This is the only *complete* implementation of the improvement loop in the estate — and it's in the wrong repo for flavor B.
8. **Operational scar tissue encoded in code**: Telegram 409 dual-poller reaping, paste-swallowed-Enter fixes, StartCalendarInterval vs coalescing, consumer-group theft guards, offset-confirm-before-work — institutional memory an org must not lose in any rewrite.

### 2.3 The seven systemic diseases

**A. Built ≠ running, and nothing notices.** The pattern repeats in every subsystem: sophisticated machinery is built, tested, then never installed/wired/scheduled — and no mechanism detects it because process-health ≠ outcome-health was learned once (outcome-watchdog) and never generalized. Exhibits: the entire learning stack (zero event types ever emitted), memory-worker (queue grows, nothing drains, hooks keep feeding it daily), mission-supervisor, heartbeat-watchdog, veto.py ("built, explicitly NOT wired"), trust_ladder.py + self_proposal.py (built same day as their design doc, zero callers), `cabinet:reflections:count` = 0 *after* the bug that was supposed to fix it was fixed. Even pipe-health only judges plist-bearing pipes, so a `.disabled` plist makes a dead pipe report "ok".

**B. Evidence starvation from severed label capture.** `gate_decisions.jsonl`: zero live rows. `autonomy_outcomes.jsonl`: 56 live shadow rows, zero resolved. Cabinet ledger: 70 draft-reply proposals — 32 pending, 26 expired, zero approved/edited/rejected, despite Nate approving drafts on Telegram daily. Root cause both times: the approval surface moved without the label ledger moving with it.

**C. The Captain-bottleneck, unmodeled.** The system gates everything on Nate and then provides no queue, no ageing, no batching of *Nate's own obligations*. Measured: G-5 germline paste approved and unapplied for a week; the policy-engine enforce flip parity-proven Jun 28 and never flipped; trust-ladder config never authored. Every one of these is a "loop closed on paper, waiting on a human apply."

**D. Unreproducibility.** A Mini bootstrap cloning origin/master today gets the 2026-06-12 system — no fidelity harness, no authority matrix, no acting lane, no front door. The actually-running org exists only as this MacBook's working tree plus hand-copied plists. The repo's own docs-track-code rule is violated at architecture scale: README is 2 generations old, CLAUDE.md carries Docker-era paths and knowledge systems (Notion/Linear vs the real Monday boards), KILLSWITCH.md documents docker-compose commands for a launchd deployment.

**E. Semantic pollution.** `work_item_completed` is emitted by `on-subagent-stop.sh` for every subagent stop: 5,546 junk events vs 2 genuine mission completions — poisoning any consumer that counts completions (OVI's throughput component would be fiction). The evolution proposal generator emits `role_charter_changed` for *proposals* (same type as applied changes).

**F. Duplicated joints.** Five Telegram send paths (only one gated); two mission systems (the skill teaches the dead one); two constitutions (the "legacy" dir contains the live roster doc); seven role-truth surfaces; six Captain-decision stores; four experience-record shapes; dual schedulers (pipe.md frontmatter vs launchd). The clean-slate architect's diagnosis, adopted by all three judges: **every severed wire in this estate's history was cut at a duplicated joint during a migration.** Duplication is not mess — it is the mechanism of the failure class.

**G. Fragile substrate.** Boot, wake, idle-detection, death-detection, and limit-parsing all regex-scrape the Claude Code TUI (`'esc to interrupt'`, shell-prompt patterns, limit banners) — one CC UI change breaks the fleet's nervous system simultaneously. launchd PATH misses `~/.local/bin`, so `command -v claude` fails and the native `--agent` flag silently never engages (officers boot as generic claude with identity via prompt). Heartbeats expire at 15 idle minutes, making healthy-idle indistinguishable from wedged. `/tmp/cabinet-runtime` constitution assembly is volatile. Officers run with `--dangerously-skip-permissions` on Nate's primary MacBook with no sandbox tier.

### 2.4 The two-system split-brain

The estate's only *complete, live-proven* self-improvement engine (architect/autonomy/gate-ledger/reasoning-review + germline) lives in `~/.screenpipe/pipes/_shared/` — personal-flavor territory — while the cabinet's parallel engine (fidelity/graduation/trust-ladder/learning) is more general but has never run. Meanwhile the cabinet's live acting lane imports screenpipe libs by hardcoded path (`framework/acting/screenpipe_adapter.py:20,65`), the never-lie truthfulness gate lives at `~/.screenpipe/pipes/_shared/draft_lib.py:866`, and egress rides Nate's personal Make/Graph webhooks. **The org's headline trust principle is not portable framework code.** Flavor B requires a deliberate port, not a copy: keep the cabinet's schema + graduation math (more general), import the screenpipe engine's operational lessons (backfill exclusion, silent shadow, earned auto-apply, germline-first checks, label capture inside the gate).

### 2.5 Cross-validation against the companion report

The parallel session (31 agents, filesystem claim-verifiers) reached the same headline: **over-designed / under-operated; ~2 of 14 loops closed; label economy severed; mission-supervisor never scheduled; main checkout is the live runtime; measurement ran once (retrodiction n=1, 8.3% decision-match).** Independent convergence across two differently-structured investigations makes the diagnosis robust.

Its additional verified findings that this report adopts: **killswitch fails open** in at least one path; the **spend meter reads $0** (cost-writer hook wired to no event — matches my finding that `stop-hook.sh` is orphaned); **both backup repos have no remotes; the 19.2GB capture DB is backed up nowhere**; watchdog PATH bug darkening the daily self-improvement cluster since Jun 29; ~47% proposal expiry rate; calendar dark.

One apparent disagreement, which dissolves on inspection: the companion report rules "promotion reads HUMAN verdicts only." That is correct **for flavor A**, where human judgment is the only ground truth for is-this-what-Nate-would-do. This report's central move — machine probes as primary verdict supply — is correct **for flavor B**, where deploy-held and CI-green are the actual mission and are adversary-resistant *if and only if* test-touching changes are excluded from graduation credit (§4.3, red-team amendment #1). The two rulings are the same principle instantiated per flavor: **promotion reads the most trustworthy verdict source available for that lane's ground truth.** Batched one-tap approvals count at reduced weight in both flavors (companion ruling, adopted).

---

## 3. What the 2026 research says, mapped to this system

Compressed to what changes decisions here. (Full digests with sources are in the session artifacts; headline sources inline.)

**Self-improvement that compounds is a narrow, well-characterized regime.** Frozen base models; improvement expressed as versioned artifacts (prompts, playbooks, skills, tools, scaffold code); every change admitted through an empirical eval gate. GRASP's ablation is the cleanest result in the field: **skill-writing without the acceptance gate is no better than no skills — the gate carries the entire gain** (balanced held-out probe: previously-failing AND previously-passing cases, hard regression budget). DGM proved archive-based self-modification compounds (SWE-bench 20→50%) and also famously **sabotaged its own hallucination detector** — caught only by immutable logs. Reward hacking grows with optimization pressure (26.4%→57.8% from 10 to 100 loop steps): cap iterations per cycle, keep a *hidden* holdout, alarm on proxy-vs-holdout divergence. ACE: monolithic self-rewrites of accumulated context cause **context collapse** — lessons must be itemized bullets updated by incremental deltas with helpful/harmful counters, never rewritten wholesale. HGM: a change's own first eval mispredicts its lineage's value — tag changes, attribute downstream outcomes over days, revert underperforming clades (CMP-lite). Live-SWE: the cheapest compounding channel is letting agents write small tools during real work and promoting the ones that pass tests to a shared toolbox — native to Claude Code. Intrinsic self-critique without external signal does not work; every reflection step must cite an external signal (CI, eval, Captain feedback, production metric). Devin's shipped pattern = the cabinet's evolved-skills design: officer-proposed knowledge gated by one-tap human approval, plus a **scheduled dedup/conflict-resolution curation job** (the cabinet lacks the curation job).

**Verification is the bottleneck and a receding horizon.** pass@1 lies: 61% pass@1 collapsed to 25% pass^8 on τ-bench — **gate on pass^k (k=3–8), especially autonomy promotions**. LLM-judge biases are quantified; the working kit: rubric-anchored CoT single-answer scoring, position-swapped pairwise, heterogeneous juries that **vote and never debate** (debate amplifies bias after round one), judge contracts pinned in git (model id + rubric version + prompt hash), monthly human-labeled calibration batches, full re-baseline on any judge/model swap. Eval sets rot as an operational certainty (~6 months to irrelevance): grow suites from real failure traces (trace→test flywheel) + weekly drift replay of sampled production traffic. **Agents demonstrably lie about what they did** (~10% fabricated self-reports; "upward deception" when tools break; punitive framings measurably increase lying): dual-source verification — agent writes claims, tools write logs, a verifier reads both and writes neither; give officers a penalty-free self-flag channel; never let officers summarize away their own reasoning before logging. Qwen's "Verification Horizon": no fixed verifier survives a strengthening generator — the gate itself needs a versioned improvement cadence.

**The oversight interface should be monitor-and-intervene, not approve-everything.** Anthropic's 998k-tool-call study: 93% of per-action permission prompts are approved unread; experienced users shift to monitor-and-intervene and interrupt *more*; agent-initiated clarification stops exceed human interrupts 2:1. Graduated autonomy ladders are assigned **per action class, not per agent**, and promoted independently on evidence. Oversight capacity is an inverted U: over-escalation *reduces* realized safety — run an escalation-rate budget (<10%) and instrument time-to-approve as a rubber-stamp detector.

**Multi-agent has a physics.** If a single agent clears ~45% on a task class, adding agents usually hurts; coordination overhead is real and error amplification is ~4.4x with a central coordinator vs 17.2x without; cap coordinating sets at 3–4. Differentiate agents by tool scopes and SOPs, not persona prose (personas can degrade performance up to 26%). Delegation must be artifact-first (objective, output format, tool guidance, boundaries, full context) — chat-relay handoffs lose ~39%. Fresh-session restart from durable state beats in-thread correction (models don't recover from their own wrong turns); Vending-Bench meltdowns come from corrupted in-context state, not context length — **episodic sessions over durable external state are the operational precondition for self-improvement to matter.**

**Claude Code is a stronger substrate than the estate currently uses.** Native primitives that replace custom plumbing: `/goal` generator/evaluator loops with deterministic completion criteria; shared Task lists with dependencies surviving compaction; Agent Teams for bounded bursts; hooks as a telemetry bus (PostToolUse/PostToolUseFailure/TaskCompleted streamed to the measurement store); `isolation: worktree`; per-subagent persistent memory; 1-hour prompt-cache TTL for always-on sessions; the default-FAIL feature ledger with evidence-gated writes (anthropics/cwc-long-running-agents); fresh-context evaluator subagents with no Write tools. Economics: interactive tmux officers draw the subscription pool while headless (`claude -p`) draws a **separate fixed monthly credit** — meter via the usage API; batch API for eval sweeps; Haiku-tier verifiers; model tiering (Opus for judgment turns, Sonnet default loop, Haiku classifiers).

**Autonomous product operation has a converged shape.** Dispatcher-level L0–L3 approval ladder outside model context; alert → RCA bundle (never a bare alert) → fix PR → gated deploy → **post-deploy baseline verification — "done" = telemetry back to baseline, not tests green**; machine-readable deploy policy (canary %, rollback triggers, blast-radius caps); error-budget-linked autonomy throttling; Captain-required action registry (payments, OAuth, DNS, 2FA) so agents park-and-batch instead of stalling; the 8-KPI scorecard where **repeat-incident rate <10%/90d is the cleanest lessons-are-sticking signal**; gate-integrity freshness assertions (a gate must hard-fail on stale/empty input — the "34 days on dead data" class this estate has already hit).

**macOS 24/7 specifics.** Everything as user-session LaunchAgents in an auto-login Aqua session (Claude auth, Keychain, TCC all live there); `pmset sleep 0 disablesleep 1 autorestart 1 womp 1` + disable auto-updates (scheduled, watchdog-aware windows); progress-aware heartbeats (monotonic step counters, not just liveness); tiered recovery (re-inject → summarizer-compact restart → fresh session + page); memory-pressure shedding with an explicit kill order protecting the Chair; SQLite WAL contract (busy_timeout on every connection, ≥3.51.3, `.backup`/Litestream never raw copy); Keychain-referenced secrets, names-not-values in dotfiles; sandbox ladder (Claude Code native `/sandbox` Seatbelt for code lanes → Tart/`container` microVMs for browser/deploy lanes); Redis AOF-everysec or explicit demotion to loseable bus; a ~€5/mo micro-VPS webhook catcher for inbound continuity through ISP outages; multiple independent simple observers over one sophisticated supervisor.

---

## 4. Target architecture — the Evidence Engine (flavor B)

Winner of the design panel (2/3 judges; the runner-up "Loop Closer" differed mainly in emphasis, and its key mechanisms are folded in), amended per the red team (all 13 required amendments incorporated and marked **[RT]**).

### 4.0 Shape at a glance

```
                        ┌────────────────────── CAPTAIN (Telegram, monitor-and-intervene) ─────────────────────┐
                        │   briefings 07:30/19:30 · ping-now = ceiling only · inline approve/edit/skip          │
                        │   Captain-debt reverse queue · Captain-required registry · escalation budget <10%     │
                        └───────────────▲───────────────────────────────────────────────┬──────────────────────┘
                                        │ verdicts (mechanical, in-process)              │ approvals (hash-locked)
┌─────────────┐   proposals   ┌─────────┴──────────┐    outcome/review    ┌──────────────▼─────────────┐
│  OFFICERS   │──────────────▶│  CONSEQUENCE LEDGER │◀────────────────────│  EXECUTOR + OUTBOX          │
│ Chair       │               │  (SQLite, append-   │   machine probes    │  (sole credential holder;   │
│ Builder     │  self-claim   │  only, germline)    │   gh/Vercel/Sentry/ │  veto = execute_after;      │
│ Support-    │◀──────────────│  graduation.evaluate │   CI/support        │  fails CLOSED offline)      │
│ Drafter     │  task board   │  → authority matrix │                     └─────────────────────────────┘
└──────┬──────┘               └─────────▲──────────┘
       │ PRs (self-mods too)            │ ledger-liveness dead-man (starvation ⇒ auto-demote)
┌──────▼──────────────────────────────── ┴──────────────────────────────────────────────────────────────┐
│  THE GATE (gate-runner, out of officer reach): balanced probe + zero-regression budget + pass^k=3     │
│  + read-isolated holdout + cost gate · judge contracts pinned · trace→test flywheel · drift replay    │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
   SENSING: product-brain corpus (architecture/incidents/decisions/support-kb) + ported embeddings index
   SUBSTRATE: Mac Mini, auto-login LaunchAgents, tmux, SQLite WAL + git as truth, Redis = ephemeral bus
```

### 4.1 Substrate and topology

- **One Mac Mini, dedicated auto-login user, everything as user-session LaunchAgents** (never daemons/cron — subscription auth, Keychain, TCC live in Aqua). pmset hardened; macOS auto-updates disabled in favor of scheduled watchdog-aware windows; explicit FileVault/unattended-reboot policy verified on the target (a box stranded at FileVault is a physical-presence problem no watchdog fixes) **[RT]**.
- **Three LLM officers maximum** (the 3–4 coordination ceiling; thin personas, thick SOPs and tool scopes):
  - **Chair** — sole Telegram voice; triage, synthesis, briefings, lesson harvesting. Never in the verdict-recording path.
  - **Builder** — single writer on the product repo. Work arrives via the task board; execution is **episodic**: bounded `/goal` runs in fresh sessions from durable state (capsule + handoff files, progress file, commit-on-stop), worktree-isolated subagents for parallel spikes. The 351.9k-token 9-day marathon session is exactly the anti-pattern the meltdown research warns about.
  - **Support-Drafter** — propose-only external comms; activates **only after** the policy engine is enforcing, because it reads untrusted input **[RT]**.
- **Everything else is a deterministic daemon, not an officer:** probes, verdict binder, gate-runner, executor, watchdogs (progress-aware heartbeats with monotonic step counters; tiered recovery: re-inject → summarizer-compacted restart → fresh session + page; memory-pressure shed order protecting the Chair), the ledger-liveness dead-man.
- **Stores:** git (canonical, pushed, CI-gated) · consequence + org event ledgers (SQLite WAL + JSONL mirror, `.backup`/Litestream) · product-brain corpus + embeddings.db · task board (SQLite CAS claim + 30-min leases — Redis demoted to ephemeral trigger bus or AOF-everysec if it keeps any durable role) · `services.yml` single deployment manifest from which every plist is generated idempotently — **the Mini must be rebuildable from git alone**.
- **Runtime fragility controls:** pin the Claude Code version; boot/CI assertion that the `'esc to interrupt'` idle string still matches (mismatch = fleet-down alarm); fix launchd PATH so `--agent` engages; move constitution assembly from `/tmp` to a durable path **[RT]**.
- **Security:** Keychain-referenced secrets (names-not-values in any file an officer can read); sandbox ladder (native `/sandbox` for the Builder's code lane; microVM for anything browser/deploy-adjacent); the Mini on an isolated VLAN; micro-VPS webhook catcher for inbound continuity **[RT — required for any auto lane, not optional]**. Drop `drives_computer`/computer-use from the Mini capability profile entirely: a code+API product org needs no Accessibility/Screen-Recording grants, which dissolves the unsolved TCC/code-signing stub as a go-live blocker.

### 4.2 The evidence plane — one ledger, three writers, none of them narrative

Keep `consequence-event.schema.json` verbatim. Three independent writers:

1. **Proposals** — officers emit pending proposals with correlation_ids (existing `loop.propose()`).
2. **Captain verdicts — mechanical, in-process with the gate.** The inbound poller feeds `route_captain_response` (already fail-closed) → superseding approve/edit/skip event → *then* the approved payload goes to delivery. The Chair reads results; it is never the recorder. **Gate-owns-ledger invariant (germline):** presenting a proposal, delivering the decision, and writing both ledger rows are ONE component that migrates together — the n=0 lesson made structural.
3. **Outcome probes** — stdlib daemons polling machine truth: `gh pr checks`/merge/revert state, Vercel deploy status + rollbacks, Sentry error-budget burn, CI runs, support-thread resolution. They write `outcome.status` and (via the verifier) `review.verdict`.

**Join integrity [RT]:** correlation_ids are minted at proposal time and **propagated into the artifacts themselves** — PR/commit trailers, deploy metadata, support-thread tags. Probes attribute by exact id read-back, never by time/author heuristics; unattributable artifacts record `status=unknown` and credit no officer. `on-subagent-stop.sh`'s junk `work_item_completed` emission is killed **before** probes go live.

**Observation confidence [RT]:** every probe event carries `observed` vs `could-not-observe (upstream unreachable)`. Upstream-unreachable never counts as fabrication or demotion input; the verifier classifies agent-fault vs upstream-outage before any lesson is minted.

**Dual-source honesty verification:** deterministic claim-vs-probe reconciliation is authoritative; a Haiku pass is advisory-only. Fabrication taxonomy (confident-claim-on-null-state, hallucinated tool result, subagent fabrication, silent skip). **Verifier-detected fabrication fires demotion directly** — not just a scorecard metric — and honest self-flag calibration is a graduation input, so the incentive gradient doesn't reward confident success over honest uncertainty **[RT]**. Officers get a penalty-free `escalate/self-flag` tool; punitive framing is banned from prompts.

**The ledger-liveness dead-man [RT, from the Loop Closer — the single best 3am artifact of the panel]:** a standing launchd probe, germline, out of officer reach: if any live lane emits proposals while Captain replies are visible in getUpdates and **zero superseding verdicts land for N hours → CRITICAL page AND auto-demote the lane to propose_only.** Evidence starvation automatically revokes autonomy — staleness is loss of proof, not preservation of it. This converts the estate's twice-paid failure into a self-neutralizing one.

### 4.3 Machine truth as primary verdict supply — with the Goodhart valve closed

Machine probes fill graduation denominators at product-traffic volume instead of Nate-reply volume. This is the difference between a loop that compounds and one that starves politely — and it is exactly the "product-native ground-truth pipeline" the fidelity harness's own Mac-Mini-readiness analysis prescribes.

But CI verdicts are only adversary-resistant if the Builder can't move the goalposts — the red team's fatal attack #1: *the Builder writes the tests CI reads*. Closed by construction **[RT]**:

- **Test-diff is a positively-classified ceiling risk-class** in `authority-matrix.yml`, mechanically detected at pre-tool-use on the product repo: coverage delta, assertion-count delta, skip/xfail-count delta.
- **A PR that touches tests can never produce a graduation-advancing outcome from CI-green alone** — it routes to Captain review or an independent verification lane.
- An independent **coverage-ratchet / mutation-testing probe** the Builder cannot author.
- This is a blocking precondition for the enforcement flip, not a later hardening.

**Error-budget-linked demotion, target-separated [RT]:** budget burn throttles **new-feature deploy origination** (graduated cells drop one verdict level until recovery) while **pre-approved incident remediation and rollback stay fast** (auto behind the veto window). Never route incident fixes to the Captain during an active burn — that maximizes MTTR at the worst moment.

### 4.4 The authority plane — closing measure→gate and flipping enforcement

- `read_cell_state` calls `graduation.evaluate` (fail-safe wrapped to `'unmeasured'` on any exception — the one-function wire the stub's own docstring prescribes). Instantiate `instance/config/autonomy.yml` from its `.example`.
- Re-run the recorded 554-pair parity discipline, then **flip `CABINET_AUTHORITY_ENFORCING=1` early, scoped to L0/L1 reversible classes** — the flip is behaviorally inert until cells measure (fail-closed unmeasured ⇒ propose_only), so flipping early removes the exact "flip never executed" stall class that stranded F2 for weeks. Keep the bash hook as belt-and-suspenders through a soak with a divergence alarm; never delete the old gate in the same motion as enabling the new one.
- The six hard-ceiling classes stay `always_gated` at every confidence, CI-asserted, forever. Carve-outs (like the receipt auto-forward) are implemented **in the executor** under enumerated conditions, never by lifting a ceiling row.
- The veto window (`veto.py`) ships with the first graduated cell — as an `execute_after` timestamp on the outbox row (fixing the marker-before-send silent-drop), and it **fails closed on Captain-channel unavailability**: before firing any deferred auto-action, confirm inbound Telegram is live; if not, HOLD past expiry **[RT]**.
- Demotion is proven live by injecting a synthetic wrong verdict (chaos-engineering the trust loop) before any cell is trusted.
- **Model-version discipline [RT]:** graduation history is stamped with the model baseline; any model bump demotes graduated cells one level pending re-proof; the Mini's ledger starts **fresh** (no cross-flavor cell inheritance — flavor A cells were earned against a different ground-truth distribution), and the cold-start propose-only period is accepted as honest.

### 4.5 The Gate — eval-gated self-modification (the most protected asset)

Every durable change to the org's own behavior — CLAUDE.md playbook deltas (**ACE-style itemized bullets with helpful/harmful counters; monolithic self-rewrites lint-banned**), SKILL.md skills, policy YAML, tool descriptions, memory promotions — is a PR admitted by the **gate-runner**:

- **Balanced probe:** previously-failing AND previously-passing cases, grown by a trace→test flywheel (every escalation, wrong verdict, rollback, MAST-coded failure becomes a case).
- **Zero-regression budget** on the passing set; **pass^k (k=3)** on behavioral cases; **cost gate** (block if tokens/task rise >~15%).
- **Read-isolated hidden holdout [RT]:** rotated, living in a separate permission scope, decrypted only inside the gate-runner process — germline write-protection alone is insufficient because a proxy the optimizer can *see* is a proxy it will hack. Proxy-vs-holdout divergence alarms.
- **Split germline [RT]:** judge/policy CODE stays Captain-only; the eval-fixture CORPUS is append-only with additive cases auto-admitted (a case the current system already passes is zero-risk to add) and only verdict/threshold-*changing* mutations Captain-gated — so eval-set refresh runs at machine speed instead of rotting at Captain latency.
- **Judge discipline:** verdicts machines can't check use rubric-anchored CoT single-answer scoring; pairwise always position-swapped; contracts pinned in git (judge_model_id + rubric_version + prompt hash); Captain labels a 10–20-case calibration batch monthly; every juror/verifier reuses `oauth_llm.py`'s clean-cwd + `--setting-sources` hygiene (the holdout already leaked once through a bare `claude -p`) **[RT]**. The heterogeneous jury and CMP-lite lineage attribution are **deferred past v1** [RT, parsimony]: deterministic verifier + single pinned judge first; judgment lanes stay Captain-gated honestly until the jury exists.
- **Auto-apply is earned per change-class** exactly as `architect_lib` already implements (≥3 confirmed, 0 wrong, reversible); everything else is one-tap Captain ratification. `self_improvement_loop`'s `captain_auto_ratified=True` is **narrowed to reversible instruction-level deltas BEFORE the learning crons are installed** (the ordering hazard the org-designer lens caught).
- **Bounded pressure:** iteration caps per cycle; self-improvement halts fail-closed on headless-credit exhaustion — **no change auto-applies without a completed gate run; autonomy never widens on a skipped gate [RT]**. Headless economics are governed explicitly: usage-API metering, batch API for sweeps, Haiku-tier verifiers, deterministic-only mode when credit is low.
- **Curation:** nightly Dreaming-style consolidation over session transcripts proposes gate-bound deltas; weekly drift replay of ~50 sampled real tasks; harness-debt review on every model upgrade (scaffolding encodes assumptions about model weaknesses that go stale).
- **Ingestion-provenance gate [RT]:** content from untrusted external channels (support inbox, web, external PR comments) is quarantined — it may inform a Captain-gated draft but can NEVER be promoted to durable memory, a skill, or a gate-bound policy/CLAUDE.md delta without Captain authentication. Treated as data-not-instructions. This guards the memory-poisoning path the Gate itself can't see (a subtle compliance-wording poison shows no behavioral regression).

### 4.6 The actuator — credential-holding executor + hash-locked outbox

Adopted from the clean-slate lens (every judge flagged it as the strongest safety construct): **one deterministic process holds all send/deploy credentials.** Officers physically cannot send — they write proposal rows; the executor executes only rows carrying a fresh approval token whose payload hash matches exactly what the Captain saw. Every external side effect becomes a hash-locked row (`proposed/approved/executed/verified`) — i.e., **every send is a label by construction**, which is the gate-owns-ledger invariant expressed as physics. The veto window is an `execute_after` timestamp. `framework/outbox/relay.py` is the intended slot (built-but-stub); it gets real adapters on the product tenant (Resend/Graph). Sequenced *after* the loop is closed (Gate 1–2), not before — rebuild-by-extraction ahead of label capture is the estate's documented failure mode.

### 4.7 The Captain interface — attention as the metered resource

- **Monitor-and-intervene by default:** streamed activity digest, cheap interrupt, inline approve/edit/skip buttons; ping-now reserved for the six ceiling classes and gate escalations; everything else batches into the 07:30/19:30 briefings with auto-expiry.
- **Escalation-rate budget:** target <10% of actions; alert on breach or on queue growing faster than it clears; time-to-approve instrumented as a rubber-stamp detector (93% unread approvals is the documented failure of per-action gating).
- **The Captain-debt reverse queue** (org-designer lens — the most original high-value idea of the panel): a first-class lane tracking what **Nate owes the org** — pending ratifications, germline pastes, enforce flips, TCC clicks, OAuth/2FA, tokens, calibration batches — each with age, *what-it-blocks*, and effort estimate, surfaced in every briefing. The measured pattern (approved one-liners rotting for days) predicts the germline-apply queue stalls the loop at the last mile; this is the mechanism that prevents it. Pair with a scheduled, batched **germline-apply session** (one sit-down, N pre-verified diffs).
- **Captain-required action registry:** pre-enumerated human-only actions (payments/payouts, OAuth consent, account creation, 2FA, legal signatures, DNS) so officers park-and-batch instead of stalling.
- **L0–L3 ladder at the dispatcher:** L0 auto+audit · L1 auto above confidence bar (graduated cells) · L2 one-tap approval (spend, access, prod deploys, public messages) · **L3 dual-confirm + cooldown** (credentials, payments, germline diffs). Ceiling classes cap at L2/L3 forever.
- Batched one-tap approvals carry reduced label weight (≤0.5) and never mint eval-suite cases (companion-report ruling, adopted).

### 4.8 Memory architecture

- **Product-brain corpus** (markdown: `architecture/`, `incidents/`, `decisions/`, `support-kb/`, `deploys.md`) indexed by the **ported embeddings stack** (`embeddings/lib.py+index.py` run on any corpus; only VOYAGE_API_KEY needed). Keep the fusion contract: `{source, ref, text, base_score, ts, content_ts}` with authority weights and content_ts fencing; swap tier-2 fetchers from audio/OCR/SentItems to Sentry/Vercel/GitHub/Neon `safe_select`.
- **Bi-temporal facts** (valid_at/invalid_at, supersede-never-delete) for deploy states, decisions, customer commitments — solves the staleness class decay can't (high-relevance facts that become confidently wrong).
- **Tier model kept** (T1 always-loaded law · T2 per-officer working notes · T3 episodic) with three repairs: schedule the memory-worker (the flagship store is currently dark with 497 queued embeds); grant retrieval to the roster that actually runs; **semantic-category TTLs + a nightly consolidation job** (orient → gather → resolve contradictions → prune to a <200-line index), with the memory diff routed through the one-tap gate. Fix the six-surfaces-for-decisions fragmentation: one canonical store per fact type, others become projections or die.
- **Prompt-cache-aware injection:** stable prefix (constitution, role, skills) → cached block → volatile turns; never refresh memory into the system prompt per turn on a 24/7 session. Per-subagent persistent memory for long-lived specialists (reviewer, deploy runner).
- **Data-freshness assertions everywhere** (clean-slate lens): every gate, eval, briefing, and probe first asserts its inputs are fresh and non-empty (row counts, last-write timestamps) and hard-fails loudly otherwise — generalizing the outcome-watchdog insight to every consumer, killing the dead-data class at the root.

### 4.9 Work engine and product onboarding

- Keep STREAM / MISSIONS / INTAKE semantics (they are genuinely crisp) with the mission compiler → **SQLite task board (CAS claim, leases, dependency edges)** → officers self-claim → bounded episodic runs → probes verify. Renewal loop implemented as code, not prose.
- **Delegation contracts:** artifact-first briefs (objective, output format, tool guidance, boundaries, context); 45%-rule spawn gate before decomposing any task class; condensed-artifact returns.
- **Staged product onboarding SOP** (org-designer lens — the repeatable trust ramp for product #2+): Stage-0 `cabinet-init` interview → Stage-1 read-only shadow week producing a product dossier (architecture map, runbook, deploy-policy YAML, oracle inventory, Captain-required registry entries) → Stage-2 propose-only until n≥20 consequence events with measured escalation precision → Stage-3 per-cell graduation. Nothing about trusting a new product is ad-hoc.

### 4.10 Metrics — the scorecard that replaces OVI

OVI is killed (its feeder events were never emitted; weighted composites hide regressions). One scorecard, computed **only from the ledger**, reported as a raw vector with trends in the weekly brief:

- **Product:** deploy success rate · MTTR · repeat-incident rate (90d — the cleanest lessons-are-sticking signal) · CI green rate on main · error-budget burn · support resolution rate · cost/task.
- **Org:** interventions/day · escalation precision · approval latency (rubber-stamp detector) · autonomy coverage (% of actions in graduated cells) · fabrication rate · gate throughput (admitted/rejected — the loop is live only when it has demonstrably *rejected* something) · proxy-vs-holdout divergence · ledger-liveness.
- **North star: verified outcomes per Captain-minute.**

---

## 5. The change catalogue — phased, gated, with exit criteria

Sequenced by dependency (never calendar). Each gate has a machine-checkable exit; nothing advances without it. Phases 0–3 run **on the live MacBook deployment** so evidence continuity is never severed (the n=0 lesson); the Mini is born at Phase 4. This plan is compatible with the companion report's P0 resuscitation list — its operational fixes (watchdog PATH, external dead-man, backups/remotes, killswitch fail-closed, token split, cost writer) slot into Phase 0/1 here; deltas are noted where they exist.

### Phase 0 — Make the system real (repo + operational floor) · *days*

| # | Change | Detail |
|---|--------|--------|
| 0.1 | **Secret-scan → commit → push** the live branch | 141 unpushed commits + 101 dirty/untracked files (incl. the live watchdog, autoreply, trust_ladder, meta-cognition). Secret-scan first: this tree ran live with real credentials in env for weeks. |
| 0.2 | **Retire the dead deploy path BEFORE pushing** | `deploy-mac.sh --all` deploys the extinct cos/cto/cpo/cro/coo fleet; template the live 4-officer + 9-daemon fleet (`services.yml` manifest → all plists generated, no `/Users/nate` hardcodes). Otherwise canonicalization enables a self-inflicted wrong-fleet redeploy **[RT]**. |
| 0.3 | **CI on the real branch** | Retarget `cabinet-ci.yml` triggers; add `pytest framework/` (1,343 tests currently in no CI); fix the GNU-only `date -d` in the pre-push hook (fails closed on macOS). |
| 0.4 | Operational floor (≈ companion P0) | Backups: remotes for both repos + nightly db snapshot; killswitch fail-closed; external dead-man (healthchecks.io); watchdog PATH fix; cost writer wired to a real hook event; heartbeat-watchdog installed or explicitly waived. |
| 0.5 | Kill semantic pollution | Re-type `on-subagent-stop.sh`'s `work_item_completed` (5,546 junk events) **before** any consumer counts completions. |
| 0.6 | Constitution durability + law dedup | Move `/tmp/cabinet-runtime` assembly to a durable path; collapse dual constitutions; rewrite KILLSWITCH.md for launchd. |

**Exit:** CI green on the exact branch a Mini would clone; a scripted redeploy reproduces the running fleet.

### Phase 1 — Verdicts flow (mechanical label capture) · *days*

1.1 Wire `reply_binder.bind` into the inbound poller with `dispatch=deliver_draft` — verdict emit in-process with the send, Chair out of the recording path.
1.2 Collapse all Telegram sends into `channel.py`; delete `run_draft_lane._tg` and the raw-curl senders; CI tripwire: `api.telegram.org` outside channel.py fails the build.
1.3 Stand up the **ledger-liveness dead-man** (permanent, germline).
1.4 Companion-P0 alignment: single tap point with `verdict_human`/`verdict_judge` split; Telegram token split.

**Exit:** 7 consecutive days each landing ≥1 non-expired approve/edit/skip superseding event; zero sends outside channel.py in audit; dead-man test-fired once.

### Phase 2 — Machine truth flows · *week+*

2.1 Outcome probes (gh, Vercel, Sentry, CI) with **correlation_id propagation into artifacts** (PR trailers, deploy metadata) and observation-confidence tags.
2.2 Deterministic dual-source verifier emitting `review.verdict`; fabrication → demotion trigger.
2.3 `read_cell_state → graduation.evaluate` in shadow; `autonomy.yml` instantiated; probes/fixtures/judge contracts join the germline.
2.4 **Test-diff ceiling risk-class** live on the product repo (coverage/assertion/skip deltas) + coverage-ratchet probe.
2.5 Install the learning crons — with `captain_auto_ratified` narrowed to reversible instruction-level deltas FIRST.
2.6 Schedule memory-worker; grant retrieval to the live roster; drain the 497-item queue.

**Exit:** ≥3 cells show non-None `GraduationRatios` from machine verdicts; shadow decisions logged; parity re-run clean; test-diff detection demonstrated on a synthetic weakening PR.

### Phase 3 — Enforce · *days*

3.1 Flip `CABINET_AUTHORITY_ENFORCING=1` scoped to L0/L1 reversible classes; bash hook stays as backstop through a soak with divergence alarm.
3.2 Veto window live as `execute_after` (fail-closed offline); first reversible cell graduates (board_status or tier2_note class).
3.3 Inject a synthetic wrong verdict → prove demotion end-to-end. Error-budget demotion live, target-separated (remediation stays fast).

**Exit:** one auto cell live behind a veto window; demotion demonstrated; escalation rate measured under budget.

### Phase 4 — Mini clean-room (flavor B is born) · *week+*

4.1 `cabinet-init` interview → `generate-instance.py`; **fresh graduation ledger** (no flavor-A inheritance), model baseline stamped.
4.2 Product adapters on the `find_threads/gather/draft_fn` seams; `truthfulness_gate` ported from `draft_lib.py:866` into `framework/acting/` with product evidence sources; **CI ratchet: any `~/.screenpipe` import in `framework/` fails**.
4.3 Executor + hash-locked outbox as sole egress (relay.py gets real product-tenant adapters); micro-VPS webhook catcher deployed.
4.4 Fleet from `services.yml`; no computer-use capability (TCC dodged); pmset/auto-update/FileVault checklist verified; Redis AOF or demoted; SQLite version + `.backup` verified.
4.5 Rewrite `mac-mini-setup.md` as the actual flavor-B runbook (today it installs screenpipe).

**Exit:** 72h unattended soak — watchdogs green, probes writing, outcome events accruing against the product repo, zero screenpipe references.

### Phase 5 — The Gate goes live · *week+*

5.1 Gate-runner + balanced probe seeded from golden evals + first real traces; read-isolated holdout; split-germline fixture flow.
5.2 Nightly consolidation, weekly drift replay, monthly Captain calibration batch as launchd jobs.
5.3 Headless-credit governance live (usage-API metering, batch API, fail-closed exhaustion semantics).

**Exit:** one self-change **admitted** and one **rejected** through the full gate, both visible in the ledger with lineage tags.

### Phase 6 — Compounding · *ongoing*

6.1 Support-Drafter activates (policy engine enforcing + ingestion-provenance gate live).
6.2 Tool-synthesis promotion channel (Live-SWE pattern): officer-written scripts that pass tests promote to the shared toolbox via the Gate.
6.3 Judge jury + CMP-lite lineage attribution (deferred from v1) once first cells have graduated.
6.4 GEPA-style prompt optimization on curated real traces (20–100 cases, never 500) for officer role prompts, shipped via the Gate.
6.5 ShinkaEvolve-style small-budget evolutionary loops **only** on machine-checkable subsystems (CI pass rate, token cost/task, probe latency).
6.6 Second product onboarded via the staged SOP; federation only after that (spawning a new cabinet stays the highest-consequence, propose-only act).

**Exit (the compounding criterion):** autonomy coverage rising while interventions/day falls across two consecutive scorecard periods — verified outcomes per Captain-minute trending up.

### The kill list (execute as gated deliverables with CI tripwires so kills cannot half-happen)

1. OVI weighted composite (`framework/ovi/`) → ledger-derived scorecard.
2. Reply-cell retrodiction harness for flavor B (keep as flavor-A drift guardrail; port only leakguard concepts + the git-commit decision miner).
3. Docker/Hetzner control plane (admin-bot, host-agent, compose, Dockerfiles, entrypoint, resume-officer, `/opt/founders-cabinet` defaults leaking into live hooks) — port the pause-flag + append-only-audit concepts to a launchd-native emergency path first.
4. `org-runtime.py` mission tables + the `mission-compile` skill that teaches the dead path.
5. All Telegram send paths except `channel.py`.
6. Legacy `constitution/` duality + Docker KILLSWITCH.md.
7. The 5-officer work-preset deploy path + stale roster residue (officer-capabilities rows, platform.yml voices, mcp-scope tokens).
8. Dual scheduling truth (pipe.md frontmatter vs launchd) for anything cabinet-owned; the `.disabled`-plist pattern that hides dead jobs from health checks.
9. `cabinet/init.sql` ghost schema (4 of 5 tables writer-less) and the six-surface decision fragmentation — one canonical store per fact type.

---

## 6. Design principles the redesign is built on (the durable part)

If every file named above churns, these survive as the org's constitution-of-constitutions:

1. **The gate is the mechanism.** Proposal machinery contributes almost nothing; the acceptance gate (balanced probe, regression budget, hidden holdout, pass^k) separates compounding from thrashing. Invest there.
2. **Whoever owns the approval surface owns label capture, atomically.** Verdict emit in-process with the act; gate-owns-ledger is germline; ledger-liveness starvation auto-revokes autonomy.
3. **No loop may edit its own judge — and the judge must be read-isolated, not just write-protected.** Germline for code; split-germline for fixtures; holdout in a separate scope; immutable logs.
4. **Machine truth first, human judgment reserved.** Fill denominators with adversary-resistant probes; spend Captain attention only where machines cannot check; treat every verifier as a proxy that must co-evolve.
5. **Never trust the actor's narrative.** Dual-source verification; artifact-grounded status; fabrication demotes; failure reporting must be cheap and unpunished.
6. **Fail closed, degrade honestly.** Unmeasured ⇒ propose-only; credit exhaustion halts self-improvement rather than skipping gates; veto windows hold when the Captain is unreachable; probes report could-not-observe rather than guessing.
7. **Built = scheduled + fed + watched.** A component isn't done until a liveness/throughput expectation is registered with a watchdog that pages on starvation. Data-freshness assertions on every consumer.
8. **One joint per function.** Every severed wire in this estate's history was cut at a duplicated joint during a migration. Before any migration: enumerate duplicates, assign one owner, verify evidence continuity as an explicit gate.
9. **Episodic execution over durable state.** Fresh sessions re-reading files/SQLite beat marathon contexts; capsule + handoff + progress files; restart is the default recovery.
10. **The Captain is a metered, two-way resource.** Escalation budgets and rubber-stamp detection on one side; a debt queue with ageing on the other. Batch, dedupe, expire.
11. **Asymmetric autonomy is correct.** Machine-verifiable lanes graduate in weeks; judgment lanes may stay gated for months. Don't equalize by weakening the gate.
12. **Reversibility prices everything.** Reversible + cheap ⇒ act and log; expensive ⇒ evidence threshold; irreversible ⇒ ceiling, forever. (Already the estate's instinct — keep it universal.)

---

## 7. Flavor A — the MacBook personal assistant

**Shared framework (identical code):** the consequence schema, mechanical verdict binder, ledger-liveness dead-man, the Gate, graduation + authority matrix + germline, the scorecard, the runtime substrate, the Captain interface. `gate_ledger.py` was deliberately built field-compatible — the convergence was pre-planned in the data layer.

**Divergences:**
- **Ground truth is human.** Approve/edit/skip and Nate's observed subsequent actions are the verdict supply; machine probes exist only in slivers (Graph SentItems "already replied", calendar/audio evidence for commitment auto-close). Promotion reads human verdicts only (companion ruling — correct for this flavor); bars stay conservative (15 samples/90%/14 clean days may honestly mean months at propose-only).
- **Sensing plane stays:** screenpipe capture, the Obsidian vault, embeddings brain, brain-mcp. The retrodiction/fidelity harness remains — demoted, as the grand plan already ruled, to a drift guardrail.
- **Immediate repairs for flavor A** (the migration debt this analysis surfaced): route the pipes' suppressed evidence loop through the Chair gate so labels flow again (today: `CABINET_OWNS_TELEGRAM=1` suppressed prompts, all lanes n=0, `gate_decisions` zero live rows, `agent_reasoning` 267 written/6 reviewed); reconcile the germline contradiction (brain-bridge still declares `queue_draft` the ONLY outbound path while `chair_drafts.deliver_draft` has been the live egress since 06-24); restore the dropped Captain-voice-DM input path; finish the pipe dispositions per work-model (KEEP-CAPTURE / KEEP-REFLEX / MIGRATE) with per-pipe shadow parity.
- **The binding shared invariant** is principle #2: on both flavors, the verdict emit is in-process with the send/approve action — never a second system relying on LLM discipline.

---

## 8. Risks and open questions

1. **Probe Goodharting is permanent.** Test-diff classing + coverage ratchets + holdouts reduce, never eliminate; the gate needs its own versioned improvement cadence (meta-evals, periodic Captain calibration). *Verification is a receding horizon.*
2. **Captain-verdict scarcity for judgment lanes.** Comms tone, prioritization, product taste have no probe; juries substitute only after calibration exists. Those lanes graduate slowly or never — accept it; don't paper over with self-judging.
3. **Germline growth recreates the bottleneck it guards against.** Probes, fixtures, contracts, binder all join the Nate-only set; without the debt queue + batched apply sessions, the loop stalls at the last mile again.
4. **Headless-credit economics.** pass^k × probes × curation × verifier on a fixed monthly credit; governance is designed (§4.5) but the budget envelope is unproven — expect rationed eval depth initially.
5. **Claude Code internals coupling.** TUI scraping, `--agent` PATH fragility, compaction behavior, version pinning vs auto-update: partially mitigated (boot assertions, pinning), structurally present until officer boot moves to the Agent SDK (a candidate Phase 6+ item, not before).
6. **Single-machine SPOF.** VPS webhook catcher covers inbound; a full outage still halts the org. Acceptable for v1; the `services.yml` + fresh-ledger discipline makes standing up a replacement Mini a bounded operation.
7. **The org still cannot legally sign, pay, consent, or appear.** The Captain-required registry names the permanent human wall; the org's job is to make every arrival at that wall batched and fully-briefed.
8. **Open question — task-board substrate:** SQLite CAS board vs Claude Code native shared Task lists (dependencies, compaction-safe). Recommendation: SQLite as durable system of record now, native task lists as the officer-visible projection; revisit when Agent Teams stabilizes.
9. **Open question — when to add officer #4.** Only when a task class's single-agent success is measured <45% and the scorecard shows escalation precision holding; never for throughput alone.

---

## Appendix A — Findings index (per subsystem, with the sharpest facts)

| Subsystem | Maturity | Sharpest verified facts |
|---|---|---|
| Doctrine/governance | mixed | Authority matrix data + CI invariants excellent; `/tmp` constitution observed empty while officers ran; dual constitutions; KILLSWITCH.md is Docker commands; `autonomy.yml` missing so graduation unbound |
| Vision/principles | mixed | Supersession discipline exemplary; never-lie/prove-to-earn/meta-cognition designed with hard selectors; trust ladder + self-proposal built same-day-as-design, zero callers; captain-rules index silently dead for weeks (48 anchors, 0 live patterns) until 06-26 |
| Missions/roles | mixed | Outcome schema encodes governance in work; supervisor never routed a task (0 `work_item_assigned` ever); 5,546/5,548 completions are junk; two mission systems, skill teaches the dead one; role truth on 7 surfaces |
| Fidelity/learning/OVI | mixed | Leak-fencing is real engineering (24 leak events, 0 leaks); gate reads stub not `graduation.evaluate`; ledger can graduate nothing (0 decisions/outcomes/reviews); learning stack 0 production events; OVI feeders unemitted; single judge; ground truth n=12 |
| Acting/frontdoor | mixed | Draft lane propose-half solid, act-half is LLM-discipline; `reply_binder` dispatch deliberate no-op; 5 Telegram send paths; germline says queue_draft-only while live egress is chair_drafts; veto/deploy-classifier built-not-wired; live modules untracked in git |
| Runtime/infra | mixed | 4 officers survive crashes/limits genuinely; TUI-scrape nervous system; heartbeat-watchdog uninstalled; `--agent` dead via PATH; no `claude --continue` on Mac path; Docker residue leaks into live hooks |
| Interfaces | mixed | Front-door intake/tiering/ACK-after-send excellent; poller self-heals 409s; voice DMs silently dropped; MCP scope vs live merged configs contradict; no emergency channel on the Mac (admin-bot/host-agent are Ubuntu-only) |
| Skills/loops | mixed | Loop 4 (captain-rule-encoder) is the only fully-live loop; reflections counter 0 post-fix; R8 chain (808 lines) zero executions; foundation skills modified in place against own rule; dual-copy skill drift |
| Memory (cabinet) | mixed | Embed queue 497 pending, worker never ran, zero semantic searches in 20k calls; retrieval capability granted to extinct roster; `cabinet_research` has no CREATE TABLE; decisions on 6 surfaces; no TTL/decay anywhere |
| Screenpipe core | mixed | The transferable IP: hybrid brain, content_ts fencing, 5 ledgers, architect earned auto-apply in production; label pipelines starved (0 live gate rows; 56 unresolved shadows); paths hardcoded; two Python runtimes |
| Screenpipe pipes | mixed | Single-choke-point Telegram + germline exemplary; autonomy lanes all n=0; draft-reply dead-but-reported-ok; dual schedulers drift; capture chain fragile (Make/Graph) |
| Engineering health | mixed | Real TDD (red-green pairs); 1,343 tests in no CI; branch on no remote; commits stopped Jun 25 while work continued; master==convergence-v2 (memories stale) |
| Deployed state | mixed | Live fleet ≠ runbook fleet; plists hand-copied with hardcodes; TCC persistence a stub; mac-mini-setup.md installs screenpipe (flavor-A plan under a flavor-B name) |

## Appendix B — Method + artifacts

- **Workflow 1 (Understand):** 13 read-only subsystem readers, structured schema, ~4.1M tokens total across runs.
- **Workflow 2 (Research):** 7 researchers × 3 engines (WebSearch/Brave/Exa), triangulated, disagreements flagged rather than resolved, ~1.2M tokens.
- **Workflow 3 (Design):** 4 architect lenses (loop-closer, clean-slate, evidence-engine, org-designer) → 3 independent judges (SRE, safety, CTO personas; vote, no debate; anti-length-bias instruction) → red team (13 attacks: 2 fatal-as-written, both neutralized by amendments; verdict: survives). ~1.7M tokens.
- Judge scores: evidence-engine 8.9/8.8/8.5 · loop-closer 8.7/8.5/8.8 · clean-slate 8.4/8.0/7.7 · org-designer 7.8/7.5/8.0. Tally 2–1 evidence-engine over loop-closer; the winner absorbed the losers' must-survive mechanisms (ledger-liveness dead-man, executor+outbox, services.yml, CI tripwires, Captain-debt queue, staged onboarding, L3 tier, auto-ratify narrowing, fresh-context workers, bi-temporal facts).
- All analysis artifacts preserved at `~/mac-mini-ai-org-blueprint-artifacts-2026-07-02/{understand,research,design}/` — 13 subsystem reports, 7 research digests (with sources), 4 architecture proposals, judge votes, red-team attack log.
- Companion report (parallel session, flavor-A oriented, filesystem-verified P0s): `~/self-improving-org-report-2026-07-02.md`.
