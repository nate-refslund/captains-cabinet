#!/bin/bash
# Bounded, read-only officer doorway into Evidence Recorder v1.
# Raw ledgers and signing material stay outside the officer tool surface; this
# command returns only the prompt-injection-resistant Cabinet projection.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TRIAL_ID="${1:-}"
LIMIT="${2:-200}"

if ! [[ "$TRIAL_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$ ]]; then
  echo "usage: evidence-read.sh <trial-id> [limit]" >&2
  exit 2
fi
if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || [ "$LIMIT" -lt 1 ] || [ "$LIMIT" -gt 1000 ]; then
  echo "limit must be an integer from 1 to 1000" >&2
  exit 2
fi

cd "$REPO"
exec python3.12 -m framework.evidence \
  --store "$REPO/instance/evidence/v1" \
  project "$TRIAL_ID" --limit "$LIMIT"
