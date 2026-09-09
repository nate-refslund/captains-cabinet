#!/usr/bin/env bash
# one-responsibility.sh — the phase-1 acceptance drill.
#
# THE CLAIM IT PROVES, end to end, on a fresh hatch and nothing else:
# one declared responsibility is ratified by a named door, claimed exactly once
# by exactly one holder out of a crowd, survives that holder being killed
# mid-work, is finished by a different holder with no new Captain input, shows
# up as receipts, and the change that produced it reaches an installed Cabinet.
# Exit 0 means all of that happened. Any other exit names the stage that broke.
#
# AUTHORED RED (phase-1 contract §8 lane L0). The subjects — the ratify module,
# the claims module, the holder-gap observer, the receipts read model and the
# update path — do not exist yet. The sensor exists first so that "it works"
# has a meaning before anyone writes the thing. On the tree this file lands in,
# the drill exits 10 at P1; stub P1 through the documented --tree seam and it
# exits 20 at P2 with eight winners and zero started events, which is precisely
# the defect the claim unit exists to close.
#
# EXIT CODES — the stage, not the symptom
#   0   pass
#   10  P1  the tap: no ratified responsibility
#   20  P2  the claim: the crowd did not resolve to one holder (includes the
#           assignment leg P2b and the locked-hook leg P2h — all claim-path)
#   21      THE MEASUREMENT WAS IMPOSSIBLE: the pull path could not be
#           imported where it must be measured, or not one holder in the
#           crowd reached it at all. Distinct from 20 on purpose — an
#           ImportError is not the red the claim invariant names, and a drill
#           that reported one as the other would be lying about what it
#           proved. A PARTIAL failure is 20, not 21: seven dead holders and
#           one winner is a crowd that did not resolve, and the stage says so
#           in those words rather than printing "8 holders, 1 claim".
#   30  P3/P4  kill and resume: the item did not come back, or came back wrong
#   40  P5/P6  no re-briefing / receipts
#   50  P7  the update path
#   64      usage, or this host cannot host the drill at all
#
# HERMETIC BY CONSTRUCTION. Everything runs against a scratch hatch under a
# throwaway root; HOME, CABINET_ROOT, CABINET_EVENT_LOG_DIR, CABINET_ID and the
# A2.9 claim-lease floor (CABINET_CLAIM_LEASE_FLOOR_SECONDS=1, the only path
# below the production 60 s minimum) are pinned and every other CABINET_* plus PYTHONPATH, DATABASE_URL,
# ORG_RUNTIME_DB and REDIS_* are scrubbed (an inherited DATABASE_URL makes the
# emitter write this run's fixture rows into a real Postgres —
# framework/events/emitter.py:438). File lists of $HOME and of the repo are
# taken before and after and compared: a drill that quietly wrote outside its
# root proved nothing about a fresh hatch.
#
# THE ONE THING IT TOUCHES OUTSIDE ITS ROOT is the locked hook's debounce
# sentinel, /tmp/.session-task-injected-<slug>, because the locked bytes put it
# there. The drill therefore uses a slug that is absent from any live roster
# (drill-<8hex>) so it can never collide with a running officer's sentinel, and
# removes its own on the way out.
#
# SEAMS — all three exist for the tests that prove this drill is alive
#   --tree DIR (or CABINET_DRILL_TREE)
#       stage the scratch root from DIR instead of `git archive HEAD`. This is
#       the mutated-tree red arm: a copy whose claim() skips the lock must make
#       P2 exit 20; a copy with the pull path removed must make the drill exit
#       21; a copy carrying a stub ratify module lets P1 pass so P2's red is
#       reachable on a tree that has no subjects at all.
#   CABINET_UPDATE_TEST_RESTART_CMD
#       the command the update path runs INSTEAD of restarting the dashboard.
#       The drill points it at its own stub server so the health gate can be
#       made to go red on purpose (see P7). The name is the update path's own
#       (cabinet-update.sh restart_dashboard) and carries the A5.14 prefix,
#       because a variable that can decide a leg of the health gate must never
#       read as a production knob. This drill first drove a dashboard-shaped
#       name of its own invention that nothing on the other side read; the
#       guard below refused the leg rather than measuring a dashboard that
#       restarted perfectly well, and the reconciliation kept the update
#       path's naming law and changed the side that was wrong — this one.
#   CABINET_DRILL_DASH_PORT
#       pin the stub server's port instead of picking a free one.
#
# Usage:
#   bash cabinet/scripts/drills/one-responsibility.sh [--root DIR] [--tree DIR]
#        [--skip-update] [--with-rebuild] [--keep-scratch] [--json]
#
# STAGE VERDICTS ARE FAIL-CLOSED (lib/verdict.sh). Every stage's assertions
# run as a python block that prints one json {code, problems} verdict and then
# a sentinel line, with its stderr kept OUT of the file the verdict is read
# from; read_verdict turns a crashed block, a missing sentinel, an unparseable
# verdict, a pass that names problems or a failure that names none into a
# FAILURE of that stage. The shape it replaces — PROBLEMS="$(python …)" then
# [ -z "$PROBLEMS" ] || fail — scored an assertion that could not RUN as a
# pass; six stages and three event counts were built that way in this drill's
# first cut and an independent reviewer proved two of them green on a tree
# whose defect they exist to catch. "Not measured" and "measured clean" are
# different facts.
#
# SO IS PARTICIPATION, and it is a SECOND channel. A stage's verdict can be
# read perfectly while the run it describes never happened: eight holders are
# launched, seven die before they reach the pull path, one claims the item, and
# a stage that counts only winners and events prints "8 holders, 1 claim" — a
# sentence whose first clause is false. Every leg this drill starts in the
# background therefore has its EXIT STATUS collected one pid at a time (`wait`
# with no argument throws them away), every holder's result must parse and
# carry no error, and every P7 count is taken twice, around the leg that is
# supposed to change it, because a count across the whole run is answered by
# another leg's row. Silence is a legitimate answer from a losing hook tick and
# from a holder that found nothing, which is exactly why silence can never be
# the only thing a stage looks at.
#
# Foreground only. Every wait is a bounded inline poll (<= 30 s); no watcher,
# no daemon, no background job survives the run (macOS has no timeout(1), so
# waits are python sleeps, every background leg is started in its own process
# group, and the trap kills the GROUP — the hook legs are pipelines whose
# children are nobody's recorded pid).
#
# RESIDUAL, written down rather than left to be re-derived: contract §4 P4
# ends "(task-002 repeats the race with lease 2 s.)". Amendment A2.3 spends
# task-002 on the locked-hook stage instead ("the drill's hook stage claims
# task-002 THROUGH the hook") and the amendment supersedes the parenthetical,
# so the second, shorter-lease race is NOT run here. What that costs: the
# expiry race is proved at one lease length, not two. What would close it: a
# third seeded node carrying the same race at lease 2 s.

set -u
# Job control in a script: each background leg becomes its own process group,
# so the trap can kill the GROUP rather than the one pid it recorded. Measured:
# without this, `bash -c "printf … | python …" &` leaves the python behind when
# its parent is killed.
#
# EXPECTED NOISE, not an error: bash 3.2.57 (macOS) prints
# "one-responsibility.sh: child setpgid (N to N): Operation not permitted" on
# some legs when job control is on in a non-interactive shell. Measured on this
# host: the group kill still works (0 strays with `set -m`, 1 stray without),
# so the line is cosmetic. It is NOT suppressed, because suppressing it would
# mean discarding the drill's own stderr, and the whole unit exists to stop
# stages that hide what they could not do.
set -m 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

PY="${CABINET_PYTHON:-python3.12}"
# What a locked copy that has not had its unlock window still runs
# (session-task-inject.sh:28). Master's bytes pin ${CABINET_PYTHON:-python3.12}
# since the A7.7 landing; the box's copy does not change until the ceremony,
# and this stage exists to measure the interpreter the box actually walks.
BOX_PY="python3"

# Read every CABINET_* input the drill takes BEFORE the environment is scrubbed
# — the scrub is what makes the run hermetic, and it would eat these too.
DASH_PORT_PIN="${CABINET_DRILL_DASH_PORT:-}"

# THE BOX INTERPRETER'S LIBRARIES, resolved while the operator's own HOME is
# still in place. `pip install --user` puts them under a directory DERIVED FROM
# HOME (measured here: /Users/<me>/Library/Python/3.9/lib/python/site-packages),
# and the hermetic scrub below repoints HOME at the scratch tree — so the locked
# hook's own python3 loses pyyaml and P2h reds with "the locked hook's
# interpreter cannot import the pull path", blaming a subject that is perfectly
# 3.9-clean for an interpreter the DRILL stripped of its libraries. Scrubbing
# HOME exists to keep this deployment's state out of the run, not to model a
# python installation nobody has: production runs the hook under the officer's
# real HOME, where these libraries are visible. PYTHONPATH restores exactly
# that and nothing else — it is handed to the hook legs alone, never to the
# python3.12 legs (a 3.9 site directory on a 3.12 path is a different bug), and
# an interpreter that genuinely cannot import them yields an empty value here,
# so a real ceremony-pending host still reds for its own true reason.
# NO APOSTROPHE BELOW, and none in any heredoc nested inside $( ): bash 3.2
# (the /bin/bash this ships against) keeps tracking quote characters inside a
# command substitution even in a quoted heredoc body, so one contraction in a
# python comment makes the WHOLE script a syntax error 150 lines later.
# Measured on this host: "line 299: syntax error near unexpected token `(".
BOX_PY_DEPS="$("$BOX_PY" - 2>/dev/null <<'PY' || true
import os
paths = []
for name in ("yaml",):   # the only third-party import the pull path makes
    try:
        mod = __import__(name)
    except Exception:
        continue
    f = getattr(mod, "__file__", None)
    if f:
        paths.append(os.path.dirname(os.path.dirname(os.path.abspath(f))))
print(os.pathsep.join(dict.fromkeys(paths)))
PY
)"
HOOK_PY_ENV=""
[ -n "$BOX_PY_DEPS" ] && HOOK_PY_ENV="PYTHONPATH='$BOX_PY_DEPS'"
# The kill/resume cadence: tick 1s inside a short lease, so a lease that only
# renews when nearly spent shows up as a defect rather than as a slow test. The
# contract's number is 3; a loaded host may need a longer window to observe the
# same thing, and observing it late is better than observing it never.
LEASE_S="${CABINET_DRILL_LEASE_SECONDS:-3}"

ROOT_ARG=""
TREE_ARG="${CABINET_DRILL_TREE:-}"
SKIP_UPDATE=0
WITH_REBUILD=0
KEEP_SCRATCH=0
JSON_OUT=0

usage() {
  # the leading comment block IS the documentation; print it verbatim
  sed -n '2,/^[^#]/p' "$0" | sed '$d' | sed 's/^# \{0,1\}//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --root) [ $# -ge 2 ] || { echo "one-responsibility: --root needs a value" >&2; exit 64; }; ROOT_ARG="$2"; shift 2 ;;
    --root=*) ROOT_ARG="${1#--root=}"; shift ;;
    --tree) [ $# -ge 2 ] || { echo "one-responsibility: --tree needs a value" >&2; exit 64; }; TREE_ARG="$2"; shift 2 ;;
    --tree=*) TREE_ARG="${1#--tree=}"; shift ;;
    --skip-update) SKIP_UPDATE=1; shift ;;
    --with-rebuild) WITH_REBUILD=1; shift ;;
    --keep-scratch) KEEP_SCRATCH=1; shift ;;
    --json) JSON_OUT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "one-responsibility: unknown arg: $1" >&2; usage >&2; exit 64 ;;
  esac
done

# ---------------------------------------------------------------------------
# Reporting. Human lines go to stderr so --json owns stdout; every stage lands
# in a JSONL file that becomes the report, so a failure carries the same
# structure a pass does.
# ---------------------------------------------------------------------------
DRILL_EXIT=0
DRILL_STAGE="setup"
DRILL_REASON=""
STAGES_FILE=""
WORKER_PIDS=""
STUB_STATE=""
SENTINEL=""

say() { printf '[drill] %s\n' "$*" >&2; }

record() {  # record <stage> <verdict> <note...>
  [ -n "$STAGES_FILE" ] || return 0
  local stage="$1" verdict="$2"; shift 2
  STAGE="$stage" VERDICT="$verdict" NOTE="$*" "$PY" - >> "$STAGES_FILE" <<'PY'
import json, os
print(json.dumps({"stage": os.environ["STAGE"],
                  "verdict": os.environ["VERDICT"],
                  "note": os.environ["NOTE"]}, sort_keys=True))
PY
}

pass_stage() { record "$1" pass "${2:-}"; say "PASS [$1] ${2:-}"; }
thin_stage() { record "$1" thin "${2:-}"; say "THIN [$1] ${2:-}"; }
note_stage() { record "$1" note "${2:-}"; say "note [$1] ${2:-}"; }

fail() {  # fail <code> <stage> <reason...>
  local code="$1" stage="$2"; shift 2
  DRILL_EXIT="$code"; DRILL_STAGE="$stage"; DRILL_REASON="$*"
  record "$stage" fail "$*"
  say "FAIL [$stage] exit $code — $*"
  exit "$code"
}

kill_workers() {
  # The group first (set -m put each background leg in its own), then the pid:
  # a pipeline's children are not in $WORKER_PIDS and would outlive a pid kill.
  local pid
  for pid in $WORKER_PIDS; do
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  done
  WORKER_PIDS=""
}

on_exit() {
  local rc=$?
  [ "$rc" -eq 0 ] || DRILL_EXIT="$rc"
  kill_workers
  if [ -n "$STUB_STATE" ] && [ -f "$LIB_DIR/stub_dashboard.py" ]; then
    "$PY" "$LIB_DIR/stub_dashboard.py" stop --state-file "$STUB_STATE" >/dev/null 2>&1 || true
  fi
  [ -n "$SENTINEL" ] && rm -f "$SENTINEL" 2>/dev/null
  if [ "$JSON_OUT" = "1" ] && [ -n "$STAGES_FILE" ] && [ -f "$STAGES_FILE" ]; then
    EXITCODE="$DRILL_EXIT" STAGE="$DRILL_STAGE" REASON="$DRILL_REASON" \
    SFILE="$STAGES_FILE" ROOTDIR="${ROOT:-}" SLUGV="${SLUG:-}" TREESRC="${TREE_SOURCE:-}" \
    "$PY" - <<'PY'
import json, os
stages = []
try:
    with open(os.environ["SFILE"]) as fh:
        stages = [json.loads(line) for line in fh if line.strip()]
except OSError:
    pass
code = int(os.environ["EXITCODE"])
print(json.dumps({
    "drill": "one-responsibility",
    "verdict": "pass" if code == 0 else "fail",
    "exit": code,
    "failed_stage": None if code == 0 else os.environ["STAGE"],
    "reason": os.environ["REASON"] or None,
    "root": os.environ["ROOTDIR"] or None,
    "slug": os.environ["SLUGV"] or None,
    "tree_source": os.environ["TREESRC"] or None,
    "stages": stages,
}, indent=2, sort_keys=True))
PY
  fi
  if [ -n "${SCRATCH:-}" ] && [ "$KEEP_SCRATCH" = "0" ]; then
    chmod -R u+rwX "$SCRATCH" 2>/dev/null || true
    rm -rf "$SCRATCH" 2>/dev/null || true
  elif [ -n "${SCRATCH:-}" ]; then
    say "scratch kept: $SCRATCH"
  fi
  exit "$DRILL_EXIT"
}

# ---------------------------------------------------------------------------
# Host preconditions. Refuse loudly rather than half-run: a drill that skips
# what it cannot do and still exits 0 is the disabled sensor this whole
# programme keeps finding.
# ---------------------------------------------------------------------------
command -v "$PY" >/dev/null 2>&1 || { echo "one-responsibility: no $PY on PATH (set CABINET_PYTHON)" >&2; exit 64; }
"$PY" -c 'import yaml' >/dev/null 2>&1 || { echo "one-responsibility: $PY lacks pyyaml" >&2; exit 64; }
command -v jq >/dev/null 2>&1 || { echo "one-responsibility: jq is absent — the locked hook needs it" >&2; exit 64; }
[ -f "$LIB_DIR/worker.py" ] || { echo "one-responsibility: missing $LIB_DIR/worker.py" >&2; exit 64; }
[ -f "$LIB_DIR/stub_dashboard.py" ] || { echo "one-responsibility: missing $LIB_DIR/stub_dashboard.py" >&2; exit 64; }
[ -f "$LIB_DIR/verdict.sh" ] || { echo "one-responsibility: missing $LIB_DIR/verdict.sh — without it every stage verdict would fail OPEN" >&2; exit 64; }
# shellcheck source=cabinet/scripts/drills/lib/verdict.sh
. "$LIB_DIR/verdict.sh"

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/one-responsibility.XXXXXX")" || exit 64
STAGES_FILE="$SCRATCH/stages.jsonl"
: > "$STAGES_FILE"
trap on_exit EXIT

if [ -n "$ROOT_ARG" ]; then
  mkdir -p "$ROOT_ARG" || fail 64 setup "cannot create --root $ROOT_ARG"
  ROOT="$(cd "$ROOT_ARG" && pwd)"
else
  ROOT="$SCRATCH/root"
  mkdir -p "$ROOT"
fi
HOME_DIR="$SCRATCH/home"
EVENTS="$ROOT/events"
STATE="$SCRATCH/state"
mkdir -p "$HOME_DIR" "$STATE"

# --- env scrub + pins (A4.3; null-hatch.sh:163-171 pattern) -----------------
while IFS='=' read -r _name _; do
  case "$_name" in
    CABINET_*|REDIS_*) unset "$_name" 2>/dev/null || true ;;
  esac
done < <(env)
unset PYTHONPATH DATABASE_URL ORG_RUNTIME_DB OFFICER_NAME 2>/dev/null || true

export HOME="$HOME_DIR"
export CABINET_ROOT="$ROOT"
export CABINET_EVENT_LOG_DIR="$EVENTS"
export SESSION_TASK_INJECT_DEBOUNCE_S=0
# The locked hook's stderr channel, pointed at this run's own scratch. The
# germline bundle's G3 bytes (landed 2026-09-08, contract amendment A7.7) send
# the pull call's stderr to ${CABINET_HOOK_LOG:-$HOME/Library/Logs/cabinet/
# hooks.err} and CREATE that directory, which is the whole point — a broken
# import and an empty queue used to look identical. Left at its default here it
# would create four paths under the scratch HOME and the hermeticity stage
# would report a write outside the root (measured: it did). Pinning it drives
# the override seam the bundle added instead of suppressing the channel, and
# keeps the "nothing outside the root" claim strict rather than allow-listed.
export CABINET_HOOK_LOG="$SCRATCH/locked-hook.err"
# A2.9. Production keeps MIN_LEASE_SECONDS = 60 and this variable is the ONLY
# sub-floor path. Without it P3's 3 s lease is clamped to 60, P4's bounded wait
# for the expiry can never observe one, and the kill/resume stage would red for
# a reason that has nothing to do with the claim. 1 is the hard minimum the
# amendment allows.
export CABINET_CLAIM_LEASE_FLOOR_SECONDS=1
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$EVENTS"

SLUG="drill-$("$PY" -c 'import uuid; print(uuid.uuid4().hex[:8])')"
SENTINEL="/tmp/.session-task-injected-${SLUG}"
rm -f "$SENTINEL" 2>/dev/null
OID="resp-001"
T1="$OID-task-001"
T2="$OID-task-002"

say "root=$ROOT slug=$SLUG"

# ---------------------------------------------------------------------------
# Stage the tree. `git archive HEAD` reads the COMMITTED tree, which is the
# only tree an export, a hatch or a stranger ever sees; a working-tree copy
# would let uncommitted bytes pass a proof about committed ones.
# ---------------------------------------------------------------------------
TREE_SOURCE=""
if [ -n "$TREE_ARG" ]; then
  [ -d "$TREE_ARG" ] || fail 64 hatch "--tree is not a directory: $TREE_ARG"
  TREE_SOURCE="tree:$TREE_ARG"
  tar -cf - -C "$TREE_ARG" --exclude='./.git' . | tar -xf - -C "$ROOT" \
    || fail 64 hatch "could not stage --tree $TREE_ARG"
elif git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  TREE_SOURCE="git archive HEAD @ $(git -C "$REPO_ROOT" rev-parse --short HEAD)"
  git -C "$REPO_ROOT" archive --format=tar HEAD | tar -xf - -C "$ROOT" \
    || fail 64 hatch "git archive HEAD failed"
else
  TREE_SOURCE="tar copy (gitless tree)"
  tar -cf - -C "$REPO_ROOT" --exclude='./.git' . | tar -xf - -C "$ROOT" \
    || fail 64 hatch "could not copy the gitless tree"
fi
note_stage hatch "staged from $TREE_SOURCE"

# THE SHIPPED TREE, kept before anything runs in it. P7 cuts its bundles from
# HERE and never from $ROOT: $ROOT becomes a RUNNING cabinet a few lines below
# (the hatch writes instance/config/cabinet-init.answers.yml, a lock file, a
# roster), and the exporter refuses a source that still carries live instance
# state — "LIVE INSTANCE FILE SURVIVED THE PASS", measured. That refusal is the
# exporter being right: a bundle is a cut of a checkout, not a copy of somebody
# running deployment. This copy is taken before the manifest scrub too, so the
# exporter does its own deleting exactly as it does on a real cut.
SHIPPED="$SCRATCH/shipped"
mkdir -p "$SHIPPED"
tar -cf - -C "$ROOT" . | tar -xf - -C "$SHIPPED" \
  || fail 64 hatch "could not keep a copy of the shipped tree for the update leg"

# A fresh hatch is what a STRANGER gets, and the export's own manifest is the
# authoritative answer to what a stranger does not get: every `delete
# instance/...` line names a path that belongs to THIS deployment and is
# scrubbed out of the egg. Staging the committed tree without applying that
# list hatches the Captain's own state and calls it fresh — his
# instance/config/outcomes.yml is pinned to his deployment id, so the compiler
# skips the whole file and every stage after the tap measures nothing while
# reporting a clean run. Derived from the manifest, never hand-listed, so it
# cannot rot away from the export.
MANIFEST="$ROOT/cabinet/scripts/egg-export-manifest.txt"
[ -f "$MANIFEST" ] || fail 64 hatch "no export manifest at cabinet/scripts/egg-export-manifest.txt — the drill cannot tell this deployment's state from the framework's"
SCRUBBED=0
while IFS= read -r _line || [ -n "$_line" ]; do
  case "$_line" in
    "delete instance/"*)
      _rel="${_line#delete }"
      case "$_rel" in *..*) continue ;; esac
      if [ -e "$ROOT/$_rel" ]; then
        rm -rf "${ROOT:?}/$_rel" || fail 64 hatch "could not scrub $_rel out of the scratch tree"
        SCRUBBED=$((SCRUBBED + 1))
      fi
      ;;
  esac
done < "$MANIFEST"
[ "$SCRUBBED" -gt 0 ] || fail 64 hatch "the export manifest named no instance path to scrub — either the manifest moved or its grammar changed, and the drill would silently hatch this deployment's own state"
note_stage hatch "scrubbed $SCRUBBED deployment-local instance path(s) named by the export manifest"

# --- hermeticity: the before picture ---------------------------------------
find "$HOME_DIR" 2>/dev/null | LC_ALL=C sort > "$SCRATCH/home.before"
( cd "$REPO_ROOT" && find . -not -path './.git/*' 2>/dev/null | LC_ALL=C sort ) > "$SCRATCH/repo.before"

# --- hatch: the real primitives --------------------------------------------
( cd "$ROOT" && "$PY" cabinet/scripts/generate-instance.py --defaults --root "$ROOT" ) \
  > "$SCRATCH/generate-instance.log" 2>&1 \
  || fail 64 hatch "generate-instance.py --defaults failed (see $SCRATCH/generate-instance.log)"

CABINET_ID="$(ROOTDIR="$ROOT" "$PY" - <<'PY'
import os, yaml
from pathlib import Path
p = Path(os.environ["ROOTDIR"]) / "instance/config/cabinet-init.answers.yml"
cid = ""
try:
    cid = str((yaml.safe_load(p.read_text()) or {}).get("cabinet", {}).get("id") or "")
except Exception:
    cid = ""
print(cid)
PY
)"
[ -n "$CABINET_ID" ] || fail 64 hatch "the hatch wrote no cabinet id — nothing to pin"
export CABINET_ID

# The roster is the HIRE record and it is the drill's, not a live deployment's:
# the slug must be absent from every live roster or the locked hook's /tmp
# sentinel collides with a running officer's.
cat > "$ROOT/instance/config/roster.yml" <<EOF
# roster for the one-responsibility drill — one holder, generated per run.
roster:
  $SLUG:
    title: Drill Holder
    type: fulltime
    model: drill-model
    capabilities: [validates_deployments]
    authority_level: standard
EOF
( cd "$ROOT" && bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml --product-slug drill ) \
  > "$SCRATCH/bootstrap-roles.log" 2>&1 \
  || fail 64 hatch "bootstrap-roles.sh failed (see $SCRATCH/bootstrap-roles.log)"
[ -f "$ROOT/instance/roles/active/$SLUG.yml" ] \
  || fail 64 hatch "the roster did not produce instance/roles/active/$SLUG.yml"
pass_stage hatch "fresh hatch, one active role ($SLUG), cabinet id $CABINET_ID"

# ---------------------------------------------------------------------------
# Seed the responsibility. One deterministic card through the real proposal
# writer, then the two rich criteria the Captain would have written on it —
# the documented review-and-edit step, re-stamped so the row reads as
# unedited-since-proposed and the tap's digest arm has something true to check.
# ---------------------------------------------------------------------------
ROOTDIR="$ROOT" DRILL_SLUG="$SLUG" OID="$OID" T1="$T1" T2="$T2" "$PY" - <<'PY' > "$SCRATCH/seed.log" 2>&1 || fail 64 seed "could not seed the responsibility (see $SCRATCH/seed.log)"
import os, sys, yaml
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.onboarding import genesis
slug, oid = os.environ["DRILL_SLUG"], os.environ["OID"]
t1, t2 = os.environ["T1"], os.environ["T2"]
card = {
    "id": oid,
    "name": "One responsibility, carried end to end",
    "lane": "first-lane",
    "what": "Carry one declared responsibility from ratification to a recorded result.",
    "why": "The acceptance drill needs one responsibility it can carry deterministically.",
    "proof_expected": "Two recorded results, each with a written record kept under evidence/.",
    "proposed_by": "one-responsibility-drill",
}
res = genesis.merge_proposals([card], root)
assert res.get("written"), res
path = root / genesis.PROPOSALS_REL
doc = yaml.safe_load(path.read_text(encoding="utf-8"))
rows = [r for r in doc["outcomes"] if str(r.get("id")) == oid]
assert len(rows) == 1, rows
row = rows[0]
row["measurable_criteria"] = [
    {"node_id": t1,
     "title": "Record the first result of the declared responsibility",
     "owner_role": slug,
     "acceptance_criteria": ["A written record is kept under evidence/",
                             "The record names the holder that produced it"],
     "evidence_required": "a written record kept under evidence/",
     "depends_on": []},
    {"node_id": t2,
     "title": "Record the second result of the declared responsibility",
     "owner_role": slug,
     "acceptance_criteria": ["A written record is kept under evidence/",
                             "The record follows the first one"],
     "evidence_required": "a written record kept under evidence/",
     "depends_on": [t1]},
]
genesis._stamp_row_digests(doc["outcomes"])
raw = path.read_text(encoding="utf-8")
path.write_text(genesis._preserved_header(raw)
                + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100),
                encoding="utf-8")
print("seeded", oid)
PY
pass_stage seed "one card ($OID) with two rich criteria, chained"

# ---------------------------------------------------------------------------
# P1 — the tap. A named door ratifies; nobody edits a file by hand.
# The terminal door is attribution, not authentication: it is the same uid as
# every officer, so its actor is `operator` and never `captain`.
# ---------------------------------------------------------------------------
PRINCIPAL="$(id -un 2>/dev/null || echo unknown)"
( cd "$ROOT" && "$PY" -m framework.outcomes.ratify "$OID" --door terminal --principal "$PRINCIPAL" --json ) \
  > "$SCRATCH/p1-ratify.out" 2> "$SCRATCH/p1-ratify.err"
RATIFY_RC=$?
if [ "$RATIFY_RC" -ne 0 ]; then
  fail 10 P1 "the tap did not ratify $OID (exit $RATIFY_RC): $(tr '\n' ' ' < "$SCRATCH/p1-ratify.err" | cut -c1-400)"
fi

# stderr goes to its OWN file: folded into the file the verdict is read from,
# one library warning would make the payload unparseable and the stage would
# print a claim that is false in every clause.
ROOTDIR="$ROOT" OID="$OID" "$PY" - > "$SCRATCH/p1-assert.out" 2> "$SCRATCH/p1-assert.err" <<'PY'
import json, os, sys, hashlib, yaml
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.events.emitter import replay
oid = os.environ["OID"]
out = root / "instance/config/outcomes.yml"
problems = []
if not out.is_file():
    problems.append("instance/config/outcomes.yml was not written")
else:
    doc = yaml.safe_load(out.read_text(encoding="utf-8")) or {}
    rows = [r for r in (doc.get("outcomes") or []) if str(r.get("id")) == oid]
    if len(rows) != 1:
        problems.append("outcomes.yml holds %d rows for %s" % (len(rows), oid))
    else:
        row = rows[0]
        if row.get("status") != "active":
            problems.append("row status is %r, not active" % row.get("status"))
        if row.get("captain_ratified") is not True:
            problems.append("row captain_ratified is %r" % row.get("captain_ratified"))
evs = [e for e in replay(event_types=["captain_outcome_ratified"])
       if (e.get("payload") or {}).get("outcome_id") == oid]
if len(evs) != 1:
    problems.append("captain_outcome_ratified count is %d, expected 1" % len(evs))
else:
    ev = evs[0]
    payload = ev.get("payload") or {}
    if ev.get("actor") != "operator":
        problems.append("actor is %r; the terminal door is attribution, not authentication,"
                        " so it must never yield captain" % ev.get("actor"))
    if payload.get("door") != "terminal":
        problems.append("payload door is %r, expected terminal" % payload.get("door"))
    if not payload.get("principal"):
        problems.append("payload names no principal")
digests = {}
for rel in ("instance/config/outcomes.yml", "instance/config/outcomes-proposed.yml"):
    p = root / rel
    digests[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""
print(json.dumps({"code": 0 if not problems else 10, "problems": problems,
                  "digests": digests}, sort_keys=True))
print(os.environ["DRILL_VERDICT_SENTINEL"])
PY
read_verdict P1 10 $? "$SCRATCH/p1-assert.out" "$SCRATCH/p1-assert.err"
printf '%s' "$V_JSON" | "$PY" -c '
import json, sys
digests = json.load(sys.stdin).get("digests")
if not isinstance(digests, dict) or not digests:
    raise SystemExit(1)
json.dump(digests, open(sys.argv[1], "w"))
' "$SCRATCH/p1-digests.json" \
  || fail 10 P1 "the tap recorded no file digests, so P5 could not tell whether carrying the work rewrote the Captain's own declaration"
pass_stage P1 "$OID ratified through the terminal door by $PRINCIPAL, one event, actor operator"

# ---------------------------------------------------------------------------
# P2 — the claim. Eight holders pull at once through the REAL pull path. One
# item, one holder, one started event. The losers are proved by the ledger,
# never by hook silence: silence has too many causes to be evidence.
# ---------------------------------------------------------------------------
mkdir -p "$SCRATCH/p2"
P2_PIDS=""
i=1
while [ "$i" -le 8 ]; do
  "$PY" "$LIB_DIR/worker.py" --root "$ROOT" --slug "$SLUG" \
    --holder "$SLUG@w$i" --mode pull > "$SCRATCH/p2/w$i.json" 2>"$SCRATCH/p2/w$i.err" &
  P2_PIDS="$P2_PIDS $!"
  WORKER_PIDS="$WORKER_PIDS $!"
  i=$((i + 1))
done
# Every holder's exit status, one line each. A bare `wait` discards them, and a
# holder that died before it reached the pull path is not a loser — it is a
# holder that was never in the crowd. Scoring "8 holders, 1 claim" on a crowd
# of one is the same fail-open as scoring an assertion block that crashed:
# the channel that carries a stage's VERDICT was closed in the last round, and
# this is the channel that carries its PARTICIPATION.
: > "$SCRATCH/p2/rc.txt"
i=1
for _pid in $P2_PIDS; do
  wait "$_pid"; _rc=$?
  printf 'w%d %d\n' "$i" "$_rc" >> "$SCRATCH/p2/rc.txt"
  i=$((i + 1))
done
WORKER_PIDS=""

ROOTDIR="$ROOT" P2DIR="$SCRATCH/p2" P2RC="$SCRATCH/p2/rc.txt" OID="$OID" TID="$T1" "$PY" - \
  > "$SCRATCH/p2-assert.out" 2> "$SCRATCH/p2-assert.err" <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.events.emitter import replay
p2 = Path(os.environ["P2DIR"]); oid, tid = os.environ["OID"], os.environ["TID"]

# Exit status per holder, written by the drill one `wait` at a time. A holder
# whose status was never recorded counts as a holder that did not run: "not
# measured" and "measured clean" are different facts here too.
rcs = {}
rc_path = Path(os.environ["P2RC"])
if rc_path.is_file():
    for line in rc_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            rcs[parts[0]] = int(parts[1])

# PARTICIPATION before verdict. Eight holders racing for one item is the whole
# claim of this stage; seven holders that died on the way to the pull path make
# the eighth's success mean nothing, and every one of those seven would
# otherwise read as a well-behaved loser.
results, absent = [], []
for n in range(1, 9):
    who = "w%d" % n
    out_path, err_path = p2 / (who + ".json"), p2 / (who + ".err")
    raw = out_path.read_text(encoding="utf-8").strip() if out_path.is_file() else ""
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("the holder printed something that is not a result object")
    except Exception:
        parsed = None
    tail = ""
    if err_path.is_file():
        tail = err_path.read_text(encoding="utf-8", errors="replace").strip()[-160:]
    if parsed is None:
        reason = ("printed no readable result (%r%s)"
                  % (raw[:80], (" stderr: " + tail) if tail else ""))
    elif parsed.get("module_error"):
        reason = "could not import %s" % parsed["module_error"]
    elif parsed.get("error"):
        reason = "failed: %s" % (str(parsed["error"])[:120],)
    elif parsed.get("ok") is not True:
        reason = "reported ok=%r" % (parsed.get("ok"),)
    elif who not in rcs:
        reason = "ran with no exit status recorded, so nothing about it was measured"
    elif rcs[who] != 0:
        reason = "exited %d" % rcs[who]
    else:
        reason = None
    results.append(parsed)
    if reason:
        absent.append("%s %s" % (who, reason))

unimportable = sum(1 for r in results if r and r.get("module_error"))
winners = [r for r in results if r and (r.get("task") or {}).get("task_id")]
started = [e for e in replay(event_types=["work_item_started"])
           if (e.get("payload") or {}).get("task_id") == tid]
problems = []
if unimportable == len(results):
    first = next((r for r in results if r), {})
    print(json.dumps({"code": 21, "problems": [
        "the pull path could not be imported by any of the 8 holders: %s"
        % (first.get("error") or "<no reason given>")]}, sort_keys=True))
    print(os.environ["DRILL_VERDICT_SENTINEL"])
    raise SystemExit(0)
if len(absent) == len(results):
    print(json.dumps({"code": 21, "problems": [
        "not one of the 8 holders reached the pull path, so the claim was never "
        "measured at all: %s" % "; ".join(absent[:3])]}, sort_keys=True))
    print(os.environ["DRILL_VERDICT_SENTINEL"])
    raise SystemExit(0)
if absent:
    problems.append("%d of the 8 holders never reached the pull path (%s), so the crowd "
                    "was not a crowd; one holder that succeeds while the rest die proves "
                    "nothing about a claim under contention"
                    % (len(absent), "; ".join(absent[:4])))
if len(winners) != 1 or len(started) != 1:
    problems.append("8 holders pulled at once: %d got the item, %d work_item_started "
                    "events landed; exactly 1 of each is the claim"
                    % (len(winners), len(started)))
if len(started) == 1:
    p = started[0].get("payload") or {}
    if p.get("task_id") != tid:
        problems.append("started task_id %r, expected %r" % (p.get("task_id"), tid))
    if p.get("outcome_id") != oid:
        problems.append("started outcome_id %r, expected %r" % (p.get("outcome_id"), oid))
    if not p.get("claim_id"):
        problems.append("the started event carries no claim_id — an unguessable token is the fence")
    if not p.get("holder"):
        problems.append("the started event names no holder")
    elif winners and p.get("holder") != winners[0].get("holder"):
        problems.append("started holder %r is not the holder that got the item (%r)"
                        % (p.get("holder"), winners[0].get("holder")))
out = {"code": 0 if not problems else 20, "problems": problems,
       "winner": (winners[0].get("holder") if len(winners) == 1 else None),
       "claim_id": ((started[0].get("payload") or {}).get("claim_id") if len(started) == 1 else None)}
print(json.dumps(out, sort_keys=True))
print(os.environ["DRILL_VERDICT_SENTINEL"])
PY
read_verdict P2 20 $? "$SCRATCH/p2-assert.out" "$SCRATCH/p2-assert.err"
vfield P2 20 winner
WINNER="$V_FIELD"
vfield P2 20 claim_id
P2_CLAIM="$V_FIELD"

# THE RACE IS OVER AND THE WINNER IS STILL HOLDING THE ITEM. A claim outlives
# the process that took it — that is the whole point of a lease — so on the
# production default the item stays w-something's for 900 s and every later
# stage that needs to claim it is handed nothing. Measured: P3 red with
# `"task": null` because the pull path was working exactly as specified.
# The winner therefore stands down through the claim module's own
# `release()` — "a caller that knows it is done can hand the task back before
# its lease runs out" (framework/missions/claims.py:615-622). The two
# alternatives are both worse: racing on a short lease makes P2 fail for the
# host's speed (eight interpreters must all reach the pull path inside the
# lease or a second one takes over an expired claim and the race reports two
# winners), and waiting out a production lease is not a bounded poll. The
# stand-down reason is `released`, never `expired`, so P4's expired-release
# arm still has exactly one row to find and it is the killed holder's.
ROOTDIR="$ROOT" TID="$T1" CLAIMID="$P2_CLAIM" HOLDER="$WINNER" "$PY" - \
  > "$SCRATCH/p2-standdown.out" 2> "$SCRATCH/p2-standdown.err" <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.missions.claims import live_claim, release
tid, claim_id, holder = os.environ["TID"], os.environ["CLAIMID"], os.environ["HOLDER"]
problems = []
if not release(claim_id, holder, "released"):
    problems.append("the race winner %r could not hand %s back (claim %r); the kill stage "
                    "needs a free item and would otherwise measure a pull that found nothing"
                    % (holder, tid, claim_id))
live = live_claim(tid)
if live:
    problems.append("%s is still held by %r after the winner stood down"
                    % (tid, live.get("holder")))
print(json.dumps({"code": 0 if not problems else 20, "problems": problems}, sort_keys=True))
print(os.environ["DRILL_VERDICT_SENTINEL"])
PY
read_verdict P2 20 $? "$SCRATCH/p2-standdown.out" "$SCRATCH/p2-standdown.err"
pass_stage P2 "8 holders, 1 claim on $T1, holder $WINNER; the winner stood down so the kill stage starts from a free item"

# ---------------------------------------------------------------------------
# P2b — the assignment fallback. A real card carries string criteria and
# matches no capability keyword, so without a fallback the Captain's own tap
# yields a gap instead of work. One role on the roster: it is that role's.
# Two: it is a gap, named, not silence.
# ---------------------------------------------------------------------------
ROOTDIR="$ROOT" DRILL_SLUG="$SLUG" "$PY" - \
  > "$SCRATCH/p2b-assert.out" 2> "$SCRATCH/p2b-assert.err" <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
slug = os.environ["DRILL_SLUG"]
problems = []
try:
    from framework.missions.compiler import compile_outcome
    from framework.missions.gaps import observe_holder_gaps
except ImportError as exc:
    print(json.dumps({"code": 21,
                      "problems": ["P2b needs a module that is absent: %s" % exc]},
                     sort_keys=True))
    print(os.environ["DRILL_VERDICT_SENTINEL"])
    raise SystemExit(0)
outcome = {"id": "resp-002", "name": "An unowned responsibility",
           "status": "active",
           "measurable_criteria": ["Keep one written record of what was carried"]}
one = [{"slug": slug, "capabilities": []}]
two = [{"slug": slug, "capabilities": []}, {"slug": "drill-second", "capabilities": []}]
m1 = compile_outcome(dict(outcome), actor="drill", roles=one, emit_event=False)
node1 = list(m1["work_graph"].nodes.values())[0]
if node1.assigned_role != slug:
    problems.append("one role on the roster and an unowned node was assigned to %r, "
                    "not %r — the Captain's own card would yield a gap, not work"
                    % (node1.assigned_role, slug))
m2 = compile_outcome(dict(outcome), actor="drill", roles=two, emit_event=False)
node2 = list(m2["work_graph"].nodes.values())[0]
if node2.assigned_role is not None:
    problems.append("two roles on the roster and an unowned node was assigned to %r; "
                    "with no owner and no match it must become a gap" % node2.assigned_role)
res = observe_holder_gaps([m2], {slug, "drill-second"}, actor="drill")
# `opened` is the LIST of gap ids the pass opened (gaps.py:229 — "of gap ids,
# each subject appearing at most once across the three"), not a count. This
# drill first read it as a count and reported a correct single gap as wrong,
# which is a sensor that reds on a subject doing exactly what it promises.
# Anything that is not a list is a shape change, and it is named as one rather
# than crashing this block with a TypeError the verdict would report as
# "the assertion could not run".
opened = res.get("opened")
if not isinstance(opened, list):
    problems.append("observe_holder_gaps returned %r for 'opened'; the contract is a list "
                    "of gap ids and this drill counts it as one" % (opened,))
elif len(opened) != 1:
    problems.append("observe_holder_gaps opened %d holder gaps (%r) on a two-role roster, "
                    "expected exactly 1" % (len(opened), opened))
from framework.learning.capability_gaps import project_gaps
no_match = [g for g in project_gaps() if "no_match" in json.dumps(g, default=str)]
if len(no_match) != 1:
    problems.append("%d no_match gaps recorded, expected exactly 1" % len(no_match))
print(json.dumps({"code": 0 if not problems else 20, "problems": problems}, sort_keys=True))
print(os.environ["DRILL_VERDICT_SENTINEL"])
PY
read_verdict P2b 20 $? "$SCRATCH/p2b-assert.out" "$SCRATCH/p2b-assert.err"
pass_stage P2b "unowned node assigned on a one-role roster; exactly one no_match gap on two"

# ---------------------------------------------------------------------------
# P3 — killed inside the work. The kill lands between the claim and the
# completion while a renewal tick is due, at a scaled cadence (tick 1s, lease
# 3s) so a lease that only renews when nearly spent is visible as a defect
# rather than as a slow test.
#
# KNOWN RACE, named rather than left to be re-derived. The kill lands within
# ~0.25 s of the first renewal, which leaves roughly LEASE_S minus a tick for a
# fresh interpreter to start, import the emitter and the claims module, and ask
# who holds the task. On a loaded host that window can close, the lease expires
# before the question is asked, and the stage reds on "nothing holds <task>" —
# a wall-clock artefact of this host, not a defect in the subject. Two things
# keep that honest: CABINET_DRILL_LEASE_SECONDS raises the window without
# touching the code, and the assertion below reads the killed holder's own
# recorded expires_at, so an expiry that beat the assertion is reported AS an
# expiry that beat the assertion. It still FAILS — a stage that cannot measure
# what it names has not measured it — but it fails saying the true thing.
# ---------------------------------------------------------------------------
rm -f "$STATE/proceed" "$STATE/claimed.$SLUG@w1" "$STATE/renewed.$SLUG@w1"
"$PY" "$LIB_DIR/worker.py" --root "$ROOT" --slug "$SLUG" --holder "$SLUG@w1" \
  --lease "$LEASE_S" --renew-every 1 --mode work --pause-before-complete \
  --state-dir "$STATE" --pause-timeout 30 > "$SCRATCH/p3-w1.json" 2>"$SCRATCH/p3-w1.err" &
W1_PID=$!
WORKER_PIDS="$WORKER_PIDS $W1_PID"

CLAIMED=0
i=0
while [ "$i" -lt 40 ]; do
  if [ -f "$STATE/claimed.$SLUG@w1" ]; then CLAIMED=1; break; fi
  if ! kill -0 "$W1_PID" 2>/dev/null; then break; fi
  "$PY" -c 'import time; time.sleep(0.25)'
  i=$((i + 1))
done
if [ "$CLAIMED" != "1" ]; then
  kill -KILL "$W1_PID" 2>/dev/null || true
  fail 30 P3 "w1 never claimed within 10s: $(tr '\n' ' ' < "$SCRATCH/p3-w1.json" | cut -c1-300)$(tr '\n' ' ' < "$SCRATCH/p3-w1.err" | cut -c1-200)"
fi

# Wait for the FIRST renewal before killing. A kill before any tick would leave
# "renew on every tick" untested, and the drill would pass on a lease that only
# renews when it is nearly spent — the defect A2.1 names.
RENEWED=0
i=0
while [ "$i" -lt 60 ]; do
  if [ -f "$STATE/renewed.$SLUG@w1" ]; then RENEWED=1; break; fi
  if ! kill -0 "$W1_PID" 2>/dev/null; then break; fi
  "$PY" -c 'import time; time.sleep(0.25)'
  i=$((i + 1))
done
kill -KILL "$W1_PID" 2>/dev/null || true
wait "$W1_PID" 2>/dev/null || true
WORKER_PIDS=""
if [ "$RENEWED" != "1" ]; then
  fail 30 P3 "w1 held $T1 for a whole tick and never renewed its claim (lease ${LEASE_S}s, tick 1s); a lease that is not renewed on the tick loses every item that outlives it"
fi

W1_CLAIM="$(CLAIMED="$STATE/claimed.$SLUG@w1" "$PY" - 2>/dev/null <<'PY'
import json, os, sys
sys.stdout.write(str(json.load(open(os.environ["CLAIMED"])).get("claim_id") or ""))
PY
)" || fail 30 P3 "the killed holder's own record of its claim could not be read back"
[ -n "$W1_CLAIM" ] || fail 30 P3 "the pull path handed w1 the item with no claim token, so P4 cannot tell a NEW claim from the dead holder's old one and the fence has nothing to refuse"

ROOTDIR="$ROOT" TID="$T1" HOLDER="$SLUG@w1" SLUGV="$SLUG" \
  CLAIMEDFILE="$STATE/claimed.$SLUG@w1" "$PY" - \
  > "$SCRATCH/p3-assert.out" 2> "$SCRATCH/p3-assert.err" <<'PY'
import json, os, sys, time
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.events.emitter import replay
tid, holder, slug = os.environ["TID"], os.environ["HOLDER"], os.environ["SLUGV"]
problems = []
done = [e for e in replay(event_types=["work_item_completed", "work_item_verified"])
        if (e.get("payload") or {}).get("task_id") == tid]
if done:
    problems.append("%d completion events for %s after the holder was killed mid-work"
                    % (len(done), tid))
try:
    from framework.missions.claims import live_claim
except ImportError as exc:
    problems.append("no claims module to ask who holds %s: %s" % (tid, exc))
else:
    live = live_claim(tid)
    if not live:
        # Distinguish the defect from the host. The killed holder wrote what it
        # was handed, expires_at included; if that moment has already passed,
        # the lease outran the assertion and the stage says so instead of
        # blaming a claim path that may be perfectly correct.
        expired_first = None
        try:
            claimed = json.loads(Path(os.environ["CLAIMEDFILE"]).read_text(encoding="utf-8"))
            raw = claimed.get("expires_at")
            if raw is not None:
                try:
                    expired_first = float(raw) <= time.time()
                except (TypeError, ValueError):
                    from datetime import datetime
                    stamp = str(raw).replace("Z", "+00:00")
                    expired_first = datetime.fromisoformat(stamp).timestamp() <= time.time()
        except Exception:
            expired_first = None
        if expired_first:
            problems.append("nothing holds %s after the kill, and the claim the holder was "
                            "given had ALREADY expired by the time this ran (expires_at %r) "
                            "— the lease outran the assertion on this host; raise "
                            "CABINET_DRILL_LEASE_SECONDS and run it again" % (tid, raw))
        else:
            problems.append("nothing holds %s after the kill — the lease is the liveness "
                            "signal and it has not expired yet" % tid)
    elif live.get("holder") != holder:
        problems.append("%s is held by %r, expected %r" % (tid, live.get("holder"), holder))
# The next holder tries while the claim is still live, IN THIS PROCESS: a
# second interpreter start would spend the lease it is trying to observe.
os.environ["CABINET_WORKER_ID"] = slug + "@w9"
try:
    from framework.missions.session_bridge import get_next_task
except ImportError as exc:
    problems.append("no pull path for the next holder to try: %s" % exc)
else:
    other = get_next_task(slug, cabinet_root=str(root))
    if other and other.get("task_id") == tid:
        problems.append("a second holder was handed %s while the first holder's claim "
                        "is still live" % tid)
print(json.dumps({"code": 0 if not problems else 30, "problems": problems}, sort_keys=True))
print(os.environ["DRILL_VERDICT_SENTINEL"])
PY
read_verdict P3 30 $? "$SCRATCH/p3-assert.out" "$SCRATCH/p3-assert.err"
pass_stage P3 "w1 killed mid-work; nothing completed; the claim is still w1's"

# ---------------------------------------------------------------------------
# P4 — resume by expiry, and only by expiry. A same-holder re-claim across a
# restart is indistinguishable from a live twin stealing its own claim, which
# is the concurrency this whole unit exists to prevent.
# ---------------------------------------------------------------------------
# Past the lease, inline and bounded. The live-claim arm ran inside P3's own
# process (above) precisely because this lease is short on purpose.
LEASE_WAIT="$("$PY" -c "print($LEASE_S + 2)")"
"$PY" -c "import time; time.sleep($LEASE_WAIT)"

# No card, no prompt, no argument carrying the work: the resume worker's only
# input is the durable state — the env and the files.
# An ARRAY, not a string: a --root or --state-dir carrying a space would word
# split out of a bare expansion and the stage would fail for a reason that has
# nothing to do with the resume. The forbidden-token scan below reads the same
# array, one element per line, so the thing scanned is the thing passed.
RESUME_ARGV=(--root "$ROOT" --slug "$SLUG" --holder "$SLUG@w2" --lease 60 --mode work --state-dir "$STATE")
"$PY" "$LIB_DIR/worker.py" "${RESUME_ARGV[@]}" > "$SCRATCH/p4-w2.json" 2>"$SCRATCH/p4-w2.err"
P4_RC=$?
if [ "$P4_RC" -ne 0 ]; then
  fail 30 P4 "the resuming holder w2 exited $P4_RC: $(tr '\n' ' ' < "$SCRATCH/p4-w2.json" | cut -c1-300)$(tr '\n' ' ' < "$SCRATCH/p4-w2.err" | cut -c1-200)"
fi

ROOTDIR="$ROOT" TID="$T1" OLDCLAIM="$W1_CLAIM" OLDHOLDER="$SLUG@w1" \
  ARGV="$(printf '%s\n' "${RESUME_ARGV[@]}")" "$PY" - \
  > "$SCRATCH/p4-assert.out" 2> "$SCRATCH/p4-assert.err" <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.events.emitter import replay
tid, old_claim = os.environ["TID"], os.environ["OLDCLAIM"]
problems = []
released = [e for e in replay(event_types=["work_item_claim_released"])
            if (e.get("payload") or {}).get("task_id") == tid]
expired = [e for e in released if (e.get("payload") or {}).get("reason") == "expired"]
if not expired:
    problems.append("no work_item_claim_released{reason: expired} for %s — an expired "
                    "lease that releases nothing leaves the item stuck" % tid)
elif old_claim and (expired[0].get("payload") or {}).get("claim_id") != old_claim:
    problems.append("the released claim is %r, not the killed holder's %r"
                    % ((expired[0].get("payload") or {}).get("claim_id"), old_claim))
starts = [e for e in replay(event_types=["work_item_started"])
          if (e.get("payload") or {}).get("task_id") == tid]
claims = [(e.get("payload") or {}).get("claim_id") for e in starts]
if len(starts) < 2:
    problems.append("%d started events for %s; the resume must be a NEW claim" % (len(starts), tid))
elif old_claim and claims[-1] == old_claim:
    problems.append("the resuming holder reused claim %r — a resume is a new claim" % old_claim)
done = [e for e in replay(event_types=["work_item_completed"])
        if (e.get("payload") or {}).get("task_id") == tid]
if len(done) != 1:
    problems.append("%d completions for %s, expected exactly 1" % (len(done), tid))
argv = os.environ["ARGV"].splitlines()
for forbidden in ("--description", "Record the first result", "resp-001-task-001"):
    if any(forbidden in word for word in argv):
        problems.append("the resuming worker was handed %r on its command line; its only "
                        "input must be the durable state" % forbidden)
print(json.dumps({"code": 0 if not problems else 30, "problems": problems}, sort_keys=True))
print(os.environ["DRILL_VERDICT_SENTINEL"])
PY
read_verdict P4 30 $? "$SCRATCH/p4-assert.out" "$SCRATCH/p4-assert.err"

# The late completion: the killed holder wakes up and tries to close the item
# with the token it still remembers. It must be refused, and refused silently
# in the ledger — a refusal that still emits is not a fence.
ledger_lines P4 30
EV_BEFORE="$LEDGER_LINES"
( cd "$ROOT" && OFFICER_NAME="$SLUG" bash cabinet/scripts/work-graph-complete.sh "$T1" \
    --status "done" --actor "$SLUG" --evidence "late completion by a dead holder" \
    --claim "$W1_CLAIM" ) > "$SCRATCH/p4-late.out" 2>&1
LATE_RC=$?
ledger_lines P4 30
EV_AFTER="$LEDGER_LINES"
if [ "$LATE_RC" -ne 4 ]; then
  fail 30 P4 "a late completion with the dead holder's token exited $LATE_RC, expected 4: $(tr '\n' ' ' < "$SCRATCH/p4-late.out" | cut -c1-300)"
fi
[ "$EV_BEFORE" = "$EV_AFTER" ] || fail 30 P4 "the refused late completion still wrote to the ledger"
pass_stage P4 "expired lease released w1's claim; w2 took a new one and finished; the late token was refused"

# ---------------------------------------------------------------------------
# P2h — the locked hook's own shell path, unmodified, with the box's own
# python3. This is the path an officer actually walks; a drill that only
# exercised the python functions would be measuring a road nobody drives.
# ---------------------------------------------------------------------------
HOOK="$ROOT/cabinet/scripts/hooks/session-task-inject.sh"
[ -f "$HOOK" ] || fail 20 P2h "the locked hook is absent at cabinet/scripts/hooks/session-task-inject.sh"
( cd "$ROOT" && PYTHONPATH="$BOX_PY_DEPS" "$BOX_PY" -c "
import sys; sys.path.insert(0, '$ROOT')
from framework.missions.session_bridge import get_next_task, format_task_for_session
" ) > "$SCRATCH/p2h-import.out" 2>&1
HOOK_IMPORT_RC=$?
if [ "$HOOK_IMPORT_RC" -ne 0 ]; then
  fail 21 P2h "the locked hook's interpreter ($BOX_PY, $("$BOX_PY" -V 2>&1)) cannot import the pull path, so the real pull path is broken for any session on this host and the drill cannot measure the claim through it: $(tr '\n' ' ' < "$SCRATCH/p2h-import.out" | cut -c1-400)"
fi

rm -f "$SENTINEL"
unset CABINET_WORKER_ID 2>/dev/null || true
# Two ticks from two DISTINCT parent shells with no worker id set: two live
# sessions of one role must still resolve to one claim.
bash -c "printf '{\"session_id\":\"a\"}' | $HOOK_PY_ENV OFFICER_NAME='$SLUG' CABINET_ROOT='$ROOT' bash '$HOOK'" \
  > "$SCRATCH/p2h-a.json" 2>"$SCRATCH/p2h-a.err" &
HA=$!
bash -c "printf '{\"session_id\":\"b\"}' | $HOOK_PY_ENV OFFICER_NAME='$SLUG' CABINET_ROOT='$ROOT' bash '$HOOK'" \
  > "$SCRATCH/p2h-b.json" 2>"$SCRATCH/p2h-b.err" &
HB=$!
WORKER_PIDS="$WORKER_PIDS $HA $HB"
# Each leg's own status. Silence from the hook is how a LOSER looks — so a leg
# that crashed looks exactly like a leg that lost, and discarding the status
# (`wait … || true`) is what makes the two indistinguishable. One session that
# ticked and one that fell over is not "two sessions of one role".
wait "$HA"; HA_RC=$?
wait "$HB"; HB_RC=$?
WORKER_PIDS=""

ROOTDIR="$ROOT" TID="$T2" AOUT="$SCRATCH/p2h-a.json" BOUT="$SCRATCH/p2h-b.json" \
  ARC="$HA_RC" BRC="$HB_RC" AERR="$SCRATCH/p2h-a.err" BERR="$SCRATCH/p2h-b.err" "$PY" - \
  > "$SCRATCH/p2h-assert.out" 2> "$SCRATCH/p2h-assert.err" <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.events.emitter import replay
tid = os.environ["TID"]
problems, ctx = [], []
# A hook leg that exited non-zero prints nothing, and printing nothing is
# exactly what a legitimate LOSER does. So the status is the only thing that
# separates "this session lost the race" from "this session fell over", and a
# crashed leg scored as a loser would make one tick look like two.
for key, rckey, errkey in (("AOUT", "ARC", "AERR"), ("BOUT", "BRC", "BERR")):
    rc = os.environ.get(rckey, "")
    if rc != "0":
        tail = ""
        err = Path(os.environ.get(errkey) or "/nonexistent")
        if err.is_file():
            tail = err.read_text(encoding="utf-8", errors="replace").strip()[-200:]
        problems.append("the %s hook leg exited %r rather than 0, so its silence is a crash "
                        "and not a lost race: %s" % (key[0].lower(), rc, tail))
        continue
    raw = Path(os.environ[key]).read_text(encoding="utf-8").strip()
    if not raw:
        continue
    try:
        ctx.append(json.loads(raw)["hookSpecificOutput"]["additionalContext"])
    except Exception as exc:
        problems.append("the hook printed something that is not its output contract: %r (%s)"
                        % (raw[:160], exc))
starts = [e for e in replay(event_types=["work_item_started"])
          if (e.get("payload") or {}).get("task_id") == tid]
if len(starts) != 1:
    problems.append("two sessions of one role ticked the locked hook and %d claims landed "
                    "on %s; exactly 1 is the claim" % (len(starts), tid))
if not ctx:
    problems.append("neither hook tick injected anything — the real pull path returned no "
                    "work for a ready, owned task")
elif not any("Record the second result" in c for c in ctx):
    problems.append("the injected context does not carry the task: %r" % (ctx[0][:200],))
holder = (starts[0].get("payload") or {}).get("holder") if len(starts) == 1 else None
claim = (starts[0].get("payload") or {}).get("claim_id") if len(starts) == 1 else None
if len(starts) == 1 and not holder:
    problems.append("the hook's claim names no holder, so two sessions of one role are "
                    "indistinguishable")
print(json.dumps({"code": 0 if not problems else 20, "problems": problems,
                  "holder": holder, "claim_id": claim}, sort_keys=True))
print(os.environ["DRILL_VERDICT_SENTINEL"])
PY
read_verdict P2h 20 $? "$SCRATCH/p2h-assert.out" "$SCRATCH/p2h-assert.err"
vfield P2h 20 holder
HOOK_HOLDER="$V_FIELD"
vfield P2h 20 claim_id
HOOK_CLAIM="$V_FIELD"

# The same session ticks again. Its own live claim is renewed, not re-injected:
# a hook that re-injects what it already holds re-injects it for the whole life
# of the session.
#
# "THE SAME SESSION" IS A PROPERTY OF THE PAYLOAD, not of the environment, and
# this line used to assume it was `a`. The germline bundle's G3 bytes (landed
# 2026-09-08, contract amendment A7.7) derive the holder from the payload's
# `session_id` and EXPORT `CABINET_WORKER_ID` over whatever was inherited, so a
# re-tick that carried `a` after leg `b` won the race above is a DIFFERENT
# holder — and being handed the item again is then correct behaviour, not the
# defect this leg names. Measured: with the landed bytes and a hardcoded `a`,
# P2h fails ~half its runs with "the holder's own tick did not renew its
# claim". The winning session id is therefore read back out of the holder the
# race actually produced (`<role>@<session id>`). `CABINET_WORKER_ID` is still
# set as well, because a box whose locked copy predates the window runs the
# unpinned bytes, which export nothing and fall back to `<role>@session:<pid>`.
case "$HOOK_HOLDER" in
  *@*) HOOK_SESSION="${HOOK_HOLDER##*@}" ;;
  *) fail 20 P2h "the hook's claim holder '$HOOK_HOLDER' carries no session part, so two sessions of one role cannot be told apart and this leg cannot re-tick as the holder" ;;
esac
rm -f "$SENTINEL"
CABINET_WORKER_ID="$HOOK_HOLDER" bash -c "printf '{\"session_id\":\"$HOOK_SESSION\"}' | $HOOK_PY_ENV OFFICER_NAME='$SLUG' CABINET_ROOT='$ROOT' bash '$HOOK'" \
  > "$SCRATCH/p2h-again.json" 2>"$SCRATCH/p2h-again.err"
AGAIN_RC=$?
# This leg is the one where an empty output IS the pass condition, so a leg
# that never ran would be the strongest possible "proof". Its status is checked
# first, inside the verdict, for that reason.
ROOTDIR="$ROOT" TID="$T2" CLAIM="$HOOK_CLAIM" AGAIN="$SCRATCH/p2h-again.json" \
  AGAINRC="$AGAIN_RC" AGAINERR="$SCRATCH/p2h-again.err" "$PY" - \
  > "$SCRATCH/p2h-again-assert.out" 2> "$SCRATCH/p2h-again-assert.err" <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.events.emitter import replay
tid, claim = os.environ["TID"], os.environ["CLAIM"]
problems = []
rc = os.environ.get("AGAINRC", "")
if rc != "0":
    tail = ""
    err = Path(os.environ.get("AGAINERR") or "/nonexistent")
    if err.is_file():
        tail = err.read_text(encoding="utf-8", errors="replace").strip()[-200:]
    problems.append("the holder's own tick exited %r rather than 0; printing nothing is what "
                    "this leg PASSES on, so a tick that crashed would be read as the proof "
                    "that it did not re-inject: %s" % (rc, tail))
again = Path(os.environ["AGAIN"]).read_text(encoding="utf-8").strip()
if again:
    problems.append("the holder's own tick re-injected its live claim; it would do that "
                    "every tick for the life of the session")
starts = [e for e in replay(event_types=["work_item_started"])
          if (e.get("payload") or {}).get("task_id") == tid]
if len(starts) != 1:
    problems.append("%d started events for %s after the holder's own tick, expected 1"
                    % (len(starts), tid))
renewed = [e for e in replay(event_types=["work_item_claim_renewed"])
           if (e.get("payload") or {}).get("claim_id") == claim]
if not renewed:
    problems.append("the holder's own tick did not renew its claim; a lease that is not "
                    "renewed on the tick loses every item that outlives it")
print(json.dumps({"code": 0 if not problems else 20, "problems": problems}, sort_keys=True))
print(os.environ["DRILL_VERDICT_SENTINEL"])
PY
read_verdict P2h 20 $? "$SCRATCH/p2h-again-assert.out" "$SCRATCH/p2h-again-assert.err"

# Close the item the hook claimed, with the holder and token read back out of
# the ledger — the drill never invents a claim it did not observe.
"$PY" "$LIB_DIR/worker.py" --root "$ROOT" --slug "$SLUG" --holder "$HOOK_HOLDER" \
  --mode complete --task-id "$T2" --outcome-id "$OID" --claim-id "$HOOK_CLAIM" \
  > "$SCRATCH/p2h-complete.json" 2>"$SCRATCH/p2h-complete.err" \
  || fail 20 P2h "the hook's holder could not close $T2: $(tr '\n' ' ' < "$SCRATCH/p2h-complete.json" | cut -c1-300)"
pass_stage P2h "the locked hook claimed $T2 once across two sessions, renewed its own, and closed it"

# ---------------------------------------------------------------------------
# P5 — no re-briefing. The Captain ratified once. Nothing since then has asked
# him anything, rewritten a proposal, or ratified again.
# ---------------------------------------------------------------------------
ROOTDIR="$ROOT" OID="$OID" BEFORE="$SCRATCH/p1-digests.json" "$PY" - \
  > "$SCRATCH/p5-assert.out" 2> "$SCRATCH/p5-assert.err" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.events.emitter import replay
problems = []
before = json.load(open(os.environ["BEFORE"]))
for rel, digest in before.items():
    p = root / rel
    now = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""
    if now != digest:
        problems.append("%s changed after the tap — carrying the work re-wrote the "
                        "Captain's declaration" % rel)
evs = [e for e in replay(event_types=["captain_outcome_ratified"])
       if (e.get("payload") or {}).get("outcome_id") == os.environ["OID"]]
if len(evs) != 1:
    problems.append("%d ratifications for the one responsibility, expected 1" % len(evs))
print(json.dumps({"code": 0 if not problems else 40, "problems": problems}, sort_keys=True))
print(os.environ["DRILL_VERDICT_SENTINEL"])
PY
read_verdict P5 40 $? "$SCRATCH/p5-assert.out" "$SCRATCH/p5-assert.err"
pass_stage P5 "one ratification, no proposal file rewritten, no second ask"

# ---------------------------------------------------------------------------
# P6 — receipts. What the Captain can see afterwards, and whether the graph
# agrees with it.
# ---------------------------------------------------------------------------
( cd "$ROOT" && "$PY" -m framework.missions.receipts --root "$ROOT" --json ) \
  > "$SCRATCH/p6-receipts.json" 2>"$SCRATCH/p6-receipts.err"
RECEIPTS_RC=$?
[ "$RECEIPTS_RC" -eq 0 ] || fail 40 P6 "receipts --json exited $RECEIPTS_RC: $(tr '\n' ' ' < "$SCRATCH/p6-receipts.err" | cut -c1-400)"

ROOTDIR="$ROOT" OID="$OID" T1="$T1" T2="$T2" RECEIPTS="$SCRATCH/p6-receipts.json" "$PY" - \
  > "$SCRATCH/p6-assert.out" 2> "$SCRATCH/p6-assert.err" <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
problems = []
rows = json.load(open(os.environ["RECEIPTS"]))
if isinstance(rows, dict):
    rows = rows.get("receipts") or rows.get("rows") or []
kinds = {}
for r in rows:
    kinds.setdefault(r.get("kind"), []).append(r)
if len(kinds.get("ratified", [])) != 1:
    problems.append("%d ratified receipts, expected 1" % len(kinds.get("ratified", [])))
completed = kinds.get("completed", [])
if len(completed) != 2:
    problems.append("%d completed receipts, expected 2" % len(completed))
for r in completed:
    ep = r.get("evidence_path")
    if not ep or not Path(ep).is_file():
        problems.append("a completed receipt points at no readable evidence: %r" % ep)
for tid in (os.environ["T1"], os.environ["T2"]):
    n = len([r for r in completed if r.get("task_id") == tid])
    if n != 1:
        problems.append("%d completions for %s in the receipts, expected 1" % (n, tid))
if not kinds.get("released"):
    problems.append("no released receipt — the expired lease is not visible to the Captain")
from framework.missions.compiler import compile_from_yaml
missions = compile_from_yaml(root / "instance/config/outcomes.yml", actor="drill",
                             roles=None, emit_event=False)
mine = [m for m in missions if m["outcome_id"] == os.environ["OID"]]
if not mine:
    problems.append("a fresh compile no longer knows the ratified responsibility")
else:
    for node in mine[0]["work_graph"].nodes.values():
        if node.status.value != "done":
            problems.append("a fresh compile reports %s as %s, not done" % (node.id, node.status.value))
print(json.dumps({"code": 0 if not problems else 40, "problems": problems}, sort_keys=True))
print(os.environ["DRILL_VERDICT_SENTINEL"])
PY
read_verdict P6 40 $? "$SCRATCH/p6-assert.out" "$SCRATCH/p6-assert.err"
pass_stage P6 "1 ratified, 2 completed with readable evidence, the released row, both nodes done"

# ---------------------------------------------------------------------------
# P7 — the result reaches an installed Cabinet. Without this the drill proves
# a Cabinet that improves itself in a repository nobody is running.
#
# Three legs share one install and one ledger: a gate-red apply that must roll
# back, a gate-green apply that must land, and a locked-path bundle that must
# be refused whole. Each leg's proof is a DELTA taken around that leg — the
# events and the snapshot directory are cumulative, and leg (b) asserting "the
# ledger holds an applied event" would be satisfied by leg (a).
# ---------------------------------------------------------------------------
if [ "$SKIP_UPDATE" = "1" ]; then
  thin_stage P7 "skipped by --skip-update: the update leg was not run and nothing about it is proved"
else
  UPDATER="$ROOT/cabinet/scripts/cabinet-update.sh"
  [ -f "$UPDATER" ] || fail 50 P7 "no update path at cabinet/scripts/cabinet-update.sh — the result cannot reach an installed Cabinet"

  # A4.7 wants the FULL apply — stage build, restart, health gate. A scratch
  # install carries no node toolchain and no installed dependencies, so the
  # build step is skippable and the run that skips it says so (THIN) instead of
  # quietly reporting a leg it never walked. --with-rebuild is the full variant;
  # it is what an operator runs on a box that has the toolchain, and it is the
  # only way the staged-build-and-swap (A5.6) is exercised end to end.
  REBUILD_ARG="--skip-rebuild"
  [ "$WITH_REBUILD" = "1" ] && REBUILD_ARG=""

  INSTALL="$SCRATCH/install"
  MUT="$SCRATCH/mutated"
  LOCKMUT="$SCRATCH/mutated-locked"
  BASECUT="$SCRATCH/basecut"
  # $INSTALL is deliberately NOT created here: the exporter makes it, and it
  # refuses a --out that already has anything in it.
  mkdir -p "$BASECUT" "$MUT" "$LOCKMUT"
  tar -cf - -C "$SHIPPED" --exclude='./.git' . | tar -xf - -C "$BASECUT" \
    || fail 50 P7 "could not stage the base cut"
  tar -cf - -C "$SHIPPED" --exclude='./.git' . | tar -xf - -C "$MUT" \
    || fail 50 P7 "could not stage the shipped tree"
  tar -cf - -C "$SHIPPED" --exclude='./.git' . | tar -xf - -C "$LOCKMUT" \
    || fail 50 P7 "could not stage the locked-path tree"
  MUTATED_REL="framework/missions/session_bridge.py"
  printf '\n# the one changed line this bundle ships\n' >> "$MUT/$MUTATED_REL"
  printf '\n# a change under the locked hooks directory\n' >> "$LOCKMUT/cabinet/scripts/hooks/session-task-inject.sh"

  # A BUNDLE IS A CUT OF A CHECKOUT. `publish` runs the exporter, and the
  # exporter cuts `git archive HEAD` (egg-export.sh:154-156); publish refuses a
  # source with no .git before it ever gets there (cabinet-update.sh:343).
  # This drill handed it a tar copy and P7 red with "--from is not a checkout"
  # — the drill was wrong, not the update path: the contract's P7 is "two
  # egg-export.sh --bundle cuts of HEAD (second with one framework file
  # altered)", and a cut of HEAD needs a HEAD. Each mutated tree therefore
  # becomes a throwaway one-commit repository, which is also what gives the two
  # bundles two DISTINCT source shas — the ids the apply legs address them by.
  command -v git >/dev/null 2>&1 \
    || fail 50 P7 "this host has no git, and a bundle is a cut of a checkout — the update leg cannot be run here (use --skip-update, which says so rather than passing)"
  # `add -A -f`, not `add -A`: the tree carries paths the REAL repository both
  # tracks and gitignores (shared/interfaces/*.md), and a throwaway repo that
  # honoured the ignore file would commit a HEAD with those files missing —
  # the exporter then reds with "expected in export but missing", measured.
  # This repository exists for exactly one job: give the exporter a HEAD that
  # is the tree it was handed.
  commit_tree() {  # commit_tree <dir> <subject>
    git -C "$1" init -q >> "$SCRATCH/p7-git.log" 2>&1 \
      && git -C "$1" add -A -f >> "$SCRATCH/p7-git.log" 2>&1 \
      && git -C "$1" -c user.email=drill@localhost -c user.name=drill \
             -c commit.gpgsign=false commit -q -m "$2" >> "$SCRATCH/p7-git.log" 2>&1
  }
  commit_tree "$BASECUT" "the tree the install was cut from" \
    || fail 50 P7 "could not make the base tree a checkout: $(tr '\n' ' ' < "$SCRATCH/p7-git.log" | tail -c 400)"
  commit_tree "$MUT" "the bundle under test" \
    || fail 50 P7 "could not make the shipped tree a checkout: $(tr '\n' ' ' < "$SCRATCH/p7-git.log" | tail -c 400)"
  commit_tree "$LOCKMUT" "the locked-path bundle under test" \
    || fail 50 P7 "could not make the locked-path tree a checkout: $(tr '\n' ' ' < "$SCRATCH/p7-git.log" | tail -c 400)"

  # THE INSTALL IS AN EXPORT, not a copy of the repository. An installed
  # Cabinet is an egg: the manifest pass has run over it, so its launchd plists
  # are the portable ones, its shipped-empty interface files are empty, its
  # instance tree is gone and it carries an egg-manifest.json identity. A raw
  # `git archive` tree looks nothing like that at exactly the paths the update
  # path guards — measured: the very first apply against a copied repo was
  # REFUSED (exit 3) because the bundle differed from the "install" at three
  # locked paths — one launchd plist under cabinet/launchd/ and two
  # instance/config policy files — every one of them a difference the EXPORT
  # makes and nothing to do with the change under test. (Their names are NOT
  # written here: the plist label is a guarded literal, and a script under
  # cabinet/scripts that merely NAMES it is read as a script that LOADS it by
  # framework/authority/tests/test_golden_evals_sovereign.py — measured, two
  # golden evals went red on this comment.) Cutting the install the same way
  # its bundles are cut is what leaves the mutated file as the only difference
  # between them.
  ( cd "$SCRATCH" && bash "$BASECUT/cabinet/scripts/egg-export.sh" --out "$INSTALL" ) \
    > "$SCRATCH/p7-install-export.out" 2>&1 \
    || fail 50 P7 "could not export the scratch install: $(tr '\n' ' ' < "$SCRATCH/p7-install-export.out" | tail -c 400)"
  [ -f "$INSTALL/egg-manifest.json" ] \
    || fail 50 P7 "the exported install carries no egg-manifest.json, so it has no identity for the update path to compare a bundle against"
  [ -f "$INSTALL/cabinet/scripts/cabinet-update.sh" ] \
    || fail 50 P7 "the exported install ships no updater, so the result could not reach it"

  # A preserved path with something in it: an update that quietly emptied this
  # would be the worst possible pass. The canary is a member of the same
  # shipped-empty preserve class as the Captain's standing switches, chosen
  # deliberately NOT to be one of them — no drill puts a live safety switch in
  # its write set, even a copy of one in a throwaway tree.
  PRESERVED_REL="shared/interfaces/captain-rules-index.yaml"
  mkdir -p "$INSTALL/shared/interfaces"
  printf 'drill: one non-empty preserved row\n' > "$INSTALL/$PRESERVED_REL"
  sha256_of P7 50 "$INSTALL/$PRESERVED_REL"
  PRESERVED_BEFORE="$SHA_OUT"

  # The stub that answers the health contract. Its stamp is baked at start, so
  # the gate can be made red by simply not restarting it. The identity marker
  # is READ from the one line that declares it, never copied here: a probe with
  # its own copy of the marker keeps passing after the real one changes.
  SERVICE="$(sed -n 's/^CABINET_DASH_SERVICE="\(.*\)"$/\1/p' "$ROOT/cabinet/scripts/lib/dashboard.sh" | head -1)"
  [ -n "$SERVICE" ] || fail 50 P7 "cabinet/scripts/lib/dashboard.sh no longer declares CABINET_DASH_SERVICE on one line — the drill will not guess the identity marker the health gate matches on"
  PORT="${DASH_PORT_PIN:-$("$PY" -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1]);s.close()")}"
  STUB_STATE="$SCRATCH/stub-dash.json"
  STAMP_FILE="$SCRATCH/stub-stamp.txt"
  printf 'installed\n' > "$STAMP_FILE"
  "$PY" "$LIB_DIR/stub_dashboard.py" restart --port "$PORT" --stamp-file "$STAMP_FILE" \
    --state-file "$STUB_STATE" --service "$SERVICE" \
    || fail 50 P7 "the stub health server would not start on $PORT"
  export CABINET_DASHBOARD_PORT="$PORT"
  export CABINET_UPDATE_TEST_RESTART_CMD="$PY $LIB_DIR/stub_dashboard.py restart --port $PORT --stamp-file $STAMP_FILE --state-file $STUB_STATE --service $SERVICE"

  ( cd "$ROOT" && bash "$UPDATER" publish --from "$MUT" --to "$INSTALL" ) \
    > "$SCRATCH/p7-publish.out" 2>&1
  PUB_RC=$?
  [ "$PUB_RC" -eq 0 ] || fail 50 P7 "publish into the install's inbox exited $PUB_RC: $(tr '\n' ' ' < "$SCRATCH/p7-publish.out" | cut -c1-400)"

  BUNDLE_SHA="$(CABINET_ROOT="$INSTALL" bash "$UPDATER" status --json 2>/dev/null | "$PY" -c '
import json, sys
# `status --json` names the bundle id `sha` on each inbox row and puts the
# newest one under `latest` (cabinet-update.sh:426, :458). This drill read
# `latest.source_sha` — the manifest key, not the status key — and got an
# empty id from a publish that had worked perfectly.
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit(0)
print((d.get("latest") or {}).get("sha") or "")
')"
  [ -n "$BUNDLE_SHA" ] || fail 50 P7 "the inbox reports no latest bundle after publish"
  printf '%s\n' "$BUNDLE_SHA" > "$STAMP_FILE"

  # THE SEAM MUST BE REAL BEFORE THE LEG THAT DRIVES IT RUNS (A5.14). Leg (a)
  # makes the health gate go red by handing the apply a restart command that
  # does nothing. Measured 2026-09-07 against origin/feat/p1-update-path: that
  # updater restarts through cabinet_dash_restart() in
  # cabinet/scripts/lib/dashboard.sh and reads NO restart-command variable, and
  # A5.14 renames the update path's two health-gate command seams to
  # CABINET_UPDATE_TEST_*. A drill driving a seam nothing reads would let the
  # dashboard restart normally, watch the gate go GREEN, and report the whole
  # rollback arm against a server that was never stale. Refuse instead: a
  # sensor pointed at a seam that does not exist is the disabled sensor this
  # unit exists to be the opposite of. Whoever lands the updater reconciles the
  # name here in the same commit.
  grep -q 'CABINET_UPDATE_TEST_RESTART_CMD' "$INSTALL/cabinet/scripts/cabinet-update.sh" \
    || fail 50 P7 "nothing in the installed update path reads CABINET_UPDATE_TEST_RESTART_CMD, so the gate-red leg would drive nothing and the rollback arm would be measuring a dashboard that restarted perfectly well — reconcile the name (cabinet/scripts/tests/test_drill_wiring.py::test_the_drill_and_the_updater_name_the_same_restart_seam is the same claim, mechanically, and reds first)"

  # (a) the gate goes RED because the restart did not happen: the old process
  # answers, with the old stamp and the old start time. The apply must roll the
  # tree back rather than leave a half-updated install behind a green light.
  #
  # Counted AROUND the leg, never across the run: legs (a), (b) and (c) all
  # write to one ledger, so "the ledger holds a rolled-back event" is satisfied
  # by any leg that ever emitted one. What this leg claims is that IT rolled
  # back, and only a delta says that.
  event_count P7 50 cabinet_update_rolled_back
  ROLLED_BEFORE="$EV_COUNT"
  ( cd "$INSTALL" && CABINET_ROOT="$INSTALL" CABINET_UPDATE_TEST_RESTART_CMD="/usr/bin/true" \
      bash "$UPDATER" apply --bundle "$BUNDLE_SHA" --from terminal $REBUILD_ARG ) \
    > "$SCRATCH/p7-gate-red.out" 2>&1
  RED_RC=$?
  event_count P7 50 cabinet_update_rolled_back
  ROLLED_AFTER="$EV_COUNT"
  ROLLED_DELTA=$((ROLLED_AFTER - ROLLED_BEFORE))
  # EXACTLY 1, not merely non-zero. 1 is the exit of an apply that rolled
  # itself back (cabinet-update.sh roll_back_after); 2 is a usage error and 3 a
  # refusal, and both of those are ALSO "not zero". Measured here: the drill
  # spelled this verb `--door terminal` when the updater takes
  # `--from terminal|web|chat`, the apply never ran at all, and the only thing
  # that noticed was the event delta below — a leg that scored a mistyped
  # command as a red health gate. "Not measured" and "measured red" are
  # different facts, and an exit code is the cheapest place to keep them apart.
  if [ "$RED_RC" -ne 1 ]; then
    fail 50 P7 "an apply whose dashboard never restarted exited $RED_RC; 1 is the exit of an apply that rolled itself back, 0 would mean an identity-only probe passed an old process that survived a failed restart, and anything else means the apply never reached its health gate: $(tr '\n' ' ' < "$SCRATCH/p7-gate-red.out" | cut -c1-400)"
  fi
  [ "$ROLLED_DELTA" -eq 1 ] || fail 50 P7 "the failed health gate emitted $ROLLED_DELTA cabinet_update_rolled_back event(s) of its own (the ledger holds $ROLLED_AFTER in all); exactly one is what a rollback that happened looks like"
  if grep -q 'the one changed line this bundle ships' "$INSTALL/$MUTATED_REL" 2>/dev/null; then
    fail 50 P7 "the rolled-back install still carries the bundle's change"
  fi

  # (b) the same apply with a real restart: the gate goes green. Its event and
  # its snapshot are counted around it for the same reason — leg (a) applied
  # and rolled back a moment ago, and both of its rows are still there.
  event_count P7 50 cabinet_update_applied
  APPLIED_BEFORE="$EV_COUNT"
  dir_count P7 50 "$INSTALL/.updates/snapshots"
  SNAPS_BEFORE="$DIR_COUNT"
  ( cd "$INSTALL" && CABINET_ROOT="$INSTALL" bash "$UPDATER" apply --bundle "$BUNDLE_SHA" --from terminal $REBUILD_ARG ) \
    > "$SCRATCH/p7-apply.out" 2>&1
  APPLY_RC=$?
  [ "$APPLY_RC" -eq 0 ] || fail 50 P7 "apply exited $APPLY_RC: $(tr '\n' ' ' < "$SCRATCH/p7-apply.out" | cut -c1-400)"
  grep -q 'the one changed line this bundle ships' "$INSTALL/$MUTATED_REL" \
    || fail 50 P7 "apply reported success but the shipped change is not in the install"
  sha256_of P7 50 "$INSTALL/$PRESERVED_REL"
  PRESERVED_AFTER="$SHA_OUT"
  [ "$PRESERVED_BEFORE" = "$PRESERVED_AFTER" ] || fail 50 P7 "apply overwrote a preserved path"
  dir_count P7 50 "$INSTALL/.updates/snapshots"
  SNAPS_AFTER="$DIR_COUNT"
  SNAPS_DELTA=$((SNAPS_AFTER - SNAPS_BEFORE))
  [ "$SNAPS_DELTA" -eq 1 ] || fail 50 P7 "this apply kept $SNAPS_DELTA snapshot(s) of its own ($SNAPS_AFTER under .updates/snapshots in all); the contract is one snapshot per apply, and a directory that was already full is not a snapshot this apply took"
  event_count P7 50 cabinet_update_applied
  APPLIED_AFTER="$EV_COUNT"
  APPLIED_DELTA=$((APPLIED_AFTER - APPLIED_BEFORE))
  [ "$APPLIED_DELTA" -eq 1 ] || fail 50 P7 "this apply emitted $APPLIED_DELTA cabinet_update_applied event(s) of its own (the ledger holds $APPLIED_AFTER in all); exactly one is what an update that reached the install looks like"

  # (c) a bundle that touches the locked set is refused whole, before any write.
  sha256_of P7 50 "$INSTALL/cabinet/scripts/hooks/session-task-inject.sh"
  HOOK_BEFORE="$SHA_OUT"
  ( cd "$ROOT" && bash "$UPDATER" publish --from "$LOCKMUT" --to "$INSTALL" ) > "$SCRATCH/p7-publish-locked.out" 2>&1
  LOCK_PUB_RC=$?
  [ "$LOCK_PUB_RC" -eq 0 ] || fail 50 P7 "publishing the locked-path bundle exited $LOCK_PUB_RC, so the refusal leg would be run against no bundle at all: $(tr '\n' ' ' < "$SCRATCH/p7-publish-locked.out" | cut -c1-400)"
  LOCK_SHA="$(CABINET_ROOT="$INSTALL" bash "$UPDATER" status --json 2>/dev/null | "$PY" -c '
import json, sys
# `status --json` names the bundle id `sha` on each inbox row and puts the
# newest one under `latest` (cabinet-update.sh:426, :458). This drill read
# `latest.source_sha` — the manifest key, not the status key — and got an
# empty id from a publish that had worked perfectly.
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit(0)
print((d.get("latest") or {}).get("sha") or "")
')"
  [ -n "$LOCK_SHA" ] || fail 50 P7 "the inbox reports no bundle after the locked-path publish; an apply with an empty bundle id would be refused for the wrong reason and the drill would call it a locked-path refusal"
  event_count P7 50 cabinet_update_refused
  REFUSED_BEFORE="$EV_COUNT"
  ( cd "$INSTALL" && CABINET_ROOT="$INSTALL" bash "$UPDATER" apply --bundle "$LOCK_SHA" --from terminal $REBUILD_ARG ) \
    > "$SCRATCH/p7-locked.out" 2>&1
  LOCK_RC=$?
  [ "$LOCK_RC" -eq 3 ] || fail 50 P7 "a bundle changing a locked path exited $LOCK_RC, expected 3"
  sha256_of P7 50 "$INSTALL/cabinet/scripts/hooks/session-task-inject.sh"
  HOOK_AFTER="$SHA_OUT"
  [ "$HOOK_BEFORE" = "$HOOK_AFTER" ] || fail 50 P7 "a refused bundle still changed a locked path"
  event_count P7 50 cabinet_update_refused
  REFUSED_AFTER="$EV_COUNT"
  REFUSED_DELTA=$((REFUSED_AFTER - REFUSED_BEFORE))
  [ "$REFUSED_DELTA" -eq 1 ] || fail 50 P7 "the refused bundle emitted $REFUSED_DELTA cabinet_update_refused event(s) of its own (the ledger holds $REFUSED_AFTER in all); a refusal nobody recorded is a refusal nobody can audit"

  # A5.15 — the STATE FILE too, not only the ledger. The delta above is the
  # receipt an auditor reads; `state.json` is what the card and the briefing
  # line read, and that is the surface the refusal was invisible on when this
  # was measured (2026-09-08: refused exactly as designed, and left
  # `phase: idle, last: null`, so the card went on offering the same bundle).
  # A drill watching only the ledger cannot see that half regress — and the
  # paths are the load-bearing part, because "refused" alone is not a sentence
  # anyone can act on.
  # A5.17 — and the DURABLE store, which is the half `state.json` cannot be.
  # Every write to that document is a whole-document replace, and during an
  # update one of the writers can be an older updater copy that never knew the
  # field; the marker under `.updates/refusals/<sha>.json` is what survives it.
  # A drill that watched only the mirror would pass on an install whose next
  # state write silently forgot the verdict.
  REFUSAL_STATE="$("$PY" - "$INSTALL/.updates/state.json" "$LOCK_SHA" "$INSTALL/.updates/refusals" <<'PYREFUSAL'
import json, sys
from pathlib import Path
try:
    doc = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception as exc:
    print("state.json is unreadable: %s" % exc)
    raise SystemExit(0)
record = doc.get("last_refusal") or {}
marker_path = Path(sys.argv[3]) / (sys.argv[2] + ".json")
try:
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
except Exception as exc:
    marker = {"unreadable": str(exc)}
if doc.get("phase") != "refused":
    print("phase is %r, expected refused" % (doc.get("phase"),))
elif record.get("bundle") != sys.argv[2]:
    print("last_refusal names bundle %r, expected %s"
          % (record.get("bundle"), sys.argv[2]))
elif not record.get("paths"):
    print("last_refusal names no paths, so no surface can say which files")
elif marker.get("bundle") != sys.argv[2]:
    print("no durable marker at %s (got %r): the verdict lives only in a "
          "document the next write replaces" % (marker_path, marker))
elif not marker.get("paths") or not marker.get("ts"):
    print("the marker names no paths or no time of its own: %r" % (marker,))
else:
    print("ok")
PYREFUSAL
)"
  [ "$REFUSAL_STATE" = "ok" ] || fail 50 P7 "the refused bundle left no durable refusal any surface can read: $REFUSAL_STATE"

  "$PY" "$LIB_DIR/stub_dashboard.py" stop --state-file "$STUB_STATE" >/dev/null 2>&1 || true
  STUB_STATE=""
  if [ "$WITH_REBUILD" = "1" ]; then
    pass_stage P7 "the build step ran (--with-rebuild): the staged build was swapped in and the health gate read the stamp it baked"
  else
    thin_stage P7 "rebuild step skipped (--skip-rebuild): a scratch install carries no node toolchain, so the built stamp came from the stub server rather than from npm run build"
  fi
  pass_stage P7 "gate red rolled back, gate green applied, preserved path intact, locked bundle refused whole"
fi

# ---------------------------------------------------------------------------
# Hermeticity, after the fact. A drill that wrote outside its root proved
# nothing about a fresh hatch.
# ---------------------------------------------------------------------------
find "$HOME_DIR" 2>/dev/null | LC_ALL=C sort > "$SCRATCH/home.after"
( cd "$REPO_ROOT" && find . -not -path './.git/*' 2>/dev/null | LC_ALL=C sort ) > "$SCRATCH/repo.after"
[ -s "$SCRATCH/home.before" ] && [ -s "$SCRATCH/repo.before" ] \
  || fail 64 hermeticity "the before picture of HOME or of the repo was never taken, so 'nothing was written outside the root' cannot be claimed"
HOME_DIFF="$(diff "$SCRATCH/home.before" "$SCRATCH/home.after" | grep -c '^[<>]' | tr -d ' ')"
REPO_DIFF="$(diff "$SCRATCH/repo.before" "$SCRATCH/repo.after" | grep -c '^[<>]' | tr -d ' ')"
if [ "$HOME_DIFF" != "0" ] || [ "$REPO_DIFF" != "0" ]; then
  diff "$SCRATCH/home.before" "$SCRATCH/home.after" > "$SCRATCH/home.diff" 2>&1
  diff "$SCRATCH/repo.before" "$SCRATCH/repo.after" > "$SCRATCH/repo.diff" 2>&1
  fail 64 hermeticity "the drill wrote outside its root: $HOME_DIFF path(s) under HOME, $REPO_DIFF under the repo (see $SCRATCH/*.diff — re-run with --keep-scratch)"
fi
pass_stage hermeticity "nothing was written outside $ROOT"

DRILL_EXIT=0
say "PASS — one responsibility carried end to end"
exit 0
