"""P2 acted-overlay: ledger acted rows × undo journal → acted-state view.

Fixtures mirror the REAL 2026-07-07 incident: the testament calendar event
was acted TWICE; the Captain undid one (undo 2). The overlay must mark the
undone act reversed, keep the standing one live, and render both."""

from framework.attention.acted_overlay import (
    load_acted, load_journal_rows, render_overlay)

CID_LIVE = "aaaa111122223333"
CID_UNDONE = "bbbb444455556666"

LEDGER = [
    {"action": "acted:reminder_create", "subject": "testament-signing-kolding",
     "ts": "2026-07-07T16:09:28Z", "actor": {"kind": "officer", "id": "cos"},
     "lane": "personal",
     "refs": [f"cabinet-proposal-id:{CID_LIVE}",
              "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — reminder_set: false"]},
    {"action": "acted:reminder_create", "subject": "testament-signing-kolding-dup",
     "ts": "2026-07-07T17:30:00Z", "actor": {"kind": "officer", "id": "cos"},
     "lane": "personal",
     "refs": [f"cabinet-proposal-id:{CID_UNDONE}",
              "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Solveig booked"]},
    {"action": "acted:calendar_event_create", "subject": "chase-ec-details",
     "ts": "2026-07-07T16:09:28Z", "actor": {"kind": "officer", "id": "cos"},
     "lane": "polads",
     "refs": [f"cabinet-proposal-id:cccc7777",
              "6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md — due 2026-07-08"]},
    # non-acted rows must be ignored
    {"action": "action-card", "subject": "x", "ts": "2026-07-07T10:00:00Z",
     "refs": ["6-Commitments/owed_to_nate/cmt-000000000000.md"]},
]

JOURNAL = [
    {"jid": "j1", "cid": CID_LIVE, "ts": "2026-07-07T16:09:28Z",
     "kind": "reminder_create", "status": "executed", "reversed_at": None},
    {"jid": "j2", "cid": CID_UNDONE, "ts": "2026-07-07T17:30:00Z",
     "kind": "reminder_create", "status": "reversed",
     "reversed_at": "2026-07-07T18:40:00Z"},
]


def _view():
    return load_acted(ledger_rows=LEDGER, journal_rows=JOURNAL)


def test_join_marks_reversed_and_live():
    v = _view()
    by_subject = {e["subject"]: e for e in v["entries"]}
    assert not by_subject["testament-signing-kolding"]["reversed"]
    assert by_subject["testament-signing-kolding-dup"]["reversed"]
    assert not by_subject["chase-ec-details"]["reversed"]
    assert "x" not in by_subject   # action-card rows are not acted state


def test_shared_ref_stays_live_when_one_act_stands():
    """The testament cmt ref backs BOTH a standing act and an undone one —
    it must stay LIVE (something acted on it still exists in the world)."""
    v = _view()
    assert "cmt-fca6836e2844" in v["live_canonical"]
    assert "cmt-fca6836e2844" not in v["reversed_canonical"]


def test_fully_reversed_situation_moves_to_reversed_set():
    ledger = [LEDGER[1], LEDGER[2]]   # only the undone testament act + EC
    v = load_acted(ledger_rows=ledger, journal_rows=JOURNAL)
    assert "cmt-fca6836e2844" in v["reversed_canonical"]
    assert "cmt-fca6836e2844" not in v["live_canonical"]
    assert "cmt-8ab5d6355d15" in v["live_canonical"]


def test_since_floor_filters_ledger_not_journal():
    v = load_acted(since="2026-07-07T17:00:00Z",
                   ledger_rows=LEDGER, journal_rows=JOURNAL)
    subjects = {e["subject"] for e in v["entries"]}
    assert subjects == {"testament-signing-kolding-dup"}


def test_missing_journal_row_is_conservatively_live():
    v = load_acted(ledger_rows=[LEDGER[2]], journal_rows=[])
    assert "cmt-8ab5d6355d15" in v["live_canonical"]


def test_render_overlay_shapes():
    v = _view()
    text = render_overlay(v)
    assert "ALREADY ACTED" in text
    assert "REVERSED-BY-CAPTAIN" in text
    assert "testament-signing-kolding" in text
    assert render_overlay(None) == ""
    assert render_overlay({"entries": []}) == ""


def test_failed_reversal_stays_live():
    """reversal_failed / dead_letter rows carry reversed_at but the artifact
    STANDS — they must not read as Captain-undo (review cp2 High)."""
    journal = [{"jid": "j1", "cid": CID_LIVE, "ts": "2026-07-07T16:09:28Z",
                "status": "reversal_failed",
                "reversed_at": "2026-07-07T18:00:00Z"}]
    v = load_acted(ledger_rows=[LEDGER[0]], journal_rows=journal)
    assert "cmt-fca6836e2844" in v["live_canonical"]
    assert not v["entries"][0]["reversed"]


def test_approved_then_undone_uncover_via_action_card_rows():
    """An APPROVED execution's ledger row is 'action-card', not 'acted:*' —
    its reversal must still un-cover the situation (review cp2 M3)."""
    ledger = [{"action": "action-card", "subject": "approved-thing",
               "ts": "2026-07-07T12:00:00Z",
               "refs": [f"cabinet-proposal-id:{CID_UNDONE}",
                        "6-Commitments/owed_to_nate/cmt-999888777666.md — x"]}]
    v = load_acted(ledger_rows=ledger, journal_rows=JOURNAL)
    assert "cmt-999888777666" in v["reversed_canonical"]


def test_env_drift_in_window_raises_unknown(monkeypatch, tmp_path):
    """Journal rows IN-WINDOW + empty ledger on the default-load path = env
    drift → raise (world UNKNOWN, lane disarms); quiet-box case (journal
    rows older than the window) stays a legitimate empty world (cp2 M2)."""
    import pytest
    from framework.attention import acted_overlay as ao
    f = tmp_path / "undo-journal-2026-07-07.jsonl"
    f.write_text('{"jid":"j1","cid":"c1","ts":"2026-07-07T12:00:00Z","status":"executed"}\n',
                 encoding="utf-8")
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path))
    monkeypatch.setattr("framework.fidelity.consequence.read_ledger",
                        lambda since=None: [])
    with pytest.raises(RuntimeError):
        ao.load_acted(since="2026-07-01T00:00:00Z")
    # journal row older than the window floor -> empty world, no raise
    v = ao.load_acted(since="2026-07-08T00:00:00Z")
    assert v["entries"] == [] and not v["live_canonical"]


def test_unreadable_journal_file_raises(monkeypatch, tmp_path):
    f = tmp_path / "undo-journal-2026-07-07.jsonl"
    f.write_text('{"jid":"j1","cid":"c1","ts":"1","status":"executed"}\n',
                 encoding="utf-8")
    f.chmod(0o000)
    import pytest
    try:
        with pytest.raises(RuntimeError):
            load_journal_rows(tmp_path)
    finally:
        f.chmod(0o644)


def test_journal_loader_missing_dir_is_empty(tmp_path):
    assert load_journal_rows(tmp_path / "nope") == []


def test_journal_loader_collapses_by_jid_and_skips_garbage(tmp_path):
    f = tmp_path / "undo-journal-2026-07-07.jsonl"
    f.write_text(
        '{"jid":"j9","cid":"z1","ts":"1","status":"executed"}\n'
        'not json\n'
        '{"nope":true}\n'
        '{"jid":"j9","cid":"z1","ts":"2","status":"reversed","reversed_at":"2"}\n',
        encoding="utf-8")
    rows = load_journal_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["status"] == "reversed"
