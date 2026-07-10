"""Tests for cabinet/scripts/exhaust-archive.py (ORG-SENSES-2 organ).

Fixture-driven; NO redis, NO network — the stream/entry/embed seams inject.
Pins the load-bearing contracts:

  * verbatim archive — fields (incl. captain_verified provenance on
    killswitch/veto verbs) land byte-faithful in the append-only JSONL;
  * append-only — a second sweep appends, never rewrites;
  * incremental state — last redis-id per stream advances; next sweep reads
    only the delta (exclusive-from);
  * stable embed source_id (trig:<stream>:<id>) so re-embeds upsert;
  * embedded content is secret-scrubbed names-not-values, the archive line
    keeps the verbatim value (audits > prompts split);
  * embed failure does NOT rewind state (archive is the durability floor);
  * dry-run writes nothing; embed flood-guard cap respected;
  * services.yml row present + scheduled.

Run: python3.12 -m pytest cabinet/scripts/tests/test_exhaust_archive.py -q
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "cabinet" / "scripts" / "exhaust-archive.py"

_spec = _ilu.spec_from_file_location("exhaust_archive", _SCRIPT)
ea = _ilu.module_from_spec(_spec)
sys.modules["exhaust_archive"] = ea
_spec.loader.exec_module(ea)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EXHAUST_ARCHIVE_DIR", str(tmp_path / "arch"))
    monkeypatch.setenv("CABINET_EXHAUST_STATE", str(tmp_path / "state.json"))
    return tmp_path


def _streams():
    return ["cabinet:triggers:cos"]


def _mk_entries(rows):
    """entries_fn honoring the exclusive-from contract of read_entries."""
    def fn(stream, after_id):
        out = [(rid, f) for rid, f in rows.get(stream, [])]
        if after_id:
            out = [(rid, f) for rid, f in out if rid > after_id]
        return out
    return fn


VETO = {"sender": "captain-session", "message": "KILLSWITCH: freeze pm_write",
        "captain_verified": "true"}


class TestArchive:
    def test_verbatim_append_with_provenance(self, env):
        rows = {"cabinet:triggers:cos": [("100-0", VETO)]}
        embeds = []
        s = ea.run_sweep(streams_fn=_streams, entries_fn=_mk_entries(rows),
                         embed_fn=lambda *a: embeds.append(a) or True)
        assert s["archived"] == 1 and s["embedded"] == 1
        lines = (env / "arch" / "triggers" /
                 "cabinet_triggers_cos.jsonl").read_text().splitlines()
        row = json.loads(lines[0])
        assert row["fields"] == VETO                      # verbatim
        assert row["fields"]["captain_verified"] == "true"  # provenance intact
        assert row["id"] == "100-0"

    def test_append_only_and_incremental_state(self, env):
        rows = {"cabinet:triggers:cos": [("100-0", VETO)]}
        entries = _mk_entries(rows)
        ea.run_sweep(streams_fn=_streams, entries_fn=entries,
                     embed_fn=lambda *a: True)
        # second sweep with one NEW row — old row must not re-archive
        rows["cabinet:triggers:cos"].append(("200-0", {"message": "wake"}))
        s2 = ea.run_sweep(streams_fn=_streams, entries_fn=entries,
                          embed_fn=lambda *a: True)
        assert s2["archived"] == 1
        lines = (env / "arch" / "triggers" /
                 "cabinet_triggers_cos.jsonl").read_text().splitlines()
        assert [json.loads(l)["id"] for l in lines] == ["100-0", "200-0"]
        state = json.loads((env / "state.json").read_text())
        assert state["last_ids"]["cabinet:triggers:cos"] == "200-0"

    def test_embed_failure_does_not_rewind_state(self, env):
        rows = {"cabinet:triggers:cos": [("100-0", VETO)]}
        s = ea.run_sweep(streams_fn=_streams, entries_fn=_mk_entries(rows),
                         embed_fn=lambda *a: False)
        assert s["archived"] == 1 and s["embed_failures"] == 1
        state = json.loads((env / "state.json").read_text())
        assert state["last_ids"]["cabinet:triggers:cos"] == "100-0"

    def test_dry_run_writes_nothing(self, env):
        rows = {"cabinet:triggers:cos": [("100-0", VETO)]}
        s = ea.run_sweep(dry_run=True, streams_fn=_streams,
                         entries_fn=_mk_entries(rows),
                         embed_fn=lambda *a: True)
        assert s["archived"] == 1 and s["embedded"] == 0
        assert not (env / "arch").exists()
        assert not (env / "state.json").exists()

    def test_embed_flood_guard(self, env, monkeypatch):
        monkeypatch.setattr(ea, "MAX_EMBEDS_PER_SWEEP", 2)
        rows = {"cabinet:triggers:cos": [
            (f"{i}-0", {"m": str(i)}) for i in range(100, 105)]}
        calls = []
        s = ea.run_sweep(streams_fn=_streams, entries_fn=_mk_entries(rows),
                         embed_fn=lambda *a: calls.append(a) or True)
        assert s["archived"] == 5          # archive is uncapped (durability)
        assert len(calls) == 2             # embeds capped


class TestScrub:
    def test_names_not_values(self):
        out = ea.scrub("OPENAI_API_KEY=sk-abcdefghijklmnopqrstu and "
                       "Bearer abc123456789 done")
        assert "OPENAI_API_KEY=<redacted>" in out
        assert "sk-abcdefghijklmnopqrstu" not in out
        assert "Bearer" in out or "bearer" in out

    def test_archive_keeps_verbatim_but_embed_scrubs(self, env):
        secret = {"message": "TOKEN=supersecretvalue123"}
        rows = {"cabinet:triggers:cos": [("100-0", secret)]}
        embedded = []

        def embed(stream, rid, fields, *a):
            embedded.append(ea.scrub(json.dumps(fields)))
            return True

        ea.run_sweep(streams_fn=_streams, entries_fn=_mk_entries(rows),
                     embed_fn=embed)
        raw = (env / "arch" / "triggers" /
               "cabinet_triggers_cos.jsonl").read_text()
        assert "supersecretvalue123" in raw           # verbatim archive
        assert "supersecretvalue123" not in embedded[0]  # scrubbed embed


class TestParsing:
    def test_flat_pair_xrange_shape(self, monkeypatch):
        raw = json.dumps([["100-0", ["sender", "cron", "message", "hi"]]])
        monkeypatch.setattr(ea, "_redis_cli", lambda *a: raw)
        got = ea.read_entries("cabinet:triggers:cos", None)
        assert got == [("100-0", {"sender": "cron", "message": "hi"})]

    def test_garbage_output_yields_empty(self, monkeypatch):
        monkeypatch.setattr(ea, "_redis_cli", lambda *a: "not json")
        assert ea.read_entries("s", None) == []

    def test_exclusive_from_passed(self, monkeypatch):
        seen = {}

        def cli(*args):
            seen["args"] = args
            return "[]"

        monkeypatch.setattr(ea, "_redis_cli", cli)
        ea.read_entries("s", "42-0")
        assert "(42-0" in seen["args"]


def test_services_row_is_scheduled():
    services = yaml.safe_load(
        (_REPO / "cabinet" / "services.yml").read_text())["services"]
    rows = [s for s in services if s.get("name") == "exhaust-archive"]
    assert len(rows) == 1, "exhaust-archive row lost — ORG-SENSES-2 unscheduled"
    row = rows[0]
    assert row["label"] == "com.cabinet.exhaust-archive"
    assert "exhaust-archive.py" in row["command"]
    assert row["schedule"]["calendar"] and not row.get("disabled")
