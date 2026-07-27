#!/bin/bash
# transcribe-voice.sh — Transcribe a Telegram voice message file to text via ElevenLabs Scribe.
# Usage: transcribe-voice.sh <path-to-audio-file>
# Requires: ELEVENLABS_API_KEY in environment.
#
# STDOUT CONTRACT: the transcript, and nothing else (pre-captain-dm.sh consumes
# it). The lane meter below is silent on stdout by construction.

FILE="${1:?Usage: transcribe-voice.sh <path-to-audio-file>}"
[ -f "$FILE" ] || { echo "File not found: $FILE" >&2; exit 1; }
[ -n "$ELEVENLABS_API_KEY" ] || { echo "ELEVENLABS_API_KEY not set" >&2; exit 1; }

CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
# LANE METER (2026-07-26) — counting only, see cabinet/scripts/lib/cost-lane.sh.
# shellcheck source=/dev/null
. "$CABINET_ROOT/cabinet/scripts/lib/cost-lane.sh" 2>/dev/null || true

# Body captured rather than piped straight to jq so the meter can read it. jq is
# still the last command in the pipeline, so both the transcript on stdout and
# this script's exit status are what they were before.
RESPONSE=$(curl -sS --max-time 60 -X POST "https://api.elevenlabs.io/v1/speech-to-text" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -F "file=@$FILE" \
  -F "model_id=scribe_v2")

# PAID CALL COUNTED (lane `stt`). Unpriced by design — ElevenLabs has no row in
# meter.RATES. ElevenLabs bills speech-to-text by AUDIO DURATION, and Scribe
# returns per-word timestamps, so `units` is whole seconds of audio taken from
# the response's own last word-end. It is measured from what the vendor
# returned, not a proxy: no words (an error body, or a model that omitted them)
# yields 0, which record_lane drops rather than writing a false zero.
STT_SECONDS=$(printf '%s' "$RESPONSE" | jq -r \
  '[(.words // [])[] | (.end // 0)] | if length > 0 then (max | floor) else 0 end' \
  2>/dev/null)
case "$STT_SECONDS" in ''|*[!0-9]*) STT_SECONDS=0 ;; esac
cost_lane_record --lane stt \
  --principal "${CABINET_COST_PRINCIPAL:-${OFFICER_NAME:-}}" \
  --units "$STT_SECONDS" 2>/dev/null || true

printf '%s' "$RESPONSE" | jq -r '.text'
