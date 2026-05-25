#!/usr/bin/env bash
# test-spec-052-producers.sh — Spec 052 Phase 5 officer-side audit producers + grant reader.
#
# Covers (hermetic — capture-mode + temp fixtures, no live audit-server, no prod sinks):
#   - audit-emit.sh        : capability gate (granted/ungranted), config-absent no-op, PII-min
#                            (DM text/body stripped, length kept), oversized cap, cabinet-event.
#   - post-reply-audit.sh  : dm_sent emit — length only, NEVER the DM text; ungranted officer no-op.
#   - §14 tool_call shape   : Edit→path-only (no content), Bash→no command content (PII-safe).
#   - apply-capability-grants.sh : grant append (cos/coo/cro), idempotent, dev-mappings preserved,
#                            multi-cap, absent-block no-op, unknown-cap WARN, DEV-CONF-UNTOUCHED.
#
# Sections are presence-gated: against the unmerged /opt checkout the libs/hooks aren't present yet,
# so they SKIP (no FAIL). Pre-merge, run with CABINET_ROOT pointed at the worktree.

set -uo pipefail
CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"
LIB="$CABINET_ROOT/cabinet/scripts/lib"
HOOKS="$CABINET_ROOT/cabinet/scripts/hooks"
PRESETS="$CABINET_ROOT/presets"
PASS=0; FAIL=0
eq() { local l="$1" g="$2" w="$3"; if [ "$g" = "$w" ]; then PASS=$((PASS+1)); else FAIL=$((FAIL+1)); echo "  ✗ $l: got [$g] want [$w]"; fi; }
command -v jq >/dev/null 2>&1 || { echo "jq required"; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
printf 'cos:emits_customer_audit_events\ncto:deploys_code\n' > "$TMP/granted.conf"
printf 'cto:deploys_code\n' > "$TMP/ungranted.conf"
CAP="$TMP/cap.jsonl"
_jq() { jq -e "$1" "$CAP" >/dev/null 2>&1 && echo Y || echo N; }

echo "── audit-emit.sh — gates + payload + PII ──"
if [ -r "$LIB/audit-emit.sh" ]; then
  # shellcheck source=/dev/null
  source "$LIB/audit-emit.sh"
  : > "$CAP"; OFFICER_NAME=cos CABINET_SLUG=acme AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" AUDIT_EMIT_CAPTURE="$CAP" audit_emit_event officer tool_call tool_call Bash '{"x":1}'
  eq "emit granted shape" "$(_jq '.cabinet_id=="acme" and .stream=="officer" and .event_type=="tool_call" and .actor.officer=="cos" and .actor.captain==false and .subject.type=="tool_call" and .subject.target=="Bash"')" "Y"
  : > "$CAP"; OFFICER_NAME=cos CABINET_SLUG=acme AUDIT_CAPABILITIES_FILE="$TMP/ungranted.conf" AUDIT_EMIT_CAPTURE="$CAP" audit_emit_event officer tool_call tool_call Bash '{}'
  eq "emit ungranted no-op" "$(wc -l < "$CAP" | tr -d ' ')" "0"
  ( OFFICER_NAME=cos CABINET_SLUG=acme AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" audit_emit_event officer tool_call tool_call Bash '{}' ); eq "emit config-absent rc0" "$?" "0"
  : > "$CAP"; OFFICER_NAME=cos CABINET_SLUG=acme AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" AUDIT_EMIT_CAPTURE="$CAP" audit_emit_event officer dm_sent telegram_dm '' '{"length":7,"attachment_count":0,"text":"SECRET","body":"x"}'
  eq "emit PII strip + length kept" "$(_jq '(.subject.metadata|has("text")|not) and (.subject.metadata|has("body")|not) and .subject.metadata.length==7')" "Y"
  # Opus ship-gate HIGH fix — allow-list drops nested / case-variant / arbitrary-key PII:
  : > "$CAP"; OFFICER_NAME=cos CABINET_SLUG=acme AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" AUDIT_EMIT_CAPTURE="$CAP" audit_emit_event officer dm_sent telegram_dm '' '{"length":5,"dm":"SSN 123-45-6789","Text":"PII","msg":{"body":"nested PII"}}'
  eq "emit allow-list drops arbitrary/case/nested" "$(_jq '.subject.metadata=={"length":5}')" "Y"
  : > "$CAP"; LONGP="$(printf 'x%.0s' $(seq 1 300))"; OFFICER_NAME=cos CABINET_SLUG=acme AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" AUDIT_EMIT_CAPTURE="$CAP" audit_emit_event officer tool_call tool_call Read "$(jq -nc --arg p "$LONGP" '{path:$p}')"
  eq "emit value-length bound drops free-text" "$(_jq '(.subject.metadata|has("path")|not)')" "Y"
  : > "$CAP"; OFFICER_NAME=cos CABINET_SLUG=acme AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" AUDIT_EMIT_CAPTURE="$CAP" audit_emit_event cabinet key_rotation cabinet_event proxy-key '{"by":"cos"}'
  eq "emit cabinet-event stream" "$(_jq '.stream=="cabinet" and .event_type=="key_rotation" and .subject.target=="proxy-key" and .subject.metadata.by=="cos"')" "Y"
  : > "$CAP"; OFFICER_NAME=cos AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" AUDIT_EMIT_CAPTURE="$CAP" audit_emit_event officer tool_call tool_call Edit '{}'
  eq "emit capture-mode slug default" "$(_jq '.cabinet_id=="test-cabinet"')" "Y"

  echo "── §14 tool_call metadata shape (PII-safe) ──"
  _md_for() { local tn="$1" ti="$2" md='{}'; case "$tn" in Edit|Write|Read|NotebookEdit) md="$(printf '%s' "$ti" | jq -c '{path:(.file_path // .notebook_path // "")}' 2>/dev/null || echo '{}')";; esac; printf '%s' "$md"; }
  : > "$CAP"; OFFICER_NAME=cos CABINET_SLUG=acme AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" AUDIT_EMIT_CAPTURE="$CAP" audit_emit_event officer tool_call tool_call Edit "$(_md_for Edit '{"file_path":"/w/c/d.txt","old_string":"S","new_string":"X"}')"
  eq "§14 Edit path-only (no content)" "$(_jq '.subject.metadata.path=="/w/c/d.txt" and (.subject.metadata|has("old_string")|not)')" "Y"
  : > "$CAP"; OFFICER_NAME=cos CABINET_SLUG=acme AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" AUDIT_EMIT_CAPTURE="$CAP" audit_emit_event officer tool_call tool_call Bash "$(_md_for Bash '{"command":"API_KEY=s git push"}')"
  eq "§14 Bash no-command-content" "$(_jq '.subject.target=="Bash" and (.subject.metadata|length==0)')" "Y"

  echo "── post-reply-audit.sh — dm_sent (length only, NO text) ──"
  if [ -x "$HOOKS/post-reply-audit.sh" ] || [ -r "$HOOKS/post-reply-audit.sh" ]; then
    : > "$CAP"
    printf '%s' '{"tool_name":"reply","tool_input":{"text":"Hello SECRET status update","chat_id":"1","reply_to":"2"}}' \
      | CABINET_ROOT="$CABINET_ROOT" OFFICER_NAME=cos CABINET_SLUG=acme AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" AUDIT_EMIT_CAPTURE="$CAP" bash "$HOOKS/post-reply-audit.sh"
    eq "reply dm_sent PII-safe" "$(_jq '.event_type=="dm_sent" and .subject.type=="telegram_dm" and .subject.metadata.length>0 and (.subject.metadata|has("text")|not) and (.subject|has("target")|not)')" "Y"
    : > "$CAP"
    printf '%s' '{"tool_input":{"text":"hi"}}' \
      | CABINET_ROOT="$CABINET_ROOT" OFFICER_NAME=cro AUDIT_CAPABILITIES_FILE="$TMP/granted.conf" AUDIT_EMIT_CAPTURE="$CAP" bash "$HOOKS/post-reply-audit.sh"
    eq "reply ungranted-officer no-op" "$(wc -l < "$CAP" | tr -d ' ')" "0"
  else echo "  ⚠ SKIP post-reply-audit.sh (not found)"; fi
else echo "  ⚠ SKIP audit-emit.sh (not at $LIB — run with CABINET_ROOT=<worktree> pre-merge)"; fi

echo "── apply-capability-grants.sh — grant reader ──"
if [ -r "$LIB/apply-capability-grants.sh" ] && [ -r "$PRESETS/refslund-commercial/preset.yml" ]; then
  # shellcheck source=/dev/null
  source "$LIB/apply-capability-grants.sh"
  printf '# capabilities:\n#   emits_customer_audit_events — GDPR trail\n# ===\ncto:deploys_code\n' > "$TMP/gconf"
  DEV="$(md5sum < "$CABINET_ROOT/cabinet/officer-capabilities.conf" 2>/dev/null)"
  apply_capability_grants "$PRESETS/refslund-commercial/preset.yml" "$TMP/gconf" 2>/dev/null
  for o in cos coo cro; do eq "grant $o appended" "$(grep -c "^${o}:emits_customer_audit_events$" "$TMP/gconf")" "1"; done
  eq "grant dev-mappings preserved" "$(grep -c '^cto:deploys_code$' "$TMP/gconf")" "1"
  apply_capability_grants "$PRESETS/refslund-commercial/preset.yml" "$TMP/gconf" 2>/dev/null
  eq "grant idempotent" "$(grep -c '^cos:emits_customer_audit_events$' "$TMP/gconf")" "1"
  printf 'name: x\n' > "$TMP/nb.yml"; cp "$TMP/gconf" "$TMP/gc2"; apply_capability_grants "$TMP/nb.yml" "$TMP/gc2" 2>/dev/null
  eq "grant absent-block no-op" "$(diff -q "$TMP/gconf" "$TMP/gc2" >/dev/null && echo same || echo diff)" "same"
  printf 'capability_grants:\n  coo: [cap_a, cap_b]\n' > "$TMP/m.yml"; cp "$TMP/gconf" "$TMP/gc3"; apply_capability_grants "$TMP/m.yml" "$TMP/gc3" 2>/dev/null
  eq "grant multi-cap list" "$(grep -cE '^coo:cap_[ab]$' "$TMP/gc3")" "2"
  printf 'capability_grants:\n  cos: [nope_cap]\n' > "$TMP/u.yml"; cp "$TMP/gconf" "$TMP/gc4"; apply_capability_grants "$TMP/u.yml" "$TMP/gc4" 2>"$TMP/err"
  eq "grant unknown-cap WARN" "$(grep -c 'WARN.*nope_cap' "$TMP/err")" "1"
  eq "grant unknown-cap appended (warn-not-block)" "$(grep -c '^cos:nope_cap$' "$TMP/gc4")" "1"
  # Opus MEDIUM: a malformed/glob cap must NOT forge bogus officer:filename grants (noglob + identifier-validate)
  printf 'capability_grants:\n  cos: [*]\n' > "$TMP/star.yml"; printf '# emits_customer_audit_events\ncto:deploys_code\n' > "$TMP/gc5"; ( cd "$TMP" && apply_capability_grants "$TMP/star.yml" "$TMP/gc5" 2>/dev/null )
  eq "grant malformed/glob cap rejected" "$(grep -c '^cos:' "$TMP/gc5")" "0"
  eq "grant DEV-CONF-UNTOUCHED" "$(md5sum < "$CABINET_ROOT/cabinet/officer-capabilities.conf" 2>/dev/null)" "$DEV"
else echo "  ⚠ SKIP apply-capability-grants.sh (lib/preset not found)"; fi

echo "════════════════════════════════════════════"
echo "Spec 052 Ph5 producers harness: PASS=$PASS FAIL=$FAIL"
echo "════════════════════════════════════════════"
[ "$FAIL" -eq 0 ]
