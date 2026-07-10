"""SOV-5 — posture-aware brakes: caps→alarms (D11), unfreeze + machine-origin
auto-thaw, silence⇒content-audit forcing (D12), freeze-origin tags.

Hermetic like the TI-7 suite: tmp journal/events/root dirs, dict-backed fake
Redis, fake monday/osascript transports, injected canary/audit seams — no live
backend, no live LLM. The PRE-EXISTING test files pin guardian byte-identity;
this file additionally asserts posture=None ≡ posture="guardian" dict-for-dict
on the caps surface and that the guardian silence path never probes.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from framework.frontdoor import action_undo as au
from framework.frontdoor import actfirst_canary as ac

_WORKTREE = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _worktree_modules(monkeypatch):
    """Pin THIS checkout's lazily-imported subpackages. `framework` is a
    namespace package and `run_draft_lane` (imported at collection by the
    acting tests) hard-prepends the LIVE checkout onto sys.path — so a
    not-yet-imported `framework.events` / `framework.authority` would resolve
    to the live repo, whose emitter predates SOV-1's cap_alarm/kind_unfrozen
    event types (and which has no needs.py at all). Evict a foreign module
    subtree for the duration (monkeypatch restores it after)."""
    monkeypatch.syspath_prepend(str(_WORKTREE))
    for pkg, probe in (("framework.events", "framework.events.emitter"),
                       ("framework.authority", "framework.authority.needs")):
        mod = importlib.import_module(probe)
        if not str(getattr(mod, "__file__", "")).startswith(str(_WORKTREE)):
            for name in [n for n in list(sys.modules)
                         if n == pkg or n.startswith(pkg + ".")]:
                monkeypatch.delitem(sys.modules, name)
            mod = importlib.import_module(probe)
        assert str(mod.__file__).startswith(str(_WORKTREE))
    yield


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """Tmp undo journal + events + cabinet root; never touch a live Redis, a
    live Postgres, or a real needs ledger (CABINET_ROOT points at tmp)."""
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path / "root"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    monkeypatch.delenv("CABINET_POSTURE", raising=False)
    for mod in (au, ac):
        monkeypatch.setattr(mod, "_default_redis_set", lambda *a, **k: None)
        monkeypatch.setattr(mod, "_default_redis_get", lambda *a, **k: "")
        monkeypatch.setattr(mod, "_default_redis_del", lambda *a, **k: None)
    monkeypatch.setattr(ac, "_default_redis_incr", lambda *a, **k: "1")
    monkeypatch.setattr(ac, "_default_redis_expire", lambda *a, **k: None)
    yield


def _events(tmp_path, event_type=None):
    out = []
    for f in sorted((tmp_path / "events").glob("events-*.jsonl")):
        for line in f.read_text().splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type is None or ev.get("event_type") == event_type:
                out.append(ev)
    return out


def _mk_counter():
    store = {}
    def inc(k):
        store[k] = store.get(k, 0) + 1
        return str(store[k])
    return store, inc


def _acted(action_type, ts, *, verdict=None, source=None, lane="bakery"):
    ev = {"ts": ts, "actor": {"kind": "officer", "id": "officer:cos"}, "lane": lane,
          "action": "acted:" + action_type, "subject": "s-" + ts,
          "action_type": action_type, "refs": [],
          "proposal": {"required": False, "decision": None},
          "outcome": {"status": "unknown"}}
    if verdict:
        rev = {"verdict": verdict}
        if source:
            rev["source"] = source
        ev["review"] = rev
    return ev


class FakeMonday:
    def __init__(self, columns=None):
        self.calls = []
        self.columns = columns or {}

    def __call__(self, query, variables):
        self.calls.append((query, variables))
        if "items(ids" in query.replace(" ", ""):
            cols = variables.get("cols") or []
            return {"items": [{"column_values": [
                {"id": c, "text": (self.columns.get(c) or {}).get("text"),
                 "value": (self.columns.get(c) or {}).get("value")} for c in cols]}]}
        return {"create_item": {"id": "9001"}, "create_update": {"id": "u1"},
                "archive_item": {"id": "9001"}, "delete_update": {"id": "u1"},
                "change_column_value": {"id": "9001"}}


def _fake_osa(cmd):
    src = cmd[2] if len(cmd) > 2 else ""
    if "make new event" in src:
        return "ok:Cabinet:UID-CANARY"
    return "ok"


CAPS = {"estate": 40, "per_kind": 2}


# --- caps: guardian byte-identity --------------------------------------------

def test_caps_posture_none_and_guardian_byte_identical():
    _, inc_a = _mk_counter()
    _, inc_b = _mk_counter()
    store = {}
    rset = lambda k, v, ttl: store.__setitem__(k, v)
    rget = lambda k: store.get(k, "")
    none_seq = [ac.incr_and_check("task_create", redis_incr=inc_a,
                                  redis_expire=lambda *a: None, caps=CAPS)
                for _ in range(4)]
    guard_seq = [ac.incr_and_check("task_create", redis_incr=inc_b,
                                   redis_expire=lambda *a: None, caps=CAPS,
                                   posture="guardian", hard_multiplier=10,
                                   redis_get=rget, redis_set=rset)
                 for _ in range(4)]
    assert none_seq == guard_seq                       # dict-for-dict identical
    assert none_seq[2]["ok"] is False
    assert none_seq[2]["reason"] == "per-kind cap 2/day exceeded"   # exact string
    # read-only peek parity too
    cget = lambda k: "3"
    a = ac.cap_check("task_create", redis_get=cget, caps=CAPS)
    b = ac.cap_check("task_create", redis_get=cget, caps=CAPS, posture="guardian")
    assert a == b and a["ok"] is False and a["reason"] == "per-kind cap reached"


def test_guardian_never_alarms_never_freezes_below_hard(tmp_path):
    _, inc = _mk_counter()
    for _ in range(6):                                 # over cap, under cap×10
        ac.incr_and_check("task_create", redis_incr=inc,
                          redis_expire=lambda *a: None, caps=CAPS,
                          posture="guardian", hard_multiplier=10)
    assert _events(tmp_path, "cap_alarm") == []
    assert au.is_frozen("task_create") is False


# --- caps: sovereign alarm + hard-stop + fail-closed --------------------------

def test_sovereign_cap_alarm_proceeds_and_emits_once_per_day(tmp_path):
    _, inc = _mk_counter()
    store = {}
    rset = lambda k, v, ttl: store.__setitem__(k, v)
    rget = lambda k: store.get(k, "")
    out = [ac.incr_and_check("task_create", redis_incr=inc,
                             redis_expire=lambda *a: None, caps=CAPS,
                             posture="sovereign", hard_multiplier=3,
                             redis_get=rget, redis_set=rset,
                             now="2026-07-04T10:00:00Z")
           for _ in range(6)]
    assert out[0]["ok"] and out[1]["ok"] and "alarm" not in out[0]
    for r in out[2:]:                                  # kc 3..6: over cap, proceed
        assert r["ok"] is True and "per-kind cap exceeded" in r["alarm"]
    alarms = _events(tmp_path, "cap_alarm")
    assert len(alarms) == 1                            # once per kind per day
    assert alarms[0]["payload"]["kind"] == "task_create"
    assert store.get("cabinet:actfirst:capalarm:2026-07-04:task_create")
    assert au.is_frozen("task_create") is False        # alarm never freezes


def test_sovereign_hard_stop_freezes_and_blocks():
    _, inc = _mk_counter()
    store = {}
    rset = lambda k, v, ttl: store.__setitem__(k, v)
    rget = lambda k: store.get(k, "")
    last = None
    for _ in range(7):                                 # kc 7 > 2×3 = hard-stop
        last = ac.incr_and_check("task_create", redis_incr=inc,
                                 redis_expire=lambda *a: None, caps=CAPS,
                                 posture="sovereign", hard_multiplier=3,
                                 redis_get=rget, redis_set=rset)
    assert last["ok"] is False and last["frozen"] is True
    assert "runaway hard-stop" in last["reason"]
    assert au.is_frozen("task_create", redis_get=rget) is True


def test_guardian_hard_stop_freezes_but_keeps_todays_block_string():
    _, inc = _mk_counter()
    store = {}
    rset = lambda k, v, ttl: store.__setitem__(k, v)
    rget = lambda k: store.get(k, "")
    last = None
    for _ in range(7):
        last = ac.incr_and_check("task_create", redis_incr=inc,
                                 redis_expire=lambda *a: None, caps=CAPS,
                                 posture="guardian", hard_multiplier=3,
                                 redis_get=rget, redis_set=rset)
    # the return is TODAY's exact block dict — the freeze is the only addition
    assert last == {"ok": False, "kind": "task_create", "kind_count": 7,
                    "estate_count": 7, "reason": "per-kind cap 2/day exceeded"}
    assert au.is_frozen("task_create", redis_get=rget) is True


def test_unreadable_counter_blocks_both_postures():
    def boom(_k):
        raise RuntimeError("redis down")
    outs = [ac.incr_and_check("task_create", redis_incr=boom,
                              redis_expire=lambda *a: None, caps=CAPS,
                              posture=p, hard_multiplier=3)
            for p in (None, "guardian", "sovereign")]
    assert outs[0] == outs[1] == outs[2]
    assert outs[0]["ok"] is False and "fail-closed" in outs[0]["reason"]
    assert au.is_frozen("task_create") is False        # blocked, not frozen
    for p in (None, "guardian", "sovereign"):
        assert ac.cap_check("task_create", redis_get=boom, caps=CAPS,
                            posture=p)["ok"] is False


def test_cap_check_sovereign_alarms_at_cap_blocks_at_hard():
    at_cap = ac.cap_check("task_create", redis_get=lambda k: "2", caps=CAPS,
                          posture="sovereign", hard_multiplier=3)
    assert at_cap["ok"] is True and "alarm" in at_cap
    at_hard = ac.cap_check("task_create", redis_get=lambda k: "6", caps=CAPS,
                           posture="sovereign", hard_multiplier=3)
    assert at_hard["ok"] is False and "runaway hard-stop" in at_hard["reason"]


# --- silence breaker: D12 forcing ---------------------------------------------

def _silent_ledger(action_type="task_create", n=30):
    return [_acted(action_type, "2026-07-03T00:%02d:%02dZ" % (i // 60, i % 60))
            for i in range(n)]


def _never(*a, **k):
    raise AssertionError("must not be called in this posture/state")


def test_silence_guardian_path_never_probes_and_keeps_output_shape():
    store = {}
    out = ac.run_silence_breaker(
        ledger=_silent_ledger(), redis_set=lambda k, v, t: store.__setitem__(k, v),
        redis_del=lambda k: store.pop(k, None),
        run_canary_fn=_never, content_audit=_never)          # posture=None
    assert set(out) == {"silenced", "cleared"}               # keys unchanged
    assert [s["action_type"] for s in out["silenced"]] == ["task_create"]


def test_silence_sovereign_red_audit_freezes_pings_and_flag_stays(monkeypatch):
    pings = []
    from framework.frontdoor import intake
    monkeypatch.setattr(intake, "enqueue", lambda item, **k: pings.append(item) or "1-1")
    store = {}
    out = ac.run_silence_breaker(
        ledger=_silent_ledger(), redis_set=lambda k, v, t: store.__setitem__(k, v),
        redis_del=lambda k: store.pop(k, None), posture="sovereign",
        run_canary_fn=lambda *, kind: {"results": [{"kind": kind, "ok": True}]},
        content_audit=lambda at, rows: {"ok": False, "reason": "RED: wrong recipient"},
        redis_get=lambda k: store.get(k, ""))
    assert out["frozen"] == ["task_create"]
    assert au.is_frozen("task_create") is True
    assert any("SILENCE BREAKER" in a for a in out["alerts"])
    assert pings and pings[0]["urgency_tier"] == "ping-now"
    assert store.get("cabinet:actfirst:silenced:task_create")   # still silenced


def test_silence_sovereign_red_canary_freezes():
    out = ac.run_silence_breaker(
        ledger=_silent_ledger(), redis_set=lambda k, v, t: None,
        redis_del=lambda k: None, posture="sovereign",
        run_canary_fn=lambda *, kind: {"results": [{"kind": kind, "ok": False}]},
        content_audit=lambda at, rows: {"ok": True, "reason": "green"},
        redis_get=lambda k: "")
    assert out["frozen"] == ["task_create"]
    assert au.is_frozen("task_create") is True
    assert "canary red" in out["forced"][0]["why"]


def test_silence_sovereign_canary_cannot_run_is_red():
    def boom(*, kind):
        raise RuntimeError("no transports")
    out = ac.run_silence_breaker(
        ledger=_silent_ledger(), redis_set=lambda k, v, t: None,
        redis_del=lambda k: None, posture="sovereign",
        run_canary_fn=boom,
        content_audit=lambda at, rows: {"ok": True, "reason": "green"},
        redis_get=lambda k: "")
    assert out["frozen"] == ["task_create"]
    assert "cannot-run" in out["forced"][0]["why"]


def test_silence_sovereign_green_both_never_widens():
    seen = {}
    def audit(at, rows):
        seen["rows"] = rows
        return {"ok": True, "reason": "green"}
    store = {}
    out = ac.run_silence_breaker(
        ledger=_silent_ledger(n=35), redis_set=lambda k, v, t: store.__setitem__(k, v),
        redis_del=lambda k: store.pop(k, None), posture="sovereign",
        run_canary_fn=lambda *, kind: {"results": [{"kind": kind, "ok": True}]},
        content_audit=audit, redis_get=lambda k: store.get(k, ""))
    assert out["frozen"] == [] and out["alerts"] == []
    assert au.is_frozen("task_create") is False        # green audit widens NOTHING
    assert au.freeze_state("task_create") is None      # no unfreeze row either
    assert store.get("cabinet:actfirst:silenced:task_create")  # flag stands
    # the audit saw the last N acts, newest first
    assert len(seen["rows"]) == ac.SILENCE_BREAKER_THRESHOLD
    assert seen["rows"][0]["ts"] > seen["rows"][-1]["ts"]


def test_silence_sovereign_skips_already_frozen_kind():
    au.freeze("task_create", "pre-frozen")
    out = ac.run_silence_breaker(
        ledger=_silent_ledger(), redis_set=lambda k, v, t: None,
        redis_del=lambda k: None, posture="sovereign",
        run_canary_fn=_never, content_audit=_never, redis_get=lambda k: "")
    assert out["frozen"] == [] and out["forced"] == []


def test_default_content_audit_fail_closed_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = ac._default_content_audit("task_create", _silent_ledger(n=3))
    assert res["ok"] is False and "fail-closed" in res["reason"]


def test_run_weekly_posture_none_shape_unchanged():
    fm = FakeMonday(columns={"status": {"text": "Done"}})
    out = ac.run_weekly(monday_post=fm, osascript=_fake_osa, ledger=[],
                        now="2026-07-04T00:00:00Z")
    assert set(out) == {"canary", "breaker", "silence", "veto_divergences",
                        "env_perms", "pages"}
    assert set(out["silence"]) == {"silenced", "cleared"}


# --- canary receipts + kind scoping -------------------------------------------

def test_run_canary_kind_scoped_green_mints_valid_receipt():
    fm = FakeMonday(columns={"status": {"text": "Done"}})
    out = ac.run_canary(monday_post=fm, osascript=_fake_osa,
                        now="2026-07-04T00:00:00Z", kind="task_create")
    assert [r["kind"] for r in out["results"]] == ["monday_task_create"]
    token = out["results"][0]["receipt"]
    assert au.valid_green_receipt(token, "task_create", now="2026-07-04T12:00:00Z")
    # 25h later the same token is stale proof
    assert au.valid_green_receipt(token, "task_create",
                                  now="2026-07-05T01:00:00Z") is False
    # and it is no proof at all for another kind
    assert au.valid_green_receipt(token, "board_status",
                                  now="2026-07-04T12:00:00Z") is False


def test_red_canary_records_red_receipt():
    class NoIdMonday(FakeMonday):
        def __call__(self, query, variables):
            self.calls.append((query, variables))
            if "create_item" in query:
                return {"create_item": {}}
            return super().__call__(query, variables)
    ac.run_canary(monday_post=NoIdMonday(), osascript=_fake_osa,
                  now="2026-07-04T00:00:00Z", kind="task_create")
    rows = au.canary_receipts("task_create")
    assert rows and rows[-1]["green"] is False
    assert au.valid_green_receipt(rows[-1]["receipt"], "task_create",
                                  now="2026-07-04T01:00:00Z") is False


# --- unfreeze: receipt-gated, last-op-wins ------------------------------------

def test_unfreeze_requires_receipt_then_lifts_across_stale_redis():
    store = {}
    rset = lambda k, v, ttl: store.__setitem__(k, v)
    rget = lambda k: store.get(k, "")
    au.freeze("task_create", "breaker", redis_set=rset, now="2026-07-04T00:00:00Z")
    assert au.is_frozen("task_create", redis_get=rget) is True
    # no receipt ⇒ refused
    no = au.unfreeze("task_create", "please", canary_receipt="",
                     source="captain", now="2026-07-04T01:00:00Z")
    assert no["ok"] is False and "green canary receipt" in no["reason"]
    # fresh green receipt ⇒ lifted; the Redis DEL FAILS (stale flag stays) and
    # the durable mirror's last op still wins
    tok = au.record_canary_receipt("task_create", green=True,
                                   now="2026-07-04T01:00:00Z")["receipt"]
    def del_boom(_k):
        raise RuntimeError("redis down")
    ok = au.unfreeze("task_create", "captain rearm after green canary",
                     canary_receipt=tok, source="captain",
                     now="2026-07-04T02:00:00Z", redis_del=del_boom)
    assert ok["ok"] is True and ok["op"] == "unfreeze" and ok["source"] == "captain"
    assert store.get("cabinet:actfirst:frozen:task_create")     # stale flag present
    assert au.is_frozen("task_create", redis_get=rget) is False  # mirror wins
    assert au._kind_in_mirror("task_create") is False
    # a LATER freeze re-engages (last-op-wins in the other direction)
    au.freeze("task_create", "re-breach", redis_set=rset, now="2026-07-04T03:00:00Z")
    assert au.is_frozen("task_create", redis_get=rget) is True


def test_unfreeze_refusal_matrix():
    au.freeze("task_create", "breaker", now="2026-07-01T00:00:00Z")
    # stale receipt (>24h old)
    old = au.record_canary_receipt("task_create", green=True,
                                   now="2026-07-01T01:00:00Z")["receipt"]
    r = au.unfreeze("task_create", "x", canary_receipt=old, source="captain",
                    now="2026-07-04T00:00:00Z")
    assert r["ok"] is False and "green canary receipt" in r["reason"]
    # red receipt token
    red = au.record_canary_receipt("task_create", green=False,
                                   now="2026-07-04T00:00:00Z")["receipt"]
    assert au.unfreeze("task_create", "x", canary_receipt=red, source="captain",
                       now="2026-07-04T00:30:00Z")["ok"] is False
    # another kind's fresh green receipt
    other = au.record_canary_receipt("board_status", green=True,
                                     now="2026-07-04T00:00:00Z")["receipt"]
    assert au.unfreeze("task_create", "x", canary_receipt=other, source="captain",
                       now="2026-07-04T00:30:00Z")["ok"] is False
    # unknown token / bad source / not frozen
    assert au.unfreeze("task_create", "x", canary_receipt="f" * 32,
                       source="captain", now="2026-07-04T00:30:00Z")["ok"] is False
    assert au.unfreeze("task_create", "x", canary_receipt=red, source="cron",
                       now="2026-07-04T00:30:00Z")["ok"] is False
    fresh = au.record_canary_receipt("board_status", green=True,
                                     now="2026-07-04T00:00:00Z")["receipt"]
    nf = au.unfreeze("board_status", "x", canary_receipt=fresh, source="captain",
                     now="2026-07-04T00:30:00Z")
    assert nf["ok"] is False and "not frozen" in nf["reason"]
    # garbage-ts receipt row can never read fresh (strict parse fail-closed)
    au.freeze("board_status", "breaker", now="2026-07-04T00:00:00Z")
    d = au._undo_dir()
    with open(au._receipts_file(), "a") as fh:
        fh.write(json.dumps({"receipt": "g" * 32, "kind": "board_status",
                             "ts": "not-a-time", "green": True}) + "\n")
    assert au.unfreeze("board_status", "x", canary_receipt="g" * 32,
                       source="captain", now="2026-07-04T00:30:00Z")["ok"] is False


def test_unfreeze_emits_kind_unfrozen_event(tmp_path):
    au.freeze("task_create", "breaker", now="2026-07-04T00:00:00Z")
    tok = au.record_canary_receipt("task_create", green=True,
                                   now="2026-07-04T01:00:00Z")["receipt"]
    au.unfreeze("task_create", "rearm", canary_receipt=tok, source="captain",
                now="2026-07-04T02:00:00Z")
    evs = _events(tmp_path, "kind_unfrozen")
    assert len(evs) == 1 and evs[0]["payload"]["kind"] == "task_create"
    assert evs[0]["payload"]["source"] == "captain"


# --- run_thaw: machine-origin only, 3 greens + 7d clean ------------------------

def test_run_thaw_machine_origin_after_full_bar():
    au.freeze("task_create", "kind-breaker", now="2026-06-20T00:00:00Z")
    for ts in ("2026-06-25T00:00:00Z", "2026-06-30T00:00:00Z",
               "2026-07-03T12:00:00Z"):
        au.record_canary_receipt("task_create", green=True, now=ts)
    out = ac.run_thaw("task_create", now="2026-07-04T00:00:00Z",
                      redis_get=lambda k: "", redis_del=lambda k: None)
    assert out["ok"] is True and out["source"] == "machine"
    assert au.is_frozen("task_create") is False


def test_run_thaw_refuses_captain_origin_forever():
    au.freeze("task_create", "captain veto", source="captain",
              now="2026-06-20T00:00:00Z")
    for ts in ("2026-06-25T00:00:00Z", "2026-06-30T00:00:00Z",
               "2026-07-03T12:00:00Z"):
        au.record_canary_receipt("task_create", green=True, now=ts)
    out = ac.run_thaw("task_create", now="2026-07-04T00:00:00Z")
    assert out["ok"] is False and "rearm" in out["reason"]
    assert au.is_frozen("task_create") is True
    # the rearm path itself (Captain judgment + 1 synchronous green) still works
    tok = au.record_canary_receipt("task_create", green=True,
                                   now="2026-07-04T00:00:00Z")["receipt"]
    ok = au.unfreeze("task_create", "captain rearm", canary_receipt=tok,
                     source="captain", now="2026-07-04T00:30:00Z")
    assert ok["ok"] is True
    assert au.is_frozen("task_create") is False


def test_run_thaw_refuses_below_the_bar():
    # not frozen at all
    out = ac.run_thaw("task_create", now="2026-07-04T00:00:00Z")
    assert out["ok"] is False and "not frozen" in out["reason"]
    # young freeze (< 7d)
    au.freeze("task_create", "breaker", now="2026-06-30T00:00:00Z")
    out = ac.run_thaw("task_create", now="2026-07-04T00:00:00Z")
    assert out["ok"] is False and "younger" in out["reason"]
    # aged freeze but only 2 greens since it
    au.freeze("board_status", "breaker", now="2026-06-20T00:00:00Z")
    au.record_canary_receipt("board_status", green=True, now="2026-06-25T00:00:00Z")
    au.record_canary_receipt("board_status", green=True, now="2026-07-03T12:00:00Z")
    out = ac.run_thaw("board_status", now="2026-07-04T00:00:00Z")
    assert out["ok"] is False and "needs 3 green" in out["reason"]
    # 3 greens but a red inside the trailing 7d ⇒ not clean
    au.record_canary_receipt("board_status", green=True, now="2026-06-26T00:00:00Z")
    au.record_canary_receipt("board_status", green=False, now="2026-07-02T00:00:00Z")
    out = ac.run_thaw("board_status", now="2026-07-04T00:00:00Z")
    assert out["ok"] is False and "not clean" in out["reason"]


def test_run_thaw_stale_newest_green_refused_by_receipt_check():
    au.freeze("task_create", "breaker", now="2026-06-20T00:00:00Z")
    for ts in ("2026-06-21T00:00:00Z", "2026-06-22T00:00:00Z",
               "2026-06-23T00:00:00Z"):
        au.record_canary_receipt("task_create", green=True, now=ts)
    out = ac.run_thaw("task_create", now="2026-07-04T00:00:00Z")
    assert out["ok"] is False and "green canary receipt" in out["reason"]
    assert au.is_frozen("task_create") is True


# --- freeze origin + needs integration ----------------------------------------

def test_freeze_files_unfreeze_need_once_and_unfreeze_closes_it(monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    from framework.authority import needs
    au.freeze("task_create", "kind-breaker", now="2026-07-04T00:00:00Z")
    au.freeze("task_create", "kind-breaker again", now="2026-07-04T01:00:00Z")
    rows = [r for r in needs.list_open(now="2026-07-04T02:00:00Z")
            if r["kind"] == "unfreeze"]
    assert len(rows) == 1                              # deduped fingerprint id
    assert rows[0]["action_type"] == "task_create" and rows[0]["count"] == 2
    tok = au.record_canary_receipt("task_create", green=True,
                                   now="2026-07-04T01:30:00Z")["receipt"]
    au.unfreeze("task_create", "rearm", canary_receipt=tok, source="captain",
                now="2026-07-04T02:00:00Z")
    assert [r for r in needs.list_open(now="2026-07-04T03:00:00Z")
            if r["kind"] == "unfreeze"] == []          # marked granted


def test_freeze_files_nothing_in_guardian_default_world(tmp_path):
    au.freeze("task_create", "kind-breaker")
    assert not (tmp_path / "root" / "shared" / "interfaces"
                / "needs-ledger.jsonl").exists()


def test_freeze_survives_needs_module_absent(monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setitem(sys.modules, "framework.authority.needs", None)
    row = au.freeze("task_create", "breaker")          # must not raise
    assert row["op"] == "freeze" and row["source"] == "machine"
    assert au.is_frozen("task_create") is True


def test_freeze_unknown_source_coerces_to_captain():
    row = au.freeze("task_create", "breaker", source="something-else",
                    now="2026-06-20T00:00:00Z")
    assert row["source"] == "captain"                  # never auto-thawed
    au.record_canary_receipt("task_create", green=True, now="2026-06-25T00:00:00Z")
    au.record_canary_receipt("task_create", green=True, now="2026-06-30T00:00:00Z")
    au.record_canary_receipt("task_create", green=True, now="2026-07-03T12:00:00Z")
    assert ac.run_thaw("task_create", now="2026-07-04T00:00:00Z")["ok"] is False


def test_actfirst_freeze_wrapper_passes_origin_through():
    ac.freeze("monday_task_update", "veto follow-through", source="captain")
    st = au.freeze_state("board_status")               # breaker-key resolution kept
    assert st and st["op"] == "freeze" and st["source"] == "captain"
