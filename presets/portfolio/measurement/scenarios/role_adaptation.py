"""Scenario: Role receives adaptation → lineage records it, capabilities update.

Tests: Can the org safely evolve roles while preserving learning?
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.scenario_runner import Scenario, register


def _setup():
    """Create a role with initial capabilities."""
    tmp = tempfile.mkdtemp()
    os.environ["CABINET_ROOT"] = tmp
    os.environ["CABINET_EVENT_LOG_DIR"] = f"{tmp}/events"

    from framework.roles.lifecycle import create_role
    role = create_role(
        "engineering", "Engineering",
        "Build and ship product code",
        capabilities=["writes_code", "deploys_code"],
        authority_level="standard",
    )
    return {"role": role, "tmp": tmp}


def _execute(context):
    """Apply a series of adaptations to the role."""
    from framework.roles.lifecycle import adapt_role, assign_hat, get_effective_capabilities

    # Adaptation 1: Add a capability
    adapt_role("engineering", "capability_added", "Added code review",
               changes={"capability": "reviews_code"},
               evidence="3 consecutive tasks required code review",
               rationale="Formalizing existing responsibility")

    # Adaptation 2: Change charter
    adapt_role("engineering", "charter_change", "Expanded scope",
               changes={"charter": "Build, ship, and maintain product code with quality standards"},
               evidence="Maintenance work keeps falling through cracks",
               rationale="Explicitly own maintenance")

    # Adaptation 3: Assign a temporary hat
    hat = assign_hat("engineering", "Performance Engineer",
                     "Optimize critical user paths for speed",
                     capabilities=["performance_profiling", "load_testing"],
                     mission_id="mission-perf-001")

    # Get final state
    caps = get_effective_capabilities("engineering")

    return {"final_capabilities": caps, "hat": hat}


def _verify(context, results):
    """Verify adaptations applied correctly and lineage is intact."""
    assertions = []

    # Capabilities include original + added + hat
    caps = results["final_capabilities"]
    assertions.append(("has_original_cap_writes_code", "writes_code" in caps))
    assertions.append(("has_original_cap_deploys_code", "deploys_code" in caps))
    assertions.append(("has_added_cap_reviews_code", "reviews_code" in caps))
    assertions.append(("has_hat_cap_performance_profiling", "performance_profiling" in caps))
    assertions.append(("has_hat_cap_load_testing", "load_testing" in caps))

    # Lineage is complete and ordered
    from framework.roles.lifecycle import get_lineage
    lineage = get_lineage("engineering")
    assertions.append(("lineage_has_4_entries", len(lineage) == 4))  # created + 2 adapt + 1 hat

    if len(lineage) >= 4:
        assertions.append(("lineage_ordered_created_first",
                          lineage[0]["adaptation_type"] == "created"))
        assertions.append(("lineage_has_evidence",
                          lineage[1].get("evidence") is not None))
        assertions.append(("lineage_has_rationale",
                          lineage[1].get("rationale") is not None))

    # Events were emitted for each adaptation
    from framework.events.emitter import replay
    all_events = replay()
    assertions.append(("events_emitted", len(all_events) >= 4))

    # Role can be reloaded with updated state
    from framework.roles.lifecycle import load_role
    reloaded = load_role("engineering")
    assertions.append(("charter_updated",
                      "maintain" in reloaded.get("charter", "")))
    assertions.append(("reviews_code_in_role",
                      "reviews_code" in reloaded.get("capabilities", [])))

    return assertions


register(Scenario(
    name="role_adaptation",
    description="Role receives multiple adaptations, lineage stays intact, capabilities update correctly",
    category="role",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
