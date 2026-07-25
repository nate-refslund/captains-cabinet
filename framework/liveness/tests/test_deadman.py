"""test_deadman — the Captain-contact dead-man emitter (D1).

WHAT THESE TESTS ASSERT. The property this component exists to deliver is that
a heartbeat fires exactly when real contact happens and NEVER otherwise —
because a heartbeat that fires without contact silently suppresses the alarm it
exists to raise. So the arms below are about firing and not-firing, not about
internal shape.

Every network call goes through the injected ``opener`` seam; nothing here
touches the network. The root conftest additionally points
CABINET_LIVENESS_CONFIG at a non-existent path for the whole session.

Run: /opt/homebrew/bin/python3.12 -m pytest framework/liveness/tests/ -q
"""
from __future__ import annotations

import pytest

from framework.liveness import deadman


class _RecordingOpener:
    """Records every ping. Its CALL COUNT is the assertion that matters: an
    inert path must leave this at zero, since 'returned False' is worthless if
    a request already left the box."""

    def __init__(self, status: int = 200, raises: BaseException | None = None):
        self.calls: list[tuple[str, int]] = []
        self._status = status
        self._raises = raises

    def __call__(self, url: str, timeout: int) -> int:
        self.calls.append((url, timeout))
        if self._raises is not None:
            raise self._raises
        return self._status


def _cfg(**over) -> dict:
    base = {
        "enabled": True,
        "instance_id": "inst-a",
        "base_url": "https://watcher.invalid",
        "timeout_s": 3,
        "events": {deadman.EVENT_CAPTAIN_OUTBOUND: "slug-out",
                   deadman.EVENT_CAPTAIN_INBOUND: "slug-in"},
        "_present": True,
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# The active path — a fully configured deployment actually pings.
# ---------------------------------------------------------------------------
class TestFires:
    def test_configured_outbound_pings_the_watcher(self):
        op = _RecordingOpener()
        res = deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND, cfg=_cfg(), opener=op)
        assert res["emitted"] is True
        assert res["reason"] == "ok"
        assert res["status"] == 200
        assert op.calls == [("https://watcher.invalid/slug-out", 3)]

    def test_inbound_uses_its_own_slug(self):
        op = _RecordingOpener()
        deadman.emit(deadman.EVENT_CAPTAIN_INBOUND, cfg=_cfg(), opener=op)
        assert op.calls[0][0] == "https://watcher.invalid/slug-in"

    def test_trailing_slash_on_base_url_does_not_double(self):
        op = _RecordingOpener()
        deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND,
                     cfg=_cfg(base_url="https://watcher.invalid/"), opener=op)
        assert op.calls[0][0] == "https://watcher.invalid/slug-out"

    def test_timeout_is_clamped_so_a_bad_config_cannot_stall_a_send(self):
        op = _RecordingOpener()
        deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND,
                     cfg=_cfg(timeout_s=9999), opener=op)
        assert op.calls[0][1] == deadman._MAX_TIMEOUT_S


# ---------------------------------------------------------------------------
# INERT — the contract for a fresh clone and for every misconfiguration. Each
# arm asserts NO REQUEST WAS MADE, not merely that the result said False.
# ---------------------------------------------------------------------------
class TestInert:
    def test_unconfigured_deployment_makes_no_call_and_no_error(self, tmp_path):
        """A fresh clone pings nothing: absent config file => inert, no raise."""
        op = _RecordingOpener()
        res = deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND, opener=op,
                           config_path_override=str(tmp_path / "nope.yml"))
        assert res["emitted"] is False
        assert res["reason"] == "no-config"
        assert op.calls == []

    def test_empty_instance_is_inert_even_with_a_slug(self):
        """THE MULTI-TENANCY GUARD. N cabinets share one host, so an unnamed
        instance must never fire — it would ping a neighbour's slug and make a
        DEAD instance indistinguishable from a QUIET one."""
        op = _RecordingOpener()
        res = deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND,
                           cfg=_cfg(instance_id=""), opener=op)
        assert res["emitted"] is False
        assert res["reason"] == "no-instance"
        assert op.calls == []

    def test_malformed_instance_is_inert(self):
        op = _RecordingOpener()
        res = deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND,
                           cfg=_cfg(instance_id="Bad Instance!"), opener=op)
        assert res["reason"] == "bad-instance"
        assert op.calls == []

    def test_missing_slug_for_this_event_is_inert(self):
        op = _RecordingOpener()
        res = deadman.emit(deadman.EVENT_CAPTAIN_INBOUND,
                           cfg=_cfg(events={deadman.EVENT_CAPTAIN_OUTBOUND: "x"}),
                           opener=op)
        assert res["reason"] == "no-slug"
        assert op.calls == []

    def test_no_base_url_is_inert(self):
        op = _RecordingOpener()
        res = deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND,
                           cfg=_cfg(base_url=""), opener=op)
        assert res["reason"] == "no-base-url"
        assert op.calls == []

    def test_disabled_master_switch_is_inert(self):
        op = _RecordingOpener()
        res = deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND,
                           cfg=_cfg(enabled=False), opener=op)
        assert res["reason"] == "disabled"
        assert op.calls == []

    def test_unknown_event_never_pings(self):
        op = _RecordingOpener()
        res = deadman.emit("captain_telepathy", cfg=_cfg(), opener=op)
        assert res["reason"] == "unknown-event"
        assert op.calls == []

    @pytest.mark.parametrize("bad", ["file:///etc/passwd", "gopher://x",
                                     "ftp://host/p", "/relative"])
    def test_non_http_scheme_refused(self, bad):
        """urllib will happily open file:// — the config must never be able to
        turn a heartbeat into a local-file read."""
        op = _RecordingOpener()
        res = deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND,
                           cfg=_cfg(base_url=bad), opener=op)
        assert res["reason"] == "bad-base-url"
        assert op.calls == []

    @pytest.mark.parametrize("bad", ["../../etc/passwd", "a/b", "sl ug",
                                     "sl?ug", "x" * 129])
    def test_path_unsafe_slug_refused_not_escaped(self, bad):
        op = _RecordingOpener()
        res = deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND,
                           cfg=_cfg(events={deadman.EVENT_CAPTAIN_OUTBOUND: bad}),
                           opener=op)
        assert res["reason"] == "bad-slug"
        assert op.calls == []


# ---------------------------------------------------------------------------
# Fail direction — emit runs on the Captain send path, so it must never raise
# and must never report a ping it did not get an answer to.
# ---------------------------------------------------------------------------
class TestNeverRaises:
    def test_transport_failure_is_reported_not_raised(self):
        op = _RecordingOpener(raises=OSError("dns is on fire"))
        res = deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND, cfg=_cfg(), opener=op)
        assert res["emitted"] is False
        assert res["reason"] == "transport-error"
        assert op.calls  # it really did try

    def test_garbage_config_object_does_not_raise(self):
        res = deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND, cfg={"events": None},
                           opener=_RecordingOpener())
        assert res["emitted"] is False

    def test_non_integer_timeout_falls_back_instead_of_raising(self):
        op = _RecordingOpener()
        deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND,
                     cfg=_cfg(timeout_s="soon"), opener=op)
        assert op.calls[0][1] == deadman._DEFAULT_TIMEOUT_S


# ---------------------------------------------------------------------------
# Config parsing — stdlib only (survival contract), degrade to inert.
# ---------------------------------------------------------------------------
class TestParse:
    def test_parses_the_documented_shape(self):
        cfg = deadman.parse_config(
            "enabled: true\n"
            "instance_id: hq\n"
            "base_url: https://w.invalid   # trailing comment\n"
            "timeout_s: 7\n"
            "events:\n"
            "  captain_outbound: abc-123\n"
            "  captain_inbound: def-456\n")
        assert cfg["instance_id"] == "hq"
        assert cfg["base_url"] == "https://w.invalid"
        assert cfg["timeout_s"] == 7
        assert cfg["events"]["captain_outbound"] == "abc-123"
        assert cfg["events"]["captain_inbound"] == "def-456"

    def test_shipped_example_template_parses_and_is_inert(self):
        """The template must be BOTH valid and silent — a shipped default that
        pings would phone a stranger's host on first boot."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        text = (root / "instance/config/liveness.yml.example").read_text()
        cfg = deadman.parse_config(text)
        op = _RecordingOpener()
        for event in deadman.KNOWN_EVENTS:
            res = deadman.emit(event, cfg=cfg, opener=op)
            assert res["emitted"] is False, event
        assert op.calls == []

    def test_unparseable_file_degrades_to_inert(self):
        cfg = deadman.parse_config("\x00 not yaml at all ][")
        op = _RecordingOpener()
        assert deadman.emit(deadman.EVENT_CAPTAIN_OUTBOUND,
                            cfg=cfg, opener=op)["emitted"] is False
        assert op.calls == []

    def test_events_section_ends_at_the_next_top_level_key(self):
        cfg = deadman.parse_config(
            "events:\n  captain_outbound: a\ninstance_id: hq\n")
        assert cfg["events"] == {"captain_outbound": "a"}
        assert cfg["instance_id"] == "hq"


class TestConfigPathSeam:
    def test_env_override_wins(self, monkeypatch):
        monkeypatch.setenv(deadman.CONFIG_ENV, "/tmp/somewhere/liveness.yml")
        assert deadman.config_path() == "/tmp/somewhere/liveness.yml"

    def test_resolves_through_framework_env_when_no_override(self, monkeypatch):
        """Delegation, asserted against the seam rather than a path literal —
        deadman.py must carry no instance path token of its own (the
        layer-separation gate enforces exactly that)."""
        from framework import env

        monkeypatch.delenv(deadman.CONFIG_ENV, raising=False)
        assert deadman.config_path() == env.liveness_config_path()
        assert deadman.config_path().endswith("liveness.yml")
