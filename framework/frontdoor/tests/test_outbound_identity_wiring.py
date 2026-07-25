"""Outbound identity + machine-provenance disclosure, WIRED (2026-07-25).

The module tests (framework/tests/test_outbound_identity.py) prove the policy
engine. These arms prove the engine is actually ON the paths that reach a human
who is not the Captain — which is the only thing that matters, and the thing a
policy module can be perfectly correct about while changing nothing.

Both directions are established by construction, not by absence: every arm here
was run against origin/master with `framework/outbound_identity.py` copied in
but the WIRING reverted, and every arm went red there. So each failure is
"the seam does not stamp", never "the module is missing".

The four wired seams:
  * chair_drafts.present_draft  — composition (what the Captain approves IS what
    the recipient reads), and whose signature closes it
  * chair_drafts.deliver_draft  — the fail-closed egress, including a Captain
    `edit: <text>` override that never passed through present_draft
  * action_exec Monday note bodies — a note on an item the lane did NOT create
  * channels.ChannelAdapter      — the outbox ledger records whether an outbound
    message that owed a disclosure actually carried one
"""
from __future__ import annotations

import json

import pytest

import framework.sources as sources
from framework import outbound_identity as oi
from framework.channels import contract as C
from framework.frontdoor import action_exec as ax
from framework.frontdoor import action_undo as au
from framework.frontdoor import chair_drafts
from framework.events.emitter import replay


# ---------------------------------------------------------------------------
# shared fakes
# ---------------------------------------------------------------------------

class FakeRedis:
    """Dict-backed stand-in for chair_drafts._r (argv-shaped)."""

    def __init__(self, store=None):
        self.store = dict(store or {})

    def __call__(self, *args):
        verb = args[0]
        if verb == "GET":
            return self.store.get(args[1], "")
        if verb == "DEL":
            self.store.pop(args[1], None)
            return "1"
        if verb == "SET":
            self.store[args[1]] = args[2]
            return "OK"
        return ""


class Dispatch:
    """Records what actually reached the egress; signs like the captain."""

    MARK = "CAPTAIN-SIG"

    def __init__(self):
        self.delivered = []

    def ensure_signature(self, text, channel):
        return text + "\n\n" + self.MARK

    def deliver(self, *, record, override_text="", dry_run=False):
        self.delivered.append((record, override_text, dry_run))
        return {"ok": True, "via": record.get("channel")}


class StillAwaitingSource:
    """Pins the verify-at-fire seam to FIRE (the captain has not replied himself
    and the thread is still open), exactly as test_fire_gate_casey's control arm
    does. Without this the suite is order-dependent: `framework.sources` caches
    whatever binding an earlier module resolved, and a live source that reports
    "no longer awaiting" self-cancels the draft BEFORE the egress — which would
    make these arms silently stop exercising the disclosure they exist to test."""

    def available(self):
        return True

    def captain_replied_since(self, slug, when):
        return False

    def still_awaiting(self, slug, hours=72):
        return True


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """A hermetic frontdoor: tmp deployment root (=> the SAFE DEFAULT identity),
    fake store, fake dispatch, captured Chair message, fire gate pinned open."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_DRAFT_QUEUE_DIR", str(tmp_path / "drafts"))
    monkeypatch.delenv("CABINET_VERIFY_AT_FIRE", raising=False)
    monkeypatch.setattr(sources, "_source_cache", StillAwaitingSource())
    store = FakeRedis()
    dispatch = Dispatch()
    sent = []
    monkeypatch.setattr(chair_drafts, "_r", store)
    monkeypatch.setattr(chair_drafts, "get_dispatch", lambda: dispatch)
    monkeypatch.setattr(chair_drafts.channel, "send", lambda body: sent.append(body))
    return {"store": store, "dispatch": dispatch, "sent": sent, "root": tmp_path}


def _line(channel="email"):
    """The disclosure this deployment owes on `channel`. Asserting against this
    rather than a hardcoded string keeps the arms honest across config, and the
    guard below keeps them from passing vacuously on an empty line."""
    line = oi.disclosure_line(channel)
    assert line and oi.MACHINE_MARK in line, "no disclosure configured — arm is vacuous"
    return line


def _stored(wired_env, pid):
    return json.loads(wired_env["store"].store["cabinet:draft:%s" % pid])


# ---------------------------------------------------------------------------
# present_draft — composition
# ---------------------------------------------------------------------------

class TestPresentDraft:
    def test_the_captains_signature_is_not_applied_by_default(self, wired):
        pid = chair_drafts.present_draft(
            "Bo", "email", "Hi Bo — shipping Tuesday.",
            recipient_email="bo@example.invalid")
        stored = _stored(wired, pid)
        assert Dispatch.MARK not in stored["draft"], \
            "machine-written mail still closed with the captain's own signature"
        assert Dispatch.MARK not in wired["sent"][0]

    def test_the_presented_and_stored_bytes_both_disclose(self, wired):
        """The Captain approves exactly what the recipient will read — the
        disclosure is in the text he sees AND in the bytes stored for verbatim
        send, not bolted on afterwards."""
        pid = chair_drafts.present_draft(
            "Bo", "email", "Hi Bo — shipping Tuesday.",
            recipient_email="bo@example.invalid")
        line = _line("email")
        assert line in _stored(wired, pid)["draft"]
        assert line in wired["sent"][0]

    def test_a_teams_draft_discloses_too(self, wired):
        pid = chair_drafts.present_draft("Bo", "teams", "quick one")
        assert _line("teams") in _stored(wired, pid)["draft"]

    def test_the_record_carries_the_cabinets_own_addressing(self, wired):
        pid = chair_drafts.present_draft("Bo", "email", "Body")
        sender = _stored(wired, pid)["sender"]
        assert sender["mode"] == oi.MODE_CABINET
        assert sender["from_address"] == ""          # nothing invented
        assert sender["disclosure_required"] is True

    def test_captain_mode_restores_his_signature_and_still_discloses(
            self, wired, monkeypatch):
        cfg = oi.config_path(wired["root"])
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("version: 1\nidentity:\n  mode: captain\n", encoding="utf-8")
        pid = chair_drafts.present_draft("Bo", "email", "Body")
        draft = _stored(wired, pid)["draft"]
        assert Dispatch.MARK in draft                # opt-in honoured
        assert _line("email") in draft               # still says a machine sent it


# ---------------------------------------------------------------------------
# deliver_draft — the fail-closed egress
# ---------------------------------------------------------------------------

class TestDeliverEgress:
    def _seed(self, wired, draft="Raw text that bypassed present_draft.",
              channel="email"):
        rec = {"slug": "bo", "person": "Bo", "channel": channel,
               "recipient_email": "bo@example.invalid", "draft": draft,
               "lane": "send-1to1-reply", "queued_ts": "2026-07-25T08:00:00Z"}
        wired["store"].store["cabinet:draft:abc123"] = json.dumps(rec)
        return "abc123"

    def test_a_draft_that_bypassed_present_draft_is_still_disclosed(self, wired):
        pid = self._seed(wired)
        res = chair_drafts.deliver_draft(pid)
        assert res["ok"] is True
        record, _override, _dry = wired["dispatch"].delivered[0]
        assert _line("email") in record["draft"]

    def test_a_captain_edit_override_is_disclosed(self, wired):
        """`edit: <text>` sends the Captain's own words — but a machine still
        sends them, on the cabinet's channel, so the recipient is still told."""
        pid = self._seed(wired)
        chair_drafts.deliver_draft(pid, override_text="My own wording, thanks.")
        _record, override, _dry = wired["dispatch"].delivered[0]
        assert override.startswith("My own wording, thanks.")
        assert _line("email") in override

    def test_an_already_disclosed_draft_is_byte_unchanged(self, wired):
        prepared = oi.stamp("Hi Bo.", "email")
        pid = self._seed(wired, draft=prepared)
        chair_drafts.deliver_draft(pid)
        record, _override, _dry = wired["dispatch"].delivered[0]
        assert record["draft"] == prepared
        assert record["draft"].count(oi.MACHINE_MARK) == 1


# ---------------------------------------------------------------------------
# Monday note bodies — the artifact a colleague actually reads
# ---------------------------------------------------------------------------

class MondaySpy:
    def __init__(self):
        self.calls = []

    def __call__(self, query, variables):
        self.calls.append((query, variables))
        if "create_item" in query:
            return {"create_item": {"id": "12345"}}
        return {"create_update": {"id": "u1"}, "change_column_value": {"id": "c1"}}

    def bodies(self):
        return [v.get("body") for q, v in self.calls if "create_update" in q]


def _action_store(steps, **extra):
    rec = {"lane": "bakery", "steps": steps, **extra}
    return lambda k: json.dumps(rec) if k.startswith("cabinet:action:") else ""


@pytest.fixture
def hermetic_actions(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))
    monkeypatch.setattr(ax, "_redis", lambda *a, **k: "")
    monkeypatch.setattr(au, "_default_redis_set", lambda *a, **k: None)
    monkeypatch.setattr(au, "_default_redis_get", lambda *a, **k: "")
    monkeypatch.setattr(au, "_default_redis_del", lambda *a, **k: None)
    monkeypatch.setattr(ax.env, "_officers_cache", ("cos", "bakery-ceo"))
    yield


class TestMondayNoteBodies:
    def test_a_note_on_someone_elses_item_says_a_machine_wrote_it(
            self, hermetic_actions):
        """monday_task_update posts onto an item the lane did NOT create, so the
        body is the ONLY thing the colleague reads — a bare correlation id is not
        a human-legible statement of authorship."""
        spy = MondaySpy()
        ax.deliver_action(
            "pm-note", redis_get=_action_store([{
                "kind": "monday_task_update",
                "payload": {"monday_id": "9", "board_id": "42424242",
                            "set": {"status": "Done"},
                            "why": "closed after the deploy landed"}}]),
            monday_post=spy, osascript=lambda c: "ok")
        body = next(b for b in spy.bodies() if b)
        assert body.startswith(ax.PROVENANCE_BANNER)
        assert "closed after the deploy landed" in body

    def test_a_created_items_description_carries_it_too(self, hermetic_actions):
        spy = MondaySpy()
        ax.deliver_action(
            "pm-create", redis_get=_action_store([{
                "kind": "monday_task_create",
                "payload": {"board_id": "42424242", "title": "Ship it",
                            "description": "from the scrum"}}]),
            monday_post=spy, osascript=lambda c: "ok")
        body = next(b for b in spy.bodies() if b)
        assert body.startswith(ax.PROVENANCE_BANNER)

    def test_the_banner_is_idempotent_on_bodies(self):
        once = ax._apply_body_banner("note")
        assert ax._apply_body_banner(once) == once

    def test_an_empty_body_stays_empty(self):
        assert ax._apply_body_banner("") == ""
        assert ax._apply_body_banner("   ") == "   "


# ---------------------------------------------------------------------------
# The channel-adapter seam — the outbox ledger tells on an undisclosed send
# ---------------------------------------------------------------------------

class Recorder(C.ChannelAdapter):
    name = "recorder"
    capabilities = frozenset({"send"})
    undo_contract = C.UndoContract.delete_window(60)

    def _dispatch_send(self, recipient, body, thread_id):
        return "art-1"


class TestChannelLedger:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))

    def _payload(self):
        events = replay(event_types=["outbox_dispatched"])
        assert len(events) == 1
        return events[0]["payload"]

    def test_an_undisclosed_outbound_is_a_visible_ledger_fact(self):
        Recorder(org_domains={"acme.com"}).send("bo@acme.com", "hello world")
        p = self._payload()
        assert p["disclosure_required"] is True
        assert p["disclosed"] is False

    def test_a_disclosed_outbound_records_that_it_was(self):
        body = oi.stamp("hello world", "recorder")
        Recorder(org_domains={"acme.com"}).send("bo@acme.com", body)
        p = self._payload()
        assert p["disclosure_required"] is True and p["disclosed"] is True

    def test_an_internal_colleague_is_not_exempt(self):
        """org_domains covers a whole media group on the live deployment, so
        thousands of third parties classify `internal`. Internal is not the
        Captain, and owes the same disclosure."""
        a = Recorder(org_domains={"acme.com"})
        a.send("colleague@acme.com", "hi")
        p = self._payload()
        assert p["audience"] == C.INTERNAL and p["disclosure_required"] is True

    def test_the_body_still_never_reaches_the_ledger(self):
        Recorder(org_domains={"acme.com"}).send("bo@acme.com", "SECRET-BODY")
        assert "SECRET-BODY" not in json.dumps(self._payload())
