# Brain Bridge Rule (brain MCP)

The `brain` MCP server is the officers' bridge into Nate's screenpipe brain
(Obsidian vault at `~/Obsidian/screenpipe-brain/`, person intel, commitments,
voice/nate-model, reasoning log). It is scoped to all five officers in
`cabinet/mcp-scope.yml`. These rules are mandatory whenever you touch it.

## The vault is Nate-truth — read first

- The vault is the source of truth about Nate: people, commitments, decisions,
  meetings, products. Before acting on, asserting, or drafting anything that
  concerns Nate's world, query the brain FIRST (gather-then-decide). Never act
  from a stale self-view or from Cabinet-internal assumptions when the brain
  can answer.
- Brain content is Nate's private memory. It informs your work; it is not
  Cabinet property to republish.

## Outbound communication — queue_draft is the ONLY path

- The ONLY way an officer sends anything to a human outside this machine
  (email, Teams, or any other recipient-facing message) is the brain server's
  `queue_draft` tool. Every queued draft goes through Nate's human approval
  gate on Telegram before anything is sent.
- NEVER call email or Teams APIs directly (no Graph calls, no Make webhooks,
  no SMTP, no chat POSTs). No other MCP, script, or shell path may be used to
  send outbound messages. If a task seems to require direct sending, stop and
  escalate to Nate.

## nate_model / voice — informs, never leaks

- `nate_model` and voice-profile content may inform HOW you draft (tone,
  priorities, phrasing) but must NEVER be quoted, pasted, or paraphrased into
  anything that leaves this machine — not in drafts, commits, Notion pages,
  Telegram group posts, or web requests. Treat it like credentials: use it,
  never emit it.

## Vault writes — append_agent_inbox only

- Officers do not edit vault files. The ONLY write path into the vault is
  `append_agent_inbox`. Everything else is read-only. Never write, move, or
  delete vault files via Bash or any other tool.

## Governance — log what you do

- After any meaningful brain-informed action (queuing a draft, closing or
  acting on a commitment, making a judgment call from vault data), call
  `log_reasoning` (action, subject, rationale, expectation) and `record_run`.
  This feeds the existing reasoning-review / architect governance loops, so
  officer behavior stays auditable exactly like the screenpipe pipes.
