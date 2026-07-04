"""PRO-4 — gather_signals v2 (profile-driven, file-only). Fixtured tmp vault;
mtimes set explicitly to exercise the as_of/window fencing; no live APIs."""
from __future__ import annotations

import datetime as dt
import os
import urllib.request

import pytest

from framework.acting import run_action_lane as ral
from framework.probes import correlation

AS_OF = dt.datetime(2026, 7, 4, 12, 0, 0, tzinfo=dt.timezone.utc)
RECENT = AS_OF - dt.timedelta(hours=1)
OLD = AS_OF - dt.timedelta(hours=100)      # outside the 72h operational window
ANCIENT = AS_OF - dt.timedelta(hours=1000)
FUTURE = AS_OF + dt.timedelta(hours=1)


def _write(vault, rel, body, *, mtime=RECENT):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    ts = mtime.timestamp()
    os.utime(p, (ts, ts))
    return p


@pytest.fixture
def vault(tmp_path):
    return tmp_path / "vault"


# --- OPERATIONAL sections ----------------------------------------------------

def test_operational_core_sections_present(vault):
    _write(vault, "6-Commitments/owed_by_nate/cmt-1.md", "Nate owes Lisa the licences")
    _write(vault, "2-Meetings/2026-07-03-scrum.md", "PolAds scrum notes")
    _write(vault, "5-Reflections/Decisions/dec-1.md", "Decided: Option B staging")
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "--- OPEN COMMITMENT ref=6-Commitments/owed_by_nate/cmt-1.md ---" in out
    assert "owes Lisa" in out
    assert "--- MEETING ref=2-Meetings/2026-07-03-scrum.md ---" in out
    assert "--- DECISION ref=5-Reflections/Decisions/dec-1.md ---" in out


def test_product_health_alert_filter(vault):
    _write(vault, "9-Codebases/PolAds/health.md",
           "---\nalert: true\nproduct: polads\n---\nProd SyntaxError spike")
    _write(vault, "9-Codebases/STEPhie/health.md",
           "---\nalert: false\nproduct: stephie\n---\nall green")
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "--- PRODUCT HEALTH ref=9-Codebases/PolAds/health.md ---" in out
    assert "SyntaxError spike" in out
    assert "STEPhie/health.md" not in out          # alert:false is dropped


def test_code_section_groups_by_product_cap_2(vault):
    _write(vault, "9-Codebases/A/commits.md", "A commits", mtime=AS_OF - dt.timedelta(hours=1))
    _write(vault, "9-Codebases/A/deployment.md", "A deploy", mtime=AS_OF - dt.timedelta(hours=1))
    _write(vault, "9-Codebases/B/commits.md", "B commits", mtime=AS_OF - dt.timedelta(hours=2))
    _write(vault, "9-Codebases/C/commits.md", "C commits", mtime=AS_OF - dt.timedelta(hours=3))
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "9-Codebases/A/commits.md" in out and "9-Codebases/A/deployment.md" in out
    assert "9-Codebases/B/commits.md" in out
    assert "9-Codebases/C/commits.md" not in out   # 3rd product exceeds the 2-product cap


def test_people_radar_section(vault):
    _write(vault, "3-People/_radar/dennis.md", "Dennis: quiet 30d, worth reconnecting")
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "--- PEOPLE ref=3-People/_radar/dennis.md ---" in out


def test_missing_folders_degrade_to_empty(vault):
    vault.mkdir(parents=True)
    assert ral.gather_signals(AS_OF, vault=vault) == ""     # nothing present → no error


# --- as_of / window fencing --------------------------------------------------

def test_as_of_ceiling_excludes_future_files(vault):
    _write(vault, "6-Commitments/future.md", "not yet", mtime=FUTURE)
    _write(vault, "6-Commitments/now.md", "present", mtime=RECENT)
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "6-Commitments/now.md" in out and "6-Commitments/future.md" not in out


def test_operational_window_excludes_stale(vault):
    _write(vault, "6-Commitments/stale.md", "old", mtime=OLD)     # >72h → out
    _write(vault, "6-Commitments/fresh.md", "new", mtime=RECENT)
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "6-Commitments/fresh.md" in out and "6-Commitments/stale.md" not in out


# --- STRATEGIC profile -------------------------------------------------------

def test_strategic_opportunities_unwindowed_and_status_filtered(vault, monkeypatch):
    # ancient mtime, but OPPORTUNITY is unwindowed → still included on status
    _write(vault, "7-Opportunities/market/o1.md",
           "---\ntype: opportunity\nstatus: new\n---\nBotID reviewer", mtime=ANCIENT)
    _write(vault, "7-Opportunities/research/o3.md",
           "---\nstatus: investigating\n---\nelection calendar", mtime=ANCIENT)
    _write(vault, "7-Opportunities/market/o2.md",
           "---\nstatus: parked\n---\nold idea", mtime=ANCIENT)
    dirs = vault / "directions.yml"
    dirs.write_text("missions:\n  polads: ship v1\n")
    monkeypatch.setattr(ral, "DIRECTIONS_PATH", dirs)
    out = ral.gather_signals(AS_OF, vault=vault, profile="strategic")
    assert "--- OPPORTUNITY ref=7-Opportunities/market/o1.md ---" in out
    assert "election calendar" in out              # investigating included
    assert "o2.md" not in out                      # parked excluded
    assert "--- DIRECTIONS ref=directions.yml ---" in out and "ship v1" in out


def test_strategic_health_is_unfiltered(vault):
    # STRATEGIC health has NO alert filter → an alert:false health note is kept
    _write(vault, "9-Codebases/PolAds/health.md",
           "---\nalert: false\n---\nquiet-but-worth-seeing", mtime=RECENT)
    out = ral.gather_signals(AS_OF, vault=vault, profile="strategic")
    assert "9-Codebases/PolAds/health.md" in out


# --- cid-echo suppression (TI-7 wired into gather) ---------------------------

def test_cid_echo_suppressed_when_own_cid_passed(vault):
    cid = "c" * 32
    _write(vault, "6-Commitments/echo.md",
           "task we created\n\n" + correlation.monday_footer(cid))
    _write(vault, "6-Commitments/real.md", "a genuine open commitment")
    without = ral.gather_signals(AS_OF, vault=vault)
    assert "6-Commitments/echo.md" in without      # no suppression set → present
    with_suppress = ral.gather_signals(AS_OF, vault=vault, suppress_cids=frozenset({cid}))
    assert "6-Commitments/echo.md" not in with_suppress   # our own act, dropped
    assert "6-Commitments/real.md" in with_suppress       # unrelated file survives


# --- file-only contract ------------------------------------------------------

def test_gather_makes_no_network_call(vault, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("gather must be FILE-ONLY — no urllib on the gather path")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    _write(vault, "2-Meetings/m.md", "notes")
    out = ral.gather_signals(AS_OF, vault=vault)   # must not raise
    assert "--- MEETING ref=2-Meetings/m.md ---" in out


def test_default_profile_is_operational(vault):
    _write(vault, "7-Opportunities/market/o1.md", "---\nstatus: new\n---\nidea")
    # operational profile has no OPPORTUNITY section → opportunities absent by default
    assert "OPPORTUNITY" not in ral.gather_signals(AS_OF, vault=vault)
