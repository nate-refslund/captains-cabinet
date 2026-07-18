# Review — world-asset-intake cp1: artist-delivery intake (2026-07-18)

Change: the asset production machine's RECEIVING half (Wave 4; spec-gen +
forge landed in Wave 3). The onboarded artist (Phase-0 style bible ~Aug
18–21) delivers batches of transparent PNGs named by canonical worklist
entry id; `world-asset-intake.py` validates each file, writes machine +
human reports with exact artist-actionable reasons, composes a
deterministic conformance test scene, and — only on explicit `--promote`
— installs accepted sprites into the tracked asset tree with
content-addressed manifest rows. Batch is >300 changed lines (FW-019),
so this artifact rides the commit.

## Files

New:
- `cabinet/scripts/world-asset-intake.py` (884 L) — intake CLI.
  Validation per file: filename stem must EXACTLY equal a worklist id
  (charset `[A-Za-z0-9._-]` — all 371 canonical ids verified to it, so
  no path separator/traversal can ride a filename; unknown ids get
  difflib did-you-mean suggestions) · `covered_by` rows refuse (no new
  art — family supplied elsewhere) · `size:null` cross-refs refuse ·
  `staged` accepts with a note · PNG magic + IHDR dims BEFORE any pixel
  decode (2048px decompression-bomb bound) · dims must equal entry
  `size` {w,h}; ANIMATED entries expect ONE horizontal strip
  `(w×frames)×h` (install `_sheetN` convention) · 16px grid law · alpha
  channel required · stray-halo scan (semi-transparent alpha 1..254
  4-adjacent to alpha==0; > `--halo-max` (8) fails with coordinates) ·
  optional `--palette` exact-RGB membership over alpha>0 pixels
  (off-palette hex + count + first coordinate; > `--palette-max` (0)
  fails). Reports: `report.json` (schema
  `cabinet.world.intake-report/v1`, sorted keys) + `report.md` +
  deterministic `test-scene.png` (neutral 2-gray checker — conformance
  sheet, not world art). `--gate` runs the committed
  `world-aesthetic-gate.py --mechanical` over the scene via a single
  mockable subprocess seam (argv list, never shell) and folds the
  envelope in as INFORMATIONAL (the `generated` timestamp and abs-path
  `inputs` are dropped — determinism law: no timestamps/RNG in outputs).
  `--promote` is two-phase (every destination jail-checked + source
  re-hashed before ANYTHING is copied), copies delivered bytes VERBATIM
  into `originals/<object>/<id>.png`, and upserts manifest rows in
  world-asset-install.py's exact shape/serialization
  ({id,path,w,h,grid,sha256,pack,license}; indent=1, ensure_ascii=False,
  trailing newline; `version`/`_doc` never touched). Exit codes: 0 all
  accepted · 1 any fix_needed (reports still written) · 2 usage/promote
  refusal.
- `cabinet/scripts/tests/test_world_asset_intake.py` (621 L, 32 tests) —
  synthetic PIL fixtures only (never licensed pixels), zero network,
  in-process `main(argv)`, tmp asset roots via explicit flags, house
  importlib-by-path load. Covers: unknown-id suggestion · nested-dir /
  non-png / dotfile handling · empty-delivery refusal · static +
  animated-strip size reasons (expected-vs-actual wording) · off-grid ·
  RGB-no-alpha · non-PNG magic · halo over/within/tightened thresholds
  with coordinate assertions · palette hex/count/first + tolerance +
  skip-when-absent · covered_by / size:null / staged gates · report
  schema + BYTE-determinism across reruns (json/md/scene) · scene
  checker/grid/compositing · gate seam mocked (timestamp dropped,
  verdict informational) + one REAL wrapper smoke run · promote:
  report-only never touches manifest/assets, plain-promote refusal on
  any failure, accepted-only subset, exact install row shape + verbatim
  bytes + untouched version/_doc, idempotent re-promote (replaces, not
  duplicates), `world-asset-gate.py` GREEN over the promoted temp tree,
  containment refusal with sanitize defeated (nothing copied), missing
  manifest refusal · .gitignore negation guard · no-network-imports
  guard.
- this artifact.

Edits:
- `.gitignore` (+4) — `!cabinet/dashboard/public/world-assets/originals/`
  after the world-assets ignore pair. Mechanism: `world-assets/*` matches
  direct children only, so re-including `originals/` makes its
  descendants trackable; PROVEN in-worktree (`git check-ignore` probe:
  originals/ file not ignored; `interiors/` + `staged-future/` still
  ignored).
- `cabinet/scripts/world-asset-gate.py` (docstring only) — "asset dir is
  gitignored" now carries the originals/ exception clause.
- `cabinet/dashboard/public/world-assets/manifest.json` — ONE `_doc`
  sentence (originals/ rows are owned, committable); re-serialized with
  the install writer; diff verified to touch exactly the `_doc` line.
- `docs/runbooks/world-asset-forge.md` (+65/-2) — intro "Two tools" →
  "Three tools" + new `## 8 — Intake (artist delivery)` (CLI, validation
  rules incl. animated-strip + halo/palette thresholds, report
  locations, promote semantics + originals/ committability, the
  gate-informational caveat).

## Mission-vs-reality corrections honored (per Wave-4 recon)

1. Worklist has NO `size_hint`/`family` fields: `size` {w,h} +
   `animated`+`frames` drive expected dims; promote dir key is
   `entry["object"]` (68 tokens, all `[a-z0-9_]`, still sanitized +
   containment-checked).
2. License string: mission draft said "original-owned"; the repo
   precedent is `owned — org-original` (world-asset-forge.py:94, runbook
   §6 manifest_row template) — precedent kept for single-string grep
   coherence. One-line constant change if the Captain wants the literal.

## Verification (real runs, this worktree @ origin/master a8d603b0)

- `python3.12 -m pytest cabinet/scripts/tests/test_world_asset_intake.py
  cabinet/scripts/tests/test_world_asset_forge.py
  cabinet/scripts/tests/test_world_asset_spec.py -q` → 75 passed.
- Full `cabinet/scripts/tests/` battery: 1636 passed, 5 skipped, 2
  failed — triaged against a PRISTINE origin/master worktree:
  `test_evidence_seam_bypass_replay[evidence-access.sh]` fails
  IDENTICALLY on untouched master (pre-existing local-environment
  failure, not this change; CI is the authority);
  `test_docs_sweep::test_real_script_green_on_real_repo` failed only
  while the new tool was untracked (the sweep's existence oracle is
  `git ls-files --cached`) and is GREEN with the files staged.
- `bash cabinet/scripts/check-layer-separation.sh` → new=0 (intake names
  no product/person tokens).
- Manual e2e against the REAL 371-entry worklist: 6-file synthetic batch
  (static 96×96, animated 2f strip 64×32, covered_by, staged, wrong-id
  ×2) → report-only (3 accepted/3 fix, did-you-mean suggestions, real
  `--gate` run folded exit 1 informational with honest map-gate skips) →
  plain `--promote` REFUSED exit 2 nothing copied → 
  `--promote-accepted-only` installed 3 under `originals/<object>/` →
  `world-asset-gate.py` over the scratch manifest: WORLD_ASSETS GREEN.

## Risk notes

- The aesthetic `--gate` fold is informational BY DESIGN (committed
  calibration is LimeZu-fitted; report + runbook both say so) — it can
  never flip accepted→fix_needed, so it cannot block the artist loop.
- Report-only mode provably never opens the manifest for write nor
  creates dirs under the asset root (tested byte-for-byte).
- No live-fleet/runtime touch; no ledger row named for this wave
  (ledger untouched; A13 not in play).
