"""draft_reconcile — the reconciliation consumer (captain-surface §3.6):
queued drafts are reconciled against the captain's ACTUAL outbound via the
sources seam; honest-empty when no source is bound; conservative by default
(only a positive captain-replied withdraws)."""
import json

import pytest

from framework.acting import draft_queue, draft_reconcile
from framework.sources import NullPersonalSource


class FakeKV:
    def __init__(self, store=None):
        self.store = dict(store or {})

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)

    def keys(self, prefix):
        return [k for k in self.store if k.startswith(prefix)]


class FakeSource:
    """Per-slug scripted answers for the two probes."""

    def __init__(self, replied=None, awaiting=None, available=True):
        self.replied = dict(replied or {})
        self.awaiting = dict(awaiting or {})
        self._available = available

    def available(self):
        return self._available

    def captain_replied_since(self, slug, when):
        return self.replied.get(slug)

    def still_awaiting(self, slug, hours=72):
        return self.awaiting.get(slug)


def _store(*recs):
    store = {}
    for pid, rec in recs:
        store[f"cabinet:draft:{pid}"] = json.dumps(rec)
    return FakeKV(store)


def _rec(slug, person=None, **extra):
    return {"slug": slug, "person": person or slug.title(),
            "draft": f"draft for {slug}", "lane": "send-1to1-reply",
            "queued_ts": "2026-07-10T08:00:00Z", **extra}


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_DRAFT_QUEUE_DIR", str(tmp_path / "drafts"))


def test_unbound_source_is_honest_empty_and_touches_nothing():
    kv = _store(("aaa111", _rec("alice")))
    res = draft_reconcile.reconcile_queue(source=NullPersonalSource(), kv=kv)
    assert res["status"] == "source-unbound"
    assert res["checked"] == 0 and res["withdrawn"] == 0
    assert len(kv.store) == 1                     # nothing removed
    assert draft_queue.journal_rows() == []        # nothing journaled


def test_captain_outbound_withdraws_the_matching_draft_only():
    kv = _store(("aaa111", _rec("alice", person="Alice")),
                ("bbb222", _rec("bob")))
    src = FakeSource(replied={"alice": True, "bob": None})
    res = draft_reconcile.reconcile_queue(source=src, kv=kv)
    assert res["status"] == "ok" and res["checked"] == 2
    assert res["withdrawn"] == 1 and res["withdrawn_pids"] == ["aaa111"]
    assert "cabinet:draft:aaa111" not in kv.store   # retired
    assert "cabinet:draft:bbb222" in kv.store       # untouched
    row = draft_queue.withdrawal_of("aaa111")
    assert row is not None and row["actor"] == "draft-reconcile"
    # Plain reason, names the person (it can be echoed back to the captain).
    assert "Alice" in row["reason"] and "replied" in row["reason"]


def test_resolved_thread_alone_does_not_withdraw_by_default():
    kv = _store(("ccc333", _rec("dana")))
    src = FakeSource(replied={"dana": None}, awaiting={"dana": False})
    res = draft_reconcile.reconcile_queue(source=src, kv=kv)
    assert res["withdrawn"] == 0
    assert res["corroborated_resolved"] == 1
    assert "cabinet:draft:ccc333" in kv.store


def test_resolved_thread_withdraws_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("CABINET_RECONCILE_ON_RESOLVED", "1")
    kv = _store(("ccc333", _rec("dana", person="Dana")))
    src = FakeSource(replied={"dana": None}, awaiting={"dana": False})
    res = draft_reconcile.reconcile_queue(source=src, kv=kv)
    assert res["withdrawn"] == 1
    assert "cabinet:draft:ccc333" not in kv.store
    assert "handled or closed" in draft_queue.withdrawal_of("ccc333")["reason"]


def test_missing_queued_ts_never_probes_with_a_fabricated_clock():
    rec = _rec("lisa")
    del rec["queued_ts"]
    kv = _store(("ddd444", rec))

    class Exploding(FakeSource):
        def captain_replied_since(self, slug, when):  # must not be reached
            raise AssertionError("probed without a queue moment")

    res = draft_reconcile.reconcile_queue(
        source=Exploding(awaiting={"lisa": None}), kv=kv)
    assert res["withdrawn"] == 0
    assert "cabinet:draft:ddd444" in kv.store


def test_a_probe_error_leaves_the_draft_queued():
    kv = _store(("eee555", _rec("jakob")))

    class Flaky(FakeSource):
        def captain_replied_since(self, slug, when):
            raise RuntimeError("estate hiccup")

        def still_awaiting(self, slug, hours=72):
            raise RuntimeError("estate hiccup")

    res = draft_reconcile.reconcile_queue(source=Flaky(), kv=kv)
    assert res["status"] == "ok" and res["withdrawn"] == 0
    assert "cabinet:draft:eee555" in kv.store
