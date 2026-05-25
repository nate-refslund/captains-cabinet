#!/usr/bin/env bash
# cabinet/scripts/breach-notification.sh — FW / Spec 055 AC#12 + CTO #9 (Phase 9)
#
# GDPR Article 33/34 breach-notification TABLETOP SIMULATOR.
#
# WHAT IT DOES (CTO #9): generates a TEST breach scenario (default: a fake Anthropic
# sub-processor notice), walks the Article 33(1) risk-threshold decision tree, identifies
# affected customer cabinets from the FW-097 audit log, and SIMULATES the notification
# cascade — logging exactly what WOULD happen. It SENDS NOTHING REAL. The output is a
# report for the COO-as-DPO (runbook owner per Spec 055 v4 H1) + CoS to review for gaps.
# Real breach response stays MANUAL until trust is established.
#
# USAGE:
#   breach-notification.sh [--scenario-file <path>] [--now <UTC-ISO>]
#     --scenario-file  load a breach scenario JSON (else a built-in fake Anthropic notice)
#     --now            override "now" (test-only; for deadline math)
#
# ENV (overridable for hermetic testing):
#   LITELLM_AUDIT_LOG_ROOT   audit-log SSOT root (default: /opt/founders-cabinet/proxy/logs)
#   BREACH_SIM_OUTPUT_DIR    where the simulation report is written (default: <root>/breach-sim)
#   CABINET_HOOK_TEST_MODE   if 1, suppress the internal COO review-ping (echo instead)
#
# SCENARIO JSON SHAPE (all fields optional; sensible defaults applied):
#   { "source": "Anthropic", "breach_type": "sub_processor",
#     "breach_occurred_at": "<UTC-ISO>", "awareness_at": "<UTC-ISO>",
#     "data_categories": ["..."], "involves_personal_data": true|false,
#     "severity": "low|medium|high", "description": "..." }
#
# ARTICLE MAPPING:
#   Art 33   — notify supervisory authority (DK: Datatilsynet) within 72h of CONFIRMED
#              awareness (Spec 055 v4 I1 clock-start: sub-processor notice received OR
#              Cabinet-internal incident confirmed — NOT initial alert).
#   Art 33(1)— threshold: notification required UNLESS "unlikely to result in a risk to the
#              rights and freedoms of natural persons" (decision tree below).
#   Art 34   — notify data subjects without undue delay IF HIGH risk to rights/freedoms.
#
# SIMULATION-ONLY GUARANTEE: this script contains NO real send paths — no email, no
# external HTTP to a supervisory authority, no customer notification. It only writes a
# local report + prints + (optionally) an INTERNAL review-ping to the DPO.

set -uo pipefail

CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"
AUDIT_LOG_ROOT="${LITELLM_AUDIT_LOG_ROOT:-${CABINET_ROOT}/proxy/logs}"
AUDIT_DIR="${AUDIT_LOG_ROOT}/audit"
OUT_DIR="${BREACH_SIM_OUTPUT_DIR:-${AUDIT_LOG_ROOT}/breach-sim}"
NOTIFY_SCRIPT="${CABINET_ROOT}/cabinet/scripts/notify-officer.sh"
TEST_MODE="${CABINET_HOOK_TEST_MODE:-0}"

log()  { echo "[breach-sim] $*"; }
warn() { echo "[breach-sim] WARNING: $*" >&2; }
die()  { echo "[breach-sim] ERROR:   $*" >&2; exit 1; }
hr()   { echo "──────────────────────────────────────────────────────────────"; }

# ── Parse args ──────────────────────────────────────────────────────────────
SCENARIO_FILE=""
NOW_OVERRIDE=""
for ((i=1; i<=$#; i++)); do
    case "${!i}" in
        --scenario-file) j=$((i+1)); SCENARIO_FILE="${!j:-}" ;;
        --now)           j=$((i+1)); NOW_OVERRIDE="${!j:-}" ;;
    esac
done

command -v jq >/dev/null 2>&1 || die "jq is required."

_now_epoch() {
    if [ -n "$NOW_OVERRIDE" ]; then
        date -u -d "$NOW_OVERRIDE" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$NOW_OVERRIDE" +%s 2>/dev/null || die "bad --now: $NOW_OVERRIDE"
    else
        date -u +%s
    fi
}
_iso_to_epoch() { date -u -d "$1" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$1" +%s 2>/dev/null || echo ""; }
_epoch_to_iso() { date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -r "$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "?"; }

echo
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║  GDPR Art 33/34 Breach-Notification TABLETOP SIMULATION              ║"
echo "║  SENDS NOTHING REAL — output is for COO-as-DPO + CoS review          ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"

# ── Step 1: load scenario (built-in fake Anthropic notice, or --scenario-file) ──
hr; log "Step 1 — breach scenario"
NOW_EPOCH="$(_now_epoch)"
if [ -n "$SCENARIO_FILE" ]; then
    [ -f "$SCENARIO_FILE" ] || die "scenario file not found: $SCENARIO_FILE"
    jq -e . "$SCENARIO_FILE" >/dev/null 2>&1 || die "scenario file is not valid JSON: $SCENARIO_FILE"
    SCENARIO="$(cat "$SCENARIO_FILE")"
    log "Loaded scenario from ${SCENARIO_FILE}"
else
    # Built-in default: fake Anthropic sub-processor notice. Anthropic processes requests
    # but Cabinet retains NO prompts/completions (only token counts + metadata) — so the
    # default is the realistic LOW-risk case; override with --scenario-file for high-risk drills.
    local_breach="$(_epoch_to_iso $((NOW_EPOCH - 432000)))"   # 5 days ago
    local_aware="$(_epoch_to_iso $((NOW_EPOCH - 3600)))"       # 1 hour ago
    SCENARIO="$(jq -n --arg b "$local_breach" --arg a "$local_aware" '{
        source: "Anthropic", breach_type: "sub_processor",
        breach_occurred_at: $b, awareness_at: $a,
        data_categories: ["api_request_metadata","token_counts"],
        involves_personal_data: false, severity: "low",
        description: "TEST scenario: Anthropic notified Cabinet of unauthorized access to a logging subsystem. Cabinet retains no prompts/completions (token counts + metadata only)."
    }')"
    log "Using built-in default scenario (fake Anthropic sub-processor notice)."
fi
SRC="$(echo "$SCENARIO" | jq -r '.source // "unknown"')"
AWARE_AT="$(echo "$SCENARIO" | jq -r '.awareness_at // empty')"
BREACH_AT="$(echo "$SCENARIO" | jq -r '.breach_occurred_at // empty')"
INVOLVES_PD="$(echo "$SCENARIO" | jq -r '.involves_personal_data // false')"
SEVERITY="$(echo "$SCENARIO" | jq -r '.severity // "low"')"
log "  source=${SRC} severity=${SEVERITY} involves_personal_data=${INVOLVES_PD}"
log "  breach_occurred_at=${BREACH_AT:-unknown}  awareness_at=${AWARE_AT:-unknown}"

# ── Step 2: Art 33 clock — 72h from CONFIRMED awareness ──────────────────────
hr; log "Step 2 — Article 33 clock (72h from confirmed awareness)"
AWARE_EPOCH="$(_iso_to_epoch "${AWARE_AT:-}")"
if [ -z "$AWARE_EPOCH" ]; then
    warn "awareness_at missing/unparseable — clock cannot start; flagging as a GAP."
    DEADLINE_ISO="UNKNOWN"; HOURS_LEFT="UNKNOWN"
else
    DEADLINE_EPOCH=$(( AWARE_EPOCH + 72*3600 ))
    DEADLINE_ISO="$(_epoch_to_iso "$DEADLINE_EPOCH")"
    HOURS_LEFT=$(( (DEADLINE_EPOCH - NOW_EPOCH) / 3600 ))
    log "  72h deadline: ${DEADLINE_ISO}  (hours remaining: ${HOURS_LEFT})"
    [ "$HOURS_LEFT" -lt 0 ] && warn "72h Article-33 window is OVERDUE by $(( -HOURS_LEFT ))h — escalate immediately."
fi

# ── Step 3: Art 33(1) risk-threshold decision tree ───────────────────────────
hr; log "Step 3 — Article 33(1) risk-to-rights-and-freedoms decision tree"
# Notification required UNLESS unlikely to result in a risk. Phase-1 heuristic:
#   - no personal data involved            -> LOW (unlikely to risk) -> Art 33(1) carve-out
#   - personal data + severity low         -> LOW (document, monitor)
#   - personal data + severity medium/high -> RISK -> Art 33 required; HIGH -> Art 34 too
RISK_LEVEL="low"; ART33_REQUIRED="false"; ART34_REQUIRED="false"; RATIONALE=""
if [ "$INVOLVES_PD" != "true" ]; then
    RISK_LEVEL="none"; RATIONALE="No personal data involved (Cabinet retains token counts + metadata only; no prompts/completions). Unlikely to result in a risk to rights/freedoms — Article 33(1) carve-out applies. Document + monitor; no supervisory or data-subject notification."
elif [ "$SEVERITY" = "low" ]; then
    RISK_LEVEL="low"; RATIONALE="Personal data involved but low severity — assess case-by-case; default document + monitor. If reassessed upward, escalate to the RISK path."
else
    RISK_LEVEL="$SEVERITY"; ART33_REQUIRED="true"; RATIONALE="Personal data + ${SEVERITY} severity — likely a risk to rights/freedoms. Article 33 supervisory notification REQUIRED within 72h."
    [ "$SEVERITY" = "high" ] && ART34_REQUIRED="true" && RATIONALE="${RATIONALE} HIGH risk — Article 34 data-subject notification ALSO required without undue delay."
fi
log "  risk_level=${RISK_LEVEL}  art_33_required=${ART33_REQUIRED}  art_34_required=${ART34_REQUIRED}"
log "  rationale: ${RATIONALE}"

# ── Step 4: identify affected cabinets from the FW-097 audit log ─────────────
hr; log "Step 4 — affected-cabinet identification (FW-097 audit log)"
declare -a AFFECTED=()
GAPS=""
if [ ! -d "$AUDIT_DIR" ]; then
    warn "audit dir ${AUDIT_DIR} not found — cannot enumerate affected cabinets (GAP)."
    GAPS="${GAPS}audit-dir-missing;"
else
    win_start="$(_iso_to_epoch "${BREACH_AT:-}")"; [ -z "$win_start" ] && win_start=0
    win_end="${AWARE_EPOCH:-$NOW_EPOCH}"
    shopt -s nullglob
    for f in "${AUDIT_DIR}"/*.jsonl; do
        slug="$(basename "$f" .jsonl)"
        # count entries in the breach window (any proxy/LLM activity = potentially in-scope)
        hits="$(jq -r --argjson s "$win_start" --argjson e "$win_end" '
            select((.ts // "" | if . == "" then 0 else (try (sub("Z$";"Z") | fromdateiso8601) catch 0) end) as $t | $t >= $s and $t <= $e) | .entry_id' "$f" 2>/dev/null | wc -l)"
        if [ "${hits:-0}" -gt 0 ]; then
            AFFECTED+=("$slug")
            log "  affected: ${slug} (${hits} audit entries in breach window)"
        fi
    done
    shopt -u nullglob
    [ "${#AFFECTED[@]}" -eq 0 ] && log "  no cabinets with activity in the breach window."
fi

# ── Step 5: SIMULATE the notification cascade (logs only — sends nothing) ─────
hr; log "Step 5 — cascade SIMULATION (nothing sent)"
if [ "$ART33_REQUIRED" = "true" ]; then
    log "  [SIM] WOULD notify supervisory authority (DK: Datatilsynet) within 72h — deadline ${DEADLINE_ISO}."
else
    log "  [SIM] Supervisory notification NOT required (Article 33(1) carve-out) — document the determination."
fi
for slug in "${AFFECTED[@]}"; do
    log "  [SIM] cabinet ${slug}: WOULD email the customer + raise a dashboard breach banner."
    [ "$ART34_REQUIRED" = "true" ] && log "  [SIM] cabinet ${slug}: HIGH-risk — WOULD notify data subjects without undue delay (Article 34)."
done
[ "${#AFFECTED[@]}" -eq 0 ] && [ "$ART33_REQUIRED" = "true" ] && { warn "Art 33 required but NO affected cabinets identified — manual review needed (GAP)."; GAPS="${GAPS}art33-required-but-no-cabinets;"; }

# ── Step 6: write the simulation report ──────────────────────────────────────
hr; log "Step 6 — simulation report"
mkdir -p "$OUT_DIR" || die "could not create ${OUT_DIR}."
REPORT="${OUT_DIR}/breach-sim-$(date -u +%Y%m%dT%H%M%SZ).json"
affected_json="$(printf '%s\n' "${AFFECTED[@]:-}" | jq -R . | jq -s 'map(select(length>0))')"
jq -n \
    --argjson scenario "$SCENARIO" \
    --arg deadline "$DEADLINE_ISO" --arg hours_left "$HOURS_LEFT" \
    --arg risk "$RISK_LEVEL" --arg a33 "$ART33_REQUIRED" --arg a34 "$ART34_REQUIRED" --arg rationale "$RATIONALE" \
    --argjson affected "$affected_json" --arg gaps "$GAPS" \
    '{
        simulation: true, sent_anything_real: false,
        generated_at: (now | todateiso8601),
        scenario: $scenario,
        article_33: { clock_72h_deadline: $deadline, hours_remaining: $hours_left, supervisory_notification_required: ($a33=="true") },
        article_33_1_threshold: { risk_level: $risk, rationale: $rationale },
        article_34: { data_subject_notification_required: ($a34=="true") },
        affected_cabinets: $affected,
        simulated_cascade: "see log output above (email + dashboard banner per cabinet; supervisory notice if required) — NOTHING SENT",
        gaps_flagged: ($gaps | split(";") | map(select(length>0)))
    }' > "$REPORT" || die "could not write report."
log "Report written: ${REPORT}"
echo
echo "  ── Summary ──────────────────────────────────────────────────────────"
echo "  risk_level            : ${RISK_LEVEL}"
echo "  Article 33 (authority): $([ "$ART33_REQUIRED" = "true" ] && echo "REQUIRED by ${DEADLINE_ISO}" || echo "not required (33(1) carve-out)")"
echo "  Article 34 (subjects) : $([ "$ART34_REQUIRED" = "true" ] && echo "REQUIRED" || echo "not required")"
echo "  affected cabinets     : ${#AFFECTED[@]}"
echo "  gaps                  : ${GAPS:-none}"
echo "  NOTHING SENT — review ${REPORT}"
echo "  ─────────────────────────────────────────────────────────────────────"

# ── Step 7: internal review-ping to the DPO (NOT a breach notification) ──────
REVIEW_MSG="Breach-notification TABLETOP simulation ran (nothing sent). risk=${RISK_LEVEL}, Art33=${ART33_REQUIRED}, Art34=${ART34_REQUIRED}, affected=${#AFFECTED[@]}, gaps=${GAPS:-none}. Review the report for gaps: ${REPORT}"
if [ "$TEST_MODE" = "1" ]; then
    echo "WOULD-NOTIFY coo: ${REVIEW_MSG}"
else
    bash "$NOTIFY_SCRIPT" coo "$REVIEW_MSG" 2>/dev/null || true
fi

exit 0
