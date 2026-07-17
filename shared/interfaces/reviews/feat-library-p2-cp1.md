# Review artifact — feat/library-p2 cp1 (FW-019)

Integration landing of the Library phase-2 wave: TWO reviewed lane diffs
(identity-graph + search) from one clean worktree off origin/master
`f75648df`, by the library-phase2 integrator (2026-07-17, per the
2026-07-07 full-autonomy grant; Captain 3-question ratification
2026-07-17). Ledger rows in this commit: `LIB-IDENTITY-GRAPH-1` (rode the
identity lane diff) + `LIBRARY-P2-1` (wave row, this integrator).

## Review lineage (upstream of this commit)

Both landed lanes ran the full wave protocol: builder → 2 adversarial
Fable lenses (security + correctness-doctrine) → fix lane closing every
finding → independent re-verify (probes re-run + one mutant each proving
test teeth). Findings closed upstream include: graph hover-tooltip
stored-XSS (escaped + negative-controlled), corpus-amplified quadratic
wikilink-parse DoS (linear guards + caps + timing pins), vault-rename
ratchet unstaged-state artifact (identity's ALLOWED entry), embed
wire-text parity break vs the shell engine (proven live, fixed), db.ts
sslmode, q-length cap, and the /vault link-target ordering note.

## What this commit contains

- IDENTITY: `/library` IS the vault reader (catch-all moved from
  `/vault`; `/vault` = redirect alias; retirement notice → History note;
  ONE Library nav entry, ADVANCED_NAV pin 19).
- GRAPH+BACKLINKS: filesystem wikilink graph at `/library/graph` +
  per-note backlinks — zero API routes, zero DB.
- SEARCH: GET `/api/library/search` over cabinet_memory (parameterized
  binds, org-knowledge classes, sliding-window rate limit, cookie-gated)
  + `LibrarySearch` box on the Library root + consumer card rewired.
- The retired STORE stays retired (zero-DB route tree source contract).

## Integration deltas (beyond the two reviewed diffs)

1. Search's retirement-notice-page hunk superseded: the identity lane
   deletes that page; the search card is mounted on the catch-all ROOT
   view instead (`[[...path]]/page.tsx` DirectoryView, isRoot branch) —
   the search runbook's own integration instruction.
2. `VAULT_NOTE_BASE` flipped `'/vault'` → `'/library'` + the 3 href test
   pins in `library-search.test.tsx` — the exact flip the search lane's
   LINK-TARGET NOTE prescribed for this landing order.
3. `middleware.test.ts` same-anchor 3-way conflict resolved by keeping
   BOTH lanes' cookie-gate tests (identity: `/library` + deep paths +
   graph; search: `GET /api/library/search`).
4. `test_vault_rename_ratchet.py` ALLOWED entries for the search lane's
   6 `product_brain`-token files — the token is the live cabinet_memory
   `source_type` ENUM VALUE (the CG-30 hook writes vault notes AS
   `source_type=product_brain`): DB row data, not a path. The search lane
   never ran the ratchet with its files tracked (same unstaged-state
   artifact class the identity review caught on its own lane).
5. Docs refreshed to the landed link target (search runbook LINK-TARGET
   NOTE rewritten to the landed state; consumer + memory-search comments)
   and one docs-sweep fix (runbook example path → the real
   `vault/architecture.md`).

## NOT in this commit — world-library lane HELD

The world-library lane has NO review verdict on record: both lens
reviewers and its fix agent died to the session limit; the re-dispatched
review completed its legwork (tip-context check, patched-clone suites,
aesthetic mechanical re-run) and died before emitting the verdict.
Blocked lane must not hold identity/search hostage (wave design), so
`/api/world/library/*`, the world Library card, and the engine-client
hook ship NOTHING here. Lane diff + aesthetic-harness artifacts preserved
in the wave scratchpad (`libp2/world-library/`); it needs a
verdict-bearing review, then its own landing pass.

## Gates at landing (this worktree)

- dashboard: npm ci 0 vulnerabilities; vitest 117 files / 2153 tests
  passed + 1 env-gated live-parity skip; `tsc --noEmit` clean — includes
  both lanes' negative controls (graph confinement / tooltip-XSS / ReDoS
  timing; SQL bind-param injection controls / snippet-XSS React-text-node
  pins / rate-limit / middleware cookie-gates) and the flipped `/library`
  href pins.
- docs-track-code-sweep GREEN (files=50 findings=0).
- check-layer-separation new=0 (baseline=24 allowlist=18 current=42).
- full `cabinet/scripts/tests` (python3.12): 1532 passed / 5 skipped /
  2 failed → (a) rename ratchet, closed by delta 4 (targeted 12 passed /
  1 skipped; full re-run CONFIRMED 1533 passed / 5 skipped / 1 failed —
  only (b) remains); (b)
  `test_evidence_seam_bypass_replay[evidence-access.sh]` REPRODUCED on a
  PRISTINE detached worktree at `f75648df` — the pre-existing local-env
  condition VAULT-BROWSE-1 recorded, surface untouched by this wave; CI
  on the landing push is the authority.
- Ledger gates: A13 parity + id-uniqueness + ledger-status-parity GREEN
  pre (330) and post (331) edit.
- SCHG guard: `ls -lO` clean over every touched path (no schg/uchg);
  germline boundary armed (78 locked) and disjoint from this diff.
