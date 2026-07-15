# Fresh-Instance Relaunch — Seed Manifest (2026-07-15)

**Status: MANIFEST ONLY — read-only inventory, no live paths touched.** Built
in worktree `fresh-relaunch-prep` (branch `feat/fresh-relaunch-prep`, off
`origin/master` @2f0253b7, merged `origin/feat/dev-runtime-split` @94f18967
→ merge commit a32f7a10). The live tree `/Users/nate/captains-cabinet` and
the live fleet were read-only inspected, never written.

**Update (§6 verification pass, same day):** the `origin/feat/dev-runtime-split`
ref merged above (94f18967) turned out to be stale relative to the local,
unpushed `feat/dev-runtime-split` branch tip (742956d8) — which carries 3
adversarially-reviewed, sandbox-verified fixes on top, including one that
directly reinforces this whole exercise's core invariant (`cabinet-deploy.sh`
`--dry-run` must never kickstart an already-loaded LIVE LaunchAgent). Merged
the local tip in (commit c9b65cd2 in this worktree), confirmed via diff to be
a strict, purely-additive superset of what 94f18967 gave — nothing removed or
contradicted, `bash -n` clean. This manifest's own classifications were then
re-verified against the live tree a second time (§6 below); the two passes'
findings are folded into §1/§2 in place, with every correction dated and
sourced.

Captain rulings this manifest implements (2026-07-15, relaunch = hatch a
FRESH instance into the dev/runtime-split runtime, keeping searchable
memory, dropping governance sediment): see the task brief for the full
ruling text. Every real path found on the live instance goes in exactly one
of KEEP / DROP below; ambiguous ones are resolved in §3 with a stated rule
and also folded into KEEP/DROP for the count.

## 0. How to read this manifest (mechanism note)

Two different things are both called "carrying a file forward," and they
matter differently to whoever builds `relaunch-seed.sh`:

- **TRACKED files** (in `git ls-files`) ship with every checkout of the
  branch automatically — including a fresh hatch. They are not a "seed"
  decision; classifying them KEEP here just means "no action needed, and
  don't delete them from the tracked tree." Verified per-path via `git
  ls-files` against the live tree, not guessed.
- **Gitignored / untracked real files** (the `??` and ignored paths) are
  the actual seed question: does `relaunch-seed.sh` copy this specific
  live leaf into the fresh instance's `shared/instance/` (per
  `runtime-provision.sh`'s leaf-level symlink scheme), or does the fresh
  hatch's own `generate-instance.py --defaults` / `bootstrap-roles.sh`
  populate it instead (DROP = "regenerate, don't copy old value")?
- **External paths** (outside this repo entirely — the Obsidian vault,
  `~/Library/Application Support/cabinet/`) are real filesystem state this
  Mac holds; DROP here means "don't reconnect/re-copy it into the new
  instance," not "delete it."

`runtime-provision.sh` (merged from `feat/dev-runtime-split`) already
documents its OWN leaf list in its header comment: "the individually-
gitignored leaves... plus the handful of directories that are ENTIRELY
gitignored (`state/`, `cache/`, `archive/`, `loop-prompts/`,
`roles/{active,archive,hats}`, `secrets/`)." That list was built for a
**same-instance infra migration** (carry the live instance unchanged onto
the new runtime tree). This manifest is stricter — the 2026-07-15 relaunch
ruling deliberately drops several of those same leaves (trust-ladder,
roles, loop-prompts content) that a plain infra migration would have kept
byte-for-byte. Where the two disagree, this manifest's classification
governs the fresh-instance case specifically.

## 1. KEEP

### 1a. External (never touched, per ruling)
| Path | Why |
|---|---|
| `~/Obsidian/screenpipe-brain/**` | The vault — source of truth + CRM/memory store. Confirmed present on disk. Untouched; reconnects via the opt-in adapter (1c). |
| screenpipe embeddings brain index (`~/.screenpipe/pipes/embeddings/...`, outside this repo) | External to captains-cabinet entirely; owned by the separate screenpipe/digital-clone system. Out of this repo's inventory scope by construction — noted, not touched. |

### 1b. Fidelity regression corpus — real cases (explicit ruling)
| Path | Why |
|---|---|
| `instance/fidelity/regression_corpus/README.md` | Explains the store (frozen human corrections, flywheel §6.2). |
| `instance/fidelity/regression_corpus/manifest.json` | Tracks the corpus (currently shows modified — new cases added, not yet committed). |
| `instance/fidelity/regression_corpus/cases/*.json` (11 files) | The frozen regression cases themselves — real Captain corrections, replayable. |

### 1c. Screenpipe adapter (explicit ruling: keep, opt-in, export-excluded from public egg)
| Path | Why |
|---|---|
| `instance/flavor-a/**` (README.md, autoreply/{__init__,kristoffer_uat,wiring}.py + tests, flavor_a/{__init__,acting,_vault_gather_runner,manifest.yml,screenpipe_dispatch,screenpipe_reply_wire,screenpipe_source}.py + tests, evals/eval-021-brain-retrieval-quality.md, rules/brain-bridge-screenpipe.md) | Tracked code — the bridge that reconnects the fresh instance to the vault. `__pycache__/` dirs excluded (build artifacts, not content). |

### 1d. Secrets (carried, per ruling — with one named exception)
| Path | Why |
|---|---|
| `cabinet/.env` | Carried as-is EXCEPT the Telegram bot token value, which the Captain rotates at relaunch (chat id stays). This is a value-level edit inside the file, not a path-level drop — flagged for whoever executes cutover, not something this read-only pass edits. |

### 1e. Org-memory / knowledge content (explicit ruling: instance/memory/** knowledge, product-brain)
| Path | Why |
|---|---|
| `instance/memory/tier2/{comms-officer,coo,cos,cpo,cro,cto,polads-ceo,stephie-ceo,unknown}/*.md` (top-level files only — working-notes.md, patterns.md, findings-*.md, dated coordination/status notes, RESUME-CHECKPOINT.md, STANDING-GUARDS.md, etc.) | Officer-accumulated knowledge — the "product-brain." Sampled `cos/` (37 top-level files) and `polads-ceo/` (17 top-level files) directly; same shape applied to all 9 officer buckets. Distinguished from `reflections/` and `evolution-proposals/` subdirs (§2e) and `.session-state.json` (§2d), which are DROP. |
| `instance/memory/tier2/**/.gitkeep`, `reflections/.gitkeep` | Tracked skeleton only — ships regardless. |

### 1f. Tracked framework/instance config + code (ships with every checkout — verified via `git ls-files`, not a seed decision)
| Path | Why |
|---|---|
| `instance/config/{adapters,comms-surface,directions,egress,officer-emails,outcomes,peers,platform,probes,retention,signals,sources,warrooms,watchdog}.yml` | All confirmed TRACKED. Operational config (channels, sources, egress rules, retention, watchdog) — not roster-tied, not governance sediment. |
| `instance/config/act-first-surfaces.yml` | Confirmed TRACKED (unlike its siblings posture.yml/trust-ladder.yml — see §3d, this one has already made the "TRACKED framework-side" transition the ruling describes). |
| `instance/config/policies/README.md`, `instance/config/posture-presets/{org-docker,org-macmini,personal-macbook}.yml`, `instance/config/role-registry.md(+.example)` | Tracked framework docs/presets. |
| `instance/config/extensions.yml`, `instance/config/extra-mcps.json` | Gitignored but real — deployment capability config (which MCP servers/extensions officers can reach), not governance state or roster-tied. Carried. |
| `instance/config/contexts/{_default,adhoc,captains-cabinet,personal,polads,sensed,stephie,stepnetwork,system-self}.yml` (9 files) | Confirmed TRACKED (verification pass, §6). Context-classification taxonomy (which domain/vault-scope a conversation falls under) — framework knowledge independent of who's currently hired, same "dormant until relevant, harmless" logic as the product officer-skills files below. Missed by the first manifest pass; added on recheck. |
| `instance/config/projects/{_template,captains-cabinet,polads,sensed,stephie}.yml` (5 files) | Confirmed TRACKED (verification pass, §6). Project/product metadata definitions — same dormant-but-tracked class as contexts/ above. Missed by the first manifest pass; added on recheck. |
| every `instance/config/*.example` / `*.yml.example` / `*.md.example` template (incl. `contexts/{bakery-site,newsletter}.yml.example`) | Tracked synthetic templates — ship regardless. |
| `instance/agents/cos.md`, `instance/agents/cos/mcp.json` | Tracked baseline Chair definition — always present regardless of roster. |
| `instance/officer-skills/{README.md,comms-officer.txt,cos.txt,polads-ceo.txt,stephie-ceo.txt}` | All confirmed TRACKED skill content. Product-specific ones (polads-ceo.txt, stephie-ceo.txt, and comms-officer.txt per §3e) stay dormant until that role is re-hired — harmless to keep. |
| `instance/tools/polads-sentry-triage.sh` | Tracked tool script; dormant until polads-ceo is re-hired. |
| `memory/skills/*.md` (non-`evolved/` — deploy-and-verify, captain-pattern-listening, TEMPLATE, individual-reflection, spec-quality-gate, cro-research-sweep, create-preset, holistic-thinking, evolution-loop, proactive-quality-audit, captain-intent-inference, cross-officer-retro, quality-pyramid, agent-team-workflow, engineering-development-loop, telegram-communication, production-quality-ownership, research-quality-gate) | Tracked base skill library — distinct from `memory/skills/evolved/` (§2e, DROP). |
| `memory/golden-evals/**` (eval-001..024*.md + framework/fw-*.sh) | Tracked eval suite — framework test content. |
| `shared/backlog.md` | Tracked framework-interface DNA. Its own committed content already says the slot "starts empty on a fresh deployment... this deployment's stale 2026-05 payload was removed" — already in the fresh-ready state. |
| `shared/force-push-log.md` | Tracked git-safety audit doc/protocol — not officer/roster governance sediment. |
| `shared/interfaces/product-specs/{060-stephie-banner-canvas-drag-reposition,066-stephie-booking-front-door-v0-generalization}.md` | See §3f — durable product requirement knowledge, kept distinct from process/evidence artifacts. |
| `shared/interfaces/reviews/{codex-egress-launchd-lifetime-cp1,codex-egress-launchd-lifetime-cp2,codex-egress-launchd-lifetime-drill,codex-release-readiness-audit-cp1,feat-dev-runtime-split-cp1,feat-dev-runtime-split-cp2}.md` | Confirmed TRACKED (the other 8 review files in this dir are untracked — §2a). Commit-time review evidence, ships with repo. |
| `cabinet/world/{growth-ladders,morphology,show-grammar}.yml` | Framework world-ENGINE RULES (code/config governing how the world evolves) — distinct from world STATE/chronicle (§2f, DROP). |

## 2. DROP

### 2a. Captain governance ledgers (explicit ruling)
| Path | Why |
|---|---|
| `shared/interfaces/captain-decisions.md` | Named explicitly. |
| `shared/interfaces/captain-patterns.md` | Named explicitly. |
| `shared/interfaces/captain-intents.md` | Named explicitly. |
| `shared/interfaces/captain-rules-index.yaml` | Named explicitly ("derived captain-rules-index.yaml"). |
| `shared/interfaces/captain-knowledge-classification.yml` | Named explicitly. |
| `shared/interfaces/reviews/{feat-fidelity-harness-design-cp1,feat-fidelity-harness-design-cp2,feat-fidelity-harness-design-cp2-rereview,feat-fidelity-harness-design-cp3-t2-review-fixes,feat-fidelity-harness-design-cp4-knobs,scrub-captain-pii-2026-07-12-cp1,feat-hatch-reauth-extraction,feat-hatch-errand-slice}.md` | Untracked (confirmed via `git ls-files` — not in the tracked set of §1f) review scratch tied to old, already-landed branches. |

### 2b. Learning-loop / eval runtime series + misc process ledgers (shared/interfaces)
| Path | Why |
|---|---|
| `shared/interfaces/action-lessons.yml`, `charter-shadow-series.jsonl`, `golden-eval-scalar.jsonl`, `memory-supersession-proposals.jsonl`, `prediction-calibration.jsonl`, `preference-pairs.jsonl`, `falsifier-series.jsonl` | All gitignored "runtime series written by running lanes/daemons" per the repo's own `.gitignore` comments — regenerate as the fresh instance's learning loop runs. |
| `shared/interfaces/anomaly-ledger.md` | An outcome/anomaly log — same class as the consequence ledgers in §2c. |
| `shared/interfaces/attention-queue.json` | Gitignored — "PII-scrubbed runtime projection, rewritten each 300s surface drain," never committed. Ephemeral, will regenerate. |
| `shared/interfaces/comms-officer-activation-2026-06-24.md`, `deployment-status.md`, `draft-lane-fix-review-2026-06-24.md`, `follow-ups.md`, `graph-mail-folder-access-2026-06-24.md`, `hatch-interview-return-handoff.md`, `legacy-backlog-digest-2026-07-11.md`, `meta-cognition-proposals.md`, `officer-coordination-backlog.md` | Point-in-time process/status/handoff artifacts tied to the OLD hatch/roster/officer coordination history. Not durable knowledge. |
| `shared/interfaces/polads-{001-ci-evidence,001-uat-evidence,003-critical-evidence,ceo-activation-readiness-2026-06-24,sentry-triage-discriminator-contract-2026-07-14,tos-section9-clause-order-review-2026-07-10,uat-kristoffer-round2-2026-06-25,uat-paddle-2026-06-24,uat-paddle-PLAN}.md` (9 files) | Product-specific review/evidence artifacts tied to the OLD polads-ceo officer's completed work. Process history, not the durable product-spec knowledge kept in §1f. |

### 2c. Outcome / consequence ledgers (explicit ruling)
| Path | Why |
|---|---|
| `memory/tier3/experience-records/*.md` (~140 files) + `records-2026-*.jsonl` | Gitignored ("Experience records, decision log, research archive"). This IS the consequence ledger (`framework/fidelity/consequence.py` / `framework/docs/consequence-ledger.md` write here). |
| `memory/tier3/decision-log/`, `memory/tier3/research-archive/` | Currently empty (only `.gitkeep`) but same gitignored class — DROP by rule for consistency. |
| `memory/logs/2026-*.jsonl` (31 daily files) | Gitignored "Runtime logs" — accumulated daily action/event log. |

### 2d. Trust-ladder / earned-autonomy / act-first STATE (explicit ruling — re-earns from zero)
| Path | Why |
|---|---|
| `instance/config/observe-only` (content: `active`), `instance/config/posture-narrow` (content: `earn_up`), `instance/config/act-first-enabled` (0-byte flag) | Live posture/trust-ladder/act-first mode markers — earned state. |
| `instance/config/posture.yml`, `instance/config/trust-ladder.yml` | See §3d — currently untracked-and-unignored (not yet on the "TRACKED framework-side" path the ruling describes for their class); current live values are earned state, not carried. |
| `instance/roles/active/{comms-officer,cos,polads-ceo,stephie-ceo}.yml` | "Durable role state... encode product_slug + auth level chosen at activation time" (`.gitignore`'s own words) — regenerated by `bootstrap-roles.sh` at first deployment, not hand-carried. See §3e on cos.yml/comms-officer.yml specifically. |
| `~/Library/Application Support/cabinet/state/graduation-transitions.json` | "Graduation transitions" = trust-ladder tier-graduation events — direct match. |
| `instance/memory/tier2/**/evolution-proposals/*.md` (2 sampled under `cos/`: `2026-07-08-prod-data-remediation-preflight.md`, `2026-07-10-phase2-draft-skills.md`) | Pre-promotion skill-evolution proposal drafts — same class as §2e evolved-skill state. |

### 2e. Agent-reasoning logs + evolved-skill state (explicit ruling)
| Path | Why |
|---|---|
| `instance/memory/tier2/**/reflections/*.md` (sampled `cos/reflections/` — 25 files incl. cross-officer-retro, individual-coordination, dated boot reflections) | Narrative self-reflection/retro logs — "agent-reasoning" class, distinct from the working-notes knowledge kept in §1e. |
| `memory/skills/evolved/{captain-gated-deliverable,create-officer,create-project,verify-before-claim,chair-front-door-loop,grep-verify-folds,induced-pattern-gate-test,tool-call-syntax-integrity,principle-harvester}.md` | Gitignored "Evolved skills (created/modified by the learning loop at runtime)" — exact ruling match. |
| Officer-skill usage counters | **Not found as a distinct artifact.** Searched `instance/officer-skills/`, `instance/memory/tier2/**`, and Application Support for a counter file; found none separate from `.session-state.json` (§below). If usage counts exist, they are embedded inside the per-officer `.session-state.json` files, already classified DROP. |
| `instance/memory/tier2/**/.session-state.json` | "Per-officer session state (resets between runs)" per `.gitignore`'s own comment — ephemeral session bookkeeping, not knowledge. |

### 2f. World state + chronicle (explicit ruling — fresh world; old archived)
| Path | Why |
|---|---|
| `shared/interfaces/world-chronicle.jsonl` | Gitignored — "append-only replay history; instance data, never committed." |
| `shared/interfaces/world/chronicle-{2026-07-04,05,06,07,08,09,10,11,12,13,14,15}.jsonl`, `chronicle-undated.jsonl` (12 files) | Same class, per-day chronicle shards. |
| `~/Library/Application Support/cabinet/world/chronicle-state.json` | World chronicle checkpoint/pointer state. |
| `shared/interfaces/world/legend.json` | Gitignored under the same blanket `shared/interfaces/world/` pattern as the chronicle shards above (verification pass, §6 — missed by the first manifest pass). A derived block→codex/mechanism legend describing the CURRENT world's rendered entities; regenerates from the KEPT engine-rule YAMLs (`cabinet/world/*.yml`, §1f) once the fresh world starts producing its own chronicle. Carrying the old legend forward risks describing blocks/officers the fresh roster doesn't have. Not itself named in the ruling (unlike its chronicle siblings) — **flagged for the Captain to confirm**, same as the other unnamed grey items below. |

### 2g. Stale queues / inboxes
| Path | Why |
|---|---|
| `instance/state/triggers.json` | Confirmed by content — a literal pending-trigger queue (e.g. an `at-time` trigger tied to old PR #133 verification). Textbook stale queue. |
| `~/Library/Application Support/cabinet/attention/{pacing-state.json,pin-state.json,.pacing.lock,.pin.lock,.standing.lock}` | Attention-pacing/pin queue state. |
| `~/Library/Application Support/cabinet/feed/{feed-2026-07-09..15.jsonl,cursors/}` (7 daily files as of the §6 recheck; the range grows one file/day, so this count is expected to keep moving) | Event feed + read-cursors — an inbox by construction. |
| `~/Library/Application Support/cabinet/telegram-state/{comms-officer,cos,first-lane-ceo,ghost-officer,polads-ceo,sbx-alpha,sbx-beta,stephie-ceo,zzz-sandbox-echo}/` (9 dirs — verification pass, §6, found 4 more than the first manifest pass named: `sbx-alpha`, `sbx-beta`, `stephie-ceo`, `zzz-sandbox-echo`) | Per-officer/sandbox Telegram chat/session state — moot once the bot token is rotated (ruling) and the roster resets; the `sbx-*`/`zzz-sandbox-echo` dirs are test scaffolding, same disposition. |

### 2h. Generated launchd plists (explicit ruling)
| Path | Why |
|---|---|
| `cabinet/launchd/generated/*.plist` (43 files — verification pass, §6: the first manifest pass's own named list already had exactly these 43 entries, its "(44 files: ...)" header just miscounted its own list by one, not a live-tree change; recount confirms the SET is identical, nothing added or removed: dashboard, probe-vercel, calendar-intake, memory-curator-health, ledger-liveness, charter-shadow, regression-corpus, actfirst-canary, prediction-calibration, cabinet-doctor, healthchecks-drill, draft-lane, self-improvement-loop, surface-pin, fidelity-f1, falsifier-daily, backup, world-chronicle, apoptosis-sweep, officer.cos-inbound, probe-github, exhaust-archive, probe-sentry, intake-surface, transcript-digest, retro-trigger, outcome-watchdog, undo-sweep, memory-worker, backlog-refine, status-sweep, verifier, world-census, frontdoor-briefing, action-lane, judge-calibration, officer-supervisor-mac, preference-pairs, research-sweep, graduation-transitions, memory-reconcile, memory-contradictions, limit-reset-watchdog) | Gitignored, machine/roster-specific — regenerated by `generate-plists.py` from `cabinet/services.yml` + the new roster on the new runtime tree. |

### 2i. Roster (explicit ruling — fresh hatch default, no pre-seeded product CEOs)
| Path | Why |
|---|---|
| `instance/config/roster.yml` | Named class directly. |
| `instance/config/active-preset` (content: `portfolio`) | Deployment-local active-preset selector tied to the old multi-product setup. |
| `instance/agents/{polads-ceo,stephie-ceo}.md` | Gitignored, rendered from the portfolio template — product-CEO instantiations. |
| `instance/loop-prompts/{polads-ceo,stephie-ceo,comms-officer}.txt` | Wholly-gitignored dir; product/role self-wake prompts (comms-officer per §3e). |

### 2j. Caches, backups, undo journals, and old-archived material (regenerable or superseded by the pre-cutover tar)
| Path | Why |
|---|---|
| `instance/cache/{cabinet-context-slugs.tsv,cabinet-mcp-scope.tsv}` | Gitignored cache — ephemeral, regenerates. |
| `instance/.DS_Store`, `instance/config/.DS_Store` | macOS Finder metadata (verification pass, §6 — missed by the first manifest pass). Zero content value, not instance data under any definition; excluded regardless of the ruling's named classes. |
| `instance/archive/**` (docs/ 26 files + docs/onboarding/ 2 files = 28, presets/step-network 11 files, proposals/*.md ×3, refslund.ai/{customer-templates 8 files,runbooks 1 file}, shared/cabinet-framework-backlog.md — exact recount, §6; the first pass's "~20" for docs/ was an approximation, not an error) | Gitignored — the repo's OWN "Runtime archives (migration snapshots, etc.)" holding pen. Already-retired material; the "old...archived" principle applies generally, not just to the world. |
| `~/Library/Application Support/cabinet/apoptosis-state.json` | Hygiene/pruning-sweep state — fresh instance starts with nothing pending pruning. |
| `~/Library/Application Support/cabinet/claude-config/**` (**4,931 files** — `.claude.json`, `.cc-writes/`, `.last-cleanup`, `.last-update-result.json`, README.md) | The shared `CLAUDE_CONFIG_DIR` officers' Claude Code sessions use — MCP consents, session/project history for the OLD officer fleet. By far the largest single dataset in this inventory; carrying it forward defeats "fresh instance" (leaks old consent/session state into new officers). Regenerates on first launch. |
| `~/Library/Application Support/cabinet/events/config-drift-*.jsonl` (18 files at the §6 recheck, down from 119 at the first pass — this one is a REAL change, not a miscount: something pruned this log in the interim, consistent with this repo's self-pruning-log pattern elsewhere; either count supports the identical DROP disposition) | Historical config-drift monitoring log — fresh instance starts a new drift baseline. |
| `~/Library/Application Support/cabinet/ledger-backups/{a14-actor-id-20260707_075752Z-28605,purge-20260704_232009Z-48377,purge-20260705_083736Z-80700}/` (72 files) | Backups of ledgers that are themselves DROP; also covered by the pre-cutover tar-archive safety net. |
| `~/Library/Application Support/cabinet/probe-sentry-seen.json` | Dedup/seen-cache for a Sentry probe — regenerates (worst case: re-processes a few old issues once). |
| `~/Library/Application Support/cabinet/undo/{canary-receipts.jsonl,frozen-kinds.jsonl,frozen-kinds.jsonl.bak-1783207967,undo-journal-2026-07-04.jsonl,undo-journal-2026-07-06.jsonl}` | Undo journal for actions taken by the OLD officer set — nothing to undo once they're gone. |

## 3. Grey areas — resolved (stated rule applied; folded into §1/§2 counts above)

a. **`shared/interfaces/reviews/` mixed tracked status** — 6 of 14 real files are
   tracked (commit-evidence, kept regardless per repo convention), 8 are
   untracked scratch (dropped). Resolved by `git ls-files` ground truth, not
   guessed — see §1f / §2a.
b. **`shared/interfaces/captain-vetoes.yml`** — not on the Captain's named
   drop list (only decisions/patterns/intents + derived rules-index/
   classification were named), but it is a live-control surface encoding
   vetoes specific to OLD officers/products. Rule applied: DROP (roster-
   specific content, not itself a historical ledger like its siblings, but
   stale once the roster it references is gone) — **flagged for the
   Captain to confirm**, since it wasn't explicitly named.
c. **`instance/config/hq-instance.yml.draft`** — TRACKED (confirmed via
   `git ls-files`), so it ships with the checkout regardless of this
   manifest. Rule applied: DROP means "not activated/materialized as the
   fresh instance's identity" (the Roster ruling supersedes its proposed
   redesign) — the tracked file itself stays in the repo as dormant
   history unless the Captain separately decides to retire it.
d. **`instance/config/{posture,trust-ladder}.yml` vs `act-first-surfaces.yml`
   discrepancy** — the ruling describes all of these (plus standing-grants)
   as "TRACKED framework-side per the split design." Ground truth: only
   `act-first-surfaces.yml` has actually made that transition (tracked);
   `posture.yml` and `trust-ladder.yml` are currently just untracked-and-
   unignored live files (neither tracked nor gitignored) — i.e. the
   tracking-scheme migration the ruling describes hasn't landed for these
   two yet. Rule applied: treat by ruling INTENT, not current mechanics —
   DROP the current live values (don't seed them); note the tracking gap
   as a follow-up for whoever builds `relaunch-seed.sh` or a future
   framework-hygiene pass (they should not be silently swept up by a
   generic "gitignored leaf" copy loop, since they're not gitignored at
   all right now).
e. **`comms-officer` role-class files** — the Roster ruling names only
   "product CEOs," not comms-officer, but comms-officer is not in the
   base standing fleet (CoS/CTO/CPO/CRO/COO) either — it reads as a
   HIRED/ADDED role, same shape as a product CEO. Rule applied: treat
   comms-officer's roster/role/loop-prompt bindings (`instance/roles/
   active/comms-officer.yml`, `instance/loop-prompts/comms-officer.txt`)
   as DROP alongside the product CEOs; the tracked `instance/officer-
   skills/comms-officer.txt` content still ships (§1f). **Flagged for the
   Captain to confirm** — this wasn't explicit in the ruling text.
   `instance/roles/active/cos.yml` is dropped too, for consistency with
   its three siblings (same gitignored class, same `bootstrap-roles.sh`
   regeneration path) even though CoS itself is the one role that always
   exists — the fresh hatch re-derives its activation-time auth level
   rather than inheriting the old file.
f. **`shared/interfaces/product-specs/*.md`** — gitignored by the blanket
   `shared/interfaces/**/*.md` rule (so mechanically the same untracked
   class as the dropped process/evidence docs), but these two files are
   durable product REQUIREMENTS (what a feature should do), not officer
   process history. Rule applied: KEEP, distinguishing knowledge-content
   from process/evidence/backlog artifacts — same distinction the ruling
   draws for `instance/memory/**`.
g. **`instance/config/authority-enforcing`** — TRACKED, records a Captain
   ruling ("flip it," 2026-07-03) turning on the typed policy engine
   fleet-wide. Not per-officer earned trust (unlike trust-ladder/posture);
   it's a system-wide mode switch already proven safe via a parity proof.
   Rule applied: KEEP — dropping it would silently regress enforcement to
   a weaker mode on relaunch, which reads as a regression, not a "fresh
   start." **Flagged for the Captain to confirm**, since it wasn't an
   explicit line-item either way.

## 4. Not currently materialized on this live tree (N/A — nothing to classify)

Named in the ruling's config-class or referenced by tooling, but absent on
this specific machine right now (checked directly, not assumed):
`instance/config/{product.yml,active-project.txt,war-room-seed.yml,
publish-scan-patterns.local,required-plugins.yml,autonomy.yml,standing-
grants.yml}` (only their `.example` twins exist), `instance/onboarding/`
(no such directory), `instance/evidence/` (no such directory — the PR #140
evidence recorder store this would belong to isn't merged/active yet),
top-level `secrets/` (no such directory). If any of these materialize
before cutover, apply the same-class rule already stated above for their
sibling files (config leaves the ruling names → DROP; operational
capability config → KEEP).

## 5. Procedural notes (not a keep/drop decision — recorded so they aren't lost)

- **Pre-cutover tar-archive**: the Captain's ruling requires tarring
  `instance/**` (the FULL tree, including everything marked DROP above)
  plus the relevant `~/Library/Application Support/cabinet/` state, before
  cutover — this is the rollback safety net regardless of what this
  manifest seeds forward. Not executed by this pass (inventory only).
- **Kill-switch**: `cabinet:killswitch` is ACTIVE in the shared Redis right
  now (verified independently by the concurrent `dev-runtime-split-build`
  workflow, not re-verified here). The new instance inherits it as-is;
  clearing it is a named Captain-only step (`kill-switch.sh deactivate`),
  never done by an agent.
- **Telegram token rotation**: a value-level edit inside `cabinet/.env`
  (§1d), done by the Captain via BotFather at relaunch — not a path this
  manifest drops, since the chat id and the rest of the file carry over.

## 6. Verification pass (second pass, same day — re-walked the live tree directly)

This manifest was re-checked against `/Users/nate/captains-cabinet/instance/**`,
`shared/interfaces/*`, and `~/Library/Application Support/cabinet/` a second
time, independently, rather than trusting the first pass's counts. Several
other workflows are concurrently active against this exact live tree today
(RESUME-BOARD), so some drift between passes is expected and not itself a
defect — each is called out below as either a genuine live-tree change or a
first-pass miscount.

**Gaps found and fixed (real paths that weren't in either KEEP or DROP):**
- `instance/config/contexts/*` (9 real `.yml` + 2 `.example`, all confirmed
  TRACKED) and `instance/config/projects/*` (5 files, all TRACKED) — entirely
  unmentioned by the first pass. Added to §1f as KEEP (tracked, dormant-until-
  relevant class, same as officer-skills).
- `shared/interfaces/world/legend.json` — unmentioned; added to §2f as DROP
  (flagged for Captain confirmation, same as its unnamed siblings in §3).
- `~/Library/Application Support/cabinet/telegram-state/` — the first pass
  named only 5 of the 9 real directories present; the missing 4
  (`sbx-alpha`, `sbx-beta`, `stephie-ceo`, `zzz-sandbox-echo`) are folded into
  the same §2g row under the same rule.
- `instance/.DS_Store`, `instance/config/.DS_Store` — macOS Finder noise,
  unmentioned; added to §2j as trivial DROP.

**Counts corrected (with cause distinguished):**
- Launchd generated plists: first pass said "44 files" but its own named list
  had only 43 entries, and a fresh recount of `cabinet/launchd/generated/`
  found the identical 43-item set — this was the first pass's own arithmetic
  slip, not a live-tree change.
- `events/config-drift-*.jsonl`: 18 files now vs. 119 claimed — a REAL
  live-tree change (something pruned this log between passes); disposition
  (DROP) is unaffected either way.
- `feed/feed-2026-07-*.jsonl`: 7 files (07-09 through 07-15) vs. the first
  pass's implied 4 (07-09..12) — expected drift, the range grows one file per
  day; disposition unaffected.
- `instance/archive/docs/` (+`onboarding/` subdir): exact recount is 28 files
  vs. the first pass's "~20" — the "~" already signaled an estimate, not an
  error; disposition unaffected.

**Confirmed exactly correct on recheck (no changes needed):** `instance/config/`
enumerated exhaustively file-by-file against §1f/§2d/§2i/§3 (every real path
outside the two gaps above lands correctly); `instance/memory/tier2/` — all 9
officer buckets present as named; `instance/fidelity/regression_corpus/cases/`
— 11 files, matching exactly (the 3 newest untracked cases are already inside
that count, not additional to it); `instance/roles/active/` — exactly the 4
named files; `instance/agents/`, `instance/officer-skills/`, `instance/tools/`,
`instance/flavor-a/` (non-`__pycache__`), `instance/loop-prompts/`,
`instance/cache/` — every real file matches §1c/§1f/§2i exactly, nothing extra
and nothing missing; `shared/interfaces/reviews/` tracked/untracked 6/8 split —
confirmed via `git ls-files` run from the worktree (the correct reference
frame for a "ships with every checkout" claim, since untracked files don't
propagate into a fresh `git worktree add` the way they do on the live tree —
verified this distinction explicitly rather than assuming one tree answers
both a "what real data exists" question and a "what's tracked" question);
`~/Library/Application Support/cabinet/state/` — exactly the one claimed file
(`graduation-transitions.json`), content confirmed to be trust-ladder cell
data; `shared/interfaces/` top-level flat files, `product-specs/` (2 files) —
all exactly as listed.

**Net effect on the counts in §1/§2**: 16 real paths added across KEEP (+16:
9 contexts .yml + 2 contexts .example + 5 projects .yml) and DROP (+7: 1
legend.json + 4 telegram-state dirs + 2 .DS_Store); zero paths reclassified
between KEEP and DROP. Every real path this pass touched now lands in exactly
one list, per the task's requirement.
