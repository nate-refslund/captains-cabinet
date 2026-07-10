"""B2.7 Support probe — FIXTURED only (zero live provider/urllib). Mirrors the
B2.3 reference test style: pure classify + join truth tables, an injected fake
client, and the four run_probe invariants (resolved/reopened, silent-source
page, unattributable skip) plus the ships-disabled default."""
from __future__ import annotations

from datetime import datetime, timezone

from framework.acting import loop
from framework.probes import correlation as c
from framework.probes import lib
from framework.probes import probe_support as ps


def _dt(iso: str) -> datetime:
    return ps._parse(iso)


# --- pure classify -----------------------------------------------------------

def test_classify_truth_table():
    out = "2026-07-03T00:00:00Z"
    # no reply, past the 72h quiet window → resolved
    assert ps.classify(outbound_at=out, customer_reply_at=None,
                       now=_dt("2026-07-06T01:00:00Z"))[:2] == ("ok", "resolved")
    # exactly 72h, still no reply → resolved (>= boundary)
    assert ps.classify(outbound_at=out, customer_reply_at=None,
                       now=_dt("2026-07-06T00:00:00Z"))[:2] == ("ok", "resolved")
    # inside the window, no reply yet → pending/unknown
    assert ps.classify(outbound_at=out, customer_reply_at=None,
                       now=_dt("2026-07-03T06:00:00Z"))[:2] == ("unknown", "pending")
    # a customer reply AFTER the outbound → reopened, even well inside the window
    assert ps.classify(outbound_at=out, customer_reply_at="2026-07-03T02:00:00Z",
                       now=_dt("2026-07-03T06:00:00Z"))[:2] == ("failed", "reopened")
    # a reply BEFORE the outbound is the message we answered → not a reopen
    assert ps.classify(outbound_at=out, customer_reply_at="2026-07-02T23:00:00Z",
                       now=_dt("2026-07-06T01:00:00Z"))[:2] == ("ok", "resolved")


def test_parse_handles_z_and_fractional():
    a = ps._parse("2026-07-03T02:00:00Z")
    b = ps._parse("2026-07-03T02:00:00.1234567+00:00")   # sub-micro fractional truncated
    assert a.tzinfo is not None and a.utcoffset().total_seconds() == 0
    assert b.hour == 2 and b.minute == 0


# --- correlation join (header + subject-tag disambiguation) ------------------

def test_resolve_cid_header_path_full_cid():
    cid = c.mint()
    hdr_name, hdr_val = c.resend_header(cid)
    th = {"headers": {"Subject": "Re: help", hdr_name.upper(): hdr_val},
          "subject": "Re: help"}
    got, how = ps.resolve_cid(th, short_index={})
    assert got == cid and how == "header"


def test_resolve_cid_subject_tag_disambiguated():
    cid = c.mint()
    idx = ps._short_index([_decided(cid)])
    th = {"subject": f"Re: your ticket {c.subject_tag(cid)}"}     # no header
    got, how = ps.resolve_cid(th, idx)
    assert got == cid and how == "subject-tag"


def test_resolve_cid_ambiguous_short_fails_closed():
    # two distinct valid cids that SHARE an 8-char short → the tag can't join
    a = "abcd1234" + "0" * 24
    b = "abcd1234" + "1" * 24
    assert c.is_cid(a) and c.is_cid(b) and c.short(a) == c.short(b)
    idx = ps._short_index([_decided(a), _decided(b)])
    th = {"subject": f"Re: [CAB-{c.short(a)}]"}
    got, how = ps.resolve_cid(th, idx)
    assert got is None and how == "ambiguous-short"


def test_resolve_cid_no_open_match_and_no_cid():
    idx = ps._short_index([_decided("1" * 32)])          # short "11111111"
    assert ps.resolve_cid({"subject": "Re: [CAB-deadbeef]"}, idx) == (None, "no-open-match")
    assert ps.resolve_cid({"subject": "Re: no tag here"}, idx) == (None, "no-cid")
    # a header value that is not a well-formed cid does not join via the header
    bad = {"headers": {c.RESEND_HEADER_KEY: "not-a-cid"}, "subject": "Re: x"}
    assert ps.resolve_cid(bad, idx)[0] is None


# --- fixtured client ---------------------------------------------------------

class FakeResend:
    def __init__(self, threads, outbound=True, provider_count=0):
        self._threads = threads
        self._outbound = outbound
        self._count = provider_count

    def support_threads(self, mailbox):
        return self._threads

    def outbound_activity(self, mailbox):
        return self._outbound

    def provider_message_count(self, mailbox):
        return self._count


def _decided(cid, subject="support-thread"):
    p = loop.proposal_event(actor={"kind": "officer", "id": "bakery-ceo"},
                            lane="support-reply", subject=subject,
                            ts="2026-07-03T00:00:00Z", refs=[c.ref_for(cid)])
    p["proposal"]["decision"] = "approved"
    p["proposal"]["decided_at"] = "2026-07-03T00:00:00Z"
    return p


def _record(sink, **kw):
    sink.append(kw)
    return {"emitted": True, "status": kw["status"], "probe_status": kw["probe_status"]}


# --- run_probe invariants ----------------------------------------------------

def test_run_probe_resolved_ok_via_header():
    cid = c.mint()
    hdr_name, hdr_val = c.resend_header(cid)
    threads = [{"headers": {hdr_name: hdr_val}, "subject": "Re: ticket",
                "outbound_at": "2026-07-03T00:00:00Z", "customer_reply_at": None}]
    emitted = []
    r = ps.run_probe(mailbox="support@bakery", client=FakeResend(threads),
                     rows=[_decided(cid)], now="2026-07-06T01:00:00Z", enabled=True,
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "pinged")
    assert r["enabled"] is True and r["fresh"] is True
    assert len(r["emitted"]) == 1 and r["emitted"][0]["status"] == "ok"
    assert emitted[0]["status"] == "ok" and emitted[0]["probe_status"] == "resolved"
    assert emitted[0]["confidence"] == "medium" and emitted[0]["source"] == "support"


def test_run_probe_reopened_failed_via_subject_tag():
    cid = c.mint()
    threads = [{"subject": f"Re: still broken {c.subject_tag(cid)}",   # no header
                "outbound_at": "2026-07-03T00:00:00Z",
                "customer_reply_at": "2026-07-03T05:00:00Z"}]
    emitted = []
    r = ps.run_probe(mailbox="m", client=FakeResend(threads), rows=[_decided(cid)],
                     now="2026-07-03T06:00:00Z", enabled=True,
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "failed" and r["emitted"][0]["how"] == "subject-tag"
    assert emitted[0]["probe_status"] == "reopened" and emitted[0]["evidence"]


def test_run_probe_pending_emits_unknown_without_evidence():
    cid = c.mint()
    hdr_name, hdr_val = c.resend_header(cid)
    threads = [{"headers": {hdr_name: hdr_val}, "subject": "Re: t",
                "outbound_at": "2026-07-03T00:00:00Z", "customer_reply_at": None}]
    emitted = []
    r = ps.run_probe(mailbox="m", client=FakeResend(threads), rows=[_decided(cid)],
                     now="2026-07-03T06:00:00Z", enabled=True,   # 6h in → pending
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "unknown"
    assert emitted[0]["probe_status"] == "pending" and emitted[0]["evidence"] is None


def test_run_probe_pending_unknown_schema_valid_through_real_emit():
    # route through the REAL lib.emit_outcome (inner emit injected to a sink so no
    # file is written) so the unknown-has-no-evidence invariant is enforced by
    # validate_consequence, not just asserted against a fake sink.
    cid = c.mint()
    hdr_name, hdr_val = c.resend_header(cid)
    threads = [{"headers": {hdr_name: hdr_val}, "subject": "Re: t",
                "outbound_at": "2026-07-03T00:00:00Z", "customer_reply_at": None}]
    sink = []

    def emit_via_lib(**kw):
        return lib.emit_outcome(**kw, emit=lambda **ev: sink.append(ev))

    r = ps.run_probe(mailbox="m", client=FakeResend(threads), rows=[_decided(cid)],
                     now="2026-07-03T06:00:00Z", enabled=True,
                     emit=emit_via_lib, hc=lambda *a, **k: "")
    assert len(r["emitted"]) == 1
    ev = sink[0]
    assert ev["outcome"] == {"status": "unknown"}          # no evidence key
    assert "confidence:medium" in ev["refs"] and "probe:support" in ev["refs"]
    assert c.cid_from_refs(ev["refs"]) == cid              # join preserved


def test_run_probe_freshness_silent_source_pages_no_emit():
    # inbox read empty but outbound went out → not fresh: hc fail, no emit
    pinged = []
    r = ps.run_probe(mailbox="m", client=FakeResend([], outbound=True), rows=[],
                     enabled=True, emit=lambda **kw: pinged.append(("emit",)),
                     hc=lambda slug, fail=False: pinged.append(("hc", fail)))
    assert r["fresh"] is False
    assert ("hc", True) in pinged and ("emit",) not in pinged


def test_run_probe_freshness_silent_via_provider_count():
    # no outbound flag, but the provider reports messages exist while our read is
    # empty → still a silent source → page, no emit
    pinged = []
    r = ps.run_probe(mailbox="m", client=FakeResend([], outbound=False, provider_count=3),
                     rows=[], enabled=True, emit=lambda **kw: pinged.append(("emit",)),
                     hc=lambda slug, fail=False: pinged.append(("hc", fail)))
    assert r["fresh"] is False and ("hc", True) in pinged


def test_run_probe_empty_but_no_activity_is_fresh_no_page():
    # genuinely no threads AND no outbound/provider signal → fresh, nothing to do
    pinged = []
    r = ps.run_probe(mailbox="m", client=FakeResend([], outbound=False, provider_count=0),
                     rows=[], enabled=True, emit=lambda **kw: pinged.append("emit"),
                     hc=lambda *a, **k: pinged.append("hc"))
    assert r["fresh"] is True and r["emitted"] == [] and "emit" not in pinged


def test_run_probe_unattributable_cid_skipped():
    cid = c.mint()   # valid header cid, but NO matching decided proposal in rows
    hdr_name, hdr_val = c.resend_header(cid)
    threads = [{"headers": {hdr_name: hdr_val}, "subject": "Re: t",
                "outbound_at": "2026-07-03T00:00:00Z", "customer_reply_at": None}]
    r = ps.run_probe(mailbox="m", client=FakeResend(threads), rows=[],   # empty ledger
                     now="2026-07-06T01:00:00Z", enabled=True,
                     emit=lib.emit_outcome, hc=lambda *a, **k: "")
    assert r["emitted"] == [] and r["skipped"][0]["reason"] == "unattributable-cid"


def test_run_probe_ships_disabled_by_default(monkeypatch):
    monkeypatch.delenv(ps.ENABLED_ENV, raising=False)
    # client=None proves the disabled path never touches the client
    r = ps.run_probe(mailbox="m", client=None, rows=[])
    assert r == {"enabled": False, "fresh": None, "emitted": [], "skipped": []}
    # explicit enabled=False behaves identically
    r2 = ps.run_probe(mailbox="m", client=None, rows=[], enabled=False)
    assert r2["enabled"] is False and r2["emitted"] == []


def test_env_flag_enables(monkeypatch):
    monkeypatch.setenv(ps.ENABLED_ENV, "1")
    assert ps._is_enabled() is True
    monkeypatch.setenv(ps.ENABLED_ENV, "off")
    assert ps._is_enabled() is False
    cid = c.mint()
    hdr_name, hdr_val = c.resend_header(cid)
    threads = [{"headers": {hdr_name: hdr_val}, "subject": "Re: t",
                "outbound_at": "2026-07-03T00:00:00Z", "customer_reply_at": None}]
    monkeypatch.setenv(ps.ENABLED_ENV, "true")     # enabled via env, no enabled= arg
    emitted = []
    r = ps.run_probe(mailbox="m", client=FakeResend(threads), rows=[_decided(cid)],
                     now="2026-07-06T01:00:00Z",
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["enabled"] is True and r["emitted"][0]["status"] == "ok"
