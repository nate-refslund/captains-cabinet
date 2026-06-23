# Onboarding report — PolAds (`polads`)

_Autonomous research + lane scaffold by the Chair. The SAFE artifacts (lane-CEO role def + this report) are written; everything below under **Needs your approval** is proposed only — nothing external was executed._

## What research found
- **repo:** https://github.com/STEP-Network/v0-politiske-annoncer
- **stack:** drizzle, neon, nextjs, react, tailwind, vercel
- **plugins in repo:** dev-tasks
- **summary:** —

## Lane (answers entry, fed to generate-instance)
- slug: `polads` · name: PolAds
- repos: ['https://github.com/STEP-Network/v0-politiske-annoncer'] · boards: ['2723505568']
- task plugin: `dev-tasks` · lane MCPs: ['neon', 'vercel', 'library', 'telegram', 'brain']

## Plugin manifest
- ✅ present — `dev-tasks` (repo)
- ➕ needed — `corridor` (cabinet-default)
- ➕ needed — `brain` (cabinet-default)

## Needs your approval (gated — NOT executed)
- **install-plugin** `corridor` — lane needs corridor (not present in repo)
- **install-plugin** `brain` — lane needs brain (not present in repo)

## Notes
- neon detected — set the lane's neon_project name in projects/<slug>.yml
- vercel/next detected — set the lane's vercel_project name

## Germline diffs (Captain applies — a loop can't edit its own authorizations)
```
# add to cabinet/mcp-scope.yml (GERMLINE — Captain applies):
    polads-ceo:
      mcps: [neon, vercel, library, telegram, brain]

# add to cabinet/officer-capabilities.conf (GERMLINE — Captain applies):
polads-ceo:deploys_code
polads-ceo:validates_deployments
polads-ceo:reviews_implementations
polads-ceo:logs_captain_decisions
```

## To hire this lane-CEO
After applying the germline diffs: `bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml` (or add `polads-ceo` to the roster). The role def is at `instance/agents/polads-ceo.md`.
