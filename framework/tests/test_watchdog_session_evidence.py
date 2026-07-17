"""Phase 2 Batch B (G3) — watchdog/doctor verdicts + officer session
lifecycle receipts.

Pins the batch's laws for this lens:
* vocabulary: the seven new receipt classes are registered, mirror
  allow-listed, and disjoint from the pinned nervous-system exhaust — and
  the generic session exhaust families stay OUT forever (no re-admission);
* receipts land signed in a scratch store via the Batch A chokepoint, and a
  broken recorder degrades LOUD without ever blocking the domain emit
  (receipt class — never fail-closed: fail-closed recording on recovery
  paths would self-deadlock the org);
* the typed lens seam (framework/watchdog/receipts.py) refuses foreign
  classes and pins fixed actors (argv can never spoof identity), and its
  module-exec CLI genuinely lands org row + signed receipt cross-process;
* framework/watchdog/check.py emits ONLY when a routed action actually
  FIRED — never on cooldown-skips, never under --dry-run, never from test
  stubs (exhaust discipline; happy-path stability for the existing suite);
* the lifecycle observer is transitions-only with baseline seeding,
  unobservable-carry-forward, a per-officer daily cap, and at-least-once
  delivery;
* the shell seams use MODULE-exec (path-exec never reaches the mirror) and
  stay best-effort;
* the A2 coverage gate reconciles with zero unenumerated surfaces and both
  lens surfaces honestly WIRED.

Scratch stores only (pytest fence): the mirror runs solely against
CABINET_EVIDENCE_MIRROR_STORE under tmp_path — the live signed store is
unreachable by construction. python3.12 only.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from framework import evidence_mirror
from framework.events import emitter
from framework.watchdog import check as check_mod
from framework.watchdog import receipts
from framework.watchdog.registry import CheckResult, Tier

REPO = Path(__file__).resolve().parents[2]

#: The Batch B (G3) vocabulary — one source of truth for these pins.
BATCH_B_CLASSES = frozenset({
    "watchdog_outcome_failed",
    "doctor_verdict",
    "officer_session_started",
    "officer_session_ended",
    "officer_session_compacted",
    "officer_restarted",
    "officer_limit_wake",
})


def _load_script_module(rel_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def observer():
    return _load_script_module(
        "cabinet/scripts/emit-officer-lifecycle-transitions.py",
        "officer_lifecycle_sweep_under_test",
    )


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _receipts(store: Path, trial_id: str) -> list:
    path = store / "trials" / trial_id / "events.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()
            if line.strip()]


def _org_rows(events_dir: Path) -> list:
    rows = []
    for day_file in sorted(events_dir.glob("events-*.jsonl")):
        for line in day_file.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


@pytest.fixture()
def mirror_env(tmp_path, monkeypatch):
    """Fence-open sandbox: scratch store + marker + isolated domain ledgers
    (the test_evidence_mirror.py pattern — a test can never touch the live
    signed store)."""
    store = tmp_path / "evidence-store"
    marker = tmp_path / "degradations.jsonl"
    events = tmp_path / "events"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_STORE", str(store))
    monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_MARKER", str(marker))
    evidence_mirror._reset_state()
    yield SimpleNamespace(store=store, marker=marker, events=events)
    evidence_mirror._reset_state()


# ---------------------------------------------------------------------------
# Vocabulary + allow-list law
# ---------------------------------------------------------------------------


class TestVocabulary:
    def test_batch_b_classes_are_registered(self):
        assert BATCH_B_CLASSES <= emitter.VALID_EVENT_TYPES

    def test_batch_b_classes_are_mirror_allowlisted(self):
        assert BATCH_B_CLASSES <= evidence_mirror.MIRRORED_ORG_EVENT_TYPES

    def test_batch_b_classes_are_not_exhaust(self):
        overlap = BATCH_B_CLASSES & evidence_mirror.NEVER_MIRRORED_EXHAUST
        assert not overlap, f"Batch B classes leaked into exhaust: {sorted(overlap)}"

    def test_allow_list_still_strict_subset_of_valid_types(self):
        assert evidence_mirror.MIRRORED_ORG_EVENT_TYPES < emitter.VALID_EVENT_TYPES

    def test_generic_session_exhaust_families_stay_out_forever(self):
        # The 59%-plumbing families are NOT re-admitted via the new officer_*
        # classes — the generic classes stay pinned out individually.
        for exhaust in ("session_started", "session_ended",
                        "subagent_completed", "notification_received"):
            assert exhaust in evidence_mirror.NEVER_MIRRORED_EXHAUST
            assert exhaust not in evidence_mirror.MIRRORED_ORG_EVENT_TYPES

    def test_lens_cli_set_is_a_subset_with_pinned_actors(self):
        assert receipts.RECEIPT_CLASSES <= BATCH_B_CLASSES
        assert set(receipts.RECEIPT_ACTORS) == set(receipts.RECEIPT_CLASSES)
        # Observer classes are emitted in-process, never via the CLI seam.
        assert not (receipts.RECEIPT_CLASSES & {
            "officer_session_started", "officer_session_ended",
            "officer_session_compacted"})

    def test_lens_self_checks_report_nothing_missing(self, observer):
        assert receipts.unmirrored_classes() == frozenset()
        assert observer.LIFECYCLE_EVENT_TYPES <= evidence_mirror.MIRRORED_ORG_EVENT_TYPES


# ---------------------------------------------------------------------------
# Receipts land signed; degradation is loud and never blocks (receipt class)
# ---------------------------------------------------------------------------


class TestReceiptsLand:
    def test_lifecycle_event_lands_signed_receipt(self, mirror_env):
        event = emitter.emit(
            "officer_session_started", actor="officer-lifecycle-sweep",
            payload={"officer": "cos", "first_sighting": False},
        )
        trial_id = f"evt-orgmirror-{_today()}"
        assert event["payload"][evidence_mirror.PAYLOAD_KEY] == {"trial_id": trial_id}
        (receipt,) = _receipts(mirror_env.store, trial_id)
        assert receipt["detail"]["org_event_type"] == "officer_session_started"
        assert receipt["correlation_id"] == event["id"]

        from framework.evidence.verifier import verify_trial

        assert verify_trial(mirror_env.store, trial_id)["ok"] is True

    def test_doctor_verdict_receipt_via_lens_seam(self, mirror_env):
        event = receipts.emit_receipt(
            "doctor_verdict",
            {"verdict": "GREEN", "dead": 0, "warn": 2, "waived": 1,
             "skip": 3, "total": 40},
        )
        # Actor is PINNED by the seam — never caller-supplied.
        assert event["actor"] == "cabinet-doctor"
        rows = _receipts(mirror_env.store, f"evt-orgmirror-{_today()}")
        assert [r["detail"]["org_event_type"] for r in rows] == ["doctor_verdict"]

    def test_watchdog_outcome_receipt_via_lens_seam(self, mirror_env):
        event = receipts.emit_receipt(
            "watchdog_outcome_failed",
            {"expectation_id": "briefing-delivered", "tier": "auto_fix",
             "action": "auto_fix_fired", "detail": "send FAILED"},
        )
        assert event["actor"] == "outcome-watchdog"
        rows = _receipts(mirror_env.store, f"evt-orgmirror-{_today()}")
        assert rows and rows[-1]["detail"]["org_event_type"] == "watchdog_outcome_failed"

    def test_broken_recorder_never_blocks_the_domain_emit(self, mirror_env, monkeypatch):
        monkeypatch.setattr(
            evidence_mirror, "_recorder",
            lambda root: (_ for _ in ()).throw(RuntimeError("recorder down")),
        )
        event = receipts.emit_receipt(
            "officer_limit_wake",
            {"officer": "cos", "reset_epoch": 1786000000, "notify_ok": True},
        )
        # Domain row landed; degradation was LOUD (doctor-readable marker).
        assert any(r["id"] == event["id"]
                   for r in emitter.replay(event_types=["officer_limit_wake"]))
        marker_rows = [json.loads(l) for l in
                       mirror_env.marker.read_text().splitlines() if l.strip()]
        assert marker_rows and marker_rows[0]["chokepoint"] == "org"

    def test_seam_refuses_foreign_classes(self, mirror_env):
        # Mirrored-but-foreign and exhaust classes are both refused: the
        # seam is typed, not a generic emit CLI.
        for foreign in ("need_filed", "session_started", "made_up_class"):
            with pytest.raises(ValueError):
                receipts.emit_receipt(foreign, {"x": 1})
        assert not (mirror_env.store / "trials").exists()


# ---------------------------------------------------------------------------
# The module-exec CLI — cross-process proof + refusal exits
# ---------------------------------------------------------------------------


class TestReceiptsCLI:
    def _run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "framework.watchdog.receipts", *args],
            capture_output=True, text=True, timeout=60, cwd=str(REPO),
        )

    def test_module_exec_lands_org_row_and_signed_receipt(self, mirror_env):
        payload = {"officer": "cos", "reset_epoch": 1786000000,
                   "notify_ok": True}
        result = self._run_cli("officer_limit_wake", json.dumps(payload))
        assert result.returncode == 0, result.stderr
        (row,) = [r for r in _org_rows(mirror_env.events)
                  if r["event_type"] == "officer_limit_wake"]
        assert row["actor"] == "limit-reset-watchdog"
        assert row["payload"]["officer"] == "cos"
        assert row["payload"][evidence_mirror.PAYLOAD_KEY]["trial_id"]
        rows = _receipts(mirror_env.store, f"evt-orgmirror-{_today()}")
        assert [r["detail"]["org_event_type"] for r in rows] == ["officer_limit_wake"]

    def test_cli_refuses_foreign_class_with_exit_2(self, mirror_env):
        result = self._run_cli("need_filed", "{}")
        assert result.returncode == 2
        assert "refused" in result.stderr
        assert _org_rows(mirror_env.events) == []

    def test_cli_refuses_non_object_payload_with_exit_2(self, mirror_env):
        result = self._run_cli("doctor_verdict", "[1,2]")
        assert result.returncode == 2
        assert _org_rows(mirror_env.events) == []


# ---------------------------------------------------------------------------
# check.py routing — receipts fire ONLY when a routed action fired
# ---------------------------------------------------------------------------


class _RouterProbe:
    """Minimal probe surface for route_failure. ``_allow`` mirrors
    RealProbe's side-effects flag; stubs without it must never emit."""

    def __init__(self, allow=True, cooldown=False, trigger_ok=True,
                 with_allow_attr=True):
        if with_allow_attr:
            self._allow = allow
        self._cooldown = cooldown
        self._trigger_ok = trigger_ok
        self.triggers = []

    def cooldown_active(self, eid, action):
        return self._cooldown

    def set_cooldown(self, eid, action):
        pass

    def trigger_chair(self, message):
        self.triggers.append(message)
        return self._trigger_ok

    def emit_drift_proposal(self, title, body):
        return True


def _exp(tier, auto_fix=None, eid="exp-under-test"):
    return SimpleNamespace(id=eid, what="declared outcome", tier=tier,
                           auto_fix=auto_fix)


def _res(detail="outcome failed"):
    return CheckResult("exp-under-test", False, detail)


@pytest.fixture()
def captured_receipts(monkeypatch):
    calls = []

    def capture(eid, tier, action, detail):
        calls.append({"eid": eid, "tier": tier, "action": action,
                      "detail": detail})

    monkeypatch.setattr(check_mod, "_emit_outcome_receipt", capture)
    return calls


class TestCheckRouting:
    def test_escalation_fired_emits_one_receipt(self, captured_receipts):
        probe = _RouterProbe()
        action = check_mod.route_failure(
            probe, _exp(Tier.ESCALATE_CHAIR), _res())
        assert "ESCALATED to Chair" in action
        assert captured_receipts == [{
            "eid": "exp-under-test", "tier": Tier.ESCALATE_CHAIR.value,
            "action": "escalated", "detail": "outcome failed"}]

    def test_auto_fix_fired_emits_one_receipt(self, captured_receipts):
        probe = _RouterProbe()
        action = check_mod.route_failure(
            probe, _exp(Tier.AUTO_FIX, auto_fix=lambda p, r: "did it"), _res())
        assert "AUTO-FIX fired" in action
        assert [c["action"] for c in captured_receipts] == ["auto_fix_fired"]

    def test_auto_fix_declined_escalation_emits_fallback_receipt(self, captured_receipts):
        probe = _RouterProbe()
        action = check_mod.route_failure(
            probe, _exp(Tier.AUTO_FIX, auto_fix=lambda p, r: None), _res())
        assert "ESCALATED" in action
        assert [c["action"] for c in captured_receipts] == [
            "auto_fix_declined_escalated"]

    def test_drift_note_emits_receipt(self, captured_receipts):
        probe = _RouterProbe()
        action = check_mod.route_failure(probe, _exp(Tier.DRIFT), _res())
        assert "DRIFT note" in action
        assert [c["action"] for c in captured_receipts] == ["drift_note"]

    def test_cooldown_skip_never_emits(self, captured_receipts):
        # The exhaust law: a persistently-broken outcome records ONCE per
        # cooldown window, not once per 30-min sweep.
        probe = _RouterProbe(cooldown=True)
        action = check_mod.route_failure(
            probe, _exp(Tier.ESCALATE_CHAIR), _res())
        assert "SKIPPED (cooldown active)" in action
        assert captured_receipts == []

    def test_failed_enqueue_never_emits(self, captured_receipts):
        probe = _RouterProbe(trigger_ok=False)
        action = check_mod.route_failure(
            probe, _exp(Tier.ESCALATE_CHAIR), _res())
        assert "FAILED to enqueue" in action
        assert captured_receipts == []

    def test_dry_run_probe_never_emits(self, captured_receipts):
        probe = _RouterProbe(allow=False)  # RealProbe under --dry-run
        check_mod.route_failure(probe, _exp(Tier.ESCALATE_CHAIR), _res())
        assert captured_receipts == []

    def test_stub_probe_without_allow_never_emits(self, captured_receipts):
        # The existing suite's FakeProbe shape (no _allow attribute) must
        # never spawn an emit subprocess — happy-path stability for tests.
        probe = _RouterProbe(with_allow_attr=False)
        action = check_mod.route_failure(
            probe, _exp(Tier.ESCALATE_CHAIR), _res())
        assert "ESCALATED to Chair" in action
        assert captured_receipts == []

    def test_emit_subprocess_is_module_exec_from_repo_root(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(check_mod, "subprocess",
                            SimpleNamespace(run=fake_run))
        check_mod._emit_outcome_receipt("exp-1", "escalate_chair",
                                        "escalated", "d" * 400)
        ((cmd, kwargs),) = calls
        assert cmd[1:4] == ["-m", "framework.watchdog.receipts",
                            "watchdog_outcome_failed"]
        assert cmd[0] == sys.executable
        payload = json.loads(cmd[4])
        assert payload["expectation_id"] == "exp-1"
        assert len(payload["detail"]) == 200  # truncation cap
        # MODULE-exec from the repo root — the mirror import must resolve.
        assert kwargs["cwd"] == str(check_mod._REPO_ROOT)

    def test_emit_never_raises(self, monkeypatch):
        def boom(cmd, **kwargs):
            raise OSError("no interpreter")

        monkeypatch.setattr(check_mod, "subprocess",
                            SimpleNamespace(run=boom))
        check_mod._emit_outcome_receipt("exp-1", "drift", "drift_note", "x")

    def test_checker_stays_stdlib_only(self):
        # The independence law ("imports NOTHING it watches"): no
        # framework.events / framework.evidence / evidence_mirror import may
        # enter check.py — receipts ride a subprocess module-exec.
        source = (REPO / "framework" / "watchdog" / "check.py").read_text()
        assert "from framework.events" not in source
        assert "import framework.events" not in source
        assert "framework.evidence" not in source
        assert "evidence_mirror" not in source


# ---------------------------------------------------------------------------
# Lifecycle observer — pure transition detection (the sweep seam)
# ---------------------------------------------------------------------------


def _obs(running=None, terminated=None, captured_at=None):
    return {"running": running, "terminated": terminated,
            "captured_at": captured_at}


class TestObserverSweep:
    def test_baseline_is_flagged_for_silent_seeding(self, observer):
        result = observer.sweep({"cos": _obs(running=True, terminated="")}, None)
        assert result["baseline"] is True
        assert result["current"]["cos"]["running"] is True

    def test_started_transition(self, observer):
        prev = {"cos": {"running": False, "terminated": "", "captured_at": ""}}
        result = observer.sweep({"cos": _obs(running=True, terminated="")}, prev)
        (t,) = result["transitions"]
        assert t["type"] == "officer_session_started"
        assert t["payload"] == {"officer": "cos", "first_sighting": False,
                                "observed_via": "tmux-or-liveness"}

    def test_new_officer_after_baseline_is_first_sighting(self, observer):
        prev = {"cos": {"running": True, "terminated": "", "captured_at": ""}}
        result = observer.sweep(
            {"cos": _obs(running=True, terminated=""),
             "cto": _obs(running=True, terminated="")}, prev)
        (t,) = result["transitions"]
        assert t["type"] == "officer_session_started"
        assert t["payload"]["officer"] == "cto"
        assert t["payload"]["first_sighting"] is True

    def test_clean_end_carries_stamp_and_reason(self, observer):
        prev = {"cos": {"running": True, "terminated": "", "captured_at": ""}}
        stamp = "2026-07-17T10:00:00Z|reason=clear"
        result = observer.sweep(
            {"cos": _obs(running=False, terminated=stamp)}, prev)
        (t,) = result["transitions"]
        assert t["type"] == "officer_session_ended"
        assert t["payload"]["reason"] == "clear"
        assert t["payload"]["ended_at"] == "2026-07-17T10:00:00Z"
        assert t["payload"]["stamp"] == stamp  # joinability with hook exhaust
        assert result["current"]["cos"]["running"] is False
        assert result["current"]["cos"]["terminated"] == stamp

    def test_crash_end_without_stamp_is_unobserved(self, observer):
        prev = {"cos": {"running": True, "terminated": "", "captured_at": ""}}
        result = observer.sweep(
            {"cos": _obs(running=False, terminated="")}, prev)
        (t,) = result["transitions"]
        assert t["type"] == "officer_session_ended"
        assert t["payload"]["reason"] == "unobserved"
        assert t["payload"]["stamp"] is None

    def test_compaction_advance(self, observer):
        prev = {"cos": {"running": True, "terminated": "",
                        "captured_at": "2026-07-17T09:00:00Z"}}
        result = observer.sweep(
            {"cos": _obs(running=True, terminated="",
                         captured_at="2026-07-17T11:00:00Z")}, prev)
        (t,) = result["transitions"]
        assert t["type"] == "officer_session_compacted"
        assert t["payload"] == {"officer": "cos",
                                "captured_at": "2026-07-17T11:00:00Z"}

    def test_unobservable_probes_carry_state_forward(self, observer):
        # A tmux/Redis outage must NEVER read as a fleet-wide session end.
        prev = {"cos": {"running": True, "terminated": "t0|reason=clear",
                        "captured_at": "c0"}}
        result = observer.sweep({"cos": _obs()}, prev)
        assert result["transitions"] == []
        assert result["current"]["cos"] == prev["cos"]

    def test_quiet_second_sweep_emits_nothing(self, observer):
        observed = {"cos": _obs(running=True, terminated="", captured_at="c1")}
        first = observer.sweep(observed, {"cos": {
            "running": True, "terminated": "", "captured_at": "c1"}})
        assert first["transitions"] == []
        second = observer.sweep(observed, first["current"])
        assert second["transitions"] == []

    def test_end_then_start_ordering_in_one_sweep(self, observer):
        prev = {"cos": {"running": False,
                        "terminated": "t0|reason=clear", "captured_at": ""}}
        result = observer.sweep(
            {"cos": _obs(running=True, terminated="t1|reason=other")}, prev)
        kinds = [t["type"] for t in result["transitions"]]
        assert kinds == ["officer_session_ended", "officer_session_started"]

    def test_stamp_parsing_tolerates_partial_stamps(self, observer):
        assert observer.parse_terminated_stamp(
            "2026-07-17T10:00:00Z|reason=logout") == (
            "2026-07-17T10:00:00Z", "logout")
        assert observer.parse_terminated_stamp("only-ts") == ("only-ts", "unknown")
        assert observer.parse_terminated_stamp("ts|weird") == ("ts", "weird")


# ---------------------------------------------------------------------------
# Lifecycle observer — main() behaviors (baseline / cap / at-least-once)
# ---------------------------------------------------------------------------


class TestObserverMain:
    @pytest.fixture()
    def wired(self, observer, mirror_env, tmp_path, monkeypatch):
        state = tmp_path / "state" / "officer-lifecycle.json"
        monkeypatch.setattr(observer, "roster_slugs", lambda: {"cos"})
        monkeypatch.setattr(observer, "redis_reachable", lambda: False)
        monkeypatch.setattr(observer, "session_state_captured_at",
                            lambda officer: None)
        return SimpleNamespace(observer=observer, state=state,
                               mirror=mirror_env, monkeypatch=monkeypatch)

    def _run(self, wired, tmux_result):
        wired.monkeypatch.setattr(wired.observer, "tmux_officer_sessions",
                                  lambda: set(tmux_result))
        return wired.observer.main(["--state-file", str(wired.state)])

    def test_baseline_seeds_silently_then_detects_end(self, wired):
        assert self._run(wired, {"cos"}) == 0
        assert _org_rows(wired.mirror.events) == []  # baseline = seed, no emit
        assert self._run(wired, set()) == 0          # session vanished
        rows = _org_rows(wired.mirror.events)
        assert [r["event_type"] for r in rows] == ["officer_session_ended"]
        assert rows[0]["payload"]["reason"] == "unobserved"
        assert rows[0]["actor"] == "officer-lifecycle-sweep"
        # signed receipt landed too
        receipts_rows = _receipts(wired.mirror.store,
                                  f"evt-orgmirror-{_today()}")
        assert [r["detail"]["org_event_type"] for r in receipts_rows] == [
            "officer_session_ended"]

    def test_daily_cap_drops_loudly_and_state_advances(self, wired, monkeypatch, capsys):
        monkeypatch.setattr(wired.observer,
                            "MAX_EMITS_PER_OFFICER_PER_DAY", 1)
        self._run(wired, {"cos"})   # baseline
        self._run(wired, set())     # ended -> emitted (count 1)
        self._run(wired, {"cos"})   # started -> CAPPED, dropped
        rows = _org_rows(wired.mirror.events)
        assert [r["event_type"] for r in rows] == ["officer_session_ended"]
        err = capsys.readouterr().err
        assert "daily emit cap" in err
        # state advanced despite the drop: no re-detection storm next sweep
        assert self._run(wired, {"cos"}) == 0
        assert [r["event_type"] for r in _org_rows(wired.mirror.events)] == [
            "officer_session_ended"]

    def test_at_least_once_reverts_and_reemits(self, wired, monkeypatch):
        self._run(wired, {"cos"})   # baseline
        original_emit = emitter.emit

        def boom(*args, **kwargs):
            raise RuntimeError("emitter down")

        monkeypatch.setattr(emitter, "emit", boom)
        assert self._run(wired, set()) == 0   # detected, emit FAILED
        assert _org_rows(wired.mirror.events) == []
        monkeypatch.setattr(emitter, "emit", original_emit)
        # Same observation next sweep -> the SAME transition re-emits.
        assert self._run(wired, set()) == 0
        assert [r["event_type"] for r in _org_rows(wired.mirror.events)] == [
            "officer_session_ended"]


# ---------------------------------------------------------------------------
# Shell seams — module-exec pins + syntax (drift guards)
# ---------------------------------------------------------------------------


class TestShellSeams:
    DOCTOR = REPO / "cabinet" / "scripts" / "cabinet-doctor.sh"
    HEARTBEAT = REPO / "cabinet" / "cron" / "heartbeat-watchdog.sh"
    LIMIT = REPO / "cabinet" / "cron" / "limit-reset-watchdog.sh"

    def test_doctor_emits_verdict_after_history_best_effort(self):
        text = self.DOCTOR.read_text()
        emit_at = text.index("-m framework.watchdog.receipts doctor_verdict")
        assert emit_at > text.index('HIST="cabinet/logs/doctor-history.jsonl"')
        tail = text[emit_at:emit_at + 400]
        assert "|| true" in tail  # best-effort: never changes the verdict

    def test_heartbeat_watchdog_emits_restart_receipts_module_exec(self):
        text = self.HEARTBEAT.read_text()
        assert "python3.12 -m framework.watchdog.receipts" in text
        assert "officer_restarted" in text
        # path-exec never reaches the mirror — pinned out.
        assert "framework/events/emitter.py" not in text

    def test_limit_reset_watchdog_emits_wake_receipt_module_exec(self):
        text = self.LIMIT.read_text()
        assert "python3.12 -m framework.watchdog.receipts" in text
        assert "officer_limit_wake" in text
        assert "framework/events/emitter.py" not in text

    @pytest.mark.parametrize("script", ["DOCTOR", "HEARTBEAT", "LIMIT"])
    def test_shell_syntax_is_valid(self, script):
        path = getattr(self, script)
        result = subprocess.run(["bash", "-n", str(path)],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# A2 coverage gate — enumerated, no drift, both lens surfaces WIRED
# ---------------------------------------------------------------------------


class TestCoverageGate:
    def test_reconciles_with_lens_surfaces_wired(self):
        coverage = _load_script_module("cabinet/scripts/evidence-coverage.py",
                                       "evidence_coverage_under_test")
        report = coverage.reconcile(REPO)
        assert report["unenumerated"] == []
        rows = {row["id"]: row for row in report["surfaces"]}
        assert rows["watchdog-doctor"]["status"] == "WIRED"
        assert "framework/watchdog/receipts.py" in rows["watchdog-doctor"]["producers"]
        assert rows["officer-session-lifecycle"]["status"] == "WIRED"
        assert ("cabinet/scripts/emit-officer-lifecycle-transitions.py"
                in rows["officer-session-lifecycle"]["producers"])
