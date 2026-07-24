"""Rec 3.3 — charter-only shadow comparer (report-only sidecar).

policy-shadow.py is germline and untouched; this sidecar replays the
recorded shadow stream through a self-contained charter arm and prices the
divergence. Pins: charter rules (mechanical floor only — role/workspace
rules deliberately absent), divergence class split, secret-scrubbed
examples, idempotent-per-date append, shadow-v1 row filter, services row.
"""
from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import json
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_spec = _ilu.spec_from_file_location(
    "charter_shadow", _REPO / "cabinet" / "scripts" / "charter-shadow.py")
cs = _ilu.module_from_spec(_spec)
sys.modules["charter_shadow"] = cs
_spec.loader.exec_module(cs)

NOW = dt.datetime(2026, 7, 9, 5, 10, tzinfo=dt.timezone.utc)


def _row(cmd=None, *, tool="Bash", path=None, engine="allow",
         reason="", officer="cos"):
    ti = {"command": cmd} if cmd is not None else {"file_path": path}
    return {"created_at": "2026-07-08T10:00:00Z", "officer": officer,
            "engine": {"decision": engine, "reason": reason,
                       "policy_version": "shadow-v1"},
            "hook": {"tool_name": tool, "tool_input": ti}}


class TestCharterArm:
    @pytest.mark.parametrize("cmd,expect", [
        ("rm -rf /", "block"),
        ("rm -r -f /opt/testburg-cabinet", "block"),
        ("psql -c 'DROP TABLE cabinet_memory'", "block"),
        ("psql -c 'DELETE FROM users WHERE 1=1'", "block"),
        ("vercel --prod", "block"),
        ("ls -la && echo done", "allow"),
        ("git push origin feat/x", "allow"),
        ("rm build/output.txt", "allow"),          # non-recursive rm is fine
    ])
    def test_bash_rules(self, cmd, expect):
        assert cs.charter_decision(
            {"tool_name": "Bash", "tool_input": {"command": cmd}}
        )["decision"] == expect

    def test_env_write_blocked_but_workspace_rules_absent(self):
        assert cs.charter_decision(
            {"tool_name": "Write", "tool_input": {"file_path": "/x/.env"}}
        )["decision"] == "block"
        # the ROLE rule (non-CTO workspace write) is governance mass under
        # evaluation — the charter arm must NOT carry it
        assert cs.charter_decision(
            {"tool_name": "Write",
             "tool_input": {"file_path": "/workspace/bakery/src/app.ts"}}
        )["decision"] == "allow"


class TestCompare:
    def test_divergence_class_split(self):
        rows = [
            _row("ls", engine="allow"),                          # agree-allow
            _row("rm -rf /", engine="block"),                    # agree-block
            _row("echo x > /workspace/p/app.ts", engine="block",
                 reason="non_cto_product_workspace_write"),      # engine-only
            _row("vercel --prod", engine="allow"),               # charter-only
        ]
        m = cs.compare(rows)
        assert m["n"] == 4 and m["agree"] == 2
        assert m["agree_rate"] == 0.5
        assert m["engine_only_blocks"] == 1
        assert m["charter_only_blocks"] == 1
        assert len(m["examples"]) == 2

    def test_examples_are_secret_scrubbed_and_capped(self):
        rows = [_row(f"export API_KEY=hunter{i} && push prod", engine="block",
                     reason="r")
                for i in range(10)]
        m = cs.compare(rows)
        assert len(m["examples"]) == cs.MAX_EXAMPLES
        for ex in m["examples"]:
            assert "hunter" not in ex["command"]
            assert "API_KEY=<redacted>" in ex["command"]

    def test_empty_stream_is_honest(self):
        m = cs.compare([])
        assert m["n"] == 0 and m["agree_rate"] is None


class TestLoadRows:
    def test_filters_to_shadow_v1(self):
        class FakeStore:
            def rows(self, sql, params=()):
                mk = lambda pv, dec: {"payload_json": json.dumps({
                    "shadow_decision": {"decision": dec, "officer": "cos",
                                        "policy_version": pv},
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls"}}),
                    "created_at": "2026-07-08T10:00:00Z", "actor": "cos"}
                return [mk("shadow-v1", "allow"),
                        mk("authority-shadow-v1", "n/a"),
                        {"payload_json": "not json",
                         "created_at": "x", "actor": "cos"}]
        rows = cs.load_shadow_rows(store=FakeStore())
        assert len(rows) == 1
        assert rows[0]["engine"]["decision"] == "allow"


class TestEmitter:
    def test_idempotent_per_date_append(self, tmp_path):
        out = tmp_path / "series.jsonl"
        line = cs.emit_daily_line(rows=[_row("ls")], now=NOW, out_path=out)
        assert line and line["date"] == "2026-07-09" and line["n"] == 1
        assert cs.emit_daily_line(rows=[], now=NOW, out_path=out) is None
        assert len(out.read_text().splitlines()) == 1

    def test_report_only_side_effects(self, tmp_path):
        out = tmp_path / "series.jsonl"
        before = sorted(p.name for p in tmp_path.iterdir())
        cs.emit_daily_line(rows=[], now=NOW, out_path=out)
        assert sorted(p.name for p in tmp_path.iterdir()) == \
            before + ["series.jsonl"]


def test_charter_arm_does_not_import_the_engine_under_evaluation():
    src = (_REPO / "cabinet" / "scripts" / "charter-shadow.py").read_text()
    assert "import policy_engine" not in src
    assert "from framework.authority" not in src


def test_services_row_is_scheduled():
    """RE-ANCHORED 2026-07-24 (COG-4 W6 landing; routed surgery
    feat-cog4-w6-e2-cp1.md §6.4): the dedicated charter-shadow row was
    COMPOSED into the cog4-organ-runner wake vehicle (C4). Accept
    dedicated-row OR composed-organ; in the composed state the enabled
    runner row must NAME the manifest (§9.5 declared association), the
    entrypoint must keep the CLI, and the §3 freshness tuple must derive —
    deletion evidence continues from inside the runner."""
    services = yaml.safe_load(
        (_REPO / "cabinet" / "services.yml").read_text())["services"]
    rows = [s for s in services if s.get("name") == "charter-shadow"]
    if rows:  # dedicated-row state (pre-compose / post-rollback)
        row = rows[0]
        assert row["label"] == "com.cabinet.charter-shadow"
        assert "charter-shadow.py" in row["command"]
        assert row["schedule"]["calendar"] and not row.get("disabled")
        return
    runner_rows = [s for s in services if s.get("name") == "cog4-organ-runner"]
    assert len(runner_rows) == 1, (
        "charter-shadow row lost and no cog4-organ-runner composed row — "
        "deletion evidence stops")
    runner = runner_rows[0]
    assert not runner.get("disabled"), "the composed wake vehicle is disabled"
    manifest_rel = "cabinet/config/organs/charter-shadow.yml"
    assert manifest_rel in (runner.get("organs") or []), (
        "the runner row does not NAME the charter-shadow organ manifest "
        "(§9.5 declared association) — deletion evidence stops")
    man = yaml.safe_load((_REPO / manifest_rel).read_text())
    assert "charter-shadow.py" in man["entrypoints"]["run"]
    fn = man["freshness_needs"]
    assert isinstance(fn["max_staleness_seconds"], int) \
        and fn["max_staleness_seconds"] >= 1
    assert fn["expected_output"]
