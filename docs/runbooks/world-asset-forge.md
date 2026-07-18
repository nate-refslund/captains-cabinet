# World Asset Forge — PixelLab sprite-candidate runbook

**What this is (2026-07-17, Wave-3 asset-production machine):** the
palette-agnostic production pipeline that mass-produces original owned
sprite art the day the artist's Phase-0 master palette lands (~Aug 18–21).
Three tools:

- `cabinet/scripts/world-asset-spec.py` — turns the world grammar
  (growth-ladders / morphology / show-grammar) into the canonical asset
  worklist `cabinet/world/asset-worklist.json` + the human checklist
  `cabinet/world/asset-checklist.md` (deterministic, tracked).
- `cabinet/scripts/world-asset-forge.py` — generates N sprite CANDIDATES
  per worklist entry via the PixelLab.ai API into a gitignored review
  directory, with full provenance sidecars.
- `cabinet/scripts/world-asset-intake.py` — validates ARTIST-DELIVERED
  sprite batches against the worklist and (explicit `--promote` only)
  installs accepted originals with manifest rows (§8).

**Acceptance law (verbatim):** the forge never ingests; human accept via
the existing world-asset-install/world-asset-gate flow; candidates die in
the out-dir unless a human promotes them.

**Prerequisites:** `python3.12` with **Pillow** (`PIL` — required by the
forge tool and its tests; on this Mac it lives in user-site
`~/Library/Python/3.12`, CI installs it explicitly in the cabinet-ci
"Install test dependencies" step) and **PyYAML** (spec tool). Without
Pillow, `world-asset-forge.py` fails at import.

## 1 — Generate the worklist / artist checklists

    python3.12 cabinet/scripts/world-asset-spec.py     # regenerates both canon files

Per-phase artist checklist (one era = one phase):

    python3.12 cabinet/scripts/world-asset-spec.py --eras camp --out-md /tmp/phase-camp.md

See that tool's `--help` for the full surface. Its outputs are tracked and
deterministic — regenerate-and-diff is the freshness check.

## 2 — Forge candidates

    # dry-run FIRST: full request plan, zero API calls, zero writes
    python3.12 cabinet/scripts/world-asset-forge.py --entry 'ladder.flagpole.*' --dry-run

    # real run: 3 candidates each, style refs + palette strip
    python3.12 cabinet/scripts/world-asset-forge.py \
        --entry 'ladder.flagpole.*' --candidates 3 --limit 12 \
        --style-dir refs/owned-style/ --palette artist-master-strip.png

    # one-off (no worklist)
    python3.12 cabinet/scripts/world-asset-forge.py \
        --describe 'weathered oak harbor barrel' --size 32x32 --id barrel

Worklist prompts: canonical entries carry structured fields (`era_word`,
`rung_state`, `object`, `meaning`), not prose — the forge synthesizes the
prompt deterministically from them (an explicit `prompt`/`description`
field wins when present). Cross-ref rows with `size: null` (e.g.
`anim.voyage.harbor_boat` — no new art by design, reuses the harbor_boat
families) are skipped with a warn under a glob and refused when named
exactly. Entries whose art a ladder already owns (`covered_by`) forge with
a duplicate-spend warning.

## 3 — Spend guard (BINDING)

`--limit` (default **10**) hard-caps TOTAL API calls per invocation
(× 2 per candidate with `--rotate`). An over-limit run is REFUSED with the
exact arithmetic before any key load, API call, or write — never silently
truncated. Raising the cap is an explicit human act: re-run with
`--limit N`. Pilot calibration: ~1/3 of one-shot output was usable, hence
`--candidates` defaults to 2 and a human picks — the forge never
auto-accepts.

## 4 — API key

Runtime-only: env `PIXELLAB_API_KEY`, else `~/.pixellab-api-key` (single
line, chmod 600). Missing key = named HANDBACK, exit 4. The key is never
hardcoded, committed, logged, or written to sidecars; error paths redact
it; tests mock the HTTP seam — zero real API calls in CI.

## 5 — Style & palette contract

- `style_image` must EXACTLY match the output canvas size (pilot-proven;
  the API 400s otherwise). `--style-dir DIR` builds a deterministic
  per-canvas-size collage from local reference PNGs; a prebuilt
  `--style-image` is NEAREST-auto-fit per canvas (recorded in the sidecar
  as `style_resized_to_canvas`).
- `--palette STRIP.png` (alias `--palette-image`) rides the API as
  `color_image` (pilot-proven palette forcing) AND is the local
  post-quantize target (nearest-RGB on alpha>0 pixels; alpha bytes
  preserved). With `--style-dir` and no `--palette`, a strip is derived
  (top-64 most-frequent opaque colors, deterministic) and saved under
  `_refs/`.
- `cabinet/scripts/world-aesthetic/calibration/palette.json` is
  deliberately NOT consumed: it is the aesthetic judge's membership
  HISTOGRAM (554 five-bit quantized bins, lossy centers, fitted to the
  outgoing LimeZu estate) — not a drawing palette. When the artist's
  Phase-0 style bible lands (~Aug 18–21), the master palette becomes the
  standard `--palette` strip.

## 6 — Outputs & promotion

`<out>/<entry-id>/cand-N.png` + `cand-N.json` provenance sidecar: prompt,
request params, endpoint, sha256s (style collage / palette strip / png),
`response_meta` with image payloads stripped, the full worklist entry, and
a gate-shaped `manifest_row` `{id,path,w,h,grid,sha256,pack,license}`
prefilled with `license: "owned — org-original"`. The default out dir
`cabinet/scripts/world-asset-forge-out/` is pre-review runtime data and
must never be committed (gitignore line:
`cabinet/scripts/world-asset-forge-out/`).

Promotion = a human picks a winner → install via the world-asset-install
pattern (copy into the asset root → manifest row → `world-asset-gate.py`
GREEN). The sidecar's `manifest_row` is the row template; install re-homes
`path` inside the asset root.

## 7 — Exit codes & failure modes

`0` ok · `1` candidate failures/flags (non-PNG API payloads refused =
nothing written; off-grid results written + flagged for human review) ·
`2` usage / plan / spend-guard refusal · `4` key HANDBACK.

- 429/5xx → bounded retries (2 extra attempts, fixed sleep). 4xx →
  surfaced VERBATIM (key-redacted) plus an actionable hint for the
  pilot-known style_image-size-mismatch failure.
- `/v1/rotate` (`--rotate`, 8-direction variants, a 2nd API call per
  candidate) uses field names NOT re-verified against live docs — all
  payload builders are isolated in `_build_*_payload` for cheap
  correction. `/animate-with-text` and `/balance` are not wired yet.

## 8 — Intake (artist delivery)

`cabinet/scripts/world-asset-intake.py` is the RECEIVING half of the
loop: the onboarded artist delivers a batch of transparent PNGs — one
file per worklist entry, named `<entry-id>.png` (e.g.
`ladder.firepit.campfire.bare_ground.png`) — into a local folder, and
intake validates, reports, and (only on explicit `--promote`) installs.
Deterministic throughout: no timestamps, no RNG, no network — reports and
the test scene are byte-identical across reruns.

    # report-only (default): validate + write reports, touch nothing else
    python3.12 cabinet/scripts/world-asset-intake.py ~/deliveries/batch-01 \
        --palette artist-master-strip.png --gate

    # install accepted sprites + manifest rows, then gate the tree
    python3.12 cabinet/scripts/world-asset-intake.py ~/deliveries/batch-01 \
        --palette artist-master-strip.png --promote
    python3.12 cabinet/scripts/world-asset-gate.py

Validation per file (every failure carries an artist-readable reason —
coordinates, color hexes, expected-vs-actual sizes):

- filename stem must EXACTLY equal a worklist id (unknown ids get
  did-you-mean suggestions); `covered_by` rows refuse (no new art — the
  named family supplies it); `size: null` cross-refs refuse; `staged`
  entries accept with an informational note.
- PNG magic + IHDR before any pixel decode; dims must equal the entry's
  `size` {w,h}; ANIMATED entries deliver ONE horizontal strip of
  `frames` frames ⇒ expected file is `(w×frames) × h` (the install
  `_sheetN` convention); 16px grid law.
- alpha channel required (RGBA export); stray-halo scan: semi-transparent
  pixels (alpha 1..254) touching fully-transparent ones are anti-aliased
  fringe — more than `--halo-max` (default 8) fails, with coordinates.
- `--palette STRIP.png`: exact-RGB membership over alpha>0 pixels;
  off-palette colors reported as hex + count + first coordinate; more
  than `--palette-max` (default 0) fails.

Outputs land in `<delivery>/_intake/` (`--report-dir`): `report.json`
(schema `cabinet.world.intake-report/v1`), `report.md`, and a
deterministic `test-scene.png` conformance sheet (accepted sprites on a
neutral gray checker — a conformance scene, not world art). `--gate`
additionally runs `world-aesthetic-gate.py --mechanical` over the scene
and folds the verdict in as INFORMATIONAL — the committed calibration is
fitted to the outgoing LimeZu estate (§5), so conforming new-style art
may honestly fail it until the Phase-0 style-bible recalibration.

Promotion (`--promote`; REFUSES when any file failed unless
`--promote-accepted-only`): accepted PNGs are copied VERBATIM (delivered
bytes, no re-encode) into
`cabinet/dashboard/public/world-assets/originals/<object>/<id>.png`
(realpath-jailed) and upserted into the tracked manifest following the
world-asset-install row conventions — content-addressed sha256,
`license: "owned — org-original"`, batch tag in `pack`; the manifest's
`version`/`_doc` are never touched by the tool. `originals/` is the ONE
re-included (committable) subtree of the otherwise-gitignored asset dir:
owned commissioned art ships in git, LimeZu binaries stay ignored. After
any promote, run `python3.12 cabinet/scripts/world-asset-gate.py` (the
tool prints the exact command). Exit codes: 0 all accepted · 1 any
fix_needed (reports still written) · 2 usage / promote refusal.
