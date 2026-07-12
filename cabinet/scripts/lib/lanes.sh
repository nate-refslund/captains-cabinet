#!/bin/bash
# lanes.sh — instance-config resolvers for lane + officer names (Wave G,
# lane-name instance-split, 2026-07-12).
#
# CORE RULE: lane and officer names are INSTANCE DATA, never framework/script
# literals. Shared bash consumers source this lib and resolve names from the
# same sources the python side uses (framework/env.py precedent:
# captain_name / org_domains / tasks_board; framework/acting/run_action_lane.py
# _context_slugs is the parse these functions mirror):
#
#   cabinet_lanes                lane slugs — one per line, sorted, deduped —
#                                from instance/config/contexts/*.yml (the
#                                first `slug:` scalar per file; _default.yml
#                                has no slug and is skipped by construction).
#                                DELIBERATELY UNFILTERED by `active:` — on the
#                                launcher instance some contexts are
#                                active:false R2-pending declarations while
#                                their officers RUN LIVE, so an active-filtered
#                                enum would silently drop running lanes.
#   cabinet_officers             officer slugs — one per line, first-seen file
#                                order — the officer column of
#                                cabinet/officer-capabilities.conf.
#   cabinet_deploys_code_officer the FIRST officer holding deploys_code (eval
#                                probes use it as the live deploy officer).
#   cabinet_org_domains          the org's internal domains — one per line,
#                                lowercased, order preserved — bash twin of
#                                framework.env.org_domains(): instance/config/
#                                platform.yml `org_domains:` list, else
#                                product.yml (top-level or `product:`-nested).
#
# FAIL-HONEST CONTRACT (the tasks_board fail-closed precedent): pure stdout,
# read-only, no caching, no network, no eval — config values are DATA, only
# ever echoed. Unreadable/missing config => EMPTY output + rc 1. A readable
# source that legitimately declares nothing => empty output + rc 0 for the
# set-valued functions (an honest empty set), rc 1 for the scalar-valued
# cabinet_deploys_code_officer (an empty scalar is never consumable). NEVER a
# baked-in name fallback — consumers fail loudly at their own seam instead.
#
# Portability: macOS /bin/bash 3.2 safe (awk does the lifting; no readarray,
# no bash assoc arrays). Safe to source under `set -uo pipefail`.
#
# Usage:
#   source "$CABINET_ROOT/cabinet/scripts/lib/lanes.sh"
#   probe_officer="$(cabinet_deploys_code_officer)" || echo "unresolved" >&2

_LANES_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$_LANES_LIB_DIR/../../.." && pwd)}"

# Lane slugs from instance/config/contexts/*.yml. Parse mirrors
# run_action_lane._context_slugs byte-for-byte so the two enums can merge at a
# germline window: per file, the FIRST line whose stripped form starts with
# `slug:` wins (even when its value is empty — the file yields nothing then);
# value is whitespace-stripped, then double-quote-stripped, then
# single-quote-stripped, then lowercased.
cabinet_lanes() {
  local dir="$CABINET_ROOT/instance/config/contexts"
  [ -d "$dir" ] && [ -r "$dir" ] || return 1
  LC_ALL=C awk '
    FNR == 1 { taken = 0 }
    taken { next }
    {
      line = $0
      gsub(/^[ \t]+|[ \t\r]+$/, "", line)
      if (line ~ /^slug:/) {
        taken = 1
        val = substr(line, index(line, ":") + 1)
        gsub(/^[ \t]+|[ \t]+$/, "", val)
        gsub(/^"+|"+$/, "", val)
        gsub(/^'\''+|'\''+$/, "", val)
        if (val != "") print tolower(val)
      }
    }
  ' "$dir"/*.yml 2>/dev/null | LC_ALL=C sort -u
  return 0
}

# Officer slugs from cabinet/officer-capabilities.conf: skip comments/blanks,
# officer = text before the first `:`, deduped in first-seen file order (the
# conf groups an officer's capability rows, so this reproduces roster order).
cabinet_officers() {
  local conf="$CABINET_ROOT/cabinet/officer-capabilities.conf"
  [ -f "$conf" ] && [ -r "$conf" ] || return 1
  LC_ALL=C awk -F: '
    /^[ \t]*#/ { next }
    /^[ \t]*$/ { next }
    NF >= 2 {
      o = $1
      gsub(/^[ \t]+|[ \t]+$/, "", o)
      if (o != "" && !(o in seen)) { seen[o] = 1; print o }
    }
  ' "$conf"
  return 0
}

# The first officer holding the deploys_code capability (file order). Empty =>
# no holder declared => rc 1 (an eval/probe consumer must fail loudly, never
# invent a default officer). TWIN PARITY with env.deploys_code_officer:
# partition at the FIRST colon and compare the FULL remainder, so a malformed
# multi-colon row (`x:deploys_code:y`) is NOT a holder on either side (the
# old `-F: $2` parse matched it; python never did).
cabinet_deploys_code_officer() {
  local conf="$CABINET_ROOT/cabinet/officer-capabilities.conf"
  [ -f "$conf" ] && [ -r "$conf" ] || return 1
  local officer
  officer=$(LC_ALL=C awk '
    /^[ \t]*#/ { next }
    {
      i = index($0, ":")
      if (i == 0) next
      o = substr($0, 1, i - 1)
      c = substr($0, i + 1)
      gsub(/^[ \t]+|[ \t]+$/, "", o)
      gsub(/^[ \t\r]+|[ \t\r]+$/, "", c)
      if (o != "" && c == "deploys_code") { print o; exit }
    }
  ' "$conf")
  [ -n "$officer" ] || return 1
  printf '%s\n' "$officer"
}

# Org internal email domains — bash twin of framework.env.org_domains():
# platform.yml first, then product.yml; a top-level `org_domains:` list, or
# (product.yml) one nested directly under `product:`. Items lowercased,
# whitespace/quote-stripped, inline `#` comments dropped, ORDER PRESERVED
# (env.py preserves order; no sort here). BLOCK-STYLE lists ONLY
# (`org_domains:` header + `- item` lines — the form the live file and the
# .example twin both declare); the python twin's yaml.safe_load ALSO accepts
# inline-flow `org_domains: [a, b]`, which THIS parser resolves to nothing
# (rc 1 — the twins diverge only in the documented stricter direction: no
# anchors, never wrong anchors — declare block-form). First file yielding a
# non-empty list wins; none => empty + rc 1 (framework treats every recipient
# as external then — the conservative ceiling; consumers here likewise get no
# free anchors).
cabinet_org_domains() {
  local rel p out
  for rel in "instance/config/platform.yml" "instance/config/product.yml"; do
    p="$CABINET_ROOT/$rel"
    [ -f "$p" ] && [ -r "$p" ] || continue
    out=$(LC_ALL=C awk '
      /^[^ \t#-]/ {
        in_prod  = ($0 ~ /^product:[ \t\r]*$/) ? 1 : 0
        collect  = ($0 ~ /^org_domains:[ \t\r]*$/) ? 1 : 0
        next
      }
      in_prod && /^[ \t]+org_domains:[ \t\r]*$/ { collect = 1; next }
      collect {
        if ($0 !~ /^[ \t]*-[ \t]*/) { collect = 0; next }
        line = $0
        sub(/^[ \t]*-[ \t]*/, "", line)
        sub(/[ \t]+#.*$/, "", line)
        gsub(/^[ \t]+|[ \t\r]+$/, "", line)
        gsub(/^"+|"+$/, "", line)
        gsub(/^'\''+|'\''+$/, "", line)
        if (line != "") print tolower(line)
      }
    ' "$p")
    if [ -n "$out" ]; then
      printf '%s\n' "$out"
      return 0
    fi
  done
  return 1
}
