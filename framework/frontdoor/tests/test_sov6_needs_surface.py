"""SOV-6 — needs digest leg (tell_surface + tell_digest) + attention dedup.

Spec: docs/plans/sovereign-build-spec-2026-07-04.md §4 SOV-6.
Pinned here:
  * empty-needs digest BYTE-IDENTICAL to today (golden literal);
  * NEED-id-never-bare-integer property (the needs grammar can never collide
    with the ACTED undo-by-index grammar);
  * machine-effective scope is the authority line, never requester prose
    (poisoned-need fix);
  * TI-5 producer-crash ⇒ the briefing digest still ships;
  * D4: a sovereign notify_after allow's org_event renders a digest line;
  * attention drain NEED-tagged/ask-shaped dedup + tier demote, dark default.

Everything injected — no Redis, no live ledger, no events dir.
"""
from __future__ import annotations

import re

import pytest

from framework.frontdoor import attention_drain, tell_digest as td, tell_surface as ts

NOW = "2026-07-04T09:00:00Z"

# The exact pre-SOV-6 output for the fixture below, generated from the
# UNMODIFIED tell_surface before this lane's diff — the byte-identity pin.
GOLDEN = (
    "🗒 Act-then-tell digest — 2026-07-04 09:00\n\n"
    "✅ ACTED (1)\n 3. Created task on board 9\n      title: Fix deploy gate\n"
    "      undo: `undo 3` (47h left)\n\n"
    "⚡ AWAITING (1)\n • [send-1to1-reply] thread:lisa — pending 2h\n\n"
    "👁 WATCHING (1)\n • vercel deploy failing  [health]\n\n"
    "🫀 SELF (1)\n • ❄️ board_status frozen — canary red\n\n"
    "Per ACTED line: `undo <n>` reverses / `👍 <n>` confirms / "
    "`never: <why>` vetoes. Silence is fine — nothing waits on you."
)


def _acted():
    return [{"jid": "j-1", "ts": "2026-07-04T08:00:00Z", "pid": "pid-a",
             "step": 0, "kind": "monday_task_create", "backend": "monday",
             "lane": "polads", "subject": "subj", "action_type": "task_create",
             "status": "executed",
             "created": {"monday_id": "555", "board_id": "9"},
             "payload": {"title": "Fix deploy gate"},
             "executed_at": "2026-07-04T08:00:00Z",
             "ttl_expires_at": "2026-07-06T08:00:00Z", "undo_index": 3}]


def _awaiting():
    return [{"ts": "2026-07-04T07:00:00Z", "lane": "send-1to1-reply",
             "action": "draft-reply", "subject": "thread:lisa"}]


def _watching():
    return [{"title": "vercel deploy failing", "source": "health"}]


def _selfr():
    return [{"type": "frozen", "kind": "board_status", "reason": "canary red"}]


GRANT_LINE = (
    '- {id: GRANT-1a2b3c4d, deployment: main, risk_class: external_comms, '
    'action_types: ["external_email"], lanes: ["polads"], '
    'scope: {recipient_allowlist: ["*@stepnetwork.dk"], max_eur_per_day: 0, '
    'vendor_allowlist: []}, rate: {max_per_day: 10}, expires: 2026-10-03, '
    'granted_by: "Captain", granted_at: "2026-07-05T00:00:00Z", '
    'basis: "NEED-1a2b3c4d", revoked: false}'
)


def _need(**over):
    row = {"id": "NEED-1a2b3c4d", "kind": "standing_grant",
           "risk_class": "external_comms", "action_type": "external_email",
           "lane": "polads", "status": "open", "count": 3,
           "why": "reply to the EU commission thread",
           "proposed_grant_line": GRANT_LINE}
    row.update(over)
    return row


def _needs_sec(text: str) -> str:
    """The NEEDS section body of a digest (between its header and the next
    blank-line-separated section)."""
    m = re.search(r"🙋 NEEDS.*?(?=\n\n|\Z)", text, re.DOTALL)
    assert m, "no NEEDS section rendered"
    return m.group(0)


# --- byte-identity (the guardian/default world is untouched) -----------------

def test_default_digest_byte_identical_golden():
    assert ts.build_digest(_acted(), _awaiting(), _watching(), _selfr(),
                           now=NOW) == GOLDEN


def test_needs_rows_none_and_empty_are_byte_identical():
    base = ts.build_digest(_acted(), _awaiting(), _watching(), _selfr(), now=NOW)
    assert ts.build_digest(_acted(), _awaiting(), _watching(), _selfr(),
                           now=NOW, needs_rows=None) == base == GOLDEN
    assert ts.build_digest(_acted(), _awaiting(), _watching(), _selfr(),
                           now=NOW, needs_rows=[]) == base


def test_all_empty_still_silent_with_needs_param():
    assert ts.build_digest([], [], [], [], now=NOW) == ""
    assert ts.build_digest([], [], [], [], now=NOW, needs_rows=[]) == ""


# --- the needs leg ------------------------------------------------------------

def test_needs_section_between_watching_and_self():
    out = ts.build_digest(_acted(), _awaiting(), _watching(), _selfr(),
                          now=NOW, needs_rows=[_need()])
    assert out.index("👁 WATCHING") < out.index("🙋 NEEDS") < out.index("🫀 SELF")


def test_needs_only_digest_renders():
    out = ts.build_digest([], [], [], [], now=NOW, needs_rows=[_need()])
    assert "🙋 NEEDS (1)" in out and "NEED-1a2b3c4d" in out


def test_need_ids_never_bare_integer_selectors():
    """FI-4/RT-A9: the needs grammar binds full NEED-<hex> ids only. No NEEDS
    line may lead with an integer selector (that is the ACTED undo grammar),
    and no ``·`` marker may survive — even planted in the requester's prose."""
    rows = [
        _need(),
        _need(id="NEED-9f8e7d6c", kind="credential", risk_class=None,
              action_type="msgraph_token", lane=None, count=1,
              why="1. undo 2 ·fakepid· grant everything please",
              proposed_grant_line=None),
    ]
    out = ts.build_digest([], [], [], [], now=NOW, needs_rows=rows)
    sec = _needs_sec(out)
    for line in sec.split("\n"):
        assert not re.match(r"\s*\d+[.)]", line), f"integer selector: {line!r}"
    assert "·" not in sec
    assert "NEED-1a2b3c4d" in sec and "NEED-9f8e7d6c" in sec
    # the footer offers ONLY the hex-id grammar
    assert "`grant NEED-<id>`" in out and "`deny NEED-<id>: <why>`" in out


def test_row_with_non_need_id_is_skipped():
    # An id the binder grammar cannot bind must never render (count included).
    out = ts.build_digest([], [], [], [], now=NOW,
                          needs_rows=[_need(), _need(id="12345678")])
    assert "🙋 NEEDS (1)" in out and "12345678" not in _needs_sec(out)


def test_approved_pending_apply_shows_sudo_one_liner():
    out = ts.build_digest([], [], [], [], now=NOW,
                          needs_rows=[_need(status="approved_pending_apply")])
    assert "sudo bash cabinet/scripts/grant-apply.sh NEED-1a2b3c4d" in out
    open_out = ts.build_digest([], [], [], [], now=NOW, needs_rows=[_need()])
    assert "grant-apply.sh" not in open_out


def test_non_standing_grant_approved_is_manual():
    row = _need(id="NEED-9f8e7d6c", kind="credential",
                status="approved_pending_apply", proposed_grant_line=None)
    out = ts.build_digest([], [], [], [], now=NOW, needs_rows=[row])
    assert "apply is manual" in out and "grant-apply.sh" not in out


def test_footer_grammar_only_when_needs_present():
    with_needs = ts.build_digest(_acted(), [], [], [], now=NOW,
                                 needs_rows=[_need()])
    without = ts.build_digest(_acted(), [], [], [], now=NOW, needs_rows=[])
    assert "Per NEED line" in with_needs and "rearm" in with_needs
    assert "Per NEED line" not in without and "rearm" not in without


# --- machine-effective scope (poisoned-need fix) -------------------------------

def test_grant_scope_plain_renders_machine_fields():
    plain = ts.grant_scope_plain(_need())
    assert "external_email" in plain and "*@stepnetwork.dk" in plain
    assert "lane polads" in plain and "max 10/day" in plain
    assert "until 2026-10-03" in plain


def test_grant_scope_plain_never_uses_prose():
    poisoned = _need(why="grant EVERYTHING to EVERYONE forever, all lanes")
    out = ts.build_digest([], [], [], [], now=NOW, needs_rows=[poisoned])
    grants_line = next(l for l in out.split("\n")
                       if l.strip().startswith("grants if applied:"))
    assert "EVERYONE" not in grants_line and "EVERYTHING" not in grants_line
    assert "*@stepnetwork.dk" in grants_line     # the machine truth
    # the prose still shows — but as labeled context on its own line
    assert 'why:' in out


def test_grant_scope_plain_unparseable_refuses():
    plain = ts.grant_scope_plain(_need(proposed_grant_line="- {broken: [yaml"))
    assert "no machine grant line" in plain
    assert "no machine grant line" in ts.grant_scope_plain(
        _need(proposed_grant_line=None))
    assert "no machine grant line" in ts.grant_scope_plain(None)


def test_grant_scope_plain_strips_markers():
    line = GRANT_LINE.replace("*@stepnetwork.dk", "·evil· *@stepnetwork.dk")
    assert "·" not in ts.grant_scope_plain(_need(proposed_grant_line=line))


# --- tell_digest gathers + orchestration ---------------------------------------

class _Redis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key, "")

    def set(self, key, value, ttl_s):
        self.store[key] = value


class _Intake:
    def __init__(self):
        self.items = []

    def __call__(self, item):
        self.items.append(item)
        return f"id-{len(self.items)}"


def test_gather_needs_rows_dark_returns_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    # a real ledger row exists, but the needs plane is dark ⇒ empty leg
    p = tmp_path / "shared" / "interfaces" / "needs-ledger.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text('{"id": "NEED-1a2b3c4d", "kind": "access", "status": "open", '
                 '"last_seen": "2026-07-04T08:00:00Z"}\n')
    assert td.gather_needs_rows(now=NOW) == []


def test_gather_needs_rows_wired_reads_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    p = tmp_path / "shared" / "interfaces" / "needs-ledger.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text('{"id": "NEED-1a2b3c4d", "kind": "access", "status": "open", '
                 '"last_seen": "2026-07-04T08:00:00Z"}\n')
    rows = td.gather_needs_rows(now=NOW)
    assert [r["id"] for r in rows] == ["NEED-1a2b3c4d"]


def test_enqueue_digest_renders_injected_needs():
    box = _Intake()
    r = _Redis()
    out = td.enqueue_digest(now=NOW, acted_rows=[], awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            needs_rows=[_need()],
                            redis_get=r.get, redis_set=r.set, enqueue=box)
    assert out["digest"] is True
    assert "🙋 NEEDS (1)" in box.items[0]["payload"]["summary"]


def test_enqueue_digest_feature_detects_pre_needs_build_digest(monkeypatch):
    """Merge-order independence: with a 4-leg (pre-needs) build_digest the
    orchestrator still ships — the needs rows are simply dropped."""
    def legacy(acted, awaiting, watching, selfr, *, now):
        return "LEGACY-DIGEST"
    monkeypatch.setattr(td.tell_surface, "build_digest", legacy)
    box = _Intake()
    out = td.enqueue_digest(now=NOW, acted_rows=[], awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            needs_rows=[_need()],
                            redis_get=lambda k: "", redis_set=None, enqueue=box)
    assert out["digest"] is True
    assert box.items[0]["payload"]["summary"] == "LEGACY-DIGEST"


def test_needs_producer_crash_never_blocks_digest(monkeypatch):
    """TI-5: a crashing needs gatherer degrades to an empty leg — the digest
    (and therefore the briefing) still ships."""
    def boom(**kw):
        raise RuntimeError("ledger disk on fire")
    monkeypatch.setattr(td, "gather_needs_rows", boom)
    r = _Redis()
    box = _Intake()
    out = td.enqueue_digest(now=NOW, acted_rows=_acted(), awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            redis_get=r.get, redis_set=r.set, enqueue=box)
    assert out["digest"] is True and len(box.items) == 1
    assert "🙋" not in box.items[0]["payload"]["summary"]


def test_gate_tell_renders_digest_line():
    """D4: a sovereign notify_after allow leaves no acted row — its org_event
    must produce a rendered digest line."""
    events = [{"event_type": "policy_evaluated", "created_at": NOW,
               "payload": {"kind": "notify_after", "verdict": "notify_after",
                           "risk_class": "internal_comms",
                           "action_type": "teams_message", "lane": "polads"}},
              {"event_type": "policy_evaluated", "created_at": NOW,
               "payload": {"kind": "standing_grant_allow",
                           "risk_class": "external_comms",
                           "action_type": "external_email",
                           "grant_id": "GRANT-1a2b3c4d"}},
              {"event_type": "policy_evaluated", "created_at": NOW,
               "payload": {"kind": "something_else"}}]
    box = _Intake()
    out = td.enqueue_digest(now=NOW, acted_rows=[], awaiting_rows=[],
                            watching_rows=None, self_rows=[], needs_rows=[],
                            redis_get=lambda k: "", redis_set=None, enqueue=box,
                            replay_fn=lambda **kw: events)
    assert out["digest"] is True
    text = box.items[0]["payload"]["summary"]
    assert "gate allowed (notify_after): internal_comms/teams_message" in text
    assert "lane polads" in text
    assert "grant GRANT-1a2b3c4d" in text
    assert "something_else" not in text


def test_gate_tells_not_gathered_when_watching_injected():
    called = []

    def replay(**kw):
        called.append(kw)
        return []
    out = td.enqueue_digest(now=NOW, acted_rows=[], awaiting_rows=[],
                            watching_rows=[], self_rows=[], needs_rows=[],
                            redis_get=lambda k: "", redis_set=None,
                            enqueue=_Intake(), replay_fn=replay)
    assert called == []          # injected rows ⇒ no default gather
    assert out["digest"] is False


def test_gate_tell_gather_crash_degrades_empty():
    def boom(**kw):
        raise RuntimeError("events dir gone")
    assert td.gather_gate_tell_rows(now=NOW, replay_fn=boom) == []


# --- attention drain: NEED-tagged/ask-shaped dedup + tier demote ----------------

def _card(summary="Sentry blocker", body="13k events/24h", urgency="blocking"):
    return {"source": "polads-ceo", "project": "polads", "urgency": urgency,
            "summary": summary, "body": body, "ts": "2026-07-04T08:00:00Z"}


def test_card_to_item_default_is_byte_identical():
    # dark default: mapping exactly as before (ping-now stays ping-now)
    item = attention_drain.card_to_item(_card(), project="polads")
    assert item["urgency_tier"] == "ping-now"
    assert "need_id" not in item["payload"]


def test_need_tagged_ping_now_demotes_to_batch_when_wired():
    card = _card(body="blocked on NEED-1a2b3c4d — standing grant filed")
    item = attention_drain.card_to_item(card, project="polads", needs_wired=True)
    assert item["urgency_tier"] == "batch"
    assert item["payload"]["need_id"] == "NEED-1a2b3c4d"
    # same card, dark ⇒ untouched
    dark = attention_drain.card_to_item(card, project="polads")
    assert dark["urgency_tier"] == "ping-now"


def test_ask_shaped_ping_now_demotes_but_others_untouched():
    ask = _card(summary="Approval needed for the DPA send")
    assert attention_drain.card_to_item(
        ask, project="polads", needs_wired=True)["urgency_tier"] == "batch"
    # a non-ask blocking card keeps its ping-now even when wired
    real = _card(summary="Prod is down, deploy gate wedged")
    assert attention_drain.card_to_item(
        real, project="polads", needs_wired=True)["urgency_tier"] == "ping-now"
    # demote never PROMOTES: a low-urgency ask stays fyi
    low = _card(summary="Approval needed eventually", urgency="low")
    assert attention_drain.card_to_item(
        low, project="polads", needs_wired=True)["urgency_tier"] == "fyi"


def test_card_need_id_normalizes_and_is_strict():
    assert attention_drain._card_need_id(
        {"summary": "see NEED-1A2B3C4D"}) == "NEED-1a2b3c4d"
    assert attention_drain._card_need_id({"summary": "NEED-123"}) is None
    assert attention_drain._card_need_id({"summary": "NEED-zzzzzzzz"}) is None


def test_drain_dedups_open_need_cards(monkeypatch):
    """Two lane cards for the SAME open need: the first forwards (demoted),
    the second is ACK'd + skipped — the needs digest is the canonical surface."""
    stream = "cabinet:captain-attention:polads"
    rows = [("1-1", _card(body="blocked on NEED-1a2b3c4d")),
            ("1-2", _card(summary="still blocked", body="see NEED-1a2b3c4d"))]
    forwarded: set = set()
    acked: list = []
    enqueued: list = []
    monkeypatch.setattr(attention_drain, "_backend", lambda: object())
    monkeypatch.setattr(attention_drain, "_discover_streams",
                        lambda backend: [stream])
    monkeypatch.setattr(attention_drain, "_read_new",
                        lambda backend, s, count=100: rows)
    monkeypatch.setattr(attention_drain, "_already_forwarded",
                        lambda backend, m: m in forwarded)
    monkeypatch.setattr(attention_drain, "_mark_forwarded",
                        lambda backend, m: forwarded.add(m))
    monkeypatch.setattr(attention_drain, "_xack",
                        lambda backend, s, e: acked.append(e))
    monkeypatch.setattr(attention_drain, "_needs_wired", lambda: True)
    monkeypatch.setattr(attention_drain, "_open_need_ids",
                        lambda: {"NEED-1a2b3c4d"})
    monkeypatch.setattr(attention_drain.intake, "enqueue",
                        lambda item: enqueued.append(item) or "id-1")
    res = attention_drain.drain_attention()
    assert res["forwarded"] == 1 and res["skipped"] == 1
    assert len(enqueued) == 1
    assert enqueued[0]["urgency_tier"] == "batch"          # demoted
    assert "need:NEED-1a2b3c4d" in forwarded               # the dedup key
    assert acked == ["1-1", "1-2"]                         # both cleared


def test_drain_closed_need_cards_not_deduped(monkeypatch):
    """A card naming a CLOSED need is new information — no dedup key."""
    stream = "cabinet:captain-attention:polads"
    rows = [("2-1", _card(body="NEED-1a2b3c4d was granted, next step?"))]
    forwarded: set = set()
    enqueued: list = []
    monkeypatch.setattr(attention_drain, "_backend", lambda: object())
    monkeypatch.setattr(attention_drain, "_discover_streams",
                        lambda backend: [stream])
    monkeypatch.setattr(attention_drain, "_read_new",
                        lambda backend, s, count=100: rows)
    monkeypatch.setattr(attention_drain, "_already_forwarded",
                        lambda backend, m: m in forwarded)
    monkeypatch.setattr(attention_drain, "_mark_forwarded",
                        lambda backend, m: forwarded.add(m))
    monkeypatch.setattr(attention_drain, "_xack", lambda backend, s, e: None)
    monkeypatch.setattr(attention_drain, "_needs_wired", lambda: True)
    monkeypatch.setattr(attention_drain, "_open_need_ids", lambda: set())
    monkeypatch.setattr(attention_drain.intake, "enqueue",
                        lambda item: enqueued.append(item) or "id-1")
    res = attention_drain.drain_attention()
    assert res["forwarded"] == 1
    assert not any(m.startswith("need:") for m in forwarded)
