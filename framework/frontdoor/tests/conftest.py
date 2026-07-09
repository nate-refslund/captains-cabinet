"""frontdoor test conftest — hermetic seams for suite-wide safety.

SIE-1: the binder's DEFAULT lesson capture writes the git-tracked
``shared/interfaces/action-lessons.yml``. Tests that exercise acted/propose
correction verdicts without injecting a fake ``capture_lesson`` would otherwise
append to the REAL repo ledger — so every test in this package gets the lesson
path pointed at a throwaway tmp file. Tests asserting lesson content still
inject their own seam or set the env themselves (monkeypatch wins over this
autouse baseline because both use the same env var).
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _lessons_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ACTION_LESSONS",
                       str(tmp_path / "action-lessons.yml"))
    # P3 (2026-07-09): channel.send/edit now journal every delivered message to
    # the feed (framework.attention.feed) at the transport layer. Any test that
    # sends with allow_sends() True would otherwise append test rows to the REAL
    # per-user feed dir — same hazard as the action-lessons ledger above. Point
    # CABINET_FEED_DIR at a throwaway per-test dir so the journal stays hermetic.
    monkeypatch.setenv("CABINET_FEED_DIR", str(tmp_path / "feed"))
    yield
