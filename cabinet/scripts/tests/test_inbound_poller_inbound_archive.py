"""Durable captain-inbound archive (officer-inbound-poller.py, 2026-07-17).

The 30-entry redis ring (cabinet:captain:recent-msgs) truncates to 280 chars
and forgets — 8 of 26 traced Captain messages were unrecoverable verbatim by
2026-07-16. ``archive_captain_dm`` appends every Captain utterance VERBATIM
to durable day files with a stable ``dm_id`` (``tg-<chat>-<mid>``); the
captain-message-effect design's case ledger and every attention metric's
denominator read from here. These tests pin the row contract, verbatim-ness,
dedup, degrade-safety (an archive failure must be LOUD but never block
delivery), the conftest fence (pytest can never write the live archive), and
the three receive-path call sites.
"""
from __future__ import annotations

import importlib.util
import json
import re
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
POLLER = REPO / "cabinet/scripts/officer-inbound-poller.py"

_spec = importlib.util.spec_from_file_location(
    "officer_inbound_poller_archive_t", POLLER)
poller = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poller)


# Deliberately FAKE ids (like the capture-seam suite's 4242): this file ships
# in the egg, and the publish gate flags any 9+-digit run as a possible real
# chat id — never use live ids or long epochs in fixtures.
def _archive(monkeypatch, tmp_path, **kw):
    d = tmp_path / "captain-inbound"
    monkeypatch.setenv("CABINET_CAPTAIN_INBOUND_DIR", str(d))
    poller._ARCHIVED_DM_IDS.clear()
    dm_id = poller.archive_captain_dm(
        kw.pop("chat_id", "4242"), kw.pop("message_id", 1200),
        kw.pop("text", "hej"), **kw)
    return d, dm_id


def _rows(d: Path) -> list:
    rows = []
    for f in sorted(d.glob("inbound-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            rows.append(json.loads(line))
    return rows


# --- row contract --------------------------------------------------------------

def test_row_shape_and_stable_dm_id(monkeypatch, tmp_path):
    d, dm_id = _archive(monkeypatch, tmp_path, text="ship it",
                        update_id=77, tg_date=12345678,
                        quoted="the draft body", officer="cos")
    assert dm_id == "tg-4242-1200"
    rows = _rows(d)
    assert len(rows) == 1
    r = rows[0]
    assert r["v"] == 1
    assert r["dm_id"] == dm_id
    assert r["chat_id"] == "4242"
    assert r["message_id"] == 1200
    assert r["update_id"] == 77
    assert r["officer"] == "cos"
    assert r["kind"] == "text"
    assert r["text"] == "ship it"
    assert r["quoted"] == "the draft body"
    assert r["tg_date"] == 12345678
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", r["ts"])
    # day file named for the UTC day
    day = time.strftime("%Y-%m-%d", time.gmtime())
    assert (d / f"inbound-{day}.jsonl").exists()


def test_verbatim_no_truncation_unicode_multiline(monkeypatch, tmp_path):
    """The ring truncates to 280 chars; the archive NEVER truncates, and
    Danish text survives byte-verbatim (ensure_ascii=False)."""
    long_text = ("æøå ÆØÅ — beslutningen er endelig!\n" * 40).strip()
    assert len(long_text) > 280
    d, _ = _archive(monkeypatch, tmp_path, text=long_text,
                    quoted="q" * 900)
    r = _rows(d)[0]
    assert r["text"] == long_text
    assert r["quoted"] == "q" * 900
    raw = next(d.glob("inbound-*.jsonl")).read_text(encoding="utf-8")
    assert "æøå" in raw  # not æ-escaped


def test_file_kinds_carry_attachment_fields(monkeypatch, tmp_path):
    d, _ = _archive(monkeypatch, tmp_path, text="voice note caption",
                    kind="file", file_kind="voice",
                    file_name="memo?.ogg")
    r = _rows(d)[0]
    assert r["kind"] == "file"
    assert r["file_kind"] == "voice"
    assert r["file_name"] == poller.sanitize_filename("memo?.ogg")


# --- dedup ---------------------------------------------------------------------

def test_in_process_dedup_same_dm_once(monkeypatch, tmp_path):
    d = tmp_path / "captain-inbound"
    monkeypatch.setenv("CABINET_CAPTAIN_INBOUND_DIR", str(d))
    poller._ARCHIVED_DM_IDS.clear()
    for _ in range(3):
        poller.archive_captain_dm("42", 7, "once")
    poller.archive_captain_dm("42", 8, "twice")
    rows = _rows(d)
    assert [r["dm_id"] for r in rows] == ["tg-42-7", "tg-42-8"]


def test_dedup_set_bounded(monkeypatch, tmp_path):
    d = tmp_path / "captain-inbound"
    monkeypatch.setenv("CABINET_CAPTAIN_INBOUND_DIR", str(d))
    poller._ARCHIVED_DM_IDS.clear()
    monkeypatch.setattr(poller, "_ARCHIVE_DEDUP_MAX", 5)
    for i in range(12):
        poller.archive_captain_dm("42", i, f"m{i}")
    assert len(poller._ARCHIVED_DM_IDS) <= 5
    assert len(_rows(d)) == 12  # every distinct dm still archived


# --- degrade-safety -------------------------------------------------------------

def test_failure_is_loud_but_never_raises(monkeypatch, tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("a file where the dir should be", encoding="utf-8")
    monkeypatch.setenv("CABINET_CAPTAIN_INBOUND_DIR", str(blocker))
    poller._ARCHIVED_DM_IDS.clear()
    logged = []
    dm_id = poller.archive_captain_dm("42", 9, "must not raise",
                                      log=logged.append)
    assert dm_id == "tg-42-9"
    assert any("ARCHIVE-GAP" in ln for ln in logged), (
        "archive failure must be LOUD — a silent gap in a truth surface")


def test_failure_does_not_poison_dedup(monkeypatch, tmp_path):
    """A failed append must retry on the next call once the dir is fixed."""
    blocker = tmp_path / "blocked"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("CABINET_CAPTAIN_INBOUND_DIR", str(blocker))
    poller._ARCHIVED_DM_IDS.clear()
    poller.archive_captain_dm("42", 10, "first try fails", log=lambda _m: None)
    good = tmp_path / "captain-inbound"
    monkeypatch.setenv("CABINET_CAPTAIN_INBOUND_DIR", str(good))
    poller.archive_captain_dm("42", 10, "first try fails")
    assert [r["dm_id"] for r in _rows(good)] == ["tg-42-10"]


# --- leak fence + call-site pins ------------------------------------------------

def test_conftest_fences_the_archive_env_var():
    """pytest must NEVER write the live archive — the repo-root conftest
    fences CABINET_CAPTAIN_INBOUND_DIR like its whole durable-surface family
    (the 2026-07-04 events and 2026-07-16 feed leaks are the precedent)."""
    conftest = (REPO / "conftest.py").read_text(encoding="utf-8")
    assert "CABINET_CAPTAIN_INBOUND_DIR" in conftest


def test_receive_path_archives_all_utterance_kinds():
    """Source pin WITH TEETH: each receive path calls archive_captain_dm with
    its kind — if a refactor drops one, the archive silently loses that
    utterance class. Anchored on the CALL shape (`archive_captain_dm(chat_dm,`)
    so the function DEF line (whose signature contains kind="text" as a
    default) can never satisfy the text-kind pin vacuously — a prior draft's
    `\\([^)]*kind=` matched the def and survived deleting the call site."""
    src = POLLER.read_text(encoding="utf-8")
    for kind in ('kind="text"', 'kind="file"', 'kind="file-error"',
                 'kind="onboarding"'):
        assert re.search(
            r"archive_captain_dm\(chat_dm,[^)]*" + re.escape(kind), src,
            re.S), f"receive path lost the {kind} archive call"
    # and the def line alone must NOT satisfy the call-shaped pattern
    def_only = re.sub(r"archive_captain_dm\(chat_dm,", "REMOVED(", src)
    assert not re.search(r"archive_captain_dm\(chat_dm,", def_only)


def test_default_dir_is_the_durable_family_location(monkeypatch):
    monkeypatch.delenv("CABINET_CAPTAIN_INBOUND_DIR", raising=False)
    assert poller.captain_inbound_archive_dir().endswith(
        "Library/Application Support/cabinet/captain-inbound")
