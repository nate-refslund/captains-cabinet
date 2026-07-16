# Review — claude-md-rewrite cp1 (2026-07-16)

Change: CLAUDE.md total rewrite 318→56 lines (Captain directive 2026-07-16:
"EXTREMELY short while very effective"), captain-agnostic by construction;
CLAUDE-egg.md twin now byte-identical body + header comment; three per-model
prompt style cards added at `.claude/model-cards/` (opus-4-8, fable-5,
sonnet-5 — each cites its Anthropic source URL + cache date); repo-wide
Captain-brevity register added to CLAUDE.md ("Talking to the Captain") and
backported generically to `presets/portfolio/agents/cos.md`; stale
cross-refs to old headings fixed (CONTRIBUTING.md, cabinet-bootstrap.sh,
bootstrap-captain-triplet.sh, framework/env.py docstring,
instance/config/platform.yml comments); ledger R132 noted (status unchanged,
still captain-gated on the CG-3 assembly question).

Method: recon agent mapped the ecosystem first (loaders, enforcement,
egg-twin swap, collisions — ~72-75% of the old file was enforced elsewhere,
duplicated in always-loaded artifacts, or pointer inflation). Rewrite kept
only non-inferable, non-enforced content per Anthropic's CLAUDE.md guidance
(<200 lines; "would removing this cause a mistake?"; positive imperatives;
scope stated for literal models). Reference:
cabinet-meta designs/model-prompting-reference-2026-07-16.md.

Two independent adversarial reviews (fresh-context agents), findings applied:

1. Dropped-rule regression hunt (old file rule-by-rule vs draft, enforcement
   verified by reading hooks/CI/constitution, not assumed):
   - Keep-list floor of 22 load-bearing rules: ALL present post-fix.
   - REGRESSION (restored): Linear read-only archive "never write" — on-trigger
     skills still instruct Linear writes; the always-loaded counter-instruction
     was load-bearing. Now in "Keep the trackers honest".
   - REGRESSION (restored): research persistence (search prior briefs /
     embed with decay tag) — only mechanism making research reusable; dormant
     but bites on re-enable. Now in "Do the work".
   - Weakening (restored): Tier-3 location (`memory/tier3/` / pgvector).
   - Cleared-as-intended cuts verified enforced/duplicated: role-def edit ban
     (constitution + evolution-loop), agent-teams quota gotcha (skill),
     decision gold-label (post-tool-use hook), last-run stamping (loop skills),
     briefing-leads-with-founder-actions (cos role + synthesis), MCP founder
     setup (cabinet-init skill), Notion hub map (lane configs), trigger-wake
     mechanics (MCP + hook), channel model (constitution).

2. Path-existence + egg-safety + literal-clarity:
   - Every named path/script/key resolves at HEAD; `.claude/model-cards/`
     created in this commit; `shared/interfaces/tech-radar.md` gitignored but
     sweep-allowlisted (pre-existing).
   - Egg-safety: no captain names, home paths, product/org tokens, board ids,
     domains. One gendered pronoun for the Captain fixed to "they".
   - Literal-clarity fixes applied: ledger location `shared/interfaces/`
     named; "delete" restored to docs-track trigger list; founder-action
     artifact named; killswitch "Redis key" restored; heading kept as
     "Model Routing" so existing refs (platform.yml:250,
     agent-team-workflow.md:36 + packs twin) stay valid with zero edits to
     hook-protected skill files.

Known deferred (not in this commit):
- `cabinet/scripts/hooks/session-start.sh:8,132` stale "items 7/10/11"
  comments — file is schg-locked (germline); fix queued for the next unlock
  window (handback recorded in cabinet-meta).
- Pre-existing stale refs not created by this change:
  cabinet/docs/cabinet-slash-commands.md:52,69 ("per CLAUDE.md" /verify +
  Sonnet-4.6 claims predate this rewrite), run-golden-evals.sh:388 comment.

Verdict: APPROVE. Keep-list floor intact, regressions restored, twin in
lockstep, egg swap test satisfied (header line 1 carries "CLAUDE-egg.md").
