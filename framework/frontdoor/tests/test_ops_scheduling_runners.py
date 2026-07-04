"""L7-ops-scheduling — the machine-label producer runners (checkpoint
2026-07-04 conditions 5 + 12: UNDO-3 sweep + TI-7 canary scheduled, falsifier
line measurable).

These tests validate the SHIPPED ARTIFACTS (plists + runner scripts +
falsifier-report compute), fully fixtured — no launchctl, no network, no Redis,
no live ledger. The runner scripts' live behavior is the already-tested library
code (action_reconcile / actfirst_canary); here we prove the wiring: the plists
parse and point at real files, the scripts never execute launchctl or touch the
act-first flag, and the falsifier line computes honestly from a fixtured
ledger."""
from __future__ import annotations

import datetime as dt
import importlib.util
import plistlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
LAUNCHD = REPO / "cabinet" / "launchd"
SCRIPTS = REPO / "cabinet" / "scripts"
# The plists pin the live-checkout absolute prefix (matching every existing
# concrete com.cabinet.* plist); tests re-root it to THIS checkout so the
# referenced files are proven to exist wherever the repo lives.
LIVE_PREFIX = "/Users/nate/captains-cabinet"

PLISTS = {
    "com.cabinet.undo-sweep": LAUNCHD / "com.cabinet.undo-sweep.plist",
    "com.cabinet.actfirst-canary": LAUNCHD / "com.cabinet.actfirst-canary.plist",
    "com.cabinet.falsifier-daily": LAUNCHD / "com.cabinet.falsifier-daily.plist",
}
RUNNER_SCRIPTS = [
    SCRIPTS / "run-undo-sweep.sh",
    SCRIPTS / "run-actfirst-canary.sh",
    SCRIPTS / "falsifier-report.py",
]


def _load_falsifier_report():
    spec = importlib.util.spec_from_file_location(
        "falsifier_report", SCRIPTS / "falsifier-report.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- plists -------------------------------------------------------------------

@pytest.mark.parametrize("label", sorted(PLISTS))
def test_plist_parses_and_matches_conventions(label):
    path = PLISTS[label]
    with open(path, "rb") as f:
        data = plistlib.load(f)
    # Label naming + filename agreement (com.cabinet.* convention).
    assert data["Label"] == label
    assert label.startswith("com.cabinet.")
    # Producers must never fire mid-bootstrap (matches every existing plist).
    assert data["RunAtLoad"] is False
    # Log convention: ~/.cabinet/logs/<name>.log, stdout+stderr merged.
    assert data["StandardOutPath"].startswith("/Users/nate/.cabinet/logs/")
    assert data["StandardOutPath"] == data["StandardErrorPath"]
    # Exactly one schedule mechanism.
    assert ("StartInterval" in data) != ("StartCalendarInterval" in data)
    # repo-root PYTHONPATH + WorkingDirectory (lane requirement).
    assert data["WorkingDirectory"] == LIVE_PREFIX
    assert data["EnvironmentVariables"]["PYTHONPATH"] == LIVE_PREFIX
    # The program the plist points at must exist in the repo (re-rooted).
    prog = data["ProgramArguments"][-1]
    assert prog.startswith(LIVE_PREFIX + "/")
    assert (REPO / prog[len(LIVE_PREFIX) + 1:]).is_file()


def test_plist_cadences():
    with open(PLISTS["com.cabinet.undo-sweep"], "rb") as f:
        assert plistlib.load(f)["StartInterval"] == 3600          # hourly sweep
    with open(PLISTS["com.cabinet.actfirst-canary"], "rb") as f:
        cal = plistlib.load(f)["StartCalendarInterval"]
        assert "Weekday" in cal                                   # weekly canary
    with open(PLISTS["com.cabinet.falsifier-daily"], "rb") as f:
        cal = plistlib.load(f)["StartCalendarInterval"]
        assert "Weekday" not in cal and "Hour" in cal             # daily report


# --- runner scripts -------------------------------------------------------------

@pytest.mark.parametrize("script", RUNNER_SCRIPTS, ids=lambda p: p.name)
def test_runner_never_runs_launchctl_or_flips_act_first(script):
    """The runners produce labels/telemetry; loading the agents and flipping
    act-first stay HUMAN steps (INSTALL-flip.md). launchctl may appear only in
    comments (install/uninstall documentation), never on an executable line."""
    text = script.read_text()
    for line in text.splitlines():
        code = line.split("#", 1)[0]           # strip trailing/whole-line comments
        assert "launchctl" not in code, f"{script.name} executes launchctl: {line!r}"
    assert "CABINET_ACT_FIRST" not in text
    assert "act-first-enabled" not in text
    assert script.stat().st_mode & 0o111, f"{script.name} is not executable"


def test_sweep_runner_guards_the_false_ttl_ok_path():
    """Checkpoint condition 5's exact cited failure: 'the None-probe mints
    false ttl_ok on outage'. The runner must build a REAL probe and skip the
    run when Monday is absent/unreachable rather than sweep blind."""
    text = (SCRIPTS / "run-undo-sweep.sh").read_text()
    assert "make_monday_probe" in text
    assert "MONDAY_API_TOKEN" in text          # presence guard (env NAME only)
    assert "sys.exit(1)" in text               # skip is loud, not silent


def test_canary_runner_uses_the_journal_only_weekly_bundle():
    text = (SCRIPTS / "run-actfirst-canary.sh").read_text()
    assert "run_weekly" in text                # canary + breakers + veto audit
    assert "_default_osascript" in text        # argv-list transport, never shell


# --- falsifier line (fixtured ledger, injected redis) ---------------------------

def _ev(ts, *, action="action-card", action_type=None, required=True,
        decision=None, outcome="unknown", verdict=None, source=None,
        lane="polads"):
    ev = {"ts": ts, "actor": {"kind": "officer", "id": "officer:cos"},
          "lane": lane, "action": action,
          "proposal": {"required": required, "decision": decision},
          "outcome": {"status": outcome},
          "review": {"verdict": verdict, "source": source}}
    if action_type:
        ev["action_type"] = action_type
    return ev


NOW = dt.datetime(2026, 7, 4, 12, 0, tzinfo=dt.timezone.utc)


def _fixtured_ledger():
    return [
        # Two acted (unattended) rows inside the 7d window — one held, one undone.
        _ev("2026-07-01T10:00:00Z", action_type="monday_task_create",
            required=False, outcome="ok", verdict="confirmed", source="verdict_human"),
        _ev("2026-07-02T10:00:00Z", action_type="monday_task_create",
            required=False, outcome="failed", verdict="wrong", source="verdict_human"),
        # A proposal card approved inside the window.
        _ev("2026-07-03T09:00:00Z", action_type="monday_task_create",
            decision="approved", outcome="ok", verdict="confirmed",
            source="verdict_human"),
        # An OLD acted row (outside 7d) — still stamped, still in cell math.
        _ev("2026-06-01T10:00:00Z", action_type="monday_task_create",
            required=False, outcome="ok", verdict="confirmed", source="verdict_human"),
        # An unstamped legacy row — must count in NO cell bucket (sentinel).
        _ev("2026-07-03T11:00:00Z", decision="approved", outcome="ok"),
    ]


def test_compute_line_counts_from_fixtured_ledger():
    fr = _load_falsifier_report()
    line = fr.compute_line(_fixtured_ledger(), now=NOW, redis_get=lambda k: "")
    assert line["date"] == "2026-07-04"
    assert line["acted_7d"] == 2
    assert line["approved_7d"] == 2            # stamped + unstamped approvals
    assert line["reversal_rate_7d"] == pytest.approx(0.5)
    assert line["stamped_rows_total"] == 4
    assert line["proactive_cards_7d"] == 4     # window rows, all action-cards
    # One stamped cell (officer:cos, polads, monday_task_create): 4 samples is
    # under every bar's floor → accumulating, never graduated. The unstamped
    # sentinel cell is excluded from BOTH counts (it can never graduate).
    assert line["cells_accumulating"] == 1
    assert line["cells_graduated"] == 0


def test_compute_line_reversal_rate_is_null_not_zero_when_unmeasured():
    """No acted rows ⇒ rate is None (an unmeasured falsifier must read as
    unmeasured — a silent 0.0 would fake a passing F2b)."""
    fr = _load_falsifier_report()
    ledger = [_ev("2026-07-03T09:00:00Z", action_type="monday_task_create",
                  decision="approved", outcome="ok")]
    line = fr.compute_line(ledger, now=NOW, redis_get=lambda k: "")
    assert line["acted_7d"] == 0
    assert line["reversal_rate_7d"] is None


def test_compute_line_takes_max_of_ledger_and_cap_counters():
    """The Redis estate counters increment BEFORE the best-effort post-act
    ledger emit, so they can exceed the ledger count when an emit was lost —
    the report takes the honest max. A broken Redis degrades to ledger-only."""
    fr = _load_falsifier_report()
    counters = {"cabinet:actfirst:count:2026-07-04:estate": "5"}
    line = fr.compute_line(_fixtured_ledger(), now=NOW,
                           redis_get=lambda k: counters.get(k, ""))
    assert line["acted_7d"] == 5               # counter 5 > ledger 2

    def broken(_key):
        raise RuntimeError("redis down")
    line = fr.compute_line(_fixtured_ledger(), now=NOW, redis_get=broken)
    assert line["acted_7d"] == 2               # degrade, never crash


def test_series_append_is_idempotent_per_date(tmp_path):
    fr = _load_falsifier_report()
    series = tmp_path / "falsifier-series.jsonl"
    assert fr._already_reported(series, "2026-07-04") is False   # missing file
    series.write_text('not-json\n{"date": "2026-07-04", "acted_7d": 0}\n')
    assert fr._already_reported(series, "2026-07-04") is True    # corrupt line skipped
    assert fr._already_reported(series, "2026-07-05") is False
