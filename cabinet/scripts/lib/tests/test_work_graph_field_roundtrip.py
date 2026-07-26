"""WorkNode's Mission Compiler v2 fields must survive serialization.

`to_json()` declared six fields on WorkNode and emitted none of them;
`from_json()` never read them. A graph round-tripped through JSON came back
with verifier_role=None, risk_level='', captain_attention_estimate=0.0 — no
error, no warning.

Why this file is separate from the field list: the property under test is
"a graph that goes through JSON comes back the same graph", so these arms
assert on the RESTORED NODE, never on the emitted key set. A test that pinned
the key set would pass while the reader still dropped every value.

verifier_role is the one that bites: it names who is allowed to verify the
node, so losing it on a round-trip erases the separation of duties the
runtime relies on.
"""

from __future__ import annotations

import pytest

from work_graph import WorkGraph, WorkNode, NodeStatus


_RICH_FIELDS = {
    "evidence_required": "signed pdf attached to the ticket",
    "verifier_role": "auditor",
    "risk_level": "high",
    "rollback_note": "revert the migration, restore from the pre-cutover snapshot",
    "budget_note": "no incremental spend",
    "captain_attention_estimate": 0.9,
}


def _rich_graph():
    g = WorkGraph()
    g.add_node(WorkNode(
        id="n1",
        description="cut over the billing ledger",
        assigned_role="engineering",
        status=NodeStatus.PENDING,
        **_RICH_FIELDS,
    ))
    return g


@pytest.mark.parametrize("field,expected", sorted(_RICH_FIELDS.items()))
def test_rich_field_survives_roundtrip(field, expected):
    """Each declared field comes back with the value it went in with."""
    restored = WorkGraph.from_json(_rich_graph().to_json())
    assert getattr(restored.nodes["n1"], field) == expected


def test_verifier_role_survives_roundtrip_explicitly():
    """Called out on its own: this field decides WHO MAY VERIFY the node.

    Losing it silently downgrades a node with a named auditor into a node
    anyone may verify.
    """
    restored = WorkGraph.from_json(_rich_graph().to_json())
    assert restored.nodes["n1"].verifier_role == "auditor"


def test_roundtrip_is_a_fixed_point():
    """Serialize -> load -> serialize is stable, so a graph does not decay
    field-by-field across repeated persist/load cycles."""
    once = _rich_graph().to_json()
    twice = WorkGraph.from_json(once).to_json()
    assert once == twice


def test_payload_without_rich_keys_still_loads():
    """Back-compat: a JSON payload written before these keys existed must
    still load, taking the dataclass defaults rather than raising."""
    legacy = (
        '{"nodes": [{"id": "n1", "description": "d", "assigned_role": "eng",'
        ' "status": "pending", "verification_criteria": [],'
        ' "verification_passed": null}], "edges": []}'
    )
    node = WorkGraph.from_json(legacy).nodes["n1"]
    assert node.verifier_role is None
    assert node.evidence_required == ""
    assert node.risk_level == ""
    assert node.rollback_note == ""
    assert node.budget_note == ""
    assert node.captain_attention_estimate == 0.0
