#!/usr/bin/env bash
# backup.sh — Daily Cabinet state backup for Mac-native deployments.
#
# Phase 9 of the convergence plan. Backs up the three places Cabinet state
# lives:
#   1. Filesystem (captain triplet, role entities, evolved skills, experience
#      records, mission proposals — the durable runtime artifacts that aren't
#      git-tracked).
#   2. Redis snapshot (via BGSAVE — async, non-blocking).
#   3. Optional Postgres pg_dump (only if --pg is set + DATABASE_URL is set).
#
# Each daily run goes into $BACKUP_DEST/<YYYY-MM-DD>/. Default destination is
# ~/Cabinet-Backups; override via BACKUP_DEST env var or --dest flag. Old
# backups beyond the retention window are pruned.
#
# Schedule via cron or launchd. Example launchd snippet:
#   <key>StartCalendarInterval</key>
#   <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>0</integer></dict>
#
# Usage:
#   bash cabinet/scripts/backup.sh                       # default location, no Postgres
#   bash cabinet/scripts/backup.sh --dest /Volumes/NAS/cabinet-backups
#   bash cabinet/scripts/backup.sh --pg                  # also pg_dump the DATABASE_URL
#   bash cabinet/scripts/backup.sh --retention-days 30   # prune older backups
#
# Idempotent within a day — re-running overwrites today's snapshot.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Bug fix (R5): script lives at cabinet/scripts/, so repo root is two levels up.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

BACKUP_DEST="${BACKUP_DEST:-$HOME/Cabinet-Backups}"
RETENTION_DAYS=14
INCLUDE_PG=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dest) BACKUP_DEST="$2"; shift 2 ;;
    --dest=*) BACKUP_DEST="${1#--dest=}"; shift ;;
    --retention-days) RETENTION_DAYS="$2"; shift 2 ;;
    --pg) INCLUDE_PG=1; shift ;;
    -h|--help)
      sed -n '1,28p' "$0" | sed 's/^# \{0,1\}//' >&2
      exit 0
      ;;
    *) echo "backup.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

DATE=$(date +%Y-%m-%d)
DEST_DIR="$BACKUP_DEST/$DATE"
mkdir -p "$DEST_DIR"

echo "=== Cabinet backup → $DEST_DIR ==="

# --- 1. Filesystem (Cabinet runtime artifacts) ---
echo "[1/3] Filesystem rsync..."
rsync -a --delete \
  --exclude='*.pyc' --exclude='__pycache__' \
  --exclude='.session-state.json' \
  "$CABINET_ROOT/shared/interfaces/" \
  "$CABINET_ROOT/instance/" \
  "$CABINET_ROOT/memory/" \
  "$DEST_DIR/cabinet-state/"
FS_FILES=$(find "$DEST_DIR/cabinet-state" -type f 2>/dev/null | wc -l | tr -d ' ')
FS_SIZE=$(du -sh "$DEST_DIR/cabinet-state" 2>/dev/null | awk '{print $1}')
echo "  → $FS_FILES files, $FS_SIZE"

# --- 2. Redis snapshot (BGSAVE then copy the dump.rdb) ---
echo "[2/3] Redis snapshot..."
if command -v redis-cli >/dev/null 2>&1 && redis-cli ping >/dev/null 2>&1; then
  redis-cli BGSAVE > /dev/null 2>&1 || true
  # Wait briefly for BGSAVE to complete
  for _ in 1 2 3 4 5; do
    if redis-cli LASTSAVE 2>/dev/null > /dev/null; then
      break
    fi
    sleep 1
  done
  # Find the dump.rdb (Homebrew default vs Linux default)
  for rdb in /opt/homebrew/var/db/redis/dump.rdb /var/lib/redis/dump.rdb; do
    if [ -f "$rdb" ]; then
      cp "$rdb" "$DEST_DIR/redis-dump.rdb"
      RDB_SIZE=$(du -h "$DEST_DIR/redis-dump.rdb" | awk '{print $1}')
      echo "  → $rdb ($RDB_SIZE)"
      break
    fi
  done
  if [ ! -f "$DEST_DIR/redis-dump.rdb" ]; then
    echo "  → WARN: redis dump.rdb not found at known paths; skipping"
  fi
else
  echo "  → SKIP: redis not running"
fi

# --- 3. Postgres pg_dump (optional) ---
if [ "$INCLUDE_PG" -eq 1 ]; then
  echo "[3/3] Postgres pg_dump..."
  if [ -z "${DATABASE_URL:-}" ]; then
    echo "  → SKIP: DATABASE_URL not set"
  elif ! command -v pg_dump >/dev/null 2>&1; then
    echo "  → SKIP: pg_dump not installed (brew install libpq && brew link --force libpq)"
  else
    pg_dump "$DATABASE_URL" 2>/dev/null | gzip > "$DEST_DIR/postgres.sql.gz" || true
    if [ -s "$DEST_DIR/postgres.sql.gz" ]; then
      PG_SIZE=$(du -h "$DEST_DIR/postgres.sql.gz" | awk '{print $1}')
      echo "  → postgres.sql.gz ($PG_SIZE)"
    else
      echo "  → WARN: pg_dump failed or empty"
      rm -f "$DEST_DIR/postgres.sql.gz"
    fi
  fi
else
  echo "[3/3] Postgres: skipped (--pg not set)"
fi

# --- Prune older backups beyond retention ---
echo ""
echo "Pruning backups older than $RETENTION_DAYS days..."
if [ -d "$BACKUP_DEST" ]; then
  find "$BACKUP_DEST" -mindepth 1 -maxdepth 1 -type d \
       -mtime "+$RETENTION_DAYS" -exec rm -rf {} \; 2>/dev/null || true
fi

TOTAL_KEPT=$(find "$BACKUP_DEST" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
TOTAL_SIZE=$(du -sh "$BACKUP_DEST" 2>/dev/null | awk '{print $1}')
echo "Backup complete. Retained $TOTAL_KEPT daily snapshot(s), total $TOTAL_SIZE in $BACKUP_DEST."
