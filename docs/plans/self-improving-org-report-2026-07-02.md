# The Self-Improving Org — Analysis & Blueprint
**Scope:** `~/captains-cabinet` + `~/.screenpipe` + the Obsidian brain, toward an autonomous AI org that replaces 90%+ of Nate's work and self-improves past him.
**Date:** 2026-07-02 · **Method:** 3 orchestrated workflows, 31 agents (~4.4M tokens): 11 read-only system readers → 8 frontier researchers (multi-engine, cited) → 6 filesystem claim-verifiers (34 checks: 29 confirmed, 5 corrected) → 3 architecture panels → 2 adversarial red teams. Every load-bearing claim below was re-verified against the live filesystem today unless marked otherwise.

---

## 1. TL;DR

**The architecture is not the problem. Operation is.** Your design corpus (fidelity harness, authority matrix, prove-to-earn graduation, consequence ledger, never-lie, courses-of-action) is *ahead of commercial state of the art* — the research sweep found no shipped product with a retrodiction harness or per-(lane × action_type) earned autonomy. But of ~14 designed self-improvement loops, **exactly 2 are closed and running**. The flywheel has never completed one revolution, for reasons that are boring and fixable:

1. **The label economy is severed at the artery.** You moved to the HQ Chair bot ~Jun 10; every clone learning input (me_signal, gate ledger live path, reply enrichment, model corrections) still listens to the old screenpipe bot, which polls `updates=0`. Meanwhile 100% of the cabinet's 1,829 fidelity events carry `review.verdict="unknown"`, zero Telegram approvals have ever been written back, and **47% of proposals expire unlabeled**. `graduation.evaluate()` returns `unmeasured` for every cell — so earned autonomy is arithmetically impossible, forever, no matter how good the drafts get.
2. **The goal loop was never switched on.** `mission-supervisor.sh` + `outbox-relay.sh` are fully coded, 6 outcomes are Captain-ratified in `outcomes.yml` — and there is no plist or crontab for either. Zero `work_item_assigned` events have ever existed. Your officers are reactive sweepers, not mission executors.
3. **The immune system can't feel death.** pipe-watchdog's probe *and* its alarm both fail on one missing PATH line; the entire self-improvement daily cluster (architect, autonomy, voice-profile, codebase-digest) has been silently dark since Jun 29; both "backup" git repos have **no remotes**; the 19.2GB capture DB is backed up nowhere.
4. **Measurement ran once.** Retrodiction: n=1 (Jun 11, decision-match 8.3%). Cabinet evals: idle since Jun 25. There is no trend line for the only number that defines "getting better."

The blueprint that follows is therefore sequenced by an unusual rule, enforced by the red team: **you may not build anything new until the existing machine is breathing** — and the whole program is fitted to a hard budget on the scarcest resource, your attention (measured reality: ~30-day median verdict latency, 161 rotting cards).

The honest math: ~7% of your work is automated at parity today, ~33% is draft-gated. The 12-month ceiling with this stack is **~78%, not 90%** — and the residual isn't drafting, it's live meetings, salary/leadership, legal accountability, strategic prioritization, and identity ceremonies. The right target function (your own stated principle, now backed by external evidence) is **attention-per-outcome, not percent-of-tasks** — plus a per-work-class "better than Nate" win-rate that this report defines concretely in §6.5, because nobody has published one; you get to invent it.

---

## 2. Ground truth (verified 2026-07-02)

### 2.1 Corrections to ambient beliefs

These contradict memories/docs currently steering the system — officers reading the old narrative are navigating with a false map:

| Believed | Verified reality |
|---|---|
| Live runtime = `convergence-v2` worktree | **The main checkout is the live runtime** (`/Users/nate/captains-cabinet`, branch `feat/fidelity-harness-design`, dirty: ~57 modified + 44 untracked, last commit Jun 25). `claude/convergence-v2` is a fully-merged *ancestor*, ~141 commits behind. All `com.cabinet.*` plists and tmux cwds point at main. |
| Officers run Fable 5 | Officers run `claude-opus-4-8[1m] --dangerously-skip-permissions --effort max` (Fable was plan-gated Jun 23; your interactive session runs Fable again post-relogin — plan-bucket dynamics, see §6.3). |
| Policy shadow "fires on every call" | The bash hook fires on every call, but the **typed policy-shadow stream has emitted 31 events ever, none since Jun 28**. The 7-day burn-in the enforce-flip needs doesn't exist yet. |
| Consequence events carry `action_type` | The field is `action`; the graduation join key (lane × action_type taxonomy) **is simply absent** from live events. |
| teams-graph watchdog threshold mismatch | **Refuted** — pipe-watchdog already knows the daily cadence; that alert is fine. (The real watchdog bug is the PATH/redis-cli one.) |
| Jun 12–20 capture hole is total | Near-total: ~5 nonzero msgraph runs in the window; hole never backfilled either way. |

### 2.2 What demonstrably runs

- **Capture:** screenpipe core minutes-fresh (19.2GB db); email hourly work-hours (recovered post-outage); Teams daily-by-design (24h latency); embeddings 38,865 chunks reindexed ~15min, 64% content_ts-fenced; ~24 acting pipes produced output in the last 24h.
- **Cabinet:** 4 officer tmux sessions (7–9 days old) under launchd KeepAlive + 2h /loop re-arm; front door works end-to-end (intake-surface 5min, briefings delivered, draft-lane propose-only, approval→`chair_drafts.deliver_draft`→Make Graph proxy verified live); `pre-tool-use.sh` (1,576 lines) enforcing killswitch/germline/MCP-scope on every call; consequence ledger writing 2,542 events/48h.
- **Self-improvement actually closed (2 of ~14):** the **architect** pipe (earned auto-apply for reversible pipe changes, 6 confirmed/0 wrong — the only earned autonomy anywhere) and **golden-evals/hook-regression** (adversary findings demonstrably folded into the hook). Both currently degraded: architect missed its last 3 daily slots; its verdict source (reasoning-review) is wedged.

### 2.3 The severed loops (evidence)

| Loop | State | Evidence |
|---|---|---|
| Measure→graduate | severed ×3 | all 1,829 fidelity events `verdict="unknown"`; 0/72 draft approvals written back (42 null/27 expired/3 rejected); every cell `unmeasured` |
| Nate-signal spine | dead since Jun 10 | `me_signal.jsonl` last row Jun 10; `gate_decisions.jsonl` 160 rows, 0 live, 47% expired; `0-Self/core.md` frozen May 31; old bot polls `updates=0` |
| Mission/work-graph | never scheduled | no plist/crontab; 0 `work_item_assigned` ever; 6 active outcomes waiting |
| Retrodiction | n=1 | `retrodiction_series.jsonl` = one row (2026-06-11): decision-match **8.3%**, divergent 58.3%, style 0.586 vs 0.565 baseline |
| reasoning-review | wedged | 261/267 entries permanently unreviewed behind 40 unjudgeable pipe-health rows (head-of-line) |
| Officer reflect/retro/evolution/OVI | never scheduled | scripts exist (`self-improvement-loop.sh`, `role-evals-weekly.sh`, `ovi-weekly.sh`), no plists; 2 reflections in 8+ days; OVI never published once |
| Shadow parity | uncomputable | exact-hash matching: 0/249 "matches" — the R4 migration gate criterion cannot be evaluated |
| Daily self-improvement cluster | dark since Jun 29 | architect/autonomy/voice-profile/codebase-digest logs stop Jun 29; nothing alarmed (4× cadence grace) |
| Clone autonomy ladder | vocabulary only | `autonomy_lib` status hardcoded `"observe"`; 0 live decisions ever |
| Spend caps | metering $0 | `stop-hook.sh` cost writer not registered in `.claude/settings.json`; `cabinet:cost:*` keys empty |

### 2.4 The baselines that exist (use them; don't re-baseline)

- **Retrodiction (Jun 11, n=24):** decision-match 8.3%, partial 33.3%, divergent 58.3%; mechanics-fail 54.2%; style win-rate 33%.
- **Reply cell (Jun 20, n=10):** intent 40–50%, flat after the vault-retrieval fix → it's a *voice* cell; divergents are social glue ("Okay. fedt!").
- **Decision cell (Jun 20, n=12):** clone 58% intent-aligned vs generic assistant 33% — **+25pp clone-identity lift**, 0 values-divergent. Identity/context works; this is the thread to pull.
- **Human labels when you actually respond:** draft-reply ≈ 23% approve (5/22 non-expired) — consistent with 8.3%; the drafts aren't good enough yet, *and* the label stream to fix them is being discarded.
- **Attention reality:** 47% proposal expiry, 161 pending cards, `seconds_to_decide` median ≈ 30 days.

---

## 3. Diagnosis — why it doesn't compound

**D1. Building outruns operating ~7:1.** The estate's measured base rate for operating what it designs is ~14% (2/14 loops). Eight template pipes have never run once; the mission loop needed two plists for three weeks; the parity-proven enforce-flip has waited since Jun 28 for a one-liner. Any proposal that adds machinery without first consuming existing machinery is, on the evidence, a graveyard entry.

**D2. The system optimizes nothing because it measures nothing on a cadence.** One retrodiction point, no series, evals idle, judge uncalibrated, no per-class win-rates. "Self-improving" is currently a property of the *docs*, not the *system*.

**D3. Attention is the binding constraint and it's mis-spent.** Every outbound action costs one Nate decision regardless of track record; the queue design loses half the labels; and your own taxonomy shows self-automation already consumes **19% of your attention** (second-largest line) while PolAds (21%, Sept 1 launch) competes with it. Meta-work must be capped and made to pay back inside 30 days.

**D4. Substrate fragility caps trustable autonomy.** One machine runs everything; backups have no remotes; one Make.com delegated connection carries all email/Teams (already caused an 8-day silent brain outage); calendar is fully dark (12% of your attention is meetings and every brief says "0 events"); the watchdog can't alarm; ~50 plaintext secrets sit in officer-readable env; the killswitch fails *open* and any session may `DEL` it.

**D5. Duplicate organs, no circulation.** Two ledgers (gate_decisions vs consequence events), two autonomy machines (autonomy_lib vs graduation.py), two eval harnesses (retrodiction vs framework/fidelity), four lesson stores, two briefing generators. Each pair splits signal that is only useful concentrated.

---

## 4. What the research says (mapped to this system)

Full citations live in the workflow outputs; the decision-relevant findings:

1. **Your gate ledger is the most under-exploited asset in the estate.** Approve/edit/skip + edit-diffs + latency is simultaneously: regression-eval mint, prompt-evolution feedback (GEPA), trust-FSM promotion evidence, procedural-rule mine ("group mail from X → Nate declines"), and fatigue/drift telemetry. Six of the top-ranked techniques are different consumers of the same stream you currently discard.
2. **Decision fidelity ≠ style fidelity; they don't transfer.** Stanford genagents: **85% decision replication from interview material in context, no tuning** (arXiv 2411.10109). Your 8.3% is a *context/procedure* problem. Attack it with a **decision dossier** + analogous-past-decision retrieval + ledger-derived rules — not voice work, not fine-tuning. (Your +25pp decision-cell lift already confirms the mechanism locally.) The "SFT 44% vs prompting 25%" figure in your notes is folklore — no such published result exists. Fine-tune only at a measured style plateau, as a local LoRA sidecar, never for decisions.
3. **Self-improvement is safe only under a specific discipline:** decoupled evaluator (proposer never grades itself); cross-family judge calibrated against your real gate decisions; a **frozen, auto-minted, only-growing regression suite gating every prompt/playbook/skill/lesson change**; incremental delta updates to instruction files (ACE — wholesale rewrites cause context collapse); lessons as candidates-on-trial with eviction; git-branch archives for any self-modification (DGM pattern).
4. **Trust ladders that work:** slow promotion (Wilson lower-CI over n≥30 + dwell + human ratification), **instant human-free demotion** (CUSUM alarms), and — the red team's key addition — **post-graduation audit holdout**, because every demotion signal otherwise vanishes the moment you stop looking.
5. **The only production-validated path past draft-only** is rule-scoped auto-send on named low-blast scopes with an undo window (Microsoft Cowork pattern). Nobody ships global confidence-threshold auto-send. 
6. **Economics/ToS:** Anthropic scopes Max plans to individual usage; 24/7 fleets belong on Console API keys (per-lane workspaces). Fable Chair-only; Sonnet 5 (near-Opus agentic at $2/$10) for lanes; Haiku for pipes; cache-aligned wakes; hooks blocking non-Chair Fable spawns (documented post-compaction Fable cascades have burned users' monthly allowance in a day).
7. **Structural beats promptual security:** deterministic out-of-band gates held at ~2.6% attack success where in-band prompt defenses collapsed >90% under adaptive attack. Sleeper **memory poisoning is your most system-specific live threat**: anyone who emails you can currently write into the substrate every officer reasons from.
8. **Org shape:** don't add lanes (2–4 foreground is the human ceiling); grow per-lane autonomy. Slice missions to the **80%-success horizon (~2h nodes)** — Devin-class agents: 78% on clearly-scoped vs 15% on open-ended. Officers should be *logically persistent, physically ephemeral* (fresh sessions from durable handoff files beat 8-day tmux contexts + compaction).
9. **Validated non-bets:** no memory-platform migration (filesystem+strong harness beats Mem0/Zep/Letta on the benchmarks that matter), no GraphRAG, no LLM in the retrieval hot path, no auction task allocation, no corporate role-play orgs.

---

## 5. The honest 90% math

Attention-share taxonomy (evidence-sampled from 14 daily notes, 25 meeting notes, Monday mirrors, conversation volumes):

| Category | Share | Today | 12-mo realistic | Hard residual |
|---|---|---|---|---|
| PolAds engineering | 21% | draft-gated (strongest lane) | spot-check-only | product-taste calls, prod-risk decisions |
| AI-infra / self-automation | 19% | partially self-referential | **should shrink, not be replaced** | direction-setting, trust ratification |
| Meetings | 12% | capture ~parity; participation none | briefs/actions parity; attendance no | live negotiation, presence |
| Email/Teams | 11% | draft-gated, 23% approve | 60–70% notify-after on low-stakes | sensitive threads (salary, conflict, partners) |
| Other products (STEPhie, jobdanmark, …) | 8% | draft-gated | 70%+ | design taste, cross-product priority |
| Compliance/legal/publisher comms | 8% | draft-quality | strong draft parity | legal accountability, counsel negotiation |
| Leadership & 1:1s | 5% | nudges only | prep parity | ~80% irreducibly Nate |
| Planning/Monday hygiene | 4% | draft triage | mechanical parity | strategic trade-offs, saying no |
| Ops firefighting | 4% | detect-only | self-healing runbooks | consent ceremonies (OAuth, TCC) |
| Strategy/whitepapers/podcast | 3% | research parity | ghost-write 80% | reputation-bearing voice |
| Personal admin | 3% | nudge only | ~50% executable w/ approval | identity acts (MitID, notary) |
| Ad-ops (GAM/Prebid) — *your formal role* | 2% | **zero coverage** | monitoring/alerts | commercial relationships |

**Verdict: ~7% automated + ~33% draft-gated today → ~78% ceiling in 12 months; ~22% hard residual.** Three consequences:

1. **Reframe the goal**: the correct objective is *minutes of Nate-attention per outcome* (your OVI, never yet published) trending down, plus tap-surface shrink per work class — not "90% of tasks." As the system absorbs work, your job composition changes; "90% of current work" is a moving target that the attention metric handles and the task metric doesn't.
2. **The biggest single lever is not comms** — it's that self-automation (19%) must *shrink itself* (the system operating and improving itself without you as its SRE), and engineering (29% combined) must go from draft-gated to spot-check via verified mission execution.
3. **"Better than you" needs a new instrument** (§6.5) — every current metric measures *same-as-you*; the endorsement axis (what you'd endorse vs what you actually did) was designed but never wired, and it's the only path to detecting the clone being *right where you were wrong*.

---

## 6. The blueprint

Merged from the three architecture panels, then hardened by the red team (their fatal/serious findings are folded in as design constraints, marked ⚔ where they changed the design).

### 6.1 The One Flywheel (label economy → graduation)

**Signal spine — one tap point.** The Chair inbound poller (`officer-inbound-poller.py`) gets inline-keyboard buttons (Send / Edit / Skip, pid-embedded) plus deterministic parsing of `send` / `edit:<text>` / `skip:<why>`; the Chair LLM leaves the approval path (tmux-injection stays for free-text judgment only). Every verdict calls **`reply_binder.bind` as the single fan-out**: (1) consequence-ledger decision event (with `seconds_to_decide`, `edit_distance_ratio` ported from gate_ledger); (2) `me_signal.log_message` (revives nate-model); (3) `reply_enrichment.enrich_from_reply`; (4) `model:/wrong:/core:` prefixes → `nate_model.correct_layer`. ⚔ *One implementation, one writer — the old telegram-bot gets **no** writeback wiring (it is being retired); pid-idempotency asserted in tests. Expiring proposals fold into briefings as batched one-tap verdicts.*

**One ledger.** `~/Library/Application Support/cabinet/events/consequence-events-*.jsonl` is canonical. `gate_decisions.jsonl` + `autonomy_outcomes.jsonl` freeze as read-only archives (supersede-never-delete). Every new event stamps the canonical `(lane × action_type)` cell. ⚔ *Schema split: `review.verdict_human` vs `review.verdict_judge`, distinct provenance. **Promotion math reads human verdicts only**; judge verdicts are eligible for demotion and telemetry only — CI-asserted. Otherwise the system's own graders mint its promotion evidence.* ⚔ *Label provenance tiers: batched one-taps weight ≤0.5 toward promotion floors and **never** mint frozen-suite cases (rubber-stamp farming defense).*

**One harness.** `framework/fidelity` (gen-2: leakguard proven, intent verdicts, officer_runner) absorbs retrodiction's assets: conversations.md case extraction, the 3-channel style scorer + author centroid, `score_draft()` as hot-path grader **and as the semantic shadow-parity metric** (replacing exact-hash 0/249), CUSUM. Weekly scheduled run appends per-cell rows to one `fidelity_series.jsonl`. Judge v2: **cross-family** (via your Vercel AI Gateway), pairwise, position-swapped, deterministic rubric fields (recipient? action? commitment?) split from judged nuance, calibrated monthly against your blind-quiz picks. First analysis job: **decompose the 8.3%** into procedural / episodic / scoping failures — this split decides where P3 investment goes.

**Frozen regression suite (the foundation).** A pipe watches the ledger: every *edit with replacement text* mints {thread, your final text, diff}; every *typed* `skip:<why>` mints a should-not-draft case; quiz picks mint gold pairs. Content_ts-fenced, thread-level partitioned from quiz/training pools, ⚔ *30-day quarantine before a minted case becomes gating; suite directory is germline.* **No prompt/playbook/skill/lesson/dossier change ships without non-regression on the suite.** This single mechanism is what makes every other self-improvement loop safe to close.

**One graduation engine.** `graduation.py` + `authority-matrix.yml` + `trust_ladder.py` win; the clone's `autonomy_lib` 5-rung scaffold retires (its lanes become decision-cells). Hardened: promotion = Wilson lower-CI clears the bar over **n≥30 with edits counted (not consecutive)** + dwell + your one-tap ratification; demotion automatic, instant, human-free on CUSUM alarm. ⚔ *Pool scopes into fewer, fatter cells (one "internal routine comms" cell, not five micro-scopes) so n≥30 is reachable in weeks at your volume — honest timeline to first auto-send: day 60–90.* ⚔ ***Post-graduation audit holdout: every graduated cell keeps ~10% of actions randomly gated forever (or a weekly 5-item post-hoc sample). Demotion fires on holdout disagreement — otherwise every decay signal structurally vanishes when you stop looking.*** Hard-ceiling classes (external_comms beyond granted scopes, deploy_prod, spend, secrets, network_write, credentials_grant) stay always-gated at every confidence, forever, CI-asserted.

### 6.2 Org runtime & reliability

**Mission loop ON (throttled).** Schedule `mission-supervisor.sh` + `outbox-relay.sh` (the two missing plists). Compiler slices the 6 ratified outcomes into ~2h nodes at the 80% horizon, each with an executable done-check. ⚔ *Switch on only after the approval plane works, throttled to ≤3 nodes/officer/day, mission proposals batch-tier (exempt from your ping budget) for the first two weeks.* Completion path: officer → **fresh-context verifier** — a no-write-tools judge session holding the *original* node spec, default-FAIL, evidence required — before anything advances the graph or reaches Telegram. Verdicts land as `verdict_judge` (never promotion evidence).

**Immune system.** ⚔ *No conductor rewrite* (a custom scheduler daemon replacing launchd is a multi-week substrate rewrite with enormous migration tail risk). Instead: keep launchd; add **`jobs.yml` as the single manifest** of all ~65 pipes + cabinet crons (command, cadence, machine, expected wrote-count floor, alert tier) + a lint/audit script (declared vs installed vs firing; absolute-path check — the PATH bug class becomes lint); wrap jobs with heartbeat pings. **External out-of-band dead-man (healthchecks.io):** scheduler-alive, briefing-delivered, capture-fresh, backup-fresh, mission-supervisor-ran — breaches reach your phone independent of Redis, Telegram, and the Mac itself. **Weekly synthetic-kill drill** proves the alarm path (the current watchdog failed precisely because its alarm was never exercised). Data-dry trends (wrote=0 streaks) alarm, not just process death.

**Officer lifecycle: logically persistent, physically ephemeral.** Wake = spawn a fresh session from `lane-progress.md` + tier2 handoff; work one node; write handoff; exit. Kills compaction drift, 8-day context rot, and send-keys fragility; wakes scheduled inside the 1h cache TTL. ⚔ *Handoff files get a schema + a spawn-time sanity check against ledger/work-graph state, and are git-committed per wake (they're now the officers' memory — an ungated behavior-shaping artifact otherwise).* Pilot one lane before fleet-wide.

**Topology (this cycle).** ⚔ *The Mac Mini does exactly three dumb things now:* bare git remotes for estate+vault, nightly `sqlite3 .backup` snapshot target for db.sqlite, healthchecks relay. **Officer/fleet migration to the Mini waits** until ephemeral sessions have run 30 clean days — then it's a config change, not a distributed-systems project. Never binary-sync a live `embeddings.db` (rebuild from the vault replica instead).

**Capture repairs.** Make.com canary (hourly known-answer probe; classify healthy / degraded / auth-dead; ping-now with the re-auth runbook — the June outage took *weeks* to notice). Backfill Jun 12–20 (scripts exist; state files predate the outage). **Calendar via EventKit**: add the Outlook account to macOS Calendar.app (EWS/ActiveSync typically allowed where Graph app scopes are tenant-blocked) and read locally — a 30-minute test that lights up 12% of your attention share; ⚔ *you self-sanction the tenant-policy workaround in writing — you own that call, not an officer.* Teams back to hourly work-hours when Make budget allows. iMessage/browser senses: ⚔ *work-contact allowlist only; partner/family threads never indexed (0-Self-class fence).*

**Runtime hygiene.** ⚔ *Inverted from "deploy checkout ceremony": keep your live-iteration workflow, but (a) the enforce-flip and any autonomy grant require a clean committed tree at flip time, (b) a drift alarm (not gate) fires on dirty-runtime >24h.* Full tagged-deploy discipline only when officers move to the Mini. Retire the convergence-v2 worktree narrative everywhere (it's the false map).

### 6.3 Trust envelope & economics

**Structural safety first (small, verified):**
- **Killswitch fail-closed** for officer sessions (Redis empty/unreachable ⇒ block) + **delete the universal `DEL cabinet:killswitch` whitelist** (`pre-tool-use.sh:53-66`) — today any officer can un-halt the fleet. Resume authority = you, via typed token. ⚔ *Sequenced strictly after the watchdog/dead-man fixes so a Redis hiccup alarms instead of silently halting the fleet.*
- **Spend metering real:** register `stop-hook.sh` in `.claude/settings.json`; but ⚔ *ground truth = Console workspace billing polled daily (the Redis hook never sees API-key pipe calls or judge bursts); the hook is intraday early-warning only.*
- **Billing/ToS — pulled to P0:** ⚔ *all three panels scheduled this for P2; the red team correctly called that existential-risk-deferred. Create the Console org + per-lane workspaces and move the 24/7 fleet to API keys NOW on judgment (Chair=Fable xhigh; lanes=Sonnet 5 high; pipes/classifiers=Haiku); Max reverts to your interactive use. Run the Sonnet-5-vs-Fable comparison on your own harness later as confirmation, not gate. Hook-enforce: non-Chair Fable spawns = 0.* Cost envelope: ~$300/mo (P0–P1) → ~$600 (P2) → ~$1,200 (P3), alarmed at 2×.
- **Egress + secrets, cheap first:** Claude Code strict sandbox for unattended officers (deny-by-default network allowlist per lane, filesystem scoped) + read-exclusions on credential paths. ⚔ *Broker v1 owns ONLY the Make send webhook* (the send-as-Nate capability), running as a **separate macOS user with a 0600 ledger from day one** (an officer running as `nate` can otherwise forge approval rows — approval validation is theater without write isolation). Monday/Neon/Vercel tokens migrate one per month with rollback env vars.
- **`escalate(reason)` tool — a P0 one-liner** in officer prompts (the sanctioned raise-your-hand channel; strongest published misalignment-reduction effect for its cost). The separated trajectory monitor runs observe-only from the enforce-flip onward; its tuning is P4.

**Enforcement flip sequence (P2, all mechanisms already built):**
1. Officers resuscitate the policy-shadow stream (31 events ever — the burn-in corpus doesn't exist yet) → **7-day fresh burn-in** on the corrected event stream; zero unsafe-direction divergence vs the bash hook.
2. You apply `CABINET_AUTHORITY_ENFORCING=1` (germline one-liner — parity proof done Jun 28), with a clean committed tree. Bash regex layer retained 30 days as defense-in-depth, then retired.
3. You author `trust-ladder.yml` (from the draft minted off your actual usage) + `autonomy.yml` (the germline guard currently protects a nonexistent file).
4. First graduated cells: the low-blast pooled ones (Monday status moves, tier2 notes, internal routine comms) — promotion card carries the full evidence.
5. **First auto-send scope** (~day 60–90): internal acks/confirmations to STEP/JFM colleagues, 10-min undo, ⚔ *with channel-health check before firing (undo riding a 409-prone Telegram is decorative otherwise), fail-closed queue on channel degradation, audit holdout from day one, per-scope cancel/edit alarms auto-suspending the scope.*

**Never-lie as enforcement (your #1 priority, currently plan-only):** claim-extraction over every outbound draft → STRIP / SOFTEN / HOLD-AND-ASK with an evidence dossier rendered in the approval card; unverifiable claims can't reach the outbox even approved. This is also what makes *faster approving* safe — you stop having to fact-check every card yourself.

### 6.4 Memory & knowledge

- **Decision dossier (the 8.3% attack, P3's single permitted opening item):** nightly-compiled, git-versioned, as-of-T-capable dossier from nate-model layers + 5-Reflections/Decisions + self-knowledge answers + commitment stances + **ledger-derived procedural rules**; retrieved analogous past decisions injected per case (genagents pattern, 85% decision replication). ⚔ *Every new compile re-runs the frozen suite before going live (it shapes every output — otherwise it's a silent-regression backdoor), and intent-reconstruction for any adjudication uses only pre-cutoff artifacts, never dossier content the optimizer edits.*
- **ACE playbooks (simplified per red team):** consolidate the four lesson stores (Drafting-Lessons, _lessons.md, captain-patterns, captain-intents) into per-surface playbooks with three cheap rules now — no wholesale rewrites (hook-enforced), ID'd bullets with provenance refs, top-k retrieval instead of tail-reads. Candidate/trial/eviction lifecycle and leave-one-out attribution wait until label volume proves them computable. Fix `captain-rules-index.yaml` (48 dead anchors, 0/17 live patterns indexed — encoded rules are currently unfindable).
- **Bitemporal belief layer (later):** a SQLite `beliefs` table (subject, predicate, object, confidence, provenance→chunk, valid_from/until, superseded_by) over the immutable vault — the Graphiti *schema* without the platform. Serves `beliefs_as_of(T)` to the fence and kills the Frederik-triple-nudge class. P3+, only after labels flow.
- **Taint/provenance (80/20 now, schema later):** ⚔ *thread-scoped, not reply-scoped* — any durable fact extracted from a thread containing untrusted-inbound content inherits `untrusted-inbound` provenance even if your own sentence stated it (your approve-tap otherwise launders attacker content into trusted-self memory). Now: quarantine file + weekly batch veto for externally-triggered memory writes; draft path refuses long verbatim spans from untrusted inbound. Full provenance column on chunks: P3.

### 6.5 Beyond parity — the instrument that doesn't exist yet

Nothing published measures "better than the principal." The design, anti-gamed:

1. **Endorsement axis (wire what was designed):** distinguish *what you did* from *what you'd endorse*. On divergent cases, a weekly 2-minute adjudication: "clone proposed X, you did Y — which was right?" Clone-wins are the first `better-than-Nate` labels. (Everything today scores mimicry, including of calls you'd regret.)
2. **Weekly blind self-pick quiz (~5 pairs, inside the attention budget):** your archived real reply vs blind clone draft, anonymized, randomized. Per-class pick-rate ≥50% sustained = parity; it simultaneously calibrates the judge. ⚔ *Thread-level partition from the frozen suite and any training pool; track pick latency + repeat-pair consistency (single-annotator decay is an open research problem — instrument it from day one).*
3. **Outcome telemetry as adjudication evidence, never as a target:** recipient response latency, thread-resolution within 7d, downstream corrections, commitment-closure — ⚔ *Goodhartable if optimized (drafts that demand replies "win"); used only as evidence in human adjudication.*
4. **Quarterly shadow-Nate week:** you write your own replies for one week; the clone shadows; blind-compare. This resets drift in the gold standard as *you* change (person-drift vs clone-drift disambiguation is an open bet).
5. **Promotion meaning:** "better than Nate on class C" = quiz win-rate >50% + endorsement wins > losses + zero holdout regressions over a quarter. That class becomes a candidate for *delegation without review* — the only evidence-grounded meaning of "outperforms me."

---

## 7. The program

⚔ The red team's dimensional finding governs everything here: three panels proposed 48 workstreams + 21 ratifications + 3–5× your label throughput. **~7 of 48 would ever run.** So: one merged plan, ≤12 items in flight, hard freeze on later phases until *exit criteria are met, not scheduled*, and a global attention budget of **≤5 surfaced decisions/day + ~5 quiz picks/week + ≤8 Nate-hours/month of meta-work** — with pick-latency instrumented and an auto-halving rule on rise.

### P0 — Resuscitate (days 0–30, ≤12 items, nothing new gets built)
1. pipe-watchdog PATH fix + error surfacing (stop swallowing `FileNotFoundError`).
2. External dead-man (healthchecks.io: scheduler/briefing/capture/backup/mission checks) + weekly synthetic-kill drill.
3. Kickstart the dark daily cluster; stale threshold 4×→1.5×; unwedge reasoning-review ⚔ *(unknown-after-3 → weekly unjudgeable digest, never silent "reviewed")*.
4. Off-machine durability: Mini bare git remotes (estate+vault) + nightly db.sqlite `.backup` rsync + the `embeddings.db-*` gitignore fix.
5. Make.com canary + Jun 12–20 backfill.
6. Telegram token split (one token, one owner; kill the 409 war) — every label depends on this channel.
7. Cost writer registered **+ Console org / per-lane API keys for the fleet** (ToS exposure ends now; Max → interactive only).
8. Killswitch fail-closed + DEL-whitelist removal (after 1–2).
9. **The tap point** (one implementation): poller buttons + deterministic parse → `reply_binder.bind` fan-out → consequence ledger only; `verdict_human`/`verdict_judge` split; expiring proposals → briefing one-taps (weight ≤0.5); pre-era 1,829 events retired as unlabeled history.
10. Calendar EventKit test (30 min) → calendar pipe if it works.
11. `escalate(reason)` tool line in officer prompts.
12. **Execute the deletion list** (§8) — the cheapest wins in the estate.

**P0 exit criteria (gates P1):** zero silent job deaths for 2 consecutive weeks (proven by the drill) · live labeled decisions flowing (>30/week) · fleet on API billing · backups verified restorable on the Mini.

### P1 — Label economy (weeks 3–8)
Mission loop ON (throttled, batch-tier); frozen regression suite (quality-guarded mint + quarantine); harness merge + weekly cadence + cross-family judge; 8.3% decomposition analysis; weekly blind quiz (5 pairs); shadow-parity via `score_draft`; briefing dedupe (7-day recorded parity → retire the loser); never-lie Stage 1 in the draft path.
**Exit criteria (gate P2):** ≥50 live labeled decisions/week for 2 consecutive weeks · expiry <15% · fidelity series ≥4 weekly points · verdict coverage >90% on new events.

### P2 — Autonomy flip (weeks 8–16)
Policy-shadow resuscitation → 7-day burn-in → **you flip `CABINET_AUTHORITY_ENFORCING=1`** (clean tree) → trust-ladder + autonomy.yml authored → first pooled cells graduate (Monday writes, tier2, internal routine comms) → broker v1 (Make webhook, separate user) → ephemeral officers (one lane pilot → fleet) → first auto-send scope with holdout + channel-health guard (~day 60–90) → separated monitor observe-only.
**Exit criteria:** ≥3 cells measured (n≥30) · ≥1 cell you've granted `ive-done` · holdout stream flowing · zero hard-ceiling autos (CI green).

### P3 — Coverage (months 4–9, re-derived from what the labels actually show)
Opening item: **decision dossier** (suite-gated compiles). Then, guided by the 8.3% decomposition: ACE playbook lifecycle, GEPA nightly prompt evolution (offline, suite-gated), per-class shadow ground truth (Monday triage verdicts, PR approve/request-changes — seed: the never-scored 52-case git corpus), taint schema on chunks, officer migration to the Mini (post-30-clean-days), ad-ops sense (GAM/Prebid — your formal role's blind spot), Teams hourly.

### P4 — Beyond parity (months 6+)
Endorsement adjudication at full cadence, outcome-telemetry evidence, quarterly shadow-Nate weeks, delegation-without-review for classes that earn it, monitor tuning, LoRA style sidecar *only if* the style axis measurably plateaus.

---

## 8. Delete / stop / don't build

**Delete now (all evidence-verified dead or harmful):** the 8 never-run template pipes (top-of-mind, day-recap, standup-update, time-breakdown, missed-todos, collaboration-patterns, automate-my-work, session-digest) · teams-ocr-capture (0 conversations every run) · conversations-sync audio phase (0 segments in 2,573 runs) · exact-hash shadow matching · `gate_decisions.jsonl` as live store (freeze as archive) · clone-side `draft-outbox.md` dead-end (fix `brain-bridge.md` docs accordingly) · digital-clone curator pipe (architect proposed retirement twice; proposals expired — a live demo of the broken label loop) · the LLM-in-the-approve-path (tmux injection for verdicts) · one of the two daily briefings (after the parity week) · stale SAFETY_BOUNDARIES/KILLSWITCH Docker-era content.

**Don't build (research-validated non-bets):** fine-tuning now · memory platforms / GraphRAG · global confidence-threshold auto-send · new officer lanes · conductor scheduler-daemon rewrite · two-machine officer split this cycle · full credential-broker for all tokens at once · Gmail BCC revival · auction/blackboard task allocation · agents authoring their own charters unratified.

---

## 9. The dashboard (ratio metrics; raw volumes tracked so suppression is visible)

| Metric | Baseline (today) | Target |
|---|---|---|
| Live labeled decisions/week | **0** | >50 by P1+2wk |
| Proposal expiry | **47%** | <15% (P1), <10% (P2) |
| New events with human/judge verdict | ~0% | >90% |
| Cells not `unmeasured` / graduated | 0 / 0 | ≥5 / ≥1 by P2 exit |
| Decision-match (retrodiction, weekly) | 8.3% (n=1, Jun 11) | trend + Wilson CI, per rubric field |
| Blind-quiz clone pick-rate | — | 45–50% = parity, per class |
| **Nate-attention per delivered outcome** | unmeasured (OVI never published) | published weekly, trending down |
| Taps/day on outbound (with raw proposal volume alongside) | ~100% of actions | −30% by P2 exit |
| Auto-send cancel/edit rate | — | <2%, else auto-suspend |
| Holdout disagreement on graduated cells | — | ~0; any spike = auto-demote |
| Silent-death MTTD | 3 days (Jun 29 cluster); weeks (Graph outage) | <30 min, drill-proven weekly |
| Backup lag (vault/estate remote; db snapshot) | ∞ (no remotes; never) | <1h / <24h, restore-drilled monthly |
| Fleet spend | unmetered ($0 reads) | Console ground truth, envelope-alarmed |
| Fable tokens from non-Chair sessions | unenforced | 0 (hook-enforced) |

---

## 10. What only you can do (~one focused day, then ~20 min/week)

**One-time (unblocks everything):**
1. Ratify this plan's spine: single ledger, single tap point, P0 list, phase freeze rules.
2. Console org + per-lane workspaces + budget ceiling ($300/$600/$1,200 by phase); Max → interactive only.
3. BotFather: second bot token (interactive sessions) so the Chair token has one owner.
4. Author `trust-ladder.yml` (from the draft) + `autonomy.yml` (from example); confirm the 6 outcomes in `outcomes.yml` are still the right 6 before the mission loop compiles them.
5. Apply the `CABINET_AUTHORITY_ENFORCING=1` germline one-liner *after* the 7-day burn-in (officers cannot and must not).
6. healthchecks.io account (job-name-only payloads); Mini SSH for remotes/snapshots.
7. EventKit calendar 30-min test (your tenant credentials); self-sanction the EWS workaround in writing.
8. Ratify the first auto-send scope + undo window; killswitch resume authority (typed token, you only).
9. Decide: re-judge the 1,829 pre-era events (~$15–30) or retire them (recommended: retire; start the series clean).

**Recurring (the flywheel's fuel — hard-capped):** ≤5 surfaced decisions/day · ~5 blind-quiz picks/week · ~2 divergence adjudications/week · one 20-min monthly review of graduation/holdout evidence. If this proves too much, the system auto-halves the ask — a starved label economy with honest telemetry beats a fat one that dies of fatigue like the last one did.

---

## 11. Risks & open bets

1. **The operating pathology is the meta-risk.** The plan's freeze rules and ≤12-item cap are the mitigation; if P0 isn't done in 30 days, the correct move is to *shrink the plan again*, not push harder.
2. **Anthropic ToS/enforcement** on the current Max-OAuth fleet — the one existential ops risk; P0 item 7 removes it.
3. **Single-annotator label economics** (open research): can one person sustain the label rate without decay? Instrumented from day one; auto-halving rule.
4. **Person-drift vs clone-drift:** you will change; recency-weight retrodiction sampling now; quarterly shadow-Nate weeks recalibrate; carrying evidence across a detected preference shift is unsolved.
5. **Sonnet 5 vs Fable on your own harness:** if within noise for lane work, fleet economics transform. Run as confirmation once the harness has cadence.
6. **The 8.3% decomposition** decides P3. If it's mostly *scoping*, the fix is mission-slicing and narrower ask-classes, not smarter memory.
7. **JFM tenant limits** may block cleaner integrations (Graph app scopes); EventKit/EWS is the pragmatic detour; escalate to tenant admin only if it pays.
8. **Beyond-parity metric is invented here** — treat §6.5 as an experiment design to falsify, not a settled instrument. It's also the piece most worth publishing if it works.

---

## 12. Appendix

**Verification deltas folded into this report:** live runtime = main checkout (not worktree) · officers on Opus 4.8 · policy-shadow 31 events ever (burn-in corpus must be created) · consequence field is `action`, no `__unstamped__` literal (the taxonomy stamp is absent, which is the actual problem) · teams-graph watchdog-threshold claim refuted · Jun 12–20 hole near-total (5 nonzero email runs) · `evolution-loop.sh`/`cross-officer-retro.sh` don't exist by those names (`retro-trigger.sh`/`retrospective.sh` do, plist-less) · heartbeat-watchdog `.out.log` empty since May 26, `.err.log` stopped Jun 9.

**Key sources (full URL lists in the workflow outputs under `/Users/nate/.claude/projects/-Users-nate/ab9e35b6-134f-482e-8060-8448b6d5ab93/tasks/`):** Stanford genagents (arXiv 2411.10109) · GEPA (arXiv 2507.19457, ICLR'26) · ACE (arXiv 2510.04618) · Zep/Graphiti bitemporal KG (arXiv 2501.13956) · Digital-apprentice trust FSM (arXiv 2606.04321) · self-preference bias (arXiv 2410.21819) · memory-poisoning across vendors (arXiv 2605.15338) · CaMeL/deterministic gates (Willison, Apr 2025) · METR time-horizons · MAST multi-agent failure taxonomy (arXiv 2503.13657) · Anthropic: effective harnesses for long-running agents, demystifying evals, agent-teams docs, legal/compliance (plan-usage scope) · Microsoft Copilot Cowork auto-send pattern · Letta filesystem-memory benchmark · claude-code#67506 (post-compaction routing burn).

**Workflow artifacts:** system deep-read `tasks/wi4edg4rb.output` · research sweep `tasks/wff89sjww.output` · verify+design+red-team `tasks/wr46z9anx.output` (per-agent journals under `subagents/workflows/`).
