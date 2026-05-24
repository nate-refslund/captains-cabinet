#!/usr/bin/env bash
# test-spec-049.sh — Spec 049 regression harness.
#
# PARTIAL (Phase 7 scaffold): asserts the SHIPPED components — Phase-2a (migrate +
# ceiling) and the 4 Phase-3 Gate-4 leaves (model-pricing, cache-hash, page-allowlist,
# semaphore). The runner-core integration (Gate-4 build-atomic gate4BuildHash, MF-5
# permit placement, C1 cost accumulation), the C3 conventional-commit bypass corpus,
# the JF joint-failure determinism scenario, and the build-hash ship-pr binding land
# when those ship — extend the sections below (the spec's ≥22-assertion floor is for
# the FULL 23-AC harness; this subset already exceeds 22 for what's shipped).
#
# Hermetic: temp files for migrate/cache-hash/ceiling-file logic; redis TEST-PREFIX
# keys (DEL'd before + after) for ceiling-counter + semaphore. Never touches a real
# officer's active-task.json, toolcalls, or visual-uat permits.
#
# Usage: bash test-spec-049.sh   (exit 0 = all pass; nonzero = failures, listed)
set -u

CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"
LIB="$CABINET_ROOT/cabinet/scripts/lib"
SCRIPTS="$CABINET_ROOT/cabinet/scripts"
: "${REDIS_HOST:=redis}"; : "${REDIS_PORT:=6379}"
RC=$(command -v redis-cli >/dev/null 2>&1 && echo 1 || echo 0)
_redis() { redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@" 2>/dev/null; }

PASS=0; FAIL=0
pass() { PASS=$((PASS + 1)); }
fail() { FAIL=$((FAIL + 1)); echo "  ✗ FAIL: $1"; }
eq()  { if [ "$2" = "$3" ]; then pass; else fail "$1: got [$2] want [$3]"; fi; }
ne()  { if [ "$2" != "$3" ]; then pass; else fail "$1: [$2] should differ from [$3]"; fi; }
section() { echo; echo "── $1"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ───────────────────────────────────────────────────────────────────────────
section "AC #5 — migrate-active-task.sh (v2 schema migration)"
MIG="$SCRIPTS/migrate-active-task.sh"
printf '{"issueId":"SEN-1","branch":"feat/x","selfReviewPassed":false}\n' > "$TMP/at.json"
bash "$MIG" "$TMP/at.json" >/dev/null 2>&1
eq "schema_version=2"        "$(jq -r '.schema_version' "$TMP/at.json")"   "2"
eq "agentStepCap default"    "$(jq -r '.agentStepCap' "$TMP/at.json")"     "200"
eq "agentTokenCap default"   "$(jq -r '.agentTokenCap' "$TMP/at.json")"    "10000000"
eq "agentSteps init 0"       "$(jq -r '.agentSteps' "$TMP/at.json")"       "0"
eq "baseline null til pickup" "$(jq -r '.agentStepBaseline' "$TMP/at.json")" "null"
eq "preserves issueId"       "$(jq -r '.issueId' "$TMP/at.json")"          "SEN-1"
eq "preserves selfReviewPassed" "$(jq -r '.selfReviewPassed' "$TMP/at.json")" "false"
bash "$MIG" --validate "$TMP/at.json" >/dev/null 2>&1; eq "--validate v2 rc" "$?" "0"
bash "$MIG" "$TMP/at.json" >/dev/null 2>&1
eq "idempotent (caps unchanged)" "$(jq -r '.agentStepCap' "$TMP/at.json")" "200"
printf '{"issueId":"SEN-2"}\n' > "$TMP/partial.json"
bash "$MIG" --validate "$TMP/partial.json" >/dev/null 2>&1; eq "--validate partial rc=3" "$?" "3"

# ───────────────────────────────────────────────────────────────────────────
section "AC #8 — spec049-ceiling.sh check_caps (cap-event-chain, file-pure)"
# shellcheck source=/dev/null
. "$LIB/spec049-ceiling.sh"
mk() { # mk <file> <steps> <stepcap> <tokens> <tokcap> [cost] [costcap]
  jq -n --argjson s "$2" --argjson sc "$3" --argjson t "$4" --argjson tc "$5" \
        --argjson c "${6:-0}" --argjson cc "${7:-0}" \
    '{agentSteps:$s,agentStepCap:$sc,agentTokensTotal:$t,agentTokenCap:$tc,visualUatCost:$c}
     + (if $cc>0 then {visualUatCostCap:$cc} else {} end)' > "$1"
}
mk "$TMP/clear.json"    10  200 100 10000000;           spec049_check_caps "$TMP/clear.json"    >/dev/null 2>&1; eq "clear rc0"          "$?" "0"
mk "$TMP/approach.json" 160 200 100 10000000;           spec049_check_caps "$TMP/approach.json" >/dev/null 2>&1; eq "approach(80%) rc0"  "$?" "0"
mk "$TMP/hitstep.json"  200 200 100 10000000;           spec049_check_caps "$TMP/hitstep.json"  >/dev/null 2>&1; eq "hit step rc2"       "$?" "2"
mk "$TMP/hittok.json"   10  200 10000000 10000000;      spec049_check_caps "$TMP/hittok.json"   >/dev/null 2>&1; eq "hit token rc2"      "$?" "2"
mk "$TMP/costdorm.json" 10  200 100 10000000 999 0;     spec049_check_caps "$TMP/costdorm.json" >/dev/null 2>&1; eq "cost arm dormant(no cap) rc0" "$?" "0"
mk "$TMP/costhit.json"  10  200 100 10000000 5 5;       spec049_check_caps "$TMP/costhit.json"  >/dev/null 2>&1; eq "cost arm hit rc2"   "$?" "2"
spec049_check_caps "$TMP/nonexistent.json" >/dev/null 2>&1; eq "fail-safe no-file rc0" "$?" "0"

# ───────────────────────────────────────────────────────────────────────────
section "AC #8 — ceiling update_counters + snapshot_baseline (redis-backed)"
if [ "$RC" = "1" ] && _redis PING >/dev/null 2>&1; then
  OFC="testofc049"; DAY="$(date -u +%Y-%m-%d)"
  _redis DEL "cabinet:toolcalls:$OFC" >/dev/null
  _redis HDEL "cabinet:cost:tokens:daily:$DAY" "${OFC}_input" "${OFC}_output" >/dev/null
  # snapshot: baselines null → captured from current cumulative
  _redis SET "cabinet:toolcalls:$OFC" 300 >/dev/null
  _redis HSET "cabinet:cost:tokens:daily:$DAY" "${OFC}_input" 2000 "${OFC}_output" 1000 >/dev/null
  jq -n '{agentStepBaseline:null,agentTokenBaseline:null}' > "$TMP/snap.json"
  spec049_snapshot_baseline "$TMP/snap.json" "$OFC" >/dev/null 2>&1
  eq "snapshot step baseline=300"  "$(jq -r '.agentStepBaseline' "$TMP/snap.json")"  "300"
  eq "snapshot token baseline=3000" "$(jq -r '.agentTokenBaseline' "$TMP/snap.json")" "3000"
  # idempotent: re-run won't re-anchor even after counters move
  _redis SET "cabinet:toolcalls:$OFC" 999 >/dev/null
  spec049_snapshot_baseline "$TMP/snap.json" "$OFC" >/dev/null 2>&1
  eq "snapshot idempotent"          "$(jq -r '.agentStepBaseline' "$TMP/snap.json")"  "300"
  # update_counters: delta from baseline
  jq -n '{agentStepBaseline:100,agentTokenBaseline:200,agentSteps:0,agentTokensTotal:0}' > "$TMP/upd.json"
  _redis SET "cabinet:toolcalls:$OFC" 150 >/dev/null
  _redis HSET "cabinet:cost:tokens:daily:$DAY" "${OFC}_input" 1000 "${OFC}_output" 500 >/dev/null
  spec049_update_counters "$TMP/upd.json" "$OFC" >/dev/null 2>&1
  eq "update agentSteps=50 (150-100)"        "$(jq -r '.agentSteps' "$TMP/upd.json")"       "50"
  eq "update agentTokensTotal=1300 (1500-200)" "$(jq -r '.agentTokensTotal' "$TMP/upd.json")" "1300"
  _redis DEL "cabinet:toolcalls:$OFC" >/dev/null
  _redis HDEL "cabinet:cost:tokens:daily:$DAY" "${OFC}_input" "${OFC}_output" >/dev/null
else
  echo "  ⚠ SKIP (redis unavailable)"
fi

# ───────────────────────────────────────────────────────────────────────────
section "AC #18 — model-pricing.sh"
# shellcheck source=/dev/null
. "$LIB/model-pricing.sh"
eq "opus-4-7 input rate"   "$(model_pricing_rate claude-opus-4-7 input)"          "15.0"
eq "sonnet-4-6 output rate" "$(model_pricing_rate claude-sonnet-4-6 output)"       "15.0"
eq "cost 1000in/500out"    "$(model_pricing_cost claude-opus-4-7 1000 500)"        "0.0525"
eq "prefix-match dated id" "$(model_pricing_rate claude-opus-4-7-20260101 input)"  "15.0"
eq "cache-read 1000tok"    "$(model_pricing_cost claude-opus-4-7 0 0 0 1000)"      "0.0015"
model_pricing_staleness_check 2>/dev/null; eq "staleness fresh rc0" "$?" "0"
out=$(model_pricing_rate bogus-model input 2>/dev/null); rc=$?
eq "unknown model rc1" "$rc" "1"; eq "unknown model empty" "$out" ""

# ───────────────────────────────────────────────────────────────────────────
section "AC #14 — cache-hash.sh"
# shellcheck source=/dev/null
. "$LIB/cache-hash.sh"
CH="$TMP/proj"; mkdir -p "$CH/src" "$CH/.next" "$CH/.cabinet"
echo lockv1 > "$CH/pnpm-lock.yaml"; echo 'x' > "$CH/src/a.ts"; echo '{}' > "$CH/.next/build-manifest.json"
touch -d "2025-01-01" "$CH/pnpm-lock.yaml" "$CH/src/a.ts" "$CH/.next/build-manifest.json"
h1=$(cache_hash_compute nextjs "$CH" src .next)
eq "deterministic" "$h1" "$(cache_hash_compute nextjs "$CH" src .next)"
touch -d "2030-06-06" "$CH/.next/build-manifest.json"
eq "MF-2 build-manifest excluded" "$(cache_hash_compute nextjs "$CH" src .next)" "$h1"
touch -d "2030-06-06" "$CH/src/a.ts"; h2=$(cache_hash_compute nextjs "$CH" src .next)
ne "source-mtime invalidates" "$h2" "$h1"
ne "mode-namespacing (git-deps != nextjs)" "$(cache_hash_compute git-deps "$CH" src)" "$h2"
printf '#!/usr/bin/env bash\necho CUSTOMHASH\n' > "$CH/.cabinet/cache-hash.sh"
eq "custom mode" "$(cache_hash_compute custom "$CH")" "CUSTOMHASH"
cache_hash_compute bogus "$CH" src >/dev/null 2>&1; eq "unknown mode rc2" "$?" "2"

# ───────────────────────────────────────────────────────────────────────────
section "AC #15 — page-allowlist.sh (M3 origin-pinning)"
# shellcheck source=/dev/null
. "$LIB/page-allowlist.sh"
page_allowlist_is_safe "/dashboard" && eq "safe path" "0" "0" || eq "safe path" "1" "0"
for bad in "http://evil/x" "//evil" "/a/../b" "rel" "/x/%2e%2e/y" '/a\b'; do
  if page_allowlist_is_safe "$bad"; then fail "unsafe accepted: $bad"; else pass; fi
done
out=$(page_allowlist_filter "/,/dashboard,/tasks/*" "/" "/tasks/9" "/admin" 2>/dev/null); rc=$?
eq "filter keeps allowed" "$(echo "$out" | tr '\n' ' ')" "/ /tasks/9 "
eq "filter rc1 when any rejected" "$rc" "1"
out=$(page_allowlist_filter "/,/tasks/*" "/" "/tasks/9" 2>/dev/null); rc=$?
eq "filter rc0 all allowed" "$rc" "0"

# ───────────────────────────────────────────────────────────────────────────
section "AC #13 — visual-uat-semaphore.sh (M2 crash-safe lock)"
if [ "$RC" = "1" ] && _redis PING >/dev/null 2>&1; then
  export VUAT_SEM_PREFIX="cabinet:visual-uat:slottest049"
  _redis DEL "$VUAT_SEM_PREFIX:1" "$VUAT_SEM_PREFIX:2" "$VUAT_SEM_PREFIX:3" >/dev/null
  # shellcheck source=/dev/null
  . "$LIB/visual-uat-semaphore.sh"
  s1=$(vuat_sem_acquire 2 ownerA 60); eq "acquire A slot1" "${s1##*:}" "1"
  s2=$(vuat_sem_acquire 2 ownerB 60); eq "acquire B slot2" "${s2##*:}" "2"
  vuat_sem_acquire 2 ownerC 60 >/dev/null; eq "pool full rc1" "$?" "1"
  ttl=$(_redis TTL "$s1"); [ "$ttl" -gt 0 ] 2>/dev/null && pass || fail "TTL set (got $ttl)"
  vuat_sem_release "$s1" ownerA
  s3=$(vuat_sem_acquire 2 ownerC 60); eq "slot1 reused after release" "${s3##*:}" "1"
  vuat_sem_release "$s2" WRONGOWNER          # anti-steal: must be a no-op
  vuat_sem_acquire 2 ownerD 60 >/dev/null; eq "anti-steal (B's slot not freed) rc1" "$?" "1"
  vuat_sem_renew "$s2" ownerB 90;     eq "renew owner-correct rc0" "$?" "0"
  vuat_sem_renew "$s2" WRONGOWNER 90; eq "renew wrong-owner rc1"   "$?" "1"
  _redis DEL "$VUAT_SEM_PREFIX:1" "$VUAT_SEM_PREFIX:2" "$VUAT_SEM_PREFIX:3" >/dev/null
else
  echo "  ⚠ SKIP (redis unavailable)"
fi

# ───────────────────────────────────────────────────────────────────────────
echo
echo "════════════════════════════════════════════"
echo "Spec 049 harness (PARTIAL — shipped components): PASS=$PASS FAIL=$FAIL"
echo "════════════════════════════════════════════"
[ "$FAIL" -eq 0 ]
