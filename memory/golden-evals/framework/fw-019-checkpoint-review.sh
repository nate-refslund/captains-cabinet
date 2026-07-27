#!/bin/bash
# FW-019 behavior eval — checkpoint-review pre-commit hook
#
# Contracts from shared/interfaces/retro-proposals.md P-001 + Captain msg 1535,
# as amended by the 2026-07-27 direction gate "Catching EXPANSION":
#   (a) Diff under threshold passes silently (exit 0, no stderr)
#   (b) Diff over threshold without a review artifact → exit 1 + BLOCKED stderr
#   (c) Diff over threshold WITH an artifact BOUND to the staged bytes → exit 0
#   (d) COMMIT_NO_REVIEW=1 bypasses threshold with bypass stderr
#   (e) Merge commits skip enforcement (exit 0)
#
# WHAT CHANGED, AND WHY THE OLD ASSERTIONS ARE INVERTED HERE (2026-07-27):
# arms (c) and (h) used to accept an artifact whose entire content was the
# string "review body" — because the hook matched on FILENAME and never read a
# byte. `touch` passed it; a review copied from another branch passed it; a
# review written before the code it claims to have reviewed passed it. The hook
# now requires the artifact to record the SHA-256 scope digest of what is
# staged, so those two arms are re-pinned to the digest-bearing form and the
# forgeries they used to accept get their OWN arms below — (i) through (q).
# A check that has never been observed REJECTING proves nothing, so every way
# this gate can be forged is exercised as a rejection, not assumed.
#
# Invocation (Mac-native deployment — the /opt/founders-cabinet Docker paths
# are extinct):  bash memory/golden-evals/framework/fw-019-checkpoint-review.sh
# Exit 0 = all pass; non-zero = failure (first failure reported) or
# infra-fail (hook missing — fail-closed so the validation gate goes loudly
# red instead of silently green).
#
# Side-effect-free by construction: the hook is COPIED into a throwaway git
# repo under mktemp -d; nothing outside $TESTDIR is written.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
HOOK="$CABINET_ROOT/cabinet/scripts/git-hooks/pre-commit"
if [ ! -f "$HOOK" ]; then
  echo "FW-019 INFRA-FAIL (gate stays closed): hook under test not found: $HOOK" >&2
  exit 1
fi
TESTDIR=$(mktemp -d -t fw019-XXXXXX)
trap 'rm -rf "$TESTDIR"' EXIT

PASS=0
FAIL=0
FAIL_DETAILS=""

# ---- Set up a throwaway git repo ----
cd "$TESTDIR" || exit 1
git init -q -b master
git config user.email "eval@local"
git config user.name "FW-019 Eval"
# Simulate the framework layout
mkdir -p shared/interfaces/reviews cabinet/scripts/git-hooks
# Copy the real hook so the artifact-path calculation (find by branch slug) works
cp "$HOOK" cabinet/scripts/git-hooks/pre-commit
chmod +x cabinet/scripts/git-hooks/pre-commit
git config core.hooksPath cabinet/scripts/git-hooks
HOOK_LOCAL="cabinet/scripts/git-hooks/pre-commit"

# Initial commit so we have a HEAD to diff against
echo "initial" > README.md
git add README.md
COMMIT_NO_REVIEW=1 git commit -q -m "initial"

run() {
  # usage: run <label> <expect_exit> <stderr_expect_contains> [COMMIT_NO_REVIEW=...]
  local label="$1" expect_exit="$2" stderr_contains="$3"
  shift 3
  local err_file
  err_file=$(mktemp)
  env "$@" bash "$HOOK_LOCAL" 2>"$err_file"
  local got_exit=$?
  local got_stderr
  got_stderr=$(cat "$err_file")
  rm -f "$err_file"

  local ok=1
  if [ "$got_exit" != "$expect_exit" ]; then
    ok=0
    FAIL_DETAILS="$FAIL_DETAILS
  [$label] expected exit=$expect_exit, got=$got_exit; stderr='$got_stderr'"
  fi
  if [ -n "$stderr_contains" ] && ! echo "$got_stderr" | grep -qF "$stderr_contains"; then
    ok=0
    FAIL_DETAILS="$FAIL_DETAILS
  [$label] stderr missing '$stderr_contains'; got: '$got_stderr'"
  fi
  if [ "$stderr_contains" = "" ] && [ -n "$got_stderr" ]; then
    ok=0
    FAIL_DETAILS="$FAIL_DETAILS
  [$label] expected no stderr, got: '$got_stderr'"
  fi
  if [ $ok -eq 1 ]; then
    PASS=$((PASS+1))
    echo "PASS [$label]"
  else
    FAIL=$((FAIL+1))
    echo "FAIL [$label]"
  fi
}

ok_or_fail() {
  # usage: ok_or_fail <label> <0|1 condition result> <detail>
  local label="$1" result="$2" detail="$3"
  if [ "$result" -eq 0 ]; then
    PASS=$((PASS+1)); echo "PASS [$label]"
  else
    FAIL=$((FAIL+1)); echo "FAIL [$label]"
    FAIL_DETAILS="$FAIL_DETAILS
  [$label] $detail"
  fi
}

# Small helper: stage a file with N lines
stage_lines() {
  local lines="$1" name="$2"
  : > "$name"
  for i in $(seq 1 "$lines"); do echo "line $i" >> "$name"; done
  git add "$name"
}

clear_staged() {
  git reset -q
  rm -f a_file.txt b_file.txt c_file.txt d_file.txt e_file.txt
  rm -f shared/interfaces/reviews/master-cp*.md
}

# The digest of whatever is staged right now, straight from the hook's own CLI.
# Using the hook's CLI (rather than reimplementing the hash here) is deliberate:
# the arms below then prove the ACCEPT path and the PRINT path agree, which is
# the property a reviewer actually depends on.
scope_digest() {
  bash "$HOOK_LOCAL" --print-scope-digest 2>/dev/null | awk '{print $2}'
}

bind_artifact() {
  # usage: bind_artifact <artifact-path> [digest]
  local path="$1" digest="${2:-}"
  [ -n "$digest" ] || digest=$(scope_digest)
  printf 'checkpoint review\n\nReviewed-Scope-Digest: %s\n' "$digest" > "$path"
}

# ============================================================
# Test (a) — Under threshold passes silently
# ============================================================
clear_staged
stage_lines 50 a_file.txt
run "a_under_threshold_silent" 0 ""

# ============================================================
# Test (b) — Over threshold without review artifact → blocked
# ============================================================
clear_staged
stage_lines 400 a_file.txt
run "b_over_threshold_blocked" 1 "BLOCKED"

# Also check the block message tells the user how to unblock
clear_staged
stage_lines 400 a_file.txt
err=$(bash "$HOOK_LOCAL" 2>&1 >/dev/null)
if echo "$err" | grep -q "COMMIT_NO_REVIEW=1" \
  && echo "$err" | grep -q "Spawn a reviewer" \
  && echo "$err" | grep -q "Reviewed-Scope-Digest:"; then
  PASS=$((PASS+1)); echo "PASS [b_block_message_actionable]"
else
  FAIL=$((FAIL+1)); echo "FAIL [b_block_message_actionable]: '$err'"
  FAIL_DETAILS="$FAIL_DETAILS
  [b_block_message_actionable] block message missing override hint, reviewer nudge or the digest to record"
fi

# ============================================================
# Test (c) — Over threshold WITH a BOUND review artifact → passes
# (was: any file whose name contained the branch slug, contents unread)
# ============================================================
clear_staged
stage_lines 400 a_file.txt
bind_artifact shared/interfaces/reviews/master-cp1.md
run "c_over_threshold_with_bound_artifact" 0 "checkpoint-review artifact bound"

# ============================================================
# Test (d) — COMMIT_NO_REVIEW=1 bypasses
# ============================================================
clear_staged
stage_lines 400 a_file.txt
run "d_env_override_bypass" 0 "bypassed via COMMIT_NO_REVIEW=1" COMMIT_NO_REVIEW=1

# ============================================================
# Test (e) — Merge commit skips enforcement
# ============================================================
clear_staged
stage_lines 400 a_file.txt
# Simulate merge state (MERGE_HEAD must be a valid ref for git rev-parse --verify)
git rev-parse HEAD > .git/MERGE_HEAD
run "e_merge_commit_skipped" 0 ""
rm -f .git/MERGE_HEAD

# ============================================================
# Test (f) — Real end-to-end commit: small change goes through git commit cleanly
# ============================================================
clear_staged
stage_lines 50 a_file.txt
if git commit -q -m "small real commit" 2>/dev/null; then
  PASS=$((PASS+1)); echo "PASS [f_real_small_commit_succeeds]"
else
  FAIL=$((FAIL+1)); echo "FAIL [f_real_small_commit_succeeds]"
  FAIL_DETAILS="$FAIL_DETAILS
  [f_real_small_commit_succeeds] git commit failed for 50-line diff"
fi

# ============================================================
# Test (g) — Real end-to-end commit: large change without artifact blocked by git
# ============================================================
clear_staged
stage_lines 400 b_file.txt
if git commit -q -m "large no review" 2>/dev/null; then
  FAIL=$((FAIL+1)); echo "FAIL [g_real_large_commit_blocked]"
  FAIL_DETAILS="$FAIL_DETAILS
  [g_real_large_commit_blocked] git commit succeeded for 400-line unreviewed diff (should be blocked)"
  # Undo the accidental commit so later tests stay clean
  git reset --hard HEAD^ -q
else
  PASS=$((PASS+1)); echo "PASS [g_real_large_commit_blocked]"
fi

# ============================================================
# Test (h) — Real end-to-end commit: large change with a BOUND artifact passes
# ============================================================
clear_staged
stage_lines 400 c_file.txt
bind_artifact shared/interfaces/reviews/master-cp2.md
git add -f shared/interfaces/reviews/master-cp2.md
if git commit -q -m "large with review" 2>/dev/null; then
  PASS=$((PASS+1)); echo "PASS [h_real_large_commit_with_bound_artifact_succeeds]"
else
  FAIL=$((FAIL+1)); echo "FAIL [h_real_large_commit_with_bound_artifact_succeeds]"
  FAIL_DETAILS="$FAIL_DETAILS
  [h_real_large_commit_with_bound_artifact_succeeds] git commit blocked despite a bound review artifact"
fi

# ═══════════════════════════════════════════════════════════════════════════
# THE FORGERY ARMS — every one of these PASSED the pre-2026-07-27 hook.
# They are the reason the check was replaced; they must now all BLOCK.
# ═══════════════════════════════════════════════════════════════════════════

# ============================================================
# Test (i) — `touch`ed / empty artifact → blocked
# THE canonical forgery: filename matched, zero bytes read.
# ============================================================
clear_staged
stage_lines 400 a_file.txt
: > shared/interfaces/reviews/master-cp1.md
run "i_touched_empty_artifact_blocked" 1 "carries 0 'Reviewed-Scope-Digest: <64-hex>' line(s)"

# ============================================================
# Test (j) — artifact bound, then the staged set MOVES → blocked
# "a stale one stops satisfying the instant the code moves"
# ============================================================
clear_staged
stage_lines 400 a_file.txt
bind_artifact shared/interfaces/reviews/master-cp1.md
# Sanity: it is genuinely accepted before the move (otherwise (j) would pass
# for the wrong reason — a permanently-red artifact proves nothing).
bash "$HOOK_LOCAL" >/dev/null 2>&1
ok_or_fail "j_precondition_bound_artifact_accepted" $? "artifact was not accepted before the staged set moved"
stage_lines 40 d_file.txt
run "j_stale_after_scope_change_blocked" 1 "staged scope hashes to"

# ============================================================
# Test (k) — artifact copied from a different change → blocked
# Digest recorded for staged set A, presented against staged set B.
# ============================================================
clear_staged
stage_lines 400 a_file.txt
OTHER_DIGEST=$(scope_digest)
clear_staged
stage_lines 400 b_file.txt
bind_artifact shared/interfaces/reviews/master-cp1.md "$OTHER_DIGEST"
run "k_copied_artifact_blocked" 1 "records $OTHER_DIGEST"

# ============================================================
# Test (l) — malformed digest (not 64 lowercase hex) → blocked
# ============================================================
clear_staged
stage_lines 400 a_file.txt
printf 'review\nReviewed-Scope-Digest: deadbeef\n' > shared/interfaces/reviews/master-cp1.md
run "l_malformed_digest_blocked" 1 "carries 0 'Reviewed-Scope-Digest: <64-hex>' line(s)"

# ============================================================
# Test (m) — two digest lines → blocked (exactly one is required, so an
# artifact cannot shotgun every plausible digest)
# ============================================================
clear_staged
stage_lines 400 a_file.txt
GOOD_DIGEST=$(scope_digest)
{
  printf 'review\n'
  printf 'Reviewed-Scope-Digest: %s\n' "$GOOD_DIGEST"
  printf 'Reviewed-Scope-Digest: %064d\n' 0
} > shared/interfaces/reviews/master-cp1.md
run "m_two_digest_lines_blocked" 1 "carries 2 'Reviewed-Scope-Digest: <64-hex>' line(s)"

# ============================================================
# Test (n) — symlinked artifact → blocked, even when the link target carries
# the correct digest (a hostile swap must not be able to point the gate at a
# world-writable scratch file)
# ============================================================
clear_staged
stage_lines 400 a_file.txt
GOOD_DIGEST=$(scope_digest)
SCRATCH_REVIEW=$(mktemp)
printf 'review\nReviewed-Scope-Digest: %s\n' "$GOOD_DIGEST" > "$SCRATCH_REVIEW"
ln -s "$SCRATCH_REVIEW" shared/interfaces/reviews/master-cp1.md
run "n_symlinked_artifact_blocked" 1 "symlink"
rm -f shared/interfaces/reviews/master-cp1.md "$SCRATCH_REVIEW"

# ============================================================
# Test (o) — deletions are inside the digest: a bound artifact stops matching
# once the commit also removes a file. (Hashing only surviving blobs would
# leave a pure-removal commit binding nothing.)
# ============================================================
clear_staged
stage_lines 400 a_file.txt
bind_artifact shared/interfaces/reviews/master-cp1.md
git rm -q --cached README.md
run "o_staged_deletion_moves_digest" 1 "staged scope hashes to"
git reset -q -- README.md

# ============================================================
# Test (p) — the artifact is excluded from its own digest: editing the review
# body (keeping the digest line) must NOT invalidate it, or the binding would
# be unsatisfiable by construction.
# ============================================================
clear_staged
stage_lines 400 a_file.txt
bind_artifact shared/interfaces/reviews/master-cp1.md
{
  cat shared/interfaces/reviews/master-cp1.md
  printf '\nAdditional reviewer prose added after the digest was computed.\n'
} > shared/interfaces/reviews/master-cp1.md.tmp
mv shared/interfaces/reviews/master-cp1.md.tmp shared/interfaces/reviews/master-cp1.md
git add -f shared/interfaces/reviews/master-cp1.md
run "p_artifact_excluded_from_own_digest" 0 "checkpoint-review artifact bound"

# ============================================================
# Test (q) — degenerate scope: over threshold but everything staged is inside
# the review plane. Hashing an empty record set would yield a CONSTANT any
# artifact could record, so this must block rather than accept.
# ============================================================
clear_staged
: > shared/interfaces/reviews/master-cp1.md
for i in $(seq 1 400); do echo "review line $i" >> shared/interfaces/reviews/master-cp1.md; done
git add -f shared/interfaces/reviews/master-cp1.md
run "q_only_review_plane_staged_blocked" 1 "no reviewable bytes"

# ============================================================
# Test (r) — the CLI a reviewer actually uses: --print-scope-digest emits one
# 64-hex digest line, and refuses when there is nothing to bind.
# ============================================================
clear_staged
stage_lines 400 a_file.txt
CLI_OUT=$(bash "$HOOK_LOCAL" --print-scope-digest 2>/dev/null)
echo "$CLI_OUT" | grep -qE '^Reviewed-Scope-Digest: [0-9a-f]{64}$'
ok_or_fail "r_print_digest_shape" $? "expected one 'Reviewed-Scope-Digest: <64-hex>' line, got: '$CLI_OUT'"
clear_staged
bash "$HOOK_LOCAL" --print-scope-digest >/dev/null 2>&1
CLI_RC=$?
[ "$CLI_RC" -eq 1 ]
ok_or_fail "r_print_digest_refuses_empty_scope" $? "expected exit 1 with nothing staged, got $CLI_RC"

# ============================================================
# Summary
# ============================================================
clear_staged
echo ""
echo "======================================================"
echo "FW-019 golden eval: $PASS passed, $FAIL failed"
echo "======================================================"
if [ "$FAIL" -gt 0 ]; then
  echo -e "Failures:$FAIL_DETAILS"
  exit 1
fi
exit 0
