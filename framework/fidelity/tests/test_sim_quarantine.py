"""SIE-7 — verdict_sim quarantine. The safety invariant that lets ~100 replay
simulations run without ANY sim-generated event contaminating the live
graduation / breaker / cell math Ada's real verdicts feed.

The fence is a single structural check at the write chokepoint: an event's sim
marker MUST agree with the target dir's '-sim' suffix. These tests pin both
directions of that fence, the emit-time stamping, the validator rule, the
read-side exclusion, and the CI invariant (zero sim rows in a live dir).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.fidelity.consequence import (
    SCHEMA,
    ConsequenceValidationError,
    SimQuarantineError,
    validate_consequence,
    emit_consequence,
    read_ledger,
    _sim_mode,
)


def _ev(**overrides):
    base = {
        "ts": "2026-06-18T08:00:00+00:00",
        "actor": {"kind": "officer", "id": "cos"},
        "lane": "bakery",
        "action": "auto-closed-commitment",
        "subject": "thread-abc",
        "refs": ["msg-1"],
    }
    base.update(overrides)
    return base


def _live(monkeypatch, tmp_path):
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    d = tmp_path / "events"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    return d


def _sim(monkeypatch, tmp_path):
    monkeypatch.setenv("CABINET_SIM_MODE", "1")
    d = tmp_path / "events-sim"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(d))
    return d


def _rows(d):
    out = []
    for f in sorted(d.glob("consequence-events-*.jsonl")):
        out += [json.loads(ln) for ln in f.read_text().splitlines() if ln.strip()]
    return out


# --- flag -------------------------------------------------------------------

def test_sim_mode_off_by_default(monkeypatch):
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    assert _sim_mode() is False
    monkeypatch.setenv("CABINET_SIM_MODE", "1")
    assert _sim_mode() is True
    monkeypatch.setenv("CABINET_SIM_MODE", "0")
    assert _sim_mode() is False


# --- happy paths ------------------------------------------------------------

def test_sim_emit_stamps_marker_and_lands_in_sim_dir(monkeypatch, tmp_path):
    d = _sim(monkeypatch, tmp_path)
    ev = emit_consequence(**_ev())
    assert ev["sim"] is True
    rows = _rows(d)
    assert len(rows) == 1 and rows[0]["sim"] is True


def test_live_emit_carries_no_sim_marker(monkeypatch, tmp_path):
    d = _live(monkeypatch, tmp_path)
    ev = emit_consequence(**_ev())
    assert "sim" not in ev
    assert _rows(d) and "sim" not in _rows(d)[0]


# --- the fence: both directions refuse ---------------------------------------

def test_sim_marked_row_refused_at_live_dir(monkeypatch, tmp_path):
    # sim MODE but the dir is a live (non '-sim') dir → sim can never write live
    monkeypatch.setenv("CABINET_SIM_MODE", "1")
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    with pytest.raises(SimQuarantineError, match="quarantine fence"):
        emit_consequence(**_ev())
    # nothing was written
    assert not list((tmp_path / "events").glob("*.jsonl")) if (tmp_path / "events").exists() else True


def test_live_row_refused_at_sim_dir(monkeypatch, tmp_path):
    # live MODE but the dir is '-sim' → the sim ledger stays unambiguously all-sim
    monkeypatch.delenv("CABINET_SIM_MODE", raising=False)
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events-sim"))
    with pytest.raises(SimQuarantineError, match="quarantine fence"):
        emit_consequence(**_ev())


# --- read-side exclusion (defense in depth) ---------------------------------

def test_live_read_excludes_planted_sim_row(monkeypatch, tmp_path):
    d = _live(monkeypatch, tmp_path)
    d.mkdir(parents=True)
    # plant one live row and one (illegitimately co-located) sim row by hand
    f = d / "consequence-events-2026-06-18.jsonl"
    f.write_text(
        json.dumps(_ev(subject="live-one")) + "\n"
        + json.dumps(_ev(subject="sim-leak", sim=True)) + "\n"
    )
    subjects = {e["subject"] for e in read_ledger()}
    assert subjects == {"live-one"}          # the sim row is dropped for live consumers


def test_sim_read_includes_sim_rows(monkeypatch, tmp_path):
    d = _sim(monkeypatch, tmp_path)
    emit_consequence(**_ev(subject="sim-one"))
    subjects = {e["subject"] for e in read_ledger()}
    assert subjects == {"sim-one"}           # a sim process is the legit reader


# --- validator --------------------------------------------------------------

def test_validator_accepts_sim_true_and_omitted():
    validate_consequence(_ev(sim=True))
    validate_consequence(_ev())              # omitted is fine


@pytest.mark.parametrize("bad", [False, "true", 1, None, 0])
def test_validator_rejects_non_true_sim(bad):
    with pytest.raises(ConsequenceValidationError, match="sim"):
        validate_consequence(_ev(sim=bad))


# --- schema-of-record + CI invariant ----------------------------------------

def test_schema_declares_sim_const_true():
    sim_prop = SCHEMA["properties"]["sim"]
    assert sim_prop["const"] is True         # present-and-true only, never false
    assert set(sim_prop) <= {"const", "description"}
    assert SCHEMA["additionalProperties"] is False


def test_ci_invariant_zero_sim_rows_in_live_dir(monkeypatch, tmp_path):
    # Emit a batch of live events; the CI invariant is: a live event dir holds
    # ZERO sim-marked rows. (The fence guarantees it; this is the assertion a CI
    # job runs against the real live dir.)
    d = _live(monkeypatch, tmp_path)
    for i in range(5):
        emit_consequence(**_ev(subject=f"s{i}"))
    sim_rows = [r for r in _rows(d) if r.get("sim")]
    assert sim_rows == []
