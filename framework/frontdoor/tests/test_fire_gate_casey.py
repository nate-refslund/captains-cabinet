"""THE WORKED CASEY CASE (captain-surface master prompt §3.5, 2026-07-10) —
the regression test for verify-at-fire on the send path.

What happened: a reply draft to Casey was queued and presented; the captain
then replied to Casey HIMSELF. The queued draft kept dangling, ready to fire
on a later (mis)tap — the confusion the master prompt names. The law: at fire
time the send path re-gathers; a draft overtaken by reality SELF-CANCELS,
never fires, and journals why.

This exercises the REAL chokepoint — ``chair_drafts.deliver_draft`` (the only
egress, called by the binder on the captain's 'send' reply) — with the store,
the dispatch, and the personal source all injected."""
import json

import pytest

import framework.sources as sources
from framework.acting import draft_queue
from framework.frontdoor import chair_drafts


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

    # FakeKV face for draft_queue (same underlying dict).
    def get(self, key):
        return self.store.get(key) or None

    def delete(self, key):
        self.store.pop(key, None)

    def keys(self, prefix):
        return [k for k in self.store if k.startswith(prefix)]


class SpyDispatch:
    """Explodes if the egress is reached when it must not be; records calls."""

    def __init__(self, allow=False):
        self.allow = allow
        self.delivered = []

    def deliver(self, *, record, override_text="", dry_run=False):
        if not self.allow:
            raise AssertionError(
                "dispatch.deliver reached — the stale Casey draft FIRED")
        self.delivered.append((record, override_text, dry_run))
        return {"ok": True, "via": record.get("channel"), "dry_run": dry_run}

    def ensure_signature(self, text, channel):
        return text


class FakeSource:
    def __init__(self, replied=None, awaiting=None):
        self._replied = replied
        self._awaiting = awaiting

    def available(self):
        return True

    def captain_replied_since(self, slug, when):
        return self._replied

    def still_awaiting(self, slug, hours=72):
        return self._awaiting


CASEY_REC = {
    "slug": "casey", "person": "Casey", "channel": "email",
    "recipient_email": "casey@example.invalid",
    "draft": "Hi Casey — following up on the schedule.",
    "why": "draft reply (lane)", "lane": "send-1to1-reply",
    "queued_ts": "2026-07-10T08:00:00Z",
}


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_DRAFT_QUEUE_DIR", str(tmp_path / "drafts"))
    monkeypatch.delenv("CABINET_VERIFY_AT_FIRE", raising=False)


def _wire(monkeypatch, *, source, dispatch, store=None):
    fake = FakeRedis(store or {"cabinet:draft:c4s3y1": json.dumps(CASEY_REC)})
    monkeypatch.setattr(chair_drafts, "_r", fake)
    monkeypatch.setattr(chair_drafts, "get_dispatch", lambda: dispatch)
    # fire_gate resolves the seam via framework.sources.get_source(), which
    # returns the module cache when set — inject there, auto-restored.
    monkeypatch.setattr(sources, "_source_cache", source)
    return fake


def test_casey_case_queued_draft_self_cancels_never_fires(monkeypatch):
    """The captain replied to Casey himself AFTER the draft was queued →
    at fire the draft self-cancels: no egress, store cleared, journal row,
    plain-language reason back to the Chair."""
    dispatch = SpyDispatch(allow=False)   # any deliver() call = test failure
    fake = _wire(monkeypatch, source=FakeSource(replied=True),
                 dispatch=dispatch)

    res = chair_drafts.deliver_draft("c4s3y1")

    assert res["ok"] is False and res.get("cancelled") is True
    # Plain sentence (plain-language law) — names Casey, says it wasn't sent.
    assert "Not sent" in res["reason"] and "Casey" in res["reason"]
    # Never fired.
    assert dispatch.delivered == []
    # Self-cancelled: the queued record is gone.
    assert "cabinet:draft:c4s3y1" not in fake.store
    # Journaled with the evidence.
    row = draft_queue.withdrawal_of("c4s3y1")
    assert row is not None and row["kind"] == "fire-cancel"
    assert row["checks"]["captain_replied_since"] is True
    assert row["record"]["slug"] == "casey"


def test_casey_case_second_tap_gets_the_honest_reason(monkeypatch):
    """After the self-cancel, a later 'send' tap on the same id explains
    itself instead of the generic 'expired or already sent' miss."""
    dispatch = SpyDispatch(allow=False)
    fake = _wire(monkeypatch, source=FakeSource(replied=True),
                 dispatch=dispatch)
    chair_drafts.deliver_draft("c4s3y1")            # self-cancels
    res2 = chair_drafts.deliver_draft("c4s3y1")     # the captain taps again
    assert res2["ok"] is False and res2.get("withdrawn") is True
    assert "Casey" in res2["reason"]
    assert dispatch.delivered == []


def test_still_needed_draft_fires_normally(monkeypatch):
    """Control: no captain reply, thread still awaiting → the approved draft
    delivers exactly as before, with the verification attached."""
    dispatch = SpyDispatch(allow=True)
    fake = _wire(monkeypatch, source=FakeSource(replied=False, awaiting=True),
                 dispatch=dispatch)
    res = chair_drafts.deliver_draft("c4s3y1")
    assert res["ok"] is True
    assert len(dispatch.delivered) == 1
    assert res["verify"]["action"] == "fire"
    # Store cleared by the normal post-send path.
    assert "cabinet:draft:c4s3y1" not in fake.store


def test_uncertainty_never_blocks_an_approved_send(monkeypatch):
    """Unknown estate (both probes None) → the captain's explicit approval
    wins: the draft fires."""
    dispatch = SpyDispatch(allow=True)
    _wire(monkeypatch, source=FakeSource(replied=None, awaiting=None),
          dispatch=dispatch)
    res = chair_drafts.deliver_draft("c4s3y1")
    assert res["ok"] is True and len(dispatch.delivered) == 1


def test_dry_run_reports_would_cancel_without_removing(monkeypatch):
    """dry_run keeps its wiring-test role: the would-cancel verdict is
    reported, nothing is removed, nothing really sends."""
    dispatch = SpyDispatch(allow=True)
    fake = _wire(monkeypatch, source=FakeSource(replied=True),
                 dispatch=dispatch)
    res = chair_drafts.deliver_draft("c4s3y1", dry_run=True)
    assert res["verify"]["action"] == "cancel"
    assert "cabinet:draft:c4s3y1" in fake.store     # retained
    assert dispatch.delivered and dispatch.delivered[0][2] is True  # dry


def test_force_overrides_the_gate(monkeypatch):
    """An explicit 'send anyway' fires even when the gate would cancel."""
    dispatch = SpyDispatch(allow=True)
    _wire(monkeypatch, source=FakeSource(replied=True), dispatch=dispatch)
    res = chair_drafts.deliver_draft("c4s3y1", force=True)
    assert res["ok"] is True and len(dispatch.delivered) == 1
    assert res["verify"]["reason"] == "forced"
