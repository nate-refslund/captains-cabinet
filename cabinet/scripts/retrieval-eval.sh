#!/bin/bash
# retrieval-eval.sh — recall@k + MRR gate for memory_search ranking (R1,
# 2026-07-12 — org-memory study §5-R1).
#
# Runs each {query -> expected_ref} pair through memory_search and measures
# whether (recall@k) and where (MRR) the expected row is retrieved. This is the
# regression GATE the org spine never had: the blended weights (0.60/0.25/0.15),
# the 0.45 vec floor, and the rerank stage all shipped unmeasured. TWO floors,
# because they trip on DIFFERENT damage (R1-EVAL-NO-TEETH fix, 2026-07-12):
#   recall@k >= --floor      trips on POOL damage (expected row evicted from
#       the returned set). At --limit == k it is ORDER-BLIND — a worst-first
#       rerank still counts every "hit". Recall HITs count rank <= k only, so
#       running with --limit > k makes the k-cut order-sensitive again.
#   MRR >= --mrr-floor       trips on ORDER damage (row present but buried):
#       empirically, a rerank sorted ascending keeps recall@10 = 0.95 while
#       MRR collapses 0.925 -> ~0.10 — only this floor catches it.
# It makes "context handling excellent" MEASURABLE instead of asserted.
#
# Pairs come from the committed seed (cabinet/scripts/tests/fixtures/
# retrieval-eval-pairs.seed.json) or a fresh self-generated set from
# harvest-retrieval-eval.sh (portable to any instance).
#
# TWO ARMS (no-rerank arm added 2026-07-15 — closes the R1 landing's named
# residual "rerank rescues pool damage"):
#   rerank (default)   the production path — blended pool + Voyage rerank.
#   --no-rerank        exports CABINET_MEMORY_RERANK=off so memory_rerank
#       short-circuits to the BLENDED-order top-k cut: the same floors then
#       measure the blended weights (0.60/0.25/0.15 + vec floor) directly.
#       While rerank is live it can rescue a damaged pool order, so a
#       weight-swap passes the rerank arm — only this arm catches it. A
#       blended-arm breach is a REAL finding even when the rerank arm passes.
#       The JSON verdict carries arm: "rerank"|"no-rerank" (derived from the
#       EFFECTIVE env, so an inherited CABINET_MEMORY_RERANK=off is labeled
#       honestly).
#
# Usage:
#   retrieval-eval.sh [--pairs FILE] [--k K] [--floor F] [--mrr-floor M]
#                     [--limit L] [--min-score S] [--no-rerank] [--json]
#                     [--quiet]
# Defaults: --pairs seed, --k from the pairs file (.recall_k, else 10),
#           --floor 0.70, --mrr-floor 0.50 (seed baseline MRR ~0.925; an
#           order-inverted ranker scores ~0.10, so 0.50 has margin both ways),
#           --limit = k, --min-score = memory_search default.
# Exit: 0 if recall@k >= floor AND MRR >= mrr-floor; 1 if either gate fails;
#       2 on usage/setup error.
# Requires NEON_CONNECTION_STRING (+ VOYAGE_API_KEY for the hybrid+rerank path
# AND for the --no-rerank arm's query embeddings; keyless degrades to lexical
# and still scores). Secrets used by the lib, never printed.
# Nightly both-arm gate + verdict ledger: cabinet/scripts/retrieval-eval-nightly.sh
# (services.yml row `retrieval-eval`, 03:50).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export CABINET_ROOT
# shellcheck source=/dev/null
source "$CABINET_ROOT/cabinet/scripts/lib/memory.sh"

PAIRS="$CABINET_ROOT/cabinet/scripts/tests/fixtures/retrieval-eval-pairs.seed.json"
K=""
FLOOR="0.70"
MRR_FLOOR="0.50"
LIMIT=""
MIN_SCORE=""
JSON=0
QUIET=0
NO_RERANK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pairs) PAIRS="$2"; shift 2 ;;
    --k) K="$2"; shift 2 ;;
    --floor) FLOOR="$2"; shift 2 ;;
    --mrr-floor) MRR_FLOOR="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --min-score) MIN_SCORE="$2"; shift 2 ;;
    --no-rerank) NO_RERANK=1; shift ;;
    --json) JSON=1; shift ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) grep -E '^# ' "$0" | sed 's/^# //'; exit 0 ;;
    *) echo "retrieval-eval.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Arm selection: --no-rerank exports the memory_rerank seam off. The arm LABEL
# is derived from the EFFECTIVE env after that export — an inherited
# CABINET_MEMORY_RERANK=off without the flag still labels "no-rerank", never
# a mislabeled rerank verdict.
[ "$NO_RERANK" = 1 ] && export CABINET_MEMORY_RERANK=off
case "$(printf '%s' "${CABINET_MEMORY_RERANK:-on}" | tr '[:upper:]' '[:lower:]')" in
  off|0|no|false) ARM="no-rerank" ;;
  *) ARM="rerank" ;;
esac

[ -f "$PAIRS" ] || { echo "retrieval-eval.sh: pairs file not found: $PAIRS" >&2; exit 2; }
if ! jq -e . "$PAIRS" >/dev/null 2>&1; then
  echo "retrieval-eval.sh: pairs file is not valid JSON: $PAIRS" >&2; exit 2
fi
if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
  echo "retrieval-eval.sh: NEON_CONNECTION_STRING unset — cannot run retrieval against cabinet_memory" >&2
  exit 2
fi

# Resolve k (CLI > pairs file .recall_k > 10) and limit (= k unless overridden).
[ -z "$K" ] && K="$(jq -r '.recall_k // 10' "$PAIRS")"
case "$K" in ''|*[!0-9]*) K=10 ;; esac
[ -z "$LIMIT" ] && LIMIT="$K"

TOTAL=0; HITS=0; RR_SUM=0
MISSES=""
# ref \t query per pair (ref first: it never contains a tab; jq @tsv escapes any
# embedded control chars so the real tab is an unambiguous delimiter).
while IFS=$'\t' read -r ref query; do
  [ -z "$ref" ] && continue
  TOTAL=$((TOTAL+1))
  results="$(memory_search "$query" "" "" "$LIMIT" "$MIN_SCORE" 2>/dev/null | cut -f8)"
  rank="$(printf '%s\n' "$results" | grep -nxF -- "$ref" 2>/dev/null | head -1 | cut -d: -f1)"
  if [ -n "$rank" ] && [ "$rank" -le "$K" ]; then
    HITS=$((HITS+1))
    RR_SUM="$(awk -v s="$RR_SUM" -v r="$rank" 'BEGIN{printf "%.6f", s + 1.0/r}')"
    [ "$QUIET" = 0 ] && [ "$JSON" = 0 ] && printf '  HIT   rank=%-2s  %s\n' "$rank" "$ref"
  elif [ -n "$rank" ]; then
    # Found but past the k-cut (only possible when --limit > k): a recall@k
    # MISS — this is exactly the order/eviction sensitivity the k-cut buys —
    # but the find still informs MRR (bounded MRR@limit, standard practice).
    RR_SUM="$(awk -v s="$RR_SUM" -v r="$rank" 'BEGIN{printf "%.6f", s + 1.0/r}')"
    MISSES="${MISSES}${ref}\n"
    [ "$QUIET" = 0 ] && [ "$JSON" = 0 ] && printf '  MISS  rank=%-2s  %s (past k=%s cut)\n' "$rank" "$ref" "$K"
  else
    MISSES="${MISSES}${ref}\n"
    [ "$QUIET" = 0 ] && [ "$JSON" = 0 ] && printf '  MISS          %s\n' "$ref"
  fi
done < <(jq -r '.pairs[] | [.expected_ref, .query] | @tsv' "$PAIRS")

if [ "$TOTAL" -eq 0 ]; then
  echo "retrieval-eval.sh: pairs file has zero usable pairs: $PAIRS" >&2; exit 2
fi

RECALL="$(awk -v h="$HITS" -v t="$TOTAL" 'BEGIN{printf "%.4f", h/t}')"
MRR="$(awk -v s="$RR_SUM" -v t="$TOTAL" 'BEGIN{printf "%.4f", s/t}')"
RECALL_PASS="$(awk -v r="$RECALL" -v f="$FLOOR" 'BEGIN{print (r+1e-9 >= f) ? 1 : 0}')"
MRR_PASS="$(awk -v m="$MRR" -v f="$MRR_FLOOR" 'BEGIN{print (m+1e-9 >= f) ? 1 : 0}')"
if [ "$RECALL_PASS" = 1 ] && [ "$MRR_PASS" = 1 ]; then PASS=1; else PASS=0; fi

if [ "$JSON" = 1 ]; then
  jq -nc --argjson recall "$RECALL" --argjson mrr "$MRR" --argjson k "$K" \
    --argjson floor "$FLOOR" --argjson mrr_floor "$MRR_FLOOR" \
    --argjson hits "$HITS" --argjson total "$TOTAL" \
    --argjson pass "$PASS" --arg arm "$ARM" \
    '{arm:$arm, recall_at_k:$recall, mrr:$mrr, k:$k, floor:$floor, mrr_floor:$mrr_floor, hits:$hits, total:$total, pass:($pass==1)}'
else
  echo ""
  echo "retrieval-eval [arm=${ARM}]: recall@${K} = ${RECALL} (${HITS}/${TOTAL})   MRR = ${MRR}   floors: recall >= ${FLOOR}, mrr >= ${MRR_FLOOR}"
  if [ "$PASS" = 1 ]; then
    echo "PASS — recall@${K} >= ${FLOOR} AND MRR >= ${MRR_FLOOR}"
  else
    [ "$RECALL_PASS" = 0 ] && echo "FAIL [arm=${ARM}] — recall@${K} ${RECALL} < floor ${FLOOR} (pool regression: eviction/weights?)"
    [ "$MRR_PASS" = 0 ] && echo "FAIL [arm=${ARM}] — MRR ${MRR} < mrr-floor ${MRR_FLOOR} (order regression: rerank/weights?)"
  fi
fi

[ "$PASS" = 1 ] && exit 0 || exit 1
