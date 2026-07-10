#!/bin/bash
# emit-demo-receipt.sh — seed ONE explicitly-labeled DEMO receipt at hatch
# (Perfect Cabinet Wave B, day-1 legibility).
#
# A fresh Captain should see a legible receipt in minute one — before the org
# has acted on anything real. This script builds ONE synthetic acted row
# through the REAL schema path (framework.frontdoor.action_undo new_row +
# _validate_row — never hand-crafted JSON that could drift from the schema;
# the underscore validator is the module's own schema authority, same internal
# idiom tell_digest rides) and renders it with the REAL receipt renderer
# (framework.frontdoor.tell_surface.render_receipt), written next to the
# first-briefing file with the same atomic local-write idiom
# (run_briefing._run_local_render: tmp + os.replace under
# $CABINET_ROOT/instance/memory/).
#
# NEVER JOURNALED (fix 2026-07-10, adversarial review): the row is built and
# validated but NOT appended to the undo journal. A journaled demo row with no
# consequence-ledger event would trip the germline acted-overlay consistency
# fence on every fresh box ("journal has rows in-window but ledger returned
# nothing (env drift?)" -> act-first disarmed) and would surface in any
# digest/sweeper/labeler that walks the journal. The receipt FILE is the whole
# demo artifact; the live undo journal, the daily digest, and the undo sweeper
# never see it. (action_reconcile's demo:true skip stays as defense-in-depth
# for any future demo-stamped row.)
#
# HONESTY DOCTRINE (non-negotiable properties of the row + the file):
#   * demo: true on the row, and the row exists ONLY inside this file —
#     nothing synthetic ever enters the acted record, so no machine outcome
#     label can ever be minted from it.
#   * inverse op "none" with a demo reason — the receipt anatomy shows the
#     real 48h undo window (ttl_expires_at, computed by new_row), but the row
#     never claims an undo that is not registered; an `undo` against it is an
#     honest no-op ("nothing real to reverse").
#   * the rendered file is HEADED by an explicit DEMO label; content is
#     synthetic Testburg vocabulary only.
#   * no journal append, no Redis pointer, no ledger event, no network, no
#     Telegram.
#
# Idempotent by construction: the only artifact is the receipt file, rendered
# atomically on every run (a deleted or stale file is simply re-rendered;
# there is no durable row to duplicate).
#
# Usage: emit-demo-receipt.sh [--dry-run] [--print-row]
#   --dry-run    print what would be written, write nothing, exit 0.
#   --print-row  also print the built row as a DEMO_ROW=<json> line (tests
#                re-validate it against the real schema validator).
# Env: CABINET_ROOT (default: this checkout), CABINET_PYTHON (default
# python3.12).
# Exit codes: 0 = receipt in place · 1 = failure · 64 = usage error.
set -euo pipefail

usage() { echo "usage: emit-demo-receipt.sh [--dry-run] [--print-row]" >&2; exit 64; }
DRY_RUN=0
PRINT_ROW=0
for _arg in "$@"; do
  case "$_arg" in
    --dry-run)   DRY_RUN=1 ;;
    --print-row) PRINT_ROW=1 ;;
    *)           usage ;;
  esac
done
unset _arg

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ROOT="${CABINET_ROOT:-$REPO_ROOT}"
export CABINET_ROOT="$ROOT"
# framework/ lives in the checkout, not necessarily under a scratch CABINET_ROOT.
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
export EMIT_DEMO_PRINT_ROW="$PRINT_ROW"

PY="${CABINET_PYTHON:-python3.12}"
command -v "$PY" >/dev/null 2>&1 || { echo "emit-demo-receipt: $PY not found on PATH" >&2; exit 1; }

if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] emit-demo-receipt.sh would:"
  echo "  1. build ONE synthetic acted row (demo: true, kind monday_task_create,"
  echo "     inverse op none) via action_undo.new_row + _validate_row — NEVER"
  echo "     journaled (the live undo journal stays untouched) — skipped"
  echo "  2. render it with tell_surface.render_receipt and write"
  echo "     $ROOT/instance/memory/demo-receipt.md — skipped"
  echo "[dry-run] nothing was written."
  exit 0
fi

exec "$PY" - <<'PYEOF'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from framework.frontdoor import action_undo, tell_surface

# The fixed demo pid. A readable, obviously-synthetic id (never a real
# proposal's opaque hex) so the ·pid· marker in the rendered anatomy is
# self-describing.
PID = "demo-hatch-receipt"

# The exact Captain-facing label (Perfect Cabinet Wave B contract — tests pin it).
LABEL = ("DEMO receipt — seeded at hatch so you can see the receipt anatomy; "
         "reply-to-undo works on real receipts only")

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
root = Path(os.environ["CABINET_ROOT"])
receipt_path = root / "instance" / "memory" / "demo-receipt.md"

# THE REAL SCHEMA PATH, minus the journal: new_row builds the schema-shaped
# row (action_type resolves through the real registry: monday_task_create ->
# task_create; ttl_expires_at = ts + the real 48h UNDO_WINDOW_H). It is
# validated with the module's own validator and then rendered — but NEVER
# appended to the undo journal: a journaled demo row with no ledger event
# would trip the acted-overlay consistency fence on a fresh box and surface
# in the daily digest as a real act. Everything synthetic is
# Testburg-flavored and the row is stamped demo: true.
row = action_undo.new_row(
    pid=PID, cid="", step=1,
    kind="monday_task_create",          # real registry kind -> action_type task_create
    backend="demo", lane="demo",
    subject="Water the window boxes on Testburg Lane (demo)",
    actor={"kind": "officer", "id": "cos"},
    prestate={}, created={},
    inverse={"op": "none",
             "args": {"reason": "demo row — seeded at hatch to show the "
                                "receipt anatomy; nothing real to reverse"}},
    executed_at=now, status="executed", now=now)
row["demo"] = True
row["content"] = {
    "title": "Water the window boxes on Testburg Lane",
    "why": ("seeded at hatch so you can see how every real act reports "
            "itself — what it did, why, what it cost, and how to undo it"),
    "notes": "cost: unattributed (demo — nothing was spent)",
}
# The module's own schema validator (journal_step runs exactly this before an
# append) — the row shown in the anatomy can never drift from the real schema.
action_undo._validate_row(row)

# THE REAL RENDERER: the very code real receipts ride (head, exact content,
# undo window, the one trusted ·pid· marker last).
rendered = tell_surface.render_receipt(row, now=now)
if not rendered:
    print("emit-demo-receipt: render_receipt returned empty — refusing to "
          "write a blank receipt", file=sys.stderr)
    sys.exit(1)

body = (
    f"# {LABEL}\n"
    f"\n"
    f"- demo: true — built and validated through the real receipt schema but\n"
    f"  NEVER journaled: the live undo journal, the daily digest, and the\n"
    f"  undo sweeper cannot see this row, so no machine outcome label will\n"
    f"  ever be minted from it\n"
    f"- composed: {now} on this machine, locally — nothing was sent\n"
    f"\n"
    f"Every REAL act your cabinet takes arrives looking exactly like this:\n"
    f"\n"
    f"```\n"
    f"{rendered}\n"
    f"```\n"
    f"\n"
    f"Anatomy: WHAT was done (the headline + exact content) / WHY (the why\n"
    f"line) / COST (unattributed here — real receipts attribute real cost) /\n"
    f"UNDO (a real 48-hour window; this row's `ttl_expires_at` is\n"
    f"{row.get('ttl_expires_at')}). The `·pid·` marker on the last line is\n"
    f"what a reply binds to.\n"
    f"\n"
    f"On real receipts you reply with one of three verbs:\n"
    f"  `undo <n>`     reverses the act (deterministic inverse, never an LLM)\n"
    f"  `👍 <n>`       confirms it (your verdict feeds graduation)\n"
    f"  `never: <why>` vetoes the whole kind — verbatim, forever; silence\n"
    f"                 never clears a veto\n"
    f"\n"
    f"This one is a demo: its inverse is registered as `none` —\n"
    f"\"nothing real to reverse\" — so reply-to-undo works on real receipts only.\n"
    f"How the whole loop is governed: docs/how-your-cabinet-is-governed.md\n"
)

seeded = not receipt_path.exists()
receipt_path.parent.mkdir(parents=True, exist_ok=True)
tmp = receipt_path.with_name(receipt_path.name + ".tmp")
tmp.write_text(body, encoding="utf-8")
os.replace(tmp, receipt_path)

state = ("seeded" if seeded
         else "re-rendered (idempotent re-run)")
print(f"emit-demo-receipt: demo receipt {state} — file only, never journaled")
print(LABEL)
print("")
print(rendered)
print("")
if os.environ.get("EMIT_DEMO_PRINT_ROW") == "1":
    print("DEMO_ROW=" + json.dumps(row, default=str))
print(f"DEMO_RECEIPT={receipt_path}")
PYEOF
