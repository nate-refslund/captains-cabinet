# Checkpoint review — feat/developer-preset cp1 (FW-019)

- **Wave:** presets/developer v1 — OPTIONAL software product-kind kit
  (Captain-ratified 2026-07-17; ledger row PRESET-DEV-1).
- **Baseline:** clean worktree off origin/master @2e04642e (live tree is
  BEHIND master and untouched; branch `feat/developer-preset`).
- **Scope reviewed:** full diff — new `presets/developer/` (flat copy of
  work + ratified deltas + kit content), new `packs/preset-developer-pack/`,
  new `cabinet/scripts/tests/test_preset_developer_parity.py`, additive
  `.mcp.json` entries, `framework/onboarding/plan.py` github-when-repo +
  tests, `generate-instance.py` optional `cabinet.preset` + tests,
  cabinet-init `SKILL.md` §3b, `probes.yml.example` caveat fix,
  marketplace/README rows, ledger + plan-doc rows.
- **Artifact naming note:** the pre-commit hook derives the required
  filename from the real branch slug (`feat-developer-preset`); the work
  order's assumed `feat-preset-developer-v1` name yielded to reality.

## Findings (all closed or explicitly deferred before commit)

1. **FIXED — copied files self-identified as work with work-path
   instructions.** `measurement/README.md` told a developer deployment to
   install the seed via `cp -R presets/work/measurement/...` and to run
   `pytest presets/work/measurement`; `schemas.sql` and
   `starter-spaces/business-brain.yml` headers named the work location
   (business-brain's own header said `--preset work`). Following those
   docs from the developer tree would install/seed from the WORK tree —
   byte-identical today, silent divergence risk tomorrow. Headers and
   instructions now name this location; files added to the parity test's
   ALLOWED_DELTA with reasons (docs-track-the-code).
2. **FIXED — validate.sh residue battery false-positives.** Bare `nate`
   substring-matched "coordinate"/"designate" (word-bounded now, same for
   `jfm`), and the battery's own pattern-definition line matched itself
   (script now excludes itself; the repo-level parity test sweeps
   validate.sh with a carrier-line filter so the rest of the script stays
   swept).
3. **FIXED — parity-test residue scans over-broad.** The corridor/brain
   plugin-id scans now cover CONFIG surfaces only (yml/json, non-comment
   lines — prose can name the exclusion, only config can wire a plugin;
   the shipped work preset.yml documents "corridor, brain belong to
   instance overlays" in a comment and the flat copy keeps it); the
   Space-naming allowance covers `product_brain`/`business_brain` template
   slugs; `.sh` files exempt from the UPPER_SNAKE `${...}` check (bash
   internals are not env declarations).
4. **VERIFIED — live-fleet inertness of the .mcp.json additions.** The
   three new servers are additive (parity test pins the six pre-existing
   entries byte-present) and DOUBLY Captain-gated for officers:
   `cabinet/mcp-scope.yml` carries no grants for github/neon-ro, and
   `.claude/settings.json` `permissions.allow` (schg) lists no
   `mcp__github`/`mcp__playwright`/`mcp__neon-ro`. Nothing becomes
   callable until a Captain germline window applies both — README step 3
   now says so explicitly. Env names resolve to nothing until
   `setup-env.sh` is run; a missing `GITHUB_PAT` fails the server closed.
5. **VERIFIED — docs-track-code sweep.** Local run reports n=2 findings,
   both references from the new pack docs to the new preset files: the
   sweep's existence oracle is `git ls-files --cached`, so untracked new
   targets read dead until staged — by the script's own design ("docs and
   their new target enter the same commit"). Re-verified n=0 after
   staging.
6. **DEFERRED (recorded in the ledger note) —** (a) dashboard onboarding
   API preset question: all four route files + evidence dir are
   schg-locked (`ls -lO` evidence taken); ceremony-gated, excluded from
   this wave. (b) Pinned third-party `@robinson_ai_systems/vercel-mcp`
   retirement: live fleet references `mcp__vercel` (work cto.md tools);
   separate ratification with a fleet-impact check. (c)
   `cabinet/services.yml` probe-vercel prose note still names the lifted
   `probe_vercel.TEAM_ID` constant — same stale-caveat class fixed in
   `probes.yml.example`, left for a services.yml-owning wave. (d)
   Flat-only composition debt: developer is the 4th preset with heavy
   work overlap — the 2026-04-16 "3+ presets share structure" revisit
   trigger; BACKLOG note goes to the orchestrator meta-workspace.

7. **FIXED — full-suite run caught a vault-rename ratchet collision
   (cp2).** `cabinet/scripts/tests` full run flagged
   `test_vault_rename_ratchet.py::test_no_undeclared_product_brain_references`:
   the spec's `product-brain.yml` Space filename/template is a NEW
   `product[-_]brain` compound, forbidden since the Captain-ratified
   2026-07-16 vault rename (product-brain/ → vault/; shrink-only
   allowlist, "any NEW file mentioning product-brain reds the build").
   Reality-wins deviation from the work order: shipped as
   `starter-spaces/product-journal.yml`, Space **Product Journal**,
   template `product_journal` — same 5 seed records, zero ratchet
   allowlist growth; all references (preset README, presets/README, pack
   README/SKILL, parity test, ledger + plan-doc rows) updated in the same
   commit. The ratchet matches compounds only, so the work preset's
   'Business Brain' and prose like "business brain" are unaffected.
   Also from the same full run:
   `test_evidence_seam_bypass_replay.py::test_shipped_catalog_harness_still_green[evidence-access.sh]`
   fails identically on the PRISTINE origin/master baseline @2e04642e
   (verified in a scratch checkout — pre-existing, unrelated to this
   diff; reported upward, not papered over).

## Gate evidence at review time (all run in the worktree, python3.12)

- `bash presets/developer/validate.sh` — PASSED (8 checks incl. the two
  new asserts).
- `python3.12 -m pytest presets/ cabinet/scripts/tests/test_preset_developer_parity.py cabinet/scripts/tests/test_generate_instance.py -q` — 93 passed
  (presets/ collection = 12: work 6 + developer 6 — the org-scenarios
  rename/collision proof).
- `python3.12 -m pytest framework/onboarding/tests/test_plan.py -q` — 13
  passed (collected separately: same-named tests packages collide in one
  collection).
- `bash cabinet/scripts/check-layer-separation.sh` — new=0 (baseline 24,
  allowlist 18, current 42).
- `bash cabinet/scripts/validate-extension.sh packs/preset-developer-pack`
  — manifest + paths + axis lint OK.
- `bash cabinet/scripts/seed-library.sh --preset developer --dry-run` —
  would-create Space 'Product Brain' + 5 records, business-brain records
  already present, nothing written (read-only against the Library; env
  sourced for the one command).
- `python3.12 -m json.tool` on `.mcp.json` + `.claude-plugin/marketplace.json`
  — parse clean; `yaml.safe_load` clean on preset.yml, terminology.yml,
  both starter-space files, starter/probes.yml, pack manifest.yml.
- A13 ledger↔plan parity gate — GREEN pre-edit and post-edit; ledger
  parses, 328 entries, ids unique.
- Residue battery over `presets/developer/` + `packs/preset-developer-pack/`
  — zero personal residue, zero corridor/brain plugin-id wiring, zero
  secret-shaped strings, all `${...}` placeholders UPPER_SNAKE.

## Verdict

Ship. Declarations-only law holds (env NAMES + URLs + markdown; no glue
code, no secrets, no scope auto-grants); the preset is OPT-IN end to end
(work stays every default); twin drift is pinned by test; the known gaps
are deliberate, recorded, and Captain-visible in the ledger row.
