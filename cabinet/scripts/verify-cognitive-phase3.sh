#!/usr/bin/env bash
# Complete committed-tree exit gate for COG-3 (the "Objectives" shadow causal
# objective/value graph). Any omitted proof is a failure. Phase-local twin of
# verify-cognitive-phase2.sh (§12.3 / §12.5 — the Phase-0/1/2 instances are
# frozen-historical and untouched; COG-3 clones the pattern). Honest about reach:
# it proves the LOCAL committed-tree battery is green, NOT that CI is green ->
# ends READY_FOR_CI.
#
# Requires python3.12 (the house interpreter). All COG-3 sims are FILE-SEEDED
# (§7.2 — no DSN, no pg toolchain); the cog2 battery is NOT run here (it has its
# own verify twin). This gate is objectives-scoped.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:-} -p no:cacheprovider"
# The phase gate runs on controlled hardware: the §8 N1 measurement ceilings
# (serve p95, full-rebuild wall-time) are ENFORCED here (the COG2_ENFORCE_P95
# precedent); test_cog3_measurement.py measures always, asserts ceilings only
# under this flag.
export COG3_ENFORCE_P95=1
REVIEW="shared/interfaces/reviews/cognitive-core-phase-3-review.md"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[cog3-verify] BLOCK — not a git work tree (this gate is source-instance only)" >&2; exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "[cog3-verify] BLOCK — working tree is not clean; the gate binds COMMITTED bytes (commit or stash first)" >&2
  git status --porcelain >&2; exit 1
fi
# Frozen-review binding (§12.3): the integrator FREEZES the review at landing. If
# it is not yet present, SKIP-with-loud-note (do NOT block) — the review-to-bytes
# binding activates once the review lands (unlike phase-2's hard block, COG-3's
# wave-4 apparatus lands BEFORE the frozen review, so a hard block would make the
# gate un-runnable during the build). When present, bind reviewed==tested bytes.
if [ -f "$REVIEW" ]; then
  if ! git ls-files --error-unmatch "$REVIEW" >/dev/null 2>&1; then
    echo "[cog3-verify] BLOCK — review artifact is not tracked (force-add it: git add -f $REVIEW)" >&2; exit 1
  fi
  if ! grep -qx 'Verdict: PASS' "$REVIEW"; then
    echo "[cog3-verify] BLOCK — frozen review artifact is not Verdict: PASS" >&2; exit 1
  fi
  # reviewed bytes == tested bytes (fails if any bound impl path changed post-review)
  python3.12 cabinet/scripts/cognitive-phase3-review-scope.py --verify "$REVIEW"
else
  echo "[cog3-verify] NOTE — frozen review artifact absent ($REVIEW); SKIPPING the"
  echo "[cog3-verify] NOTE — review-to-bytes binding. TODO-FREEZE: the integrator"
  echo "[cog3-verify] NOTE — freezes it at landing (§12.3); the --verify step then binds."
fi
# §7.4 pointer tripwire (attack C-m11): NO read-pointer file is created this phase.
# Its mere existence pre-opens the future flip seam — RED if it exists at all.
if [ -e "$HOME/.cabinet/state/cog3-read-pointer" ]; then
  echo "[cog3-verify] BLOCK — a cog3 read-pointer file exists ($HOME/.cabinet/state/cog3-read-pointer);" >&2
  echo "[cog3-verify] no pointer file is created this phase (§7.4). Remove it; the flip is a later gated amendment." >&2
  exit 1
fi
# COG-3 rollback-manifest closure + review-scope teeth
python3.12 -m pytest cabinet/scripts/tests/test_cognitive_phase3_rollback.py -q
# ALL COG-3 gate + sim + apparatus suites (the step-0 gates, the six sims, the
# state-function fixture, the boundary/vocab tripwires, the parity falsifier, the
# M-measurement). File-seeded — no DSN.
python3.12 -m pytest cabinet/scripts/tests/test_cog3_*.py -q
# architecture census (--check: line / module / sink / service ceilings). COG-3's
# framework/objectives modules + lines ride the temporary_allowances rows; scripts
# + tests + docs (this unit's whole surface) count toward NO framework budget.
python3.12 cabinet/scripts/cognitive-architecture-census.py --check
# §6.5 shadow-boundary import gate (cortex + objectives, both directions + AST +
# data-plane sweep) — rc=0 == boundary intact.
python3.12 cabinet/scripts/cog2-import-gate.py
# A13 operative-ledger parity (the universal heredoc — byte-identical to the
# phase-1/2 twins + the rollback rehearsal's A13_ASSERTION).
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
# egg-manifest land battery (O-B3 / §12.5): COG-3 extends the export manifest +
# the test's phase list, so the same battery that lands them proves them green.
python3.12 -m pytest cabinet/scripts/tests/test_egg_export.py -q
# CODE-inverse rollback rehearsal in a disposable worktree (§12.4; the named twin)
python3.12 cabinet/scripts/cognitive-phase3-rollback-rehearsal.py
echo "[cog3-verify] READY_FOR_CI — committed-tree battery green and (when frozen) review bound to the tested bytes; CI-green is NOT proven by this command. Push, then confirm every branch CI job green per-job before flipping COG-3 to done."
