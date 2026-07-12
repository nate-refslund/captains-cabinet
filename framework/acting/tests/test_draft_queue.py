"""draft_queue — the withdraw/supersede primitive on the queued-draft path
(captain-surface §3.6): removal is journaled with the full record (undo
trail), a gone draft explains itself, ids are validated before touching the
store, and the journal file is user-only."""
import json

import pytest

from framework.acting import draft_queue


class FakeKV:
    """Dict-backed stand-in for the redis store (same three verbs)."""

    def __init__(self, store=None):
        self.store = dict(store or {})

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)

    def keys(self, prefix):
        return [k for k in self.store if k.startswith(prefix)]


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_DRAFT_QUEUE_DIR", str(tmp_path / "drafts"))


def _kv_with(pid="abc123", **extra):
    rec = {"person": "Alice", "slug": "alice", "channel": "email",
           "draft": "Hi Alice — here is the plan.", **extra}
    return FakeKV({f"cabinet:draft:{pid}": json.dumps(rec)}), rec


def test_withdraw_removes_record_and_journals_full_undo_trail():
    kv, rec = _kv_with()
    res = draft_queue.withdraw("abc123", "no longer needed",
                               actor="test", kv=kv)
    assert res["ok"] is True and res["kind"] == "withdraw"
    assert kv.store == {}  # removed from the store
    rows = draft_queue.journal_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "withdraw" and row["pid"] == "abc123"
    assert row["reason"] == "no longer needed" and row["actor"] == "test"
    # The FULL record rides the journal row — that is the undo trail.
    assert row["record"]["draft"] == rec["draft"]
    assert row["record"]["slug"] == "alice"


def test_supersede_links_the_newer_draft():
    kv, _ = _kv_with(pid="old111")
    res = draft_queue.supersede("old111", "new222", kv=kv)
    assert res["ok"] is True and res["kind"] == "supersede"
    assert res["superseded_by"] == "new222"
    row = draft_queue.journal_rows()[-1]
    assert row["kind"] == "supersede" and row["superseded_by"] == "new222"


def test_withdrawal_of_returns_the_honest_reason():
    kv, _ = _kv_with(pid="abc123")
    draft_queue.withdraw("abc123", "you already replied yourself",
                         actor="draft-reconcile", kv=kv)
    w = draft_queue.withdrawal_of("abc123")
    assert w is not None
    assert w["reason"] == "you already replied yourself"
    assert draft_queue.withdrawal_of("nothere") is None


def test_withdraw_is_idempotent_and_reports_the_prior_row():
    kv, _ = _kv_with(pid="abc123")
    assert draft_queue.withdraw("abc123", "first", kv=kv)["ok"] is True
    res2 = draft_queue.withdraw("abc123", "second", kv=kv)
    assert res2["ok"] is False and res2.get("already_withdrawn") is True
    assert res2["prior"]["reason"] == "first"
    # Only the first removal journaled a removal row.
    assert len([r for r in draft_queue.journal_rows()
                if r["kind"] == "withdraw"]) == 1


def test_missing_draft_is_an_honest_error():
    res = draft_queue.withdraw("zzz999", "whatever", kv=FakeKV())
    assert res["ok"] is False and "no queued draft" in res["error"]


def test_invalid_ids_are_refused_before_touching_the_store():
    # Allow-list validation: anything outside [A-Za-z0-9_-]{1,64} is refused.
    for bad in ("", "a b", "x*y", "k\nv", "α", "a" * 65):
        res = draft_queue.withdraw(bad, "r", kv=FakeKV())
        assert res["ok"] is False and "invalid" in res["error"]
    res = draft_queue.supersede("good1", "bad id", kv=FakeKV())
    assert res["ok"] is False and "invalid" in res["error"]


def test_pending_lists_records_and_skips_garbage():
    kv = FakeKV({
        "cabinet:draft:aaa111": json.dumps({"slug": "a", "draft": "x"}),
        "cabinet:draft:bbb222": "not-json{{{",
        "cabinet:draft:bad id": json.dumps({"slug": "c"}),
    })
    rows = draft_queue.pending(kv=kv)
    assert [r["pid"] for r in rows] == ["aaa111"]
    assert rows[0]["slug"] == "a"


def test_journal_fire_cancel_row_is_found_by_withdrawal_of():
    verdict = {"reason": "captain-already-replied",
               "captain_reason": "Not sent — you already replied to Alice "
                                 "yourself after this draft was written.",
               "checks": {"captain_replied_since": True}}
    draft_queue.journal_fire_cancel("fff000", {"slug": "alice"}, verdict)
    w = draft_queue.withdrawal_of("fff000")
    assert w is not None and w["kind"] == "fire-cancel"
    assert "you already replied" in w["captain_reason"]


def test_journal_file_is_user_only():
    kv, _ = _kv_with()
    draft_queue.withdraw("abc123", "perm check", kv=kv)
    mode = draft_queue.journal_path().stat().st_mode & 0o777
    assert mode & 0o077 == 0, f"journal is group/world accessible: {oct(mode)}"
