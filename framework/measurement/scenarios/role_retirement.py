"""Scenario: Role retired → learning preserved, lineage intact, no data loss.

Tests: Can the org safely retire roles without losing institutional knowledge?
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.scenario_runner import Scenario, register


def _setup():
    """Create a role with history, then prepare to retire it."""
    tmp = tempfile.mkdtemp()
    os.environ["CABINET_ROOT"] = tmp
    os.environ["CABINET_EVENT_LOG_DIR"] = f"{tmp}/events"

    from framework.roles.lifecycle import create_role, adapt_role, assign_hat

    create_role("growth", "Growth", "Grow the user base",
                capabilities=["seo", "ads", "content_marketing", "analytics"])

    adapt_role("growth", "capability_added", "Added A/B testing",
               changes={"capability": "ab_testing"},
               evidence="Running experiments is core to growth",
               rationale="Need structured experimentation")

    assign_hat("growth", "Launch Strategist", "Plan product launches",
               capabilities=["launch_planning"])

    return {"tmp": tmp}


def _execute(context):
    """Retire the role and verify state."""
    from framework.roles.lifecycle import retire_role, load_role, get_lineage, list_roles

    retire_role("growth", "Merged responsibilities into Product role")

    active_role = load_role("growth")
    active_roles = list_roles("active")
    retired_roles = list_roles("retired")
    lineage = get_lineage("growth")

    return {
        "active_role": active_role,
        "active_roles": active_roles,
        "retired_roles": retired_roles,
        "lineage": lineage,
    }


def _verify(context, results):
    """Verify retirement preserves learning."""
    assertions = []

    # Role is no longer active
    assertions.append(("not_in_active", results["active_role"] is None))
    assertions.append(("not_in_active_list",
                      not any(r.get("slug") == "growth" for r in results["active_roles"])))

    # Role is in archive
    assertions.append(("in_retired_list", len(results["retired_roles"]) >= 1))
    if results["retired_roles"]:
        archived = results["retired_roles"][0]
        assertions.append(("archive_has_capabilities",
                          "seo" in archived.get("capabilities", [])))
        assertions.append(("archive_has_ab_testing",
                          "ab_testing" in archived.get("capabilities", [])))
        assertions.append(("archive_has_retirement_reason",
                          "Merged" in archived.get("retirement_reason", "")))
        assertions.append(("archive_status_retired",
                          archived.get("status") == "retired"))

    # Lineage is preserved (all entries from before retirement still exist)
    lineage = results["lineage"]
    assertions.append(("lineage_preserved", len(lineage) >= 3))  # created + adapt + hat + retired
    if lineage:
        assertions.append(("lineage_has_retirement",
                          any(e["adaptation_type"] == "retired" for e in lineage)))
        assertions.append(("lineage_ordered",
                          lineage[0]["adaptation_type"] == "created"))

    # Events recorded
    from framework.events.emitter import replay
    retired_events = replay(event_types=["role_retired"])
    assertions.append(("retirement_event_emitted", len(retired_events) >= 1))

    return assertions


register(Scenario(
    name="role_retirement",
    description="Role retired with all learning preserved in archive and lineage",
    category="role",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
