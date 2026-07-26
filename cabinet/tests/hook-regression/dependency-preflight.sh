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

# ---------------------------------------------------------------------
# BLOCK REASONS — the gate each arm must prove refused it.
#
# WHY THIS EXISTS (the defect this harness was itself carrying): asserting
# only `exit 2` certified something other than the control. Every arm below
# used to run with the CORRUPT-LEDGER redis-cli stub first on PATH, so the
# spend-ledger gate refused the call before the dependency preflight was ever
# the reason — and the grep/sed/tr arms passed while the germline write they
# name was NOT being blocked. Measured: DELETE the preflight entirely and the
# original harness still scored 28 of 30 PASS. A control test that survives
# deletion of the control is not testing it.
#
# Two changes make each arm honest, and they are load-bearing together:
#   1. ASSERT THE REASON. A BLOCK arm names the gate that must refuse it and
#      the arm fails if some other gate did. Passing an empty reason is itself
#      a failure, so a future arm cannot be added without one.
#   2. NEUTRAL STUB. Dependency arms run with fixtures/redis-cli (reachable,
#      key-absent, ledger-absent) so no ledger/kill-switch gate can be the
#      thing refusing. With that stub and no preflight, these payloads LEAK
#      (exit 0) — which is exactly what the arms must detect.
# MEASURED, both directions (2026-07-26, same box, same stubs). Mutation =
# delete the `if [ -n "$_CABINET_MISSING_DEPS" ]` refusal from pre-tool-use.sh,
# leaving the detection loop in place:
#   original harness, control intact  -> 30 PASS / 0 FAIL
#   original harness, control DELETED -> 28 PASS / 2 FAIL   <- vacuous
#   this harness,     control intact  -> 32 PASS / 0 FAIL
#   this harness,     control DELETED -> 18 PASS / 14 FAIL
# Of the 15 arms that name the preflight as their gate, 14 now go red on the
# mutation. The 15th — `jq LYING` — passes because its declared gate is the
# MALFORMED-PAYLOAD guard, a genuinely separate control that the mutation does
# not remove; that is a correct pass, not a survivor. The other 17 arms are
# positive controls and posture pins that never depended on the preflight and
# must keep passing. Re-run the mutation whenever an arm is added: an arm that
# survives deletion of the gate it names is not testing that gate.
R_PREFLIGHT='BLOCKED: pre-tool-use enforcement cannot run — missing or non-functional required tool'
R_PAYLOAD='BLOCKED: pre-tool-use received no parseable tool_name'
R_GERMLINE='BLOCKED: Germline file'
# Gate, not rule id, and deliberately so: the typed policy engine resolves a
# DIFFERENT rule name for the same payload depending on $HOME (measured on this
# tree — `production_deploy_requires_captain_approval` under a scratch HOME,
# `no_production_deploy` under the Captain's), because policy resolution reads
# user-level config. Pinning the rule id would flake between CI and a live Mac.
# The gate identity is the property under test here; which rule fired is the
# policy corpus's business and is asserted by the policy suites.
R_POLICY='TYPED POLICY BLOCK'
R_CAP='BLOCKED — officer=cos today='
R_LEDGER_OWN='BLOCKED — your own spend ledger row'
R_LEDGER_OWN_WARN='WARN your own spend ledger row'
R_KILLSWITCH='KILL SWITCH UNVERIFIABLE'
R_POST_PREFLIGHT='post-tool-use: FAILING CLOSED — missing or non-functional required tool'

# probe <label> <expected BLOCK|ALLOW> <payload> <PATH to use> <reason>
# <reason> is a FIXED string that must appear on stderr. Mandatory for BLOCK
# (that is the whole point); for ALLOW it is optional — pass '' to skip, or a
# string that must still be present (used for the warn-but-proceed arms).
probe() {
  local label="$1" expected="$2" payload="$3" use_path="$4" reason="${5-}"
  local out ec verdict
  out=$(printf '%s' "$payload" | env -i \
        PATH="$use_path" HOME="${HOME:-/tmp}" \
        CABINET_ROOT="$REPO_ROOT" CABINET_HOOK_TEST_MODE=1 \
        OFFICER_NAME=cos OFFICER=cos PYTHONDONTWRITEBYTECODE=1 \
        "$BASH_BIN" "$HOOK" 2>&1 >/dev/null)
  ec=$?
  local why=""
  if [ "$expected" = "BLOCK" ]; then
    # A block must be exit 2, say why, AND the why must be THE GATE NAMED.
    if [ -z "$reason" ]; then
      verdict="FAIL"; FAIL=$((FAIL+1)); why="arm declares no expected block reason"
    elif [ "$ec" != "2" ]; then
      verdict="FAIL"; FAIL=$((FAIL+1)); why="expected exit 2, got $ec"
    elif [ -z "$out" ]; then
      verdict="FAIL"; FAIL=$((FAIL+1)); why="blocked silently (no stderr)"
    elif ! printf '%s' "$out" | grep -qF -- "$reason"; then
      verdict="FAIL"; FAIL=$((FAIL+1))
      why="blocked by the WRONG gate — wanted [$reason]"
    else
      verdict="PASS"; PASS=$((PASS+1))
    fi
  else
    if [ "$ec" != "0" ]; then
      verdict="FAIL"; FAIL=$((FAIL+1)); why="expected exit 0, got $ec"
    elif [ -n "$reason" ] && ! printf '%s' "$out" | grep -qF -- "$reason"; then
      verdict="FAIL"; FAIL=$((FAIL+1)); why="allowed but did not say [$reason]"
    else
      verdict="PASS"; PASS=$((PASS+1))
    fi
  fi
  printf '  [%s] %-56s exit=%s\n' "$verdict" "$label" "$ec"
  if [ "$verdict" = "FAIL" ]; then
    printf '         %s\n         stderr=%s\n' "$why" "$(printf '%s' "$out" | head -1)"
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
probe "jq ABSENT      + production deploy   -> BLOCK" BLOCK "$DANGER" "$TEST_BIN:$NOJQ" "$R_PREFLIGHT"
probe "cat ABSENT     + production deploy   -> BLOCK" BLOCK "$DANGER" "$TEST_BIN:$(mirror_without cat)" "$R_PREFLIGHT"

mkdir -p "$WORK/brokenjq"
printf '#!/bin/sh\nexit 1\n' > "$WORK/brokenjq/jq"
chmod +x "$WORK/brokenjq/jq"
probe "jq BROKEN      + production deploy   -> BLOCK" BLOCK "$DANGER" "$WORK/brokenjq:$TEST_BIN:$PATH" "$R_PREFLIGHT"

# A jq that LIES rather than fails: answers the preflight probe correctly and
# returns empty for .tool_name. Passes both the presence check and the
# functional probe, so this arm asserts the gate does not rest on the probe —
# the malformed-payload guard is what has to catch it. Officer-writable
# $HOME/.local/bin sits ahead of the system dirs on the officer PATH, so a
# shadowing jq is a realistic same-uid route, not a contrived one.
# The gate that must catch it is the MALFORMED-PAYLOAD guard, not the
# preflight — the lying jq passes the preflight's functional probe by design.
# Naming the gate is what proves the claim "the gate does not rest on the probe".
probe "jq LYING       + production deploy   -> BLOCK" BLOCK "$DANGER" "$SCRIPT_DIR/fixtures-lying-jq:$TEST_BIN:$PATH" "$R_PAYLOAD"

# ---------------------------------------------------------------------
# 2. grep / sed / tr class — detector: a Bash write to a germline file.
#    Pre-change every one of these returned EXIT 0, i.e. the write to the
#    Captain's veto file was allowed.
# ---------------------------------------------------------------------
echo "-- grep/sed/tr class (detector: Bash write to captain-vetoes.yml) --"
# Positive control: with the toolchain intact the germline gate itself refuses.
probe "toolchain OK   + germline write      -> BLOCK" BLOCK "$GERMLINE" "$TEST_BIN:$PATH" "$R_GERMLINE"
# With the dep removed the germline gate can no longer match — verified: on the
# neutral stub with the preflight deleted these leak at exit 0. So the preflight
# is the ONLY thing that can be refusing, and the arm now says so.
for dep in grep sed tr; do
  probe "$(printf '%-14s' "$dep ABSENT") + germline write      -> BLOCK" \
        BLOCK "$GERMLINE" "$TEST_BIN:$(mirror_without "$dep")" "$R_PREFLIGHT"
done

# ---------------------------------------------------------------------
# 3. awk / date class — detector: an over-cap spend ledger.
#    Pre-change both returned EXIT 0 with $999,000 recorded against a $225 cap.
# ---------------------------------------------------------------------
echo "-- awk/date class (detector: over-cap spend ledger) --"
# Positive control: the cap gate itself refuses $999,000 against a $225 cap.
probe "toolchain OK   + over-cap ledger     -> BLOCK" BLOCK "$BENIGN" "$OVERCAP_BIN:$PATH" "$R_CAP"
# The ABSENT arms run on the NEUTRAL stub, not the over-cap one. Keeping the
# over-cap stub here would re-introduce the original defect in miniature: with
# awk gone the cap arithmetic collapses, so the over-cap stub cannot be what
# refuses, and pairing it with a bare exit-2 check is what made these arms
# vacuous. Neutral stub + named gate = the preflight is provably the refuser.
for dep in awk date; do
  probe "$(printf '%-14s' "$dep ABSENT") + benign command      -> BLOCK" \
        BLOCK "$BENIGN" "$TEST_BIN:$(mirror_without "$dep")" "$R_PREFLIGHT"
done

# ---------------------------------------------------------------------
# 4. Defence-in-depth arms — no bypass demonstrated at this operating point.
#    These assert the preflight refuses, nothing stronger. See header.
# ---------------------------------------------------------------------
echo "-- defence-in-depth (preflight refuses; no bypass demonstrated) --"
for dep in cut head mktemp dirname perl python3; do
  probe "$(printf '%-14s' "$dep ABSENT") + production deploy   -> BLOCK" \
        BLOCK "$DANGER" "$TEST_BIN:$(mirror_without "$dep")" "$R_PREFLIGHT"
done

# ---------------------------------------------------------------------
# 5. NO FALSE POSITIVES — the arms that stop this fix bricking the cabinet.
# ---------------------------------------------------------------------
echo "-- no-false-positive guards --"
probe "toolchain OK   + benign command      -> ALLOW" ALLOW "$BENIGN" "$TEST_BIN:$PATH" ''
probe "toolchain OK   + benign Read         -> ALLOW" ALLOW '{"tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}' "$TEST_BIN:$PATH" ''
probe "toolchain OK   + production deploy   -> BLOCK" BLOCK "$DANGER" "$TEST_BIN:$PATH" "$R_POLICY"

# ---------------------------------------------------------------------
# 6. MALFORMED PAYLOAD — even with a working jq, an empty or unparseable
#    payload yielded TOOL_NAME="" which matched no gate and fell through to 0.
# ---------------------------------------------------------------------
echo "-- malformed payload --"
probe "empty payload                        -> BLOCK" BLOCK ''                                                    "$TEST_BIN:$PATH" "$R_PAYLOAD"
probe "non-JSON payload                     -> BLOCK" BLOCK 'not json at all'                                     "$TEST_BIN:$PATH" "$R_PAYLOAD"
probe "JSON, no tool_name, danger           -> BLOCK" BLOCK '{"tool_input":{"command":"vercel deploy --prod"}}'   "$TEST_BIN:$PATH" "$R_PAYLOAD"
probe "JSON, empty tool_name                -> BLOCK" BLOCK '{"tool_name":"","tool_input":{}}'                    "$TEST_BIN:$PATH" "$R_PAYLOAD"

# ---------------------------------------------------------------------
# 7. LEDGER INTEGRITY — a corrupt spend ledger must refuse, not read as $0.
# ---------------------------------------------------------------------
echo "-- spend-ledger integrity --"
# OWN row corrupt -> refuse STATE-CHANGING calls. Blast radius is one session,
# and it is the officer's own data, so fail-closed is right for mutations.
probe "own-row-corrupt + Bash               -> BLOCK" BLOCK "$BENIGN" "$CORRUPT_BIN:$PATH" "$R_LEDGER_OWN"
# ...but NOT reads. A blanket own-row refusal was a targeted cross-officer DoS:
# any same-uid officer can HSET `<victim>_cost_micro garbage`, HINCRBY cannot
# overwrite a non-numeric field so it persists to the UTC rollover, and the
# victim lost EVERY tool including Read — unable to see the problem, report it,
# or be told what happened. Scoped to §1's ratified posture (EVAL-001c): reads
# and the Captain-comms door stay open, mutations fail closed. These two arms
# pin that split; if a future "harden everything" change re-blankets the arm,
# the Read arm goes red.
probe "own-row-corrupt + Read               -> ALLOW" ALLOW '{"tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}' "$CORRUPT_BIN:$PATH" "$R_LEDGER_OWN_WARN"
probe "own-row-corrupt + Grep               -> ALLOW" ALLOW '{"tool_name":"Grep","tool_input":{"pattern":"x"}}' "$CORRUPT_BIN:$PATH" "$R_LEDGER_OWN_WARN"
# ANOTHER officer's row corrupt -> must PROCEED. Failing closed on shared data
# would let one field, writable by any same-uid officer and TTL-less on a bare
# HSET, halt the whole fleet with no in-band repair path. This is also the
# repair path for the own-row case above: a bystander officer's Bash still runs
# the `redis-cli HDEL` that clears the poison.
probe "corrupt ledger value (foreign row)   -> ALLOW" ALLOW "$BENIGN" "$SCRIPT_DIR/fixtures-ledger-corrupt-foreign:$PATH" ''

# ---------------------------------------------------------------------
# 8. redis-cli keeps its RATIFIED posture (EVAL-001c).
# ---------------------------------------------------------------------
echo "-- redis-cli posture is unchanged (EVAL-001c) --"
NOREDIS="$(mirror_without redis-cli)"
probe "redis-cli ABSENT + Bash              -> BLOCK" BLOCK "$BENIGN" "$NOREDIS" "$R_KILLSWITCH"
probe "redis-cli ABSENT + Read              -> ALLOW" ALLOW '{"tool_name":"Read","tool_input":{"file_path":"/tmp/x"}}' "$NOREDIS" ''

# ---------------------------------------------------------------------
# 9. post-tool-use.sh — the audit log must not silently record a hollow entry.
#    It decides nothing, so exit 2 here does not undo the tool; it makes the
#    lost audit record loud instead of silent.
# ---------------------------------------------------------------------
echo "-- post-tool-use audit integrity --"
post_probe() {
  local label="$1" expected="$2" use_path="$3" reason="${4-}"
  local ec verdict out why=""
  out=$(printf '%s' '{"tool_name":"Bash","tool_input":{"command":"echo hi"},"tool_response":{}}' \
    | env -i PATH="$use_path" HOME="${HOME:-/tmp}" CABINET_ROOT="$REPO_ROOT" \
      CABINET_HOOK_TEST_MODE=1 OFFICER_NAME=cos CABINET_LOG_DIR="$WORK/logs" \
      "$BASH_BIN" "$POST_HOOK" 2>&1 >/dev/null)
  ec=$?
  if [ "$expected" = "BLOCK" ]; then
    if [ -z "$reason" ]; then
      verdict="FAIL"; FAIL=$((FAIL+1)); why="arm declares no expected block reason"
    elif [ "$ec" != "2" ]; then
      verdict="FAIL"; FAIL=$((FAIL+1)); why="expected exit 2, got $ec"
    elif ! printf '%s' "$out" | grep -qF -- "$reason"; then
      verdict="FAIL"; FAIL=$((FAIL+1)); why="blocked by the WRONG gate — wanted [$reason]"
    else
      verdict="PASS"; PASS=$((PASS+1))
    fi
  else
    if [ "$ec" = "0" ]; then verdict="PASS"; PASS=$((PASS+1)); else verdict="FAIL"; FAIL=$((FAIL+1)); why="expected exit 0, got $ec"; fi
  fi
  printf '  [%s] %-56s exit=%s\n' "$verdict" "$label" "$ec"
  [ "$verdict" = "FAIL" ] && printf '         %s\n         stderr=%s\n' "$why" "$(printf '%s' "$out" | head -1)"
  return 0
}
post_probe "post-hook jq ABSENT                  -> BLOCK" BLOCK "$TEST_BIN:$NOJQ" "$R_POST_PREFLIGHT"
post_probe "post-hook toolchain OK               -> ALLOW" ALLOW "$TEST_BIN:$PATH"

echo ""
echo "=== dependency-preflight summary ==="
echo "PASS: $PASS"
echo "FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
