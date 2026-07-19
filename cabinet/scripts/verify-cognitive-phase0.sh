#!/usr/bin/env bash
# Complete committed-tree exit gate for COG-0. Any omitted proof is a failure.
# Binds the frozen PASS review to the EXACT candidate bytes and is honest about reach:
# it proves the LOCAL committed-tree battery is green, NOT that CI is green -> ends READY_FOR_CI.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
# keep the gate's own pytest runs from leaving cache cruft (hygiene; harmless)
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} -p no:cacheprovider"
REVIEW="shared/interfaces/reviews/codex-cognitive-foundry-masterplan-cp1.md"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "COG-0 verify: BLOCK — not a git work tree (this gate is source-instance only)" >&2; exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "COG-0 verify: BLOCK — working tree is not clean; the gate binds COMMITTED bytes (commit or stash first)" >&2
  git status --porcelain >&2; exit 1
fi
if [ ! -f "$REVIEW" ]; then
  echo "COG-0 verify: BLOCK — frozen review artifact missing: $REVIEW" >&2; exit 1
fi
if ! git ls-files --error-unmatch "$REVIEW" >/dev/null 2>&1; then
  echo "COG-0 verify: BLOCK — review artifact is not tracked (force-add it: git add -f $REVIEW)" >&2; exit 1
fi
if ! grep -qx 'Verdict: PASS' "$REVIEW"; then
  echo "COG-0 verify: BLOCK — frozen review artifact is not Verdict: PASS" >&2; exit 1
fi
# reviewed bytes == tested bytes (fails if any bound impl path changed post-review)
python3.12 cabinet/scripts/cognitive-phase0-review-scope.py --verify "$REVIEW"
# subordinate battery — reached only once the binding holds
bash cabinet/scripts/verify-cognitive-architecture.sh
python3.12 -m pytest cabinet/scripts/tests/test_cognitive_phase0_rollback.py -q
python3.12 -m pytest \
  framework/authority/tests framework/acting/tests framework/attention/tests \
  framework/events/tests framework/outbox/tests framework/missions/tests \
  framework/sources/tests framework/ovi/tests framework/triggers/tests -q
python3.12 -m pytest cabinet/scripts/lib/tests/test_install_extensions_gate.py -q
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
python3.12 cabinet/scripts/cognitive-phase0-rollback-rehearsal.py
echo "COG-0 verify: READY_FOR_CI — committed-tree battery green and review bound to the tested bytes; CI-green is NOT proven by this command. Push, then confirm every branch CI job green per-job before flipping COG-0 to done."
