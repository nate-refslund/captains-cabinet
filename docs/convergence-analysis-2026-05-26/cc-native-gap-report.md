# Claude Code-Native Gap Report

**Date:** 2026-05-26
**Branch reviewed:** `claude/convergence` @ `655537d`
**Method:** Two parallel deep-dive subagents — one audited the branch for CC-native usage, one cataloged the full CC feature surface (stable + beta + preview + experimental). Then synthesis.

---

## Executive verdict

The convergence branch is **51% CC-native** (23/45 dimensions, per the audit scorecard). Where it leans into the surface — hooks, rules, agent frontmatter, MCP servers, custom channel capability — it goes deep. Where it doesn't — distribution packaging, custom slash commands, the `skills:` frontmatter binding, native voice / sandbox / statusLine settings, two unwired compaction hooks — those are real gaps with concrete next-step fixes.

**Headline takeaway:** the framework is *CC-aware* but not *CC-distributed*. It's a sophisticated Cabinet built on Claude Code, but it doesn't yet present itself as a CC-native plugin that another founder could install in one step.

---

## What's working well (depth-3 integrations)

These five areas are exemplary uses of CC's native surface:

### 1. Hooks (16 wired across 5 event types)
- **PreToolUse**: 944-line `pre-tool-use.sh` is essentially a mini policy engine — kill switch + spending limits + typed `policy_engine.py` invocation + Layer 1 gate. 15+ `exit 2` block paths.
- **PostToolUse with matchers**: `(any)`, `(Bash)`, `(Write|Edit)`, `(Agent)`, `(mcp__plugin_telegram_telegram__reply)` — precise routing.
- **UserPromptSubmit (×3)**: `pre-captain-dm.sh` (5th-loop retrieval), `captain-rule-encoder.sh` (4th-loop encoder with Phase 3 two-count rule), `session-task-inject.sh` (mission task injection via Phase 1.1 session bridge).
- **`hookSpecificOutput.additionalContext`** used in 9+ hooks to inject CC context.

### 2. Agent frontmatter (5 officers, full spec)
Every `.claude/agents/<slug>.md` has `model` + `effort` + `allowedTools` + `description`. The model tiering is intentional: Opus 4.7 max for orchestrators (CoS/CTO/CPO), Sonnet 4.6 high for validators (COO/CRO). Tool allowlists differentiate write-capable from read-only.

### 3. Path-scoped rules (5 files, glob-precise)
`framework.md`, `hooks.md`, `missions.md`, `policies.md`, `roles.md` — each with precise globs (`framework/**/*.py`, `cabinet/scripts/hooks/*.sh`, etc.) and substantive invariants (event-first, no instance imports, DAG validation, YAML+Python over bash regex, append-only lineage).

### 4. MCP — including custom `claude/channel` capability
6 servers configured. `redis-trigger-channel` is a **custom TypeScript MCP server** using the experimental `claude/channel` capability — push delivery of inter-officer triggers from Redis Streams. Most Cabinets don't get this far. `library-mcp` exposes Cabinet Library CRUD.

### 5. Agent Teams + Subagent patterns
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` set. CTO/CRO/COO agent files explicitly document `Agent({...})` and `TeamCreate` patterns with model routing (subagents → Sonnet). `post-subagent.sh` bridges subagent completions to the event ledger via task-ref regex matching.

---

## Gaps — High priority (structural, ~hours of work each)

### G1. ❌ `PreCompact` is missing from `settings.json`
`cabinet/scripts/hooks/pre-compact.sh` and `post-compact.sh` exist and are substantive (state snapshot, re-injection), but they aren't wired in `.claude/settings.json::hooks`. The compaction safety net is broken.

**Fix:** add `PreCompact` and `PostCompact` entries pointing at the existing scripts. ~5 minutes.

### G2. ❌ Foundation skills not exposed to CC
~20 foundation skills live at `memory/skills/*.md` (individual-reflection, cross-officer-retro, evolution-loop, telegram-communication, engineering-development-loop, spec-quality-gate, research-quality-gate, agent-team-workflow, holistic-thinking, production-quality-ownership, etc.). Only **3 are surfaced as `.claude/skills/<name>/SKILL.md`**.

CC's progressive disclosure means listed skills cost ~minimal context; full bodies load on demand. Today the Cabinet pays full context cost for *some* skills via `Read` instructions and *zero* context cost for the rest — neither path uses CC's native skill discovery.

**Fix:** lift the top ~10 skills into `.claude/skills/<name>/SKILL.md` (just frontmatter + symlink to the foundation file, OR move + replace the original with a stub). The skill body stays exactly where it is; CC discovers it via the SKILL.md wrapper. Per-officer skills can go in plugin-namespaced directories.

### G3. ❌ `skills:` frontmatter key not used in agents
Agent files list skill paths in the markdown body (e.g. "Read these skills: `memory/skills/holistic-thinking.md`") rather than declaring them via the `skills:` frontmatter key that CC auto-loads on agent activation.

**Fix:** add `skills:` lists to each agent file once G2 lands. CC then auto-associates skills at agent boot, removing the manual `Read` step.

### G4. ❌ Inconsistent `hookSpecificOutput` wrapping
Some hooks emit `{hookSpecificOutput: {additionalContext: ...}}` (correct, structured), others emit `{additionalContext: ...}` (the older, non-wrapped form). CC will accept both but the wrapped form is the documented contract going forward.

**Fix:** sweep the 9+ context-emitting hooks, standardize on `{hookSpecificOutput: {additionalContext: ...}}` everywhere. ~30 minutes.

### G5. ❌ No `.claude/commands/` directory
The Cabinet has obvious recurring operations (briefing, retro, research-sweep, role-eval-run, mission-route, work-graph-complete) that are natural slash commands but are invoked via bash scripts. CC's `.claude/commands/<name>.md` would make them `/cabinet-briefing`, `/cabinet-retro`, etc. — discoverable in the slash menu, with documented arguments.

**Fix:** author `.claude/commands/cabinet-*.md` for the ~6 highest-traffic operations. Skills (`/cabinet-org-status` etc.) already cover some; commands cover the rest. ~2 hours.

### G6. ❌ Cabinet not packaged as a CC plugin
No `marketplace.json` exists. The three-layer architecture is *designed* for distribution but isn't *distributed* via the CC plugin system. A founder today bootstraps via `git clone + SETUP.sh`, not `corridor install cabinet@captains-cabinet`.

**Fix:** author `.claude-plugin/plugin.json` + a marketplace manifest (own repo or contributed to `dev-tasks-marketplace`). Plugin contributes: 3 skills, 5 agent definitions, 16 hooks, 5 rules, 2 MCP servers, ~6 slash commands. Per-officer profiles via plugin variants. ~half-day for the manifest + testing the install path on a fresh Mac.

---

## Gaps — Medium priority

### G7. ⚠️ `permissions.defaultMode` not set
Defaults to interactive. The Cabinet's auto-operation model would benefit from `permissions.defaultMode: "auto"` with hooks doing real enforcement (which they already do). Today CC asks before some actions that the hook layer would have allowed anyway.

**Fix:** set `defaultMode: "auto"`. The Cabinet's pre-tool-use hook + spending limits + kill switch already provide tighter enforcement than auto mode's classifier. ~2 minutes.

### G8. ⚠️ No `statusLine`
A custom status line showing current officer + OVI score + active mission would be visible in the CC UI without a Captain DM. CC supports `statusLine: { type: "command", command: "..." }` reading JSON from stdin.

**Fix:** write a 30-line shell script that prints `<officer> | OVI: 0.62 ↑ | mission: outcome-001 (3/5)`. Wire as `statusLine`. ~30 minutes.

### G9. ⚠️ Voice config in `instance/config/product.yml`, not CC settings
CC has a native `voice: { enabled, mode, autoSubmit }` block in settings.json. The Cabinet implements voice independently via ElevenLabs + a `post-reply-voice.sh` hook. Both can coexist, but the native CC voice features (dictation, fullscreen TTS) aren't enabled.

**Fix:** add CC's `voice.enabled: true` so the Captain gets native push-to-talk dictation when conversing with officers in the CC TUI. Hook-driven ElevenLabs voice for Telegram replies stays as-is. ~5 minutes.

### G10. ⚠️ Limited subset of newer hook events
CC supports 32+ hook events. The Cabinet wires 5: `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `Notification`. Newer events the Cabinet doesn't use:
- **`SessionStart` / `SessionEnd`** (distinct from Stop) — clean session boundaries
- **`SubagentStart`** (already have `SubagentStop` via `post-subagent.sh`)
- **`TaskCreated` / `TaskCompleted`** — would auto-emit work_item events from CC's task tool
- **`Elicitation` / `ElicitationResult`** — auto-answer MCP queries
- **`WorktreeCreate` / `WorktreeRemove`** — Cabinet could auto-spawn an officer per new worktree
- **`InstructionsLoaded` / `CwdChanged` / `FileChanged`** — context-aware re-loading

**Fix:** wire the 3 highest-leverage events first: `SessionStart` (for officer boot rituals — read tier2 + captain triplet), `TaskCreated`/`TaskCompleted` (auto-emit work_item events), `WorktreeCreate` (auto-bootstrap officer-per-worktree pattern). Each ~30 minutes.

### G11. ⚠️ No `skillOverrides` / `skillListingMaxDescChars`
With G2's expanded skill set, the listing budget matters. CC's default skill description cap is ~1536 chars per skill, and total skill listing budget is 1% of context. Once the Cabinet has 25+ skills, `skillListingBudgetFraction` should be tuned.

**Fix:** measure after G2 lands. ~5 minutes once measured.

### G12. ⚠️ Hook handler types — only `command` used
CC supports 5 handler types: `command`, `prompt`, `agent`, `http`, `mcp_tool`. The Cabinet uses only `command` (bash scripts). The other four:
- **`prompt`** — an LLM evaluates the hook payload. Use case: captain-reply-refine could use `type: prompt` with a Haiku evaluator instead of shelling out.
- **`agent`** — full subagent verifier. Use case: post-deploy verification spawn.
- **`http`** — POST to a URL. Use case: webhook into a dashboard, GitHub-comment-on-PR, etc.
- **`mcp_tool`** — call an MCP tool. Use case: trigger an event in the Library MCP from a hook directly.

**Fix:** convert 1–2 hooks to test each handler type. e.g. `captain-reply-refine.sh` → `type: prompt`. The Haiku call replaces the shell + Python detour.

---

## Gaps — Lower priority

- **G13.** No `sandbox` config — current strategy (pre-tool-use hook + Redis kill switch) is functionally equivalent
- **G14.** `claude --bg` / background agents — Cabinet intentionally uses tmux/LaunchAgent persistence; CC's native background daemon is an alternative path worth comparing
- **G15.** No `agent` setting for main-thread agent — could give the main session itself a Cabinet identity
- **G16.** No `outputStyle` set
- **G17.** No `worktree.symlinkDirectories` — Cabinet's worktree pattern doesn't share `node_modules` etc.
- **G18.** SDK (Python/TS) not used — Cabinet uses subprocess + JSONL ledger instead (constraint: OAuth/Max-only, no API key)
- **G19.** No `defaultView: "transcript"` for verbose officer debug
- **G20.** No `availableModels` allowlist — Captain could pin model versions

---

## Beta / preview features worth testing now

From the CC feature catalog, ranked by expected Cabinet value:

| Rank | Feature | Status | Why now |
|---|---|---|---|
| 1 | **Agent Teams** (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) | experimental, opt-in | Already enabled but underused. CTO/CRO/COO agent files reference it; no Python code spawns programmatic teams. Phase 5 task adapter authoring + Phase 2 eval running could parallelize via TeamCreate. |
| 2 | **`claude/channel` MCP capability** | experimental | Cabinet already uses this in `redis-trigger-channel`. Could extend to a Telegram-channel MCP that pushes Captain DMs directly to officers without Telegram-plugin polling. |
| 3 | **`type: prompt` hooks** | stable (model-default Haiku) | Replace the bash + Python shell-out in `captain-reply-refine.sh` with a direct prompt hook. Cleaner, faster, native. |
| 4 | **`type: agent` hooks** | stable | Auto-verifier on PR / deploy — would replace the manual `/verify` skill flow. |
| 5 | **TaskCreated / TaskCompleted hooks** | likely beta | Auto-emit `work_item_assigned` / `work_item_completed` events from CC's task tool. Could replace `post-subagent.sh`'s regex-based detection. |
| 6 | **Routines (cron/API/GitHub triggers)** | beta | Could replace `cabinet/cron/*.sh` LaunchAgent setup with first-party CC scheduled invocations. |
| 7 | **Fullscreen TUI renderer** (`tui: "fullscreen"`) | recent | Cleaner UX for the Captain during long Cabinet sessions. |
| 8 | **Voice mode tap-to-toggle** (`voice.mode: "tap"`) | recent | Hands-free Captain dictation during driving / walking. |
| 9 | **Computer-use MCP** | preview | `cua-driver` already configured for the lead officer. Tighter integration possible. |
| 10 | **Channels expansion (Slack, Discord)** | beta/preview | Captain DM surface beyond Telegram. |

---

## Recommended sequence of next changes

If you want to lift the CC-native score from 51% → ~80% without breaking what's working:

**Sprint A — Foundation tightening (~half-day total):**
1. G1 — wire PreCompact + PostCompact (5 min)
2. G4 — standardize `hookSpecificOutput` wrapping (30 min)
3. G7 — set `permissions.defaultMode: "auto"` (2 min)
4. G9 — enable CC native voice for TUI (5 min)
5. G10 partial — wire `SessionStart` for officer boot (30 min)

**Sprint B — Skill surface migration (~half-day to day):**
6. G2 — lift 10 top foundation skills into `.claude/skills/` (a few hours)
7. G3 — add `skills:` frontmatter to each agent (30 min)
8. G11 — measure + tune skill listing budget (5 min)

**Sprint C — Slash commands + statusLine (~half-day):**
9. G5 — author 6 `.claude/commands/cabinet-*.md` (2 hours)
10. G8 — write the statusLine script (30 min)
11. G12 partial — convert `captain-reply-refine.sh` → `type: prompt` hook (1 hour)

**Sprint D — Plugin packaging (~half-day):**
12. G6 — `marketplace.json` + plugin manifest; test install flow on a fresh Mac (~half-day)

**Total estimate to reach ~80% CC-native:** 2-3 days.

---

## What the Cabinet should keep doing its own way

Not every gap is worth closing. These are intentional:

- **Officer persistence via tmux/LaunchAgent, not `claude --bg`.** The Cabinet's persistence model is process-supervised; CC's background daemon is a different abstraction. Worth comparing at some point, but no urgency.
- **Custom Python framework + event ledger.** CC has memory + autoMemory, but they're conversation-scoped; the Cabinet needs cross-session durable org state. The event-sourced framework is correct.
- **Bash hook layer.** Some folks would migrate hooks to `type: prompt` / `type: agent`, but the bash layer has battle-hardened safety logic (FW-029 through FW-051) that shouldn't be casually rewritten.
- **MCP-based Telegram instead of CC channels.** The Telegram MCP plugin is mature; CC's channels feature is still adding integrations. No need to migrate.

---

## Files relevant to this report

- Audit source data (the two agent reports) — embedded in this session's transcript
- This report — `docs/convergence-analysis-2026-05-26/cc-native-gap-report.md`
- The convergence plan — `docs/convergence-analysis-2026-05-26/05-convergence-plan.md`
- Phase logs 0-9 — `docs/convergence-analysis-2026-05-26/phase-*-log.md`
- `.claude/settings.json` — the surface that gates which CC features are active
- `cabinet/scripts/hooks/` — 22 hook scripts (21 wired, 1 utility)
- `memory/skills/` — 20+ foundation skills (G2 lift candidates)
- `.claude/skills/` — 3 current Cabinet skills
