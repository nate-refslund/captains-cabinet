#!/bin/bash
# demo-dashboard.sh — serve the dashboard against the SYNTHETIC Testburg
# fixture (cabinet/fixtures/testburg/) for licensing-safe demos + screenshots.
#
# Perfect Cabinet Wave B demo kit (egg ledger row PC-B scope item 7): public
# demos must never show captain-personal or employer data. This script
#   1. stages the fixture into a scratch dir (never touches the tracked
#      fixture — read-only semantics by construction), by default REBASING
#      the story's fixed dates so "yesterday" is the last story day and the
#      active undo windows on /receipts stay genuinely active,
#   2. starts the EXISTING Next.js dashboard (cabinet/dashboard — no new
#      packages; npm ci only installs the lockfile if node_modules is absent)
#      as a dev server bound to 127.0.0.1 on a scratch port,
#   3. with an ALLOWLIST environment (env -i): the server inherits no shell
#      secrets, cabinet/.env is never sourced, REDIS_URL is absent so every
#      lib/redis.ts consumer stays on its built-in mock branch (IS_MOCK),
#      and the file surfaces the /receipts + config readers use point into
#      the stage:
#        CABINET_UNDO_DIR       <stage>/undo      (the /receipts journal)
#        CONFIG_PATH            <stage>/config/product.yml  (Ada Testburg)
#        CABINET_ENV_PATH       <stage>/cabinet.env         (empty file)
#        ACTIVE_PROJECT_FILE    <stage>/active-project.txt  ("testburg")
#        PROJECTS_DIR           <stage>/projects  (one synthetic testburg.yml)
#        AGENTS_DIR / LOOP_PROMPTS_DIR
#                               empty stage dirs (never the real instance)
#        CABINET_WORLD_OUT_DIR  <stage>/world     } WRITER-side belt-and-
#        CABINET_EVENT_LOG_DIR  <stage>/events    } suspenders only: honored
#                               by cabinet/scripts/world-chronicle.py + event
#                               writers if anything shells out python during
#                               a demo — NO dashboard page reads them.
#      CABINET_ROOT stays at THIS checkout so /governance reads the real
#      constitution/safety docs (code-tracked, non-personal — the PC-B
#      "governance reads the real files" direction).
#
# Screenshot-safe: /receipts, and the TOP cards of /governance ONLY — the
#   role-registry/CLAUDE.md editors further down /governance render THIS
#   checkout's real files (personal on a configured box; hero-demo runbook
#   A6 gate 3; long-term close = staging those reads, cross-area).
#   NOT /world: its engine route (dashboard app/api/world/engine) bypasses
#   the allowlist guarantee above — it builds its OWN redis client with a
#   localhost default and reads THIS checkout's live world surfaces
#   (instance/config/outcomes.yml + shared/interfaces/world-chronicle.jsonl),
#   so it renders live-estate data, never the fixture. Do not open or
#   screenshot it in a public demo (cross-area fix tracked in the Wave-B
#   report). The nav's project selector renders the dashboard's built-in
#   mock vocabulary (actions/projects.ts mock branch), not the fixture —
#   frame captures on the content region (hero-demo runbook A6).
# Other pages render mock or honest-empty data. Login password:
# testburg-demo (local demo only, printed below — NOT a secret).
#
# Usage:
#   bash cabinet/scripts/demo-dashboard.sh              start (port 3199)
#   bash cabinet/scripts/demo-dashboard.sh --port 4000  start on a port
#   bash cabinet/scripts/demo-dashboard.sh --no-rebase  keep 2026-07 story dates
#   bash cabinet/scripts/demo-dashboard.sh --stage-only stage the fixture, no server
#   bash cabinet/scripts/demo-dashboard.sh --status     is it running?
#   bash cabinet/scripts/demo-dashboard.sh --stop       tear down + rm stage
#
# Env knobs: CABINET_DEMO_TODAY=YYYY-MM-DD pins the rebase "today" (tests/CI);
# CABINET_PYTHON overrides the python used for staging.
#
# NEVER: launchctl, live Redis, Telegram, cabinet/.env, writes outside the
# stage dir. Tests: cabinet/scripts/tests/test_demo_dashboard_script.py.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FIXTURE="$REPO_ROOT/cabinet/fixtures/testburg"
DASH_DIR="$REPO_ROOT/cabinet/dashboard"
# NUMERIC uid suffix on purpose: the /receipts PROOF line prints the resolved
# journal dir, and a login-name suffix would put the captain's username into
# demo screenshots. uid keeps multi-user /tmp collision-safety without the leak.
# (Trailing slash stripped: macOS TMPDIR ends in "/" and the doubled slash
# would show verbatim in the rendered PROOF footer.)
TMP_BASE="${TMPDIR:-/tmp}"
STAGE="${TMP_BASE%/}/cabinet-testburg-demo-$(id -u)"
PID_FILE="$STAGE/server.pid"
LOG_FILE="$STAGE/dev.log"
PORT=3199
REBASE=1
MODE="start"
PY="${CABINET_PYTHON:-python3.12}"

usage() {
  sed -n 's/^# \?//p' "$0" | sed -n '/^Usage:/,/^$/p' >&2
  exit 64
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --port) [ "$#" -ge 2 ] || usage; PORT="$2"; shift 2 ;;
    --no-rebase) REBASE=0; shift ;;
    --stage-only) MODE="stage"; shift ;;
    --stop) MODE="stop"; shift ;;
    --status) MODE="status"; shift ;;
    -h|--help) usage ;;
    *) echo "demo-dashboard: unknown argument $1" >&2; usage ;;
  esac
done

case "$PORT" in (*[!0-9]*|'') echo "demo-dashboard: --port wants digits" >&2; exit 64 ;; esac

running_pid() {
  # prints the live server pid, or nothing
  [ -f "$PID_FILE" ] || return 0
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && echo "$pid"
  return 0
}

if [ "$MODE" = "status" ]; then
  pid="$(running_pid)"
  if [ -n "$pid" ]; then
    echo "demo-dashboard: running (pid $pid, stage $STAGE)"
    echo "  log: $LOG_FILE"
  else
    echo "demo-dashboard: not running"
  fi
  exit 0
fi

if [ "$MODE" = "stop" ]; then
  pid="$(running_pid)"
  if [ -n "$pid" ]; then
    # next dev forks workers — take down the process group it leads.
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    kill -0 "$pid" 2>/dev/null && { kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true; }
    echo "demo-dashboard: stopped (pid $pid)"
  else
    echo "demo-dashboard: nothing running"
  fi
  # Only ever delete OUR fixed stage path (guard against a mangled env).
  case "$STAGE" in
    */cabinet-testburg-demo-*) rm -rf "$STAGE" ;;
    *) echo "demo-dashboard: refusing to delete unexpected stage $STAGE" >&2 ;;
  esac
  exit 0
fi

# ── start ────────────────────────────────────────────────────────────────────
[ -d "$FIXTURE/undo" ] && [ -d "$FIXTURE/world" ] || {
  echo "demo-dashboard: fixture incomplete at $FIXTURE (run cabinet/fixtures/testburg/generate.py)" >&2
  exit 1
}
command -v "$PY" >/dev/null 2>&1 || { echo "demo-dashboard: $PY not found on PATH" >&2; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "demo-dashboard: npm not found on PATH" >&2; exit 1; }

if [ -n "$(running_pid)" ]; then
  echo "demo-dashboard: already running (pid $(running_pid)) — --stop first" >&2
  exit 1
fi

# Refuse a busy port rather than hunting (deterministic demos). Stage-only
# runs never bind it, so they skip the check.
if [ "$MODE" = "start" ] && command -v nc >/dev/null 2>&1 \
    && nc -z 127.0.0.1 "$PORT" 2>/dev/null; then
  echo "demo-dashboard: 127.0.0.1:$PORT is already in use — pick --port" >&2
  exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE/events" "$STAGE/projects" "$STAGE/agents" "$STAGE/loop-prompts"
: > "$STAGE/cabinet.env"
# Active-project identity for the dashboard's env-honoring file readers
# (lib/config.ts): Testburg vocabulary, never a real product slug (the
# lane-decouple direction — demo defaults must not ship a real lane).
# The nav selector itself rides actions/projects.ts's mock branch and does
# NOT read these files — see the header note.
printf 'testburg\n' > "$STAGE/active-project.txt"
cp -R "$FIXTURE/config" "$STAGE/config"
cp "$FIXTURE/config/projects/testburg.yml" "$STAGE/projects/testburg.yml"

# Stage undo/ + world/, rebasing the five fixed story dates (README: the
# story runs 2026-07-07..09 with ttl horizons 07-10/07-11) so the demo's
# "yesterday" is the last story day and active undo windows stay active.
# SINGLE-PASS regex over the whole mapping, never sequential replaces: a
# per-date replace chain cascades whenever the run date sits inside the
# story window (replaced output collides with a later map key), silently
# merging story days and overwriting staged files (2026-07-10 adversarial
# review). The uniqueness assert turns any future mapping bug into a loud
# failure instead of an overwrite. Fixed literal replacements only — no
# user input touches this. CABINET_DEMO_TODAY pins "today" for tests.
REBASE="$REBASE" "$PY" - "$FIXTURE" "$STAGE" <<'PYEOF'
import datetime as dt
import os
import pathlib
import re
import sys

fixture, stage = map(pathlib.Path, sys.argv[1:3])
story = ["2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10", "2026-07-11"]
mapping = {}
if os.environ.get("REBASE") == "1":
    pin = os.environ.get("CABINET_DEMO_TODAY")
    today = dt.date.fromisoformat(pin) if pin else dt.date.today()
    # story index 3 ("story now", 2026-07-10) maps onto today
    mapping = {s: (today + dt.timedelta(days=i - 3)).isoformat()
               for i, s in enumerate(story)}
pat = re.compile("|".join(re.escape(s) for s in story))


def rebased(text: str) -> str:
    if not mapping:
        return text
    return pat.sub(lambda m: mapping[m.group(0)], text)


for sub in ("undo", "world"):
    out_dir = stage / sub
    out_dir.mkdir(parents=True, exist_ok=True)
    staged = set()
    for src in sorted((fixture / sub).glob("*.jsonl")):
        name = rebased(src.name)
        if name in staged:
            sys.exit(f"demo-dashboard: staging collision on {sub}/{name} — "
                     "mapping bug, refusing to overwrite a staged file")
        staged.add(name)
        (out_dir / name).write_text(rebased(src.read_text(encoding="utf-8")),
                                    encoding="utf-8")
        print(f"staged {sub}/{name}")
PYEOF

if [ "$MODE" = "stage" ]; then
  echo "demo-dashboard: stage-only complete at $STAGE"
  exit 0
fi

# Install the ALREADY-DECLARED dependencies if this checkout has none yet.
if [ ! -d "$DASH_DIR/node_modules" ]; then
  echo "demo-dashboard: node_modules missing — npm ci (lockfile only, no new packages)…"
  (cd "$DASH_DIR" && npm ci --no-audit --no-fund)
fi

# Allowlist environment: env -i means NOTHING leaks in from this shell (no
# tokens, no REDIS_URL → every lib/redis.ts consumer stays on its mock
# branch; the /world engine route's own client is the known exception —
# header). PATH/HOME/TMPDIR are what node+npm legitimately need.
echo "demo-dashboard: starting on http://127.0.0.1:$PORT (stage $STAGE)"
cd "$DASH_DIR"
set -m   # own process group per job, so --stop can take down next's workers
env -i \
  PATH="$PATH" HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" \
  CABINET_ROOT="$REPO_ROOT" \
  CABINET_RUNTIME_MODE=native \
  CONFIG_PATH="$STAGE/config/product.yml" \
  CABINET_UNDO_DIR="$STAGE/undo" \
  CABINET_WORLD_OUT_DIR="$STAGE/world" \
  CABINET_EVENT_LOG_DIR="$STAGE/events" \
  CABINET_ENV_PATH="$STAGE/cabinet.env" \
  PROJECTS_DIR="$STAGE/projects" \
  AGENTS_DIR="$STAGE/agents" \
  LOOP_PROMPTS_DIR="$STAGE/loop-prompts" \
  ACTIVE_PROJECT_FILE="$STAGE/active-project.txt" \
  DASHBOARD_PASSWORD=testburg-demo \
  npx next dev --port "$PORT" --hostname 127.0.0.1 \
  >"$LOG_FILE" 2>&1 &
pid=$!
set +m
echo "$pid" > "$PID_FILE"

# Wait for the server to answer (dev compile of the first route included).
ok=0
for _ in $(seq 1 90); do
  if curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/login"; then
    ok=1; break
  fi
  kill -0 "$pid" 2>/dev/null || break
  sleep 1
done
if [ "$ok" != 1 ]; then
  echo "demo-dashboard: server failed to come up — tail of $LOG_FILE:" >&2
  tail -20 "$LOG_FILE" >&2 || true
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  exit 1
fi

cat <<EOF
demo-dashboard: up. Testburg demo estate (synthetic — cabinet/fixtures/testburg):

  login       http://127.0.0.1:$PORT/login        password: testburg-demo
  receipts    http://127.0.0.1:$PORT/receipts     (undo journal — Wave B page)
  governance  http://127.0.0.1:$PORT/governance   (capture TOP cards only —
              the lower editors render THIS checkout's real files; runbook A6)

  NOT demo-safe: /world — its engine route reads THIS checkout's live world
  surfaces through its own redis client (localhost default), never the
  fixture; do not open or screenshot it in a public demo. The nav project
  selector shows built-in mock vocabulary, not the fixture — frame captures
  on the content region (hero-demo runbook A6).

  log         $LOG_FILE
  stop        bash cabinet/scripts/demo-dashboard.sh --stop
EOF
