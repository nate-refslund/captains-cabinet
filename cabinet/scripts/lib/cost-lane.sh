#!/bin/bash
# cost-lane.sh — one line of lane metering for the shell scripts that spend
# money OUTSIDE a Claude Code session.
#
# WHY IT EXISTS. The Stop hook (cabinet/scripts/hooks/session-stop.sh →
# framework.cost.record_turn) meters officer sessions. Every other paid path —
# Voyage embeddings and reranks, ElevenLabs speech, raw curl to
# api.anthropic.com from a hook or a cron job — bypasses it entirely and was
# INVISIBLE until 2026-07-26. Not under-reported: absent.
#
# CONTRACT — read this before adding a call site:
#   * COUNTING ONLY. The Captain removed all spend caps on 2026-07-26. No call
#     here may gate, block or fail a caller. cost_lane_record ALWAYS returns 0,
#     writes nothing to stdout, and swallows stderr — so it is safe inside a
#     command substitution whose stdout is the caller's return value.
#   * CALL IT AS `cost_lane_record … || true`. If this file failed to source
#     (a partially deployed tree), the call is a 127 "command not found";
#     `|| true` keeps that from tripping `set -e` in the caller.
#   * ATTRIBUTION. `--principal` is the officer slug when a session owns the
#     call, or `svc:<service>` for a launchd/cron/daemon caller that has no
#     officer. It NEVER falls back to an officer: infrastructure spend charged
#     to a person is a corrupted per-officer number, which is worse than the
#     honest `unattributed` bucket framework/cost/meter.py assigns to an empty
#     or malformed name. Shell callers pass
#     "${CABINET_COST_PRINCIPAL:-${OFFICER_NAME:-}}" — the override lets a
#     daemon that sources an officer-shaped env name itself instead.
#   * LATENCY. One python3 start plus one redis-cli round trip on 127.0.0.1,
#     ~50-100ms, against calls that already cost hundreds of ms over the
#     network. A Redis that is DOWN fails on connect (instant); the 5s ceiling
#     in meter._redis_atomic only bites on a server that accepts and never
#     answers — the same exposure the Stop hook already carries.
#
# Field shape and the rate table live in framework/cost/meter.py. Nothing in
# this file knows either — that is the point.

COST_LANE_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

# cost_lane_record <args…> — forwarded verbatim to framework.cost.record_lane.
# Optionally reads an API response body on stdin with `--response -`.
cost_lane_record() {
  PYTHONPATH="${CABINET_ROOT:-$COST_LANE_ROOT}${PYTHONPATH:+:$PYTHONPATH}" \
    "${CABINET_PYTHON:-python3}" -m framework.cost.record_lane "$@" \
    >/dev/null 2>&1
  # Unconditional success: a metering failure is not the caller's problem, and
  # a non-zero return here would propagate through `set -e` into a paid path.
  return 0
}
