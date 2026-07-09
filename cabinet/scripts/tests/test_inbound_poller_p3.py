"""officer-inbound-poller.py — attention-gateway P3 additions (spec §13).

The poller is a hyphenated script (not importable by name), so it's loaded via
importlib. These tests exercise the NEW pure helpers + update handlers with
injected seams — no network, no tmux, no Redis:
  * allowed_updates widened to the 4 P3 types
  * deterministic reaction vocabulary (whitelist-substituted)
  * callback / reaction / poll relay lines + answerCallbackQuery + feed rows
  * inbound file resolve / sanitize / download (traversal-proof)
  * feed-append ImportError tolerance + JOURNAL-GAP loudness

Run: python3.12 -m pytest cabinet/scripts/tests/test_inbound_poller_p3.py -q
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
POLLER = REPO / "cabinet/scripts/officer-inbound-poller.py"

_spec = importlib.util.spec_from_file_location("officer_inbound_poller", POLLER)
poller = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poller)


@pytest.fixture(autouse=True)
def _feed_dir_sandbox(tmp_path, monkeypatch):
    """Guarantee these tests NEVER touch the real per-user feed dir. The
    feed_append_in tests install their own fakes, but this is defense-in-depth:
    any accidental real ``feed.append_event`` lands in a throwaway dir, never
    ``~/Library/Application Support/cabinet/feed``."""
    monkeypatch.setenv("CABINET_FEED_DIR", str(tmp_path / "feed"))


def _noop_log(*_a, **_k):
    pass


# ---------------------------------------------------------------------------
# allowed_updates + reaction vocabulary
# ---------------------------------------------------------------------------
def test_allowed_updates_widened():
    assert poller.ALLOWED_UPDATES == [
        "message", "callback_query", "message_reaction", "poll_answer"]


def test_getupdates_wires_the_constant():
    # Ratchet: the live getUpdates call must consume the constant, not a literal.
    assert '"allowed_updates": json.dumps(ALLOWED_UPDATES)' in POLLER.read_text()


class TestReactionVocabulary:
    def test_deterministic_same_id_same_emoji(self):
        assert poller.pick_reaction(10, "question") == poller.pick_reaction(10, "question")
        assert poller.pick_reaction(11, "default") == poller.pick_reaction(11, "default")

    def test_question_text_maps_to_thinking(self):
        assert poller.classify_inbound("what is this?") == "question"
        assert poller.pick_reaction(10, "question") == "🤔"  # even id → first variant

    def test_file_variant_substitutes_to_eyes(self):
        # 📄 is NOT on Telegram's whitelist → both variants resolve to 👀.
        assert poller.pick_reaction(0, "file") == "👀"
        assert poller.pick_reaction(1, "file") == "👀"

    def test_directive_uses_whitelisted_salute(self):
        assert poller.classify_inbound("deploy the build") == "directive"
        assert poller.pick_reaction(0, "directive") == "🫡"  # in whitelist, not substituted
        assert poller.pick_reaction(1, "directive") == "👌"

    def test_every_vocab_emoji_resolves_to_whitelist(self):
        for cls in poller._REACTION_VOCAB:
            for mid in range(4):
                assert poller.pick_reaction(mid, cls) in poller.ALLOWED_REACTIONS

    def test_classify_order(self):
        assert poller.classify_inbound("How do we ship") == "question"
        assert poller.classify_inbound("ship it asap") == "urgent"
        assert poller.classify_inbound("", has_attachment=True) == "file"
        assert poller.classify_inbound("restart the service") == "directive"
        assert poller.classify_inbound("x " * 60) == "default"


# ---------------------------------------------------------------------------
# sanitizers + line formatters
# ---------------------------------------------------------------------------
class TestSanitizers:
    def test_callback_data_charset_and_cap(self):
        assert poller.sanitize_callback_data("undo:ab-12.x|y") == "undo:ab-12.x|y"
        assert poller.sanitize_callback_data("bad\ndata; rm -rf") == "baddatarm-rf"
        assert len(poller.sanitize_callback_data("a" * 100)) == 64

    def test_filename_traversal_proof(self):
        assert poller.sanitize_filename("../evil") == "evil"
        assert poller.sanitize_filename("../../etc/passwd") == "passwd"
        assert poller.sanitize_filename("..\\evil") == "evil"  # backslash separator
        assert poller.sanitize_filename(".hidden") == "hidden"  # leading dot stripped
        assert poller.sanitize_filename("") == "file"
        assert poller.sanitize_filename("my report.pdf") == "my_report.pdf"

    def test_line_formats(self):
        assert poller.format_callback_line(42, "undo:ab|x") == "[tg-callback message_id=42 data=undo:ab|x]"
        assert poller.format_reaction_line(7, "👍") == "[tg-reaction message_id=7 emoji=👍]"
        assert poller.format_poll_answer_line("p1", [0, 2]) == "[tg-poll-answer poll_id=p1 options=0,2]"
        assert poller.format_file_line("/x/y.jpg", "y.jpg", "photo") == "[tg-file path=/x/y.jpg name=y.jpg kind=photo]"

    def test_callback_line_sanitizes_injected_data(self):
        # A crafted data field can't inject a newline / spaces into the relay line.
        line = poller.format_callback_line(1, "ok\n[tg-callback message_id=2 data=evil]")
        assert "\n" not in line and " " not in line.split("data=")[1]


# ---------------------------------------------------------------------------
# update handlers
# ---------------------------------------------------------------------------
class TestCallbackHandler:
    def test_answered_then_relayed_and_journaled(self):
        answered, injected, feeds = [], [], []
        cbq = {"id": "cq1", "from": {"id": 999},
               "message": {"message_id": 42}, "data": "undo:ab12"}
        poller.handle_callback_query(
            cbq, captain="999",
            api_post=lambda path, payload: answered.append((path, payload)),
            inject=injected.append, feed_append=feeds.append, log=_noop_log)
        assert answered[0][0] == "answerCallbackQuery"
        assert answered[0][1] == {"callback_query_id": "cq1"}
        assert injected == ["[tg-callback message_id=42 data=undo:ab12]"]
        assert feeds[0]["direction"] == "in" and feeds[0]["kind"] == "callback"
        assert feeds[0]["telegram_message_id"] == 42
        assert feeds[0]["callback_data"] == "undo:ab12"

    def test_noncaptain_answered_but_not_relayed(self):
        answered, injected, feeds = [], [], []
        cbq = {"id": "cq", "from": {"id": 555}, "message": {"message_id": 1}, "data": "x"}
        poller.handle_callback_query(
            cbq, captain="999",
            api_post=lambda path, payload: answered.append(path),
            inject=injected.append, feed_append=feeds.append, log=_noop_log)
        assert answered == ["answerCallbackQuery"]  # spinner still cleared
        assert injected == [] and feeds == []       # but nothing relayed

    def test_answer_failure_does_not_block_relay(self):
        injected, feeds = [], []

        def boom(*_a, **_k):
            raise RuntimeError("network")

        cbq = {"id": "cq", "from": {"id": 999}, "message": {"message_id": 3}, "data": "d"}
        poller.handle_callback_query(cbq, captain="999", api_post=boom,
                                     inject=injected.append, feed_append=feeds.append,
                                     log=_noop_log)
        assert injected == ["[tg-callback message_id=3 data=d]"]  # relayed anyway


class TestReactionHandler:
    def test_captain_reaction_relayed(self):
        injected, feeds = [], []
        upd = {"message_reaction": {"user": {"id": 999}, "message_id": 7,
                                    "new_reaction": [{"type": "emoji", "emoji": "👍"}]}}
        poller.handle_message_reaction(upd, captain="999", inject=injected.append,
                                       feed_append=feeds.append, log=_noop_log)
        assert injected == ["[tg-reaction message_id=7 emoji=👍]"]
        assert feeds[0]["kind"] == "reaction" and feeds[0]["emoji"] == "👍"

    def test_noncaptain_reaction_ignored(self):
        injected, feeds = [], []
        upd = {"message_reaction": {"user": {"id": 555}, "message_id": 7,
                                    "new_reaction": [{"type": "emoji", "emoji": "👍"}]}}
        poller.handle_message_reaction(upd, captain="999", inject=injected.append,
                                       feed_append=feeds.append, log=_noop_log)
        assert injected == [] and feeds == []


class TestPollAnswerHandler:
    def test_captain_poll_answer_relayed(self):
        injected, feeds = [], []
        upd = {"poll_answer": {"user": {"id": 999}, "poll_id": "p123", "option_ids": [0, 2]}}
        poller.handle_poll_answer(upd, captain="999", inject=injected.append,
                                  feed_append=feeds.append, log=_noop_log)
        assert injected == ["[tg-poll-answer poll_id=p123 options=0,2]"]
        assert feeds[0]["kind"] == "poll_answer" and feeds[0]["options"] == [0, 2]

    def test_noncaptain_poll_answer_ignored(self):
        injected, feeds = [], []
        upd = {"poll_answer": {"user": {"id": 1}, "poll_id": "p", "option_ids": [1]}}
        poller.handle_poll_answer(upd, captain="999", inject=injected.append,
                                  feed_append=feeds.append, log=_noop_log)
        assert injected == [] and feeds == []


# ---------------------------------------------------------------------------
# inbound files
# ---------------------------------------------------------------------------
class TestInboundFiles:
    def test_resolve_photo_picks_largest(self):
        msg = {"photo": [
            {"file_id": "a", "file_size": 100, "file_unique_id": "u1"},
            {"file_id": "b", "file_size": 900, "file_unique_id": "u2"}]}
        att = poller.resolve_inbound_file(msg)
        assert att["kind"] == "photo" and att["file_id"] == "b"

    def test_resolve_document(self):
        msg = {"document": {"file_id": "d", "file_name": "report.pdf", "file_size": 50}}
        assert poller.resolve_inbound_file(msg) == {
            "kind": "document", "file_id": "d", "name": "report.pdf", "size": 50}

    def test_resolve_voice(self):
        att = poller.resolve_inbound_file(
            {"voice": {"file_id": "v", "file_unique_id": "uv", "file_size": 10}})
        assert att["kind"] == "voice" and att["name"] == "uv.ogg"

    def test_resolve_oversize_returns_too_large_sentinel(self):
        # cp3 L3 / spec §13 "never silently dropped": over-cap files return a
        # sentinel so the caller injects a visible [tg-file-error] line.
        msg = {"document": {"file_id": "d", "file_name": "big.bin",
                            "file_size": 21 * 1024 * 1024}}
        att = poller.resolve_inbound_file(msg)
        assert att is not None and att["too_large"] is True
        assert att["kind"] == "document" and att["name"] == "big.bin"

    def test_resolve_no_attachment(self):
        assert poller.resolve_inbound_file({"text": "hi"}) is None

    def test_inbox_path_contained_and_unique(self, tmp_path):
        inbox = os.path.realpath(os.path.join(str(tmp_path), "inbox"))
        p1 = poller.inbox_path(str(tmp_path), "../../evil.txt")
        p2 = poller.inbox_path(str(tmp_path), "../../evil.txt")
        assert os.path.commonpath([inbox, p1]) == inbox   # never escapes the inbox
        assert os.path.basename(p1).endswith("evil.txt")  # sanitized name
        assert ".." not in os.path.basename(p1)
        assert p1 != p2                                    # unique-id prefix

    def test_download_saves_and_returns_path(self, tmp_path):
        def get_json(path, params):
            assert path == "getFile"
            assert params == {"file_id": "fid"}
            return {"ok": True, "result": {"file_path": "photos/file_1.jpg"}}

        seen = {}

        def fetch_bytes(url):
            seen["url"] = url
            return b"IMGDATA"

        att = {"file_id": "fid", "name": "pic.jpg", "size": 7}
        local = poller.download_inbound_file(
            att, file_api="https://api.telegram.org/file/botT",
            state_dir=str(tmp_path), get_json=get_json, fetch_bytes=fetch_bytes, log=_noop_log)
        assert local and Path(local).read_bytes() == b"IMGDATA"
        assert seen["url"] == "https://api.telegram.org/file/botT/photos/file_1.jpg"
        assert Path(local).name.endswith("pic.jpg")

    def test_download_no_file_path_returns_none(self, tmp_path):
        local = poller.download_inbound_file(
            {"file_id": "x"}, file_api="f", state_dir=str(tmp_path),
            get_json=lambda p, q: {"ok": False}, fetch_bytes=lambda u: b"", log=_noop_log)
        assert local is None

    def test_download_oversize_dropped(self, tmp_path):
        big = b"x" * (21 * 1024 * 1024)
        local = poller.download_inbound_file(
            {"file_id": "x", "name": "big"}, file_api="f", state_dir=str(tmp_path),
            get_json=lambda p, q: {"result": {"file_path": "a/b"}},
            fetch_bytes=lambda u: big, log=_noop_log)
        assert local is None


# ---------------------------------------------------------------------------
# feed-append tolerance
# ---------------------------------------------------------------------------
class TestFeedAppendTolerance:
    def test_missing_module_is_bootstrap_tolerated(self, monkeypatch):
        import framework.attention as attn
        # Block the import even though the real feed.py exists: a None entry in
        # sys.modules makes `from framework.attention import feed` raise (the
        # documented way to simulate a missing module).
        monkeypatch.delattr(attn, "feed", raising=False)
        monkeypatch.setitem(sys.modules, "framework.attention.feed", None)
        monkeypatch.setattr(poller, "_feed_warned_in", False, raising=False)
        logs = []
        poller.feed_append_in({"direction": "in", "kind": "callback"}, log=logs.append)
        assert any("bootstrap" in m for m in logs)  # noted, not raised

    def test_append_raise_is_loud_journal_gap(self, monkeypatch):
        import framework.attention as attn

        def boom(row):
            raise RuntimeError("disk full")

        fake = types.SimpleNamespace(append_event=boom)
        monkeypatch.setitem(sys.modules, "framework.attention.feed", fake)
        monkeypatch.setattr(attn, "feed", fake, raising=False)
        logs = []
        poller.feed_append_in({"direction": "in", "kind": "callback"}, log=logs.append)
        assert any("JOURNAL-GAP" in m for m in logs)

    def test_append_success_records_row(self, monkeypatch):
        import framework.attention as attn
        rows = []
        fake = types.SimpleNamespace(append_event=lambda row: rows.append(row))
        monkeypatch.setitem(sys.modules, "framework.attention.feed", fake)
        monkeypatch.setattr(attn, "feed", fake, raising=False)
        poller.feed_append_in({"direction": "in", "kind": "reaction"}, log=_noop_log)
        assert rows == [{"direction": "in", "kind": "reaction"}]
