#!/usr/bin/env bash
# cabinet/tests/test-breach-notification.sh — Spec 055 AC#12 + CTO #9 regression harness.
#
# Hermetic validation of cabinet/scripts/breach-notification.sh (Art 33/34 tabletop simulator):
#   §A scenario load   §B Art-33 72h clock   §C Art-33(1) decision tree   §D affected-cabinet
#   window filter   §E no-send guarantee   §F report fields   §G gap flagging
#
# HERMETIC: LITELLM_AUDIT_LOG_ROOT + BREACH_SIM_OUTPUT_DIR → mktemp; CABINET_HOOK_TEST_MODE=1
# (no real notify). The script has no real send paths anyway. Usage: bash <this>  (exit 0 = pass)

set -u
_THIS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$_THIS/../.." && pwd)"
SCRIPT="${REPO}/cabinet/scripts/breach-notification.sh"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
mkdir -p "$T/audit" "$T/sim"

PASS=0; FAIL=0; FAILURES=""
pass()    { PASS=$((PASS+1)); }
fail()    { FAIL=$((FAIL+1)); FAILURES="${FAILURES}  FAIL: $1\n"; printf '  FAIL: %s\n' "$1"; }
section() { printf '\n── %s\n' "$1"; }

iso() { date -u -d "$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -v"$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null; }
seed_audit() { # <slug> <ts-iso>
    printf '{"ts":"%s","cabinet_id":"%s","entry_id":"e-%s","stream":"proxy","event_type":"llm_request"}\n' \
        "$2" "$1" "$RANDOM" >> "$T/audit/$1.jsonl"
}
mk_scenario() { # <involves_pd> <severity> [breach_iso] [aware_iso] -> path
    local f="$T/scn-$RANDOM.json"
    jq -n --argjson pd "$1" --arg sev "$2" --arg b "${3:-$(iso '-5 days')}" --arg a "${4:-$(iso '-1 hours')}" \
        '{source:"Anthropic",breach_type:"sub_processor",breach_occurred_at:$b,awareness_at:$a,data_categories:["x"],involves_personal_data:$pd,severity:$sev,description:"test"}' > "$f"
    echo "$f"
}
run_breach() { LITELLM_AUDIT_LOG_ROOT="$T" BREACH_SIM_OUTPUT_DIR="$T/sim" CABINET_HOOK_TEST_MODE=1 CABINET_ROOT="$REPO" bash "$SCRIPT" "$@"; }
report_of() { printf '%s' "$1" | grep -oE '[^ ]*breach-sim-[^ ]*\.json' | head -1; }

# ════════════════════════════════════════════════════════════════════════════
section "§A — scenario load (built-in default + --scenario-file)"
OUT="$(run_breach 2>&1)"; [ "$?" -eq 0 ] && pass || fail "default-scenario run should exit 0"
printf '%s' "$OUT" | grep -qF "built-in default scenario" && pass || fail "default scenario should be used when no file"
SF="$(mk_scenario false low)"
OUT="$(run_breach --scenario-file "$SF" 2>&1)"
printf '%s' "$OUT" | grep -qF "Loaded scenario from" && pass || fail "--scenario-file should load"

# ════════════════════════════════════════════════════════════════════════════
section "§C — Article 33(1) decision tree (4 branches)"
# no PII -> risk none, no Art33/34
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario false low)" 2>&1)")"
[ "$(jq -r '.article_33_1_threshold.risk_level' "$R")" = "none" ] && pass || fail "no-PII -> risk none"
[ "$(jq -r '.article_33.supervisory_notification_required' "$R")" = "false" ] && pass || fail "no-PII -> Art33 not required"
# PII + low -> low, no Art33
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario true low)" 2>&1)")"
[ "$(jq -r '.article_33_1_threshold.risk_level' "$R")" = "low" ] && pass || fail "PII+low -> risk low"
[ "$(jq -r '.article_33.supervisory_notification_required' "$R")" = "false" ] && pass || fail "PII+low -> Art33 not required"
# PII + medium -> Art33 required, Art34 not
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario true medium)" 2>&1)")"
[ "$(jq -r '.article_33.supervisory_notification_required' "$R")" = "true" ] && pass || fail "PII+medium -> Art33 required"
[ "$(jq -r '.article_34.data_subject_notification_required' "$R")" = "false" ] && pass || fail "PII+medium -> Art34 not required"
# PII + high -> Art33 AND Art34 required
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario true high)" 2>&1)")"
[ "$(jq -r '.article_33.supervisory_notification_required' "$R")" = "true" ] && pass || fail "PII+high -> Art33 required"
[ "$(jq -r '.article_34.data_subject_notification_required' "$R")" = "true" ] && pass || fail "PII+high -> Art34 required"

# ════════════════════════════════════════════════════════════════════════════
section "§B — Article 33 72h clock"
# awareness 1h ago -> ~71h remaining, not overdue
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario false low)" 2>&1)")"
HRS="$(jq -r '.article_33.hours_remaining' "$R")"
[ "$HRS" -ge 70 ] && [ "$HRS" -le 72 ] 2>/dev/null && pass || fail "72h clock ~71h remaining (got $HRS)"
# awareness 100h ago -> OVERDUE warning
OUT="$(run_breach --scenario-file "$(mk_scenario true high "$(iso '-200 hours')" "$(iso '-100 hours')")" 2>&1)"
printf '%s' "$OUT" | grep -qiF "OVERDUE" && pass || fail "100h-old awareness should warn OVERDUE"

# ════════════════════════════════════════════════════════════════════════════
section "§D — affected-cabinet window filter (FW-097 audit log)"
rm -f "$T/audit"/*.jsonl
seed_audit "cab-inwindow"  "$(iso '-2 days')"    # inside [breach-5d, aware-1h]
seed_audit "cab-outofwin"  "$(iso '-30 days')"   # before the breach window
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario false low)" 2>&1)")"
jq -e '.affected_cabinets | index("cab-inwindow")  != null' "$R" >/dev/null 2>&1 && pass || fail "in-window cabinet should be affected"
jq -e '.affected_cabinets | index("cab-outofwin") == null' "$R" >/dev/null 2>&1 && pass || fail "out-of-window cabinet must NOT be affected"

# ════════════════════════════════════════════════════════════════════════════
section "§E — no-send guarantee"
OUT="$(run_breach --scenario-file "$(mk_scenario true high)" 2>&1)"
R="$(report_of "$OUT")"
[ "$(jq -r '.sent_anything_real' "$R")" = "false" ] && pass || fail "report must record sent_anything_real=false"
[ "$(jq -r '.simulation' "$R")" = "true" ] && pass || fail "report must record simulation=true"
printf '%s' "$OUT" | grep -qF "WOULD-NOTIFY coo:" && pass || fail "test-mode must echo WOULD-NOTIFY (no real notify)"
printf '%s' "$OUT" | grep -qiE "\[SIM\]" && pass || fail "cascade must be logged as [SIM]"

# ════════════════════════════════════════════════════════════════════════════
section "§F — report fields present"
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario true medium)" 2>&1)")"
for field in '.scenario' '.article_33.clock_72h_deadline' '.article_33_1_threshold.rationale' '.affected_cabinets' '.gaps_flagged'; do
    jq -e "$field" "$R" >/dev/null 2>&1 && pass || fail "report missing field: $field"
done

# ════════════════════════════════════════════════════════════════════════════
section "§G — gap flagging (Art33 required but no affected cabinets)"
rm -f "$T/audit"/*.jsonl   # no cabinets at all
OUT="$(run_breach --scenario-file "$(mk_scenario true high)" 2>&1)"
R="$(report_of "$OUT")"
jq -e '.gaps_flagged | index("art33-required-but-no-cabinets") != null' "$R" >/dev/null 2>&1 && pass || fail "should flag gap: Art33 required but no cabinets"

# ════════════════════════════════════════════════════════════════════════════
section "§H — Opus-review FAIL-SAFE regressions (under-notify / missed-cabinet)"
mk_raw()     { local f="$T/raw-$RANDOM.json"; printf '%s' "$1" > "$f"; echo "$f"; }
seed_proxy() { mkdir -p "$T/proxy-audit"; printf '{"ts":"%s","cabinet_id":"%s","entry_id":"p-%s","stream":"proxy"}\n' "$2" "$1" "$RANDOM" >> "$T/proxy-audit/$1.jsonl"; }
B="$(iso '-5 days')"; A="$(iso '-1 hours')"

# BUG-1: missing breach_occurred_at must NOT invert the window + drop all cabinets.
rm -f "$T/audit"/*.jsonl "$T/proxy-audit"/*.jsonl 2>/dev/null; seed_audit "cab-nobreach" "$(iso '-2 days')"
R="$(report_of "$(run_breach --scenario-file "$(mk_raw "$(jq -n --arg a "$A" '{source:"x",awareness_at:$a,involves_personal_data:false,severity:"low"}')")" 2>&1)")"
jq -e '.affected_cabinets|index("cab-nobreach")!=null' "$R" >/dev/null 2>&1 && pass || fail "BUG-1: missing breach time must not drop cabinets (all-time window)"

# BUG-2: fractional .NNNZ ts (canonical FW-097 schema) must parse + window, not collapse to 0.
rm -f "$T/audit"/*.jsonl "$T/proxy-audit"/*.jsonl 2>/dev/null; seed_audit "cab-frac" "$(iso '-2 days' | sed 's/Z$/.500Z/')"
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario false low)" 2>&1)")"
jq -e '.affected_cabinets|index("cab-frac")!=null' "$R" >/dev/null 2>&1 && pass || fail "BUG-2: fractional ts must be parsed + windowed (not dropped)"

# BUG-3: missing awareness_at must flag GAP + UNKNOWN deadline (no fabricated 'now+72h').
R="$(report_of "$(run_breach --scenario-file "$(mk_raw "$(jq -n --arg b "$B" '{source:"x",breach_occurred_at:$b,involves_personal_data:false,severity:"low"}')")" 2>&1)")"
jq -e '.gaps_flagged|index("awareness-time-unknown")!=null' "$R" >/dev/null 2>&1 && pass || fail "BUG-3: missing awareness_at must flag GAP"
[ "$(jq -r '.article_33.clock_72h_deadline' "$R")" = "UNKNOWN" ] && pass || fail "BUG-3: missing awareness_at -> deadline UNKNOWN"

# BUG-4: ambiguous classification inputs must fail SAFE (escalate, not carve-out).
R="$(report_of "$(run_breach --scenario-file "$(mk_raw "$(jq -n --arg a "$A" --arg b "$B" '{source:"x",breach_occurred_at:$b,awareness_at:$a,severity:"high"}')")" 2>&1)")"
[ "$(jq -r '.article_33.supervisory_notification_required' "$R")" = "true" ] && pass || fail "BUG-4a: omitted involves_personal_data + high must escalate"
R="$(report_of "$(run_breach --scenario-file "$(mk_raw "$(jq -n --arg a "$A" --arg b "$B" '{source:"x",breach_occurred_at:$b,awareness_at:$a,involves_personal_data:true}')")" 2>&1)")"
[ "$(jq -r '.article_33.supervisory_notification_required' "$R")" = "true" ] && pass || fail "BUG-4b: omitted severity (PD true) must default high -> Art33"
R="$(report_of "$(run_breach --scenario-file "$(mk_raw "$(jq -n --arg a "$A" --arg b "$B" '{source:"x",breach_occurred_at:$b,awareness_at:$a,involves_personal_data:"yes",severity:"high"}')")" 2>&1)")"
[ "$(jq -r '.article_33.supervisory_notification_required' "$R")" = "true" ] && pass || fail "BUG-4c: involves_personal_data 'yes' must be treated as PII"

# BUG-5: case/term-variant high severity must still trigger Art 34.
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario true HIGH)" 2>&1)")"
[ "$(jq -r '.article_34.data_subject_notification_required' "$R")" = "true" ] && pass || fail "BUG-5a: uppercase HIGH must trigger Art34"
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario true critical)" 2>&1)")"
[ "$(jq -r '.article_34.data_subject_notification_required' "$R")" = "true" ] && pass || fail "BUG-5b: 'critical' must trigger Art34"

# BUG-7: a malformed audit line must not hide a cabinet (skip bad lines).
rm -f "$T/audit"/*.jsonl "$T/proxy-audit"/*.jsonl 2>/dev/null
seed_audit "cab-mal" "$(iso '-2 days')"; printf 'THIS IS NOT JSON {{{\n' >> "$T/audit/cab-mal.jsonl"; seed_audit "cab-mal" "$(iso '-2 days')"
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario false low)" 2>&1)")"
jq -e '.affected_cabinets|index("cab-mal")!=null' "$R" >/dev/null 2>&1 && pass || fail "BUG-7: malformed line must not hide a cabinet"

# BUG-6: audit/ empty -> fall back to the raw proxy-audit/ stream + flag the GAP.
rm -f "$T/audit"/*.jsonl "$T/proxy-audit"/*.jsonl 2>/dev/null; seed_proxy "cab-proxyonly" "$(iso '-2 days')"
R="$(report_of "$(run_breach --scenario-file "$(mk_scenario false low)" 2>&1)")"
jq -e '.affected_cabinets|index("cab-proxyonly")!=null' "$R" >/dev/null 2>&1 && pass || fail "BUG-6: audit/ empty must fall back to proxy-audit/"
jq -e '.gaps_flagged|index("audit-ssot-empty-used-proxy-audit")!=null' "$R" >/dev/null 2>&1 && pass || fail "BUG-6: should flag audit-ssot-empty GAP"

# ── Summary ──────────────────────────────────────────────────────────────────
printf '\n════════════════════════════════════════════════════════════════════\n'
printf '  Spec 055 AC#12 / CTO#9 — breach-notification tabletop harness\n'
printf '  PASS: %d   FAIL: %d   TOTAL: %d\n' "$PASS" "$FAIL" "$((PASS+FAIL))"
[ "$FAIL" -gt 0 ] && printf '\nFailed:\n%b\n' "$FAILURES"
printf '════════════════════════════════════════════════════════════════════\n'
[ "$FAIL" -eq 0 ]
