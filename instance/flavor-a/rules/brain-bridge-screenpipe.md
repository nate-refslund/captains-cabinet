# Brain Bridge — screenpipe binding addendum (Flavor-A instance)

Instance-specific binding content for `.claude/rules/brain-bridge.md` (the
framework-generic outbound-gate invariant — read that rule first; it governs
in full on this deployment). This file carries ONLY what is specific to THIS
launcher's Flavor-A screenpipe deployment (captain "Nate"); it travels with
the flavor-a pack (egg plan rows R132/R153, wave CG-3) and never migrates
back into the germline rule.

## What the `brain` MCP binds to here

- The personal sensing estate is **Nate's screenpipe brain**: the Obsidian
  vault at `~/Obsidian/screenpipe-brain/` (person intel under `3-People/`,
  commitments under `6-Commitments/`, meetings, reflections), plus the
  voice/nate-model surfaces and the agent reasoning log.
- The adapter chain is `instance/config/sources.yml` →
  `flavor_a.screenpipe_source:ScreenpipeSource` (read) and
  `flavor_a.screenpipe_dispatch:ScreenpipeDispatch` (write/actuator), under
  `instance/flavor-a/flavor_a/`. Framework core reaches them only through
  `framework.sources.get_source()` / `get_dispatch()` — never import the
  screenpipe `_shared` libs or touch `~/.screenpipe`/vault paths from
  `framework/**` (CI ratchet: `framework/tests/test_no_screenpipe_in_core.py`).
- The bridge is scoped to all five officers in `cabinet/mcp-scope.yml`.

## Instance names for the generic invariants

- "The personal store is Captain-truth" = **the vault is Nate-truth**. The
  vault is the source of truth about Nate's world; gather-then-decide is the
  standing screenpipe build principle.
- "Captain-model / voice" = the **`nate_model`** and **voice-profile**
  artifacts (real Flavor-A artifact identifiers — external names, kept
  verbatim). They inform tone and judgment; they never leak into anything
  outbound (drafts, commits, Notion pages, Telegram group posts, web
  requests).
- "Outbound" concretely means **email (Microsoft Graph/Outlook) and Teams**
  on this deployment: no Graph calls, no Make webhooks, no SMTP, no chat
  POSTs. `queue_draft` routes every outbound through Nate's approval gate on
  **Telegram**.
- "Governance loops" = the screenpipe **reasoning-review / architect** loops:
  `log_reasoning` + `record_run` feed them so officer behavior stays
  auditable exactly like the screenpipe pipes.
