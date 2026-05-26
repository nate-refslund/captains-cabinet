#!/bin/bash
# cabinet/scripts/hooks/captain-rule-encoder.sh — Spec 048 v2 Phase 1
#
# Sibling UserPromptSubmit hook to pre-captain-dm.sh. When an inbound
# Captain DM contains an encode-signal phrase ("remember", "always",
# "never", "encode", "save as", etc.), this hook:
#   1. Appends an entry to captain-patterns.md (or captain-intents.md
#      based on signal class) using the existing append-only format.
#   2. Fires async classifier (Sonnet via classify-rule.sh) in the
#      background — does NOT block the Captain-acknowledge reply path.
#   3. Writes audit JSONL to cabinet/logs/rule-promotions.jsonl with
#      classifier verdict (when async result lands) for retrospection.
#
# Phase 2 (separate PR) consumes the classifier output to generate hook
# + skill drafts and surface them in the next outbound Captain reply
# for ratify.
#
# Per Spec 048 v2 anti-FW-042 + A6 minimal-change:
#   - Warn-only / side-effect-only. NEVER exits non-zero. NEVER blocks.
#   - Env-var disable: RULE_ENCODER_HOOK_ENABLED=0
#   - Captain-only by chat_id (default-deny on missing config).
#   - Anti-over-hooking floor enforced in classify-rule.sh (≥3 triggers).
#
# Reversibility: rm this file + drop UserPromptSubmit registration.

set -u

if [ "${RULE_ENCODER_HOOK_ENABLED:-1}" = "0" ]; then
  exit 0
fi

# Phase 3 (convergence): resolve REPO_ROOT for both Docker (/opt/founders-cabinet)
# and Mac-native (script-relative path) without breaking either invocation.
if [ -z "${REPO_ROOT:-}" ]; then
  if [ -d "/opt/founders-cabinet" ]; then
    REPO_ROOT="/opt/founders-cabinet"
  else
    REPO_ROOT="${CABINET_ROOT:-$(cd "$(dirname "$0")/../../.." 2>/dev/null && pwd)}"
  fi
fi
SIGNALS_YAML="$REPO_ROOT/cabinet/scripts/captain-rules/encode-signals.yaml"
CLASSIFIER="$REPO_ROOT/cabinet/scripts/captain-rules/classify-rule.sh"
PATTERNS_FILE="$REPO_ROOT/shared/interfaces/captain-patterns.md"
INTENTS_FILE="$REPO_ROOT/shared/interfaces/captain-intents.md"
LOG_DIR="$REPO_ROOT/cabinet/logs"
AUDIT_LOG="$LOG_DIR/rule-promotions.jsonl"
PRODUCT_YML="$REPO_ROOT/instance/config/product.yml"
PLATFORM_YML="$REPO_ROOT/instance/config/platform.yml"

OFFICER="${OFFICER_NAME:-${CABINET_OFFICER:-unknown}}"
NOW_ISO="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# Phase 3 — Redis two-count rule + cross-officer broadcast.
# When the same pattern signal fires for the SECOND time, the encoder
# escalates from "log silently" to "broadcast to other officers". Counter
# lives in Redis at cabinet:patterns:seen:<rule_id> with a 30-day TTL so
# stale-but-rare patterns don't drift forever.
REDIS_HOST_LOCAL="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT_LOCAL="${REDIS_PORT:-6379}"

INPUT="$(cat)"
[ -z "$INPUT" ] && exit 0

PROMPT="$(printf '%s' "$INPUT" | jq -r '.prompt // ""' 2>/dev/null)"
[ -z "$PROMPT" ] && exit 0

# Captain-only filter: same default-deny pattern as pre-captain-dm.sh.
if ! printf '%s' "$PROMPT" | grep -q '<channel source="telegram"'; then
  exit 0
fi
CAPTAIN_CHAT_ID="$(grep -E '^[[:space:]]*captain_telegram_chat_id:' "$PRODUCT_YML" "$PLATFORM_YML" 2>/dev/null | head -1 | awk -F: '{print $NF}' | tr -d '"' | tr -d ' ')"
[ -z "$CAPTAIN_CHAT_ID" ] && exit 0
if ! printf '%s' "$PROMPT" | grep -qE "<channel source=\"telegram\"[^>]*chat_id=\"$CAPTAIN_CHAT_ID\""; then
  exit 0
fi

# Extract DM body (between channel open + close tags).
DM_BODY="$(printf '%s' "$PROMPT" | python3 -c '
import sys, re
text = sys.stdin.read()
m = re.search(r"<channel source=\"telegram\"[^>]*>(.*?)</channel>", text, re.DOTALL)
sys.stdout.write(m.group(1).strip() if m else "")
' 2>/dev/null)"
[ -z "$DM_BODY" ] && exit 0

# Detect encode signals via the YAML regex list. Pass DM_BODY via argv
# (heredoc consumes stdin, so piping echo doesn't reach the script).
MATCHED_SIGNAL="$(python3 - "$SIGNALS_YAML" "$DM_BODY" <<'PYEOF' 2>/dev/null
import sys, re
yaml_path = sys.argv[1]
text = sys.argv[2]
patterns = []
try:
    with open(yaml_path) as f:
        in_signals = False
        for line in f:
            stripped = line.rstrip("\n")
            if stripped.startswith("signals:"):
                in_signals = True
                continue
            if in_signals and stripped and not stripped.startswith(" ") and not stripped.startswith("-"):
                in_signals = False
            if in_signals and stripped.lstrip().startswith("- "):
                val = stripped.lstrip()[2:].strip()
                if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                    val = val[1:-1]
                patterns.append(val)
except FileNotFoundError:
    sys.exit(0)
for pat in patterns:
    try:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            sys.stdout.write(m.group(0))
            sys.exit(0)
    except re.error:
        continue
PYEOF
)"

[ -z "$MATCHED_SIGNAL" ] && exit 0

# Generate a stable rule_id from the DM body hash for audit trail.
RULE_ID="C-$(printf '%s' "$DM_BODY" | sha1sum | awk '{print substr($1,1,8)}')"

# Phase 3 — two-count rule. INCR a Redis counter keyed by rule_id. The
# first sighting gets a normal encode entry; the second sighting (and
# beyond) ALSO triggers a cross-officer broadcast so other roles refresh
# their captain-patterns.md cache. Counter is best-effort: any Redis
# failure falls through silently to the legacy single-sighting behaviour.
RULE_COUNT=0
if command -v redis-cli >/dev/null 2>&1; then
  RULE_COUNT="$(redis-cli -h "$REDIS_HOST_LOCAL" -p "$REDIS_PORT_LOCAL" \
    INCR "cabinet:patterns:seen:$RULE_ID" 2>/dev/null)"
  # Set a TTL on first INCR so stale rule_ids don't accumulate forever
  if [ "$RULE_COUNT" = "1" ]; then
    redis-cli -h "$REDIS_HOST_LOCAL" -p "$REDIS_PORT_LOCAL" \
      EXPIRE "cabinet:patterns:seen:$RULE_ID" 2592000 >/dev/null 2>&1 || true
  fi
fi

# Append entry to captain-patterns.md using the existing format.
# Files are gitignored (shared/interfaces/**/*.md); writes are runtime-only.
mkdir -p "$LOG_DIR" 2>/dev/null

if [ -w "$PATTERNS_FILE" ] || [ ! -e "$PATTERNS_FILE" ]; then
  {
    printf '\n---\n\n'
    printf '### Auto-encoded rule %s (%s)\n\n' "$RULE_ID" "$NOW_ISO"
    printf -- '- **Trigger signal:** `%s`\n' "$MATCHED_SIGNAL"
    printf -- '- **Captain DM body (verbatim):**\n\n  > %s\n\n' "$(printf '%s' "$DM_BODY" | tr '\n' ' ' | head -c 500)"
    printf -- '- **Encoded by:** captain-rule-encoder.sh (Spec 048 v2 Phase 1)\n'
    printf -- '- **Source:** %s\n' "$OFFICER"
    printf -- '- **Classifier verdict:** PENDING (async; check audit log)\n'
    printf -- '- **Sighting count:** %s (Phase 3 — broadcast on count >= 2)\n' "$RULE_COUNT"
  } >> "$PATTERNS_FILE" 2>/dev/null
fi

# Phase 3 — cross-officer broadcast on second+ sighting. Each active
# officer's trigger stream gets one notification telling them to re-read
# captain-patterns.md. The notify-officer.sh script handles the Redis
# Stream push + cabinet memory queue. Best-effort: failures don't block
# the hook.
if [ -n "$RULE_COUNT" ] && [ "$RULE_COUNT" -ge 2 ] 2>/dev/null; then
  NOTIFIER="$REPO_ROOT/cabinet/scripts/notify-officer.sh"
  ACTIVE_OFFICERS_DIR="$REPO_ROOT/instance/roles/active"
  if [ -x "$NOTIFIER" ] && [ -d "$ACTIVE_OFFICERS_DIR" ]; then
    BROADCAST_MSG="Captain pattern ${RULE_ID} encoded for the ${RULE_COUNT}th time — re-read shared/interfaces/captain-patterns.md before next Captain DM."
    for role_yml in "$ACTIVE_OFFICERS_DIR"/*.yml; do
      [ -f "$role_yml" ] || continue
      target_slug="$(basename "$role_yml" .yml)"
      [ "$target_slug" = "$OFFICER" ] && continue
      REDIS_HOST="$REDIS_HOST_LOCAL" REDIS_PORT="$REDIS_PORT_LOCAL" \
        bash "$NOTIFIER" "$target_slug" "$BROADCAST_MSG" >/dev/null 2>&1 || true
    done
  fi
fi

# Audit log: pre-classifier entry. Phase 2 will append a follow-up line
# with the classifier verdict + Captain ratify state.
PRE_LOG="$(jq -cn \
  --arg ts "$NOW_ISO" \
  --arg officer "$OFFICER" \
  --arg rule_id "$RULE_ID" \
  --arg matched "$MATCHED_SIGNAL" \
  --arg body "$DM_BODY" \
  --arg phase "encoded" \
  '{ts:$ts, officer:$officer, rule_id:$rule_id, matched_signal:$matched, dm_body:$body, phase:$phase}' 2>/dev/null)"
[ -n "$PRE_LOG" ] && echo "$PRE_LOG" >> "$AUDIT_LOG"

# Fire async classifier — fully detached from this hook's lifetime.
# stdout of classifier appended to audit log when it completes. Phase 2:
# if classifier returns operationalizable + confidence >= 0.7, also fire
# draft-generator.sh to emit hook + skill drafts at the .draft paths.
DRAFT_GEN="$REPO_ROOT/cabinet/scripts/captain-rules/draft-generator.sh"
if [ -x "$CLASSIFIER" ]; then
  (
    CLASS_RESULT="$(bash "$CLASSIFIER" "$DM_BODY" 2>/dev/null)"
    if [ -n "$CLASS_RESULT" ]; then
      POST_LOG="$(jq -cn \
        --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --arg rule_id "$RULE_ID" \
        --argjson classifier "$CLASS_RESULT" \
        --arg phase "classified" \
        '{ts:$ts, rule_id:$rule_id, classifier:$classifier, phase:$phase}' 2>/dev/null)"
      [ -n "$POST_LOG" ] && echo "$POST_LOG" >> "$AUDIT_LOG"

      # Phase 2: auto-draft hook + skill if operationalizable + confident.
      CLS_CHECK="$(printf '%s' "$CLASS_RESULT" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    cls = d.get("class")
    conf = float(d.get("confidence") or 0)
    if cls == "operationalizable" and conf >= 0.7:
        print("draft")
except Exception:
    pass
' 2>/dev/null)"
      if [ "$CLS_CHECK" = "draft" ] && [ -x "$DRAFT_GEN" ]; then
        TMP_BODY="$(mktemp)"
        printf '%s' "$DM_BODY" > "$TMP_BODY"
        DRAFT_PATHS="$(bash "$DRAFT_GEN" "$RULE_ID" "$TMP_BODY" "$CLASS_RESULT" 2>/dev/null)"
        rm -f "$TMP_BODY" 2>/dev/null
        if [ -n "$DRAFT_PATHS" ]; then
          DRAFT_LOG="$(jq -cn \
            --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            --arg rule_id "$RULE_ID" \
            --arg paths "$DRAFT_PATHS" \
            --arg phase "drafted" \
            '{ts:$ts, rule_id:$rule_id, draft_paths:$paths, phase:$phase}' 2>/dev/null)"
          [ -n "$DRAFT_LOG" ] && echo "$DRAFT_LOG" >> "$AUDIT_LOG"
        fi
      fi
    fi
  ) >/dev/null 2>&1 &
  disown
fi

# Hook silent on stdout (no additionalContext); side-effect-only.
exit 0
