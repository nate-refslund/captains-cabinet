#!/usr/bin/env bash
# Complete committed-tree exit gate for COG-1. Any omitted proof is a failure.
# Phase-local twin of verify-cognitive-phase0.sh (§10.3 / §12.3 — the Phase-0
# instance is frozen-historical and untouched; COG-1 clones the pattern and
# COMPOSES the enduring verify-cognitive-architecture.sh rather than re-running
# Phase-0's own gate). Binds the frozen PASS review to the EXACT COG-1
# implementation bytes and is honest about reach: it proves the LOCAL
# committed-tree battery is green, NOT that CI is green -> ends READY_FOR_CI.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} -p no:cacheprovider"
REVIEW="shared/interfaces/reviews/cognitive-core-phase-1-review.md"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "COG-1 verify: BLOCK — not a git work tree (this gate is source-instance only)" >&2; exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "COG-1 verify: BLOCK — working tree is not clean; the gate binds COMMITTED bytes (commit or stash first)" >&2
  git status --porcelain >&2; exit 1
fi
if [ ! -f "$REVIEW" ]; then
  echo "COG-1 verify: BLOCK — frozen review artifact missing: $REVIEW (the §12.3 post-implementation review lands it)" >&2; exit 1
fi
if ! git ls-files --error-unmatch "$REVIEW" >/dev/null 2>&1; then
  echo "COG-1 verify: BLOCK — review artifact is not tracked (force-add it: git add -f $REVIEW)" >&2; exit 1
fi
if ! grep -qx 'Verdict: PASS' "$REVIEW"; then
  echo "COG-1 verify: BLOCK — frozen review artifact is not Verdict: PASS" >&2; exit 1
fi
# reviewed bytes == tested bytes (fails if any bound impl path changed post-review)
python3.12 cabinet/scripts/cognitive-phase1-review-scope.py --verify "$REVIEW"
# enduring architecture gate (COMPOSED, never a re-run of Phase-0's own instance)
bash cabinet/scripts/verify-cognitive-architecture.sh
# COG-1 rollback-manifest closure + review-scope teeth
python3.12 -m pytest cabinet/scripts/tests/test_cognitive_phase1_rollback.py -q
# COG-1 implementation suites (DB/redis sims skip without the ephemeral harness)
python3.12 -m pytest \
  framework/triggers/tests/test_envelope_v2.py \
  framework/triggers/tests/test_schema_registry.py \
  framework/outbox/tests -q
python3.12 -m pytest \
  cabinet/scripts/tests/test_cog1_outbox_capture.py \
  cabinet/scripts/tests/test_cog1_cutover.py \
  cabinet/scripts/tests/test_cog1_fencing.py \
  cabinet/scripts/tests/test_cog1_parity.py \
  cabinet/scripts/tests/test_cog1_replay_hash.py \
  cabinet/scripts/tests/test_task_events_watch.py -q
# v1 envelope compat regression gate (frozen v1 suite stays green beside v2)
python3.12 -m pytest framework/triggers/tests/test_envelope_redteam.py -q
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
python3.12 -m pytest cabinet/scripts/tests/test_egg_export.py -q
bash cabinet/scripts/null-hatch.sh
python3.12 cabinet/scripts/cognitive-phase1-rollback-rehearsal.py
echo "COG-1 verify: READY_FOR_CI — committed-tree battery green and review bound to the tested bytes; CI-green is NOT proven by this command. Push, then confirm every branch CI job green per-job before flipping COG-1 to done."
