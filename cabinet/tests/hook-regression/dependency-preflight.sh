#!/bin/bash
# dependency-preflight harness — the enforcement plane must FAIL CLOSED when a
# tool it depends on is missing or broken, and when the payload is unparseable.
#
# WHAT THIS CATCHES, and why it did not exist before:
#   pre-tool-use.sh parses `cat | jq` into TOOL_NAME, and EVERY gate dispatches
#   on TOOL_NAME. With jq absent both TOOL_NAME and TOOL_INPUT are empty, no
#   case/if arm matches, and the script falls through to its closing `exit 0`
#   = ALLOW. Reproduced against the real hook: `vercel deploy --prod` returned
#   exit 0 with ZERO bytes on stderr. Even the typed policy engine cannot save
#   it — §0 runs policy-shadow.py (which parses JSON in Python and correctly
#   returns "block"), then reads that verdict back with `jq -r '.decision'`,
#   so the verdict is discarded and the hook falls through. The kill switch
#   survived only because it uses redis-cli and a string compare, not jq.
#
#   Nobody caught it because CI installs jq explicitly — so every existing gate
#   test ran in the one environment where this cannot happen, while the real
#   target is a Mac where these are Homebrew packages and launchd hands daemons
#   a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin). That exact PATH gap already
#   bit this repo once for redis-cli, and check-deps.sh has been logging
#   MISSING at every officer boot — non-blocking, so nothing acted on it.
#   THIS HARNESS EXISTS SO CI IS NO LONGER THAT ENVIRONMENT.
#
# THE PROPERTY ASSERTED is the one the control exists to deliver — "is the
# dangerous thing actually stopped?" — never an internal invariant.
#
# EACH PROBE IS MATCHED TO THE CLASS IT ACTUALLY DETECTS. This matters: the
# obvious probe is misleading. `vercel deploy --prod` is caught by a pure-bash
# `case` in §3a, so it still blocks with grep/sed/tr/awk missing and would have
# passed those arms for an unrelated reason. Verified against pre-change code,
# the honest detectors are:
#
#   jq / cat / payload  -> 'vercel deploy --prod'
#                          (TOOL_NAME empties, §3 is never entered)
#   grep / sed / tr     -> Bash write to a germline file
#                          (pre-change: EXIT 0 — a write to the Captain's veto
#                          file was ALLOWED with any one of them missing)
#   awk / date          -> over-cap spend ledger
#                          (pre-change: EXIT 0 — $999,000 of realized spend
#                          sails past a $225 cap)
#   corrupt foreign row -> REGRESSION GUARD, not a defect detector. It passes
#                          against pre-change code too (which coerced the value
#                          to 0 and allowed). It exists so a future change
#                          cannot turn the shared-data path into a cabinet-wide
#                          self-DoS. Do not count it as evidence of a fix.
#   cut/head/mktemp/dirname/perl/python3
#                       -> no demonstrated bypass at this operating point;
#                          their documented fail-opens are in §8 capacity, §10
#                          peer consent, CABINET_ROOT resolution and the §3
#                          bare-command detector, which need enforcement to be
#                          OFF or a peer/context config present to reach.
#                          Carried as defence-in-depth and labelled as such —
#                          the arms assert the preflight refuses, not that a
#                          bypass was demonstrated. Do not read them as
#                          stronger evidence than they are.
#
# Absence is simulated faithfully: a mirror directory of symlinks to every
# binary on the CURRENT PATH except the one under test, so the tool is
# genuinely not found while the other ~1600 binaries stay real. Derived from
# the live PATH, so it works on macOS and in CI containers alike.
#
# redis-cli is deliberately NOT in the hook's required set — its absence
# already fails CLOSED via the §1 kill-switch gate, and EVAL-001c pins reads
# staying open. That ratified posture is asserted here too, so this harness
# fails if a future "harden everything" change converts it into a blanket
# block.
#
# CABINET_HOOK_TEST_MODE=1 is set inline per probe (no global export) per
# feedback_test_harness_production_sinks.md. The redis-cli fixtures keep every
# probe hermetic — no live Redis is contacted, no production key is written.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
HOOK="$REPO_ROOT/cabinet/scripts/hooks/pre-tool-use.sh"
POST_HOOK="$REPO_ROOT/cabinet/scripts/hooks/post-tool-use.sh"
TEST_BIN="$SCRIPT_DIR/fixtures"
CORRUPT_BIN="$SCRIPT_DIR/fixtures-ledger-corrupt"
OVERCAP_BIN="$SCRIPT_DIR/fixtures-ledger-overcap"
BASH_BIN="$(command -v bash)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dep-preflight.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

PASS=0; FAIL=0

DANGER='{"tool_name":"Bash","tool_input":{"command":"vercel deploy --prod"}}'
BENIGN='{"tool_name":"Bash","tool_input":{"command":"echo hello"}}'
GERMLINE='{"tool_name":"Bash","tool_input":{"command":"echo forged > shared/interfaces/captain-vetoes.yml"}}'

# Build a PATH in which exactly one binary is absent, everything else real.
mirror_without() {
  local omit="$1"
  local dir="$WORK/without-$omit"
  if [ -d "$dir" ]; then printf '%s' "$dir"; return 0; fi
  mkdir -p "$dir"
  local d f b
  local -a path_dirs
  IFS=':' read -r -a path_dirs <<< "$PATH"
  for d in "${path_dirs[@]}"; do
    [ -n "$d" ] && [ -d "$d" ] || continue
    for f in "$d"/*; do
      [ -e "$f" ] || continue
      b="${f##*/}"
      [ "$b" = "$omit" ] && continue
      [ -e "$dir/$b" ] && continue
      ln -s "$f" "$dir/$b" 2>/dev/null || true
    done
  done
  printf '%s' "$dir"
}

# probe <label> <expected BLOCK|ALLOW> <payload> <PATH to use>
probe() {
  local label="$1" expected="$2" payload="$3" use_path="$4"
  local out ec verdict
  out=$(printf '%s' "$payload" | env -i \
        PATH="$use_path" HOME="${HOME:-/tmp}" \
        CABINET_ROOT="$REPO_ROOT" CABINET_HOOK_TEST_MODE=1 \
        OFFICER_NAME=cos OFFICER=cos PYTHONDONTWRITEBYTECODE=1 \
        "$BASH_BIN" "$HOOK" 2>&1 >/dev/null)
  ec=$?
  if [ "$expected" = "BLOCK" ]; then
    # A block must be exit 2 AND say why — a silent refusal is its own defect.
    if [ "$ec" = "2" ] && [ -n "$out" ]; then verdict="PASS"; PASS=$((PASS+1))
    else verdict="FAIL"; FAIL=$((FAIL+1)); fi
  else
    if [ "$ec" = "0" ]; then verdict="PASS"; PASS=$((PASS+1))
    else verdict="FAIL"; FAIL=$((FAIL+1)); fi
  fi
  printf '  [%s] %-56s exit=%s\n' "$verdict" "$label" "$ec"
  if [ "$verdict" = "FAIL" ]; then
    printf '         expected=%s stderr=%s\n' "$expected" "$(printf '%s' "$out" | head -1)"
  fi
}

echo "=== dependency-preflight: enforcement must fail closed on a missing tool ==="
echo "Hook: $HOOK"
echo ""

# ---------------------------------------------------------------------
# 1. jq / cat class — detector: a production deploy.
# ---------------------------------------------------------------------
echo "-- jq/cat class (detector: 'vercel deploy --prod') --"
NOJQ="$(mirror_without jq)"
if [ -e "$NOJQ/jq" ] || ! [ -e "$NOJQ/sed" ]; then
  echo "  [FAIL] mirror PATH construction broken (jq present or sed missing)"
  FAIL=$((FAIL+1))
fi
probe "jq ABSENT      + production deploy   -> BLOCK" BLOCK "$DANGER" "$CORRUPT_BIN:$NOJQ"
probe "cat ABSENT     + production deploy   -> BLOCK" BLOCK "$DANGER" "$CORRUPT_BIN:$(mirror_without cat)"

mkdir -p "$WORK/brokenjq"
printf '#!/bin/sh\nexit 1\n' > "$WORK/brokenjq/jq"
chmod +x "$WORK/brokenjq/jq"
probe "jq BROKEN      + production deploy   -> BLOCK" BLOCK "$DANGER" "$WORK/brokenjq:$CORRUPT_BIN:$PATH"

# A jq that LIES rather than fails: answers the preflight probe correctly and
# returns empty for .tool_name. Passes both the presence check and the
# functional probe, so this arm asserts the gate does not rest on the probe —
# the malformed-payload guard is what has to catch it. Officer-writable
# $HOME/.local/bin sits ahead of the system dirs on the officer PATH, so a
# shadowing jq is a realistic same-uid route, not a contrived one.
probe "jq LYING       + production deploy   -> BLOCK" BLOCK "$DANGER" "$SCRIPT_DIR/fixtures-lying-jq:$CORRUPT_BIN:$PATH"

# ---------------------------------------------------------------------
# 2. grep / sed / tr class — detector: a Bash write to a germline file.
#    Pre-change every one of these returned EXIT 0, i.e. the write to the
#    Captain's veto file was allowed.
# ---------------------------------------------------------------------
echo "-- grep/sed/tr class (detector: Bash write to captain-vetoes.yml) --"
probe "toolchain OK   + germline write      -> BLOCK" BLOCK "$GERMLINE" "$TEST_BIN:$PATH"
for dep in grep sed tr; do
  probe "$(printf '%-14s' "$dep ABSENT") + germline write      -> BLOCK" \
        BLOCK "$GERMLINE" "$CORRUPT_BIN:$(mirror_without "$dep")"
done

# ---------------------------------------------------------------------
# 3. awk / date class — detector: an over-cap spend ledger.
#    Pre-change both returned EXIT 0 with $999,000 recorded against a $225 cap.
# ---------------------------------------------------------------------
echo "-- awk/date class (detector: over-cap spend ledger) --"
probe "toolchain OK   + over-cap ledger     -> BLOCK" BLOCK "$BENIGN" "$OVERCAP_BIN:$PATH"
for dep in awk date; do
  probe "$(printf '%-14s' "$dep ABSENT") + over-cap ledger     -> BLOCK" \
        BLOCK "$BENIGN" "$OVERCAP_BIN:$(mirror_without "$dep")"
done

# ---------------------------------------------------------------------
# 4. Defence-in-depth arms — no bypass demonstrated at this operating point.
#    These assert the preflight refuses, nothing stronger. See header.
# ---------------------------------------------------------------------
echo "-- defence-in-depth (preflight refuses; no bypass demonstrated) --"
for dep in cut head mktemp dirname perl python3; do
  probe "$(printf '%-14s' "$dep ABSENT") + production deploy   -> BLOCK" \
        BLOCK "$DANGER" "$CORRUPT_BIN:$(mirror_without "$dep")"
done

# ---------------------------------------------------------------------
# 5. NO FALSE POSITIVES — the arms that stop this fix bricking the cabinet.
# ---------------------------------------------------------------------
echo "-- no-false-positive guards --"
probe "toolchain OK   + benign command      -> ALLOW" ALLOW "$BENIGN" "$TEST_BIN:$PATH"
probe "toolchain OK   + benign Read         -> ALLOW" ALLOW '{"tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}' "$TEST_BIN:$PATH"
probe "toolchain OK   + production deploy   -> BLOCK" BLOCK "$DANGER" "$TEST_BIN:$PATH"

# ---------------------------------------------------------------------
# 6. MALFORMED PAYLOAD — even with a working jq, an empty or unparseable
#    payload yielded TOOL_NAME="" which matched no gate and fell through to 0.
# ---------------------------------------------------------------------
echo "-- malformed payload --"
probe "empty payload                        -> BLOCK" BLOCK ''                                                    "$TEST_BIN:$PATH"
probe "non-JSON payload                     -> BLOCK" BLOCK 'not json at all'                                     "$TEST_BIN:$PATH"
probe "JSON, no tool_name, danger           -> BLOCK" BLOCK '{"tool_input":{"command":"vercel deploy --prod"}}'   "$TEST_BIN:$PATH"
probe "JSON, empty tool_name                -> BLOCK" BLOCK '{"tool_name":"","tool_input":{}}'                    "$TEST_BIN:$PATH"

# ---------------------------------------------------------------------
# 7. LEDGER INTEGRITY — a corrupt spend ledger must refuse, not read as $0.
# ---------------------------------------------------------------------
echo "-- spend-ledger integrity --"
# OWN row corrupt -> refuse. Blast radius is one session, and it is the
# officer's own data, so fail-closed is right.
probe "corrupt ledger value (own row)       -> BLOCK" BLOCK "$BENIGN" "$CORRUPT_BIN:$PATH"
# ANOTHER officer's row corrupt -> must PROCEED. Failing closed on shared data
# would let one field, writable by any same-uid officer and TTL-less on a bare
# HSET, halt the whole fleet with no in-band repair path.
probe "corrupt ledger value (foreign row)   -> ALLOW" ALLOW "$BENIGN" "$SCRIPT_DIR/fixtures-ledger-corrupt-foreign:$PATH"

# ---------------------------------------------------------------------
# 8. redis-cli keeps its RATIFIED posture (EVAL-001c).
# ---------------------------------------------------------------------
echo "-- redis-cli posture is unchanged (EVAL-001c) --"
NOREDIS="$(mirror_without redis-cli)"
probe "redis-cli ABSENT + Bash              -> BLOCK" BLOCK "$BENIGN" "$NOREDIS"
probe "redis-cli ABSENT + Read              -> ALLOW" ALLOW '{"tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}' "$NOREDIS"

# ---------------------------------------------------------------------
# 9. post-tool-use.sh — the audit log must not silently record a hollow entry.
#    It decides nothing, so exit 2 here does not undo the tool; it makes the
#    lost audit record loud instead of silent.
# ---------------------------------------------------------------------
echo "-- post-tool-use audit integrity --"
post_probe() {
  local label="$1" expected="$2" use_path="$3"
  local ec verdict
  printf '%s' '{"tool_name":"Bash","tool_input":{"command":"echo hi"},"tool_response":{}}' \
    | env -i PATH="$use_path" HOME="${HOME:-/tmp}" CABINET_ROOT="$REPO_ROOT" \
      CABINET_HOOK_TEST_MODE=1 OFFICER_NAME=cos CABINET_LOG_DIR="$WORK/logs" \
      "$BASH_BIN" "$POST_HOOK" >/dev/null 2>&1
  ec=$?
  if [ "$expected" = "BLOCK" ]; then
    if [ "$ec" = "2" ]; then verdict="PASS"; PASS=$((PASS+1)); else verdict="FAIL"; FAIL=$((FAIL+1)); fi
  else
    if [ "$ec" = "0" ]; then verdict="PASS"; PASS=$((PASS+1)); else verdict="FAIL"; FAIL=$((FAIL+1)); fi
  fi
  printf '  [%s] %-56s exit=%s\n' "$verdict" "$label" "$ec"
}
post_probe "post-hook jq ABSENT                  -> BLOCK" BLOCK "$CORRUPT_BIN:$NOJQ"
post_probe "post-hook toolchain OK               -> ALLOW" ALLOW "$TEST_BIN:$PATH"

echo ""
echo "=== dependency-preflight summary ==="
echo "PASS: $PASS"
echo "FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
