"""B2.1 correlation-id standard — mint, stamp, read-back round-trips + propose wire."""
from __future__ import annotations

import re

from framework.acting import loop
from framework.probes import correlation as c


def test_mint_is_uuid4_hex():
    cid = c.mint()
    assert re.fullmatch(r"[0-9a-f]{32}", cid)
    assert c.is_cid(cid) and not c.is_cid("nope") and not c.is_cid(cid[:-1])
    assert c.mint() != c.mint()  # unique


def test_refs_convention_round_trip():
    cid = c.mint()
    refs = [c.ref_for(cid), "other-ref"]
    assert c.cid_from_refs(refs) == cid
    assert c.cid_from_refs(["nothing", "cabinet-proposal-id:bogus"]) is None
    assert c.cid_from_refs([]) is None


def test_git_trailer_round_trip():
    cid = c.mint()
    body = f"feat: do a thing\n\nlonger paragraph\n\n{c.git_trailer(cid)}"
    assert c.from_git_trailer(body) == cid
    assert c.extract(body) == cid


def test_git_trailer_case_insensitive_and_surrounded():
    cid = c.mint()
    body = f"line\ncabinet-proposal-id: {cid}\nmore"  # lowercased key, mid-body
    assert c.from_git_trailer(body) == cid


def test_monday_footer_round_trip():
    cid = c.mint()
    body = f"Update: shipped.\n\n{c.monday_footer(cid)}"
    assert c.extract(body) == cid


def test_subject_tag_is_short_form():
    cid = c.mint()
    subj = f"Re: your ticket {c.subject_tag(cid)}"
    assert c.subject_tag(cid) == f"[CAB-{cid[:8]}]"
    assert c.from_subject_tag(subj) == cid[:8]
    # a full-cid extract over a subject line finds nothing (short form only)
    assert c.extract(subj) is None


def test_resend_and_vercel_stampers():
    cid = c.mint()
    assert c.resend_header(cid) == ("X-Cabinet-Proposal-Id", cid)
    assert c.vercel_meta(cid) == ("cabinetProposalId", cid)


def test_extract_rejects_malformed_and_untrusted_text():
    # a too-short / too-long hex run must not match the strict cid pattern
    assert c.extract("Cabinet-Proposal-Id: deadbeef") is None          # 8 chars
    assert c.extract("Cabinet-Proposal-Id: " + "a" * 40) is None        # 40 chars
    assert c.extract("random text with no id at all") is None


def test_extract_returns_first_token_in_document_order():
    # The git trailer and the Monday footer are the SAME token modulo case
    # ("cabinet-proposal-id: <cid>"), so extract() recovers the FIRST one in
    # document order — there is no meaningful trailer-vs-footer precedence.
    cid_first = c.mint()
    cid_second = c.mint()
    body = f"{c.monday_footer(cid_first)}\n{c.git_trailer(cid_second)}"
    assert c.extract(body) == cid_first


# --- propose() wiring -------------------------------------------------------

_ACTOR = {"kind": "officer", "id": "cos"}  # matches the estate convention (test_loop)
_TS = "2026-07-03T01:00:00Z"


def _run_propose(refs=None, mint_cid=None):
    events = []
    p = loop.propose(
        thread_ref="thr", subject="kristoffer", ts=_TS, actor=_ACTOR,
        gather=lambda tr: {}, draft_fn=lambda tr, ctx: "et udkast",
        present=lambda d, prop: None, emit=lambda **ev: events.append(ev),
        refs=refs, mint_cid=mint_cid)
    return p, events


def test_propose_mints_correlation_id_into_refs():
    fixed = "a" * 32
    p, events = _run_propose(mint_cid=lambda: fixed)
    assert p["correlation_id"] == fixed
    assert c.ref_for(fixed) in events[0]["refs"]
    # identity tuple unchanged — the binder/pending logic is unaffected
    assert p["proposal_id"] == "cos|draft-reply|kristoffer|" + _TS


def test_propose_preserves_an_explicit_cid_no_double_mint():
    supplied = "b" * 32
    p, events = _run_propose(refs=[c.ref_for(supplied)],
                             mint_cid=lambda: "c" * 32)
    assert p["correlation_id"] == supplied  # not re-minted
    assert sum(1 for r in events[0]["refs"] if r.startswith(c.REF_PREFIX)) == 1


def test_propose_real_mint_is_wellformed():
    p, _ = _run_propose()  # real minter
    assert c.is_cid(p["correlation_id"])
