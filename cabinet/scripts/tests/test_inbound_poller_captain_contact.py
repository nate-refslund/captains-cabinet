"""officer-inbound-poller.py — the inbound leg of the Captain-contact dead-man.

THE PROPERTY UNDER TEST. Before this change the cabinet could not answer "has
the Captain stopped reaching me?" — the only inbound key held a message ID, and
an ID cannot express staleness no matter who reads it. The watchdog said so in
its own source and fell back to a file-age heuristic. So these arms assert that
a timestamped sibling is now written at the moment of contact, that the ID key
is untouched for its existing reply-threading consumer, and that neither the
stamp nor the off-machine heartbeat can ever cost an inbound DM.

No Redis, no network: subprocess.run and the emitter are injected seams.

Run: python3.12 -m pytest cabinet/scripts/tests/test_inbound_poller_captain_contact.py -q
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
POLLER = REPO / "cabinet/scripts/officer-inbound-poller.py"

_spec = importlib.util.spec_from_file_location("officer_inbound_poller", POLLER)
poller = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poller)


class _Runs:
    """Records redis-cli argv instead of running it."""

    def __init__(self, raises: BaseException | None = None):
        self.calls: list[list[str]] = []
        self._raises = raises

    def __call__(self, argv, **_kw):
        self.calls.append(list(argv))
        if self._raises is not None:
            raise self._raises
        return None

    def sets(self) -> dict[str, str]:
        return {c[4]: c[5] for c in self.calls
                if len(c) >= 6 and c[3] == "SET"}


def _contact(**kw):
    runs = kw.pop("runs", None) or _Runs()
    beats = kw.pop("beats", None)
    if beats is None:
        beats = []
    poller.record_captain_contact(
        "127.0.0.1", kw.pop("mid", 4242), run=runs,
        emit=lambda e: beats.append(e),
        now=kw.pop("now", lambda: "2026-07-25T09:00:00Z"), **kw)
    return runs, beats


class TestTimestampedSibling:
    def test_writes_an_iso_timestamp_sibling_key(self):
        """The one line the watchdog's author was blocked from having."""
        runs, _ = _contact()
        assert runs.sets()["cabinet:last-captain-msg-at"] == "2026-07-25T09:00:00Z"

    def test_leaves_the_id_key_holding_an_id(self):
        """The existing consumer (channel.send reply threading) must not notice
        this change at all — merging the two keys would break threading."""
        runs, _ = _contact(mid=987)
        assert runs.sets()["cabinet:last-captain-msg-id"] == "987"

    def test_both_keys_written_on_one_contact(self):
        runs, _ = _contact()
        keys = runs.sets()
        assert "cabinet:last-captain-msg-id" in keys
        assert "cabinet:last-captain-msg-at" in keys

    def test_stamp_format_is_what_the_watchdog_parses(self):
        """Cross-module contract: the registry parses this with _parse_iso, so a
        format drift here silently disables the inbound check rather than
        failing loudly."""
        import sys

        sys.path.insert(0, str(REPO))
        from framework.watchdog import registry as reg

        runs = _Runs()
        poller.record_captain_contact("h", 1, run=runs, emit=lambda _e: None)
        stamped = runs.sets()["cabinet:last-captain-msg-at"]
        assert reg._parse_iso(stamped) is not None


class TestInboundHeartbeat:
    def test_emits_the_inbound_contact_event(self):
        _, beats = _contact()
        assert beats == ["captain_inbound"]

    def test_wires_the_real_emitter_constant_not_a_literal(self):
        """Ratchet: the live call must consume the emitter's constant, so a
        rename cannot leave the poller pinging a slug nobody watches."""
        src = POLLER.read_text()
        assert "deadman.EVENT_CAPTAIN_INBOUND" in src

    def test_heartbeat_fires_only_on_captain_contact_not_offset_advance(self):
        """Every caller of this function sits inside a `from == captain` branch.
        A heartbeat on bare offset advance would fire for any stranger's update
        and would merely re-report that machinery is alive."""
        src = POLLER.read_text()
        # Exactly one live call site, and it is the set_last_captain_msg_id
        # delegate (which every caller reaches only from a `from == captain`
        # branch) — never the offset-advance path.
        assert src.count("record_captain_contact(redis_host, message_id)") == 1
        assert "record_captain_contact" in src.split(
            "def set_last_captain_msg_id")[1][:900]
        assert "record_captain_contact" not in src.split("def save_offset")[1][:400]


class TestNeverCostsAnInboundDM:
    def test_redis_failure_does_not_raise(self):
        runs = _Runs(raises=OSError("redis-cli missing"))
        _contact(runs=runs)  # must not raise

    def test_emitter_failure_does_not_raise(self):
        def _boom(_e):
            raise RuntimeError("watcher exploded")

        poller.record_captain_contact("h", 1, run=_Runs(), emit=_boom)

    def test_a_failed_id_write_does_not_prevent_the_stamp(self):
        """Independently wrapped: one dead effect must not swallow the others,
        or a partial Redis failure would silently disable silence detection."""

        class _FailFirst:
            def __init__(self):
                self.calls = []

            def __call__(self, argv, **_kw):
                self.calls.append(list(argv))
                if argv[4] == "cabinet:last-captain-msg-id":
                    raise OSError("boom")
                return None

        runs = _FailFirst()
        beats: list[str] = []
        poller.record_captain_contact("h", 5, run=runs,
                                      emit=lambda e: beats.append(e))
        written = [c[4] for c in runs.calls]
        assert "cabinet:last-captain-msg-at" in written
        assert beats == ["captain_inbound"]

    def test_real_emitter_is_inert_when_unconfigured(self, monkeypatch, tmp_path):
        """End-to-end with the REAL emitter: an unconfigured deployment records
        contact with zero outbound traffic."""
        import sys

        sys.path.insert(0, str(REPO))
        from framework.liveness import deadman

        monkeypatch.setenv(deadman.CONFIG_ENV, str(tmp_path / "absent.yml"))
        opened: list = []
        monkeypatch.setattr(deadman, "_default_opener",
                            lambda url, timeout: opened.append(url))
        poller.record_captain_contact("h", 1, run=_Runs())
        assert opened == []
