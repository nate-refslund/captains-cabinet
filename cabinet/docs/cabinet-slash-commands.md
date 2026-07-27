# Cabinet — Latest Claude Code Slash Commands Reference

The Cabinet leverages the latest Claude Code primitives. This doc maps each
to the Cabinet's autonomous-org architecture so officers (and the
implementing session) know which lever to pull for which problem.

## `/loop` — Continuous self-pacing work

**Use for:** ad-hoc multi-turn autonomous work where each iteration needs to
check a condition, do something, then optionally schedule the next wake.

**Pattern:**
- `/loop 5m bash cabinet/scripts/verify-launchagents.sh` — temporary watch, every 5 min
- `/loop bash <your-check-script>` — self-paces via `ScheduleWakeup`

(The old example here looped `mission-supervisor.sh` — don't: routing is
pull-only per Captain ruling; the supervisor is a manual push-nudge, see
`.claude/skills/cabinet-route-tasks/`.)

**Cabinet rule:** **No permanent `/loop` for recurring delivery.** The Redis
Trigger Channel + `cabinet/cron/*.sh` LaunchAgents handle all scheduled
work. `/loop` is for *temporary* / *implementation* tasks only — like the
convergence work currently in flight.

**Cost discipline:** there is NO spending cap to catch you (Captain ruling
2026-07-26 — `instance/config/platform.yml` reads `unlimited`). A runaway
`/loop` will NOT halt on its own, and — read this before you rely on anything
— NOTHING will tell you it is running away either. What exists is
MEASUREMENT: every turn is metered, so the spend is visible in
`cabinet:cost:tokens:daily:<UTC date>` and in the briefing's per-lane line
*if someone looks*. No watchdog row escalates it. The `spend-without-output`
row that would page the Chair when cost climbs while nothing ships is **not
implemented — withheld pending a two-model direction gate** (2026-07-27 scope
ruling: deciding what counts as anomalous and interrupting the Captain is new
behaviour, not a repair), so there is no after-the-fact report either.
Stopping a `/loop` that cannot make progress is entirely your
responsibility — not the gate's, and not a watchdog's. See
`docs/cost-metering.md`.

## `/goal` — Outcome-driven autonomy with a Stop-hook gate

**Use for:** "do X until Y is true." The Stop hook keeps the session running
until the condition holds.

**Pattern:**
- `/goal Execute the convergence plan ... until MacMini-readiness checklist
  is fully green` — exactly what the implementing session is doing now.
- `/goal Ensure all framework tests pass before merging` — auto-loops until
  pytest green.

**Cabinet rule:** `/goal` is appropriate when the WIN STATE is a verifiable
boolean (test passes, OVI threshold met, mission verified). Don't use
`/goal` for fuzzy "make the code nicer" objectives.

## `/verify` — End-to-end behavioral verification

**Use for:** after a code change claims "done," verify the feature actually
works end-to-end (not just that tests pass).

**Pattern:** `/verify the new mission-supervisor.sh routes ready tasks`
→ the verify skill triggers, runs the supervisor, inspects events + Redis
streams, reports.

**Cabinet rule:** for UI changes, `/verify` is mandatory (per CLAUDE.md
"For UI or frontend changes, start the dev server and use the feature in a
browser"). For framework changes, scenario evals + role evals cover most
behavior — `/verify` is for end-to-end Captain-visible flows.

## Agent Teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)

**Enabled in:** `.claude/settings.json::env`.

**Use for:** parallel work that the orchestrator can divide and recombine —
e.g., 5 officers running role evals concurrently, or 3 subagents
authoring task adapters (Phase 5).

**Pattern:** spawn multiple `Agent(...)` calls in a single message. Each
runs in parallel. Background mode (`run_in_background: true`) for genuinely
independent work where the parent has other things to do.

**Cabinet rule:** subagent calls use Sonnet 4.6 (per CLAUDE.md model
routing). Opus is reserved for the orchestrating officer.

## Tool Search

**Enabled by default** in current Claude Code. Deferred MCP tools (those
listed in the system reminder but not yet schema-loaded) become available
via `ToolSearch({query: "...", max_results: N})`.

**Cabinet rule:** when a task needs a tool from a heavy MCP server (e.g.,
Vercel, Notion, Linear), prefer to `ToolSearch({query: "select:<exact_name>"})`
to load *only* the tools you need. Reduces context cost.

## `ScheduleWakeup`

**Use for:** waiting on external state that the harness can't notify you
about — a CI run, an external API call settling, an apt-get install.

**Pattern:** `ScheduleWakeup({delaySeconds: 270, reason: "polling CI run",
prompt: <self-contained prompt>})`. Cache stays warm under 300s.

**Cabinet rule:** don't `ScheduleWakeup` to poll for harness-tracked work
(background subagents, agent teams) — you'll be auto-notified. Reserve it
for external state.

## `mcp__corridor__analyzePlan` (via Corridor hooks)

**Fires automatically** via the corridor@corridor-plugins hooks installed
globally. Every `Edit` / `Write` triggers Corridor security scanning. You
don't call analyzePlan manually; the hooks do.

**Cabinet rule:** if Corridor blocks a code change, **fix the finding**
rather than bypassing the hook. Corridor's findings are usually real
security issues.

## Teammates — implicit teams (`TeamCreate` removed in v2.1.178)

**Current reality:** `TeamCreate` no longer exists. Teams are implicit —
your session is its own team. Teammates spawn via the `Agent` tool's
`name` parameter; coordination runs over the shared task list
(`TaskCreate`/`TaskUpdate` with `owner`) and `SendMessage` (agent messages
carry no user authority — harness-enforced).

**Pattern:** spawn `Agent(name: "worker", ...)` + `Agent(name: "reviewer",
...)` for a bounded implementation task and let them iterate directly.
Full guidance: the `agent-team-workflow` skill
(`.claude/skills/agent-team-workflow/`).

**Cabinet rule:** the officer fleet (roster-derived,
`instance/config/roster.yml`) is NOT a Claude Code team in this sense —
officers are separate `claude` CLI processes (one per officer) that
communicate via Redis Streams and shared interfaces. Teammates are for
ephemeral sub-teams within a single interactive implementation task —
Agent Teams do NOT work headless, so unattended lanes use subagents or
workflow orchestration instead.

---

## Summary table

| Primitive | When | Cabinet integration |
|---|---|---|
| `/loop` | Multi-turn temporary work | Implementation phases, not recurring delivery |
| `/goal` | Outcome with verifiable win-state | Used by the implementing session right now |
| `/verify` | Confirm end-to-end behavior | Mandatory for UI, optional for framework |
| Agent Teams (env flag) | Parallel work | Enabled in `.claude/settings.json` for Cabinet officers |
| Tool Search | Heavy MCP toolkits | Use `select:` query to load only needed tools |
| `ScheduleWakeup` | External-state polling | CI / API / install wait — NOT for harness-tracked work |
| Corridor analyzePlan | Every code generation | Auto-fires via hooks; fix findings, don't bypass |
| Teammates (`Agent` `name:` param) | Ephemeral sub-team (interactive only; `TeamCreate` removed v2.1.178) | Implementation-task scope, not the officer roster |
