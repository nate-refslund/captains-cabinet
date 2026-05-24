#!/usr/bin/env bash
# cabinet/scripts/sla-tracker.sh — Shared GDPR-request SLA tracker
#
# Tracks Article-15 access + Article-17 erasure requests against the 30-day
# SLA mandated by GDPR Article 12(3). Generic substrate — consumed by both
# customer-erasure.sh (FW-100 Spec 055 AC#6) and the Article-15 access
# runbook (Spec 052).
#
# Ticket store: ${CABINET_GDPR_TICKET_DIR}/  (runtime data, gitignored)
#   Each ticket: <ticket-id>.json
#
# Subcommands:
#   create <type> <cabinet_id>  — type ∈ {access, erasure}
#   complete <ticket-id>        — mark done (idempotent)
#   check                       — scan open tickets; alert CoS at 25/29/31 days
#   list                        — print open tickets with day counts
#
# Env:
#   CABINET_GDPR_TICKET_DIR     — ticket store dir (default: /opt/founders-cabinet/proxy/logs/gdpr-requests)
#   CABINET_HOOK_TEST_MODE      — if 1, suppress notify-officer.sh + echo WOULD-NOTIFY instead
#   CABINET_SLA_NOW_OVERRIDE    — TEST ONLY: override "now" for `check` (UTC ISO or epoch)
#
# Usage: bash cabinet/scripts/sla-tracker.sh <subcommand> [args...]
#
# IMPORTANT: notify-officer.sh message strings use plain variable expansion ONLY —
# no backticks, no $(...) — because the trigger system shell-evaluates message text.

set -euo pipefail

TICKET_DIR="${CABINET_GDPR_TICKET_DIR:-/opt/founders-cabinet/proxy/logs/gdpr-requests}"
NOTIFY_SCRIPT="/opt/founders-cabinet/cabinet/scripts/notify-officer.sh"
TEST_MODE="${CABINET_HOOK_TEST_MODE:-0}"

# ── Helpers ──────────────────────────────────────────────────────────────────

die() { echo "ERROR: $*" >&2; exit 1; }

# Return "now" as UTC epoch seconds, honouring CABINET_SLA_NOW_OVERRIDE (test-only).
_now_epoch() {
    if [ -n "${CABINET_SLA_NOW_OVERRIDE:-}" ]; then
        # Accept either ISO (2026-01-01T00:00:00Z) or raw epoch integer
        if echo "$CABINET_SLA_NOW_OVERRIDE" | grep -qE '^[0-9]+$'; then
            echo "$CABINET_SLA_NOW_OVERRIDE"
        else
            date -u -d "$CABINET_SLA_NOW_OVERRIDE" +%s 2>/dev/null \
                || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$CABINET_SLA_NOW_OVERRIDE" +%s 2>/dev/null \
                || die "Cannot parse CABINET_SLA_NOW_OVERRIDE: $CABINET_SLA_NOW_OVERRIDE"
        fi
    else
        date -u +%s
    fi
}

# Convert epoch seconds to UTC ISO-8601 string.
_epoch_to_iso() {
    local epoch="$1"
    date -u -d "@$epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -r "$epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || die "Cannot convert epoch to ISO: $epoch"
}

# Parse an ISO date string to epoch seconds.
_iso_to_epoch() {
    local iso="$1"
    date -u -d "$iso" +%s 2>/dev/null \
        || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$iso" +%s 2>/dev/null \
        || die "Cannot parse ISO date: $iso"
}

# ── Subcommand: create ────────────────────────────────────────────────────────

cmd_create() {
    local type="${1:-}" cabinet_id="${2:-}"
    [ -n "$type" ]       || die "create requires <type>: access or erasure"
    [ -n "$cabinet_id" ] || die "create requires <cabinet_id>"
    case "$type" in
        access|erasure) ;;
        *) die "type must be 'access' or 'erasure', got: $type" ;;
    esac

    mkdir -p "$TICKET_DIR"

    local now_iso
    now_iso="$(date -u +%Y-%m-%dT%H%M%SZ)"
    local ticket_id="${type}-${cabinet_id}-${now_iso}"
    local requested_at
    requested_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    local due_at
    due_at="$(date -u -d "${requested_at} +30 days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
              || date -u -v+30d -j -f "%Y-%m-%dT%H:%M:%SZ" "${requested_at}" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"

    local ticket_file="${TICKET_DIR}/${ticket_id}.json"
    jq -n \
        --arg ticket_id    "$ticket_id" \
        --arg type         "$type" \
        --arg cabinet_id   "$cabinet_id" \
        --arg requested_at "$requested_at" \
        --arg due_at       "$due_at" \
        '{
            ticket_id:    $ticket_id,
            type:         $type,
            cabinet_id:   $cabinet_id,
            requested_at: $requested_at,
            due_at:       $due_at,
            status:       "open",
            completed_at: null,
            alerts_sent:  []
        }' > "$ticket_file"

    echo "$ticket_id"
    echo "$due_at"
}

# ── Subcommand: complete ──────────────────────────────────────────────────────

cmd_complete() {
    local ticket_id="${1:-}"
    [ -n "$ticket_id" ] || die "complete requires <ticket-id>"

    local ticket_file="${TICKET_DIR}/${ticket_id}.json"
    [ -f "$ticket_file" ] || die "Ticket not found: $ticket_file"

    local status
    status="$(jq -r '.status' "$ticket_file")"
    if [ "$status" = "done" ]; then
        echo "Ticket ${ticket_id} already complete (idempotent)."
        return 0
    fi

    local completed_at
    completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    local tmp_file
    tmp_file="$(mktemp "${ticket_file}.tmp.XXXXXX")"
    jq --arg completed_at "$completed_at" \
       '.status = "done" | .completed_at = $completed_at' \
       "$ticket_file" > "$tmp_file" \
       && mv "$tmp_file" "$ticket_file"

    echo "Ticket ${ticket_id} marked complete at ${completed_at}."
}

# ── Subcommand: check ─────────────────────────────────────────────────────────

cmd_check() {
    mkdir -p "$TICKET_DIR"
    local now_epoch
    now_epoch="$(_now_epoch)"

    local found_any=0
    local ticket_file
    for ticket_file in "${TICKET_DIR}"/*.json; do
        [ -f "$ticket_file" ] || continue

        # Fail-safe: skip malformed ticket files
        local ticket_id type cabinet_id requested_at due_at status alerts_sent_json
        if ! ticket_id="$(jq -re '.ticket_id'      "$ticket_file" 2>/dev/null)" ||
           ! type="$(jq       -re '.type'           "$ticket_file" 2>/dev/null)" ||
           ! cabinet_id="$(jq -re '.cabinet_id'     "$ticket_file" 2>/dev/null)" ||
           ! requested_at="$(jq -re '.requested_at' "$ticket_file" 2>/dev/null)" ||
           ! due_at="$(jq     -re '.due_at'         "$ticket_file" 2>/dev/null)" ||
           ! status="$(jq     -re '.status'         "$ticket_file" 2>/dev/null)"; then
            echo "WARNING: skipping malformed ticket file: $ticket_file" >&2
            continue
        fi

        # Skip completed tickets
        if [ "$status" = "done" ]; then
            continue
        fi

        found_any=1

        local requested_epoch
        if ! requested_epoch="$(_iso_to_epoch "$requested_at" 2>/dev/null)"; then
            echo "WARNING: cannot parse requested_at in $ticket_file, skipping" >&2
            continue
        fi

        local elapsed_secs=$(( now_epoch - requested_epoch ))
        local days_elapsed=$(( elapsed_secs / 86400 ))

        # Determine which alert level applies (if any)
        local level=""
        if   [ "$days_elapsed" -ge 31 ]; then
            level="BREACH"
        elif [ "$days_elapsed" -ge 29 ]; then
            level="urgent"
        elif [ "$days_elapsed" -ge 25 ]; then
            level="approaching"
        fi

        [ -n "$level" ] || continue

        # Check idempotency — only alert if this level NOT already in alerts_sent[]
        alerts_sent_json="$(jq -c '.alerts_sent // []' "$ticket_file")"
        if echo "$alerts_sent_json" | jq -e --arg l "$level" 'index($l) != null' >/dev/null 2>&1; then
            # Already alerted for this level — skip
            continue
        fi

        # Send or simulate the alert
        local msg
        msg="GDPR ${type} SLA ${level}: ticket ${ticket_id} (cabinet ${cabinet_id}) day ${days_elapsed} of 30, due ${due_at}. Action required."
        if [ "${TEST_MODE}" = "1" ]; then
            echo "WOULD-NOTIFY cos: ${level} ${ticket_id}"
        else
            bash "$NOTIFY_SCRIPT" cos "$msg" 2>/dev/null || true
        fi

        # Persist the alert level to alerts_sent[] (idempotency tracking)
        local tmp_file
        tmp_file="$(mktemp "${ticket_file}.tmp.XXXXXX")"
        jq --arg level "$level" \
           '.alerts_sent = (.alerts_sent // []) + [$level]' \
           "$ticket_file" > "$tmp_file" \
           && mv "$tmp_file" "$ticket_file"
    done

    if [ "$found_any" -eq 0 ]; then
        : # no open tickets — normal
    fi
}

# ── Subcommand: list ──────────────────────────────────────────────────────────

cmd_list() {
    mkdir -p "$TICKET_DIR"
    local now_epoch
    now_epoch="$(_now_epoch)"

    local header_printed=0
    local ticket_file
    for ticket_file in "${TICKET_DIR}"/*.json; do
        [ -f "$ticket_file" ] || continue

        local status
        status="$(jq -re '.status' "$ticket_file" 2>/dev/null)" || continue
        [ "$status" = "open" ] || continue

        if [ "$header_printed" -eq 0 ]; then
            printf '%-50s  %-10s  %-22s  %-22s  %s  %s\n' \
                "TICKET_ID" "TYPE" "REQUESTED_AT" "DUE_AT" "ELAPSED_DAYS" "REMAINING_DAYS"
            printf '%s\n' "$(printf '─%.0s' {1..120})"
            header_printed=1
        fi

        local ticket_id type cabinet_id requested_at due_at
        ticket_id="$(jq -r '.ticket_id'      "$ticket_file")"
        type="$(jq      -r '.type'           "$ticket_file")"
        requested_at="$(jq -r '.requested_at' "$ticket_file")"
        due_at="$(jq    -r '.due_at'         "$ticket_file")"

        local requested_epoch elapsed_secs days_elapsed days_remaining
        requested_epoch="$(_iso_to_epoch "$requested_at" 2>/dev/null)" || continue
        elapsed_secs=$(( now_epoch - requested_epoch ))
        days_elapsed=$(( elapsed_secs / 86400 ))
        days_remaining=$(( 30 - days_elapsed ))

        printf '%-50s  %-10s  %-22s  %-22s  %12d  %14d\n' \
            "$ticket_id" "$type" "$requested_at" "$due_at" \
            "$days_elapsed" "$days_remaining"
    done

    if [ "$header_printed" -eq 0 ]; then
        echo "No open GDPR tickets."
    fi
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

SUBCOMMAND="${1:-}"
shift || true

case "$SUBCOMMAND" in
    create)   cmd_create   "$@" ;;
    complete) cmd_complete "$@" ;;
    check)    cmd_check          ;;
    list)     cmd_list           ;;
    *) die "Unknown subcommand '${SUBCOMMAND}'. Use: create | complete | check | list" ;;
esac
