"""Evidence citations on ACTED digest items (evidence Phase 3 item 4).

Covers ``action_language.digest_with_evidence`` + its ``tell_digest`` wiring:
the compact "— evidence: <trial-id>" clause appears on an ACTED headline ONLY
when the journal row carries the Batch-B ``evidence_trial_id`` stamp AND the
id passes the evidence-plane alphabet; every pre-evidence row (and any
garbled/forged id) renders byte-identically (honest gap, never a fabricated
or spliced citation); the decoration is idempotent, ACTED-scoped, keyed on
the server-minted undo index, and coexists with the "— why" clause.

Fully fixtured like test_action_language.py: journal → tmp CABINET_UNDO_DIR,
Redis → dict lambdas, intake → recorder. Synthetic Testburg vocabulary only.
"""
from __future__ import annotations

import pytest

from framework.evidence import verifier
from framework.frontdoor import action_language as al
from framework.frontdoor import action_undo as au
from framework.frontdoor import tell_digest as td
from framework.frontdoor import tell_surface as ts

NOW = "2026-07-17T12:00:00Z"
MARKER = "·"                                # the reserved pid-marker char
TRIAL = "trial-0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))
    monkeypatch.setattr(au, "_default_redis_set", lambda *a, **k: None)
    monkeypatch.setattr(au, "_default_redis_get", lambda *a, **k: "")
    monkeypatch.setattr(au, "_default_redis_del", lambda *a, **k: None)
    yield


def _row(**over):
    row = {"jid": "j-ev-1", "ts": "2026-07-17T08:00:00Z", "pid": "pid-ev-1",
           "cid": "", "step": 1, "kind": "monday_task_create",
           "backend": "monday", "lane": "testburg",
           "subject": "Repave Testburg Lane",
           "actor": {"kind": "officer", "id": "cos"},
           "action_type": "task_create", "prestate": {},
           "created": {"monday_id": "555", "board_id": "9"},
           "inverse": {"op": "monday_archive_item", "args": {}},
           "executed_at": "2026-07-17T08:00:00Z", "reversed_at": None,
           "ttl_expires_at": "2026-07-19T08:00:00Z", "status": "executed",
           "canary": False}
    row.update(over)
    return row


def _enqueue(rows, *, now=NOW):
    items = []

    def _intake(item):
        items.append(item)
        return "id-1"

    store = {}
    out = td.enqueue_digest(now=now, acted_rows=rows, awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            redis_get=lambda k: store.get(k, ""),
                            redis_set=lambda k, v, t: store.__setitem__(k, v),
                            enqueue=_intake)
    text = items[0]["payload"]["summary"] if items else ""
    return out, text


# --- the citation, end to end through the real orchestrator ----------------------


def test_acted_items_cite_evidence_trial_only_where_stamped():
    rows = [_row(pid="A", jid="jA", evidence_trial_id=TRIAL),
            _row(pid="B", jid="jB")]          # pre-evidence row — untouched
    out, text = _enqueue(rows)
    assert out["digest"] is True
    lines = text.split("\n")
    line_a = next(ln for ln in lines if ln.startswith(" 1. "))
    line_b = next(ln for ln in lines if ln.startswith(" 2. "))
    assert line_a.endswith(" — evidence: " + TRIAL)
    assert " — evidence: " not in line_b
    # undo grammar + manifest untouched; digests still carry NO marker
    assert "undo: `undo 1` (" in text and "undo: `undo 2` (" in text
    assert {it["pid"]: it["index"] for it in out["manifest"]} == {"A": 1, "B": 2}
    assert MARKER not in text


def test_backcompat_byte_identical_without_stamp():
    rows = [_row(pid="A", jid="jA"), _row(pid="B", jid="jB")]
    _, text = _enqueue(rows)
    indexed = td.assign_undo_indexes([dict(r) for r in rows], date=NOW[:10],
                                     redis_get=lambda k: "")
    expected = ts.build_digest(indexed, [], [], [], now=NOW, needs_rows=[])
    assert text == expected                   # decoration added NOTHING
    assert al.digest_with_evidence(expected, indexed) == expected


@pytest.mark.parametrize("bad_id", [
    "bad trial id",                 # whitespace — fails the alphabet
    "trial\nid",                    # newline smuggle
    MARKER + "forged" + MARKER,     # reserved marker char
    "-leading-dash",                # first char must be alnum
    "x" * 129,                      # over-long
    "",                             # empty
    123,                            # not a string
    None,
])
def test_garbled_or_invalid_ids_render_nothing(bad_id):
    rows = [_row(pid="A", jid="jA", evidence_trial_id=bad_id)]
    _, text = _enqueue(rows)
    assert " — evidence: " not in text
    assert MARKER not in text


def test_citation_is_idempotent_and_acted_scoped():
    rows = [_row(pid="A", jid="jA", evidence_trial_id=TRIAL)]
    _, text = _enqueue(rows)
    indexed = td.assign_undo_indexes([dict(r) for r in rows], date=NOW[:10],
                                     redis_get=lambda k: "")
    # a second decoration pass changes nothing (future germline renderer safe)
    assert al.digest_with_evidence(text, indexed) == text
    assert text.count(" — evidence: ") == 1
    # a text without an ACTED section is untouched
    plain = "🗒 Act-then-tell digest\n\n⚡ AWAITING (1)\n • [x] y"
    assert al.digest_with_evidence(
        plain, [_row(undo_index=1, evidence_trial_id=TRIAL)]) == plain


def test_defensive_edges_never_cost_the_digest():
    assert al.digest_with_evidence("", [_row(evidence_trial_id=TRIAL)]) == ""
    assert al.digest_with_evidence(None, [_row(evidence_trial_id=TRIAL)]) == ""
    assert al.digest_with_evidence("text", None) == "text"
    text = "✅ ACTED (1)\n 1. Created task\n      undo: `undo 1` (48h left)"
    # quiet rows, non-dict rows, and rows without a server-minted undo_index
    # decorate nothing (positional matching binds wrong lines by design)
    assert al.digest_with_evidence(
        text, [None, "junk",
               _row(evidence_trial_id=TRIAL, quiet=True, undo_index=1),
               _row(evidence_trial_id=TRIAL)]) == text


def test_why_and_evidence_clauses_coexist():
    rows = [_row(pid="A", jid="jA", why="lane asked for a repave",
                 evidence_trial_id=TRIAL)]
    _, text = _enqueue(rows)
    line = next(ln for ln in text.split("\n") if ln.startswith(" 1. "))
    assert " — why: lane asked for a repave" in line
    assert line.endswith(" — evidence: " + TRIAL)
    assert line.index(" — why: ") < line.index(" — evidence: ")


def test_id_alphabet_matches_the_evidence_plane():
    """The literal in action_language (kept import-free for 3.9) must never
    drift from the verifier's TRIAL_ID_RE — one id alphabet across planes."""
    assert al._EVIDENCE_ID_RE.pattern == verifier.TRIAL_ID_RE.pattern
