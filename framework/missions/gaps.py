"""Holder gaps: a ready work item nobody can do becomes a row, not a silence.

`observe_holder_gaps(missions, active_slugs, actor=...)` records one keyed
`capability_gaps` row per (outcome, task) that is ready and has no holder, and
resolves the ones that healed. It routes nothing, claims nothing and blocks
nothing.
"""

# WHAT WAS SILENT. A compiled work graph can hold a ready node that nobody can
# do: the compiler found no role whose capabilities match it, or it stamped an
# explicit owner that is not on the roster. Both branches ended in `continue`
# (supervisor.py's own comment said "silently skip for now"), and the pull path
# answered None with no trace at all. The condition is invisible until somebody
# wonders why nothing is happening — the failure the phase-1 direction of
# record names, and the whole reason this module exists.
#
# KIND `skill`, which is STRUCTURAL: surfaced and rendered, never proposed,
# never auto-skilled, never DM'd (capability_gaps.py STRUCTURAL_KINDS). A
# missing holder is not something the loop can build for itself, so a proposal
# would be an ask the Captain cannot approve into existence.
#
# KEYED, so a standing condition costs one row and not one per pass. The key is
# `holder:<outcome_id>:<task_id>` and `record_gap(dedup_key=...)` deduplicates
# on identity under its own lock: re-observing an open gap returns it and emits
# nothing. Without the key the Jaccard merge would fold `…task-001` into
# `…task-002` (their need sentences differ by one character) and emit a
# `capability_gap_merged` on every scan — a merge storm that also destroys the
# one-row-per-subject property the surface depends on.
#
# SELF-RESOLVING, so nobody has to close it. A pass that finds the node's role
# on the roster, or the node finished, resolves the gap. No Captain act, no
# approval, no proposal.
#
# IDS IN THE NEED SENTENCE, never the task description or the outcome name. A
# description is instance text this module does not control: it can carry a
# product noun (the agnostic law) and a skeleton criterion can carry a literal
# `<TODO` marker, and both would then be sitting in a gap row. The ids are the
# same identifiers the evidence carries and they survive a re-description.
#
# LOCK ORDER, fixed and one-directional: claims lock -> gaps lock -> ledger
# lock. The pull path holds the claims lock across its observation (A3.1),
# `record_gap` takes the gaps lock inside that, `emit` takes the ledger lock
# inside that. Nothing here takes a claims lock itself, so this module cannot
# invert the order on its own; the rule binds whoever adds a call in the other
# direction.
#
# PYTHON 3.9. The locked prompt hook reaches this module through
# `session_bridge.get_next_task`, and the reference box's `python3` is 3.9.6.
# No runtime `X | Y`, no `match`, no 3.10+ stdlib (A0.3).

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.learning.capability_gaps import (  # noqa: E402
    STATUS_DECLINED,
    STATUS_RESOLVED,
    project_gaps,
    record_gap,
    resolve_gap,
)

# The dedup-key namespace. Every key this module mints starts here, which is
# also how the resolve pass recognises its own rows in the projection: a gap
# recorded by anything else is none of its business.
KEY_PREFIX = "holder"

# The vocabulary phase 2 routes on. Recording it now is what makes the
# condition readable at all.
GAP_KIND = "skill"

# Why no holder was found. Two reasons, because they want different answers:
# `no_match` is "nobody on the roster fits this", `not_on_roster` is "the row
# names somebody who does not exist here".
REASON_NO_MATCH = "no_match"
REASON_NOT_ON_ROSTER = "not_on_roster"

# A node past this line will never need a holder again. BLOCKED and
# IN_PROGRESS are NOT terminal: the first still wants one, and the second is
# held under a claim whose role may still be off the roster.
_TERMINAL_STATUS_VALUES = frozenset({"done", "failed"})


def holder_key(outcome_id: str, task_id: str) -> str:
    """The dedup key for one (outcome, task). Identity, never similarity."""
    return "{0}:{1}:{2}".format(KEY_PREFIX, outcome_id, task_id)


def holder_need(outcome_id: str, task_id: str) -> str:
    """The need sentence. Ids only — see the module comment."""
    return "no holder on the roster for `{0}` of `{1}`".format(task_id, outcome_id)


def _status_value(node: Any) -> str:
    status = getattr(node, "status", None)
    value = getattr(status, "value", status)
    return str(value or "").lower()


# ONE walk over the graphs, so the record side and the resolve side read the
# SAME observation: two independent walks could disagree about a node that
# changed between them, and the disagreement would show up as a gap opened and
# resolved in the same pass.
def _node_facts(
    missions: Optional[Iterable[Dict[str, Any]]],
    active: Set[str],
) -> Dict[str, Dict[str, Any]]:
    """Every node of every mission, keyed by its holder key."""
    facts = {}  # type: Dict[str, Dict[str, Any]]
    for mission in missions or ():
        graph = (mission or {}).get("work_graph")
        if graph is None:
            continue
        outcome_id = str((mission or {}).get("outcome_id") or "")
        ready_ids = {node.id for node in graph.ready_tasks()}
        for node in graph.nodes.values():
            role = getattr(node, "assigned_role", None) or None
            if role is None:
                reason = REASON_NO_MATCH  # type: Optional[str]
            elif role not in active:
                reason = REASON_NOT_ON_ROSTER
            else:
                reason = None
            facts[holder_key(outcome_id, node.id)] = {
                "reason": reason,
                "assigned_role": role,
                "outcome_id": outcome_id,
                "task_id": node.id,
                "ready": node.id in ready_ids,
                "terminal": _status_value(node) in _TERMINAL_STATUS_VALUES,
            }
    return facts


# JSON, not a mapping. `record_gap` types evidence as a string, concatenates it
# into the touch inference, and the dashboard renders `gap.evidence` as a React
# child — a raw mapping there is an object child, which throws. Compact sorted
# JSON keeps the four contract fields and every consumer that exists today.
def _evidence(fact: Dict[str, Any]) -> str:
    """The four contract fields, as the string the record plane stores."""
    return json.dumps(
        {
            "reason": fact["reason"],
            "assigned_role": fact["assigned_role"],
            "outcome_id": fact["outcome_id"],
            "task_id": fact["task_id"],
        },
        sort_keys=True,
    )


def _resolution(fact: Dict[str, Any]) -> str:
    if fact["terminal"]:
        return "the work item finished without one"
    return "holder on the roster: {0}".format(fact["assigned_role"])


# THE THREE LISTS ARE ADVISORY under concurrency: two observers of one new
# subject can both call it opened, because the projection is read before the
# lock that settles the record. The RECORD is exact — one row per subject,
# whatever the labels say — and the sensors count events, never labels.
#
# NEVER RAISES for a gap it could not record or resolve. A supervisor pass and
# a prompt hook both call this, and neither may die because the record plane
# did: that would trade one silence for a louder one.
def observe_holder_gaps(
    missions: Optional[Iterable[Dict[str, Any]]],
    active_slugs: Optional[Iterable[str]],
    *,
    actor: str,
    now: Optional[Any] = None,
    product_slug: Optional[str] = None,
) -> Dict[str, List[str]]:
    """Record a gap for every ready node with no holder; resolve the healed.

    Args:
        missions: compiled missions (each a dict with `work_graph` and
            `outcome_id`) — the caller's own compile, never a second one.
        active_slugs: the roster the caller routed against. An empty roster is
            a legitimate observation (every owned node is then off-roster), not
            a reason to skip: a fresh instance with no roles is exactly the
            state this surface exists to make visible.
        actor: who observed. Recorded as both `actor` and `recorded_by`.
        now: accepted for signature parity and NOT used. Every timestamp on
            this path is the ledger's own `created_at`; a caller-supplied clock
            would let a gap be dated by something other than the event that
            recorded it.
        product_slug: the gaps namespace. Defaults exactly as `record_gap`
            does, from `CABINET_PRODUCT_SLUG` (A3.2 — a pre-existing leak, and
            a second one is not added here).

    Returns:
        `{"opened": [...], "resolved": [...], "unchanged": [...]}` of gap ids.
    """
    del now  # documented above: this path has no clock of its own
    slug = product_slug or os.environ.get("CABINET_PRODUCT_SLUG") or "default"
    active = {str(s) for s in (active_slugs or ()) if s}
    facts = _node_facts(missions, active)

    live = {}  # type: Dict[str, Dict[str, Any]]
    for gap in project_gaps(product_slug=slug):
        key = gap.get("dedup_key") or ""
        if not key.startswith(KEY_PREFIX + ":"):
            continue
        if gap.get("status") in (STATUS_RESOLVED, STATUS_DECLINED):
            continue
        live[key] = gap

    opened = []  # type: List[str]
    resolved = []  # type: List[str]
    unchanged = []  # type: List[str]

    for key in sorted(facts):
        fact = facts[key]
        if not fact["ready"] or fact["terminal"] or fact["reason"] is None:
            continue
        if key in live:
            unchanged.append(live[key]["gap_id"])
            continue
        try:
            gap = record_gap(
                holder_need(fact["outcome_id"], fact["task_id"]),
                kind=GAP_KIND,
                evidence=_evidence(fact),
                recorded_by=actor,
                actor=actor,
                product_slug=slug,
                dedup_key=key,
            )
        except Exception as exc:  # noqa: BLE001 — a pass survives the record plane
            print(
                "observe_holder_gaps: WARN could not record {0}: {1}: {2}".format(
                    key, type(exc).__name__, exc
                ),
                file=sys.stderr,
            )
            continue
        opened.append(gap["gap_id"])

    for key in sorted(live):
        gap = live[key]
        fact = facts.get(key)
        # The subject is not in this pass's missions at all — an outcome that
        # stopped compiling, or a caller looking at one mission. The gap STAYS
        # OPEN: "I cannot see it right now" is not "it is fixed", and a row
        # closed on absence is a condition that disappeared without anybody
        # deciding it should.
        if fact is None:
            unchanged.append(gap["gap_id"])
            continue
        if fact["reason"] is not None and not fact["terminal"]:
            unchanged.append(gap["gap_id"])
            continue
        try:
            resolve_gap(
                gap["gap_id"], _resolution(fact), actor=actor, product_slug=slug,
            )
        except Exception as exc:  # noqa: BLE001
            print(
                "observe_holder_gaps: WARN could not resolve {0}: {1}: {2}".format(
                    gap["gap_id"], type(exc).__name__, exc
                ),
                file=sys.stderr,
            )
            continue
        resolved.append(gap["gap_id"])

    return {"opened": opened, "resolved": resolved, "unchanged": unchanged}
