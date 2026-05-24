#!/usr/bin/env bash
# rotate-llm-key.sh — Spec 051 AC #10 cabinet-side LLM proxy key rotation.
# Replaces LLM_PROXY_KEY=<old-value> in the target .env file with the new key
# passed as an argument. All other lines are preserved unchanged.
#
# WHY CABINET-SIDE ONLY: the key revocation and new-key mint happen SERVER-SIDE
# (LiteLLM proxy admin API, called by refslund.ai backend). This script handles
# the CABINET side: installing the newly minted key into the cabinet's .env so
# officer sessions can use it without a restart. The 24h overlap grace period
# (old key remains valid server-side for 24h) is documented below; enforcement
# is entirely proxy-side.
#
# Rotation triggers (Spec 051 AC #10):
#   (a) Customer-initiated via refslund.ai dashboard
#   (b) Security incident (compromised key detected in proxy audit log)
#   (c) Mandatory annual rotation
#
# Usage:
#   rotate-llm-key.sh <new-key> [<env-file>]
#
#   <new-key>   — the new LLM_PROXY_KEY value (sk-... virtual key from proxy)
#   <env-file>  — path to the .env file to update
#                 (default: ${CABINET_ROOT}/cabinet/.env)
#
# Atomic: writes to a temp file in the same directory, then renames.
# Idempotent: running again with the same key is a no-op net-change (replaces).
# Fail-safe: exits nonzero with a message if the file is unreadable or the
#             write fails; never truncates the .env silently.

set -euo pipefail

CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"
DEFAULT_ENV="${CABINET_ROOT}/cabinet/.env"

usage() {
  echo "Usage: rotate-llm-key.sh <new-key> [<env-file>]" >&2
  echo "  Replaces LLM_PROXY_KEY in <env-file> (default: $DEFAULT_ENV)" >&2
  exit 2
}

[ "${1:-}" = "--help" ] && usage
[ -z "${1:-}" ] && usage

NEW_KEY="$1"
ENV_FILE="${2:-$DEFAULT_ENV}"

# Basic key format guard — proxy keys start with sk-
case "$NEW_KEY" in
  sk-*) : ;;  # valid prefix
  *)
    echo "ERROR: new key does not look like a proxy virtual key (expected sk-...)" >&2
    exit 1
    ;;
esac

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  exit 1
fi
if [ ! -r "$ENV_FILE" ]; then
  echo "ERROR: env file not readable: $ENV_FILE" >&2
  exit 1
fi

# Atomic replacement: write to a sibling temp file, then mv into place.
# This ensures no partial write is visible even if the process is killed mid-write.
TMP_FILE="$(mktemp "${ENV_FILE}.rotllm.XXXXXX")"
trap 'rm -f "$TMP_FILE"' EXIT

# Replace or append LLM_PROXY_KEY line.
# The sed expression matches optional surrounding whitespace and any quoting style.
#   LLM_PROXY_KEY=value
#   LLM_PROXY_KEY = value
#   LLM_PROXY_KEY="value"
#   LLM_PROXY_KEY='value'
FOUND=0
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    LLM_PROXY_KEY*=*)
      # Replace this line with the new key (unquoted — matches Claude Code .env convention)
      printf 'LLM_PROXY_KEY=%s\n' "$NEW_KEY"
      FOUND=1
      ;;
    *)
      printf '%s\n' "$line"
      ;;
  esac
done < "$ENV_FILE" > "$TMP_FILE"

# If LLM_PROXY_KEY was not already present, append it
if [ "$FOUND" = "0" ]; then
  printf 'LLM_PROXY_KEY=%s\n' "$NEW_KEY" >> "$TMP_FILE"
fi

# Preserve original permissions on the target file.
# GNU chmod --reference is unavailable on macOS (mac-native arc); use stat instead.
# stat -c (GNU) vs stat -f (BSD/macOS) — try both, fall back to 600.
_orig_mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null \
              || stat -f '%A' "$ENV_FILE" 2>/dev/null \
              || echo 600)"
chmod "$_orig_mode" "$TMP_FILE" 2>/dev/null || true

# Atomic rename into place
mv "$TMP_FILE" "$ENV_FILE"
trap '' EXIT  # clear the trap — temp file is now the live env file

echo "LLM_PROXY_KEY rotated in $ENV_FILE"
echo "NOTE: old key remains valid on proxy for 24h (server-side overlap grace period)."
echo "      Revocation is handled by the refslund.ai proxy admin API — not this script."
