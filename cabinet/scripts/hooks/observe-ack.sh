#!/bin/bash
# observe-ack.sh — bounded receipt ACK doorway for observe-only officers.
#
# ACK is not business authority: it records that the current officer processed
# specific Redis Stream deliveries. Observe-only blocks every general Bash and
# Redis surface, so this germline wrapper is the sole state mutation permitted
# to keep at-least-once delivery finite during the 72-hour soak.

set -u

ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-}"

if [ "${CABINET_OBSERVE_ONLY:-0}" != 1 ]; then
  state=$(CABINET_ROOT="$ROOT" bash "$ROOT/cabinet/scripts/observe-only.sh" status 2>/dev/null) || {
    echo "observe-ack: observe-only state is invalid" >&2
    exit 1
  }
  if [ "$state" != active ]; then
    echo "observe-ack: available only while observe-only is active" >&2
    exit 1
  fi
fi

if [[ ! "$OFFICER" =~ ^[a-z0-9][a-z0-9-]*$ ]] || [ "${#OFFICER}" -gt 32 ]; then
  echo "observe-ack: valid OFFICER_NAME is required" >&2
  exit 2
fi

if [ "$#" -lt 1 ] || [ "$#" -gt 50 ]; then
  echo "usage: observe-ack.sh <redis-stream-id> [redis-stream-id ...] (max 50)" >&2
  exit 2
fi

for id in "$@"; do
  if [[ ! "$id" =~ ^[0-9]+-[0-9]+$ ]]; then
    echo "observe-ack: invalid Redis Stream id: $id" >&2
    exit 2
  fi
done

# The project value is inherited from the clean launcher environment. Reject
# malformed non-empty values rather than letting triggers.sh fall back to the
# legacy stream and acknowledge a receipt in the wrong namespace.
if [ -n "${CABINET_ACTIVE_PROJECT:-}" ]; then
  if [[ ! "$CABINET_ACTIVE_PROJECT" =~ ^[a-z0-9][a-z0-9-]*$ ]] \
      || [ "${#CABINET_ACTIVE_PROJECT}" -gt 32 ]; then
    echo "observe-ack: invalid CABINET_ACTIVE_PROJECT" >&2
    exit 2
  fi
fi

if ! . "$ROOT/cabinet/scripts/lib/triggers.sh"; then
  echo "observe-ack: trigger library unavailable" >&2
  exit 1
fi

keys=$(_trigger_keys "$OFFICER")
IFS='|' read -r stream group _ids_file <<< "$keys"

acked=0
already_clear=0
for id in "$@"; do
  if ! result=$(redis-cli --raw -h "$TRIG_REDIS_HOST" -p "$TRIG_REDIS_PORT" \
      XACK "$stream" "$group" "$id" 2>/dev/null); then
    echo "observe-ack: Redis ACK failed after $acked newly acknowledged receipt(s)" >&2
    exit 1
  fi
  case "$result" in
    1) acked=$((acked + 1)) ;;
    0) already_clear=$((already_clear + 1)) ;;
    *)
      echo "observe-ack: unexpected Redis ACK response: $result" >&2
      exit 1
      ;;
  esac
done

# Trimming is conservative: triggers.sh retains the oldest pending boundary
# and does nothing when the stream topology is ambiguous.
_trigger_trim_processed_prefix "$stream" "$group"
echo "observe-ack: receipts clear=$# newly_acknowledged=$acked already_clear=$already_clear"
