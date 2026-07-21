#!/bin/bash
# pre-tool-use.sh — Runs before every tool invocation
# Exit 0 = allow, Exit 2 = block (with reason on stderr).
# Stderr (not stdout) is the operator-visible channel on block; Claude Code's
# hook engine treats stdout as tool-stdout and suppresses it on exit 2, which
# manifests as silent "No stderr output" rejection. FW-022 migrated every
# exit-2 echo path here to `>&2` for this reason — keep new paths the same way.
# Claude Code passes JSON on stdin: { tool_name, tool_input }

# Read JSON from stdin
HOOK_INPUT=$(cat)
TOOL_NAME=$(echo "$HOOK_INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
TOOL_INPUT=$(echo "$HOOK_INPUT" | jq -c '.tool_input // {}' 2>/dev/null)

# REDIS CONNECTION RESOLUTION (B4 — Mac portability)
# Honors REDIS_HOST + REDIS_PORT first; REDIS_URL only if neither is set.
# Rationale: LaunchAgent plists on Mac export REDIS_HOST=localhost +
# REDIS_PORT=6379 but do NOT set REDIS_URL. The legacy default of
# REDIS_URL=redis://redis:6379 (Docker DNS) silently broke the kill switch,
# spending limits, and policy enforcement on Mac whenever REDIS_URL was
# unset or inherited stale. Explicit REDIS_HOST/REDIS_PORT wins; REDIS_URL
# is a fallback for callers that only set the URL form. This block touches
# the Redis connection only — policy/allow/block logic below is unchanged.
if [ -n "${REDIS_HOST:-}" ] || [ -n "${REDIS_PORT:-}" ]; then
  REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
  REDIS_PORT="${REDIS_PORT:-6379}"
elif [ -n "${REDIS_URL:-}" ]; then
  REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
  REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)
  REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
  REDIS_PORT="${REDIS_PORT:-6379}"
else
  REDIS_HOST="127.0.0.1"
  REDIS_PORT="6379"
fi

# ============================================================
# 0. TYPED POLICY ENGINE (shadow, or ENFORCING behind the Captain flip)
# ============================================================
# policy-shadow.py evaluates the same hook input through the typed policy
# engine and emits {"decision": allow|block, "reason": ...} while recording to
# org_events for parity analysis.
#
# CAPTAIN FLIP (2026-07-03, "flip it" — parity proof v2: 100% covered-rule
# agreement, 0 fail-open, 0 fail-safe): when enforcement is ON — env
# CABINET_AUTHORITY_ENFORCING=1 OR the flag file
# instance/config/authority-enforcing exists (file flag = instant flip/revert
# for every live session, no restarts; revert = rm the file) — a typed "block"
# verdict exits 2 with the engine's reason.
#
# FAIL-OPEN TO THE PROVEN FLOOR: any wrapper failure (python error, empty or
# unparseable output) falls through to the bash rules below, which per the
# parity proof enforce a superset of the typed engine's stateless coverage —
# so this path can never be bricked by telemetry and never widens allowed
# behavior. The three STATEFUL attestation gates (Layer-1 push/merge review,
# CI-green, gh-api branch-delete) and all legacy bash rules remain untouched
# and still run after this section.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
POLICY_SHADOW="$CABINET_ROOT/cabinet/scripts/policy-shadow.py"
if [ -x "$POLICY_SHADOW" ]; then
  if [ "${CABINET_AUTHORITY_ENFORCING:-0}" = "1" ] \
     || [ -f "$CABINET_ROOT/instance/config/authority-enforcing" ]; then
    PS_OUT=$(printf '%s' "$HOOK_INPUT" | python3 "$POLICY_SHADOW" 2>/dev/null || true)
    PS_DEC=$(printf '%s' "$PS_OUT" | jq -r '.decision // empty' 2>/dev/null)
    if [ "$PS_DEC" = "block" ]; then
      PS_REASON=$(printf '%s' "$PS_OUT" | jq -r '.reason // "typed policy"' 2>/dev/null)
      echo "TYPED POLICY BLOCK — $PS_REASON (authority-enforcing; revert: rm instance/config/authority-enforcing)" >&2
      exit 2
    fi
    # non-block or wrapper failure → fall through to the bash floor below
  else
    printf '%s' "$HOOK_INPUT" | python3 "$POLICY_SHADOW" >/dev/null 2>/dev/null || true
  fi
fi

# ============================================================
# 0a. OBSERVE-ONLY DOGFOOD CAP (narrow-only, fail-closed)
# ============================================================
# The Captain-side marker is re-read on EVERY tool call, so enabling constrains
# already-running officers immediately. Fresh launchers add three more layers:
# CABINET_ENV=dev (dispatch disabled), no computer-control MCP, and Mac
# Seatbelt source-write denies. Removing the marker never widens an existing
# process that inherited CABINET_OBSERVE_ONLY=1; restart is required.
OBSERVE_MARKER="$CABINET_ROOT/instance/config/observe-only"
OBSERVE_ONLY="${CABINET_OBSERVE_ONLY:-0}"
if [ -e "$OBSERVE_MARKER" ] || [ -L "$OBSERVE_MARKER" ]; then
  if [ -f "$OBSERVE_MARKER" ] && [ ! -L "$OBSERVE_MARKER" ] \
    && [ "$(tr -d '[:space:]' < "$OBSERVE_MARKER" 2>/dev/null)" = active ]; then
    OBSERVE_ONLY=1
  else
    echo "OBSERVE-ONLY FAIL-CLOSED — marker is present but invalid; all officer tools are halted until the Captain repairs it." >&2
    exit 2
  fi
fi
if [ "$OBSERVE_ONLY" = 1 ]; then
  case "$TOOL_NAME" in
    # Native read/inspection surfaces continue through every ordinary gate
    # below (secret/evidence raw-read inversions still apply).
    Read|Grep|Glob|LS|TodoWrite)
      ;;
    # Keep the existing Captain conversation alive. These continue through
    # spending, MCP scope, and every normal Telegram rule below.
    mcp__plugin_telegram_telegram__reply|mcp__plugin_telegram_telegram__react|mcp__cabinet-comms__reply_current|mcp__cabinet-comms__react_current)
      ;;
    # Two germline, argument-closed shell doorways remain: bounded redacted
    # evidence reads and receipt-only trigger ACKs. No interpreter prefix,
    # redirects, or shell composition. Section 5a independently validates the
    # same shapes before the ordinary Bash screens.
    Bash)
      OBSERVE_CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null | tr -s '/')
      # PR#140 finding 5a-3: the doorway allow is SINGLE-LINE only. `grep -qE
      # '^...$'` returns success if ANY line matches, so a multi-line command
      # whose FIRST line is the legit doorway would smuggle every following line
      # (e.g. `evidence-read.sh <trial><NL>cat .../.signing-key`) into an allow.
      # A multi-line command is never a bounded doorway — refuse it BEFORE the
      # shape check. (§5a's evidence-read doorway carries the identical guard.)
      case "$OBSERVE_CMD" in
        *$'\n'*)
          echo "OBSERVE-ONLY BLOCK — multi-line Bash is not a bounded doorway during the soak; issue one bounded command per call." >&2
          exit 2
          ;;
      esac
      if ! printf '%s' "$OBSERVE_CMD" | grep -qE '^(\.?/?cabinet/scripts/evidence-read\.sh[[:space:]]+[A-Za-z0-9][A-Za-z0-9._:-]{0,127}([[:space:]]+[0-9]{1,4})?|\.?/?cabinet/scripts/hooks/observe-ack\.sh[[:space:]]+[0-9]+-[0-9]+([[:space:]]+[0-9]+-[0-9]+){0,49})[[:space:]]*$'; then
        echo "OBSERVE-ONLY BLOCK — Bash is disabled during the 72-hour soak (only bounded evidence-read and receipt ACK doorways remain)." >&2
        exit 2
      fi
      ;;
    *)
      echo "OBSERVE-ONLY BLOCK — tool '$TOOL_NAME' can mutate state, spawn authority, or call an untyped MCP; this soak permits inspection and Captain reply/react only." >&2
      exit 2
      ;;
  esac
fi

# ============================================================
# 0b. OFFICER SECRET-READ INVERSION (native tools)
# ============================================================
# Per-MCP credential projection is meaningless if Read/Grep/Glob/LS can open
# the master dotenv store directly.  Resolve existing path aliases before the
# decision so `/tmp/alias -> product/.env` is blocked too.  Seatbelt repeats
# this at the vnode boundary for subprocesses and recursive search tools.
case "$TOOL_NAME" in
  Read|Grep|Glob|LS)
    SECRET_READ_PATHS=$(printf '%s' "$TOOL_INPUT" \
      | jq -r '[.file_path, .path, .pattern] | .[] // empty' 2>/dev/null || true)
    if [ -n "$SECRET_READ_PATHS" ]; then
      if ! SECRET_READ_PATHS="$SECRET_READ_PATHS" CABINET_ROOT="$CABINET_ROOT" \
          python3 - <<'PY'
import os
import re
import sys
from pathlib import Path

root = Path(os.environ["CABINET_ROOT"]).expanduser().resolve()
home = Path.home().resolve()

shared = None
platform = root / "instance/config/platform.yml"
try:
    import yaml
    data = yaml.safe_load(platform.read_text(encoding="utf-8")) or {}
    value = data.get("shared_env_path")
    if isinstance(value, str) and value.strip():
        shared = Path(os.path.expanduser(value.strip())).resolve(strict=False)
except Exception:
    # Generic .env* denial below still fails closed for the configured file's
    # normal name if the optional YAML parser/config is unavailable.
    pass

master_dirs = {(root / "cabinet/env").resolve(strict=False)}
if shared is not None:
    master_dirs.add(shared.parent)


def within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def blocked(raw: str) -> bool:
    if not raw or "\x00" in raw or "\n" in raw or "\r" in raw:
        return bool(raw)
    raw = os.path.expanduser(raw)
    # A glob that asks for any .env* name is a direct secret enumeration even
    # when its static prefix does not exist yet.
    if re.search(r"(^|/)\.env[^/]*($|/)", raw):
        return True
    has_magic = any(ch in raw for ch in "*?[")
    static = re.split(r"[*?[\]]", raw, maxsplit=1)[0] if has_magic else raw
    candidate = Path(static or ".")
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    if resolved.name.startswith(".env"):
        return True
    if shared is not None and resolved == shared:
        return True
    return any(within(resolved, directory) for directory in master_dirs)


paths = os.environ.get("SECRET_READ_PATHS", "").splitlines()
sys.exit(2 if any(blocked(item) for item in paths) else 0)
PY
      then
        echo "BLOCKED: Officer sessions cannot read master credential sources or .env* files. Credentials arrive only through the role-scoped environment projection." >&2
        exit 2
      fi
    fi
    ;;
esac

# ============================================================
# 1. KILL SWITCH CHECK (fail-closed — CRIT-5 hardening 2026-07-03)
# ============================================================
# Two deliberate properties:
#   (a) NO self-serve deactivation. While active, NOTHING a hooked officer
#       session runs can disarm or bypass the halt. The old substring
#       whitelist for "DEL cabinet:killswitch" let ANY compound command
#       embedding that string exit 0 — skipping not just this check but
#       every downstream gate (spending, prohibited actions, germline).
#       Deactivation is Captain-side only: cabinet/scripts/kill-switch.sh
#       deactivate (terminal) or the dashboard governance toggle — both run
#       outside officer hooks, so removing the whitelist strands nothing.
#   (b) UNREACHABLE control plane halts mutations. redis-cli's exit code
#       distinguishes key-absent (0, empty) from connection failure (non-0).
#       When Redis cannot answer, state-changing tool classes are blocked
#       until it returns; read/observe/comms tools stay allowed so officers
#       report the outage instead of going silently dark. Deliberately
#       stricter than the spending gate's fail-open contract below: a
#       missing budget is ambiguity; a missing safety switch is exposure.
#   (c) BOUNDED probe, same verdict (g-hooks 2026-07-04). `-t 1` caps the
#       redis-cli connect phase at 1s (measured worst case ~2s wall-clock:
#       redis-cli retries the connect once). Without it redis-cli blocks
#       with no timeout, so a WEDGED Redis — up but not answering (seen in the wild
#       as a stuck bgsave, CRIT-4 re-review 2026-07-03) — hung this GET
#       forever and froze EVERY tool call in EVERY officer session, instead
#       of tripping branch (b). The choice on ambiguity is unchanged and
#       deliberate: timeout → non-zero exit → the (b) branch below fail-
#       SAFEs toward BLOCKING mutations while read/comms tools stay up to
#       report the outage. Residual, accepted: -t bounds CONNECT only — a
#       server that accepts the TCP connection then goes silent mid-command can
#       still hang the GET; the observed wedge modes (process down, refused
#       port, un-accepted connect during bgsave stall) all resolve inside the
#       1s window.
#       PORTABILITY (2026-07-05): NOT every redis-cli build honors -t — older
#       ones (CI's redis-tools 7.0.x) error on the flag itself, which would make
#       redis-cli exit non-zero against a perfectly REACHABLE Redis and wrongly
#       trip the fail-closed branch below (it did: the shadow-parity CI eval saw
#       a benign `echo hello` blocked). So a non-zero exit is disambiguated by
#       stderr: a FLAG-parse error means retry once WITHOUT -t (reachable Redis,
#       benign command must not block); a genuine CONNECTION error stays
#       fail-closed. The wedge bound is preserved wherever -t is honored, and a
#       real timeout/outage never matches the flag-error pattern so it still
#       blocks.
KILLSWITCH=$(redis-cli -t 1 -h "$REDIS_HOST" -p "$REDIS_PORT" GET cabinet:killswitch 2>/dev/null)
KS_EXIT=$?
if [ "$KS_EXIT" -ne 0 ]; then
  KS_ERR=$(redis-cli -t 1 -h "$REDIS_HOST" -p "$REDIS_PORT" GET cabinet:killswitch 2>&1 >/dev/null)
  if printf '%s' "$KS_ERR" | grep -qiE "unrecognized|unknown option|bad number of args|invalid option|ambiguous"; then
    KILLSWITCH=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET cabinet:killswitch 2>/dev/null)
    KS_EXIT=$?
  fi
fi
if [ "$KILLSWITCH" = "active" ]; then
  echo "KILL SWITCH ACTIVE — all operations halted by Captain. Deactivation is Captain-side only: kill-switch.sh deactivate, or the dashboard governance toggle." >&2
  exit 2
fi
if [ "$KS_EXIT" -ne 0 ]; then
  case "$TOOL_NAME" in
    # NARROW COMMS ALLOWLIST (default-DENY carve-out): the Captain-facing
    # channel must stay live so an officer can report the outage instead of
    # going silently dark — the reply/react subset of contract b's comms
    # surfaces (IS_TELEGRAM_COMMS, ~line 178). send-to-group rides the Bash
    # arm and remains blocked here, as before — so this door lets an officer
    # respond in an existing chat, not initiate a new outbound message. Kept
    # BEFORE the mcp__* catch-all so first-match wins; anything unrecognized
    # hits the fail-closed default arm at the bottom.
    mcp__plugin_telegram_telegram__reply|mcp__plugin_telegram_telegram__react)
      : # allowed — Captain-comms door stays open during the outage
      ;;
    # READ/OBSERVE ALLOWLIST: these native tools have no state-changing or
    # egress side-effect, so an officer can still inspect the situation while
    # the control plane is unverifiable. Listed EXPLICITLY (not relying on
    # fall-through) so the fail-closed default arm below can refuse everything
    # unrecognized without also denying safe reads.
    Read|Grep|Glob|LS|TodoWrite)
      : # allowed — read/observe only, no side-effect
      ;;
    # DEFAULT-DENY the mutating + egress surface when the control plane can't
    # be verified. Native state-changing tools (as before) PLUS every MCP server
    # and Task subagent-spawn — previously these fell OPEN here, so a mutating
    # MCP (Neon prod-DB writes, Vercel deploy, Make, Monday, brain queue_draft)
    # or a Task spawn RAN during the halt. Native egress (WebFetch/WebSearch)
    # is denied too, so no outbound-network side-effect/exfil channel stays
    # open during the halt (an ACTIVE killswitch already blocks these).
    Bash|Write|Edit|MultiEdit|NotebookEdit|Task|WebFetch|WebSearch|mcp__*)
      echo "KILL SWITCH UNVERIFIABLE — Redis unreachable at $REDIS_HOST:$REDIS_PORT; state-changing tools, MCP servers, subagent spawns, and network-egress tools are halted until the control plane answers (read + Captain-comms tools still allowed)." >&2
      exit 2
      ;;
    # FAIL-CLOSED DEFAULT: anything unrecognized — including an empty TOOL_NAME
    # (unparseable stdin) or a future native mutating tool — is REFUSED rather
    # than allowed while the kill switch is unverifiable.
    *)
      echo "KILL SWITCH UNVERIFIABLE — Redis unreachable at $REDIS_HOST:$REDIS_PORT; tool '$TOOL_NAME' refused (fail-closed default) until the control plane answers (read + Captain-comms tools still allowed)." >&2
      exit 2
      ;;
  esac
fi

# ============================================================
# 2. DAILY SPENDING LIMIT CHECK (FW-002)
# ============================================================
# Caps read from instance/config/platform.yml → spending_limits (this Cabinet
# overrides); framework defaults at framework/defaults/spending-limits.yml.
# Any cap key set to 0 disables enforcement for that scope.
#
# Four contracts (all must hold; regressions break the framework for forkers):
#   (a) Every non-zero exit prints a one-line reason to stderr naming the
#       officer, current spend, the cap, and the override path.
#   (b) Telegram reply/react/send-to-group always bypass the gate (subject
#       to a separate hourly sub-cap) so a blocked officer can still DM
#       "I'm over budget, need a raise" instead of going silently dark.
#   (c) Coordinating officer (cos) gets a 3× multiplier on the per-officer
#       cap because trigger routing is structural overhead other officers
#       don't pay. Configurable via coordinating_officer_multiplier.
#   (d) When config or Redis is unreachable, fail-open with a stderr warn.
#       Silent-brick is never acceptable; ambiguous configuration should
#       surface, not disappear.
#
# Source of truth for realized spend: cabinet:cost:tokens:daily:$DATE HSET,
# written by stop-hook.sh from API usage × model pricing (Fable 5 / Opus / Sonnet). Legacy
# cabinet:cost:daily:$DATE byte-count estimate is no longer consulted;
# CTO's 14:18 2026-04-17 fix corrected the formula.
#
# Background: shared/cabinet-framework-backlog.md FW-002; incident
# 2026-04-17 — CoS bricked for ~15 min when a cap bit silently.

TODAY=$(date -u +%Y-%m-%d)
OFFICER="${OFFICER:-${OFFICER_NAME:-unknown}}"

# -- Telegram whitelist short-circuit (contract b) --------------------
# A narrow set of user-facing tools must reach the Captain even when the
# officer is otherwise capped. Rate-limited so the whitelist cannot be
# looped-abused.
IS_TELEGRAM_COMMS=0
case "$TOOL_NAME" in
  mcp__plugin_telegram_telegram__reply|mcp__plugin_telegram_telegram__react)
    IS_TELEGRAM_COMMS=1
    ;;
  Bash)
    _CMD_CHECK=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null)
    # FW-032: command-start anchor — CMD must START with a recognized
    # invocation form of send-to-group.sh (bash/sh invocation, or direct
    # path exec), optionally prefixed by priv-esc/env VAR=X/timeout.
    # Prior word-boundary match `(^|[[:space:]/])send-to-group\.sh([[:space:]]|$)`
    # allowed `cat /path/send-to-group.sh | head` / `grep send-to-group.sh log`
    # to spuriously set IS_TELEGRAM_COMMS=1, which cascades to _SKIP_MAIN_CAP=1
    # (line 220) — bypassing the per-officer daily spending cap for that call.
    # head -n1 restricts to first line so heredoc bodies cannot trip either.
    # Adversary Finding #1 (Sonnet 2026-04-21 post-EVAL-015): `"?`
    # before/after filename covers double-quoted invocations
    # (`bash "send-to-group.sh"`). Single-quote support skipped because
    # (a) bash single-quoted args don't permit embedded quote escapes and
    # (b) the EVAL-015 extractor parses the anchor out of a single-quoted
    # grep payload and can't tolerate embedded single quotes. Officers
    # using single-quoted paths should switch to double-quoted — documented
    # as FW-036 scope gap.
    echo "$_CMD_CHECK" | head -n1 | grep -qE '^[[:space:]]*(sudo[[:space:]]+|env([[:space:]]+[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+)+[[:space:]]+|timeout[[:space:]]+[0-9]+[smhd]?[[:space:]]+)*(bash[[:space:]]+(-[A-Za-z]+[[:space:]]+)*|sh[[:space:]]+(-[A-Za-z]+[[:space:]]+)*)?([^[:space:]]*/)?"?send-to-group\.sh"?([[:space:]]|$)' && IS_TELEGRAM_COMMS=1
    ;;
esac

# -- Parse caps (fail-open + warn on config trouble, contract d) -------
# SECURITY (Finding B, C17 audit 2026-07-12): the enforcement cache used to be
# a FIXED path in world-writable /tmp trusted on an mtime-only freshness check,
# so any SAME-UID officer Bash could plant a poisoned cache (e.g.
# daily_per_officer_usd 999999) that the gate then trusted — spend cap
# bypassed. Ownership/permission checks CANNOT close this: officers run as the
# SAME uid as the hook (single-user Mac — that is exactly why germline uses
# schg, not perms), so an officer-owned 0600 cache with a fresh mtime passes
# every -O/perm test. The only same-uid-safe fix without root is to NEVER trust
# a persisted cache: recompute from the source yaml on EVERY call into an
# UNPREDICTABLE per-invocation mktemp file that no officer can pre-plant (random
# name, O_EXCL, 0600) or race (written then read in-process, then deleted). No
# persistent trusted state remains to poison.
# RESIDUAL (SEPARATE finding — CG row, NOT closed here): platform.yml and
# framework/defaults/spending-limits.yml are themselves officer-writable (not
# schg, not in the hook's GERM_PATH_RE), so a determined officer can still edit
# the SOURCE cap. This patch closes the /tmp CACHE vector only; source integrity
# for the spend/peers/contexts configs is a distinct exposure.
# (cabinet/mcp-scope.yml IS schg + GERM_PATH_RE-guarded, so section 9 below is
# airtight end-to-end.)
PLATFORM_YML="$CABINET_ROOT/instance/config/platform.yml"
FRAMEWORK_DEFAULTS_YML="$CABINET_ROOT/framework/defaults/spending-limits.yml"
SPENDING_CONFIG_CACHE=$(mktemp "${TMPDIR:-/tmp}/cabinet-spending-limits.XXXXXX" 2>/dev/null)

if [ -n "$SPENDING_CONFIG_CACHE" ]; then
  if ! python3 - "$PLATFORM_YML" "$FRAMEWORK_DEFAULTS_YML" "$SPENDING_CONFIG_CACHE" <<'PY' 2>/dev/null
import re, sys
instance, default, dst = sys.argv[1], sys.argv[2], sys.argv[3]

def parse(path):
    out = {}
    if not path:
        return out
    try:
        text = open(path).read()
    except FileNotFoundError:
        return out
    in_block = False
    for raw in text.splitlines():
        # Normalize trailing whitespace including CR from CRLF files — without
        # this, "true\r" survives into shell and breaks the `true` check.
        line = raw.rstrip('\r\t ')
        if re.match(r'^spending_limits:\s*$', line):
            in_block = True
            continue
        if in_block:
            # End of block: any top-level key (no leading whitespace) that isn't blank/comment
            if line and not line.startswith((' ', '\t')) and not line.lstrip().startswith('#'):
                break
            m = re.match(r'^\s+([a-z_]+):\s*([^\s#][^#]*?)?\s*(#.*)?$', line)
            if m:
                k = m.group(1)
                v = (m.group(2) or '').strip().rstrip('\r')
                # Strip surrounding quotes
                if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                    v = v[1:-1]
                out[k] = v
    return out

cfg = parse(default)           # framework defaults first
cfg.update(parse(instance))    # instance overrides wins

with open(dst, 'w') as f:
    for k, v in cfg.items():
        f.write(f"{k}\t{v}\n")
PY
  then
    # Parser crashed (missing python3, broken yaml, whatever). Fail-open with
    # warn — silent-brick is never acceptable (FW-002 contract d); _cfg_get's
    # hardcoded fallbacks (75/300) apply when the cache is empty/unreadable.
    echo "pre-tool-use: WARN spending-limits parser failed, using hardcoded framework defaults (\$75/officer, \$300/cabinet)" >&2
  fi
else
  # mktemp failed (astronomically rare). Fail-open + warn to the hardcoded
  # framework defaults rather than brick the officer (FW-002 contract d).
  echo "pre-tool-use: WARN spending-limits temp cache unavailable, using hardcoded framework defaults (\$75/officer, \$300/cabinet)" >&2
fi

# Read each key with a sane hardcoded fallback (for the case where parsing
# failed entirely and the cache is empty). Fallback values match framework
# defaults so a broken cache still gets forker-safe behavior.
_cfg_get() {
  local key="$1" fallback="$2"
  local v
  v=$(awk -F'\t' -v k="$key" '$1==k{print $2; exit}' "$SPENDING_CONFIG_CACHE" 2>/dev/null)
  [ -z "$v" ] && v="$fallback"
  echo "$v"
}

PER_OFF_CAP_USD=$(_cfg_get daily_per_officer_usd 75)
CABINET_CAP_USD=$(_cfg_get daily_cabinet_wide_usd 300)
COS_MULT=$(_cfg_get coordinating_officer_multiplier 3.0)
TG_WHITELIST_ON=$(_cfg_get telegram_whitelist_enabled true)
TG_HOURLY_CAP=$(_cfg_get telegram_whitelist_hourly_cap 10)

# Finding B: enforcement values are captured in shell vars — remove the
# per-invocation temp cache so no trusted-content file survives this call.
[ -n "$SPENDING_CONFIG_CACHE" ] && rm -f "$SPENDING_CONFIG_CACHE"

# Coerce non-numeric values to 0 (unlimited) rather than crash. If caps are
# garbage, fail-open + warn.
case "$PER_OFF_CAP_USD" in *[!0-9.]*|'') PER_OFF_CAP_USD=0 ;; esac
case "$CABINET_CAP_USD" in *[!0-9.]*|'') CABINET_CAP_USD=0 ;; esac
case "$COS_MULT" in *[!0-9.]*|'') COS_MULT=1 ;; esac
case "$TG_HOURLY_CAP" in *[!0-9]*|'') TG_HOURLY_CAP=10 ;; esac

# Convert cap USD → cap micro-dollars for integer arithmetic with Redis data.
# awk handles decimals. Result is integer micro-dollars.
PER_OFF_CAP_MICRO=$(awk -v v="$PER_OFF_CAP_USD" 'BEGIN{printf "%.0f", v*1000000}')
CABINET_CAP_MICRO=$(awk -v v="$CABINET_CAP_USD" 'BEGIN{printf "%.0f", v*1000000}')

# CoS carve-out (contract c)
EFFECTIVE_PER_OFF_CAP_MICRO=$PER_OFF_CAP_MICRO
if [ "$OFFICER" = "cos" ] && [ "$PER_OFF_CAP_MICRO" -gt 0 ] 2>/dev/null; then
  EFFECTIVE_PER_OFF_CAP_MICRO=$(awk -v c="$PER_OFF_CAP_MICRO" -v m="$COS_MULT" 'BEGIN{printf "%.0f", c*m}')
fi

# -- If this call is a Telegram comms whitelist tool, apply hourly sub-cap
# only (contract b) and exit 0 without checking the main cap.
if [ "$IS_TELEGRAM_COMMS" = "1" ] && [ "$TG_WHITELIST_ON" = "true" ]; then
  # When OFFICER is empty or unknown, don't enforce the hourly sub-cap —
  # an unknown-officer session sharing one global bucket would false-block
  # Telegram across every misconfigured session at once, recreating the
  # exact "silent-dark" failure FW-002 is meant to prevent. Fail-open + warn.
  if [ -z "$OFFICER" ] || [ "$OFFICER" = "unknown" ]; then
    echo "pre-tool-use: WARN telegram whitelist skipping hourly sub-cap (OFFICER env unset/unknown)" >&2
    _SKIP_MAIN_CAP=1
  else
    _HOUR_BUCKET=$(date -u +%Y%m%d%H)
    _TG_KEY="cabinet:tg-whitelist:${OFFICER}:${_HOUR_BUCKET}"
    _TG_COUNT=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INCR "$_TG_KEY" 2>/dev/null)
    # Set TTL on first hit; subsequent INCRs keep the existing TTL.
    [ "$_TG_COUNT" = "1" ] && redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" EXPIRE "$_TG_KEY" 3900 > /dev/null 2>&1
    if [ -n "$_TG_COUNT" ] && [ "$_TG_COUNT" -gt "$TG_HOURLY_CAP" ] 2>/dev/null; then
      echo "pre-tool-use: BLOCKED — officer=$OFFICER telegram whitelist hourly sub-cap exceeded ($_TG_COUNT > $TG_HOURLY_CAP). Override: instance/config/platform.yml → spending_limits.telegram_whitelist_hourly_cap" >&2
      exit 2
    fi
    # Whitelisted and under sub-cap: skip main-cap enforcement and proceed.
    # Fall through to other sections (kill switch already passed, prohibited
    # actions still checked below, etc.).
    _SKIP_MAIN_CAP=1
  fi
fi

# -- Main cap enforcement (contract a: explicit stderr on every block) --
if [ "${_SKIP_MAIN_CAP:-0}" != "1" ]; then

  # Per-officer cap.
  #
  # FW-072 / S3 (Pool Phase 1A): cost field shape is now either legacy
  # `<officer>_cost_micro` (pre-pool) OR per-project `<officer>_<project>_cost_micro`
  # (pool mode, post-Phase-1B start-officer.sh --project). Sum both patterns
  # by HKEYS-scanning fields that start with `<officer>_` and end with
  # `_cost_micro`. One field in pre-pool, N fields in pool mode.
  if [ "$EFFECTIVE_PER_OFF_CAP_MICRO" -gt 0 ] 2>/dev/null; then
    OFFICER_COST_MICRO=0
    while IFS= read -r fld; do
      [ -z "$fld" ] && continue
      case "$fld" in
        "${OFFICER}_cost_micro"|"${OFFICER}_"*"_cost_micro")
          v=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "cabinet:cost:tokens:daily:$TODAY" "$fld" 2>/dev/null)
          v=${v:-0}
          case "$v" in *[!0-9]*|'') v=0 ;; esac
          OFFICER_COST_MICRO=$((OFFICER_COST_MICRO + v))
          ;;
      esac
    done < <(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HKEYS "cabinet:cost:tokens:daily:$TODAY" 2>/dev/null)
    case "$OFFICER_COST_MICRO" in *[!0-9]*|'') OFFICER_COST_MICRO=0 ;; esac
    if [ "$OFFICER_COST_MICRO" -ge "$EFFECTIVE_PER_OFF_CAP_MICRO" ] 2>/dev/null; then
      OFFICER_COST_USD=$(awk -v v="$OFFICER_COST_MICRO" 'BEGIN{printf "%.2f", v/1000000}')
      EFFECTIVE_CAP_USD=$(awk -v v="$EFFECTIVE_PER_OFF_CAP_MICRO" 'BEGIN{printf "%.2f", v/1000000}')
      _NOTE=""
      [ "$OFFICER" = "cos" ] && [ "$(awk -v m="$COS_MULT" 'BEGIN{print (m>1)}')" = "1" ] && _NOTE=" (includes CoS ${COS_MULT}× coordinator multiplier)"
      echo "pre-tool-use: BLOCKED — officer=$OFFICER today=\$$OFFICER_COST_USD cap=\$${EFFECTIVE_CAP_USD}${_NOTE}. Override: instance/config/platform.yml → spending_limits.daily_per_officer_usd (0 = unlimited). Telegram tools still allowed to reach Captain." >&2
      exit 2
    fi
  fi

  # Cabinet-wide cap
  if [ "$CABINET_CAP_MICRO" -gt 0 ] 2>/dev/null; then
    CABINET_COST_MICRO=0
    while IFS= read -r fld; do
      [ -z "$fld" ] && continue
      case "$fld" in *_cost_micro)
        v=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "cabinet:cost:tokens:daily:$TODAY" "$fld" 2>/dev/null)
        v=${v:-0}
        case "$v" in *[!0-9]*|'') v=0 ;; esac
        CABINET_COST_MICRO=$((CABINET_COST_MICRO + v))
        ;;
      esac
    done < <(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HKEYS "cabinet:cost:tokens:daily:$TODAY" 2>/dev/null)
    if [ "$CABINET_COST_MICRO" -ge "$CABINET_CAP_MICRO" ] 2>/dev/null; then
      CABINET_COST_USD=$(awk -v v="$CABINET_COST_MICRO" 'BEGIN{printf "%.2f", v/1000000}')
      CABINET_CAP_USD_PRINT=$(awk -v v="$CABINET_CAP_MICRO" 'BEGIN{printf "%.2f", v/1000000}')
      echo "pre-tool-use: BLOCKED — cabinet-wide today=\$$CABINET_COST_USD cap=\$$CABINET_CAP_USD_PRINT. Override: instance/config/platform.yml → spending_limits.daily_cabinet_wide_usd (0 = unlimited). Telegram tools still allowed to reach Captain." >&2
      exit 2
    fi
  fi
fi
unset _SKIP_MAIN_CAP

# ============================================================
# 3. PROHIBITED ACTIONS
# ============================================================
if [ "$TOOL_NAME" = "Bash" ]; then
  CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null)

  # 3a. Literal multi-word / case-sensitive prohibitions — substring match is
  # safe here: these phrases are unlikely to appear inside filenames or grep
  # patterns and are case-sensitive (uppercase SQL verbs, "vercel deploy").
  case "$CMD" in
    *"vercel deploy"*|*"vercel --prod"*)
      echo "BLOCKED: Production deployment requires Captain approval" >&2
      exit 2
      ;;
    *"DROP TABLE"*|*"DROP DATABASE"*|*"TRUNCATE"*|*"DELETE FROM"*)
      echo "BLOCKED: Destructive database operation requires Captain approval" >&2
      exit 2
      ;;
  esac

  # 3b. Word-boundary prohibitions — target must appear in COMMAND POSITION,
  # not as substring inside filenames, grep patterns, or quoted echo strings.
  # FW-042: prior substring match (*"docker"*|*"sudo"*|...) silently blocked
  # legitimate `grep docker file`, `ls docker-compose.yml`, `cat shutdown.md`.
  #
  # Approach (v3.3):
  #  (a) CMD_STRIPPED: remove all `'...'`, `"..."`, `$'...'` spans from CMD, then
  #      strip heredoc bodies (`<<WORD\n...\nWORD`). Eliminates quote/heredoc
  #      mention FPs (`grep -E 'sudo|docker'`, `cat <<EOF\ndocker\nEOF`). Real
  #      direct invocations (`sudo ls`, `{ sudo; }`) survive and are caught by
  #      CMD_PREAMBLE below.
  #  (b) CMD_PREAMBLE on STRIPPED: boundary-char anchor, optional shell reserved
  #      word (then/do/else/elif), optional inline VAR=VAL, then keyword.
  #  (c) SHELL_C_PREAMBLE / SHELL_HERE_PREAMBLE on RAW: detect `bash -c 'sudo'`,
  #      `sh <<< 'docker'` etc. across 10 POSIX shells. Explicit shell-binary
  #      prefix prevents literal `bash -c` inside echo strings from FPing.
  #  (d) WRAPPER_PREAMBLE on RAW: exec|eval|nohup|time|trap|coproc[[ NAME]].
  #      coproc NAME accepts `[A-Za-z_][A-Za-z0-9_]*` (bash identifier). Optional
  #      flags with flag-arg absorber (`[/A-Z][^[:space:]]*` — uppercase/path
  #      values only, avoids swallowing lowercase keyword as value).
  #  (e) ENV_PREAMBLE on RAW (v3.3): dedicated because env's arg surface is too
  #      permissive for WRAPPER's flag-only absorber — env takes arbitrary
  #      lowercase args (`-u foo`, `--unset=PATH`, SQ/DQ VAR=VAL). Generic-token
  #      absorber `[^[:space:]|><;&()}]+` stops at shell metachars so `env |
  #      grep sudo` and `env > file` don't FP.
  #  (f) COMMAND_PREAMBLE on RAW: only `command -p` is exec'ing (`command -v` is
  #      introspection — print type). Dedicated so `command -v sudo` PASSes.
  #  (g) BRACE_AFTER_COMMA: close `{,kw}` empty-first-element brace bypass.
  #      Paired with `\}` inside keyword match + POST_SUFFIX_BRACE (omits `}`)
  #      so `{,docker}-compose.yml` (filename brace prefix) doesn't FP.
  #      Symmetric `{kw,}` caught via POST_SUFFIX's `,` in terminator set.
  #
  # v3.3 closes (from v3.2): heredoc-body strip (E22 FP); POST_SUFFIX comma
  # `{kw,}`; BRACE_AFTER_COMMA `{,kw}`; env/coproc wrappers; A5 filename-brace
  # FP (`ls {,docker}-compose.yml`); env lowercase flag-args (C1/C9);
  # env long-flags C3 + env SQ/DQ VAR=VAL C5; coproc lowercase identifier D2.
  #
  # v3.4 post-adversary (shell-parse + regex dual-pass, 2026-04-23):
  #   H1 — eval 'env sudo ls' bypassed: quoted-arg wipe before WRAPPER keyword.
  #        Fix: EVAL_WRAPPER_PREAMBLE re-enters quoted eval arg. Extended to
  #        env|nohup|exec|time|trap|coproc (broader probe confirmed leak class).
  #   H2 — env \sudo ls bypassed: absorber ate `\sudo` as one token. Fix:
  #        ENV_PREAMBLE absorber excludes `\`; grep branches add `\\?` before kw.
  #   H3 — command -p -- sudo ls bypassed: no `--` absorber. Fix: COMMAND_PREAMBLE
  #        now absorbs `(--[[:space:]]+)?` after optional `-p`.
  #   H4 — {rm,} -rf / bypassed: rm block only caught `{,rm}` form. Fix: symmetric
  #        `(^|anchor)\{rm,+\}[[:space:]]+-rf` branch added. sudo/shutdown blocks
  #        already catch via POST_SUFFIX comma terminator.
  #   BUG 2 — bash -xc/-vc/-ec/-lc/-ic/-xec/--login -c/--norc -c bypassed:
  #        SHELL_C flag absorber ate `-xc` as single flag, swallowing c-marker.
  #        Fix: absorber excludes ANY short flag containing `c`, adds `--[A-Za-z]`
  #        long-flag absorber. c-marker = single-dash cluster with at least one
  #        `c` anywhere (covers all 9 variants).
  #   PARITY — SHELL_HERE (`bash --login <<<`) same single-dash-only absorber
  #        limitation. Fix: added `--[A-Za-z]` long-flag to SHELL_HERE_PREAMBLE
  #        absorber (no c-marker since `<<<` itself is the trigger).
  #
  # v3.5 post-adversary (shell-parse + regex dual-pass #2, 2026-04-23):
  #   BUG-1 (regex HIGH) — `bash -C -c 'sudo'` bypassed: SHELL_C absorber range
  #        `[ABD-Z]` excluded uppercase-C (range letter-math), so `-C -c` not
  #        recognized as absorber+c-marker. Fix: widen to `[A-Zabd-z0-9]` (A-Z
  #        full, lowercase excludes `c` only).
  #   BUG-2 (regex HIGH) — `eval "env 'sudo' ls"`, `eval "nohup \"sudo\" ls"`:
  #        quoted keyword inside wrapper arg. LEAD_PREFIX `['"]?\\*` couldn't
  #        eat nested escape-quote `\"` or interleaved `'\`. Fix: LEAD_PREFIX
  #        widened to `(\\|['"])*` — any order/count of backslash+quote chars.
  #        Also POST_SUFFIX_Q adds `\` for trailing `\"` after keyword.
  #   BUG-3 (regex MED) — `\eval 'sudo'`, `\nohup sudo`, `\env sudo`: leading
  #        backslash before wrapper name. Shell treats `\eval` as `eval` (no-op
  #        escape on non-special char). Fix: all preambles prefix with `\\*`.
  #   BUG-4 (regex MED) — `eval 'env 2>/dev/null sudo'`, `eval 'nohup 2>&1 reboot'`:
  #        redirect inside eval-quoted arg. EVAL_WRAPPER absorber excluded `><&`,
  #        couldn't eat `2>/dev/null` or `2>&1`. Fix: remove `><&` from absorber
  #        exclusion — allow redirect/background chars. Same applied to ENV.
  #   H1 (shell-parse HIGH) — `bash <<EOF\nsudo\nEOF`: heredoc body untouched by
  #        strip (preserved for CMD_STRIPPED), but body content fed to shell is
  #        direct invocation path. Fix: SHELL_HEREDOC_PREAMBLE detects
  #        `bash/sh/... <<WORD`, then perl multiline scan of body for keyword.
  #   H2 (shell-parse HIGH) — `eval 'eval sudo ls'`: double-eval nesting; outer
  #        EVAL_WRAPPER inner wrapper list omitted `eval` itself. Fix: added
  #        `eval` to inner wrapper alternation.
  #   H3 (shell-parse HIGH) — `eval 'bash -c sudo ls'`: eval of shell command.
  #        Inner wrapper list omitted shell binaries. Fix: added
  #        `bash|sh|dash|zsh|ksh` to inner wrapper alternation.
  #   BUG-5 (regex HIGH, v3.5 round 2) — `eval "exec 'rm' -rf /"`: quoted binary
  #        name splits `rm -rf /` token sequence. Fix: rm EVAL_WRAPPER branch
  #        uses `[[:space:]'"\\]+` interstitial class (accepts quote/backslash
  #        between rm→-rf→/).
  #
  # v3.6 post-adversary (shell-parse + regex dual-pass #3, 2026-04-24):
  #   B4 (HIGH) — `bash <<<sudo` (bare, no quote) bypassed: SHELL_HERE_PREAMBLE
  #        required quote after `<<<`. Fix: `['"]` → `['"]?` (quote optional).
  #   B5 (HIGH) — `/usr/bin/sudo`, `/sbin/reboot`, `/bin/rm -rf /`: full-path
  #        invocation. All 7 keywords affected. Fix: PATH_PREFIX variable
  #        `((/[^[:space:]/]+)+/)?` applied as optional prefix in all 24 grep
  #        branches (3 kw groups × 8 paths). CMD_PREAMBLE anchor excludes bare
  #        space so arg-position `echo /usr/bin/sudo` doesn't FP.
  #   B6 (HIGH) — `bash --rcfile FILE -c 'sudo'`, `--init-file FILE`: long-flag
  #        takes argument. Old SHELL_C/SHELL_HERE/SHELL_HEREDOC absorbers only
  #        matched `--[a-z]+` without arg. Fix: optional value absorber
  #        `([[:space:]]+[^-][^[:space:]]*)?` after each long flag.
  #   B7/B8/B9 (HIGH) — `rm -fr /`, `rm -f -r /`, `rm --recursive --force /`:
  #        flag-order variants bypassed literal `-rf` match. Fix: RM_FLEX pattern
  #        requires rm + at least one recursive-indicator flag (r/R in short
  #        cluster, or --recursive long) + trailing `/`. Catches all 8 flag
  #        permutations while rejecting non-recursive `rm file.txt`.
  #   B10 (HIGH) — `{,sudo,}` trailing comma: BRACE_AFTER_COMMA required `\}`
  #        immediately after kw. Fix: `(kw)\}` → `(kw),*\}` (allow trailing
  #        commas before close brace).
  #   BYPASS 2 (HIGH) — `eval '(sudo)'`, `eval '{ sudo; }'`, `eval '! sudo ls'`:
  #        subshell/brace-group/negation operators inside eval's quoted arg.
  #        EVAL_WRAPPER inner wrapper list missed `(`, `{`, `!`. Fix: added
  #        `[({!]` to wrapper alternation + post-wrapper `[[:space:]]+` →
  #        `[[:space:]]*` (subshell-open doesn't require following space).
  #   BYPASS 4 (MED) — `mksh -c 'sudo'`, `ash`, `fish`, `csh`, `tcsh`, `busybox`:
  #        shell binary enumeration gap. Fix: extended SHELL_C/SHELL_HERE/
  #        SHELL_HEREDOC/EVAL_WRAPPER shell list to 11 shells.
  #
  # Accepted gaps (uncommon, all tracked):
  #   - redirect prefix: `>/dev/null sudo`, `2>&1 sudo`
  #   - xargs wrapper:   `echo x | xargs sudo` (dataflow-decoupled, FW-040 Phase B)
  #   - timeout wrapper: `timeout 10 sudo`
  #   - process subst:   `<(sudo ...)` / `source <(echo sudo ...)`
  #   - bare `$'reboot'` (ANSI-C as command) — stripped, no match
  #   - variable expansion: `X=sudo; $X ls` (FW-040 Phase B)
  #   - stdin-read shells: `bash <<<"cmd"` outer (string-input form caught; body
  #     path is FW-040 Phase B class)
  #   - `{,sudo}}` double-brace-close: bash PARSE-ERROR (not executable);
  #     empirically verified via `bash -c '{,echo}} MAGIC_OK'` → `}: command not
  #     found`. Classified SCOPE_GAP, not BUG; regex-adv confirmed non-exploitable.

  # v3.7.2 BSQ fix: normalize backslash-escaped quotes (`\"` → `"`, `\'` → `'`)
  # in the input string. Defeats backslash-escape quoted-splice class bypass
  # (COO Pass-1 on 716fb96): `echo hi;\"sudo\" ls`, `(\"sudo\" ls)`, etc. all
  # bypassed HAS_SPLICE because the `\` between boundary and quote hides the
  # quote-adjacent-letter structural signal that HAS_SPLICE detects. Bash
  # treats `\"` in unquoted context as literal `"`, so normalizing to `"`
  # preserves bash exec semantics for attack inputs (adjacent-quote concat
  # still fuses the token at runtime) while restoring the detectable splice
  # signal for our regex. Applied once; CMD_STRIPPED, CMD_UNQUOTED, CMD_MASKED
  # all derive from CMD_NORM so no surface is missed.
  CMD_NORM=$(printf '%s' "$CMD" | sed -e 's/\\"/"/g' -e "s/\\\\'/'/g")

  # (a) Strip data-context quotes. sed -e runs each independently to survive
  #     malformed quotes. Order: \$'...' then '...' then "...". Double-quote
  #     strip preserves spans containing `$` or backtick (code-substitution
  #     context) so `"$(sudo)"` and `"$(`sudo`)"` survive for RAW scans.
  # v3.3: perl pipe strips `<<WORD\n...\nWORD` heredoc bodies — their content is
  # always data, never a direct invocation. Fixes E22 FP (`cat <<EOF\ndocker...\nEOF`).
  CMD_STRIPPED=$(printf '%s' "$CMD_NORM" \
    | sed -e "s/\\\$'[^']*'//g" -e "s/'[^']*'//g" -e 's/"[^"$`]*"//g' \
    | perl -0777 -pe 's/<<([A-Za-z_]\w*)\n.*?\n\1(?=\n|\z)//gs')

  # v3.7 post-adversary Finding 2 fix: CMD_UNQUOTED preserves the CONTENT of quoted
  # spans (unwraps them) instead of wiping them. Defeats quoted-token splice like
  # `"sudo" ls`, `s"udo" ls`, `"su""do" ls`, `s'udo' ls` — adjacent-quote concat is
  # a POSIX word-splicing feature; bash emits the fused literal. Scanned against
  # STRICT_KW_START (boundary-only, no VAR= absorber) so we don't FP on
  # `echo "sudo ls"` (kw preceded by space, not by operator boundary).
  CMD_UNQUOTED=$(printf '%s' "$CMD_NORM" \
    | sed -e "s/\\\$'\\([^']*\\)'/\\1/g" -e "s/'\\([^']*\\)'/\\1/g" -e 's/"\([^"$`]*\)"/\1/g' \
    | perl -0777 -pe 's/<<([A-Za-z_]\w*)\n.*?\n\1(?=\n|\z)//gs')

  # Unquoted-context preamble (runs on STRIPPED). Anchor includes backtick so
  # `` `sudo` `` and `$(`sudo`)` are caught post-strip.
  # v3.7 post-adversary Finding 1 fix: absorber now accepts leading/interleaved
  # redirects (`2>&1`, `>/dev/null`, `<&0`) at command-position. Adversary proved
  # `2>&1 sudo ls`, `echo hi; 2>&1 sudo ls`, `echo hi && 2>&1 reboot` bypassed
  # CMD_PREAMBLE because `2>&1` sits between boundary+space and kw but wasn't
  # consumed by the VAR= absorber. New absorber alt: `[0-9]*[<>]+[&0-9-]*[^[:space:]]*`
  # covers `N>FILE`, `N<FILE`, `N>&M`, `>FILE`, `<FILE`, `>&-`, `&>FILE` forms.
  CMD_PREAMBLE='(^|[;&|({)}`!][[:space:]]*|(^|[;&|({)}`!])[[:space:]]*(then|do|else|elif|if|while|until|for|case|select|function)[[:space:]]+)[[:space:]]*(([0-9]*[<>]+[&0-9-]*[^[:space:]]*|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)[[:space:]]+)*'

  # v3.7 post-adversary: strict command-start anchor for CMD_UNQUOTED scans.
  # Only operator boundaries — no VAR= absorber, no reserved-word prefix, no
  # redirect absorber. Reason: CMD_UNQUOTED already rewrote quote-content in
  # place; kw at strict cmd-start after unwrap means adversary quoted-splice,
  # not legitimate arg. Space NOT in leading class — prevents FP on
  # `echo "sudo ls"` (unwrap → `echo sudo ls`, space-preceded kw).
  STRICT_KW_START='(^|[;&|({)}`!]|&&|\|\|)[[:space:]]*'

  # HAS_SPLICE gate: STRICT_KW_START scans CMD_UNQUOTED, but UNQUOTED also
  # exposes kw inside DATA-position quotes like `grep '|docker|' file` (the
  # `|` inside the regex string matches STRICT_KW_START's `|` boundary).
  # HAS_SPLICE detects the adversary splice signal specifically: a
  # command-position token whose body crosses a quote boundary — `"sudo"`,
  # `s"udo"`, `"s"udo`. Such tokens always appear at boundary-then-quote-or-
  # letter-then-quote positions. Data-position quotes (preceded by space,
  # never by operator) don't match this pattern. STRICT_KW_START runs only
  # if HAS_SPLICE=1 — else we stay on CMD_STRIPPED's existing gates.
  #
  # v3.7.1 post-review fix (BUG-A): HAS_SPLICE runs on CMD_MASKED (quoted
  # interiors replaced with literal `x`) rather than raw CMD. Raw CMD exposes
  # boundary chars (|, &, ;) inside quoted strings, falsely triggering the
  # splice signal on `grep -E "foo|docker" file`. CMD_MASKED keeps the outer
  # quotes so letter-adjacent-quote / quote-adjacent-letter patterns at true
  # command position still match, but interior pipes/ampersands become `x`
  # and stop false-triggering the boundary class.
  CMD_MASKED=$(printf '%s' "$CMD_NORM" \
    | sed -e "s/\\\$'[^']*'/\$'x'/g" -e "s/'[^']*'/'x'/g" -e 's/"[^"$`]*"/"x"/g')
  HAS_SPLICE=0
  if echo "$CMD_MASKED" | grep -qE "(^|[;&|({)}\`!]|&&|\|\|)[[:space:]]*([A-Za-z_]+['\"\`]|['\"\`][A-Za-z_])"; then
    HAS_SPLICE=1
  fi

  # Shell-wrapper quoted-code paths (runs on RAW). Shell-binary anchor prevents
  # literal `-c` substrings in echo args from FPing.
  # v3.4 BUG 2 fix: compound-flag bypass (bash -xc 'sudo', -lc, -xec, --login -c).
  # Old absorber `(-[A-Za-z][A-Za-z0-9-]*)*` ate `-xc` as one flag, swallowing the
  # c-marker. New: short-flag absorber excludes ANY cluster containing `c`, long
  # flag absorber added for `--login`/`--norc`. c-marker = single-dash cluster
  # with at least one `c` anywhere (covers `-c`, `-xc`, `-cx`, `-xec`, `-lc`).
  # v3.4 edge: `\\*` before wrapper name catches `\bash -c '\sudo'` escape forms.
  SHELL_C_PREAMBLE='(^|[;&|({)}`!]|[[:space:]])[[:space:]]*\\*(bash|sh|dash|zsh|ksh|mksh|ash|fish|csh|tcsh|busybox|su|runuser|script)[[:space:]]+((-[A-Zabd-z0-9][A-Zabd-z0-9-]*([[:space:]]+[^-][^[:space:]]*)?|--[A-Za-z][A-Za-z0-9-]*(=[^[:space:]]*)?([[:space:]]+[^-][^[:space:]]*)?)[[:space:]]+)*-[A-Za-z0-9]*c[A-Za-z0-9]*[[:space:]]*\$?['\''"]?[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=([^[:space:]'\''"]|'\''[^'\'']*'\''|"[^"]*"|\$'\''[^'\'']*'\'')*[[:space:]]+)*'
  # v3.4 parity fix: `bash --login <<<'sudo ls'` bypassed old single-dash-only
  # absorber. Added long-flag absorber for `<<<` path. No c-marker needed — `<<<`
  # itself triggers execution.
  SHELL_HERE_PREAMBLE='(^|[;&|({)}`!]|[[:space:]])[[:space:]]*\\*(bash|sh|dash|zsh|ksh|mksh|ash|fish|csh|tcsh|busybox|su|runuser|script)[[:space:]]+((-[A-Za-z][A-Za-z0-9-]*([[:space:]]+[^-][^[:space:]]*)?|--[A-Za-z][A-Za-z0-9-]*(=[^[:space:]]*)?([[:space:]]+[^-][^[:space:]]*)?)[[:space:]]+)*<<<[[:space:]]*\$?['\''"]?[[:space:]]*'

  # Wrapper keywords that ALWAYS execute (exec|eval|nohup|time|trap). Optional
  # flags between wrapper and keyword. Optional quote opener for `trap "reboot"`.
  # v3.7 timeout/duration fix: wrappers like `timeout 30s sudo ls`, `timeout -k 5s 30s
  # sudo ls` have positional non-flag args between wrapper and target keyword. Added
  # `[0-9]+[A-Za-z]*` absorber alt for duration-style tokens (30s, 5m, 1h, 100).
  # v3.7 long-flag + positional fix: chroot /, taskset 0x1, numactl --physcpubind=0.
  # Added `--[A-Za-z][A-Za-z0-9-]*(=[^[:space:]]*)?` for long flags and broad
  # `[^-][^[:space:]]*` for bare positional args. Grep backtracking ensures bare-pos
  # doesn't greedy-eat target kw (eval sudo ls → iter 0 match wins).
  WRAPPER_PREAMBLE='(^|[;&|({)}`!]|[[:space:]])[[:space:]]*\\*(exec|eval|nohup|time|trap|coproc([[:space:]]+[A-Za-z_][A-Za-z0-9_]*)?|setsid|stdbuf|nice|ionice|chrt|taskset|unbuffer|cgexec|doas|pkexec|gosu|su-exec|strace|ltrace|gdb|valgrind|watch|chroot|timeout|numactl)[[:space:]]+((-[A-Za-z][A-Za-z0-9-]*([[:space:]]+[^-][^[:space:]]*)?|--[A-Za-z][A-Za-z0-9-]*(=[^[:space:]]*)?([[:space:]]+[^-][^[:space:]]*)?|[0-9]*[<>]+[&0-9-]*[^[:space:]]*|[0-9]+[A-Za-z]*|[^-][^[:space:]]*)[[:space:]]+)*\$?['\''"]?[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=([^[:space:]'\''"]|'\''[^'\'']*'\''|"[^"]*"|\$'\''[^'\'']*'\'')*[[:space:]]+)*'

  # v3.3 env-dedicated preamble. env takes flag-args (-u VAR, -C DIR, -S STR),
  # long flags (--unset=PATH), quoted VAR=VAL, and the cmd-to-run. Generic-token
  # absorber stops at shell metachars (|, >, <, ;, &, (, ), }) so that
  # `env | grep sudo` and `env > file` don't FP.
  # v3.4 H2 fix: `env \sudo ls` bypassed because absorber ate `\sudo` as one
  # token. `\sudo` = `sudo` in bash (backslash quotes next char, no-op on `s`).
  # Absorber token now excludes `\` so `\keyword` forms surface to the keyword
  # match. Each token can optionally start with `\`. Keyword match uses `\\?`
  # prefix (added in grep branches, not here) to consume the leading backslash.
  ENV_PREAMBLE='(^|[;&|({)}`!]|[[:space:]])[[:space:]]*\\*env[[:space:]]+(\\*[^[:space:]|;()}\\]+[[:space:]]+)*'

  # `command` wrapper: only `-p` flag executes; `-v`/`-V` are introspection
  # (resolve path, print type). Dedicated regex allows only `-p` to avoid
  # FPing `command -v sudo` (standard "does sudo exist?" query).
  # v3.4 H3 fix: `command -p -- sudo ls` bypassed because old regex had no `--`
  # absorber. `--` is POSIX end-of-options; `command -p -- sudo` still executes
  # sudo. Added `(--[[:space:]]+)?` after `(-p[[:space:]]+)?` — also covers
  # `command -- sudo` (no -p, still exec).
  COMMAND_PREAMBLE='(^|[;&|({)}`!]|[[:space:]])[[:space:]]*\\*command[[:space:]]+(-p[[:space:]]+)?(--[[:space:]]+)?\$?['\''"]?[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=([^[:space:]'\''"]|'\''[^'\'']*'\''|"[^"]*"|\$'\''[^'\'']*'\'')*[[:space:]]+)*'

  # v3.4 H1 fix: nested eval+wrapper class. `eval 'env sudo ls'`, `eval 'nohup
  # sudo'`, `eval 'exec sudo'`, `eval 'time sudo'` all bypass both CMD_STRIPPED
  # (quoted content wiped) and WRAPPER_PREAMBLE (keyword slot sees the nested
  # wrapper, not the target). Dedicated regex re-enters the eval-quoted arg to
  # match wrapper + target keyword. Quote optional so `eval env sudo ls`
  # (unquoted) also caught.
  EVAL_WRAPPER_PREAMBLE='(^|[;&|({)}`!]|[[:space:]])[[:space:]]*\\*eval[[:space:]]+(-[A-Za-z][A-Za-z0-9-]*[[:space:]]+)*\$?['\''"]?[[:space:]]*\\*(eval|bash|sh|dash|zsh|ksh|mksh|ash|fish|csh|tcsh|busybox|env|nohup|exec|time|trap|coproc([[:space:]]+[A-Za-z_][A-Za-z0-9_]*)?|command|builtin|setsid|stdbuf|nice|ionice|chrt|taskset|unbuffer|cgexec|doas|pkexec|gosu|su-exec|strace|ltrace|gdb|valgrind|watch|chroot|timeout|numactl|su|runuser|script|[({!])[[:space:]]*(\\*[^[:space:]|;()}\\'\''"]+[[:space:]]+)*'

  # v3.7 eval-compound fix: `eval 'echo ok; sudo ls'` — eval's quoted arg has a
  # compound statement with boundary (`;`/`&`/`|`) separating a benign first kw
  # from the target kw. Pattern re-enters the eval arg, consumes up to a boundary
  # char, then matches kw at that compound-position.
  EVAL_COMPOUND_PREAMBLE='(^|[;&|({)}`!]|[[:space:]])[[:space:]]*\\*eval[[:space:]]+\$?['\''"][^'\''"]*[;&|]+[[:space:]]*'

  # v3.7 env-S fix: `env -S'sudo ls'` — env's -S flag takes a split-string arg
  # that env re-parses internally. Attacker glues `-S` to quoted kw with no
  # space, hiding kw from token absorber. Branch matches env, optional prior
  # flags/VAR= assignments, literal -S, optional space, quote, LEAD_PREFIX, kw.
  ENV_S_PREAMBLE='(^|[;&|({)}`!]|[[:space:]])[[:space:]]*\\*env[[:space:]]+((-[A-Za-z][A-Za-z0-9-]*([[:space:]]+[^-][^[:space:]]*)?|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*)[[:space:]]+)*-S[[:space:]]*['\''"][[:space:]]*'

  # Post-suffix: unquoted (stripped) + quoted (raw). Both include backtick
  # closing for command-substitution spans.
  POST_SUFFIX='([[:space:];&|)},<>`]|$)'
  POST_SUFFIX_Q='([[:space:];&|)},<>'\''"`\\]|$)'
  # v3.3 A5 fix: POST_SUFFIX_BRACE omits `}` so that `{,docker}-compose.yml`
  # (filename brace prefix) doesn't FP. Paired with `\}` inside the keyword
  # match so BRACE branches require the closing brace immediately after kw.
  POST_SUFFIX_BRACE='([[:space:];&|)<>,`'\''"]|$)'

  # v3.3: BRACE_AFTER_COMMA closes `{,kw}` brace-expansion bypass — empty first
  # element followed by keyword (e.g. `{,sudo}` runs sudo). POST_SUFFIX adds `,`
  # to close `{kw,}` symmetric form.
  # v3.7 nested-brace fix: `{,{,sudo}}` bypassed single-level BRACE_AFTER_COMMA.
  # Widened to `(\{,+)+` for 1+ empty-leading brace levels. Each branch's closing
  # pattern also widened from `,*\}` to `(,*\})+` for balanced depth.
  BRACE_AFTER_COMMA='(^|[;&|({)},`!]|[[:space:]])(\{,+)+'

  # v3.5 H1 fix: unquoted heredoc bypass — `bash <<EOF\nsudo ls\nEOF` escaped
  # all prior blocks because (a) CMD_STRIPPED strips heredoc body (correct FP
  # avoidance for `cat <<EOF\ndocker\nEOF`), (b) no preamble ran on RAW body,
  # (c) `bash` is not a prohibited keyword. SHELL_HEREDOC_PREAMBLE detects
  # `<shell> <flags>* <<WORD` leader. Then perl multiline scan inspects body
  # between delimiter lines for target kws (including `rm -rf`). Only unquoted
  # `<<WORD` (starts with `[A-Za-z_]`) triggers — quoted `<<'EOF'`, `<<"EOF"`,
  # dash-strip `<<-EOF` all correctly leave body un-stripped, caught by
  # CMD_PREAMBLE on CMD_STRIPPED.
  SHELL_HEREDOC_PREAMBLE='(^|[;&|({)}`!]|[[:space:]])[[:space:]]*\\*(bash|sh|dash|zsh|ksh|mksh|ash|fish|csh|tcsh|busybox|su|runuser|script)[[:space:]]+((-[A-Zabd-z0-9][A-Zabd-z0-9-]*([[:space:]]+[^-][^[:space:]]*)?|--[A-Za-z][A-Za-z0-9-]*(=[^[:space:]]*)?([[:space:]]+[^-][^[:space:]]*)?)[[:space:]]+)*<<[[:space:]]*[A-Za-z_]'
  if echo "$CMD" | grep -qE "$SHELL_HEREDOC_PREAMBLE"; then
    if echo "$CMD" | perl -0777 -ne '
      exit 0 if /<<[A-Za-z_]\w*\n(.*?)\n[A-Za-z_]\w*(?=\n|\z)/s &&
                $1 =~ /(?:^|[;&|({)}`!]|\s)\s*(?:sudo|docker|systemctl|shutdown|reboot|halt|rm\s+-rf)\b/m;
      exit 1;
    '; then
      echo "BLOCKED: Heredoc to shell binary contains prohibited command" >&2
      exit 2
    fi
  fi

  # v3.5: LEAD_PREFIX — 0+ chars, each either a backslash or a quote (' or ").
  # Handles three bypass classes:
  #   BUG-2: `eval "env 'sudo' ls"` — quoted keyword inside eval arg. Token
  #          absorbers exclude `'`/`"`, so a quoted keyword escapes the absorber
  #          but arrives at keyword-match position prefixed with a quote that
  #          the literal keyword cannot consume.
  #   BUG-2 nested: `eval "nohup \"sudo\" ls"` — escape+quote interleave.
  #          Alternation eats any mix of `\`, `'`, `"`.
  #   H2 extended: `env \\sudo ls` — multiple backslashes before kw.
  # POST_SUFFIX_Q also extended with `\` for trailing escape (e.g. `sudo\" ls`).
  # Applied as prefix to keyword match in every RAW grep branch. Safe (won't FP
  # on bare kw — outer preamble already anchored in command position).
  LEAD_PREFIX='(\\|['\''"])*'

  # v3.6: PATH_PREFIX — optional absolute-path prefix before keyword (e.g.
  # `/usr/bin/sudo`, `/sbin/reboot`). Applied as optional prefix in all branches
  # so `/usr/bin/sudo ls` blocks same as `sudo ls`. Leading `/` required (no
  # relative paths — those would FP on `./grep sudo` etc). Intermediate
  # segments disallow whitespace and `/`. Trailing `/` connects to keyword.
  PATH_PREFIX='((~[A-Za-z0-9_+-]*)?/+([^[:space:]/]+/+)*)?'

  # v3.6: RM_FLEX — flexible rm-destructive pattern. Catches v3.5's literal
  # `-rf` PLUS flag-order variants (-fr, split -f -r, long --recursive/--force).
  # Logic: rm, optional interstitial flags, mandatory flag containing r or R
  # (or --recursive), optional trailing flags, slash target. At least one r-flag
  # required — plain `rm /path` (non-recursive) doesn't match. Ends at `/`;
  # per-branch suffix controls what follows (strict end for STRIPPED, lax quote
  # for RAW).
  RM_FLEX='rm[[:space:]]+((-[[:alnum:]]+|--[[:alnum:]-]*(=[^[:space:]]*)?)[[:space:]]+)*(-[[:alnum:]]*[rR][[:alnum:]]*|--recursive)([[:space:]]+(-[[:alnum:]]+|--[[:alnum:]-]*(=[^[:space:]]*)?))*[[:space:]]+/'
  # v3.7 H11 fix: `rm -rf "/"` — CMD_STRIPPED wipes the quoted "/" entirely so
  # the slash vanishes before RM_FLEX scans. RM_FLEX_QS targets CMD (raw) and
  # tolerates quote chars wrapping the slash (`"/", '/', `/`).
  # v3.7.1 post-review fix (BUG-B): terminal constraint `\**['"`]*([space];&|)]|$)`
  # so pattern matches only when `/` is FOLLOWED by optional `*`, optional closing
  # quote(s), then terminator/end. Prevents FP on legitimate `rm -rf '/tmp/build'`
  # where the slash begins a non-root path. Still matches `rm -rf "/"`, `rm -rf '/'`,
  # `rm -rf "/*"`, `rm -rf '/' && echo done`.
  RM_FLEX_QS='rm[[:space:]]+((-[[:alnum:]]+|--[[:alnum:]-]*(=[^[:space:]]*)?)[[:space:]]+)*(-[[:alnum:]]*[rR][[:alnum:]]*|--recursive)([[:space:]]+(-[[:alnum:]]+|--[[:alnum:]-]*(=[^[:space:]]*)?))*[[:space:]]+['\''"`]+/\**['\''"`]*([[:space:];&|)]|$)'

  # Destructive filesystem: rm with recursive flag targeting / (+ flag-order variants)
  if echo "$CMD_STRIPPED" | grep -qE "${CMD_PREAMBLE}${PATH_PREFIX}${RM_FLEX}(\*|[[:space:]]|$)" \
     || echo "$CMD" | grep -qE "${SHELL_C_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}${RM_FLEX}" \
     || echo "$CMD" | grep -qE "${SHELL_HERE_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}${RM_FLEX}" \
     || echo "$CMD" | grep -qE "${WRAPPER_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}${RM_FLEX}" \
     || echo "$CMD" | grep -qE "${COMMAND_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}${RM_FLEX}" \
     || echo "$CMD" | grep -qE "${BRACE_AFTER_COMMA}${LEAD_PREFIX}${PATH_PREFIX}rm(,*\})+[[:space:]]+-rf[[:space:]]+/" \
     || echo "$CMD" | grep -qE "(^|[;&|({)}\`!]|[[:space:]])\{${LEAD_PREFIX}${PATH_PREFIX}rm,+\}[[:space:]]+-rf[[:space:]]+/" \
     || echo "$CMD" | grep -qE "(^|[;&|({)}\`!]|[[:space:]])\{${LEAD_PREFIX}${PATH_PREFIX}rm,[^}]+\}[[:space:]]+-rf[[:space:]]+/" \
     || echo "$CMD" | grep -qE "${ENV_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}${RM_FLEX}" \
     || echo "$CMD" | grep -qE "${EVAL_WRAPPER_PREAMBLE}${LEAD_PREFIX}rm[[:space:]'\''\"\\\\]+-rf[[:space:]'\''\"\\\\]+/" \
     || echo "$CMD" | grep -qE "${EVAL_COMPOUND_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}${RM_FLEX}" \
     || echo "$CMD" | grep -qE "${ENV_S_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}${RM_FLEX}" \
     || echo "$CMD" | grep -qE "${CMD_PREAMBLE}${PATH_PREFIX}${RM_FLEX_QS}" \
     || { [ "$HAS_SPLICE" = "1" ] && echo "$CMD_UNQUOTED" | grep -qE "${STRICT_KW_START}${PATH_PREFIX}${RM_FLEX}(\*|[[:space:]]|$)"; } \
     || { [ "$HAS_SPLICE" = "1" ] && echo "$CMD_UNQUOTED" | grep -qE "${STRICT_KW_START}${PATH_PREFIX}${RM_FLEX_QS}"; }; then
    echo "BLOCKED: Destructive filesystem operation" >&2
    exit 2
  fi

  # System-level commands: sudo, docker, systemctl
  if echo "$CMD_STRIPPED" | grep -qE "${CMD_PREAMBLE}${PATH_PREFIX}(sudo|docker|systemctl)${POST_SUFFIX}" \
     || echo "$CMD" | grep -qE "${SHELL_C_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(sudo|docker|systemctl)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${SHELL_HERE_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(sudo|docker|systemctl)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${WRAPPER_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(sudo|docker|systemctl)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${COMMAND_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(sudo|docker|systemctl)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${BRACE_AFTER_COMMA}${LEAD_PREFIX}${PATH_PREFIX}(sudo|docker|systemctl)(,*\})+${POST_SUFFIX_BRACE}" \
     || echo "$CMD" | grep -qE "(^|[;&|({)}\`!]|[[:space:]])\{${LEAD_PREFIX}${PATH_PREFIX}(sudo|docker|systemctl),[^}]+\}${POST_SUFFIX_BRACE}" \
     || echo "$CMD" | grep -qE "${ENV_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(sudo|docker|systemctl)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${EVAL_WRAPPER_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(sudo|docker|systemctl)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${EVAL_COMPOUND_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(sudo|docker|systemctl)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${ENV_S_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(sudo|docker|systemctl)${POST_SUFFIX_Q}" \
     || { [ "$HAS_SPLICE" = "1" ] && echo "$CMD_UNQUOTED" | grep -qE "${STRICT_KW_START}${PATH_PREFIX}(sudo|docker|systemctl)${POST_SUFFIX}"; }; then
    echo "BLOCKED: System-level command not permitted" >&2
    exit 2
  fi

  # System control: shutdown, reboot, halt
  if echo "$CMD_STRIPPED" | grep -qE "${CMD_PREAMBLE}${PATH_PREFIX}(shutdown|reboot|halt)${POST_SUFFIX}" \
     || echo "$CMD" | grep -qE "${SHELL_C_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(shutdown|reboot|halt)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${SHELL_HERE_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(shutdown|reboot|halt)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${WRAPPER_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(shutdown|reboot|halt)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${COMMAND_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(shutdown|reboot|halt)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${BRACE_AFTER_COMMA}${LEAD_PREFIX}${PATH_PREFIX}(shutdown|reboot|halt)(,*\})+${POST_SUFFIX_BRACE}" \
     || echo "$CMD" | grep -qE "(^|[;&|({)}\`!]|[[:space:]])\{${LEAD_PREFIX}${PATH_PREFIX}(shutdown|reboot|halt),[^}]+\}${POST_SUFFIX_BRACE}" \
     || echo "$CMD" | grep -qE "${ENV_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(shutdown|reboot|halt)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${EVAL_WRAPPER_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(shutdown|reboot|halt)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${EVAL_COMPOUND_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(shutdown|reboot|halt)${POST_SUFFIX_Q}" \
     || echo "$CMD" | grep -qE "${ENV_S_PREAMBLE}${LEAD_PREFIX}${PATH_PREFIX}(shutdown|reboot|halt)${POST_SUFFIX_Q}" \
     || { [ "$HAS_SPLICE" = "1" ] && echo "$CMD_UNQUOTED" | grep -qE "${STRICT_KW_START}${PATH_PREFIX}(shutdown|reboot|halt)${POST_SUFFIX}"; }; then
    echo "BLOCKED: System control command not permitted" >&2
    exit 2
  fi
fi

# ============================================================
# 4. CODEBASE OWNERSHIP — Only CTO may modify product code
# ============================================================
if [ "$OFFICER" != "cto" ] && [ "$OFFICER" != "unknown" ]; then
  if [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; then
    FILE_PATH=$(echo "$TOOL_INPUT" | jq -r '.file_path // .path // empty' 2>/dev/null)
    case "$FILE_PATH" in
      /workspace/[a-z0-9][a-z0-9-]*/*)
        echo "BLOCKED: Only CTO can modify the active project codebase. Write a spec to shared/interfaces/product-specs/ and notify CTO." >&2
        exit 2
        ;;
    esac
  fi
  if [ "$TOOL_NAME" = "Bash" ]; then
    CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null)
    case "$CMD" in
      *"git commit"*|*"git push"*|*"git add"*)
        case "$CMD" in
          *"/workspace/"*)
            echo "BLOCKED: Only CTO can commit/push to the active project codebase. Write a spec and notify CTO." >&2
            exit 2
            ;;
        esac
        ;;
    esac
    # Block Bash write patterns whose TARGET is /workspace/<slug>/ (FW-034 fix).
    # FW-076 (2026-04-29): generalized from /workspace/product/ literal to
    # /workspace/[a-z0-9][a-z0-9-]*/ per-project pattern for pool-mode (FW-073).
    # Slug class matches start-officer.sh guard exactly; preserves product/ (legacy).
    # Pre-FW-034 used two independent substring checks (mentions-product AND has-write-op),
    # which false-blocked `cat /workspace/<slug>/x | tee /tmp/y` (read source is project,
    # write target is /tmp). Regex requires project path in the write-operator's TARGET
    # position: redirect stdout target, sed -i/--in-place file arg, tee trailing file,
    # cp/mv/rsync last arg (dest) OR -t/--target-directory=, patch filename arg.
    # Hotfix 2026-04-22 (COO + Sonnet empirical adversary on b6c7cf2): narrowed sed
    # flag anchor to -i/--in-place only (pre-hotfix `-[-a-zA-Z]+` over-matched
    # -n/-E/-e/-r — broke officer read-analysis workflows); sed `-i` suffix now
    # consumes non-space to catch `-i.bak` (Sonnet adversary BUG-1); added Patterns
    # 5a/5b for `cp|mv -t DEST` bundle (incl -rfvt/-at/-bt — Sonnet adversary
    # BUG-2/3/4) and `cp|mv|rsync --target-directory=DEST`; rsync intentionally
    # excluded from -t bundle (rsync -t means --times not target-directory — would
    # false-block `rsync -rt SOURCE DEST` source-reads from /workspace/product/);
    # added `>|` to Pattern 1 (bash force-overwrite under noclobber).
    # Hotfix 3 2026-04-22 (COO 3rd-round + Sonnet post-fix adversary on 37888dc):
    # sed script-body class `[^<]*` → `[^&]*` — sed scripts legitimately contain
    # `<` (HTML/XML bodies, e.g. `sed -i 's/<h1>/<h2>/' file.html`), `|` (valid
    # delimiter, e.g. `sed -i 's|a|b|' f`), AND `;` (intra-script command
    # separator, e.g. `sed -i 's/a/b/;s/c/d/' f`). Attempted hotfix-3a `[^|&;]`
    # over-rejected `|`; hotfix-3b `[^&;]` over-rejected `;`. Final class `[^&]*`
    # allows all three; `&` alone still flags `&&`/`|| →` command-chain
    # boundaries.
    # Hotfix 4 2026-04-23 (COO 4th-round + Sonnet adversary pass 2 & 3 on
    # hotfix-4 interim forms): `[^&]*` over-rejects sed replacement-`&`
    # (standard sed feature meaning "the matched text"): `s/foo/&bar/`,
    # `/&/d`, `s/^/& /`, and sed's `&&` = "matched text twice"
    # (`s/a/&&/`). Progression:
    #   - Interim (COO) `([^&]|&[^&])*`: fixed single-& but missed
    #     `&&`-inside-quotes (Sonnet pass 2 HIGH).
    #   - Interim 2 (quote-balanced) `([^&'"]|'[^']*'|"[^"]*"|&[^&])*`:
    #     fixed `&&`-in-quotes but broke A2 (escape-out `'\''` idiom)
    #     and A6 (quoted product path `'/workspace/product/x'`) — both
    #     HIGH (Sonnet pass 3).
    # Final class: `([^&'"]|'[^']*'|"[^"]*"|'|"|&[^&])*` — balanced-span
    # alternatives absorb `&&`/`;`/`|` inside quotes; solo `'`/`"`
    # fallbacks absorb orphan quotes (escape-out idioms, unmatched
    # trailing quotes); `&[^&]` still consumes sed-literal `&`; outside
    # quotes, none of the alternatives accept `&&` so the match still
    # halts at shell chain boundaries. Plus `/workspace/<slug>/` anchor
    # now accepts optional `["']?` opening quote to catch quoted path
    # forms (`sed -i ... '/workspace/product/x'`). Verified: `sed -i
    # 's/x/y/' /tmp/f && cat /workspace/product/log` still correctly
    # PASSES (the `&&` halts the unquoted class before the project
    # anchor can be reached). The downstream `[[:space:]]+/workspace/<slug>/` anchor keeps
    # the project-path write requirement (so false-pos from `sed -i /tmp/f; echo
    # /workspace/product/` is a known pre-existing greedy-match FP, not a
    # delta-3 regression). Pattern 5a `-[a-zA-Z]*t[[:space:]]+` → `[[:space:]]*`
    # — GNU cp/mv accept `-t/DIR` no-space form (bundle-flag + attached-arg),
    # bypass pre-hotfix. Known gaps tracked as FW-040 Phase B: quoted dest with
    # internal space, variable expansion, `install` + other write tools (awk/dd/
    # touch/mkdir/truncate/sqlite3), python3 -c, node -e, sed `/pat/w PATH`
    # internal-write directive (no -i needed), Pattern 4 last-arg-is-dest
    # assumption violated by `cp -t DEST SOURCE...` ordering.
    # Hotfix 5 2026-04-24 (FW-040 HIGH — CTO Sonnet crew agent, COO-adversary-rated
    # HIGH severity): Added Pattern 8 (perl -i inplace-edit) + Pattern 9 (tar
    # extract/create touching /workspace/product/).
    # Hotfix 6 2026-04-24 (FW-040 HIGH — COO Pass-1 adversary on d752992):
    # - Pattern 9b: added `--file[=[:space:]]+` long-form alt; closes 3 HIGH GNU
    #   tar `--file=` bypasses (--file=, --file<space>, -c --file=).
    # - Pattern 8: prefix char class iterated — Pass-1 `[^[:space:]]*` → `[a-z]*`
    #   (fixes -I/usr/local/lib FP), Pass-2 Sonnet `[a-z]*` → `[^[:space:]Ii]*`
    #   (restores -Ti/-Wi/-0777i coverage regressed by lowercase-only).
    # Known scope gaps deferred: (a) `tar -tf|-xf /workspace/product/archive.tar`
    # read-ops from product archive file (fail-closed FP, low sev); (b) perl
    # `$^I` special-var inplace inside `-e` body (flag-level regex can't see
    # body) — filed as FW-051 orthogonal scope-gap.
    #
    # Pattern 8 (perl -i): `-[^[:space:]Ii]*i[^[:space:]]*` matches any flag token
    # containing `i` where the prefix bundle excludes `I` (the include-path flag)
    # and `i` itself (since `i` appears at end of prefix). Covers -i, -i.bak, -pi,
    # -ip, -ipe, -ni, -i0, -Ti (taint+inplace), -Wi (warnings+inplace), -0777i
    # (record-sep+inplace), -li, -wi, -si, -ai, -lpi etc. The two optional middle
    # groups absorb additional flags between -i and the product path. Long-form
    # `--in-place[=suffix]` alternative covers the GNU long alias.
    # Hotfix-6 Pass-1 (COO 2026-04-24): narrowed prefix class from `[^[:space:]]*`
    # to `[a-z]*` to fix `-I/usr/local/lib` include-path FP (where greedy absorber
    # caught `i` in `lib`). Pass-2 (Sonnet 2026-04-24): `[a-z]*` regressed uppercase
    # (`-Ti`, `-Wi`) and digit-prefixed (`-0777i`) bundles; re-widened to
    # `[^[:space:]Ii]*` — excludes ONLY the FP-causing `I` char, not the whole
    # uppercase+digit alphabet. Discriminator: requires `-<bundle>i`-containing
    # flag token AND `/workspace/product/` as a subsequent argument. Allows:
    # `perl -pe ...` (no -i, stdout-only), `perl -ne '...' /workspace/product/x`
    # (no -i, read-only), `perl -pi /tmp/f` (inplace but non-product target),
    # `perl -I/usr/local/lib -pe ...` (include-path, not inplace),
    # `perl -Iinclude_dir -pe ...` (relative include path).
    # Accepted FPs:
    #   - `echo "perl -i /workspace/product/x"` (data-position quoted body) —
    #     fail-closed per FW-045 FP-1; workaround: omit product path from echo
    #     body or write to /tmp first.
    #   - `perl -e 'BEGIN{$^I=""}...' /workspace/product/f` — scope gap:
    #     inplace mode enabled via `$^I` special var inside `-e` body, no `-i`
    #     flag at shell level. Inherent limitation of flag-level regex; would
    #     require `-e` body inspection (same class as FW-040 Phase B gap #3:
    #     "Scripting inline-writes via python3 -c / node -e / ruby -e").
    #     Flat regex alternative (match `\$\^I` textually) is cat-and-mouse
    #     (attacker variants: `${^I}`, dynamic var name assignment). Left as
    #     FW-040 Phase B scope-gap. Low operational risk (obscure idiom, Edit/
    #     Write tools still gated for non-CTO officers via Section 3a).
    #
    # Pattern 9 (tar): Two sub-alternatives:
    #   9a: tar with -C[space|no-space] or --directory[=space] followed by
    #       /workspace/product/ (covers: -C, -C/ no-space bundle, --directory space,
    #       --directory=). GNU tar accepts -C/PATH with no space — Adversary Pass-1
    #       found -C[[:space:]]+ missed -C/PATH; fixed to -C[[:space:]]* to catch
    #       both forms. Catches all extract+create forms.
    #   9b: tar with `-[flags]f[space]|--file[=|space]` + /workspace/product/
    #       (archive FILE written to product path, e.g.
    #       `tar -cf /workspace/product/archive.tar /some/src` OR
    #       `tar --file=/workspace/product/archive.tar -c /some/src`).
    #       Hotfix-6 (COO 2026-04-24): added `--file[=[:space:]]+` long-form
    #       alt — parity with Pattern 9a's `--directory=` alt. Pre-hotfix, GNU
    #       `tar --file=/workspace/product/x.tar` bypassed short-form-only gate.
    # Allows: `tar -xf archive.tar` (no -C, no product -f), `tar -xf a.tar -C /tmp/`
    # (non-product -C), `tar -tf archive.tar` (list-only, no -C). Accepted FPs:
    # `tar -czf /tmp/x.tar -C /workspace/product/ .` (-C as SOURCE context for -c
    # where archive is written to /tmp, product is source content) — fail-closed;
    # officer workaround: `cd /workspace/product && tar -czf /tmp/x.tar .`.
    # `tar -xf /workspace/product/archive.tar` and `tar -tf /workspace/product/x.tar`
    # (read-op from product archive file) — fail-closed by Pattern 9b; workaround:
    # copy archive to /tmp first. Low severity (read-ops, not writes); tracked as
    # FW-040 scope gap for future read-op vs write-op differentiation.
    # Blocks `tar -cf /workspace/product/archive.tar /some/src` (archive written
    # TO product path — correct BLOCK). Pattern 9b gates on archive -f path position.
    if echo "$CMD" | grep -qE '(>[>|]?[[:space:]]*["'\'']?/workspace/[a-z0-9][a-z0-9-]*/|sed[[:space:]]+(([^&'\''"]|'\''[^'\'']*'\''|"[^"]*"|'\''|"|&[^&])*[[:space:]])?(-[a-zA-Z]*i[^[:space:]]*|--in-place(=[^[:space:]]*)?)([[:space:]]([^&'\''"]|'\''[^'\'']*'\''|"[^"]*"|'\''|"|&[^&])*)?[[:space:]]+["'\'']?/workspace/[a-z0-9][a-z0-9-]*/|tee[[:space:]]+(-[-a-zA-Z]+[[:space:]]+)*([^;|&<]+[[:space:]]+)?["'\'']?/workspace/[a-z0-9][a-z0-9-]*/|(cp|mv|rsync)[[:space:]]+(-[-a-zA-Z]+[[:space:]]+)*[^;|&]+[[:space:]]+["'\'']?/workspace/[a-z0-9][a-z0-9-]*/[^[:space:];|&"'\'']*["'\'']?([[:space:]]*($|[;&|<>])|[[:space:]]+[0-9]+[<>])|(cp|mv)[[:space:]]+([^;|&]*[[:space:]])?-[a-zA-Z]*t[[:space:]]*["'\'']?/workspace/[a-z0-9][a-z0-9-]*/|(cp|mv|rsync)[[:space:]]+([^;|&]*[[:space:]])?--target-directory(=|[[:space:]]+)["'\'']?/workspace/[a-z0-9][a-z0-9-]*/|patch[[:space:]]+([^;|&<]+[[:space:]]+)?["'\'']?/workspace/[a-z0-9][a-z0-9-]*/|perl[[:space:]]+([^;&|]*[[:space:]])?(-[^[:space:]Ii]*i[^[:space:]]*|--in-place(=[^[:space:]]*)?)(([[:space:]]([^;&|]*[[:space:]])?)|([[:space:]]([^;&|]*[[:space:]])?)?)[[:space:]]*["'\'']?/workspace/[a-z0-9][a-z0-9-]*/|tar[[:space:]]+([^;&|]*[[:space:]]+)?(-[a-zA-Z]*C[a-zA-Z]*[[:space:]]*|-[a-zA-Z]*f[a-zA-Z]*C[a-zA-Z]*[[:space:]]+[^;&|[:space:]]+[[:space:]]+|--directory[=[:space:]]+)["'\'']?/workspace/[a-z0-9][a-z0-9-]*(/|[[:space:];&|<>"'\'']|$)|tar[[:space:]]+([^;&|]*[[:space:]]+)?(-[^[:space:]]*f[[:space:]]*|--file[=[:space:]]+)["'\'']?/workspace/[a-z0-9][a-z0-9-]*(/|[[:space:];&|<>"'\'']|$))'; then
      echo "BLOCKED: Only CTO can modify the active project codebase via Bash. Write a spec and notify CTO." >&2
      exit 2
    fi
  fi
fi

# ============================================================
# 5. GERMLINE PROTECTION (constitution/ retired 2026-07-07 — CG-15/R104:
#    the runtime constitution assembles from framework/constitution-base.md
#    + the active preset addendum; the old dir + its write-protect arm are gone)
# ============================================================
if [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; then
  FILE_PATH=$(echo "$TOOL_INPUT" | jq -r '.file_path // .path // empty' 2>/dev/null)
  # Collapse repeated slashes before matching (scoped to this section).
  # Without this, exact-file germline patterns (suffix-anchored, e.g.
  # *"cabinet/mcp-scope.yml") are bypassable via `lib//mcp-scope.yml`
  # path forms. tr -s '/' is purely collapsing — every pre-existing arm
  # below matches the same or strictly safer on the normalized path
  # (e.g. tier2 double-slash false-blocks self-writes today; collapsed
  # paths resolve correctly).
  FILE_PATH=$(printf '%s' "$FILE_PATH" | tr -s '/')
  # Finding C (2026-07-12): also resolve `..` LEXICALLY before matching, so
  # `shared/interfaces/reviews/../captain-vetoes.yml` (or any parent-dir hop)
  # cannot reach the real germline file behind the suffix-anchored patterns
  # below (a native Write there truncates — e.g. an officer erasing its own
  # veto row). os.path.normpath is pure-lexical (no realpath — the target may
  # not exist): collapses a/b/../c -> a/c AND preserves leading `..` (does NOT
  # over-block legit relative paths that don't escape into germline). Falls
  # back to the tr-only value if python3 is unavailable — fail toward today's
  # behavior, never crash the gate. KEEP IN LOCKSTEP with §5b/§5c.
  FILE_PATH=$(printf '%s' "$FILE_PATH" | python3 -c 'import os,sys; sys.stdout.write(os.path.normpath(sys.stdin.read()))' 2>/dev/null || printf '%s' "$FILE_PATH")
  # G1 (2026-07-14): Finding C collapsed lexical `..` but left the gate
  # SYMLINK-BLIND — a symlinked DIRECTORY COMPONENT (e.g. an officer's own
  # instance/memory/tier2/<self>/si -> shared/interfaces) still resolves to the
  # real germline file, so a native Write to
  # instance/memory/tier2/<self>/si/captain-vetoes.yml truncates the real
  # (schg-EXEMPT) veto registry = self-un-demotion. Resolve symlinks in the
  # directory components with os.path.realpath BEFORE the membership test below:
  # realpath follows symlinks in existing components and leaves a non-existent
  # trailing basename lexical (so Write-to-a-new-file still resolves its parent
  # dir). The germline arm is matched FIRST and is suffix-anchored, so a symlink
  # that lands on a germline file now matches and BLOCKS, while a genuine
  # own-tier2 write (real dirs, no symlink) resolves to itself and still reaches
  # the tier2 arm. FAIL-CLOSED: if realpath yields nothing (python3 crash/absent)
  # force a sentinel that matches the germline arm so the write is REFUSED, never
  # passed through symlink-blind. KEEP IN LOCKSTEP with §5b/§5c (a symlinked
  # Bash-write target is the named §5b variable-indirection-class residual).
  FILE_PATH=$(printf '%s' "$FILE_PATH" | python3 -c 'import os,sys; p=sys.stdin.read(); sys.stdout.write(os.path.realpath(p) if p else "")' 2>/dev/null || printf '')
  if [ -z "$FILE_PATH" ]; then
    FILE_PATH="/__germline_unresolved__/shared/interfaces/captain-vetoes.yml"
  fi
  case "$FILE_PATH" in
    # GERMLINE SET (2026-06-10) — the files that JUDGE officer/loop
    # behavior: golden evals, the typed policy engine + its policies, MCP
    # scope, capability routing, the brain-bridge and courses-of-action
    # rules, and the autonomy gradient. Read-only for EVERY officer and
    # loop (including cos): no loop may edit its own judge. Officers/loops
    # PROPOSE germline changes (improvement proposal / founder-action);
    # only the Captain applies them. Directory entries are contains-matched
    # (trailing slash keeps e.g. memory/golden-evals-notes.md editable);
    # single files are suffix-anchored so siblings like
    # instance/config/autonomy.yml.example stay editable.
    # ACTING-PLANE JUDGES added 2026-07-04 (build-checkpoint hard-blocker
    # #2, safety-perimeter CRITICAL: captain-vetoes.yml was empirically
    # Edit→ALLOWED — a forgeable veto registry). The captain-veto registry
    # (the sharpest demotion tooth), the act-first surface allowlist, and
    # the frontdoor/acting executor+gate modules JUDGE or CARRY unattended
    # act-first behavior; an officer edit to any of them forges its own
    # demotion or widens its own act surface. KEEP IN LOCKSTEP with
    # GERM_PATH_RE in section 5b below — a path added here without 5b
    # reopens the bash-redirect write bypass for it.
    # ENFORCER SELF-PROTECTION added 2026-07-04 (red-team + independent review:
    # the perimeter did NOT protect its own files — `Write`/`echo >` over
    # pre-tool-use.sh, .claude/settings.json, or policy-shadow.py exited 0, so
    # one injected officer write neutered the whole gate). The hooks dir,
    # settings wiring, typed-engine, kill switch, and germline-lock.sh are now
    # germline. DEFENSE-IN-DEPTH only: a path hook over a Turing-complete shell
    # cannot be a complete boundary (cd-relative, var-indirection, script-file
    # interpreters, patch/archive all evade it) — the COMPLETE boundary is the
    # filesystem lock (cabinet/scripts/germline-lock.sh, `chflags schg`) which
    # makes the officer uid physically unable to write every static germline
    # file. Keep both.
    # SOVEREIGN-POSTURE KERNEL added 2026-07-05 (amendment
    # docs/proposals/germline-amendment-sovereign-posture-2026-07-05.md): the
    # posture/grants/needs kernel, the gate-apply lane, the Captain-locked
    # attestation configs (posture.yml + standing-grants.yml — hook-covered
    # BEFORE the deployment creates them), the D8 instance policy-layer dir,
    # and the needs-ledger data plane (O_APPEND via needs.py ONLY — direct
    # officer writes forge needs). The single source of this set is
    # framework/policies/immutable-core.yml; the lockstep meta-test
    # (framework/tests/test_germline_lockstep_consistency.py) diffs this arm
    # against it — extend BOTH or the suite fails.
    # ROOT-EXECUTED APPLY LANE added 2026-07-05 (SOV-9a): gate-apply.sh runs
    # as root (sudo apply + the DARK com.cabinet.gate-apply daemon), the
    # plist's ProgramArguments run as root on load, and the watch ledger's
    # rows are executed by cmd_watch as a root `git apply -R` — an officer
    # write to any of the three turns into root code, so all are germline
    # (the ledger is locked files-class, NOT a sanctioned-append SKIP).
    # CABINET-AXES KERNEL added 2026-07-05 (amendment
    # docs/proposals/germline-amendment-cabinet-axes-2026-07-05.md): the
    # earn_up rung-ladder overlay (trust_ladder.py — a forged rung map LIFTS
    # verdicts), the axes-contract rule, the extension gate pair
    # (extension-manifest.schema.json + validate-extension.sh), the live
    # Captain-locked rung-grant file (trust-ladder.yml — hook-covered BEFORE
    # the deployment creates it; the .example sibling stays editable via the
    # suffix anchor), and the shipped posture-presets dir (a forged preset
    # seeds a widened ruling). The axis-branching allowlist
    # (framework/policies/axes-allowlist.yml) rides the framework/policies/
    # dir-cover already on this line. instance/config/posture-narrow is
    # DELIBERATELY unprotected: narrow-only cap, Captain's binder verb
    # writes it at runtime (axes spec §1).
    *"memory/golden-evals/"*|*"framework/policies/"*|*"framework/authority/classifier.py"|*"framework/authority/lane.py"|*"framework/authority/matrix.py"|*"framework/authority/veto.py"|*"framework/authority/deploy_classifier.py"|*"framework/fidelity/graduation.py"|*"framework/authority/policy_engine.py"|*"cabinet/mcp-scope.yml"|*"cabinet/officer-capabilities.conf"|*".claude/rules/brain-bridge.md"|*".claude/rules/courses-of-action.md"|*"instance/config/autonomy.yml"|*"shared/interfaces/captain-vetoes.yml"|*"shared/interfaces/action-lessons.yml"|*"instance/config/act-first-surfaces.yml"|*"framework/frontdoor/action_exec.py"|*"framework/frontdoor/action_undo.py"|*"framework/frontdoor/actfirst_canary.py"|*"framework/frontdoor/veto_registry.py"|*"framework/frontdoor/tell_surface.py"|*"framework/frontdoor/calendar_template.py"|*"framework/acting/action_lane.py"|*"framework/acting/run_action_lane.py"|*"framework/frontdoor/channel.py"|*"framework/attention/situation.py"|*"framework/attention/feed.py"|*"framework/attention/acted_overlay.py"|*"framework/attention/situations.py"|*"framework/attention/queue.py"|*"framework/attention/hygiene.py"|*"framework/attention/queue_card.py"|*".claude/settings.json"|*"cabinet/scripts/hooks/"*|*"cabinet/scripts/policy-shadow.py"|*"cabinet/scripts/kill-switch.sh"|*"cabinet/scripts/germline-lock.sh"|*"framework/authority/posture.py"|*"framework/authority/grants.py"|*"framework/authority/needs.py"|*"framework/learning/gate.py"|*"framework/learning/apply_watch.py"|*"cabinet/scripts/grant-apply.sh"|*"cabinet/scripts/gate-apply.sh"|*"cabinet/launchd/com.cabinet.gate-apply.plist"|*"cabinet/launchd/com.cabinet.egress-proxy.template.plist"|*"shared/interfaces/gate-apply-watch.jsonl"|*"instance/config/posture.yml"|*"instance/config/standing-grants.yml"|*"instance/config/policies/"*|*"shared/interfaces/needs-ledger.jsonl"|*"framework/learning/trust_ladder.py"|*".claude/rules/axes-contract.md"|*"framework/schemas/extension-manifest.schema.json"|*"cabinet/scripts/validate-extension.sh"|*"instance/config/trust-ladder.yml"|*"instance/config/posture-presets/"*|*"framework/onboarding/journey.py"|*"framework/schemas/evidence-event.schema.json"|*"framework/evidence/"*|*"cabinet/dashboard/src/app/api/onboarding/"*|*"cabinet/dashboard/src/lib/onboarding/bridge.ts"|*"cabinet/dashboard/src/lib/onboarding/telegram.ts"|*"cabinet/dashboard/src/app/api/telegram/provisioning-webhook/route.ts"|*"cabinet/dashboard/src/components/onboarding/journey-card.tsx"|*"cabinet/companion/main.swift"|*"cabinet/scripts/evidence-read.sh"|*"instance/evidence/v1/"*|*"cabinet/scripts/start-officer-mac.sh"|*"cabinet/scripts/start-officer.sh"|*"cabinet/scripts/gen-officer-mcp-config.py"|*"cabinet/scripts/append-interface.sh"|*"cabinet/scripts/captain-law-broker.py"|*"cabinet/scripts/egress-guard.sh"|*"cabinet/scripts/egress-proxy.py"|*"cabinet/scripts/observe-only.sh"|*"cabinet/scripts/lib/officer-env.py"|*"cabinet/scripts/lib/officer-env.sh"|*"cabinet/scripts/lib/officer-sandbox.sh"|*"framework/comms/channel_adapter.py"|*"framework/comms/tools.py"|*"framework/comms/mcp/server.py"|*"framework/comms/adapters/telegram.py"|*"instance/config/egress.yml")
      echo "BLOCKED: Germline file — read-only for officers and loops (no loop may edit its own judge). Propose the change to the Captain; only the Captain applies germline edits." >&2
      exit 2
      ;;
    # CAPTAIN-LAW PLANE added 2026-07-07 (audit CRITICAL: self-persuasion /
    # injection-persistence channel). The always-injected "Captain law"
    # files — captain-patterns.md, captain-intents.md, captain-decisions.md,
    # and memory/skills/ (incl. evolved/) — were officer-writable with NO
    # guard while session-start injects their head/tail into EVERY officer,
    # and CLAUDE.md told officers to write captain-patterns.md directly: any
    # officer-authored (or prompt-injected) text became standing law with no
    # provenance. DELIBERATELY NOT germline (kept out of the §5 arm above,
    # GERM_PATH_RE, and immutable-core.yml — the lockstep meta-test
    # framework/tests/test_germline_lockstep_consistency.py diffs those
    # against the Ring-0 source): unlike Ring-0 read-only files, the three
    # ledgers keep a SANCTIONED officer APPEND lane —
    # cabinet/scripts/append-interface.sh (stdin-only content, fixed target
    # whitelist, append-only under a lock with a prefix-sha256 tripwire,
    # provenance stamp '### officer-note … [trust:officer]', refuses
    # Captain-format '## ' headings) — the same mechanism that lets
    # veto_registry.py remain the only writer of captain-vetoes.yml: block
    # every direct write vector on the TARGET paths, leave the sanctioned
    # writer script as the narrow doorway, and protect the writer script
    # itself from tampering (it is in this arm + §5c). memory/skills/ has NO
    # append lane: skills changes are evolution-loop proposals under
    # memory/skills/evolved/ review — Captain-applied, per the audit.
    # KEEP IN LOCKSTEP with CAPLAW_PATH_RE in §5c below — a path added here
    # without §5c reopens the bash-redirect write bypass for it.
    # BC BOOT-PACK (2026-07-15, ceremony addendum docs/proposals/germline-
    # session-start-digest-addendum-2026-07-15.md): captain-law-digest.md
    # joins the plane — session-start injects it IN FULL and FIRST, so an
    # officer-writable digest would reopen the exact injection-persistence
    # channel this arm closes for the ledgers. Its ONLY sanctioned writer is
    # cabinet/scripts/memory-distill.py --apply (Captain-reviewed, run from
    # an unsandboxed Captain/CoS context; the invocation carries no
    # write-shaped token so it passes §5c). The distiller script itself is
    # guarded too — same doorway protection as append-interface.sh. The
    # .proposal.md review file is DELIBERATELY outside the plane: --apply
    # refuses unless it byte-matches a fresh ledger render, so tampering it
    # can never reach boot.
    *"shared/interfaces/captain-patterns.md"|*"shared/interfaces/captain-intents.md"|*"shared/interfaces/captain-decisions.md"|*"shared/interfaces/captain-law-digest.md"|*"memory/skills/"*|*"cabinet/scripts/memory-distill.py")
      echo "BLOCKED: Captain-law file — officer-authored text may not become standing law via direct Write/Edit (no provenance). Append to captain-patterns / captain-intents / captain-decisions through the sanctioned interface: cabinet/scripts/append-interface.sh <target> with the entry on stdin (append-only, provenance-stamped). captain-law-digest.md is the machine-promoted boot index: regenerate via python3.12 cabinet/scripts/memory-distill.py, Captain review, then --apply — never hand-edit it or the distiller. memory/skills/ and append-interface.sh itself are Captain-applied only — propose the change to the Captain." >&2
      exit 2
      ;;
    *"cabinet/.env"*)
      # CoS manages the cabinet's OWN secret store (Captain-granted 2026-06-23:
      # "you should be able to both read and write ... handle the integrations for
      # me"). Security-neutral: cos already holds the host MCP (edit_file/run over
      # every host file), so this only surfaces — via native tools — a capability
      # cos already has. NARROW by design: other officers (no host MCP) stay
      # blocked from ALL .env via the general arm below, and even cos is allowed
      # ONLY the cabinet store here (product / screenpipe .env paths do not match
      # this arm, so they remain blocked).
      if [ "${OFFICER:-}" != "cos" ]; then
        echo "BLOCKED: Environment files cannot be modified by Officers" >&2
        exit 2
      fi
      ;;
    *".env"*)
      echo "BLOCKED: Environment files cannot be modified by Officers" >&2
      exit 2
      ;;
    *"cabinet/docker-compose"*|*"Dockerfile"*)
      if [ "${OFFICER:-}" != "cos" ]; then
        echo "BLOCKED: Infrastructure files cannot be modified by Officers — route to CoS" >&2
        exit 2
      fi
      ;;
    *"instance/memory/tier2/"*)
      # Officers can only write to their OWN tier2 directory
      if ! echo "$FILE_PATH" | grep -q "instance/memory/tier2/${OFFICER}/"; then
        echo "BLOCKED: Officers can only write to their own tier2 directory (instance/memory/tier2/${OFFICER}/)" >&2
        exit 2
      fi
      ;;
  esac
fi

# ============================================================
# 5a. EVIDENCE RAW-READ INVERSION (Evidence Recorder v1)
# ============================================================
# Officers receive the bounded projection through evidence-read.sh. Raw JSONL,
# anchors, purge receipts, control state, and especially .signing-key are not
# an officer read surface. The app/core writer does not pass through this
# officer hook, so its sanctioned append/recovery/purge lane remains intact.
if [ "$TOOL_NAME" = "Read" ] || [ "$TOOL_NAME" = "Grep" ] || [ "$TOOL_NAME" = "Glob" ] \
    || [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; then
  EVIDENCE_READ_PATH=$(echo "$TOOL_INPUT" | jq -r '.file_path // .path // empty' 2>/dev/null | tr -s '/')
  # PR#140 finding 5a-1: the case below matches a LITERAL 'instance/evidence/'
  # substring, so `instance/config/../evidence/v1/.signing-key` (no substring —
  # the OS resolves `..` to the HMAC signing key) slipped. Normalize LEXICALLY
  # (os.path.normpath collapses `..`) THEN os.path.realpath (a symlinked dir
  # component — e.g. instance/pub -> instance/evidence — also resolves to the raw
  # store; normpath alone is symlink-blind). normpath first so a non-existent
  # trailing basename still folds; realpath then follows symlinks in existing
  # components. FAIL-CLOSED: empty python3 output forces a sentinel that MATCHES
  # the block case, never a normalize-blind pass. Mirrors §5's Edit/Write
  # normalization pair (KEEP IN LOCKSTEP).
  if [ -n "$EVIDENCE_READ_PATH" ]; then
    EVIDENCE_READ_PATH=$(printf '%s' "$EVIDENCE_READ_PATH" | python3 -c 'import os,sys; p=sys.stdin.read(); sys.stdout.write(os.path.realpath(os.path.normpath(p)) if p else "")' 2>/dev/null || printf '')
    [ -z "$EVIDENCE_READ_PATH" ] && EVIDENCE_READ_PATH="/__evidence_unresolved__/instance/evidence/v1/raw"
  fi
  case "$EVIDENCE_READ_PATH" in
    *"instance/evidence/"*|*"Library/Application"*"/cabinet/evidence/"*)
      echo "BLOCKED: Raw evidence is Captain-controlled. Use cabinet/scripts/evidence-read.sh for the read-only redacted Cabinet projection." >&2
      exit 2
      ;;
  esac
fi

if [ "$TOOL_NAME" = "Bash" ]; then
  EVIDENCE_READ_CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null | tr -s '/')
  # Exact, argument-closed safe doorways. Exit before §5b sees the protected
  # script paths; compound commands, redirects, env prefixes, and extra shell
  # syntax do not match and continue through the ordinary gates.
  # PR#140 finding 5a-3: the doorway allow is SINGLE-LINE only. `grep -qE '^...$'`
  # returns success if ANY line matches, so a two-line command whose FIRST line is
  # the legit `evidence-read.sh <trial>` and whose SECOND line is `cat
  # .../.signing-key` was approved wholesale (the exit 0 smuggled the second line).
  # A multi-line command is never a bounded doorway — refuse the doorway match for
  # it and let it fall through to the raw-store / rm / interpreter blocks below.
  # (§0a's observe-only doorway carries the identical guard.)
  case "$EVIDENCE_READ_CMD" in
    *$'\n'*) : ;;  # multi-line — never a doorway; fall through to the blocks below
    *)
      if printf '%s' "$EVIDENCE_READ_CMD" | grep -qE '^(\.?/?cabinet/scripts/evidence-read\.sh[[:space:]]+[A-Za-z0-9][A-Za-z0-9._:-]{0,127}([[:space:]]+[0-9]{1,4})?|\.?/?cabinet/scripts/hooks/observe-ack\.sh[[:space:]]+[0-9]+-[0-9]+([[:space:]]+[0-9]+-[0-9]+){0,49})[[:space:]]*$'; then
        exit 0
      fi
      ;;
  esac
  # PR#140 finding 5a-1/5a-2: normalize PER PATH TOKEN (mirror §5b's CMD_SQ
  # normpath) so `cat instance/config/../evidence/v1/.signing-key` and
  # `rm -rf instance/x/../evidence/v1` fold to the literal store substring the
  # case below matches. Per-token, NEVER whole-string — a `..` in a later token
  # would erase an earlier store filename. Two normalizations per token: (a)
  # normpath for the lexical `..` forms, trailing `/` re-appended (normpath strips
  # it); (b) realpath — if a token's REAL path resolves INTO the store (a symlinked
  # dir component like instance/pub -> evidence, which normpath is blind to), the
  # token is replaced with a canonical `instance/evidence/` marker so the case
  # below fires (parity with the §5a Read arm's realpath). realpath is read-only.
  # The store test is slash-anchored ('/instance/evidence/'), so a sibling like
  # instance/evidence-notes.md is NOT over-matched. Fallback to the un-normalized
  # copy if python3 is unavailable (fail toward the substring match, which still
  # catches the literal no-`..` forms).
  EVIDENCE_CMD_NORM=$(printf '%s' "$EVIDENCE_READ_CMD" | python3 -c '
import os, re, sys
def _n(t):
    p = os.path.normpath(t)
    if t.endswith("/") and not p.endswith("/"):
        p += "/"
    try:
        rp = os.path.realpath(t).rstrip("/") + "/"
    except Exception:
        rp = ""
    if "/instance/evidence/" in rp or "/cabinet/evidence/" in rp:
        return "instance/evidence/__resolved__"
    return p
sys.stdout.write(re.sub(r"[^\s;|&<>()\x22\x27\x60]+", lambda m: _n(m.group(0)), sys.stdin.read()))
' 2>/dev/null || printf '%s' "$EVIDENCE_READ_CMD")
  # Raw store paths / dotted recorder modules anywhere in the normalized command —
  # reads AND destructive ops both trip this: the officer surface is the bounded
  # projection only.
  case "$EVIDENCE_CMD_NORM" in
    *"framework.evidence"*|*"framework.onboarding.journey"*|*"instance/evidence/"*|*"Library/Application"*"/cabinet/evidence/"*)
      echo "BLOCKED: Direct shell access to raw evidence is unavailable to officers. Use cabinet/scripts/evidence-read.sh for the bounded projection." >&2
      exit 2
      ;;
  esac
  # PR#140 finding 5a-2 (defense-in-depth): the evidence store is APPEND-ONLY; a
  # delete/move wipes recorded onboarding events. In the NORMAL path the realpath
  # normalizer above already routes every store delete — `..`-hop AND bare-parent
  # `rm -rf instance/evidence` — to the case block (bare tokens resolve to the
  # slash-suffixed `instance/evidence/__resolved__` marker, which the case matches).
  # This arm is the GUARANTEE when that normalizer degrades: python3 unavailable →
  # EVIDENCE_CMD_NORM falls back to the un-normalized command, and then the case's
  # trailing-slash pattern misses a bare `instance/evidence` (no slash) — exactly
  # the store-wipe finding #2 named (§5b's GERM_PATH_RE also lists the store only
  # as 'instance/evidence/v1/' WITH a slash, so a normpath'd 'instance/evidence/v1'
  # misses §5b's rm-allowlist too). Independent target-anchored arm, GERM_PATH_RE
  # untouched (the lockstep meta-test pins it to immutable-core.yml). A destructive
  # verb whose target token contains the store root — dev `instance/evidence...` or
  # deployed `.../cabinet/evidence...`, with or without a trailing slash or `/v1` —
  # is refused fail-closed (reads via the bounded projection are unaffected; a
  # store-adjacent sibling like `instance/evidence-notes` under a destructive verb
  # is over-matched, an accepted fail-closed FP — rephrase). `mv` is included:
  # moving the store dir away is deletion-equivalent for the audit trail.
  EVID_ANCH='(^|[;&|`([:space:]])'
  EVID_STORE_TGT="[\"']?[^[:space:];|&<>\"']*(instance|cabinet)/evidence[^[:space:];|&<>\"']*"
  if printf '%s' "$EVIDENCE_CMD_NORM" | grep -qE "${EVID_ANCH}(rm|rmdir|unlink|shred|mv)[[:space:]]+([^;|&]*[[:space:]])?${EVID_STORE_TGT}"; then
    echo "BLOCKED: Destructive operation on the append-only evidence store. It records onboarding events for the Captain's audit; officers may not delete or move it. Use cabinet/scripts/evidence-read.sh for the bounded projection." >&2
    exit 2
  fi
  # PR#140 finding 5a-4 (hook screen; the recorder-side capability check is a
  # separate group): an interpreter importing the recorder modules dodges the
  # dotted `framework.evidence` / `framework.onboarding.journey` substrings via the
  # `from framework import evidence` form (and import aliases / extra whitespace /
  # string concatenation). Fail-closed STRUCTURAL cut: a Python interpreter
  # invocation (python/ipython/pypy, any version, at start / after a separator /
  # path-prefixed) that names BOTH `framework` and an evidence|onboarding|journey
  # module token is refused. Requiring the interpreter token avoids false-blocking
  # a plain `grep evidence framework/...` source read (which stays allowed).
  if printf '%s' "$EVIDENCE_CMD_NORM" | grep -qE '(^|[[:space:];|&`(/])(python[0-9.]*|ipython[0-9.]*|pypy[0-9.]*)([[:space:]]|$)' \
     && printf '%s' "$EVIDENCE_CMD_NORM" | grep -qE 'framework' \
     && printf '%s' "$EVIDENCE_CMD_NORM" | grep -qE 'evidence|onboarding|journey'; then
    echo "BLOCKED: Interpreter access to the evidence/onboarding recorder modules (framework.evidence / framework.onboarding.journey) is unavailable to officers. Use cabinet/scripts/evidence-read.sh for the bounded projection." >&2
    exit 2
  fi
fi

# ============================================================
# 5b. GERMLINE BASH WRITE SCREEN (2026-07-04)
# ============================================================
# Build-checkpoint 2026-07-04 hard-blocker #2 (safety-perimeter CRITICAL):
# section 5 binds the Edit/Write TOOLS only, so `echo forged > shared/
# interfaces/captain-vetoes.yml`, `tee`, `sed -i`, `cp/mv/install`,
# `truncate`, `dd of=` and `python -c 'open(...,"w")'` were an open Bash
# bypass around the germline judge plane — one injected officer command
# could forge the veto registry (the demotion tooth) or widen the act-first
# surface allowlist. This screen closes the write-shaped vectors while
# leaving reads (cat/grep/less/head, copies OUT of a germline path,
# redirects whose target is elsewhere) untouched.
#
# Design rules (deterministic string/regex — no dataflow, no LLM):
#   - FAIL TOWARD BLOCKING on ambiguity. Prose false-positives (e.g. an
#     unquoted `git commit -m` body containing `> <germ path>`, or `echo`
#     lines mentioning tee/cp + a germ path) are ACCEPTED and stateless —
#     nothing is consumed on match (not the FW-028/FW-029 amplification
#     class), the officer just rephrases. Missing a real write is the
#     failure mode we refuse.
#   - Write arms are TARGET-anchored (redirect target token, cp/mv FINAL
#     dest, dd of=, tee/truncate args) so germline paths appearing as read
#     sources (`cp <germ> /tmp/`, `dd if=<germ> of=/tmp/x`, `2>/dev/null`)
#     do not trip them. Interpreter arms (python -c / heredoc / bare stdin)
#     cannot be statically bounded — quote spans swallow in-quote paths in
#     both directions — so they block on interpreter-shape + germ-mention
#     anywhere in the command; accepted FP documented (workaround: read via
#     cat/grep, or split the python call from the germ-path read).
#   - Newlines are joined to spaces in the MATCH-ONLY copy so a `\`-line-
#     continuation cannot split `>` from its target across grep lines.
#     Side effect: heredoc BODIES join into the scanned line — a doc
#     heredoc whose prose contains `tee <germ path>` blocks (accepted FP;
#     write docs via the Write tool instead).
#   - Cost: one cheap pre-filter grep short-circuits ~every command (germ
#     paths appear in almost no officer bash); the write-shape grep runs
#     only on germ-mentioning commands. 1 jq + 1 pipeline + ≤2 greps, no
#     loops, no per-path subshells.
#
# KNOWN residuals (not closable by substring matching, named follow-ups):
# variable indirection (`V=<germ>; echo x > $V`), git-content restores
# (`git checkout -- <germ>`, `git apply`), perl/ruby/node -e interpreters,
# `cp evil -t <germ dir>` basename joins, and typed-policy-engine parity
# for these entries (section 0 engine has no germline rules yet).
if [ "$TOOL_NAME" = "Bash" ]; then
  CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null)
  # Match-only copy: squeeze slashes (mirrors section 5's tr -s '/' so
  # `instance/config//autonomy.yml` cannot dodge), fold shell line-
  # continuations (a trailing `\` before a newline joins the two lines in
  # bash — strip it FIRST so `echo x > \<NL> germ` reads as `echo x > germ`
  # and the operator cannot be split from its target), then join remaining
  # newlines to spaces so a multi-line command scans as one line.
  CMD_SQ=$(printf '%s' "$CMD" | tr -s '/' | sed 's/\\$//' | tr '\n' ' ')
  # Finding C (2026-07-12): also resolve `..` LEXICALLY so a parent-dir hop like
  # `echo forged > shared/interfaces/reviews/../captain-vetoes.yml` cannot dodge
  # the GERM_PATH_RE pre-filter + target-anchored write arms below. normpath is
  # pure-lexical (no realpath — target may not exist). CRITICAL: apply it
  # PER PATH TOKEN, never to the whole command string — a whole-string normpath
  # treats spaces/operators as path chars, so a `..` in a LATER token cancels the
  # segment holding an EARLIER germline filename (`echo > <germ> && cat x/../y`,
  # or a trailing `<tok>/..` arg), erasing the germline substring and skipping the
  # entire screen. The regex matches each maximal run of non-separator chars (a
  # path token) — whitespace and shell metachars `;|&<>()"' \x60` are the
  # boundaries — and normpaths ONLY that run, so `..` can never cross a token
  # edge. Trailing `/` is re-appended (normpath strips it) so directory-dest arms
  # like the Edit-C basename-forge screen below still fire on `cp x germ_dir/`.
  # Fallback to the un-normalized copy if python3 is unavailable (fail toward
  # today's behavior). KEEP IN LOCKSTEP with §5c's copy of this line.
  CMD_SQ=$(printf '%s' "$CMD_SQ" | python3 -c 'import os,re,sys; _n=lambda t:(lambda p:p+"/" if t.endswith("/") and not p.endswith("/") else p)(os.path.normpath(t)); sys.stdout.write(re.sub(r"[^\s;|&<>()\x22\x27\x60]+",lambda m:_n(m.group(0)),sys.stdin.read()))' 2>/dev/null || printf '%s' "$CMD_SQ")
  # Edit C (2026-07-04): cp/mv/rsync/install/ln with an ENTIRELY-germline parent
  # DIR as the write destination (basename-join forge, e.g.
  # `cp /tmp/evil framework/authority/x.py` or into cabinet/scripts/hooks/ to
  # drop a malicious hook). Those dir paths are NOT in GERM_PATH_RE, so this arm
  # is independent + target-anchored (germ dir must be the FINAL dest token).
  # Mixed dirs (cabinet/, .claude/rules/, instance/config/, shared/interfaces/)
  # are deliberately excluded — their residual is closed by the filesystem lock.
  GERM_DIR_RE='framework/authority/|framework/frontdoor/|framework/acting/|framework/fidelity/|framework/policies/|cabinet/scripts/lib/|cabinet/scripts/hooks/|memory/golden-evals/|instance/config/policies/|instance/config/posture-presets/|framework/evidence/|cabinet/dashboard/src/app/api/onboarding/|instance/evidence/v1/'
  _GDIR_TGT="[\"']?[^[:space:];|&<>\"']*(${GERM_DIR_RE})[^[:space:];|&<>\"']*"
  # branch 1: germ dir as FINAL positional dest; branch 2: -t/--target-directory DEST form (dir not final)
  if printf '%s' "$CMD_SQ" | grep -qE "(^|[;&|\`([:space:]])(cp|mv|rsync|install|ln)[[:space:]]+(-[-a-zA-Z]+[[:space:]]+)*([^;|&]+[[:space:]]+)?${_GDIR_TGT}[\"']?([[:space:]]*(\$|[;&|<>#])|[[:space:]]+[0-9]+[<>])" \
     || printf '%s' "$CMD_SQ" | grep -qE "(^|[;&|\`([:space:]])(cp|mv|rsync|install|ln)[[:space:]]+([^;|&]*[[:space:]])?(-[a-zA-Z]*t[[:space:]]*|--target-directory[=[:space:]])${_GDIR_TGT}"; then
    echo "BLOCKED: Germline directory — cp/mv/rsync/install/ln into an all-germline directory is a forge (basename-join). Reads are unaffected. Propose the change to the Captain." >&2
    exit 2
  fi
  # Same protected set as section 5's germline case list — KEEP IN LOCKSTEP.
  GERM_PATH_RE='memory/golden-evals/|framework/policies/|framework/authority/(classifier|lane|matrix|veto|deploy_classifier|posture|grants|needs|policy_engine)\.py|framework/fidelity/graduation\.py|cabinet/mcp-scope\.yml|cabinet/officer-capabilities\.conf|\.claude/rules/(brain-bridge|courses-of-action|axes-contract)\.md|instance/config/(autonomy|posture|standing-grants|trust-ladder|egress)\.yml|shared/interfaces/(captain-vetoes|action-lessons)\.yml|shared/interfaces/(needs-ledger|gate-apply-watch)\.jsonl|instance/config/act-first-surfaces\.yml|instance/config/policies/|instance/config/posture-presets/|framework/frontdoor/(action_exec|action_undo|actfirst_canary|veto_registry|tell_surface|calendar_template|channel)\.py|framework/attention/(situation|situations|feed|acted_overlay|queue|queue_card|hygiene)\.py|framework/acting/(action_lane|run_action_lane)\.py|framework/learning/(gate|apply_watch|trust_ladder)\.py|framework/schemas/extension-manifest\.schema\.json|\.claude/settings\.json|cabinet/scripts/hooks/|cabinet/scripts/policy-shadow\.py|cabinet/scripts/kill-switch\.sh|cabinet/scripts/germline-lock\.sh|cabinet/scripts/validate-extension\.sh|cabinet/scripts/(grant|gate)-apply\.sh|cabinet/launchd/com\.cabinet\.gate-apply\.plist|cabinet/launchd/com\.cabinet\.egress-proxy\.template\.plist|framework/onboarding/journey\.py|framework/schemas/evidence-event\.schema\.json|framework/evidence/|cabinet/dashboard/src/app/api/onboarding/|cabinet/dashboard/src/lib/onboarding/bridge\.ts|cabinet/dashboard/src/lib/onboarding/telegram\.ts|cabinet/dashboard/src/app/api/telegram/provisioning-webhook/route\.ts|cabinet/dashboard/src/components/onboarding/journey-card\.tsx|cabinet/companion/main\.swift|cabinet/scripts/evidence-read\.sh|instance/evidence/v1/|cabinet/scripts/(start-officer-mac|start-officer|append-interface|egress-guard|observe-only)\.sh|cabinet/scripts/gen-officer-mcp-config\.py|cabinet/scripts/(captain-law-broker|egress-proxy)\.py|cabinet/scripts/lib/officer-env\.(sh|py)|cabinet/scripts/lib/officer-sandbox\.sh|framework/comms/(channel_adapter|tools)\.py|framework/comms/mcp/server\.py|framework/comms/adapters/telegram\.py'
  if printf '%s' "$CMD_SQ" | grep -qE "$GERM_PATH_RE"; then
    # Target token: optional opening quote, then ONE shell word containing a
    # germline path (germ paths never contain spaces/quotes, so excluding
    # separators + redirect chars from the token class is sound).
    GERM_TGT="[\"']?[^[:space:];|&<>\"']*($GERM_PATH_RE)[^[:space:];|&<>\"']*"
    # Command-position anchor (start or a separator that can precede a
    # command word). Single-quoted so the backtick stays literal.
    ANCH='(^|[;&|`([:space:]])'
    # Quote-aware filler (same shape as section 4's sed arm): crosses quoted
    # spans so `sed 's/x/y/' -i <germ>` cannot hide -i behind an arg, and
    # deliberately tolerates unbalanced quotes (fail-closed).
    QF="([^&'\"]|'[^']*'|\"[^\"]*\"|'|\"|&[^&])*"
    # a) redirect INTO a germ path: >, >>, 2>, 2>>, &>, >|, >& forms
    GERM_WRITE_RE=">{1,2}[|&]?[[:space:]]*${GERM_TGT}"
    # b) tee: every file arg is a write target; `<` excluded from the filler
    #    so `tee /tmp/out < <germ>` stays a read
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}tee[[:space:]]+(-[-a-zA-Z]+[[:space:]]+)*([^;|&<]+[[:space:]]+)?${GERM_TGT}"
    # c) sed in-place (plain `sed -n p <germ>` reads stay allowed)
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}sed[[:space:]]+(${QF}[[:space:]])?(-[a-zA-Z]*i[^[:space:]]*|--in-place(=[^[:space:]]*)?)([[:space:]]${QF})?[[:space:]]+${GERM_TGT}"
    # d) copy/move/link/install with a germ path as FINAL destination
    #    (germ as SOURCE with a non-germ dest falls through = read); the
    #    trailing group also accepts fd-redirect tails like `2>/dev/null`
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}(cp|mv|rsync|install|ln)[[:space:]]+(-[-a-zA-Z]+[[:space:]]+)*[^;|&]+[[:space:]]+${GERM_TGT}[\"']?([[:space:]]*(\$|[;&|<>#])|[[:space:]]+[0-9]+[<>])"
    # d2) -t/--target-directory destination form
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}(cp|mv|rsync|install|ln)[[:space:]]+([^;|&]*[[:space:]])?(-[a-zA-Z]*t[[:space:]]*|--target-directory(=|[[:space:]]+))${GERM_TGT}"
    # e) truncate: file args are write targets
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}truncate[[:space:]]+([^;|&<]+[[:space:]]+)?${GERM_TGT}"
    # f) dd of=<germ> (dd if=<germ> of=/tmp/x stays a read)
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}dd[[:space:]]+[^;|&]*of=${GERM_TGT}"
    # g) python -c with a germ path anywhere in the command (see header:
    #    interpreter args are unboundable; germ presence already established
    #    by the pre-filter). `-c` must be a standalone flag — a following
    #    quote/paren/space/EOL — so `--config <germ>` reads stay allowed.
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}python[0-9.]*[[:space:]]+([^;|&]*[[:space:]])?-c([\"'([:space:]]|\$)"
    # g2) python fed by heredoc
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}python[0-9.]*[[:space:]][^;|&]*<<"
    # g3) bare/stdin-fed python (`echo 'open(...)' | python3` / `python3 -`).
    #     Trailing class is pipe / subshell-close / EOL ONLY — deliberately
    #     excludes `;` and `&` so a compound READ like `which python3 && cat
    #     <germ>` (python3 is an ARGUMENT, not a stdin interpreter) is not a
    #     false-positive block. The dangerous stdin-fed forms all end in a
    #     pipe segment, `-`, or EOL, which stay covered.
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}python[0-9.]*([[:space:]]+-)?[[:space:]]*(\$|[|)])"
    # g4) python COMBINED flag cluster ending in c: `python3 -Sc '...'`,
    #     `-Ic`, `-OOc`, `-Bsc` all put `c` adjacent to another flag letter, so
    #     arm g's standalone `-c` misses them. Match a leading `-` + flag
    #     letters + `c` immediately before the code word. [re-verify KILLED #5]
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}python[0-9.]*[[:space:]]+([^;|&]*[[:space:]])?-[A-Za-z]*c([\"'([:space:]]|\$)"
    # h) general-purpose scripting interpreters invoked WITH A FLAG while a
    #    germline path is present. The pre-filter already confirmed a germ path
    #    is in THIS command; a germline READ uses cat/grep/less (never these),
    #    and every real write form takes a flag (perl -i / ruby -pi / awk -i
    #    inplace / node -e fs.writeFile). Requiring the trailing "-" avoids
    #    false-blocking a bare interpreter NAME that is merely an argument to a
    #    read (e.g. `grep perl <germ>`). Enumerating each interpreter's exact
    #    write flags is whack-a-mole, so flag-presence is the fail-closed cut.
    #    [re-verify KILLED #5: `perl -i -pe 's/.../' <germ>`]
    GERM_WRITE_RE="${GERM_WRITE_RE}|${ANCH}(perl|ruby|node|nodejs|awk|gawk|mawk)[[:space:]]+-"
    if printf '%s' "$CMD_SQ" | grep -qE "$GERM_WRITE_RE"; then
      echo "BLOCKED: Germline file — read-only for officers and loops (no loop may edit its own judge). This Bash command contains a write-shaped operation targeting a germline path (reads like cat/grep/less are allowed). Propose the change to the Captain; only the Captain applies germline edits." >&2
      exit 2
    fi
    # FAIL-CLOSED READ ALLOWLIST [re-verify round 3, 2026-07-04]. The interpreter
    # denylist above is unwinnable on its own (tclsh, lua, php, ed, ex, patch,
    # `git checkout`, ruby/tclsh heredocs, `$(printf '\x3e')`-built redirects all
    # slipped a denylist). Inversion: with a germline path present, EVERY
    # command-position verb must be a recognized READ; any other verb — an
    # interpreter, editor, patcher, vcs-write, or writer — blocks. A small closed
    # allowlist beats an unbounded denylist. (A string hook is still only
    # defense-in-depth vs a Turing-complete shell; the complete germline boundary
    # is officers-run-as-a-separate-uid at deployment. See flip record.)
    # Continuation-folded, NEWLINES PRESERVED as real command separators [round 3
    # bypass: a multi-line "cat germ <NL> ed germ <<EOF" collapses under
    # newline->space and only the first verb is checked]. RS="\4" (EOT, never in
    # a command) reads the whole input as one record so `\<NL>` continuation
    # pairs fold to nothing while real newlines survive; the allowlist awk then
    # sees each physical line as its own record and checks every segment's verb.
    CMD_FOLDED=$(printf '%s' "$CMD" | tr -s '/' | awk 'BEGIN{RS="\4"}{gsub(/\\\n/,"");printf "%s",$0}')
    GERM_ALLOW_BLOCK=$(printf '%s' "$CMD_FOLDED" | awk '
      BEGIN{
        # pure reads
        split("cat tac bat grep egrep fgrep zgrep rg ag less more head tail wc nl cut sort uniq column tr od xxd hexdump base32 base64 md5 md5sum shasum sha1sum sha256sum sha512sum cksum b2sum file stat ls realpath readlink dirname basename diff cmp comm which type command hash test true false echo printf pwd env id whoami date sleep jq yq colordiff nkf",R," ")
        for(i in R) ok[R[i]]=1
        # dual-use tools whose WRITE forms are ALL caught by the precise arms
        # a-h ABOVE (redirect / of= / dest / dash-c). A bare read through them
        # (cp FROM germ, dd if=germ, tee fed by germ, python script.py config
        # germ) is legitimate and passes; the precise arm already fired-and-
        # exited if it was a write. NOTE sed is DELIBERATELY EXCLUDED here: it
        # writes via the w / W / e SCRIPT commands (not only dash-i), which the
        # arm-c dash-i check does not screen [round-3 bypass], so any sed
        # touching a germline path is refused fail-closed. Read one with cat.
        split("cp mv rsync install ln dd tee truncate python python2 python3",D," ")
        for(i in D) ok[D[i]]=1
        ok[":"]=1; ok["["]=1; ok["]"]=1
        # git is a read ONLY with a read subcommand
        split("show log diff cat-file blame grep ls-files ls-tree status rev-parse describe shortlog reflog",G," ")
        for(i in G) gitok[G[i]]=1
        # exec-wrappers run their ARGUMENT — peel them so the allowlist sees the real verb
        split("env command builtin exec nohup setsid stdbuf unbuffer nice ionice timeout time doas xargs chroot",WP," ")
        for(i in WP) wrap[WP[i]]=1
      }
      {
        # break into command-position segments at separators/substitutions
        gsub(/\$\(/, "\n", $0); gsub(/[|;&`()]/, "\n", $0)
        m=split($0, seg, "\n")
        for(s=1;s<=m;s++){
          line=seg[s]
          # strip leading whitespace + env-assignment prefixes (VAR=val ...)
          sub(/^[[:space:]]+/,"",line)
          while(match(line, /^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+/)){
            line=substr(line, RLENGTH+1)
          }
          # peel exec-wrapper prefixes (env/command/nice/timeout/xargs/...) so
          # `env ed <germ>` / `command ed <germ>` cannot smuggle a writer past
          # the allowlist. Bounded + fail-closed; preserves `env VAR=v cat germ`.
          _wp=0
          while(1){
            split(line,_wt,/[[:space:]]+/); _v=_wt[1]
            sub(/^.*\//,"",_v); sub(/^["'"'"']/,"",_v)
            if(!(_v in wrap)) break
            if(++_wp>4){ print "BLOCK"; exit }
            _before=line
            sub(/^[[:space:]]*[^[:space:]]+[[:space:]]+/,"",line)   # drop wrapper token
            if(line==_before) break                                 # bare wrapper, no arg
            while(match(line,/^(-[^[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*|[0-9]+[smhd]?)[[:space:]]+/)){
              line=substr(line,RLENGTH+1)                           # drop its flags/VAR=/duration args
            }
            if(line=="") break
          }
          if(line=="") continue
          split(line, w, /[[:space:]]+/); verb=w[1]
          sub(/^.*\//,"",verb)            # strip a path prefix (/usr/bin/cat->cat)
          sub(/^["'\'']/,"",verb)          # strip a leading quote
          if(verb=="") continue
          if(verb ~ /^python[0-9.]+$/) continue    # versioned python (arms g* guard writes)
          if(verb=="git"){ if(w[2] in gitok) continue; else {print "BLOCK"; exit} }
          if(!(verb in ok)){ print "BLOCK"; exit }
        }
      }')
    if [ "$GERM_ALLOW_BLOCK" = "BLOCK" ]; then
      echo "BLOCKED: Germline file — read-only for officers and loops. This Bash command references a germline path but is not a recognized read-only command (cat/grep/less/head/tail/diff/stat/git-show...). An interpreter, editor, patcher, or writer touching a germline path is refused fail-closed. Propose the change to the Captain; only the Captain applies germline edits." >&2
      exit 2
    fi
  fi
fi

# ============================================================
# 5c. CAPTAIN-LAW PLANE BASH WRITE SCREEN (2026-07-07)
# ============================================================
# Companion to the §5 CAPTAIN-LAW Write/Edit arm — KEEP IN LOCKSTEP with it.
# Audit finding (CRITICAL): the always-injected Captain-law files
# (captain-patterns.md / captain-intents.md / captain-decisions.md +
# memory/skills/ incl. evolved/) had NO write guard at all, so one bash
# redirect (`echo forged-law >> shared/interfaces/captain-patterns.md`)
# made officer- or injection-authored text standing law injected into every
# future officer session. This screen closes the write-shaped Bash vectors
# (same arm shapes as §5b: redirect, tee, sed -i, cp/mv/rsync/install/ln
# dest, truncate, dd of=, python -c/heredoc/stdin, interpreter-with-flag,
# plus rm/unlink — this plane has no chflags backstop) while leaving reads
# untouched.
#
# SANCTIONED-WRITER CARVE-OUT (mirrors how veto_registry.py writes
# captain-vetoes.yml through §5b): the write arms are TARGET-anchored, and
# the sanctioned appender is invoked as a script with a slug argument —
# `cabinet/scripts/append-interface.sh captain-patterns <<'EOF' … EOF` —
# so its invocation never contains a write-shaped token targeting a
# protected path and passes every arm. Deliberately NO §5b-style fail-closed
# read-allowlist inversion here: that inversion would block the appender's
# own verb (the exact reason this plane is append-only-via-interface, not
# Ring-0 read-only). The appender script ITSELF is in CAPLAW_PATH_RE (and
# the §5 arm), so redirect/sed/cp/rm tampering with the doorway is blocked.
#
# Accepted FPs (fail-closed, stateless — rephrase and re-run): heredoc
# ENTRY BODIES whose prose contains a write-op word + a captain-law path
# (newlines join in the match-only copy, same class as §5b's documented
# heredoc FP; workaround: keep raw paths out of entry prose or pipe the
# entry via printf), and prose `echo`s mentioning tee/cp + a captain-law
# path. KNOWN residuals (same set as §5b, accepted): variable indirection,
# `git checkout -- <path>` content restores, script-file interpreters
# (`python3 evil.py`). Backstop: session-start provenance — appended law
# carries the '### officer-note … [trust:officer]' stamp, so unstamped
# '## ' entries not in git history are forensically visible.
if [ "$TOOL_NAME" = "Bash" ]; then
  CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null)
  # Match-only copy: squeeze slashes, fold line-continuations, join newlines
  # (same normalization as §5b — see its header for why each step exists).
  CMD_SQ=$(printf '%s' "$CMD" | tr -s '/' | sed 's/\\$//' | tr '\n' ' ')
  # Finding C (2026-07-12): resolve `..` LEXICALLY, PER PATH TOKEN (same
  # normalizer as §5b — KEEP IN LOCKSTEP; see its header for why whole-string
  # normpath is unsafe) so `echo forged-law >> shared/interfaces/x/../captain-patterns.md`
  # — and the underblock form `echo >> <caplaw> && cat x/../y` — cannot dodge the
  # CAPLAW_PATH_RE pre-filter + target-anchored write arms below.
  # Fallback to the un-normalized copy if python3 is unavailable.
  CMD_SQ=$(printf '%s' "$CMD_SQ" | python3 -c 'import os,re,sys; _n=lambda t:(lambda p:p+"/" if t.endswith("/") and not p.endswith("/") else p)(os.path.normpath(t)); sys.stdout.write(re.sub(r"[^\s;|&<>()\x22\x27\x60]+",lambda m:_n(m.group(0)),sys.stdin.read()))' 2>/dev/null || printf '%s' "$CMD_SQ")
  # The captain-law plane: 3 append-only ledgers + the skills dir + the
  # sanctioned appender itself + (BC boot-pack 2026-07-15) the boot-injected
  # captain-law-digest.md and its sanctioned writer memory-distill.py
  # (doorway protection, same as the appender). Bare distiller invocations —
  # `python3.12 cabinet/scripts/memory-distill.py [--apply|--check]` — match
  # no write arm below and stay ALLOWED; the .proposal.md review file is
  # deliberately outside the plane (its \.md anchor cannot match the
  # .proposal.md suffix). KEEP IN LOCKSTEP with the §5 CAPTAIN-LAW arm.
  CAPLAW_PATH_RE='shared/interfaces/captain-(patterns|intents|decisions|law-digest)\.md|memory/skills/|cabinet/scripts/append-interface\.sh|cabinet/scripts/memory-distill\.py'
  if printf '%s' "$CMD_SQ" | grep -qE "$CAPLAW_PATH_RE"; then
    CAPLAW_TGT="[\"']?[^[:space:];|&<>\"']*($CAPLAW_PATH_RE)[^[:space:];|&<>\"']*"
    ANCH='(^|[;&|`([:space:]])'
    QF="([^&'\"]|'[^']*'|\"[^\"]*\"|'|\"|&[^&])*"
    # a) redirect INTO a captain-law path (>, >>, 2>, &>, >|, >& forms)
    CAPLAW_WRITE_RE=">{1,2}[|&]?[[:space:]]*${CAPLAW_TGT}"
    # b) tee: every file arg is a write target (`tee /tmp/x < <ledger>` stays a read)
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}tee[[:space:]]+(-[-a-zA-Z]+[[:space:]]+)*([^;|&<]+[[:space:]]+)?${CAPLAW_TGT}"
    # c) sed in-place (plain sed reads stay allowed)
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}sed[[:space:]]+(${QF}[[:space:]])?(-[a-zA-Z]*i[^[:space:]]*|--in-place(=[^[:space:]]*)?)([[:space:]]${QF})?[[:space:]]+${CAPLAW_TGT}"
    # d) copy/move/link/install with a captain-law path as FINAL destination
    #    (covers the dir-dest basename-join into memory/skills/ too — the
    #    target token contains the dir prefix)
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}(cp|mv|rsync|install|ln)[[:space:]]+(-[-a-zA-Z]+[[:space:]]+)*[^;|&]+[[:space:]]+${CAPLAW_TGT}[\"']?([[:space:]]*(\$|[;&|<>#])|[[:space:]]+[0-9]+[<>])"
    # d2) -t/--target-directory destination form
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}(cp|mv|rsync|install|ln)[[:space:]]+([^;|&]*[[:space:]])?(-[a-zA-Z]*t[[:space:]]*|--target-directory(=|[[:space:]]+))${CAPLAW_TGT}"
    # e) truncate: file args are write targets
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}truncate[[:space:]]+([^;|&<]+[[:space:]]+)?${CAPLAW_TGT}"
    # f) dd of=<ledger> (dd if=<ledger> of=/tmp/x stays a read)
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}dd[[:space:]]+[^;|&]*of=${CAPLAW_TGT}"
    # g/g2/g3/g4) python -c / heredoc / stdin-fed / combined-flag-cluster with
    # a captain-law path present (interpreter args are statically unboundable
    # — same rationale and shapes as §5b arms g*)
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}python[0-9.]*[[:space:]]+([^;|&]*[[:space:]])?-c([\"'([:space:]]|\$)"
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}python[0-9.]*[[:space:]][^;|&]*<<"
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}python[0-9.]*([[:space:]]+-)?[[:space:]]*(\$|[|)])"
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}python[0-9.]*[[:space:]]+([^;|&]*[[:space:]])?-[A-Za-z]*c([\"'([:space:]]|\$)"
    # h) scripting interpreters invoked WITH A FLAG while a captain-law path
    #    is present (perl -i / ruby -pi / awk -i inplace / node -e …)
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}(perl|ruby|node|nodejs|awk|gawk|mawk)[[:space:]]+-"
    # i) delete/shred: this plane is NOT chflags-locked (appends must keep
    #    working), so removal of a ledger/skill/the appender is write-shaped
    CAPLAW_WRITE_RE="${CAPLAW_WRITE_RE}|${ANCH}(rm|rmdir|unlink|shred)[[:space:]]+([^;|&]*[[:space:]])?${CAPLAW_TGT}"
    if printf '%s' "$CMD_SQ" | grep -qE "$CAPLAW_WRITE_RE"; then
      echo "BLOCKED: Captain-law file — officer-authored text may not become standing law via a direct write (no provenance). This Bash command contains a write-shaped operation targeting captain-patterns/captain-intents/captain-decisions, captain-law-digest (boot-injected index), memory/skills/, the append interface, or the digest distiller (reads like cat/grep/less are allowed). Append to the three ledgers through the sanctioned interface: cabinet/scripts/append-interface.sh <target> with the entry on stdin (append-only, provenance-stamped). captain-law-digest.md regenerates only via python3.12 cabinet/scripts/memory-distill.py + Captain review + --apply. memory/skills/, append-interface.sh and memory-distill.py themselves are Captain-applied only — propose the change to the Captain." >&2
      exit 2
    fi
  fi
fi


# ============================================================
# 6. LAYER 1 GATE — CTO must run Crew review before push/merge
# ============================================================
# FW-029: two-phase guard to prevent substring-amplification.
# The old single-regex check matched ANY CMD containing `git push main`
# as a substring — including `git commit -m "...git push main..."`
# heredoc bodies, `echo "git push main"` debug prints, and
# `cat /tmp/log | grep 'git push main'` — each of which CONSUMED the
# cabinet:layer1:cto:reviewed key via the DEL on match, forcing a re-SET
# before the actual push. Same amplification class as FW-028, but with
# state-consumption semantics.
#
# Phase 1 (anchor): CMD must START with a deploy SUBCOMMAND —
#   git push / gh pr / gh api / curl — optionally prefixed by
#   priv-esc / env VAR=X / timeout. Subcommand-level narrowing rejects
#   `git commit`, `git log`, `gh pr view` etc. at Phase 1 so substring
#   action matches on their -m/--grep bodies cannot trip the gate.
# FW-041 (hotfix 2026-04-22 — Rule 4 class from FW-034): BOTH phases
#   extended to accept `git -FLAG [VALUE] push` and `gh -FLAG [VALUE]
#   pr merge`. GNU `git` accepts global flags (-C <path>, -c key=val,
#   --git-dir=<path>, --work-tree=<path>, --namespace=<ns>) BETWEEN
#   `git` and the subcommand; `gh` accepts (-R owner/repo, --repo
#   owner/repo). Pre-hotfix Phase 1 required subcommand immediately
#   after `git`/`gh`, AND Phase 2 required literal `git push` / `gh pr
#   merge` — so `git -C /path push origin main` and `gh -R owner/repo
#   pr merge N` bypassed BOTH phases (fail-open — gate silently not
#   consulted). Fix: identical optional repeated `(-FLAG [VALUE] )*`
#   group between tool and subcommand at BOTH phases. Each flag group
#   requires leading `-` on the flag and non-`-` leading char on the
#   value, so non-deploy subcommands like `git commit -m "..."` —
#   where `commit` doesn't start with `-` — still correctly fall out
#   of the flag-repeat and fail the `push` verb check. Phase 1 `gh`
#   alternation ALSO narrowed from `(pr|api)` to `(pr merge|api)` —
#   read-only `gh pr view/list/checkout/status` are not write actions
#   and have no business passing Phase 1.
# FW-041 hotfix-4 (2026-04-24 — regression close: d752992 silent revert
#   of ff11e85 escape-aware rich flag-value atom). Commit d752992
#   ("FW-040 Hotfix 5") silently bundled a widened VAR_ASSIGN value
#   class AND reverted ff11e85's flag-value atom back to plain
#   exclusive-alternation `[^-][^[:space:]]*|'[^']*'|"[^"]*"`. Plain
#   exclusive-alt cannot match `alias.x='val with space'` because the
#   unquoted alt stops at the space INSIDE the quote span — 3 HIGH
#   attack forms silently bypassed the live gate:
#     (a) `git -C $'path space' push origin main` (ANSI-C quoted path)
#     (b) `git -c alias.x='val with space' push origin main` (SQ embed)
#     (c) `git -c alias.x="val with space" push origin main` (DQ embed)
#   Fix: restore ff11e85's rich chain-of-atoms at all 21 occurrences
#   across 4 gate regex lines (Layer 1 Phase 1, Phase 2a, Phase 2b,
#   CI Green Phase 1). Atom structure:
#     ([^-[:space:]'"]|'([^'\\]|\\.)*'|"([^"\\]|\\.)*"|\$'([^'\\]|\\.)*')
#     ([^[:space:]'"]|'([^'\\]|\\.)*'|"([^"\\]|\\.)*"|\$'([^'\\]|\\.)*')*
#   Escape-aware quote span `([^'\\]|\\.)*` absorbs `\'`/`\"` inside
#   the quote as 2 chars instead of terminating early. ANSI-C alt
#   `\$'([^'\\]|\\.)*'` handles bash `$'…'` (distinct quote context
#   from `'…'`). Sonnet adversary Pass-1+2 on fix: 0 bugs, 0 new FPs,
#   6 scope-gaps deferred to FW-051, BONUS coverage of `$"…"`
#   localized-string. EVAL-014 regression pins added: 8 new positives
#   (HF2-A1/A2/A3 + HF2-B1/B2 + HF4-C1/C2/C3) + 5 new FP guards
#   (git -c color.ui, user.name SQ/DQ, ANSI-C dir/email). Gotcha for
#   future hotfix authors: when widening one atom (VAR_ASSIGN value
#   class etc), `git show` every predecessor hotfix touching the same
#   regex before shipping — silent atom-revert pattern is easy to
#   reintroduce when the diff widens adjacent atoms.
# FW-043 (hotfix 2026-04-23 — COO + Sonnet empirical adversary on FW-041 ship):
#   6 bypass forms silently skipped Phase 1 because the anchor was
#   LINE-START-ONLY (`^[[:space:]]*` + `head -n1`), not statement-start.
#   Forms: (a) `cd /tmp && git push origin main` — chain prefix,
#   (b) multiline `echo ok\ngit push origin main` — head -n1 eats
#   line 1, (c) `(git push origin main)` — subshell paren prefix,
#   (d) `true && git push origin main` — always-succeed chain,
#   (e) `: ; git push origin main` — null-command + semi,
#   (f) `{ git push origin main; }` — brace-group prefix (Sonnet
#   pass-1 against initial fix). Fix for both Layer 1 + CI Green
#   gate: (1) remove `head -n1` — grep's line-mode handles
#   multiline naturally (each line checked independently against
#   the anchor, which still uses `^`). (2) Widen anchor prefix
#   from `^[[:space:]]*` to `(^|[;&|({\`][[:space:]]*)` — accepts
#   bare line-start OR a preceding shell statement-boundary char
#   (semi, amp, pipe, open-paren, open-brace, backtick) + whitespace.
#   Trade-off: false-positives when a boundary char appears INSIDE
#   a quoted string followed by literal `git push origin main` text,
#   e.g., `git commit -m "staged && git push origin main"` would fire
#   the gate (Phase 2 already substring-matched; Phase 1 now also
#   matches at `&&` inside quotes). Accepted as fail-closed trade
#   (over-block vs FW-041's silent fail-open); FP rate ~rare in
#   officer workflow, gate prompt tells CTO to set the reviewed
#   key + retry. Also extends Layer 1 Phase 2 trailing-terminator
#   class from `[[:space:];]|$` to `[[:space:];&|(){}\`]|$` so
#   trailing shell-chain chars (incl. close-brace/close-paren)
#   after `main`/`master` also match. Heredoc body FP (line-mode
#   grep sees `git push origin main` as its own line) also
#   accepted as fail-closed per same rationale.
#   FW-041 Phase 2 scope-gap (quoted-space flag value) remains
#   open — still tracked as FW-041 Phase 2.
# FW-045 (hotfix-6 2026-04-23 — COO Pass-2 empirical adversary on f7a231b):
#   17/20 probes against the FW-043 statement-boundary prefix bypassed
#   Phase 1. Four HIGH classes, 14 addressable forms:
#   (1) prefix-consumer gap — 8 POSIX command-modifier wrappers
#   absent from alternation: `exec|time|nohup|nice|ionice|coproc|stdbuf
#   |unbuffer cmd`. Fix: unified flag-tolerant branch
#   `(exec|time|nohup|nice|ionice|coproc|stdbuf|unbuffer)(
#   [[:space:]]+-[^[:space:]]+([[:space:]]+[^-][^[:space:]]*)?)*[[:space:]]+`
#   (same flag pattern as FW-041 for git/gh — handles `nice -n 10 cmd`,
#   `ionice -c 3 -n 5 cmd`, `stdbuf -oL cmd`, bare `nohup cmd`).
#   (2) inline VAR=val prefix — `GIT_TRACE=1 git push`, `FOO=bar
#   BAZ=qux git push`. THE canonical POSIX idiom. Existing `env`
#   branch only handles `env VAR=val cmd`, not bare assignment. Fix:
#   prepend `[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+[[:space:]]+` to
#   alternation — 1+ iterations handled by outer `*`.
#   (3) boundary class gap — `!` (bash negation: `! cmd` returns
#   !exit-code). Added to class. (`<`/`>` redirects handled as prefix
#   consumer, not boundary, since they take an arg: `>/tmp/out cmd` =
#   redirect-then-run-cmd.) Fix: boundary class extended from
#   `[;&|({\`]` to `[;&|({\`!]`; redirect branch
#   `[<>][[:space:]]*[^[:space:]]+[[:space:]]+` added to prefix-consumer.
#   (4) wrapper-exec with quote-body — `bash -c 'git push'`, `sh -c`,
#   `zsh -c`, `eval 'git push'`, bare `eval git push`. Fix: two new
#   prefix-consumer branches `(bash|sh|zsh)[[:space:]]+-c[[:space:]]+
#   ['"]?` and `eval[[:space:]]+['"]?` (optional quote absorbs through
#   the opening delimiter — engine re-anchors at `git push` inside the
#   quoted body).
#   CRITICAL Phase 2 co-change: `bash -c 'git push origin main'`
#   ends with `'` after `main`, which was NOT in Phase 2 trailing
#   terminator class — Phase 2 then failed to match even after Phase 1
#   succeeded. Phase 2 trailing class extended from `[[:space:];&|(){}<>\`]`
#   to `[[:space:];&|(){}<>'"\`]` — adds quote chars as valid post-`main`
#   terminators. (Pattern 1 from memory: "Phase 2 action regex must
#   mirror Phase 1 anchor flag-tolerance" — FW-045 re-confirmed: any
#   wrapper form that introduces a new post-`main` context needs Phase
#   2 trailing class extension. 5th instance in FW-029-family work.)
#   Sonnet Pass-3 additions (same commit, 9 new findings — HIGH: H-1
#   `bash -x -c`, H-2 ANSI-C `$'...'`, H-3 `)` boundary, H-4 `}` boundary;
#   MEDIUM: M-1 bare `env` (no VAR=val), M-2 Phase 2 asymmetry (`main!`,
#   `main^`, `main~`, `main#comment`), M-3 digit-prefix redirect
#   `2>/dev/null`, M-4 `timeout --preserve-status 30s`; plus `setsid` +
#   `wget` tool additions):
#   - Boundary class `[;&|({\`!]` → `[;&|({)}\`!]` (adds close-paren
#     for case-arm end, close-brace for function-body end).
#   - `env` branch: flag-tolerant idiom `env([[:space:]]+-[^[:space:]]+
#     ([[:space:]]+[^-][^[:space:]]*)?)*[[:space:]]+` replaces
#     VAR=val-required form (bare-env now matches; inline VAR=val
#     handled by separate `[A-Za-z_]…=[…]` branch).
#   - `timeout` branch: pre-duration flag-tolerance (`timeout -k 5s
#     --preserve-status 30s cmd`).
#   - Wrapper list: add `setsid` (session leader).
#   - `bash|sh|zsh` branch: flag-tolerant before `-c` (`bash -x -c`,
#     `bash --norc -c`), ANSI-C absorber `(\$?['\''"])?` handles
#     `bash -c $'…'`.
#   - Redirect branch: digit-prefix `[0-9]?[<>]` handles `2>/dev/null cmd`
#     and `1>/tmp/out cmd`.
#   - Command alternation: add `wget[[:space:]]` (parallel to curl).
#   - Phase 2 trailing class: add `!#\\^~` to post-`main|master`
#     terminators (`main!`, `main#comment` shell-comment strip, `main^1`
#     git-ancestor, `main~2` git-ancestor, `main\\foo` backslash).
#   Sonnet Pass-4 additions (fresh-context re-review after Pass-3 fix —
#   4 real bypasses confirmed empirically; 2 Pass-4 findings were
#   false-positives: `<(cmd)` process sub already fires via existing
#   `(` boundary, and `main:refs/heads/main` fires via greedy `.*main$`):
#   - Wrapper alternation: add `command` and `builtin` — POSIX builtin
#     modifiers (`command cmd` bypasses aliases; `builtin cmd` forces
#     shell builtin). Real bypasses: `command git push origin main`.
#   - Shell -c alternation: extend `(bash|sh|zsh)` →
#     `([^[:space:]]*/)?(bash|sh|zsh|fish|ksh|dash|ash|csh|tcsh|mksh)`. Real bypass:
#     `fish -c 'git push origin main'`. All POSIX-family shells take
#     `-c CMD_STRING`, so gap covered by common alt-shells.
#   COO Pass-5 additions (fresh-context empirical post-Pass-4 — 6 real
#   bypasses in one HIGH class confirmed on e588850, all canonical bash
#   compound-statement keywords; 2 additional MEDIUM stdin-shell forms
#   documented as scope-gap):
#   - Prefix-consumer alt: add `(then|do|else|elif)[[:space:]]+` branch.
#     No flag-tolerance — bash reserved words do NOT take flags. Closes
#     `if ci_green; then git push origin main; fi` canonical conditional
#     push, `while <cond>; do git push origin main; done` retry loop,
#     `for x in a b; do git push origin main; done` batch, `until` wait-
#     then-push, `elif`/`else` branches. The reserved word follows a `;`
#     (or newline) statement-boundary — anchor fires at `;`, but prior
#     regex had no alt to consume `then|do|else|elif`, so scan halted.
#   Remaining scope-gaps (acknowledged, NOT fixable by flat regex):
#   (a) xargs-construct `echo origin main | xargs git push` — lexical
#   disaggregation across pipe, main is LHS arg not RHS refspec.
#   (b) variable expansion `X=git; $X push` — already tracked as FW-040
#   Phase B P8.
#   (c) dot-source `. /tmp/push.sh` + `source /tmp/push.sh` — hook can't
#   scan file contents.
#   (d) perl/python -e / awk 'system(…)' shell-out — not in wrapper
#   alternation; same filesystem-escape class as dot-source, deferred
#   to FW-040 Phase B shell-parse-aware gate.
#   (e) shell-stdin-mode `bash <<<"git push …"` here-string + `echo ...
#   | bash -s` explicit-stdin-read — same dataflow-decoupled class as
#   xargs and dot-source (the `git push` text is carried across a
#   stdin boundary, flat regex can't bridge). Deferred to FW-040 Phase
#   B. Pass-5 MEDIUM #2.
#   FP surface expansion (accepted fail-closed, same class as FW-043 FP-1):
#   commit bodies or inline text containing wrapper-name or inline-VAR
#   token adjacent to literal `git push origin main` text WILL fire the
#   gate. Example: commit msg "nohup git push origin main for CI" →
#   trips. Also: `git push --force-with-lease origin main` now fires
#   (was already in flag-tolerant scope but worth calling out — ACK
#   re-SET retry works). Pass-6 Sonnet widening: multi-line `-m` commit
#   bodies with a line starting `then git push origin main` / `do git
#   push …` / `else …` / `elif …` now also fire (new reserved-word
#   branch matches at `^` anchor on the second line). Same class, same
#   workaround. Mitigation: `cabinet:layer1:cto:reviewed` re-SET after
#   gate-block → retry-commit workflow (same as FW-043).
# Phase 2 (action regex): actual push-to-main-or-master / pr-merge pattern.
# AND-composed so both must pass to trip the gate.
# Action regex covers BOTH `main` (example product repo) and `master`
# (framework repo default) — CTO pushes to both.
# FW-044 (2026-04-24): Phase 2b — unified positional regex.
# Covers `gh api <DELETE> refs(/|%2[Ff])heads(/|%2[Ff])(main|master)` + branch-protection
# endpoint + curl DELETE + wget DELETE analogs. Structure: statement-boundary
# anchor (^|[;&|({)}`!]) on gh/curl/wget prevents the pattern from matching
# inside quoted echo bodies (`gh api user && echo "gh api -X DELETE refs/heads/main"`
# → inside `"…"`, no boundary char precedes the inner `gh api` → no match).
# Env-var prefix wrapper `([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+[[:space:]]+)*`
# absorbs inline POSIX assignments before gh/curl/wget (`GH_TOKEN=abc gh api
# -X DELETE refs/heads/main` — Pass-2 MEDIUM-C fix, canonical auth-override).
# Clause-exclusion [^;&|#]* between anchor and DELETE/ref signals stops at
# `;`/`&`/`|`/`#` → compound-command FPs (`gh api user && git commit -m
# "…DELETE refs/heads/main…"`) don't cross clauses. Case-insensitive
# [Dd][Ee][Ll][Ee][Tt][Ee] + fused flag `(-X|--method|--request)[=[:space:]]*`
# covers -XDELETE, -X DELETE, -X=DELETE, --method DELETE, --method=DELETE,
# --request DELETE, and quoted "DELETE"/'DELETE' variants (adversary A2/A5/A6).
# Trailing-slash `(main|master)/?` handles ref with/without trailing slash
# (Pass-1 B1). Branch-protection endpoint
# `branches(/|%2[Ff])(main|master)(/|%2[Ff])protection` — same destructive verb class — blocked
# as OR-alternative (Pass-1 D1). curl + wget anchors handle raw REST calls
# that bypass gh (Pass-1 C3 + Pass-2 HIGH-B wget --method=DELETE).
# Terminator set includes `?` (Pass-2 HIGH-A: `?v=1` query string on ref URL).
# Order-agnostic: flag-before-ref AND ref-before-flag both covered by the two
# top-level alternatives inside the trailing group.
# Branch disambiguation via terminator [[:space:];&|(){}<>'"`!#\^~/?] — trailing
# char `l`/`.`/`-`/`s` NOT in set so mainline/main.md/main-feature/mastership
# correctly pass through.
# FW-044 hotfix-1 (2026-04-24): close 14 HIGH bypasses from COO Pass-1
# adversary across two root causes:
#   ROOT CAUSE 1 (PA-F class, 11 bypasses): Phase 2b prefix-absorber was a
#     strict SUBSET of Phase 1's — Phase 2b only absorbed VAR_ASSIGN plus
#     env-var-only prefix, so AND-composed gate `phase1 && (phase2a||phase2b)`
#     fired false on every wrapper Phase 1 absorbed but Phase 2b didn't
#     (`eval`, `bash -c`, `sh -c`, `nohup`, `time`, `exec`, `sudo`, `env CMD`,
#     `timeout 5`, `command`, `stdbuf -o0` before `gh api -X DELETE
#     refs/heads/main`). Fix: replace narrow Phase 2b prefix absorber with
#     full Phase 1 alternation (sudo/env/timeout/exec/time/nohup/nice/ionice/
#     coproc/stdbuf/unbuffer/setsid/command/builtin/VAR_ASSIGN/shell-c/eval/
#     redirect/then-do).
#   ROOT CAUSE 2 (PA-E class, 3 bypasses): VAR_ASSIGN value class
#     `[^[:space:]]+` truncated quoted values at the first space —
#     `PATH="foo bar" gh api -X DELETE refs/heads/main` broke Phase 1 at
#     the `foo` → `bar` boundary. Fix: widen value class to
#     `('...'|"..."|[^[:space:]]+)` then extend to include ANSI-C quoting
#     `\'...'` (Pass-2 P2-A2). Applied at Phase 1 AND Phase 2b for parity.
# Hotfix-1 Pass-2 adversary: 1 additional bypass closed (ANSI-C quoted
# VAR_ASSIGN value). 15 total HIGH bypasses closed in hotfix-1. Remaining
# deferrals to FW-051:
#   - `FOO=''hello world''` bash adjacent-quoted-string concatenation
#     (Pass-2 P2-A1) — same class as `-X 'DE''LETE'` quote-concat. No
#     CMD_NORM preprocessing at Layer 1.
#   - `eval "PATH=\"foo bar\" gh api -X DELETE refs/heads/main"` (Pass-1
#     CA1) — backslash-escaped quotes inside quoted eval body need
#     CMD_NORM preprocessing; same class.
# Hotfix-1 Pass-3 identified 3 orthogonal scope-gaps also deferred to
# FW-051:
#   - full-path shell `/bin/bash -c "..."` (shell alternation has no slash)
#   - fused flag `bash -lc "..."` (no `-lc` branch; only `-c`)
#   - wrapper indirection `./wrapper.sh` / `$(command -v gh)` (no
#     indirection absorber)
# Deferred to FW-051: Layer 1 quoted-splice (`"gh" api`), subshell-eval splice
# (`$(echo gh) api`), URL-encoded refs (`refs%2fheads%2fmain`), wildcard refs
# (`refs/heads/m*`), heredoc body scan, Pass-2 MEDIUM-D quote-concat DELETE
# (`-X 'DE''LETE'`). Same root class as FW-042 pre-v3.7.2 BSQ — Layer 1 does
# not apply CMD_NORM.
if [ "$OFFICER" = "cto" ] && [ "$TOOL_NAME" = "Bash" ]; then
  CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null)
  # FW-051 (2026-04-24): reuse Section 3b CMD_NORM / CMD_UNQUOTED preprocessing
  # to defeat no-preprocessing bypass classes. Strip adjacent empty-quote pairs
  # (`''`, `""`) that fuse neighbor tokens at bash exec (PA-D1/D2), and strip
  # backtick command-substitution wrappers (`` `gh` `` → `gh`) that fuse to
  # expose the inner token at command position (Sonnet adversary Pass A HIGH,
  # same class as deferred AC-3 `$(echo gh)`). The HAS_SPLICE-gated
  # CMD_UNQUOTED secondary scan catches command-position quoted splice like
  # `"gh" api`, `g"h" api`. Regex also extended: shell alternation accepts
  # leading path (`/bin/bash`), `env` preamble atom also accepts leading path
  # (`/usr/bin/env bash -c` — Sonnet adversary Pass A CRITICAL), `-c` flag
  # widened to `-[A-Za-z]*c[A-Za-z]*` (catches `-lc`, `-xc`, compound flags),
  # refs and branches patterns accept `%2[Ff]` URL-encoded separator.
  CMD_L1_NORM=$(printf '%s' "$CMD_NORM" | sed -e "s/''//g" -e 's/""//g' -e 's/`\([^`]*\)`/\1/g')
  CMD_L1_UNQUOTED=$(printf '%s' "$CMD_UNQUOTED" | sed -e "s/''//g" -e 's/""//g' -e 's/`\([^`]*\)`/\1/g')
  L1_P1='(^|[;&|({)}`!])[[:space:]]*(sudo[[:space:]]+|([^[:space:]]*/)?env([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+|timeout([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+[0-9]+[smhd]?[[:space:]]+|(exec|time|nohup|nice|ionice|coproc|stdbuf|unbuffer|setsid|command|builtin)([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=(\$'\''[^'\'']*'\''|'\''[^'\'']*'\''|"[^"]*"|[^[:space:]]+)[[:space:]]+|([^[:space:]]*/)?(bash|sh|zsh|fish|ksh|dash|ash|csh|tcsh|mksh)([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+-[A-Za-z]*c[A-Za-z]*[[:space:]]+(\$?['\''"])?|eval[[:space:]]+['\''"]?|[0-9]?[<>][[:space:]]*[^[:space:]]+[[:space:]]+|(then|do|else|elif)[[:space:]]+)*(git[[:space:]]+(-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?[[:space:]]+)*push|gh[[:space:]]+(-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?[[:space:]]+)*(pr[[:space:]]+merge|api)|curl[[:space:]]|wget[[:space:]])'
  L1_P2A='git[[:space:]]+(-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?[[:space:]]+)*push.*(main|master)([[:space:];&|(){}<>'\''"`!#\\^~]|$)|gh[[:space:]]+(-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?[[:space:]]+)*pr[[:space:]]+merge'
  L1_P2B='(^|[;&|({)}`!])[[:space:]]*(sudo[[:space:]]+|([^[:space:]]*/)?env([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+|timeout([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+[0-9]+[smhd]?[[:space:]]+|(exec|time|nohup|nice|ionice|coproc|stdbuf|unbuffer|setsid|command|builtin)([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=(\$'\''[^'\'']*'\''|'\''[^'\'']*'\''|"[^"]*"|[^[:space:]]+)[[:space:]]+|([^[:space:]]*/)?(bash|sh|zsh|fish|ksh|dash|ash|csh|tcsh|mksh)([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+-[A-Za-z]*c[A-Za-z]*[[:space:]]+(\$?['\''"])?|eval[[:space:]]+['\''"]?|[0-9]?[<>][[:space:]]*[^[:space:]]+[[:space:]]+|(then|do|else|elif)[[:space:]]+)*(gh[[:space:]]+(-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?[[:space:]]+)*api[[:space:]]|curl([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]|wget([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]])[^;&|#]*((-X|--method|--request)[=[:space:]]*["'\'']?[Dd][Ee][Ll][Ee][Tt][Ee]["'\'']?[^;&|#]*(refs(/|%2[Ff])heads(/|%2[Ff])(main|master)([[:space:];&|(){}<>'\''"`!#\\^~/?]|$)|branches(/|%2[Ff])(main|master)(/|%2[Ff])protection([[:space:];&|(){}<>'\''"`!#\\^~?]|$))|(refs(/|%2[Ff])heads(/|%2[Ff])(main|master)([[:space:];&|(){}<>'\''"`!#\\^~/?]|$)|branches(/|%2[Ff])(main|master)(/|%2[Ff])protection([[:space:];&|(){}<>'\''"`!#\\^~?]|$))[^;&|#]*(-X|--method|--request)[=[:space:]]*["'\'']?[Dd][Ee][Ll][Ee][Tt][Ee]["'\'']?)'
  # Triple-scan: (1) RAW $CMD preserves escape-aware atom semantics for
  # backslash-escaped quote flag values (e.g. `git -c alias.x='va\'l' push`
  # where CMD_NORM's \' → ' collapse breaks the 'single-quoted' atom);
  # (2) CMD_L1_NORM applies normalization + empty-quote-pair strip to catch
  # no-preprocessing bypass classes; (3) HAS_SPLICE-gated CMD_L1_UNQUOTED
  # secondary catches command-position quoted splice.
  if { echo "$CMD" | grep -qE "$L1_P1" && \
       { echo "$CMD" | grep -qE "$L1_P2A" || \
         echo "$CMD" | grep -qE "$L1_P2B"; }; } \
     || { echo "$CMD_L1_NORM" | grep -qE "$L1_P1" && \
          { echo "$CMD_L1_NORM" | grep -qE "$L1_P2A" || \
            echo "$CMD_L1_NORM" | grep -qE "$L1_P2B"; }; } \
     || { [ "$HAS_SPLICE" = "1" ] && \
          echo "$CMD_L1_UNQUOTED" | grep -qE "$L1_P1" && \
          { echo "$CMD_L1_UNQUOTED" | grep -qE "$L1_P2A" || \
            echo "$CMD_L1_UNQUOTED" | grep -qE "$L1_P2B"; }; }; then
    REVIEWED=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "cabinet:layer1:cto:reviewed" 2>/dev/null)
    if [ -z "$REVIEWED" ] || [ "$REVIEWED" = "(nil)" ]; then
      echo "LAYER 1 GATE: Spawn a Crew agent to review your diff before pushing/merging. After review, run: redis-cli -h redis -p 6379 SET cabinet:layer1:cto:reviewed 1 EX 300" >&2
      exit 2
    fi
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL "cabinet:layer1:cto:reviewed" > /dev/null 2>&1
  fi
fi

# ============================================================
# 7. CI GREEN GATE — CTO must verify CI before merge
# ============================================================
# FW-029: same two-phase guard as Layer 1. Prevents echoes of
# `pulls/N/merge` URLs (in docs, logs, debug prints) from consuming
# the cabinet:layer1:cto:ci-green key. Anchor narrowed to deploy
# subcommand (git push / gh pr / gh api / curl) so `git commit -m
# "...pulls/42/merge..."` bodies cannot pass Phase 1.
if [ "$OFFICER" = "cto" ] && [ "$TOOL_NAME" = "Bash" ]; then
  CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null)
  # FW-051 (2026-04-24): same CMD_L1_NORM / CMD_L1_UNQUOTED preprocessing as
  # Section 6 (empty-quote-pair + backtick-substitution strip). L1_P1 is
  # reused as Phase 1 (deploy-subcommand anchor); the Phase 2 check is
  # `pulls/[0-9]+/merge` URL literal.
  CMD_L1_NORM=$(printf '%s' "$CMD_NORM" | sed -e "s/''//g" -e 's/""//g' -e 's/`\([^`]*\)`/\1/g')
  CMD_L1_UNQUOTED=$(printf '%s' "$CMD_UNQUOTED" | sed -e "s/''//g" -e 's/""//g' -e 's/`\([^`]*\)`/\1/g')
  S7_P1='(^|[;&|({)}`!])[[:space:]]*(sudo[[:space:]]+|([^[:space:]]*/)?env([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+|timeout([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+[0-9]+[smhd]?[[:space:]]+|(exec|time|nohup|nice|ionice|coproc|stdbuf|unbuffer|setsid|command|builtin)([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=(\$'\''[^'\'']*'\''|'\''[^'\'']*'\''|"[^"]*"|[^[:space:]]+)[[:space:]]+|([^[:space:]]*/)?(bash|sh|zsh|fish|ksh|dash|ash|csh|tcsh|mksh)([[:space:]]+-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?)*[[:space:]]+-[A-Za-z]*c[A-Za-z]*[[:space:]]+(\$?['\''"])?|eval[[:space:]]+['\''"]?|[0-9]?[<>][[:space:]]*[^[:space:]]+[[:space:]]+|(then|do|else|elif)[[:space:]]+)*(git[[:space:]]+(-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?[[:space:]]+)*push|gh[[:space:]]+(-[^[:space:]]+([[:space:]]+([^-[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')([^[:space:]'\''"]|'\''([^'\''\\]|\\.)*'\''|"([^"\\]|\\.)*"|\$'\''([^'\''\\]|\\.)*'\'')*)?[[:space:]]+)*(pr[[:space:]]+merge|api)|curl[[:space:]]|wget[[:space:]])'
  S7_PULLS='pulls/[0-9]+/merge'
  # Triple-scan: (1) RAW $CMD for escape-aware atoms, (2) CMD_L1_NORM for
  # empty-quote-pair bypass, (3) HAS_SPLICE-gated CMD_L1_UNQUOTED for splice.
  if { echo "$CMD" | grep -qE "$S7_P1" && echo "$CMD" | grep -qE "$S7_PULLS"; } \
     || { echo "$CMD_L1_NORM" | grep -qE "$S7_P1" && echo "$CMD_L1_NORM" | grep -qE "$S7_PULLS"; } \
     || { [ "$HAS_SPLICE" = "1" ] && \
          echo "$CMD_L1_UNQUOTED" | grep -qE "$S7_P1" && \
          echo "$CMD_L1_UNQUOTED" | grep -qE "$S7_PULLS"; }; then
    CI_VERIFIED=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "cabinet:layer1:cto:ci-green" 2>/dev/null)
    if [ -z "$CI_VERIFIED" ] || [ "$CI_VERIFIED" = "(nil)" ]; then
      echo "CI GREEN GATE: Run 'bash $CABINET_ROOT/cabinet/scripts/verify-deploy.sh ci <commit-sha>' and confirm CI is green before merging. After CI passes, run: redis-cli -h $REDIS_HOST -p $REDIS_PORT SET cabinet:layer1:cto:ci-green 1 EX 300" >&2
      exit 2
    fi
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL "cabinet:layer1:cto:ci-green" > /dev/null 2>&1
  fi
fi

# ============================================================
# 8. CONTEXT_SLUG VALIDATION + CAPACITY COUPLING (Phase 1 CP2)
# ============================================================
# YAML files at instance/config/contexts/*.yml are source of truth for
# known slugs and their capacity (work|personal). Every tool call that
# writes a context_slug must reference a known slug AND must not cross
# the capacity boundary of the acting officer.
#
# Cache: rebuilt from source into a private per-invocation mktemp (slug<TAB>
# capacity) on EVERY call — never a persisted /tmp cache (Finding B). Pure-shell
# rebuild keeps the hook fast (~1ms per call).

CONTEXTS_DIR="$CABINET_ROOT/instance/config/contexts"
# SECURITY (Finding B, C17 audit): rebuild EVERY call from source into an
# unpredictable per-invocation mktemp; never trust a persisted /tmp cache a
# same-uid officer could poison. Pure-shell rebuild is ~1ms. On mktemp failure
# the block is skipped (fail-open on infra error, consistent with FW-002 d).
SLUG_CACHE=$(mktemp "${TMPDIR:-/tmp}/cabinet-context-slugs.XXXXXX" 2>/dev/null)

if [ -d "$CONTEXTS_DIR" ] && [ -n "$SLUG_CACHE" ]; then
    : > "$SLUG_CACHE"
    for f in "$CONTEXTS_DIR"/*.yml "$CONTEXTS_DIR"/*.yaml; do
      [ -f "$f" ] || continue
      # Strip inline # comments, quotes, and surrounding whitespace before capture.
      slug=$(awk -F: '/^slug:/{sub(/[ \t]*#.*$/,"",$2); gsub(/^[ \t]+|[ \t\r\n]+$/,"",$2); gsub(/^["'"'"']|["'"'"']$/,"",$2); print $2; exit}' "$f")
      cap=$(awk -F: '/^capacity:/{sub(/[ \t]*#.*$/,"",$2); gsub(/^[ \t]+|[ \t\r\n]+$/,"",$2); gsub(/^["'"'"']|["'"'"']$/,"",$2); print $2; exit}' "$f")
      [ -n "$slug" ] && [ -n "$cap" ] && printf "%s\t%s\n" "$slug" "$cap" >> "$SLUG_CACHE"
    done

  # Extract context_slug from tool_input if present (any depth)
  SLUG_IN_CALL=$(echo "$TOOL_INPUT" | jq -r '.context_slug // (..|.context_slug? // empty)' 2>/dev/null | grep -v '^$' | head -1)

  # Also pull from Bash command args (e.g. record-experience.sh --context-slug foo)
  if [ -z "$SLUG_IN_CALL" ] && [ "$TOOL_NAME" = "Bash" ]; then
    BCMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null)
    SLUG_IN_CALL=$(echo "$BCMD" | grep -oE -- '--context[_-]slug[= ]+[a-z0-9_-]+' | head -1 | awk -F'[= ]' '{print $NF}')
  fi

  if [ -n "$SLUG_IN_CALL" ]; then
    # Validate slug exists in cache
    CTX_CAPACITY=$(awk -F'\t' -v s="$SLUG_IN_CALL" '$1==s{print $2; exit}' "$SLUG_CACHE")
    if [ -z "$CTX_CAPACITY" ]; then
      echo "BLOCKED: unknown context_slug '$SLUG_IN_CALL' — add to instance/config/contexts/<slug>.yml first." >&2
      echo "Known slugs: $(cut -f1 "$SLUG_CACHE" | tr '\n' ' ')" >&2
      exit 2
    fi

    # Cross-capacity enforcement: officer's capacity (from env) must match the context's.
    # OFFICER_CAPACITY defaults to 'work' for the example work preset. Phase 2 will read
    # from preset.yml or per-officer config, not hardcoded default.
    OFFICER_CAPACITY="${OFFICER_CAPACITY:-work}"
    if [ "$OFFICER_CAPACITY" != "$CTX_CAPACITY" ]; then
      echo "BLOCKED: capacity_check failed — officer '$OFFICER' has capacity '$OFFICER_CAPACITY' but context_slug '$SLUG_IN_CALL' has capacity '$CTX_CAPACITY'. Cross-capacity writes are forbidden." >&2
      exit 2
    fi
  fi
  # Finding B: drop the per-invocation temp slug cache.
  rm -f "$SLUG_CACHE"
fi

# ============================================================
# 9. MCP SCOPE ENFORCEMENT (Phase 1 CP5)
# ============================================================
# cabinet/mcp-scope.yml declares which MCP servers each hired agent may
# reach. On every MCP tool call (tool_name starts with 'mcp__'), the
# hook derives the server name and rejects the call if it is not in the
# acting officer's scope.
#
# Cache: rebuilt from source into a private per-invocation mktemp (officer\t
# csv-of-mcps) on EVERY call — never a persisted /tmp cache (Finding B).

MCP_SCOPE_FILE="$CABINET_ROOT/cabinet/mcp-scope.yml"

if [ -f "$MCP_SCOPE_FILE" ] && echo "$TOOL_NAME" | grep -q '^mcp__'; then
  # SECURITY (Finding B, C17 audit): scope is recomputed from the schg-locked
  # source on EVERY mcp call into an unpredictable per-invocation mktemp — never
  # a trusted persisted /tmp cache a same-uid officer could poison (repro: 'cos
  # GRANTED neon'). mcp-scope.yml is schg + GERM_PATH_RE-guarded, so this path
  # is airtight end-to-end. Cache format per line:  agent\tmcp1,mcp2,...
  # Universals from yaml's top-level 'universal:' list are merged into every
  # agent's set at build time, so the membership check stays one string lookup.
  # FAIL CLOSED (audit 4c, germline window 2 2026-07-07; and on mktemp failure):
  # no usable scope table -> refuse. A build failure used to be swallowed —
  # stale/absent cache then resolved ALLOWED="" and the unknown-officer arm let
  # the call through, contradicting the axes-contract "corrupt allowlist loads
  # EMPTY" doctrine. The parser SHAPE is unchanged — gen-officer-mcp-config.py
  # ::parse_scope mirrors it (parity tests in
  # cabinet/scripts/tests/test_gen_officer_mcp_config.py).
  MCP_SCOPE_CACHE=$(mktemp "${TMPDIR:-/tmp}/cabinet-mcp-scope.XXXXXX" 2>/dev/null)
  if [ -z "$MCP_SCOPE_CACHE" ] || ! python3 - "$MCP_SCOPE_FILE" "$MCP_SCOPE_CACHE" <<'PY' 2>/dev/null
import re, sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src).read()
out = []
section = None
cur_agent = None
universals = []
# First pass: collect universals
for line in text.splitlines():
    m = re.match(r'^universal:\s*\[([^\]]*)\]', line)
    if m:
        universals = [x.strip() for x in m.group(1).split(',') if x.strip()]
        break
# Second pass: parse agents/scaffolds
for line in text.splitlines():
    if re.match(r'^(agents|scaffolds):\s*$', line):
        section = line.split(':',1)[0]
        continue
    # Reset section when any other top-level key is hit
    if re.match(r'^[A-Za-z]', line):
        if not re.match(r'^(agents|scaffolds):\s*$', line):
            section = None
        continue
    if section and re.match(r'^  [A-Za-z][A-Za-z0-9_-]*:\s*$', line):
        cur_agent = line.strip().rstrip(':')
        continue
    if cur_agent and re.match(r'^\s+mcps:\s*\[', line):
        mcps_raw = line.split('[',1)[1].split(']',1)[0]
        mcps = [m.strip() for m in mcps_raw.split(',') if m.strip()]
        # Merge universals (deduped, order preserved with agent's own first)
        seen = set(mcps)
        for u in universals:
            if u not in seen:
                mcps.append(u)
                seen.add(u)
        out.append(f"{cur_agent}\t{','.join(mcps)}")
        cur_agent = None
with open(dst, 'w') as f:
    f.write('\n'.join(out) + '\n')
PY
  then
    [ -n "$MCP_SCOPE_CACHE" ] && rm -f "$MCP_SCOPE_CACHE"
    echo "BLOCKED: mcp-scope cache build FAILED (cabinet/scripts/hooks/pre-tool-use.sh section 9 parsing cabinet/mcp-scope.yml). Corrupt scope loads EMPTY — MCP calls are refused until the yaml parses. Fix cabinet/mcp-scope.yml (Captain window) and retry." >&2
    exit 2
  fi

  # Resolve acting officer
  AGENT_KEY="${OFFICER:-unknown}"
  ALLOWED=$(awk -F'\t' -v a="$AGENT_KEY" '$1==a{print $2; exit}' "$MCP_SCOPE_CACHE" 2>/dev/null)
  rm -f "$MCP_SCOPE_CACHE"

  # Derive MCP server from tool_name. Formats observed:
  #   mcp__<server>__<tool>                      (e.g. mcp__notion__API-post-page)
  #   mcp__plugin_<server>_<server>__<tool>      (e.g. mcp__plugin_telegram_telegram__reply)
  #   mcp__claude_ai_<Service>__<tool>           (e.g. mcp__claude_ai_Google_Drive__authenticate)
  # Note: assumes single-token server names. Multi-word plugin names
  # (e.g. a hypothetical mcp__plugin_google_drive_google_drive__...) would
  # truncate to 'google' under current parser. None in use today.
  MCP_SERVER=$(echo "$TOOL_NAME" | awk -F'__' '{print $2}')
  case "$MCP_SERVER" in
    plugin_*) MCP_SERVER=$(echo "$MCP_SERVER" | sed 's/^plugin_//' | awk -F'_' '{print $1}') ;;
    claude_ai_*) MCP_SERVER=$(echo "$MCP_SERVER" | sed 's/^claude_ai_//' | tr '[:upper:]' '[:lower:]') ;;
  esac

  if [ -z "$ALLOWED" ]; then
    # FAIL CLOSED (audit 4c, germline window 2 2026-07-07 — was fail-warn):
    # an unset/unlisted officer identity now refuses the MCP call, matching
    # the structural plane (gen-officer-mcp-config.py boots an unknown
    # officer with an EMPTY server set) and the axes-contract doctrine.
    # Hiring flows: create-officer.sh adds the scope entry in the same run;
    # a non-officer session in this repo must export OFFICER/OFFICER_NAME
    # to a scoped identity (or the Captain adds one in an unlock window).
    echo "BLOCKED: mcp-scope — officer '$AGENT_KEY' has no entry in cabinet/mcp-scope.yml; unknown/unlisted identity fails CLOSED (audit 4c). Refusing '$MCP_SERVER' call. Add the officer to cabinet/mcp-scope.yml (Captain unlock window) or run under a scoped OFFICER identity." >&2
    exit 2
  else
    # Check membership
    if ! echo ",$ALLOWED," | grep -qi ",${MCP_SERVER}," ; then
      echo "BLOCKED: MCP scope check — officer '$OFFICER' is not scoped for MCP server '$MCP_SERVER'. Allowed: $ALLOWED. Edit cabinet/mcp-scope.yml to grant access." >&2
      exit 2
    fi
  fi
fi

# ============================================================
# 10. CABINET MCP INTER-CABINET TRUST POLICY (Phase 2 CP4)
# ============================================================
# When a tool call targets the Cabinet MCP (mcp__cabinet__*) AND crosses
# Cabinets (send_message / request_handoff), enforce trust policy from
# instance/config/peers.yml:
#   - target peer must exist in peers.yml
#   - consented_by_captain must be true
#   - the tool must be in that peer's allowed_tools list
#
# Cache: rebuilt from source into a private per-invocation mktemp (peer_id<TAB>
# consented<TAB>allowed_tools_csv) on EVERY call — never persisted (Finding B).
#
# Tools that DON'T cross Cabinets (local self-query): identify, presence,
# availability. No peer check for those.

PEERS_FILE="$CABINET_ROOT/instance/config/peers.yml"

if [ -f "$PEERS_FILE" ] && echo "$TOOL_NAME" | grep -q '^mcp__cabinet__'; then
  # SECURITY (Finding B, C17 audit): recompute from source every call into a
  # private per-invocation mktemp; never trust a persisted /tmp cache (same-uid
  # poisonable). A build/mktemp failure leaves the table empty, so the peer
  # checks below refuse the cross-Cabinet call (fail-closed).
  PEERS_CACHE=$(mktemp "${TMPDIR:-/tmp}/cabinet-peers.XXXXXX" 2>/dev/null)
  if [ -n "$PEERS_CACHE" ]; then
    python3 - "$PEERS_FILE" "$PEERS_CACHE" <<'PY' 2>/dev/null || true
import re, sys
src, dst = sys.argv[1], sys.argv[2]
peers = {}
current = None
last_list = None
for line in open(src):
    line = line.rstrip()
    if not line or line.lstrip().startswith('#'):
        continue
    if re.match(r'^peers:\s*$', line):
        continue
    m = re.match(r'^  ([A-Za-z][A-Za-z0-9_-]*):\s*$', line)
    if m:
        current = m.group(1); peers[current] = {}; last_list = None; continue
    if current is None:
        continue
    mk = re.match(r'^\s{4,}([a-z_]+):\s*(.*)$', line)
    if mk:
        k, v = mk.group(1), mk.group(2).strip().strip('"\'')
        if v.startswith('[') and v.endswith(']'):
            peers[current][k] = [x.strip() for x in v[1:-1].split(',') if x.strip()]
            last_list = k
        elif v.lower() in ('true', 'false'):
            peers[current][k] = v.lower() == 'true'; last_list = None
        elif v == '':
            if k == 'allowed_tools':
                peers[current][k] = peers[current].get(k, []); last_list = k
            else:
                peers[current][k] = ''; last_list = None
        elif v:
            peers[current][k] = v; last_list = None
    elif last_list is not None:
        lm = re.match(r'^\s{4,}- (.+)$', line)
        if lm:
            peers[current].setdefault(last_list, []).append(lm.group(1).strip().strip('"\''))
with open(dst, 'w') as f:
    for pid, p in peers.items():
        consented = 'true' if p.get('consented_by_captain') else 'false'
        tools = ','.join(p.get('allowed_tools', []))
        f.write(f"{pid}\t{consented}\t{tools}\n")
PY
  fi

  CABINET_TOOL=$(echo "$TOOL_NAME" | sed 's/^mcp__cabinet__//')

  case "$CABINET_TOOL" in
    send_message|request_handoff)
      TARGET_PEER=$(echo "$TOOL_INPUT" | jq -r '.to_cabinet // empty' 2>/dev/null)
      if [ -z "$TARGET_PEER" ]; then
        echo "BLOCKED: Cabinet MCP $CABINET_TOOL call missing to_cabinet parameter." >&2
        exit 2
      fi
      PEER_LINE=$(awk -F'\t' -v p="$TARGET_PEER" '$1==p{print; exit}' "$PEERS_CACHE" 2>/dev/null)
      if [ -z "$PEER_LINE" ]; then
        echo "BLOCKED: peer '$TARGET_PEER' not declared in instance/config/peers.yml." >&2
        exit 2
      fi
      CONSENTED=$(echo "$PEER_LINE" | cut -f2)
      ALLOWED=$(echo "$PEER_LINE" | cut -f3)
      if [ "$CONSENTED" != "true" ]; then
        echo "BLOCKED: peer '$TARGET_PEER' has consented_by_captain=false. Flip to true in peers.yml after Captain provisions the peer." >&2
        exit 2
      fi
      if ! echo ",$ALLOWED," | grep -q ",$CABINET_TOOL," ; then
        echo "BLOCKED: peer '$TARGET_PEER' allowed_tools does not include '$CABINET_TOOL'. Allowed: $ALLOWED." >&2
        exit 2
      fi
      ;;
  esac
  [ -n "$PEERS_CACHE" ] && rm -f "$PEERS_CACHE"
fi

exit 0
