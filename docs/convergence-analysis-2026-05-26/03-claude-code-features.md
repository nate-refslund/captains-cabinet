# Claude Code & Agent SDK: Comprehensive Feature Research
## For Autonomous 24/7 AI Organization on Mac Mini

**Research Date:** May 26, 2026
**Knowledge Cutoff:** February 2025 (with May 2026 releases included)

---

## Executive Summary

Claude Code v2.1.150+ and Agent SDK provide robust foundation for 24/7 autonomous organization:

**Core Enablers:**
1. Native hooks (SessionStart, PreToolUse, PostToolUse) for enforcement + logging
2. Agent teams (experimental, opt-in) for multi-agent coordination
3. Session persistence with resume/fork for long-lived state
4. MCP integration (local + remote) for external systems
5. Scheduled tasks (/loop, /schedule, Desktop cron) for recurring work
6. Permission modes (auto, bypassPermissions) for unattended operation
7. Model routing (Opus 4.7 xhigh, Sonnet 4.6, Haiku 4.5) for cost
8. Agent SDK for headless Python/TypeScript operation
9. Skills (namespaced) for reusable expertise
10. File-based configuration for version control

**Critical Limitation:** Session-scoped tasks expire after 7 days. For true 24/7 without restarts, use Managed Agents (REST API, beta) or Routines (cloud-backed scheduling).

---

## 1. NATIVE HOOKS

### Lifecycle Events

7 hook types fire at specific points:
- SessionStart (once per init/resume/clear/compact)
- UserPromptSubmit (before prompt processing)
- PreToolUse (before tool execution, can block)
- PostToolUse (after tool execution)
- Stop (after Claude finishes)
- SessionEnd (at exit)

### Execution Models

1. Command hooks (.sh/.py): JSON stdin → stdout
2. HTTP hooks: POST request with timeout
3. MCP tool hooks: invoke tool on MCP server
4. Prompt hooks: single-turn LLM eval
5. Agent hooks (experimental): spawn subagent

### Cabinet Use Cases

- Constitution enforcement (PreToolUse blocks rm -rf /)
- Audit logging (PostToolUse → PostgreSQL)
- Cost tracking (token counters per officer, per day)
- Context injection (SessionStart loads tier2 memory)
- Permission decisions (extensible rule engine)

### Key Gotchas

- Synchronous blocking: long timeouts freeze session
- Command hooks need workspace trust
- Matcher patterns (regex) can be tricky
- No streaming: outputs are atomic

---

## 2. SKILLS & COMMANDS

### What They Are

Agent Skills (open standard, https://agentskills.io) packaged in .claude/skills/*/SKILL.md

Frontmatter controls behavior:
- description: auto-trigger condition
- disable-model-invocation: false = Claude invokes automatically
- tools: optional allowlist
- model: force specific model
- effort: effort level override

### Invocation Methods

- Auto: Claude recognizes task and invokes based on description
- Explicit: /skill-name
- Slash command: /deploy (backward compat)
- MCP prompt: /mcp__github__list_prs

### Cabinet Pattern

Define per-role skills (mission-compile, role-eval, org-status) and cross-cutting concerns (research-embed, reflection). Namespacing prevents conflicts (cabinet:mission-compile vs vercel:deploy).

### Limits

- No skill→skill chaining
- Description matching is heuristic
- No named parameters
- Auto-invocation not guaranteed

---

## 3. AGENT DEFINITIONS

### What They Are

Persistent role templates in .claude/agents/*.md

Frontmatter:
- description: auto-selector trigger
- model: override (e.g., cto=opus, cro=sonnet)
- effort: effort override
- tools: allowlist (critical for scoped authority)
- color: UI indicator

### How Harness Uses Them

- Auto-selection: "CTO review" finds + loads CTO agent
- Tool filtering: agent can only use listed tools
- Model override: CTO always runs on Opus 4.7
- Subagent spawning: /agent cto "find the bug"
- System prompt concatenation: agent body appended

### Cabinet Pattern

Define CTO, CPO, CRO, COO, COS matching your role registry. Each has scoped tools matching their charter.

### Key Strength

Persistent identity + tool-scoped authority = roles can't do things outside their mandate.

---

## 4. PLUGINS

### Structure

Directory with .claude-plugin/plugin.json + components:
- skills/
- agents/
- hooks/
- .mcp.json
- settings.json
- monitors/

### Distribution

- GitHub marketplace: pinned to commit SHA
- Private marketplace: your org's GitHub repo
- Direct: /plugin install /path or --plugin-dir for dev

### Cabinet Value

Ship entire Cabinet as plugin:
- Encapsulation: skills + agents + hooks + MCP servers ship together
- Team distribution: one marketplace URL, all officers installed
- Versioning: single version number
- Namespace isolation: no conflicts with other plugins

### Limits

- Plugin order matters
- No plugin dependencies
- Settings merge is shallow
- Some components need session restart for reload

---

## 5. RULES (Not Yet Implemented)

Rules don't exist in Claude Code yet (planned for Managed Agents).

Workaround: Use hooks to implement rule-like enforcement.

---

## 6. MCP SERVERS

### Local vs Remote

Local (stdio): spawn subprocess, good for file access + custom scripts
Remote (HTTP): HTTPS requests, for cloud services
SSE (deprecated): don't use

### Tool Search (Default)

Defers tool loading: only names load at session start, schemas fetch on demand.
Saves context window; no upfront tool cost.

Can disable with ENABLE_TOOL_SEARCH=false for legacy behavior.

### Configuration (.mcp.json)

```json
{
  "mcpServers": {
    "neon": {
      "type": "stdio",
      "command": "npx",
      "args": ["@neon/mcp"],
      "env": {"NEON_API_KEY": "${NEON_API_KEY}"}
    },
    "notion": {
      "type": "http",
      "url": "https://mcp.notion.com/mcp",
      "headers": {"Authorization": "Bearer ${NOTION_TOKEN}"}
    }
  }
}
```

### Auth Flows

- Static headers: API keys
- Environment vars: ${API_KEY} expansion
- OAuth 2.0: /mcp auth flow
- Dynamic headers: custom auth script
- Workload Identity: AWS/GCP federation

### Cabinet Pattern

Notion (business brain), Linear (backlog), Neon (database), Vercel (deploy), GitHub (code).
All connected via MCP; no custom API client code.

### Vercel-Hosted MCP

For Cabinet APIs, use mcp-handler package:
```typescript
// pages/api/mcp.ts
import { MCP } from 'mcp-handler';
const mcp = new MCP();
mcp.tool('list_tasks', async () => {
  const tasks = await db.query(...);
  return tasks;
});
export default mcp.handler();
```

---

## 7. SESSIONS & STATEFULNESS

### Lifecycle

- Session created (UUID)
- Interactive loop: prompt → work → respond
- Session persisted to ~/.claude/projects/{project}/{session-id}.jsonl
- Resume later with full context

### Resume, Fork, Branch

- claude --resume <name>: load prior session
- /branch <name>: copy conversation, try different approach
- /rewind <turn>: go back N turns
- /clear: fresh context, old transcript stays resumable

### Compaction

/compact [instructions] summarizes history to free context.
Preserves CLAUDE.md, skills, hooks, agents, MCP servers.
Triggers post-compact.sh hook (skill refresh, memory reload).

### Strengths for Cabinet

- Persistent context across restarts
- Branching for A/B testing hypotheses
- Compaction for long projects (reduce 10k turns to summary)
- 7-day auto-cleanup (old sessions deleted)
- Offline-safe: all local

### Limits

- No cloud replication: loss of disk = loss of sessions
- No cross-session sharing: officers can't directly share context
- Compaction is lossy: summaries may miss subtleties

---

## 8. BACKGROUND SUBAGENTS (TaskCreate)

### Architecture

Main agent spawns subagent with prompt.
Subagent runs in own context.
Results returned inline (summarized).

### Features

- Own context window (doesn't bloat main transcript)
- Tool allowlist (read-only reviewer: can't edit)
- Parent tracking (messages include parent_tool_use_id)
- Model override (subagent runs different model)
- Result summarization (full results optional)

### Notification

SubagentStop event when subagent completes.
No polling: completion is pushed.

### Cabinet Pattern

CTO spawns "code-reviewer" subagent for detailed audit without cluttering main transcript.
Results summarized; expensive processing doesn't bloat context.

### Limits

- No inter-subagent messaging (only report back to main)
- Results are summarized (lose detail)
- Tool set is static at spawn time
- Cost scales linearly (N subagents = N contexts)

---

## 9. MULTI-AGENT ORCHESTRATION (TeamCreate)

### Current Status

Experimental, opt-in: CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1

### Architecture

Team lead (main session) coordinates teammates (separate sessions).
Shared task list (claim/complete), mailbox (messaging), lead orchestrates.

### Tools

- TeamCreate: create team + spawn teammates
- TaskCreate/TaskClaim: manage task queue
- SendMessage: inter-agent messaging
- TaskComplete: unblocks dependent tasks

### Display Modes

- In-process (default): all teammates in one terminal; Shift+Down cycles
- Split panes: each teammate in own pane (tmux/iTerm2)

### Best Use Cases

- Research + review: parallel investigation, debate findings
- New modules: teammates own separate files
- Debugging: competing hypotheses, converge on answer

### Strengths

- True parallelism: 3 officers work 3 aspects simultaneously
- Shared task list: automatic load balancing
- Inter-agent messaging: debate, synthesize
- Lead coordination: you stay in control

### Limits

- Experimental: session resumption breaks
- Token cost is high: each teammate = full context
- File conflicts: partition by ownership
- One team at a time
- Task status can lag

---

## 10. MODEL ROUTING & EFFORT LEVELS

### Models (May 2026)

| Model | Context | Speed | Cost |
|-------|---------|-------|------|
| Opus 4.7 | 200k | Baseline | $5–$25 |
| Opus 4.7 Fast | 200k | 2.5x | $30–$150 (6x) |
| Sonnet 4.6 | 200k | 5–10x | $3–$15 |
| Haiku 4.5 | 200k | 10x | $0.80–$4 |

### Effort Levels (Adaptive Reasoning)

- low: minimal thinking, fastest
- medium: some thinking, fast
- high: moderate thinking, normal (default Sonnet)
- xhigh: deep thinking, normal (NEW, default Opus 4.7)
- max: exhaustive, slowest

**xhigh is new (May 2026)**: sits between high and max, gives deeper reasoning without full cost.

### Model Routing in Session

```bash
claude --model opus-4-7 --effort xhigh
/model sonnet-4-6        # Switch
/effort xhigh            # Change effort
/effort slider           # Interactive
```

### Agent-Specific Overrides

Agents specify model in frontmatter; subagents inherit from lead unless overridden.

### Cabinet Pattern

Opus lead (xhigh) makes decisions; Sonnet teammates implement.
CRO runs Sonnet to save cost; CTO always Opus for architecture.

### Cost Example (5 officers, monthly)

- CTO (Opus, xhigh): ~$300
- CRO/CPO/COO (Sonnet, high): ~$240
- COS (Opus, high): ~$150
- Total: ~$690–$1200 (with agent teams)

---

## 11. /LOOP, /SCHEDULE, /VERIFY

### /loop (Session-Scoped, 1-min minimum)

```bash
/loop 5m check if deploy finished
/loop check CI and address comments    # Claude picks interval
/loop                                  # Built-in maintenance prompt
```

Runs while session open. Jitter 0–30min. 7-day expiry.

### /schedule (Cloud, 1-hour minimum)

```bash
/schedule --daily 06:00 "generate briefing"
/schedule --hourly "check for new work"
```

Runs on Anthropic infrastructure; persists across restarts.

### Desktop Scheduled Tasks

For truly durable scheduling (survives Mac Mini restart):
```bash
claude desktop-task create --schedule "daily 06:00" --prompt "..."
```

Stored in ~/Library/Application Support/Claude/schedules/.

### /verify Skill

Post-deployment verification:
1. Check HTTP health endpoint
2. Run core workflow (login → buy → logout)
3. Check error logs
4. Monitor latency
5. Report go/no-go

Can use browser MCP (claude-in-chrome) for end-to-end testing.

### Monitor Tool

For background processes:
```bash
Monitor(command: "tail -f deploy.log")
# Streams lines; check if deployment complete
```

---

## 12. MEMORY & AUTO-MEMORY

### Tier Structure

**Tier 1 (loaded at start):** Constitution, safety, role definitions, CLAUDE.md, captain-patterns, captain-intents

**Tier 2 (session-to-session):** instance/memory/tier2/{role}/*.md (officer notes, learned patterns)

**Tier 3 (on-demand query):** Postgres pgvector (research briefs, competitive intel, decision logs)

### Tier 2 Workflow

Officer reads at session start:
```bash
cat instance/memory/tier2/$OFFICER_ROLE/*.md | head -100
```

Officer updates after work:
```bash
cat >> instance/memory/tier2/$OFFICER_ROLE/$(date +%Y-%m-%d)-topic.md << 'EOF'
## What happened
## What I learned
## Next time
EOF
```

### Tier 3 (Semantic Search)

```bash
bash embed-research.sh brief.md --tags "claude-code,2026" --decay "fast-moving"
bash search-research.sh "autonomous agent scheduling"
```

Voyage AI embedding (1024-dim), tagged with decay rate.

### Auto-Memory

Agent SDK supports MemoryManager (not yet in CLI):
```python
memory=MemoryManager(
    user_file="~/.claude/user.memory",
    auto_update=True
)
```

### Strengths

- 3-tier matches improvement loops (Tier 1 = constitution; Tier 2 = session notes; Tier 3 = research)
- File-based Tier 2 survives session exits
- Pgvector Tier 3 enables semantic search
- Officer memory ownership

### Limits

- No built-in consolidation (manual prune needed)
- Tier 3 needs Postgres
- Memory state not versioned

---

## 13. PERMISSION MODES

### Modes

| Mode | Behavior | Unattended Safe |
|------|----------|-----------------|
| default | Ask Claude on each decision | No |
| auto | Approve based on learned intent | No (but safer) |
| bypassPermissions | Auto-approve all | Yes (risky) |
| acceptEdits | Auto-approve edits unless dangerous | Maybe |
| plan | Read-only; approve before changes | Yes (slow) |

### Permission Rules

```json
{
  "allow": ["Read", "Bash(git *)", "Bash(npm run *)", "mcp__notion__*"],
  "deny": ["Bash(rm -rf /*)", "Bash(sudo *)", "Bash(docker *)"]
}
```

Deny rules always block; allow rules always permit; others depend on mode.

### Cabinet Pattern

Set bypassPermissions for CTO + Sonnet subagents (they have trusted tool limits via agent frontmatter).

---

## 14. HEADLESS / SDK MODE

### Agent SDK (Python/TypeScript)

Runs without terminal UI. Perfect for Mac Mini daemons.

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(
    prompt="Find and fix the bug in auth.ts",
    options=ClaudeAgentOptions(
        allowed_tools=["Read", "Edit", "Bash"],
        permission_mode="acceptEdits"
    )
):
    if hasattr(message, 'result'):
        print(message.result)
```

### Session Persistence in SDK

```python
# Capture session ID
session_id = ...  # from SystemMessage(subtype='init')

# Resume later
async for message in query(
    prompt="Now find all places that call it",
    options=ClaudeAgentOptions(resume=session_id)
):
    ...
```

### Hooks in SDK

```python
async def log_file_change(input_data, tool_use_id, context):
    file_path = input_data.get("tool_input", {}).get("file_path")
    with open("./audit.log", "a") as f:
        f.write(f"{datetime.now()}: modified {file_path}\n")
    return {}

async for message in query(..., options=ClaudeAgentOptions(hooks={
    "PostToolUse": [HookMatcher(matcher="Edit|Write", hooks=[log_file_change])]
})):
    ...
```

### Strengths

- True headless execution (no terminal)
- Programmatic control (spawn from Python)
- Hook-based observability (audit every action)
- Session persistence (SDK respects .claude/)

### Limits

- SDK not feature-parity with CLI (/goal, /agents not in SDK)
- No real-time interaction during task
- Terminal-only MCP servers problematic
- No built-in logging (implement via hooks)

---

## 15. COST & SPEND LIMITS

### Billing (May 2026)

Opus 4.7: $5 input, $25 output per 1M tokens
Sonnet 4.6: $3 input, $15 output per 1M tokens
Haiku 4.5: $0.80 input, $4 output per 1M tokens

Cache write: 25% of input cost
Cache hit: 10% of input cost

### Spend Guards

```bash
export ANTHROPIC_MONTHLY_BUDGET=2000    # Dollars
export ANTHROPIC_DAILY_BUDGET=100       # Dollars
```

CLI warns when approaching limits; SDK does not enforce (implement in hook).

### Monthly Cost Estimate (5 officers)

- CTO (Opus, xhigh): ~$300
- 4 others (Sonnet, high): ~$240
- Total: ~$540 (baseline)
- With 2-agent teams: ~$1200

### Cabinet Pattern

Hook-based cost tracking:
```bash
# PostToolUse hook increments Redis counters
redis-cli INCR cabinet:costs:$(date +%Y-%m-%d):input:$TOKENS_IN
```

---

## 16. VERIFICATION & TESTING

### /verify Skill

Post-deployment checklist:
1. HTTP health endpoint (200 OK)
2. Core workflow (login → buy → logout)
3. Error logs (no new exceptions)
4. Performance (P99 latency < threshold)
5. Report go/no-go

### Browser-Driven Testing

```bash
claude mcp add --transport stdio playwright -- npx @playwright/mcp@latest
```

Use in verification:
```
Take screenshot of home page.
Fill login form with test@example.com / password.
Click submit.
Verify dashboard shows username.
```

### vercel:verification Skill

Vercel-specific:
1. Deployment status (green?)
2. Preview URL health
3. Lighthouse score comparison
4. Smoke tests
5. Blockers or green light

### Strengths

- Integration testing without UI mocks
- Automated smoke tests after every deploy
- Lighthouse CI for perf regression detection
- Error log monitoring (catch exceptions early)

### Limits

- Browser tests are slow (30–60s each)
- Flakiness: need retries
- Test data management: clean accounts, isolated DBs
- Rate limits: too many tests trigger DDoS protection

---

## 17. LONG-RUNNING AUTONOMY

### Session Lifecycle for 24/7

Problem: Sessions are interactive; they time out.

Solution stack:
1. Persistent task queue (Postgres officer_tasks)
2. Officer daemon (Python + Agent SDK)
3. Scheduled launch (LaunchAgent on macOS)
4. Task scheduler (/schedule or cron)
5. Monitoring (health checks, alerts)

### Daemon Loop Pattern

```python
async def officer_loop(role='cto'):
    while True:
        task = get_pending_task(role, status='pending')
        if not task:
            await asyncio.sleep(60)
            continue
        
        mark_complete(task['id'], status='in_progress')
        
        try:
            result = None
            async for message in query(
                prompt=task['prompt'],
                options=ClaudeAgentOptions(allowed_tools=task['allowed_tools'])
            ):
                if hasattr(message, 'result'):
                    result = message.result
            mark_complete(task['id'], status='done', result=result)
        except Exception as e:
            mark_complete(task['id'], status='failed', error=str(e))
            await asyncio.sleep(300)
```

### LaunchAgent (macOS)

```xml
<!-- ~/Library/LaunchAgents/com.founders-cabinet.cto.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" ...>
<plist version="1.0">
<dict>
  <key>Label</key><string>com.founders-cabinet.cto</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/opt/founders-cabinet/scripts/officer-daemon.py</string>
    <string>--role</string><string>cto</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ANTHROPIC_API_KEY</key><string>sk-ant-...</string>
    <key>DATABASE_URL</key><string>postgresql://...</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>/tmp/cabinet-cto.log</string>
  <key>StandardErrorPath</key><string>/tmp/cabinet-cto-error.log</string>
</dict>
</plist>
```

Load: `launchctl load ~/Library/LaunchAgents/com.founders-cabinet.cto.plist`

### Retry & Escalation

```python
def handle_failure(task_id, error):
    task = get_task(task_id)
    task['retry_count'] = (task.get('retry_count', 0) or 0) + 1
    
    if task['retry_count'] < 3:
        delay = 2 ** task['retry_count']  # 2, 4, 8 seconds
        schedule_retry(task_id, delay)
    else:
        notify_officer('cos', f"Task {task_id} failed after 3 retries: {error}")
        mark_complete(task_id, status='escalated')
```

### Health Monitoring

```python
def health_check():
    last_activity = redis_get('cabinet:last-activity:cto')
    if time.time() - last_activity > 600:  # 10 min idle
        if not process_alive('officer-daemon'):
            launchctl_restart('com.founders-cabinet.cto')
```

### Managed Agents Alternative

For serverless 24/7 (no Mac Mini):
```bash
curl -X POST https://api.anthropic.com/agents/sessions \
  -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
  -d '{"model": "claude-opus-4-7", "system_prompt": "...", "tools": [...]}'
# Returns session_id; Anthropic manages lifecycle
```

---

## 18. LATEST CHANGELOGS (May 2026)

### Claude Code v2.1.142+

**New:**
- Opus 4.7 as fast mode default (2.5x throughput, 6x cost)
- xhigh effort level (between high and max, default for Opus 4.7)
- agent view (`claude agents`): dashboard to dispatch background sessions
- `/goal` command: set completion condition, Claude iterates until met
- Desktop scheduled tasks: persistent cron-like scheduler
- Agent teams (experimental): opt-in multi-agent orchestration

**Improvements:**
- MCP pagination fixed
- OAuth token refresh race condition fixed
- Extended thinking redaction fixed
- Tool search enabled by default
- PowerShell tool rolling out (Windows)
- Fullscreen TUI mode (flicker-free, low memory)

**Fixes:**
- Bash tool exit code 127 fixed
- find command file descriptor exhaustion fixed
- Full Disk Access compatibility fixed
- Memory growth with images fixed

**Deprecation:**
- SSE MCP transport deprecated (use HTTP)
- Linear write restriction: post-Spec-039, Linear is read-only; write to /tasks (Postgres)

---

## 19. MAC MINI STORAGE & DURABLE STATE

### File-Based Persistence

Claude Code stores everything locally:
- ~/.claude/projects/{project-hash}/{session-id}.jsonl (30-day retention)
- ~/.claude/settings.json
- ~/.claude/agents/
- ~/.claude/skills/
- ~/.claude/teams/
- ~/.claude.json (MCP servers, user scope)
- ~/Library/LaunchAgents/ (daemons)

**No cloud sync by default**: loss of disk = loss of sessions.

### Best Practices

1. **Regular exports**: Hook PostToolUse to export sessions to Git/S3
2. **Database backups**: Neon auto-backs up; Upstash has snapshots
3. **Disk monitoring**: Alert if > 80%
4. **Transcript rotation**: Archive after 25 days (auto-delete at 30)

### Recommended Architecture

```
Mac Mini (daemons, task queue cron)
    ↓
Neon PostgreSQL (persistent state, tasks, logs)
    ↓
Upstash Redis (memory, cache, locks)
    ↓
GitHub (git-backed: CLAUDE.md, shared/*, tier2 notes)
    ↓
S3 (long-term backup: transcripts, research)
```

### State Recovery

If Mac Mini restarts:
1. LaunchAgent auto-restarts officer daemons
2. Daemon resumes from last session ID (stored in Redis)
3. Pending tasks re-claimed from task queue
4. Session resumes with full context

---

## 20. CROSS-SESSION/CROSS-OFFICER COMMUNICATION

### Recommended Patterns

| Pattern | Tech | Latency | Persistence |
|---------|------|---------|-------------|
| Real-time urgent | Redis Streams | <50ms | 24h (FIFO) |
| Event-driven | Postgres LISTEN/NOTIFY | <100ms | None (volatile) |
| Durable async | Git files + Notion | 1–10s | Indefinite |
| Shared knowledge | MCP resource refs | Depends | Depends |

### Pattern 1: Redis Streams

Officers subscribe to notification channels:
```bash
redis-cli XREAD BLOCK 0 STREAMS cabinet:notifications:cto $
```

Another officer sends:
```bash
redis-cli XADD cabinet:notifications:cto \* task_id "AUTH_REFACTOR" priority "high"
```

**Strengths**: real-time, automatic delivery
**Limits**: volatile (24h expiry); no persistence across restart

### Pattern 2: Postgres LISTEN/NOTIFY

```sql
NOTIFY cabinet_events, json_build_object('event', 'task_created', ...)::text;
```

Officer daemon listens with `conn.set_notice_processor()`.

**Strengths**: event-driven, WAL-persisted
**Limits**: listeners lose events while offline

### Pattern 3: File-Based (Git)

Officers write shared artifacts to git-tracked locations:
- shared/interfaces/captain-decisions.md
- shared/interfaces/captain-patterns.md
- shared/interfaces/tech-radar.md

SessionStart hook reads into context.

**Strengths**: version-controlled, auditable, human-readable
**Limits**: eventual consistency (polling-based)

### Pattern 4: MCP Resource References

Instead of copying Notion docs:
```
@notion:database://product-specs/AUTH_REFACTOR
```

Claude fetches on demand (always current).

---

## TOP 10 FEATURES FOR AUTONOMOUS CABINET

**Ranked by impact on 24/7 operation:**

1. **Session persistence + resume** — survives crashes, maintains context across restarts
2. **Hooks (PostToolUse, SessionStart)** — audit, logging, cost tracking, context injection
3. **Agent definitions (roles)** — persistent identity, tool-scoped authority
4. **MCP servers (Notion, Linear, Neon)** — zero-boilerplate integration
5. **Agent SDK (headless)** — run officers without terminal UI
6. **Scheduled tasks (/schedule, Desktop)** — recurring work without intervention
7. **Subagents + agent teams** — parallelizable work, delegation, multi-perspective
8. **Permission modes (auto, bypassPermissions)** — unattended operation without prompts
9. **Model routing (Opus/Sonnet) + effort** — cost-optimized execution
10. **Skills (namespaced)** — reusable expertise, encapsulated knowledge

---

## CONCLUSION

**Production-Ready:**
- Session persistence (resilient context across restarts)
- Hooks (enforce constitution, audit, logging)
- Agent definitions (persistent roles)
- MCP integration (external systems)
- Agent SDK (programmatic headless)
- Permissions (auto-approval)

**Experimental:**
- Agent teams (useful but marked experimental; resumption breaks)
- Managed Agents (REST API alternative; not fully documented)

**Architecture for 24/7 on Mac Mini:**
```
[5 Officer daemons (Python + Agent SDK)]
    ↓
[Shared task queue (Postgres)]
    ↓
[Memory & audit (Tier 2 files + pgvector)]
    ↓
[External systems (MCP: Notion, Linear, Neon, Vercel)]
```

**Next Steps:**
1. Implement Postgres task queue
2. Create officer daemon (Python SDK)
3. Set up LaunchAgents (auto-restart + boot)
4. Build hooks (audit, cost, context)
5. Test session resumption (crash recovery)
6. Monitor & alert (health checks)

---

**Report:** May 26, 2026
**Sources:** Claude Code v2.1.150, Agent SDK, Anthropic Platform docs
**For:** Autonomous Cabinet with 24/7 runtime on Mac Mini

