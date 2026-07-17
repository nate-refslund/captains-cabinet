# Review artifact — feat/radar-observe cp1 (2026-07-17)

Batch: dependency radar, deterministic observe half (RADAR-OBSERVE).
13 files, +2314/−8 → FW-019 artifact required at commit time.
New organ: `cabinet/scripts/dependency-radar.py` + tracked registry
`cabinet/config/dependency-radar.yml` (9 surfaces: vendor changelogs /
release feeds / model-doc pages + the claude binary/PATH probe), nightly
04:20 `services.yml` row, cabinet-doctor check #13 (`--probe` ladder),
runbook `docs/runbooks/dependency-radar.md`, radar suite (48 tests),
comparator version-shape gate in `cabinet/scripts/workaround-retest.py`
`condition_matches_delta()` + repro tests, ledger RADAR-OBSERVE row +
A13 plan-doc parity row, docs-sweep-allowlist dedupe (one glob serves
both platform-radar lanes).

## Review provenance (lane-side, before this landing)

Independent adversarial review in the radarwave observe lane; the
2026-07-17 fix pass closed all 5 findings (evidence: ledger row
RADAR-OBSERVE note; re-probe tasks all green):

- P2 ReDoS: `normalize()`'s four lazy-dot markup strips were O(n²) on
  open-flood input (700KB hung >25s) — replaced with a single-pass
  linear block stripper; byte-equivalence corpus-pinned; 5MB flood
  controls <2s (measured 0.04s) + end-to-end flood-source sweep control.
- P2 stale PATH pin: binary-probe `service_path` had hand-copied the
  stale installed-plist PATH — now cross-pinned to `generate-plists.py`
  `PATH_ENV` in registry+remedy+runbook; the test PARSES the generator
  so the surfaces cannot drift silently.
- P2 dead cross-lane seam: sweep now emits the per-day triage mirror
  `cabinet/logs/platform-radar/delta-<date>.json` in the gated triage
  lane's exact intake shape; installed-version bumps (stable status)
  are deltas so `version_condition` retests are mechanically reachable;
  same-day merge, atomic replace, corrupt-file rebuild, mirror failure
  fail-soft; hostile content inert-data-pinned in the mirror too.
- (4+5) ledger row + A13 parity.

Landing pass closed the one OPEN cross-lane P2 in the LANDED matcher:
sha-shaped `new_version` mirror stamps (and probe status words like
FAIL) satisfied every numeric comparator pin via `compare_versions`'
non-numeric fallback — comparator `version_condition` rows now match
only VERSION-SHAPED values (optional v prefix + dotted numerals +
optional qualifiers; 120-char cap BEFORE the anchored regex so hostile
flood values reject linearly). Reviewer's repro pinned in BOTH suites
(unit + e2e `--from-delta` in test_workaround_retest.py; through the
REAL matcher in test_dependency_radar.py).

## Security law carried by the batch

Observe-only: no LLM in path, nothing auto-acted-on. Fetched text is
UNTRUSTED end to end — json-escaped JSONL, sha256-keyed fences +
injection screen in the daily report, never executed / shell- or
SQL-interpolated; curl https-only (`--proto =https --proto-redir
=https --disable -m 20`, 5MB cap), subprocess argv-fixed (`shell=True`
test-prohibited); runtime outputs all gitignored; `last_seen` lives
only in the runtime sidecar, never the tracked registry.

## Integration gates (this worktree, off origin/master ff7e0ae0)

- RADAR-OBSERVE gate_cmd: 48 passed (radar+retest suites) +
  `--validate-registry` VALID (9 entries) — PASS
- A13 parity gate_cmd: exit 0 (pre-commit; re-run post-commit) — PASS
- ledger-status-parity.sh: GREEN (ids=325 md_rows=325 findings=0)
- Full `cabinet/scripts/tests`: 1335 passed, 4 skipped
- docs-track-code-sweep.sh: GREEN (files=44 findings=0)
- check-layer-separation.sh: OK (new=0, fixed=0)
- generate-plists.py render: `com.cabinet.dependency-radar.plist`
  rendered, plutil lint=OK (all fleet plists lint OK)
- schg guard: `ls -lO` clean on every touched path; no germline paths
  in the batch. Live-tree dirty overlap = stale RADAR-1-era staging on
  an older master (d9f09bb8); this landing rides a clean worktree off
  origin/master.

Verdict: **SHIP** — deliberate residuals (unchanged from the lane):
generate-plists + deploy-mac install of `com.cabinet.dependency-radar`
and the stale-PATH fleet-plist refresh ride the orchestrator's deploy
pass, not this commit.
