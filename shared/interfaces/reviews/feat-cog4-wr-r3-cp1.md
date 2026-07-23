# FW-019 review artifact — feat/cog4-wr-r3 cp1 (R3 weekly shadow-dividend report)

Unit: the R3 rider (BACKLOG :1561; COG-4 contract §18 WR lane) — a read-only
CLI turning the shadow objectives graph into a weekly plain-English Captain
report, plus its battery and the import-gate curation the new reader needs.

## Batch contents
- `cabinet/scripts/cog3-shadow-dividend.py` (new, ~460 lines): serve-surface-only
  consumer (`serve_graph`/`serve_objective`/`recommend` + `to_captain_word`;
  never opens the row store, never imports graph/cortex internals). Declared
  `--now` (no clock/env reads, no shelling out); deterministic bytes for fixed
  inputs. Report → `shared/interfaces/cognitive/shadow-dividend-<date>.md`
  (the shared/interfaces captain surface, atomic tmp+os.replace); last-report
  state → `cabinet/cache/shadow-dividend/state.json` (the `cabinet/cache/*`
  gitignored runtime convention). `ServeRefused` ⇒ loud refusal exit 2, no
  report, state untouched; missing graph ⇒ loud operator error exit 3.
- `cabinet/scripts/tests/test_cog3_shadow_dividend.py` (new, 13 tests):
  fixture-graph idiom (real cortex seed → real cog3-rebuild.py → real CLI as
  subprocess, every path injected); content sections; first-report / no-change
  / delta paths; byte determinism across PYTHONHASHSEED; tampered-rows refusal
  (exit 2, nothing written, state byte-untouched); missing-graph + non-canonical
  --now errors; R1 verdict-inbox cross-ref present/absent; jargon deny-list;
  purity + serve-surface source ratchets.
- `cabinet/scripts/cog2-import-gate.py` + `tests/test_cog3_import_gate.py`:
  curated `ALLOWLIST_EXACT_OBJECTIVES` grown by exactly the new reader (the
  designed curation act — gate + membership pin updated in the same commit;
  the reader is exempted as a sanctioned objectives reader in Check O and the
  data-plane sweep, same as the three COG-3 instruments).

## Review evidence (2026-07-23, scratch clone off de5d16c4)
- R3 battery: 13/13 green.
- `cabinet/scripts/tests` full suite: 2616 passed / 10 skipped / 3 failed —
  the 3 are the documented pre-existing rollback-ratchet full-clone class
  (phase-1/2/3 open-ended BASELINE..HEAD; fail identically on pristine
  de5d16c4; CI shallow-skips them). One transient sandbox-redis flake
  (test_killswitch_watchdog) appeared in exactly one of three full runs and
  passes isolated + paired with this battery — unrelated surface.
- `verify-cognitive-architecture.sh`: PASS — all 10 budgets at observed ≤ max,
  zero new layer-separation violations (no framework modules, no services
  rows, no action/event types added; no allowance row needed).
- Structural constraints held: no `cabinet/services.yml` rows; no `framework/`
  modules; graph read only through the public serve functions; cortex only
  inside the surface; no external sends (artifact on the repo-internal captain
  surface only); no edits to `framework/objectives` or `framework/cortex`.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Captain GO on the masterplan riders
2026-07-22/23.
