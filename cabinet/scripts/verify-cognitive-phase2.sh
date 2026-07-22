#!/usr/bin/env bash
# Complete committed-tree exit gate for COG-2 (the "Cortex" shadow temporal
# epistemic world model). Any omitted proof is a failure. Phase-local twin of
# verify-cognitive-phase1.sh (§12.3 / §12.5 — the Phase-0/1 instances are
# frozen-historical and untouched; COG-2 clones the pattern and COMPOSES the
# enduring verify-cognitive-architecture.sh rather than re-running an earlier
# phase's own gate). Binds the frozen PASS review to the EXACT COG-2
# implementation bytes and is honest about reach: it proves the LOCAL
# committed-tree battery is green, NOT that CI is green -> ends READY_FOR_CI.
#
# Requires python3.12 (the house interpreter). The DB-backed sims want a
# PostgreSQL 17 toolchain on PATH (e.g. /opt/homebrew/opt/postgresql@17/bin);
# CI provides the postgres service container.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} -p no:cacheprovider"
# The phase gate runs on controlled hardware: the §8/§11 M6 ceilings (as-of p95,
# full-rebuild time, store-size envelope) are ENFORCED here even under CI-like
# environments — the measurement sims assert-on-a-quiet-host only when this flag
# is set (the exact COG1_ENFORCE_P95 precedent; skips-on-noise otherwise).
export COG2_ENFORCE_P95=1
REVIEW="shared/interfaces/reviews/cognitive-core-phase-2-review.md"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[cog2-verify] BLOCK — not a git work tree (this gate is source-instance only)" >&2; exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "[cog2-verify] BLOCK — working tree is not clean; the gate binds COMMITTED bytes (commit or stash first)" >&2
  git status --porcelain >&2; exit 1
fi
if [ ! -f "$REVIEW" ]; then
  echo "[cog2-verify] BLOCK — frozen review artifact missing: $REVIEW (the §12.3 post-implementation review lands it)" >&2; exit 1
fi
if ! git ls-files --error-unmatch "$REVIEW" >/dev/null 2>&1; then
  echo "[cog2-verify] BLOCK — review artifact is not tracked (force-add it: git add -f $REVIEW)" >&2; exit 1
fi
if ! grep -qx 'Verdict: PASS' "$REVIEW"; then
  echo "[cog2-verify] BLOCK — frozen review artifact is not Verdict: PASS" >&2; exit 1
fi
# reviewed bytes == tested bytes (fails if any bound impl path changed post-review)
python3.12 cabinet/scripts/cognitive-phase2-review-scope.py --verify "$REVIEW"
# enduring architecture gate (COMPOSED, never a re-run of an earlier phase's instance)
bash cabinet/scripts/verify-cognitive-architecture.sh
# COG-2 rollback-manifest closure + review-scope teeth
python3.12 -m pytest cabinet/scripts/tests/test_cognitive_phase2_rollback.py -q
# COG-2 gate suites — no-DB group (envelope-lib fixtures + AST/static suites)
python3.12 -m pytest \
  cabinet/scripts/tests/test_cog2_import_gate.py \
  cabinet/scripts/tests/test_cog2_parity_wiring.py \
  cabinet/scripts/tests/test_cog2_asof_fence.py \
  cabinet/scripts/tests/test_cog2_contradiction.py \
  cabinet/scripts/tests/test_cog2_provenance.py \
  cabinet/scripts/tests/test_cog2_consequence_seam.py \
  cabinet/scripts/tests/test_cog2_fencing.py \
  cabinet/scripts/tests/test_cog2_parity.py -q
# COG-2 gate suites — DB group (EphemeralPG17; skip without the ephemeral harness).
# Includes the M6 measurement gate (§8 / exit :172): with COG2_ENFORCE_P95=1 set
# above, the bounded-history sim ASSERTS the as-of p95 / full-rebuild / store-size
# ceilings on a quiet host — the real M6 tripwire (COG1_ENFORCE_P95 precedent).
python3.12 -m pytest \
  cabinet/scripts/tests/test_cog2_rebuild_determinism.py \
  cabinet/scripts/tests/test_cog2_corruption.py \
  cabinet/scripts/tests/test_cog2_measurement.py -q
# architecture census (--check: line / module / sink / service ceilings)
python3.12 cabinet/scripts/cognitive-architecture-census.py --check
# evidence-coverage reconcile (every detector hit enumerated)
python3.12 cabinet/scripts/evidence-coverage.py
# §7.1 shadow-boundary import gate (net-new AST walk + grep/data-plane backstop)
python3.12 cabinet/scripts/cog2-import-gate.py
bash cabinet/scripts/run-golden-evals.sh
bash cabinet/scripts/docs-track-code-sweep.sh
bash cabinet/scripts/ledger-status-parity.sh
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
# egg-manifest land battery (O-B3 / §12.5): COG-2 extends the export manifest +
# the test's phase list, so the same battery that lands them proves them green.
python3.12 -m pytest cabinet/scripts/tests/test_egg_export.py -q
bash cabinet/scripts/null-hatch.sh
# CODE-inverse rollback rehearsal in a disposable worktree (§12.4; the named twin)
python3.12 cabinet/scripts/cognitive-phase2-rollback-rehearsal.py
echo "[cog2-verify] READY_FOR_CI — committed-tree battery green and review bound to the tested bytes; CI-green is NOT proven by this command. Push, then confirm every branch CI job green per-job before flipping COG-2 to done."
