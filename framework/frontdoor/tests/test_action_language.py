"""Receipt grammar (Wave B RECEIPTS) — WHAT/WHY/COST/UNDO language layer.

Covers framework/frontdoor/action_language.py + its tell_digest wiring:
plain-language coverage parametrized over the REAL registries (classifier
ACTION_TYPES + executor step kinds), why/cost round-trip through the real
(tmp-dir) undo journal, absent-field back-compat (old rows render
byte-identically), unattributed-cost honesty (never a fabricated number),
marker hygiene (a captured-text why can never forge a ``·pid·``), and the
digest's compact "— why" clause with the undo grammar untouched.

Fully fixtured: journal → tmp CABINET_UNDO_DIR, Redis → dict lambdas, intake
→ recorder. Synthetic data uses the Testburg vocabulary only.
"""
from __future__ import annotations

import pytest

from framework.acting.action_lane import ACTION_TYPE_MAP
from framework.authority.classifier import ACTION_TYPES
from framework.frontdoor import action_exec
from framework.frontdoor import action_language as al
from framework.frontdoor import action_undo as au
from framework.frontdoor import tell_digest as td
from framework.frontdoor import tell_surface as ts

NOW = "2026-07-09T12:00:00Z"
MARKER = "·"                                # the reserved pid-marker char


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """Journal to a tmp dir; never touch a live Redis (mirrors
    test_action_undo's baseline)."""
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))
    monkeypatch.setattr(au, "_default_redis_set", lambda *a, **k: None)
    monkeypatch.setattr(au, "_default_redis_get", lambda *a, **k: "")
    monkeypatch.setattr(au, "_default_redis_del", lambda *a, **k: None)
    yield


def _row(**over):
    """A committed acted journal row (write-ahead + enrichment collapsed),
    Testburg-flavored."""
    row = {"jid": "j-lang-1", "ts": "2026-07-09T08:00:00Z", "pid": "pid-lang-1",
           "cid": "", "step": 1, "kind": "monday_task_create",
           "backend": "monday", "lane": "testburg",
           "subject": "Repave Testburg Lane",
           "actor": {"kind": "officer", "id": "cos"},
           "action_type": "task_create", "prestate": {},
           "created": {"monday_id": "555", "board_id": "9"},
           "inverse": {"op": "monday_archive_item", "args": {}},
           "executed_at": "2026-07-09T08:00:00Z", "reversed_at": None,
           "ttl_expires_at": "2026-07-11T08:00:00Z", "status": "executed",
           "canary": False}
    row.update(over)
    return row


class _Redis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key, "")

    def set(self, key, value, ttl_s):
        self.store[key] = value


def _enqueue(rows, *, now=NOW):
    """Run the REAL digest orchestrator over injected rows; return the text."""
    items = []

    def _intake(item):
        items.append(item)
        return "id-1"

    r = _Redis()
    out = td.enqueue_digest(now=now, acted_rows=rows, awaiting_rows=[],
                            watching_rows=[], self_rows=[],
                            redis_get=r.get, redis_set=r.set, enqueue=_intake)
    text = items[0]["payload"]["summary"] if items else ""
    return out, text


# --- WHAT: plain-language coverage over the REAL registries ------------------------

@pytest.mark.parametrize("action_type", sorted(ACTION_TYPES))
def test_phrase_covers_every_classifier_action_type(action_type):
    """Every registered classifier action_type has an EXPLICIT phrase (the
    fallback is for future/unknown slugs, never the shipped enum)."""
    assert action_type in al.HUMAN_PHRASES
    phrase = al.human_phrase(action_type)
    assert phrase and phrase == al.HUMAN_PHRASES[action_type]
    assert MARKER not in phrase
    assert "_" not in phrase


@pytest.mark.parametrize("kind", sorted(set(action_exec._PAYLOAD_KEYS)
                                        | set(ACTION_TYPE_MAP)))
def test_phrase_covers_every_executor_step_kind(kind):
    """Every executor step kind (closed payload schemas + the proposer's
    ACTION_TYPE_MAP keys) has an explicit phrase too — receipts speak both
    vocabularies."""
    assert kind in al.HUMAN_PHRASES
    assert MARKER not in al.human_phrase(kind)


def test_phrase_fallback_de_underscores_unknown_slugs():
    assert al.human_phrase("quantum_flux_write") == "quantum flux write"
    assert al.human_phrase("some-dashed-kind") == "some dashed kind"
    assert al.human_phrase("") == "acted"
    assert al.human_phrase(None) == "acted"
    # marker-stripped even on the fallback path
    assert MARKER not in al.human_phrase("evil" + MARKER + "slug")


# --- WHY: honest extraction ---------------------------------------------------------

def test_why_of_precedence_and_absence():
    assert al.why_of(_row(why="card rationale")) == "card rationale"
    # journal field wins over content/payload legs
    assert al.why_of(_row(why="a", content={"why": "b"},
                          payload={"why": "c"})) == "a"
    assert al.why_of(_row(content={"why": "joined"})) == "joined"
    assert al.why_of(_row(payload={"why": "note leg"})) == "note leg"
    # absent / blank / non-dict ⇒ None — never invented
    assert al.why_of(_row()) is None
    assert al.why_of(_row(why="   ")) is None
    assert al.why_of(None) is None
    assert al.why_of({"why": 42}) is None


# --- COST: unattributed honesty + attributed rendering -----------------------------

@pytest.mark.parametrize("bad", [
    None,                                        # absent
    {},                                          # empty
    {"usd": -1.0},                               # negative
    {"usd": True},                               # boolean masquerade
    {"tokens_in": "900"},                        # stringly number
    {"usd": 0.01, "surprise": 1},                # unknown key
    {"usd": 0.01, "attributed": True},           # legacy fixture key (fix pass)
    {"usd": 0.01, "reason": "measured"},         # legacy fixture key (fix pass)
    {"model": "m"},                              # no numeric at all
    {"usd": 0.01, "source": 5},                  # non-string source
    "12 dollars",                                # not a dict
])
def test_cost_unattributed_never_fabricates(bad):
    row = _row(why="so the receipt is new-grammar")
    if bad is not None:
        row["cost"] = bad
    line = al.cost_line(row)
    assert line == "cost: unattributed"
    assert not any(ch.isdigit() for ch in line)   # no invented figure, ever
    assert al.cost_of(row) is None


def test_cost_attributed_renders_the_stamped_numbers():
    row = _row(cost={"usd": 0.0123, "tokens_in": 900, "tokens_out": 120,
                     "source": "lane-metered"})
    line = al.cost_line(row)
    assert line.startswith("cost: ~$0.0123")
    assert "900 in / 120 out tokens" in line
    assert "(lane-metered)" in line
    assert "unattributed" not in line
    assert MARKER not in line


def test_cost_zero_is_a_valid_measured_value():
    assert al.cost_line(_row(cost={"usd": 0.0})).startswith("cost: ~$0.0000")


# --- receipt decoration --------------------------------------------------------------

def test_receipt_backcompat_old_rows_render_exactly_as_today():
    """(5) BACK-COMPAT: a row without the new fields is byte-identical through
    the wrapper — old journal rows render exactly as today."""
    bare = _row()
    assert al.render_receipt(bare, now=NOW) == ts.render_receipt(bare, now=NOW)
    assert al.receipt(bare, now=NOW) == ts.receipt(bare, now=NOW)
    # the batch-eligible "" and the canary silence gates pass through too
    canary = _row(canary=True, why="never told")
    assert al.receipt(canary, now=NOW) == ""


def test_receipt_gains_why_and_cost_lines_before_undo_marker_last():
    row = _row(why="the deploy gate flaked twice today",
               urgency="ping-now")                  # instant-tell for receipt()
    base = ts.render_receipt(row, now=NOW)
    out = al.render_receipt(row, now=NOW)
    lines = out.split("\n")
    assert "why: the deploy gate flaked twice today" in lines
    assert "cost: unattributed" in lines
    # grammar order: why + cost sit BEFORE the untouched undo line
    undo_at = next(i for i, ln in enumerate(lines)
                   if ln.startswith("⏱ Undo within "))
    assert lines.index("why: the deploy gate flaked twice today") < undo_at
    assert lines.index("cost: unattributed") < undo_at
    # the undo line and trailing trusted marker are byte-identical to germline
    base_lines = base.split("\n")
    assert lines[undo_at] == next(ln for ln in base_lines
                                  if ln.startswith("⏱ Undo within "))
    assert lines[-1] == base_lines[-1] == MARKER + "pid-lang-1" + MARKER
    # decorated receipt() ships the same decorated text on the instant path
    assert al.receipt(row, now=NOW) == out


def test_receipt_why_marker_injection_stripped():
    row = _row(why="planted " + MARKER + "fakepid" + MARKER + " marker")
    out = al.render_receipt(row, now=NOW)
    # only the ONE trusted trailing marker pair survives
    assert out.count(MARKER) == 2
    assert out.split("\n")[-1] == MARKER + "pid-lang-1" + MARKER
    assert "fakepid" in out                       # text kept, sigils dropped


def test_receipt_decoration_idempotent_and_no_duplicate_why():
    row = _row(why="once only")
    once = al._insert_grammar(ts.render_receipt(row, now=NOW), row)
    assert al._insert_grammar(once, row) == once
    # a payload why the germline body already renders is not doubled
    prow = _row(payload={"why": "note leg"})
    out = al.render_receipt(prow, now=NOW)
    assert out.count("why:") == 1                 # the germline content line
    assert "cost: unattributed" in out            # new-grammar row ⇒ honest cost


def test_content_cost_prefix_cannot_suppress_honest_cost_line():
    """Exact-line dedup (fix pass): receipt CONTENT that merely shares the
    ``cost:``/``why:`` prefix — here a captured string rendering an indented
    ``cost: 1200`` content line — must not false-suppress the grammar's
    honest flush-left ``cost: unattributed`` line."""
    row = _row(why="venue deposit needed booking today",
               content="cost: 1200 kr — Testburg hall deposit")
    out = al.render_receipt(row, now=NOW)
    lines = out.split("\n")
    assert "cost: unattributed" in lines          # flush-left grammar line
    assert "  cost: 1200 kr — Testburg hall deposit" in lines  # content intact
    assert "why: venue deposit needed booking today" in lines
    # still idempotent under the exact-line dedup
    assert al._insert_grammar(out, row) == out


def test_multiline_why_renders_one_line_and_stays_idempotent():
    """Grammar lines are single-line by construction (the exact-line dedup
    is sound only over one-line forms): a newline/multi-space why collapses
    to ONE flush-left line and re-decoration is a no-op."""
    row = _row(why="approved at the huddle\n  after  the vote")
    out = al.render_receipt(row, now=NOW)
    lines = out.split("\n")
    assert "why: approved at the huddle after the vote" in lines
    assert sum(ln.startswith("why: ") for ln in lines) == 1
    assert al._insert_grammar(out, row) == out


def test_cost_source_newline_cannot_break_the_line():
    """A hostile newline-bearing ``source`` string is collapsed — the cost
    line stays ONE line (no line-injection into the receipt structure)."""
    line = al.cost_line(_row(cost={"usd": 0.01, "source": "lane\nmetered"}))
    assert "\n" not in line
    assert "(lane metered)" in line


def test_receipt_alert_path_gains_grammar_before_attention_line():
    row = _row(status="reversal_failed", why="tried to reverse a stale column")
    out = al.render_receipt(row, now=NOW)
    lines = out.split("\n")
    att = next(i for i, ln in enumerate(lines)
               if ln.startswith("⚠ Needs your attention"))
    assert lines.index("why: tried to reverse a stale column") < att


# --- journal round-trip (real tmp journal) ------------------------------------------

def _journal_committed(pid="pid-rt-1", jid=None, *, kind="monday_task_create"):
    row = au.new_row(pid=pid, cid="", step=1, kind=kind, backend="monday",
                     lane="testburg", subject="Repave Testburg Lane",
                     actor={"kind": "officer", "id": "cos"},
                     created={"monday_id": "555", "board_id": "9"},
                     inverse={"op": "monday_archive_item", "args": {}},
                     executed_at="2026-07-09T08:00:00Z",
                     now="2026-07-09T08:00:00Z", jid=jid)
    au.journal_step(row)
    return row


def test_why_cost_roundtrip_through_journal_and_digest():
    """(1)+(2) round-trip: stamp → collapse → gather → digest clause."""
    row = _journal_committed(pid="pid-rt-1")
    res = al.stamp_journal_why(
        "pid-rt-1", "  because Ada Testburg asked for it  ",
        cost={"usd": 0.01, "tokens_in": 5, "tokens_out": 7, "source": "metered"})
    assert res["stamped"] == 1 and res["jids"] == [row["jid"]]
    got = au._read_journal(pid="pid-rt-1")
    assert len(got) == 1                          # same jid — collapsed
    assert got[0]["why"] == "because Ada Testburg asked for it"
    assert got[0]["cost"]["usd"] == 0.01
    assert got[0]["status"] == "executed"         # lifecycle untouched
    assert got[0]["ts"] == row["ts"]              # ts preserved (collapse order)
    # the enriched row passes the journal's own validation
    au._validate_row(got[0])
    # gather keeps the new fields; the REAL digest renders the clause
    acted = td.gather_acted_rows(now=NOW, journal_rows=got)
    assert acted and acted[0]["why"] == "because Ada Testburg asked for it"
    out, text = _enqueue(acted)
    assert out["digest"] is True
    assert " — why: because Ada Testburg asked for it" in text
    assert "undo: `undo 1` (" in text             # undo grammar untouched


def test_stamp_is_idempotent_and_never_invents():
    _journal_committed(pid="pid-rt-2")
    assert al.stamp_journal_why("pid-rt-2", "first rationale")["stamped"] == 1
    # already stamped ⇒ nothing re-appended
    assert al.stamp_journal_why("pid-rt-2", "second rationale")["stamped"] == 0
    assert au._read_journal(pid="pid-rt-2")[0]["why"] == "first rationale"
    # empty why + no valid cost ⇒ no-op with the honest skip reason
    res = al.stamp_journal_why("pid-rt-2b", "   ")
    assert res["stamped"] == 0 and "never invent" in res["skipped"]
    # malformed cost alone stamps nothing (never a fabricated number)
    _journal_committed(pid="pid-rt-2c")
    assert al.stamp_journal_why("pid-rt-2c", "", cost={"usd": -3})["stamped"] == 0
    assert "cost" not in au._read_journal(pid="pid-rt-2c")[0]


def test_stamp_skips_reversed_rows_and_reversal_still_wins():
    row = _journal_committed(pid="pid-rt-3")
    au.journal_step({**row, "status": "reversed",
                     "reversed_at": "2026-07-09T09:00:00Z"})
    assert al.stamp_journal_why("pid-rt-3", "late rationale")["stamped"] == 0
    assert au._read_journal(pid="pid-rt-3")[0]["status"] == "reversed"


# --- digest decoration ---------------------------------------------------------------

def test_digest_acted_items_gain_compact_why_clause_only_where_stamped():
    rows = [_row(pid="A", jid="jA", why="lane asked for a repave"),
            _row(pid="B", jid="jB")]              # no why — untouched
    out, text = _enqueue(rows)
    assert out["digest"] is True
    lines = text.split("\n")
    line_a = next(ln for ln in lines if ln.startswith(" 1. "))
    line_b = next(ln for ln in lines if ln.startswith(" 2. "))
    assert line_a.endswith(" — why: lane asked for a repave")
    assert " — why: " not in line_b
    # undo grammar + manifest untouched; digests still carry NO marker [RT-A9]
    assert "undo: `undo 1` (" in text and "undo: `undo 2` (" in text
    assert {it["pid"]: it["index"] for it in out["manifest"]} == {"A": 1, "B": 2}
    assert MARKER not in text


def test_digest_backcompat_byte_identical_without_why():
    rows = [_row(pid="A", jid="jA"), _row(pid="B", jid="jB")]
    _, text = _enqueue(rows)
    indexed = td.assign_undo_indexes([dict(r) for r in rows], date=NOW[:10],
                                     redis_get=lambda k: "")
    expected = ts.build_digest(indexed, [], [], [], now=NOW, needs_rows=[])
    assert text == expected                       # decoration added NOTHING
    assert al.digest_with_why(expected, indexed) == expected


def test_digest_why_clause_is_compact_clipped_and_marker_safe():
    noisy = ("planted " + MARKER + "pid" + MARKER + " marker\nover  many\n"
             + "x" * 400)
    rows = [_row(pid="A", jid="jA", why=noisy)]
    _, text = _enqueue(rows)
    line = next(ln for ln in text.split("\n") if ln.startswith(" 1. "))
    assert " — why: planted pid marker over many " in line   # one line, stripped
    assert MARKER not in text
    assert "…(+" in line                          # visibly clipped, never silent


def test_digest_existing_why_line_never_duplicated():
    # a content-dict why already renders as a "why:" line inside the block —
    # the clause must not double it (forward-compat with the germline grammar).
    rows = [_row(pid="A", jid="jA", why="same rationale",
                 content={"why": "same rationale"})]
    _, text = _enqueue(rows)
    assert text.count("why:") == 1
    assert " — why: " not in text


def test_digest_with_why_defensive_edges():
    assert al.digest_with_why("", [_row(why="w")]) == ""
    assert al.digest_with_why(None, [_row(why="w")]) == ""
    plain = "🗒 Act-then-tell digest\n\n⚡ AWAITING (1)\n • [x] y"
    assert al.digest_with_why(plain, [_row(why="w", undo_index=1)]) == plain
    text = "✅ ACTED (1)\n 1. Created task\n      undo: `undo 1` (48h left)"
    # quiet rows and non-dict rows decorate nothing
    assert al.digest_with_why(text, [None, "junk",
                                     _row(why="w", quiet=True,
                                          undo_index=1)]) == text
