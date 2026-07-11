# Plan A — The Personal Clone Org (MacBook · screenpipe · Obsidian brain · Chair)

> **HISTORICAL RECORD** (banner added 2026-07-11, hardening loop — record
> unedited below): paths cited may predate later moves, e.g.
> `cabinet/scripts/lib/policy_engine.py` → `framework/authority/policy_engine.py`
> (@3aa93ef8, CG-14) and the `constitution/` retirement (@5cfe9453). Current
> execution truth lives in `operative-egg-ledger-2026-07-07.yml` + `EXECUTION-STATUS.md`.

**Date:** 2026-07-02 · **Flavor:** A (personal clone / autonomous assistant) · **Companion:** Plan B (Mac Mini product org, `~/plan-B-macmini-product-org-2026-07-02.md`) shares Phase F0 (identical in intent, item IDs differ — map by intent; execute once).
**Binding inputs:** `~/self-improving-org-report-2026-07-02.md` (§P0 12-item list + design rulings), `~/mac-mini-ai-org-blueprint-2026-07-02.md` (§2 diagnosis, §4.2 evidence plane, §6 principles, §7 flavor-A divergences), the understand/research artifacts under `~/mac-mini-ai-org-blueprint-artifacts-2026-07-02/`.

## Mission

Turn the already-designed, mostly-severed clone estate into one operating flywheel: every Nate verdict (send/edit/skip, quiz pick, adjudication, correction) lands mechanically on ONE consequence ledger; ONE graduation engine converts human verdicts into per-cell earned autonomy; ONE harness measures decision/intent/style fidelity on a weekly cadence and mints a frozen, only-growing regression suite that gates every self-modification; the ~63-pipe perception estate is rationalized to KEEP/MIGRATE/RETIRE dispositions with shadow-parity retirements; the personal memory stack (vault + embeddings + nate-model + bi-temporal beliefs) gets consolidation, provenance and backups; and the clone-quality program (decision dossier + never-lie stages + the better-than-Nate instrument) attacks the measured 8.3% decision-match. Nothing new is built where wiring or deleting suffices; nothing advances past a phase exit that has not been machine-checked; the whole program is fitted to Nate's attention budget (≤5 surfaced decisions/day, ~5 quiz picks/week, ≤8 meta-hours/month) because attention — not architecture — is the measured binding constraint.

## Definition of Highest Potential

**North-star metric (report ruling, binding): Nate-attention-minutes per delivered outcome, published weekly, trending down** — paired with a per-work-class *better-than-Nate win rate* (§6.5 instrument). NOT "% of tasks automated": the honest 12-month ceiling is **~78%, not 90%** (report §5), and the ~22% residual (live meetings, salary/leadership, legal accountability, identity ceremonies) is permanent. The plan's end-state is a system that (a) measures itself weekly, (b) earns autonomy per pooled cell on human verdicts only, and (c) makes its own upkeep shrink (self-automation attention share 19% → <10%).

**You know you're there when:**
1. **Labels flow:** ≥50 live human-labeled decisions/week land as superseding `verdict_human` events for 4+ consecutive weeks; proposal expiry <10%; `me_signal.jsonl` grows daily (vs frozen at 80 rows since Jun 10).
2. **One lane acts:** ≥1 pooled low-blast cell (newsletter-digest or archive-email) runs auto behind a 7-min fail-closed veto window, with ~10% audit holdout, cancel/edit rate <2%, zero hard-ceiling autos (CI-green invariant).
3. **The clone is measurably better somewhere:** blind-quiz pick-rate ≥45–50% on ≥1 class AND endorsement wins > losses on that class over a quarter — the first evidence-grounded better-than-Nate label.
4. **The estate runs itself:** 8 consecutive weekly synthetic-kill drills caught by the alarm path; monthly restore drill green (vault + state + 19GB db.sqlite); zero silent job deaths; silent-death MTTD <30 min (vs 3 days–weeks today).
5. **Singularity of organs, CI-proven:** one ledger, one graduation engine, one harness, one scheduler truth, one Telegram send path, one canonical decision store — each with a grep tripwire that fails CI on regression.
6. **The Captain surface is one voice with a debt queue:** briefs/pre-meeting/what-needs-you-now all through the Chair composer, calendar no longer dark, Captain-debt queue surfaced in every briefing, and Nate's recurring ask auto-halves if pick latency rises.

## How to read this plan

- **Phases are dependency-ordered, never calendar-ordered.** A phase opens only when its predecessor's exit criteria are machine-checked. Global rule (report §7, binding): **≤12 items in flight estate-wide**; if a phase stalls 30 days, shrink the plan, don't push.
- **Owners:** `NATE-ONLY` (only Nate's hands/authority: germline applies, tokens, TCC/OAuth, account creation, ratifications — all duplicated in Appendix B) · `Chair` (the cos officer session) · `Builder` (a dedicated Claude Code build session in `~/captains-cabinet` or `~/.screenpipe`) · `any-CC-session`.
- **"Done" = scheduled + fed + watched** (constraint 7): every item shipping a component ships its launchd job, a data-freshness assertion, and a watchdog expectation in the same change. Code-written-only is not done.
- **Grounding:** every item cites a real path, a report/blueprint finding, or a research technique. Paths verified against the live filesystem 2026-07-02.
- **F0 is shared — execute once; both Plan A and Plan B depend on it.** Do not run two copies.

**Phase roll-up (attention front-loaded by design):**

| Phase | Items | NATE-ONLY | Dominant effort | Opens when |
|---|---|---|---|---|
| F0 Shared Foundation | 19 | 6 (≈3h) | days | now |
| A1 Labels + Data Safety | 16 | 2 (≈45m) | days | F0 exit |
| A2 Measurement Plane | 9 | 0 | days–week | A1 exit |
| A3 Pipes Estate | 17 + table | 1 (≈20m) | days | A1 exit (retirements need A2.7) |
| A4 Memory Program | 13 | 0 | days–week | A1 exit (A4.4 after labels) |
| A5 Clone Quality | 13 | 1 (≈20m) | week+ | A1.2 (Stage 1) / A2.4 (dossier) |
| A6 Loops + Substrate | 11 | 1 (≈20m) | days–week | A2.4 |
| A7 Autonomy Graduation | 13 | 4 (≈1.8h) | days + dwell | A1+A2+A5 evidence |

## Governing constraints (binding, from blueprint §6 — violations are defects)

1. The gate is the mechanism. 2. Approval-surface owner owns label capture atomically (verdict emit in-process; ledger-liveness starvation auto-revokes autonomy). 3. No loop edits its own judge (germline code; READ-isolated holdout). 4. Machine truth first, human judgment reserved — **flavor A promotes on HUMAN verdicts only**. 5. Never trust the actor's narrative (dual-source; fabrication demotes). 6. Fail closed, degrade honestly. 7. Built = scheduled + fed + watched. 8. One joint per function; migrations verify evidence continuity as an explicit gate. 9. Episodic execution over durable state. 10. The Captain is a metered two-way resource (escalation <10%, Captain-debt queue, ≤5 decisions/day). 11. Asymmetric autonomy is correct — never equalize by weakening a gate. 12. Reversibility prices everything. **HARD CEILING (never lifts): external_comms, deploy_prod, spend, secrets, network_write, credentials_grant** — CI-asserted in `framework/policies/authority-matrix.yml`; the receipt carve-out (A5.5) is implemented as executor-enforced conditions, never a ceiling-row lift.

## Sequencing DAG (dependency, never calendar)

```
F0 (shared foundation)
 └─► A1 (labels + data safety)          ← nothing else opens until M1
      ├─► A2 (one measurement plane)    ← consumes A1's live verdicts to mint the suite
      │    ├─► A5 (clone quality)       ← dossier/never-lie gated by suite; re-aimed by A2.5
      │    └─► A6 (loops + substrate)   ← the Gate (A6.5) consumes A2.4
      ├─► A3 (pipes estate)             ← parallel with A2/A4; retirements gated by A2.7 parity
      └─► A4 (memory program)           ← parallel; A4.4 beliefs waits for labels (A1 exit)
                A2+A5+A6 evidence ─► A7 (autonomy graduation — always last)
```

Parallelization: A3 and A4 are independent of A2 except where marked (A3.13–16 need A2.7; A4.13 needs A2.4). A5.1 (never-lie Stage 1) may start the moment A1.2 lands — it is approve-only and Nate's #1 priority. The ≤12-in-flight cap applies across ALL phases jointly.

**The first 14 days, in literal order** (dependency-honest; not a calendar promise):
1. F0.10 watchdog PATH fix (hours — the alarm system before anything it must watch).
2. F0.13 + F0.13a external dead-man + first synthetic-kill drill (proof the alarm path works).
3. F0.9a + F0.9 Mini remotes + nightly db snapshot (data safety before any migration touches anything).
4. F0.0 spine-ratification sit-down — batch F0.8a, F0.11a, F0.15 into the same session (one Captain hour, four debts cleared).
5. F0.2 → F0.1 → F0.3 repo canonicalization (scan, retire dead deploy path, commit, push, CI).
6. F0.5 reply_binder wire — verdicts start landing mechanically even before the buttons exist.
7. F0.6 + F0.7 + F0.8 one send path, ledger-liveness dead-man, killswitch fail-closed.
8. F0.11 Console keys live; F0.14 kill list with tripwires.
9. A1.1 + A1.2 the tap point. Everything else queues behind M0/M1 evidence.

**Interface to Plan B (what B consumes from here):** F0 in its entirety (execute once) · the A1.3 schema split and A1.5 canonical-ledger conventions (B's probes write `verdict_judge` to the same schema) · A2.4's gate-check contract (B's gate-runner reuses the mint/pass^k semantics against product traces; B deliberately swaps the 30-day quarantine for B5.3's verified additive auto-admit) · the A3.2/F0.4 manifest+auditor pattern (B's `services.yml` on the Mini) · A6.6's episodic-officer evidence (B ships its episodic Builder independently at B4.12 — core to its design, not gated on this pilot; A6.6's 30-day result informs whether B's *Chair* also goes episodic). Flavor divergence stays as ruled: A promotes on human verdicts, B on machine probes with the test-diff Goodhart valve closed.

## Dashboard (flavor-A vector — ratio metrics, raw volumes alongside so suppression is visible)

| Metric | Baseline (2026-07-02) | Target | Owning items |
|---|---|---|---|
| Live labeled decisions/week | **0** (all inputs listen to a dead bot) | >30 by M1+2wk, >50 by A2 exit | A1.1–A1.5 |
| Proposal expiry | **47%** | <15% (M1), <10% (A7) | A1.4, A1.10 |
| New events with human/judge verdict | ~0% (1,829/1,829 `unknown`) | >90% | A1.2, A1.3 |
| Cells measured / graduated | 0 / 0 | ≥5 / ≥1 by M4 | A1.6, A7.3–A7.4 |
| Decision-match (weekly series) | 8.3% (n=1 run, Jun 11) | trend + Wilson CI, per rubric field | A2.2, A2.5 |
| Blind-quiz clone pick-rate | — (never run) | 45–50% = parity, per class | A2.6 |
| **Nate-attention per delivered outcome** | unmeasured (OVI never published) | published weekly, trending down | A7.9 |
| Taps/day on outbound | ~100% of actions | −30% by M4 | A7.4, A7.5 |
| Auto-send cancel/edit rate | — | <2%, else auto-suspend | A7.5 |
| Holdout disagreement on graduated cells | — | ~0; any spike auto-demotes | A7.7 |
| Silent-death MTTD | 3 days (Jun 29 cluster) – weeks (Graph outage) | <30 min, drill-proven weekly | F0.10, F0.13, A3.4 |
| Backup lag (vault/estate remote; db snapshot) | ∞ (no remotes; never) | <1h / <24h; restore-drilled monthly | F0.9, A1.13 |
| Fleet spend | unmetered ($0 reads) | Console ground truth, envelope-alarmed 2× | F0.11 |
| me_signal rows/day | 0 (frozen at 80 since Jun 10) | ≥5/day | A1.7 |
| content_ts fence coverage | 64% (21,144/33,917 chunks) | ≥80%, NULLs honest | A4.2 |

---

# Phase F0 — Shared Foundation (execute once; Plan A and Plan B both depend on it)

> **Packaging note (cross-plan ruling):** F0 is ONE shared phase whose scope is the UNION of Plan A's F0.* and Plan B's F0.* lists — the plans package the same phase differently (IDs differ; a few items appear in only one list, e.g. A-side F0.0 spine ratification and F0.16, B-side F0.7 verdict-schema split). An item in either plan's F0 is shared-phase work, executed once. Exit = the union of both exit lists.

**Goal.** Make the system real (versioned, reproducible, CI-tested), make verdict capture mechanical, put in the operational floor (backups, dead-men, killswitch, cost), and execute the kill-list so every following migration happens at a single joint. Nothing in A1+ is trustworthy until F0 exits: today the live runtime is a dirty tree 141 commits past any remote (`~/captains-cabinet`, branch `feat/fidelity-harness-design`, ~57 modified + 44 untracked incl. the live `framework/watchdog/` and `framework/autoreply/`), the 19.2GB `~/.screenpipe/db.sqlite` is backed up nowhere, the killswitch fails open, and the watchdog cannot alarm (blueprint §2.3-D/F, report §2.3).

| ID | Item | What exactly | Verification | Owner | Effort | Depends on |
|---|---|---|---|---|---|---|
| F0.0 | Ratify the plan spine | One sit-down: single ledger, single tap point, this P0/F0 list, phase-freeze rules, ≤12-in-flight cap, retire-vs-rejudge call deferred to A1.4; same session confirms the 6 outcomes in `instance/config/outcomes.yml` are still the right 6 (report §10.4 — retained here because the mission loop defers; see Deliberate exclusions). (Report §10.1) | Ratification note in `shared/interfaces/captain-decisions.md` incl. the outcomes.yml confirmation | NATE-ONLY | 0.5h | — |
| F0.1 | Secret-scan → commit → push the live branch | `gitleaks detect` (or trufflehog) over `~/captains-cabinet` working tree; scrub hits; rotate any live hits at provider (= Plan B F0.2, NATE-ONLY); commit the ~101 dirty/untracked files (incl. `framework/watchdog/`, `framework/autoreply/`, live acting/frontdoor edits); push `feat/fidelity-harness-design`. (Blueprint P0.1) | `git status` clean; branch on remote; scan report zero criticals | Builder | days | F0.0, F0.2 |
| F0.2 | Retire the dead 5-officer deploy path FIRST | `cabinet/scripts/deploy-mac.sh --all` deploys the extinct cos/cto/cpo/cro/coo fleet — neuter/replace before push so canonicalization can't enable a wrong-fleet redeploy (blueprint P0.2 [RT]). Purge stale roster residue: `cabinet/officer-capabilities.conf` cto/cpo/cro/coo rows, `instance/config/platform.yml` legacy voices, `cabinet/mcp-scope.yml` dead tokens | `deploy-mac.sh` refuses or deploys the live fleet; grep for dead officer names in configs = 0 | Builder | days | — |
| F0.3 | CI on the live branch incl. `pytest framework/` | Retarget `.github/workflows/cabinet-ci.yml` triggers to the live branch; add the 1,343-test `framework/` suite (currently in NO CI); fix the GNU-only `date -d` in the pre-push hook (fails closed on macOS) | CI green on the exact branch a clone would fetch | Builder | days | F0.1 |
| F0.4 | `services.yml` fleet manifest | One manifest (`cabinet/services.yml`) declaring the REAL fleet: 4 officers + 9 support daemons (see `~/Library/LaunchAgents/com.cabinet.*`), command/cadence/expected-output-floor/alert-tier; generator renders plists idempotently, zero `/Users/nate` hardcodes; `verify-launchagents.sh` extended to declared-vs-installed-vs-firing diff | Scripted redeploy reproduces the running fleet on a scratch user; lint job in CI | Builder | days | F0.2 |
| F0.5 | Mechanical verdict capture — `reply_binder` wired | Wire `framework/frontdoor/reply_binder.py::bind` into `cabinet/scripts/officer-inbound-poller.py` with `dispatch=chair_drafts.deliver_draft`: verdict superseding-event emit IN-PROCESS with the send; Chair LLM leaves the recording path (constraint 2; blueprint move #2). Fail-closed: no ledger write ⇒ no delivery | 7 consecutive days each landing ≥1 non-expired approve/edit/skip superseding event in `~/Library/Application Support/cabinet/events/consequence-events-*.jsonl` | Builder | days | F0.1 |
| F0.6 | One Telegram send path | Collapse all sends into `framework/frontdoor/channel.py`: delete `run_draft_lane.py::_tg` (raw, ungated), migrate `reply-to-captain.sh`/`send-to-warroom.sh` raw-curl paths; CI grep tripwire: `api.telegram.org` outside channel.py fails build (blueprint kill-list #5) | Tripwire in CI; audit of 48h logs shows zero out-of-path sends | Builder | days | F0.3 |
| F0.7 | Ledger-liveness dead-man | Standing launchd probe (germline, out of officer reach): lane emits proposals + Captain replies visible in getUpdates + zero superseding verdicts for N hours → CRITICAL page AND auto-demote lane to propose_only (blueprint §4.2 — the twice-paid n=0 failure made self-neutralizing) | Test-fire once by suppressing binder in a sandbox; page received; demotion event written | Builder | hours | F0.5 |
| F0.8 | Killswitch fail-closed + DEL-whitelist removal | Officer sessions: Redis empty/unreachable ⇒ block (today fails open); delete the universal `DEL cabinet:killswitch` whitelist at `cabinet/scripts/lib/pre-tool-use.sh:53-66` (any officer can currently un-halt the fleet). Sequenced strictly AFTER F0.10/F0.13 so a Redis hiccup alarms instead of silently halting (report §6.3) | Kill Redis in a drill: officers block, alarm fires, resume requires the token | Builder | hours | F0.10, F0.13 |
| F0.8a | Killswitch resume authority | Ratify: resume = Nate only, via typed token; document in the rewritten KILLSWITCH.md (F0.14) | Token verified in drill | NATE-ONLY | 0.2h | F0.8 |
| F0.9 | Off-machine durability: remotes + nightly db snapshot | Bare git remotes on the Mini (Shiny-Teapo) for BOTH backup repos (vault `~/Obsidian/screenpipe-brain` via `com.screenpipe.vault-backup.plist`; estate via `com.screenpipe.estate-backup.plist` — currently **no remotes**); nightly `sqlite3 ~/.screenpipe/db.sqlite ".backup ..."` + rsync to Mini; fix the `embeddings.db-shm` gitignore bug that has estate-backup writing fatal errors (report P0.4; pipe-health memories). **Interim target ruling:** the Mini serves as backup target only until Plan B B4.1 rebuilds it as the clean-room product org — B4.1's pre-flight relocates these remotes/snapshots to a replacement target (external SSD on the MacBook + optional cloud), so the product org's clean room is never also the estate's only backup | `git remote -v` shows Mini on both; snapshot file <24h old on Mini; estate-backup stderr clean | Builder | days | F0.9a |
| F0.9a | Mini reachable for backups | Confirm Tailscale SSH to Shiny-Teapo from this MacBook; create the bare-repo + snapshot directories (Nate's machine/account) | `ssh shiny-teapo true` from a launchd context | NATE-ONLY | 0.5h | — |
| F0.10 | pipe-watchdog PATH fix + error surfacing | Fix the one missing PATH line that breaks both the probe AND the alarm in `~/.screenpipe/pipes/pipe-watchdog/check.py` context (redis-cli/`FileNotFoundError` swallowed); stop swallowing exceptions — any probe error is itself an alarm (report P0.1; the entire daily self-improvement cluster has been dark since Jun 29 unalarmed) | Synthetic kill of a watched pipe alarms within one cycle; exception path unit-tested | Builder | hours | — |
| F0.11 | Cost writer + fleet on Console API keys | Register `stop-hook.sh` cost writer in `.claude/settings.json` (today `cabinet:cost:*` reads $0); move the 24/7 fleet off Max-OAuth to Console API keys per lane (Chair=Fable xhigh; lanes=Sonnet high; pipes/classifiers=Haiku); Max reverts to interactive; hook-enforce non-Chair Fable spawns = 0 (report P0.7 — the ToS existential risk ends now) | `cabinet:cost:*` non-zero; Console billing polled daily as ground truth; hook blocks a test Fable spawn from a lane | Builder | days | F0.11a |
| F0.11a | Console org + per-lane workspaces + budget | Create Anthropic Console org, per-lane workspaces, budget ceilings ($300→$600→$1,200 by phase, alarm at 2×); hand keys into `cabinet/.env` names | Keys live; envelope alarm test fires | NATE-ONLY | 1h | — |
| F0.12 | heartbeat-watchdog: install or waive | `com.cabinet.heartbeat-watchdog` exists only as a template — a wedged-but-alive claude is caught by nothing. Either install with progress-aware semantics (monotonic step counters, idle≠dead — fixes the 900s-TTL false-dead reads on cos/polads) or write an explicit signed waiver in `docs/` (blueprint P0.4) | Installed: synthetic wedge caught in drill. Waived: waiver doc merged | Builder | hours | F0.4 |
| F0.13 | External out-of-band dead-man + weekly kill drill | healthchecks.io checks: scheduler-alive, briefing-delivered, capture-fresh, backup-fresh, ledger-liveness — breaches reach Nate's phone independent of Redis/Telegram/the Mac. Weekly synthetic-kill drill (the current watchdog failed precisely because its alarm was never exercised) (report P0.2) | Drill: kill a job, phone alert <30 min; drill logged weekly | Builder | hours | F0.13a |
| F0.13a | healthchecks.io account | Create account (job-name-only payloads, no content) | Ping URL live | NATE-ONLY | 0.2h | — |
| F0.14 | Kill-list execution with CI grep tripwires | (a) Re-type `on-subagent-stop.sh`'s junk `work_item_completed` (5,546 junk vs 2 real — semantic decontamination BEFORE any consumer counts); (b) ONE constitution (collapse legacy `constitution/` duality; `/tmp/cabinet-runtime` assembly → durable path); (c) ONE killswitch doc (rewrite Docker-era KILLSWITCH.md for launchd); (d) ONE scheduler truth for cabinet-owned jobs (no pipe.md frontmatter scheduling anything cabinet-side); (e) delete Docker/Hetzner residue leaking into live hooks (`/opt/founders-cabinet` defaults in `policy_engine.py`, `stop-hook.sh`). Each kill gets a CI grep tripwire so it cannot half-happen (blueprint kill-list) | Tripwires green in CI; `grep -rn work_item_completed` shows typed emission only | Builder | days | F0.3 |
| F0.15 | Telegram token split | Second bot token from BotFather so the Chair token has exactly one owner/poller — kills the 409 war; interactive/legacy screenpipe sessions get the new token (report P0.6 — every label rides this channel) | 48h with zero 409s in poller logs | NATE-ONLY | 0.3h | — |
| F0.16 | `escalate(reason)` tool line | Add the sanctioned penalty-free raise-your-hand tool to officer prompts (report P0.11; strongest published misalignment-reduction per cost — verification-evals.md "rewarded self-report channel") | Line present in all 4 officer defs; one live escalation observed | Builder | hours | — |

### F0 build notes — the fleet being manifested, and the manifest shape

- **The REAL fleet `services.yml` must declare** (verified in `~/Library/LaunchAgents/` today): officers `com.cabinet.officer.{cos,polads-ceo,stephie-ceo,comms-officer}` + support `com.cabinet.{officer.cos-inbound, officer-supervisor-mac, frontdoor-briefing, intake-surface, status-sweep, limit-reset-watchdog, outcome-watchdog, dashboard, draft-lane}` — 4 + 9. Anything the manifest doesn't declare gets flagged by the auditor as an unmanaged agent.
- **Manifest row shape:** `{name, kind: officer|daemon, command, schedule|keepalive, env_names (never values), expected: {output_floor, heartbeat}, alert_tier, germline: bool}` → generator renders plists with `${CABINET_ROOT}` substitution; `verify-launchagents.sh` becomes the declared-vs-installed-vs-firing differ.
- **Kill-list tripwire set (F0.14), concretely:** `grep -rn 'api.telegram.org' --include='*.sh' --include='*.py' | grep -v channel.py` = 0 · `grep -rln '/opt/founders-cabinet' cabinet/scripts/hooks/` = 0 · exactly one constitution assembly path · `work_item_completed` emitted only with `source: mission` typed field · KILLSWITCH.md contains no docker-compose commands.

**Exit criteria (gates A1 and Plan B's Phase 1) — all machine-checkable:**
- [ ] CI green on the exact branch a second machine would clone (incl. `pytest framework/`).
- [ ] Scripted redeploy reproduces the running fleet on a scratch user (F0.4).
- [ ] Zero silent job deaths for 2 consecutive weeks, proven by the weekly synthetic-kill drill (F0.13).
- [ ] Backups present on the Mini: both remotes pushed <1h stale; db snapshot <24h (F0.9).
- [ ] Fleet on Console API billing; `cabinet:cost:*` non-zero; non-Chair Fable spawns blocked in test (F0.11).
- [ ] ≥7 consecutive days of mechanical verdicts landing via reply_binder (F0.5).
- [ ] All kill-list tripwires green in CI (F0.14); one Telegram send path audited over 48h (F0.6).
- [ ] Shared-phase rule: F0 exits on the UNION of this list and Plan B's F0 exit criteria — one phase, one bar (never gate the two plans on different F0 bars).
**Rollback:** every F0 change is a git revert + `launchctl unload/load` of regenerated plists; F0.2 keeps the old deploy script archived under `docs/attic/`; killswitch flip has the bash-hook layer retained as belt-and-suspenders.
**Captain-attention budget: 6 one-time NATE-ONLY actions (F0.0, F0.8a, F0.9a, F0.11a, F0.13a, F0.15), ≈3 focused hours total.**

---

# Phase A1 — Label Economy Resurrection + Data Safety (Milestone M1)

**Goal.** Reconnect the severed artery. Every clone learning input still listens to the dead screenpipe bot (polls `updates=0` since ~Jun 10): `me_signal.jsonl` frozen at 80 rows, `gate_decisions.jsonl` zero live rows, all 7 autonomy lanes n=0, 47% of proposals expiring unlabeled, 100% of 1,829 fidelity events `verdict="unknown"` (report §2.3). This phase makes the Chair poller the ONE tap point with `reply_binder.bind` as the single fan-out, migrates the 7 screenpipe lanes onto the ONE cabinet graduation engine (retiring `autonomy_lib` per the companion ruling), thickens me_signal, restores the dropped Captain input channels (voice DMs, calendar), and proves the backups restorable. Nothing else in this plan matters until evidence flows and data is safe.

| ID | Item | What exactly | Verification | Owner | Effort | Depends on |
|---|---|---|---|---|---|---|
| A1.1 | Inline-keyboard tap point on the poller | Add Send/Edit/Skip inline buttons (pid-embedded callback data) + deterministic parsing of `send` / `edit:<text>` / `skip:<why>` to `cabinet/scripts/officer-inbound-poller.py`. The Chair LLM leaves the approval path entirely (tmux injection remains for free-text judgment only) — the LLM-in-the-approve-path is on the report §8 delete list | Buttons render on a live draft card; verdict lands in <2s without the Chair session running | Builder | days | F0.5 |
| A1.2 | `reply_binder.bind` = the single fan-out | One implementation, one writer: (1) consequence decision event with `seconds_to_decide` + `edit_distance_ratio` ported from `~/.screenpipe/pipes/_shared/gate_ledger.py` features; (2) `me_signal.log_message` (revives nate-model input); (3) `reply_enrichment.enrich_from_reply` (`~/.screenpipe/pipes/_shared/reply_enrichment.py`); (4) `model:/wrong:/core:` prefixes → `nate-model` `correct_layer`. Old telegram-bot gets NO writeback wiring (being retired, A3 table). pid-idempotency asserted in pytest | Unit tests for all 4 fan-out legs + idempotent double-tap; live: one approve produces exactly one superseding event, one me_signal row, one enrichment pass | Builder | days | A1.1 |
| A1.2b | Kind-handler migration table — no reply kind severs silently | Enumerate ALL 13 telegram-bot `REPLY_HANDLERS` kinds (`~/.screenpipe/pipes/telegram-bot/handlers.py:2124`); beyond the draft verdicts (A1.1/A1.2) and self-knowledge (A3.11), the 11 unported: feedback-triage, decision, nate-model-core, rule-confirm, commitment (done/drop/snooze/task), draft-action, inbox-triage, commit-id-nudge, relationship-radar, ask-my-brain, architect (the verdict source of the ONLY production-earned auto-apply organ). Each kind is either ported to the poller tap point with its gate-ledger/me_signal wiring intact, or retired-with-reason in the table — evidence continuity is the explicit migration gate (constraint 8); telegram-bot's A3.T retirement is blocked on this table being complete | Committed kind-coverage table in `docs/`; one live round-trip test per surviving kind (at minimum: commitment done/snooze, architect approve, nate-model-core apply, inbox-triage action) | Builder | days | A1.2 |
| A1.3 | `verdict_human` / `verdict_judge` schema split | Extend `framework/schemas/consequence-event.schema.json` review block with distinct provenance fields (same fields as Plan B's F0.7 spec — one schema extension, land once; A-specific here is the CI assertion); **CI assertion: promotion math in `framework/fidelity/graduation.py` reads `verdict_human` only** — judge verdicts eligible for demotion + telemetry only (report §6.1 ruling; otherwise the system's own graders mint its promotion evidence) | Schema validated; a synthetic judge-verdict-only cell stays `unmeasured`; pytest asserts the read path | Builder | days | F0.5 |
| A1.4 | Expiry fold-in + pre-era retirement | Expiring proposals fold into briefings as batched one-tap verdicts, **provenance-tiered: batch one-taps weight ≤0.5 toward promotion floors and NEVER mint frozen-suite cases** (rubber-stamp-farming defense, report §6.1). Nate decision: retire the 1,829 pre-era `verdict="unknown"` fidelity events as unlabeled history (recommended over ~$15–30 re-judging) — series starts clean | Briefing shows batch card; batch verdicts land with `provenance=batch`; retirement decision recorded | NATE-ONLY (decision) + Builder | hours | A1.1 |
| A1.5 | One ledger; archives frozen | `~/Library/Application Support/cabinet/events/consequence-events-*.jsonl` is canonical. Freeze `~/.screenpipe/state/gate_decisions.jsonl` + `autonomy_outcomes.jsonl` as read-only archives (chmod + header row; supersede-never-delete). Fix the join key: every new event stamps the canonical `(lane × action_type)` cell via `framework/authority/classifier.py` (the field is `action` today; the taxonomy stamp is simply absent — report §2.1) | New events carry `lane`+`action_type`; archive files immutable; CI tripwire on writes to archived paths | Builder | days | A1.2 |
| A1.6 | Migrate the 7 autonomy lanes → cabinet graduation engine; retire `autonomy_lib` | Lane definitions in `~/.screenpipe/pipes/autonomy/sync.py` (send-1to1-reply, send-group-reply, auto-close-commit, auto-add-task, archive-email, forward-invoice, newsletter-digest) become authority-matrix cells in `framework/policies/authority-matrix.yml`; **backfill-exclusion and silent-shadow semantics are preserved** in `framework/fidelity/graduation.py` (port `autonomy_lib.record_shadow/resolve_shadow` anti-anchoring + backfill-row exclusion); `_shared/autonomy_lib.py` + the autonomy pipe retire after one clean parity cycle (companion ruling: one graduation engine) | All 7 cells visible in `graduation.evaluate` output as `unmeasured→propose_only`; shadow rows land on the ONE ledger; `autonomy.json` frozen as archive | Builder | days | A1.5 |
| A1.7 | me_signal thickening | 80 rows is starvation. New capture points, all through the A1.2 fan-out: every tap verdict; **every approve/edit diff (edit deltas are the richest voice/judgment signal)**; every free-text Captain DM at the poller choke point; quiz picks (A2.6); endorsement adjudications (A5.9); voice-DM transcripts (A1.9); self-knowledge answers (A3.11). Each row typed by source | `me_signal.jsonl` growing ≥5 rows/day over 14 days; source-type histogram in weekly brief | Builder | days | A1.2 |
| A1.8 | Ledger-liveness dead-man extended to flavor-A lanes | F0.7's probe covers cabinet lanes; extend the lane manifest to the migrated screenpipe cells (draft-reply/commitment/triage lanes): proposals pending + Captain visibly replying + zero verdicts landing → page + auto-demote to propose_only | Sandbox suppression test per lane class fires page + demotion event | Builder | hours | A1.6, F0.7 |
| A1.9 | Voice-DM input restored | The poller relays `msg.text` only — Captain voice notes are silently dropped while a complete transcription path exists for the retired Channels-plugin format (interfaces.md). Rewire `cabinet/scripts/transcribe-voice.sh` (Scribe STT) into the poller's non-text branch → transcript enters the same DM path + me_signal | Voice note → transcribed DM in Chair pane + me_signal row, live test | Builder | hours | A1.1 |
| A1.10 | Captain-debt reverse queue | First-class lane tracking what NATE owes the org: pending ratifications, germline applies, enforce flips, tokens, TCC/OAuth clicks, calibration batches — each with age + what-it-blocks + effort estimate; surfaced in every 07:30/19:30 briefing (`framework/frontdoor/run_briefing.py`); seeded from Appendix B. Shared organ with Plan B B2.13 — one queue, build once (B adds the Captain-required registry). Measured pattern it fixes: approved germline one-liners rotting for days (blueprint §4.7) | Debt section in next briefing; queue drains tracked weekly | Builder | hours | F0.5 |
| A1.11 | Make.com capture canary + Jun 12–20 backfill | **Decision: keep Make-with-canary; reject direct-Graph migration** — STEP tenant blocks OAuth app consent (screenpipe-pipes.md), so Make webhooks remain the only viable transport; the failure mode is detection latency, not the transport. Hourly known-answer probe classifying healthy/degraded/auth-dead with ping-now + re-auth runbook (the June outage took weeks to notice). Run the existing `~/.screenpipe/pipes/msgraph-backfill` + `teams-graph-backfill` for the Jun 12–20 near-total hole (state files predate the outage — report §2.1) | Canary state visible in pipe-health; synthetic auth-kill alerts <1h; backfill writes >0 messages for the hole window, deduped | Builder | days | F0.10 |
| A1.12 | Calendar via EventKit — light up the dark 12% | 30-min test: read the Outlook account from macOS Calendar.app via EventKit (EWS/ActiveSync typically allowed where Graph app scopes are tenant-blocked); if green, a minimal calendar reader feeding `context_lib` tier-2 + the CAL_GUARD in `_shared/draft_lib.py` (CALENDAR_COMPLETE flips true) + pre-meeting data (A3.14). Every brief today says "0 events" while meetings are 12% of attention (report §3-D3) | `beliefs`-free read returns today's real events; draft-lane calendar guard exercises the complete-view branch | Builder | hours | A1.12a |
| A1.12a | EventKit account + written self-sanction | Add the Outlook account to macOS Calendar.app (Nate's credentials); write the one-paragraph self-sanction of the EWS workaround (Nate owns the tenant-policy call, not an officer — report §6.2) | Account syncing; sanction note in captain-decisions.md | NATE-ONLY | 0.5h | — |
| A1.13 | Restore DRILL | Monthly drill, first one now: clone vault+estate from the Mini bare remotes to a scratch dir; open the db.sqlite snapshot, `PRAGMA integrity_check` + row-count sanity vs live; document RTO. Backups that have never restored are hope, not backups | Drill log committed; all three stores restored green | Builder | hours | F0.9 |
| A1.14 | Unwedge reasoning-review + kickstart the dark daily cluster | reasoning-review is head-of-line wedged (261/267 entries permanently unreviewed behind 40 unjudgeable pipe-health rows): unknown-after-3-attempts → weekly unjudgeable digest, never silent "reviewed". Kickstart architect/autonomy/voice-profile/codebase-digest (dark since Jun 29 = the F0.10 PATH bug); tighten pipe-watchdog stale threshold 4×→1.5× cadence (report P0.3) | Review backlog draining ≥20/day; all 4 cluster pipes wrote within cadence for 7 days | Builder | hours | F0.10 |

**Exit criteria (gates A2, and pipes/memory work in A3/A4) — all machine-checkable:**
- [ ] ≥5 human verdicts/day landing as superseding `verdict_human` events for 7 consecutive days (M1 — the milestone this whole plan pivots on).
- [ ] Proposal expiry <15% over the same window; batch one-taps visible with `weight ≤0.5` provenance.
- [ ] `me_signal.jsonl` growing ≥5 rows/day; source-type histogram shows ≥3 distinct capture points.
- [ ] All 7 migrated lanes visible as cells in `graduation.evaluate` output (propose_only, honest n; backfill excluded).
- [ ] Restore drill green on all three stores (vault, estate, db.sqlite snapshot) with documented RTO.
- [ ] Make canary alive with one synthetic auth-kill drill passed; Jun 12–20 hole backfilled (>0 deduped writes).
- [ ] Calendar returning today's real events via EventKit — or a written EventKit-blocked finding + iMIP fallback decision.
**Rollback:** the tap point is additive (buttons + parse); the old free-text path keeps working. Lane migration keeps `autonomy.json` frozen-not-deleted; re-enabling `autonomy_lib` is a two-line revert. Archives are frozen, never deleted.
**Captain-attention budget: 2 one-time NATE-ONLY actions (A1.4 decision, A1.12a) ≈45 min + the recurring verdict flow itself (≤5 surfaced decisions/day cap enforced by composer tiers).**

### A1 build notes — the tap point, concretely

- **Callback data** (Telegram inline keyboard, 64-byte limit): `v1|<verb>|<pid>` where verb ∈ {send, edit, skip} and pid is the proposal id already minted by `loop.propose()` and stored at `cabinet:draft:<pid>`. `edit` and typed `skip:<why>` arrive as replies quoting the card (the poller already captures quoted-message context). Free text without a verb falls through to the Chair tmux path unchanged — judgment stays with the Chair, recording never does.
- **The superseding event** (one write, canonical ledger `~/Library/Application Support/cabinet/events/consequence-events-*.jsonl`, schema `framework/schemas/consequence-event.schema.json` + A1.3 extension):

```json
{"event":"proposal_decided","pid":"<pid>","lane":"draft-reply","action_type":"send_1to1_reply",
 "proposal":{"decision":"edited"},
 "review":{"verdict_human":"wrong","verdict_judge":null,
           "provenance":"live-tap|batch-onetap|quiz|adjudication","weight":1.0},
 "features":{"seconds_to_decide":412,"edit_distance_ratio":0.31,"audience":"direct"},
 "ts":"<iso>"}
```

- **Fan-out order (in-process, fail-closed):** ledger append → `me_signal.log_message` → `reply_enrichment.enrich_from_reply` → prefix router (`model:`/`wrong:`/`core:` → `correct_layer`) → THEN `chair_drafts.deliver_draft(pid)`. A ledger-append failure aborts delivery (constraint 2); a fan-out leg 2–4 failure logs + continues (they are enrichment, not evidence).
- **Verdict taxonomy (what graduation reads, unchanged from `framework/acting/loop.py`):** approve → `confirmed` (proof, climbs) · edit → `wrong` + lesson_ref (correction) · skip → `unknown` (boundary, no credit either way) · expired → excluded from EVERY denominator (never counts for or against). Hold/negation phrases in free text downgrade an approve to hold (FIX-A fail-closed behavior preserved through the button path: a button tap with a contradicting quoted reply routes to the Chair for judgment instead of auto-recording).
- **Lane cell migration map (A1.6):** send-1to1-reply / send-group-reply → pooled `internal_routine_comms` + `external_comms` (ceiling) cells; auto-close-commit → `commitment_state_write`; auto-add-task → `board_write`; archive-email + newsletter-digest → `mailbox_move`; forward-invoice → `receipt_forward` (executor-conditioned, A5.5). Seven lanes → five pooled cells + one ceiling class: n≥30 becomes reachable at Nate's volume.

---

# Phase A2 — One Measurement Plane (harness merge, frozen suite, judge v2, quiz)

**Goal.** Collapse the two eval harnesses into one and give the only number that defines "getting better" a cadence. `framework/fidelity/` (gen-2: leakguard proven — 24 leak events, 0 leaks; intent verdicts; officer_runner) absorbs the retrodiction pipe's proven assets; a weekly scheduled run appends per-cell rows to one `fidelity_series.jsonl` (today: n=1, Jun 11, decision-match 8.3%); a frozen, auto-minted, only-growing regression suite becomes the gate for every prompt/playbook/skill/lesson/dossier change (GRASP: the gate carries the entire gain); the judge goes cross-family and contract-pinned; and the first analysis job decomposes the 8.3% into procedural/episodic/scoping failures — the split that decides where A5 invests. Retrodiction is explicitly demoted to a scheduled drift guardrail per the grand plan (`docs/grand-plan-captain-agent-2026-06-21.md` — "DEMOTE to a regression guardrail... stop chasing the %").

| ID | Item | What exactly | Verification | Owner | Effort | Depends on |
|---|---|---|---|---|---|---|
| A2.1 | Harness merge — fidelity absorbs retrodiction | Vendor `~/.screenpipe/pipes/retrodiction/lib.py` INTO `framework/fidelity/` (git mv + retarget `retro.py` + update `test_retro_shim.py`) so `framework/fidelity/` has zero `~/.screenpipe` path dependency: conversations.md case extraction, the 3-channel style scorer + author centroid, `score_draft()` as hot-path grader, CUSUM. The standalone retrodiction pipe retires only after the vendoring commit is green in CI (A3 table). One harness (report §6.1 ruling) | pytest green on merged paths; no second harness entry point; kill-list tripwire on a new standalone runner | Builder | days | A1.5 |
| A2.2 | Weekly scheduled fidelity run | launchd job (in `services.yml`) running the reply + decision cells weekly, appending per-(lane × action_type) rows to one `fidelity_series.jsonl`; registered with the outcome-watchdog (`framework/watchdog/registry.py`) so a missed run alarms. Prior runs were manual `/tmp` one-offs, now gone (fidelity-learning.md) | ≥4 consecutive weekly rows in the series; missed-run drill alarms | Builder | days | A2.1 |
| A2.3 | Judge v2 — cross-family, contract-pinned | Route judge calls through Nate's Vercel AI Gateway for a cross-family judge (self-preference bias defense); pairwise always position-swapped; deterministic rubric fields (recipient? action? commitment?) split from judged nuance; judge contract (model id + rubric version + prompt hash) pinned in git; monthly calibration against Nate's blind-quiz picks (verification-evals.md: judge contract + monthly human calibration). Reuse `framework/fidelity/oauth_llm.py` clean-cwd hygiene — the holdout already leaked once through a bare `claude -p` | Contract file in git; calibration batch #1 scored; position-swap asserted in tests | Builder | days | A2.1 |
| A2.4 | Frozen auto-minted regression suite (THE foundation) | A pipe watches the ledger: every *edit with replacement text* mints {thread, Nate's final text, diff}; every *typed* `skip:<why>` mints a should-not-draft case; quiz picks mint gold pairs. Content_ts-fenced; thread-level partitioned from quiz/training pools; **30-day quarantine before a minted case gates; suite directory joins the germline** (pre-tool-use write-block list ~line 936). Batch one-taps NEVER mint cases (A1.4). **No prompt/playbook/skill/lesson/dossier change ships without non-regression on the suite** (report §6.1; GRASP pattern, self-improving-agents.md). The mint watcher is registered in `cabinet/services.yml` with a wrote-floor (≥N minted-or-scanned/week) + outcome-watchdog expectation (constraint 7) | Suite grows ≥5 cases/week; a synthetic regressing change is rejected by the gate; germline write-block test green | Builder | week+ | A1.2, A1.5 |
| A2.5 | Decompose the 8.3% | First analysis job over the decision-cell corpus (`framework/fidelity/decision_cell.py`, 5-Reflections/Decisions + the never-scored 52-case git corpus): classify each divergence procedural / episodic / scoping. This split DECIDES A5 investment (report §6.1: "if it's mostly scoping, the fix is mission-slicing and narrower ask-classes, not smarter memory") | Decomposition report committed; A5 priorities annotated against it | Builder | days | A2.1 |
| A2.6 | Weekly blind self-pick quiz (~5 pairs) | Archived real reply vs blind clone draft, anonymized, randomized, delivered as one Chair card weekly; per-class pick-rate tracked (≥50% sustained = parity); **thread-partitioned from the frozen suite and any training pool; pick latency + repeat-pair consistency instrumented from day one** (single-annotator decay is an open research problem — report §6.5.2). Quiz picks feed judge calibration (A2.3) + me_signal (A1.7) | 4 consecutive weekly quizzes answered; latency series exists; partition assert in tests | Builder + NATE (recurring) | days | A2.4 |
| A2.7 | Shadow-parity = `score_draft` semantic compare | Replace exact-hash shadow matching (0/249 "matches" — uncomputable) with the 3-channel `score_draft` semantic metric; this is the per-pipe retirement gate A3 consumes (work-model.md retirement rule) and the R4 migration-gate criterion made evaluable | Parity score computable on live shadow pairs; threshold documented | Builder | days | A2.1 |
| A2.8 | Retrodiction demoted to scheduled drift guardrail | Monthly run, n≥30, judge contract pinned, CUSUM trend — a drift alarm, NOT the headline metric (grand-plan ruling; coverage matrix 4). Alarm wired to Chair intake, not Nate | Monthly row lands; CUSUM fires on injected drift in test | Builder | hours | A2.2, A2.3 |
| A2.9 | Rubber-stamp detector + escalation budget | Instrument `seconds_to_decide` distribution + approve-without-read proxy (sub-2s uniform approvals); escalation-rate budget <10% of actions with alert on breach; **auto-halving rule**: if pick latency trends up 2 weeks, the system halves its weekly ask (report §7: a starved label economy with honest telemetry beats a fat one that dies of fatigue) | Detector rows in weekly brief; synthetic rubber-stamp pattern flagged | Builder | hours | A1.2 |

**Exit criteria (gates A5 fully, A7 partially) — all machine-checkable:**
- [ ] `fidelity_series.jsonl` carries ≥4 consecutive weekly rows with per-cell decomposition.
- [ ] Frozen suite: ≥25 active (post-quarantine) cases; ≥1 synthetic regressing change rejected with case ids in the record.
- [ ] Judge contract (model id + rubric version + prompt hash) pinned in git; calibration batch #1 scored against quiz picks.
- [ ] 8.3% decomposition report committed with procedural/episodic/scoping percentages; A5 priorities annotated.
- [ ] Quiz: 4 consecutive weekly runs answered; pick-latency + repeat-pair-consistency series exist.
- [ ] Shadow-parity metric returns a score on live pipe shadow pairs (A2.7 — unblocks A3 retirements).
**Rollback:** the suite gate is advisory-log-only for its first 2 weeks (observe mode), then enforcing; judge v2 falls back to the pinned v1 contract on gateway failure (fail closed = hold the eval, never skip it).
**Captain-attention budget: 0 one-time NATE-ONLY actions; recurring ≈5 quiz picks/week + 1 monthly calibration batch (10–20 labels, ~15 min) — inside the global cap.**

### A2 build notes — suite mint rules, concretely

- **Mint sources → case types:** `edit` with replacement text → `{thread_prefix, nate_final_text, diff}` regression pair · typed `skip:<why>` → should-not-draft case (the WHY becomes the rubric line) · quiz picks → gold preference pairs. `provenance=batch-onetap` rows NEVER mint (A1.4). Every case content_ts-fenced at mint time (leakguard reused from `framework/fidelity/leakguard.py`).
- **Lifecycle:** minted → `quarantine/` (30 days, non-gating) → `active/` (gating) → never deleted, only `superseded_by`. Directory lives under `memory/golden-evals/suite/`, added to the pre-tool-use germline write-block list and to `architect_lib.GERMLINE`.
- **Partitions (hard, asserted in tests):** suite ∩ quiz-pool ∩ any-training-pool = ∅ at THREAD level, not message level — one thread never appears in two pools.
- **The gate check** (consumed by A6.5): candidate change → run `active/` suite → zero regressions on previously-passing + pass^k(k=3) on behavioral cases + token-cost delta <+15% → admit; else reject with the failing case ids in the rejection record. Gate runs are logged to the ledger as `verdict_judge` (never promotion evidence).

---

# Phase A3 — Pipes Estate Rationalization (parallel with A4/A5 after A1)

**Goal.** Give every one of the 63 pipes under `~/.screenpipe/pipes/` exactly one disposition per `docs/work-model.md` (KEEP-CAPTURE / KEEP-REFLEX / MIGRATE-TO-CABINET / RETIRE), collapse the dual scheduler to one source of truth, extend pipe-health to the jobs it structurally cannot see today (the draft-reply dead-but-"ok" bug), and pay down the runtime debt (two Pythons, three raw-curl LLM clients, ~40 files of hardcoded paths, one .env of plaintext secrets). Retirements follow the work-model rule: **per-pipe shadow parity (A2.7 metric), one pipe at a time, each retirement reversible by re-enabling the pipe** — except the never-ran batch, which has nothing to shadow. The grand plan's RELAY→ABSORB ruling governs the brief family: nothing that works gets rebuilt; it gets re-fronted through the one surface.

### A3.T — Full pipe disposition table (63 pipes; `_shared`/`_archived` are not pipes)

| Pipe(s) | Disposition | Grounding / destination |
|---|---|---|
| msgraph-incremental, teams-graph-incremental | KEEP-CAPTURE | The email/Teams senses (Make/Graph); A1.11 canary guards them |
| msgraph-backfill, teams-graph-backfill, monday-halfhourly-backfill | KEEP-CAPTURE (dormant utilities) | Run on demand (A1.11 backfill); no schedule; listed in jobs.yml as manual. monday-halfhourly-backfill follows its parent's RE-POINT destination at re-point time |
| teams-import | KEEP-CAPTURE | Teams thread import; goes on the watchdog WATCH list (was stale 12–13h repeatedly per pipe-health memories) |
| conversations-sync | KEEP-CAPTURE (surgery) | Delete the dead audio phase — 0 segments in 2,573 runs (report §8) |
| teams-ocr-capture | RETIRE | 0 conversations every run (report §8) |
| commit-stream, product-ops, codebase-digest | KEEP-CAPTURE | The 9-Codebases product pillar (git/Vercel/Neon senses) |
| claude-code-prompts-sync, claude-code-insights, daily-summary-of-claude-code-usage | KEEP-CAPTURE | CC telemetry; A3.10 reviews the trio for a 3→1 merge (architect proposal, not this plan) |
| monday-halfhourly, monday-daily-summary | RE-POINT-TO-VAULT (ruled 2026-07-02) | Activity rollups + daily summary born as vault markdown (`5-Reflections/Activity/…`); `_fetch_monday` re-points to the vault note (third-party API leaves gather()'s hot path); Monday writes retire after shadow parity |
| decisions-capture | KEEP-CAPTURE | Writes 5-Reflections/Decisions — the decision-cell ground truth (A2.5) |
| embeddings | KEEP-CAPTURE | The brain index; content_ts work in A4.2 |
| meeting-intel | KEEP-CAPTURE (surgery, ruled 2026-07-02) | Already vault-first (2-Meetings/); its Monday **Reflections push retires**; its TASK creation stays — that's PM via the adapter |
| people-intel | KEEP-CAPTURE (surgery, ruled 2026-07-02) | Vault dossiers become the ONLY birthplace; the Monday People-board upsert **retires** (optional vault→Monday mirror later; the label-write gotcha goes moot with it) |
| obsidian-sync | RETIRE-AFTER-MIGRATION (ruled 2026-07-02) | The Monday→vault mirror dissolves as each RE-POINT lands (synthesis becomes vault-born) — retires per-type, shadow-parity, last type wins |
| brain-mcp, perplexity-mcp | KEEP-CAPTURE (interface) | The officers' bridge; triple privacy fence pinned in A4.11 |
| video-export | KEEP-CAPTURE (manual utility) | No schedule; harmless |
| pipe-health, pipe-watchdog | KEEP-CAPTURE (infra) | Scope/PATH fixes F0.10, A3.4 |
| commitment-ledger | KEEP-REFLEX | Extraction + evidence-gated auto-close stay perception-side (work-model REFLEX); nudge *presentation* already rides Chair intake |
| completion-tracker | KEEP-REFLEX | Deterministic close-back (5/cycle cap); debris cleanup A3.9 |
| reminders, daily-loop-closer, feedback-triage | KEEP-REFLEX | Time-bound routing / loop closing / correction detection — no judgment to migrate |
| nate-model, voice-profile | KEEP-REFLEX (memory layer) | Grand-plan: memory stays screenpipe-side; hygiene in A4.7/A5.8 |
| self-knowledge | KEEP-REFLEX — re-enable | Disabled since ~Jun 3; A3.11 re-enables weekly through the Chair reply loop (answers feed the interior model + me_signal) |
| reasoning-review | KEEP-REFLEX | Unwedged in A1.14; feeds architect evidence |
| architect | KEEP-REFLEX (meta-organ) | The only earned auto-apply in production (fix-once: 3 confirmed/0 wrong) — preserved as the Gate model (A6.5) |
| autonomy | MIGRATE-TO-CABINET | Lanes → authority-matrix cells (A1.6); pipe + `autonomy_lib` retire after parity |
| telegram-bot | MIGRATE→RETIRE | Reply loop + 13 kind-handlers port to the A1.1/A1.2 tap point per the A1.2b kind-coverage table; me_signal choke point moves to the poller; pipe retires after one clean week AND the A1.2b kind-coverage table is complete — every kind ported or retired-with-reason (work-model: the approval gate is capture-side plumbing — and it moved) |
| draft-reply | RETIRE (already superseded) | Superseded by `com.cabinet.draft-lane` since Jun 25; plist already `.disabled`; formal retirement + pipe-health scope fix A3.4 |
| morning-brief | MIGRATE-TO-CABINET | 7-day recorded parity vs the Chair briefing → retire the loser (report §8 "one of the two daily briefings") |
| pre-meeting-brief | MIGRATE-TO-CABINET | Chair calendar routine on EventKit (A1.12, A3.13) |
| ask-my-brain | MIGRATE-TO-CABINET | The "what needs you now" digest → Chair (work-model MIGRATE list) |
| relationship-radar | MIGRATE-TO-CABINET | Coordinating-role routine, decision-aware as today (work-model) |
| inbox-triage | MIGRATE-TO-CABINET | Superseded by never-lie Stage 2 classifier (A5.4); deterministic detection halves stay as reflexes |
| todo-list-assistant, idea-tracker | MIGRATE-TO-CABINET | Chair routines / lane research crews (grand-plan RELAY→ABSORB); lowest priority |
| monday-deep-research | RE-POINT-TO-VAULT (ruled 2026-07-02) | Research briefs born as vault markdown (`5-Reflections/Research/…`, indexed); Chair absorbs presentation later (RELAY→ABSORB); Monday write retires after shadow parity |
| monday-daily-insights, monday-daily-improvements, monday-weekly-trends | RE-POINT-TO-VAULT (ruled 2026-07-02 — supersedes "Monday remains source of truth") | Synthesis born as vault markdown (`5-Reflections/…`); Chair briefing may absorb presentation later; Monday board writes retire after shadow parity |
| retrodiction | RETIRE (absorbed) | Assets merged into `framework/fidelity` (A2.1); monthly drift run replaces the pipe (A2.8). Depends on A2.1 vendoring complete (the retro shim resolves this dir until vendored); excluded from the A3.10 `_archived/` sweep until the vendoring commit is green in CI |
| digital-clone | RETIRE | Architect proposed retirement twice; proposals expired — a live demo of the broken label loop (report §8) |
| top-of-mind, day-recap, standup-update, time-breakdown, missed-todos, collaboration-patterns, automate-my-work, session-digest | RETIRE | The 8 never-run template pipes (report §8) — nothing to shadow |
| monday-migrate | RETIRE | Vestigial (screenpipe-pipes.md) |
| meeting-summary | RETIRE | Superseded by meeting-intel; move dir under `_archived/` |
| ai-habits | RETIRE (architect-verified) | Synthesis with no found consumer; one fleet_lib debris-survey cycle confirms value=0 before deletion |

| ID | Item | What exactly | Verification | Owner | Effort | Depends on |
|---|---|---|---|---|---|---|
| A3.1 | Ratify the disposition table | One batched one-tap card: the A3.T table + the self-knowledge re-enable + the teams-graph cadence recommendation | Ratification in captain-decisions.md; table committed to `docs/` | NATE-ONLY | 0.3h | A1 exit |
| A3.2 | `jobs.yml` — one pipe manifest + auditor | `~/.screenpipe/jobs.yml`: every pipe → {command, schedule, machine, expected wrote-count floor, alert tier, disposition}; audit script diffs declared vs installed (`launchctl list`) vs firing (log mtimes) vs A3.T disposition; absolute-path lint (the F0.10 PATH bug class becomes lint). One auditor also covers `cabinet/services.yml` (F0.4) — one immune system, two manifests | Auditor runs in pipe-health cadence; seeded with 3 known drifts, catches all 3 | Builder | days | A3.1 |
| A3.3 | Scheduler consolidation — launchd is the ONE truth | pipe.md `schedule:`/`enabled:` frontmatter demoted to docs (or generated FROM jobs.yml); the screenpipe agent-scheduler disabled for every deterministic pipe (generalizing meeting-intel's defensive `enabled: false` hack into policy); commitment-ledger's double registration (frontmatter AND plist) resolved to plist-only | Zero pipes with live dual scheduling; jobs.yml auditor asserts it; embeddings/pipe.md drift (says manual/disabled while launchd-live) fixed | Builder | days | A3.2 |
| A3.4 | pipe-health scope extension | Today it judges only plist-bearing pipes — a `.disabled` plist drops a pipe from scope, so dead draft-reply reported "ok" for a week. Extend `~/.screenpipe/pipes/pipe-health/check.py` to judge (a) every jobs.yml row regardless of plist state, (b) agent-scheduled jobs, (c) `.disabled` plists (must alarm as RETIRED-or-BROKEN, never silence); keep data-dry (wrote=0 streak) trend alarms | Synthetic: disable a plist → alarm within one cycle; jobs.yml rows all covered | Builder | days | A3.2 |
| A3.5 | StartCalendarInterval conversion | Convert the remaining throttle-exposed StartInterval plists (the 2026-06-25 msgraph/teams fix, generalized — StartInterval coalescing froze whole banks for 6–13h repeatedly per pipe-health memories); wall-clock schedules for anything cadence-critical | Zero cadence-critical pipes on StartInterval; 7 days without a coalescing stall | Builder | hours | A3.2 |
| A3.6 | Python runtime unification (3.12) | telegram-bot's retirement (A3.T) dissolves the 3.9 constraint that held `gate_ledger.py` down; audit every plist/shebang to `/opt/homebrew/bin/python3.12`; drop 3.9-compat comments — **in pipes only: `framework/` runs the system-Python 3.9.6 interpreter (`test_retro_shim.py` asserts importability under it), so framework-side 3.9-compat stays; upgrading the framework interpreter would be its own explicit sub-item with `test_retro_shim.py` updated, never a side effect of this item** | `grep -rn '/usr/bin/python3'` over pipes = 0 live jobs; smoke run of every KEEP pipe | Builder | days | A3.3 |
| A3.7 | Central LLM client | `_shared/llm.py` replacing the 3 raw-curl implementations (`nate-model/sync.py::_raw_llm`, `architect/sync.py::_raw_llm`, `commitments_lib.call_llm` with its hardcoded model id): retries, rate-limit handling, model tiering (Haiku for classifiers, Sonnet for pipes), **no secrets on argv** (visible in process listings today), Console-key routing per F0.11 | All three call sites migrated; `ps`-visibility test shows no key material; retry unit tests | Builder | days | F0.11 |
| A3.8 | Path/config extraction | `SCREENPIPE_ROOT` + `OBSIDIAN_VAULT_PATH` env honored everywhere (today only `embeddings/lib.py` honors an override; ~40 files hardcode `/Users/nate` — screenpipe-core.md): one `sp_lib.paths()` accessor, grep-driven migration | `grep -rn '/Users/nate' pipes/ --include='*.py'` → only sp_lib defaults remain | Builder | days | — |
| A3.9 | Secrets → Keychain, names-not-values | `sp_lib.load_env` gains a `security find-generic-password` resolver; `_shared/.env` migrates one credential class per month (Monday → Neon → Vercel → Voyage → Telegram) with rollback env vars retained; error paths keep naming env-var NAMES only | First credential class resolves from Keychain; .env value removed; pipes green | Builder | days | A3.7 |
| A3.10 | completion-tracker debris + `_archived` sweep | Archive the ~60 abandoned one-off scripts + `_quarantine_20260608` inside completion-tracker (visible archaeology of the 2026-06-09 mass-completion incident); sweep RETIREd pipe dirs into `_archived/` with a tombstone README each — **retrodiction/ excluded from the sweep until the A2.1 vendoring commit is green in CI** (until vendored, the retro shim resolves that dir; moving it breaks the weekly fidelity run); CC-telemetry-trio merge review filed as an architect proposal | fleet_lib debris survey re-run shows referenced-file ratio healthy; RETIREd dirs gone from pipes/ root (retrodiction last, post-A2.1) | any-CC-session | hours | A3.1; retrodiction dir: A2.1 |
| A3.11 | self-knowledge re-enable | Re-enable weekly (was `enabled: false` since ~Jun 3): one reflective question/week through the Chair tap point (kind ported in A1.2); MIN_GAP + Jaccard dedup guards retained (reply-enrichment memory) | First question delivered + answer lands in 5-Reflections/Self-Knowledge + me_signal | Builder | hours | A1.2, A3.1 |
| A3.12 | teams-graph cadence revisit | Daily-by-design = 24h Teams staleness (a Make-ops cost choice, not an outage — screenpipe-pipes.md). Recommendation: work-hours hourly (07–19 CET) once the A1.11 canary proves Make budget headroom; decision rides the A3.1 card | Cadence changed; Teams messages <2h stale in work hours; Make ops within budget | Builder | hours | A1.11, A3.1 |
| A3.13 | Brief family absorption (RELAY→ABSORB) | Chair composer (`framework/frontdoor/run_briefing.py` + `morning_synthesis`/`daily_recap`) absorbs morning-brief content reading the same vault sources; 7-day RECORDED parity (both run, diffs logged) → retire the loser (grand-plan; report §8). day-recap/standup/top-of-mind are already RETIREd (never ran) | Parity log committed; one briefing generator remains; kill tripwire on the retired one | Chair + Builder | days | A1 exit |
| A3.14 | pre-meeting-brief → Chair calendar routine | Chair trigger from the EventKit read (A1.12): T-30min brief per meeting (attendees via people-intel dossiers, open commitments, last meeting note) — the pipe retires after shadow parity on ≥5 real meetings | 5 parity braces logged; pipe plist removed; briefs arrive T-30 | Builder | days | A1.12, A2.7 |
| A3.15 | ask-my-brain → Chair digest | The 6h "what needs you now" gather-rank-digest becomes a Chair routine reading the same sources (open commitments, waiting-on, deploy failures); pipe retires after shadow parity ≥2 weeks | Parity ≥ threshold on A2.7 metric; pipe retired reversibly | Builder | days | A2.7 |
| A3.16 | Retirement executor discipline | Every MIGRATE pipe follows: replacement shadows on real traffic → A2.7 semantic parity ≥ threshold → architect-mediated retire (reversible re-enable documented per pipe) → jobs.yml disposition flips. **Evidence continuity is an explicit gate** (constraint 8): the replacement must write to the SAME ledger before the pipe stops | Per-pipe retirement records in architect ledger; no pipe retired without a parity row | Builder | ongoing | A2.7 |

**Exit criteria — all machine-checkable:**
- [ ] jobs.yml auditor green across declared vs installed vs firing vs disposition (63 rows).
- [ ] Zero dual-scheduled pipes (frontmatter schedule keys inert everywhere; auditor asserts).
- [ ] pipe-health covers 100% of jobs.yml rows incl. `.disabled` plists (synthetic-disable drill passed).
- [ ] RETIRE batch executed: ≥12 dirs tombstoned under `_archived/`; kill tripwires green.
- [ ] ≥2 MIGRATE pipes retired via recorded shadow parity (retirement records in the architect ledger).
- [ ] One Python (3.12) across live jobs; one LLM client (3 raw-curl call sites migrated); first Keychain credential class resolving.
**Rollback:** every retirement is a plist re-enable + jobs.yml flip (documented per pipe); scheduler consolidation keeps frontmatter as inert docs so reverting is a config change; Keychain migration retains .env fallbacks until each class proves.
**Captain-attention budget: 1 one-time NATE-ONLY action (A3.1 batch ratification, ~20 min).**

### A3 build notes — jobs.yml row schema + disposition arithmetic

```yaml
# ~/.screenpipe/jobs.yml — one row per pipe (auditor: declared vs installed vs firing vs disposition)
- name: msgraph-incremental
  disposition: keep-capture          # keep-capture | keep-reflex | migrate | re-point-to-vault | retire
  command: /opt/homebrew/bin/python3.12 pipes/msgraph-incremental/sync.py
  schedule: {type: calendar, minutes: [0,15,30,45], hours: 7-19}   # StartCalendarInterval only
  wrote_floor: {window_h: 24, min_writes: 1}    # data-dry alarm threshold
  alert_tier: page                   # page | chair | digest
  watchdog: true
```

- **Disposition arithmetic (63 pipes; recomputed after the 2026-07-02 RE-POINT-TO-VAULT ruling):** KEEP-CAPTURE 22 · KEEP-REFLEX 10 · MIGRATE-TO-CABINET 9 · RE-POINT-TO-VAULT 6 (monday-halfhourly, monday-daily-summary, monday-daily-insights, monday-daily-improvements, monday-weekly-trends, monday-deep-research) · RETIRE 16 (obsidian-sync joins as RETIRE-AFTER-MIGRATION). Verification: `python3 -c "import yaml; rows=yaml.safe_load(open('jobs.yml')); assert len(rows)==63"` + auditor cross-check against `ls pipes/` (excluding `_shared`, `_archived`).
- **Retirement record shape (A3.16, written by architect):** `{pipe, replacement, parity_metric: score_draft, parity_n, parity_score, threshold, retired_ts, revert: "launchctl load ~/Library/LaunchAgents/com.screenpipe.<pipe>.plist + jobs.yml flip"}`.
- **Never-ran batch (RETIRE without shadow):** top-of-mind, day-recap, standup-update, time-breakdown, missed-todos, collaboration-patterns, automate-my-work, session-digest — plus teams-ocr-capture (0-output evidence), monday-migrate (vestigial), meeting-summary (superseded), digital-clone (architect-proposed ×2), retrodiction (absorbed A2.1), draft-reply (superseded by draft-lane), ai-habits (after one debris-survey cycle).

---

# Phase A4 — Personal Memory Program (parallel with A3/A5 after A1)

**Goal.** Affirm what works (the vault trinity, the hybrid embeddings brain, the nate-model volatility ladder, the brain-mcp privacy fences), then fix the measured gaps: content_ts fencing at 64% coverage, decisions fragmented across six surfaces, no consolidation/forgetting policy, no bi-temporal semantics for facts that supersede (the Frederik-triple-nudge class), a cabinet semantic-memory pipeline that is dead-but-fed (497 queued embeds, worker never ran), and provenance that lets anyone who emails Nate write into the substrate every officer reasons from (the report's #1 system-specific live threat). Research anchors: agent-memory.md (Dreams consolidation, bi-temporal invalidation-not-deletion, semantic-category TTLs, provenance-gated writes, file-based memory validated).

| ID | Item | What exactly | Verification | Owner | Effort | Depends on |
|---|---|---|---|---|---|---|
| A4.1 | Vault architecture affirmation + gaps note | One committed page: Obsidian vault = source of truth, Monday = work-tracking, Reminders = nudge (the load-bearing trinity — never collapse); folder contract (0-Self/1-Daily/2-Meetings/3-People/4-Projects/5-Reflections/6-Commitments/9-Codebases); named gaps → the items below. No restructuring — affirmation is the deliverable | Page in vault + repo `docs/`; cross-linked from CLAUDE.md | any-CC-session | hours | — |
| A4.2 | content_ts coverage 64% → ≥80% | Extend `embeddings/lib.py::derive_content_ts` for the honest-absence classes that ARE derivable: 4-Projects `generated:` frontmatter, 9-Codebases per-commit dates in commits.md, 5-Monday note dates; re-run `embeddings/backfill_content_ts.py` (UPDATE-only, no re-embed). Target ≥80% of chunks fenced; **NULL stays honest — never mtime, never fabricated** (the fence clock the fidelity harness relies on) | Coverage query ≥80%; leakguard tests green; spot-check 20 newly-fenced chunks | Builder | days | — |
| A4.3 | Entity-graph decision: DEFER | `docs/data-foundation-entity-graph-design-2026-06-20.md` is designed-only. **Ruling: defer.** Justification: the decision dossier (A5.2) attacks the measured 8.3% directly (genagents: 85% decision replication from context, no graph); the hybrid index already covers recall; research verdict = no GraphRAG/memory-platform migration (report §4.9). The one load-bearing graph idea — invalidation-not-deletion — ships as A4.4 without the platform | Decision row in captain-decisions.md; design doc annotated DEFERRED with this rationale | Builder | hours | A2.5 |
| A4.4 | Bi-temporal beliefs slice | SQLite `beliefs` table over the immutable vault (subject, predicate, object, confidence, provenance→chunk ref, valid_from/valid_until, superseded_by) for the three fact classes that go confidently-wrong: commitments, decisions, deploy-facts; `beliefs_as_of(T)` API for the fence + dossier; contradicting facts close the old edge, never delete (Graphiti schema without the platform — agent-memory.md). Kills the Frederik-triple-nudge class. Timed AFTER labels flow (report §6.4: P3+). Feeder named (constraint 7): an extraction pass wired into the commitment-ledger / decisions-capture / product-ops cadences writes the three fact classes, declared as a `jobs.yml` row with a row-count freshness assert | A superseded commitment returns the old belief for as-of-T and the new one for now; commitment-ledger nudge gate reads it; jobs.yml row present, row-count freshness assert green | Builder | week+ | A1 exit, A4.2 |
| A4.5 | Semantic-category TTLs | Extend the nate-model memory layer's 10-day TTL into a category policy: org/identity constraints = no expiry; commitments = until closed + 90d; deploy-facts = superseded-by-next-deploy; incident context = 14d; unvalidated reflections expire unless confirmed. **Never LRU/frequency eviction** (destroys rare-but-critical long-tail — agent-memory.md pitfalls) | Policy table in code; expiry pass logged; a rare annual-procedure note survives the sweep | Builder | days | A4.4 |
| A4.6 | Nightly Dreams-style consolidation + one-tap memory diff | launchd job over 0-Self + 5-Reflections (+ recent session transcripts): orient → gather signal (corrections, decisions, recurring patterns) → consolidate (merge, absolutize dates, resolve contradictions) → prune to a lean index; **output is a DIFF routed through the Chair one-tap gate before adoption** (Anthropic Dreams pattern, agent-memory.md; review-before-adopt). Approved diffs land via nate-model's existing propose-gated core path. Job registered with the outcome-watchdog — a missed night = alarm (constraint 7) | Nightly run visible; a missed night alarms via the outcome-watchdog; first 3 diffs approved/rejected via one tap; 0-Self/core.md moving again (frozen since May 31) | Builder | days | A1.2 |
| A4.7 | nate-model layer hygiene pinned | Assertion tests for the volatility ladder (core ~30d propose-gated · patterns 7d auto · memory 1d/TTL, promotes upward), the `correct_layer` immediate-correction path (exercised e2e once via a `model:` prefixed DM through A1.2), and the privacy fence in `me_signal.nate_model()` | pytest suite green; e2e correction visible in 0-Self within one cycle | Builder | hours | A1.2 |
| A4.8 | reply_enrichment continuation verified | Post-rewire (A1.2 leg 3): durable_facts → memories store, person_context → `3-People/{slug}/... intel.md`, premise_wrong → flag + confirmation — verified end-to-end on live replies (the second-pass extraction that made replies compound) | One live reply produces an intel append + a memory fact with correct slug resolution | Builder | hours | A1.2 |
| A4.9 | Decision fragmentation: six surfaces → one canonical + projections | Canonical: `shared/interfaces/captain-decisions.md` (+ `org_events` as the event-log projection). Kill the other four: `cabinet/init.sql` ghost tables (decision_log + friends — 4 of 5 tables writer-less), Neon `captain_decisions` (schema-only), `memory/tier3/decision-log/` (empty), cabinet_memory decision rows (dies with A4.10). Vault `5-Reflections/Decisions` stays — different function (Nate-life decision corpus feeding the decision cell), explicitly documented as such | Grep tripwire on writes to killed surfaces; one-store rule documented; decision-cell extraction unaffected | Builder | days | F0.14 |
| A4.10 | memory-worker / cabinet_memory: RETIRE for flavor A | **Ruling: retire, don't drain.** Justification (constraint 8 — one joint per function): flavor A's semantic recall IS the screenpipe embeddings brain (38,865 chunks) via brain-mcp; `cabinet_memory` duplicates it and has never served a query (497 queued, worker never scheduled, 0 searches in ~20k tool calls — memory-cabinet.md). **Narrowed by cross-plan ruling (Plan B B2.12 governs the shared worker):** `memory-worker.sh` IS scheduled and the queue IS drained — as the *cabinet's org-memory* organ (Captain patterns/decisions, officer artifacts), per B2.12. What retires for flavor A is the *personal-content duplication*: stop enqueueing vault-duplicating personal content (the brain/vault stays the sole personal-recall surface — one joint per function), keep org-content enqueues. Officers' personal recall path (brain-mcp) unchanged | Personal-content enqueues stop (audit of queue payload source_types); org-content flows and drains per B2.12; officers' recall path (brain-mcp) unchanged; scope doc committed | Builder | hours | A3.1 |
| A4.11 | 0-Self fences pinned | CI/pytest guards for the triple fence: 0-Self excluded from the embeddings index, brain-mcp hit-stripping + `read_note` refusal, gate ledger stores labels/features never bodies; fence files listed germline. Partner/family threads stay never-indexed (3-People/_noise exclusion held) | Fence tests green in CI; a synthetic 0-Self chunk never surfaces in search | Builder | hours | — |
| A4.12 | Taint/provenance 80/20 | **Thread-scoped, not reply-scoped**: any durable fact extracted from a thread containing untrusted-inbound content inherits `untrusted-inbound` provenance even if Nate's own sentence stated it (approve-taps must not launder attacker content — report §6.4). Now: quarantine file + weekly batched one-tap veto for externally-triggered memory writes; draft path refuses long verbatim spans from untrusted inbound. Full provenance column on chunks deferred to a later pass | A seeded injection email's "fact" lands in quarantine, not memories; weekly veto card appears | Builder | days | A1.2 |
| A4.13 | Four lesson stores → per-surface ACE playbooks | Consolidate Drafting-Lessons.md (vault 5-Reflections), Agent-Reasoning `_lessons.md`, `captain-patterns.md`, `captain-intents.md` into per-surface playbooks: ID'd bullets with provenance refs + helpful/harmful counters, incremental deltas ONLY (monolithic rewrites lint-banned — ACE context-collapse finding), top-k retrieval instead of tail-reads. Fix `shared/interfaces/captain-rules-index.yaml` (48 dead anchors, 0/17 live patterns indexed — encoded rules currently unfindable). Candidate/trial/eviction lifecycle deferred until label volume proves it computable | Playbooks in place with IDs; rules-index eval >0/5; rewrite-lint blocks a synthetic wholesale rewrite | Builder | days | A2.4 |

**Exit criteria — all machine-checkable:**
- [ ] content_ts coverage ≥80% (SQL count over `chunks`); leakguard tests green; NULLs remain honest absences.
- [ ] beliefs table serving `beliefs_as_of(T)` to the commitment nudge gate (one live nudge suppressed by a superseded belief in test).
- [ ] Consolidation job producing diffs; ≥3 approved via one-tap; `0-Self/core.md` mtime moving again (frozen since May 31).
- [ ] One canonical decision store; grep tripwires on the four killed surfaces green.
- [ ] cabinet_memory retired: embed queue length flat for 14 days; feeder hooks clean; tombstone committed.
- [ ] Seeded injection email's extracted "fact" lands in quarantine, not memories (A4.12 drill).
- [ ] Playbooks consolidated with ID'd bullets + top-k retrieval; captain-rules-index eval >0/5.
**Rollback:** beliefs/TTL/consolidation are additive layers over an immutable vault — disable the launchd job to revert; A4.10 keeps the queue frozen (revivable); A4.9 kills only writer-less surfaces (nothing reads them today).
**Captain-attention budget: 0 one-time NATE-ONLY actions; recurring ≈1 weekly quarantine-veto batch + memory-diff one-taps (~5 min/week).**

### A4 build notes — beliefs DDL + TTL policy table

```sql
-- ~/.screenpipe/state/beliefs.db (A4.4) — the Graphiti schema without the platform
CREATE TABLE beliefs (
  id INTEGER PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL, object TEXT NOT NULL,
  fact_class TEXT NOT NULL CHECK(fact_class IN ('commitment','decision','deploy_fact')),
  confidence REAL, provenance TEXT NOT NULL,          -- chunk ref / event id / 'untrusted-inbound:<thread>'
  valid_from TEXT NOT NULL, valid_until TEXT,          -- NULL = currently believed
  superseded_by INTEGER REFERENCES beliefs(id));
CREATE INDEX idx_beliefs_asof ON beliefs(subject, fact_class, valid_from, valid_until);
-- beliefs_as_of(T): WHERE valid_from <= T AND (valid_until IS NULL OR valid_until > T)
```

- **TTL policy (A4.5):** `identity/constraint: none` · `commitment: closed+90d` · `deploy_fact: superseded-by-next` · `incident: 14d` · `unvalidated_reflection: 10d unless confirmed`. Expiry = set `valid_until`, never DELETE. Consumers: commitment-ledger nudge gate (kills the Frederik class), decision dossier (A5.2), the fidelity fence (as-of-T context).
- **Consolidation diff card (A4.6):** one Chair card/night max, sections {facts merged, contradictions resolved (old→new), pruned}, one-tap apply/reject; rejected diffs mint should-not-consolidate lessons.
- **Taint rule (A4.12), exactly:** provenance is assigned per THREAD at capture; `enrich_from_reply` and the consolidation job check the source thread's taint before writing to memories/intel — tainted extractions land in `0-Inbox/quarantine-memory.md` for the weekly batch veto, regardless of who uttered the sentence.

---

# Phase A5 — Clone Quality Program (the 8.3% attack + never-lie + better-than-Nate)

**Goal.** Convert the label stream into draft/decision quality. The evidence: decision-match 8.3% (n=24, Jun 11); reply cell flat at 40–50% intent (it measures voice); decision cell +25pp clone-identity lift (identity/context works — pull that thread); draft approvals ≈23%. The research verdict (report §4.2): this is a *context/procedure* problem — attack with a decision dossier + analogous-past-decision retrieval + ledger-derived rules (genagents 85% decision replication from context), not voice work, not fine-tuning. The never-lie stages (`docs/never-lie-build-plan-2026-06-29.md` — Nate's #1 priority, currently plan-only) make faster approving safe; the §6.5 instrument makes "better than Nate" measurable for the first time. A2.5's decomposition re-prioritizes this phase when it lands.

| ID | Item | What exactly | Verification | Owner | Effort | Depends on |
|---|---|---|---|---|---|---|
| A5.1 | Never-lie Stage 1 in the draft path | Per the build plan: (1a) MANDATORY dossier in `_shared/draft_lib.py::build_draft` (replace the optional RESEARCH planner; fills thread+audience, person_intel, why-now, commitments both directions, board state, livedata, nate_model, calendar_busy); (1b) truthfulness gate post-composition — claim-extraction → map to dossier evidence → STRIP / SOFTEN / HOLD-AND-ASK at the LOW threshold, evidence dossier rendered in the approval card (generalizes the shipped `has_meeting_time_ask` CAL_GUARD; verdict computed in CODE at `draft_lib.py:866` pattern); (1c) represent-Nate's-stance anti-sycophancy pass. Approve-only; no germline change needed | The Tomás+Kristoffer demo thread yields the informed reply, not "passer fint"; unbacked load-bearing claims HELD in a battery; card shows the evidence table | Builder | week+ | A1.2 |
| A5.2 | Decision dossier — nightly compile, suite-gated | Nightly-compiled, git-versioned, as-of-T-capable dossier from nate-model layers + 5-Reflections/Decisions + self-knowledge answers + commitment stances + **ledger-derived procedural rules (A5.3)**; retrieval of analogous past decisions injected per case (genagents pattern). **Every compile re-runs the frozen suite before going live** (it shapes every output — otherwise a silent-regression backdoor); intent-reconstruction for adjudication uses only pre-cutoff artifacts, never optimizer-edited dossier content (report §6.4). Compile job registered with `framework/watchdog/registry.py` (constraint 7) | Dossier repo with nightly commits; a missed nightly compile alarms; suite gate blocks a synthetic bad compile; per-case injection visible in draft-lane gather logs | Builder | week+ | A2.4, A2.5 |
| A5.3 | Ledger-derived procedural rules miner | Mine approve/edit/skip + audience + thread features into explicit rules ("group mail from X → Nate declines ~90%", "invoice from Y → forward ulkri") feeding the dossier + `should_nate_reply`; rules carry provenance (event ids) and land as ACE playbook bullets (A4.13), candidates-on-trial. Cadence: weekly re-mine over the ledger, declared as its own `jobs.yml` row (constraint 7) | ≥10 rules mined with provenance; should_nate_reply hit-rate improvement measured on the next 50 gates; weekly jobs.yml row live | Builder | days | A1.5 |
| A5.4 | Never-lie Stage 2 — inbox-zero show-first + rule-learning store | Cheap classifier on ALL inbound (info→archive · needs-action→task · do-now→surface · belongs-in-folder→move · awaiting-reply→Stage-1 pipeline); **persisted per-sender/per-type rule-learning store in `instance/`** (cabinet repo, officer-writable — ask once, apply forever); newsletters → propose auto-move + digest; receipts → propose forward-to-ulkri in SHOW-FIRST proving batch; everything-else show-first. Folder mechanics via the Captain-approved `MSGRAPH_WRITE_WEBHOOK` | ~1 week show-first; per-category precision measured; rule store consulted before every proposal (log line) | Builder | week+ | A5.1 |
| A5.5 | Stage 2.5 — receipt carve-out IN the brain server, dormant | Implement `forward_receipt(message_id)` in `~/.screenpipe/pipes/brain-mcp/server.py` enforcing ALL six conditions in code (≥HIGH classification by ≥2 independent signals; proving batch at 100% precision completed; verbatim-forward only; single fixed recipient ulkri@stepnetwork.dk; sanctioned-path-only; log_reasoning + receipts ledger + morning-digest fold + killswitch). **Ships DORMANT until the Stage-2 proving batch passes** — the officer requests, the server enforces | Below-bar/unproven message falls back to queue_draft in test; all six conditions unit-tested; dormancy flag default off | Builder | days | A5.4 |
| A5.5a | Apply the receipt germline carve-out | Nate applies the narrow brain-bridge amendment per the spec in `docs/never-lie-build-plan-2026-06-29.md` §carve-out (do NOT self-apply — germline) | Amendment committed by Nate; pre-tool-use germline hash updated | NATE-ONLY | 0.3h | A5.5 |
| A5.6 | Stage 3 — comms-officer becomes the reply executor | The thin scheduled draft-lane is the wrong executor for officer-grade reasoning (build plan §29): the comms-officer session executes gather→dossier→draft→gate with courses-of-action discipline; draft-lane demotes to trigger/scheduler. Evidence continuity: same ledger, same pids (constraint 8) | One week dual-run; comms-officer drafts match/beat draft-lane approval rate; ledger rows uninterrupted | Builder + Chair | days | A5.1, A1.2 |
| A5.7 | Stage 4 — graduate per proven category | Wire Stage-2 category precision + rule-store maturity into A7's promotion inputs: show-first → auto per category ONLY through the graduation engine (no side-door autonomy). This item is the handoff contract to A7 | Category cells visible in `graduation.evaluate`; no auto behavior outside matrix verdicts | Builder | hours | A5.4, A7.3 |
| A5.8 | voice-profile maintenance | Verify the weekly run (in the dark-cluster kickstart A1.14), recency weighting (45d heavy) + context-keying (channel × audience) intact; add a jobs.yml wrote-floor so silence alarms. Voice work stays MAINTENANCE — the measured gap is decisions, not voice (rebaseline finding) | Weekly voice.md commits resume; watchdog expectation registered | Builder | hours | A1.14 |
| A5.9 | Endorsement axis wired | On divergent cases: weekly 2-minute adjudication card — "clone proposed X, you did Y — which was right?" Clone-wins land as the first `better-than-Nate` labels (distinct event type, never promotion evidence for OTHER cells); feeds me_signal + the §6.5 instrument. This is the axis that detects the clone being right where Nate was wrong (everything today scores mimicry) | ≥2 adjudications/week for 4 weeks; endorsement events in ledger with correct provenance | Builder + NATE (recurring) | days | A2.6 |
| A5.10 | Quarterly shadow-Nate week | Protocol committed + calendared: Nate writes his own replies for one week/quarter; the clone shadows silently; blind-compare via the harness. Resets gold-standard drift as Nate changes (person-drift vs clone-drift disambiguation — report §6.5.4) | Protocol doc; first week scheduled; comparison report template ready | Builder | hours | A2.6 |
| A5.11 | Outcome telemetry as evidence, never target | Recipient response latency, thread-resolution-within-7d, downstream corrections, commitment-closure — computed per draft and attached to adjudication cards as EVIDENCE ONLY; **lint/CI assert no optimizer or promotion math reads these fields** (Goodhartable: drafts that demand replies "win") | Fields present on cards; grep tripwire on promotion-path reads | Builder | days | A5.9 |
| A5.12 | "Better than Nate on class C" codified | Promotion meaning per §6.5.5: quiz win-rate >50% + endorsement wins > losses + zero holdout regressions over a quarter → class becomes a candidate for delegation-without-review (the only evidence-grounded meaning of "outperforms me"). Codified in the trust-ladder doc A7.2 consumes *(2026-07-04: trust-ladder removed — earn-demotion ruling; codify directly in `framework/policies/`)* | Definition in `framework/policies/` + referenced by graduation cards | Builder | hours | A5.9, A7.7 |

**Exit criteria — all machine-checkable:**
- [ ] Stage-1 gate live on every draft: 0 unbacked load-bearing claims reach the outbox on the 50-draft battery.
- [ ] Decision dossier compiling nightly, git-versioned, suite gate blocking a synthetic bad compile.
- [ ] Stage-2 classifier: per-category precision measured over ≥1 week of show-first traffic; rule store consulted on every proposal (log-asserted).
- [ ] Endorsement adjudications running 4 consecutive weeks with events landing under the correct provenance.
- [ ] Decision-cell re-run at n≥30 shows honest movement vs the 8.3% baseline (Wilson CI reported; direction over magnitude).
- [ ] Stage 2.5 dormancy verified: below-bar/unproven receipts fall back to queue_draft in test.
**Rollback:** every stage is approve-only until A7; Stage 2.5 dormant flag; dossier compiles are git-versioned (revert = checkout); the truthfulness gate fails closed to HOLD (worst case = more asks, never more lies).
**Captain-attention budget: 1 one-time NATE-ONLY action (A5.5a); recurring ≈2 adjudications/week (~4 min) inside the global cap.**

### A5 build notes — the mandatory dossier slots (never-lie §B, made non-optional)

Every draft/decision fills, from EXISTING functions (the gap is not retrieval — never-lie plan finding):
1. **Thread + full To/CC audience** (`audience_of`; a reply drafted without the audience is malformed by definition — courses-of-action rule).
2. **Person intel + trajectory** per counterparty (`person_intel`, 3-People dossiers).
3. **Why-now / workstream** (`search_brain` + Monday boards + `search_codebase` for technical threads).
4. **Open commitments, both directions** (`open_commitments`; beliefs as-of-T once A4.4 lands).
5. **Board state** (the lane's Monday backlog rows this thread touches).
6. **Live data** when technical (`query_live_data` through the read-only Neon gate).
7. **Nate stance priors** (`nate_model` + captain-decisions/patterns — inform, never quoted outbound).
8. **Calendar** (`calendar_busy` + CAL_GUARD state; commits to times only when CALENDAR_COMPLETE).
9. **Ledger-derived rules** (A5.3 miner output) + analogous past decisions (A5.2 retrieval).
The truthfulness gate (1b) maps every extracted claim to a slot or NONE; NONE + load-bearing ⇒ HOLD-AND-ASK. Verification battery: the Tomás+Kristoffer demo thread + 50-draft regression set, asserted before Stage 2 opens.

---

# Phase A6 — Self-Improvement Loops + Substrate Hygiene

**Goal.** Activate the coded-but-never-run improvement chain WITH signal (the loops are arithmetically dead today: ~2 real experience records/week, `cabinet:reflections:count`=0 post-fix, retro never scheduled, the 808-line R8 chain zero production executions — skills-improvement-loops.md), apply the Gate discipline to every self-modification using A2.4's frozen suite, keep the germline honest (including the brain-bridge contradiction that has the live egress violating the written law), and fix the MacBook substrate fragilities that cap trustable autonomy (marathon sessions, TUI-scrape nervous system, heartbeat semantics, sleep).

| ID | Item | What exactly | Verification | Owner | Effort | Depends on |
|---|---|---|---|---|---|---|
| A6.1 | Experience records hook-enforced + reflections counter proven | Make emission structurally unavoidable: post-tool-use/TaskCompleted hook blocks task-close without `record-experience.sh` (today it only nudges); verify `reflection_stamp` → `cabinet:reflections:count` end-to-end ONCE (it has never worked in production despite the 2026-06-25 fix) | Counter increments on a live reflection; a task-close without a record is blocked in test | Builder | hours | F0.4 |
| A6.2 | Retro + evolution loops scheduled — auto-ratify narrowed FIRST | Schedule `cabinet/cron/retro-trigger.sh` (launchd, in services.yml); install `role-evals-weekly.sh` + `self-improvement-loop.sh` ONLY AFTER narrowing `self_improvement_loop.py`'s `captain_auto_ratified=True` to reversible instruction-level deltas (the blueprint 2.5 ordering hazard — today it would auto-apply charter amendments validated only by plumbing tests); everything else one-tap. Same narrowing+install as Plan B B2.11 — shared instance, execute once | Crons live; a synthetic non-reversible proposal routes to the Captain queue, not auto-apply | Builder | days | A6.1, A2.4 |
| A6.3 | Meta-cognition layers 1–3 live | Layer 1 PREVENT `encode-gate.sh` verified firing; Layer 2 HARVEST (`principle-harvester`, threshold 5) + DETECT (`anomaly-scan.sh`, confidence floor) on schedule; Layer 3 retro backstop = A6.2. All proposal-only into the ONE sink (`shared/interfaces/meta-cognition-proposals.md`) | Counters ticking; one harvested principle reaches the sink within 4 weeks | Builder | hours | A6.2 |
| A6.4 | Skill dedup — one canonical copy | Resolve the memory/skills vs .claude/skills divergence (cross-officer-retro is a 53-line-diff stale subset in the auto-discovered location; 4 foundation skills modified in-place uncommitted against the repo's own rule): one canonical dir, the other generated or removed; commit or revert the in-place edits | Diff between copies = 0 or one copy gone; CI tripwire on future divergence | Builder | hours | F0.1 |
| A6.5 | The Gate applied to pipe/prompt changes — architect preserved as the model | `architect_lib`'s earned-auto-apply (≥3 confirmed/0 wrong, reversible, GERMLINE-first — the only production-earned autonomy in the estate) stays the pattern; extend the same discipline to cabinet prompt/playbook/skill changes: frozen-suite non-regression (A2.4) + pass^k(3) on behavioral cases + cost gate; germline list maintained in ONE place (pre-tool-use write-block + `architect_lib.GERMLINE`), now including the suite dir, reply_binder, ledger-liveness probe, and beliefs table | A prompt change without a suite run cannot merge (CI); germline lists identical in both enforcement points (diff test) | Builder | days | A2.4 |
| A6.5a | Reconcile the brain-bridge germline contradiction | `.claude/rules/brain-bridge.md` still declares `queue_draft` the ONLY outbound path while `chair_drafts.deliver_draft` has been the live egress since 06-24 (blueprint §7 flavor-A repair). Nate applies the amendment naming chair_drafts the sanctioned Chair egress (approval-gated, ledger-bound) — officers cannot self-amend germline | Amended rule committed by Nate; policy-engine tests updated; parity note in captain-decisions.md | NATE-ONLY | 0.3h | F0.5 |
| A6.6 | Episodic officer pattern — pilot then Chair | Officers become logically persistent, physically ephemeral: wake = fresh session from `lane-progress.md` + tier2 handoff (schema'd, spawn-time sanity check vs ledger state, git-committed per wake — handoffs are now memory, an otherwise-ungated behavior artifact); work bounded; exit. Pilot ONE lane officer for 30 days, then the Chair (the 351.9k-token 9-day marathon is the meltdown anti-pattern — self-improving-agents.md episodic-sessions finding). Wakes scheduled inside the 1h prompt-cache TTL | Pilot lane: 30 days, zero compaction-drift incidents, handoff commits present; then Chair cutover with evidence continuity check | Builder | week+ | F0.4, A1 exit |
| A6.7 | Heartbeat semantics fix | Progress-aware heartbeats (monotonic step counters via post-tool-use), idle≠dead (the 900s TTL reads healthy-idle officers as heartbeat-absent today — deployed-state.md); wire into F0.12's watchdog | Idle officer shows healthy; synthetic wedge (alive-but-stuck) alarms | Builder | hours | F0.12 |
| A6.8 | Boot assertions — TUI scrape + version pin | Boot/CI assertion that the `'esc to interrupt'` idle string still matches and the pinned Claude Code version is running (one CC UI change currently breaks idle-gating fleet-wide: poller, triggers.sh, babysitter); mismatch = fleet-down alarm, not silent misbehavior | Assertion fails loudly on a doctored string in test; version pin documented | Builder | hours | F0.4 |
| A6.9 | Sleep + power floor | Assert the MacBook substrate reality in the auditor: `pmset -g` disablesleep=1 (Nate's standing config), StartCalendarInterval used for cadence-critical jobs (A3.5), a wake-gap detector that logs sleep-caused misses instead of letting them masquerade as pipe failures | Auditor row green; a forced sleep window produces a wake-gap log line, no false pipe alarms | Builder | hours | A3.5 |
| A6.10 | GEPA prompt evolution — deferred until the suite has cadence | Offline reflective prompt optimization on 20–100 curated real traces (never 500 — reflector overfits), feedback-rich textual metrics, shipped only through the A6.5 gate. Explicitly AFTER the suite + judge have 4+ weeks of cadence (bounded optimization pressure; hacking grows with loop steps) | First GEPA run report with proxy-vs-holdout delta; changes shipped as gated PRs | Builder | days | A2.4, A6.5 |

**Exit criteria — all machine-checkable:**
- [ ] `cabinet:reflections:count` > 0 from live reflections; retro fired ≥2× on real signal (not the manual command).
- [ ] One skill/prompt change ADMITTED and one REJECTED through the Gate — the loop is live only when it has demonstrably rejected something.
- [ ] Germline lists reconciled (two enforcement points diff-tested) incl. the brain-bridge amendment applied.
- [ ] Episodic pilot: 30 clean days on one lane officer (handoff commits present, zero compaction-drift incidents).
- [ ] Boot assertions green (TUI string + version pin); doctored-string test fails loudly.
- [ ] Heartbeat drill distinguishes idle-healthy from wedged-alive.
**Rollback:** loop crons unload cleanly; auto-ratify narrowing is a config revert; episodic pilot keeps the KeepAlive marathon path available per officer flag; germline amendment is a one-commit Nate revert.
**Captain-attention budget: 1 one-time NATE-ONLY action (A6.5a); recurring 0 (loops route through existing one-tap surfaces).**

### A6 build notes — the maintained germline list (one list, two enforcement points, diff-tested)

After this plan, the germline (officer-unwritable; Nate-applied only) comprises: `framework/policies/authority-matrix.yml` + `base-safety.yml` · `cabinet/scripts/lib/policy_engine.py` + `pre-tool-use.sh` · `framework/fidelity/` judge/scorer/leakguard code · `memory/golden-evals/` incl. the A2.4 suite dir · `framework/frontdoor/reply_binder.py` + the ledger-liveness probe (F0.7) · `cabinet/mcp-scope.yml` + `officer-capabilities.conf` · `.claude/rules/` (brain-bridge, courses-of-action, org-runtime-native) · `instance/config/autonomy.yml` + `trust-ladder.yml` (once authored, A7.2) *(trust-ladder.yml is DEAD as of 2026-07-04 — earn-demotion ruling; never to be authored — drop it from the germline list at the next Nate-applied germline batch)* · screenpipe side: `architect_lib.GERMLINE` set (me_signal, nate-model, ledgers, architect/autonomy machinery) + the A4.4 beliefs DDL + A4.11 fence tests. Two enforcement points (pre-tool-use write-block list ~line 936 and `architect_lib.GERMLINE`) carry the SAME list — a pytest diffs them so they cannot drift apart. Growth discipline: every germline addition rides the Captain-debt queue with a batched apply session (blueprint risk #3 — germline growth recreates the bottleneck it guards against).

---

# Phase A7 — Autonomy Graduation (last; consumes everything above)

**Goal.** Convert accumulated human verdicts into earned, revocable autonomy. Promotion reads HUMAN verdicts only (flavor-A ruling); the ladder is per pooled cell, never per agent; demotion is automatic, instant, human-free; every graduated cell keeps a forever audit holdout; the six hard-ceiling classes never lift. Honest expectation, stated as design not failure: **lanes may take months to graduate — that is the gate working** (report: first auto-send ~day 60–90 at Nate's volume, and only because A7.3 pools scopes into fatter cells so n≥30 is reachable).

| ID | Item | What exactly | Verification | Owner | Effort | Depends on |
|---|---|---|---|---|---|---|
| A7.0 | Broker v1 — write-isolated send executor | Broker v1 owns ONLY the Make send webhook(s): `MSGRAPH_WRITE_WEBHOOK` (and any other send webhooks) removed from officer-readable `_shared/.env` and `cabinet/.env` into the broker's env alone; broker runs as a separate macOS user (A7.0a) with an append-only 0600 outbox/approval ledger **from day one** — an officer running as `nate` can otherwise forge approval rows, and approval validation is theater without write isolation (report §6.3, binding; report P2 sequences broker v1 before/with the first auto-send). `chair_drafts.deliver_draft` delegates the physical send to the broker; A7.5's `execute_after` timestamp lives on the broker outbox row; a send without a matching hash-locked approval row is refused — the hard ceiling becomes physics, not prompt discipline | Officer session cannot invoke the webhook (env absent + permission denied); a send without a matching hash-locked approval row is refused in test; ledger is mode-0600, broker-user-owned, append-only | Builder | days | A7.0a, F0.5 |
| A7.0a | Create the broker macOS user | Create the separate macOS user the broker runs as; hand the send webhook secret(s) into its env only (account creation + secret custody are Nate's hands) | Broker user exists; webhook secret unreadable from a `nate`-user officer session | NATE-ONLY | 0.3h | — |
| A7.1 | Wire the gate to the measurement + policy-shadow burn-in | Replace the hardcoded `'unmeasured'` stub at `cabinet/scripts/lib/policy_engine.py:~1064` with `graduation.evaluate` (fail-safe wrapped to unmeasured on exception — the stub's own comment names the fix; same wire as Plan B B2.9 — shared framework, execute once: if B2.9 landed first, this reduces to verification); officers resuscitate the typed policy-shadow stream (31 events ever, none since Jun 28) → **7-day fresh burn-in** with zero unsafe-direction divergence vs the bash hook. The separated trajectory monitor starts observe-only at the burn-in and stays observe-only from the flip onward (report §6.3); its tuning is deferred post-M4 | Shadow decisions logged daily for 7 days; divergence report = 0 unsafe; stub gone, tests green; trajectory monitor emitting observe rows during the 7-day burn-in | Builder | days | A1.6, A2 exit |
| A7.1a | Flip `CABINET_AUTHORITY_ENFORCING=1` | Nate applies the germline one-liner AFTER the burn-in, with a CLEAN COMMITTED TREE at flip time (runtime-hygiene rule); same env flag as Plan B B3.2 — one flip per deployment, execute once, never two. **Single-flip protocol (cross-plan ruling):** whichever plan reaches the flip first executes it under the UNION of both plans' preconditions — B's (B2.10 test-diff valve + B2.14 parity + F0.9 dead-man + clean tree) always; A's 7-day burn-in additionally required only if a flavor-A lane would change behavior at flip time (fail-closed unmeasured⇒propose_only makes the flip inert for unmeasured lanes, so flipping early is safe). The later plan's flip item reduces to scope-extension verification; bash regex layer retained 30 days as defense-in-depth, then retired via kill tripwire | Flag live; parity soak divergence alarm quiet for 30 days; bash layer retired | NATE-ONLY | 0.2h | A7.1 |
| A7.2 | Author `trust-ladder.yml` + `autonomy.yml` | From the existing `.draft`/`.example` in `instance/config/` (the germline guard currently protects a nonexistent file); ladder rungs = the grand-plan vocabulary (I-would-like-to / I-intend-to / I've-done / I've-been-doing) mapped to matrix verdicts; incorporates A5.12's better-than-Nate definition **[SUPERSEDED 2026-07-04 — earn-demotion ruling: the trust-ladder half is DEAD. `framework/learning/trust_ladder.py` + the `trust-ladder.yml` drafts were removed (lane/ripout-0705); reversible classes are trusted day-one with undo and demoted on evidence, never rung-earned. Do NOT author trust-ladder.yml or rebuild the loader. Only the `autonomy.yml` half of this row remains live.]** | Files exist, validated by `framework/learning/trust_ladder.py` fail-closed loader; ladder card rendered *(superseded — see note)* | NATE-ONLY | 1h | A7.1 |
| A7.3 | Promotion math hardened + pooled cells | Wilson lower-CI over **n≥30 with edits counted (not consecutive)** + dwell time + Nate one-tap ratification per promotion; **pool micro-scopes into fatter cells** (ONE "internal routine comms" cell, not five) so denominators fill in weeks; batch one-taps weight ≤0.5 (A1.4); CI-assert the human-verdicts-only read path (A1.3) | Promotion card for the first eligible cell carries full evidence (n, CI, dwell, provenance mix); pooling visible in matrix | Builder | days | A7.1 |
| A7.4 | First auto-lane candidates, blast-radius ranked | Order: (1) **newsletter-digest** (folder move + digest — lowest blast), (2) **archive-email** (reversible move), (3) **commitment-auto-close** with the evidence gate (state-only; gather_evidence + beliefs as-of-T), (4) **receipt-forward** (only after the A5.4 proving batch + A5.5a carve-out). Each graduates individually through A7.3; nothing skips the ladder | Cells measured; first promotion card delivered when bar clears | Builder | ongoing | A7.0, A7.3, A5.7 |
| A7.4a | Ratify first auto scope + undo window | Nate grants the first `ive-done` cell + confirms the undo window length (per-cell ratification is the ladder's human step, one tap each) | Grant recorded; scope live behind veto window | NATE-ONLY | 0.2h/cell | A7.4 |
| A7.5 | internal_comms veto window — fail-CLOSED | Wire `framework/authority/veto.py` as an `execute_after` timestamp on the broker outbox row (A7.0; fixes the marker-before-send silent-drop): 7-min deferred send for graduated internal-comms actions; **channel-health check before firing** (undo riding a 409-prone Telegram is decorative); **Captain channel unreachable ⇒ HOLD past expiry** (fail closed); per-scope cancel/edit alarms auto-suspend the scope at >2% | Deferred send observable; kill the Captain channel in drill → sends HOLD; cancel-rate alarm fires on synthetic edits | Builder | days | A7.0, A7.4 |
| A7.6 | Demotion thermostat + synthetic wrong-verdict drill | Demotion automatic, instant, human-free on CUSUM alarm / wrong-verdict threshold / fabrication finding (constraint 5); BEFORE trusting any cell, inject a synthetic wrong verdict end-to-end and prove demotion fires (chaos-engineering the trust loop) | Drill: injected wrong verdict demotes the cell + pages within one cycle | Builder | hours | A7.3 |
| A7.7 | Post-graduation audit holdout — forever | Every graduated cell keeps ~10% of actions randomly gated (or a weekly 5-item post-hoc sample); holdout disagreement → auto-demote. Without this, every decay signal structurally vanishes the moment Nate stops looking (red-team addition, report §6.1) | Holdout stream visible per graduated cell; synthetic disagreement demotes in drill | Builder | days | A7.4 |
| A7.8 | Hard-ceiling CI assertions | Permanent CI tests: external_comms (beyond granted executor scopes), deploy_prod, spend, secrets, network_write, credentials_grant resolve `always_gated` at EVERY confidence, forever (`framework/policies/authority-matrix.yml` FIX-6/7 invariants extended); the receipt carve-out exists only as executor-enforced conditions (A5.5), never a matrix row | CI red on any ceiling mutation; carve-out grep tripwire green | Builder | hours | A7.1 |
| A7.9 | Honest-timeline telemetry | Dashboard/briefing rows: cells measured / eligible / graduated, days-at-propose-only per cell, expiry rate, taps/day on outbound (with raw proposal volume alongside so suppression is visible), attention-per-outcome (the north star — published weekly from ledger `seconds_to_decide` × outcomes). Months at propose-only is reported as CORRECT, not stalled | Weekly brief carries the vector; attention-per-outcome series ≥4 points | Builder | hours | A7.3 |

**Exit criteria (Milestone M4) — all machine-checkable:**
- [ ] ≥3 cells measured at n≥30 with Wilson CI computed (query over `graduation.evaluate` output).
- [ ] ≥1 cell Nate-granted `ive-done`, live behind the fail-closed 7-min veto window, holdout stream flowing.
- [ ] Demotion drill passed: synthetic wrong verdict → auto-demote + page within one cycle (A7.6).
- [ ] Zero hard-ceiling autos ever (A7.8 CI green continuously since flip).
- [ ] Attention-per-outcome published weekly, ≥4 points, trending down (A7.9).
- [ ] Cancel/edit rate on the auto scope <2% (else it would have auto-suspended — verify it didn't).
**Rollback:** enforce-flip reverts by unsetting the env (bash layer still present for 30 days); any cell demotes to propose_only instantly via thermostat or `killswitch`; veto-window scopes auto-suspend on alarm; the ladder never deletes evidence — only verdict levels change.
**Captain-attention budget: 4 one-time NATE-ONLY actions (A7.0a, A7.1a, A7.2, A7.4a) ≈1.8h + one 20-min monthly graduation/holdout evidence review.**

### A7 build notes — the promotion card (what Nate sees before granting a cell)

One card per eligible cell, rendered by the Chair composer, carrying ALL of: cell name + pooled scopes · n (live, edits counted; batch-weighted sum shown separately) · Wilson lower-CI vs bar · dwell days · provenance mix (% live-tap / % batch / % quiz) · last 10 verdicts inline · CUSUM state · the 3 worst edits (diffs) in the window · proposed verdict level + undo window + holdout % · one-tap GRANT / HOLD / DEMOTE. A card missing any field is malformed and must not be sent (composer validation). Rationale: promotion is the single highest-blast Captain decision in the system; it gets the full evidence or it doesn't happen.

### Expected-reality statement (binding, from the report)

At ~30 gated drafts/week with ~23% approval, a pooled cell reaches n≥30 clean evidence in 6–12 weeks — **first auto-send land ~day 60–90 after M1, and only for the lowest-blast cell**. Judgment-heavy cells (external comms tone, prioritization) may stay propose-only for quarters. This plan treats that as the gate working. Any pressure to shortcut it routes to weakening a gate — which constraint 11 forbids.

---

# Milestone ladder

| Milestone | Named capability | Measurable exit |
|---|---|---|
| **M0 — The machine is real & breathing** (F0) | Versioned, reproducible, alarmed, billed | CI green on the clonable branch · scripted redeploy reproduces the fleet · 2 weeks zero silent deaths (drill-proven) · backups on the Mini · fleet on Console keys, cost ≠ $0 · kill-list tripwires green |
| **M1 — Labels flow** (A1) | The label economy lives | ≥5 human verdicts/day landing as superseding `verdict_human` ledger events for 7 consecutive days · expiry <15% · me_signal growing · 7 lanes on the one engine · restore drill green |
| **M2 — Measurement has a pulse** (A2) | One harness, one suite, one judge | fidelity_series ≥4 weekly points · frozen suite ≥25 active cases and has rejected ≥1 change · judge contract pinned + calibrated · 8.3% decomposed · quiz running with latency telemetry |
| **M3 — One estate, one memory** (A3+A4) | Rationalized organs | jobs.yml auditor green · ≥12 pipes retired (incl. never-ran batch) + ≥2 via recorded shadow parity · one scheduler truth · pipe-health full scope · content_ts ≥80% · beliefs as-of-T live · one decision store · cabinet_memory retired · consolidation diffs flowing |
| **M4 — Earned hands** (A5+A6+A7) | Trust converts to action | Stage-1 gate on every draft · dossier nightly under suite gate · ≥1 graduated cell behind fail-closed veto + holdout · demotion drill passed · endorsement axis producing labels · attention-per-outcome trending down 4 weeks |

**Milestone verification, one command each:** M0 `gh run list --branch feat/fidelity-harness-design` green + drill log · M1 `jq 'select(.review.verdict_human!=null)' consequence-events-*.jsonl | wc -l` per day ≥5 for 7 days · M2 `wc -l fidelity_series.jsonl` ≥4 + suite rejection record · M3 jobs.yml auditor exit 0 + `ls pipes/ | wc -l` reflects retirements · M4 `graduation.evaluate` dump shows ≥1 graduated cell + holdout events present.

# Risks (with owning mitigation IDs)

1. **The operating pathology recurs** — building outruns operating 7:1; ~14% of designed loops ever ran. Mitigation: phase exits are machine-checked gates (every phase), ≤12 items in flight (How-to-read), auto-shrink rule — if a phase stalls 30 days, shrink the plan (F0.0 ratifies this rule).
2. **Single-annotator label decay** — Nate is the only labeler; fatigue killed the last economy (47% expiry). Mitigation: A2.9 rubber-stamp detector + auto-halving, A1.4 expiry fold-in + batch weighting, A1.10 debt queue, recurring budget hard-capped (Appendix C).
3. **Severed-wire-during-migration class** — every historical dead loop was cut at a duplicated joint mid-migration. Mitigation: A3.16 evidence-continuity gate + A2.7 shadow parity on every MIGRATE; F0.6/F0.14 kill duplicates with CI tripwires; A1.5/A1.6 freeze-not-delete archives.
4. **Make.com/Graph capture outage recurrence** — the brain silently starved for weeks once already. Mitigation: A1.11 canary + re-auth runbook, F0.13 capture-fresh dead-man, A3.4 data-dry trend alarms, A3.12 cadence change only under canary.
5. **Memory poisoning via inbound content** — anyone who emails Nate can write into the substrate officers reason from. Mitigation: A4.12 thread-scoped taint + quarantine veto, A4.11 fences pinned, A2.4 suite-gated self-modification, A5.2 suite-gated dossier compiles.
6. **Goodharting the promotion math** — one-tap farming, judge self-preference, outcome-metric gaming. Mitigation: A1.3 human-verdicts-only CI assert, A1.4 batch weight ≤0.5 + never-mint, A2.3 cross-family pinned judge, A5.11 telemetry-as-evidence lint, A7.7 forever holdout, A7.6 demotion drill.
7. **MacBook substrate fragility caps trust** — sleep, TUI-scrape nervous system, 19GB db on one disk, marathon contexts. Mitigation: F0.9/A1.13 backups + restore drill, A6.8 boot assertions, A6.9 sleep floor, A6.6 episodic sessions, F0.12/A6.7 heartbeat semantics.
8. **Person-drift vs clone-drift confusion** — Nate changes; the gold standard rots. Mitigation: A5.10 quarterly shadow-Nate week, A2.8 CUSUM drift guardrail, recency-weighted sampling in the harness (A2.1), A2.3 monthly judge recalibration.

---

# Appendix A — Coverage map (audit surface)

Every source obligation → satisfying item(s), or an explicit exclusion with reason.

### Coverage matrix areas

| # | Obligation | Item(s) |
|---|---|---|
| 1 | One tap point (poller buttons → reply_binder.bind → ledger) | F0.5, A1.1, A1.2 |
| 1 | verdict_human/verdict_judge split; promotion reads human only | A1.3, A7.3 |
| 1 | gate_decisions live rows flowing again (as canonical-ledger events; file frozen as archive) | A1.2, A1.5 |
| 1 | autonomy_lib 7 lanes → ONE graduation engine; retirement; backfill-exclusion + silent-shadow preserved | A1.6 |
| 1 | me_signal thickening incl. approve/edit diffs | A1.7 |
| 1 | Ledger-liveness dead-man extended to flavor-A lanes | F0.7, A1.8 |
| 1 | telegram-bot's 13 reply kind-handlers each ported or retired-with-reason (no silent severs) | A1.2b, A3.T telegram-bot row |
| 2 | Disposition table, ALL pipes, work-model semantics + shadow-parity retirement rule | A3.T, A3.1, A3.16 |
| 2 | Scheduler consolidation (launchd one truth; frontmatter demoted) | A3.3, F0.14(d) |
| 2 | pipe-health scope: agent-scheduled + .disabled plists | A3.4 |
| 2 | StartCalendarInterval conversion | A3.5 |
| 2 | Make.com keep-with-canary vs direct-Graph (recommended: keep; tenant blocks app consent) + Jun 12–20 backfill | A1.11 |
| 2 | Python 3.12 unification + central LLM client (3 raw-curl impls) | A3.6, A3.7 |
| 2 | SCREENPIPE_ROOT/OBSIDIAN_VAULT_PATH extraction | A3.8 |
| 2 | Secrets → Keychain names-not-values | A3.9 |
| 2 | completion-tracker debris + _archived cleanup | A3.10 |
| 2 | self-knowledge re-enable decision | A3.11 |
| 2 | teams-graph cadence revisit | A3.12 |
| 3 | Vault architecture affirmation + gaps | A4.1 |
| 3 | content_ts 64% → target (≥80%) | A4.2 |
| 3 | Entity-graph decision (defer, justified vs dossier priority) | A4.3 |
| 3 | Nightly Dreams-style consolidation + one-tap memory diff | A4.6 |
| 3 | Semantic-category TTLs + bi-temporal valid_at/invalid_at | A4.5, A4.4 |
| 3 | nate-model layer hygiene (ladder, correct_layer, privacy fence) | A4.7 |
| 3 | reply_enrichment continuation | A4.8 |
| 3 | Six-surface decision fragmentation → one canonical + projections | A4.9 |
| 3 | memory-worker/cabinet_memory decision (retire for A, justified) | A4.10 |
| 3 | Backups: 19GB db snapshot, git remotes, estate-backup shm fix, restore DRILL | F0.9, A1.13 |
| 3 | 0-Self index-exclusion + brain-mcp triple fence kept | A4.11 |
| 4 | Decision dossier (mandatory gather → dossier before draft/decision) | A5.1(a), A5.2, A5.3 |
| 4 | Never-lie Stage 2 / 2.5 (six conditions, dormant) / 3 / 4 | A5.4, A5.5+A5.5a, A5.6, A5.7 |
| 4 | voice-profile maintenance; drafting-lessons loop | A5.8, A4.13 |
| 4 | §6.5 instrument: blind quiz + endorsement axis + shadow-Nate week + outcome telemetry + promotion meaning | A2.6, A5.9, A5.10, A5.11, A5.12 |
| 4 | Retrodiction demoted to scheduled drift guardrail (monthly, n≥30, pinned judge, CUSUM) | A2.8 |
| 5 | Promotion on HUMAN verdicts only | A1.3, A7.3 |
| 5 | First auto-lanes ranked by blast radius | A7.4 |
| 5 | internal_comms veto window (7-min, fail-CLOSED on Captain-channel loss) | A7.5 |
| 5 | Demotion thermostat live | A7.6 |
| 5 | Honest expected reality (months = correct) | A7.9 |
| 5 | Broker v1 (§6.3, report P2): separate-user send executor owns the Make webhook; hash-locked 0600 approval ledger; officer env stripped | A7.0, A7.0a |
| 5 | Separated trajectory monitor observe-only from burn-in through the flip; tuning post-M4 | A7.1 |
| 6 | One voice: brief family RELAY→ABSORB through Chair composer | A3.13, A3.14, A3.15 |
| 6 | Captain-debt reverse queue | A1.10 |
| 6 | Voice-DM input restored | A1.9 |
| 6 | Escalation budget + rubber-stamp detector; ≤5 decisions/day budget | A2.9, F0.16, composer tier caps (existing) |
| 6 | Calendar: EventKit test + pre-meeting briefs | A1.12+A1.12a, A3.14 |
| 7 | Reflection→retro→evolution activated with signal (hook-enforced records; counter verified) | A6.1, A6.2 |
| 7 | Meta-cognition layers 1–3 on schedule | A6.3 |
| 7 | Skill dedup (two dirs diverged) | A6.4 |
| 7 | The Gate on pipe/prompt changes; architect earned-auto-apply as model; germline maintained | A6.5, A6.5a, A2.4 |
| 8 | Sleep reality; tmux/TUI boot assertion; episodic sessions (marathon fix); heartbeat semantics | A6.9, A6.8, A6.6, A6.7+F0.12 |

### Report §P0 (binding 12)

| P0 | Item(s) | P0 | Item(s) |
|---|---|---|---|
| 1 watchdog PATH + error surfacing | F0.10 | 7 cost writer + Console keys | F0.11, F0.11a |
| 2 external dead-man + kill drill | F0.13, F0.13a | 8 killswitch fail-closed + DEL whitelist | F0.8, F0.8a |
| 3 dark cluster + threshold + reasoning-review unwedge | A1.14 | 9 the tap point (full spec) | A1.1–A1.5 |
| 4 off-machine durability + gitignore fix | F0.9, F0.9a, A1.13 | 10 calendar EventKit test | A1.12, A1.12a |
| 5 Make canary + backfill | A1.11 | 11 escalate(reason) | F0.16 |
| 6 Telegram token split | F0.15 | 12 deletion list (§8) | F0.14, A3.T, A3.10 (LLM-in-approve-path killed by A1.1; briefing dedupe A3.13; exact-hash A2.7; brain-bridge docs A6.5a) |

### Report §8 delete list — explicit enumeration

| Delete item | Executed by |
|---|---|
| 8 never-run template pipes (top-of-mind, day-recap, standup-update, time-breakdown, missed-todos, collaboration-patterns, automate-my-work, session-digest) | A3.T RETIRE + A3.10 |
| teams-ocr-capture (0 conversations every run) | A3.T RETIRE |
| conversations-sync audio phase (0 segments / 2,573 runs) | A3.T surgery row |
| exact-hash shadow matching (0/249) | A2.7 (replaced by score_draft) |
| `gate_decisions.jsonl` as live store → frozen archive | A1.5 |
| clone-side `draft-outbox.md` dead-end + brain-bridge docs fix | A6.5a (germline reconcile names chair_drafts; queue_draft docs corrected in same amendment) |
| digital-clone curator pipe | A3.T RETIRE |
| LLM-in-the-approve-path (tmux injection for verdicts) | A1.1 (buttons + deterministic parse; tmux = free-text judgment only) |
| One of the two daily briefings (after parity week) | A3.13 |
| Stale SAFETY_BOUNDARIES/KILLSWITCH Docker-era content | F0.14(c) |

### Design rulings (binding)

| Ruling | Item(s) |
|---|---|
| One ledger (archives frozen, supersede-never-delete) | A1.5 |
| One graduation engine (autonomy_lib retires) | A1.6, A7.3 |
| One harness (fidelity absorbs retrodiction) | A2.1, A2.2 |
| Frozen auto-minted only-growing regression suite, quarantine, germline | A2.4 |
| Promotion reads HUMAN verdicts only (CI-asserted) | A1.3, A7.3 |
| Batch one-taps weight ≤0.5, never mint suite cases | A1.4 |
| Decision dossier = the 8.3% attack | A5.2 (+A2.5 decides emphasis) |
| §6.5 better-than-Nate instrument | A2.6, A5.9–A5.12 |
| Honest ~78% ceiling | Definition of Highest Potential (goal framing; no 90% claims anywhere) |
| Attention-per-outcome as north star | DoHP, A7.9 |

### Governing constraints → where each is enforced

| Constraint | Enforcement item(s) |
|---|---|
| 1 Gate is the mechanism | A2.4 (the suite IS the investment), A6.5 |
| 2 Approval surface owns label capture atomically | F0.5, A1.2 (in-process emit), F0.7+A1.8 (starvation auto-revokes) |
| 3 No loop edits its own judge | A2.4 (suite germline), A6.5 (list diff-tested), A4.11 |
| 4 Machine truth first / human reserved — A promotes on human only | A1.3, A7.3 (CI-asserted read path) |
| 5 Never trust the actor's narrative | A7.6 (fabrication demotes), A5.1 (claims vs evidence), F0.16 |
| 6 Fail closed, degrade honestly | F0.8 (killswitch), A7.5 (veto HOLD), A5.1 (gate→HOLD), A2.3 (judge fallback holds) |
| 7 Built = scheduled + fed + watched | Every item's Verification column; A3.2 auditor; F0.13 dead-man |
| 8 One joint per function; evidence continuity gates migrations | A1.5/A1.6, A3.16, A4.9, A4.10, F0.6/F0.14 |
| 9 Episodic over durable state | A6.6 |
| 10 Captain = metered two-way resource | A1.10 (debt queue), A2.9 (budget+detector), Appendix C caps |
| 11 Asymmetric autonomy; never weaken a gate | A7.9 expected-reality statement, A7.8 |
| 12 Reversibility prices everything | A1.6 lane→cell map, A7.4 blast-radius ranking, architect change-type costing (A6.5) |
| HARD CEILING never lifts | A7.8 CI assertions; A5.5 executor-conditioned carve-out (never a matrix row) |

### Deliberate exclusions

| Obligation/idea | Why excluded |
|---|---|
| Mission loop (mission-supervisor/outbox-relay plists, ~2h-node compiler) | **SUPERSEDES companion report P1**, which scheduled "Mission loop ON (throttled, batch-tier)" for flavor A (§6.2, §7): deferred because flavor A's officers are assistants not product executors, the proactive surface is Chair routines (A3.13–15), and Plan B validates the work-graph pattern first — revisit at M4. Shared F0 keeps its options open; nothing here blocks B's switch-on (B2.11 cron install, B4.10 first routed task). The report §10.4 outcomes.yml confirmation is NOT dropped: Plan B's seed list doesn't carry it, so it rides the F0.0 ratification sit-down here (Appendix B #1). |
| Officer sandbox (deny-by-default network allowlist) + credential-path read-exclusions beyond the send webhook (report §6.3 companions to broker v1) | Partially superseded, remainder deferred: A7.0 removes the highest-blast egress (the send webhook) from officer reach as physics before any cell goes auto; the full deny-by-default sandbox and estate-wide credential read-exclusions are a substrate rewrite with migration tail risk on the MacBook. Interim ceiling on officer reach = broker isolation (A7.0) + F0.6 one send path + germline write-blocks + A3.9 Keychain migration. Revisit at M4 with the Mini-migration decision. |
| Fine-tuning / LoRA sidecar | Frozen-model regime (task directive; report §4.2 — the "SFT 44%" figure is folklore). Only a P4-era style sidecar IF style measurably plateaus — out of this plan's scope. |
| Memory-platform migration (Mem0/Zep/Letta), GraphRAG, LLM-in-retrieval-hot-path | Research-validated non-bets (report §4.9); A4.4 takes the one load-bearing idea (bi-temporality) without the platform. |
| New officer lanes / corporate role-play orgs | 2–4 foreground lanes is the ceiling; grow per-lane autonomy instead (report §4.8). |
| Conductor scheduler-daemon rewrite | Substrate rewrite with migration tail risk; launchd + manifests + auditor instead (F0.4, A3.2). |
| Officer/fleet migration to the Mini this cycle | Waits for 30 clean episodic days (A6.6); Mini does three dumb things only (F0.9). |
| Gmail BCC revival | Redundant with msgraph SentItems capture (architecture decision memory; report §8 don't-build). |
| New pipes for new senses (iMessage/browser) | Wiring/deleting suffices this cycle; revisit post-M4 with the work-contact-allowlist fence (report §6.2). |

# Appendix B — Captain-debt seed list (ALL NATE-ONLY items, one place)

Seeds A1.10's debt queue. **15 one-time actions, ≈8–9 focused hours total, front-loaded into F0/A1.**

| # | ID | Action | Unblocks | Est |
|---|---|---|---|---|
| 1 | F0.0 | Ratify plan spine (ledger/tap-point/freeze rules/≤12 cap) + confirm the 6 outcomes in outcomes.yml are still the right 6 (report §10.4) | everything | 0.5h |
| 2 | F0.8a | Killswitch resume authority = typed token, Nate only | F0.8 drill | 0.2h |
| 3 | F0.9a | Tailscale SSH to Shiny-Teapo + bare-repo/snapshot dirs | all backups | 0.5h |
| 4 | F0.11a | Console org + per-lane workspaces + budget ceilings | ToS-safe fleet, cost truth | 1h |
| 5 | F0.13a | healthchecks.io account | external dead-man | 0.2h |
| 6 | F0.15 | BotFather second bot token | one-owner channel, 409 fix | 0.3h |
| 7 | A1.4 | Decide: retire 1,829 pre-era events (recommended) vs re-judge (~$15–30) | clean series | 0.2h |
| 8 | A1.12a | Add Outlook account to Calendar.app + written EWS self-sanction | calendar sense, 12% of attention | 0.5h |
| 9 | A3.1 | One-tap ratify pipe disposition table (+self-knowledge, +teams cadence) | A3 execution | 0.3h |
| 10 | A5.5a | Apply receipt-forward germline carve-out (six-condition spec) | Stage 2.5 (dormant until proven) | 0.3h |
| 11 | A6.5a | Apply brain-bridge.md germline amendment (chair_drafts reconcile) | germline honesty | 0.3h |
| 12 | A7.0a | Create the broker macOS user + hand send-webhook secret(s) into its env only | A7.0 write-isolated executor — the physics behind every auto-send | 0.3h |
| 13 | A7.1a | Flip CABINET_AUTHORITY_ENFORCING=1 (post burn-in, clean tree) | enforcement | 0.2h |
| 14 | A7.2 | Author autonomy.yml from example *(trust-ladder half SUPERSEDED 2026-07-04 — earn-demotion ruling; module + drafts removed)* | graduation vocabulary | 1h |
| 15 | A7.4a | Ratify first auto-send scope + undo window (per-cell, repeats per cell) | first earned hands | 0.2h |

# Appendix C — Recurring Captain budget (the flywheel's fuel, hard-capped)

- ≤5 surfaced decisions/day (composer tier caps enforce; A2.9 detects rubber-stamping).
- ~5 blind-quiz picks/week (A2.6) + ~2 endorsement adjudications/week (A5.9) ≈ 10 min/week.
- 1 monthly judge-calibration batch, 10–20 labels (A2.3) ≈ 15 min.
- 1 monthly 20-min graduation/holdout evidence review (A7.9) + restore-drill glance (A1.13).
- 1 weekly quarantine/memory-diff batch veto (A4.12, A4.6) ≈ 5 min.
- Quarterly: shadow-Nate week (A5.10 — normal work, clone shadows silently).
- **Auto-halving rule (binding):** if pick latency trends up for 2 weeks, the system halves its weekly ask (A2.9). A starved label economy with honest telemetry beats a fat one that dies of fatigue — that is how the last one died.

# Open questions (tracked, not blocking)

1. **EventKit outcome fork (A1.12):** if the tenant also blocks EWS/ActiveSync sync to Calendar.app, the fallback is the iMIP-email derivation already designed in `docs/email-calendar-imip-2026-06-25.md` — decide only if the 30-min test fails.
2. **The 8.3% decomposition (A2.5) re-aims A5:** if divergence is mostly *scoping*, investment shifts from dossier depth to narrower ask-classes and thread-scoping — the plan pre-authorizes that swap without a new ratification.
3. **Sonnet-vs-Fable on lane work (F0.11):** run as confirmation on the A2 harness once it has cadence; if within noise, fleet economics change materially (report risk #5) — a cost decision, not a design decision.
4. **Batch one-tap weight (≤0.5) calibration:** the ceiling is ruled; the exact weight below it should be fitted once A2.9 latency telemetry distinguishes considered-batch from rubber-stamp-batch behavior.
5. **Chair episodic cutover timing (A6.6):** pilot evidence decides whether the Chair itself goes ephemeral or keeps the 1M-context marathon with tightened compaction — blocked on 30 clean pilot days, not on opinion.
6. **iMessage/browser senses:** excluded this cycle (Appendix A); revisit post-M4 with the work-contact allowlist and the 0-Self-class fence as preconditions.
7. **PM decoupling + voyage-context-4 + linking backfill (Captain-ratified, 2026-07-02; extended same day):** Monday/Jira/Linear become optional TaskAdapter plugins over a local-first canonical store, AND the vault becomes the ONE synthesis destination — a new **RE-POINT-TO-VAULT** disposition class joins A3 (monday-halfhourly + daily/weekly synthesis family + deep-research → vault markdown; people-intel → vault-only dossiers; meeting-intel Reflections-push retires; obsidian-sync mirror → retirement; `context_lib._fetch_monday` → vault note). Monday's only remaining surface = PM via the adapter (dev-tasks, todos, commitment promotion, completion-tracker closes, briefs reading due tasks). The A4 memory program gains one unified vault pass (context-4 re-embed within free tier, 1024d drop-in + chunk_entities + content_ts re-derive + deterministic link backfill; inferred links provenance-tagged); style-centroid stays pinned to voyage-4-large until A2 re-baseline. Spec: `docs/plans/EXECUTION-STATUS.md` §Captain-ratified additions.
8. **Estate Mapper + federated gather (Captain-ratified workstream, 2026-07-02):** applies to flavor A whenever a new tool connects (Slack, OneDrive, …): discovery → Source Map → gated sync plan → compiler-generated jobs with freshness floors; adapter `search` capabilities register as context_lib tier-2 fetchers so un-synced sources stay reachable live. The vault remains the one memory destination (per the RE-POINT-TO-VAULT ruling); live state stays in tools. Spec + gap sweep (webhook seam, vault librarian, elicitation, identity, offboarding): `docs/plans/EXECUTION-STATUS.md` §Captain-ratified additions.
9. **Directions layer + brain-linking program (Captain-ratified additions, 2026-07-02):** per-lane `directions.yml` feeding the renewal loop (AI proposes outcomes against Captain-owned direction; direction-drift check in the retro), and the link-at-write-time program (bidirectional ID stamping, `chunk_entities` lite, big-four frontmatter backlinks) folding into A4 — full spec + sequencing in `docs/plans/EXECUTION-STATUS.md` §Captain-ratified additions. Post-M1/M2; not blocking.

---

*End of Plan A. Companion: Plan B (Mac Mini product org, `~/plan-B-macmini-product-org-2026-07-02.md`) shares F0 (identical in intent, execute once); flavor divergence per blueprint §7 — flavor A promotes on human verdicts, keeps the sensing plane, and demotes retrodiction to a guardrail; the binding shared invariant is that the verdict emit is in-process with the act, on both flavors, forever.*




