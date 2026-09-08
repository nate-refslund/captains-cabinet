"""Session-to-mission bridge: connects worker sessions to the mission work graph.

Reads the active outcomes, compiles them via the mission compiler, and finds
the next ready task for the current session's role.  This lets hooks inject
mission context into sessions so they know what to work on.

CLAIM BY DEFAULT.  Every pull takes an atomic claim with a lease
(``framework/missions/claims.py``).  It has to be the default rather than an
opt-in: the only production caller is a locked prompt hook whose call site
cannot be changed, so a claim that had to be asked for would never be taken,
and two live sessions of one role would keep believing they both owned the
same task.  ``claim=False`` is the read-only projection for callers that only
want to look.

WHAT A TICK DOES.  A tick that finds the session's OWN live claim renews it and
returns ``None`` — the task is already in flight and re-injecting it every tick
for the whole of its life is noise, not work (pass ``include_own=True`` to see
it anyway).  A tick that finds no claim of its own takes the first ready node
for the role that nobody else holds.  A tick that finds every ready node
claimed returns ``None``.

NOTHING HERE RAISES.  A failure anywhere on the claim path returns ``None`` and
appends a line to ``claims.err`` beside the ledger: the hook that calls this
runs on every prompt submit, and an exception there costs the session, not just
the task.

GAPS, NOT SILENCE.  Ready work with no holder on the roster is recorded as one
keyed row per subject (``framework/missions/gaps.py``) instead of being skipped
without a trace.  Once per invocation, on the CLAIMING path only —
``claim=False`` is a projection and keeps its event-free contract — after the
pull, under the claims lock, and unable to change what the pull answered.

Python 3.9 compatible — the locked hook imports this module and the reference
box's ``python3`` is 3.9.

Usage:
    from framework.missions.session_bridge import get_next_task, format_task_for_session

    task = get_next_task("engineering", cabinet_root="/opt/founders-cabinet")
    if task:
        print(format_task_for_session(task))
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from cabinet.scripts.lib.work_graph import WorkGraph, NodeStatus
from framework.missions import claims as _claims
from framework.missions import compiler as _compiler
from framework.missions import gaps as _gaps
from framework.missions.compiler import compile_from_yaml


def _outcomes_path(cabinet_root: str | None = None) -> Path:
    """Resolve the path to the outcomes YAML file."""
    if cabinet_root is None:
        cabinet_root = os.environ.get(
            "CABINET_ROOT",
            str(Path(__file__).parent.parent.parent),
        )
    return Path(cabinet_root) / "instance" / "config" / "outcomes.yml"


def _dependencies_met(graph: WorkGraph, node_id: str) -> list[str]:
    """Return descriptions of completed dependencies for a node."""
    dep_ids = graph._deps.get(node_id, set())
    return [
        graph.nodes[d].description
        for d in dep_ids
        if graph.nodes[d].status == NodeStatus.DONE
    ]


def _task_dict(
    mission: dict[str, Any],
    graph: WorkGraph,
    node: Any,
    claim: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the task dict handed to the session."""
    task = {
        "mission_name": mission["name"],
        "outcome_id": mission["outcome_id"],
        "task_id": node.id,
        "task_description": node.description,
        "verification_criteria": node.verification_criteria,
        "dependencies_met": _dependencies_met(graph, node.id),
        "assigned_role": node.assigned_role,
    }
    if claim is not None:
        task["claim_id"] = claim.get("claim_id")
        task["expires_at"] = claim.get("expires_at")
        task["holder"] = claim.get("holder")
    return task


def _compile_missions(outcomes_file: Path) -> list[dict[str, Any]] | None:
    try:
        # Projection compile: this runs from session hooks every few minutes
        # purely to FIND the next task. emit_event=False keeps it from
        # spamming mission_created into the ledger on every invocation —
        # materialization events belong to the supervisor's real routing pass.
        return compile_from_yaml(
            outcomes_file, actor="session_bridge", roles=None, emit_event=False,
        )
    except (FileNotFoundError, ValueError):
        return None


def _first_ready_for_role(
    missions: list[dict[str, Any]], role_slug: str
) -> dict[str, Any] | None:
    """The read-only projection: the first ready node for this role."""
    for mission in missions:
        graph: WorkGraph = mission["work_graph"]
        for node in graph.ready_tasks():
            if node.assigned_role == role_slug:
                return _task_dict(mission, graph, node)
    return None


def _pull_with_claim(
    missions: list[dict[str, Any]],
    role_slug: str,
    holder: str,
    lease_s: int | None,
    include_own: bool,
) -> dict[str, Any] | None:
    """Renew the holder's own claim, else claim the first free ready node."""
    live = _claims.live_claims()

    # (a) The holder's own live claim.  It is NOT in ready_tasks() — the
    # compiler overlays IN_PROGRESS for an unexpired claim — so the whole node
    # set is scanned, not the ready subset.
    for mission in missions:
        graph: WorkGraph = mission["work_graph"]
        for node in graph.nodes.values():
            if node.assigned_role != role_slug:
                continue
            held = live.get(node.id)
            if held is None or held.get("holder") != holder:
                continue
            renewed = _claims.renew(held["claim_id"], holder, lease_s=lease_s) or held
            if include_own:
                return _task_dict(mission, graph, node, renewed)
            return None

    # (b) The first ready node for this role that nobody holds.
    for mission in missions:
        graph = mission["work_graph"]
        for node in graph.ready_tasks():
            if node.assigned_role != role_slug:
                continue
            if node.id in live:
                continue  # someone else's; the lock below settles a real race
            taken = _claims.claim(
                node.id,
                mission["outcome_id"],
                holder,
                actor=role_slug,
                lease_s=lease_s,
            )
            if taken is None:
                continue  # lost the race — try the next node
            return _task_dict(mission, graph, node, taken)

    return None


# THE ROSTER IS THE COMPILER'S OWN.  `_compiler.list_roles` rather than a
# second import of the same function: the roster that decides "is there a
# holder" has to be the roster the compile used to stamp `assigned_role`, or a
# caller who supplies one and not the other gets a gap naming a mismatch that
# does not exist.
#
# UNDER THE CLAIMS LOCK (A3.1), which fixes the acquisition order at
# claims -> gaps -> ledger.  It runs AFTER the pull rather than around it:
# `claims.claim` takes the same lock, and `flock` is per open file description,
# so a nested acquire in one process waits on itself forever.  This is the ONE
# place the pull path holds the claims lock while recording a gap, and
# `test_gaps.py::test_the_pull_path_takes_the_locks_in_order` pins the order
# here.
#
# Never raises and never changes what the pull returns: the caller is a prompt
# hook, and an observation that could cost a session or a task would be worse
# than the silence it replaces.
#
# The failure goes to `claims.err`, NOT to stderr. The only production caller
# is `cabinet/scripts/hooks/session-task-inject.sh`, which ran this as
# `RESULT="$(python3 -c "..." 2>/dev/null)"`: a stderr line there is
# discarded, so an observation failing on every tick would be invisible — the
# same silence this unit exists to remove, one layer up. Master's copy appends
# that stderr to `${CABINET_HOOK_LOG:-...}` since the A7.7 landing of the
# germline bundle's G3 bytes, but the deployment runs its locked copy until the
# Captain's window, so the discarding shape is still the live one. `record_error`
# is the seam the claim path in this same function already uses, and it is
# durable, beside the ledger, where a later pass can find it.
def _observe_gaps(missions: list[dict[str, Any]], role_slug: str) -> None:
    """Record the pull path's silence, once per invocation."""
    try:
        active = {
            role.get("slug")
            for role in _compiler.list_roles(status="active")
            if role.get("slug")
        }
        with _claims.claims_lock():
            _gaps.observe_holder_gaps(missions, active, actor=role_slug)
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        _claims.record_error(
            "get_next_task({0!r}): holder-gap observation failed: {1}: {2}".format(
                role_slug, type(exc).__name__, exc
            )
        )


def get_next_task(
    role_slug: str,
    cabinet_root: str | None = None,
    *,
    holder: str | None = None,
    lease_s: int | None = None,
    claim: bool = True,
    include_own: bool = False,
) -> dict[str, Any] | None:
    """Get the next ready task for this role from active missions, and claim it.

    Looks for ``instance/config/outcomes.yml``, compiles active outcomes into
    missions, then searches the resulting work graphs for a ready task assigned
    to *role_slug*.

    Args:
        role_slug: the role pulling work.
        cabinet_root: repo root; ``CABINET_ROOT`` or the module's own root.
        holder: the claim identity; derived per ``claims.derive_holder`` when
            absent, so two sessions of one role never share a claim.
        lease_s: lease override in seconds.
        claim: when False, a side-effect-free projection — no claim, no event,
            and no gap observation (that path emits).
        include_own: when True, a tick that renews its own live claim returns
            that task instead of ``None``.

    Returns a task dict or ``None`` if nothing is ready and unclaimed.
    """
    outcomes_file = _outcomes_path(cabinet_root)
    if not outcomes_file.exists():
        return None

    missions = _compile_missions(outcomes_file)
    if missions is None:
        return None

    if not claim:
        return _first_ready_for_role(missions, role_slug)

    # The claim path is best-effort BY CONTRACT: the caller is a prompt hook.
    try:
        resolved = holder or _claims.derive_holder(role_slug)
        task = _pull_with_claim(missions, role_slug, resolved, lease_s, include_own)
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        _claims.record_error(
            "get_next_task({0!r}): claim path failed: {1}: {2}".format(
                role_slug, type(exc).__name__, exc
            )
        )
        task = None

    # Whatever the pull answered, the nodes it could not take are now a row
    # somebody can read. Last, so nothing here can change what it answered.
    _observe_gaps(missions, role_slug)
    return task


def format_task_for_session(task: dict[str, Any]) -> str:
    """Format a task dict as a human-readable context string for injection."""
    lines = [
        f"Mission: {task['mission_name']}",
        f"Task: {task['task_description']}",
        f"Role: {task['assigned_role']}",
    ]

    if task.get("verification_criteria"):
        lines.append("Verification criteria:")
        for criterion in task["verification_criteria"]:
            lines.append(f"  - {criterion}")

    if task.get("dependencies_met"):
        lines.append("Completed dependencies:")
        for dep in task["dependencies_met"]:
            lines.append(f"  - {dep}")

    # The claim is the reason this task is yours and nobody else's, and the
    # token is what a completion is fenced on — so the id, the expiry and the
    # exact completion command go into the injected context. Without the
    # command the holder has a token it has no way to spend.
    if task.get("claim_id"):
        lines.append(f"Claim: {task['claim_id']} (expires {task.get('expires_at')})")
        lines.append(
            "Complete with: cabinet/scripts/work-graph-complete.sh "
            f"{task['task_id']} --claim {task['claim_id']} "
            "--status done --evidence <file-or-text>"
        )

    return "\n".join(lines)
