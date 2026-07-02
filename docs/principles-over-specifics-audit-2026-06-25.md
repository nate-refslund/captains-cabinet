# Principles-over-Specifics Audit — Proposal (2026-06-25)

Captain-requested cabinet-wide review: *think in principles, not specifics (except concrete memories)* — scalable, lean in context, tune one place when mis-worded. Three finders across the behavioral, governance, and execution layers. **Proposal only — nothing applied; Captain's call per item.**

## The meta-pattern (confirmed across all three layers)
The cabinet has accreted **one rule per feature / person / case**, each re-deriving a shared principle inline, growing and rotting. The fix is always the same shape: replace an enumeration-that-must-grow with a **principle / whitelist / single-source / data-table** that catches the unanticipated case. Proven this session by the charset normalizer (a "Danish keyboard + emojis" whitelist replaced a substitution list).

## The model to emulate
`framework/policies/authority-matrix.yml` already does it right: Captain authority as **risk-class × confidence-state DATA** with a hard-ceiling floor — rules expressed as a data table, not prose. Everything below moves toward that shape.

## Genuine BUGS (verified — defects regardless of the principle work; fix first)
1. **`shared/interfaces/captain-rules-index.yaml` is STALE.** Indexes 48 old-gen anchors (A1-A5, I-W-*, P-*); **zero** of the current 17 `captain-patterns.md` patterns. Officers query this index by trigger-words to pick which patterns apply → every pattern encoded this session (and the new principles) silently does NOT propagate. **Fix:** regenerate from current sources + repair the pre-commit freshness hook. *This is the propagation mechanism for the entire cleanup — do first.* Upside: the orphaned A*/I-W-* anchors are clean PRINCIPLES — likely the very layer the specifics should collapse into; review for reinstatement.
2. ~~**`cabinet/scripts/health-check.sh:14` hardcodes `OFFICERS=(cos cto cro cpo)`** — 3 phantom officers that don't exist in the portfolio preset, while never checking the live lane CEOs + comms-officer → a real officer death goes unalerted. `import-linear-to-library.sh:106` has the same `cos*|cto*|cpo*|cro*|coo*` hardcode.~~ **RESOLVED 2026-06-25.** Both scripts now DERIVE the roster, each from the canonical source reachable *in its own runtime context*:
   - **Canonical roster source resolved.** Two surfaces are kept in lockstep by the activation flow and are both accurate (unlike empty `instance/roles/active/` and the stale `instance/memory/tier2/*` dirs which still carry phantom `cto/cpo/cro/coo` + a junk `unknown/`):
     - `cabinet/mcp-scope.yml` `agents:` block = the documented *hired roster source of truth* (per `sync-agents.sh` / `load-preset.sh`), but it lists ALL deployments' agents (the functional five **and** the portfolio three) because the file is shared across the Mini's `work` preset and hq's `portfolio`.
     - `.claude/agents/*.md` = the **deployment-resolved** roster: `load-preset.sh`/`sync-agents.sh` render it as *(hired in mcp-scope.yml) ∩ (has a role-def in active-preset ∪ instance overlay)*, and `start-officer-mac.sh:226` gates each officer boot on it. On hq that resolves to exactly `cos, polads-ceo, stephie-ceo, comms-officer`. This is the canonical *active* roster.
     - In Redis, `load-preset.sh` writes `cabinet:officer:expected:<slug>=active` for that same resolved set — the only roster surface reachable cross-container.
   - **`health-check.sh`** runs in the Docker **watchdog** container, which ships the script standalone (`Dockerfile.watchdog`: `COPY scripts/health-check.sh /opt/watchdog/`) with **no repo tree** — so `.claude/agents/` is unreachable there. Fixed to enumerate `redis-cli KEYS cabinet:officer:expected:*` (the cross-container resolved roster), exactly as the 7th working script `officer-supervisor.sh:211` already does. Added an empty-roster guard so a silently-empty list (Redis down, or zero expected-active) ALERTS instead of falsely reading healthy.
   - **`import-linear-to-library.sh`** runs with the full repo tree, so it derives officer slugs from `.claude/agents/*.md` (the resolved roster) and matches the Linear assignee's first-name token against real slugs; the phantom `cos*|cto*|cpo*|cro*|coo*` prefix list is gone.
   - **Verified:** both derive `[cos, comms-officer, polads-ceo, stephie-ceo]`; health-check would now ping the live officers and *not* `cto/cpo/cro/coo`; the phantom `cto` no longer maps to a fake officer.

   **Full defect class swept (3 more scripts, RESOLVED 2026-06-25).** Same hardcoded-phantom-roster defect, each fixed to derive from the source canonical *in its own runtime context*:
   - **`cabinet/scripts/test-escalation.sh:136`** — was `for officer in cos cto cro cpo`. Runs in the watchdog container (no repo tree), so fixed to enumerate `redis-cli KEYS cabinet:officer:expected:*` like `health-check.sh`. Empty-keyset prints a no-officers notice (no phantom check).
   - **`cabinet/cron/cost-summary.sh:46`** — Mac-cron (repo tree). Kept `instance/roles/active/` as the primary path; replaced the `cos cto cpo cro coo` *fallback* with derivation from `.claude/agents/*.md` (no type filter — consultants spend tokens too). Final no-op guard logs + emits totals-only if both sources are empty; never invents phantoms.
   - **`cabinet/cron/heartbeat-watchdog.sh:90`** — Mac-cron fulltime-only restarter. Kept `instance/roles/active/` primary; replaced the `cos cto cpo coo` *fallback* with `.claude/agents/*.md` **∩ installed `com.cabinet.officer.<slug>.plist`**. The plist intersection is the belt-and-braces: `.claude/agents/*.md` carries no reliable `officer_type` (frontmatter omits it; lane-CEO bodies say "consultant" while their frontmatter says "fulltime"), and a restarter must never kickstart a slug with no agent — gating on the installed plist guarantees no phantom restart regardless of roster drift, and every officer with a persistent agent on this host is fulltime by construction.
   - **Verified (all 3, against live on-disk state):** each derives exactly `[cos, comms-officer, polads-ceo, stephie-ceo]`; `cto/cpo/cro/coo` absent from all; empty-roster guards fire safely. None of the three depends on `instance/roles/active/` being populated (test-escalation is Redis-only; the two cron scripts' fallbacks are proven with the dir empty).

   **⚠️ ROOT-CAUSE FLAG (NOT fixed here — Captain decision).** `instance/roles/active/` holds only `.gitkeep` (zero `*.yml`) on hq — the documented roster source that `bootstrap-roles.sh` seeds is **empty on this deployment**. That is *why* every `instance/roles/active/`-based path silently degraded to the phantom hardcoded fallback. The above fixes make the fallbacks robust (empty dir → derive the real roster, never phantoms), but the deeper fix is to actually seed it: `bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml` (note: `instance/config/roster.yml` does not exist yet either — `cabinet-init`/`generate-instance.py` would produce it). NOT done autonomously: seeding is a config decision with possible broader effects (it also drives `verify-launchagents.sh` consultant-skip, the mission compiler's `org_roles`, and `deploy-mac.sh`'s per-officer refusal gate) — surface to Nate.

## Collapses by layer (ranked by value)

### Behavioral patterns (`captain-patterns.md`: ~17 → ~12)
- **B-1 Kristoffer cluster → one principle.** `kristoffer-is-e2e-test-partner` + `close-the-loop-with-reporter-when-shipped` + `colleague-feedback-actions-first-then-reply` + the auto-ack = ONE `close-the-loop-with-work-givers` (ack → action-first → report-when-shipped → validate via willing colleagues). Kristoffer-as-test-partner becomes a people FACT, not 3 behaviors. ~25 lines → ~6 + 1 fact.
- **B-2 Merge `verify-before-surfacing` + `deep-dive-and-fix-before-escalating`** (the 2nd literally says it strengthens the 1st) → `verify-and-fix-before-escalating`; incident lists → evidence, not body.
- **B-3 `teams-message-voice-formatting`** → keep `nate-voice-charset` 1-liner + fast-path examples; MOVE the Implemented-block (fn names/test counts) OUT of the always-loaded behavioral file; split the hej-rule into `greeting-only-first-message-of-day`.
- **B-4 `monday-task-not-card` → `speak-each-systems-native-vocabulary`** + a glossary line (absorbs all future term corrections).
- **B-5 `dont-resurface-resolved-health-items` → `report-current-state-once-never-restale`** (any resolved item, not just pipe-health).

### Governance / CLAUDE.md (~511 → ~300 lines, ~40% of always-loaded context)
- **G-1 (top win) The 5 "loops" + 3 review-types = ONE principle written 4×** (~180 lines / 35% of CLAUDE.md) → one principle block ("improve via nested loops fastest-signal-first; review-by-risk") + pointers to the loop skills (already load on-trigger). Cuts ~150 lines. *This accretion is what keeps re-bloating CLAUDE.md — establishing "mechanics live in skills, CLAUDE.md carries principle + pointer" is the durable fix.*
- **G-2 §Communication duplicates `constitution-base.md`** (already drifting) → delete dup, 2-line pointer. ~40 lines.
- **G-3 "Three Knowledge Systems"** mixes durable principle with rotting dated state ("560 Linear rows as of 2026-04-26", "until cutover") → keep principle; dated state → instance/spec.
- **G-4 Hooks 9-item runbook** → "hooks enforce automatically, rely on them" + pointer to `cabinet/scripts/hooks/`. ~22 lines.
- **G-5 `courses-of-action.md` §1** hardcodes a comms-shaped 6-source list → the BAR is the principle; the source-inventory → per-lane config (scales across presets).
- **G-6 "Required Reading" 12-item manifest** (grows每loop) → layered-loading principle; the loader owns the manifest (also preset-agnostic).
- **G-7 Model Routing** buries the tiering principle under model IDs + dated lineage (3 swaps inline) → keep principle; IDs/lineage → config.
- **G-8 Captain-Decision-Trail + Linear-state + Founder-accountability** circle ONE principle (truth-in-tracking + log-with-why); founder-action steps enumerated 2× → merge.

### Execution / libs / configs
- **E-1 (top, charset's twin) `email_lib._HTML_ENTITIES` hand-map → `html.unescape`** (stdlib full HTML5 table). Today —/'/…/æøå survive as literal garbage in every parsed email → vault + classifiers. Kills the map + a dead regex + a bespoke numeric decoder. (Preserve nbsp→space.)
- **E-2 The charset normalizer is DUPLICATED** in `framework/acting/screenpipe_adapter.py` (~60 lines re-implement `draft_lib.normalize_charset`; the header admits it) → single source (import). The reframe's whole point was "the table never grows again" — two copies re-introduce the drift.
- **E-3 Fidelity magic numbers scattered in `context_lib.py`** (0.4 floor, per-file cap, 0.15/0.4 fusion, length gates) → hoist to a named policy block (the file already does this for SOURCE_AUTHORITY). Most-retuned file; latent `0.4` collision (floor vs min_score both 0.4).
- **E-4 (lower)** private-app hint set duplicated (sp_lib); urgency keyed off a hardcoded pipe-name allowlist → per-pipe `urgency_tier`; `_FWD_MARKERS` per-language regex → one alternation; "Nate" name special-case → `is_nate_name` oracle.

**LEAVE AS-IS (correctly specific / genuine safety):** safety-boundaries (keep strict), authority-matrix.yml (the model), brain-bridge (principle-shaped; tiny nit: "five officers" → "scoped per mcp-scope.yml"), and all genuine facts (NATE_EMAILS, Graph URL grammar, SECRET_PATTERNS, board/model IDs, RETRYABLE, stopwords). Watch trip-wire: NOISE_PATTERNS / BOT_PATTERNS are generic-category now — flip to a structural rule the moment a vendor name is added.

## Recommended sequence
1. **Fix the 2 bugs now** (stale index + roster hardcode) — defects regardless.
2. **G-1 loops-collapse + B-1 Kristoffer-cluster** — biggest context + clarity wins.
3. Work the rest in batches, Captain sign-off per item.
