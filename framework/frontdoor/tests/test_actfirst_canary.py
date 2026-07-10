"""TI-7 — canaries + breakers + caps (fixtured: fake monday/osascript/redis, tmp
journal + tmp consequence dir; no live calls, ZERO consequence emission)."""
from __future__ import annotations

import json

import pytest

from framework.frontdoor import action_undo as au
from framework.frontdoor import actfirst_canary as ac


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """Journal to a tmp dir; consequence dir empty + tmp; never touch live Redis
    (both the undo module's defaults AND this module's defaults are no-ops)."""
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    for mod in (au, ac):
        monkeypatch.setattr(mod, "_default_redis_set", lambda *a, **k: None)
        monkeypatch.setattr(mod, "_default_redis_get", lambda *a, **k: "")
        monkeypatch.setattr(mod, "_default_redis_del", lambda *a, **k: None)
    monkeypatch.setattr(ac, "_default_redis_incr", lambda *a, **k: "1")
    monkeypatch.setattr(ac, "_default_redis_expire", lambda *a, **k: None)
    yield


class FakeMonday:
    """Records every GraphQL call; answers a column read from a seeded map;
    hands back create/archive/update ids so the executor ops succeed."""
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

    def qs(self):
        return " ".join(q for q, _ in self.calls)


def _fake_osa(cmd):
    # The act-first calendar write now runs a double-book gather first
    # (calendar_read helper: `<helper> read <start> <end>`); return a valid empty
    # JSON array = no conflict, so the synthetic canary write proceeds.
    if len(cmd) > 1 and cmd[1] == "read":
        return "[]"
    # ...and an F1 pre-write gate (`<helper> calinfo <cal>`); report the canary
    # target as a private, writable, un-shared calendar so the gate clears.
    if len(cmd) > 1 and cmd[1] == "calinfo":
        return ('{"calendar":"Cabinet","found":true,"ambiguous":false,'
                '"writable":true,"shared":false,"shared_signal":"none","type":"calDAV"}')
    src = cmd[2] if len(cmd) > 2 else ""
    if "make new event" in src:
        return "ok:Cabinet:UID-CANARY"
    return "ok"


def _acted(action_type, ts, *, verdict=None, source=None, refs=None, lane="bakery"):
    """A synthetic acted ledger row (proposal.required False, RT-B1 marker)."""
    ev = {"ts": ts, "actor": {"kind": "officer", "id": "officer:cos"}, "lane": lane,
          "action": "acted:" + action_type, "subject": "s-" + ts,
          "action_type": action_type, "refs": refs or [],
          "proposal": {"required": False, "decision": None},
          "outcome": {"status": "unknown"}}
    if verdict:
        rev = {"verdict": verdict}
        if source:
            rev["source"] = source
        ev["review"] = rev
    return ev


# --- canary kinds ------------------------------------------------------------

def test_canary_kinds_are_exactly_the_act_first_eligible_set():
    kinds = dict(ac.canary_kinds())
    assert kinds == {"monday_task_create": "monday",
                     "monday_task_update": "monday",
                     "reminder_create": "calendar"}
    # delegate_work + apple_reminders are NOT act-first-eligible → never a canary
    assert all(au.act_first_eligible(k, b) for k, b in ac.canary_kinds())


# --- canary happy path: create -> verify -> reverse -> verify -----------------

def test_run_canary_all_kinds_roundtrip_no_freeze_zero_ledger(tmp_path):
    fm = FakeMonday(columns={"status": {"text": "Done"}})   # compare-restore matches
    out = ac.run_canary(monday_post=fm, osascript=_fake_osa,
                        board="42424242", now="2026-07-04T00:00:00Z")
    assert [r["kind"] for r in out["results"]] == \
        ["monday_task_create", "monday_task_update", "reminder_create"]
    assert all(r["ok"] for r in out["results"])          # every reverse clean
    assert out["frozen"] == [] and out["alerts"] == []
    # a create canary archives (never deletes) its synthetic item
    assert "archive_item" in fm.qs() and "delete_item" not in fm.qs()
    # ZERO consequence events emitted — a canary never looks like real acting
    assert not list((tmp_path / "events").glob("consequence-events-*.jsonl"))


def test_canary_journal_rows_are_all_marked_canary():
    fm = FakeMonday(columns={"status": {"text": "Done"}})
    ac.run_canary(monday_post=fm, osascript=_fake_osa, now="2026-07-04T00:00:00Z")
    rows = au._read_journal()
    assert rows and all(r.get("canary") is True for r in rows)


def test_canary_reverse_failure_freezes_that_kind():
    # board_status drift (a "colleague edit") makes compare-restore dead-letter →
    # the reverse is not clean → freeze board_status; the other kinds stay green.
    fm = FakeMonday(columns={"status": {"text": "Blocked"}})
    out = ac.run_canary(monday_post=fm, osascript=_fake_osa, now="2026-07-04T00:00:00Z")
    assert "board_status" in out["frozen"]
    assert au.is_frozen("board_status") is True          # durable mirror holds
    assert any("CANARY FAILED" in a and "board_status" in a for a in out["alerts"])
    byk = {r["kind"]: r for r in out["results"]}
    assert byk["monday_task_update"]["ok"] is False
    assert byk["monday_task_create"]["ok"] is True       # unaffected kinds green


def test_canary_create_no_id_freezes_task_create():
    class NoIdMonday(FakeMonday):
        def __call__(self, query, variables):
            self.calls.append((query, variables))
            if "create_item" in query:
                return {"create_item": {}}               # backend returned no id
            return super().__call__(query, variables)
    out = ac.run_canary(monday_post=NoIdMonday(), osascript=_fake_osa,
                        now="2026-07-04T00:00:00Z")
    # task_create's key resolves to the step-kind pre-germline (dormant enum)
    assert out["frozen"] and any("undo probe" not in f for f in out["frozen"])
    assert any(r["kind"] == "monday_task_create" and r["ok"] is False
               for r in out["results"])


# --- caps (fail-closed) ------------------------------------------------------

def test_load_caps_reads_instance_config():
    caps = ac.load_caps()
    assert caps["estate"] == 40 and caps["per_kind"] == 20     # act-first-surfaces.yml


def test_load_caps_falls_back_when_absent(tmp_path):
    caps = ac.load_caps(config_path=tmp_path / "nope.yml")
    assert caps == {"estate": 40, "per_kind": 20}


def test_incr_and_check_under_cap_ok_then_blocks_per_kind():
    store = {}
    def inc(k):
        store[k] = store.get(k, 0) + 1
        return str(store[k])
    caps = {"estate": 40, "per_kind": 2}
    a = ac.incr_and_check("task_create", redis_incr=inc, redis_expire=lambda *a: None, caps=caps)
    b = ac.incr_and_check("task_create", redis_incr=inc, redis_expire=lambda *a: None, caps=caps)
    c = ac.incr_and_check("task_create", redis_incr=inc, redis_expire=lambda *a: None, caps=caps)
    assert a["ok"] and b["ok"] and c["ok"] is False        # the 3rd trips per-kind
    assert "per-kind" in c["reason"]


def test_incr_and_check_blocks_on_estate_cap():
    store = {}
    def inc(k):
        store[k] = store.get(k, 0) + 1
        return str(store[k])
    caps = {"estate": 1, "per_kind": 20}
    ac.incr_and_check("task_create", redis_incr=inc, redis_expire=lambda *a: None, caps=caps)
    d = ac.incr_and_check("board_status", redis_incr=inc, redis_expire=lambda *a: None, caps=caps)
    assert d["ok"] is False and "estate" in d["reason"]     # estate counts across kinds


def test_incr_and_check_fail_closed_on_redis_error():
    def boom(_k):
        raise RuntimeError("redis down")
    r = ac.incr_and_check("task_create", redis_incr=boom, redis_expire=lambda *a: None)
    assert r["ok"] is False and "fail-closed" in r["reason"]


def test_cap_check_readonly_fail_closed():
    def boom(_k):
        raise RuntimeError("redis down")
    assert ac.cap_check("task_create", redis_get=boom)["ok"] is False


# --- kind breaker ------------------------------------------------------------

def test_undo_rate_over_window():
    led = [_acted("task_create", "2026-07-03T10:00:00Z", verdict="wrong",
                  source="verdict_human")] \
        + [_acted("task_create", "2026-07-03T1%d:00:00Z" % i) for i in range(1, 4)]
    r = ac.undo_rate("task_create", ledger=led, now="2026-07-04T00:00:00Z")
    assert r["acts"] == 4 and r["undone"] == 1 and abs(r["rate"] - 0.25) < 1e-9


def test_kind_breaker_freezes_over_bar_and_skips_below_floor():
    led = []
    # task_create: 8 acts, 3 undone (0.375 > 0.25) → freeze
    for i in range(3):
        led.append(_acted("task_create", "2026-07-03T0%d:00:00Z" % i,
                          verdict="wrong", source="verdict_human"))
    for i in range(3, 8):
        led.append(_acted("task_create", "2026-07-03T0%d:00:00Z" % i))
    # board_status: 8 acts, 1 undone (0.125) → no freeze
    for i in range(1):
        led.append(_acted("board_status", "2026-07-03T1%d:00:00Z" % i,
                          verdict="wrong", source="verdict_human"))
    for i in range(1, 8):
        led.append(_acted("board_status", "2026-07-03T1%d:00:00Z" % i))
    store = {}
    rset = lambda k, v, ttl: store.__setitem__(k, v)
    rget = lambda k: store.get(k, "")
    out = ac.run_kind_breaker(ledger=led, redis_set=rset, redis_get=rget,
                             now="2026-07-04T00:00:00Z")
    frozen = {f["action_type"] for f in out["frozen"]}
    assert frozen == {"task_create"}
    assert au.is_frozen("task_create") is True
    assert au.is_frozen("board_status") is False


def test_kind_breaker_needs_the_sample_floor():
    # 4 acts, all undone (rate 1.0) but acts < 8 → NOT frozen
    led = [_acted("task_create", "2026-07-03T0%d:00:00Z" % i,
                  verdict="wrong", source="verdict_human") for i in range(4)]
    out = ac.run_kind_breaker(ledger=led, now="2026-07-04T00:00:00Z")
    assert out["frozen"] == []
    assert au.is_frozen("task_create") is False


def test_kind_breaker_skips_already_frozen_no_duplicate():
    led = [_acted("task_create", "2026-07-03T0%d:00:00Z" % i,
                  verdict="wrong", source="verdict_human") for i in range(4)] \
        + [_acted("task_create", "2026-07-03T1%d:00:00Z" % i) for i in range(4)]
    store = {}
    rset = lambda k, v, ttl: store.__setitem__(k, v)
    rget = lambda k: store.get(k, "")
    first = ac.run_kind_breaker(ledger=led, redis_set=rset, redis_get=rget,
                               now="2026-07-04T00:00:00Z")
    assert [f["action_type"] for f in first["frozen"]] == ["task_create"]
    second = ac.run_kind_breaker(ledger=led, redis_set=rset, redis_get=rget,
                                now="2026-07-04T00:00:00Z")
    assert second["frozen"] == []                          # already frozen — no dup


# --- silence breaker [RT-A6] -------------------------------------------------

def test_silence_state_thirty_untouched_is_silenced():
    led = [_acted("task_create", "2026-07-03T00:00:%02dZ" % i) for i in range(30)]
    st = ac.silence_state("task_create", ledger=led)
    assert st["consecutive_untouched"] == 30 and st["silenced"] is True


def test_silence_self_clears_on_a_recent_human_touch():
    led = [_acted("task_create", "2026-07-03T00:00:%02dZ" % i) for i in range(30)]
    # the newest act carries a human confirm → consecutive resets to 0
    led.append(_acted("task_create", "2026-07-03T00:01:00Z",
                      verdict="confirmed", source="verdict_human"))
    st = ac.silence_state("task_create", ledger=led)
    assert st["consecutive_untouched"] == 0 and st["silenced"] is False


def test_run_silence_breaker_publishes_and_clears_flags():
    led = [_acted("task_create", "2026-07-03T00:00:%02dZ" % i) for i in range(30)] \
        + [_acted("board_status", "2026-07-03T01:00:00Z", verdict="confirmed",
                  source="verdict_human")]
    store = {}
    rset = lambda k, v, ttl: store.__setitem__(k, v)
    rdel = lambda k: store.pop(k, None)
    out = ac.run_silence_breaker(ledger=led, redis_set=rset, redis_del=rdel)
    assert [s["action_type"] for s in out["silenced"]] == ["task_create"]
    assert "board_status" in out["cleared"]
    assert store.get("cabinet:actfirst:silenced:task_create")
    assert ac.is_silenced("task_create", redis_get=lambda k: store.get(k, "")) is True
    assert ac.is_silenced("board_status", redis_get=lambda k: store.get(k, "")) is False


def test_is_silenced_fail_closed():
    def boom(_k):
        raise RuntimeError("redis down")
    assert ac.is_silenced("anything", redis_get=boom) is True


# --- cid-echo suppression ----------------------------------------------------

def test_own_acted_cids_and_echo_detection():
    cid = "a" * 32
    led = [_acted("task_create", "2026-07-03T00:00:00Z", refs=[ac.correlation.ref_for(cid)])]
    own = ac.own_acted_cids(ledger=led)
    assert cid in own
    echo = "some note body\n\n" + ac.correlation.monday_footer(cid)
    assert ac.is_cid_echo(echo, own) is True
    assert ac.is_cid_echo("unrelated text", own) is False


def test_filter_cid_echoes_drops_and_logs():
    cid = "b" * 32
    own = frozenset({cid})
    items = [{"t": "clean note"},
             {"t": "our own act " + ac.correlation.monday_footer(cid)}]
    logs = []
    kept = ac.filter_cid_echoes(items, own, text_of=lambda it: it["t"], log=logs.append)
    assert kept == [{"t": "clean note"}]
    assert logs and "cid-echo" in logs[0]


def test_filter_cid_echoes_noop_when_no_own_cids():
    items = [{"t": "x"}, {"t": "y"}]
    assert ac.filter_cid_echoes(items, frozenset(), text_of=lambda it: it["t"]) == items


# --- veto <-> ledger divergence [RT-B7] --------------------------------------

def test_load_vetoes_absent_is_empty(tmp_path):
    assert ac.load_vetoes(path=tmp_path / "nope.yml") == []


def test_veto_divergence_flags_acted_after_active_veto():
    vetoes = [{"id": "veto-001", "ts": "2026-07-03T00:00:00Z", "status": "active",
               "scope": {"action_type": "task_create", "lane": "bakery"}}]
    led = [_acted("task_create", "2026-07-03T12:00:00Z"),          # AFTER the veto → page
           _acted("task_create", "2026-07-02T00:00:00Z"),          # before → fine
           _acted("board_status", "2026-07-04T00:00:00Z")]         # wrong type → no match
    div = ac.veto_ledger_divergences(vetoes=vetoes, ledger=led)
    assert len(div) == 1
    assert div[0]["veto_id"] == "veto-001" and div[0]["acted_ts"] == "2026-07-03T12:00:00Z"


def test_lifted_veto_never_diverges():
    vetoes = [{"id": "veto-002", "ts": "2026-07-01T00:00:00Z", "status": "lifted",
               "scope": {"action_type": "task_create"}}]
    led = [_acted("task_create", "2026-07-03T12:00:00Z")]
    assert ac.veto_ledger_divergences(vetoes=vetoes, ledger=led) == []


def test_board_only_scope_is_not_ledger_matchable():
    vetoes = [{"id": "veto-003", "ts": "2026-07-01T00:00:00Z", "status": "active",
               "scope": {"board_id": "999"}}]
    led = [_acted("task_create", "2026-07-03T12:00:00Z")]
    assert ac.veto_ledger_divergences(vetoes=vetoes, ledger=led) == []


# --- env perms + weekly bundle -----------------------------------------------

def test_env_perms_finding(tmp_path):
    loose = tmp_path / "loose.env"
    loose.write_text("K=v\n")
    loose.chmod(0o644)
    f = ac.env_perms_finding(path=loose)
    assert f and "0600" in f["reason"]
    tight = tmp_path / "tight.env"
    tight.write_text("K=v\n")
    tight.chmod(0o600)
    assert ac.env_perms_finding(path=tight) is None
    assert ac.env_perms_finding(path=tmp_path / "absent.env") is None


def test_run_weekly_smoke():
    fm = FakeMonday(columns={"status": {"text": "Done"}})
    out = ac.run_weekly(monday_post=fm, osascript=_fake_osa, ledger=[],
                       now="2026-07-04T00:00:00Z")
    assert set(out) == {"canary", "breaker", "silence", "veto_divergences",
                        "env_perms", "pages"}
    assert out["canary"]["frozen"] == []          # clean canary, nothing frozen


# =============================================================================
# CANARY-UNFREEZE (germline batch 2026-07-05) — the manual green-canary
# unfreeze. CRIT-5 contract: a frozen kind is re-armed ONLY by an explicit,
# Captain-triggered probe that first PROVES create→verify→reverse green, then
# lifts the freeze (durable mirror supersede + Redis flag clear). A non-green
# probe leaves the kind frozen; no scheduled/automatic path may ever lift.
# Fixtured transports throughout — never real Monday/Calendar.
# =============================================================================

def _freeze_store():
    """A dict-backed Redis triple, pre-loaded by au.freeze through rset."""
    store = {}
    return (store,
            lambda k, v, ttl: store.__setitem__(k, v),      # rset
            lambda k: store.get(k, ""),                     # rget
            lambda k: store.pop(k, None))                   # rdel


def test_unfreeze_green_probe_lifts_flag_and_mirror(tmp_path):
    store, rset, rget, rdel = _freeze_store()
    au.freeze("board_status", "canary failed", redis_set=rset)
    assert au.is_frozen("board_status", redis_get=rget) is True
    fm = FakeMonday(columns={"status": {"text": "Done"}})   # clean roundtrip
    out = ac.run_unfreeze_canary("board_status", monday_post=fm,
                                 osascript=_fake_osa, redis_get=rget,
                                 redis_del=rdel, now="2026-07-05T00:00:00Z")
    assert out["ok"] is True and out["green"] is True and out["unfrozen"] is True
    assert out["was_frozen"] is True
    assert out["kind"] == "monday_task_update" and out["action_type"] == "board_status"
    assert out["lift"]["op"] == "unfreeze"
    # the probe genuinely ran create→verify→reverse (setup item archived after)
    assert "change_column_value" in fm.qs() and "archive_item" in fm.qs()
    # BOTH halves cleared: Redis flag deleted AND the durable mirror superseded
    assert "cabinet:actfirst:frozen:board_status" not in store
    assert au._kind_in_mirror("board_status") is False
    assert au.is_frozen("board_status", redis_get=rget) is False
    # ZERO consequence events — an unfreeze probe never looks like real acting
    assert not list((tmp_path / "events").glob("consequence-events-*.jsonl"))


def test_unfreeze_non_green_probe_leaves_frozen_fail_closed():
    store, rset, rget, rdel = _freeze_store()
    au.freeze("board_status", "canary failed", redis_set=rset)
    # column drift ("Blocked" vs the probe's "Done") → compare-restore
    # dead-letters → the reverse is NOT clean → no lift, kind stays frozen.
    fm = FakeMonday(columns={"status": {"text": "Blocked"}})
    out = ac.run_unfreeze_canary("board_status", monday_post=fm,
                                 osascript=_fake_osa, redis_get=rget,
                                 redis_del=rdel, now="2026-07-05T00:00:00Z")
    assert out["ok"] is False and out["green"] is False and out["unfrozen"] is False
    assert "CRIT-5" in out["note"]
    assert "cabinet:actfirst:frozen:board_status" in store   # flag untouched
    assert au._kind_in_mirror("board_status") is True        # mirror untouched
    assert au.is_frozen("board_status", redis_get=rget) is True


def test_unfreeze_cannot_run_probe_leaves_frozen():
    # A probe that cannot even run (backend erroring on create) is cannot-run,
    # not green — same fail-closed leg as a dirty reverse.
    store, rset, rget, rdel = _freeze_store()
    au.freeze("board_status", "canary failed", redis_set=rset)
    def boom(query, variables):
        raise RuntimeError("monday 500")
    out = ac.run_unfreeze_canary("board_status", monday_post=boom,
                                 osascript=_fake_osa, redis_get=rget, redis_del=rdel)
    assert out["ok"] is False and out["unfrozen"] is False and out.get("error")
    assert au.is_frozen("board_status", redis_get=rget) is True


def test_unfreeze_accepts_step_kind_alias():
    # --unfreeze takes EITHER the action_type ('board_status') or the step kind
    # ('monday_task_update') — both resolve to the ONE probe + freeze key.
    store, rset, rget, rdel = _freeze_store()
    au.freeze("board_status", "canary failed", redis_set=rset)
    fm = FakeMonday(columns={"status": {"text": "Done"}})
    out = ac.run_unfreeze_canary("monday_task_update", monday_post=fm,
                                 osascript=_fake_osa, redis_get=rget, redis_del=rdel)
    assert out["unfrozen"] is True and out["action_type"] == "board_status"
    assert au.is_frozen("board_status", redis_get=rget) is False


def test_unfreeze_unknown_kind_refused():
    out = ac.run_unfreeze_canary("bogus_kind", monday_post=FakeMonday(),
                                 osascript=_fake_osa)
    assert out["ok"] is False and out["unfrozen"] is False
    assert "unknown act-first kind" in out["error"]


def test_unfreeze_ineligible_kind_refused(monkeypatch):
    # A kind with no registered inverse has no reversible probe to prove green —
    # refuse rather than pretend a lift (fail-closed, freeze intact).
    store, rset, rget, rdel = _freeze_store()
    au.freeze("board_status", "canary failed", redis_set=rset)
    monkeypatch.setattr(au, "act_first_eligible", lambda *a, **k: False)
    out = ac.run_unfreeze_canary("board_status", monday_post=FakeMonday(),
                                 osascript=_fake_osa, redis_get=rget, redis_del=rdel)
    assert out["ok"] is False and out["unfrozen"] is False
    assert "not act-first-eligible" in out["error"]
    assert au.is_frozen("board_status", redis_get=rget) is True


def test_weekly_green_canary_never_auto_unfreezes():
    # CRIT-5 behavioral pin: even a GREEN scheduled/weekly canary run does NOT
    # lift an existing freeze — the ONLY lift path is the explicit
    # run_unfreeze_canary above (freeze() has no timer; run_canary only ADDS
    # freezes on failure).
    store, rset, rget, rdel = _freeze_store()
    au.freeze("board_status", "canary failed last week", redis_set=rset)
    fm = FakeMonday(columns={"status": {"text": "Done"}})   # all-green run
    out = ac.run_canary(monday_post=fm, osascript=_fake_osa, redis_get=rget,
                        redis_set=rset, redis_del=rdel, now="2026-07-05T00:00:00Z")
    assert all(r["ok"] for r in out["results"])             # genuinely green
    assert au.is_frozen("board_status", redis_get=rget) is True   # freeze holds
    # ...and the explicit manual path is what lifts it:
    out2 = ac.run_unfreeze_canary("board_status", monday_post=fm,
                                  osascript=_fake_osa, redis_get=rget, redis_del=rdel)
    assert out2["unfrozen"] is True
    assert au.is_frozen("board_status", redis_get=rget) is False


def test_unfreeze_has_no_auto_caller_in_source():
    # CRIT-5 structural pin (RECONCILE 2026-07-05: kept both): action_undo.
    # unfreeze( is CALLED only from (a) actfirst_canary — run_unfreeze_canary's
    # synchronous manual green-canary lift + run_thaw's SOURCE-GATED machine
    # auto-thaw (refuses captain-origin freezes forever) — and (b) binder_wire's
    # FI-4 Captain `rearm <kind>` verb: an EXPLICIT Captain reply that runs one
    # synchronous scoped canary and lifts with source="captain" only on a green
    # receipt. Neither is an automatic/timer lift; run_unfreeze_canary( stays
    # referenced only inside actfirst_canary itself (its def + the manual _cli),
    # and no launchd plist / cabinet script wires any lift.
    import re
    from pathlib import Path
    root = Path(ac.__file__).resolve().parents[2]
    call_re = re.compile(r"(?<!def )\bunfreeze\(")            # calls, not the def
    runner_re = re.compile(r"(?<!def )\brun_unfreeze_canary\(")
    unfreeze_callers, runner_callers = set(), set()
    for f in (root / "framework").rglob("*.py"):
        if "tests" in f.parts:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        if call_re.search(text):
            unfreeze_callers.add(f.name)
        if runner_re.search(text):
            runner_callers.add(f.name)
    assert unfreeze_callers == {"actfirst_canary.py", "binder_wire.py"}
    assert runner_callers == {"actfirst_canary.py"}           # only its own _cli
    # binder_wire's lift is the Captain rearm verb: its unfreeze call must be
    # captain-sourced AND receipted (the receipt is re-verified ≤24h-green
    # inside action_undo.unfreeze) — never a bare/blind lift.
    bw = (root / "framework" / "frontdoor" / "binder_wire.py").read_text(
        encoding="utf-8", errors="ignore")
    assert 'source="captain"' in bw
    assert "canary_receipt=" in bw
    # nothing scheduled invokes the manual flag (docs may mention it; plists and
    # cron/scripts must not)
    for d in (root / "cabinet" / "launchd", root / "cabinet" / "scripts"):
        for f in d.rglob("*"):
            if f.is_file() and f.suffix in (".plist", ".sh", ".py"):
                assert "--unfreeze" not in f.read_text(encoding="utf-8",
                                                       errors="ignore"), f


def test_unfreeze_cli_exit_codes(monkeypatch, capsys):
    # The exact command INSTALL-flip.md documents:
    #   python3.12 -m framework.frontdoor.actfirst_canary --unfreeze <kind>
    # exit 0 only on a green lift; non-zero LEAVES the freeze. Production
    # transports are monkeypatched to fixtures — never real Monday/Calendar.
    store, rset, rget, rdel = _freeze_store()
    au.freeze("board_status", "canary failed", redis_set=rset)
    monkeypatch.setattr(ac, "_default_redis_get", rget)
    monkeypatch.setattr(ac, "_default_redis_del", rdel)
    monkeypatch.setattr(au, "_default_redis_get", rget)
    bad = FakeMonday(columns={"status": {"text": "Blocked"}})
    monkeypatch.setattr(au, "_prod_transports", lambda: (bad, _fake_osa))
    assert ac._cli(["--unfreeze", "board_status"]) == 1     # non-green → freeze holds
    assert au.is_frozen("board_status", redis_get=rget) is True
    good = FakeMonday(columns={"status": {"text": "Done"}})
    monkeypatch.setattr(au, "_prod_transports", lambda: (good, _fake_osa))
    assert ac._cli(["--unfreeze", "board_status"]) == 0     # green → lifted
    assert au.is_frozen("board_status", redis_get=rget) is False
    out = capsys.readouterr().out
    assert '"unfrozen": true' in out
