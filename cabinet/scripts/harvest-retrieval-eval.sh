#!/bin/bash
# harvest-retrieval-eval.sh — self-generate a retrieval-quality eval set from
# THIS cabinet's own memory (R1, 2026-07-12 — org-memory study §5-R1).
#
# GENERIC / PORTABLE, by design. It reads high-signal, non-exhaust rows from
# cabinet_memory, derives a realistic topical query from each row's OWN leading
# content (the title/summary text an officer would actually search for), and
# emits {query, expected_ref, source_type} pairs. A fresh instance runs THIS
# with zero captain-specific input and gets its own eval set from its own first
# weeks of org memory — closing the only real retrieval cold-start gap (the
# eval no longer depends on any personal/non-portable seed). See the companion
# runner retrieval-eval.sh and the committed seed under
# cabinet/scripts/tests/fixtures/retrieval-eval-pairs.seed.json.
#
# WHY these types: exhaust rows (officer_trigger, trigger-archive,
# transcript-digest) are nervous-system plumbing, ~59% of the store and NOT
# knowledge (study §4-C3) — harvesting them would make the eval measure noise
# retrieval. The default set is the durable-knowledge surface only.
#
# HOW the query is derived (no LLM, deterministic): the leading QCHARS of the
# row's content, markdown-stripped and whitespace-collapsed. This is close
# enough to the source row to clear the vec floor (so a healthy ranker retrieves
# it) yet phrased as topical prose (so a ranking regression that reshuffles the
# pool drops it out of top-k). Ordering is by md5(ref) so re-runs are stable.
#
# Usage:
#   harvest-retrieval-eval.sh [--limit N] [--out FILE] [--types t1,t2,...]
#                             [--query-chars N] [--recall-k K]
# Defaults: --limit 20, --out stdout, high-signal types, --query-chars 110,
#           --recall-k 10. Requires NEON_CONNECTION_STRING (read-only SELECT;
#           the secret is used by psql, never printed).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export CABINET_ROOT
# shellcheck source=/dev/null
source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh"   # back-fills NEON/CABINET_ID from cabinet/.env

LIMIT=20
OUT=""
# Durable-knowledge surface only. session_memory + transcript-digest are
# EXCLUDED here (in addition to the exhaust types): they are per-officer/session
# working-state whose conversational, truncated content derives noisy queries —
# valid memory, but not the durable knowledge an org query targets, and they
# depress the eval baseline without measuring a real ranker regression.
TYPES="captain_decision,reflection,skill,experience_record,product_spec,role_definition,research_brief,working_note"
QCHARS=110
RECALL_K=10
while [ $# -gt 0 ]; do
  case "$1" in
    --limit) LIMIT="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --types) TYPES="$2"; shift 2 ;;
    --query-chars) QCHARS="$2"; shift 2 ;;
    --recall-k) RECALL_K="$2"; shift 2 ;;
    -h|--help) grep -E '^# ' "$0" | sed 's/^# //'; exit 0 ;;
    *) echo "harvest-retrieval-eval.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
  echo "harvest-retrieval-eval.sh: NEON_CONNECTION_STRING unset — cannot harvest from cabinet_memory" >&2
  exit 1
fi

cid_scope="$(memory_cabinet_scope)"

# TSV: expected_ref \t source_type \t query  (filters injection-safe via -v)
rows="$(psql "$NEON_CONNECTION_STRING" -q -t -A -F $'\t' \
  -v types="$TYPES" -v qchars="$QCHARS" -v lim="$LIMIT" -v cid="$cid_scope" \
  2>/dev/null <<'SQLEOF'
WITH picked AS (
  SELECT COALESCE(source_id, id::text) AS ref, source_type,
    btrim(regexp_replace(
      regexp_replace(LEFT(content, (:'qchars')::int), E'[#*>`~_\n\t\r]+', ' ', 'g'),
      '[[:space:]]+', ' ', 'g')) AS query
  FROM cabinet_memory
  WHERE superseded_by IS NULL
    AND source_type = ANY(string_to_array(:'types', ','))
    AND length(coalesce(content,'')) > 80
    AND (:'cid' = '' OR cabinet_id = :'cid' OR cabinet_id = 'main')
  ORDER BY md5(COALESCE(source_id, id::text))
  LIMIT (:'lim')::int
)
SELECT ref, source_type, query FROM picked WHERE length(query) >= 20;
SQLEOF
)"

if [ -z "$(printf '%s' "$rows" | tr -d '[:space:]')" ]; then
  echo "harvest-retrieval-eval.sh: no high-signal rows found (types=$TYPES) — nothing to harvest" >&2
  exit 1
fi

# Build the pairs array with jq (content travels as DATA, never as code).
pairs_json="$(printf '%s\n' "$rows" | jq -R -s '
  split("\n") | map(select(length>0) | split("\t")
    | {query: .[2], expected_ref: .[0], source_type: .[1]})
')"

meta_json="$(jq -n \
  --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg cid "${CABINET_ID:-main}" \
  --argjson k "$RECALL_K" \
  --argjson pairs "${pairs_json:-[]}" \
  '{generated_at: $ts,
    generator: "harvest-retrieval-eval.sh",
    cabinet_id: $cid,
    recall_k: $k,
    note: "Self-generated from this cabinet_memory (high-signal, non-exhaust rows). Regenerate on any instance: bash cabinet/scripts/harvest-retrieval-eval.sh --out <file>. Each query is derived from a row leading content; expected_ref is that row source_id. Run the gate with retrieval-eval.sh --pairs <file>.",
    pairs: $pairs}')"

if [ -n "$OUT" ]; then
  printf '%s\n' "$meta_json" > "$OUT"
  echo "harvested $(printf '%s' "$meta_json" | jq '.pairs | length') pairs -> $OUT" >&2
else
  printf '%s\n' "$meta_json"
fi
