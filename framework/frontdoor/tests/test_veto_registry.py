"""Tests for TI-4 — the Captain's veto registry.

Fully fixtured: a tmp yml (never the real instance/config file), fake redis via
plain dicts, an injected emit recorder for the ledger audit. No live APIs, no
subprocess, no network."""
from __future__ import annotations

import json

import pytest

from framework.frontdoor import veto_registry as vr


@pytest.fixture()
def vetofile(tmp_path):
    """A tmp veto file seeded with the header + empty schema (like the shipped
    starter). Returns the Path; pass it as path=... to the registry API."""
    p = tmp_path / "captain-vetoes.yml"
    p.write_text(
        "# captain-vetoes.yml — CAPTAIN-AUTHORED header (must survive writes)\n"
        "# germline-protected, verbatim, lift-only.\n"
        "version: 1\nnext_id: 1\nvetoes: []\n",
        encoding="utf-8")
    return p


class EmitRec:
    def __init__(self):
        self.events = []

    def __call__(self, **ev):
        self.events.append(ev)


# --- record / scope hygiene --------------------------------------------------

def test_record_veto_appends_monotonic_ids(vetofile):
    em = EmitRec()
    a = vr.record_veto({"action_type": "task_create"}, "never: no auto tasks",
                       ts="2026-07-04T10:00:00Z", path=vetofile, emit=em)
    b = vr.record_veto({"action_type": "board_status", "board": "999"},
                       "never: no status writes on 999",
                       ts="2026-07-04T11:00:00Z", path=vetofile, emit=em)
    assert a["id"] == "veto-001" and b["id"] == "veto-002"
    assert a["lifted_at"] is None and a["source"] == "captain"
    rows = vr.load_vetoes(vetofile)
    assert [r["id"] for r in rows] == ["veto-001", "veto-002"]
    # each write emitted an audit event with the veto ref, no action_type stamp
    assert len(em.events) == 2
    ev = em.events[0]
    assert ev["action"] == "captain-veto" and ev["subject"] == "veto:veto-001"
    assert ev["actor"] == {"kind": "officer", "id": "veto-registry"}
    assert "action_type" not in ev and ev["outcome"]["status"] == "ok"


def test_record_veto_refuses_catch_all_scope(vetofile):
    """A scope with no deterministic enforceable field would veto the whole
    estate — refused."""
    with pytest.raises(vr.VetoRegistryError):
        vr.record_veto({"lane": "polads"}, "never: anything", path=vetofile)
    with pytest.raises(vr.VetoRegistryError):
        vr.record_veto({}, "never:", path=vetofile)
    assert vr.load_vetoes(vetofile) == []          # nothing was written


def test_record_veto_scope_hygiene_drops_free_text(vetofile):
    """RT-A10: only deterministic fields survive; free text / unknown keys / an
    LLM slug are dropped, so paraphrase can never widen a veto."""
    v = vr.record_veto(
        {"action_type": "task_create", "board": "5091706356",
         "note": "board 999 for everyone", "slug": "no-tasks", "": "x"},
        "never: create tasks", path=vetofile)
    assert v["scope"] == {"action_type": "task_create", "board": "5091706356"}
    assert "note" not in v["scope"] and "slug" not in v["scope"]


# --- is_vetoed deterministic match -------------------------------------------

def test_is_vetoed_action_type_only_is_wildcard_on_board(vetofile):
    vr.record_veto({"action_type": "task_create"}, "never: tasks", path=vetofile)
    assert vr.is_vetoed("task_create", path=vetofile) is True
    assert vr.is_vetoed("task_create", board="anything", path=vetofile) is True
    assert vr.is_vetoed("board_status", path=vetofile) is False


def test_is_vetoed_board_scoped_requires_exact_board(vetofile):
    vr.record_veto({"action_type": "board_status", "board": "999"},
                   "never: status on 999", path=vetofile)
    assert vr.is_vetoed("board_status", board="999", path=vetofile) is True
    assert vr.is_vetoed("board_status", board="5091706356", path=vetofile) is False
    # board-scoped veto must NOT fire on an action with no board
    assert vr.is_vetoed("board_status", board=None, path=vetofile) is False


def test_is_vetoed_content_family(vetofile):
    vr.record_veto({"action_type": "task_create", "content_family": "abc123"},
                   "never: this family", path=vetofile)
    assert vr.is_vetoed("task_create", content_family="abc123", path=vetofile) is True
    assert vr.is_vetoed("task_create", content_family="other", path=vetofile) is False


def test_lifted_veto_no_longer_matches(vetofile):
    vr.record_veto({"action_type": "task_create"}, "never: tasks", path=vetofile)
    assert vr.is_vetoed("task_create", path=vetofile) is True
    vr.lift_veto("veto-001", ts="2026-07-05T00:00:00Z", path=vetofile)
    assert vr.is_vetoed("task_create", path=vetofile) is False


# --- lift semantics ----------------------------------------------------------

def test_lift_veto_stamps_and_is_idempotent(vetofile):
    em = EmitRec()
    vr.record_veto({"action_type": "task_create"}, "never", path=vetofile, emit=em)
    r1 = vr.lift_veto("veto-001", ts="2026-07-05T00:00:00Z", path=vetofile, emit=em)
    assert r1["lifted_at"] == "2026-07-05T00:00:00Z"
    # idempotent: a second lift returns the row unchanged, no new stamp
    r2 = vr.lift_veto("veto-001", ts="2026-07-06T00:00:00Z", path=vetofile, emit=em)
    assert r2["lifted_at"] == "2026-07-05T00:00:00Z"
    assert vr.lift_veto("veto-404", path=vetofile) is None      # unknown id
    lift_events = [e for e in em.events if e["action"] == "captain-veto-lift"]
    assert len(lift_events) == 1                                # only the first lift audits


def test_ids_monotonic_across_lift(vetofile):
    """A lifted row is never deleted and its id is never reused."""
    vr.record_veto({"action_type": "task_create"}, "a", path=vetofile)
    vr.lift_veto("veto-001", path=vetofile)
    v2 = vr.record_veto({"action_type": "board_status", "board": "1"}, "b", path=vetofile)
    assert v2["id"] == "veto-002"                               # continues, never reuses 001
    assert len(vr.load_vetoes(vetofile)) == 2                   # the lifted row still present


# --- cell demotion [RT-A10] --------------------------------------------------

def test_demote_cell_for_veto_whole_kind_all_actors(vetofile):
    """A never: on an act-first kind demotes the (actor,lane,action_type) cell
    across ALL actors — not one slug."""
    d = vr.demote_cell_for_veto({"action_type": "task_create", "lane": "polads"})
    assert d == {"actor_id": None, "lane": "polads", "action_type": "task_create"}
    # every actor's task_create cell on that lane is demoted
    assert vr.cell_matches(("officer:cos", "polads", "task_create"), d) is True
    assert vr.cell_matches(("officer:cpo", "polads", "task_create"), d) is True
    # a different action_type or lane is untouched
    assert vr.cell_matches(("officer:cos", "polads", "board_status"), d) is False
    assert vr.cell_matches(("officer:cos", "stephie", "task_create"), d) is False


def test_board_only_veto_demotes_no_cell(vetofile):
    """A board/content-only veto is enforced by is_vetoed at act time, never by
    nuking the whole matrix — the directive matches no cell (safe)."""
    d = vr.demote_cell_for_veto({"board": "999"})
    assert d["action_type"] is None
    assert vr.cell_matches(("officer:cos", "polads", "task_create"), d) is False
    assert vr.cell_matches(("officer:cos", "polads", "board_status"), d) is False


# --- rebuild_cache / fail-closed ---------------------------------------------

def test_rebuild_cache_writes_active_and_sentinel_ok(vetofile):
    vr.record_veto({"action_type": "task_create"}, "a", path=vetofile)
    vr.record_veto({"action_type": "board_status", "board": "9"}, "b", path=vetofile)
    vr.lift_veto("veto-002", path=vetofile)         # lifted -> excluded from cache
    store = {"cabinet:vetoes:stale": "old"}         # a stale key to be cleared
    def rset(k, v, ttl): store[k] = v
    def rdel(k): store.pop(k, None)
    def rscan(pat): return [k for k in list(store) if k.startswith("cabinet:vetoes:")]
    res = vr.rebuild_cache(vetoes=vr.load_vetoes(vetofile),
                           redis_set=rset, redis_del=rdel, redis_scan=rscan)
    assert res == {"ok": True, "count": 1}
    assert "cabinet:vetoes:stale" not in store       # stale cleared
    assert "cabinet:vetoes:veto-001" in store        # active cached
    assert "cabinet:vetoes:veto-002" not in store    # lifted not cached
    assert store["cabinet:vetoes:__cache__"] == "ok"
    assert json.loads(store["cabinet:vetoes:veto-001"])["scope"]["action_type"] == "task_create"


def test_rebuild_cache_failure_is_fail_closed(vetofile):
    """A redis failure during rebuild => ok=False AND the sentinel marked fail;
    veto_cache_ready then reports False (act-first off this run)."""
    store = {}
    def rset(k, v, ttl):
        if k != vr._CACHE_SENTINEL:     # simulate the veto writes failing
            raise RuntimeError("redis down")
        store[k] = v
    def rdel(k): pass
    def rscan(pat): return []
    res = vr.rebuild_cache(
        vetoes=[{"id": "veto-001", "scope": {"action_type": "task_create"},
                 "lifted_at": None}],
        redis_set=rset, redis_del=rdel, redis_scan=rscan)
    assert res["ok"] is False
    assert store.get(vr._CACHE_SENTINEL) == "fail"
    assert vr.veto_cache_ready(redis_get=lambda k: store.get(k, "")) is False


def test_veto_cache_ready_true_only_when_ok():
    assert vr.veto_cache_ready(redis_get=lambda k: "ok") is True
    assert vr.veto_cache_ready(redis_get=lambda k: "fail") is False
    assert vr.veto_cache_ready(redis_get=lambda k: "") is False
    def boom(k): raise RuntimeError("no redis")
    assert vr.veto_cache_ready(redis_get=boom) is False    # unreadable => not ready


# --- misc: header preservation, prompt block, env override, malformed --------

def test_header_survives_write(vetofile):
    vr.record_veto({"action_type": "task_create"}, "never", path=vetofile)
    text = vetofile.read_text(encoding="utf-8")
    assert text.startswith("# captain-vetoes.yml — CAPTAIN-AUTHORED header")
    assert "germline-protected" in text
    assert "veto-001" in text                        # and the row landed


def test_render_veto_prompt_block(vetofile):
    assert vr.render_veto_prompt_block(path=vetofile) == ""     # empty registry
    vr.record_veto({"action_type": "task_create", "board": "9"},
                   "never: no tasks on 9", path=vetofile)
    block = vr.render_veto_prompt_block(path=vetofile)
    assert "CAPTAIN VETOES" in block and "veto-001" in block
    assert "action_type=task_create" in block and "board=9" in block


def test_veto_file_path_env_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom-vetoes.yml"
    monkeypatch.setenv("CABINET_CAPTAIN_VETOES", str(custom))
    assert vr.veto_file_path() == custom
    monkeypatch.delenv("CABINET_CAPTAIN_VETOES")
    assert vr.veto_file_path() == vr._DEFAULT_VETO_FILE


def test_malformed_file_raises_not_silently_empty(tmp_path):
    """A malformed veto file must NEVER collapse to an empty set (fail OPEN);
    it raises so record/rebuild treat it as failure."""
    p = tmp_path / "bad.yml"
    p.write_text("vetoes: [this: is: not: valid: yaml\n", encoding="utf-8")
    with pytest.raises(vr.VetoRegistryError):
        vr.load_vetoes(p)


def test_missing_file_is_empty(tmp_path):
    assert vr.load_vetoes(tmp_path / "nope.yml") == []


# --- per-veto golden-eval regression (three-layer enforcement (c)) -----------

def test_recorded_veto_blocks_matching_card_allows_others(vetofile):
    """Golden-eval seed: once a veto is recorded, the shared is_vetoed predicate
    (imported by BOTH the proposer pre-filter and the executor hard-stop) blocks
    the matching card and ONLY the matching card."""
    vr.record_veto({"action_type": "task_create", "board": "5091706356"},
                   "never: auto-create tasks on the AI-Workspace board",
                   path=vetofile)
    rows = vr.load_vetoes(vetofile)
    # the exact card the Captain vetoed — blocked on both layers
    assert vr.is_vetoed("task_create", board="5091706356", vetoes=rows) is True
    # a different board / different kind — NOT over-blocked
    assert vr.is_vetoed("task_create", board="9999", vetoes=rows) is False
    assert vr.is_vetoed("board_status", board="5091706356", vetoes=rows) is False
    # which veto blocked it (for the tell surface)
    m = vr.matching_vetoes("task_create", board="5091706356", vetoes=rows)
    assert len(m) == 1 and m[0]["id"] == "veto-001"
