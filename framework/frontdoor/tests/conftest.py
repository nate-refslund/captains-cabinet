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


@pytest.fixture(autouse=True)
def _killswitch_clear(monkeypatch):
    """Hermetic SEC-3 killswitch seam. channel.py now fails CLOSED on the send
    path: a send with allow_sends() True consults action_exec's ONE killswitch
    reader (``_redis_get_strict`` → Redis ``GET cabinet:killswitch``), and an
    unreachable control plane HALTS (fail-closed). The suite has no Redis, so
    default that reader to "clear" — every existing runtime-send test stays
    green without knowing the gate exists. Same autouse-seam discipline as the
    lessons/feed neutralizers above.

    action_exec's killswitch/caps TESTS always inject their own ``redis_get``
    and never use this default reader, so neutralizing it does not weaken them.
    Tests that DO exercise the killswitch (test_channel_killswitch.py) override
    this per-case — an in-test monkeypatch wins over this baseline."""
    import framework.frontdoor.action_exec as _action_exec
    monkeypatch.setattr(_action_exec, "_redis_get_strict", lambda _key: "")
