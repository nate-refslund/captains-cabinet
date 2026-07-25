"""The org-runtime projections are keyed by LANE, under the name ``lane_slug``.

The column was called ``product_slug`` until 2026-07-25. It never carried
product data — measured on the live store before the rename, all 225,559
org_events rows held exactly two values (the deployment's own lane key and
``default``), the dashboard states the same thing in code
(cabinet/dashboard/src/lib/world/course.ts), and the schema is deployed to no
Postgres database at all. It was a misnamed lane key, and the misnomer is the
kind of thing that makes a cabinet run by a law firm or a bakery read as a
tool built for one software product.

What these tests assert is the property the store EXISTS to deliver, not an
internal invariant: rows stay addressable by lane, under one name, across the
rename — including in a store written before it, whose org_events table is
append-only by trigger and is the only place that history has ever lived.

S0: python3.12, stdlib sqlite3 only, tmp_path roots. Never the live store.

Provenance: authored per the 2026-07-07 full-autonomy grant.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import org_runtime  # noqa: E402
from org_runtime import Store  # noqa: E402

# The lane-keyed table set, stated HERE and not imported from the module
# under test. Reading the module's own list back would make every arm
# below agree with whatever the module happens to say — and would turn a
# pre-change run into a collection error (no assertion executed) instead
# of a real failure.
LANE_KEYED_TABLES = (
    "org_events", "captain_outcomes", "missions", "claude_native_tasks",
    "org_roles", "role_memory_bindings", "role_eval_results",
    "role_evolution_recommendations", "role_hats", "role_lineage_events",
    "ovi_weeks", "learning_digests",
)

_REPO = Path(__file__).resolve().parents[4]
_SCHEMA = _REPO / "cabinet" / "sql" / "045-org-runtime-slice.sql"


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')")}


# ---------------------------------------------------------------------------
# A fresh store speaks lane, everywhere
# ---------------------------------------------------------------------------

def test_every_lane_keyed_table_carries_lane_slug(tmp_path):
    store = Store(tmp_path / "fresh.sqlite3")
    for table in LANE_KEYED_TABLES:
        cols = _columns(store.conn, table)
        assert "lane_slug" in cols, f"{table} is not keyed by lane"
        assert "product_slug" not in cols, f"{table} still carries the old name"


def test_a_lane_keyed_row_round_trips_through_the_new_name(tmp_path):
    """The point of the key: append under a lane, read back by that lane."""
    store = Store(tmp_path / "rt.sqlite3")
    store.append_event("role.defined", "harbour-legal", "org_role", "r1", "tester", {})
    store.append_event("role.defined", "other-lane", "org_role", "r2", "tester", {})
    rows = store.rows("SELECT * FROM org_events WHERE lane_slug = ?", ("harbour-legal",))
    assert [r["aggregate_id"] for r in rows] == ["r1"]
    assert rows[0]["lane_slug"] == "harbour-legal"


# ---------------------------------------------------------------------------
# A store written BEFORE the rename survives it with every row intact
# ---------------------------------------------------------------------------

_LEGACY_DDL = """
CREATE TABLE org_events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  product_slug TEXT NOT NULL,
  aggregate_type TEXT NOT NULL,
  aggregate_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'cli',
  payload_json TEXT NOT NULL DEFAULT '{}',
  supersedes_event_id TEXT REFERENCES org_events(event_id),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_org_events_product_created ON org_events(product_slug, created_at DESC);
CREATE TABLE org_roles (
  product_slug TEXT NOT NULL,
  role_slug TEXT NOT NULL,
  role_name TEXT NOT NULL,
  charter TEXT NOT NULL DEFAULT '',
  capabilities_json TEXT NOT NULL DEFAULT '[]',
  authority_level TEXT NOT NULL DEFAULT 'mission_executor',
  state TEXT NOT NULL DEFAULT 'active',
  version INTEGER NOT NULL DEFAULT 1,
  defined_event_id TEXT NOT NULL,
  latest_event_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (product_slug, role_slug)
);
CREATE INDEX idx_org_roles_product_state ON org_roles(product_slug, state, role_slug);
"""


def _legacy_store(path: Path, lanes: tuple[str, ...] = ("captains-cabinet", "default")) -> dict:
    """A database in the pre-rename shape, carrying history worth losing."""
    conn = sqlite3.connect(str(path))
    conn.executescript(_LEGACY_DDL)
    counts = {}
    for i, lane in enumerate(lanes):
        for n in range(3 + i):
            conn.execute(
                "INSERT INTO org_events (event_id, event_type, product_slug, "
                "aggregate_type, aggregate_id, actor, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (f"e-{lane}-{n}", "session_started", lane, "session", f"a{n}",
                 "officer", f"2026-07-0{n + 1}T00:00:00Z"))
        counts[lane] = 3 + i
    conn.execute(
        "INSERT INTO org_roles (product_slug, role_slug, role_name, defined_event_id, "
        "latest_event_id, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (lanes[0], "cos", "Chief of Staff", "e-x", "e-x", "2026-07-01T00:00:00Z",
         "2026-07-01T00:00:00Z"))
    conn.commit()
    conn.close()
    return counts


def test_pre_rename_store_is_migrated_in_place_with_no_row_lost(tmp_path):
    db = tmp_path / "legacy.sqlite3"
    expected = _legacy_store(db)

    store = Store(db)                      # __init__ runs the migration

    assert "lane_slug" in _columns(store.conn, "org_events")
    assert "product_slug" not in _columns(store.conn, "org_events")
    observed = dict(store.conn.execute(
        "SELECT lane_slug, COUNT(*) FROM org_events GROUP BY 1"))
    assert observed == expected, "history changed shape across the rename"
    assert store.conn.execute("SELECT COUNT(*) FROM org_roles").fetchone()[0] == 1
    # the composite primary key travelled with the column
    assert store.row("SELECT * FROM org_roles WHERE lane_slug = ? AND role_slug = ?",
                     ("captains-cabinet", "cos"))["role_name"] == "Chief of Staff"


def test_migration_is_a_no_op_the_second_time(tmp_path):
    db = tmp_path / "twice.sqlite3"
    _legacy_store(db)
    store = Store(db)                              # opening it did the work
    assert "lane_slug" in _columns(store.conn, "org_events")
    assert store.migrate_lane_key() == []          # nothing left to rename
    assert Store(db).migrate_lane_key() == []      # every open after is inert


def test_migration_reports_every_table_it_renames(tmp_path):
    """Guard mutation: push a migrated store BACK to the pre-rename shape and
    re-run. A migration that silently skipped tables would report fewer."""
    store = Store(tmp_path / "back.sqlite3")
    pushed = ("org_events", "org_roles", "learning_digests")
    for table in pushed:
        store.conn.execute(f"ALTER TABLE {table} RENAME COLUMN lane_slug TO product_slug")
    assert set(store.migrate_lane_key()) == set(pushed)
    for table in pushed:
        assert "lane_slug" in _columns(store.conn, table)


def test_migration_drops_only_the_legacy_named_indexes(tmp_path):
    db = tmp_path / "idx.sqlite3"
    _legacy_store(db)
    names = {r[0] for r in Store(db).conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")}
    assert "idx_org_events_product_created" not in names
    assert "idx_org_roles_product_state" not in names
    assert {"idx_org_events_lane_created", "idx_org_roles_lane_state"} <= names


def test_appending_to_a_migrated_store_keeps_the_old_history_addressable(tmp_path):
    """The migration is worthless if it strands the history it preserved."""
    db = tmp_path / "append.sqlite3"
    _legacy_store(db)
    store = Store(db)
    store.append_event("role.defined", "captains-cabinet", "org_role", "new", "t", {})
    rows = store.rows("SELECT * FROM org_events WHERE lane_slug = ? ORDER BY created_at",
                      ("captains-cabinet",))
    assert len(rows) == 4                                   # 3 legacy + 1 new
    assert {r["aggregate_id"] for r in rows} >= {"a0", "new"}


# ---------------------------------------------------------------------------
# The two schema statements must never drift apart (the half-rename guard)
# ---------------------------------------------------------------------------

def test_sqlite_mirror_and_045_agree_on_the_lane_key(tmp_path):
    """Postgres 045 is the production contract; the SQLite Store is its mirror.
    A rename applied to one and not the other is a runtime break that no
    single-file test would see."""
    schema = _SCHEMA.read_text()
    pg_lane_tables = {
        m.group(1) for m in re.finditer(
            r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((?:[^;]*?)lane_slug", schema)
    }
    assert pg_lane_tables, "045 declares no lane-keyed table — parse broke"
    store = Store(tmp_path / "parity.sqlite3")
    mirrored = {t for t in pg_lane_tables
                if store.conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (t,)).fetchone()}
    for table in mirrored:
        assert "lane_slug" in _columns(store.conn, table), (
            f"045 keys {table} by lane_slug but the SQLite mirror does not")
    assert set(LANE_KEYED_TABLES) >= pg_lane_tables, (
        "045 gained a lane-keyed table this contract does not cover")
    assert set(getattr(org_runtime, "LANE_KEYED_TABLES", ())) >= pg_lane_tables, (
        "the migration would skip a lane-keyed table 045 declares")


def test_045_names_the_old_column_only_inside_its_migration(tmp_path):
    """The old name may survive as MIGRATION text — renaming a legacy column
    requires naming it — but never as a live column, index or constraint."""
    schema = _SCHEMA.read_text()
    live = [ln for ln in schema.splitlines()
            if "product_slug" in ln
            and "RENAME COLUMN" not in ln
            and "column_name = 'product_slug'" not in ln
            and not ln.lstrip().startswith("--")]
    assert live == [], f"045 still defines the old column: {live}"


# ---------------------------------------------------------------------------
# Callers: the new flag works, and the old spelling did not stop working
# ---------------------------------------------------------------------------

def _parsed(*argv):
    return org_runtime.build_parser().parse_args(list(argv))


def _resolve(*argv) -> str:
    """Parse a CLI line and resolve the lane key through whichever resolver
    this build ships. Named by fallback DELIBERATELY: these arms must exercise
    the flag and env BEHAVIOUR on a pre-rename build too, not die on a missing
    symbol and prove nothing."""
    resolver = getattr(org_runtime, "lane_arg", None) or org_runtime.product_arg
    return resolver(_parsed(*argv))


def test_lane_slug_flag_resolves():
    assert _resolve("org-event", "list", "--lane-slug", "harbour") == "harbour"


def test_legacy_product_slug_flag_still_resolves():
    """Back-compat guard, NOT a new behaviour — it passes before and after.
    bootstrap-roles.sh, activate-project.sh and the dashboard fetchers all
    pass the old spelling, and the rename must not break a single one."""
    assert _resolve("org-event", "list", "--product-slug", "harbour") == "harbour"


@pytest.mark.parametrize("env,expected", [
    ({}, "captains-cabinet"),
    ({"ORG_RUNTIME_PRODUCT": "legacy-env"}, "legacy-env"),
    ({"ORG_RUNTIME_LANE": "new-env"}, "new-env"),
    ({"ORG_RUNTIME_LANE": "new-env", "ORG_RUNTIME_PRODUCT": "legacy-env"}, "new-env"),
])
def test_env_resolution_prefers_the_lane_name_and_honors_the_old_one(
        monkeypatch, env, expected):
    monkeypatch.delenv("ORG_RUNTIME_LANE", raising=False)
    monkeypatch.delenv("ORG_RUNTIME_PRODUCT", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert _resolve("org-event", "list") == expected
