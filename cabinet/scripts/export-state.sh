#!/bin/bash
# export-state.sh — Export Hetzner-host Cabinet state for Mac mini migration.
#
# Captures everything that isn't in git or in the cloud (Neon):
#   - cabinet/.env (API keys, Telegram tokens, Neon connection string)
#   - /etc/cabinet/* (host-agent secrets)
#   - /var/log/cabinet/* (audit logs — host-agent + cos-actions, optional)
#   - /etc/systemd/system/cabinet-*.service (reference for launchd port)
#   - /etc/cron.d/cabinet-* + /var/spool/cron/crontabs/* (cron entries)
#   - Per-officer Claude Code auth state (~/.claude/ inside each officer container, optional)
#   - Redis dump (optional — Redis state is mostly ephemeral)
#
# Output: a single tar.gz at the output path you specify, plus a manifest text file.
#
# Usage:
#   bash cabinet/scripts/export-state.sh /tmp/cabinet-export.tar.gz \
#     [--include-claude-auth] \
#     [--include-redis-dump] \
#     [--include-logs] \
#     [--dry-run]
#
# Run as a user with sudo access (the /etc/cabinet/ + /var/log/cabinet/ paths
# are root-owned). Script will sudo as needed.
#
# Captain ratified pre-Mac-migration export script (msg 2599 → 2601).

set -euo pipefail

# ============================================================
# Args
# ============================================================
OUTPUT="${1:-}"
shift || true

INCLUDE_CLAUDE_AUTH=false
INCLUDE_REDIS_DUMP=false
INCLUDE_LOGS=true   # default ON — small but useful for continuity
DRY_RUN=false

while [ $# -gt 0 ]; do
  case "$1" in
    --include-claude-auth)  INCLUDE_CLAUDE_AUTH=true ;;
    --include-redis-dump)   INCLUDE_REDIS_DUMP=true ;;
    --no-logs)              INCLUDE_LOGS=false ;;
    --dry-run)              DRY_RUN=true ;;
    *)
      echo "ERROR: unknown flag '$1'" >&2
      exit 64
      ;;
  esac
  shift
done

if [ -z "$OUTPUT" ]; then
  echo "Usage: bash cabinet/scripts/export-state.sh <output.tar.gz> [--include-claude-auth] [--include-redis-dump] [--no-logs] [--dry-run]" >&2
  exit 64
fi

case "$OUTPUT" in
  *.tar.gz|*.tgz) ;;
  *) echo "ERROR: output must end in .tar.gz or .tgz (got: $OUTPUT)" >&2; exit 64 ;;
esac

# ============================================================
# Setup
# ============================================================
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STAGE="$(mktemp -d -t cabinet-export.XXXXXX)"
trap 'rm -rf "$STAGE"' EXIT

MANIFEST="$STAGE/MANIFEST.txt"
{
  echo "Cabinet state export"
  echo "===================="
  echo "Source host:   $(hostname)"
  echo "Source repo:   $REPO_ROOT"
  echo "Export date:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Git HEAD:      $(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo 'unknown')"
  echo "Git branch:    $(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"
  echo ""
  echo "Flags:"
  echo "  --include-claude-auth = $INCLUDE_CLAUDE_AUTH"
  echo "  --include-redis-dump  = $INCLUDE_REDIS_DUMP"
  echo "  --include-logs        = $INCLUDE_LOGS"
  echo "  --dry-run             = $DRY_RUN"
  echo ""
  echo "What's in this tarball:"
} > "$MANIFEST"

stage_copy() {
  # stage_copy <label> <src> <dest-relative-to-stage>
  local label="$1" src="$2" rel="$3"
  if [ ! -e "$src" ]; then
    echo "  $label: SKIPPED (source missing: $src)" >> "$MANIFEST"
    return 0
  fi
  if $DRY_RUN; then
    echo "  $label: WOULD-COPY $src → $rel" >> "$MANIFEST"
    return 0
  fi
  mkdir -p "$STAGE/$(dirname "$rel")"
  if [ -d "$src" ]; then
    sudo cp -a "$src" "$STAGE/$rel"
  else
    sudo cp -a "$src" "$STAGE/$rel"
  fi
  sudo chown -R "$(id -u):$(id -g)" "$STAGE/$rel" 2>/dev/null || true
  echo "  $label: OK ($src → $rel)" >> "$MANIFEST"
}

# ============================================================
# 1. cabinet/.env — the single most important file
# ============================================================
stage_copy "cabinet/.env" "$REPO_ROOT/cabinet/.env" "cabinet/.env"

# ============================================================
# 2. Host-agent secrets at /etc/cabinet/
# ============================================================
stage_copy "/etc/cabinet/" "/etc/cabinet" "etc/cabinet"

# ============================================================
# 3. Audit logs at /var/log/cabinet/ (optional, default ON)
# ============================================================
if $INCLUDE_LOGS; then
  stage_copy "/var/log/cabinet/" "/var/log/cabinet" "var/log/cabinet"
else
  echo "  /var/log/cabinet/: SKIPPED (--no-logs)" >> "$MANIFEST"
fi

# ============================================================
# 3b. Captain-rules runtime state (gitignored — regenerates blank on bootstrap)
# ============================================================
# These 3 files accumulate behavioral knowledge during officer sessions via
# captain-rule-encoder.sh + per-officer encoding from the 4th + 5th improvement
# loops. They are gitignored — without explicit export here, the Mac cutover
# regenerates them blank from cabinet-bootstrap.sh. (Cross-fold per Spec 057 v1.1
# amendment on mac-native; replicated here so Hetzner-side Phase 0 export
# from master picks them up too.)
for crf in captain-patterns.md captain-intents.md captain-decisions.md; do
  stage_copy "shared/interfaces/$crf" "$REPO_ROOT/shared/interfaces/$crf" "shared/interfaces/$crf"
done

# ============================================================
# 4. systemd units — reference only, launchd port lives elsewhere
# ============================================================
for unit in /etc/systemd/system/cabinet-*.service; do
  [ -e "$unit" ] || continue
  stage_copy "systemd unit $(basename "$unit")" "$unit" "etc/systemd/system/$(basename "$unit")"
done

# ============================================================
# 5. cron entries — reference only for launchd plist port
# ============================================================
for cron in /etc/cron.d/cabinet-*; do
  [ -e "$cron" ] || continue
  stage_copy "cron $(basename "$cron")" "$cron" "etc/cron.d/$(basename "$cron")"
done

# Also capture any user crontabs (per feedback_cron_cutover_dual_location memory)
if sudo test -d /var/spool/cron/crontabs; then
  mkdir -p "$STAGE/var/spool/cron"
  if ! $DRY_RUN; then
    sudo cp -a /var/spool/cron/crontabs "$STAGE/var/spool/cron/crontabs" 2>/dev/null || true
    sudo chown -R "$(id -u):$(id -g)" "$STAGE/var/spool/cron/crontabs" 2>/dev/null || true
  fi
  echo "  /var/spool/cron/crontabs/: OK" >> "$MANIFEST"
fi

# ============================================================
# 6. Per-officer Claude auth (optional — saves re-OAuth pain on Mac)
# ============================================================
if $INCLUDE_CLAUDE_AUTH; then
  echo "" >> "$MANIFEST"
  echo "Officer Claude auth (~/.claude/ per officer container):" >> "$MANIFEST"
  mkdir -p "$STAGE/officer-claude-auth"

  # Discover officer containers
  if command -v docker >/dev/null 2>&1; then
    OFFICERS=$(docker ps --filter "name=cabinet-officers" --format "{{.Names}}" 2>/dev/null || true)
  else
    OFFICERS=""
  fi

  if [ -z "$OFFICERS" ]; then
    # Fallback: standard roster
    OFFICERS="cabinet-officers"
  fi

  for container in $OFFICERS; do
    if $DRY_RUN; then
      echo "  $container: WOULD-COPY /home/cabinet/.claude → officer-claude-auth/$container" >> "$MANIFEST"
      continue
    fi
    if docker exec "$container" test -d /home/cabinet/.claude 2>/dev/null; then
      docker cp "$container:/home/cabinet/.claude" "$STAGE/officer-claude-auth/$container" 2>/dev/null || {
        echo "  $container: FAILED to copy ~/.claude" >> "$MANIFEST"
        continue
      }
      echo "  $container: OK" >> "$MANIFEST"
    else
      echo "  $container: SKIPPED (~/.claude not present)" >> "$MANIFEST"
    fi
  done
fi

# ============================================================
# 7. Redis dump (optional — mostly ephemeral, but useful for trigger history)
# ============================================================
if $INCLUDE_REDIS_DUMP; then
  if $DRY_RUN; then
    echo "  redis dump: WOULD-CAPTURE via 'redis-cli --rdb'" >> "$MANIFEST"
  else
    if command -v docker >/dev/null 2>&1 && docker ps --format "{{.Names}}" | grep -q "^cabinet-redis$"; then
      docker exec cabinet-redis redis-cli SAVE >/dev/null 2>&1 || true
      docker cp cabinet-redis:/data/dump.rdb "$STAGE/redis-dump.rdb" 2>/dev/null && \
        echo "  redis dump: OK ($STAGE/redis-dump.rdb)" >> "$MANIFEST" || \
        echo "  redis dump: FAILED (cabinet-redis container or dump.rdb missing)" >> "$MANIFEST"
    elif command -v redis-cli >/dev/null 2>&1; then
      redis-cli --rdb "$STAGE/redis-dump.rdb" 2>/dev/null && \
        echo "  redis dump: OK (native redis-cli)" >> "$MANIFEST" || \
        echo "  redis dump: FAILED (redis-cli native fallback)" >> "$MANIFEST"
    else
      echo "  redis dump: FAILED (no docker, no redis-cli)" >> "$MANIFEST"
    fi
  fi
fi

# ============================================================
# 8. instance/config/ snapshot (already in git but explicit copy useful)
# ============================================================
stage_copy "instance/config/" "$REPO_ROOT/instance/config" "instance-config-snapshot"

# ============================================================
# Wrap-up
# ============================================================
{
  echo ""
  echo "Mac side restore guide:"
  echo "  1. Extract tarball into a working directory:"
  echo "     mkdir ~/cabinet-import && cd ~/cabinet-import && tar xzf $(basename "$OUTPUT")"
  echo "  2. Place cabinet/.env into the fresh-cloned repo:"
  echo "     cp ~/cabinet-import/cabinet/.env <repo>/cabinet/.env"
  echo "  3. /etc/cabinet/ contents → /usr/local/etc/cabinet/ on macOS (macOS-conventional path)."
  echo "  4. systemd units + cron entries: REFERENCE ONLY — port to launchd plists per Phase 2 directive."
  echo "  5. Per-officer claude-auth (if included): docker cp each back into officer-claude-auth volumes."
  echo "  6. Redis dump (if included): mount as cabinet-redis volume initial state."
  echo "  7. Run cabinet-bootstrap.sh with --preset work to bring up native-Mac Cabinet."
} >> "$MANIFEST"

echo ""
echo "=== Manifest ==="
cat "$MANIFEST"
echo ""

if $DRY_RUN; then
  echo "DRY-RUN complete. Re-run without --dry-run to write tarball."
  exit 0
fi

# ============================================================
# Final tar
# ============================================================
echo "Writing tarball: $OUTPUT"
mkdir -p "$(dirname "$OUTPUT")"
tar czf "$OUTPUT" -C "$STAGE" .
echo "Done. Tarball: $OUTPUT ($(du -h "$OUTPUT" | cut -f1))"
echo "Manifest also embedded inside: tar tzf $OUTPUT | head -5"
