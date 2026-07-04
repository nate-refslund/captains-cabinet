#!/bin/bash
# limit-reset-watchdog.sh — Auto-resume officers after an account session-limit
# reset (Nate-requested resilience feature, 2026-06-25).
#
# THE PROBLEM
# When an officer (or one of its subagents) exhausts the account session limit,
# Claude Code prints a line like:
#     You've hit your session limit · resets 5:10pm
# (wording also seen as "Approaching your session limit", "resets at 5pm",
# "resets 17:10"). The active turn FAILS and the officer goes idle. Nothing
# resumes it until a human types "resume" — the never-stop discipline can't
# fire because the turn itself died, not stopped. Work stalls for the whole
# window (can be hours).
#
# THE FIX (reuses existing infra end-to-end — nothing new invented):
#   DETECT      — scan each officer's tmux pane (`tmux capture-pane`) for the
#                 limit string, same probe the heartbeat-watchdog + trigger
#                 wake already use.
#   PARSE+STORE — extract the reset clock time, resolve it to a UTC epoch in the
#                 Captain's timezone (Europe/Copenhagen; am/pm aware; "already
#                 past today" ⇒ tomorrow), and store it at
#                 cabinet:limit-reset:<officer>. The officer's own
#                 cabinet:active-task:<officer> flag (set by the officer, read
#                 by session-stop.sh) is the durable RESUME pointer — it already
#                 survives idle/restart, we only confirm it is present.
#   WATCH+WAKE  — when now >= the stored reset epoch, fire the EXISTING wake
#                 (notify-officer.sh → trigger_send → trigger_wake_officer's
#                 tmux send-keys) and DELETE the key so it fires exactly once.
#   RESUME      — the woken officer reads its active-task flag and continues via
#                 the never-stop loop. We do not re-implement resume here.
#
# This script does DETECT+PARSE+STORE and WATCH+WAKE on every tick (one cron,
# every ~3 min). It is deliberately SEPARATE from heartbeat-watchdog.sh:
# heartbeat's job is restart-on-death (a destructive launchctl kickstart);
# a session-limit officer is ALIVE and must NOT be restarted (that would lose
# its in-flight context). Keeping the two concerns in separate daemons keeps
# heartbeat's death matrix clean.
#
# IDEMPOTENT / NO WAKE-SPAM:
#   * Re-storing while a key already exists refreshes the SAME epoch (parse is
#     deterministic), never stacks.
#   * The key is DELETED the instant a wake fires, so a given reset wakes once.
#   * The wake itself (trigger_wake_officer) is debounced + idle-gated.
#   * If Redis is down we no-op (can't read/write state) and retry next tick.

set -uo pipefail

REPO_ROOT="${CABINET_SOURCE_REPO:-${CABINET_ROOT:-$HOME/work/captains-cabinet}}"

# Source cabinet/.env so notify-officer.sh's downstream Telegram/Redis env is
# populated under launchd (no login shell). set -a exports to children.
if [ -f "$REPO_ROOT/cabinet/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO_ROOT/cabinet/.env"
  set +a
fi
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

# Captain timezone: read from platform.yml, fall back to the Captain's home tz.
# Both Berlin and Copenhagen are CEST/CET (identical offset) so either is
# correct for am/pm resolution; Copenhagen is the documented Captain tz.
CAPTAIN_TZ="$(awk -F'#' '{print $1}' "$REPO_ROOT/instance/config/platform.yml" 2>/dev/null \
  | awk -F': *' '$1=="captain_timezone"{print $2; exit}' | tr -d '[:space:]')"
CAPTAIN_TZ="${CAPTAIN_TZ:-Europe/Copenhagen}"

# How long a stored reset is allowed to linger unfired before we treat it as
# stale and clear it (a malformed/way-future parse should not pin an officer
# forever). 12h covers the longest realistic reset window with margin.
RESET_TTL_SECONDS=$((12 * 3600))

# ---------------------------------------------------------------------------
# Officer roster — same derivation strategy as heartbeat-watchdog: prefer
# instance/roles/active/*.yml (all officer_types; even a consultant that is
# CURRENTLY running can hit a limit and should be resumed), else fall back to
# .claude/agents/*.md slugs that have an installed officer LaunchAgent. We only
# act on slugs whose tmux session `officer-<slug>` actually exists, so a stale
# roster entry is harmless.
# ---------------------------------------------------------------------------
OFFICERS=()
ROLES_DIR="$REPO_ROOT/instance/roles/active"
if [ -d "$ROLES_DIR" ]; then
  for role_yml in "$ROLES_DIR"/*.yml; do
    [ -f "$role_yml" ] || continue
    OFFICERS+=("$(basename "$role_yml" .yml)")
  done
fi
if [ "${#OFFICERS[@]}" -eq 0 ]; then
  AGENTS_DIR="$REPO_ROOT/.claude/agents"
  LA_DIR="$HOME/Library/LaunchAgents"
  if [ -d "$AGENTS_DIR" ]; then
    for agent_md in "$AGENTS_DIR"/*.md; do
      [ -f "$agent_md" ] || continue
      slug="$(basename "$agent_md" .md)"
      [ "$slug" = "TEMPLATE" ] && continue
      if [ -f "$LA_DIR/com.cabinet.officer.$slug.plist" ]; then
        OFFICERS+=("$slug")
      fi
    done
  fi
fi

# ---------------------------------------------------------------------------
# parse_reset_to_epoch <clock-text> [now_epoch]
#   Pure time-parse, factored out so it is unit-testable in isolation
#   (CABINET_LRW_SELFTEST=1 below). Echoes a UTC epoch (seconds) on success,
#   nothing on failure (caller checks for empty). Resolution rules:
#     * accepts "5:10pm", "5pm", "17:10", "5:10 PM", "at 5:10pm"
#     * interprets the clock in $CAPTAIN_TZ on "today"; if that instant is
#       already <= now, it means the NEXT day (resets roll forward).
#     * am/pm honored; 24h honored; "12am"=00:00, "12pm"=12:00.
#   Implemented in Python (zoneinfo, DST-correct) — the BSD/GNU `date` split
#   makes tz-aware epoch math fragile in pure bash.
# ---------------------------------------------------------------------------
parse_reset_to_epoch() {
  local raw="$1" now="${2:-}"
  CAPTAIN_TZ="$CAPTAIN_TZ" LRW_RAW="$raw" LRW_NOW="$now" python3 - <<'PY'
import os, re, sys, datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    sys.exit(0)

raw = os.environ.get("LRW_RAW", "")
tzname = os.environ.get("CAPTAIN_TZ", "Europe/Copenhagen")
now_env = os.environ.get("LRW_NOW", "").strip()

try:
    tz = ZoneInfo(tzname)
except Exception:
    tz = ZoneInfo("UTC")

# Reference "now": injectable for tests, else real wall clock in Captain tz.
if now_env:
    now = datetime.datetime.fromtimestamp(int(now_env), tz=tz)
else:
    now = datetime.datetime.now(tz)

# Pull the FIRST time-of-day token. Accepts H, H:MM, optional am/pm (any case,
# optional space / dots like "p.m."). 24h (e.g. 17:10) handled when no am/pm.
m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?', raw, re.IGNORECASE)
ampm = None
if m:
    hour = int(m.group(1)); minute = int(m.group(2) or 0); ampm = m.group(3).lower()
else:
    m = re.search(r'(\d{1,2}):(\d{2})', raw)  # 24h "17:10"
    if not m:
        sys.exit(0)
    hour = int(m.group(1)); minute = int(m.group(2))

if minute > 59:
    sys.exit(0)

if ampm is not None:
    if hour < 1 or hour > 12:
        sys.exit(0)
    if ampm == 'a':
        hour = 0 if hour == 12 else hour
    else:  # pm
        hour = 12 if hour == 12 else hour + 12
else:
    if hour > 23:
        sys.exit(0)

candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
# Resets roll forward: if the clock time already passed today, it's tomorrow.
if candidate <= now:
    candidate = candidate + datetime.timedelta(days=1)

print(int(candidate.timestamp()))
PY
}

# ---------------------------------------------------------------------------
# SELF-TEST mode — `CABINET_LRW_SELFTEST=1 bash limit-reset-watchdog.sh`
# Exercises parse_reset_to_epoch with a fixed reference now and asserts the
# resolved UTC epoch. No Redis, no tmux, no side effects.
# ---------------------------------------------------------------------------
if [ "${CABINET_LRW_SELFTEST:-0}" = "1" ]; then
  fails=0
  # Reference now: 2026-06-25 10:00:00 Europe/Copenhagen (CEST, +02:00) == 1782374400.
  # Expected epochs below are derived directly from this ref via zoneinfo
  # (computed once, asserted here) — NOT hand-converted.
  REF=1782374400
  # Guard: if the captain tz drifts from a CEST-offset zone the fixtures below
  # no longer hold. Skip (don't false-fail) and say so.
  REF_TZ_OK="$(CAPTAIN_TZ="$CAPTAIN_TZ" python3 - <<'PY'
import os, datetime
try:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(os.environ["CAPTAIN_TZ"])
    off = datetime.datetime(2026,6,25,10,0,tzinfo=tz).utcoffset()
    print("yes" if off == datetime.timedelta(hours=2) else "no")
except Exception:
    print("no")
PY
)"
  if [ "$REF_TZ_OK" != "yes" ]; then
    echo "limit-reset-watchdog self-test: captain tz '$CAPTAIN_TZ' is not +02:00 on the fixture date; skipping fixed-epoch asserts (parser still exercised live)."
    parse_reset_to_epoch "resets 5:10pm" "$REF" >/dev/null && echo "  parser ran OK on '$CAPTAIN_TZ'" && exit 0
    echo "  parser FAILED to run"; exit 1
  fi
  check() {
    local label="$1" text="$2" want="$3"
    local got; got="$(parse_reset_to_epoch "$text" "$REF")"
    if [ "$got" = "$want" ]; then
      echo "  ok   | $label | '$text' -> $got"
    else
      echo "  FAIL | $label | '$text' -> got='$got' want='$want'"; fails=$((fails+1))
    fi
  }
  echo "limit-reset-watchdog self-test (tz=$CAPTAIN_TZ, ref now=2026-06-25 10:00 Copenhagen / ${REF}):"
  # 5:10pm Copenhagen, later today (after ref 10:00)
  check "5:10pm today"          "You've hit your session limit · resets 5:10pm" 1782400200
  # 5pm shorthand, later today
  check "5pm shorthand"         "resets 5pm"                                    1782399600
  # 24h 17:10 == 5:10pm
  check "24h 17:10"             "resets 17:10"                                  1782400200
  # 9:00am is BEFORE ref now (10:00) -> rolls to tomorrow 2026-06-26 09:00
  check "9am already-past→tmrw" "resets 9:00am"                                 1782457200
  # 12pm = noon today (after ref 10:00)
  check "12pm noon"             "resets at 12pm"                                1782381600
  # 12am = midnight; today's already passed -> tomorrow 2026-06-26 00:00
  check "12am midnight→tmrw"    "resets 12am"                                   1782424800
  # dotted p.m.
  check "dotted p.m."           "resets 5:10 p.m."                              1782400200
  # garbage -> empty
  check "no time → empty"       "some unrelated text"                          ""
  echo "---"
  if [ "$fails" -eq 0 ]; then echo "ALL PASS"; exit 0; else echo "$fails FAIL(S)"; exit 1; fi
fi

# ---------------------------------------------------------------------------
# Redis reachability — no state without it, so no-op + retry next tick. exit 0
# so launchd accrues no failure backoff (mirrors heartbeat-watchdog).
# ---------------------------------------------------------------------------
REDIS_PING=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -t 2 PING 2>/dev/null || echo "")
if [ "$REDIS_PING" != "PONG" ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) limit-reset-watchdog: Redis unreachable at $REDIS_HOST:$REDIS_PORT — no-op, retry next tick" >&2
  exit 0
fi

NOW_EPOCH=$(date -u +%s)

# Limit-banner matcher — DELIBERATELY two-part to avoid false positives.
#
# The real Claude Code banner ALWAYS pairs a limit phrase with a "reset(s)"
# clause carrying a CLOCK TIME, e.g.:
#     You've hit your session limit · resets 5:10pm
#     Approaching your usage limit — resets at 5pm
# A matched line must therefore satisfy BOTH:
#   LIMIT_RE  — a genuine limit phrase ("hit/reached/approaching ... limit"), AND
#   RESET_RE  — a "reset" clause immediately followed by a clock (Hpm | H:MMam | 24h).
# Requiring the clock IN the regex (not just downstream in the parser) stops
# benign pane text — including THIS watchdog's own resume nudge ("Session limit
# reset — resume your active-task") and trigger echoes that mention "session
# limit reset" — from ever being treated as a banner. Those lines have no
# clock after "reset", so RESET_RE rejects them outright (observed false-arm
# source 2026-06-25: a polads-ceo pane echoing a prior "session limit reset"
# trigger). Detection still only ARMS; the now>=reset gate guards the wake.
LIMIT_RE='(hit|reached|approaching|exceeded)[^.]{0,40}(session|usage|message|rate)?[[:space:]]*limit'
RESET_RE='reset[s]?[[:space:]]*(at[[:space:]]*)?[0-9]{1,2}([:.][0-9]{2})?[[:space:]]*([ap]\.?[[:space:]]*m\.?)?'
# Lines that are unmistakably OUR resume nudge / a relayed trigger, never a
# banner — excluded belt-and-braces even though RESET_RE already drops them.
SELF_NUDGE_RE='resume your active-task|never-stop loop|surface to the Chair'

for o in "${OFFICERS[@]}"; do
  SESSION="officer-${o}"

  # ----- DETECT + PARSE + STORE -------------------------------------------
  # Only meaningful where the officer's tmux session exists on this host.
  if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$SESSION" 2>/dev/null; then
    # Capture a generous tail (limit banners can scroll up a few lines under a
    # spinner). -p prints the visible pane; we scan the last ~40 non-blank lines.
    PANE=$(tmux capture-pane -t "$SESSION" -p 2>/dev/null | grep -v '^[[:space:]]*$' | tail -40)

    # A real banner line has BOTH a limit phrase AND a reset+clock clause, and
    # is NOT our own resume nudge. grep the limit lines, then require the reset
    # clause and reject self-nudge on the SAME line.
    LIMIT_LINE=$(echo "$PANE" | grep -iE "$LIMIT_RE" \
                   | grep -iE "$RESET_RE" \
                   | grep -ivE "$SELF_NUDGE_RE" | tail -1)

    if [ -n "$LIMIT_LINE" ]; then
      RESET_EPOCH=$(parse_reset_to_epoch "$LIMIT_LINE" "")

      if [ -n "$RESET_EPOCH" ]; then
        EXISTING=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "cabinet:limit-reset:$o" 2>/dev/null || echo "")
        # Store with a TTL guard so a stale key self-clears even if the wake
        # branch never runs. SET (overwrite) is fine — deterministic parse means
        # re-detecting the same banner yields the same epoch (idempotent).
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
          SET "cabinet:limit-reset:$o" "$RESET_EPOCH" EX "$RESET_TTL_SECONDS" >/dev/null 2>&1
        if [ "$EXISTING" != "$RESET_EPOCH" ]; then
          # Confirm the resume pointer exists. We do NOT create it (only the
          # officer knows its task); we surface its absence so the operator
          # knows resume will be a bare wake (still useful — the loop prompt
          # re-engages the officer even without an active-task string).
          AT=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "cabinet:active-task:$o" 2>/dev/null || echo "")
          HUMAN=$(TZ="$CAPTAIN_TZ" date -r "$RESET_EPOCH" '+%Y-%m-%d %H:%M %Z' 2>/dev/null \
                  || date -u -r "$RESET_EPOCH" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || echo "$RESET_EPOCH")
          echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) limit-reset-watchdog: ARMED $o reset=$RESET_EPOCH ($HUMAN) active-task=$([ -n "$AT" ] && echo present || echo ABSENT) line='$LIMIT_LINE'" >&2
        fi
      else
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) limit-reset-watchdog: $o limit notice seen but no parseable reset time in: '$LIMIT_LINE'" >&2
      fi
    fi
  fi

  # ----- WATCH + WAKE ------------------------------------------------------
  # Independent of the detect branch above (a key armed on a prior tick must
  # fire even if the banner has since scrolled away or the session was probed
  # as absent this tick).
  STORED=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "cabinet:limit-reset:$o" 2>/dev/null || echo "")
  [ -z "$STORED" ] && continue
  if ! [[ "$STORED" =~ ^[0-9]+$ ]]; then
    # Corrupt value — drop it so it can't wedge the officer.
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL "cabinet:limit-reset:$o" >/dev/null 2>&1
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) limit-reset-watchdog: $o cleared non-numeric limit-reset value '$STORED'" >&2
    continue
  fi

  if [ "$NOW_EPOCH" -ge "$STORED" ]; then
    # Fire-once: DELETE FIRST (atomic GETDEL) so a slow notify can't double-fire
    # if ticks overlap. Only the tick that actually removes the key sends.
    CLAIMED=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GETDEL "cabinet:limit-reset:$o" 2>/dev/null || echo "")
    if [ -z "$CLAIMED" ]; then
      # Lost the race (another tick / GETDEL unsupported + already gone) — skip.
      continue
    fi
    if ! [[ "$CLAIMED" =~ ^[0-9]+$ ]] || [ "$NOW_EPOCH" -lt "$CLAIMED" ]; then
      # GETDEL returned an unexpected/early value — re-arm to be safe and move on.
      [[ "$CLAIMED" =~ ^[0-9]+$ ]] && redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
        SET "cabinet:limit-reset:$o" "$CLAIMED" EX "$RESET_TTL_SECONDS" >/dev/null 2>&1
      continue
    fi

    # Fire the EXISTING wake. notify-officer.sh → trigger_send → (a) durable XADD
    # on cabinet:triggers:<o>, (b) trigger_wake_officer tmux send-keys to re-invoke
    # the idle pane. The officer then reads its active-task flag and resumes.
    MSG="Session limit reset — resume your active-task. The account session limit window has elapsed; pick up exactly where the limited turn left off (read cabinet:active-task:$o and continue per the never-stop loop). gather-then-decide; surface to the Chair; never DM Nate."
    if bash "$REPO_ROOT/cabinet/scripts/notify-officer.sh" "$o" "$MSG" >/dev/null 2>&1; then
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) limit-reset-watchdog: FIRED wake for $o (reset $CLAIMED reached) + cleared key" >&2
    else
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) limit-reset-watchdog: notify-officer FAILED for $o (reset $CLAIMED) — key already cleared, will re-arm on next banner detect" >&2
    fi
  fi
done

# ---------------------------------------------------------------------------
# Tick heartbeat (adversarial review, lane-ops 2026-07-04). WHY: the
# outcome-watchdog now derives a log-freshness floor for every services.yml
# row (registry.py::verify_no_silent_cron_failure; this row: interval 180s →
# 2h floor), and this script used to log ONLY on events (armed/fired/error,
# all to stderr) — so any healthy quiet stretch >2h false-paged the Chair
# forever (live evidence the day the floors shipped: 5.7h of legitimate
# silence while running fine). The services.yml `expected:` for this row has
# always claimed "log writes every cycle"; this line makes that claim TRUE
# instead of the floor false-paging on it. Placement is load-bearing: END of
# the tick, so the heartbeat asserts "a full DETECT+WATCH pass COMPLETED" —
# a mid-loop wedge stops the heartbeat and the freshness floor catches it.
# stdout (not stderr) on purpose: it lands in limit-reset-watchdog.out.log
# (a watched freshness candidate) while .err.log stays event-only, keeping
# the watchdog's 25-line tail marker scan high-signal. The text must never
# contain a JOB_ERROR_MARKERS token (FATAL / NOGROUP / "command not found" /
# "trigger NOT pushed" / "trigger_send failed" / Traceback) — a heartbeat
# that spells an error token would page the very scan it feeds.
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) limit-reset-watchdog: tick complete (${#OFFICERS[@]} officer pane(s) scanned)"

exit 0
