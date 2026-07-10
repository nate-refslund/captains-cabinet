#!/bin/bash
# first-briefing.sh — the genesis FIRST RECEIPT, local-first.
#
# Perfect Cabinet Wave A (Captain decision 2026-07-09): the first receipt at
# hatch end = proofs + a first briefing carrying org-PROPOSED outcome cards;
# Telegram/BotFather is a post-receipt errand. hatch-spine calls this verbatim:
#
#   bash cabinet/scripts/first-briefing.sh --local
#
# What it does (thin wrapper — orchestrates, never reimplements):
#   1. ONBOARD-1 + ONBOARD-2: `python3.12 -m framework.onboarding.genesis`
#      — the org PROPOSES 2-4 outcome cards from the cabinet-init answers
#      (propose-only: status draft + captain_ratified false, staged in
#      instance/config/outcomes-proposed.yml which the mission compiler never
#      reads), and attempts the genesis research brief into the Library shelf
#      (claude CLI, fixed argv, short timeout) — honest IOU note on any
#      failure, never fake content.
#   2. Local render: `python3.12 -m framework.frontdoor.run_briefing --now
#      --local-render` composes ONE briefing from those genesis surfaces and
#      writes instance/memory/first-briefing-<UTC date>.md.
#   3. Receipt gate: exit 0 ONLY if that file exists and carries >=1 proposed
#      outcome card.
#
# LOCAL-FIRST by construction: no Telegram (channel.py untouched; CABINET_ENV
# is not set here, so allow_sends() stays False in an unconfigured shell), no
# Redis, no launchctl. Scratch instances: export CABINET_ROOT=<scratch root>
# (default: this checkout — the normal hatch case, where the clone IS the
# instance). Python: CABINET_PYTHON overrides the python3.12 default.
# Genesis knobs (see framework/onboarding/genesis.py): CABINET_GENESIS_BRIEF_TIMEOUT,
# CABINET_GENESIS_NET_HOST/_PORT (preflight target — point at 127.0.0.1:1 to
# force the honest-IOU path in offline drills).
set -euo pipefail

usage() { echo "usage: first-briefing.sh --local" >&2; exit 64; }
[ "$#" -eq 1 ] || usage
[ "$1" = "--local" ] || usage

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT="${CABINET_ROOT:-$REPO_ROOT}"
export CABINET_ROOT="$ROOT"
# framework/ lives in the checkout, not necessarily under a scratch CABINET_ROOT.
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

PY="${CABINET_PYTHON:-python3.12}"
command -v "$PY" >/dev/null 2>&1 || { echo "first-briefing: $PY not found on PATH" >&2; exit 1; }

# 1) Genesis organs (ONBOARD-1 propose + ONBOARD-2 brief-or-IOU). Exit 3 from
#    the module = answers missing (run cabinet-init + generate-instance first).
"$PY" -m framework.onboarding.genesis

# 2) Compose the briefing locally (no send, no Redis; prints the receipt line).
OUT="$("$PY" -m framework.frontdoor.run_briefing --now --local-render)"
printf '%s\n' "$OUT"

# 3) Receipt gate: the file must exist and carry >=1 proposed outcome card.
#    LITERAL COUPLING: the 'Proposed outcome:' literal grepped below is emitted
#    by framework/onboarding/genesis.py genesis_intake_items() — reword BOTH
#    sides in the same commit.
RECEIPT="$(printf '%s\n' "$OUT" | sed -n 's/^FIRST_BRIEFING_RECEIPT=//p' | tail -1)"
if [ -z "$RECEIPT" ]; then
  echo "first-briefing: no FIRST_BRIEFING_RECEIPT line in run_briefing output" >&2
  exit 1
fi
if [ ! -f "$RECEIPT" ]; then
  echo "first-briefing: receipt file missing: $RECEIPT" >&2
  exit 1
fi
CARDS="$(grep -c 'Proposed outcome:' "$RECEIPT" || true)"
if [ "${CARDS:-0}" -lt 1 ]; then
  echo "first-briefing: receipt carries no proposed outcome cards: $RECEIPT" >&2
  exit 1
fi
echo "FIRST BRIEFING RECEIPT: $RECEIPT ($CARDS proposed outcome cards, propose-only)"
