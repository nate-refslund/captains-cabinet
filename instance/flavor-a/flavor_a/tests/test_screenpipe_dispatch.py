"""Tests for the Flavor-A dispatch adapter (``flavor_a.screenpipe_dispatch``, SRC-3).

``ScreenpipeDispatch`` OWNS the re-homed frontdoor-egress bodies: the former
``chair_drafts.deliver_draft`` SEND execution + ``_apply_signature``, and the
former ``daily_recap._write_vault`` / ``_vault_path`` / ``_sp`` / LLM-model
bodies. These tests PIN that the re-home is byte-identical to what ran when those
bodies lived in ``framework/`` — using INJECTED fake screenpipe libs (no real
estate, no Graph, no vault):

  * ``deliver`` drives the EXACT Microsoft Graph call sequence per branch —
    fresh send / threaded reply / already-replied guard / teams / dry-run /
    no-address — and returns the SAME result dicts (dest/via on the ok path);
  * ``ensure_signature`` delegates to ``draft_lib.ensure_signature`` and fails
    OPEN (returns the draft unchanged) on any error;
  * ``write_daily_note`` is the marker-guarded sha256 write-if-changed;
  * ``daily_note_path`` is the pure dry-preview path;
  * it satisfies ``framework.sources.base.PersonalDispatch`` structurally, and
    ``framework.sources.get_dispatch()`` binds it on THIS instance.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# instance/flavor-a on sys.path so ``flavor_a`` imports; repo root so
# ``framework.*`` resolves. tests/ [0] flavor_a [1] flavor-a [2] instance [3] root [4]
_PKG_PARENT = Path(__file__).resolve().parents[2]   # instance/flavor-a
_REPO_ROOT = Path(__file__).resolve().parents[4]    # worktree / repo root
for _p in (str(_REPO_ROOT), str(_PKG_PARENT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flavor_a.screenpipe_dispatch import ScreenpipeDispatch
from framework.sources.base import PersonalDispatch


# ---------------------------------------------------------------------------
# Fake screenpipe send libs — record calls; drive the deliver() branches.
# ---------------------------------------------------------------------------
class FakeEmailLib:
    """Stands in for ``email_lib``: a stateful Graph fake. ``inbox`` seeds thread
    resolution; a reply POST marks the matched conversation as landed in Sent, so
    the pre/post verify-sent checks behave exactly as against the real proxy."""

    def __init__(self, inbox=None, sent=None, send_result=None):
        self.inbox = list(inbox or [])
        self.sent = list(sent or [])            # conversationIds present in Sent
        self.send_result = send_result if send_result is not None else {"ok": True, "sent": True}
        self.calls = []

    def msgraph_call(self, url=None, method="GET", top=None, select=None,
                     orderby=None, body=None, retries=None):
        self.calls.append({"fn": "msgraph_call", "url": url, "method": method,
                           "body": body, "retries": retries})
        u = url or ""
        if method == "POST" and u.endswith("/reply"):
            gid = u.split("/messages/", 1)[1].rsplit("/reply", 1)[0]
            for m in self.inbox:
                if m.get("id") == gid:
                    self.sent.append(m.get("conversationId"))
            return {}
        if "inbox" in u:
            return {"value": list(self.inbox)}
        if "sentitems" in u:
            return {"value": [{"conversationId": c, "sentDateTime": "t"} for c in self.sent]}
        return {}

    def send_email(self, addr, subject, html, content_type="HTML"):
        self.calls.append({"fn": "send_email", "addr": addr, "subject": subject,
                           "html": html, "content_type": content_type})
        return dict(self.send_result)


class FakeTeamsLib:
    def __init__(self, result=None):
        self.result = result if result is not None else {"ok": True, "sent": True}
        self.calls = []

    def send_teams_to_email(self, addr, text, name=None):
        self.calls.append({"addr": addr, "text": text, "name": name})
        return dict(self.result)


class FakeDraftLib:
    def __init__(self, raise_it=False):
        self.raise_it = raise_it
        self.calls = []

    def ensure_signature(self, text, channel):
        self.calls.append({"text": text, "channel": channel})
        if self.raise_it:
            raise RuntimeError("boom")
        return text + "\n-- Nate"


@pytest.fixture
def _inject(monkeypatch):
    """Inject fake screenpipe libs into ``sys.modules`` so the adapter's lazy
    ``import email_lib`` / ``teams_graph_lib`` / ``draft_lib`` bind the fakes (a
    module in sys.modules wins over anything on ~/.screenpipe on sys.path).
    Auto-restored by monkeypatch."""
    def _do(email=None, teams=None, draft=None):
        if email is not None:
            monkeypatch.setitem(sys.modules, "email_lib", email)
        if teams is not None:
            monkeypatch.setitem(sys.modules, "teams_graph_lib", teams)
        if draft is not None:
            monkeypatch.setitem(sys.modules, "draft_lib", draft)
    return _do


def _rec(person="Morten", draft="Hej Morten\n\nTak for din besked.", channel="email",
         addr="morten@ex.com", subject="Re: DPA"):
    return {"person": person, "draft": draft, "channel": channel,
            "recipient_email": addr, "subject": subject, "last_subject": subject}


# ---------------------------------------------------------------------------
# Protocol conformance + binding.
# ---------------------------------------------------------------------------
def test_satisfies_personaldispatch_protocol():
    assert isinstance(ScreenpipeDispatch(), PersonalDispatch)


def test_get_dispatch_binds_screenpipe_dispatch_on_this_instance():
    from framework import sources as src_pkg
    src_pkg._reset_cache()
    try:
        assert type(src_pkg.get_dispatch()).__name__ == "ScreenpipeDispatch"
    finally:
        src_pkg._reset_cache()


# ---------------------------------------------------------------------------
# ensure_signature — delegate + fail-open.
# ---------------------------------------------------------------------------
def test_ensure_signature_delegates(_inject):
    dl = FakeDraftLib()
    _inject(draft=dl)
    out = ScreenpipeDispatch().ensure_signature("Body", "email")
    assert out == "Body\n-- Nate"
    assert dl.calls == [{"text": "Body", "channel": "email"}]


def test_ensure_signature_fails_open(_inject):
    _inject(draft=FakeDraftLib(raise_it=True))
    # any error → the draft unchanged (former _apply_signature behavior)
    assert ScreenpipeDispatch().ensure_signature("Body", "email") == "Body"


# ---------------------------------------------------------------------------
# deliver — the Graph send sequence, per branch (byte-identical to deliver_draft).
# ---------------------------------------------------------------------------
def test_deliver_email_fresh_send(_inject):
    """No matching thread → a FRESH send_email(addr, subject, html HTML)."""
    el = FakeEmailLib(inbox=[])                 # nothing to thread into
    _inject(email=el)
    res = ScreenpipeDispatch().deliver(_rec(draft="Line1\nLine2"))
    assert res["ok"] is True
    assert res["via"] == "email" and res["dest"] == "morten@ex.com"
    sends = [c for c in el.calls if c["fn"] == "send_email"]
    assert len(sends) == 1
    s = sends[0]
    assert s["addr"] == "morten@ex.com" and s["subject"] == "Re: DPA"
    assert s["content_type"] == "HTML"
    # HTML preserves the newline as <br> (the Morten one-line-flatten fix)
    assert s["html"] == "Line1<br>\nLine2"
    # a fresh send does NOT POST a /reply
    assert not any(c.get("method") == "POST" for c in el.calls)


def test_deliver_email_threaded_reply(_inject):
    """A matching inbox thread → a Graph /reply POST (retries=0), then confirmed."""
    inbox = [{"id": "GID1", "conversationId": "C1", "subject": "DPA",
              "from": {"emailAddress": {"address": "morten@ex.com"}}}]
    el = FakeEmailLib(inbox=inbox)
    _inject(email=el)
    res = ScreenpipeDispatch().deliver(_rec())
    assert res["ok"] is True and res["threaded"] is True
    assert res["via"] == "email" and res["dest"] == "morten@ex.com"
    posts = [c for c in el.calls if c.get("method") == "POST"]
    assert len(posts) == 1
    assert posts[0]["url"] == "/v1.0/me/messages/GID1/reply"
    assert posts[0]["retries"] == 0
    assert posts[0]["body"]["message"]["body"]["contentType"] == "HTML"
    # a threaded reply never calls send_email (fresh)
    assert not any(c["fn"] == "send_email" for c in el.calls)


def test_deliver_email_already_replied_never_resends(_inject):
    """Sent already carries the conversation → 'already-replied', NO reply POST
    (the 4x-Morten resend guard)."""
    inbox = [{"id": "GID1", "conversationId": "C1", "subject": "DPA",
              "from": {"emailAddress": {"address": "morten@ex.com"}}}]
    el = FakeEmailLib(inbox=inbox, sent=["C1"])   # already in Sent
    _inject(email=el)
    res = ScreenpipeDispatch().deliver(_rec())
    assert res.get("note") == "already-replied" and res["ok"] is True
    assert not any(c.get("method") == "POST" for c in el.calls)


def test_deliver_teams(_inject):
    tg = FakeTeamsLib()
    _inject(teams=tg)
    res = ScreenpipeDispatch().deliver(_rec(channel="teams", addr="x@y.com",
                                            draft="Hej"), )
    assert res["ok"] is True and res["via"] == "Teams" and res["dest"] == "x@y.com"
    assert tg.calls == [{"addr": "x@y.com", "text": "Hej", "name": "Morten"}]


def test_deliver_dry_run_email_does_not_send(_inject):
    el = FakeEmailLib(inbox=[])
    _inject(email=el)
    res = ScreenpipeDispatch().deliver(_rec(), dry_run=True)
    assert res == {"ok": True, "dry_run": True, "via": "email",
                   "dest": "morten@ex.com", "subject": "Re: DPA", "threaded": False}
    assert not any(c["fn"] == "send_email" for c in el.calls)


def test_deliver_dry_run_teams_does_not_send(_inject):
    tg = FakeTeamsLib()
    _inject(teams=tg)
    res = ScreenpipeDispatch().deliver(_rec(channel="teams", addr="x@y.com"), dry_run=True)
    assert res == {"ok": True, "dry_run": True, "via": "Teams", "dest": "x@y.com"}
    assert tg.calls == []


def test_deliver_email_no_address_errors(_inject):
    _inject(email=FakeEmailLib())
    res = ScreenpipeDispatch().deliver(_rec(addr=""))
    assert res["ok"] is False and "no email" in res["error"]


def test_deliver_override_text_wins(_inject):
    el = FakeEmailLib(inbox=[])
    _inject(email=el)
    ScreenpipeDispatch().deliver(_rec(draft="original"), override_text="EDITED")
    s = [c for c in el.calls if c["fn"] == "send_email"][0]
    assert s["html"] == "EDITED"


# ---------------------------------------------------------------------------
# write_daily_note — marker-guarded sha256 write-if-changed (in a tmp vault).
# ---------------------------------------------------------------------------
def _vault(tmp_path, monkeypatch, marked=True):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    if marked:
        (tmp_path / ".obsidian-vault-marker").write_text("")
    return tmp_path


def test_write_daily_note_writes_then_unchanged(tmp_path, monkeypatch):
    v = _vault(tmp_path, monkeypatch)
    d = ScreenpipeDispatch()
    r1 = d.write_daily_note("2026-06-23", "hello\n")
    assert r1["action"] == "written"
    assert (v / "1-Daily" / "2026-06-23.md").read_text() == "hello\n"
    # identical bytes → unchanged (the obsidian-sync hash-match skip)
    r2 = d.write_daily_note("2026-06-23", "hello\n")
    assert r2["action"] == "unchanged"
    # changed bytes → written again
    r3 = d.write_daily_note("2026-06-23", "hello world\n")
    assert r3["action"] == "written"


def test_write_daily_note_skips_without_marker(tmp_path, monkeypatch):
    _vault(tmp_path, monkeypatch, marked=False)
    r = ScreenpipeDispatch().write_daily_note("2026-06-23", "x")
    assert r["action"] == "skipped" and "marker" in r["reason"]


def test_daily_note_path(tmp_path, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(tmp_path))
    p = ScreenpipeDispatch().daily_note_path("2026-06-23")
    assert p == str(tmp_path / "1-Daily" / "2026-06-23.md")
    assert p.endswith("1-Daily/2026-06-23.md")
