# Onboarding report — STEPhie (`stephie`)

_Autonomous research + lane scaffold by the Chair. The SAFE artifacts (lane-CEO role def + this report) are written; everything below under **Needs your approval** is proposed only — nothing external was executed._

## What research found
- **repo:** https://github.com/STEP-Network/stephie-mcp
- **stack:** mcp-server, nextjs, vercel
- **plugins in repo:** dev-tasks
- **summary:** Domain-specific MCP servers for ad operations, built as a TypeScript pnpm monorepo.

## Lane (answers entry, fed to generate-instance)
- slug: `stephie` · name: STEPhie
- repos: ['https://github.com/STEP-Network/stephie-mcp'] · boards: ['5091839409']
- task plugin: `dev-tasks` · lane MCPs: ['vercel', 'library', 'telegram', 'brain']

## Plugin manifest
- ✅ present — `dev-tasks` (repo)
- ➕ needed — `corridor` (cabinet-default)
- ➕ needed — `brain` (cabinet-default)

## Needs your approval (gated — NOT executed)
- **install-plugin** `corridor` — lane needs corridor (not present in repo)
- **install-plugin** `brain` — lane needs brain (not present in repo)

## Notes
- vercel/next detected — set the lane's vercel_project name

## Germline diffs (Captain applies — a loop can't edit its own authorizations)
```
# add to cabinet/mcp-scope.yml (GERMLINE — Captain applies):
    stephie-ceo:
      mcps: [vercel, library, telegram, brain]

# add to cabinet/officer-capabilities.conf (GERMLINE — Captain applies):
stephie-ceo:deploys_code
stephie-ceo:validates_deployments
stephie-ceo:reviews_implementations
stephie-ceo:logs_captain_decisions
```

## To hire this lane-CEO
After applying the germline diffs: `bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml` (or add `stephie-ceo` to the roster). The role def is at `instance/agents/stephie-ceo.md`.
