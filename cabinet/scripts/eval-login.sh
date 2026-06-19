#!/usr/bin/env bash
# eval-login.sh — establish + validate a CLEAN, leak-free HOME for the fidelity
# eval judge.
#
# Why: the eval `claude -p` (framework/fidelity/oauth_llm.py) reads
# CABINET_EVAL_HOME and runs from a clean temp cwd, so it auto-discovers NO
# personal ~/.claude/CLAUDE.md, ~/.claude.json, .remember, or screenpipe-
# memories. The clean-cwd fix already closed the PROJECT/.remember leak; a clean
# HOME closes the USER-GLOBAL leak. Together = graduation-grade leak-clean
# fidelity numbers. (See task #5; design §"Evidence check".)
#
# Usage:
#   bash cabinet/scripts/eval-login.sh
# If it reports "not authenticated", run ONCE (your dedicated clone account):
#   HOME="$HOME/.cabinet-eval-home" claude login
# then re-run this script. On success, export the printed CABINET_EVAL_HOME.
set -u

CLEAN="${CABINET_EVAL_HOME:-$HOME/.cabinet-eval-home}"
mkdir -p "$CLEAN/.claude"
echo "Clean eval HOME: $CLEAN"
echo "  (contains NO CLAUDE.md / screenpipe-memories — that is the point.)"
echo ""

# 1. Auth check — does the dedicated account authenticate from this HOME?
OUT="$(HOME="$CLEAN" claude -p "Reply with exactly: AUTH_OK" --output-format text </dev/null 2>&1)"
if printf '%s' "$OUT" | grep -qi "AUTH_OK"; then
  echo "[1/2] auth: OK — authenticated in the clean HOME"
elif printf '%s' "$OUT" | grep -qiE "not logged in|/login|configuration file not found"; then
  echo "[1/2] auth: NOT AUTHENTICATED in the clean HOME."
  echo "      Run ONCE (use your dedicated clone Max account):"
  echo ""
  echo "          HOME=\"$CLEAN\" claude login"
  echo ""
  echo "      then re-run this script. (This creates $CLEAN/.claude.json +"
  echo "      a clean session; the credential itself lives in the keychain.)"
  exit 1
else
  echo "[1/2] auth: UNEXPECTED output — inspect manually:"
  printf '   %s\n' "$OUT"
  exit 1
fi

# 2. Leak check — the clean HOME must NOT surface personal/user-global context.
LEAK="$(cd /tmp && HOME="$CLEAN" claude -p "In one sentence, what is PolAds? If not known from available context, reply exactly UNKNOWN." --output-format text </dev/null 2>&1)"
if printf '%s' "$LEAK" | grep -qiE '\bUNKNOWN\b' && ! printf '%s' "$LEAK" | grep -qiE 'political|transparency|advertis'; then
  echo "[2/2] leak: CLEAN — no personal/user-global context bleeds in"
else
  echo "[2/2] leak: ⚠️  the clean HOME STILL surfaces personal context."
  echo "      Check for a CLAUDE.md / screenpipe-memories.md under $CLEAN/.claude/"
  echo "      and remove it; the eval must run leak-free. Got:"
  printf '   %s\n' "$LEAK"
  exit 1
fi

echo ""
echo "DONE — clean eval HOME validated. Point the harness at it:"
echo ""
echo "    export CABINET_EVAL_HOME=\"$CLEAN\""
echo ""
echo "(add to your shell profile, or prefix the eval run). The fidelity eval"
echo "judge will then run leak-free: clean cwd (project/.remember) + clean HOME"
echo "(user-global). Combined with the pi-agent gather-query fix + F2, this"
echo "yields the first graduation-grade fidelity numbers."
