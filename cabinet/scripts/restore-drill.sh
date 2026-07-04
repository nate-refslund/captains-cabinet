#!/usr/bin/env bash
# restore-drill.sh — prove the Cabinet backups actually restore (lane-ops
# 2026-07-04, companion to cabinet/scripts/backup.sh / the com.cabinet.backup
# LaunchAgent).
#
# WHY THIS EXISTS: a backup nobody has restored is a hope, not a backup (the
# same "process green ≠ outcome true" lesson as the outcome-watchdog — the
# 2026-06-29 briefing ran clean while nothing was delivered). This drill takes
# the NEWEST snapshot under $BACKUP_DEST and performs a full restore into a
# throwaway temp dir, then verifies the restored tree carries the artifacts a
# real disaster recovery would need.
#
# HARD SAFETY CONTRACT (Corridor-reviewed posture, do not weaken):
#   * READ-ONLY against the backup, WRITE-ONLY into a fresh mktemp dir.
#   * NEVER writes to the live repo, ~/Library, Redis, or Postgres. There is
#     deliberately NO "--apply" mode — promoting a restored tree into the live
#     checkout is a human (Captain) action, by design.
#   * Exit 0 = drill PASSED; exit 1 = drill FAILED (missing/thin/corrupt
#     snapshot); exit 2 = usage error. The no-silent-cron watchdog picks up a
#     FAILED line via the "FATAL" marker if this ever runs under launchd.
#
# Usage:
#   bash cabinet/scripts/restore-drill.sh                      # newest snapshot
#   bash cabinet/scripts/restore-drill.sh --date 2026-07-04    # specific day
#   BACKUP_DEST=/Volumes/NAS/cabinet-backups bash cabinet/scripts/restore-drill.sh
#
# Run it after the first scheduled backup lands, and thereafter whenever the
# backup contents change shape (new state dirs, Postgres added, etc.).

set -uo pipefail

BACKUP_DEST="${BACKUP_DEST:-$HOME/Cabinet-Backups}"
WANT_DATE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --date) WANT_DATE="$2"; shift 2 ;;
    --date=*) WANT_DATE="${1#--date=}"; shift ;;
    -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 0 ;;
    *) echo "restore-drill: unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAILS=0
fail() { echo "  ✗ FAIL: $1"; FAILS=$((FAILS + 1)); }
ok()   { echo "  ✓ $1"; }

# ── 1. Pick the snapshot ────────────────────────────────────────────────────
# Snapshot dirs are named YYYY-MM-DD by backup.sh; lexicographic sort == date
# sort, so `sort | tail -1` is the newest. A --date arg pins a specific day.
if [ ! -d "$BACKUP_DEST" ]; then
  echo "restore-drill FATAL: no backup destination at $BACKUP_DEST (has the"
  echo "com.cabinet.backup LaunchAgent ever run? see INSTALL-flip.md)"
  exit 1
fi
if [ -n "$WANT_DATE" ]; then
  SNAP="$BACKUP_DEST/$WANT_DATE"
else
  SNAP=$(find "$BACKUP_DEST" -mindepth 1 -maxdepth 1 -type d -name '20??-??-??' \
         2>/dev/null | sort | tail -1)
fi
if [ -z "${SNAP:-}" ] || [ ! -d "$SNAP" ]; then
  echo "restore-drill FATAL: no snapshot dir found under $BACKUP_DEST"
  exit 1
fi
echo "=== Restore drill: $SNAP ==="

# ── 2. Restore into a throwaway dir ─────────────────────────────────────────
# A real recovery would rsync cabinet-state/ back over the live checkout; the
# drill performs the IDENTICAL copy into a temp dir so the mechanics (perms,
# symlinks, partial writes) are exercised without touching anything live.
RESTORE_DIR=$(mktemp -d /tmp/cabinet-restore-drill.XXXXXX)
trap 'rm -rf "$RESTORE_DIR"' EXIT
if rsync -a "$SNAP/cabinet-state/" "$RESTORE_DIR/cabinet-state/" 2>/dev/null; then
  ok "rsync restore into $RESTORE_DIR/cabinet-state"
else
  fail "rsync restore errored (snapshot unreadable or cabinet-state/ missing)"
fi

# ── 3. Verify the restored tree ─────────────────────────────────────────────
# The three state roots backup.sh snapshots (shared/interfaces, instance,
# memory) land as cabinet-state/{interfaces-and-others}. We assert (a) the
# copy is non-trivial and (b) the recovery-critical artifacts exist — the
# captain triplet + instance config are what a rebuilt Mac needs on day one.
FILE_COUNT=$(find "$RESTORE_DIR/cabinet-state" -type f 2>/dev/null | wc -l | tr -d ' ')
if [ "${FILE_COUNT:-0}" -ge 10 ]; then
  ok "restored file count: $FILE_COUNT (≥10)"
else
  fail "restored tree is thin ($FILE_COUNT files) — snapshot likely incomplete"
fi

# Recovery-critical paths. rsync of "shared/interfaces/" lands its CONTENTS in
# cabinet-state/ root alongside instance/ and memory/ (see backup.sh's rsync
# argument order) — so probe both layouts rather than assuming one.
critical_any() {  # critical_any <label> <path...> — pass if ANY path exists
  local what="$1"; shift
  for p in "$@"; do
    if [ -e "$RESTORE_DIR/$p" ]; then ok "$what present ($p)"; return 0; fi
  done
  fail "$what missing (checked: $*)"
}
critical_any "captain decisions"  "cabinet-state/captain-decisions.md" \
                                  "cabinet-state/interfaces/captain-decisions.md"
critical_any "instance config"    "cabinet-state/instance/config" \
                                  "cabinet-state/config"
critical_any "officer memory"     "cabinet-state/memory" \
                                  "cabinet-state/instance/memory"

# ── 4. Redis dump integrity ─────────────────────────────────────────────────
# redis-check-rdb ships with Homebrew redis; it validates the dump without
# loading it into any server (still zero live-state contact). Absent tool or
# absent dump degrade to a warning-pass: the FS restore is the primary drill,
# and backup.sh already logs when the rdb copy was skipped.
if [ -f "$SNAP/redis-dump.rdb" ]; then
  if command -v redis-check-rdb >/dev/null 2>&1; then
    if redis-check-rdb "$SNAP/redis-dump.rdb" >/dev/null 2>&1; then
      ok "redis-dump.rdb passes redis-check-rdb"
    else
      fail "redis-dump.rdb is corrupt (redis-check-rdb rejected it)"
    fi
  else
    ok "redis-dump.rdb present ($(du -h "$SNAP/redis-dump.rdb" | awk '{print $1}')) — redis-check-rdb not installed, integrity unchecked"
  fi
else
  ok "no redis-dump.rdb in snapshot (backup.sh logged why) — skipping"
fi

# ── 5. Verdict ──────────────────────────────────────────────────────────────
echo ""
if [ "$FAILS" -eq 0 ]; then
  echo "RESTORE DRILL PASSED — $SNAP restores cleanly (drill dir discarded)."
  exit 0
fi
echo "restore-drill FATAL: $FAILS check(s) failed for $SNAP — the backup may"
echo "not survive a real recovery. Fix backup.sh / the snapshot before trusting it."
exit 1
