"""TI-5 — tests for the digest orchestrator (framework/frontdoor/tell_digest).

Fully fixtured: journal rows / pending proposals / self rows are injected
dicts, Redis is a plain dict via lambdas, the intake enqueue is a recorder.
No live Redis, no ledger, no journal, no clock beyond the frozen ``now``.
"""
from __future__ import annotations

import json

from framework.frontdoor import tell_digest as td

NOW = "2026-07-04T09:00:00Z"
DATE = "2026-07-04"


def _jrow(pid="pid-a", jid="j-1", *, status="executed", canary=False,
          executed_at="2026-07-04T08:00:00Z", ttl="2026-07-06T08:00:00Z", **over):
    row = {"jid": jid, "ts": executed_at, "pid": pid, "step": 0,
           "kind": "monday_task_create", "backend": "monday", "lane": "polads",
           "subject": "subj", "actor": {"kind": "officer", "id": "officer:cos"},
           "action_type": "task_create", "status": status, "canary": canary,
           "created": {"monday_id": "555", "board_id": "9"},
           "payload": {"title": "Fix deploy gate"},
           "executed_at": executed_at, "ttl_expires_at": ttl}
    row.update(over)
    return row


def _awaiting(subject="thread:lisa", ts="2026-07-04T07:00:00Z"):
    return {"ts": ts, "actor": {"kind": "officer", "id": "officer:cos"},
            "lane": "send-1to1-reply", "action": "draft-reply",
            "subject": subject, "refs": [],
            "proposal": {"required": True, "decision": None}}


class _Redis:
    def __init__(self, seed=None):
        self.store = dict(seed or {})
        self.set_calls = []

    def get(self, key):
        return self.store.get(key, "")

    def set(self, key, value, ttl_s):
        self.set_calls.append((key, value, ttl_s))
        self.store[key] = value


class _Intake:
    def __init__(self, fail=False):
        self.items, self.fail = [], fail

    def __call__(self, item):
        if self.fail:
            raise RuntimeError("redis down")
        self.items.append(item)
        return f"id-{len(self.items)}"


# --- gathers ---------------------------------------------------------------------

def test_gather_acted_filters_dead_and_canary_and_expired():
    rows = [
        _jrow(pid="live", jid="j1"),
        _jrow(pid="canary", jid="j2", canary=True),
        _jrow(pid="undone", jid="j3"),
        _jrow(pid="undone", jid="j3", status="reversed"),   # supersedes j3
        _jrow(pid="expired", jid="j4", ttl="2026-07-04T08:59:00Z"),
        _jrow(pid="pendingrow", jid="j5", status="pending", executed_at=None),
    ]
    out = td.gather_acted_rows(now=NOW, journal_rows=rows)
    assert [r["pid"] for r in out] == ["live"]


def test_gather_self_rows_frozen_kinds():
    rows = [
        _jrow(),
        {"op": "freeze", "kind": "monday_task_create", "reason": "undo failed",
         "ts": "t"},
        {"op": "freeze", "kind": "monday_task_create", "reason": "again", "ts": "t2"},
    ]
    out = td.gather_self_rows(journal_rows=rows)
    assert out == [{"type": "frozen", "kind": "monday_task_create",
                    "reason": "again"}]


# --- stable index assignment -------------------------------------------------------

def test_indexes_stable_across_rebuilds_and_never_reused():
    """The wrong-target guard: an act keeps ONE number for its whole window, and
    a new act NEVER takes a number any live manifest already issued — so a reply
    to an OLDER rendered digest can't bind a renumbered act."""
    r = _Redis()
    rows1 = [_jrow(pid="A", jid="j1"), _jrow(pid="B", jid="j2")]
    out1 = td.enqueue_digest(now=NOW, acted_rows=rows1, awaiting_rows=[],
                             watching_rows=[], self_rows=[],
                             redis_get=r.get, redis_set=r.set, enqueue=_Intake())
    assert out1["digest"] is True
    m1 = {it["pid"]: it["index"] for it in out1["manifest"]}
    assert m1 == {"A": 1, "B": 2}

    # PM rebuild same day: A's window closed (dropped), B persists, C is new.
    rows2 = [_jrow(pid="B", jid="j2"), _jrow(pid="C", jid="j3")]
    out2 = td.enqueue_digest(now="2026-07-04T19:30:00Z", acted_rows=rows2,
                             awaiting_rows=[], watching_rows=[], self_rows=[],
                             redis_get=r.get, redis_set=r.set, enqueue=_Intake())
    m2 = {it["pid"]: it["index"] for it in out2["manifest"]}
    assert m2["B"] == 2                    # kept its number
    assert m2["C"] == 3                    # minted ABOVE A's retired 1 — never reused


def test_indexes_carry_over_from_yesterday():
    """An act indexed yesterday and still open today keeps its number in TODAY's
    manifest, so both yesterday's and today's rendered digests bind the same act."""
    seed = {td._DIGEST_KEY_PREFIX + "2026-07-03": json.dumps(
        {"date": "2026-07-03", "next_index": 6,
         "items": [{"index": 5, "pid": "B", "jid": "j2"}]})}
    r = _Redis(seed)
    out = td.enqueue_digest(now=NOW, acted_rows=[_jrow(pid="B", jid="j2"),
                                                 _jrow(pid="D", jid="j4")],
                            awaiting_rows=[], watching_rows=[], self_rows=[],
                            redis_get=r.get, redis_set=r.set, enqueue=_Intake())
    m = {it["pid"]: it["index"] for it in out["manifest"]}
    assert m == {"B": 5, "D": 6}
    today = json.loads(r.store[td._DIGEST_KEY_PREFIX + DATE])
    assert {it["pid"]: it["index"] for it in today["items"]} == {"B": 5, "D": 6}
    assert today["next_index"] == 7


def test_digest_text_uses_the_stable_indexes():
    seed = {td._DIGEST_KEY_PREFIX + DATE: json.dumps(
        {"date": DATE, "next_index": 4,
         "items": [{"index": 3, "pid": "pid-a", "jid": "j-1"}]})}
    r = _Redis(seed)
    intake = _Intake()
    td.enqueue_digest(now=NOW, acted_rows=[_jrow()], awaiting_rows=[],
                      watching_rows=[], self_rows=[],
                      redis_get=r.get, redis_set=r.set, enqueue=intake)
    text = intake.items[0]["payload"]["summary"]
    assert "undo 3" in text and "undo 1" not in text


# --- orchestration invariants ---------------------------------------------------------

def test_manifest_persisted_before_enqueue_with_ttl():
    events = []
    r = _Redis()
    orig_set = r.set

    def tracking_set(key, value, ttl_s):
        events.append("manifest")
        orig_set(key, value, ttl_s)

    def tracking_enqueue(item):
        events.append("enqueue")
        return "id-1"

    out = td.enqueue_digest(now=NOW, acted_rows=[_jrow()], awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            redis_get=r.get, redis_set=tracking_set,
                            enqueue=tracking_enqueue)
    assert out["digest"] is True
    assert events == ["manifest", "enqueue"]     # ordering invariant
    key, _value, ttl = r.set_calls[0]
    assert key == td._DIGEST_KEY_PREFIX + DATE
    assert ttl == 48 * 3600


def test_manifest_write_failure_aborts_no_dead_handles():
    """Fail-closed toward no-tell: indexes that cannot bind must never render."""
    def broken_set(key, value, ttl_s):
        raise RuntimeError("redis unreachable")
    intake = _Intake()
    out = td.enqueue_digest(now=NOW, acted_rows=[_jrow()], awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            redis_get=lambda k: "", redis_set=broken_set,
                            enqueue=intake)
    assert out["digest"] is False and "manifest persist failed" in out["error"]
    assert intake.items == []                    # nothing enqueued


def test_awaiting_only_digest_needs_no_manifest():
    """The no-pid-leak leg: zero acts, open proposals — the digest still rides
    (AWAITING section) and no manifest is written (nothing to index)."""
    r = _Redis()
    intake = _Intake()
    out = td.enqueue_digest(now=NOW, acted_rows=[], awaiting_rows=[_awaiting()],
                            watching_rows=[], self_rows=[],
                            redis_get=r.get, redis_set=r.set, enqueue=intake)
    assert out["digest"] is True
    assert r.set_calls == []
    text = intake.items[0]["payload"]["summary"]
    assert "⚡ AWAITING (1)" in text and "thread:lisa" in text


def test_empty_everything_skips_quietly():
    out = td.enqueue_digest(now=NOW, acted_rows=[], awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            redis_get=lambda k: "", redis_set=None,
                            enqueue=_Intake())
    assert out == {"digest": False, "skipped": "nothing to tell", "date": DATE,
                   "acted": 0, "awaiting": 0}


def test_kill_switch_env(monkeypatch):
    monkeypatch.setenv("CABINET_TELL_DIGEST", "0")
    out = td.enqueue_digest(now=NOW, acted_rows=[_jrow()], awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            redis_get=lambda k: "", redis_set=None,
                            enqueue=_Intake())
    assert out["digest"] is False and "disabled" in out["skipped"]


def test_enqueue_failure_reported_not_raised():
    r = _Redis()
    out = td.enqueue_digest(now=NOW, acted_rows=[_jrow()], awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            redis_get=r.get, redis_set=r.set,
                            enqueue=_Intake(fail=True))
    assert out["digest"] is False and "intake enqueue failed" in out["error"]


def test_item_shape_is_valid_intake_item():
    from framework.frontdoor import intake
    r = _Redis()
    box = _Intake()
    td.enqueue_digest(now=NOW, acted_rows=[_jrow()], awaiting_rows=[_awaiting()],
                      watching_rows=[], self_rows=[],
                      redis_get=r.get, redis_set=r.set, enqueue=box)
    item = box.items[0]
    intake.validate_item(item)                   # raises if malformed
    assert item["source"] == "tell-digest"
    assert item["urgency_tier"] == "batch"
    # all four legs present when rows exist for them
    text = item["payload"]["summary"]
    assert "✅ ACTED (1)" in text and "⚡ AWAITING (1)" in text


# --- e2e: digest manifest → binder undo-by-index -----------------------------------

def test_digest_manifest_binds_undo_by_index_in_binder():
    """The full TI-5→UNDO-2 loop, fixtured: the orchestrator persists the
    manifest; a Captain `undo <n>` reply resolves through THAT manifest,
    re-checks the cabinet:undo pointer, and lands the wrong verdict + reversal
    on the acted pid."""
    from framework.frontdoor import binder_wire

    r = _Redis()
    intake = _Intake()
    jrow = _jrow(pid="pid-a", jid="j-1")
    out = td.enqueue_digest(now=NOW, acted_rows=[jrow], awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            redis_get=r.get, redis_set=r.set, enqueue=intake)
    idx = out["manifest"][0]["index"]
    assert f"undo {idx}" in intake.items[0]["payload"]["summary"]

    # the acted pid has a live undo pointer beside the manifest
    r.store["cabinet:undo:pid-a"] = json.dumps({"pid": "pid-a"})

    emitted, reversed_pids = [], []
    res = binder_wire.handle_captain_update(
        f"undo {idx}", "🗒 Act-then-tell digest — reply `undo <n>`",
        redis_get=r.get,
        emit=lambda **ev: emitted.append(ev),
        reverse=lambda pid: (reversed_pids.append(pid) or
                             {"ok": True, "reversed": [{"step": 0}]}),
        freeze=lambda k, why: None,
        journal_rows_for=lambda pid=None: [jrow],
        read_ledger_fn=lambda: [],
        capture_lesson=lambda **kw: {"lesson_ref": "lesson-001"},
        now=NOW)
    assert res["handled"] is True and res["primary"] == "undo"
    assert res["pid"] == "pid-a"
    assert reversed_pids == ["pid-a"]
    assert emitted and emitted[0]["review"]["verdict"] == "wrong"
