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

REDIS_URL="${REDIS_URL:-redis://redis:6379}"
REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)

# ============================================================
# 1. KILL SWITCH CHECK
# ============================================================
KILLSWITCH=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET cabinet:killswitch 2>/dev/null)
if [ "$KILLSWITCH" = "active" ]; then
  # Allow the command that deactivates the kill switch
  if [ "$TOOL_NAME" = "Bash" ]; then
    CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null)
    case "$CMD" in
      *"DEL cabinet:killswitch"*|*"del cabinet:killswitch"*)
        exit 0
        ;;
    esac
  fi
  echo "KILL SWITCH ACTIVE — all operations halted by Captain. Send /resume to deactivate." >&2
  exit 2
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
# written by stop-hook.sh from API usage × Opus 4.7 pricing. Legacy
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
SPENDING_CONFIG_CACHE="/tmp/cabinet-spending-limits.tsv"
PLATFORM_YML="/opt/founders-cabinet/instance/config/platform.yml"
FRAMEWORK_DEFAULTS_YML="/opt/founders-cabinet/framework/defaults/spending-limits.yml"

# Rebuild cache when either yaml has been touched since last build, the
# cache is missing, OR a yaml that was present at last rebuild has been
# removed (marker file tracks instance presence — without it a deleted
# platform.yml would keep stale instance values in cache indefinitely).
# Instance wins; framework defaults fill the gaps.
_REBUILD=0
_INSTANCE_MARKER="${SPENDING_CONFIG_CACHE}.instance-exists"
if [ ! -f "$SPENDING_CONFIG_CACHE" ]; then
  _REBUILD=1
else
  [ -f "$PLATFORM_YML" ] && [ "$PLATFORM_YML" -nt "$SPENDING_CONFIG_CACHE" ] && _REBUILD=1
  [ -f "$FRAMEWORK_DEFAULTS_YML" ] && [ "$FRAMEWORK_DEFAULTS_YML" -nt "$SPENDING_CONFIG_CACHE" ] && _REBUILD=1
  # yaml disappearance: marker says it existed last time, now it doesn't
  [ -f "$_INSTANCE_MARKER" ] && [ ! -f "$PLATFORM_YML" ] && _REBUILD=1
fi

if [ "$_REBUILD" = "1" ]; then
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
    # Parser crashed (missing python3, broken yaml, permissions on /tmp,
    # whatever). Fail-open with warn — silent-brick is never acceptable
    # (FW-002 contract d).
    echo "pre-tool-use: WARN spending-limits parser failed, using hardcoded framework defaults (\$75/officer, \$300/cabinet)" >&2
  fi
  # Track whether platform.yml existed at the time of this rebuild so a
  # subsequent deletion triggers rebuild instead of leaving stale values.
  if [ -f "$PLATFORM_YML" ]; then
    touch "$_INSTANCE_MARKER" 2>/dev/null
  else
    rm -f "$_INSTANCE_MARKER" 2>/dev/null
  fi
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
# 3. TYPED POLICY ENGINE (replaces bash regex sections 3-5)
# ============================================================
# Sections 3 (prohibited actions), 4 (codebase ownership), and
# 5 (constitution protection) are now evaluated by the typed
# Python policy engine. The engine uses shlex to parse shell
# commands and detect prohibited binaries, handling all bypass
# patterns (eval wrapping, bash -c, quote splicing, heredoc
# injection, brace expansion, full-path invocation) that previously
# required 600+ lines of regex.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../../.." 2>/dev/null && pwd)}"
POLICY_ENGINE="$CABINET_ROOT/cabinet/scripts/lib/policy_engine.py"

if [ -f "$POLICY_ENGINE" ]; then
  POLICY_RESULT=$(echo "$HOOK_INPUT" | OFFICER="$OFFICER" CABINET_ROOT="$CABINET_ROOT" python3 "$POLICY_ENGINE" 2>&1)
  POLICY_EXIT=$?
  if [ "$POLICY_EXIT" -eq 2 ]; then
    echo "$POLICY_RESULT" >&2
    exit 2
  fi
else
  echo "pre-tool-use: WARN policy engine not found at $POLICY_ENGINE, skipping typed policy checks" >&2
fi

# ============================================================
# 6-7 PREPROCESSING — variables needed by Layer 1 and CI Green gates
# ============================================================
# Sections 6-7 are stateful workflow gates that use Redis keys
# (reviewed/ci-green). They still use regex for command-position
# detection because they need to distinguish "real git push" from
# "git push mentioned inside a commit message." The preprocessing
# variables below support that detection.
if [ "$TOOL_NAME" = "Bash" ]; then
  _L1_CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null)
  CMD_NORM=$(printf '%s' "$_L1_CMD" | sed -e 's/\\"/"/g' -e "s/\\\\'/'/g")
  CMD_UNQUOTED=$(printf '%s' "$CMD_NORM" \
    | sed -e "s/\\\$'\\([^']*\\)'/\\1/g" -e "s/'\\([^']*\\)'/\\1/g" -e 's/"\([^"$`]*\)"/\1/g' \
    | perl -0777 -pe 's/<<([A-Za-z_]\w*)\n.*?\n\1(?=\n|\z)//gs' 2>/dev/null)
  CMD_MASKED=$(printf '%s' "$CMD_NORM" \
    | sed -e "s/\\\$'[^']*'/\$'x'/g" -e "s/'[^']*'/'x'/g" -e 's/"[^"$`]*"/"x"/g')
  HAS_SPLICE=0
  if echo "$CMD_MASKED" | grep -qE "(^|[;&|({)}\`!]|&&|\|\|)[[:space:]]*([A-Za-z_]+['\"\`]|['\"\`][A-Za-z_])"; then
    HAS_SPLICE=1
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
# Action regex covers BOTH `main` (product repo) and `master`
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
      echo "CI GREEN GATE: Run 'bash /opt/founders-cabinet/cabinet/scripts/verify-deploy.sh ci <commit-sha>' and confirm CI is green before merging. After CI passes, run: redis-cli -h redis -p 6379 SET cabinet:layer1:cto:ci-green 1 EX 300" >&2
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
# Cache layer: /tmp/cabinet-context-slugs.tsv (slug<TAB>capacity), rebuilt
# when any yaml in the contexts dir is newer than the cache. Keeps the
# hook fast (~1ms) on every call.

CONTEXTS_DIR="/opt/founders-cabinet/instance/config/contexts"
SLUG_CACHE="/tmp/cabinet-context-slugs.tsv"

if [ -d "$CONTEXTS_DIR" ]; then
  # Rebuild cache if stale or missing. Dir mtime covers both file modifications
  # AND deletions (Linux bumps dir mtime on unlink); file-newer covers individual
  # edits. Combined: cache reflects current yaml set even after a deletion.
  if [ ! -f "$SLUG_CACHE" ] \
     || [ -n "$(find "$CONTEXTS_DIR" -maxdepth 0 -newer "$SLUG_CACHE" 2>/dev/null)" ] \
     || [ -n "$(find "$CONTEXTS_DIR" -maxdepth 1 -name '*.yml' -newer "$SLUG_CACHE" 2>/dev/null)" ]; then
    : > "$SLUG_CACHE"
    for f in "$CONTEXTS_DIR"/*.yml "$CONTEXTS_DIR"/*.yaml; do
      [ -f "$f" ] || continue
      # Strip inline # comments, quotes, and surrounding whitespace before capture.
      slug=$(awk -F: '/^slug:/{sub(/[ \t]*#.*$/,"",$2); gsub(/^[ \t]+|[ \t\r\n]+$/,"",$2); gsub(/^["'"'"']|["'"'"']$/,"",$2); print $2; exit}' "$f")
      cap=$(awk -F: '/^capacity:/{sub(/[ \t]*#.*$/,"",$2); gsub(/^[ \t]+|[ \t\r\n]+$/,"",$2); gsub(/^["'"'"']|["'"'"']$/,"",$2); print $2; exit}' "$f")
      [ -n "$slug" ] && [ -n "$cap" ] && printf "%s\t%s\n" "$slug" "$cap" >> "$SLUG_CACHE"
    done
  fi

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
    # OFFICER_CAPACITY defaults to 'work' for the work preset. Phase 2 will read
    # from preset.yml or per-officer config, not hardcoded default.
    OFFICER_CAPACITY="${OFFICER_CAPACITY:-work}"
    if [ "$OFFICER_CAPACITY" != "$CTX_CAPACITY" ]; then
      echo "BLOCKED: capacity_check failed — officer '$OFFICER' has capacity '$OFFICER_CAPACITY' but context_slug '$SLUG_IN_CALL' has capacity '$CTX_CAPACITY'. Cross-capacity writes are forbidden." >&2
      exit 2
    fi
  fi
fi

# ============================================================
# 9. MCP SCOPE ENFORCEMENT (Phase 1 CP5)
# ============================================================
# cabinet/mcp-scope.yml declares which MCP servers each hired agent may
# reach. On every MCP tool call (tool_name starts with 'mcp__'), the
# hook derives the server name and rejects the call if it is not in the
# acting officer's scope.
#
# Cache: /tmp/cabinet-mcp-scope.tsv (officer\tcsv-of-mcps), rebuilt when
# the yaml is newer than the cache. Same pattern as context cache.

MCP_SCOPE_FILE="/opt/founders-cabinet/cabinet/mcp-scope.yml"
MCP_SCOPE_CACHE="/tmp/cabinet-mcp-scope.tsv"

if [ -f "$MCP_SCOPE_FILE" ] && echo "$TOOL_NAME" | grep -q '^mcp__'; then
  # Rebuild cache if stale. Cache format per line:
  #   agent\tmcp1,mcp2,...
  # Universals from yaml's top-level 'universal:' list are merged into every
  # agent's set at build time, so the hook's membership check stays a single
  # string lookup per tool call.
  if [ ! -f "$MCP_SCOPE_CACHE" ] || [ "$MCP_SCOPE_FILE" -nt "$MCP_SCOPE_CACHE" ]; then
    python3 - "$MCP_SCOPE_FILE" "$MCP_SCOPE_CACHE" <<'PY' 2>/dev/null || true
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
  fi

  # Resolve acting officer
  AGENT_KEY="${OFFICER:-unknown}"
  ALLOWED=$(awk -F'\t' -v a="$AGENT_KEY" '$1==a{print $2; exit}' "$MCP_SCOPE_CACHE" 2>/dev/null)

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
    # Unknown officer — fail-warn (not fail-open, not fail-closed). Hard block
    # would brick hiring flows when a new officer starts before mcp-scope.yml
    # is updated; silent allow hides configuration drift. Warn + allow lets
    # the call through while surfacing the gap for the retro.
    echo "WARN: mcp-scope — officer '$AGENT_KEY' has no entry in cabinet/mcp-scope.yml. Allowing '$MCP_SERVER' call. Add an entry to enforce scope." >&2
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
# Cache: /tmp/cabinet-peers.tsv (peer_id<TAB>consented<TAB>allowed_tools_csv)
# rebuilt when peers.yml is newer than cache (same pattern as CP2 contexts).
#
# Tools that DON'T cross Cabinets (local self-query): identify, presence,
# availability. No peer check for those.

PEERS_FILE="/opt/founders-cabinet/instance/config/peers.yml"
PEERS_CACHE="/tmp/cabinet-peers.tsv"

if [ -f "$PEERS_FILE" ] && echo "$TOOL_NAME" | grep -q '^mcp__cabinet__'; then
  # Rebuild cache if stale
  if [ ! -f "$PEERS_CACHE" ] || [ "$PEERS_FILE" -nt "$PEERS_CACHE" ]; then
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
fi

exit 0
