#!/usr/bin/env bash
# cache-hash.sh — Spec 049 AC #14 action-cache invalidation hash.
# Sourced by the Gate-4 stagehand-runner. Computes a deterministic SHA256 over the
# inputs that should invalidate the Stagehand action-cache; the runner stores it as
# gate4BuildHash at loop START and re-checks at loop END (MF-4 build-atomic).
#
# Modes (visual_uat.cache_invalidation_source in .cabinet/agent-instructions.md):
#   nextjs   (default) — lockfile hash + cache_invalidation_paths subtree mtimes.
#                        .next/build-manifest.json is EXCLUDED (MF-2, highest-leverage
#                        fold): a preview redeploy rewrites it byte-differently with no
#                        source change → would invalidate by construction + drive the
#                        recovery livelock (JF-1). Source-mtime + lockfile are precise.
#   git-deps           — lockfile hash + cache_invalidation_paths mtimes. git HEAD is
#                        deliberately NOT included (a commit with no dep/code change
#                        would needlessly shrink the cross-commit replay window).
#   custom             — project ships .cabinet/cache-hash.sh; must exit 0 with a
#                        deterministic hash on stdout.
#
# The mode is prepended to the hash basis so two modes NEVER collide on identical
# inputs (AC #14 "consistent cache-key namespacing, no cross-mode collision").
#
# Portable across GNU + BSD/macOS (stat, sha) per the Mac-native arc. No hardcoded
# paths. Target <100ms typical (custom mode budget +200ms).
#
# Usage: cache_hash_compute <mode> <project_root> [invalidation_path ...]  → SHA256 hex

# mtime epoch of a file: GNU stat, then BSD/macOS stat, then 0.
_ch_mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0; }

# SHA256 hex of stdin: coreutils sha256sum, else BSD/macOS shasum.
_ch_sha() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print $1}'
  else shasum -a 256 | awk '{print $1}'; fi
}

# First recognised lockfile under the project root → "lock:<name>:<sha>"; else "lock:none".
_ch_lockfile_hash() {
  local root="$1" lf
  for lf in pnpm-lock.yaml package-lock.json yarn.lock Cargo.lock poetry.lock; do
    if [ -f "$root/$lf" ]; then echo "lock:$lf:$(_ch_sha < "$root/$lf")"; return 0; fi
  done
  echo "lock:none"
}

cache_hash_compute() {
  local mode="${1:-}" root="${2:-}"
  [ -n "$mode" ] && [ -n "$root" ] || { echo "cache_hash_compute: need <mode> <project_root>" >&2; return 2; }
  shift 2
  local paths=("$@")

  case "$mode" in
    custom)
      local cs="$root/.cabinet/cache-hash.sh"
      [ -f "$cs" ] || { echo "cache_hash_compute: custom mode but no $cs" >&2; return 2; }
      bash "$cs"; return $? ;;
    nextjs|git-deps) ;;
    *) echo "cache_hash_compute: unknown mode: $mode" >&2; return 2 ;;
  esac

  {
    echo "mode:$mode"                     # namespacing → no cross-mode collision (AC #14)
    _ch_lockfile_hash "$root"
    local p f
    for p in "${paths[@]}"; do
      [ -n "$p" ] || continue
      [ -e "$root/$p" ] || continue
      # Enumerate files under the path, EXCLUDING the volatile Next.js build manifest
      # (MF-2). Emit "<mtime> <path>" per file; the outer sort makes order deterministic.
      find "$root/$p" -type f ! -path '*/.next/build-manifest.json' -print 2>/dev/null \
        | while IFS= read -r f; do printf '%s %s\n' "$(_ch_mtime "$f")" "$f"; done
    done
  } | LC_ALL=C sort | _ch_sha
}
