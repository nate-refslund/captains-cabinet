#!/usr/bin/env bash
# Complete committed-tree exit gate for COG-4 (composable cognitive organs +
# deterministic shadow scheduler inside fixed wakes). Any omitted proof is a
# failure. Phase-local twin of verify-cognitive-phase3.sh (contract §14.1 — the
# Phase-0/1/2/3 instances are frozen-historical and untouched; COG-4 clones the
# pattern). Honest about reach: it proves the LOCAL committed-tree battery is
# green, NOT that CI is green -> ends READY_FOR_CI.
#
# Requires python3.12 (the house interpreter). All COG-4 sims are FILE-SEEDED
# (§12 — no DSN, no clock, no network); the cog2/cog3 batteries are NOT run
# here (each has its own verify twin). This gate is COG-4-scoped; the composed
# enduring-architecture gate below is the cross-phase spine.
#
# INTERIM DISCHARGED (W6 landing 2026-07-24): the §13 corpus surgery is DONE —
# every designed flip-arm (the two test_cog4_measurement.py arms, the
# test_cog4_floor_conservation.py derivation arm, both
# test_cog4_organ_runner.py runner arms) is retired-live per its own
# RETIREMENT CONDITION, bound to the landed real surfaces (pre-proven
# out-of-band in test_cog4_measure_baseline.py + test_cog4_organ_runner_real.py,
# the parity-record mirror). The battery below runs with ZERO designed REDs.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} -p no:cacheprovider"
REVIEW="shared/interfaces/reviews/cognitive-core-phase-4-review.md"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[cog4-verify] BLOCK — not a git work tree (this gate is source-instance only)" >&2; exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "[cog4-verify] BLOCK — working tree is not clean; the gate binds COMMITTED bytes (commit or stash first)" >&2
  git status --porcelain >&2; exit 1
fi
# §10 armed-mode leg (N6, MR2 — the anti-phantom arm in test_cog4_measurement.py
# keys on THIS consumer): the cog4-measure CLI + the S0 baseline artifact LANDED
# in W6-e3, so COG4_ENFORCE_BOUND is ARMED LIVE (e1's file-existence deferral is
# discharged — the same-commit armed-consumer law, §10.3). The export arms the
# wall-clock tripwire in the pytest battery below; this leg additionally runs the
# REAL measurement check against the tracked S0 baseline (deterministic proxies
# EXACT always-on; wall-clock p95 <= the floor-aware bound when armed). A
# regression fails the gate here, LOUD. (test_cog4_measurement.py's two former
# vacuity arms are retired-live since the 2026-07-24 W6 landing — they bind the
# same real surfaces this leg runs.)
export COG4_ENFORCE_BOUND=1
python3.12 cabinet/scripts/cog4-measure.py --check \
  --baseline-file cabinet/scripts/tests/fixtures/cog4/cog4-measure-baseline-2026-07-24.json
echo "[cog4-verify] N6 armed: COG4_ENFORCE_BOUND=1 (real-pilot proxies EXACT + wall-clock tripwire vs the S0 baseline)"
# Frozen-review binding (§15): the integrator FREEZES the review at landing. If
# it is not yet present, SKIP-with-loud-note (do NOT block) — the review-to-bytes
# binding activates once the review lands (the phase-3 precedent: the twins land
# BEFORE the frozen review, so a hard block would make the gate un-runnable
# during the build). When present, bind reviewed==tested bytes.
if [ -f "$REVIEW" ]; then
  if ! git ls-files --error-unmatch "$REVIEW" >/dev/null 2>&1; then
    echo "[cog4-verify] BLOCK — review artifact is not tracked (force-add it: git add -f $REVIEW)" >&2; exit 1
  fi
  if ! grep -qx 'Verdict: PASS' "$REVIEW"; then
    echo "[cog4-verify] BLOCK — frozen review artifact is not Verdict: PASS" >&2; exit 1
  fi
  # reviewed bytes == tested bytes (fails if any bound impl path changed post-review)
  python3.12 cabinet/scripts/cognitive-phase4-review-scope.py --verify "$REVIEW"
else
  echo "[cog4-verify] NOTE — frozen review artifact absent ($REVIEW); SKIPPING the"
  echo "[cog4-verify] NOTE — review-to-bytes binding. TODO-FREEZE: the integrator"
  echo "[cog4-verify] NOTE — freezes it at landing (§15); the --verify step then binds."
fi
# §7.3 pointer tripwire (the COG-3 §7.4 idiom): NO cutover pointer file is
# created this phase — the scheduler is SHADOW-ONLY and the future cutover is a
# pointer/adapter AMENDMENT. Its mere existence pre-opens the flip seam — RED if
# it exists at all.
if [ -e "$HOME/.cabinet/state/cog4-dispatch-pointer" ]; then
  echo "[cog4-verify] BLOCK — a cog4 dispatch-pointer file exists ($HOME/.cabinet/state/cog4-dispatch-pointer);" >&2
  echo "[cog4-verify] no pointer file is created this phase (§7.3). Remove it; the cutover is a later gated amendment." >&2
  exit 1
fi
# enduring architecture gate (COMPOSED, never a re-run of an earlier phase's
# instance) — evolution contract tests + census self-tests + census --check +
# check-layer-separation.sh. The standalone census --check and layer-sep runs
# below are KEPT (the phase-2/3 twins keep the census double-run; both are
# idempotent, and the brief's compose list names layer-sep explicitly).
bash cabinet/scripts/verify-cognitive-architecture.sh
bash cabinet/scripts/check-layer-separation.sh
# ALL COG-4 gate + sim + apparatus suites (the 15 §12 sims across the fold +
# dispatch batteries, the N1-N9 gate suites incl. N9 parity + runner-invariance,
# the boundary-row mutant harness, the AST pins, fleet-truth,
# floor-conservation, parity, measurement). File-seeded — no DSN.
python3.12 -m pytest cabinet/scripts/tests/test_cog4_*.py -q
# architecture census (--check: line / module / sink / service ceilings).
# COG-4's framework/{projection,scheduler,organs} modules + lines ride the
# COG-4 temporary_allowances rows; scripts + tests + docs (this unit's whole
# surface) count toward NO framework budget.
python3.12 cabinet/scripts/cognitive-architecture-census.py --check
# C2 boundary engine (§8 — the converted cog2-import-gate.py over
# cabinet/config/boundary-manifest.yml: cortex + objectives + the COG-4
# scheduler/organs/projection module rows + data-plane sweeps, both directions
# + AST) — rc=0 == every boundary intact.
python3.12 cabinet/scripts/cog2-import-gate.py
# A13 operative-ledger parity (the universal heredoc — byte-identical to the
# phase-1/2/3 twins + the rollback rehearsal's A13_ASSERTION).
python3.12 - <<'PY'
import re
import yaml

ledger = yaml.safe_load(open("docs/plans/operative-egg-ledger-2026-07-07.yml"))["entries"]
ids = [entry["id"] for entry in ledger]
assert len(ids) == len(set(ids)), "duplicate operative ledger ids"
plan = open("docs/plans/operative-egg-plan-2026-07-07.md").read()
plan_ids = set(re.findall(r"^\| ([A-Z][A-Z0-9-]*[0-9-][A-Z0-9-]*) ", plan, re.M))
assert plan_ids == set(ids), sorted(plan_ids ^ set(ids))
PY
# egg-manifest land battery (O-B3 / §14.1): COG-4 extends the export manifest
# (twin delete/expect-absent rows), so the same battery that lands them proves
# them green.
python3.12 -m pytest cabinet/scripts/tests/test_egg_export.py -q
# CODE-inverse rollback rehearsal in a disposable worktree (§16; the named twin
# — carries the C1 sentinel anchor, the strict out-of-phase-aware inverse-diff
# ratchet, the pre-adoption refold arm, and the vacuity-armed compose-revert
# round-trip arm).
python3.12 cabinet/scripts/cognitive-phase4-rollback-rehearsal.py
echo "[cog4-verify] READY_FOR_CI — committed-tree battery green and (when frozen) review bound to the tested bytes; CI-green is NOT proven by this command. Push, then confirm every branch CI job green per-job before flipping COG-4 to done."
