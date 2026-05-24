# Spec 049: /self-review 4-Gate Composition + Stagehand v3 Visual-UAT + Workflow Discipline Extensions

**Version:** v3.1 (COO adversary fold — 21 findings, SHIP-WITH-FOLDS + ast-grep C4 collapse) — v3.0.2 superseded

**v3.1 changelog — COO adversary fold (independent Opus-agent substitute, 2026-05-24; artifact `shared/interfaces/2026-05-24-spec049-adversary-review.md`).** Verdict SHIP-WITH-FOLDS, 21 findings, all surgical, no Captain ack required. PRIMARY = the gate-scoped simultaneous multi-failure-mode interaction (MF-1..MF-5); secondary = mechanism/invariant scan (C1-C4, M1-M7, m1-m5). Folds:

**NEW §"Gate-4 joint-failure determinism" (MF-1..MF-5 — the gate-critical surface):** the 3 target failures (preview-down + cache-poison + cost-cap) are a *causal cascade*, not independent: preview-recovery→new-deploy→cache-invalidation→cold-runs→cost-cap→corrupted-resume. Folds: (MF-2, highest-leverage) **drop `.next/build-manifest.json` from the `nextjs` cache-hash** — rely on source-mtime + lockfile (CRO v3.0.1's established reasoning, now applied to `nextjs` mode) so deploy-only churn doesn't invalidate → breaks the cascade at root [AC #14]; (MF-1+MF-4+M5) **build-hash binding** — `checkpointBuildHash` + `gate4BuildHash` + `selfReviewPassedSha`; Gate-4 runs are build-atomic (hash re-checked at loop end; mismatch → discard + re-run); resume discards stale checkpoint [AC #4/#5/#14 + schema]; (MF-3) **terminal-state precedence FAIL > BLOCK > INDETERMINATE** — a real visual FAIL is never masked by a preview-INDETERMINATE override [new AC #22]; (MF-5) **release the concurrency permit across blocking waits** (preview-poll + officer-decision) — lock protects only active Chromium work [AC #13].

**CRITICAL (C1-C4):**
- **C1 [DECISION — per-task cost/token source of truth, blocks Phase 2a]:** AC #8/#10 assumed a per-task counter that doesn't exist (FW-016 removed byte-count tracking; real cost is the per-officer-per-day Redis HSET `cabinet:cost:tokens:daily:<date>`). **Resolution:** (a) **Gate-4 USD (AC #10 `visualUatCost`)** = `stagehand-runner.sh` reads its OWN Anthropic API `usage` object per vision call × `model-pricing.json` (the runner is a discrete process controlling exactly this spend — clean + testable); (b) **agent token cap (AC #8 `agentTokensTotal`)** = per-task DELTA of the wrapper HSET (`<role>_cost_micro`), snapshot at `/pickup-task` baseline, diffed each check; officer-scoped ≈ task-scoped under the Spec 034 §2b.4 one-task-per-officer-window pool invariant (pinned as the enabling invariant); (c) **agent step cap (`agentStepCap`)** = hook counts `cabinet:toolcalls:$OFFICER` (already exists). Each cap now names its writer + data source. **CTO confirms the HSET field names + runner usage-object access at Phase 2a.**
- **C2 [remove inappropriate Captain-facing write]:** removed the `captain-decisions.md` auto-append from AC #16 (machine append violates the file's WHY-required human-curated contract + triggers Spec 034 cross-cabinet pub-sub sync churn on every >$10 bump). Audit trail stays in `visual-uat-cost.jsonl` (A11-log per ARCH-5); material bumps emit `CAP_BUMP_MATERIAL` for the CoS briefing cost-section (officer-authored, with WHY). Resolves the latent ARCH-5 self-contradiction.
- **C3 [Layer-2 hook hardening, blocks Phase 5]:** AC #7 conventional-commit hook MUST reuse the existing pre-tool-use.sh `git`/`gh` flag-tolerant anchor machinery (FW-041/043/045 reference) not a fresh fragile regex; enumerate `-F`/`--file` + `-c`/`-C` (parse target or fail-closed-with-warn, never fail-open); **explicitly block `--no-verify`/`-n` on git commit/push argv** (else the anti_pattern is decorative); golden eval ships the FW-029-family bypass corpus. ≥2 adversary passes per security-regex-authoring discipline.
- **C4 [DECISION — ast-grep version topology, blocks Phase 2b]:** **COLLAPSED ast-grep Gate-3 into THIS v3.1** (Captain-ratified msg 2547/2550, build-blocking — splitting to a later v3.2 leaves Phase 2b/Gate-3 under-specified). Folds the staged ACs: ast-grep binary in `bootstrap-host.sh` PATH; `anti_patterns[]` schema accepts `{ast_grep: <rule.yaml>}` alongside plain strings; Gate-3 runs `ast-grep scan` against the rule set, surfaces structural matches as findings [AC #3 + new AC #23]. (Supersedes the separate v3.2-staging — task #35 absorbed here.)

**MAJOR (M1-M7):** M1 cost-cap layering ($5 visual sub-cap nested under FW-002 + Spec 050 $50/day cabinet cap; new INDETERMINATE-BUDGET edge case) [AC #10]; M2 replace `BLPOP`-as-mutex with a real crash-safe semaphore (`SET key <owner> NX EX <ttl>` per-permit keys + TTL auto-release) [AC #13]; M3 page-list allowlist = path-only against the PINNED preview origin (reject `//host`/absolute/`..`) + flag self-modifying-config diffs (widening `allowed_paths`/caps/`custom` cache-script) as Gate-3 approval-required [AC #15]; M4 drop the phantom Anthropic pricing endpoint — `model-pricing.json` is SoT with a `pricing_as_of` staleness WARN (≥30d), no hot-path scrape [AC #18]; M5 see build-hash binding above [AC #5]; M6 Gate-3 partial-PASS: define `coverage` = % changed-hunks (orchestrator-computed, not subagent-self-reported) + unscanned remainder recorded as a `/tasks` follow-up + forbidden for security-sensitive paths [AC #3]; M7 AC #4 SLA gets a hard ceiling (cold ≤10s/pg p95, replay ≤2s p95) that fails regardless of measurement, Phase-3 pins the target within it [AC #4].

**MINOR (m1-m5):** m1 AC #9 validates `schema_version` + WARNs on older; m2 raise lock timeout to 180s OR checkpoint per-page (tie M2/MF-5); m3 AC #2 trufflehog FP claim → mechanism not %; m4 rename `visual_uat.cache_depth` → `conventions.atomic_commit_group_depth` [AC #6]; m5 Phase-5 pre-step reconciles the live /ship-pr duplicate-step-10 + stale notify path before layering.

**Verified SOUND (false-positives rejected by the reviewer):** A12 graceful degradation (AC #12), A11/ARCH-5 (once C2 fixed), Stagehand A3 build-vs-buy, ARCH-2 cap ordering (contingent on C1 ✓), CRO v3.0.1 HEAD-exclusion, F22 host-mount.

**Ship status:** SHIP-READY for CTO Phase 2a after this fold. No Captain final-ack (none introduce an irreversible Captain-gated call; C2 *removes* an inappropriate Captain-facing write). The MF subsection + AC edits below carry the substantive folds; this changelog is the audit record.

**Version numbering policy (resolves CTO process question):** v3 = first CRO adversary fold; v3.0.x = patch-level parallel/incremental adversary folds (CRO re-review, CoS architecture review); **v3.1 reserved for COO adversary fold** (final pre-CTO-build gate per Phasing table Phase 1b). CTO Phase 2a build holds on v3.1 ship-ready signal (v3.0.2 + COO adversary clean OR v3.1 with COO findings folded).
**v3.0.2 changelog:** CoS architecture review (verdict: A11 clean ✓ + anti-Devin posture sound ✓ + loop integrity preserved ✓) surfaced 5 findings folded in this pass:
- **ARCH-1 (A12 circular dependency):** AC#12 test gracefully degrades on A12-missing — WARN not FAIL — decouples Spec 049 ship from CoS A12 ratification cycle (CoS encoding A12 PROPOSED tonight for tomorrow 07:00 briefing).
- **ARCH-2 (cap event-chain priority):** cost-cap BLOCK > token-cap WARNING (cost is irreversible spend); 80%/100% events consolidated into structured `CAP_APPROACH` / `CAP_HIT` with payload listing all triggered caps (no duplicate events).
- **ARCH-3 (pool × concurrency starvation):** Gate 4 lock timeout default 60s configurable; early-reject path → `INDETERMINATE-CONCURRENCY-STARVATION` returns to Gate 3 or defer-and-retry (not session-blocking).
- **ARCH-4 (/pickup-task documentation completeness):** Phase 4 explicitly enumerates /pickup-task SKILL.md edit (step 13 documentation) alongside per-project agent-instructions.md template.
- **ARCH-5 (A11 logs-vs-canonical clarification):** spec-body confirmation that `cabinet/logs/*` are ephemeral operational logs (A11-orthogonal). Canonical: Library Specs Space + captain-decisions.md + /tasks.

**v3.0.1 prior changelog preserved below:** CRO re-review surfaced 5 fold-incomplete items + 1 non-Next.js cache-invalidation scope-gap. All 6 resolved: F1b problem-section 89%→85.8%; F3b AC #4 SLA citation aligned to empirical baseline; F5b edge-case action-cache references AC #14 mechanism; F13b edge-case secret-scan uses new .gitleaks.toml-vs-baseline disambiguation; F22b Dependencies host-mount /opt/stagehand-shared/ pattern; AC #14 cache_invalidation_source extended with `nextjs` / `git-deps` / `custom` modes. Plus CRO v3.0.1 spot-check optimization: `git rev-parse HEAD` removed from git-deps cache hash (lockfile + path-mtime sufficient; HEAD adds noise without precision).

COO adversary review LANDED 2026-05-24 (independent Opus substitute — COO injection-locked + bot-down) → 21 findings folded into v3.1 (this version) → CTO Phase 2a build start UNBLOCKED. ast-grep collapsed into v3.1 per C4 (no separate v3.2).
**v3 changelog:** CRO adversary review fold — 22 actionable findings resolved (F1 Stagehand WebVoyager 85.8% conservative / F2 local-vs-Browserbase substrate AC / F3 cold-run latency citation / F4 concurrency model + per-officer Chromium profile / F5 action-cache invalidation concrete mechanism / F6 page-list allowlist via agent-instructions.md / F7 cost-cap bump audit trail + selective captain-decisions / F8 vision-fallback per-page retry cap / F9 atomic-commit override audit / F10 model-pricing.json per-model conversion / F11 gitleaks + trufflehog-verified pairing / F12 first-adoption full sweep + delta-scan / F13 baseline-vs-allowlist semantic clarification / F14 duplicate paste removed / F15 rationale-anchor pointer not literal grep / F16 propose A12 captain-pattern via CoS / F18 framework-backlog A11-canonical Spec 050 candidate / F19 conventional-commit scope underscore widening / F20 ≥13 assertions floor / F21 Phase 6 schema sequenced first / F22 Stagehand host-mount note / F23 selfReviewIterationCount field). F17 A11-clean verified ✓.
**Priority:** P0 (Captain greenlit msg 2540, 2026-05-18 21:34 UTC)
**Framework ticket:** FW-095 (filed in `shared/cabinet-framework-backlog.md` post-Captain-greenlight)
**Owner:** CPO (spec) + CTO (implementation) + CRO (adversary review at draft-time per offer)
**Scope:** Per-project officer skills (`.claude/skills/{self-review,ship-pr,pickup-task}/SKILL.md`) + new framework-level `.cabinet/agent-instructions.md` per-project template + new substrate `cabinet/scripts/visual-uat/stagehand-runner.sh` (or equivalent Node.js entrypoint)
**Canonical artifact home:** Library Space "Specs" (per A11; cabinet's persistent surface for spec records, NOT Notion or external docs system)
**Evidence:** 3-brief convergent seed —
  - `shared/interfaces/research-briefs/2026-05-18-mac-clone-and-computer-use-scope.md` (CoS scoping)
  - `shared/interfaces/research-briefs/2026-05-18-competitor-pickup-review-ship-patterns.md` (CRO lateral)
  - `shared/interfaces/research-briefs/2026-05-18-screenpipe-ocr-and-frontier-autonomy.md` (CoS frontier)
  - Captain msg 2540 ratification routed via CoS @ 21:34 UTC
**v2 changelog:** CPO self-review (4 BLOCKERs + 5 IMPROVEMENTs + 3 POLISH) + CTO tech review (8 substrate + 2 housekeeping) BOTH folded in single pass. Resolutions:
- **B1 (A1 cost-cap misapplication):** removed Captain-gate on $5 default (reversible config edit); resolves CTO #9 confirming-gate which assumed B1's premise.
- **B2 (A3 build-vs-buy on Stagehand v3):** new "Build-vs-Buy on Stagehand v3" section.
- **B3 (Gate-3-loop ⨯ token-cap):** defined behavior — Gate 3 partial-result-on-cap with WARNING event, not abrupt termination.
- **B4 (A11 canonical artifact home):** Library Space "Specs" designated.
- **I1 (Gate 2 history scanning):** gitleaks scope extended to last 100 commits.
- **I2 + CTO #7 (atomic-commit heuristic precision):** file-group = top-level directory subtree at depth ≤2, configurable in agent-instructions.md.
- **I3 (Stagehand cold-run SLA disentanglement):** AC4 split into Stagehand-execution-time SLA (<5s/page cold, <1s replay) and Vercel-preview-availability gate (separate timeout).
- **I4 (agent-instructions.md YAML schema):** schema skeleton block added.
- **I5 (anti-Devin AC testability):** AC12 rewritten as grep-testable assertion.
- **CTO #1 (.claude/active-task.json greenfield):** explicit lifecycle section added — per-(officer,project), created by /pickup-task, deleted post-merge by /ship-pr Phase 10 (already in existing skill, now memorialized in spec).
- **CTO #2 (pre-commit hook class clarification):** install path = pre-tool-use intercept on `git commit` argv (NOT git-native, NOT husky); composes with existing pre-tool-use.sh as new Layer-2 gate.
- **CTO #3 (tooling gap pnpm + gitleaks):** Option (b) adopted — pnpm via npx, gitleaks in `cabinet/scripts/bootstrap-host.sh` PATH.
- **CTO #4 (Stagehand 250MB footprint):** explicit `.gitignore` entry for `cabinet/scripts/visual-uat/node_modules/`.
- **CTO #5 (state-file schema migration):** new substrate `cabinet/scripts/migrate-active-task.sh` upgrades partial state files on first /self-review.
- **CTO #6 (Vercel preview race at Gate 4):** first-iteration INDETERMINATE on missing preview (not FAIL); existing /ship-pr Phase 4 polling reused only AFTER first-iteration triggered preview.
- **CTO #8 (.cabinet/agent-instructions.md vs CLAUDE.md boundary):** explicit boundary doc — agent-instructions.md = AGENT-EXECUTION rules + cost caps + visual-UAT defaults; CLAUDE.md = OFFICER session-start context. No duplication.
- **CTO #10 (FW-095 backlog filing):** added to v2 land step.
- **POLISH P1-P3:** Phasing reorder note + Gate 1/2 iterative-loop language cleanup + A7 fan-out review note inline.

---

## Problem

Today's `/self-review` skill ships with a 10-point checklist (Types/Security/Snapshots/GDPR/OptimisticUpdates/UI/i18n/Tests/Docs/Database) executed by a spawned `self-reviewer` subagent against the diff. The skill is robust on code-level concerns but has three gaps surfaced by the 3-brief seed:

1. **No visual-UAT gate.** Officer reads diff + tests pass, but no automated check that the rendered UI *actually looks right* after the change. CRO competitor brief: none of Cursor/Devin/Copilot/Aider ship this in May 2026 either — Cabinet-novel slot, differentiated bet.
2. **No per-task token+step ceiling.** Cursor's failure mode (unbounded agent loops on unsolvable problems) is unguarded today; an officer's review loop can run indefinitely if a subagent hallucinates persistent issues.
3. **Atomic-commit + conventional-commit discipline informal.** `/ship-pr` Phase 2 "Stage and commit (if uncommitted changes exist)" is too loose — agents bundle unrelated changes or skip semantic commit messages.

CRO competitor brief Recommendation #4 (officer-in-loop on architecture) is currently implicit; spec needs to make it explicit in rationale so future agent-platform evaluations don't drift toward Devin-style full-autonomy planning.

CoS screenpipe/OCR brief decision ask #2 pivots visual-UAT implementation from naive screenshot+vision to **Stagehand v3 (DOM+CDP+action-cache) primary + Claude Opus 4.7 vision fallback**. Stagehand v3 production-grade architecture (85.8% WebVoyager publication number per Browserbase launch; ~$0 replay via action-cache; cold-run target measured empirically in CTO Phase 3), Cabinet's Next.js dashboard already provides the Node.js stack.

## Solution

Extend the existing `/self-review` workflow with a **4-gate composition**, layer atomic-commit + conventional-commit discipline into `/ship-pr`, add per-task token+step ceiling tracking, and introduce per-project `.cabinet/agent-instructions.md` (Copilot pattern). Anti-Devin rationale: officer-in-loop on architecture preserved as constitutional posture.

### 4-Gate self-review composition

| Gate | Purpose | Implementation | Failure mode → action |
|---|---|---|---|
| **Gate 1: Tests** | tests pass | existing `/ship-pr` Phase 1 #3 `pnpm test` + #4 `pnpm playwright test` | FAIL → block `/ship-pr`, fix tests, re-run /self-review |
| **Gate 2: Security-scan** | dependency CVEs + secret-leak + injection scan | new tool: `pnpm audit --audit-level=high` + `gitleaks` (or equivalent) run inline | FAIL → block, fix or accept-known-risk via explicit comment |
| **Gate 3: Agent-self-diff-critique** | existing 10-point self-reviewer subagent on diff | existing `/self-review` SKILL.md workflow (no change) | FAIL → loop fix→re-review per existing iterative skill (no hard cap) |
| **Gate 4: Visual-UAT via Stagehand v3** | render-verify changed pages produce correct visual + interaction state | new substrate: `cabinet/scripts/visual-uat/stagehand-runner.sh` invokes Stagehand v3 against Vercel preview URL with page-list resolved from spec metadata + Claude Opus 4.7 vision fallback for DOM-blind elements | FAIL → block; mismatch surfaces as diff with annotated screenshots; officer reviews + fixes or accepts-with-rationale via explicit comment |

All 4 gates must PASS before `selfReviewPassed: true` flag is set in `.claude/active-task.json`. Existing iterative loop (fix→re-review until clean, no hard cap) applies across all 4 gates.

### Stagehand v3 visual-UAT pipeline

```
/self-review Gate 4 invocation
  ↓
1. Resolve page-list from spec metadata
   (spec frontmatter: visual-uat: pages: [/dashboard, /tasks, /signal/abc, ...])
2. Wait for Vercel preview URL ready (existing /ship-pr Phase 4 polling reused)
3. For each page:
   a. Stagehand v3 navigates with CDP + cached action set
   b. Captures DOM snapshot + viewport screenshot
   c. Compares against last known good (action-cache hit) OR runs vision-fallback
      via Claude Opus 4.7 (DOM-blind elements: canvas, custom widgets, images)
   d. Emits findings: visual-diff regions, interaction-state mismatches, accessibility issues
4. Roll up per-page findings → BLOCKER/IMPROVEMENT/POLISH triage (reuse /ship-pr Phase 6 rules)
5. Output to officer for fix-or-accept decision
```

**Action-cache discipline:** first run on a page = expensive ($0.005-0.015); subsequent runs replay cached actions (~$0). Cache invalidates on page-route or component-tree structural change.

**Cost cap per task + audit trail (resolves CRO F7 + F8 + F10):** $5/task default (configurable in `.cabinet/agent-instructions.md`; per A1 reversibility, default-value is a config-edit reversal, NOT a Captain-gate).

- **Cap hit:** Gate 4 blocks with cost-detail surface; officer bumps cap one-shot OR splits task; no Captain ratification required.
- **Cap-bump audit (F7):** every bump appended to `cabinet/logs/visual-uat-cost.jsonl` with ts/task-id/officer/from/to/reason. **Bumps >2× default ($10)** ALSO append to `shared/interfaces/captain-decisions.md` with auto-classify `cap-bump-material` for retro analysis. Stealth-bypass surface closed.
- **USD computation (F10):** per-model-pricing table at `cabinet/scripts/lib/model-pricing.json` (committed, dated, version-pinned). On first /self-review run, validate against Anthropic's current pricing endpoint (or public pricing-page scrape if no API); mismatch → WARN officer + emit `MODEL_PRICING_DRIFT` event. Prevents cache-TTL-regression-class silent breakage (per memory `reference_cache_ttl_regression`).
- **Vision-fallback budget (F8):** SEPARATE from per-task cost cap. Per-page retry cap (default 3) prevents infinite fallback loops; cumulative per-task vision-fallback budget ($1 default) prevents single-page hot-spot from burning total cap. Both configurable in agent-instructions.md.

**Atomic-commit override audit (resolves CRO F9):** Officer override of file-group split stored in `.claude/active-task.json → atomic_commit_override` (ephemeral). ALSO: rationale copied to PR description on push + appended to `cabinet/logs/atomic-commit-overrides.jsonl` for retro analysis. Audit signal survives post-merge state-file deletion.

**Self-review iteration scope (resolves CRO F23):** `.claude/active-task.json → selfReviewIterationCount` increments on each /self-review invocation per task (NOT per Gate-N iteration within a single /self-review run). Gate 4's "first-iteration INDETERMINATE" applies ONLY when `selfReviewIterationCount == 1`; subsequent invocations FAIL on missing Vercel preview after existing polling exhausts.

### Build-vs-Buy on Stagehand v3 (per A3 anchor)

Per Captain anchor A3 ("build-our-own > add-dependency unless real complex"), explicit build-vs-buy:

| Option | Effort to ship Gate 4 | Production quality | Cost shape | Verdict |
|---|---|---|---|---|
| **(A) Stagehand v3 (BUY)** | ~1 day | 85.8% WebVoyager (publication number per Browserbase launch; 89.1% is marketing-deck cite — use conservative per CRO F1) | $0.005-0.015/page cold, $0 replay | **Chosen** |
| **(B) Playwright-native + Claude vision (BUILD)** | ~3-5 days | DOM-only diff, no action-cache, no vision smarts | $0.01-0.05/page (all-vision) | A3 build-route exists but adds 2-4 days for inferior result |
| **(C) Pure screenshot + Claude vision (NAIVE)** | ~1 day | 78% OSWorld, no DOM signal, 2-5s/action latency | $0.01-0.03/page | Functional but production-grade-inferior |

Stagehand v3 chosen because Option B's "build" path duplicates Stagehand's core innovation (CDP+action-cache+DOM-vision hybrid) for ~3-5x more effort and worse production characteristics. Stagehand is MIT-licensed (vendor-independent), npm-installable (no SaaS lock-in), Cabinet's Next.js dashboard already provides Node.js ≥20. Genuine "real complex" carve-out per A3.

### Stagehand v3 substrate selection (resolves CRO F2/F3/F4)

Stagehand v3 ships in two execution modes:
- **(I) Local CDP-on-Puppeteer/Playwright** — runs Chromium binary in officer container; Cabinet-pays-no-additional-SaaS-fee path; constraint: per-officer Chromium profile dir + concurrent-run cap (F4 concurrency model below)
- **(II) Browserbase cloud session pool** — Browserbase-hosted Chromium; captcha-solving, Agent Identity, session-replay features cloud-only; pay-per-session; future option

**v3 picks (I) Local for Phase 2-7 ship; (II) Browserbase listed as future option in Out-of-scope.** Rationale: Cabinet's officers already run containerized; adding Browserbase introduces SaaS dependency per A3 ("unless real complex stuff"). Captcha-solving + session replay are not required for `/self-review` Gate 4 (preview deploys behind preview-auth, not captcha). Future spec can promote (II) if captcha-bound projects (e.g., politiske-annoncer regulator portals) need it.

**Concurrency model (F4):** Cabinet's 5-officer pool means up to 5 simultaneous Gate-4 invocations. Mitigations:
- Per-officer Chromium profile dir at `cabinet/scripts/visual-uat/chromium-profiles/<officer>/` (no cross-officer state interference)
- Per-task screenshot namespace at `cabinet/logs/visual-uat-screenshots/<task-id>/` (no naming collisions)
- Concurrent-run cap default 2 (configurable in `agent-instructions.md → agent_caps.visual_uat_concurrent`); cap-hit serializes via redis lock `cabinet:visual-uat:lock` (BLPOP wait)

**Cold-run latency target (F3 — published source not authoritative for "500ms"):** Stagehand v3 published numbers (Browserbase blog) cite "44.11% faster on iframes/shadow-root" + "2x faster on cached replays" — no absolute cold-run number. **Use empirical target:** cold-run <5s/page (covers Stagehand init + first navigation + DOM snapshot + Claude vision-fallback if triggered); replay <1s/page (action-cache hit). CTO substrate Phase 3 measures actual numbers on test project + ships SLA AC against measured baseline.

**Action-cache invalidation mechanism (F5):** detection signal needs concrete computation. **v3 picks:**
- Hash basis: SHA256 of (Next.js `.next/build-manifest.json` + `app/` subtree mtime + `pages/` subtree mtime if present + `components/` subtree mtime)
- Invalidate cache when hash differs from cached value
- Computed cheaply on every Gate 4 invocation (file mtime check + manifest read; <100ms)
- Configurable hash-basis paths in `agent-instructions.md → visual_uat.cache_invalidation_paths` (project may add `lib/`, `styles/`, etc.)
- Without concrete mechanism, cache poisoning is realistic — Gate 4 false-PASS on stale cache

### /ship-pr discipline extensions

Two extensions layer onto existing `/ship-pr` Phase 2:

1. **Atomic-commit discipline** (Aider pattern): before `git commit`, agent groups changed files by **file-group** (defined: top-level directory subtree at depth ≤2 — e.g., `apps/mobile/lib/foo` and `apps/mobile/lib/bar` are SAME group; `apps/mobile/lib/foo` and `apps/web/components/bar` are DIFFERENT groups; configurable depth in `.cabinet/agent-instructions.md`). If diff spans ≥3 different file-groups, agent splits into multiple commits within the same branch — never bundles unrelated changes. Officer can override the split with explicit rationale.
2. **Conventional-commit messages**: agent generates commit message per Conventional Commits spec (`type(scope): subject` format; types: feat / fix / refactor / docs / test / chore / perf / style). Existing /ship-pr Phase 3 PR template stays unchanged.

### Per-task token+step ceiling

New substrate: per-task counter tracked in `.claude/active-task.json`:

```json
{
  "agentSteps": 0,
  "agentTokensTotal": 0,
  "agentStepCap": 200,
  "agentTokenCap": 10000000
}
```

Defaults configurable per project in `.cabinet/agent-instructions.md`.

**Cap event-chain priority (resolves CoS ARCH-2):** consolidated structured events, NOT separate-per-cap events.
- **At ≥80% of any cap (warning):** agent emits single `CAP_APPROACH` event with structured payload listing ALL triggered caps and their percentages (e.g., `{caps: [{name: "agentTokenCap", pct: 84}, {name: "visualUatCost", pct: 81}]}`). Officer prompted to extend, downscope, or abandon.
- **At 100% of any cap (block):** agent emits single `CAP_HIT` event with same payload structure. Priority ordering for which cap-hit triggers block first: **cost-cap > token-cap > step-cap** (cost is irreversible spend; tokens and steps recoverable via session restart). `/self-review` and `/ship-pr` block until officer explicitly bumps the highest-priority hit cap (one-shot decision per task) OR splits task.

This prevents duplicate event spam when multiple caps cross thresholds in the same iteration AND clarifies which cap drives the block under simultaneous-hit scenarios.

**Gate 3 ⨯ token-cap composition (resolves self-review B3):** Gate 3 iterative loop is unbounded by spec ("no hard cap on review iterations"), but token-cap is a hard-stop. Behavior when token-cap hits mid-Gate-3-loop:
- **Cap reached at ≥80%:** Gate 3 subagent receives WARNING in next iteration prompt, finishes current iteration's findings + emits partial-result with `gate3.complete: false` + `gate3.coverage: <%>`
- **Cap reached at 100%:** Gate 3 BLOCKS with partial findings preserved; officer decides (a) bump cap one-shot + resume Gate 3, (b) finalize triage on partial coverage + ship if no BLOCKERs in scanned set, (c) split task + ship the scanned portion
- **Partial Gate 3 PASS condition:** if `coverage ≥80%` AND zero BLOCKERs in scanned set, officer can mark Gate 3 PASS with `coverage` flag preserved in state file for audit trail

### .cabinet/agent-instructions.md per project (Copilot pattern)

New per-project file at `<project-root>/.cabinet/agent-instructions.md`. **Schema skeleton** (YAML frontmatter):

```yaml
---
schema_version: 2  # v3 fold extended schema
conventions:
  package_manager: pnpm                  # or npm | yarn | bun
  node_version: ">=20"
  commit_format_enforce: true            # toggle pre-tool-use Layer-2 hook
  commit_scope_charset: "[a-z0-9_-]+"   # F19: underscore-allowed for step_network / politiske_annoncer
code_style:
  rules:
    - "no React class components"
    - "no Promise.all without rejection handling"
secret_handling:
  storage: ".env.local"
  scan_allowlist: ".gitleaks.toml"       # F13: config-allowlist for known-FPs (regex + path patterns)
  scan_baseline: ".gitleaks-baseline.json"  # F13: delta-scan baseline (skip findings present at last clean scan)
  history_scan_mode: "first-adoption-full-then-delta"  # F12: full sweep on first /self-review per repo, delta on subsequent
agent_caps:
  visual_uat_cost_per_task_usd: 5
  visual_uat_cost_bump_audit_threshold_usd: 10  # F7: bumps >2× default also append captain-decisions
  visual_uat_concurrent: 2                # F4: per-cabinet concurrency cap (redis-locked)
  visual_uat_vision_fallback_retry_per_page: 3  # F8: per-page vision-fallback retry cap
  visual_uat_vision_fallback_budget_per_task_usd: 1  # F8: cumulative vision-fallback budget separate from total
  agent_step_cap: 200
  agent_token_cap: 10000000
visual_uat:
  enabled: true            # set false for CLI-only / library-only projects
  default_pages: ["/", "/dashboard", "/tasks"]
  allowed_paths: ["/", "/dashboard", "/tasks/*", "/library/*"]  # F6: glob allowlist; pages outside reject with WARN
  cache_depth: 2           # atomic-commit file-group depth
  cache_invalidation_paths: ["app/", "pages/", "components/"]  # F5: subtrees feeding cache-hash basis
anti_patterns:
  - "never modify lib/legacy/* without explicit officer approval"
  - "never bypass /self-review with --no-verify"
---

# Agent Execution Notes (free-form below frontmatter)
<project-specific narrative for agents reading this file>
```

Per project. Read by `/self-review` Gate 3 subagent AND `/pickup-task` step 13 AND `/ship-pr` Phase 0 verification. If absent, agent runs framework defaults + emits one-time warning to officer.

**Boundary vs project CLAUDE.md (resolves CTO #8):**
- `CLAUDE.md` = **OFFICER session-start context** (project description, who-does-what, knowledge systems, key files). Read at session-load by officers. Human-targeted prose.
- `.cabinet/agent-instructions.md` = **AGENT-EXECUTION rules** (caps, file-groups, anti-patterns, schema-validated). Read at /self-review + /pickup-task + /ship-pr by automated tooling. Machine-targeted YAML + sparse prose.

No content duplication. If a project rule is BOTH officer-relevant AND agent-relevant, prose lives in CLAUDE.md (cite source-of-truth) + machine-readable representation lives in agent-instructions.md (with prose pointer).

### .claude/active-task.json lifecycle (resolves CTO #1)

State file at `<project-root>/.claude/active-task.json`. **Scope:** per-(officer, project) — each officer's pool window for a given project has its own state file (since pool model isolates officer contexts per Spec 034 v3 §2b.4). **Lifecycle:**

1. **Created by `/pickup-task` step 12** (per existing skill — unchanged by Spec 049). All Spec 049 new fields (`agentSteps`, `agentTokensTotal`, `agentStepCap`, `agentTokenCap`, `visualUatCost`) initialized to defaults from `.cabinet/agent-instructions.md` OR framework defaults.
2. **Updated by /self-review + /ship-pr workflow steps** (existing + new — agentSteps + token counters increment via post-tool-use hook; visualUatCost increments per Gate 4 page).
3. **Migration on first /self-review:** new substrate `cabinet/scripts/migrate-active-task.sh` upgrades pre-Spec-049 state files (partial schemas) to v2 schema on first /self-review invocation. Adds missing fields with defaults; existing fields preserved.
4. **Deleted by /ship-pr Phase 10** (post-merge cleanup — existing skill behavior, unchanged).
5. **Archive (optional):** if `agent_instructions.md` flag `archive_state_files: true`, deleted state file gets archived to `<project-root>/.claude/active-task-archive/<task-id>.json` for audit. Default OFF.

### Hook composition: pre-commit-conventional-commit (resolves CTO #2)

NEW Layer-2 gate on existing `pre-tool-use.sh` (NOT git-native, NOT husky). Install path:
- `cabinet/scripts/hooks/pre-tool-use-conventional-commit.sh` — new hook script
- Triggers ONLY on Bash tool calls matching `^git commit ` (or `-m`/`-F` variants)
- Parses commit-message argv, applies regex `^(feat|fix|refactor|docs|test|chore|perf|style)(\([a-z0-9-]+\))?: .+$`
- Non-conforming → exit non-zero with surfaced diff + suggested corrections; conforming → exit zero (allow Bash to proceed)
- Composes with existing pre-tool-use.sh Layer 1 (kill switch, spending limits) via standard hook-chain order — Layer 1 runs first, then Layer 2 only if Layer 1 passes
- Per-project enable: `agent_instructions.md → conventions.commit_format_enforce: true|false` (default true)
- Anti-FW-042 discipline: warn-mode default + FP-rate JSONL at `cabinet/logs/hook-fires/conventional-commit.jsonl` + env-var disable `CONVENTIONAL_COMMIT_ENABLED=0`

### A11 artifact-vs-log classification (resolves CoS ARCH-5)

Spec 049 introduces several `cabinet/logs/*` JSONL files (visual-uat-cost.jsonl, atomic-commit-overrides.jsonl, visual-uat-fallback.jsonl, hook-fires/conventional-commit.jsonl). **These are ephemeral operational logs, A11-orthogonal — NOT canonical artifacts under A11.**

| Canonical (A11) | Ephemeral (operational logs) |
|---|---|
| Library Specs Space (spec artifacts, decisions, playbooks) | `cabinet/logs/*.jsonl` (cost trails, hook FP-rate, override audit) |
| `shared/interfaces/captain-decisions.md` (decision trail) | `cabinet/logs/hook-fires/*.jsonl` (transient debugging signal) |
| `/tasks` (officer_tasks Postgres — authoritative backlog) | `cabinet/logs/visual-uat-screenshots/<task-id>/` (per-task images, retained via retention policy) |
| `shared/cabinet-framework-backlog.md` (FW-tickets — Spec 050 candidate to migrate to /tasks) | |

Logs feed audit + retro + cost analysis. Canonical surfaces feed cabinet-wide trust + cross-officer reference. When in doubt: canonical = "another officer or future-Captain needs this to make a decision"; log = "trace data for debugging or compliance, derivable from canonical sources."

### Anti-Devin rationale (constitutional posture)

Spec rationale section explicitly rejects Devin-style full-autonomy planning per CRO competitor brief Recommendation #4 + Captain msg 2540 ratification. **Officer-in-loop on architecture preserved:**
- Officers make architectural calls (which approach, which abstraction, which dependency to add)
- Agents execute well-defined slices (implement function X with spec Y, apply diff to file Z)
- `/self-review` Gate 3 agent-self-diff-critique surfaces architectural concerns but never overrides officer judgment
- `/ship-pr` Phase 6 review-triage stays as-is (BLOCKER/IMPROVEMENT/POLISH tiers preserved)

Rationale-anchor pointer (resolves CRO F15 — stronger than literal grep): `<project>/.claude/skills/self-review/SKILL.md` Step 0 reading list references this section's URL in the Library Specs Space AND `shared/interfaces/captain-patterns.md` A12 (proposed via CoS per CRO F16 going-forward). Future agent-platform evaluations check A12 in captain-patterns + this section, not a literal string match. AC12 below is updated accordingly.

---

## Gate-4 joint-failure determinism (MF fold — the gate-critical surface)

The three Gate-4 failure modes — **preview-unavailable, cache-poison/invalidation, cost-cap-hit** — are NOT independent. They form a **causal cascade**: preview-down recovery (AC #4) triggers a new preview deploy → a new build → (under the pre-fold hash) cache invalidated by construction → forced cold-runs → cold-runs are the only real Gate-4 cost driver → cost-cap hits mid-iteration → its checkpoint-resume is corrupted because the build changed underneath it. Failure #1's recovery *causes* #2 which *causes* #3 whose recovery is broken by #1. The spec's `## Edge cases` lists each in isolation, each assuming the other two are healthy; this section defines the **joint state** deterministically.

**JF-1 — Break the cascade at its root (MF-2):** the `nextjs` cache-hash (AC #14) drops `.next/build-manifest.json` and relies on **source-subtree mtime + lockfile hash** (the `git-deps` reasoning CRO v3.0.1 established as sufficient + replay-preserving, now applied to `nextjs` mode). A deploy that changes only the build manifest but no source no longer invalidates the cache → the action-cache amortizes across iterations as intended → no recovery livelock. This is the single highest-leverage fold.

**JF-2 — Build-atomic Gate-4 runs + build-hash binding (MF-1, MF-4, M5):**
- A Gate-4 run attests to **exactly one build**. Compute the AC #14 hash at loop start, store as `gate4BuildHash`; re-check at loop end (<100ms). If it changed mid-loop, the run spanned two builds → **discard + re-run the whole gate** (never roll up a split-build result); cost spent counts toward the cap.
- The cost-cap checkpoint stores `checkpointBuildHash`. On resume: if `checkpointBuildHash == current hash`, resume from checkpoint (safe); else **discard checkpoint + mandatory full re-run** (cached pages are stale against the new build), surfacing "preview changed since checkpoint; pages 1–N must re-run; $X already spent" to the officer. Kills the stale-checkpoint false-PASS AND the re-run livelock.
- `selfReviewPassed: true` is bound to `selfReviewPassedSha = git rev-parse HEAD` at pass time; `/ship-pr` Phase 0 BLOCKs unless `selfReviewPassedSha == current HEAD` (no commits since review) — closes the stale-true + add-commit-after-pass gaming holes (same discipline as the Layer-1 reviewed-key→artifact binding).

**JF-3 — Terminal-state precedence when outcomes co-fire (MF-3):** when a single Gate-4 run produces more than one of {real visual FAIL, cost-cap BLOCK, preview INDETERMINATE}, the rolled-up state follows **FAIL > BLOCK > INDETERMINATE** (a confirmed defect is the most decision-relevant signal and must never be masked). If *any* page produced a real BLOCKER-tier visual finding, Gate 4 rolls up to FAIL regardless of co-occurring cap/preview state, and **the override-and-ship path is disabled** (so a preview-INDETERMINATE override can never bury a real FAIL). Cap/preview issues surface as secondary annotations. (Extends ARCH-2's cap-vs-cap ordering to gate-outcome-vs-cap-outcome.)

**JF-4 — No mutex held across a blocking wait (MF-5):** the `cabinet:visual-uat` concurrency permit (AC #13) protects only **active Chromium/CDP work**. It is RELEASED during the AC #4 preview-availability poll AND during the cost-cap officer-decision wait (both unbounded/human-latency), and re-acquired on resume. This defuses the pool-wide starvation where two officers caught in the triple-failure hold permits for minutes (preview-poll + human-decision inside the lock) and starve the other three. Pairs with the M2 crash-safe semaphore (a holder that dies mid-decision must not leak the permit).

**Joint-state determinism test (Phase 7):** a single scenario co-firing all three failures asserts: terminal state == FAIL when a real visual defect is present (override path closed); checkpoint discarded when `checkpointBuildHash` differs; permit released during the preview-poll + decision waits; cumulative per-task cost persists across `selfReviewIterationCount` increments (livelock visible as monotonic climb, not per-iteration reset).

---

## Acceptance criteria

1. **Gate 1 (tests) AC** — `/self-review` skill explicitly enumerates `pnpm test` + `pnpm playwright test` as Gate 1; existing /ship-pr Phase 1 reused; both must pass before Gate 2 fires. Failure: block + surface failing test names + line numbers.

2. **Gate 2 (security-scan) AC** (resolves CRO F11/F12/F13) — `/self-review` skill invokes:
   - `pnpm audit --audit-level=high` (working-tree dependency CVE scan)
   - `gitleaks detect --source . --no-git --config=.gitleaks.toml` (working-tree secret scan; speed-optimized; `.gitleaks.toml` is the **config-allowlist** for known FPs — regex + path patterns. F13 disambiguation)
   - `trufflehog git file://. --only-verified` (history secret scan with verified-mode; <2% FP per 2026 benchmarks vs gitleaks 5-15% untuned). Scope per `agent_caps.history_scan_mode`:
     - `first-adoption-full-then-delta` (default): full history sweep ONCE per repo (recorded in `.cabinet/scan-state.json`), then delta from last-scan-HEAD on each subsequent invocation (F12 — replaces arbitrary HEAD~100 cap)
     - `delta-only`: only delta (assumes prior full sweep; cheaper)
     - `full-always`: every run scans full history (paranoid mode)
   `.gitleaks-baseline.json` (separate from `.gitleaks.toml`) is **delta-scan baseline** — JSON output of prior clean scan; only relevant if gitleaks invoked with `--baseline-path` flag for delta-mode (F13 disambiguation).
   HIGH+ severity vulnerability OR any verified secret leak → FAIL. Output: vulnerability list + remediation suggestions OR secret-line numbers (redacted).

3. **Gate 3 (agent-self-diff-critique) AC (+ C4 ast-grep + M6 coverage)** — existing 10-point self-reviewer subagent runs unchanged; ship-readiness triage (BLOCKER/IMPROVEMENT/POLISH) preserved. Subagent reads `.cabinet/agent-instructions.md` and surfaces violations of `anti_patterns`, `code_style.rules`, `secret_handling.storage`. **ast-grep structural enforcement (C4 — collapsed from v3.2, Captain-ratified msg 2547/2550):** `anti_patterns[]` entries are EITHER a plain string (text-grep, existing) OR `{ast_grep: <rule.yaml>}`; for ast-grep entries the Gate-3 runner invokes `ast-grep scan` against the rule set and surfaces structural matches as BLOCKER findings (AST-aware, eliminates text-grep false-positives). `ast-grep` binary added to `bootstrap-host.sh` PATH; absent → WARN + text-grep fallback (never FAIL on missing optional binary). See also new AC #23. **Partial-PASS coverage (M6):** `coverage` = **% of changed HUNKS reviewed, computed by the orchestrator from the diff** (NOT self-reported by the capped subagent). PASS allowed at ≥80% coverage with zero BLOCKERs in scanned set, BUT: (a) the unscanned remainder is recorded as a tracked `/tasks` follow-up (with `context_slug` + the unscanned file list) reviewed before the NEXT ship; (b) partial-PASS is FORBIDDEN when the unscanned set contains files matching `anti_patterns` path globs or security-sensitive paths (auth, api, migrations) — those are fully scanned regardless of cap.

4. **Gate 4 (visual-UAT via Stagehand v3) AC** — new substrate `cabinet/scripts/visual-uat/stagehand-runner.sh` invokes Stagehand v3 against current branch's Vercel preview URL with page-list from spec frontmatter or `.cabinet/agent-instructions.md → visual_uat.default_pages`. Output: per-page pass/fail with annotated screenshots. **Two SLAs distinguished (resolves I3):**
   - **Stagehand execution SLA (M7 — made falsifiable):** a **HARD CEILING that fails the AC regardless of measurement** — cold-run ≤10s/page p95, replay ≤2s/page p95 (generous but non-vacuous). Phase 3 pins the *target* WITHIN that ceiling (expected replay <1s, cold <5s) and records the measured number in the AC. If the measured cold-run EXCEEDS the hard ceiling, that is a Phase-3 FAIL escalated to CPO/CTO for a scope decision (reduce default page-list, warm-profile reuse) — NOT a silently-widened SLA. (Keeps "measure-then-pin" honest: discovery within a fixed ceiling, not a vacuous floor.)
   - **Vercel preview availability gate:** SEPARATE timeout — first-iteration triggers preview deploy if not yet ready and returns INDETERMINATE (not FAIL) per CTO #6; subsequent iterations reuse existing /ship-pr Phase 4 polling (30s × 3 retries)

5. **All-4-gates-PASS condition AC (+ M5 diff-binding)** — `selfReviewPassed: true` set ONLY when all 4 gates PASS in the same iteration (Gate 3 partial-PASS per AC #3). **Bound to the reviewed tree (M5):** set `selfReviewPassedSha = git rev-parse HEAD` alongside the flag; `/ship-pr` Phase 0 BLOCKs unless `selfReviewPassedSha == current HEAD` (no commits landed since review — closes the stale-true + commit-after-pass holes, same discipline as the Layer-1 gate-key→artifact binding). Existing iterative loop (fix→re-review) applies on Gates 1/3/4; Gate 2 binary pass/fail (resolves POLISH P2).

6. **Atomic-commit discipline AC** — `/ship-pr` Phase 2 groups files by **file-group** (top-level directory subtree at depth ≤2; configurable via `.cabinet/agent-instructions.md → conventions.atomic_commit_group_depth` — **renamed from `visual_uat.cache_depth` per m4**: the commit-grouping depth is unrelated to visual-UAT/caching, and keying it under `visual_uat:` invited mis-wiring; `visual_uat.cache_*` is now cache-only). If `git diff main...HEAD` spans ≥3 distinct file-groups, agent splits into multiple commits within the branch before push. Officer override with rationale (logged to `.claude/active-task.json → atomic_commit_override`).

7. **Conventional-commit message AC** (CRO F19 + C3 hardening) — `/ship-pr` Phase 2 commit message matches `^(feat|fix|refactor|docs|test|chore|perf|style)(\([a-z0-9_-]+\))?: .+$`. NEW Layer-2 pre-tool-use hook `cabinet/scripts/hooks/pre-tool-use-conventional-commit.sh` enforces on `git commit` argv (NOT git-native, NOT husky — CTO #2). **C3 hardening (MUST, else it inherits the FW-029-family argv-parsing minefield):** (1) the hook REUSES the existing `pre-tool-use.sh` `git`/`gh` flag-tolerant anchor machinery (FW-041/043/045 reference impl — extract to a shared lib) rather than a fresh fragile regex; ≥2 adversary passes per the security-regex-authoring discipline. (2) `-F`/`--file` + `-c`/`-C`/`-C <path>` cases enumerated: parse the `-F` target's first line OR **fail-closed-with-warn** on message forms the hook can't extract (NEVER fail-open). (3) the hook (or a sibling) **explicitly blocks `--no-verify`/`-n` on `git commit`/`git push` argv** with a surfaced reason — else the agent-instructions "never bypass with --no-verify" anti_pattern is decorative (the Layer-2 hook is a PreToolUse argv intercept, so git-native --no-verify doesn't apply to it; it must detect the flag itself). (4) golden eval ships the FW-029-family bypass corpus (multiline `-m $'...'`, `-F`, `-c`, `bash -c`, `cd && git commit` chain, subshell/brace) as pos/neg cases, gated into Phase 7. Charset configurable via `agent-instructions.md → conventions.commit_scope_charset`.

8. **Per-task step+token ceiling AC (C1 — sources named, was unimplementable):** each cap names its writer + data source (FW-016 removed byte-count tracking, so there is no naive per-task token counter):
   - **`agentSteps`** ← the hook counts `cabinet:toolcalls:$OFFICER` (already exists); per-task delta from the `/pickup-task` snapshot baseline.
   - **`agentTokensTotal`** ← per-task DELTA of the cost-aware wrapper's Redis HSET `cabinet:cost:tokens:daily:<date>` field `<role>_cost_micro` (+ `_input`/`_output`), snapshotted at `/pickup-task` and diffed at each check. Officer-scoped ≈ task-scoped under the **Spec 034 §2b.4 one-task-per-officer-window invariant** (pinned here as the enabling assumption); if an officer multitasks, this over-counts conservatively (fails safe toward the cap).
   At ≥80% of either cap, emit `STEP_CAP_WARNING`; at 100%, `/self-review` + `/ship-pr` block with `TASK_STEP_CAP_EXCEEDED`; officer bumps or splits. **CTO confirms HSET field names + baseline-snapshot hook point at Phase 2a (the schema phase).**

9. **.cabinet/agent-instructions.md AC** — per-project file validates against YAML schema (skeleton in spec body). If absent, framework defaults + one-time warning. Validated fields: `schema_version`, `conventions.{package_manager,commit_scope_charset,atomic_commit_group_depth}`, `agent_caps.*`, `visual_uat.*`, `anti_patterns[]`. **schema_version handling (m1):** the validator checks `schema_version` and emits a one-shot WARN on a known-older version, listing which keys are being defaulted (a project pinned at v1 read by the v2 reader silently misses new keys otherwise); missing keys → framework-default (logged). Read by /self-review Gate 3, /pickup-task step 13, /ship-pr Phase 0.

10. **Stagehand v3 cost-cap AC (C1 source + M1 layering)** — `visualUatCost` is written by **`stagehand-runner.sh` reading its own Anthropic API `usage` object on each vision call × `model-pricing.json`** (the runner is a discrete process that controls exactly this spend — clean, testable, bounds AC #10 to Gate-4 spend). At per-task cap (default $5; configurable), Gate 4 blocks with cost-detail. Officer bumps one-shot — NOT Captain-gated (config-edit reversal per A1; resolves B1 + CTO #9). **Cost-cap layering (M1):** the $5 visual cap is a *sub-cap nested under* FW-002's per-officer/cabinet daily gate AND Spec 050's $50/day per-cabinet cap — visual-uat spend counts toward the cabinet daily cap (no double-exemption); a bump is rejected if it would cross the cabinet daily cap (defer to FW-002's override path, don't invent a parallel one). See the new INDETERMINATE-BUDGET edge case for a mid-Gate-4 FW-002 block.

11. **Vision-fallback trigger AC** — Stagehand v3 falls back to Claude Opus 4.7 vision ONLY when DOM-blind element detected (canvas, custom widget, image, opaque iframe). Triggers logged to `cabinet/logs/visual-uat-fallback.jsonl` for cost analysis + cache-tuning.

12. **Anti-Devin rationale AC** (CRO F15+F16 stronger anchor + CoS ARCH-1 graceful degradation) — `<project>/.claude/skills/self-review/SKILL.md` Step 0 reading list references BOTH: (a) this section's URL in the Library Specs Space, (b) `shared/interfaces/captain-patterns.md` A12 "Officer-in-loop on architecture; agents execute well-defined slices" (CoS encoding tonight as PROPOSED status; Captain ratifies in 07:00 briefing). **Test:** SKILL.md Step 0 contains a markdown link to the Library Specs URL AND a reference to `captain-patterns.md` A12. **Graceful degradation per ARCH-1:** if A12 file-section absent at test time (A12 not yet Captain-ratified), test emits `WARN: A12 reference present but section not yet ratified in captain-patterns.md` and continues; if Library Specs URL link absent, test FAILs. Decouples Spec 049 ship from CoS A12 ratification cycle.

13. **Gate 4 concurrency cap AC** (CRO F4 + ARCH-3 + M2 real-lock + MF-5 permit-release) — concurrent Gate-4 invocations capped at `agent_caps.visual_uat_concurrent` (default 2). **Real crash-safe semaphore (M2 — `BLPOP` is a queue primitive, not a mutex):** per-permit keys `cabinet:visual-uat:slot:{1,2}` via `SET key <owner> NX EX <ttl>` with TTL-based auto-release (crash-safe by construction — a holder that dies mid-run does not leak the permit). AC names acquire/release/expire explicitly. **Permit held ONLY during active Chromium/CDP work (MF-5):** RELEASED during the AC #4 preview-availability poll AND the cost-cap officer-decision wait (both unbounded/human-latency), re-acquired on resume — so a triple-failure holder cannot starve the pool for minutes. **Lock-wait timeout 180s** (m2 — raised from 60s to exceed the documented ~150s single-run hold, since per-page checkpointing + permit-release now bound the actual hold; configurable via `agent_caps.visual_uat_lock_timeout_s`); on timeout → `INDETERMINATE-CONCURRENCY-STARVATION` → (a) skip Gate 4 with logged-defer OR (b) defer-and-retry (officer call). Per-officer Chromium profile dir `cabinet/scripts/visual-uat/chromium-profiles/<officer>/`; per-task screenshot namespace `cabinet/logs/visual-uat-screenshots/<task-id>/`.

14. **Action-cache invalidation AC** (CRO F5 + F5b non-Next.js fallback) — cache hash basis configurable per project via `agent-instructions.md → visual_uat.cache_invalidation_source`:
    - **`nextjs` (default for Next.js projects, e.g., dashboard):** SHA256 of (lockfile hash + each path in `visual_uat.cache_invalidation_paths` subtree mtime). **`.next/build-manifest.json` is DELIBERATELY EXCLUDED (MF-2, highest-leverage fold):** a preview redeploy produces a byte-different manifest with no source change, which would invalidate the cache by construction and drive the recovery livelock (JF-1). Source-mtime + lockfile are precise to actual changes (CRO v3.0.1's `git-deps` reasoning, applied here to `nextjs` mode). Deploy-only churn no longer invalidates → action-cache amortizes across iterations as intended.
    - **`git-deps` (fallback for non-Next.js projects, e.g., stephie-mcp TypeScript pnpm monorepo, politiske-annoncer if non-Next.js sub-projects emerge):** SHA256 of (lockfile hash (pnpm-lock.yaml / package-lock.json / yarn.lock / Cargo.lock / poetry.lock per project) + each path in `visual_uat.cache_invalidation_paths` mtime). **NOTE per CRO v3.0.1 optimization observation:** `git rev-parse HEAD` deliberately excluded — both lockfile-hash and path-mtime signals are precise to actual changes; HEAD would invalidate cache on every commit even when caches are still valid, shrinking cross-commit replay window. Lockfile-hash catches dep changes, mtime catches code changes; combination is sufficient + preserves replay value.
    - **`custom` (per-project override):** project ships its own hash-computation script at `.cabinet/cache-hash.sh`; AC requires script exits 0 with deterministic hash on stdout
    
    Cache invalidates when computed hash differs from cached value. Mechanism computed in <100ms per Gate 4 invocation (typical); custom-script mode budget +200ms allowed. **Build-atomic guarantee (MF-4):** the hash is computed at loop START (stored as `gate4BuildHash`) AND re-checked at loop END; if it changed mid-loop the run spanned two builds → discard + re-run the whole gate (never roll up a split-build result), spent cost counts toward the cap. A Gate-4 PASS attests to exactly one `gate4BuildHash`, recorded in the state file alongside `selfReviewPassedSha`. CTO Phase 3 measures actual on Sensed (nextjs) + stephie-mcp (git-deps); AC includes regression check that switching cache_invalidation_source produces consistent cache-key namespacing (no cross-mode collision).

15. **Page-list allowlist enforcement AC** (CRO F6 + M3 origin-pinning + self-modifying-config gate) — Gate 4 page-list intersected with `visual_uat.allowed_paths` glob list before invocation; pages outside → reject + WARN. Default framework allowlist `["/", "/dashboard", "/tasks/*"]`; per-project widening via agent-instructions.md. **M3 hardening:** (1) matching is **path-only against the PINNED origin** = the resolved Vercel preview host — reject any entry resolving to a different host/scheme (`//host`, absolute URL, `..` traversal) with WARN+block (the allowlist globs paths, not origins → was an SSRF/exfil gap). (2) Any diff under review that **widens its own Gate-4 constraints** — `allowed_paths`, caps, `anti_patterns`, or `cache_invalidation_source: custom` pointing `.cabinet/cache-hash.sh` at a new script (arbitrary code exec on every Gate 4) — is flagged by Gate 3 as a **self-modifying-config change requiring explicit officer approval**. (3) Trust model: `agent-instructions.md` is trusted *as of the base branch*; Gate 3 diffs changes to it against base (a PR cannot silently relax its own review gates).

16. **Cost-cap bump audit AC** (CRO F7 + C2 fix) — every cost-cap bump appended to `cabinet/logs/visual-uat-cost.jsonl` with (ts, task-id, officer, from-usd, to-usd, reason). **NO automated write to `captain-decisions.md` (C2 — removed):** a machine append violates that file's WHY-required, human-curated, LEARNED-not-recorded contract AND triggers Spec 034 cross-cabinet pub-sub sync churn on every >$10 bump. Instead, bumps crossing `visual_uat_cost_bump_audit_threshold_usd` (default $10) emit a `CAP_BUMP_MATERIAL` event that the CoS surfaces in the next briefing's cost section (officer-authored, with WHY); if a durable decision record is genuinely warranted, the bumping officer writes a normal prose entry manually. The jsonl is the canonical audit trail (A11-log, ARCH-5). Resolves the latent ARCH-5 self-contradiction (cost trail classified as log, then routed to a canonical surface).

17. **Vision-fallback retry cap AC** (CRO F8) — per-page vision-fallback retry capped at `visual_uat_vision_fallback_retry_per_page` (default 3); cumulative per-task vision-fallback budget at `visual_uat_vision_fallback_budget_per_task_usd` (default $1, separate from per-task total cost cap). Both caps emit WARNING at 80%, BLOCK at 100% with officer-override path.

18. **USD cost-conversion AC** (CRO F10 + M4 phantom-endpoint fix) — per-model pricing table at `cabinet/scripts/lib/model-pricing.json` (committed, dated, version-pinned) is the **single source of truth** with a `pricing_as_of` date field. **No live validation** (M4 — Anthropic publishes no machine-readable pricing API; the "scrape" fallback was itself the drift it claimed to prevent: brittle HTML scrape on every session's first review → false `MODEL_PRICING_DRIFT` alarm fatigue). The only drift check is a **staleness assertion** — WARN if `pricing_as_of` older than N days (default 30), surfaced to CoS/retro for a manual refresh (same discipline as the tech-radar cache-TTL pattern). Optional opt-in scrape behind an off-by-default env flag, never on the hot path. AC is now testable (fixture JSON + staleness check; no phantom endpoint).

19. **Atomic-commit override audit AC** (CRO F9) — officer override of file-group split stored in `.claude/active-task.json → atomic_commit_override`; ALSO: rationale copied to PR description on push + appended to `cabinet/logs/atomic-commit-overrides.jsonl`. Survives post-merge state-file deletion.

20. **Self-review iteration scope AC** (CRO F23) — `.claude/active-task.json → selfReviewIterationCount` increments on each /self-review invocation per task (NOT per gate iteration). Gate 4 "first-iteration INDETERMINATE on missing preview" applies ONLY when `selfReviewIterationCount == 1`; subsequent invocations FAIL on missing preview after existing polling.

21. **Test harness AC** (CRO F20 + COO MF/C/M fold) — `cabinet/tests/test-spec-049.sh` covers 1:1 AC #1-23 PLUS: cap-bump audit-trail (now jsonl-only, NO captain-decisions write — C2 negative assertion); atomic-commit override jsonl; **the JF joint-failure determinism scenario** (all 3 failures co-fire → terminal==FAIL + override-path-closed + checkpoint-discard-on-build-change + permit-released-during-waits + cumulative-cost-persists); build-hash binding (`gate4BuildHash`/`checkpointBuildHash`/`selfReviewPassedSha` — ship-pr BLOCK when HEAD advanced); C3 conventional-commit bypass corpus (multiline/`-F`/`-c`/`bash -c`/chain/subshell + `--no-verify` block); semaphore crash-safe release (M2). **≥22 assertions total** (raised from ≥15). Each AC has a dedicated scenario.

22. **Gate-4 terminal-state precedence AC (MF-3 — formalizes JF-3)** — when a single Gate-4 run produces more than one of {real visual FAIL, cost-cap BLOCK, preview INDETERMINATE}, roll-up follows **FAIL > BLOCK > INDETERMINATE**. If any page produced a real BLOCKER-tier visual finding, Gate 4 == FAIL regardless of co-occurring cap/preview state, and the override-and-ship path is DISABLED (a preview-INDETERMINATE override can never bury a real FAIL). Cap/preview surface as secondary annotations. Test: all three co-fire with a real visual defect present → assert terminal==FAIL, override path closed.

23. **ast-grep Gate-3 structural-enforcement AC (C4 — collapsed from v3.2)** — `bootstrap-host.sh` adds `ast-grep` to PATH (single binary). `agent-instructions.md → anti_patterns[]` schema accepts BOTH plain strings (text-grep) AND `{ast_grep: <rule.yaml>}` objects. Gate-3 runner: for ast_grep entries, run `ast-grep scan --rule <rule.yaml>` over the diff and surface structural matches as BLOCKER findings; for string entries, existing text-grep. If `ast-grep` binary absent → one-time WARN + text-grep fallback (never FAIL on missing optional binary). Captain-ratified msg 2547/2550. Test: an ast_grep anti_pattern rule catches a structural match that the equivalent text-grep would false-positive or miss.

---

## Edge cases

- **Vercel preview URL not ready at Gate 4 time** — reuse existing `/ship-pr` Phase 4 polling (30s × 3 retries). If still missing, Gate 4 returns INDETERMINATE; officer can override-and-ship with rationale.
- **Project has no visual surface (CLI-only, library-only project)** — `.cabinet/agent-instructions.md` flag `visual-uat: skip: true` exempts Gate 4 entirely. Documented per-project.
- **Stagehand v3 dependency conflict in monorepo** — install at `/opt/stagehand-shared/` (one-time host-agent action per CRO F22) and mount into each officer container. No per-officer reinstall churn on image rebuild; no project-side package.json modification required.
- **Action-cache poisoning (false negative because cache is stale)** — cache invalidates per AC #14 (SHA256 of lockfile-hash + invalidation-paths mtime; `.next/build-manifest.json` EXCLUDED per MF-2 so deploy-only churn doesn't invalidate). Configurable source via `visual_uat.cache_invalidation_source`.
- **Cost cap hit mid-iteration (MF-1 checkpoint binding)** — partial Gate 4 results saved with `checkpointBuildHash`. On resume: if `checkpointBuildHash == current hash`, resume from checkpoint (safe); if it differs (preview redeployed since checkpoint), **discard the checkpoint + full re-run is mandatory** (cached pages are stale against the new build), surfacing "preview changed since checkpoint; pages 1–N must re-run; $X already spent" — closes the stale-checkpoint false-PASS AND the re-run livelock. Cumulative per-task cost persists across `selfReviewIterationCount` increments (a livelock is visible as monotonically-climbing cost, not a per-iteration reset).
- **FW-002 daily-cap block during Gate 4 (M1 INDETERMINATE-BUDGET)** — if the officer is near the FW-002 per-cabinet/officer daily spend cap, a Gate-4 vision call can be rejected mid-run by Layer-1 (surfaces as an API error, not a clean cap event). Gate 4 catches this and returns **INDETERMINATE-BUDGET** (not FAIL); the officer resolves the *cabinet daily cap* (FW-002 override path), not the per-task visual cap. Distinct from the $5 visual sub-cap BLOCK.
- **Token cap hit during Gate 3 subagent loop** — Gate 3 subagent emits partial findings + cap-warning event; officer decides to bump cap or finalize triage on partial data.
- **Multiple Vercel preview URLs (preview + production-promote)** — Gate 4 runs against preview by default; spec frontmatter `visual-uat: target: production` allows promote-cycle validation.
- **Secret-scan false positive (test fixtures, mock keys)** — known FPs go in `.gitleaks.toml` (config-allowlist with regex + path patterns; AC #2 disambiguation). `.gitleaks-baseline.json` is the SEPARATE delta-scan baseline (JSON output of prior clean scan; only relevant if delta-mode invoked with `--baseline-path`). Don't conflate the two.
- **Conventional-commit type ambiguity (refactor vs chore)** — agent surfaces both candidate types to officer; one-shot decision per commit.

---

## Dependencies

- **CTO substrate:** new script `cabinet/scripts/visual-uat/stagehand-runner.sh` + Node.js wrapper using Stagehand v3 npm package + Claude Opus 4.7 vision API client. Cabinet's Next.js dashboard already provides Node.js ≥20.
- **CTO substrate (tooling gap — resolves CTO #3):** officer image currently has Node 22 but no `pnpm`, no `gitleaks`. Recommended path (CTO Option (b)): pnpm invoked via `npx pnpm` (no Dockerfile change); gitleaks installed at officer boot via `cabinet/scripts/bootstrap-host.sh` PATH addition (single binary, ~10MB). Keeps officer image lean. Alternative paths (Dockerfile add vs npm fallback) documented in CTO impl plan.
- **CTO substrate:** new Layer-2 pre-tool-use hook `cabinet/scripts/hooks/pre-tool-use-conventional-commit.sh` enforcing commit message regex (NOT git-native, NOT husky — composes with existing pre-tool-use.sh per spec body).
- **CTO substrate:** atomic-commit detection logic in `/ship-pr` skill — file-group enumeration at depth ≤2 (configurable).
- **CTO substrate:** `.claude/active-task.json` schema extension (new fields: agentSteps, agentTokensTotal, agentStepCap, agentTokenCap, visualUatCost, atomic_commit_override). State-file validation update.
- **CTO substrate (state-file migration — resolves CTO #5):** new script `cabinet/scripts/migrate-active-task.sh` upgrades pre-Spec-049 state files (partial schemas) to v2 schema on first /self-review invocation. Adds missing fields with defaults; existing fields preserved. Idempotent.
- **CTO substrate (Stagehand v3 footprint — resolves CTO #4 + CRO F22):** install at `/opt/stagehand-shared/` via one-time host-agent action; bind-mount into each officer container at `/opt/stagehand/` (or equivalent). Prevents per-officer-container reinstall churn (~250MB × N officers on image rebuild = 1.25GB+ saved). Path added to `.gitignore` at repo root in case any officer-local artifact spills. No project-side `package.json` modification required. Per-officer Chromium profile dir at `cabinet/scripts/visual-uat/chromium-profiles/<officer>/` remains officer-local (small, profile state).
- **Per-project:** `.cabinet/agent-instructions.md` template ships with framework defaults. CPO writes template per stephie-mcp + politiske-annoncer + Sensed product on first adoption. Schema validated per AC #9.
- **CRO adversary review** at draft-time (per CRO offer 2026-05-18 21:11 UTC). v2 fold (CPO self-review + CTO tech review) → CRO adversary → v3 LANDED before CTO build starts on Phase 2.
- **FW-095 backlog filing (CTO #10):** new entry filed in `shared/cabinet-framework-backlog.md` once v2 lands. Owner: CTO build, CPO spec, CRO adversary, COO ratify.

Cost-cap default ($5/task) is a config-edit reversal per A1 — NOT Captain-gated (resolves B1 + CTO #9). Officer bumps cap one-shot at runtime when justified.

---

## Out of scope

- **Full computer-use agent loop** (Cursor/Devin-style autonomous "go fix the bug"). Defer until: (a) leaves beta, (b) PolAds e2e flow Playwright can't cover, (c) budget for $1-5/run nondeterministic runs is justified. Per CoS scoping brief Section 2.
- **Screenpipe integration.** Mac-side only, defers to post-Mac-Mini-arrival per CoS scoping brief Section 1.
- **OCR-based computer-use** (Apple Vision OCR, PaddleOCR). Stagehand v3 + Claude vision fallback is the production architecture per CoS frontier brief Section 2. Pure-OCR skipped.
- **Multi-provider routing** (Gemini 2.5 Computer Use, OpenAI Operator). Single-provider (Anthropic) for now.
- **Cookie-banner / consent flow automation.** Anthropic requires human-in-loop. Manual officer review preserved.
- **Visual regression CI gate** (pass/fail every commit on every PR). Non-determinism = false positives at scale. Stick with Percy/Chromatic for that surface; Gate 4 is agent-mediated, not CI-mediated.
- **SKILL.md spec compliance for cabinet skills** — separate framework spec (Move 2 from CoS frontier brief). Spec 050 candidate.
- **Sonnet+Opus model routing** — separate framework substrate change (Move 1 from CoS frontier brief). Captain ratified separately; CTO lane.
- **Anthropic Managed Agents Dreaming** — Captain rejected per msg 2540.

---

## Cost model

| Component | Per-PR cost (est.) | Notes |
|---|---|---|
| Gate 1 (tests) | $0 | Existing CI infrastructure |
| Gate 2 (security-scan) | $0 | pnpm audit + gitleaks local execution |
| Gate 3 (agent-self-diff-critique) | $0.10-0.50 | Existing subagent on Claude Sonnet 4.6 |
| Gate 4 (Stagehand v3 primary) | $0-0.05 | Cache-replay $0, cold-run $0.005-0.015/page × ~3-5 pages |
| Gate 4 (vision-fallback) | $0.01-0.10 | Only when DOM-blind elements detected; Claude Opus 4.7 vision |
| **Total per-PR** | **$0.10-0.70** | Well below $5 per-task cap; cap is safety not budget target |

At 100 PRs/month across all projects: $10-70/month. At 1000 validations/day across all officers + agents: ~$5-15/day per CoS frontier brief Section 2 estimate. Cost-cap discipline keeps spend bounded.

---

## Phasing

Phases marked with `║` can run in parallel after their dependency phase clears (resolves POLISH P1).

| Phase | Scope | Effort | Depends on | Gate |
|---|---|---|---|---|
| 1 | CRO + CoS adversary review parallel + CRO re-review + CoS architecture review → spec v3.0.2 fold | ~1h CRO + ~1h CoS + ~1h CPO consolidation | v2 LANDED | **v3.0.2 LANDED ✓** (2026-05-18 22:15 UTC) |
| 1b | COO adversary review → spec v3.1 fold (if findings) OR v3.0.2 ship-ready (if clean) | ~1h COO + ~0.5h CPO | v3.0.2 LANDED | **v3.1 LANDED before CTO build starts** — Phase 2a gated |
| 2a | Per-task step+token ceiling tracking + cap-hit blocking + state-file migration script + schema extension (formerly Phase 6 — resequenced per CRO F21 since Phase 5+2+3 modify `.claude/active-task.json` schema) | ~3-4h CTO | v3.1 LANDED | State-file schema validates; cap-hit triggers documented event chain |
| 2b ║ | Gate 1 + Gate 2 skill update + tooling-gap bootstrap (gitleaks PATH + trufflehog PATH + npx pnpm) | ~3-4h CTO | Phase 2a GREEN | Gate 1/2 PASS on existing project test fixtures |
| 3 ║ | Gate 4 substrate: `stagehand-runner.sh` + Node.js wrapper + vision-fallback + cost-cap + concurrency lock + cache-invalidation hash + page-list allowlist + Stagehand v3 isolated install at `/opt/stagehand-shared/` (CRO F22 host-mount; one-time host-agent action) | ~7-9h CTO | Phase 2a GREEN | One project's `/self-review` runs all 4 gates green |
| 4 ║ | `.cabinet/agent-instructions.md` template (framework) + per-project authoring (stephie-mcp + politiske-annoncer + Sensed) + schema validator + **/pickup-task SKILL.md edit per CoS ARCH-4** (Step 13 documentation: "read .cabinet/agent-instructions.md if present, inject conventions into agent context") | ~3-4h CPO + per-project officer consultation on conventions | Phase 2a GREEN | Per-project agent-instructions.md merged + officer roster acknowledges + /pickup-task SKILL.md updated in each project repo |
| 5 ║ | Atomic-commit + conventional-commit discipline in `/ship-pr` + new Layer-2 pre-tool-use hook + audit-trail JSONL append | ~3-4h CTO | Phase 2a GREEN | Hook installed + test cases passing |
| 7 | Test harness `cabinet/tests/test-spec-049.sh` (≥15 assertions per CRO F20) | ~3-4h CTO | Phases 2b, 3, 5 GREEN | All assertions passing on CI |
| 8 | End-to-end validation: run full /pickup-task → /self-review → /ship-pr cycle on a test PR with all 4 gates exercised | ~2-3h CTO + CPO observation | Phase 7 GREEN | Cycle green; CRO post-impl review folds into Spec v4 if findings |

**Total effort estimate:** ~24-32h CTO + ~5-6h CPO + ~2h CRO + ~1h CoS + ~1h COO. Critical path: v3 → v3.1 → Phase 2a (schema first per F21) → Phases 2b+3+4+5 in parallel → Phase 7 → Phase 8. 4 of 7 phases parallelize after schema lands.

**Going-forward (CRO F18 follow-up):** `shared/cabinet-framework-backlog.md` is a third backlog surface (neither A11-canonical Library/tasks nor CLAUDE.md-canonical GitHub Issues). Spec 050 candidate — migrate FW-* backlog into `/tasks` with `context_slug=cabinet-framework`. Not in Spec 049 scope; flagged for separate CPO spec.

---

## Review process

Per Captain bar "production-ready, no gaps, reviewed multiple times". Per A7 (decompose to officers), domain-independent reviews run in parallel where possible (resolves POLISH P3):

| Reviewer | Domain focus | Sequencing |
|---|---|---|
| **CPO self-spawned subagent** | Fresh-context audit, internal consistency, AC testability | Pre-v2 (DONE 2026-05-18, surfaced 4 BLOCKERs + 5 IMPROVEMENTs + 3 POLISH, all folded into v2) |
| **CTO tech review** | Stagehand v3 deps, hook composition, state-file migration, tooling gaps | Pre-v2 (DONE 2026-05-18 21:39, surfaced 8 substrate + 2 housekeeping findings, all folded into v2) |
| **CRO adversary** (offered 21:11 UTC) | Stagehand v3 production-reliability vs claimed numbers, cost-cap edge cases under adversarial input, security-scan tool selection (gitleaks vs alternatives), anti-Devin rationale-anchor sufficient for future evaluations | v2 → v3 fold (parallel with CoS review per A7) |
| **CoS architecture review** | Cross-officer workflow consistency, anti-Devin posture anchoring, /pickup-task→/self-review→/ship-pr loop integrity preserved | v2 → v3 fold (parallel with CRO per A7) |
| **COO adversary** | What breaks when Stagehand v3 cache poisoned + cost-cap hit mid-iteration + Vercel preview unavailable simultaneously? Multi-failure-mode interaction surface | v3 (post CRO+CoS fold, sequential since depends on resolved cross-officer surface) |

Iterate until all 5 reviewers ack. No Captain final-ack required (cost-cap default is reversible config edit per A1; no other irreversible call surfaces).

---

**v3.0.2 LANDED 2026-05-18 22:15 UTC** (CPO self-review + CTO tech review + CRO adversary + CRO re-review + CoS architecture review all folded in parallel/incremental versions: v2 → v3 → v3.0.1 → v3.0.2). COO adversary review next (final pre-build gate per Phasing table Phase 1b). v3.1 = post-COO-fold ship-ready version that unblocks CTO Phase 2a build.
