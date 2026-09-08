"""The briefing's gap line — A3.3, every arm including the degenerate ones.

WHAT THIS FILE IS FOR. `run_briefing._gaps_notice` is the card half of the two
gap kinds nobody in the Cabinet can close for itself: `authority` (a permission
only the Captain can grant) and `information` (a fact only he has). Both are
recorded SURFACE-ONLY — never proposed, never DM'd — so before this line the
whole delivery path for them was a page he had to think to visit. A3.3 says the
card carries it too, never `/gaps` alone.

It ends in a blanket `except Exception: return ""`, which is right and is also
a total fail-open — the shape this program has paid for repeatedly. So the
degenerate arms below name what must NOT be produced as carefully as the live
ones name what must.

Fully fixtured: a tmp event ledger, no clock, no network, no subprocess.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.frontdoor import run_briefing
from framework.learning import capability_gaps


@pytest.fixture(autouse=True)
def ledger(tmp_path, monkeypatch):
    """Point the REAL emitter at a throwaway ledger."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CABINET_PRODUCT_SLUG", raising=False)
    return tmp_path / "events"


def _gap(kind: str, need: str):
    return capability_gaps.record_gap(
        need, kind=kind, evidence="", recorded_by="test", actor="test",
    )


# ---------------------------------------------------------------------------
# The degenerate ends
# ---------------------------------------------------------------------------


def test_no_gaps_says_nothing():
    """An empty ledger is silence, never "nothing needs you"."""
    assert run_briefing._gaps_notice() == ""


def test_an_unreadable_ledger_says_nothing(monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("the ledger is not readable")

    monkeypatch.setattr(capability_gaps, "project_gaps", _boom)
    assert run_briefing._gaps_notice() == ""


def test_the_other_kinds_are_not_his_to_answer():
    """`skill` resolves itself when a role appears; `tool`/`integration`
    already reach him as proposals. Only the two he alone can close count."""
    _gap("skill", "no holder on the roster for `t` of `o`")
    _gap("tool", "read the billing ledger")
    _gap("procedure", "how to close the month")

    assert run_briefing._gaps_notice() == ""


def test_a_closed_gap_stops_counting():
    gap = _gap("authority", "permission to publish the release notes")
    assert run_briefing._gaps_notice() != ""

    capability_gaps.resolve_gap(gap["gap_id"], "granted")
    assert run_briefing._gaps_notice() == ""


# ---------------------------------------------------------------------------
# The live arms
# ---------------------------------------------------------------------------


def test_one_authority_gap_reads_singular():
    _gap("authority", "permission to publish the release notes")
    line = run_briefing._gaps_notice()
    assert line == (
        "1 thing is waiting on a permission only you can give — see the gaps page"
    )


def test_two_authority_gaps_read_plural():
    _gap("authority", "permission to publish the release notes")
    _gap("authority", "permission to sign the renewal")
    assert run_briefing._gaps_notice().startswith("2 things are waiting on a permission")


def test_one_information_gap():
    _gap("information", "which of the two dates is the real deadline")
    assert run_briefing._gaps_notice() == (
        "1 thing is waiting on a fact only you have — see the gaps page"
    )


def test_both_kinds_are_counted_separately():
    _gap("authority", "permission to publish the release notes")
    _gap("information", "which of the two dates is the real deadline")
    line = run_briefing._gaps_notice()
    assert "1 thing is waiting on a permission only you can give" in line
    assert "1 on a fact only you have" in line


def test_the_line_carries_no_need_text():
    """Counts only. A gap row is written by whatever hit the wall, and the
    card surface does not carry payload text from elsewhere."""
    _gap("authority", "permission to email the acme-widget customer list")
    line = run_briefing._gaps_notice()
    assert "acme-widget" not in line
    assert "customer list" not in line


# ---------------------------------------------------------------------------
# The wiring — the sentence has to reach the card
# ---------------------------------------------------------------------------


def test_the_headline_carries_the_gap_line():
    """Without this the notice could be perfect and never reach a surface."""
    _gap("authority", "permission to publish the release notes")
    head = run_briefing._plain_headline({"items": []}, None)
    assert "waiting on a permission only you can give" in head


def test_the_headline_is_unharmed_when_no_gap_is_his():
    head = run_briefing._plain_headline({"items": []}, None)
    assert "gaps page" not in head
    assert head.endswith(".")
