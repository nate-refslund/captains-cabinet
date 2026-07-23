# Checkpoint review — feat/cog4-contract, cp1 (COG-4 contract landing)

**Scope (docs-only, one commit, >300 lines → FW-019 artifact required; this
is it):**
1. `docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` — the COG-4
   phase contract of record, copied BYTE-FOR-BYTE from the reviewed artifact
   (sha256-verified against the panel-adjudicated rev-1 original).
2. `docs/proposals/germline-amendment-extension-manifest-organ-2026-07-23.md`
   — the §4.5 germline amendment proposal (CG-33): complete proposed edit
   text for BOTH files of the extension gate pair
   (`framework/schemas/extension-manifest.schema.json` +
   `cabinet/scripts/validate-extension.sh`), mirroring the CG-4
   manifest-sunset precedent's structure; one-revert rollback (itself
   Captain-windowed); NO germline file is touched by this commit.
3. `docs/plans/operative-egg-ledger-2026-07-07.yml` — COG-4 row flipped
   todo → in-flight (last_update 2026-07-23, note gains the
   contract-of-record reference, appended not rewritten); NEW CG-33 row
   (captain-gated) appended after CG-32, modeled on CG-4's field shape.
4. `docs/plans/operative-egg-plan-2026-07-07.md` — §9 COG-4 table row
   flipped to in-flight + contract reference; CG-33 table row added beside
   the other CG rows (A13 parity).

**Review chain of record (the contract is the reviewed artifact — this
landing changes none of its bytes):** 8-reader premise-check workflow
`wf_8625da64-a2a` (7 ground readers + synthesis) verdict READY-TO-PLAN,
adversarial attack UPHOLD (3 serious + 4 minor mandatory items MR1-MR7, each
with a named in-text resolution) → four-lens plan-attack panel (4 MF + 9
SF/notes, ALL orchestrator-adjudicated, applied in place as rev-1) →
independent MF-verify verdict LAND (4/4 must-fixes byte-verified). Grounding
tip e7f95d5a, byte-verified anchors.

**Germline handback note:** COG-4's ONLY germline surface is the extension
gate pair (schg-locked, `germline-lock.sh` FILES[] :128-129). This landing
FILES the handback at maximum lead time (proposal doc + CG-33 ledger row +
plan-doc twin) — Captain action at convenience; the actual edit is the W4
Captain-windowed micro-unit with same-day relock; if the window has not
opened when W4 lands, dependent organ-validation units PARK with dated
markers. Nothing here edits or works around an schg path.

**Gates run before commit:** A13 parity gate green; ledger-status-parity.sh
green; duplicate-YAML-key grep clean on touched rows; HEAD-bytes YAML parse
after `git add`; amendment-doc lint green with the new proposal in the
union.

Provenance: per the 2026-07-07 full-autonomy grant + the Captain 2026-07-20
cognitive-masterplan grant. Landing agent on Fable 5 (judgment-tier pin).
