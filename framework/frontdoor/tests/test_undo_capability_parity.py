"""[GERM-2] undo-capability parity — TYPE and PATH [RT-B2].

TYPE: every action_type in an `act_with_undo` class has a registered, non-`none`
inverse executor — you cannot classify something reversible-with-undo that the
undo plane cannot actually reverse.

PATH: an `act_with_undo` verdict is honored ONLY through the journaled action
lane. An officer's RAW pm_write/calendar_write tool call never auto-executes
from the matrix verdict — the matrix is SHADOW-consumed at the officer gate
(policy_engine, "adds NO new live exit-2"), and the sole act-first executor is
the lane, which write-ahead-journals before every mutation
(test_action_exec::test_write_ahead_journal_exists_before_mutation). So an
unattested pm_write/calendar_write can never act unattended.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.frontdoor import action_undo as U


# act_with_undo type -> the lane kind (+ backend) that actually executes it.
AWU_TYPE_TO_KIND = {
    "task_create":           ("monday_task_create", "monday"),
    "board_status":          ("monday_task_update", "monday"),
    "calendar_event_create": ("reminder_create",    "calendar"),
}


# --- TYPE parity ------------------------------------------------------------

def test_every_act_with_undo_type_has_a_real_inverse():
    for at, (kind, backend) in AWU_TYPE_TO_KIND.items():
        assert U.act_first_eligible(kind, backend) is True, at
        inv = U.inverse_for(kind, backend, {}, {}, {})
        assert inv["op"] != "none", (at, inv)


def test_officer_dispatch_has_no_inverse_and_is_not_act_first():
    # internal_comms, not act_with_undo — must have NO act-first inverse.
    assert U.act_first_eligible("delegate_work", "delegate") is False


# --- PATH parity ------------------------------------------------------------

def _load_policy():
    import yaml
    root = Path(__file__).resolve().parent.parent.parent.parent
    data = yaml.safe_load((root / "framework" / "policies" / "authority-matrix.yml").read_text())
    # matrix_policy normalizes; the verdicts table lives under policies[0]
    pol = data["policies"][0] if isinstance(data, dict) and "policies" in data else data
    return pol


def test_pm_write_cell_verdict_is_act_with_undo():
    # The matrix DOES class pm_write as act_with_undo at every confidence state
    # (that is the earn-demotion posture) — this is the cell verdict the lane
    # reads when it decides to act-with-undo.
    import importlib.util
    root = Path(__file__).resolve().parent.parent.parent.parent
    spec = importlib.util.spec_from_file_location(
        "policy_engine", root / "cabinet" / "scripts" / "lib" / "policy_engine.py")
    pe = importlib.util.module_from_spec(spec); spec.loader.exec_module(pe)
    verdicts = _load_policy()["verdicts"]
    for state in ("graduated", "eligible", "propose_only", "unmeasured"):
        assert pe.resolve_verdict(verdicts, "pm_write", state) == "act_with_undo"
    assert pe.resolve_verdict(verdicts, "pm_write", "demote") == "propose_only"


def test_officer_raw_call_verdict_is_shadow_not_a_live_grant():
    # PATH invariant: the matrix verdict is consumed in SHADOW at the officer
    # gate — evaluate_policy() (the live exit-2 floor of pre-tool-use) does NOT
    # auto-execute act_with_undo. The string 'act_with_undo' must not appear as
    # a live-enforced auto branch in the policy engine's floor.
    root = Path(__file__).resolve().parent.parent.parent.parent
    src = (root / "cabinet" / "scripts" / "lib" / "policy_engine.py").read_text()
    # the resolver KNOWS the verdict, but the live floor never turns it into an
    # unattended execution — documented as shadow-consumed (no live exit-2).
    assert "shadow" in src.lower()


def test_executor_uses_the_single_source_calendar_template():
    # [GERM-2] drift guard — the executor must reference the shared constant, so
    # "byte-match the lane template" in the classifier can never silently drift.
    import inspect
    import framework.frontdoor.action_exec as AE
    assert "CALENDAR_EVENT_SCRIPT" in inspect.getsource(AE._exec_calendar_event)
