# Germline amendment — remove the dangling CoS `host` MCP grant (2026-07-07)

**Status:** APPLIED under the Captain's temporary germline unlock for the
2026-07-07 cleanup wave (ledger row CG-8). This document is the companion
record for the germline edit; no further apply token is needed. Reply
**"revert host grant removal"** to have a session restore the grant and the
`officers/cos/.mcp.json` definition from this commit's parent.

**Why:** `cabinet/mcp-scope.yml` granted CoS an MCP server named `host`
(Spec 035 Phase A host-agent tools: run, rebuild_service, restart_officer,
tail_logs, edit_file, read_file) that no live configuration defines. A grant
without a definition is dead policy weight and a latent confusion vector —
the scope file is the single source of truth for what an officer can reach,
and it claimed a capability that cannot exist on this deployment.

**Verified facts (2026-07-07, live checkout):**

- No live `.mcp.json` layer defines `host`. The Mac boot merge in
  `cabinet/scripts/start-officer-mac.sh` stacks `.mcp.json.mac-native`
  (notion, neon, linear, vercel, redis-trigger-channel, library, screenpipe,
  chrome_devtools, playwright, cua) + `instance/config/extra-mcps.json`
  (brain, perplexity) + `instance/agents/<officer>/mcp.json`. The Hetzner
  fallback root `.mcp.json` (notion, neon, linear, vercel,
  redis-trigger-channel, library, make) doesn't define it either.
- The ONLY definition anywhere was `officers/cos/.mcp.json`, pointing at
  `/usr/bin/python3 /opt/founders-cabinet/cabinet/mcp-server/host-tools.py`.
  `/opt/founders-cabinet` does not exist on this machine; that Docker/Hetzner
  deployment is declared extinct (CLAUDE.md, re-grounded 2026-07-04). The
  file is read by no boot path, no `cabinet/services.yml` entry, no
  `com.cabinet.*.plist` LaunchAgent, and no settings hook.
- `.claude/agents/cos.md` references no host tools — officer boot smoke is
  unaffected by the removal.

## Diff 1 — cabinet/mcp-scope.yml (germline, `germline-lock.sh` line 64)

```diff
   cos:
-    mcps: [notion, library, telegram, host, brain, exa, brave-search, perplexity, claude-in-chrome]
+    mcps: [notion, library, telegram, brain, exa, brave-search, perplexity, claude-in-chrome]
     rationale: >
       Coordination and briefings. Not code; CoS does not touch Neon or
       Vercel directly — that's CTO/COO. Library for Phase 1 inbox and
       memory lookups; Notion for legacy business brain until migration.
-      host: Spec 035 Phase A host-agent tools (run, rebuild_service,
-      restart_officer, tail_logs, edit_file, read_file). CoS-only scope —
-      no other officer is allowed host MCP access.
+      (host grant removed 2026-07-07 — dangling: no live .mcp.json layer
+      defines a `host` server; the only definition pointed at the extinct
+      /opt/founders-cabinet deployment. See
+      docs/proposals/germline-amendment-host-grant-removal-2026-07-07.md.)
```

## Diff 2 — delete officers/cos/.mcp.json (NOT germline; tracked, clean)

The stale CoS-local definition pointing at the extinct deployment is removed
(`git rm officers/cos/.mcp.json`). It was the last artifact keeping the
phantom `host` server nominally "defined".

## What it does NOT do

- Does not touch any other officer's scope, the `scaffolds:` section, or the
  `universal:` list.
- Does not change hook enforcement semantics — pre-tool-use.sh continues to
  block any MCP call outside an agent's `mcps:` list; `host` calls by CoS
  were already impossible in practice (server undefined) and now the scope
  file agrees with reality.
- Does not delete `cabinet/mcp-server/host-tools.py` (the in-repo server
  implementation). It is now fully unreferenced by config; retiring it is a
  separate, ordinary (non-germline) cleanup decision.

## Known residuals (noted, deliberately not edited here)

- `cabinet/scripts/hooks/pre-tool-use.sh` (germline, NOT unlocked for this
  row) carries a stale rationale comment in the `cabinet/.env` arm ("cos
  already holds the host MCP (edit_file/run over every host file)"). The
  enforcement logic is unaffected — only the justification prose is stale.
  Flagged for the next pre-tool-use.sh germline window.
- `cabinet/mcp-server/host-tools.py` docstring still names
  `officers/cos/.mcp.json`; dead code describing its own removed wiring.

**One-revert rollback:** `git revert <this-commit>` restores both the grant
line and `officers/cos/.mcp.json` exactly; no other file participates.
