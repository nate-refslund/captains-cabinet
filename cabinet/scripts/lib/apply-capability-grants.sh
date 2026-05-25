#!/usr/bin/env bash
# cabinet/scripts/lib/apply-capability-grants.sh — Spec 052 Phase 5 (CoS I2) grant reader.
#
# SOURCE this. Provides apply_capability_grants <preset_yml> <target_conf> — reads the preset's
# optional `capability_grants:` block and appends `<officer>:<capability>` grant lines to the
# GENERATED cabinet's officer-capabilities.conf, so a commercial cabinet's officers carry the
# grants their preset declares (e.g. emits_customer_audit_events for cos/coo/cro).
#
# WHY preset-driven (Option B, CTO-ratified): the preset is the single source of truth for what a
# GENERATED cabinet gets — grants live with the preset, no hardcoded preset-name checks in scripts,
# any future generated-conf preset reuses this with zero new code.
#
# CONTRACT (CoS spec): optional (no-op if no block); appends after the header; IDEMPOTENT (skip if
# the grant is already present); preserves existing framework-default grants; if a capability is not
# in the conf's header doc-comment listing, WARN to stderr but continue.
#
# CONSTRAINT: operates ONLY on the <target_conf> passed by the caller (the cabinet's conf). The
# bootstrap passes the GENERATED cabinet conf — never the dev/STEP conf at /opt. This lib never
# resolves a path itself, so it cannot touch the dev conf.
#
# Block format (FINAL conf slugs, inline list):
#   capability_grants:
#     cos: [emits_customer_audit_events]
#     coo: [emits_customer_audit_events, other_cap]

# apply_capability_grants <preset_yml> <target_conf>  — returns 0 (fail-safe).
apply_capability_grants() {
    local preset_yml="${1:-}" conf="${2:-}"
    [ -f "$preset_yml" ] && [ -f "$conf" ] || return 0

    # Extract the indented, non-comment lines under `capability_grants:` (block ends at the next
    # column-0 line or EOF). Dependency-free — no yq/python needed for this fixed structure.
    local block
    block="$(awk '
        /^capability_grants:[[:space:]]*$/ { ingrants=1; next }
        ingrants && /^[^[:space:]]/        { ingrants=0 }
        ingrants && /^[[:space:]]*#/       { next }
        ingrants && NF                     { print }
    ' "$preset_yml")"
    [ -n "$block" ] || return 0

    # Parse each `  <officer>: [<cap>, <cap>]` line; append each grant idempotently.
    # IMPORTANT: use a here-string (<<<) + a for-loop, NOT `cmd | while` — a pipe forks a SUBSHELL
    # whose file appends do not reliably persist (lost-state footgun). <<< keeps the loop in the
    # current shell so the >> appends + idempotency reads land on the real file.
    local line off caps cap
    while IFS= read -r line; do
        off="$(printf '%s' "$line"  | sed -nE 's/^[[:space:]]*([A-Za-z0-9_-]+)[[:space:]]*:[[:space:]]*\[.*/\1/p')"
        caps="$(printf '%s' "$line" | sed -nE 's/^[[:space:]]*[A-Za-z0-9_-]+[[:space:]]*:[[:space:]]*\[([^]]*)\].*/\1/p')"
        [ -n "$off" ] && [ -n "$caps" ] || continue
        for cap in ${caps//,/ }; do   # comma->space then word-split (capability names are safe identifiers)
            cap="$(printf '%s' "$cap" | tr -d '[:space:]')"
            [ -n "$cap" ] || continue
            # safety: warn (don't block) if the capability isn't documented in the conf header listing
            grep -q "^#.*${cap}" "$conf" 2>/dev/null \
                || echo "apply-capability-grants: WARN: capability '$cap' not in $conf header listing" >&2
            # idempotent append
            if ! grep -q "^${off}:${cap}$" "$conf" 2>/dev/null; then
                printf '%s:%s\n' "$off" "$cap" >> "$conf"
            fi
        done
    done <<< "$block"
    return 0
}
