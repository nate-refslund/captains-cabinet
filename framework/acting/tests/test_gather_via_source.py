"""CG-2/R004a — gather_signals dispatch: extracted vault walk (flag OFF,
byte-identical) vs the PersonalSource seam (CABINET_GATHER_VIA_SOURCE=1, dark).

Extends the test_gather_corpus fixture patterns (tmp vault + explicit mtimes,
no live APIs). Three planes:

  1. FLAG-OFF PARITY — the default path must produce exactly what the
     extracted vault_signals walk produces (the dispatch adds nothing), and
     the germline lane file must carry ZERO vault-dir literals (the CG-2 row
     gate, pinned so a regression re-inlining the table fails loudly).
  2. FLAG-ON SEAM — commitments + leak-scoped search context render in the
     same fenced-block channel; content_ts fencing holds (future hits and
     ts-less hits DROPPED); org-corpus sections ride along.
  3. FAIL-CLOSED — a broken/absent source gathers EMPTY; it never falls back
     to the vault walk (leak scoping would be defeated silently).
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

import framework.sources as fsources
from framework.acting import action_lane
from framework.acting import run_action_lane as ral
from framework.sources import vault_signals

AS_OF = dt.datetime(2026, 7, 7, 12, 0, 0, tzinfo=dt.timezone.utc)
RECENT = AS_OF - dt.timedelta(hours=1)


def _write(root, rel, body, *, mtime=RECENT):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    ts = mtime.timestamp()
    os.utime(p, (ts, ts))
    return p


@pytest.fixture
def vault(tmp_path):
    return tmp_path / "vault"


@pytest.fixture(autouse=True)
def _flag_off(monkeypatch):
    """Every test starts flag-OFF (the shipped default); flag-ON tests set it
    explicitly."""
    monkeypatch.delenv("CABINET_GATHER_VIA_SOURCE", raising=False)


class _StubSource:
    """A minimal PersonalSource stand-in for the flag-ON path."""

    def __init__(self, rows=None, hits=None, avail=True):
        self.rows = rows or []
        self.hits = hits or []
        self.search_calls = []

        self._avail = avail

    def available(self):
        return self._avail

    def open_commitments(self, direction):
        return [r for r in self.rows if r.get("direction") == direction]

    def search(self, handle, *, topic=None):
        self.search_calls.append((handle, topic))
        return {"hits": self.hits}


# --- 1. flag-OFF parity -------------------------------------------------------

def test_flag_off_matches_extracted_walk_exactly(vault, monkeypatch):
    _write(vault, "6-Commitments/owed_by_captain/cmt-1.md", "Ada owes Lena the licences")
    _write(vault, "2-Meetings/2026-07-06-scrum.md", "Bakery scrum notes")
    _write(vault, "5-Reflections/Decisions/dec-1.md", "Decided: Option B staging")
    monkeypatch.setattr(ral, "product_brain_dir", lambda: "")
    out = ral.gather_signals(AS_OF, vault=vault)
    parts = vault_signals.collect_sections(AS_OF, vault=vault, corpus_dir="")
    assert out == "\n\n".join(fenced for _, fenced in parts)
    assert "--- OPEN COMMITMENT ref=6-Commitments/owed_by_captain/cmt-1.md ---" in out
    assert "--- MEETING ref=2-Meetings/2026-07-06-scrum.md ---" in out
    assert "--- DECISION ref=5-Reflections/Decisions/dec-1.md ---" in out


def test_flag_off_never_touches_the_source_seam(vault, monkeypatch):
    """The default path must not even resolve a source (a sourceless clean
    room stays exactly on the file walk)."""
    def _boom():
        raise AssertionError("get_source must not be called flag-off")
    monkeypatch.setattr(fsources, "get_source", _boom)
    _write(vault, "2-Meetings/m.md", "notes")
    monkeypatch.setattr(ral, "product_brain_dir", lambda: "")
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "--- MEETING ref=2-Meetings/m.md ---" in out


def test_cg2_gate_no_vault_dir_literals_in_lane_file():
    """The CG-2 row gate, pinned: the germline lane file carries zero
    vault-directory literals (the table lives in vault_signals)."""
    src = (Path(ral.__file__)).read_text(encoding="utf-8")
    for literal in ("6-Commitments", "2-Meetings", "5-Reflections",
                    "3-People", "7-Opportunities", "9-Codebases"):
        assert literal not in src, f"vault literal {literal!r} re-inlined in run_action_lane.py"


def test_d13_floor_pinned_and_effective_prefixes_superset():
    """CG-2 review must-fix: the D13 never-act-first fence keeps its judgment
    DATA floored in the germline. (a) the floor's contents are pinned exactly
    (a germline edit here is a deliberate Captain amendment); (b) the lane's
    effective prefix tuple is a superset of the floor — so narrowing the
    officer-writable vault_signals.INBOUND_REF_PREFIXES (even to ()) can
    never route inbound-derived cards as "internal"/act-first."""
    assert set(action_lane.D13_INBOUND_FLOOR) == {
        "3-People/", "2-Meetings/", "4-Interactions/"}
    assert set(ral._INBOUND_REF_PREFIXES) >= set(action_lane.D13_INBOUND_FLOOR)


def test_d13_effective_prefixes_derive_via_floor_union():
    """Pin the MECHANISM, not just today's values: the lane must derive
    _INBOUND_REF_PREFIXES as adapter-table ∪ germline floor (source-level
    gate, like the literal ban above — a regression back to a bare
    `= vault_signals.INBOUND_REF_PREFIXES` read fails loudly)."""
    src = " ".join(Path(ral.__file__).read_text(encoding="utf-8").split())
    assert ("set(vault_signals.INBOUND_REF_PREFIXES) | "
            "set(action_lane.D13_INBOUND_FLOOR)") in src, \
        "_INBOUND_REF_PREFIXES no longer unions the germline D13 floor"


def test_d13_floor_module_is_germline_locked():
    """The floor is only a floor while its home module stays in the germline
    lock set (the lockstep suite keeps the four lists consistent — checking
    the canonical source list + the lock script here suffices)."""
    repo = Path(ral.__file__).resolve().parents[2]
    for lock_list in ("framework/policies/immutable-core.yml",
                      "cabinet/scripts/germline-lock.sh"):
        text = (repo / lock_list).read_text(encoding="utf-8")
        assert "framework/acting/action_lane.py" in text, \
            f"D13 floor module missing from germline lock list {lock_list}"


# --- 2. flag-ON seam ----------------------------------------------------------

def test_flag_on_renders_commitments_and_fenced_context(vault, monkeypatch):
    rows = [
        {"direction": "owed_by_captain", "text": "send licences to Lena",
         "person": "lena-baker", "path": "cmt-abc.md", "due": "2026-07-08"},
    ]
    hits = [
        {"text": "Lena asked for the licences in the scrum",
         "path": "notes/scrum.md", "content_ts": "2026-07-06T09:00:00Z"},
        {"text": "FUTURE leak", "path": "notes/future.md",
         "content_ts": "2026-07-08T09:00:00Z"},          # > as_of → dropped
        {"text": "undated note", "path": "notes/undated.md"},  # no ts → dropped
    ]
    stub = _StubSource(rows=rows, hits=hits)
    monkeypatch.setattr(fsources, "get_source", lambda: stub)
    monkeypatch.setenv("CABINET_GATHER_VIA_SOURCE", "1")
    monkeypatch.setattr(ral, "product_brain_dir", lambda: "")
    # vault HAS walkable files — they must NOT appear (the walk is replaced)
    _write(vault, "2-Meetings/m.md", "raw meeting file")
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "--- OPEN COMMITMENT ref=cmt-abc.md ---" in out
    assert "send licences to Lena" in out
    assert "--- CONTEXT ref=notes/scrum.md ---" in out
    assert "FUTURE leak" not in out
    assert "undated note" not in out
    assert "raw meeting file" not in out
    assert stub.search_calls == [("lena-baker", "send licences to Lena")]


def test_flag_on_corpus_sections_ride_along(vault, tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    _write(corpus, "architecture.md", "Next.js on Vercel")
    stub = _StubSource(rows=[], hits=[])
    monkeypatch.setattr(fsources, "get_source", lambda: stub)
    monkeypatch.setenv("CABINET_GATHER_VIA_SOURCE", "1")
    monkeypatch.setattr(ral, "product_brain_dir", lambda: str(corpus))
    out = ral.gather_signals(AS_OF, vault=vault)
    assert "--- CORPUS ref=vault/architecture.md ---" in out


# --- 3. fail-closed -----------------------------------------------------------

def test_flag_on_source_unavailable_gathers_empty(vault, monkeypatch):
    monkeypatch.setattr(fsources, "get_source",
                        lambda: _StubSource(avail=False))
    monkeypatch.setenv("CABINET_GATHER_VIA_SOURCE", "1")
    monkeypatch.setattr(ral, "product_brain_dir", lambda: "")
    _write(vault, "2-Meetings/m.md", "raw meeting file")
    assert ral.gather_signals(AS_OF, vault=vault) == ""


def test_flag_on_source_raises_gathers_empty_never_falls_back(vault, monkeypatch):
    def _broken():
        raise RuntimeError("adapter import blew up")
    monkeypatch.setattr(fsources, "get_source", _broken)
    monkeypatch.setenv("CABINET_GATHER_VIA_SOURCE", "1")
    monkeypatch.setattr(ral, "product_brain_dir", lambda: "")
    _write(vault, "6-Commitments/cmt.md", "walkable commitment")
    assert ral.gather_signals(AS_OF, vault=vault) == ""
