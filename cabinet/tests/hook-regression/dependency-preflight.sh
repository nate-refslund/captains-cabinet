#!/bin/bash
# dependency-preflight.sh — the enforcement plane must fail CLOSED when its
# toolchain is missing or lying.
#
# WHAT THIS EXISTS FOR. pre-tool-use.sh parses its payload with `cat | jq` and
# every gate dispatches on the result. Before the preflight landed, removing jq
# from PATH emptied TOOL_NAME and TOOL_INPUT, no gate arm matched, and control
# reached the script's closing `exit 0` = ALLOW. Measured against master
# 8ffeae51: 24 of 24 payloads that block on a healthy toolchain — `sudo rm -rf
# /`, a Write to a germline path, a Bash append to the Captain-law plane, a
# production deploy, an out-of-scope MCP call — were ALLOWED, exit 0, with zero
# bytes on stderr.
#
# WHY NOBODY SAW IT. CI installs jq explicitly, so every existing gate test ran
# in the one environment where the fault cannot occur. This harness therefore
# BUILDS the deprived environment itself, out of symlinks, rather than relying
# on the host to be missing anything. It is designed to run on a machine with a
# complete toolchain and still exercise the incomplete one.
#
# THE HARNESS CONTRACT, because a vacuous harness is how this class survives:
#   * every arm names the GATE that must refuse it and FAILS if a different
#     gate did — a kill-switch refusal is not a preflight refusal, and an arm
#     that accepts any exit 2 proves nothing;
#   * an arm with an empty expected-signature is itself a failure, so no arm
#     can be added without one;
#   * the harness re-proves its own non-vacuity ON EVERY RUN (arms MUT-*): it
#     strips the preflight from a copy of the LIVE hook and requires the copy
#     to leak. If the copy does not leak, this harness cannot see the defect it
#     exists for, and that is a FAIL, never a skip;
#   * negative controls (arm NEG-*) require that a healthy toolchain never
#     produces a preflight refusal, AND that a benign call is genuinely ALLOWED
#     (NEG-0, exit 0) — an absent-signature check alone passes while some other
#     gate refuses everything, which a review demonstrated by pointing an
#     earlier version of this file at an unreachable control plane and watching
#     it stay green while every Bash call was blocked;
#   * the ABS-* and LIE-* arms take their dependency list FROM the hook, so a
#     dependency ADDED to the preflight is tested automatically. A hardcoded
#     copy only catches removals.
#
# WHAT THIS HARNESS STILL CANNOT SEE, stated so nobody reads a green run as more
# than it is: every arm invokes the hook through `env -i`, so a hostile edit that
# gates the refusal on an environment variable (`[ "${SOMEVAR:-on}" = on ]`)
# leaves every arm green while the plane is defeatable by exporting that
# variable. The MUT-* arms catch REMOVAL of the preflight, not an env-gated
# escape hatch added to it. Reviewing the diff remains load-bearing.
#
# HERMETIC, AND THE HARNESS PROVES IT RATHER THAN CLAIMING IT. The first
# version of this file claimed hermeticity and was not: `env -i` without
# REDIS_HOST/REDIS_PORT let the hooks fall back to their 127.0.0.1:6379 default,
# so the full-toolchain arms wrote seven keys into the LIVE control plane under
# a phantom officer (one of them a stream with no TTL, which the dashboard's
# `cabinet:officer:activity:*` scan then rendered as a real officer), and the
# post-hook arms appended phantom entries to the real `memory/logs/` audit
# trail. CI could never have caught it — its Redis is a throwaway service
# container and its checkout is disposable, which is precisely the
# "what does the test environment guarantee that production does not?" trap
# this harness exists to close. So now:
#   * every hook run is pinned to $DEAD_PORT, and arm HERM-1 refuses to run a
#     single other arm unless that port is proven CLOSED (bash /dev/tcp, no
#     external binary);
#   * CABINET_LOG_DIR is redirected into the scratch dir, so no audit line is
#     ever appended to a real log;
#   * CABINET_ESTOP_MARKER points at a scratch path that does not exist, so the
#     real emergency-stop marker is never read and never written.
# Every arm's verdict is decided ABOVE §1 (or asserts the ABSENCE of a gate's
# signature), so an unreachable control plane cannot change any result.
#
# Exit 0 = all arms passed. Exit = number of failed arms otherwise.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PRE_HOOK="$REPO_ROOT/cabinet/scripts/hooks/pre-tool-use.sh"
POST_HOOK="$REPO_ROOT/cabinet/scripts/hooks/post-tool-use.sh"
SETTINGS="$REPO_ROOT/.claude/settings.json"
CHECK_DEPS="$REPO_ROOT/cabinet/scripts/check-deps.sh"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dep-preflight.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/home" "$WORK/logs"

# Where every hook run is pointed instead of the real control plane. Asserted
# closed by HERM-1 before any arm runs, so no arm can write anywhere.
DEAD_PORT="${DEP_PREFLIGHT_DEAD_PORT:-1}"

PASS=0
FAIL=0

# ---- gate signatures ------------------------------------------------------
# The literal each arm must (or must not) see on stderr. Naming the gate is the
# whole point: "exit 2" alone is satisfied by the kill-switch, by observe-only,
# or by any unrelated refusal, and an arm that accepts it is decorative.
SIG_PREFLIGHT="pre-tool-use enforcement cannot run"
SIG_PAYLOAD="no parseable tool_name"
SIG_CROSSCHECK="does not appear in the raw payload"
SIG_POST="post-tool-use: FAILING CLOSED"
SIG_TYPED="TYPED POLICY BLOCK"

ok ()   { PASS=$((PASS + 1)); printf '  [PASS] %s\n' "$1"; }
bad ()  { FAIL=$((FAIL + 1)); printf '  [FAIL] %s\n      %s\n' "$1" "$2"; }

# ---- curated PATH construction -------------------------------------------
# TOOLS is everything either hook may reach for. A curated bin dir is a
# directory of symlinks; omitting a name from it is how a binary is made
# "absent" without touching the host.
TOOLS="bash sh cat sed awk grep egrep fgrep tr cut date rm mkdir mktemp
python3 git head tail sort uniq wc dirname basename readlink realpath stat env
id whoami sleep xargs find ls cp mv touch chmod comm diff perl jq redis-cli dd
od tee expr uname hostname ps"

# mkbin <name> [omit ...] -> echoes the bin dir path
mkbin () {
  local name="$1"; shift
  local bin="$WORK/bin-$name"
  local t p skip
  rm -rf "$bin"; mkdir -p "$bin"
  for t in $TOOLS; do
    skip=""
    for o in "$@"; do [ "$t" = "$o" ] && skip=1; done
    [ -n "$skip" ] && continue
    p="$(command -v "$t" 2>/dev/null)" && ln -sf "$p" "$bin/$t"
  done
  printf '%s' "$bin"
}

# shim <name> <binary> <body> -> echoes a bin dir where <binary> is replaced by
# a script with <body>, everything else real. Models the officer-writable
# $HOME/.local/bin that start-officer-mac.sh puts AHEAD of the system dirs.
shim () {
  local name="$1" binary="$2" body="$3"
  local bin
  bin="$(mkbin "$name" "$binary")"
  printf '#!/bin/bash\n%s\n' "$body" > "$bin/$binary"
  chmod +x "$bin/$binary"
  printf '%s' "$bin"
}

FULL="$(mkbin full)"

# ---- runner ---------------------------------------------------------------
# Runs a hook with a constructed PATH and captures exit code + stderr.
RUN_EC=0
RUN_ERR=""
run_hook () {
  local hook="$1" bin="$2" payload="$3"
  RUN_ERR="$(printf '%s' "$payload" | env -i \
      PATH="$bin" \
      HOME="$WORK/home" \
      CABINET_ROOT="$REPO_ROOT" \
      CABINET_ESTOP_MARKER="$WORK/no-such-estop-marker" \
      CABINET_LOG_DIR="$WORK/logs" \
      REDIS_HOST=127.0.0.1 \
      REDIS_PORT="$DEAD_PORT" \
      REDIS_URL="redis://127.0.0.1:$DEAD_PORT" \
      OFFICER_NAME=dep-preflight-harness \
      /bin/bash "$hook" 2>&1 >/dev/null)"
  RUN_EC=$?
}

# expect_refusal <arm> <hook> <bin> <payload> <signature>
# Requires exit 2 AND that the named gate is the refuser.
expect_refusal () {
  local arm="$1" hook="$2" bin="$3" payload="$4" sig="$5"
  if [ -z "$sig" ]; then
    bad "$arm" "arm declares no expected gate signature — an arm that accepts any refusal proves nothing"
    return
  fi
  run_hook "$hook" "$bin" "$payload"
  if [ "$RUN_EC" != "2" ]; then
    bad "$arm" "expected exit 2 (refused by: $sig), got exit $RUN_EC. stderr: $(printf '%s' "$RUN_ERR" | tr '\n' ' ' | cut -c1-160)"
    return
  fi
  case "$RUN_ERR" in
    *"$sig"*) ok "$arm" ;;
    *) bad "$arm" "refused (exit 2) but by the WRONG gate — expected '$sig', got: $(printf '%s' "$RUN_ERR" | tr '\n' ' ' | cut -c1-160)" ;;
  esac
}

# expect_absent_signature <arm> <hook> <bin> <payload> <signature>
# The verdict is irrelevant; the named gate must NOT be the one talking.
expect_absent_signature () {
  local arm="$1" hook="$2" bin="$3" payload="$4" sig="$5"
  run_hook "$hook" "$bin" "$payload"
  case "$RUN_ERR" in
    *"$sig"*) bad "$arm" "'$sig' fired on a healthy toolchain — false positive: $(printf '%s' "$RUN_ERR" | tr '\n' ' ' | cut -c1-160)" ;;
    *) ok "$arm" ;;
  esac
}

# expect_allow <arm> <hook> <bin> <payload>
# The ONLY arm shape that proves fail-closed did not become block-everything.
# An absent-signature check is not enough: it passes while some OTHER gate
# refuses the call, which an adversarial review demonstrated by pointing this
# harness at an unreachable control plane and watching it stay green while
# every Bash call was refused by §1.
expect_allow () {
  local arm="$1" hook="$2" bin="$3" payload="$4"
  run_hook "$hook" "$bin" "$payload"
  if [ "$RUN_EC" = "0" ]; then
    ok "$arm"
  else
    bad "$arm" "expected exit 0 (ALLOWED), got exit $RUN_EC — fail-closed must not mean block-everything. stderr: $(printf '%s' "$RUN_ERR" | tr '\n' ' ' | cut -c1-160)"
  fi
}

BENIGN='{"tool_name":"Bash","tool_input":{"command":"echo hello"}}'
DEPLOY='{"tool_name":"Bash","tool_input":{"command":"vercel deploy --prod"}}'
POST_PAYLOAD='{"tool_name":"Bash","tool_input":{"command":"echo hello"},"tool_response":{"stdout":"hello"}}'
# The ALLOW control. A Read is used rather than a Bash call on purpose: §1
# keeps read tools open when the control plane is unverifiable (EVAL-001c), and
# this harness deliberately runs against a dead control plane, so a Bash call
# would be refused by §1 for reasons that have nothing to do with this fix.
BENIGN_READ='{"tool_name":"Read","tool_input":{"file_path":"README.md"}}'

echo "=== Dependency preflight — enforcement plane fails closed on a missing or lying toolchain ==="
echo "repo: $REPO_ROOT"
echo ""

# ===========================================================================
# HERMETICITY — proven before a single arm runs, never assumed
# ===========================================================================
# The hooks under test write heartbeat, activity, tool-call and trigger records
# to whatever Redis they can reach, and an audit line to CABINET_LOG_DIR. Both
# are redirected above; this arm proves the redirect actually points at nothing.
# `/dev/tcp` is a bash builtin, so this check needs no binary that a curated
# PATH could remove. If the port answers, the whole harness stops: running the
# arms against a live control plane once already planted a phantom officer in
# the dashboard, and a test that pollutes what it measures is worse than no
# test.
echo "--- hermeticity ---"
if (exec 3<>"/dev/tcp/127.0.0.1/$DEAD_PORT") 2>/dev/null; then
  exec 3<&- 2>/dev/null
  bad "HERM-1 the hooks' control-plane port ($DEAD_PORT) is closed" \
      "something is LISTENING on 127.0.0.1:$DEAD_PORT — these arms would write heartbeat/activity/trigger records into it. Re-run with DEP_PREFLIGHT_DEAD_PORT=<a closed port>."
  echo ""
  echo "=== Summary ==="
  echo "PASS: $PASS"
  echo "FAIL: $FAIL"
  echo "STATUS: refusing to run against a reachable control plane"
  exit "$FAIL"
fi
ok "HERM-1 the hooks' control-plane port ($DEAD_PORT) is closed"
echo ""

# ===========================================================================
# WIRING — the sensor must point at the LIVE artifact
# ===========================================================================
# The defect class this whole harness belongs to has bitten here as a sensor
# aimed at a dead twin (a golden eval pinned stop-hook.sh, which is wired to no
# hook event). So assert the files under test are the ones the runtime loads.
echo "--- wiring drift ---"
WIRED_PRE="$(python3 - "$SETTINGS" <<'PY' 2>/dev/null
import json, sys
d = json.load(open(sys.argv[1]))
for m in d.get("hooks", {}).get("PreToolUse", []):
    if m.get("matcher", "") == "":
        for h in m.get("hooks", []):
            for a in h.get("args", []):
                print(a)
PY
)"
case "$WIRED_PRE" in
  *cabinet/scripts/hooks/pre-tool-use.sh*) ok "WIRE-1 settings.json PreToolUse(all) runs the hook this harness tests" ;;
  *) bad "WIRE-1 settings.json PreToolUse(all) runs the hook this harness tests" "PreToolUse matcher '' resolves to [$WIRED_PRE], not cabinet/scripts/hooks/pre-tool-use.sh" ;;
esac

WIRED_POST="$(python3 - "$SETTINGS" <<'PY' 2>/dev/null
import json, sys
d = json.load(open(sys.argv[1]))
for m in d.get("hooks", {}).get("PostToolUse", []):
    if m.get("matcher", "") == "":
        for h in m.get("hooks", []):
            for a in h.get("args", []):
                print(a)
PY
)"
case "$WIRED_POST" in
  *cabinet/scripts/hooks/post-tool-use.sh*) ok "WIRE-2 settings.json PostToolUse(all) runs the hook this harness tests" ;;
  *) bad "WIRE-2 settings.json PostToolUse(all) runs the hook this harness tests" "PostToolUse matcher '' resolves to [$WIRED_POST], not cabinet/scripts/hooks/post-tool-use.sh" ;;
esac

# The hook is the authority on which binaries are enforcement-critical;
# check-deps.sh is the diagnostic an operator is told to run. If they drift, the
# diagnostic sends the operator looking in the wrong place during an outage.
HOOK_DEPS="$(grep -m1 '^for _dep in .*; do' "$PRE_HOOK" | sed -e 's/^for _dep in //' -e 's/; do$//')"
POST_DEPS="$(grep -m1 '^for _dep in .*; do' "$POST_HOOK" | sed -e 's/^for _dep in //' -e 's/; do$//')"
DIAG_DEPS="$(grep -m1 '^ENFORCEMENT_CRITICAL=' "$CHECK_DEPS" | sed -e 's/^ENFORCEMENT_CRITICAL="//' -e 's/"$//')"
DIAG_POST="$(grep -m1 '^POST_HOOK_DEPS=' "$CHECK_DEPS" | sed -e 's/^POST_HOOK_DEPS="//' -e 's/"$//')"
if [ -z "$HOOK_DEPS" ]; then
  bad "WIRE-3 check-deps.sh lists exactly the pre-hook's enforcement-critical set" "could not read the preflight dependency loop from $PRE_HOOK — the preflight is missing or was reshaped"
elif [ "$HOOK_DEPS" = "$DIAG_DEPS" ]; then
  ok "WIRE-3 check-deps.sh lists exactly the pre-hook's enforcement-critical set"
else
  bad "WIRE-3 check-deps.sh lists exactly the pre-hook's enforcement-critical set" "hook=[$HOOK_DEPS] check-deps=[$DIAG_DEPS]"
fi
# WIRE-3 alone could not see a false statement ABOUT the post-hook's list: an
# earlier draft of check-deps.sh described it as "the pre-hook's set minus perl"
# when it also drops awk and adds cut/head/mkdir/dirname. Pin it directly.
if [ -z "$POST_DEPS" ]; then
  bad "WIRE-4 check-deps.sh records the post-hook's set verbatim" "could not read the preflight dependency loop from $POST_HOOK"
elif [ "$POST_DEPS" = "$DIAG_POST" ]; then
  ok "WIRE-4 check-deps.sh records the post-hook's set verbatim"
else
  bad "WIRE-4 check-deps.sh records the post-hook's set verbatim" "post-hook=[$POST_DEPS] check-deps=[$DIAG_POST]"
fi
echo ""

# ===========================================================================
# MUTATION — this harness re-proves, every run, that it can still see the bug
# ===========================================================================
# Build a copy of the LIVE hook with the preflight and the malformed-payload
# guard removed. That copy is pre-change code by construction (it tracks the
# live file, so it cannot rot into testing a stale snapshot). MUT-1 requires the
# copy to leak; MUT-2 requires the same copy, on a healthy toolchain, to still
# produce a real policy refusal — without MUT-2, MUT-1 would also "pass" in an
# environment where nothing ever blocks, which is the vacuous case.
echo "--- mutation (non-vacuity) ---"
STRIPPED="$WORK/pre-tool-use.stripped.sh"
python3 - "$PRE_HOOK" "$STRIPPED" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
out = src
# drop the preflight block: its banner through the line before the stdin read
out, n1 = re.subn(
    r"# =+\n# -1\. DEPENDENCY PREFLIGHT.*?\n(?=# Read JSON from stdin)",
    "", out, flags=re.S)
# drop the malformed-payload guard
out, n2 = re.subn(
    r"# ---- MALFORMED-PAYLOAD FAIL-CLOSED -+\n(?:#.*\n)*if \[ -z \"\$TOOL_NAME\" \]; then\n(?:.*?\n)*?fi\n",
    "", out, flags=0)
if n1 != 1 or n2 != 1:
    sys.stderr.write("MUTATION-BUILD-FAILED preflight=%d payload-guard=%d\n" % (n1, n2))
    sys.exit(3)
open(sys.argv[2], "w").write(out)
PY
MUT_BUILD=$?
if [ "$MUT_BUILD" != "0" ]; then
  bad "MUT-0 a pre-change copy of the live hook can be built" "could not remove the preflight/payload guard from $PRE_HOOK (rc=$MUT_BUILD) — either they are gone, or they were reshaped and this harness is now blind"
else
  ok "MUT-0 a pre-change copy of the live hook can be built"

  NOJQ="$(mkbin nojq jq)"
  # MUT-2 first: prove the environment CAN produce a policy refusal at all.
  run_hook "$STRIPPED" "$FULL" "$DEPLOY"
  case "$RUN_ERR" in
    *"$SIG_TYPED"*) ok "MUT-2 pre-change copy still refuses a production deploy on a healthy toolchain" ;;
    *) bad "MUT-2 pre-change copy still refuses a production deploy on a healthy toolchain" "expected '$SIG_TYPED'; got exit $RUN_EC / $(printf '%s' "$RUN_ERR" | tr '\n' ' ' | cut -c1-160). Without this, MUT-1 below is vacuous." ;;
  esac
  # MUT-1: the defect itself. Same copy, same payload, jq removed.
  run_hook "$STRIPPED" "$NOJQ" "$DEPLOY"
  case "$RUN_ERR" in
    *"$SIG_TYPED"*) bad "MUT-1 pre-change copy LEAKS a production deploy with jq off PATH" "the policy gate still fired without jq — this harness can no longer reproduce the defect it exists for, so every arm below is unproven" ;;
    *) ok "MUT-1 pre-change copy LEAKS a production deploy with jq off PATH" ;;
  esac
fi
echo ""

# ===========================================================================
# ABSENT — one enforcement-critical binary removed at a time
# ===========================================================================
# The arm list is DERIVED from the hook, never a copy of it. A hardcoded list
# catches a dependency REMOVED from the hook and silently fails to test one
# ADDED to it — a sensor with a blind spot on the direction that matters.
# $HOOK_DEPS is read above for WIRE-3; an empty read already failed there.
echo "--- absent binary (pre-tool-use) ---"
for dep in $HOOK_DEPS; do
  expect_refusal "ABS-$dep no '$dep' on PATH" "$PRE_HOOK" "$(mkbin "no-$dep" "$dep")" "$BENIGN" "$SIG_PREFLIGHT"
done
# Degenerate ends: everything gone, and nothing on PATH at all.
# shellcheck disable=SC2086
expect_refusal "ABS-all every enforcement binary removed" "$PRE_HOOK" \
  "$(mkbin no-all $HOOK_DEPS)" "$BENIGN" "$SIG_PREFLIGHT"
mkdir -p "$WORK/bin-empty"
expect_refusal "ABS-empty an empty PATH" "$PRE_HOOK" "$WORK/bin-empty" "$BENIGN" "$SIG_PREFLIGHT"
# The refusal must NAME the missing tool — an operator staring at a dead fleet
# needs the binary, not just the fact of a block.
run_hook "$PRE_HOOK" "$(mkbin no-jq2 jq)" "$BENIGN"
case "$RUN_ERR" in
  *"jq"*) ok "ABS-name the refusal names the missing binary" ;;
  *) bad "ABS-name the refusal names the missing binary" "stderr never mentions jq: $(printf '%s' "$RUN_ERR" | tr '\n' ' ' | cut -c1-160)" ;;
esac
echo ""

# ===========================================================================
# LYING — present, executable, and wrong. The officer-writable-PATH channel.
# ===========================================================================
# start-officer-mac.sh launches officers with PATH="$HOME/.local/bin:$PATH", so
# a same-uid officer can shadow any of these with a two-line script. Measured on
# master: a jq that exits 0 and prints nothing disarmed the entire plane; a grep
# that always exits 1 disarmed 16 of 24 gates. Presence checks alone do not see
# this, which is why the preflight probes function.
echo "--- lying binary (pre-tool-use) ---"
expect_refusal "LIE-jq-silent   jq exits 0, prints nothing" "$PRE_HOOK" \
  "$(shim lie-jq-silent jq 'exit 0')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-jq-fail     jq always fails" "$PRE_HOOK" \
  "$(shim lie-jq-fail jq 'exit 1')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-jq-garbage  jq prints something else" "$PRE_HOOK" \
  "$(shim lie-jq-garbage jq 'echo nope')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-grep-never  grep never matches" "$PRE_HOOK" \
  "$(shim lie-grep-never grep 'exit 1')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-grep-always grep always matches" "$PRE_HOOK" \
  "$(shim lie-grep-always grep 'exit 0')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-cat         cat prints nothing" "$PRE_HOOK" \
  "$(shim lie-cat cat 'exit 0')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-sed         sed passes input through" "$PRE_HOOK" \
  "$(shim lie-sed sed 'exec /bin/cat')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-awk         awk prints nothing" "$PRE_HOOK" \
  "$(shim lie-awk awk 'exit 0')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-tr          tr passes input through" "$PRE_HOOK" \
  "$(shim lie-tr tr 'exec /bin/cat')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-perl        perl prints nothing" "$PRE_HOOK" \
  "$(shim lie-perl perl 'exit 0')" "$BENIGN" "$SIG_PREFLIGHT"
# PASSTHROUGH shims specifically. An earlier probe used identity filters for
# awk and perl, so a shim that merely `exec /bin/cat`s satisfied it while lying
# to every gate downstream. These arms pin that every probed stage transforms.
expect_refusal "LIE-awk-pass    awk passes input through" "$PRE_HOOK" \
  "$(shim lie-awk-pass awk 'exec /bin/cat')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-perl-pass   perl passes input through" "$PRE_HOOK" \
  "$(shim lie-perl-pass perl 'exec /bin/cat')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-cat-trunc   cat truncates its input" "$PRE_HOOK" \
  "$(shim lie-cat-trunc cat 'exec /usr/bin/head -c 0')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-date        date prints nothing" "$PRE_HOOK" \
  "$(shim lie-date date 'exit 0')" "$BENIGN" "$SIG_PREFLIGHT"
expect_refusal "LIE-date-junk   date prints a non-date" "$PRE_HOOK" \
  "$(shim lie-date-junk date 'echo not-a-date')" "$BENIGN" "$SIG_PREFLIGHT"
echo ""

# ===========================================================================
# SHADOW + ADAPTIVE — the two channels a naive presence check cannot see
# ===========================================================================
echo "--- shadowed and adaptive substitution ---"
# A shell function exported through BASH_ENV satisfies `command -v` while
# replacing the binary for every call site; `command -v` returns a bare name
# rather than a path, which is what the hook keys off.
printf 'jq(){ printf "" ; }\nexport -f jq\n' > "$WORK/bashenv-jq.sh"
RUN_ERR="$(printf '%s' "$BENIGN" | env -i \
    PATH="$FULL" HOME="$WORK/home" CABINET_ROOT="$REPO_ROOT" \
    CABINET_ESTOP_MARKER="$WORK/no-such-estop-marker" CABINET_LOG_DIR="$WORK/logs" \
    REDIS_HOST=127.0.0.1 REDIS_PORT="$DEAD_PORT" OFFICER_NAME=dep-preflight-harness \
    BASH_ENV="$WORK/bashenv-jq.sh" /bin/bash "$PRE_HOOK" 2>&1 >/dev/null)"
RUN_EC=$?
if [ "$RUN_EC" != "2" ]; then
  bad "SHADOW-1 BASH_ENV shell-function jq" "expected exit 2, got $RUN_EC — an exported function replaced the parser and the hook proceeded"
else
  case "$RUN_ERR" in
    *"$SIG_PREFLIGHT"*) ok "SHADOW-1 BASH_ENV shell-function jq" ;;
    *) bad "SHADOW-1 BASH_ENV shell-function jq" "refused by the wrong gate: $(printf '%s' "$RUN_ERR" | tr '\n' ' ' | cut -c1-160)" ;;
  esac
fi

# The RES-021 shim in its simplest form: a jq that is REAL for every query
# except .tool_name, where it substitutes a permissive tool. It answers the
# functional probe honestly, so only the parse cross-check can see it. This arm
# pins the cost-raiser; it does not claim the class is closed — RES-021 does.
ADAPT="$WORK/bin-adaptive"
rm -rf "$ADAPT"; mkdir -p "$ADAPT"
REAL_JQ="$(command -v jq 2>/dev/null)"
if [ -z "$REAL_JQ" ]; then
  bad "ADAPT-1 probe-aware jq substituting a tool name" \
      "no real jq on this host to build the adaptive shim from — the arm cannot run, and a skipped arm is a disabled sensor, not a pass"
else
  {
    printf '#!/bin/bash\n'
    printf 'for a in "$@"; do\n'
    printf '  if [ "$a" = ".tool_name // empty" ]; then cat >/dev/null; echo Read; exit 0; fi\n'
    printf 'done\n'
    printf 'exec %s "$@"\n' "$REAL_JQ"
  } > "$ADAPT/jq"
  chmod +x "$ADAPT/jq"
  # Shim first on PATH, everything else real — the officer launcher's own order.
  expect_refusal "ADAPT-1 probe-aware jq substituting a tool name" "$PRE_HOOK" \
    "$ADAPT:$FULL" "$BENIGN" "$SIG_CROSSCHECK"
fi
echo ""

# ===========================================================================
# MALFORMED PAYLOAD — healthy toolchain, unauthorizable input
# ===========================================================================
# An empty tool_name matches no gate arm and used to reach `exit 0`. These run
# on the FULL toolchain on purpose, so the preflight cannot be the refuser and
# the payload guard is the only thing that can pass them.
echo "--- malformed payload (healthy toolchain) ---"
expect_refusal "PAY-empty     empty stdin"            "$PRE_HOOK" "$FULL" ''                      "$SIG_PAYLOAD"
expect_refusal "PAY-nonjson   stdin is not JSON"      "$PRE_HOOK" "$FULL" 'not json at all'       "$SIG_PAYLOAD"
expect_refusal "PAY-nokey     JSON without tool_name" "$PRE_HOOK" "$FULL" '{}'                    "$SIG_PAYLOAD"
expect_refusal "PAY-blank     tool_name is empty"     "$PRE_HOOK" "$FULL" '{"tool_name":""}'      "$SIG_PAYLOAD"
expect_refusal "PAY-null      tool_name is null"      "$PRE_HOOK" "$FULL" '{"tool_name":null}'    "$SIG_PAYLOAD"
expect_refusal "PAY-truncated truncated JSON"         "$PRE_HOOK" "$FULL" '{"tool_name":"Bash"'   "$SIG_PAYLOAD"
echo ""

# ===========================================================================
# NEGATIVE CONTROLS — fail-closed must not mean block-everything
# ===========================================================================
echo "--- negative controls (healthy toolchain) ---"
expect_allow "NEG-0 a benign read is ALLOWED (fail-closed is not block-everything)" \
  "$PRE_HOOK" "$FULL" "$BENIGN_READ"
expect_absent_signature "NEG-1 benign call is not refused by the preflight" \
  "$PRE_HOOK" "$FULL" "$BENIGN" "$SIG_PREFLIGHT"
expect_absent_signature "NEG-2 benign call is not refused by the payload guard" \
  "$PRE_HOOK" "$FULL" "$BENIGN" "$SIG_PAYLOAD"
expect_absent_signature "NEG-2b benign call is not refused by the parse cross-check" \
  "$PRE_HOOK" "$FULL" "$BENIGN" "$SIG_CROSSCHECK"
# A real refusal must still come from the real gate, not from the new one.
expect_refusal "NEG-3 a production deploy is still refused by the policy gate" \
  "$PRE_HOOK" "$FULL" "$DEPLOY" "$SIG_TYPED"
expect_absent_signature "NEG-4 post-tool-use does not refuse a healthy call" \
  "$POST_HOOK" "$FULL" "$POST_PAYLOAD" "$SIG_POST"
run_hook "$POST_HOOK" "$FULL" "$POST_PAYLOAD"
if [ "$RUN_EC" = "0" ]; then
  ok "NEG-5 post-tool-use still exits 0 on a healthy toolchain"
else
  bad "NEG-5 post-tool-use still exits 0 on a healthy toolchain" "exit $RUN_EC: $(printf '%s' "$RUN_ERR" | tr '\n' ' ' | cut -c1-160)"
fi
echo ""

# ===========================================================================
# POST-TOOL-USE — the recorder's own preflight
# ===========================================================================
# It authorizes nothing, but a silently empty audit trail is worse than a
# missing one: the record looks complete, and the spend cap the pre-hook
# enforces is only as good as the ledger this hook feeds.
echo "--- post-tool-use recorder ---"
expect_refusal "POST-jq-absent no jq on PATH" "$POST_HOOK" \
  "$(mkbin post-no-jq jq)" "$POST_PAYLOAD" "$SIG_POST"
expect_refusal "POST-jq-lying  jq exits 0, prints nothing" "$POST_HOOK" \
  "$(shim post-lie-jq jq 'exit 0')" "$POST_PAYLOAD" "$SIG_POST"
expect_refusal "POST-cat       no cat on PATH" "$POST_HOOK" \
  "$(mkbin post-no-cat cat)" "$POST_PAYLOAD" "$SIG_POST"
echo ""

echo "=== Summary ==="
echo "PASS: $PASS"
echo "FAIL: $FAIL"
if [ "$FAIL" -ne 0 ]; then
  echo "STATUS: the enforcement plane does not fail closed on a broken toolchain"
  exit "$FAIL"
fi
echo "STATUS: ALL GREEN"
exit 0
