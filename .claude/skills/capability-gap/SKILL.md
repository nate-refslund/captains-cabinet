---
name: capability-gap
description: Record a capability gap when you hit a wall current tools can't solve, and (as CTO) fulfill an approved gap proposal by building the MCP/skill. Use when an officer can't do something with available tools, keeps doing a manual workaround, or needs to act on a Captain-approved capability proposal. This is how the cabinet extends its own capabilities.
---

# Capability gaps — how the cabinet extends itself

When you hit a wall that your current tools can't solve, **don't silently
work around it** — record it. The cabinet's self-extension loop turns gaps
into new capabilities: procedures become auto-skills, tool/integration needs
become Captain-approved MCPs. Silently working around a gap means the org
never gains the capability and the next officer hits the same wall.

## When to record a gap

Record one when ANY of these is true:
- You needed data/an action and **no tool you have can do it** (e.g. "I need
  the product's Stripe MRR and have no Stripe tool").
- You're about to do a **manual multi-step workaround** you suspect you'll
  repeat (that's a latent skill).
- You notice you've **done the same workaround before** (recurring = priority).

Don't record: one-off trivia, something a tool you DO have can do, or a task
you simply haven't tried yet.

## How to record (one line)

```bash
bash cabinet/scripts/record-capability-gap.sh \
  --need "read the product's Stripe MRR" \
  --kind integration \
  --evidence "tried to report revenue 3x this week, no Stripe tool" \
  --touches secrets,spending      # if you know it touches the hard ceiling
```

- `--kind` is optional; omit it and the cabinet classifies (safe-default:
  propose). Use `procedure` only when it's genuinely just a how-to.
- `--touches` flags hard-ceiling categories (secrets / spending /
  external_comms / production / network_write / credentials_grant). Be honest
  — anything touching these is **always** Captain-gated, never auto.

Recurring near-identical gaps merge (hit-count++), so frequency ranks them.

## What happens next (you don't drive this)

The self-improvement loop picks up open gaps and routes by kind:
- **procedure** → drafts a skill, validates it against evals, auto-promotes
  if it passes. You'll see it appear in `.claude/skills/` / `memory/skills/`.
- **tool / integration** → drafts a one-paragraph proposal and DMs the
  Captain a plain-language yes/no. **Nothing installs without approval.**

### When you've already TESTED the MCP/plugin (the one-tap self-proposal)

If you (the Chair) have evaluated + tested a new MCP/plugin and just need the
**scope grant**, surface a ONE-TAP card instead of a prose proposal —
`framework.learning.self_proposal.prepare_mcp_proposal(server, officers=[...],
why=..., test_evidence=..., account_step=..., gap_id=...)`. It computes the
**exact `cabinet/mcp-scope.yml` diff line** (read-only), bundles the test
evidence + any account step, flags hard-ceiling touches, and enqueues a
front-door intake card. **Nate applies the one scope line himself — the Chair
never self-edits `mcp-scope.yml`** (hard line; the germline guard blocks it
anyway).

Track everything at `/gaps` in the dashboard or
`python3 cabinet/scripts/org-runtime.py gaps list`.

## Fulfilling an approved proposal (CTO)

When the Captain **approves** a tool/integration gap, you (CTO) build it:

1. Confirm it's really approved + safe to install:
   ```bash
   python3 cabinet/scripts/org-runtime.py gaps show <gap_id>
   ```
   The status must be `approved`. The install gate (`capability_gaps.can_install`)
   fails closed — if it's not approved, or it touches the hard ceiling, STOP
   and re-surface to the Captain. Never bypass the gate.
2. Build the MCP with the first-party `mcp-builder` skill (Python FastMCP or
   Node MCP SDK). Keep it **read-only** unless the proposal + approval
   explicitly cover writes.
3. Declare it in `instance/config/extensions.yml` under `mcps:` and run
   `bash cabinet/scripts/install-extensions.sh`.
4. Grant the officer(s) that need it: add `mcp__<name>` to an
   `instance/agents/<officer>.md` overlay; `sync-agents.sh` merges it.
5. Mark the gap resolved:
   ```bash
   python3 cabinet/scripts/org-runtime.py gaps resolve <gap_id> --resolution "mcp: <name>"
   ```

## The principle

Gaps are how the org learns what it's missing. Record them honestly, let the
loop auto-handle the safe ones, and treat the Captain-approval gate on
code/credentials/spend as inviolable — that gate is what makes the rest safe
to automate.
