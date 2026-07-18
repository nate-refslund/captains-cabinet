# Review — world-asset-forge cp1: spec-gen lane (2026-07-18)

Change: the asset PRODUCTION MACHINE's first half — spec-gen. A palette-
agnostic worklist generator that turns the REAL world grammar (growth-
ladders / morphology / show-grammar, parsed live — never a hardcoded copy)
into the canonical asset checklist consumed by BOTH the artist (per-phase
checklist via `--eras`; one era = one phase) and the forge (machine
worklist). Batch is >300 lines (FW-019), so this artifact rides the commit.
The forge half (world-asset-forge.py + its tests + runbook + .gitignore
line) lands in the sibling lane's checkpoint.

## Files

New:
- `cabinet/scripts/world-asset-spec.py` (863 L) — generator CLI.
  Pre-flights the ladders file through the REAL
  `world-growth-validate.py` (loaded via importlib; its
  ERA_NAMES/MODES/CLASSES constants reused, never re-hardcoded); refusal
  ⇒ exit 2, nothing written.
- `cabinet/world/asset-worklist-supplement.yml` (174 L) — curated DATA
  overlay: art-brief district map (all 29 ladders + all 30 non-meta
  morphology ids), ladder-coverage map (11 dual-view suppressions),
  artist meanings, canvas-size/frame hints. Captain-tunable values;
  validated against closed enums / real ladder ids / the 16-px grid.
- `cabinet/world/asset-worklist.json` (415 L) — TRACKED generated canon:
  schema `cabinet.world.asset-worklist/v1`, sources sha256-pinned,
  counts, 371 one-line entries (313 ladder + 30 morphology + 28
  animation; 44 day-0, 5 staged-priority, 12 covered/no-new-art).
- `cabinet/world/asset-checklist.md` (767 L) — TRACKED generated artist
  checklist: Phase 1 village core → 2 harbor → 3 law/observatory/fields
  → 4 services → 5 UI & props, ship estate + animation families as
  separate sections; 371 checkbox rows carrying id, era word, rung
  state, day-0 flag, suggested canvas, meaning.
- `cabinet/scripts/tests/test_world_asset_spec.py` (281 L, 14 tests) +
  3 golden fixtures under
  `cabinet/scripts/tests/fixtures/world-asset-spec/` (the mini ladders
  fixture passes the REAL growth validator).
- this artifact.

No edits to any existing file. No manifest change; no live-fleet or
runtime touch; no secrets surface (spec-gen makes zero HTTP calls and
reads no credentials).

## Law properties (test-pinned)

1. **Truth gate reuse** — generation refuses (exit 2, no output files)
   when `world-growth-validate.py` refuses the ladders file
   (`test_preflight_refuses_malformed_ladders`).
2. **Schema-drift honesty** — unknown keys WARN to stderr, generation
   proceeds; missing required keys REFUSE (`test_unknown_key_warns…`,
   `test_missing_required_key_errors`).
3. **Expansion law** (spec v2 §15.1–15.3 — ERA styles, RUNG measures):
   per-ladder era dedupe into families; mode-aware rung expansion
   (tier/flag/per_lane = family × rung; count = one per family,
   "rendered N×"); literal `none` rungs skipped (bare_pole/dark_cairn
   etc. kept as real art); meta axis morphology entries excluded;
   covered_by suppression (no duplicate art for dual-view surfaces);
   staged/dark ⇒ STAGED-priority flags (`test_expansion_ids_modes_and_flags`).
4. **Determinism** — byte-identical across runs, no timestamps/RNG
   (`test_determinism_byte_identical`; regenerate-and-diff verified in
   the worktree: sha256 stable across two live runs).
5. **Canon protection** — `--eras` filtered runs refuse the canonical
   default output paths (`test_era_filter_refuses_canonical_default_paths`).
6. **Path/id hygiene** — every id token slugified to `[a-z0-9_]` (the
   downstream forge can never receive traversal-capable ids); sizes
   validated as positive 16-px grid multiples; supplement coverage
   targets validated against real ladder ids
   (`test_supplement_untruthful_coverage_refused`,
   `test_supplement_off_grid_size_refused`).

## Verification (2026-07-18, worktree @ 345461c0)

- `python3.12 -m pytest cabinet/scripts/tests/test_world_asset_spec.py -q`
  → 14 passed.
- `python3.12 cabinet/scripts/world-growth-validate.py` → OK, 29 ladders.
- Generator run: 313+30+28 = 371 entries, zero drift warnings on the
  real grammar files; camp-phase artist export smoke-tested.
- `world-asset-gate.py` → GREEN against the real asset root (2407
  conformant; manifest untouched by this lane).
- `check-layer-separation.sh` → 0 new violations.
