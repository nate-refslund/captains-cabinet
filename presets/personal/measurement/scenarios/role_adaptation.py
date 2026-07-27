"""Scenario: a personal-preset role adapts → lineage records it, capabilities update.

Tests the same question the work-preset seed asks — can the org evolve a role
while preserving the learning that justified the change — but over THIS
preset's roster, which has no C-suite in it. The roles here are the ones
`presets/personal/preset.yml` actually ships (navigator, librarian), so the
gate measures the preset that is loaded rather than a copy of another one.

WHY THIS FILE HAD TO EXIST BEFORE THE PRESET COULD BE ACTIVATED.
`framework.learning.self_improvement_loop._run_scenario_evals_for_validation`
FAILS CLOSED on zero role/learning scenarios (audit #27): an unseeded preset
makes `run_all_scenarios()` return `[]` and the gate then reports red rather
than passing vacuously. `presets/personal/` shipped no `measurement/` seed at
all, which was correct while the preset was a forbidden placeholder and became
a bricked self-improvement gate the moment it was activated —
`cabinet/scripts/tests/test_preset_scenario_seed_parity.py` said so in its own
exclusion comment ("fail-closed correctly surfaces it the day it activates").
This is that day.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.scenario_runner import Scenario, register


def _setup():
    """Create the Navigator role with its initial capabilities."""
    tmp = tempfile.mkdtemp()
    os.environ["CABINET_ROOT"] = tmp
    os.environ["CABINET_EVENT_LOG_DIR"] = f"{tmp}/events"

    from framework.roles.lifecycle import create_role
    role = create_role(
        "navigator", "Navigator",
        "Hold the shape of one project and propose the next move with evidence",
        capabilities=["reads_notes", "proposes_next_step"],
        authority_level="standard",
    )
    return {"role": role, "tmp": tmp}


def _execute(context):
    """Adapt the role the way this preset's operator actually would."""
    from framework.roles.lifecycle import (
        adapt_role, assign_hat, get_effective_capabilities)

    # Adaptation 1: a capability the operator kept asking for by hand.
    adapt_role("navigator", "capability_added", "Added stale-item surfacing",
               changes={"capability": "surfaces_stalled_work"},
               evidence="3 consecutive weeks the operator asked what had not moved",
               rationale="Formalizing a request that was already recurring")

    # Adaptation 2: charter widened to say what it had started doing anyway.
    adapt_role("navigator", "charter_change", "Named the citation duty",
               changes={"charter": "Hold the shape of one project and propose the "
                                   "next move, citing the evidence for each item"},
               evidence="Uncited proposals were being ignored",
               rationale="A proposal the operator cannot check is not a proposal")

    # Adaptation 3: a temporary hat — recall depth for one stretch of work.
    hat = assign_hat("navigator", "Librarian",
                     "Assemble cited context across the declared folder",
                     capabilities=["searches_local_notes", "joins_across_time"],
                     mission_id="mission-context-001")

    caps = get_effective_capabilities("navigator")
    return {"final_capabilities": caps, "hat": hat}


def _verify(context, results):
    """Adaptations applied, lineage intact, evidence preserved."""
    assertions = []

    caps = results["final_capabilities"]
    assertions.append(("has_original_cap_reads_notes", "reads_notes" in caps))
    assertions.append(("has_original_cap_proposes_next_step",
                       "proposes_next_step" in caps))
    assertions.append(("has_added_cap_surfaces_stalled_work",
                       "surfaces_stalled_work" in caps))
    assertions.append(("has_hat_cap_searches_local_notes",
                       "searches_local_notes" in caps))
    assertions.append(("has_hat_cap_joins_across_time",
                       "joins_across_time" in caps))

    from framework.roles.lifecycle import get_lineage
    lineage = get_lineage("navigator")
    assertions.append(("lineage_has_4_entries", len(lineage) == 4))
    if len(lineage) >= 4:
        assertions.append(("lineage_ordered_created_first",
                           lineage[0]["adaptation_type"] == "created"))
        assertions.append(("lineage_has_evidence",
                           lineage[1].get("evidence") is not None))
        assertions.append(("lineage_has_rationale",
                           lineage[1].get("rationale") is not None))

    from framework.events.emitter import replay
    assertions.append(("events_emitted", len(replay()) >= 4))

    from framework.roles.lifecycle import load_role
    reloaded = load_role("navigator")
    assertions.append(("charter_updated",
                       "citing" in reloaded.get("charter", "")))
    assertions.append(("added_capability_persisted",
                       "surfaces_stalled_work" in reloaded.get("capabilities", [])))

    # NOT pinned here: that the shipped roster carries no C-suite. This file is
    # COPIED into instance/measurement/scenarios/ by load-preset.sh and runs
    # with CABINET_ROOT repointed at a temp dir, so it cannot reliably find the
    # preset it came from — reading presets/personal/preset.yml from here would
    # be a sensor pointed at whatever happens to be relative to the install
    # location. That invariant is pinned where the repo layout is known:
    # cabinet/scripts/tests/test_personal_preset_live.py.
    return assertions


register(Scenario(
    name="personal_role_adaptation",
    description="A personal-preset role adapts on evidence; lineage stays intact "
                "and the roster stays free of C-suite officers",
    category="role",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
