#!/bin/bash
# cabinet/scripts/meta-cognition/harvest-check.sh — LAYER 2 (HARVEST) driver
#
# The deterministic half of the principle-harvester (the orchestration lives in
# the evolved skill memory/skills/evolved/principle-harvester.md). This script:
#
#   --status    Report whether the accretion threshold has been crossed since the
#               last harvest (the content trigger). Echoes a one-line verdict and
#               exits 0 if a harvest is DUE, 10 if not (so callers can branch).
#
#   --corpus    Emit the harvest corpus: every `## ` / `### ` rule heading in
#               captain-patterns.md that is NOT on the LEAVE-AS-IS allow-list
#               (facts/IDs/secrets/germline are dropped), one per line as
#               "<overlap-eligible?>\t<heading>". This is what the fresh-context
#               finders mine for collapse-to-principle clusters.
#
#   --mark      Stamp "harvest happened now" (sets the accretion mark to the
#               current counter) so the next harvest fires only on NEW accretion.
#               Call this AFTER a harvest pass completes.
#
# Selectors enforced here (design's generator+selector rule):
#   * Accretion threshold (content trigger) — never harvests on a clock.
#   * LEAVE-AS-IS allow-list — facts can never enter the collapse corpus.
#
# Secrets: NONE. Reads one local markdown + a Redis counter. No network.
# Reversibility: rm this file; the skill falls back to a manual corpus read.

set -u

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck source=/dev/null
. "$SELF_DIR/lib.sh"

PATTERNS_FILE="${PATTERNS_FILE:-$MC_REPO_ROOT/shared/interfaces/captain-patterns.md}"

usage() {
  echo "usage: harvest-check.sh --status | --corpus | --mark" >&2
  exit 2
}

MODE="${1:-}"
case "$MODE" in
  --status)
    crossed="$(mc_accretion_threshold_crossed)"
    since="$(mc_accretion_since_harvest)"
    if [ "${crossed:-0}" = "1" ]; then
      echo "HARVEST DUE — accretion since last harvest = ${since} (threshold ${MC_ACCRETION_THRESHOLD})"
      exit 0
    fi
    echo "no harvest — accretion since last harvest = ${since} (threshold ${MC_ACCRETION_THRESHOLD})"
    exit 10
    ;;
  --mark)
    mc_accretion_mark_harvest
    echo "harvest mark stamped (counter=$(redis-cli -h "$MC_REDIS_HOST" -p "$MC_REDIS_PORT" GET "$MC_ACCRETION_KEY" 2>/dev/null))"
    exit 0
    ;;
  --corpus)
    : # fall through
    ;;
  *)
    usage
    ;;
esac

# --corpus: emit collapse-eligible rule headings (allow-list applied). For each
# `## `/`### ` heading, take the heading + its short body as the candidate text
# and run mc_is_leave_as_is; drop the ones that are facts/IDs/germline.
[ -f "$PATTERNS_FILE" ] || { echo "harvest-check.sh: no patterns file at $PATTERNS_FILE" >&2; exit 1; }

# Extract heading + first ~200 chars of body via python (robust), then filter in
# bash through the allow-list selector.
python3 - "$PATTERNS_FILE" <<'PYEOF' | while IFS=$'\t' read -r heading blurb; do
import sys, re
path = sys.argv[1]
with open(path) as f:
    text = f.read()
heads = list(re.finditer(r'^#{2,3}\s+(.*)$', text, re.MULTILINE))
for i, h in enumerate(heads):
    title = h.group(1).strip()
    start = h.end()
    end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
    body = re.sub(r'\s+', ' ', text[start:end][:200]).strip()
    # tab-separated: heading <TAB> body-blurb (for the allow-list check)
    sys.stdout.write(f"{title}\t{body}\n")
PYEOF
  [ -z "$heading" ] && continue
  # Drop the master-directive ANCHORS (A1..An / "(anchor)") — collapsing a
  # foundational anchor is the over-reach risk; anchors are germline-adjacent and
  # only the Captain restructures them. Also drop explicit facts/memory headings.
  case "$heading" in
    A[0-9]*\ —\ *|*\(anchor\)|People*|*"concrete facts"*) continue ;;
  esac
  if mc_is_leave_as_is "$heading $blurb" >/dev/null 2>&1; then
    # On the allow-list → a fact/ID/germline heading; never a collapse target.
    continue
  fi
  printf 'eligible\t%s\n' "$heading"
done
exit 0
