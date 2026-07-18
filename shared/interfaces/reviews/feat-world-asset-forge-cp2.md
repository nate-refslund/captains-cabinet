# Review — world-asset-forge cp2: forge lane (2026-07-18)

Change: the asset PRODUCTION MACHINE's second half — the forge. Batch is
>300 lines (FW-019), so this artifact rides the commit. Sibling lane's
spec-gen landed at cp1 (350afcd5); this checkpoint completes the wave's
tool pair.

## Files

New:
- `cabinet/scripts/world-asset-forge.py` (993 L) — PixelLab.ai
  sprite-candidate forge. Worklist + one-off modes; N candidates/entry
  (default 2; pilot ~1/3 one-shot usable ⇒ human pick, never
  auto-accept); HARD `--limit` spend guard (default 10; over-limit runs
  refused with the exact arithmetic BEFORE any key load, API call, or
  write); per-canvas-size style collage from `--style-dir` (pilot-proven:
  style_image must EXACTLY match the canvas), prebuilt `--style-image`
  NEAREST-auto-fit + sidecar-recorded; `--palette` strip rides the API as
  color_image AND is the post-quantize target (nearest-RGB on alpha>0,
  alpha bytes preserved); strip derivable from `--style-dir` (top-64
  opaque, deterministic); PNG-magic refusal on API payloads; 16px grid
  check (off-grid written + flagged); realpath jail + install-mirrored id
  sanitize on every write; provenance sidecars with a gate-shaped
  `manifest_row` (`license: "owned — org-original"`); `--dry-run` (zero
  calls, zero writes; reports key SOURCE only); bounded retries on
  429/5xx; 4xx surfaced verbatim + actionable size-mismatch hint.
  Secrets: env `PIXELLAB_API_KEY` else `~/.pixellab-api-key`,
  runtime-only, redacted from every error path, never in sidecars;
  single `_post_json` stdlib-urllib seam (requests not installed).
- `cabinet/scripts/tests/test_world_asset_forge.py` (570 L, 29 tests) —
  HTTP fully mocked at the seam; autouse hermetic fixture (tmp HOME, env
  key cleared, transport primitive replaced with a raiser so real HTTP is
  impossible); synthetic key only ('test-key-123'); key-leak byte-scan
  over stdout+stderr+every output file; spend guard both sides; collage
  exactly canvas-sized (direct + via payload); quantize
  only-strip-colors + alpha preserved; non-PNG refusal (nothing
  written); off-grid flag (written + flagged); traversal jail (sanitize,
  jail-with-sanitize-defeated, end-to-end worklist id); bounded retries
  + 4xx verbatim + hint; canonical-worklist-shape end-to-end; gate-shape
  proven by running world-asset-gate.py `png_dimensions` over written
  candidates and matching the sidecar manifest_row.
- `docs/runbooks/world-asset-forge.md` (119 L) — commands (spec +
  forge), per-phase artist export, spend guard, key sourcing,
  style/palette contract (palette.json = the judge's histogram, NOT a
  palette), acceptance law verbatim, exit codes, failure modes.

## Reality notes (work order: follow reality and note it)

- Canonical worklist v1 carries `meaning` + structured fields
  (`era_word`/`rung_state`/`object`) and a `size:{w,h}` px dict — no
  prose description, no size_hint. The forge synthesizes prompts
  deterministically from those fields (explicit `prompt`/`description`
  wins when present).
- One designed `size: null` cross-ref row (`anim.voyage.harbor_boat`,
  "no new art" — reuses harbor_boat families): skip-with-warn under a
  glob, refuse when named exactly, refuse when a selection skips to
  empty. `covered_by` entries forge with a duplicate-spend warning.
- `.gitignore` line `cabinet/scripts/world-asset-forge-out/` NOT in this
  batch: the live tree's `.gitignore` is dirty (another wave's staged
  governance-labels change) — blocked-dirty per doctrine. The line is
  documented in the runbook and handed back for a follow-up landing.

## Verification evidence (python3.12, worktree on 350afcd5)

- `python3.12 -m pytest cabinet/scripts/tests/test_world_asset_forge.py -q`
  → 29 passed.
- Cross-lane integration dry-run against the COMMITTED canon:
  `world-asset-forge.py --entry '*' --dry-run` → rc=0, 370/371 entries
  planned, 1 designed skip, "planned API calls: 740 — EXCEEDS --limit
  10: a real run would REFUSE", zero calls, zero writes.
- `world-asset-gate.py`: LIVE tree GREEN (assets=2407 — all conformant);
  this wave changes no manifest (worktree red is 100% license-absent
  gitignored LimeZu binaries, pre-existing by design).
- `check-layer-separation.sh`: baseline=24 allowlist=19 current=43
  new=0 — OK.
- Corridor analyzePlan on the build plan: guardrails matched
  (runtime-only secrets + redaction, realpath jail, hardened HTTP seam
  with magic-byte validation); no new findings.

## Risks

PixelLab field names beyond the pilot-proven set (notably `/v1/rotate`)
are best-effort — isolated in `_build_*_payload` for cheap correction
against live docs. The forge writes only its gitignored out-dir;
promotion stays human via world-asset-install/world-asset-gate.
