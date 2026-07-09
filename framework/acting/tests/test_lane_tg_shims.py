"""The three one-door lane shims (cp3 test gap): every _tg poster now routes
through channel.send and must be LOUD on anything non-sent — including
blocked-dev (H1/H2: a production process missing CABINET_ENV=runtime must
page, never silently blackhole cards while ledger rows record them)."""
import os

import pytest

# run_draft_lane reads its telegram env at IMPORT time (module constants) —
# provide inert values so this file collects standalone, not only under the
# tree conftest that exports them.
os.environ.setdefault("TELEGRAM_COS_TOKEN", "test-token")
os.environ.setdefault("CAPTAIN_TELEGRAM_ID", "1")

from framework.acting import run_action_lane as ral  # noqa: E402
from framework.acting import run_draft_lane as rdl  # noqa: E402
from framework.frontdoor import action_exec as ae  # noqa: E402


SHIMS = [(ral, "_tg"), (rdl, "_tg"), (ae, "_tg_send")]


@pytest.mark.parametrize("mod,fn", SHIMS)
def test_sent_status_passes(monkeypatch, mod, fn):
    calls = []
    monkeypatch.setattr("framework.frontdoor.channel.send",
                        lambda text, **kw: calls.append((text, kw)) or
                        {"status": "sent", "sent": True, "response": {"message_id": 7},
                         "message_ids": [7]})
    getattr(mod, fn)("card text")
    assert calls and calls[0][0] == "card text"
    assert "kind" in (calls[0][1].get("feed_meta") or {})


@pytest.mark.parametrize("mod,fn", SHIMS)
def test_blocked_dev_raises_loudly(monkeypatch, mod, fn):
    monkeypatch.setattr("framework.frontdoor.channel.send",
                        lambda text, **kw: {"status": "blocked-dev", "sent": False})
    with pytest.raises(RuntimeError, match="CABINET_ENV=runtime"):
        getattr(mod, fn)("card text")


@pytest.mark.parametrize("mod,fn", SHIMS)
def test_error_status_raises(monkeypatch, mod, fn):
    monkeypatch.setattr("framework.frontdoor.channel.send",
                        lambda text, **kw: {"status": "error", "sent": False,
                                            "error": "telegram HTTP 400"})
    with pytest.raises(RuntimeError, match="channel send failed"):
        getattr(mod, fn)("card text")
