"""Tests for cabinet/scripts/world-chronicle.py (E0b chronicle daemon).

Pins the kickoff doc's binding properties:
  * normalizers are PURE + deterministic (same rows → identical records —
    the E0 frame-identical-render gate rides on this),
  * secret/PII scrub AT INGEST — hostile payloads (names, emails, tokens,
    free text) through EVERY source path leak zero bytes into the chronicle,
  * monotonic ingest ids, cursor resume without duplicates, dated-file
    rollover, and the write fence (records land only under the world dirs).
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import sqlite3
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "world-chronicle.py"

spec = _ilu.spec_from_file_location("world_chronicle", _SCRIPT)
wch = _ilu.module_from_spec(spec)
sys.modules["world_chronicle"] = wch
spec.loader.exec_module(wch)


HOSTILE_STRINGS = [
    "casper@example.com",
    "Reply to Kanal9 about the contract redline",
    "ghp_AbCdEf123456789012345678901234567890",
    "AKIAIOSFODNN7EXAMPLE",
    "xoxb-1234-abcdef",
    "sk-proj-abc123def456ghi789",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload",
    "-----BEGIN PRIVATE KEY-----",
    "Bearer AbC123",
    "password=hunter2",
]


def _org_row(rowid=1, event_id="9493f9ea-302a-4aee-96e8-c3e4bec88796",
             event_type="work_item_completed", aggregate_type="work_item",
             actor="cos", source="framework", payload=None,
             created_at="2026-07-07T10:00:00.000000Z"):
    return (rowid, event_id, event_type, aggregate_type, actor, source,
            json.dumps(payload or {}), created_at)


class TestNormalizerPurity:
    def test_same_row_identical_record(self):
        row = _org_row(payload={"action_type": "pm_write", "risk_class": "low"})
        a = wch.normalize_org_event(row)
        b = wch.normalize_org_event(row)
        assert a == b
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_verb_mapping_and_family_fallback(self):
        assert wch.verb_for("work_item_completed") == "work.completed"
        assert wch.verb_for("mail.sent") == "mail.family"
        assert wch.verb_for("captain_ratified") == "captain.family"
        assert wch.verb_for("never_seen_kind") == "org.other"

    def test_record_carries_no_wall_clock(self):
        # Determinism: nothing in the record may depend on ingest time.
        rec = wch.normalize_org_event(_org_row())
        blob = json.dumps(rec)
        assert rec["ts"] == "2026-07-07T10:00:00.000000Z"
        import datetime as dt
        assert dt.datetime.now(dt.timezone.utc).strftime("%H:%M") not in blob


class TestScrubAtIngest:
    def test_org_event_payload_free_text_never_copied(self):
        payload = {
            "title": HOSTILE_STRINGS[1],
            "email": HOSTILE_STRINGS[0],
            "token": HOSTILE_STRINGS[2],
            "action_type": "pm_write",          # allowlisted + clean → passes
            "risk_class": "low",
        }
        rec = wch.normalize_org_event(_org_row(payload=payload))
        blob = json.dumps(rec)
        for hostile in HOSTILE_STRINGS:
            assert hostile not in blob
        assert rec["attrs"] == {"action_type": "pm_write", "risk_class": "low"}

    def test_allowlisted_field_with_hostile_value_dropped(self):
        # Even an ALLOWLISTED key is dropped when its value fails the guard.
        for hostile in HOSTILE_STRINGS:
            rec = wch.normalize_org_event(
                _org_row(payload={"action_type": hostile}))
            assert "attrs" not in rec or "action_type" not in rec.get("attrs", {})

    def test_consequence_free_text_never_copied(self):
        row = {"ts": "2026-07-07T10:00:00Z", "actor": "cos",
               "action": "action-card", "action_type": "pm_write",
               "subject": HOSTILE_STRINGS[1], "body": HOSTILE_STRINGS[0],
               "proposal": {"required": False, "decision": "approved",
                            "text": HOSTILE_STRINGS[3]},
               "review": {"verdict": "ok", "note": HOSTILE_STRINGS[4]}}
        rec = wch.normalize_consequence(json.dumps(row), "f:1")
        blob = json.dumps(rec)
        for hostile in HOSTILE_STRINGS:
            assert hostile not in blob
        assert rec["verb"] == "consequence.acted"
        assert rec["attrs"]["decision"] == "approved"

    def test_toollog_inputs_outputs_never_copied(self):
        row = {"ts": "2026-07-07T10:00:00Z", "officer": "cos", "tool": "Bash",
               "input": "export SECRET=" + HOSTILE_STRINGS[2],
               "output_preview": HOSTILE_STRINGS[0]}
        rec = wch.normalize_toollog(json.dumps(row), "f:2")
        blob = json.dumps(rec)
        for hostile in HOSTILE_STRINGS:
            assert hostile not in blob
        assert rec["attrs"] == {"tool": "Bash"}

    def test_assert_scrubbed_belt_and_suspenders(self):
        assert wch.assert_scrubbed({"verb": "work.completed", "actor": "cos"})
        assert not wch.assert_scrubbed({"verb": "x", "ref": "a@b.dk"})
        assert not wch.assert_scrubbed({"verb": "x", "kind": "ghp_" + "a" * 30})

    def test_ident_guard(self):
        assert wch.ident_ok("pm_write")
        assert wch.ident_ok("bakery-ceo")
        assert not wch.ident_ok("a b c")             # spaces = free text
        assert not wch.ident_ok("x" * 81)            # unbounded
        assert not wch.ident_ok("ada@example.org") # email
        assert not wch.ident_ok("Bearer abc")
        assert not wch.ident_ok(42)                  # non-str
        assert not wch.ident_ok(None)


class TestPipelineOnFixtureEstate:
    @pytest.fixture()
    def estate(self, tmp_path, monkeypatch):
        db = tmp_path / "org-runtime.sqlite3"
        con = sqlite3.connect(db)
        con.execute("""CREATE TABLE org_events (
            event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL,
            product_slug TEXT NOT NULL DEFAULT 'x',
            aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL DEFAULT 'a',
            actor TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'cli',
            payload_json TEXT NOT NULL DEFAULT '{}',
            supersedes_event_id TEXT, created_at TEXT NOT NULL)""")
        rows = [
            ("e1", "session_started", "session", "cos",
             json.dumps({"note": HOSTILE_STRINGS[0]}), "2026-07-07T09:00:00Z"),
            ("e2", "work_item_completed", "work_item", "bakery-ceo",
             json.dumps({"action_type": "pm_write",
                         "title": HOSTILE_STRINGS[1]}), "2026-07-07T09:05:00Z"),
            ("e3", "policy.shadow_decision", "policy", "newsletter-ceo",
             json.dumps({"action_type": "bash_exec", "risk_class": "low",
                         "posture": "guardian", "verdict": "allow",
                         "command": HOSTILE_STRINGS[2]}), "2026-07-07T09:06:00Z"),
        ]
        for eid, et, agg, actor, payload, ts in rows:
            con.execute(
                "INSERT INTO org_events (event_id, event_type, aggregate_type,"
                " actor, payload_json, created_at) VALUES (?,?,?,?,?,?)",
                (eid, et, agg, actor, payload, ts))
        con.commit()
        con.close()

        events_dir = tmp_path / "events"
        undo_dir = tmp_path / "undo"
        tool_dir = tmp_path / "logs"
        out_dir = tmp_path / "world-out"
        state_dir = tmp_path / "world-state"
        for d in (events_dir, undo_dir, tool_dir):
            d.mkdir()
        import datetime as dt
        today = dt.date.today().isoformat()
        (events_dir / f"consequence-events-{today}.jsonl").write_text(
            json.dumps({"ts": "2026-07-07T09:10:00Z", "actor": "cos",
                        "action": "action-card", "action_type": "pm_write",
                        "proposal": {"required": False, "decision": "approved"},
                        "body": HOSTILE_STRINGS[5]}) + "\n")
        (undo_dir / f"undo-journal-{today}.jsonl").write_text(
            json.dumps({"ts": "2026-07-07T09:11:00Z", "actor": "cos",
                        "action_type": "pm_write", "undo_index": 7,
                        "inverse": HOSTILE_STRINGS[6]}) + "\n")
        (tool_dir / f"{today}.jsonl").write_text(
            json.dumps({"ts": "2026-07-07T09:12:00Z", "officer": "cos",
                        "tool": "Edit", "input": HOSTILE_STRINGS[7]}) + "\n")

        monkeypatch.setattr(wch, "SQLITE_DB", db)
        monkeypatch.setattr(wch, "EVENT_LOG_DIR", events_dir)
        monkeypatch.setattr(wch, "UNDO_DIR", undo_dir)
        monkeypatch.setattr(wch, "TOOL_LOG_DIR", tool_dir)
        monkeypatch.setattr(wch, "OUT_DIR", out_dir)
        monkeypatch.setattr(wch, "STATE_DIR", state_dir)
        monkeypatch.setattr(wch, "STATE_PATH", state_dir / "chronicle-state.json")
        return tmp_path

    def test_collect_assigns_monotonic_iids(self, estate):
        records, state, dropped = wch.collect_batch({"org_events_rowid": 0})
        assert [r["iid"] for r in records] == list(range(1, len(records) + 1))
        assert len(records) == 6      # 3 org + 1 consequence + 1 undo + 1 tool
        assert dropped == 0
        assert state["org_events_rowid"] == 3

    def test_zero_hostile_bytes_end_to_end(self, estate):
        records, _, _ = wch.collect_batch({"org_events_rowid": 0})
        blob = json.dumps(records, sort_keys=True)
        for hostile in HOSTILE_STRINGS:
            assert hostile not in blob

    def test_cursor_resume_no_duplicates(self, estate):
        records1, state1, _ = wch.collect_batch({"org_events_rowid": 0})
        records2, state2, _ = wch.collect_batch(state1)
        assert records2 == []          # nothing new — no re-ingest
        assert state2["org_events_rowid"] == state1["org_events_rowid"]
        assert state2["iid"] == state1["iid"]

    def test_determinism_same_inputs_same_records(self, estate):
        a, _, _ = wch.collect_batch({"org_events_rowid": 0})
        b, _, _ = wch.collect_batch({"org_events_rowid": 0})
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_append_partitions_by_source_date(self, estate):
        records, _, _ = wch.collect_batch({"org_events_rowid": 0})
        wch.append_records(records)
        out = wch.OUT_DIR / "chronicle-2026-07-07.jsonl"
        assert out.exists()
        lines = [json.loads(l) for l in out.read_text().splitlines()]
        assert len(lines) == len(records)
        blob = out.read_text()
        for hostile in HOSTILE_STRINGS:
            assert hostile not in blob

    def test_write_fence_only_world_dirs(self, estate):
        records, state, _ = wch.collect_batch({"org_events_rowid": 0})
        wch.append_records(records)
        wch.save_state(state)
        written = {p for p in Path(estate).rglob("*") if p.is_file()}
        for p in written:
            rel = p.relative_to(estate)
            top = rel.parts[0]
            assert top in {"org-runtime.sqlite3", "events", "undo", "logs",
                           "world-out", "world-state"}, f"stray write: {rel}"

    def test_tail_rollover_and_truncation(self, estate, tmp_path):
        f = tmp_path / "roll.jsonl"
        f.write_text('{"a":1}\n{"a":2}\n')
        lines, off = wch.tail_jsonl(f, 0)
        assert len(lines) == 2
        lines2, off2 = wch.tail_jsonl(f, off)
        assert lines2 == [] and off2 == off
        # SHRINKING truncation (size < offset) restarts honestly from 0.
        # (Same-size in-place rewrite is deliberately out of contract: the
        # sources are append-only dated ledgers — real rollover is a NEW
        # dated filename, which the offset state keys by name.)
        f.write_text('{"b":2}\n')
        lines3, off3 = wch.tail_jsonl(f, off)
        assert len(lines3) == 1 and json.loads(lines3[0][0]) == {"b": 2}

    def test_partial_trailing_line_waits(self, tmp_path):
        f = tmp_path / "partial.jsonl"
        f.write_text('{"a":1}\n{"incomp')
        lines, off = wch.tail_jsonl(f, 0)
        assert len(lines) == 1
        with open(f, "a") as fh:
            fh.write('lete":2}\n')
        lines2, _ = wch.tail_jsonl(f, off)
        assert len(lines2) == 1 and json.loads(lines2[0][0]) == {"incomplete": 2}


class TestPresenceSnapshot:
    def test_build_presence_pure_and_scrubbed(self):
        activity = {
            "cos": json.dumps({"verb": "working", "object": "cabinet/x.py",
                               "since": "2026-07-07T16:47:28Z"}),
            "bakery-ceo": json.dumps({"verb": "deploying",
                                      "object": "token ghp_" + "a" * 30,
                                      "since": "2026-07-07T16:46:29Z"}),
            "newsletter-ceo": None,
        }
        snap = wch.build_presence(activity, {"cos": 100}, False, 42,
                                  "2026-07-07T17:00:00Z")
        assert snap["officers"]["cos"]["verb"] == "working"
        assert snap["officers"]["cos"]["object"] == "cabinet/x.py"
        # Secret-shaped object dropped entirely (ephemeral surface still
        # never carries credential shapes).
        assert "object" not in snap["officers"]["bakery-ceo"]
        assert snap["officers"]["newsletter-ceo"] == {"present": False}
        assert snap["killswitch"] is False
        assert snap["iid_high"] == 42
        # Pure: same inputs, same snapshot.
        assert snap == wch.build_presence(activity, {"cos": 100}, False, 42,
                                          "2026-07-07T17:00:00Z")

    def test_killswitch_flag_breaks_through(self):
        snap = wch.build_presence({}, {}, True, 0, "2026-07-07T17:00:00Z")
        assert snap["killswitch"] is True


class TestRespEncoder:
    def test_resp_roundtrip_shape(self):
        payload = json.dumps({"line": "a b c", "n": 1})
        buf = wch._resp_encode([["XADD", "k", "MAXLEN", "~", "100", "*",
                                 "line", payload]])
        assert buf.startswith(b"*8\r\n$4\r\nXADD\r\n")
        assert payload.encode() in buf
        assert buf.endswith(b"\r\n")
