# Brain Bridge Rule (personal-source outbound gate)

The `brain` MCP server is the officers' bridge into the Captain's personal
sensing estate — the personal knowledge store, person intel, commitments,
captain-model/voice surfaces, and the reasoning log. WHICH estate it binds to
is instance data, never framework law: the concrete adapter is resolved
through `framework.sources` from `instance/config/sources.yml`, and the
instance-specific binding addenda live in `instance/flavor-a/rules/`
(one `brain-bridge-<adapter>.md` per bound adapter — read the one matching
the adapter in `sources.yml` alongside this rule; a deployment with no
personal source binds the null source and this rule still governs). Officer scoping
lives in `cabinet/mcp-scope.yml`. These rules are mandatory whenever you
touch the bridge, on every deployment, in every posture.

## The personal store is Captain-truth — read first

- The personal store is the source of truth about the Captain's world:
  people, commitments, decisions, meetings, products. Before acting on,
  asserting, or drafting anything that concerns the Captain's world, query
  the brain FIRST (gather-then-decide). Never act from a stale self-view or
  from Cabinet-internal assumptions when the brain can answer.
- Brain content is the Captain's private memory. It informs your work; it is
  not Cabinet property to republish.

## Outbound communication — queue_draft is the ONLY path

- The ONLY way an officer sends anything to a human outside this machine
  (email, chat, or any other recipient-facing message) is the brain server's
  `queue_draft` tool. Every queued draft goes through the Captain's human
  approval gate before anything is sent.
- NEVER call email or chat APIs directly (no provider-API calls, no
  automation webhooks, no SMTP, no chat POSTs). No other MCP, script, or
  shell path may be used to send outbound messages. If a task seems to
  require direct sending, stop and escalate to the Captain.

## Captain-model / voice — informs, never leaks

- Captain-model and voice-profile content may inform HOW you draft (tone,
  priorities, phrasing) but must NEVER be quoted, pasted, or paraphrased
  into anything that leaves this machine — not in drafts, commits, published
  pages, group posts, or web requests. Treat it like credentials: use it,
  never emit it. Content derived from it is tainted the same way.

## Personal-store writes — append_agent_inbox only

- Officers do not edit personal-store files. The ONLY write path into the
  store is `append_agent_inbox`. Everything else is read-only. Never write,
  move, or delete personal-store files via Bash or any other tool.

## Governance — log what you do

- After any meaningful brain-informed action (queuing a draft, closing or
  acting on a commitment, making a judgment call from personal-store data),
  call `log_reasoning` (action, subject, rationale, expectation) and
  `record_run`. This feeds the deployment's reasoning-review / governance
  loops, so officer behavior stays auditable.
