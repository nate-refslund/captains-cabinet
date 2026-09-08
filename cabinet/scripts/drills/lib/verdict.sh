# shellcheck shell=bash
# shellcheck disable=SC2034  # V_* / EV_COUNT / SHA_OUT / LEDGER_LINES are read by the drill that sources this
# verdict.sh — fail-CLOSED stage verdicts for the one-responsibility drill.
# Sourced by cabinet/scripts/drills/one-responsibility.sh; not executable on
# its own. `fail`, `$PY` and `$SCRATCH` come from the drill that sources it.
#
# THE DEFECT THIS FILE EXISTS TO FORBID, and it was found in this drill's own
# first cut by an independent reviewer. The obvious shell shape for a stage
#
#     PROBLEMS="$(ENV… "$PY" - <<'PY' … PY
#     )"
#     [ -z "$PROBLEMS" ] || fail 40 P6 "$PROBLEMS"
#
# scores an assertion block that CRASHED as a PASS: the traceback goes to
# stderr, stdout is empty, and empty reads as "no problems found". The same
# shape with the block's stderr folded into the file the reader parses scores a
# block whose output could not be PARSED as a pass — worse, because the stage
# then prints a specific claim ("ratified through the terminal door, one event,
# actor operator") that is false in every clause. A sensor that goes green
# because its assertion could not run cannot fail for the reason it was written
# to catch, and this drill is the sensor that declares phase 1 finished.
#
# THE CONTRACT INSTEAD. Every assertion block prints, on stdout, ONE json
# object {"code": <int>, "problems": [<string>…], …} on one line and then the
# line in $DRILL_VERDICT_SENTINEL — a line only a block that ran all the way to
# its end can print. Its stderr goes to a SEPARATE file, so nothing a library
# writes there can enter the payload. read_verdict refuses everything else — a
# non-zero block exit, a missing sentinel, a non-json verdict, a verdict that
# is not {code, problems}, a pass that names problems, a failure that names
# none — and turns each refusal into a stage FAILURE carrying the stage's own
# exit code. "Not measured" and "measured clean" are different facts and the
# drill must never confuse them.
#
# NONE of these helpers may be called inside a command substitution. `fail`
# exits, and `exit` inside $( ) exits only the subshell — the caller would sail
# on with an empty variable, which is the very fail-open this file removes.
# They return their answers in globals instead: V_CODE, V_PROBLEMS, V_JSON,
# V_FIELD, EV_COUNT, DIR_COUNT, SHA_OUT, LEDGER_LINES.
#
# EVERY COUNT IS TAKEN TWICE, AROUND THE LEG THAT IS SUPPOSED TO CHANGE IT.
# A count of the whole run answers "has this ever happened", which is a
# different question from "did THIS leg do it" and is satisfied by an earlier
# leg's row: three of P7's four legs would have been scored by an event another
# leg emitted. The helpers here refuse a count that could not be TAKEN; the
# caller's job is to compare two of them, because a count that did not CHANGE
# is the other half of the same fail-open.

DRILL_VERDICT_SENTINEL='--- one-responsibility stage verdict ends here ---'
export DRILL_VERDICT_SENTINEL

V_CODE=""
V_PROBLEMS=""
V_JSON=""
V_FIELD=""
EV_COUNT=""
DIR_COUNT=""
SHA_OUT=""
LEDGER_LINES=""

read_verdict() {  # read_verdict <stage> <fail_code> <block_rc> <out_file> <err_file>
  local stage="$1" code="$2" rc="$3" out="$4" err="$5"
  local parsed prc
  V_CODE=""; V_PROBLEMS=""; V_JSON=""
  if [ "$rc" -ne 0 ]; then
    fail "$code" "$stage" "the stage's assertions could not run (exit $rc), so the stage was NOT measured: $(tr '\n' ' ' < "$err" 2>/dev/null | cut -c1-400)"
  fi
  parsed="$(VOUT="$out" "$PY" - 2>"$out.readerr" <<'PY'
import json, os, sys
sentinel = os.environ["DRILL_VERDICT_SENTINEL"]
try:
    with open(os.environ["VOUT"], encoding="utf-8") as fh:
        lines = fh.read().splitlines()
except OSError as exc:
    raise SystemExit("the stage wrote no verdict file (%s)" % exc)
while lines and not lines[-1].strip():
    lines.pop()
if not lines or lines[-1] != sentinel:
    raise SystemExit("the assertion block never reached its end — no verdict sentinel. "
                     "Last bytes: %r" % ("\n".join(lines[-3:])[-300:],))
if len(lines) < 2:
    raise SystemExit("the assertion block printed its sentinel and no verdict")
try:
    verdict = json.loads(lines[-2])
except Exception as exc:
    raise SystemExit("the verdict line is not json (%s): %r" % (exc, lines[-2][:300]))
if not isinstance(verdict, dict) or "code" not in verdict or "problems" not in verdict:
    raise SystemExit("the verdict is not a {code, problems} object: %r" % (str(verdict)[:300],))
try:
    vcode = int(verdict["code"])
except Exception:
    raise SystemExit("the verdict code is not a number: %r" % (verdict["code"],))
problems = verdict["problems"]
if not isinstance(problems, list) or not all(isinstance(p, str) for p in problems):
    raise SystemExit("the verdict problems are not a list of strings: %r" % (str(problems)[:300],))
if vcode == 0 and problems:
    raise SystemExit("the verdict says pass and names %d problem(s): %s"
                     % (len(problems), "; ".join(problems)[:300]))
if vcode != 0 and not problems:
    raise SystemExit("the verdict says fail (%d) and names no problem, so the drill would "
                     "print an exit code nobody can act on" % vcode)
print(vcode)
print(" ".join("; ".join(problems).split()))
print(json.dumps(verdict, sort_keys=True))
PY
)"
  prc=$?
  if [ "$prc" -ne 0 ]; then
    fail "$code" "$stage" "the stage produced no readable verdict, so nothing about it was measured: $(tr '\n' ' ' < "$out.readerr" 2>/dev/null | cut -c1-400)"
  fi
  V_CODE="$(printf '%s\n' "$parsed" | sed -n '1p')"
  V_PROBLEMS="$(printf '%s\n' "$parsed" | sed -n '2p')"
  V_JSON="$(printf '%s\n' "$parsed" | sed -n '3p')"
  case "$V_CODE" in
    ''|*[!0-9]*) fail "$code" "$stage" "the verdict code came back as '$V_CODE', which is not a number" ;;
  esac
  [ "$V_CODE" = "0" ] || fail "$V_CODE" "$stage" "$V_PROBLEMS"
}

vfield() {  # vfield <stage> <fail_code> <field> — the field into $V_FIELD, or the stage fails
  local stage="$1" code="$2" name="$3"
  V_FIELD="$(VJSON="$V_JSON" VNAME="$name" "$PY" - 2>/dev/null <<'PY'
import json, os, sys
value = json.loads(os.environ["VJSON"]).get(os.environ["VNAME"])
if value is None or value == "":
    raise SystemExit(1)
sys.stdout.write(str(value))
PY
)" || fail "$code" "$stage" "the stage's verdict names no $name, so the drill would carry the next leg out against a value it never observed"
}

event_count() {  # event_count <stage> <fail_code> <event_type> — the count into $EV_COUNT
  local stage="$1" code="$2" etype="$3"
  EV_COUNT="$(ROOTDIR="$ROOT" ETYPE="$etype" "$PY" - 2>"$SCRATCH/event-count.err" <<'PY'
import os, sys
sys.path.insert(0, os.environ["ROOTDIR"])
from framework.events.emitter import replay
print(len(replay(event_types=[os.environ["ETYPE"]])))
PY
)" || fail "$code" "$stage" "the $etype count could not be taken, so the leg was not measured: $(tr '\n' ' ' < "$SCRATCH/event-count.err" 2>/dev/null | cut -c1-300)"
  case "$EV_COUNT" in
    ''|*[!0-9]*) fail "$code" "$stage" "the $etype count came back as '$EV_COUNT', which is not a number — a count that could not be taken must never read as 'more than none'" ;;
  esac
}

dir_count() {  # dir_count <stage> <fail_code> <dir> — entries in <dir> into $DIR_COUNT
  # An ABSENT directory is 0 (nothing has been written there yet, which is a
  # true fact about the leg before it runs); a path that exists and cannot be
  # listed is a FAILURE, because "I could not look" must never read as "there
  # was nothing there".
  local stage="$1" code="$2" path="$3"
  DIR_COUNT="$(TARGET="$path" "$PY" - 2>"$SCRATCH/dir-count.err" <<'PY'
import os, sys
from pathlib import Path
p = Path(os.environ["TARGET"])
if not p.exists():
    print(0)
    raise SystemExit(0)
if not p.is_dir():
    raise SystemExit("%s exists and is not a directory" % p)
print(len(list(p.iterdir())))
PY
)" || fail "$code" "$stage" "could not count the entries under $path, so a leg that kept nothing there and a leg nobody could look at would read the same: $(tr '\n' ' ' < "$SCRATCH/dir-count.err" 2>/dev/null | cut -c1-300)"
  case "$DIR_COUNT" in
    ''|*[!0-9]*) fail "$code" "$stage" "the entry count for $path came back as '$DIR_COUNT', which is not a number" ;;
  esac
}

sha256_of() {  # sha256_of <stage> <fail_code> <path> — the digest into $SHA_OUT
  local stage="$1" code="$2" path="$3"
  SHA_OUT="$(TARGET="$path" "$PY" - 2>/dev/null <<'PY'
import hashlib, os, sys
sys.stdout.write(hashlib.sha256(open(os.environ["TARGET"], "rb").read()).hexdigest())
PY
)" || fail "$code" "$stage" "could not digest $path — two digests that both failed to be taken compare EQUAL, which would read as 'the file was preserved'"
  [ -n "$SHA_OUT" ] || fail "$code" "$stage" "the digest of $path came back empty"
}

ledger_lines() {  # ledger_lines <stage> <fail_code> — total event lines into $LEDGER_LINES
  local stage="$1" code="$2"
  LEDGER_LINES="$(EVDIR="$EVENTS" "$PY" - 2>/dev/null <<'PY'
import os, sys
from pathlib import Path
d = Path(os.environ["EVDIR"])
if not d.is_dir():
    raise SystemExit(1)
total = 0
for p in sorted(d.glob("*.jsonl")):
    total += sum(1 for line in p.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())
print(total)
PY
)" || fail "$code" "$stage" "the ledger could not be counted, so 'the refusal wrote nothing' cannot be claimed"
  case "$LEDGER_LINES" in
    ''|*[!0-9]*) fail "$code" "$stage" "the ledger line count came back as '$LEDGER_LINES', which is not a number" ;;
  esac
}
