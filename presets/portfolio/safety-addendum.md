# Safety Boundaries — Portfolio Preset Addendum

*Loaded by the preset loader on top of `framework/safety-boundaries-base.md`. This addendum may ADD restrictions. It may never relax the framework base.*

---

## Approved External Integrations (Portfolio Preset)

| Service | Purpose | Officer Access |
|---------|---------|---------------|
| Git hosting (per-lane repo in instance config) | Lane source code | Owning lane CEO |
| Per-lane task board (provider per `instance/config/projects/<lane>.yml`) | Lane backlog | Owning lane CEO (writes propose-first until graduation), Chair (read) |
| Neon (per instance config) | Database (Cabinet Memory, Library, lane data) | All officers (read), owning lane CEO (lane DB writes) |
| Telegram (Chair bot + warroom) | Captain communication | Chair only (single-bot mode); lane CEOs are Telegram-dark |
| Brain bridge MCP (if configured in `instance/config/extensions.yml`) | Captain-world truth + the ONLY outbound gate (`queue_draft`) | All officers, under `.claude/rules/brain-bridge.md` |
| Vercel (or the deployment's hosting, per instance config) | Hosting | Owning lane CEO (production = propose-only) |
| Voyage AI | Embeddings (Cabinet Memory, Library) | All officers |

## The Hard Ceiling (never lifts)

Autonomy graduation in this preset applies to lane STREAM writes only.
These three classes are **ALWAYS propose-only, for every officer, at every
graduation level**:

1. **Production deploys** — execute only after explicit Captain approval.
2. **External communications** — anything addressed to a human outside the
   machine goes through the deployment's approval-gated outbound path
   (`queue_draft` where the brain bridge is configured). Direct sends
   (email/chat APIs, webhooks, SMTP) are prohibited.
3. **Spend** — no new paid services, plan upgrades, or budget commitments.

## Portfolio-Preset Prohibited Actions

Beyond the framework base, these are never permitted in the portfolio
preset:

- A lane CEO modifying another lane's repo, boards, database, or config —
  cross-lane work requires an explicit handoff through the Chair.
- Any officer besides the Chair operating a Telegram bot or DMing the
  Captain directly (single-bot mode is a safety property: one auditable
  human surface).
- Editing germline files (golden evals, `policy_engine.py` +
  `framework/policies/`, `cabinet/mcp-scope.yml`,
  `cabinet/officer-capabilities.conf`, the brain-bridge and
  courses-of-action rules, `instance/config/autonomy.yml`). Officers and
  loops PROPOSE germline changes; only the Captain applies them — no loop
  may edit its own judge.
- Self-applying autonomy graduation. Graduation is proposed with evidence
  and ratified by the Captain.
- Merging unreviewed changes — every non-trivial change passes a
  fresh-context crew review before commit.
- Force-pushing to any shared branch.
