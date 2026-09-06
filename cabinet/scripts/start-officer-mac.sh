#!/bin/bash
# start-officer-mac.sh — Start an Officer Claude Code session on Mac native.
#
# Invoked by LaunchAgent (com.cabinet.officer.<role>.plist). Reads officer
# capabilities, builds the right Claude Code invocation flags (telegram_bot
# gate + cua-driver MCP overlay + per-officer structural MCP scoping from
# cabinet/mcp-scope.yml via gen-officer-mcp-config.py → --strict-mcp-config
# + --settings overlay, audit 2026-07-07 #4), starts a detached tmux session,
# and launches claude inside.
#
# Per Spec 059 v1.1 Checkpoint 2.7 + CTO v1.1 #4 (tmux new-session -d) + Spec
# 060 v1.1 (telegram_bot capability gate) + Spec 061 v1.2 (drives_computer
# capability gate with jq deep-merge per CTO v1.1 #1 CRITICAL).
#
# Usage (LaunchAgent calls this):
#   /bin/bash $REPO_ROOT/cabinet/scripts/start-officer-mac.sh <officer> [--dry-run]
#
# --dry-run (alias for CABINET_MAC_DRY_RUN=1): print the assembled claude
# command + native-agent/lane facts and exit 0 — NO tmux, NO redis, NO boot.
#
# CABINET_MAC_TEST_ASSEMBLY=1 (test hook, no flag): --dry-run PLUS the runtime
# constitution assembly that --dry-run skips, so cabinet/scripts/test-mac-dry-run.sh
# can reach the assembly failure branch — which REFUSES the boot (exit 78,
# like every other assembly failure here) rather than starting an officer on a
# constitution nothing can vouch for.
# Unknown args are REJECTED (exit 64): this script's real path kills and
# replaces the officer's live tmux session, so a mistyped flag must never
# silently fall through to the real boot (hatch-rehearsal finding 2026-07-07:
# a guessed `cos --dry-run` from a scratch clone killed the live Chair).

set -euo pipefail

usage() {
  echo "Usage: start-officer-mac.sh <officer> [--dry-run]" >&2
}

OFFICER=""
for _arg in "$@"; do
  case "$_arg" in
    --dry-run) CABINET_MAC_DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    -*)
      echo "[ERROR] start-officer-mac.sh: unknown flag '$_arg' — refusing (the real" >&2
      echo "[ERROR]   boot path replaces the live officer session; flags are never ignored)." >&2
      usage; exit 64 ;;
    *)
      if [ -z "$OFFICER" ]; then
        OFFICER="$_arg"
      else
        echo "[ERROR] start-officer-mac.sh: unexpected extra argument '$_arg'" >&2
        usage; exit 64
      fi ;;
  esac
done
if [ -z "$OFFICER" ]; then
  usage; exit 64
fi

# CABINET_MAC_TEST_ASSEMBLY=1 — a dry render that deliberately does NOT skip the
# runtime-constitution assembly block (the ONE thing CABINET_MAC_DRY_RUN=1 skips
# wholesale). It exists because that block's failure branch was otherwise
# untestable: no test could reach it, and it shipped fail-OPEN — booting an
# officer on an unverified constitution — with nothing able to see that.
# Everything downstream of the assembly behaves exactly like --dry-run: no tmux,
# no redis, no claude, no writes to the live per-officer caches. Point
# CABINET_RUNTIME_DIR at a scratch dir (load-preset.sh honours it) so a test run
# cannot clobber the live /tmp/cabinet-runtime bundle.
if [ "${CABINET_MAC_TEST_ASSEMBLY:-0}" = "1" ]; then
  CABINET_MAC_DRY_RUN=1
fi
REPO_ROOT="${CABINET_SOURCE_REPO:-${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}}"
export CABINET_SOURCE_REPO="$REPO_ROOT"
export CABINET_ROOT="$REPO_ROOT"
OFFICER_ENV_LIB="$REPO_ROOT/cabinet/scripts/lib/officer-env.sh"
if [ ! -f "$OFFICER_ENV_LIB" ]; then
  echo "[ERROR] start-officer-mac.sh: missing clean-environment library: $OFFICER_ENV_LIB" >&2
  exit 78
fi
# shellcheck source=lib/officer-env.sh
source "$OFFICER_ENV_LIB"
officer_env_scrub_authority

# Resolve the sticky observe posture BEFORE credential projection. The env
# parser uses this effective posture to subtract CUA/CUA-driver credentials,
# matching the later structural removal of the computer-control overlay.
export CABINET_OBSERVE_ONLY=0
OBSERVE_STATE="$(bash "$REPO_ROOT/cabinet/scripts/observe-only.sh" status)" || {
  echo "[ERROR] start-officer-mac.sh: invalid observe-only marker — refusing officer boot" >&2
  exit 78
}
if [ "$OBSERVE_STATE" = active ]; then
  export CABINET_OBSERVE_ONLY=1
  export CABINET_ENV=dev
fi
LOGS_DIR="$HOME/Library/Logs/cabinet"
SESSION_NAME="officer-$OFFICER"
# Fleet default: Opus 4.8 1M (Fable 5 is access-gated on this account, 2026-06-23; Captain-set).
# Override per-officer via CABINET_MODEL=... (e.g. claude-sonnet-4-6 to downgrade, or
# claude-fable-5[1m] once Fable access returns).
MODEL="${CABINET_MODEL:-claude-opus-4-8[1m]}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

mkdir -p "$LOGS_DIR"

cd "$REPO_ROOT"

# Load only the reviewed officer environment.  cabinet/.env also contains the
# dashboard password used for Captain session/verdict signatures; sourcing the
# whole file collapsed that authority boundary.  The parser never executes the
# dotenv file and the final Claude command runs under env -i.
if [ -f "cabinet/.env" ]; then
  officer_env_load_file "$REPO_ROOT/cabinet/.env" "$OFFICER"
else
  echo "[WARN] start-officer-mac.sh: cabinet/.env not found at $REPO_ROOT/cabinet/.env — officer will boot without secrets" >&2
fi

# Reconcile the deployment-wide egress guard before projecting its proxy env.
# A real launch fails closed when enforcement is requested but the proxy is not
# verified.  The later Seatbelt profile uses EGRESS_KERNEL_ENFORCED to block
# raw external TCP/UDP as well as proxy-bypassing clients.
EGRESS_GUARD="$REPO_ROOT/cabinet/scripts/egress-guard.sh"
EGRESS_ENFORCE=0
EGRESS_ENV_FILE=""
EGRESS_KERNEL_ENFORCED=0
if [ ! -f "$EGRESS_GUARD" ]; then
  if [ "${CABINET_MAC_DRY_RUN:-0}" != "1" ]; then
    echo "[ERROR] start-officer-mac.sh: egress guard missing — refusing officer boot" >&2
    exit 78
  fi
elif [ "${CABINET_MAC_DRY_RUN:-0}" != "1" ]; then
  if ! bash "$EGRESS_GUARD" apply >&2; then
    echo "[ERROR] start-officer-mac.sh: egress reconciliation failed — refusing officer boot" >&2
    exit 78
  fi
fi
if [ -f "$EGRESS_GUARD" ]; then
  # DRY-RUN ASYMMETRY FIX (fresh-hatch blocker, 2026-07-26).  A dry render
  # deliberately SKIPS `apply` above — and `apply` is the ONLY thing that ever
  # creates $STATE_DIR/egress (egress-guard.sh acquire_apply_lock/install_enforce).
  # Demanding an attested live proxy here therefore required the postcondition
  # of a step this very block had just chosen not to run, so `hatch.sh`'s
  # proof-c1 ("officer boot command assembly, zero side effects") died on every
  # fresh hatch with "FAIL-CLOSED — runtime state directory is absent".
  # The guard is CORRECT and is untouched: a REAL boot still refuses (exit 78).
  # Only the dry render tolerates an unattested state — exactly as the
  # `elif [ ... != "1" ]` arm eight lines below ALREADY does for the very next
  # egress precondition (proxy env absent).  Deliberately NOT the Linux twin's
  # shape (start-officer.sh:105 skips the whole block in dry-run): that would
  # blind the dogfood sensor, which requires `egress_enforced=1` to still
  # appear in DRY-RUN output after a manual `egress-guard.sh apply`
  # (docs/runbooks/observe-only-dogfood.md).  So the call is still made and
  # still reports 1 when enforcement really is live; only its FAILURE is
  # downgraded, and only in dry-run.
  if EGRESS_RUNTIME="$(bash "$EGRESS_GUARD" runtime-state)"; then
    IFS=$'\t' read -r EGRESS_ENFORCE EGRESS_ENV_FILE <<< "$EGRESS_RUNTIME"
  elif [ "${CABINET_MAC_DRY_RUN:-0}" = "1" ]; then
    # Honest, not silent: EGRESS_ENFORCE/EGRESS_ENV_FILE keep their safe
    # defaults (0 / empty), so egress_enforced=0 is reported rather than a
    # reassuring fake 1.
    echo "[WARN] start-officer-mac.sh: egress runtime state unattested (no proxy applied) — dry render continues, egress_enforced=0" >&2
  else
    echo "[ERROR] start-officer-mac.sh: cannot resolve egress runtime state — refusing officer boot" >&2
    exit 78
  fi
  if [ "$EGRESS_ENFORCE" = "1" ]; then
    EGRESS_KERNEL_ENFORCED=1
    if [ -f "$EGRESS_ENV_FILE" ]; then
      officer_env_load_file "$EGRESS_ENV_FILE" "$OFFICER"
    elif [ "${CABINET_MAC_DRY_RUN:-0}" != "1" ]; then
      echo "[ERROR] start-officer-mac.sh: egress is enforced but proxy env is absent — refusing officer boot" >&2
      exit 78
    fi
  fi
fi

# Assemble runtime constitution + safety + preset (idempotent).
# Audit-fix 2026-05-23: capture exit status via PIPESTATUS — `tail` always exits 0.
# Dry-run skip: in CABINET_MAC_DRY_RUN=1 the fake repo has no load-preset / check-deps;
# we only need to materialise CLAUDE_CMD so tests can grep it. Side-effecting calls
# are skipped — the dry-run gate exits 0 long before tmux/redis/boot logic anyway.
# CABINET_MAC_TEST_ASSEMBLY=1 opts back IN to this block (with load-preset stubbed
# and CABINET_RUNTIME_DIR redirected) so the fail-closed branch below is reachable
# by a test; without it the branch has no sensor at all.
if [ "${CABINET_MAC_DRY_RUN:-0}" != "1" ] || [ "${CABINET_MAC_TEST_ASSEMBLY:-0}" = "1" ]; then
  # `|| LOAD_PRESET_RC=...` so `set -euo pipefail` does not exit at THIS pipeline
  # before the rc handler runs: pipefail makes a failed load-preset non-zero, and
  # bare (no `||`) that aborts the whole boot here — the PIPESTATUS capture and
  # the rc branch below were dead code. The `||` RHS is an assignment,
  # so PIPESTATUS still reflects the failed pipeline (load-preset's rc, not tail's).
  LOAD_PRESET_RC=0
  bash cabinet/scripts/load-preset.sh 2>&1 | tail -3 >&2 || LOAD_PRESET_RC="${PIPESTATUS[0]}"
  if [ "$LOAD_PRESET_RC" -ne 0 ]; then
    # FAIL CLOSED (2026-09-06). This branch used to log and CONTINUE ("let officer
    # try to boot anyway"), which started a worker whose constitution + safety
    # boundaries were of unknown provenance — while every sibling assembly failure
    # in this script already refuses (egress reconciliation, security paths,
    # sandbox, broker, launcher). An officer running on instructions nobody can
    # vouch for is strictly worse than an officer that is down: launchd KeepAlive
    # retries, and a down officer is visible.
    #
    # NOT "keep the last verified bundle": that path was considered and rejected
    # because nothing here can prove the retained files are the RIGHT ones.
    # $CABINET_RUNTIME_DIR (default /tmp/cabinet-runtime) holds constitution.md and
    # safety-boundaries.md with no manifest, no framework/preset revision stamp and
    # no completion marker; load-preset.sh mv's them into place mid-run and keeps
    # going (schemas, .claude/agents population), so both files can be present and
    # current while assembly failed AFTER them, or present and STALE — from an
    # earlier commit or a DIFFERENT preset — when it failed BEFORE them. The only
    # in-band signal is the "# Preset Addendum: <slug>" heading, which says nothing
    # about the framework base, the safety file or the agent set. And the directory
    # is a predictable path under /tmp, so "the files look right" is not a property
    # this script can safely trust. Presence is not completeness (the sensor-vs-
    # control failure class), so the honest answer is to refuse.
    cat >&2 <<PRESETERR
[ERROR] start-officer-mac.sh: load-preset.sh exited $LOAD_PRESET_RC — the runtime
[ERROR]   constitution + safety bundle in ${CABINET_RUNTIME_DIR:-/tmp/cabinet-runtime} is
[ERROR]   incomplete or stale, and cannot be proven complete for this officer.
[ERROR]   REFUSING to boot '$OFFICER' — a worker running on unverified instructions is
[ERROR]   worse than one that is down.
[ERROR]   Recovery:
[ERROR]     1. bash $REPO_ROOT/cabinet/scripts/load-preset.sh   (shows the real error)
[ERROR]     2. check the active preset named in $REPO_ROOT/instance/config/active-preset
[ERROR]        resolves to a populated $REPO_ROOT/presets/<slug>/ with a preset.yml
[ERROR]     3. see docs/how-your-cabinet-is-governed.md ("The constitution and presets")
[ERROR]   launchd KeepAlive will retry; the officer stays down until assembly passes.
PRESETERR
    exit 78
  fi

  # Dep audit — non-blocking, logs any missing tools to stderr
  bash "$REPO_ROOT/cabinet/scripts/check-deps.sh" 2>&1 | tee -a "$LOGS_DIR/officer-$OFFICER.out.log" || true
fi

# ===========================================================
# Capability resolution (Spec 060 + Spec 061 capability gates)
# ===========================================================
# Returns "true" if officer has the capability, "false" otherwise
read_capability() {
  local role="$1" cap="$2"
  if grep -E "^${role}:${cap}$" cabinet/officer-capabilities.conf > /dev/null 2>&1; then
    echo "true"
  else
    echo "false"
  fi
}

HAS_TELEGRAM=$(read_capability "$OFFICER" "telegram_bot")
HAS_CUA_DRIVER=$(read_capability "$OFFICER" "drives_computer")
if [ "$CABINET_OBSERVE_ONLY" = 1 ]; then
  HAS_CUA_DRIVER=false
fi

# ===========================================================
# MCP config — Mac base + (if drives_computer) overlay
# ===========================================================
# Per Spec 061 v1.1 CTO #1 CRITICAL: jq DEEP-MERGE preserving framework mcpServers.
# Shallow merge would silently overwrite framework servers (notion/neon/make)
# with overlay-only. (library deregistered 2026-07-16 — Library retirement.)
# Audit-fix 2026-05-23: base is .mcp.json.mac-native (Mac-resolved paths + localhost
# Redis), NOT .mcp.json (which has Docker DNS + /opt paths from Hetzner). Mac-side
# always uses the .mac-native base. Audit-fix: umask 077 on /tmp output (secret hygiene).
MCP_BASE=".mcp.json.mac-native"
[ ! -f "$MCP_BASE" ] && MCP_BASE=".mcp.json"   # graceful fallback if mac-native variant missing

MERGED_MCP_PATH="$HOME/Library/Caches/cabinet/merged-mcp-${OFFICER}.json"
if [ "${CABINET_MAC_DRY_RUN:-0}" = "1" ]; then
  # --dry-run must write NOTHING to the live cache (contract at the dry-run gate
  # below): route the merge output to a throwaway temp file so a rehearsal never
  # creates/overwrites the live merged-mcp cache (or its Caches/ dir), which a
  # concurrent real boot could otherwise pick up mid-write.
  MERGED_MCP_PATH="$(mktemp -t "cabinet-dryrun-mcp-${OFFICER}.XXXXXX")"
fi
mkdir -p "$(dirname "$MERGED_MCP_PATH")"

# Build the MCP overlay stack (highest precedence last):
#   base                                .mcp.json.mac-native (curated core)
#   + instance/config/extra-mcps.json   captain-declared extras (ALL officers;
#                                       rendered by install-extensions.sh)
#   + per-officer cua overlay           instance/agents/<o>/mcp.json when the
#                                       deployment provides one, else the shipped
#                                       template cabinet/mcp-overlays/cua-driver.mcp.json
# Deep-merge preserves base mcpServers; later layers add/override by key.
# R128 (egg plan 2026-07-07): instance/agents/ is instance payload and leaves
# the egg at packaging — cabinet/mcp-overlays/ is the capability's shipped
# template home, so a fresh hatch's drives_computer officers keep computer-use
# wiring instead of silently losing it. Instance overlay wins when present.
EXTRA_MCPS="instance/config/extra-mcps.json"
PER_OFFICER_MCP="instance/agents/$OFFICER/mcp.json"
CUA_TEMPLATE_MCP="cabinet/mcp-overlays/cua-driver.mcp.json"

MCP_LAYERS=("$MCP_BASE")
[ -f "$EXTRA_MCPS" ] && MCP_LAYERS+=("$EXTRA_MCPS")
if [ "$HAS_CUA_DRIVER" = "true" ]; then
  if [ -f "$PER_OFFICER_MCP" ]; then
    MCP_LAYERS+=("$PER_OFFICER_MCP")
  elif [ -f "$CUA_TEMPLATE_MCP" ]; then
    MCP_LAYERS+=("$CUA_TEMPLATE_MCP")
  fi
fi

if [ "${#MCP_LAYERS[@]}" -gt 1 ]; then
  # jq reduce: fold each overlay's mcpServers into the accumulator.
  # Final pass strips pseudo-server keys starting with "_" (comment/doc
  # entries like "_comment" in overlay files) — Claude Code would try to
  # boot them as real MCP servers otherwise.
  MERGE_RC=0
  ( umask 077
    jq -s 'reduce .[1:][] as $o (.[0];
             . * $o | .mcpServers = (.mcpServers + ($o.mcpServers // {})))
           | .mcpServers |= with_entries(select(.key|startswith("_")|not))' \
       "${MCP_LAYERS[@]}" > "$MERGED_MCP_PATH"
  ) || MERGE_RC=$?
  if [ "$MERGE_RC" -ne 0 ]; then
    # A layer is corrupt/truncated JSON (install-extensions.sh writes
    # extra-mcps.json non-atomically). Do NOT let `set -e` crash-loop the officer
    # at the jq merge — fall back to the curated base config (the designed
    # fail-closed boot, minus overlays) with a loud error instead of dying before
    # the fail-closed net downstream.
    echo "[ERROR] start-officer-mac.sh: MCP overlay merge failed (rc=$MERGE_RC) — a layer is likely corrupt JSON (${MCP_LAYERS[*]}). Booting on the base MCP config without overlays." >&2
    SCOPE_INPUT="$REPO_ROOT/$MCP_BASE"
  else
    SCOPE_INPUT="$MERGED_MCP_PATH"
  fi
else
  # Single layer — filter the base directly (covers both the mac-native base
  # and the bare .mcp.json fallback; the generator strips "_" pseudo-keys the
  # jq pass above would otherwise have handled).
  SCOPE_INPUT="$REPO_ROOT/$MCP_BASE"
fi

# ===========================================================
# Per-officer STRUCTURAL MCP scoping (audit 2026-07-07 #4, non-germline half)
# ===========================================================
# The merged config above is the union of every layer. Scope it DOWN to the
# officer's grant set from cabinet/mcp-scope.yml (READ-ONLY germline parse —
# gen-officer-mcp-config.py mirrors the pre-tool-use.sh §9 parser) so
# unscoped servers never even BOOT: the launch line passes the filtered
# config with --strict-mcp-config, plus a --settings overlay disabling
# enableAllProjectMcpServers so the session cannot auto-approve the project
# .mcp.json back in. (The overlay carries NO allowedMcpServers mirror:
# managed-settings-only key, unenforced from --settings, and CC 2.1.202's
# overlay schema validation of it BLOCKED officer boot — 2026-07-07
# rolling restart.) The §9 call-time
# hook stays as defense-in-depth. FAIL CLOSED: if the scope parse fails
# (missing file, unknown officer, corrupt yaml) or the generator itself
# cannot run, the officer boots with an EMPTY MCP server set + loud stderr —
# never fail open.
OFFICER_CFG_DIR="$HOME/Library/Caches/cabinet"
if [ "${CABINET_MAC_DRY_RUN:-0}" = "1" ]; then
  # Dry-run must not clobber the live per-officer cache files — generate
  # into a throwaway dir (we only need CLAUDE_CMD materialised for greps).
  OFFICER_CFG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cabinet-mcp-dryrun.XXXXXX")"
fi
mkdir -p "$OFFICER_CFG_DIR"
OFFICER_MCP_PATH="$OFFICER_CFG_DIR/officer-mcp-${OFFICER}.json"
OFFICER_SETTINGS_PATH="$OFFICER_CFG_DIR/officer-settings-${OFFICER}.json"

# Launcher INFRA pass-through (NOT capability grants — see the generator's
# docstring). redis-trigger-channel moved OUT of this pass-through into the
# scope file's `universal:` list (germline window 2, 2026-07-07 — addendum
# 4a applied), where the structural plane + hook §9 enforce it like every
# other grant. Only the cua/cua-driver overlay pair remains here: it rides
# the drives_computer capability gate that assembled the overlay above
# (proper scoping = addendum 4b, deferred). The generator IGNORES
# extra-allow when the scope parse fails, so this pass-through cannot mask
# a fail-closed boot; an empty EXTRA_ALLOW is a no-op ("" splits to []).
EXTRA_ALLOW=""
if [ "$HAS_CUA_DRIVER" = "true" ]; then
  EXTRA_ALLOW="cua,cua-driver"
fi
GEN_MCP_ARGS=(
  --officer "$OFFICER"
  --scope "$REPO_ROOT/cabinet/mcp-scope.yml"
  --input "$SCOPE_INPUT"
  --extra-allow "$EXTRA_ALLOW"
)
if [ "$CABINET_OBSERVE_ONLY" = 1 ]; then
  GEN_MCP_ARGS+=(--observe-only)
fi
GEN_MCP_ARGS+=(
  --out-mcp "$OFFICER_MCP_PATH"
  --out-settings "$OFFICER_SETTINGS_PATH"
)

if ! python3 "$REPO_ROOT/cabinet/scripts/gen-officer-mcp-config.py" \
      "${GEN_MCP_ARGS[@]}"; then
  echo "[ERROR] start-officer-mac.sh: gen-officer-mcp-config.py failed — FAIL CLOSED: booting $OFFICER with an EMPTY MCP server set" >&2
  ( umask 077
    printf '{"mcpServers":{}}\n' > "$OFFICER_MCP_PATH"
    printf '{"enableAllProjectMcpServers":false}\n' > "$OFFICER_SETTINGS_PATH"
  )
fi
MCP_FLAG="--mcp-config $OFFICER_MCP_PATH --strict-mcp-config"
SETTINGS_FLAG="--settings $OFFICER_SETTINGS_PATH"

# ===========================================================
# Telegram bot token resolution
# ===========================================================
# Lead-only (per Spec 060 v1.1): only officers with telegram_bot=true get a bot token.
# Non-Lead officers run Telegram-dark (no --channels plugin:telegram).
#
# CANONICAL env var: TELEGRAM_<OFFICER_UPPER>_TOKEN (e.g. TELEGRAM_COS_TOKEN).
# Fallbacks, tried in order, first non-empty wins:
#   1. TELEGRAM_<OFFICER_UPPER>_TOKEN       canonical
#   2. TELEGRAM_BOT_TOKEN_<OFFICER_UPPER>   legacy generator/docs name
#   3. TELEGRAM_BOT_TOKEN                   bare name — safe to inherit here
#      because this whole branch is gated on the telegram_bot capability
# Hyphenated slugs (e.g. bakery-ceo) map '-' -> '_' for the var name.
TELEGRAM_FLAG=""
if [ "$HAS_TELEGRAM" = "true" ]; then
  OFFICER_UPPER=$(echo "$OFFICER" | tr '[:lower:]-' '[:upper:]_')
  TOKEN_VAR="TELEGRAM_${OFFICER_UPPER}_TOKEN"
  ALT_TOKEN_VAR="TELEGRAM_BOT_TOKEN_${OFFICER_UPPER}"
  BOT_TOKEN="${!TOKEN_VAR:-}"
  RESOLVED_VAR="$TOKEN_VAR"
  if [ -z "$BOT_TOKEN" ]; then
    BOT_TOKEN="${!ALT_TOKEN_VAR:-}"
    RESOLVED_VAR="$ALT_TOKEN_VAR"
  fi
  if [ -z "$BOT_TOKEN" ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
    RESOLVED_VAR="TELEGRAM_BOT_TOKEN"
  fi
  if [ -n "$BOT_TOKEN" ]; then
    export TELEGRAM_BOT_TOKEN="$BOT_TOKEN"
    # Receive path: if an inbound-watchdog LaunchAgent exists for this officer, that
    # poller OWNS getUpdates — do NOT also load --channels, or two pollers on one bot
    # token fight (Telegram 409 Conflict → nothing consumes; observed 2026-06-23). The
    # officer still SENDS via framework.frontdoor.channel.send (token exported above).
    # The Channels plugin's idle-delivery is unreliable; the watchdog is the fix.
    if [ "$CABINET_OBSERVE_ONLY" = 1 ]; then
      TELEGRAM_FLAG=""
      echo "start-officer-mac.sh: $OFFICER observe-only receive is watchdog-owned — not loading --channels" >&2
    elif [ -f "$REPO_ROOT/cabinet/launchd/com.cabinet.officer.$OFFICER-inbound.plist" ]; then
      TELEGRAM_FLAG=""
      echo "start-officer-mac.sh: $OFFICER receive via inbound watchdog — not loading --channels (token resolved from \$$RESOLVED_VAR for sends)" >&2
    else
      TELEGRAM_FLAG="--channels plugin:telegram@claude-plugins-official"
      echo "start-officer-mac.sh: $OFFICER telegram token resolved from \$$RESOLVED_VAR" >&2
    fi
  else
    cat >&2 <<TOKERR
[ERROR] start-officer-mac.sh: officer '$OFFICER' has the telegram_bot capability
[ERROR]   but NO bot token candidate is set. Tried, in order:
[ERROR]     1. $TOKEN_VAR        (canonical)
[ERROR]     2. $ALT_TOKEN_VAR    (legacy generator name)
[ERROR]     3. TELEGRAM_BOT_TOKEN          (bare fallback)
[ERROR]   Set the canonical var in cabinet/.env:
[ERROR]     $TOKEN_VAR=<bot token from BotFather>
[ERROR]   Continuing WITHOUT --channels — this officer boots Telegram-dark
[ERROR]   until the token is set and the officer is restarted.
TOKERR
  fi
fi

# Export OFFICER_NAME for hooks (stop-hook.sh + post-tool-use.sh etc.)
export OFFICER_NAME="$OFFICER"
export CABINET_OFFICER="$OFFICER"

# ===========================================================
# CABINET_LANE — load-bearing lane dimension [FIX-4]
# ===========================================================
# framework/authority/lane.py resolve_lane() reads CABINET_LANE FIRST as the
# lane of the F+A cell tuple (officer, lane, action_type). The Mac officer is
# single-project-per-LaunchAgent (no --project flag), so its lane source is
# instance/config/active-project.txt (the same active-context machinery the
# Linux script's legacy mode uses). Read defensively + whitespace-strip, then
# validate against the slug allowlist (mirrors start-officer.sh FW-073 regex) so
# a malformed active-project.txt cannot inject into the exported value. Export
# ONLY when a valid slug exists — an empty CABINET_LANE would shadow PROJECT in
# resolve_lane; omitting it lets resolve_lane fall through to PROJECT then None
# (fail-safe → unmeasured cell, propose-only at the gate).
CABINET_LANE_SLUG=""
if [ -f "$REPO_ROOT/instance/config/active-project.txt" ]; then
  CABINET_LANE_SLUG=$(tr -d '[:space:]' < "$REPO_ROOT/instance/config/active-project.txt" 2>/dev/null)
fi
if [ -n "$CABINET_LANE_SLUG" ] && [[ "$CABINET_LANE_SLUG" =~ ^[a-z0-9][a-z0-9-]*$ ]] && [ "${#CABINET_LANE_SLUG}" -le 32 ]; then
  export CABINET_LANE="$CABINET_LANE_SLUG"
else
  # Scrub any inherited/stale value so a non-conforming active-project.txt or a
  # poisoned parent env can't silently shadow PROJECT/None in resolve_lane.
  unset CABINET_LANE
  CABINET_LANE_SLUG=""
fi

# Audit-fix 2026-05-23: per memory feedback_telegram_state_dir.md, each officer
# needs a distinct TELEGRAM_STATE_DIR or Telegram polling state collides across
# officers. Linux start-officer.sh sets this at line 280; mirror on Mac.
export TELEGRAM_STATE_DIR="$HOME/Library/Application Support/cabinet/telegram-state/$OFFICER"
mkdir -p "$TELEGRAM_STATE_DIR"

# ===========================================================
# Native --agent probe (CC v2.1.150+: claude --agent <name> runs the whole
# session as that officer; supersedes the legacy boot-prompt-only approach).
# ===========================================================
# Gated by:
#   * CABINET_USE_NATIVE_AGENT (default on; set to 0 to force-disable)
#   * presence of .claude/agents/<officer>.md in the repo
#   * `claude` binary on PATH
#   * `claude --help` advertising the --agent flag
AGENT_FLAG=""
if [ "${CABINET_USE_NATIVE_AGENT:-1}" = "1" ] \
  && [ -f "$REPO_ROOT/.claude/agents/$OFFICER.md" ] \
  && command -v claude >/dev/null 2>&1 \
  && claude --help 2>&1 | grep -q -- '--agent'; then
  AGENT_FLAG="--agent $OFFICER"
fi

# ===========================================================
# Fallback-model probe (AUD-2, audit 2026-07-07): if the installed CLI supports
# --fallback-model (v2.1.166+, verified present on 2.1.202), pin an explicit
# fallback so an overloaded/unavailable primary degrades to plain
# claude-opus-4-8 (deliberately NON-[1m] — the fallback should never widen the
# context bill) instead of whatever the CLI would silently pick. Probed like
# AGENT_FLAG so older CLIs just omit the flag. Override via
# CABINET_FALLBACK_MODEL; set it to "none" to disable.
# NOTE: the loud-fallback Notification-hook page (no silent fallback) is the
# other half of AUD-2 — SHIPPED 2026-07-07 as
# cabinet/scripts/hooks-src/model-fallback-pager.sh, wired via
# .claude/settings.local.json (non-germline local settings layer; germline
# settings.json is schg-locked — the AUD-9 unlock window may consolidate the
# entry there, see the claude-code-audit addendum §AUD-2). Officers pick the
# hook up at natural relaunch; it stamps cabinet:model-fallback:<officer> and
# pages the Chair (debounced) when the CLI reports fallback engagement.
# ===========================================================
FALLBACK_MODEL="${CABINET_FALLBACK_MODEL:-claude-opus-4-8}"
FALLBACK_FLAG=""
if [ "$FALLBACK_MODEL" != "none" ] \
  && command -v claude >/dev/null 2>&1 \
  && claude --help 2>&1 | grep -q -- '--fallback-model'; then
  FALLBACK_FLAG="--fallback-model '$FALLBACK_MODEL'"
fi

# ===========================================================
# Officer config-home isolation (AUD-1, audit 2026-07-07 #1)
# ===========================================================
# When the officer's LaunchAgent sets CLAUDE_CONFIG_DIR (pilot: comms-officer),
# claude runs from a dedicated config home (~/Library/Application Support/
# cabinet/claude-config) instead of inheriting the Captain's personal ~/.claude
# (21 personal plugins, corridor mandate, personal auto-memory). Like
# OFFICER_NAME below, the var must ride ON the command line — tmux send-keys
# runs in the tmux SERVER's env, so plist EnvironmentVariables never reach the
# pane when the server pre-exists.
# CLAUDE_SECURESTORAGE_CONFIG_DIR federates ONLY the OAuth keychain lookup back
# to the default "Claude Code-credentials" item: CC (verified on 2.1.202)
# suffixes the keychain service name with sha256(config-dir)[0:8] when
# CLAUDE_CONFIG_DIR is set, so a fresh config home boots "Not logged in".
# Set-to-EMPTY drops the suffix (shares the existing keychain item,
# refresh-token coherent) — NEVER duplicate the OAuth item into a second
# keychain entry instead: refresh-token rotation would race the two copies.
# KNOWN RESIDUAL (documented in the AUD-1 ledger row): the ~3KB BODY of the
# Captain's personal ~/.claude/CLAUDE.md still loads via the cwd ANCESTOR walk
# (the repo lives under $HOME); the 58KB @screenpipe-memories.md dossier
# import does NOT load (external-includes gate, unapproved in the fresh home).
# The clean env prefix below carries CLAUDE_CONFIG_DIR and
# CLAUDE_SECURESTORAGE_CONFIG_DIR explicitly; no credential/config assignment
# is typed into tmux pane history.

# ===========================================================
# OS-enforced Captain-law + secret-store boundary
# ===========================================================
# Text-matching hooks are useful guidance but cannot constrain a shell that
# constructs paths dynamically.  macOS Seatbelt resolves the actual vnode and
# denies reads of shared secret stores plus all writes to the three Captain-law
# ledgers.  Officer observations use a fixed-policy broker started outside the
# sandbox; the broker, not the request, chooses identity and provenance.
SANDBOX_LIB="$REPO_ROOT/cabinet/scripts/lib/officer-sandbox.sh"
if [ ! -f "$SANDBOX_LIB" ]; then
  echo "[ERROR] start-officer-mac.sh: missing officer sandbox library: $SANDBOX_LIB" >&2
  exit 78
fi
# shellcheck source=lib/officer-sandbox.sh
source "$SANDBOX_LIB"

BROKER_DIR="$HOME/Library/Caches/cabinet/captain-law"
if [ "${CABINET_MAC_DRY_RUN:-0}" != "1" ]; then
  mkdir -p "$BROKER_DIR"
  chmod 700 "$BROKER_DIR"
fi
BROKER_SOCKET="$BROKER_DIR/$OFFICER.sock"

if [ "${CABINET_MAC_DRY_RUN:-0}" = "1" ]; then
  SANDBOX_PROFILE="$(mktemp -t "cabinet-officer-${OFFICER}.XXXXXX.sb")"
else
  SANDBOX_DIR="$HOME/Library/Caches/cabinet/officer-sandbox"
  mkdir -p "$SANDBOX_DIR"
  chmod 700 "$SANDBOX_DIR"
  SANDBOX_PROFILE="$SANDBOX_DIR/$OFFICER.sb"
fi
OBSERVE_SOURCE_ROOTS=("$REPO_ROOT")
SHARED_ENV_PATH=""
CABINET_RUNTIME_STATE_DIR=""
if ! SECURITY_PATH_OUTPUT="$(python3.12 - "$REPO_ROOT/instance/config/platform.yml" "$REPO_ROOT/instance/config/projects" <<'PY'
import os
import sys
import yaml
with open(sys.argv[1], encoding="utf-8") as handle:
    data = yaml.safe_load(handle) or {}
repos = data.get("git_repos") or []
if not isinstance(repos, list) or any(not isinstance(item, str) for item in repos):
    raise SystemExit("git_repos must be a string list")
shared = data.get("shared_env_path") or ""
state = os.environ.get("CABINET_STATE_DIR") or data.get("state_dir") or ""
if not isinstance(shared, str) or not isinstance(state, str):
    raise SystemExit("shared_env_path/state_dir must be strings")

roots = list(repos)
projects = sys.argv[2]
if os.path.isdir(projects):
    for name in sorted(os.listdir(projects)):
        if not name.endswith((".yml", ".yaml")):
            continue
        try:
            with open(os.path.join(projects, name), encoding="utf-8") as handle:
                project = yaml.safe_load(handle) or {}
        except Exception as exc:
            raise SystemExit(f"invalid project config {name}: {exc}")
        product = project.get("product") if isinstance(project, dict) else None
        mount = product.get("mount_path") if isinstance(product, dict) else None
        if isinstance(mount, str) and mount.strip():
            roots.append(mount.strip())

def clean(value):
    value = os.path.abspath(os.path.expanduser(value)) if value else ""
    if any(ch in value for ch in "\r\n\t"):
        raise SystemExit("security path contains a control character")
    return value

print("shared\t" + clean(shared))
print("state\t" + clean(state))
seen = set()
for item in roots:
    value = clean(item)
    if value and value not in seen:
        seen.add(value)
        print("root\t" + value)
PY
  )"; then
  echo "[ERROR] start-officer-mac.sh: cannot resolve officer security paths — refusing officer boot" >&2
  exit 78
fi
while IFS=$'\t' read -r _security_kind _security_path; do
  case "$_security_kind" in
    shared) SHARED_ENV_PATH="$_security_path" ;;
    state) CABINET_RUNTIME_STATE_DIR="$_security_path" ;;
    root) [ -n "$_security_path" ] && OBSERVE_SOURCE_ROOTS+=("$_security_path") ;;
  esac
done <<< "$SECURITY_PATH_OUTPUT"
officer_sandbox_write_profile "$REPO_ROOT" "$SANDBOX_PROFILE" "$BROKER_DIR" "$BROKER_SOCKET" \
  "$EGRESS_KERNEL_ENFORCED" "$CABINET_OBSERVE_ONLY" "$SHARED_ENV_PATH" \
  "$CABINET_RUNTIME_STATE_DIR" "${OBSERVE_SOURCE_ROOTS[@]}"

# SANDBOX RESOLUTION — ABSOLUTE PATH + BINARY VERIFICATION (2026-07-25 audit).
# This used to be `command -v sandbox-exec` and a BARE-NAME invocation. The
# officer is launched through `env -i ... PATH="$HOME/.local/bin:$PATH"` (see
# the tmux new-session below), which puts an OFFICER-WRITABLE directory FIRST
# on PATH. So an officer with Bash could write $HOME/.local/bin/sandbox-exec —
# a shim that drops the `-f <profile>` argument and execs the agent — and the
# NEXT restart would boot that officer completely UNSANDBOXED, with the
# Captain-law/secret boundary silently gone. The sandbox is now invoked by its
# absolute system path and that binary is verified before it is trusted:
# a regular file, not a symlink, executable, and owned by root (on Darwin
# /usr/bin is SIP-protected, so root ownership there is a strong guarantee).
# Anything that fails the check is treated exactly like a missing sandbox —
# the boot REFUSES rather than proceeding unconfined.
SANDBOX_EXEC_BIN="${CABINET_SANDBOX_EXEC_BIN:-/usr/bin/sandbox-exec}"
_sandbox_exec_trusted() {
  local p="$1" owner
  [ -n "$p" ] || return 1
  case "$p" in /*) : ;; *) return 1 ;; esac   # absolute paths only
  [ -f "$p" ] || return 1
  [ -L "$p" ] && return 1
  [ -x "$p" ] || return 1
  [ "$(uname -s 2>/dev/null)" = "Darwin" ] || return 0
  # GNU-first (`stat -c`) then BSD (`stat -f`): GNU `stat -f` SUCCEEDS printing
  # filesystem info, so a BSD-first probe never falls through on Linux.
  owner=$(stat -c '%u' "$p" 2>/dev/null || stat -f '%u' "$p" 2>/dev/null)
  [ "$owner" = "0" ]
}

SANDBOX_CMD=""
if _sandbox_exec_trusted "$SANDBOX_EXEC_BIN"; then
  printf -v _SANDBOX_Q '%q' "$SANDBOX_PROFILE"
  printf -v _SANDBOX_BIN_Q '%q' "$SANDBOX_EXEC_BIN"
  SANDBOX_CMD="$_SANDBOX_BIN_Q -f $_SANDBOX_Q"
elif [ "${CABINET_MAC_DRY_RUN:-0}" != "1" ]; then
  echo "[ERROR] start-officer-mac.sh: no trusted sandbox-exec at $SANDBOX_EXEC_BIN (must be a root-owned, non-symlink executable) — refusing to boot without the Captain-law/secret boundary" >&2
  exit 78
else
  # CI may exercise the Mac dry-run on Linux.  The real Mac boot path above is
  # fail-closed; dry-run still exposes that no executable sandbox is present.
  SANDBOX_CMD=""
fi

if [ "${CABINET_MAC_DRY_RUN:-0}" != "1" ]; then
  BROKER_PIDFILE="$BROKER_DIR/$OFFICER.pid"
  if [ -f "$BROKER_PIDFILE" ]; then
    OLD_BROKER_PID="$(cat "$BROKER_PIDFILE" 2>/dev/null || true)"
    if [[ "$OLD_BROKER_PID" =~ ^[0-9]+$ ]] \
      && ps -p "$OLD_BROKER_PID" -o command= 2>/dev/null | grep -Fq "captain-law-broker.py serve"; then
      kill "$OLD_BROKER_PID" 2>/dev/null || true
    fi
  fi
  rm -f "$BROKER_SOCKET"
  BROKER_CAPABILITY="$(python3.12 -c 'import secrets; print(secrets.token_hex(32))')"
  CABINET_LAW_BROKER_CAPABILITY="$BROKER_CAPABILITY" \
    nohup python3.12 "$REPO_ROOT/cabinet/scripts/captain-law-broker.py" serve \
    --socket "$BROKER_SOCKET" --root "$REPO_ROOT" --officer "$OFFICER" \
    >> "$LOGS_DIR/captain-law-broker-$OFFICER.log" 2>&1 &
  BROKER_PID=$!
  printf '%s\n' "$BROKER_PID" > "$BROKER_PIDFILE"
  chmod 600 "$BROKER_PIDFILE"
  _broker_ready=0
  for _try in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if [ -S "$BROKER_SOCKET" ]; then _broker_ready=1; break; fi
    sleep 0.05
  done
  if [ "$_broker_ready" != "1" ]; then
    echo "[ERROR] start-officer-mac.sh: Captain-law broker did not become ready — refusing officer boot" >&2
    kill "$BROKER_PID" 2>/dev/null || true
    exit 78
  fi
  export CABINET_CAPTAIN_LAW_SOCKET="$BROKER_SOCKET"
  export CABINET_CAPTAIN_LAW_CAPABILITY="$BROKER_CAPABILITY"
fi

# The clean env is assembled only after the launcher has resolved the officer's
# one Telegram token, lane, config home, and broker socket.  No other parent or
# tmux-server variables cross this boundary.
OFFICER_ENV_PREFIX="$(officer_env_command_prefix)"

# Build the claude invocation.  The real form is written to a mode-0700,
# self-unlinking launcher immediately before tmux starts; it is never typed
# into pane history (the env prefix contains credentials).
# $MODEL is single-quoted: model ids can carry a [1m] context suffix (e.g.
# claude-opus-4-8[1m]) and this command is typed into a zsh pane, which would
# glob the unquoted brackets ("zsh: no matches found"). Single quotes pass it literally.
# OFFICER_NAME/CABINET_OFFICER are pinned ON the command (not just exported in this
# script): tmux send-keys runs claude in the SESSION's env, which inherits the tmux
# SERVER's global env. When the server was first started by another officer (e.g. cos),
# a new session would otherwise launch claude as OFFICER_NAME=cos and mis-attribute every
# heartbeat / cost / log / tier2 write to cos. Forcing them here pins the real identity.
printf -v _REPO_ROOT_Q '%q' "$REPO_ROOT"
CLAUDE_CMD="cd $_REPO_ROOT_Q && exec ${SANDBOX_CMD:+$SANDBOX_CMD }$OFFICER_ENV_PREFIX claude --model '$MODEL' $FALLBACK_FLAG $MCP_FLAG $SETTINGS_FLAG $TELEGRAM_FLAG $AGENT_FLAG --dangerously-skip-permissions --effort max"

# ===========================================================
# Dry-run gate — print plan & exit before any tmux/redis/launch side-effects.
# Used by cabinet/scripts/test-mac-dry-run.sh to verify flag assembly without a
# real Mac host. Behaviour: stdout reports the assembled command + whether the
# native --agent flag was picked up, then exits 0.
# ===========================================================
if [ "${CABINET_MAC_DRY_RUN:-0}" = "1" ]; then
  # Never print credential values during a rehearsal.  The executable command
  # above uses the real clean prefix; the displayed plan carries names only.
  REDACTED_ENV_PREFIX="$(officer_env_redacted_prefix)"
  REDACTED_CLAUDE_CMD="cd $REPO_ROOT && ${SANDBOX_CMD:+$SANDBOX_CMD }$REDACTED_ENV_PREFIX claude --model '$MODEL' $FALLBACK_FLAG $MCP_FLAG $SETTINGS_FLAG $TELEGRAM_FLAG $AGENT_FLAG --dangerously-skip-permissions --effort max"
  echo "$REDACTED_CLAUDE_CMD"
  if [ -n "$SANDBOX_CMD" ]; then
    echo "security_sandbox=true"
  else
    echo "security_sandbox=unavailable-dry-run"
  fi
  echo "egress_enforced=$EGRESS_KERNEL_ENFORCED"
  echo "observe_only=$CABINET_OBSERVE_ONLY"
  if [ -n "$AGENT_FLAG" ]; then
    echo "native_agent=true"
  else
    echo "native_agent=false"
  fi
  # [FIX-4] surface the resolved lane so test-mac-dry-run.sh can assert the
  # CABINET_LANE export contract. Printed ONLY when a slug resolved (empty →
  # no line → resolve_lane falls through, fail-safe).
  if [ -n "${CABINET_LANE:-}" ]; then
    echo "CABINET_LANE=$CABINET_LANE"
  fi
  rm -f "$SANDBOX_PROFILE"
  exit 0
fi

# ===========================================================
# Heartbeat — SETEX 900s TTL per Spec 064 v1.1 CTO #3
# ===========================================================
# Below the dry-run gate ON PURPOSE: --dry-run must write nothing (no Redis
# keys, no tmux, no files) — it only prints the assembled command.
#
# THE VALUE IS ISO-8601, and it was `date -u +%s` until 2026-08-14.
# officer-supervisor.sh and the post-tool-use hook have always written
# ISO-8601 into this same key, so the fleet disagreed with itself about the
# format of its own liveness stamp. No shell reader noticed — they all test
# PRESENCE and let the 900s TTL do the freshness work — but the dashboard
# parses it (`lib/liveness.ts freshnessOf` → `Date.parse`), and
# `Date.parse('1786719742')` is NaN. That is the module's `unknown` arm, so
# the first thing an operator saw after starting an officer was
# "heartbeat unreadable" in amber, until the supervisor's next pass
# overwrote it with a stamp in the other format. A just-started officer
# reading as unreadable is the same class of defect as a never-started one
# reading as offline: the render is scarier than the fact.
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  SETEX "cabinet:heartbeat:$OFFICER" 900 "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > /dev/null 2>&1 || true

# ===========================================================
# tmux session + claude launch
# ===========================================================
# tmux new-session -d creates detached (no terminal attached) — per CTO v1.1 #4
# LaunchAgent doesn't have a TTY, so attached tmux would fail to start.

# Multi-checkout takeover guard (hatch-rehearsal finding 2026-07-07): session
# names are fixed (`officer-<role>`, no CABINET_ID namespacing yet), so this
# script run from a SECOND checkout (scratch clone, worktree, rehearsal) would
# silently kill-and-replace the LIVE deployment's officer session. Each session
# records its owning repo root in the tmux session env (CABINET_REPO_ROOT,
# stamped below at create); if an existing session belongs to a DIFFERENT
# root, refuse (exit 65) unless the operator explicitly forces the takeover.
# Sessions predating this guard carry no stamp → guard passes (same-behavior).
if tmux has-session -t "=$SESSION_NAME" 2>/dev/null; then
  EXISTING_ROOT="$(tmux show-environment -t "=$SESSION_NAME" CABINET_REPO_ROOT 2>/dev/null \
    | grep '^CABINET_REPO_ROOT=' | cut -d= -f2- || true)"
  if [ -n "$EXISTING_ROOT" ] && [ "$EXISTING_ROOT" != "$REPO_ROOT" ] \
      && [ "${CABINET_FORCE_TAKEOVER:-0}" != "1" ]; then
    cat >&2 <<TAKEOVER
[ERROR] start-officer-mac.sh: tmux session '$SESSION_NAME' is owned by ANOTHER
[ERROR]   checkout: $EXISTING_ROOT
[ERROR]   This invocation runs from:  $REPO_ROOT
[ERROR]   Refusing to kill the other deployment's live session. If you really
[ERROR]   mean to take it over: CABINET_FORCE_TAKEOVER=1 start-officer-mac.sh $OFFICER
TAKEOVER
    exit 65
  fi
fi

# Kill any existing session for this officer (idempotent restart)
tmux kill-session -t "=$SESSION_NAME" 2>/dev/null || true

# Reap orphaned Telegram channel-plugin pollers. The kill-session above kills the
# pane's process tree, but the --channels telegram plugin DETACHES (reparents to
# PID 1) and survives, keeping its getUpdates long-poll alive. Telegram allows only
# ONE getUpdates poll per bot token — a second (orphaned) poller returns 409 Conflict
# and NOTHING consumes, so the officer silently stops receiving DMs (observed
# 2026-06-23 after repeated relaunches). This Cabinet is single-Telegram-voice (only
# the Chair has a bot), so any stray telegram plugin is an orphan to replace.
# (Revisit if a deployment ever runs >1 telegram-capable officer — needs per-token scoping.)
if [ "$HAS_TELEGRAM" = "true" ]; then
  pkill -f 'plugins/cache/claude-plugins-official/telegram' 2>/dev/null \
    && echo "start-officer-mac.sh: reaped orphaned telegram channel-plugin poller(s)" >&2 || true
  sleep 1   # let the token's getUpdates lock release before the new plugin claims it
fi

# Reap orphaned redis-trigger-channel processes while retaining the stable
# group consumer and its pending-entry list across restarts.
# Same class of bug as the telegram reap above, on the OTHER delivery path:
# each officer runs a `bun run .../redis-trigger-channel/index.ts` MCP that
# joins the Redis consumer group `officer-<officer>` as consumer `channel` and
# injects new triggers into the live session. A Redis group hands each new
# message to exactly ONE consumer, so a stale/orphaned `channel` from a prior
# (dead) session would SPLIT the stream — silently eating triggers the live
# Chair should have woken to (root cause 2026-06-25: notify-officer cos never
# surfaced in the active Chair). The MCP child is normally killed with the
# tmux pane, but it can detach/reparent to PID 1 on crash, and a broken launch
# path that failed to expand $OFFICER_NAME leaked 15 zombies on a junk
# `cabinet:triggers:${OFFICER_NAME}` stream (observed 2026-06-25). The
# invariant we enforce here: exactly ONE live `channel` process per officer,
# using the stable `channel` consumer identity across restarts.
#
# 1) Kill any existing channel process for THIS officer (env OFFICER_NAME=<o>).
#    We are restarting, so any pre-existing one is stale by definition.
for _ch_pid in $(pgrep -f 'redis-trigger-channel/index.ts' 2>/dev/null); do
  _ch_off=$(ps eww -p "$_ch_pid" 2>/dev/null | tr ' ' '\n' | grep '^OFFICER_NAME=' | head -1 | cut -d= -f2-)
  # Match this officer, OR a literal unexpanded ${OFFICER_NAME} leak (junk).
  if [ "$_ch_off" = "$OFFICER" ] || [ "$_ch_off" = '${OFFICER_NAME}' ]; then
    kill -9 "$_ch_pid" 2>/dev/null \
      && echo "start-officer-mac.sh: reaped stale redis-trigger-channel pid=$_ch_pid (OFFICER_NAME='$_ch_off')" >&2 || true
  fi
done
# 2) Keep the `channel` consumer and its PEL intact. The replacement channel
#    calls processPending() with ID 0 before reading new entries, so the first
#    50 unACKed receipts are re-delivered at startup; the post-tool-use safety
#    net drains any overflow. Deleting the consumer would delete those ownership
#    records and violate AUD-12's consumer-side ACK contract.
# 3) Best-effort cleanup of the junk stream from the unexpanded-variable leak.
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  DEL 'cabinet:triggers:${OFFICER_NAME}' > /dev/null 2>&1 || true

# Start fresh detached session through a one-shot launcher.  Do not use
# send-keys for CLAUDE_CMD: it contains the clean officer environment and would
# persist API credentials in tmux pane history.  BROKER_DIR is already 0700 and
# the officer sandbox cannot read it; the launcher unlinks itself before exec.
LAUNCH_SCRIPT="$(officer_env_write_one_shot_launcher "$BROKER_DIR" "$CLAUDE_CMD")"
# env -i scrubs the environment, so PATH must carry ~/.local/bin explicitly:
# Claude Code's native installer puts `claude` there by default, and launchd's
# baked service PATH omits it (daemon plists fix this in their own wrapper —
# generate-plists.py). Without it the officer boots and fails at move-in when it
# cannot find `claude` (audit #60). $HOME/$PATH expand in THIS shell before env -i.
if ! tmux new-session -d -s "$SESSION_NAME" -x 220 -y 50 -c "$REPO_ROOT" \
    /usr/bin/env -i HOME="$HOME" PATH="$HOME/.local/bin:$PATH" USER="${USER:-}" \
    LOGNAME="${LOGNAME:-}" SHELL=/bin/bash \
    /bin/bash --noprofile --norc "$LAUNCH_SCRIPT"; then
  rm -f "$LAUNCH_SCRIPT"
  echo "[ERROR] start-officer-mac.sh: tmux failed to start $OFFICER" >&2
  exit 1
fi
tmux set-environment -t "=$SESSION_NAME" CABINET_REPO_ROOT "$REPO_ROOT" 2>/dev/null || true
# A healthy child removes the credential-bearing launcher immediately.  If it
# did not even open the file, delete it here and fail closed instead of leaving
# a secret artifact behind.
for _try in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  [ ! -e "$LAUNCH_SCRIPT" ] && break
  sleep 0.05
done
if [ -e "$LAUNCH_SCRIPT" ]; then
  rm -f "$LAUNCH_SCRIPT"
  tmux kill-session -t "=$SESSION_NAME" 2>/dev/null || true
  echo "[ERROR] start-officer-mac.sh: one-shot launcher was not consumed — refusing officer boot" >&2
  exit 78
fi

# ===========================================================
# Auto-confirm startup prompts + submit boot prompt.
# Shared logic with Docker start-officer.sh via lib/officer-boot.sh
# (officer_boot_drive) — a fix lands once for both platforms.
# ===========================================================
# shellcheck source=lib/officer-boot.sh
source "$REPO_ROOT/cabinet/scripts/lib/officer-boot.sh"
BOOT_PROMPT="You are $OFFICER. Read your role definition at .claude/agents/$OFFICER.md and your session start checklist.$(officer_role_registry_clause "$REPO_ROOT" "$OFFICER") Read your foundation skills in memory/skills/. Read your tier 2 notes in instance/memory/tier2/$OFFICER/. Then announce yourself on the warroom: bash $REPO_ROOT/cabinet/scripts/send-to-group.sh '<b>$OFFICER online (Mac native).</b> Session started. Checking for pending work.' — then run the calendar boot self-check: bash $REPO_ROOT/cabinet/scripts/calendar-boot-selfcheck.sh (it surfaces ONE warroom line only if the calendar grant is missing for this officer context, and never blocks boot) — then check for pending triggers and overdue work immediately."
officer_boot_drive "$SESSION_NAME" "$BOOT_PROMPT"

# ===========================================================
# Durable self-wake /loop (Gap 1: Mac officers stall after one turn).
# ===========================================================
# A Mac officer runs as its own detached tmux session and only advances when it
# takes a tool action — the post-tool-use hook is what surfaces queued triggers
# (cabinet:triggers:<officer>) and carded work. With no recurring nudge an
# officer does ONE boot burst then sits idle at the prompt forever, stranding
# every trigger and carded decision behind it (observed 2026-06-24:
# bakery-ceo + newsletter-ceo idle with 4 pending triggers + 4 captain-attention
# cards each). The fix: queue a `/loop 5m <prompt>` after the boot prompt so the
# officer re-checks its triggers + intake + lane work on a cadence and stays
# alive. Per-role prompt in cabinet/loop-prompts/<officer>.txt (gather-then-
# decide; surface to the Chair; never DM the Captain). R091: when no per-role
# prompt exists, the generic parameterized tick template
# (cabinet/loop-prompts/_template.txt, {{officer}} slots) is rendered instead;
# only if THAT is also absent does the officer simply have no self-wake.
# Idempotent: each boot is a fresh
# session, and officer_boot_drive already drained the startup prompts, so this
# `/loop` is the session's next command. The officer-supervisor-mac re-sends it
# every ~2h as a safety net if the officer ever exits its loop.
LOOP_FILE="$REPO_ROOT/cabinet/loop-prompts/${OFFICER}.txt"
LOOP_TEMPLATE="$REPO_ROOT/cabinet/loop-prompts/_template.txt"
if [ ! -f "$LOOP_FILE" ] && [ -f "$LOOP_TEMPLATE" ]; then
  LOOP_FILE=$(mktemp "/tmp/loop-prompt-${OFFICER}.XXXXXX")
  sed "s/{{officer}}/${OFFICER}/g" "$LOOP_TEMPLATE" > "$LOOP_FILE"
  echo "start-officer-mac.sh: $OFFICER has no per-role loop prompt — rendered _template.txt" >&2
fi
if [ -f "$LOOP_FILE" ]; then
  LOOP_PROMPT=$(tr '\n' ' ' < "$LOOP_FILE" | sed 's/  */ /g; s/ *$//')
  if [ -n "$LOOP_PROMPT" ]; then
    sleep 5  # let the boot prompt settle into a running turn before queuing /loop
    # officer_loop_arm (from lib/officer-boot.sh, already sourced above) submits
    # the /loop with the paste-safe technique: text, settle, C-m separately, then
    # verify + nudge. A bare `send-keys "... " C-m` would be absorbed as a paste
    # and never submit (observed 2026-06-24).
    officer_loop_arm "$SESSION_NAME" "/loop 5m $LOOP_PROMPT"
    echo "start-officer-mac.sh: $OFFICER self-wake /loop 5m armed from $LOOP_FILE" >&2
  fi
fi

echo "start-officer-mac.sh: $OFFICER started in tmux session $SESSION_NAME (model=$MODEL, telegram=$HAS_TELEGRAM, cua_driver=$HAS_CUA_DRIVER)"

# Audit-fix 2026-05-23: drop infinite while-true heartbeat loop. The in-session
# claude tool-use hook (stop-hook.sh + post-tool-use.sh) already writes heartbeat
# on every officer action — that's the canonical writer. A second writer here
# would double-stamp + mask the case where the in-session writer is broken.
#
# Hardening 2026-05-26 (Strategy B): launchd's KeepAlive watches THIS wrapper
# script. The old logic waited on `tmux display-message #{pid}` — that's the
# tmux server process tied to the session, NOT the claude inside. If claude
# crashed to a shell prompt inside tmux, the session stayed alive and launchd
# saw nothing wrong. Officer "running" but doing nothing.
#
# Fix: wait on the tmux PANE pid (the shell that has claude as its child). When
# claude exits to the shell, OR the shell itself dies, pane_pid disappears and
# we exit non-zero so launchd restarts us. Also publish that pid to a sentinel
# file + Redis so heartbeat-watchdog can do a `kill -0` cross-check.
PANE_PID=$(tmux list-panes -t "$SESSION_NAME" -F '#{pane_pid}' 2>/dev/null | head -1)
if [ -z "$PANE_PID" ]; then
  echo "[ERROR] start-officer-mac.sh: tmux pane for $SESSION_NAME has no pane_pid — session likely died during boot" >&2
  exit 1
fi

# Sentinel file: persists across the wrapper lifetime; heartbeat-watchdog reads
# it for `kill -0` liveness probing the actual claude process tree.
SENTINEL_DIR="$HOME/Library/Caches/cabinet"
mkdir -p "$SENTINEL_DIR"
echo "$PANE_PID" > "$SENTINEL_DIR/$OFFICER.pane.pid"

# Also stash in Redis (TTL'd to twice the watchdog interval — 600s — so a dead
# watchdog can't leave a stale pid claim around forever).
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
  SETEX "cabinet:officer:pane-pid:$OFFICER" 600 "$PANE_PID" > /dev/null 2>&1 || true

echo "start-officer-mac.sh: $OFFICER pane_pid=$PANE_PID (sentinel: $SENTINEL_DIR/$OFFICER.pane.pid)"

# Wait on the pane shell. If claude exits to shell, the shell stays — that's
# still a busted state. So also probe the pane CONTENT for an idle prompt
# pattern: if we see a bare shell prompt for >2 consecutive checks (60s), the
# pane is broken even though the PID lives. Exit non-zero to let KeepAlive cycle.
SHELL_PROMPT_STREAK=0
while kill -0 "$PANE_PID" 2>/dev/null; do
  sleep 30
  # Re-refresh Redis pane-pid TTL so the watchdog always has a live anchor.
  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
    SETEX "cabinet:officer:pane-pid:$OFFICER" 600 "$PANE_PID" > /dev/null 2>&1 || true
  # Detect claude-exited-to-shell. A live CC pane shows "esc to interrupt" or
  # ">" input cursor in the last few lines. A bare zsh/bash prompt with the
  # user@host marker means CC died and we're just looking at a shell.
  PANE_TAIL=$(tmux capture-pane -t "$SESSION_NAME" -p 2>/dev/null | grep -v '^[[:space:]]*$' | tail -5 || true)
  if echo "$PANE_TAIL" | grep -qE '^[^>]*[%#\$][[:space:]]*$' && \
     ! echo "$PANE_TAIL" | grep -qE '(esc to interrupt|Bypassing Permissions|^[[:space:]]*>)'; then
    SHELL_PROMPT_STREAK=$((SHELL_PROMPT_STREAK + 1))
    if [ "$SHELL_PROMPT_STREAK" -ge 2 ]; then
      echo "[ERROR] start-officer-mac.sh: $OFFICER claude exited to shell (pane_pid=$PANE_PID still alive) — exiting non-zero for KeepAlive restart" >&2
      tmux kill-session -t "=$SESSION_NAME" 2>/dev/null || true
      exit 1
    fi
  else
    SHELL_PROMPT_STREAK=0
  fi
done
echo "[INFO] start-officer-mac.sh: $OFFICER pane_pid=$PANE_PID exited — letting KeepAlive cycle" >&2
exit 1   # pane died — let KeepAlive restart us
