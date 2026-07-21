"""Hermetic seams for the comms test suite.

The comms MCP server reaches the Captain THROUGH the front door
(framework/frontdoor/channel.py), whose send path now fails CLOSED on the SEC-3
killswitch: a send consults action_exec's one killswitch reader
(``_redis_get_strict`` → Redis ``GET cabinet:killswitch``), and an unreachable
control plane HALTS (fail-closed). This suite has no Redis, so an unseamed
reader would read "unreachable" and (correctly, for production) refuse every
send — silently breaking the observe-doorway e2e that asserts reply/react
DELIVER. Default the reader to "clear" so those runtime-send tests stay green
without knowing the gate exists. Same autouse-seam discipline as
framework/frontdoor/tests/conftest.py; a test that wants to exercise the
killswitch overrides this per-case (an in-test monkeypatch wins).
"""
import pytest


@pytest.fixture(autouse=True)
def _killswitch_clear(monkeypatch):
    import framework.frontdoor.action_exec as _action_exec
    monkeypatch.setattr(_action_exec, "_redis_get_strict", lambda _key: "")
