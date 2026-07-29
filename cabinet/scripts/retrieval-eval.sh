#!/bin/bash
# retrieval-eval.sh — recall@k + MRR gate for memory_search ranking (R1,
# 2026-07-12 — org-memory study §5-R1).
#
# Runs each {query -> expected_ref} pair through memory_search and measures
# whether (recall@k) and where (MRR) the expected row is retrieved. This is the
# regression GATE the org spine never had: the blended weights (0.60/0.25/0.15),
# the vec floor, and the rerank stage all shipped unmeasured. TWO floors,
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
# retrieval-questions.seed.json). Every query in it is a QUESTION A PERSON
# WOULD ACTUALLY ASK and every expected_ref is a document this repository
# ships, so it is portable to any cabinet that has ingested its own docs and
# reveals nothing about any operator's private material.
#
# WHY THE SEED WAS REPLACED (2026-07-29). The previous seed's queries were
# each document's own leading 110 characters — the corpus asked to find
# itself. It reported recall@10 = 1.0000 and MRR = 1.0000 while plainly
# worded questions against the same store were returning "No results found."
# for 7 of 16. An eval that cannot fail is not a sensor, and this one was
# also the gate standing between the ranking and a fix.
#
# THE ABSTAIN ARM (added with that seed, and load-bearing). The pairs file
# may carry `unanswerable: [...]` — questions in domains the corpus holds
# nothing on. Each must return ZERO rows. Without it the whole eval is
# satisfiable by DELETING the similarity floor, which scores a perfect
# recall@k and answers every question with the nearest unrelated document.
# A pairs file with no `unanswerable` key skips the arm and says so
# (abstain_rate: null) rather than reporting a pass it never measured.
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
#                     [--abstain-floor A] [--limit L] [--min-score S]
#                     [--no-rerank] [--json] [--quiet]
# Defaults: --pairs seed, --k from the pairs file (.recall_k, else 10),
#           --floor 0.70, --mrr-floor 0.50 (an order-inverted ranker scores
#           ~0.10, so 0.50 has margin both ways), --abstain-floor 1.00 (every
#           unanswerable question must return nothing — a single fabricated
#           answer is the failure this arm exists to catch),
#           --limit = k, --min-score = memory_search default.
# Exit: 0 if recall@k >= floor AND MRR >= mrr-floor AND abstain >= its floor;
#       1 if any gate fails; 2 on usage/setup error.
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

PAIRS="$CABINET_ROOT/cabinet/scripts/tests/fixtures/retrieval-questions.seed.json"
K=""
FLOOR="0.70"
MRR_FLOOR="0.50"
ABSTAIN_FLOOR="1.00"
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
    --abstain-floor) ABSTAIN_FLOOR="$2"; shift 2 ;;
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

# --- ABSTAIN ARM ------------------------------------------------------------
# Questions the corpus holds nothing on MUST return zero rows. This is the arm
# that stops "make retrieval find things" from being satisfied by removing the
# similarity floor: with no floor, recall@k goes to 1.0000 and every one of
# these fabricates an answer out of the nearest unrelated document.
# A pairs file with no `unanswerable` key SKIPS the arm and reports
# abstain_rate: null — a skipped sensor is reported as skipped, never as a pass.
AB_TOTAL=0; AB_OK=0; AB_LEAKS=""
while IFS= read -r q; do
  [ -z "$q" ] && continue
  AB_TOTAL=$((AB_TOTAL+1))
  rows="$(memory_search "$q" "" "" "$LIMIT" "$MIN_SCORE" 2>/dev/null \
          | grep -c '[^[:space:]]')"
  case "$rows" in ''|*[!0-9]*) rows=0 ;; esac
  if [ "$rows" -eq 0 ]; then
    AB_OK=$((AB_OK+1))
    [ "$QUIET" = 0 ] && [ "$JSON" = 0 ] && printf '  ABSTAIN       %s\n' "$q"
  else
    AB_LEAKS="${AB_LEAKS}${q}\n"
    [ "$QUIET" = 0 ] && [ "$JSON" = 0 ] && printf '  ANSWERED  %-3s %s  <-- should have returned nothing\n' "$rows" "$q"
  fi
done < <(jq -r '(.unanswerable // [])[]' "$PAIRS")

if [ "$AB_TOTAL" -eq 0 ]; then
  ABSTAIN="null"; ABSTAIN_PASS=1
else
  ABSTAIN="$(awk -v h="$AB_OK" -v t="$AB_TOTAL" 'BEGIN{printf "%.4f", h/t}')"
  ABSTAIN_PASS="$(awk -v a="$ABSTAIN" -v f="$ABSTAIN_FLOOR" 'BEGIN{print (a+1e-9 >= f) ? 1 : 0}')"
fi

if [ "$RECALL_PASS" = 1 ] && [ "$MRR_PASS" = 1 ] && [ "$ABSTAIN_PASS" = 1 ]; then
  PASS=1
else
  PASS=0
fi

if [ "$JSON" = 1 ]; then
  jq -nc --argjson recall "$RECALL" --argjson mrr "$MRR" --argjson k "$K" \
    --argjson floor "$FLOOR" --argjson mrr_floor "$MRR_FLOOR" \
    --argjson hits "$HITS" --argjson total "$TOTAL" \
    --argjson abstain "$ABSTAIN" --argjson abstain_ok "$AB_OK" \
    --argjson abstain_total "$AB_TOTAL" --argjson abstain_floor "$ABSTAIN_FLOOR" \
    --argjson pass "$PASS" --arg arm "$ARM" \
    '{arm:$arm, recall_at_k:$recall, mrr:$mrr, k:$k, floor:$floor, mrr_floor:$mrr_floor, hits:$hits, total:$total, abstain_rate:$abstain, abstain_ok:$abstain_ok, abstain_total:$abstain_total, abstain_floor:$abstain_floor, pass:($pass==1)}'
else
  echo ""
  echo "retrieval-eval [arm=${ARM}]: recall@${K} = ${RECALL} (${HITS}/${TOTAL})   MRR = ${MRR}   abstain = ${ABSTAIN} (${AB_OK}/${AB_TOTAL})   floors: recall >= ${FLOOR}, mrr >= ${MRR_FLOOR}, abstain >= ${ABSTAIN_FLOOR}"
  if [ "$PASS" = 1 ]; then
    echo "PASS — recall@${K} >= ${FLOOR} AND MRR >= ${MRR_FLOOR} AND abstain >= ${ABSTAIN_FLOOR}"
    [ "$AB_TOTAL" -eq 0 ] && echo "NOTE — abstain arm SKIPPED: this pairs file carries no 'unanswerable' list, so nothing proves the floor still refuses an off-corpus question."
  else
    [ "$RECALL_PASS" = 0 ] && echo "FAIL [arm=${ARM}] — recall@${K} ${RECALL} < floor ${FLOOR} (pool regression: eviction/weights/floor too high?)"
    [ "$MRR_PASS" = 0 ] && echo "FAIL [arm=${ARM}] — MRR ${MRR} < mrr-floor ${MRR_FLOOR} (order regression: rerank/weights?)"
    [ "$ABSTAIN_PASS" = 0 ] && printf 'FAIL [arm=%s] — abstain %s < floor %s: the store answered a question it holds nothing on (floor too low / removed?):\n%b' "$ARM" "$ABSTAIN" "$ABSTAIN_FLOOR" "$AB_LEAKS"
  fi
fi

[ "$PASS" = 1 ] && exit 0 || exit 1
