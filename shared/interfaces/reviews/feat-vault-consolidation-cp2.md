# Checkpoint review — feat/vault-consolidation cp2 (library-retire lane)

**Date:** 2026-07-17 · **Reviewer:** vault-consolidation integrator (Fable 5)
· **Scope:** the reviewed `library-retire` lane diff (50 files, builder's 34
+ 16 fix-pass, all 7 upstream review findings closed; +1758/−3147) + the
integrator's cross-lane seam fixes + ledger rows LIB-RETIRE-1/CG-29 +
supersede notes (R084, R098, AUD-12, R086) + plan-doc §38 rows.

## What this checkpoint lands

Library retirement (Captain-ratified 2026-07-16; runbook of record
`docs/runbooks/library-retirement-2026-07-16.md`): the `library` MCP server
deregistered from BOTH `.mcp.json` layers (both verified UNLOCKED on the
live box — no schg flag; `cabinet/mcp-scope.yml` deliberately untouched,
its dangling grants are inert while the server is unregistered); dashboard
`/library` surfaces become retirement stubs; `lib/library.sh` writes go
vector-free; schema stays in place, dormant (no destructive DDL);
`retire-library-export.py` archives records → `<root>/vault/library-archive/`.
Staged germline ceremony package (comment-only start-officer-mac.sh patch +
addendum) rides `docs/proposals/` with egg `expect-absent` rows; CG-29 filed
as the ceremony handback per the addendum's own contract.

## Export script security posture (Corridor guardrails matched pre-landing)

Fixed SELECT only — no variable of any provenance concatenated into SQL;
psql invoked with `default_transaction_read_only=on`, fixed argv, no shell;
DB content treated as untrusted (JSON transport; YAML frontmatter values
JSON-serialized; filename slugs whitelisted `[a-z0-9-]`; every write path
containment-checked under the archive root; markdown body written as data).
Missing DATABASE_URL/NEON_CONNECTION_STRING → LOUD stderr skip, exit 0,
psql never invoked — reproduced on this worktree. **The export was NOT run
against any DB in this landing** — the orchestrator executes it on the box.

## Cross-lane seam (the integration finding this cp exists for)

The lane was regenerated against a pre-rename tip; landing it AFTER VAULT-1
tripped `test_vault_rename_ratchet.py::test_no_undeclared_product_brain_references`
with 10 offender files. Disposition, each deliberate:

- **Finished to vault/** (transitional "until the vault rename lands" copy,
  stale at birth once the rename landed first): `CLAUDE.md`,
  `docs/templates/CLAUDE-egg.md`, `cabinet/channels/library-mcp/README.md`,
  `library/page.tsx` stub copy.
- **Declared in the ratchet's reasoned ALLOWED list** (genuine dual-root
  back-compat seams — un-migrated deployment roots may carry the legacy dir
  name): `.gitignore` archive rules, `retire-library-export.py` fallback,
  `test_retire_library_export.py`, `test_library_retirement_ratchet.py`,
  `docs/runbooks/library-retirement-2026-07-16.md`.
- **`shared/interfaces/reviews/` added to HISTORICAL_PREFIXES**: checkpoint
  artifacts are dated records of the batch as reviewed — the vault wave's
  own reviews necessarily name the rename; freezing them is the same
  construction as the docs/plans exclusion.

## Verification evidence (this worktree, after all fixes)

- Retirement + export + ratchet + egg suites: 62 passed, 1 skipped;
  `lib/tests` 6 passed (collected separately — same-named `tests` package
  collision is a known repo gotcha, recorded in both new gate_cmds).
- Full `cabinet/scripts/tests`: 1153 passed pre-fix run (sole fail was the
  ratchet seam above; re-verified green after) — full re-run again before
  push.
- Dashboard vitest: 101 files, 1766 passed (fresh `npm ci` in this
  worktree).
- `docs-track-code-sweep.sh` GREEN (files=41, findings=0) — the deleted
  library routes/components leave no dead references in living docs.
- `check-layer-separation.sh` new=0.
- A13 parity 321 ids · uniqueness 321 · ledger-status-parity GREEN
  (ids=321 md_rows=321 findings=0).
- Ledger discipline: old library rows R084/R098/AUD-12/R086 SUPERSEDE-NOTED
  (never deleted), statuses unchanged, `last_update` bumped in the same
  commit.

## Risks accepted at this checkpoint

- Dangling `library` grants in schg `cabinet/mcp-scope.yml` +
  `.claude/settings.json` until the CG-29 ceremony — inert by construction
  (unregistered server), policed appliable/comment-only by the ratchet.
- Dormant vector schema stays in the DB until the runbook's follow-up drop
  plan — deliberate (no destructive DDL in a landing wave).

Verdict: LAND.
