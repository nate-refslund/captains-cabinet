"""Tests for ``framework.sources.org.OrgSource`` — the org-box adapter (P3a).

Proves:
  * protocol conformance — ``OrgSource`` structurally satisfies
    ``base.PersonalSource`` and mirrors ``null.py`` semantics on every
    non-search method (honest empties, tri-state ``None``, ``read_note``
    raises);
  * hit-shape mapping — a mocked ``memory_search`` TSV payload maps to the
    framework hit contract ``{source, ref, text, base_score, who, ts,
    content_ts}`` with ISO-8601 ``content_ts`` (or honest ``None``), malformed
    rows + the ``Embedding failed`` sentinel skipped;
  * argv discipline — untrusted query text travels ONLY as a subprocess argv
    element, never interpolated into the fixed ``bash -c`` snippet;
  * fail-closed on missing env — no ``NEON_CONNECTION_STRING`` (env or named
    in ``cabinet/.env``) ⇒ honest empty, NO subprocess spawned;
  * comma-type handling — ``CABINET_ORG_MEMORY_TYPES="a,b"`` fans out one
    backend query per type, merges, dedupes by ``(source, ref)``, ranks by
    ``base_score``;
  * resolver binding — a ``sources.yml`` naming
    ``framework.sources.org:OrgSource`` binds through ``get_source()`` (the
    framework/sources tree is a trusted adapter home), while the stray-module
    refusal of the resolver stays intact (covered by the sibling resolver
    suite).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

from framework import sources as src_pkg
from framework.sources import org as org_mod
from framework.sources.base import PersonalSource
from framework.sources.org import OrgSource

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)?$")

_ENV_KEYS = (
    "NEON_CONNECTION_STRING",
    "CABINET_ROOT",
    "CABINET_ORG_MEMORY_TYPES",
    "CABINET_ORG_SEARCH_LIMIT",
    "CABINET_ORG_MIN_SCORE",
)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Every case starts with a clean resolver cache and none of the adapter's
    env knobs set (each test sets exactly what it needs); both are restored."""
    src_pkg._reset_cache()
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    src_pkg._reset_cache()


def _configured(monkeypatch, tmp_path):
    """Point the adapter at an empty root with the backend 'configured' via a
    dummy env-var VALUE (never used — the subprocess is always mocked)."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("NEON_CONNECTION_STRING", "postgres://dummy.invalid/db")


# --- protocol conformance ----------------------------------------------------
def test_org_source_satisfies_the_protocol():
    src = OrgSource()
    assert isinstance(src, PersonalSource)


def test_non_search_methods_mirror_null_semantics(monkeypatch, tmp_path):
    """Every capability an org box does not have is an HONEST empty — the same
    value ``NullPersonalSource`` returns, for the same documented reasons."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # nothing configured
    src = OrgSource()
    assert src.available() is False
    assert src.find_reply_candidates() == []
    assert src.person_intel("slug") == ""
    assert src.open_commitments("owed_by_captain") == []
    assert src.voice_profile() == "" and src.model_patterns() == ""
    assert src.drafting_lessons("2026-01-01") == ""
    assert src.find_threads() == []
    assert src.gather({"slug": "x"}) == {}
    assert src.draft_fn({"slug": "x"}, {}) == ""       # honest decline (falsy)
    assert src.captain_replied_since("x", None) is None  # honest UNKNOWN
    assert src.still_awaiting("x") is None               # honest UNKNOWN
    assert src.deploy_health("app") == {}
    assert src.briefing_commitments() == []
    with pytest.raises(FileNotFoundError):
        src.read_note("anything.md")


# --- fail-closed on missing env ------------------------------------------------
def test_search_fails_closed_without_neon_env(monkeypatch, tmp_path):
    """No NEON_CONNECTION_STRING in env, no cabinet/.env at the root ⇒ the
    honest empty, and NO subprocess is ever spawned."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))

    def _boom(*a, **k):  # pragma: no cover - failing is the assertion
        raise AssertionError("subprocess must not be spawned when unconfigured")

    monkeypatch.setattr(org_mod.subprocess, "run", _boom)
    src = OrgSource()
    assert src.available() is False
    assert src.search("who is the counterparty") == {"hits": [], "topic_terms": None}


def test_env_file_name_only_counts_as_configured(monkeypatch, tmp_path):
    """A cabinet/.env that NAMES the variable configures the backend (memory.sh
    sources it) — checked by name, the value never surfaces anywhere."""
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    env_file = tmp_path / "cabinet" / ".env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("export NEON_CONNECTION_STRING=postgres://x.invalid/db\n",
                        encoding="utf-8")
    assert OrgSource().available() is True


def test_empty_or_nul_query_fails_closed(monkeypatch, tmp_path):
    _configured(monkeypatch, tmp_path)
    called = []
    src = OrgSource(run_search=lambda *a: called.append(a) or "")
    assert src.search("") == {"hits": [], "topic_terms": None}
    assert src.search("  ", topic="  ") == {"hits": [], "topic_terms": None}
    assert src.search("bad\x00query") == {"hits": [], "topic_terms": None}
    assert called == []


# --- hit-shape mapping from a mocked subprocess payload -------------------------
# Hybrid 8-col rows (source_type/who/when_at/similarity/score/trust/preview/ref),
# one legacy 6-col row, one degenerate row, the sentinel, a blank — all handled.
_TSV = (
    "captain_decision\tcos\t2026-07-01 09:30\t0.912\t0.870\tcaptain\tDecision preview text\tdec-42\n"
    "product_spec\tcpo\t2026-06-15 14:05\t0.871\t0.790\tderived\tSpec preview\tspec-7\n"
    "working_note\tcto\t2026-05-01 08:00\t0.610\tLegacy six-col preview\tnote-6\n"
    "working_note\tcto\tnot-a-date\tnot-a-float\t0.100\tderived\tOdd row still mapped\tnote-1\n"
    "malformed row without tabs\n"
    "Embedding failed\n"
    "\n"
)


def test_hit_shape_mapping_from_mocked_subprocess(monkeypatch, tmp_path):
    """The default backend path: subprocess.run is mocked, the TSV payload maps
    to the exact hit contract the framework callers consume, and the query
    travels ONLY as an argv element (never inside the -c snippet)."""
    _configured(monkeypatch, tmp_path)
    # The default runner requires memory.sh to exist at the root.
    lib = tmp_path / "cabinet" / "scripts" / "lib" / "memory.sh"
    lib.parent.mkdir(parents=True)
    lib.write_text("# stub\n", encoding="utf-8")

    captured = {}

    class _Proc:
        returncode = 0
        stdout = _TSV
        stderr = ""

    def _fake_run(argv, **kw):
        captured["argv"] = argv
        captured["kw"] = kw
        return _Proc()

    monkeypatch.setattr(org_mod.subprocess, "run", _fake_run)
    query_text = "garden budget'; DROP TABLE x; --"
    out = OrgSource().search("some-slug", topic=query_text)

    # argv discipline: shell=False list; the untrusted text is a discrete argv
    # element; the -c snippet is the fixed constant.
    argv = captured["argv"]
    assert argv[0] == "bash" and argv[1] == "-c"
    assert argv[2] == org_mod._MEMORY_SEARCH_SNIPPET
    assert any(query_text in a for a in argv[3:])
    assert query_text not in argv[2]
    assert captured["kw"].get("timeout") == org_mod._SUBPROCESS_TIMEOUT
    assert captured["kw"]["env"]["CABINET_ROOT"] == str(tmp_path)

    hits = out["hits"]
    assert out["topic_terms"] is None
    # 4 parseable rows survive; sentinel/malformed/blank skipped; ranked by
    # base_score (blended score on hybrid rows, similarity on the legacy row).
    assert [h["ref"] for h in hits] == ["dec-42", "spec-7", "note-6", "note-1"]
    top = hits[0]
    assert top["source"] == "captain_decision"
    assert top["text"] == "Decision preview text"
    assert top["who"] == "cos"
    assert top["base_score"] == pytest.approx(0.870)      # blended ranking score
    assert top["similarity"] == pytest.approx(0.912)      # vec-sim extra
    assert top["trust"] == "captain"
    assert top["content_ts"] == "2026-07-01T09:30:00+00:00"
    assert _ISO_RE.match(top["content_ts"])
    assert top["ts"] == top["content_ts"]
    # Legacy 6-col row: base_score = similarity, no hybrid extras.
    legacy = hits[2]
    assert legacy["base_score"] == pytest.approx(0.610)
    assert "trust" not in legacy and "similarity" not in legacy
    assert legacy["text"] == "Legacy six-col preview"
    # The odd row degrades honestly: unparseable similarity -> 0.0 extra,
    # content_ts None (un-fenceable ⇒ the downstream leak fence EXCLUDES it —
    # never a fabricated timestamp).
    odd = hits[3]
    assert odd["base_score"] == pytest.approx(0.100)
    assert odd["similarity"] == 0.0
    assert odd["content_ts"] is None and odd["ts"] is None


def test_backend_failure_returns_honest_empty(monkeypatch, tmp_path):
    _configured(monkeypatch, tmp_path)
    src = OrgSource(run_search=lambda *a: None)          # runner failed
    assert src.search("q") == {"hits": [], "topic_terms": None}
    boom = OrgSource(run_search=lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    assert boom.search("q") == {"hits": [], "topic_terms": None}  # never raises


def test_missing_memory_lib_fails_closed(monkeypatch, tmp_path):
    """Default runner: no cabinet/scripts/lib/memory.sh at the root ⇒ no spawn,
    honest empty (a clean-room box missing the cabinet scripts stays Null-like)."""
    _configured(monkeypatch, tmp_path)

    def _boom(*a, **k):  # pragma: no cover - failing is the assertion
        raise AssertionError("must not spawn without memory.sh")

    monkeypatch.setattr(org_mod.subprocess, "run", _boom)
    assert OrgSource().search("q") == {"hits": [], "topic_terms": None}


# --- comma-type handling ---------------------------------------------------------
def test_comma_types_normalize_to_one_query_dedup_and_rank(monkeypatch, tmp_path):
    """The hybrid backend takes the comma list natively: ONE query (one
    embedding), types normalized (whitespace/blank segments dropped), results
    deduped by (source, ref) and ranked by base_score."""
    _configured(monkeypatch, tmp_path)
    monkeypatch.setenv("CABINET_ORG_MEMORY_TYPES", " captain_decision , product_spec ,,")
    calls = []

    def _runner(query, source_types, limit, min_score):
        calls.append((query, source_types, limit, min_score))
        return ("captain_decision\tcos\t2026-07-01 09:30\t0.65\tlow\tshared-ref\n"
                "captain_decision\tcos\t2026-07-01 09:30\t0.65\tlow-dup\tshared-ref\n"
                "captain_decision\tcos\t2026-07-02 10:00\t0.95\thigh\tdec-9\n"
                "product_spec\tcpo\t2026-07-03 11:00\t0.80\tmid\tspec-3\n")

    out = OrgSource(run_search=_runner).search("handle", topic="the topic")
    assert len(calls) == 1                                   # ONE backend query
    assert calls[0][0] == "the topic handle"                 # topic-prepended
    assert calls[0][1] == "captain_decision,product_spec"    # normalized CSV
    assert calls[0][3] == ""                                 # min_score: backend default
    # dedup by (source, ref): shared-ref appears once; ranked score-desc
    refs = [h["ref"] for h in out["hits"]]
    assert refs == ["dec-9", "spec-3", "shared-ref"]


def test_limit_and_min_score_knobs(monkeypatch, tmp_path):
    _configured(monkeypatch, tmp_path)
    monkeypatch.setenv("CABINET_ORG_SEARCH_LIMIT", "2")
    monkeypatch.setenv("CABINET_ORG_MIN_SCORE", "0.5")
    rows = ("t\twho\t2026-07-01 09:30\t0.9\ta\tr1\n"
            "t\twho\t2026-07-01 09:31\t0.7\tb\tr2\n"
            "t\twho\t2026-07-01 09:32\t0.6\tc\tr3\n"
            "t\twho\t2026-07-01 09:33\t0.1\tbelow-floor\tr4\n")
    seen = {}
    out = OrgSource(
        run_search=lambda q, t, l, ms: seen.setdefault("args", (q, t, l, ms)) and rows or rows
    ).search("q")
    assert [h["ref"] for h in out["hits"]] == ["r1", "r2"]  # floor + cap applied
    assert seen["args"][3] == "0.5"    # floor passed through to the backend too


# --- resolver binding --------------------------------------------------------------
def test_resolver_binds_org_source_from_sources_yml(tmp_path, monkeypatch):
    """``adapter: framework.sources.org:OrgSource`` in sources.yml binds through
    ``get_source()`` — the framework/sources package is a trusted adapter home
    alongside the instance flavor-a tree."""
    cfg_dir = tmp_path / "instance/config"   # joined literal (layer-sep safe)
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "sources.yml").write_text(
        "adapter: framework.sources.org:OrgSource\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    src = src_pkg.get_source()
    assert isinstance(src, OrgSource)
    assert isinstance(src, PersonalSource)
    # unconfigured backend at this empty root ⇒ still fail-closed empties
    assert src.available() is False
    assert src.search("x") == {"hits": [], "topic_terms": None}


def test_org_module_stays_layer_sep_clean():
    """org.py lives in framework/ — no bare quoted instance token, no
    screenpipe/_shared import (same self-check the resolver suite runs on the
    package's other modules; needle assembled at runtime)."""
    dq, sq = chr(34), chr(39)
    needle_dq = dq + "inst" + "ance" + dq
    needle_sq = sq + "inst" + "ance" + sq
    text = Path(org_mod.__file__).read_text(encoding="utf-8")
    assert needle_dq not in text and needle_sq not in text
    forbidden_imports = ("screenpipe", "draft_lib", "commitments_lib",
                         "context_lib", "me_signal", "sp_lib", "product_ops_lib")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            for tok in forbidden_imports:
                assert tok not in stripped, "org.py statically imports %s" % tok
