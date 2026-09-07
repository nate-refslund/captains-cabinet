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
#   21      THE MEASUREMENT WAS IMPOSSIBLE: a module the pull path needs could
#           not be imported where it must be measured. Distinct from 20 on
#           purpose — an ImportError is not the red the claim invariant names,
#           and a drill that reported one as the other would be lying about
#           what it proved.
#   30  P3/P4  kill and resume: the item did not come back, or came back wrong
#   40  P5/P6  no re-briefing / receipts
#   50  P7  the update path
#   64      usage, or this host cannot host the drill at all
#
# HERMETIC BY CONSTRUCTION. Everything runs against a scratch hatch under a
# throwaway root; HOME, CABINET_ROOT, CABINET_EVENT_LOG_DIR and CABINET_ID are
# pinned and every other CABINET_* plus PYTHONPATH, DATABASE_URL,
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
#   CABINET_DASH_RESTART_CMD
#       the command the update path must run to restart the dashboard. The
#       drill points it at its own stub server so the health gate can be made
#       to go red on purpose (see P7).
#   CABINET_DRILL_DASH_PORT
#       pin the stub server's port instead of picking a free one.
#
# Usage:
#   bash cabinet/scripts/drills/one-responsibility.sh [--root DIR] [--tree DIR]
#        [--skip-update] [--keep-scratch] [--json]
#
# Foreground only. Every wait is a bounded inline poll; no watcher, no daemon,
# no background job survives the run (macOS has no timeout(1), so waits are
# python sleeps and the trap kills every pid the drill started).

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LIB_DIR="$SCRIPT_DIR/lib"

PY="${CABINET_PYTHON:-python3.12}"
BOX_PY="python3"          # what the locked hook pins (session-task-inject.sh:28)

# Read every CABINET_* input the drill takes BEFORE the environment is scrubbed
# — the scrub is what makes the run hermetic, and it would eat these too.
DASH_PORT_PIN="${CABINET_DRILL_DASH_PORT:-}"
# The kill/resume cadence: tick 1s inside a short lease, so a lease that only
# renews when nearly spent shows up as a defect rather than as a slow test. The
# contract's number is 3; a loaded host may need a longer window to observe the
# same thing, and observing it late is better than observing it never.
LEASE_S="${CABINET_DRILL_LEASE_SECONDS:-3}"

ROOT_ARG=""
TREE_ARG="${CABINET_DRILL_TREE:-}"
SKIP_UPDATE=0
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
  local pid
  for pid in $WORKER_PIDS; do
    kill -KILL "$pid" 2>/dev/null || true
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

ROOTDIR="$ROOT" OID="$OID" "$PY" - <<'PY' > "$SCRATCH/p1-assert.out" 2>&1
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
print(json.dumps({"problems": problems, "digests": digests}, sort_keys=True))
PY
P1_RC=$?
[ "$P1_RC" -eq 0 ] || fail 10 P1 "the tap's assertions could not run: $(tr '\n' ' ' < "$SCRATCH/p1-assert.out" | cut -c1-400)"
P1_PROBLEMS="$("$PY" -c 'import json,sys; print("; ".join(json.load(open(sys.argv[1]))["problems"]))' "$SCRATCH/p1-assert.out")"
[ -z "$P1_PROBLEMS" ] || fail 10 P1 "$P1_PROBLEMS"
"$PY" -c 'import json,sys; json.dump(json.load(open(sys.argv[1]))["digests"], open(sys.argv[2],"w"))' \
  "$SCRATCH/p1-assert.out" "$SCRATCH/p1-digests.json"
pass_stage P1 "$OID ratified through the terminal door by $PRINCIPAL, one event, actor operator"

# ---------------------------------------------------------------------------
# P2 — the claim. Eight holders pull at once through the REAL pull path. One
# item, one holder, one started event. The losers are proved by the ledger,
# never by hook silence: silence has too many causes to be evidence.
# ---------------------------------------------------------------------------
mkdir -p "$SCRATCH/p2"
i=1
while [ "$i" -le 8 ]; do
  "$PY" "$LIB_DIR/worker.py" --root "$ROOT" --slug "$SLUG" \
    --holder "$SLUG@w$i" --mode pull > "$SCRATCH/p2/w$i.json" 2>"$SCRATCH/p2/w$i.err" &
  WORKER_PIDS="$WORKER_PIDS $!"
  i=$((i + 1))
done
wait
WORKER_PIDS=""

P2_VERDICT="$(ROOTDIR="$ROOT" P2DIR="$SCRATCH/p2" OID="$OID" TID="$T1" "$PY" - <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.events.emitter import replay
p2 = Path(os.environ["P2DIR"]); oid, tid = os.environ["OID"], os.environ["TID"]
results, unimportable = [], 0
for n in range(1, 9):
    raw = (p2 / ("w%d.json" % n)).read_text(encoding="utf-8").strip() if (p2 / ("w%d.json" % n)).is_file() else ""
    try:
        results.append(json.loads(raw))
    except Exception:
        results.append({"ok": False, "error": "no result from w%d: %r" % (n, raw[:120])})
for r in results:
    if r.get("module_error"):
        unimportable += 1
winners = [r for r in results if (r.get("task") or {}).get("task_id")]
started = [e for e in replay(event_types=["work_item_started"])
           if (e.get("payload") or {}).get("task_id") == tid]
problems = []
if unimportable == len(results):
    print(json.dumps({"code": 21, "problems": [
        "the pull path could not be imported by any of the 8 holders: %s"
        % (results[0].get("error") or "")]}, sort_keys=True))
    raise SystemExit(0)
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
PY
)"
P2_CODE="$(printf '%s' "$P2_VERDICT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["code"])')"
if [ "$P2_CODE" != "0" ]; then
  fail "$P2_CODE" P2 "$(printf '%s' "$P2_VERDICT" | "$PY" -c 'import json,sys; print("; ".join(json.load(sys.stdin)["problems"]))')"
fi
WINNER="$(printf '%s' "$P2_VERDICT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["winner"])')"
pass_stage P2 "8 holders, 1 claim on $T1, holder $WINNER"

# ---------------------------------------------------------------------------
# P2b — the assignment fallback. A real card carries string criteria and
# matches no capability keyword, so without a fallback the Captain's own tap
# yields a gap instead of work. One role on the roster: it is that role's.
# Two: it is a gap, named, not silence.
# ---------------------------------------------------------------------------
P2B_VERDICT="$(ROOTDIR="$ROOT" DRILL_SLUG="$SLUG" "$PY" - <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
slug = os.environ["DRILL_SLUG"]
problems = []
try:
    from framework.missions.compiler import compile_outcome
    from framework.missions.gaps import observe_holder_gaps
except ImportError as exc:
    print(json.dumps({"code": 21, "problems": ["P2b needs a module that is absent: %s" % exc]}))
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
if res.get("opened") != 1:
    problems.append("observe_holder_gaps opened %r holder gaps on a two-role roster, expected 1"
                    % res.get("opened"))
from framework.learning.capability_gaps import project_gaps
no_match = [g for g in project_gaps() if "no_match" in json.dumps(g, default=str)]
if len(no_match) != 1:
    problems.append("%d no_match gaps recorded, expected exactly 1" % len(no_match))
print(json.dumps({"code": 0 if not problems else 20, "problems": problems}, sort_keys=True))
PY
)"
P2B_CODE="$(printf '%s' "$P2B_VERDICT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["code"])')"
if [ "$P2B_CODE" != "0" ]; then
  fail "$P2B_CODE" P2b "$(printf '%s' "$P2B_VERDICT" | "$PY" -c 'import json,sys; print("; ".join(json.load(sys.stdin)["problems"]))')"
fi
pass_stage P2b "unowned node assigned on a one-role roster; exactly one no_match gap on two"

# ---------------------------------------------------------------------------
# P3 — killed inside the work. The kill lands between the claim and the
# completion while a renewal tick is due, at a scaled cadence (tick 1s, lease
# 3s) so a lease that only renews when nearly spent is visible as a defect
# rather than as a slow test.
# ---------------------------------------------------------------------------
rm -f "$STATE/proceed" "$STATE/claimed.$SLUG@w1" "$STATE/renewed.$SLUG@w1"
"$PY" "$LIB_DIR/worker.py" --root "$ROOT" --slug "$SLUG" --holder "$SLUG@w1" \
  --lease "$LEASE_S" --renew-every 1 --mode work --pause-before-complete \
  --state-dir "$STATE" --pause-timeout 40 > "$SCRATCH/p3-w1.json" 2>"$SCRATCH/p3-w1.err" &
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

W1_CLAIM="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("claim_id") or "")' "$STATE/claimed.$SLUG@w1")"
P3_PROBLEMS="$(ROOTDIR="$ROOT" TID="$T1" HOLDER="$SLUG@w1" SLUGV="$SLUG" "$PY" - <<'PY'
import os, sys
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
print("; ".join(problems))
PY
)"
[ -z "$P3_PROBLEMS" ] || fail 30 P3 "$P3_PROBLEMS"
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
RESUME_ARGV="--root $ROOT --slug $SLUG --holder $SLUG@w2 --lease 60 --mode work --state-dir $STATE"
"$PY" "$LIB_DIR/worker.py" $RESUME_ARGV > "$SCRATCH/p4-w2.json" 2>"$SCRATCH/p4-w2.err"
P4_RC=$?
if [ "$P4_RC" -ne 0 ]; then
  fail 30 P4 "the resuming holder w2 exited $P4_RC: $(tr '\n' ' ' < "$SCRATCH/p4-w2.json" | cut -c1-300)$(tr '\n' ' ' < "$SCRATCH/p4-w2.err" | cut -c1-200)"
fi

P4_PROBLEMS="$(ROOTDIR="$ROOT" TID="$T1" OLDCLAIM="$W1_CLAIM" OLDHOLDER="$SLUG@w1" ARGV="$RESUME_ARGV" "$PY" - <<'PY'
import os, sys
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
argv = os.environ["ARGV"]
for forbidden in ("--description", "Record the first result", "resp-001-task-001"):
    if forbidden in argv:
        problems.append("the resuming worker was handed %r on its command line; its only "
                        "input must be the durable state" % forbidden)
print("; ".join(problems))
PY
)"
[ -z "$P4_PROBLEMS" ] || fail 30 P4 "$P4_PROBLEMS"

# The late completion: the killed holder wakes up and tries to close the item
# with the token it still remembers. It must be refused, and refused silently
# in the ledger — a refusal that still emits is not a fence.
EV_BEFORE="$(ls "$EVENTS" 2>/dev/null | wc -l | tr -d ' ')$(cat "$EVENTS"/*.jsonl 2>/dev/null | wc -l | tr -d ' ')"
( cd "$ROOT" && OFFICER_NAME="$SLUG" bash cabinet/scripts/work-graph-complete.sh "$T1" \
    --status "done" --actor "$SLUG" --evidence "late completion by a dead holder" \
    --claim "$W1_CLAIM" ) > "$SCRATCH/p4-late.out" 2>&1
LATE_RC=$?
EV_AFTER="$(ls "$EVENTS" 2>/dev/null | wc -l | tr -d ' ')$(cat "$EVENTS"/*.jsonl 2>/dev/null | wc -l | tr -d ' ')"
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
( cd "$ROOT" && "$BOX_PY" -c "
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
bash -c "printf '{\"session_id\":\"a\"}' | OFFICER_NAME='$SLUG' CABINET_ROOT='$ROOT' bash '$HOOK'" \
  > "$SCRATCH/p2h-a.json" 2>"$SCRATCH/p2h-a.err" &
HA=$!
bash -c "printf '{\"session_id\":\"b\"}' | OFFICER_NAME='$SLUG' CABINET_ROOT='$ROOT' bash '$HOOK'" \
  > "$SCRATCH/p2h-b.json" 2>"$SCRATCH/p2h-b.err" &
HB=$!
WORKER_PIDS="$WORKER_PIDS $HA $HB"
wait "$HA" 2>/dev/null || true
wait "$HB" 2>/dev/null || true
WORKER_PIDS=""

HOOK_VERDICT="$(ROOTDIR="$ROOT" TID="$T2" AOUT="$SCRATCH/p2h-a.json" BOUT="$SCRATCH/p2h-b.json" "$PY" - <<'PY'
import json, os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.events.emitter import replay
tid = os.environ["TID"]
problems, ctx = [], []
for key in ("AOUT", "BOUT"):
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
PY
)"
HOOK_CODE="$(printf '%s' "$HOOK_VERDICT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["code"])')"
if [ "$HOOK_CODE" != "0" ]; then
  fail "$HOOK_CODE" P2h "$(printf '%s' "$HOOK_VERDICT" | "$PY" -c 'import json,sys; print("; ".join(json.load(sys.stdin)["problems"]))')"
fi
HOOK_HOLDER="$(printf '%s' "$HOOK_VERDICT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["holder"])')"
HOOK_CLAIM="$(printf '%s' "$HOOK_VERDICT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["claim_id"])')"

# The same session ticks again. Its own live claim is renewed, not re-injected:
# a hook that re-injects what it already holds re-injects it for the whole life
# of the session.
rm -f "$SENTINEL"
CABINET_WORKER_ID="$HOOK_HOLDER" bash -c "printf '{\"session_id\":\"a\"}' | OFFICER_NAME='$SLUG' CABINET_ROOT='$ROOT' bash '$HOOK'" \
  > "$SCRATCH/p2h-again.json" 2>"$SCRATCH/p2h-again.err"
AGAIN_PROBLEMS="$(ROOTDIR="$ROOT" TID="$T2" CLAIM="$HOOK_CLAIM" AGAIN="$SCRATCH/p2h-again.json" "$PY" - <<'PY'
import os, sys
from pathlib import Path
root = Path(os.environ["ROOTDIR"]); sys.path.insert(0, str(root))
from framework.events.emitter import replay
tid, claim = os.environ["TID"], os.environ["CLAIM"]
problems = []
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
print("; ".join(problems))
PY
)"
[ -z "$AGAIN_PROBLEMS" ] || fail 20 P2h "$AGAIN_PROBLEMS"

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
P5_PROBLEMS="$(ROOTDIR="$ROOT" OID="$OID" BEFORE="$SCRATCH/p1-digests.json" "$PY" - <<'PY'
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
print("; ".join(problems))
PY
)"
[ -z "$P5_PROBLEMS" ] || fail 40 P5 "$P5_PROBLEMS"
pass_stage P5 "one ratification, no proposal file rewritten, no second ask"

# ---------------------------------------------------------------------------
# P6 — receipts. What the Captain can see afterwards, and whether the graph
# agrees with it.
# ---------------------------------------------------------------------------
( cd "$ROOT" && "$PY" -m framework.missions.receipts --root "$ROOT" --json ) \
  > "$SCRATCH/p6-receipts.json" 2>"$SCRATCH/p6-receipts.err"
RECEIPTS_RC=$?
[ "$RECEIPTS_RC" -eq 0 ] || fail 40 P6 "receipts --json exited $RECEIPTS_RC: $(tr '\n' ' ' < "$SCRATCH/p6-receipts.err" | cut -c1-400)"

P6_PROBLEMS="$(ROOTDIR="$ROOT" OID="$OID" T1="$T1" T2="$T2" RECEIPTS="$SCRATCH/p6-receipts.json" "$PY" - <<'PY'
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
print("; ".join(problems))
PY
)"
[ -z "$P6_PROBLEMS" ] || fail 40 P6 "$P6_PROBLEMS"
pass_stage P6 "1 ratified, 2 completed with readable evidence, the released row, both nodes done"

# ---------------------------------------------------------------------------
# P7 — the result reaches an installed Cabinet. Without this the drill proves
# a Cabinet that improves itself in a repository nobody is running.
# ---------------------------------------------------------------------------
if [ "$SKIP_UPDATE" = "1" ]; then
  thin_stage P7 "skipped by --skip-update: the update leg was not run and nothing about it is proved"
else
  UPDATER="$ROOT/cabinet/scripts/cabinet-update.sh"
  [ -f "$UPDATER" ] || fail 50 P7 "no update path at cabinet/scripts/cabinet-update.sh — the result cannot reach an installed Cabinet"

  INSTALL="$SCRATCH/install"
  MUT="$SCRATCH/mutated"
  LOCKMUT="$SCRATCH/mutated-locked"
  mkdir -p "$INSTALL" "$MUT" "$LOCKMUT"
  tar -cf - -C "$ROOT" --exclude='./events' --exclude='./.git' . | tar -xf - -C "$INSTALL" \
    || fail 50 P7 "could not stage the scratch install"
  tar -cf - -C "$ROOT" --exclude='./events' --exclude='./.git' . | tar -xf - -C "$MUT" \
    || fail 50 P7 "could not stage the shipped tree"
  tar -cf - -C "$ROOT" --exclude='./events' --exclude='./.git' . | tar -xf - -C "$LOCKMUT" \
    || fail 50 P7 "could not stage the locked-path tree"
  MUTATED_REL="framework/missions/session_bridge.py"
  printf '\n# the one changed line this bundle ships\n' >> "$MUT/$MUTATED_REL"
  printf '\n# a change under the locked hooks directory\n' >> "$LOCKMUT/cabinet/scripts/hooks/session-task-inject.sh"

  # A preserved path with something in it: an update that quietly emptied this
  # would be the worst possible pass. The canary is a member of the same
  # shipped-empty preserve class as the Captain's standing switches, chosen
  # deliberately NOT to be one of them — no drill puts a live safety switch in
  # its write set, even a copy of one in a throwaway tree.
  PRESERVED_REL="shared/interfaces/captain-rules-index.yaml"
  mkdir -p "$INSTALL/shared/interfaces"
  printf 'drill: one non-empty preserved row\n' > "$INSTALL/$PRESERVED_REL"
  PRESERVED_BEFORE="$("$PY" -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$INSTALL/$PRESERVED_REL")"

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
  export CABINET_DASH_RESTART_CMD="$PY $LIB_DIR/stub_dashboard.py restart --port $PORT --stamp-file $STAMP_FILE --state-file $STUB_STATE --service $SERVICE"

  ( cd "$ROOT" && bash "$UPDATER" publish --from "$MUT" --to "$INSTALL" ) \
    > "$SCRATCH/p7-publish.out" 2>&1
  PUB_RC=$?
  [ "$PUB_RC" -eq 0 ] || fail 50 P7 "publish into the install's inbox exited $PUB_RC: $(tr '\n' ' ' < "$SCRATCH/p7-publish.out" | cut -c1-400)"

  BUNDLE_SHA="$(CABINET_ROOT="$INSTALL" bash "$UPDATER" status --json 2>/dev/null | "$PY" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit(0)
print(d.get("latest", {}).get("source_sha") or d.get("latest_sha") or "")
')"
  [ -n "$BUNDLE_SHA" ] || fail 50 P7 "the inbox reports no latest bundle after publish"
  printf '%s\n' "$BUNDLE_SHA" > "$STAMP_FILE"

  # (a) the gate goes RED because the restart did not happen: the old process
  # answers, with the old stamp and the old start time. The apply must roll the
  # tree back rather than leave a half-updated install behind a green light.
  ( cd "$INSTALL" && CABINET_ROOT="$INSTALL" CABINET_DASH_RESTART_CMD="/usr/bin/true" \
      bash "$UPDATER" apply --bundle "$BUNDLE_SHA" --from cli --skip-rebuild ) \
    > "$SCRATCH/p7-gate-red.out" 2>&1
  RED_RC=$?
  ROLLED="$(ROOTDIR="$ROOT" "$PY" - <<'PY'
import os, sys
from pathlib import Path
sys.path.insert(0, os.environ["ROOTDIR"])
from framework.events.emitter import replay
print(len(replay(event_types=["cabinet_update_rolled_back"])))
PY
)"
  if [ "$RED_RC" -eq 0 ]; then
    fail 50 P7 "an apply whose dashboard never restarted exited 0 — an identity-only probe passes an old process that survived a failed restart"
  fi
  [ "$ROLLED" != "0" ] || fail 50 P7 "the failed health gate emitted no cabinet_update_rolled_back"
  if grep -q 'the one changed line this bundle ships' "$INSTALL/$MUTATED_REL" 2>/dev/null; then
    fail 50 P7 "the rolled-back install still carries the bundle's change"
  fi

  # (b) the same apply with a real restart: the gate goes green.
  ( cd "$INSTALL" && CABINET_ROOT="$INSTALL" bash "$UPDATER" apply --bundle "$BUNDLE_SHA" --from cli --skip-rebuild ) \
    > "$SCRATCH/p7-apply.out" 2>&1
  APPLY_RC=$?
  [ "$APPLY_RC" -eq 0 ] || fail 50 P7 "apply exited $APPLY_RC: $(tr '\n' ' ' < "$SCRATCH/p7-apply.out" | cut -c1-400)"
  grep -q 'the one changed line this bundle ships' "$INSTALL/$MUTATED_REL" \
    || fail 50 P7 "apply reported success but the shipped change is not in the install"
  PRESERVED_AFTER="$("$PY" -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$INSTALL/$PRESERVED_REL")"
  [ "$PRESERVED_BEFORE" = "$PRESERVED_AFTER" ] || fail 50 P7 "apply overwrote a preserved path"
  SNAPS="$(ls "$INSTALL/.updates/snapshots" 2>/dev/null | wc -l | tr -d ' ')"
  [ "$SNAPS" -ge 1 ] || fail 50 P7 "apply kept no snapshot to roll back to"
  APPLIED="$(ROOTDIR="$ROOT" "$PY" - <<'PY'
import os, sys
sys.path.insert(0, os.environ["ROOTDIR"])
from framework.events.emitter import replay
print(len(replay(event_types=["cabinet_update_applied"])))
PY
)"
  [ "$APPLIED" != "0" ] || fail 50 P7 "a successful apply emitted no cabinet_update_applied"

  # (c) a bundle that touches the locked set is refused whole, before any write.
  HOOK_BEFORE="$("$PY" -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$INSTALL/cabinet/scripts/hooks/session-task-inject.sh")"
  ( cd "$ROOT" && bash "$UPDATER" publish --from "$LOCKMUT" --to "$INSTALL" ) > "$SCRATCH/p7-publish-locked.out" 2>&1
  LOCK_SHA="$(CABINET_ROOT="$INSTALL" bash "$UPDATER" status --json 2>/dev/null | "$PY" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit(0)
print(d.get("latest", {}).get("source_sha") or d.get("latest_sha") or "")
')"
  ( cd "$INSTALL" && CABINET_ROOT="$INSTALL" bash "$UPDATER" apply --bundle "$LOCK_SHA" --from cli --skip-rebuild ) \
    > "$SCRATCH/p7-locked.out" 2>&1
  LOCK_RC=$?
  [ "$LOCK_RC" -eq 3 ] || fail 50 P7 "a bundle changing a locked path exited $LOCK_RC, expected 3"
  HOOK_AFTER="$("$PY" -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$INSTALL/cabinet/scripts/hooks/session-task-inject.sh")"
  [ "$HOOK_BEFORE" = "$HOOK_AFTER" ] || fail 50 P7 "a refused bundle still changed a locked path"
  REFUSED="$(ROOTDIR="$ROOT" "$PY" - <<'PY'
import os, sys
sys.path.insert(0, os.environ["ROOTDIR"])
from framework.events.emitter import replay
print(len(replay(event_types=["cabinet_update_refused"])))
PY
)"
  [ "$REFUSED" != "0" ] || fail 50 P7 "a refused bundle emitted no cabinet_update_refused"

  "$PY" "$LIB_DIR/stub_dashboard.py" stop --state-file "$STUB_STATE" >/dev/null 2>&1 || true
  STUB_STATE=""
  thin_stage P7 "rebuild step skipped (--skip-rebuild): a scratch install carries no node toolchain, so the built stamp came from the stub server rather than from npm run build"
  pass_stage P7 "gate red rolled back, gate green applied, preserved path intact, locked bundle refused whole"
fi

# ---------------------------------------------------------------------------
# Hermeticity, after the fact. A drill that wrote outside its root proved
# nothing about a fresh hatch.
# ---------------------------------------------------------------------------
find "$HOME_DIR" 2>/dev/null | LC_ALL=C sort > "$SCRATCH/home.after"
( cd "$REPO_ROOT" && find . -not -path './.git/*' 2>/dev/null | LC_ALL=C sort ) > "$SCRATCH/repo.after"
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
