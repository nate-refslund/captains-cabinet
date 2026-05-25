#!/usr/bin/env bash
# cabinet/tests/test-ff-pull-main.sh — #192 FF-pull backstop safety harness.
#
# Verifies the safety-critical behaviors of cabinet/cron/ff-pull-main.sh using hermetic git
# fixtures (bare remote + local clone), since the script writes to the SHARED /opt checkout and a
# bug would affect every officer. The headline test (#2) pins the tracked-only clean-gate gotcha:
# untracked cruft (.claude/worktrees/, spawned-cabinets/) must NOT block the ff — a porcelain gate
# would have falsely aborted. Run: bash cabinet/tests/test-ff-pull-main.sh
set -u

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../cron" && pwd)/ff-pull-main.sh"
BR="mac-native"
PASS=0; FAIL=0
pass() { PASS=$((PASS + 1)); }
fail() { FAIL=$((FAIL + 1)); printf '  FAIL: %s\n' "$1"; }
assert_eq() { if [ "$2" = "$3" ]; then pass; else fail "$1: got [$2] want [$3]"; fi; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# Fresh bare remote + seed (pushes to it) + local clone on $BR at c1.
setup() {
  rm -rf "$TMP/remote" "$TMP/seed" "$TMP/local" "$TMP/lock"
  git init -q --bare "$TMP/remote"
  git init -q "$TMP/seed"
  ( cd "$TMP/seed"
    git config user.email t@t; git config user.name t
    git checkout -q -b "$BR"
    echo v1 > f.txt; git add f.txt; git commit -qm c1
    git remote add origin "$TMP/remote"; git push -q -u origin "$BR" )
  git -C "$TMP/remote" symbolic-ref HEAD "refs/heads/$BR" 2>/dev/null   # silence clone's default-HEAD warning
  git clone -q "$TMP/remote" "$TMP/local"
  ( cd "$TMP/local"; git config user.email t@t; git config user.name t; git checkout -q "$BR" )
}
advance_remote() { ( cd "$TMP/seed"; echo v2 >> f.txt; git commit -qam c2; git push -q origin "$BR" ); }
run()         { CABINET_REPO="$TMP/local" CABINET_MAIN_BRANCH="$BR" FF_PULL_LOG="$TMP/log" FF_PULL_LOCK="$TMP/lock" bash "$SCRIPT"; }
head_of()     { git -C "$1" rev-parse HEAD; }
remote_head() { git -C "$TMP/seed" rev-parse HEAD; }

# parse-clean
bash -n "$SCRIPT" && pass || fail "ff-pull-main.sh: bash -n syntax"

# 1. clean + behind -> fast-forwards
setup; advance_remote; run
assert_eq "clean+behind fast-forwards" "$(head_of "$TMP/local")" "$(remote_head)"

# 2. untracked-only (THE #192 gotcha) -> STILL fast-forwards (tracked-only gate, not porcelain)
setup; advance_remote
mkdir -p "$TMP/local/.claude/worktrees" "$TMP/local/spawned-cabinets"; echo x > "$TMP/local/untracked.tmp"
run
assert_eq "untracked-only still ff (tracked-only gate)" "$(head_of "$TMP/local")" "$(remote_head)"

# 3. dirty tracked (unstaged) -> skip (no clobber)
setup; advance_remote; before="$(head_of "$TMP/local")"; echo dirty >> "$TMP/local/f.txt"; run
assert_eq "dirty-unstaged skips" "$(head_of "$TMP/local")" "$before"

# 4. dirty tracked (staged) -> skip
setup; advance_remote; before="$(head_of "$TMP/local")"
echo dirty >> "$TMP/local/f.txt"; git -C "$TMP/local" add f.txt; run
assert_eq "dirty-staged skips" "$(head_of "$TMP/local")" "$before"

# 5. diverged -> skip (local commit preserved, never force-resolved)
setup; advance_remote
( cd "$TMP/local"; echo local-only > g.txt; git add g.txt; git commit -qm local-divergent )
before="$(head_of "$TMP/local")"; run
assert_eq "diverged skips (local preserved)" "$(head_of "$TMP/local")" "$before"

# 6. wrong branch -> skip (do not pull main onto another checkout)
setup; advance_remote; ( cd "$TMP/local"; git checkout -q -b feature ); before="$(head_of "$TMP/local")"; run
assert_eq "wrong-branch skips" "$(head_of "$TMP/local")" "$before"

# 7. up-to-date -> no-op, exit 0
setup; run; rc=$?
assert_eq "up-to-date exit 0" "$rc" "0"
assert_eq "up-to-date no change" "$(head_of "$TMP/local")" "$(remote_head)"

printf '\n════════════════════════════════════\n  PASS: %d   FAIL: %d   TOTAL: %d\n════════════════════════════════════\n' "$PASS" "$FAIL" "$((PASS + FAIL))"
[ "$FAIL" -eq 0 ]
