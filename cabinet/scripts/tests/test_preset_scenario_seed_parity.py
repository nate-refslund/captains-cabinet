"""Audit #27 — full-org presets must ship a role/learning scenario seed.

The self-improvement validation gate
(``framework.learning.self_improvement_loop._run_scenario_evals_for_validation``)
runs the ``role``/``learning`` scenarios as its org-safety check and now FAILS
CLOSED on zero of them (partner of the golden-eval shells gate, audit #21). The
portfolio preset — the DEFAULT shape — shipped no ``measurement/`` seed at all,
so the gate discovered zero scenarios and returned a vacuous ``else True`` green
without ever measuring adaptation discipline.

This pins the invariant so it cannot silently regress: every full-org preset
that runs the gate carries >=1 scenario registering under category ``role`` or
``learning``. A new default preset that forgets the seed turns this red instead
of shipping a vacuous (or, post-fix, bricked) self-improvement gate.

Run: python3.12 -m pytest cabinet/scripts/tests/test_preset_scenario_seed_parity.py -q
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_PRESETS = _REPO / "presets"

# Presets that run the org self-improvement gate on a full roster. `personal`
# is intentionally excluded: it is a minimal placeholder preset with no
# measurement seed, and fail-closed correctly surfaces it the day it activates.
_FULL_ORG_PRESETS = ("work", "developer", "portfolio")
_CAT_RE = re.compile(r"""category\s*=\s*["'](?:role|learning)["']""")


@pytest.mark.parametrize("preset", _FULL_ORG_PRESETS)
def test_preset_ships_gate_relevant_scenario(preset: str) -> None:
    sdir = _PRESETS / preset / "measurement" / "scenarios"
    assert sdir.is_dir(), (
        f"{preset}: no presets/{preset}/measurement/scenarios/ seed — the "
        f"self-improvement gate would fail closed on this preset")
    hits = [
        f.name
        for f in sorted(sdir.glob("*.py"))
        if f.name != "__init__.py" and _CAT_RE.search(f.read_text())
    ]
    assert hits, (
        f"{preset}: measurement/scenarios/ ships no role/learning scenario, so "
        f"_run_scenario_evals_for_validation() sees an empty set and fails "
        f"closed (pre-fix: passed vacuously). Seed it like "
        f"presets/work/measurement/scenarios/.")


def test_portfolio_scenarios_byte_identical_to_work() -> None:
    """Portfolio's scenario seed is a VERBATIM copy of the canonical work seed
    (audit #27). Pin byte-identity so a future work-side scenario fix cannot
    leave portfolio silently stale — the self-improvement gate would then
    measure against an outdated scenario, and a stale copy is the same drift
    class the repo already pins for developer (test_preset_developer_parity.py)
    and flags for pack copies (audit B2).
    """
    work = _PRESETS / "work" / "measurement" / "scenarios"
    port = _PRESETS / "portfolio" / "measurement" / "scenarios"
    work_files = {f.name: f.read_bytes() for f in work.glob("*.py")}
    port_files = {f.name: f.read_bytes() for f in port.glob("*.py")}
    assert port_files == work_files, (
        "portfolio measurement/scenarios/ drifted from the canonical work seed; "
        "re-sync with `cp presets/work/measurement/scenarios/*.py "
        "presets/portfolio/measurement/scenarios/` (or update this pin if the "
        "divergence is intentional).")
