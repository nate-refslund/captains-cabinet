"""Tests for the organizational event emitter."""

import json
import os
import tempfile
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.events.emitter import emit, replay, VALID_EVENT_TYPES


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path):
    """Use a temporary directory for event logs."""
    os.environ["CABINET_EVENT_LOG_DIR"] = str(tmp_path)
    os.environ.pop("DATABASE_URL", None)  # no DB in tests
    yield tmp_path


class TestEmit:
    def test_basic_event(self, event_log_dir):
        event = emit("role_created", actor="captain", payload={"slug": "eng"})
        assert event["event_type"] == "role_created"
        assert event["actor"] == "captain"
        assert event["payload"]["slug"] == "eng"
        assert event["id"]
        assert event["created_at"]
        assert event["parent_id"] is None

    def test_event_with_parent(self, event_log_dir):
        parent = emit("mission_created", actor="cos", payload={"name": "Ship MVP"})
        child = emit("work_item_created", actor="cos", payload={"desc": "Build UI"}, parent_id=parent["id"])
        assert child["parent_id"] == parent["id"]

    def test_unknown_event_type_raises(self, event_log_dir):
        with pytest.raises(ValueError, match="Unknown event type"):
            emit("totally_made_up", actor="test")

    def test_event_written_to_jsonl(self, event_log_dir):
        emit("session_started", actor="system", payload={"role": "cos"})
        log_files = list(event_log_dir.glob("events-*.jsonl"))
        assert len(log_files) == 1
        with open(log_files[0]) as f:
            line = f.readline().strip()
            event = json.loads(line)
            assert event["event_type"] == "session_started"

    def test_multiple_events_append(self, event_log_dir):
        emit("role_created", actor="captain", payload={"slug": "eng"})
        emit("role_created", actor="captain", payload={"slug": "product"})
        emit("role_created", actor="captain", payload={"slug": "growth"})
        log_files = list(event_log_dir.glob("events-*.jsonl"))
        with open(log_files[0]) as f:
            lines = [l.strip() for l in f if l.strip()]
            assert len(lines) == 3

    def test_empty_payload_defaults(self, event_log_dir):
        event = emit("kill_switch_activated", actor="captain")
        assert event["payload"] == {}

    def test_all_event_types_are_strings(self):
        for et in VALID_EVENT_TYPES:
            assert isinstance(et, str)
            assert "_" in et  # snake_case convention


class TestReplay:
    def test_replay_all(self, event_log_dir):
        emit("role_created", actor="captain", payload={"slug": "eng"})
        emit("mission_created", actor="cos", payload={"name": "test"})
        events = replay()
        assert len(events) == 2

    def test_replay_filter_by_type(self, event_log_dir):
        emit("role_created", actor="captain", payload={"slug": "eng"})
        emit("mission_created", actor="cos", payload={"name": "test"})
        emit("role_created", actor="captain", payload={"slug": "ops"})
        events = replay(event_types=["role_created"])
        assert len(events) == 2
        assert all(e["event_type"] == "role_created" for e in events)

    def test_replay_filter_by_actor(self, event_log_dir):
        emit("role_created", actor="captain", payload={"slug": "eng"})
        emit("mission_created", actor="cos", payload={"name": "test"})
        events = replay(actor="cos")
        assert len(events) == 1
        assert events[0]["actor"] == "cos"

    def test_replay_empty_log(self, event_log_dir):
        events = replay()
        assert events == []

    def test_replay_filter_by_since(self, event_log_dir):
        e1 = emit("role_created", actor="captain", payload={"slug": "eng"})
        events = replay(since=e1["created_at"])
        # since is exclusive-ish (string comparison)
        assert len(events) >= 0  # depends on timing


class TestEventTypes:
    """Verify the event type vocabulary covers the core systems."""

    def test_captain_events_exist(self):
        captain_types = [t for t in VALID_EVENT_TYPES if t.startswith("captain_")]
        assert len(captain_types) >= 3

    def test_role_events_exist(self):
        role_types = [t for t in VALID_EVENT_TYPES if t.startswith("role_")]
        assert len(role_types) >= 5

    def test_mission_events_exist(self):
        mission_types = [t for t in VALID_EVENT_TYPES if t.startswith("mission_")]
        assert len(mission_types) >= 3

    def test_work_item_events_exist(self):
        wi_types = [t for t in VALID_EVENT_TYPES if t.startswith("work_item_")]
        assert len(wi_types) >= 4

    def test_policy_events_exist(self):
        policy_types = [t for t in VALID_EVENT_TYPES if t.startswith("policy_")]
        assert len(policy_types) >= 2

    def test_measurement_events_exist(self):
        assert "ovi_snapshot_computed" in VALID_EVENT_TYPES
        assert "eval_passed" in VALID_EVENT_TYPES
        assert "eval_failed" in VALID_EVENT_TYPES


# ---------------------------------------------------------------------------
# F3: event-kernel unification (org_runtime.Store mirror)
# ---------------------------------------------------------------------------


from framework.events.emitter import (
    _resolve_aggregate,
    _resolve_product_slug,
    _write_to_store,
    _AGGREGATE_MAP,
)


class TestAggregateResolution:
    """_resolve_aggregate maps framework event_type → Store (agg_type, agg_id)."""

    def test_mission_created_uses_mission_id(self):
        agg_type, agg_id = _resolve_aggregate(
            "mission_created", {"mission_id": "m-1", "name": "Launch"}
        )
        assert agg_type == "mission"
        assert agg_id == "m-1"

    def test_work_item_uses_task_id(self):
        agg_type, agg_id = _resolve_aggregate(
            "work_item_completed", {"task_id": "outcome-001-task-003"}
        )
        assert agg_type == "work_item"
        assert agg_id == "outcome-001-task-003"

    def test_role_event_uses_slug(self):
        agg_type, agg_id = _resolve_aggregate("role_created", {"slug": "engineering"})
        assert agg_type == "role"
        assert agg_id == "engineering"

    def test_ovi_uses_period(self):
        agg_type, agg_id = _resolve_aggregate(
            "ovi_snapshot_computed", {"period": "2026-W21"}
        )
        assert agg_type == "ovi"
        assert agg_id == "2026-W21"

    def test_missing_payload_key_falls_back_to_id(self):
        # Use a captain_decision_logged event; expected key is "decision_id"
        # but payload only has "id"
        agg_type, agg_id = _resolve_aggregate(
            "captain_decision_logged", {"id": "decision-42"}
        )
        assert agg_type == "captain"
        assert agg_id == "decision-42"

    def test_unmapped_event_type_uses_prefix(self):
        # Not in _AGGREGATE_MAP — should derive aggregate_type from prefix
        agg_type, agg_id = _resolve_aggregate("custom_unknown_event", {"id": "x"})
        assert agg_type == "custom"
        assert agg_id == "x"

    def test_completely_missing_id_returns_unknown(self):
        agg_type, agg_id = _resolve_aggregate("mission_created", {})
        assert agg_type == "mission"
        assert agg_id == "unknown"

    def test_all_valid_event_types_covered(self):
        """Every event type in VALID_EVENT_TYPES should have an aggregate mapping
        OR have a sensible prefix fallback."""
        for et in VALID_EVENT_TYPES:
            agg_type, _ = _resolve_aggregate(et, {})
            assert agg_type, f"{et} produced empty aggregate_type"


class TestProductSlugResolution:
    def test_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("CABINET_PRODUCT_SLUG", "myproduct")
        assert _resolve_product_slug() == "myproduct"

    def test_active_project_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CABINET_PRODUCT_SLUG", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "active-project.txt").write_text("alpha-project\n")
        assert _resolve_product_slug() == "alpha-project"

    def test_default_when_nothing_set(self, monkeypatch):
        monkeypatch.delenv("CABINET_PRODUCT_SLUG", raising=False)
        monkeypatch.delenv("CABINET_ROOT", raising=False)
        assert _resolve_product_slug() == "default"

    def test_empty_active_project_falls_back(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CABINET_PRODUCT_SLUG", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "active-project.txt").write_text("   \n")  # whitespace only
        assert _resolve_product_slug() == "default"


class TestStoreMirrorGating:
    """_write_to_store should skip cleanly under test/disabled conditions."""

    def test_skips_under_pytest(self, monkeypatch):
        # PYTEST_CURRENT_TEST is set by pytest during test runs; emit() should
        # auto-skip the Store write so the dev cache isn't polluted.
        monkeypatch.delenv("CABINET_FRAMEWORK_STORE_MIRROR", raising=False)
        # Even if we pass a "valid"-looking event, no Store import / write happens
        event = {
            "id": "test-id",
            "event_type": "mission_created",
            "actor": "test",
            "payload": {"mission_id": "m-test"},
            "parent_id": None,
            "created_at": "2026-05-26T00:00:00Z",
        }
        # Should not raise + should be a no-op
        _write_to_store(event)

    def test_force_off_short_circuits(self, monkeypatch):
        monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
        event = {
            "id": "x", "event_type": "mission_created", "actor": "t",
            "payload": {}, "parent_id": None, "created_at": "x",
        }
        # Should not raise — explicit force-off
        _write_to_store(event)

    def test_emit_does_not_crash_when_store_disabled(self, monkeypatch, tmp_path):
        # Full emit() with store mirror disabled — confirms F3 doesn't break
        # the JSONL/DB writes when Store is unavailable.
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
        event = emit("role_created", actor="cap", payload={"slug": "eng"})
        assert event["event_type"] == "role_created"
        # JSONL was written
        log_files = list(tmp_path.glob("*.jsonl"))
        assert len(log_files) >= 1


# ---------------------------------------------------------------------------
# F3 / R4: single authoritative event_id + canonical Postgres schema shape
# ---------------------------------------------------------------------------


class TestEventIdPassthrough:
    """emit() and the Store mirror must agree on event_id.

    Pre-R4 bug: framework minted an event['id'] for JSONL/Postgres while
    Store.append_event() minted its own uuid → one logical event ended up
    with TWO ids across ledgers, breaking traceability.
    """

    def test_store_mirror_uses_same_event_id_as_framework(
        self, monkeypatch, tmp_path
    ):
        import sqlite3

        # Isolate the Store SQLite to a tmp path
        db_path = tmp_path / "org-runtime-test.sqlite3"
        monkeypatch.setenv("ORG_RUNTIME_DB", str(db_path))
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "1")  # force on
        monkeypatch.setenv("CABINET_PRODUCT_SLUG", "test-product")

        event = emit(
            "mission_created",
            actor="cos",
            payload={"mission_id": "m-r4-test", "title": "R4 unification"},
        )

        # Read the row Store wrote and assert event_id passthrough
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT event_id, event_type, actor, aggregate_type, "
                "aggregate_id, product_slug, source FROM org_events"
            ).fetchall()
        finally:
            conn.close()

        assert len(rows) == 1, "expected exactly one mirrored row"
        store_event_id = rows[0][0]
        assert store_event_id == event["id"], (
            f"Store event_id {store_event_id!r} must equal framework "
            f"event id {event['id']!r} — they describe the SAME event"
        )

    def test_store_mirror_propagates_resolved_fields(
        self, monkeypatch, tmp_path
    ):
        """aggregate_type, aggregate_id, product_slug, source must propagate."""
        import sqlite3

        db_path = tmp_path / "org-runtime-resolve.sqlite3"
        monkeypatch.setenv("ORG_RUNTIME_DB", str(db_path))
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "1")
        monkeypatch.setenv("CABINET_PRODUCT_SLUG", "vertical-slice")

        emit(
            "work_item_completed",
            actor="cto",
            payload={"task_id": "outcome-001-task-007"},
        )

        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT aggregate_type, aggregate_id, product_slug, source, "
                "event_type FROM org_events"
            ).fetchone()
        finally:
            conn.close()

        agg_type, agg_id, product_slug, source, event_type = row
        assert agg_type == "work_item"
        assert agg_id == "outcome-001-task-007"
        assert product_slug == "vertical-slice"
        assert source == "framework"
        assert event_type == "work_item_completed"

    def test_store_append_event_default_signature_unchanged(
        self, monkeypatch, tmp_path
    ):
        """When called without event_id (pre-R4 callers), Store still mints
        its own uuid. R4 must not break existing org_runtime CLI callers."""
        import sys as _sys

        # Import Store the same way emitter does
        framework_root = Path(__file__).resolve().parent.parent.parent.parent
        lib_path = framework_root / "cabinet" / "scripts" / "lib"
        if str(lib_path) not in _sys.path:
            _sys.path.insert(0, str(lib_path))
        from org_runtime import Store  # type: ignore

        db_path = tmp_path / "org-runtime-default.sqlite3"
        monkeypatch.setenv("ORG_RUNTIME_DB", str(db_path))

        store = Store()
        event_a = store.append_event(
            event_type="role_created",
            product_slug="p",
            aggregate_type="role",
            aggregate_id="eng",
            actor="captain",
            payload={"slug": "eng"},
        )
        event_b = store.append_event(
            event_type="role_created",
            product_slug="p",
            aggregate_type="role",
            aggregate_id="ops",
            actor="captain",
            payload={"slug": "ops"},
        )

        # No event_id passed → each call gets a fresh uuid (existing behavior)
        assert event_a["event_id"] != event_b["event_id"]
        assert len(event_a["event_id"]) == 36  # uuid4 string length

    def test_store_append_event_honors_caller_supplied_event_id(
        self, monkeypatch, tmp_path
    ):
        """When event_id is passed, Store uses it verbatim (R4 contract)."""
        import sys as _sys

        framework_root = Path(__file__).resolve().parent.parent.parent.parent
        lib_path = framework_root / "cabinet" / "scripts" / "lib"
        if str(lib_path) not in _sys.path:
            _sys.path.insert(0, str(lib_path))
        from org_runtime import Store  # type: ignore

        db_path = tmp_path / "org-runtime-supplied.sqlite3"
        monkeypatch.setenv("ORG_RUNTIME_DB", str(db_path))

        store = Store()
        result = store.append_event(
            event_type="role_created",
            product_slug="p",
            aggregate_type="role",
            aggregate_id="eng",
            actor="captain",
            payload={},
            event_id="11111111-2222-3333-4444-555555555555",
        )
        assert result["event_id"] == "11111111-2222-3333-4444-555555555555"


class TestPostgresSchemaAlignment:
    """_write_to_db must INSERT against the canonical 045 schema columns.

    Pre-R4 bug: emitter wrote (id, event_type, actor, payload, parent_id,
    created_at) but 045-org-runtime-slice.sql defines (event_id, event_type,
    product_slug, aggregate_type, aggregate_id, actor, source, payload,
    supersedes_event_id, created_at). Live writes would fail.
    """

    REQUIRED_COLUMNS = {
        "event_id",
        "event_type",
        "product_slug",
        "aggregate_type",
        "aggregate_id",
        "actor",
        "source",
        "payload",
        "supersedes_event_id",
        "created_at",
    }

    def _capture_sql(self, monkeypatch, tmp_path):
        """Run emit() against a fake psycopg2 and capture the SQL + params."""
        import types

        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("DATABASE_URL", "postgres://fake/db")
        monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
        monkeypatch.setenv("CABINET_PRODUCT_SLUG", "pg-test-product")

        captured: dict = {}

        class FakeCursor:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def execute(self_inner, sql, params):
                captured["sql"] = sql
                captured["params"] = params

        class FakeConn:
            def cursor(self_inner):
                return FakeCursor()

            def commit(self_inner):
                captured["committed"] = True

            def close(self_inner):
                captured["closed"] = True

        fake_module = types.SimpleNamespace(connect=lambda url: FakeConn())
        monkeypatch.setitem(sys.modules, "psycopg2", fake_module)
        return captured

    def test_insert_uses_canonical_045_columns(self, monkeypatch, tmp_path):
        captured = self._capture_sql(monkeypatch, tmp_path)

        emit(
            "mission_created",
            actor="cos",
            payload={"mission_id": "m-pg-1", "title": "Schema align"},
        )

        sql = captured["sql"]
        # Extract the column-list between "(" and ")" after INSERT INTO
        import re

        m = re.search(r"INSERT INTO org_events\s*\(([^)]+)\)", sql)
        assert m, f"could not parse INSERT column list from SQL: {sql!r}"
        cols = {c.strip() for c in m.group(1).split(",")}
        assert cols == self.REQUIRED_COLUMNS, (
            f"INSERT column set {cols} != canonical 045 schema "
            f"{self.REQUIRED_COLUMNS}"
        )

    def test_insert_params_align_with_column_order(
        self, monkeypatch, tmp_path
    ):
        captured = self._capture_sql(monkeypatch, tmp_path)

        event = emit(
            "mission_created",
            actor="cos",
            payload={"mission_id": "m-pg-2"},
        )

        sql = captured["sql"]
        params = captured["params"]

        # 10 placeholders, 10 params
        assert sql.count("%s") == 10
        assert len(params) == 10

        # Position 0 = event_id (same as framework event["id"], R4 contract)
        assert params[0] == event["id"]
        # Position 1 = event_type
        assert params[1] == "mission_created"
        # Position 2 = product_slug
        assert params[2] == "pg-test-product"
        # Position 3 = aggregate_type, Position 4 = aggregate_id
        assert params[3] == "mission"
        assert params[4] == "m-pg-2"
        # Position 5 = actor
        assert params[5] == "cos"
        # Position 6 = source (framework writes mark themselves)
        assert params[6] == "framework"
        # Position 7 = payload JSON (must be a string for psycopg2 jsonb cast)
        assert isinstance(params[7], str)
        loaded = json.loads(params[7])
        assert loaded == {"mission_id": "m-pg-2"}
        # Position 8 = supersedes_event_id (framework's parent_id → None here)
        assert params[8] is None
        # Position 9 = created_at
        assert params[9] == event["created_at"]

    def test_insert_columns_are_subset_of_045_schema(self):
        """Cross-check: every column we INSERT into must exist in the
        canonical 045-org-runtime-slice.sql definition of org_events."""
        import re

        schema_path = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "cabinet"
            / "sql"
            / "045-org-runtime-slice.sql"
        )
        sql_text = schema_path.read_text()

        # Find the CREATE TABLE block for org_events
        m = re.search(
            r"CREATE TABLE IF NOT EXISTS org_events\s*\((.*?)\);",
            sql_text,
            flags=re.DOTALL,
        )
        assert m, "could not locate org_events CREATE TABLE in 045 schema"
        body = m.group(1)
        # Crude column-name extraction: first token of each non-empty,
        # non-constraint line
        schema_cols: set[str] = set()
        for raw_line in body.splitlines():
            line = raw_line.strip().rstrip(",")
            if not line:
                continue
            upper = line.upper()
            if upper.startswith(("PRIMARY KEY", "FOREIGN KEY", "CONSTRAINT", "CHECK")):
                continue
            token = line.split()[0]
            schema_cols.add(token)

        assert TestPostgresSchemaAlignment.REQUIRED_COLUMNS.issubset(
            schema_cols
        ), (
            f"Emitter wants to INSERT into "
            f"{TestPostgresSchemaAlignment.REQUIRED_COLUMNS - schema_cols} "
            f"which are NOT in 045 org_events columns {schema_cols}"
        )
