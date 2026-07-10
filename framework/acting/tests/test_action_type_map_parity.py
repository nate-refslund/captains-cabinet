"""CI pin — the two classifiers agree on every act-first kind [CONTESTED #9].

The estate has TWO stamp paths for "what is this action":

  * the acting lane's ``ACTION_TYPE_MAP`` + ``chain_action_type`` — stamps
    ``action_type`` on ledger rows (proposal / acted / verdict events), i.e.
    which graduation CELL the evidence lands in; and
  * the shared ``classify_action`` — what the authority gate consults when the
    same act arrives as a raw tool call.

Checkpoint 2026-07-04 §4 CONTESTED #9: these can diverge (executed proof:
a Bash ``trigger_send`` dispatch stamps ``officer_dispatch`` on the ledger
while ``classify_action`` returns ``local_edit`` at the gate — different risk
rows). This suite pins the invariant for every ACT-FIRST kind: the ledger
stamp MUST equal the gate verdict on a representative REAL tool-call shape of
that kind, so an act-first act's evidence can never land in a different cell
than the one the gate priced it against.

Discipline: if a kind here ever diverges, fix the MAPPING side (or the
dispatch order) — NEVER weaken the classifier to make this pass.
"""
from __future__ import annotations

from framework.acting.action_lane import ACTION_TYPE_MAP
from framework.authority.classifier import ACTION_TYPES, classify_action
from framework.frontdoor.calendar_template import CALENDAR_EVENT_SCRIPT

# The act-first kinds (the act_with_undo executable surface at the flip) and a
# representative REAL tool-call shape for each — the exact transport the
# executor uses, not a synthetic stub:
#   * monday_task_create — a named per-op MCP create_item call.
#   * monday_task_update — a named per-op change_item_column_values call.
#   * reminder_create    — the lane's own calendar-template Bash command (the
#     classifier byte-matches CALENDAR_EVENT_SCRIPT, so this is the real
#     command shape the executor runs).
ACT_FIRST_KIND_CALLS = {
    "monday_task_create": (
        "mcp__claude_ai_monday_com__create_item",
        {"board_id": "42424242", "item_name": "Follow up VIES autofill"},
    ),
    "monday_task_update": (
        "mcp__claude_ai_monday_com__change_item_column_values",
        {"board_id": "42424242", "item_id": "123",
         "column_values": '{"status": {"label": "Done"}}'},
    ),
    "reminder_create": (
        "Bash",
        {"command": "osascript -e '" + CALENDAR_EVENT_SCRIPT
                    + "' Cabinet 'Prep EU repository onboarding' '' 2026-07-10T10:00"},
    ),
}


def test_every_act_first_kind_has_a_parity_shape():
    """Anti-shrinkage: every act-first kind pinned here must exist in the map,
    and this suite must be extended when a new Monday/calendar act-first kind
    is added (delegate_work/investigation_run act via officer transports that
    have no single raw-call equivalent — the known CONTESTED #9 residual, NOT
    covered by this parity pin)."""
    for kind in ACT_FIRST_KIND_CALLS:
        assert kind in ACTION_TYPE_MAP, f"{kind} missing from ACTION_TYPE_MAP"


def test_ledger_stamp_equals_gate_verdict_for_each_act_first_kind():
    """THE pin [CONTESTED #9]: for each act-first kind, the action_type the
    lane stamps on ledger rows equals what classify_action returns for the
    real tool call executing that kind — one cell, one risk row, no
    dual-classifier drift."""
    for kind, (tool_name, tool_input) in ACT_FIRST_KIND_CALLS.items():
        stamped = ACTION_TYPE_MAP[kind]
        gate_verdict = classify_action(tool_name, tool_input)
        assert stamped == gate_verdict, (
            f"dual-classifier divergence for {kind}: ledger stamps "
            f"{stamped!r} but classify_action says {gate_verdict!r} — fix the "
            f"mapping/dispatch, never weaken the classifier")
        # and the shared enum recognizes the stamp (no dormant-typo cell)
        assert stamped in ACTION_TYPES
