#!/bin/bash
# retrieval-eval-nightly.sh — the standing retrieval REFINEMENT GATE
# (Lane D, 2026-07-15; closes the R1 landing's "eval gates nothing" gap and
# its named residual "rerank rescues pool damage").
#
# Runs the retrieval eval (cabinet/scripts/retrieval-eval.sh) in BOTH arms
# every night against the COMMITTED QUESTION SEED (2026-07-29 — it used to
# self-harvest its pairs, and that harvester derived each query from the
# expected document's own leading 110 characters, so the nightly gate was
# asking the corpus to find itself and scored 1.0000 forever; the harvester
# is deleted, the seed is question-shaped and ships with the repo) and
# appends ONE verdict JSONL line to the runtime ledger:
#   arm "rerank"     the production path (blended pool + Voyage rerank)
#   arm "no-rerank"  CABINET_MEMORY_RERANK=off — the same floors over the
#                    BLENDED order, so weight/pool damage cannot hide behind
#                    a healthy reranker. A blended-arm breach is a REAL
#                    finding even when the rerank arm passes.
#
# STORE-LOCAL BY DESIGN: the eval queries the LIVE cabinet_memory store, so
# it can only run where NEON_CONNECTION_STRING resolves (env or cabinet/.env
# — memory.sh back-fills; values are used by psql/curl, NEVER printed). A
# credless box (clean-room/CI) logs a skip line and exits 0 — GitHub CI gates
# the ranking-change FINGERPRINT instead (see --stamp below +
# cabinet/scripts/tests/test_retrieval_eval_gate.py).
#
# VERDICT LEDGER (runtime, untracked — .gitignore `cabinet/logs/*`):
#   cabinet/logs/retrieval-eval-history.jsonl — one line per run:
#   {"ts","status":"ok|no-pairs|error","pass":true|false|null,
#    "pairs_source","floors":{...},"arms":{"rerank":{...},"blended":{...}}}
#   status=ok      both arms produced verdicts; .pass = both arms passed
#   status=no-pairs harvest found no usable rows (young store) — pass=null
#   status=error   an arm failed to produce a verdict (setup error) — pass=false
#   Composed exclusively via jq -n --arg/--argjson (eval content is untrusted
#   data and never travels through shell program text). Self-prunes like
#   doctor-history (>200 lines → tail 120).
#
# CONSUMERS: cabinet-doctor.sh (retrieval-eval check) reads the latest line
# via `--probe` — AMBER/WARN on a floor breach or a >48h-stale verdict,
# SKIP on a credless box; the services watchdog registry covers the row's
# log freshness (daily calendar → 26h floor).
#
# Usage:
#   retrieval-eval-nightly.sh                    nightly run (committed question seed)
#   retrieval-eval-nightly.sh --pairs FILE       use a different pairs file (replays/tests)
#   retrieval-eval-nightly.sh --stamp            after a BOTH-ARM PASS, refresh the
#       ranking fingerprint cabinet/scripts/tests/fixtures/memory-ranking.fingerprint
#       (sha256 over the RANKING-BLOCK marker regions of lib/memory.sh). This is
#       THE sanctioned regeneration path: CI pins the fingerprint to the live
#       ranking code, so any ranking edit is a red build until a store-local
#       run that HOLDS the floors re-stamps it. Never stamps on a breach.
#   retrieval-eval-nightly.sh --probe            NO DB / NO network: inspect the
#       latest verdict line for the doctor. Prints exactly one token line:
#         NOCREDS            no NEON_CONNECTION_STRING resolvable (name-checked
#                            in env / cabinet/.env — value never read out)
#         NOFILE             creds resolvable but no ledger yet
#         BADLINE            latest line is not parseable verdict JSON
#         STALE age=<s> ...  latest verdict older than 48h (gate not running)
#         BREACH ...         latest verdict is a floor breach (pass=false)
#         NOTOK status=<s>   latest verdict could not measure (no-pairs/error;
#                            no-pairs now means THIS STORE HOLDS NONE of the
#                            seed's expected documents — a store that has not
#                            ingested its own docs cannot be measured by it)
#         OK age=<s> ...     latest verdict fresh + passing
# Floors (env-overridable): RE_FLOOR=0.60 RE_MRR_FLOOR=0.50 (rerank arm — the
#   proven live-test floors), RE_BLENDED_MRR_FLOOR=0.50 (no-rerank arm;
#   calibrated live 2026-07-15 on self-harvested pairs: rerank r@10=1.00
#   MRR=0.958, blended r@10=0.833 MRR=0.736 vs ~0.10 for an order-inverted
#   mutant — 0.50 has margin both ways),
#   RE_LIMIT=20 (> k=10 keeps the k-cut order-sensitive),
#   RE_ABSTAIN_FLOOR=1.00 (every unanswerable seed question must return
#   nothing — the arm that stops a floor deletion from scoring a perfect
#   recall; see retrieval-eval.sh).
# Exit: 0 pass / skip (credless, no-pairs); 1 floor breach or arm error;
#       2 usage error.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export CABINET_ROOT

# Estate paths ride CABINET_ROOT (the deployment being measured — tests point
# it at a fixture tree with a stub lib); sibling SCRIPTS ride SCRIPT_DIR (they
# live next to this wrapper by construction and are the code under test).
HIST="$CABINET_ROOT/cabinet/logs/retrieval-eval-history.jsonl"
MEMLIB="$CABINET_ROOT/cabinet/scripts/lib/memory.sh"
FPRINT="$CABINET_ROOT/cabinet/scripts/tests/fixtures/memory-ranking.fingerprint"
RUNNER="$SCRIPT_DIR/retrieval-eval.sh"
SEED="$CABINET_ROOT/cabinet/scripts/tests/fixtures/retrieval-questions.seed.json"
STALE_S=172800   # 48h — one missed night is grace, two is a dead gate

RE_FLOOR="${RE_FLOOR:-0.60}"
RE_MRR_FLOOR="${RE_MRR_FLOOR:-0.50}"
RE_BLENDED_MRR_FLOOR="${RE_BLENDED_MRR_FLOOR:-0.50}"
RE_LIMIT="${RE_LIMIT:-20}"
RE_ABSTAIN_FLOOR="${RE_ABSTAIN_FLOOR:-1.00}"
# Floors must be plain non-negative decimals — they travel into jq --argjson
# (JSON numbers) and awk comparisons in the runner; junk fails loudly here,
# never as a malformed verdict line.
for _f in "$RE_FLOOR" "$RE_MRR_FLOOR" "$RE_BLENDED_MRR_FLOOR" "$RE_ABSTAIN_FLOOR"; do
  if ! printf '%s' "$_f" | grep -qE '^[0-9]*\.?[0-9]+$'; then
    echo "retrieval-eval-nightly.sh: floor env not a plain decimal: $_f" >&2; exit 2
  fi
done

MODE="run"
PAIRS=""
STAMP=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pairs) PAIRS="$2"; shift 2 ;;
    --stamp) STAMP=1; shift ;;
    --probe) MODE="probe"; shift ;;
    -h|--help) grep -E '^# ' "$0" | sed 's/^# //'; exit 0 ;;
    *) echo "retrieval-eval-nightly.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

_now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# sha256 of the RANKING-BLOCK marker regions of lib/memory.sh — awk range
# extraction (inclusive of both marker lines), byte-identical to the Python
# twin in cabinet/scripts/tests/test_retrieval_eval_gate.py (parity-pinned
# there). macOS ships shasum (perl), Linux CI ships sha256sum — try both.
_ranking_sha() {
  awk '/RANKING-BLOCK-BEGIN/,/RANKING-BLOCK-END/' "$MEMLIB" | {
    if command -v sha256sum >/dev/null 2>&1; then sha256sum; else shasum -a 256; fi
  } | awk '{print $1}'
}

# ---------------------------------------------------------------------------
# --probe: pure file+env inspection for cabinet-doctor. No DB, no network, no
# secret VALUES (creds resolvability = env non-empty OR the NAME appears in
# cabinet/.env; grep -q never emits the line).
# ---------------------------------------------------------------------------
if [ "$MODE" = "probe" ]; then
  if [ -z "${NEON_CONNECTION_STRING:-}" ] \
     && ! grep -qE '^NEON_CONNECTION_STRING=' "$CABINET_ROOT/cabinet/.env" 2>/dev/null; then
    echo "NOCREDS"; exit 0
  fi
  if [ ! -f "$HIST" ]; then echo "NOFILE"; exit 0; fi
  last_line="$(tail -n 1 "$HIST" 2>/dev/null)"
  ts="$(printf '%s' "$last_line" | jq -r '.ts // empty' 2>/dev/null)"
  if [ -z "$ts" ]; then echo "BADLINE"; exit 0; fi
  # ISO ts → epoch: BSD date (macOS) first, GNU date (CI) fallback.
  ts_epoch="$(date -j -u -f '%Y-%m-%dT%H:%M:%SZ' "$ts" +%s 2>/dev/null \
              || date -u -d "$ts" +%s 2>/dev/null)"
  case "$ts_epoch" in ''|*[!0-9]*) echo "BADLINE"; exit 0 ;; esac
  age=$(( $(date -u +%s) - ts_epoch ))
  [ "$age" -lt 0 ] && age=0
  if [ "$age" -gt "$STALE_S" ]; then
    echo "STALE age=${age}s ts=$ts (floor ${STALE_S}s)"; exit 0
  fi
  pass="$(printf '%s' "$last_line" | jq -r '.pass' 2>/dev/null)"
  status="$(printf '%s' "$last_line" | jq -r '.status // "?"' 2>/dev/null)"
  detail="$(printf '%s' "$last_line" | jq -r \
    '"rerank r@k=\(.arms.rerank.recall_at_k // "?") mrr=\(.arms.rerank.mrr // "?"); blended r@k=\(.arms.blended.recall_at_k // "?") mrr=\(.arms.blended.mrr // "?")"' \
    2>/dev/null)"
  case "$pass" in
    true)  echo "OK age=${age}s ${detail}" ;;
    false) echo "BREACH age=${age}s status=${status} ${detail}" ;;
    *)     echo "NOTOK status=${status} age=${age}s" ;;
  esac
  exit 0
fi

# ---------------------------------------------------------------------------
# nightly run — both arms against the live store
# ---------------------------------------------------------------------------
# shellcheck source=/dev/null
source "$MEMLIB"   # back-fills NEON_CONNECTION_STRING / CABINET_ID from cabinet/.env

if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
  echo "retrieval-eval-nightly: no NEON_CONNECTION_STRING resolvable — the gate is store-local; nothing to measure on this box (clean-room/CI). Skipping clean."
  exit 0
fi

mkdir -p "$(dirname "$HIST")"

_append_line() {  # $1 = one compact JSON line (already jq-composed)
  printf '%s\n' "$1" >> "$HIST"
  # Self-prune (doctor-history pattern): one line/night, keep years bounded.
  if [ "$(wc -l < "$HIST" 2>/dev/null || echo 0)" -gt 200 ]; then
    tail -n 120 "$HIST" > "$HIST.tmp" && mv "$HIST.tmp" "$HIST"
  fi
}

PAIRS_SOURCE="file"

if [ -z "$PAIRS" ]; then
  PAIRS_SOURCE="seed"
  PAIRS="$SEED"
  [ -f "$PAIRS" ] || {
    echo "retrieval-eval-nightly: seed not found: $PAIRS" >&2; exit 2; }
  # PRESENCE PRECHECK. The seed's expected documents are ones this repo ships,
  # but a store that has not ingested its docs yet holds none of them — and
  # measuring recall for documents that are ABSENT would red the gate for a
  # young store rather than report that it cannot be measured. Pure SQL COUNT,
  # no embedding, no paid call. A store holding SOME of them is measurable and
  # proceeds (the eval scores what it finds); only zero is unmeasurable.
  _present="$(psql "$NEON_CONNECTION_STRING" -q -t -A \
      -v refs="$(jq -r '[.pairs[].expected_ref] | join("|")' "$PAIRS")" \
      2>/dev/null <<'SQLEOF' | tr -cd '0-9'
SELECT count(*) FROM cabinet_memory
WHERE superseded_by IS NULL
  AND source_id = ANY(string_to_array(:'refs', '|'));
SQLEOF
)"
  if [ -z "$_present" ] || [ "$_present" -eq 0 ] 2>/dev/null; then
    line="$(jq -nc --arg ts "$(_now_iso)" \
      '{ts:$ts, status:"no-pairs", pass:null,
        note:"this store holds NONE of the seed expected documents (docs not ingested yet?) — gate unmeasurable tonight"}')"
    _append_line "$line"
    echo "retrieval-eval-nightly: NO-PAIRS — store holds none of the seed's expected documents; verdict line appended, exiting 0"
    exit 0
  fi
fi

# Arm 1 — production path (rerank live). --quiet --json → stdout is exactly
# one JSON verdict line (per-pair HIT/MISS prints are JSON-gated off).
rerank_json="$(bash "$RUNNER" --pairs "$PAIRS" --floor "$RE_FLOOR" \
  --mrr-floor "$RE_MRR_FLOOR" --abstain-floor "$RE_ABSTAIN_FLOOR" \
  --limit "$RE_LIMIT" --json --quiet)"
rerank_rc=$?
# Arm 2 — blended order (rerank seam off).
blended_json="$(bash "$RUNNER" --no-rerank --pairs "$PAIRS" --floor "$RE_FLOOR" \
  --mrr-floor "$RE_BLENDED_MRR_FLOOR" --abstain-floor "$RE_ABSTAIN_FLOOR" \
  --limit "$RE_LIMIT" --json --quiet)"
blended_rc=$?

if ! printf '%s' "$rerank_json" | jq -e . >/dev/null 2>&1 \
   || ! printf '%s' "$blended_json" | jq -e . >/dev/null 2>&1; then
  line="$(jq -nc --arg ts "$(_now_iso)" \
    --argjson rrc "$rerank_rc" --argjson brc "$blended_rc" \
    '{ts:$ts, status:"error", pass:false, rerank_rc:$rrc, blended_rc:$brc,
      note:"an arm produced no JSON verdict (setup error — see service log stderr)"}')"
  _append_line "$line"
  echo "retrieval-eval-nightly: ERROR — arm rc rerank=$rerank_rc blended=$blended_rc produced no verdict JSON" >&2
  exit 1
fi

if [ "$rerank_rc" -eq 0 ] && [ "$blended_rc" -eq 0 ]; then PASS=true; else PASS=false; fi

line="$(jq -nc --arg ts "$(_now_iso)" --arg pairs_source "$PAIRS_SOURCE" \
  --argjson pass "$PASS" \
  --argjson floors "$(jq -nc --argjson r "$RE_FLOOR" --argjson m "$RE_MRR_FLOOR" \
      --argjson b "$RE_BLENDED_MRR_FLOOR" \
      '{recall:$r, mrr_rerank:$m, mrr_blended:$b}')" \
  --argjson rerank "$rerank_json" --argjson blended "$blended_json" \
  '{ts:$ts, status:"ok", pass:$pass, pairs_source:$pairs_source,
    floors:$floors, arms:{rerank:$rerank, blended:$blended}}')"
_append_line "$line"

echo "retrieval-eval-nightly: pass=$PASS  rerank(rc=$rerank_rc) $(printf '%s' "$rerank_json" | jq -r '"r@k=\(.recall_at_k) mrr=\(.mrr)"')  blended(rc=$blended_rc) $(printf '%s' "$blended_json" | jq -r '"r@k=\(.recall_at_k) mrr=\(.mrr)"')  -> $HIST"

if [ "$STAMP" = 1 ]; then
  if [ "$PASS" = "true" ]; then
    sha="$(_ranking_sha)"
    {
      echo "# memory-ranking.fingerprint — sha256 over the RANKING-BLOCK marker regions"
      echo "# of cabinet/scripts/lib/memory.sh (blended weights + vec floor + pool order"
      echo "# + rerank stage + the no-rerank seam). CI pins this to the live ranking code"
      echo "# (cabinet/scripts/tests/test_retrieval_eval_gate.py): any ranking edit is a"
      echo "# red build until a store-local eval run that HOLDS both arms' floors"
      echo "# re-stamps it:  bash cabinet/scripts/retrieval-eval-nightly.sh --stamp"
      echo "# (stamps ONLY on a both-arm PASS; commit the refreshed file WITH the ranking"
      echo "# change). Hand-editing the hex defeats the gate's purpose — don't."
      echo "$sha"
    } > "$FPRINT"
    echo "retrieval-eval-nightly: STAMPED ranking fingerprint $sha -> $FPRINT"
  else
    echo "retrieval-eval-nightly: --stamp REFUSED — floors not held (pass=$PASS); fix the regression first" >&2
  fi
fi

if [ "$PASS" = "true" ]; then exit 0; else
  echo "retrieval-eval-nightly: FLOOR BREACH — see $HIST (doctor will AMBER until a passing run)" >&2
  exit 1
fi
