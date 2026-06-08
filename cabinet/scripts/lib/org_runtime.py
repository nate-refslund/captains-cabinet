#!/usr/bin/env python3
"""Org runtime vertical slice.

The production contract is the Postgres schema in cabinet/sql/045-*. This
module uses SQLite for local/CI execution so the first branch can prove the
whole loop without live Neon credentials.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import textwrap
import uuid
from pathlib import Path
from typing import Any, Iterable


DEFAULT_PRODUCT = "captains-cabinet"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_db_path() -> Path:
    root = Path(os.environ.get("CABINET_ROOT", str(repo_root())))
    return Path(os.environ.get("ORG_RUNTIME_DB", root / "cabinet/cache/org-runtime.sqlite3"))


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def as_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def parse_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"payload must be JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("payload must be a JSON object")
    return data


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS org_events (
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
            CREATE INDEX IF NOT EXISTS idx_org_events_product_created
              ON org_events(product_slug, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_org_events_aggregate
              ON org_events(product_slug, aggregate_type, aggregate_id, created_at DESC);

            CREATE TRIGGER IF NOT EXISTS prevent_org_events_update
            BEFORE UPDATE ON org_events
            BEGIN
              SELECT RAISE(ABORT, 'org_events is append-only; append a superseding event instead');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_org_events_delete
            BEFORE DELETE ON org_events
            BEGIN
              SELECT RAISE(ABORT, 'org_events is append-only; append a superseding event instead');
            END;

            CREATE TABLE IF NOT EXISTS captain_outcomes (
              outcome_id TEXT PRIMARY KEY,
              product_slug TEXT NOT NULL,
              title TEXT NOT NULL,
              metric_name TEXT NOT NULL,
              target_value REAL NOT NULL,
              current_value REAL NOT NULL DEFAULT 0,
              unit TEXT NOT NULL DEFAULT 'points',
              state TEXT NOT NULL CHECK (state IN ('proposed', 'ratified', 'superseded')),
              proposed_by TEXT NOT NULL,
              ratified_by TEXT,
              proposed_event_id TEXT REFERENCES org_events(event_id),
              ratified_event_id TEXT REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS missions (
              mission_id TEXT PRIMARY KEY,
              outcome_id TEXT NOT NULL REFERENCES captain_outcomes(outcome_id),
              product_slug TEXT NOT NULL,
              title TEXT NOT NULL,
              state TEXT NOT NULL CHECK (state IN ('compiled', 'in_progress', 'verified', 'superseded')),
              compiled_event_id TEXT REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS work_graph_nodes (
              node_id TEXT PRIMARY KEY,
              mission_id TEXT NOT NULL REFERENCES missions(mission_id),
              title TEXT NOT NULL,
              owner_role TEXT NOT NULL,
              acceptance_criteria TEXT NOT NULL DEFAULT '',
              evidence_required TEXT NOT NULL DEFAULT '',
              verifier_role TEXT NOT NULL DEFAULT '',
              risk_level TEXT NOT NULL DEFAULT 'medium',
              rollback_note TEXT NOT NULL DEFAULT '',
              budget_note TEXT NOT NULL DEFAULT '',
              captain_attention_estimate REAL NOT NULL DEFAULT 0,
              status TEXT NOT NULL CHECK (status IN ('queue', 'wip', 'verified')),
              verified_value REAL NOT NULL DEFAULT 0,
              verification_summary TEXT,
              completion_event_id TEXT REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              completed_at TEXT,
              UNIQUE(mission_id, node_id)
            );

            CREATE TABLE IF NOT EXISTS work_graph_edges (
              edge_id TEXT PRIMARY KEY,
              mission_id TEXT NOT NULL REFERENCES missions(mission_id),
              from_node_id TEXT NOT NULL REFERENCES work_graph_nodes(node_id),
              to_node_id TEXT NOT NULL REFERENCES work_graph_nodes(node_id),
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS claude_native_tasks (
              product_slug TEXT NOT NULL,
              task_id TEXT NOT NULL,
              session_id TEXT,
              transcript_path TEXT,
              cwd TEXT,
              task_subject TEXT NOT NULL DEFAULT '',
              task_description TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL CHECK (status IN ('created', 'completed')),
              actor TEXT NOT NULL,
              teammate_name TEXT,
              team_name TEXT,
              mission_id TEXT,
              node_id TEXT,
              owner_role TEXT,
              acceptance_criteria TEXT,
              evidence_required TEXT,
              verifier_role TEXT,
              risk_level TEXT,
              metadata_json TEXT NOT NULL DEFAULT '{}',
              created_event_id TEXT REFERENCES org_events(event_id),
              completed_event_id TEXT REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              completed_at TEXT,
              PRIMARY KEY (product_slug, task_id)
            );
            CREATE INDEX IF NOT EXISTS idx_claude_native_tasks_mission
              ON claude_native_tasks(product_slug, mission_id, node_id);
            CREATE INDEX IF NOT EXISTS idx_claude_native_tasks_status
              ON claude_native_tasks(product_slug, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS org_roles (
              product_slug TEXT NOT NULL,
              role_slug TEXT NOT NULL,
              role_name TEXT NOT NULL,
              charter TEXT NOT NULL,
              current_focus TEXT NOT NULL DEFAULT '',
              authority_level TEXT NOT NULL DEFAULT 'mission_executor',
              capabilities_json TEXT NOT NULL DEFAULT '[]',
              state TEXT NOT NULL CHECK (state IN ('active', 'inactive', 'retired')) DEFAULT 'active',
              version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
              officer_session_slug TEXT,
              defined_event_id TEXT NOT NULL REFERENCES org_events(event_id),
              latest_event_id TEXT NOT NULL REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (product_slug, role_slug)
            );
            CREATE INDEX IF NOT EXISTS idx_org_roles_product_state
              ON org_roles(product_slug, state, role_slug);

            CREATE TABLE IF NOT EXISTS role_memory_bindings (
              binding_id TEXT PRIMARY KEY,
              product_slug TEXT NOT NULL,
              role_slug TEXT NOT NULL,
              memory_path TEXT NOT NULL,
              memory_kind TEXT NOT NULL DEFAULT 'tier2',
              bound_event_id TEXT NOT NULL REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              FOREIGN KEY (product_slug, role_slug) REFERENCES org_roles(product_slug, role_slug)
            );
            CREATE INDEX IF NOT EXISTS idx_role_memory_bindings_role
              ON role_memory_bindings(product_slug, role_slug, created_at DESC);

            CREATE TABLE IF NOT EXISTS role_eval_results (
              eval_id TEXT PRIMARY KEY,
              product_slug TEXT NOT NULL,
              role_slug TEXT NOT NULL,
              mission_id TEXT REFERENCES missions(mission_id),
              hat_id TEXT REFERENCES role_hats(hat_id),
              eval_name TEXT NOT NULL,
              score REAL NOT NULL CHECK (score >= 0 AND score <= 1),
              passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
              evidence TEXT NOT NULL,
              recorded_event_id TEXT NOT NULL REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              FOREIGN KEY (product_slug, role_slug) REFERENCES org_roles(product_slug, role_slug)
            );
            CREATE INDEX IF NOT EXISTS idx_role_eval_results_role_created
              ON role_eval_results(product_slug, role_slug, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_role_eval_results_hat
              ON role_eval_results(product_slug, role_slug, hat_id)
              WHERE hat_id IS NOT NULL;

            CREATE TABLE IF NOT EXISTS role_evolution_recommendations (
              recommendation_id TEXT PRIMARY KEY,
              product_slug TEXT NOT NULL,
              role_slug TEXT NOT NULL,
              recommendation_type TEXT NOT NULL CHECK (
                recommendation_type IN (
                  'promote_hat_to_capability',
                  'adjust_charter',
                  'retire_role_review',
                  'continue_current_role'
                )
              ),
              hat_id TEXT REFERENCES role_hats(hat_id),
              basis TEXT NOT NULL,
              recommended_event_id TEXT NOT NULL REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              FOREIGN KEY (product_slug, role_slug) REFERENCES org_roles(product_slug, role_slug)
            );
            CREATE INDEX IF NOT EXISTS idx_role_evolution_recommendations_role_created
              ON role_evolution_recommendations(product_slug, role_slug, created_at DESC);

            CREATE TABLE IF NOT EXISTS role_hats (
              hat_id TEXT PRIMARY KEY,
              product_slug TEXT NOT NULL,
              role_slug TEXT NOT NULL,
              hat_name TEXT NOT NULL,
              purpose TEXT NOT NULL,
              state TEXT NOT NULL CHECK (state IN ('active', 'retired')) DEFAULT 'active',
              created_event_id TEXT REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              FOREIGN KEY (product_slug, role_slug) REFERENCES org_roles(product_slug, role_slug)
            );

            CREATE TABLE IF NOT EXISTS mission_role_assignments (
              assignment_id TEXT PRIMARY KEY,
              mission_id TEXT NOT NULL REFERENCES missions(mission_id),
              hat_id TEXT NOT NULL REFERENCES role_hats(hat_id),
              node_id TEXT REFERENCES work_graph_nodes(node_id),
              assigned_to_role TEXT NOT NULL,
              assignment_event_id TEXT REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              FOREIGN KEY (mission_id, node_id) REFERENCES work_graph_nodes(mission_id, node_id)
            );

            CREATE TABLE IF NOT EXISTS role_lineage_events (
              lineage_id TEXT PRIMARY KEY,
              product_slug TEXT NOT NULL,
              role_slug TEXT NOT NULL,
              hat_id TEXT REFERENCES role_hats(hat_id),
              event_id TEXT NOT NULL REFERENCES org_events(event_id),
              event_kind TEXT NOT NULL,
              note TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (product_slug, role_slug) REFERENCES org_roles(product_slug, role_slug)
            );

            CREATE TABLE IF NOT EXISTS ovi_weeks (
              product_slug TEXT NOT NULL,
              week_start TEXT NOT NULL,
              verified_outcome_value REAL NOT NULL,
              burden_index REAL NOT NULL CHECK (burden_index > 0),
              ovi REAL NOT NULL,
              trend_vs_prior REAL,
              components_json TEXT NOT NULL DEFAULT '{}',
              published_event_id TEXT REFERENCES org_events(event_id),
              created_at TEXT NOT NULL,
              PRIMARY KEY (product_slug, week_start)
            );

            CREATE TABLE IF NOT EXISTS learning_digests (
              digest_id TEXT PRIMARY KEY,
              product_slug TEXT NOT NULL,
              week_start TEXT NOT NULL,
              title TEXT NOT NULL,
              content TEXT NOT NULL,
              sanitized INTEGER NOT NULL DEFAULT 1,
              published_event_id TEXT REFERENCES org_events(event_id),
              created_at TEXT NOT NULL
            );

            CREATE TRIGGER IF NOT EXISTS prevent_role_lineage_events_update
            BEFORE UPDATE ON role_lineage_events
            BEGIN
              SELECT RAISE(ABORT, 'organizational history is append-only; append a superseding event instead');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_role_lineage_events_delete
            BEFORE DELETE ON role_lineage_events
            BEGIN
              SELECT RAISE(ABORT, 'organizational history is append-only; append a superseding event instead');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_role_memory_bindings_update
            BEFORE UPDATE ON role_memory_bindings
            BEGIN
              SELECT RAISE(ABORT, 'organizational history is append-only; append a superseding event instead');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_role_memory_bindings_delete
            BEFORE DELETE ON role_memory_bindings
            BEGIN
              SELECT RAISE(ABORT, 'organizational history is append-only; append a superseding event instead');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_role_eval_results_update
            BEFORE UPDATE ON role_eval_results
            BEGIN
              SELECT RAISE(ABORT, 'organizational history is append-only; append a superseding event instead');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_role_eval_results_delete
            BEFORE DELETE ON role_eval_results
            BEGIN
              SELECT RAISE(ABORT, 'organizational history is append-only; append a superseding event instead');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_role_evolution_recommendations_update
            BEFORE UPDATE ON role_evolution_recommendations
            BEGIN
              SELECT RAISE(ABORT, 'organizational history is append-only; append a superseding event instead');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_role_evolution_recommendations_delete
            BEFORE DELETE ON role_evolution_recommendations
            BEGIN
              SELECT RAISE(ABORT, 'organizational history is append-only; append a superseding event instead');
            END;
            """
        )
        self.conn.execute("DROP TRIGGER IF EXISTS prevent_role_lineage_events_update")
        self.conn.execute("DROP TRIGGER IF EXISTS prevent_role_lineage_events_delete")
        self.ensure_column("work_graph_nodes", "acceptance_criteria", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("work_graph_nodes", "evidence_required", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("work_graph_nodes", "verifier_role", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("work_graph_nodes", "risk_level", "TEXT NOT NULL DEFAULT 'medium'")
        self.ensure_column("work_graph_nodes", "rollback_note", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("work_graph_nodes", "budget_note", "TEXT NOT NULL DEFAULT ''")
        self.ensure_column("work_graph_nodes", "captain_attention_estimate", "REAL NOT NULL DEFAULT 0")
        self.ensure_column("role_lineage_events", "product_slug", "TEXT")
        self.conn.execute(
            """
            UPDATE role_lineage_events
               SET product_slug = (
                 SELECT product_slug FROM org_events
                  WHERE org_events.event_id = role_lineage_events.event_id
               )
             WHERE product_slug IS NULL
            """
        )
        self.conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS prevent_role_lineage_events_update
            BEFORE UPDATE ON role_lineage_events
            BEGIN
              SELECT RAISE(ABORT, 'organizational history is append-only; append a superseding event instead');
            END;

            CREATE TRIGGER IF NOT EXISTS prevent_role_lineage_events_delete
            BEFORE DELETE ON role_lineage_events
            BEGIN
              SELECT RAISE(ABORT, 'organizational history is append-only; append a superseding event instead');
            END;
            """
        )
        self.conn.commit()

    def ensure_column(self, table: str, column: str, ddl: str) -> None:
        columns = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def append_event(
        self,
        event_type: str,
        product_slug: str,
        aggregate_type: str,
        aggregate_id: str,
        actor: str,
        payload: dict[str, Any],
        source: str = "cli",
        supersedes_event_id: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        # F3: allow caller (e.g. framework.events.emitter) to pass through its
        # own event_id so the Store ledger and the framework JSONL/Postgres
        # ledger share a single authoritative id. Default behavior unchanged:
        # if event_id is None we mint a fresh uuid4 here (matching pre-F3
        # callers like the org_runtime CLI).
        event = {
            "event_id": event_id or str(uuid.uuid4()),
            "event_type": event_type,
            "product_slug": product_slug,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "actor": actor,
            "source": source,
            "payload": payload,
            "supersedes_event_id": supersedes_event_id,
            "created_at": utc_now(),
        }
        self.conn.execute(
            """
            INSERT INTO org_events
              (event_id, event_type, product_slug, aggregate_type, aggregate_id,
               actor, source, payload_json, supersedes_event_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event_type,
                product_slug,
                aggregate_type,
                aggregate_id,
                actor,
                source,
                as_json(payload),
                supersedes_event_id,
                event["created_at"],
            ),
        )
        self.conn.commit()
        return event

    def rows(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        return [row_to_dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def row(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        result = self.conn.execute(sql, tuple(params)).fetchone()
        return row_to_dict(result) if result else None


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    for key in ("payload_json", "components_json", "capabilities_json", "metadata_json"):
        if key in out:
            out[key.replace("_json", "")] = json.loads(out.pop(key) or "{}")
    for key in ("sanitized", "passed"):
        if key in out:
            out[key] = bool(out[key])
    return out


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def product_arg(args: argparse.Namespace) -> str:
    return args.product_slug or os.environ.get("ORG_RUNTIME_PRODUCT", DEFAULT_PRODUCT)


def parse_capabilities(values: list[str] | None) -> list[str]:
    capabilities: list[str] = []
    for raw in values or []:
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("["):
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"capability JSON must be a string list: {exc}") from exc
            if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
                raise SystemExit("capability JSON must be a string list")
            capabilities.extend(decoded)
        else:
            capabilities.extend(part.strip() for part in raw.split(",") if part.strip())
    return sorted(dict.fromkeys(capabilities))


def role_key(product_slug: str, role_slug: str) -> str:
    return f"{product_slug}:{role_slug}"


def active_role(store: Store, product_slug: str, role_slug: str) -> dict[str, Any] | None:
    return store.row(
        """
        SELECT * FROM org_roles
         WHERE product_slug = ? AND role_slug = ? AND state = 'active'
        """,
        (product_slug, role_slug),
    )


def require_role(store: Store, product_slug: str, role_slug: str) -> dict[str, Any]:
    role = store.row(
        "SELECT * FROM org_roles WHERE product_slug = ? AND role_slug = ?",
        (product_slug, role_slug),
    )
    if not role:
        raise SystemExit(f"unknown role for {product_slug}: {role_slug}")
    return role


def require_active_role(store: Store, product_slug: str, role_slug: str) -> dict[str, Any]:
    role = require_role(store, product_slug, role_slug)
    if role["state"] != "active":
        raise SystemExit(f"role is not active for {product_slug}: {role_slug}")
    return role


def cmd_event_append(args: argparse.Namespace) -> None:
    store = Store()
    aggregate_id = args.aggregate_id or new_id(args.aggregate_type)
    event = store.append_event(
        args.type,
        product_arg(args),
        args.aggregate_type,
        aggregate_id,
        args.actor,
        parse_payload(args.payload),
        source=args.source,
        supersedes_event_id=args.supersedes_event_id,
    )
    print_json(event)


def cmd_event_list(args: argparse.Namespace) -> None:
    store = Store()
    rows = store.rows(
        """
        SELECT * FROM org_events
         WHERE product_slug = ?
         ORDER BY created_at DESC
         LIMIT ?
        """,
        (product_arg(args), args.limit),
    )
    for row in rows:
        print(json.dumps(row, sort_keys=True))


def cmd_outcome_propose(args: argparse.Namespace) -> None:
    store = Store()
    now = utc_now()
    outcome_id = args.outcome_id or new_id("outcome")
    payload = {
        "outcome_id": outcome_id,
        "title": args.title,
        "metric_name": args.metric_name,
        "target_value": args.target_value,
        "current_value": args.current_value,
        "unit": args.unit,
    }
    event = store.append_event(
        "outcome.proposed", product_arg(args), "captain_outcome", outcome_id, args.actor, payload
    )
    store.conn.execute(
        """
        INSERT INTO captain_outcomes
          (outcome_id, product_slug, title, metric_name, target_value, current_value,
           unit, state, proposed_by, proposed_event_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?, ?)
        """,
        (
            outcome_id,
            product_arg(args),
            args.title,
            args.metric_name,
            args.target_value,
            args.current_value,
            args.unit,
            args.actor,
            event["event_id"],
            now,
            now,
        ),
    )
    store.conn.commit()
    print_json({**payload, "state": "proposed", "event_id": event["event_id"]})


def cmd_outcome_ratify(args: argparse.Namespace) -> None:
    store = Store()
    outcome = store.row("SELECT * FROM captain_outcomes WHERE outcome_id = ?", (args.outcome_id,))
    if not outcome:
        raise SystemExit(f"unknown outcome_id: {args.outcome_id}")
    payload = {"outcome_id": args.outcome_id, "ratified_by": args.ratified_by, "note": args.note}
    event = store.append_event(
        "outcome.ratified",
        outcome["product_slug"],
        "captain_outcome",
        args.outcome_id,
        args.ratified_by,
        payload,
    )
    store.conn.execute(
        """
        UPDATE captain_outcomes
           SET state = 'ratified',
               ratified_by = ?,
               ratified_event_id = ?,
               updated_at = ?
         WHERE outcome_id = ?
        """,
        (args.ratified_by, event["event_id"], utc_now(), args.outcome_id),
    )
    store.conn.commit()
    print_json({**payload, "state": "ratified", "event_id": event["event_id"]})


def cmd_outcome_list(args: argparse.Namespace) -> None:
    store = Store()
    print_json(
        store.rows(
            "SELECT * FROM captain_outcomes WHERE product_slug = ? ORDER BY updated_at DESC",
            (product_arg(args),),
        )
    )


def cmd_mission_compile(args: argparse.Namespace) -> None:
    store = Store()
    outcome = store.row("SELECT * FROM captain_outcomes WHERE outcome_id = ?", (args.outcome_id,))
    if not outcome:
        raise SystemExit(f"unknown outcome_id: {args.outcome_id}")
    if outcome["state"] != "ratified":
        raise SystemExit("mission compilation requires a ratified outcome")
    require_active_role(store, outcome["product_slug"], args.owner_role)

    now = utc_now()
    mission_id = args.mission_id or new_id("mission")
    node_id = args.node_id or new_id("node")
    payload = {
        "mission_id": mission_id,
        "outcome_id": args.outcome_id,
        "title": args.title,
        "nodes": [{"node_id": node_id, "title": args.node_title, "owner_role": args.owner_role}],
    }
    event = store.append_event(
        "mission.compiled", outcome["product_slug"], "mission", mission_id, args.actor, payload
    )
    store.conn.execute(
        """
        INSERT INTO missions
          (mission_id, outcome_id, product_slug, title, state, compiled_event_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'compiled', ?, ?, ?)
        """,
        (mission_id, args.outcome_id, outcome["product_slug"], args.title, event["event_id"], now, now),
    )
    store.conn.execute(
        """
        INSERT INTO work_graph_nodes
          (node_id, mission_id, title, owner_role, status, created_at)
        VALUES (?, ?, ?, ?, 'queue', ?)
        """,
        (node_id, mission_id, args.node_title, args.owner_role, now),
    )
    store.conn.commit()
    print_json({**payload, "state": "compiled", "event_id": event["event_id"]})


MISSION_NODE_FIELDS = (
    "node_id",
    "title",
    "owner_role",
    "acceptance_criteria",
    "evidence_required",
    "verifier_role",
    "risk_level",
)


def load_plan_file(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text())
    except OSError as exc:
        raise SystemExit(f"cannot read plan file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"plan file must be JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("plan file must contain a JSON object")
    return data


def require_text(value: Any, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise SystemExit(f"mission plan node missing required field: {field}")
    return text


def normalized_plan_nodes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    raw_nodes = plan.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise SystemExit("mission plan requires a non-empty nodes array")
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_nodes, start=1):
        if not isinstance(raw, dict):
            raise SystemExit(f"mission plan node {index} must be an object")
        node = {field: require_text(raw.get(field), field) for field in MISSION_NODE_FIELDS}
        if node["node_id"] in seen:
            raise SystemExit(f"duplicate node_id in mission plan: {node['node_id']}")
        seen.add(node["node_id"])
        node["rollback_note"] = str(raw.get("rollback_note") or "").strip()
        node["budget_note"] = str(raw.get("budget_note") or "").strip()
        try:
            node["captain_attention_estimate"] = float(raw.get("captain_attention_estimate") or 0)
        except (TypeError, ValueError) as exc:
            raise SystemExit(f"captain_attention_estimate must be numeric for {node['node_id']}") from exc
        depends_on = raw.get("depends_on") or []
        if not isinstance(depends_on, list) or not all(isinstance(item, str) and item.strip() for item in depends_on):
            raise SystemExit(f"depends_on must be a string array for {node['node_id']}")
        node["depends_on"] = [item.strip() for item in depends_on]
        nodes.append(node)
    return nodes


def normalized_plan_edges(plan: dict[str, Any], nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    node_ids = {node["node_id"] for node in nodes}
    edges: list[dict[str, str]] = []
    for node in nodes:
        for upstream in node["depends_on"]:
            if upstream not in node_ids:
                raise SystemExit(f"depends_on references unknown node_id: {upstream}")
            edges.append({"from_node_id": upstream, "to_node_id": node["node_id"]})
    raw_edges = plan.get("edges") or []
    if not isinstance(raw_edges, list):
        raise SystemExit("mission plan edges must be an array")
    for raw in raw_edges:
        if not isinstance(raw, dict):
            raise SystemExit("mission plan edge must be an object")
        edge = {
            "from_node_id": require_text(raw.get("from_node_id"), "from_node_id"),
            "to_node_id": require_text(raw.get("to_node_id"), "to_node_id"),
        }
        if edge["from_node_id"] not in node_ids or edge["to_node_id"] not in node_ids:
            raise SystemExit(f"edge references unknown node_id: {edge}")
        edges.append(edge)
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for edge in edges:
        key = (edge["from_node_id"], edge["to_node_id"])
        if key not in seen:
            seen.add(key)
            deduped.append(edge)
    return deduped


def cmd_mission_compile_plan(args: argparse.Namespace) -> None:
    store = Store()
    outcome = store.row("SELECT * FROM captain_outcomes WHERE outcome_id = ?", (args.outcome_id,))
    if not outcome:
        raise SystemExit(f"unknown outcome_id: {args.outcome_id}")
    if outcome["state"] != "ratified":
        raise SystemExit("mission plan compilation requires a ratified outcome")
    plan = load_plan_file(args.plan_file)
    title = require_text(plan.get("title"), "title")
    nodes = normalized_plan_nodes(plan)
    edges = normalized_plan_edges(plan, nodes)
    for node in nodes:
        require_active_role(store, outcome["product_slug"], node["owner_role"])
        require_active_role(store, outcome["product_slug"], node["verifier_role"])

    now = utc_now()
    mission_id = str(plan.get("mission_id") or args.mission_id or new_id("mission")).strip()
    payload = {
        "mission_id": mission_id,
        "outcome_id": args.outcome_id,
        "title": title,
        "nodes": nodes,
        "edges": edges,
        "rollback_note": str(plan.get("rollback_note") or "").strip(),
        "budget_note": str(plan.get("budget_note") or "").strip(),
        "captain_attention_estimate": sum(float(node["captain_attention_estimate"]) for node in nodes),
    }
    event = store.append_event(
        "mission.plan_compiled", outcome["product_slug"], "mission", mission_id, args.actor, payload
    )
    store.conn.execute(
        """
        INSERT INTO missions
          (mission_id, outcome_id, product_slug, title, state, compiled_event_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'compiled', ?, ?, ?)
        """,
        (mission_id, args.outcome_id, outcome["product_slug"], title, event["event_id"], now, now),
    )
    for node in nodes:
        store.conn.execute(
            """
            INSERT INTO work_graph_nodes
              (node_id, mission_id, title, owner_role, acceptance_criteria,
               evidence_required, verifier_role, risk_level, rollback_note,
               budget_note, captain_attention_estimate, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queue', ?)
            """,
            (
                node["node_id"],
                mission_id,
                node["title"],
                node["owner_role"],
                node["acceptance_criteria"],
                node["evidence_required"],
                node["verifier_role"],
                node["risk_level"],
                node["rollback_note"],
                node["budget_note"],
                node["captain_attention_estimate"],
                now,
            ),
        )
    for edge in edges:
        store.conn.execute(
            """
            INSERT INTO work_graph_edges
              (edge_id, mission_id, from_node_id, to_node_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (new_id("edge"), mission_id, edge["from_node_id"], edge["to_node_id"], now),
        )
    store.conn.commit()
    print_json({**payload, "state": "compiled", "event_id": event["event_id"]})


def task_packet_for_node(mission: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    description = textwrap.dedent(
        f"""\
        mission_id: {mission['mission_id']}
        node_id: {node['node_id']}
        owner_role: {node['owner_role']}
        acceptance_criteria: {node['acceptance_criteria']}
        evidence_required: {node['evidence_required']}
        verifier_role: {node['verifier_role']}
        risk_level: {node['risk_level']}

        Mission: {mission['title']}
        Rollback: {node.get('rollback_note') or 'None specified'}
        Budget: {node.get('budget_note') or 'None specified'}
        Captain attention estimate: {node.get('captain_attention_estimate') or 0}
        """
    ).strip()
    return {
        "node_id": node["node_id"],
        "owner_role": node["owner_role"],
        "task_subject": node["title"],
        "task_description": description,
    }


def cmd_mission_native_task_packets(args: argparse.Namespace) -> None:
    store = Store()
    mission = store.row("SELECT * FROM missions WHERE mission_id = ?", (args.mission_id,))
    if not mission:
        raise SystemExit(f"unknown mission_id: {args.mission_id}")
    nodes = store.rows(
        "SELECT * FROM work_graph_nodes WHERE mission_id = ? ORDER BY created_at, node_id",
        (args.mission_id,),
    )
    print_json({"mission": mission, "task_packets": [task_packet_for_node(mission, node) for node in nodes]})


def cmd_mission_status(args: argparse.Namespace) -> None:
    store = Store()
    mission = store.row("SELECT * FROM missions WHERE mission_id = ?", (args.mission_id,))
    if not mission:
        raise SystemExit(f"unknown mission_id: {args.mission_id}")
    nodes = store.rows("SELECT * FROM work_graph_nodes WHERE mission_id = ? ORDER BY created_at", (args.mission_id,))
    edges = store.rows("SELECT * FROM work_graph_edges WHERE mission_id = ? ORDER BY created_at", (args.mission_id,))
    assignments = store.rows(
        """
        SELECT a.*, h.role_slug, h.hat_name, h.purpose
          FROM mission_role_assignments a
          JOIN role_hats h ON h.hat_id = a.hat_id
         WHERE a.mission_id = ?
         ORDER BY a.created_at
        """,
        (args.mission_id,),
    )
    print_json({"mission": mission, "nodes": nodes, "edges": edges, "assignments": assignments})


def cmd_mission_complete(args: argparse.Namespace) -> None:
    store = Store()
    node = store.row("SELECT * FROM work_graph_nodes WHERE node_id = ?", (args.node_id,))
    if not node:
        raise SystemExit(f"unknown node_id: {args.node_id}")
    mission = store.row("SELECT * FROM missions WHERE mission_id = ?", (node["mission_id"],))
    payload = {
        "node_id": args.node_id,
        "mission_id": node["mission_id"],
        "verified_value": args.verified_value,
        "verification_summary": args.verification_summary,
    }
    event = store.append_event(
        "work_graph.node_verified",
        mission["product_slug"],
        "work_graph_node",
        args.node_id,
        args.actor,
        payload,
    )
    now = utc_now()
    store.conn.execute(
        """
        UPDATE work_graph_nodes
           SET status = 'verified',
               verified_value = ?,
               verification_summary = ?,
               completion_event_id = ?,
               completed_at = ?
         WHERE node_id = ?
        """,
        (args.verified_value, args.verification_summary, event["event_id"], now, args.node_id),
    )
    remaining = store.row(
        "SELECT COUNT(*) AS n FROM work_graph_nodes WHERE mission_id = ? AND status != 'verified'",
        (node["mission_id"],),
    )["n"]
    if remaining == 0:
        store.conn.execute(
            "UPDATE missions SET state = 'verified', updated_at = ? WHERE mission_id = ?",
            (now, node["mission_id"]),
        )
    else:
        store.conn.execute(
            "UPDATE missions SET state = 'in_progress', updated_at = ? WHERE mission_id = ?",
            (now, node["mission_id"]),
        )
    store.conn.commit()
    print_json({**payload, "event_id": event["event_id"]})


def cmd_claude_tasks_list(args: argparse.Namespace) -> None:
    store = Store()
    params: list[Any] = [product_arg(args)]
    where = "WHERE product_slug = ?"
    if args.status:
        where += " AND status = ?"
        params.append(args.status)
    params.append(args.limit)
    print_json(
        store.rows(
            f"""
            SELECT * FROM claude_native_tasks
             {where}
             ORDER BY updated_at DESC, task_id
             LIMIT ?
            """,
            params,
        )
    )


def cmd_claude_tasks_show(args: argparse.Namespace) -> None:
    store = Store()
    product_slug = product_arg(args)
    task = store.row(
        "SELECT * FROM claude_native_tasks WHERE product_slug = ? AND task_id = ?",
        (product_slug, args.task_id),
    )
    if not task:
        raise SystemExit(f"unknown Claude native task for {product_slug}: {args.task_id}")
    events = store.rows(
        """
        SELECT * FROM org_events
         WHERE product_slug = ?
           AND aggregate_type = 'claude_native_task'
           AND aggregate_id = ?
         ORDER BY created_at
        """,
        (product_slug, args.task_id),
    )
    print_json({"task": task, "events": events})


# ---------------------------------------------------------------------------
# Capability gaps (self-extension loop) — delegates to framework.learning
# ---------------------------------------------------------------------------

def _capability_gaps():
    """Import the framework capability_gaps module (repo root on sys.path)."""
    import sys as _sys
    from pathlib import Path as _Path
    repo_root = str(_Path(__file__).resolve().parents[3])
    if repo_root not in _sys.path:
        _sys.path.insert(0, repo_root)
    from framework.learning import capability_gaps as cg  # noqa
    return cg


def cmd_gaps_list(args: argparse.Namespace) -> None:
    cg = _capability_gaps()
    os.environ.setdefault("CABINET_PRODUCT_SLUG", product_arg(args))
    gaps = cg.project_gaps(product_slug=product_arg(args))
    if getattr(args, "status", None):
        gaps = [g for g in gaps if g["status"] == args.status]
    print_json(gaps)


def cmd_gaps_show(args: argparse.Namespace) -> None:
    cg = _capability_gaps()
    for g in cg.project_gaps(product_slug=product_arg(args)):
        if g["gap_id"] == args.gap_id:
            print_json(g)
            return
    raise SystemExit(f"unknown capability gap: {args.gap_id}")


def cmd_gaps_propose(args: argparse.Namespace) -> None:
    cg = _capability_gaps()
    touches = [t.strip() for t in (args.touches or "").split(",") if t.strip()]
    ev = cg.propose_gap(args.gap_id, summary=args.summary, approach=args.approach,
                        touches=touches, actor=args.actor, product_slug=product_arg(args))
    print_json({"proposed": args.gap_id, "event_id": ev.get("id")})


def cmd_gaps_approve(args: argparse.Namespace) -> None:
    cg = _capability_gaps()
    ev = cg.approve_gap(args.gap_id, actor=args.actor, note=args.note or "",
                        product_slug=product_arg(args))
    print_json({"approved": args.gap_id, "event_id": ev.get("id")})


def cmd_gaps_decline(args: argparse.Namespace) -> None:
    cg = _capability_gaps()
    ev = cg.decline_gap(args.gap_id, reason=args.reason or "", actor=args.actor,
                        product_slug=product_arg(args))
    print_json({"declined": args.gap_id, "event_id": ev.get("id")})


def cmd_gaps_resolve(args: argparse.Namespace) -> None:
    cg = _capability_gaps()
    ev = cg.resolve_gap(args.gap_id, resolution=args.resolution, actor=args.actor,
                        product_slug=product_arg(args))
    print_json({"resolved": args.gap_id, "resolution": args.resolution, "event_id": ev.get("id")})


def table_exists(store: Store, table: str) -> bool:
    row = store.row("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))
    return row is not None


def cmd_tasks_drift_report(args: argparse.Namespace) -> None:
    store = Store()
    product_slug = product_arg(args)
    legacy_tasks = []
    if table_exists(store, "officer_tasks"):
        legacy_tasks = store.rows(
            """
            SELECT id, title, status, officer_slug, context_slug, linked_kind, linked_id
              FROM officer_tasks
             WHERE context_slug = ?
             ORDER BY id DESC
             LIMIT ?
            """,
            (product_slug, args.limit),
        )
    nodes = store.rows(
        """
        SELECT n.node_id, n.title, n.owner_role, n.status, m.mission_id
          FROM work_graph_nodes n
          JOIN missions m ON m.mission_id = n.mission_id
         WHERE m.product_slug = ?
         ORDER BY n.created_at DESC, n.node_id
         LIMIT ?
        """,
        (product_slug, args.limit),
    )
    claude_tasks = store.rows(
        """
        SELECT task_id, task_subject, status, node_id, mission_id, owner_role
          FROM claude_native_tasks
         WHERE product_slug = ?
         ORDER BY updated_at DESC, task_id
         LIMIT ?
        """,
        (product_slug, args.limit),
    )
    node_ids = {node["node_id"] for node in nodes}
    claude_node_ids = {task["node_id"] for task in claude_tasks if task.get("node_id")}
    legacy_node_links = {
        str(task.get("linked_id"))
        for task in legacy_tasks
        if task.get("linked_kind") == "work_graph_node" and task.get("linked_id")
    }
    print_json(
        {
            "product_slug": product_slug,
            "legacy_tasks_table_present": table_exists(store, "officer_tasks"),
            "counts": {
                "legacy_tasks": len(legacy_tasks),
                "work_graph_nodes": len(nodes),
                "claude_native_tasks": len(claude_tasks),
            },
            "work_nodes_without_claude_task": sorted(node_ids - claude_node_ids),
            "work_nodes_without_legacy_task_link": sorted(node_ids - legacy_node_links),
            "claude_tasks_without_work_node": [
                task for task in claude_tasks if not task.get("node_id") or task.get("node_id") not in node_ids
            ],
            "legacy_tasks_without_work_node_link": [
                task
                for task in legacy_tasks
                if task.get("linked_kind") != "work_graph_node" or str(task.get("linked_id")) not in node_ids
            ],
        }
    )


def insert_role_lineage(
    store: Store,
    product_slug: str,
    role_slug: str,
    event_id: str,
    event_kind: str,
    note: str,
    hat_id: str | None = None,
) -> None:
    store.conn.execute(
        """
        INSERT INTO role_lineage_events
          (lineage_id, product_slug, role_slug, hat_id, event_id, event_kind, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (new_id("lineage"), product_slug, role_slug, hat_id, event_id, event_kind, note, utc_now()),
    )


def cmd_roles_define(args: argparse.Namespace) -> None:
    store = Store()
    product_slug = product_arg(args)
    if store.row("SELECT 1 FROM org_roles WHERE product_slug = ? AND role_slug = ?", (product_slug, args.role)):
        raise SystemExit(f"role already defined for {product_slug}: {args.role}")

    now = utc_now()
    capabilities = parse_capabilities(args.capability)
    payload = {
        "product_slug": product_slug,
        "role_slug": args.role,
        "role_name": args.name,
        "charter": args.charter,
        "current_focus": args.current_focus,
        "authority_level": args.authority_level,
        "capabilities": capabilities,
        "state": args.state,
        "version": 1,
        "officer_session_slug": args.officer_session_slug,
    }
    event = store.append_event(
        "role.defined",
        product_slug,
        "org_role",
        role_key(product_slug, args.role),
        args.actor,
        payload,
    )
    store.conn.execute(
        """
        INSERT INTO org_roles
          (product_slug, role_slug, role_name, charter, current_focus, authority_level,
           capabilities_json, state, version, officer_session_slug, defined_event_id,
           latest_event_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
        """,
        (
            product_slug,
            args.role,
            args.name,
            args.charter,
            args.current_focus,
            args.authority_level,
            as_json(capabilities),
            args.state,
            args.officer_session_slug,
            event["event_id"],
            event["event_id"],
            now,
            now,
        ),
    )
    insert_role_lineage(
        store,
        product_slug,
        args.role,
        event["event_id"],
        "role_defined",
        f"Defined role: {args.name}",
    )
    store.conn.commit()
    print_json({**payload, "event_id": event["event_id"]})


def cmd_roles_list(args: argparse.Namespace) -> None:
    store = Store()
    print_json(
        store.rows(
            "SELECT * FROM org_roles WHERE product_slug = ? ORDER BY state, role_slug",
            (product_arg(args),),
        )
    )


def cmd_roles_show(args: argparse.Namespace) -> None:
    store = Store()
    product_slug = product_arg(args)
    role = require_role(store, product_slug, args.role)
    memory = store.rows(
        """
        SELECT * FROM role_memory_bindings
         WHERE product_slug = ? AND role_slug = ?
         ORDER BY created_at
        """,
        (product_slug, args.role),
    )
    evals = store.rows(
        """
        SELECT * FROM role_eval_results
         WHERE product_slug = ? AND role_slug = ?
         ORDER BY created_at
        """,
        (product_slug, args.role),
    )
    recommendations = store.rows(
        """
        SELECT * FROM role_evolution_recommendations
         WHERE product_slug = ? AND role_slug = ?
         ORDER BY created_at
        """,
        (product_slug, args.role),
    )
    lineage = store.rows(
        """
        SELECT l.*, h.hat_name, h.purpose
          FROM role_lineage_events l
          LEFT JOIN role_hats h ON h.hat_id = l.hat_id
         WHERE l.product_slug = ? AND l.role_slug = ?
         ORDER BY l.created_at
        """,
        (product_slug, args.role),
    )
    print_json(
        {
            "role": role,
            "memory_bindings": memory,
            "eval_results": evals,
            "evolution_recommendations": recommendations,
            "lineage": lineage,
        }
    )


def cmd_roles_bind_memory(args: argparse.Namespace) -> None:
    store = Store()
    product_slug = product_arg(args)
    require_active_role(store, product_slug, args.role)
    memory_path = args.memory_path.strip()
    path = Path(memory_path)
    if not path.is_absolute():
        path = repo_root() / path
    if not path.exists():
        raise SystemExit(f"memory path does not exist: {memory_path}")

    binding_id = args.binding_id or new_id("memory")
    payload = {
        "binding_id": binding_id,
        "product_slug": product_slug,
        "role_slug": args.role,
        "memory_path": memory_path,
        "memory_kind": args.memory_kind,
    }
    event = store.append_event(
        "role.memory_bound",
        product_slug,
        "role_memory_binding",
        binding_id,
        args.actor,
        payload,
    )
    store.conn.execute(
        """
        INSERT INTO role_memory_bindings
          (binding_id, product_slug, role_slug, memory_path, memory_kind, bound_event_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (binding_id, product_slug, args.role, memory_path, args.memory_kind, event["event_id"], utc_now()),
    )
    insert_role_lineage(
        store,
        product_slug,
        args.role,
        event["event_id"],
        "memory_bound",
        f"Bound memory path: {memory_path}",
    )
    store.conn.commit()
    print_json({**payload, "event_id": event["event_id"]})


def cmd_roles_record_eval(args: argparse.Namespace) -> None:
    store = Store()
    product_slug = product_arg(args)
    require_active_role(store, product_slug, args.role)
    if args.score < 0 or args.score > 1:
        raise SystemExit("score must be between 0 and 1")
    if args.mission_id:
        mission = store.row("SELECT * FROM missions WHERE mission_id = ?", (args.mission_id,))
        if not mission or mission["product_slug"] != product_slug:
            raise SystemExit(f"unknown mission_id for {product_slug}: {args.mission_id}")
    if args.hat_id:
        hat = store.row("SELECT * FROM role_hats WHERE hat_id = ?", (args.hat_id,))
        if not hat or hat["product_slug"] != product_slug or hat["role_slug"] != args.role:
            raise SystemExit(f"unknown hat_id for role {args.role}: {args.hat_id}")

    eval_id = args.eval_id or new_id("eval")
    passed = args.passed
    if passed is None:
        passed = args.score >= 0.8
    payload = {
        "eval_id": eval_id,
        "product_slug": product_slug,
        "role_slug": args.role,
        "mission_id": args.mission_id,
        "hat_id": args.hat_id,
        "eval_name": args.eval_name,
        "score": args.score,
        "passed": bool(passed),
        "evidence": args.evidence,
    }
    event = store.append_event(
        "role.eval_recorded",
        product_slug,
        "role_eval_result",
        eval_id,
        args.actor,
        payload,
    )
    store.conn.execute(
        """
        INSERT INTO role_eval_results
          (eval_id, product_slug, role_slug, mission_id, hat_id, eval_name, score,
           passed, evidence, recorded_event_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            eval_id,
            product_slug,
            args.role,
            args.mission_id,
            args.hat_id,
            args.eval_name,
            args.score,
            1 if passed else 0,
            args.evidence,
            event["event_id"],
            utc_now(),
        ),
    )
    insert_role_lineage(
        store,
        product_slug,
        args.role,
        event["event_id"],
        "eval_recorded",
        f"Recorded role eval {args.eval_name}: score={args.score}",
        hat_id=args.hat_id,
    )
    store.conn.commit()
    print_json({**payload, "event_id": event["event_id"]})


def active_mission_assignment_count(store: Store, product_slug: str, role_slug: str) -> int:
    row = store.row(
        """
        SELECT COUNT(*) AS n
          FROM mission_role_assignments a
          JOIN missions m ON m.mission_id = a.mission_id
         WHERE m.product_slug = ?
           AND a.assigned_to_role = ?
           AND m.state IN ('compiled', 'in_progress')
        """,
        (product_slug, role_slug),
    )
    return int(row["n"] or 0)


def role_recommendation(store: Store, product_slug: str, role_slug: str) -> tuple[str, str | None, str]:
    latest = store.rows(
        """
        SELECT * FROM role_eval_results
         WHERE product_slug = ? AND role_slug = ?
         ORDER BY created_at DESC, eval_id DESC
         LIMIT 3
        """,
        (product_slug, role_slug),
    )
    if len(latest) == 3:
        if all(not item["passed"] for item in latest) and active_mission_assignment_count(store, product_slug, role_slug) == 0:
            return (
                "retire_role_review",
                None,
                "Latest 3 evals failed and the role has no active mission assignments.",
            )
        avg_score = sum(float(item["score"]) for item in latest) / 3
        if avg_score < 0.6:
            return ("adjust_charter", None, f"Latest 3 evals average {avg_score:.2f}, below 0.60.")

    promote = store.row(
        """
        SELECT hat_id, COUNT(*) AS n
          FROM role_eval_results
         WHERE product_slug = ?
           AND role_slug = ?
           AND hat_id IS NOT NULL
           AND passed = 1
           AND score >= 0.8
         GROUP BY hat_id
        HAVING COUNT(*) >= 2
         ORDER BY n DESC, hat_id
         LIMIT 1
        """,
        (product_slug, role_slug),
    )
    if promote:
        return (
            "promote_hat_to_capability",
            promote["hat_id"],
            f"Hat {promote['hat_id']} has {promote['n']} passing evals with score >= 0.8.",
        )

    return ("continue_current_role", None, "No deterministic promote, adjust, or retire-review condition was met.")


def cmd_roles_recommend(args: argparse.Namespace) -> None:
    store = Store()
    product_slug = product_arg(args)
    require_active_role(store, product_slug, args.role)
    recommendation_type, hat_id, basis = role_recommendation(store, product_slug, args.role)
    recommendation_id = args.recommendation_id or new_id("recommendation")
    payload = {
        "recommendation_id": recommendation_id,
        "product_slug": product_slug,
        "role_slug": args.role,
        "recommendation_type": recommendation_type,
        "hat_id": hat_id,
        "basis": basis,
    }
    event_type = "role.retire_review_recommended" if recommendation_type == "retire_role_review" else "role.evolution_recommended"
    event = store.append_event(
        event_type,
        product_slug,
        "role_evolution_recommendation",
        recommendation_id,
        args.actor,
        payload,
    )
    store.conn.execute(
        """
        INSERT INTO role_evolution_recommendations
          (recommendation_id, product_slug, role_slug, recommendation_type,
           hat_id, basis, recommended_event_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recommendation_id,
            product_slug,
            args.role,
            recommendation_type,
            hat_id,
            basis,
            event["event_id"],
            utc_now(),
        ),
    )
    insert_role_lineage(
        store,
        product_slug,
        args.role,
        event["event_id"],
        "retire_review_recommended" if recommendation_type == "retire_role_review" else "evolution_recommended",
        basis,
        hat_id=hat_id,
    )
    store.conn.commit()
    print_json({**payload, "event_id": event["event_id"]})


def role_evolve_event_type(changed_fields: set[str]) -> str:
    if changed_fields == {"charter"}:
        return "role.charter_changed"
    if changed_fields == {"current_focus"}:
        return "role.focus_changed"
    if changed_fields == {"capabilities"}:
        return "role.capability_changed"
    if changed_fields == {"authority_level"}:
        return "role.authority_changed"
    return "role.evolved"


def cmd_roles_evolve(args: argparse.Namespace) -> None:
    store = Store()
    product_slug = product_arg(args)
    role = require_active_role(store, product_slug, args.role)
    if not args.ratified_by or args.ratified_by.lower() != "captain":
        raise SystemExit("role evolution requires --ratified-by captain")

    capabilities = list(role["capabilities"])
    next_values = {
        "charter": role["charter"],
        "current_focus": role["current_focus"],
        "authority_level": role["authority_level"],
        "capabilities": capabilities,
    }
    if args.charter is not None:
        next_values["charter"] = args.charter
    if args.current_focus is not None:
        next_values["current_focus"] = args.current_focus
    if args.authority_level is not None:
        next_values["authority_level"] = args.authority_level
    added_capabilities = parse_capabilities(args.add_capability)
    if added_capabilities:
        next_values["capabilities"] = sorted(dict.fromkeys([*capabilities, *added_capabilities]))

    changes: dict[str, dict[str, Any]] = {}
    for field, next_value in next_values.items():
        if role[field] != next_value:
            changes[field] = {"from": role[field], "to": next_value}
    if not changes:
        raise SystemExit("role evolution requires at least one changed charter, focus, authority, or capability")

    new_version = int(role["version"]) + 1
    payload = {
        "product_slug": product_slug,
        "role_slug": args.role,
        "old_version": role["version"],
        "new_version": new_version,
        "ratified_by": args.ratified_by,
        "approval_note": args.approval_note,
        "changes": changes,
    }
    event = store.append_event(
        role_evolve_event_type(set(changes)),
        product_slug,
        "org_role",
        role_key(product_slug, args.role),
        args.actor,
        payload,
    )
    now = utc_now()
    store.conn.execute(
        """
        UPDATE org_roles
           SET charter = ?,
               current_focus = ?,
               authority_level = ?,
               capabilities_json = ?,
               version = ?,
               latest_event_id = ?,
               updated_at = ?
         WHERE product_slug = ? AND role_slug = ?
        """,
        (
            next_values["charter"],
            next_values["current_focus"],
            next_values["authority_level"],
            as_json(next_values["capabilities"]),
            new_version,
            event["event_id"],
            now,
            product_slug,
            args.role,
        ),
    )
    insert_role_lineage(
        store,
        product_slug,
        args.role,
        event["event_id"],
        "role_evolved",
        f"Captain-ratified role evolution to version {new_version}",
    )
    store.conn.commit()
    print_json({**payload, "event_id": event["event_id"]})


def cmd_roles_assign_hat(args: argparse.Namespace) -> None:
    store = Store()
    mission = store.row("SELECT * FROM missions WHERE mission_id = ?", (args.mission_id,))
    if not mission:
        raise SystemExit(f"unknown mission_id: {args.mission_id}")
    require_active_role(store, mission["product_slug"], args.role)
    if args.node_id:
        node = store.row("SELECT * FROM work_graph_nodes WHERE node_id = ?", (args.node_id,))
        if not node:
            raise SystemExit(f"unknown node_id: {args.node_id}")
        if node["mission_id"] != args.mission_id:
            raise SystemExit(f"node_id {args.node_id} does not belong to mission_id {args.mission_id}")

    now = utc_now()
    hat = store.row(
        """
        SELECT * FROM role_hats
         WHERE product_slug = ? AND role_slug = ? AND hat_name = ? AND state = 'active'
        """,
        (mission["product_slug"], args.role, args.hat_name),
    )
    if hat:
        hat_id = hat["hat_id"]
        hat_event_id = hat["created_event_id"]
    else:
        hat_id = args.hat_id or new_id("hat")
        hat_payload = {"hat_id": hat_id, "role_slug": args.role, "hat_name": args.hat_name, "purpose": args.purpose}
        hat_event = store.append_event(
            "role_hat.created", mission["product_slug"], "role_hat", hat_id, args.actor, hat_payload
        )
        hat_event_id = hat_event["event_id"]
        store.conn.execute(
            """
            INSERT INTO role_hats
              (hat_id, product_slug, role_slug, hat_name, purpose, state, created_event_id, created_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (hat_id, mission["product_slug"], args.role, args.hat_name, args.purpose, hat_event_id, now),
        )
        insert_role_lineage(
            store,
            mission["product_slug"],
            args.role,
            hat_event_id,
            "hat_created",
            f"Created role hat: {args.hat_name}",
            hat_id=hat_id,
        )

    assignment_id = args.assignment_id or new_id("assignment")
    payload = {
        "assignment_id": assignment_id,
        "mission_id": args.mission_id,
        "hat_id": hat_id,
        "node_id": args.node_id,
        "assigned_to_role": args.role,
    }
    event = store.append_event(
        "mission_role.assigned",
        mission["product_slug"],
        "mission_role_assignment",
        assignment_id,
        args.actor,
        payload,
    )
    store.conn.execute(
        """
        INSERT INTO mission_role_assignments
          (assignment_id, mission_id, hat_id, node_id, assigned_to_role, assignment_event_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (assignment_id, args.mission_id, hat_id, args.node_id, args.role, event["event_id"], now),
    )
    insert_role_lineage(
        store,
        mission["product_slug"],
        args.role,
        event["event_id"],
        "mission_assigned",
        f"Assigned to mission {args.mission_id}",
        hat_id=hat_id,
    )
    store.conn.commit()
    print_json({**payload, "hat_created_event_id": hat_event_id, "event_id": event["event_id"]})


def cmd_roles_show_lineage(args: argparse.Namespace) -> None:
    store = Store()
    product_slug = product_arg(args)
    require_role(store, product_slug, args.role)
    print_json(
        store.rows(
            """
            SELECT l.*, h.hat_name, h.purpose
              FROM role_lineage_events l
              LEFT JOIN role_hats h ON h.hat_id = l.hat_id
             WHERE l.product_slug = ? AND l.role_slug = ?
             ORDER BY l.created_at
            """,
            (product_slug, args.role),
        )
    )


def burden_index(args: argparse.Namespace) -> float:
    return (
        1.0
        + (args.captain_attention_minutes / 30.0)
        + (args.captain_decisions * 0.5)
        + (args.spend_usd / 25.0)
        + (args.policy_violations * 2.0)
        + (args.verification_debt * 1.5)
        + (args.safety_debt * 3.0)
    )


def verified_value_for_week(store: Store, product_slug: str, week_start: str) -> float:
    start = dt.date.fromisoformat(week_start)
    end = start + dt.timedelta(days=7)
    row = store.row(
        """
        SELECT COALESCE(SUM(n.verified_value), 0) AS total
          FROM work_graph_nodes n
          JOIN missions m ON m.mission_id = n.mission_id
         WHERE m.product_slug = ?
           AND n.status = 'verified'
           AND n.completed_at >= ?
           AND n.completed_at < ?
        """,
        (product_slug, start.isoformat(), end.isoformat()),
    )
    return float(row["total"] or 0)


def ovi_payload(args: argparse.Namespace, store: Store) -> dict[str, Any]:
    product_slug = product_arg(args)
    verified_value = (
        args.verified_value
        if args.verified_value is not None
        else verified_value_for_week(store, product_slug, args.week_start)
    )
    burden = burden_index(args)
    components = {
        "captain_attention_minutes": args.captain_attention_minutes,
        "captain_decisions": args.captain_decisions,
        "spend_usd": args.spend_usd,
        "policy_violations": args.policy_violations,
        "verification_debt": args.verification_debt,
        "safety_debt": args.safety_debt,
    }
    return {
        "product_slug": product_slug,
        "week_start": args.week_start,
        "verified_outcome_value": verified_value,
        "burden_index": burden,
        "ovi": verified_value / burden,
        "components": components,
    }


def cmd_ovi_compute(args: argparse.Namespace) -> None:
    store = Store()
    print_json(ovi_payload(args, store))


def cmd_ovi_publish(args: argparse.Namespace) -> None:
    store = Store()
    payload = ovi_payload(args, store)
    prior = store.row(
        """
        SELECT ovi FROM ovi_weeks
         WHERE product_slug = ? AND week_start < ?
         ORDER BY week_start DESC
         LIMIT 1
        """,
        (payload["product_slug"], args.week_start),
    )
    trend = None if prior is None else payload["ovi"] - float(prior["ovi"])
    payload["trend_vs_prior"] = trend
    event = store.append_event(
        "ovi.week_published",
        payload["product_slug"],
        "ovi_week",
        args.week_start,
        args.actor,
        payload,
    )
    store.conn.execute(
        """
        INSERT INTO ovi_weeks
          (product_slug, week_start, verified_outcome_value, burden_index, ovi,
           trend_vs_prior, components_json, published_event_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(product_slug, week_start) DO UPDATE SET
          verified_outcome_value = excluded.verified_outcome_value,
          burden_index = excluded.burden_index,
          ovi = excluded.ovi,
          trend_vs_prior = excluded.trend_vs_prior,
          components_json = excluded.components_json,
          published_event_id = excluded.published_event_id
        """,
        (
            payload["product_slug"],
            args.week_start,
            payload["verified_outcome_value"],
            payload["burden_index"],
            payload["ovi"],
            trend,
            as_json(payload["components"]),
            event["event_id"],
            utc_now(),
        ),
    )
    store.conn.commit()
    print_json({**payload, "event_id": event["event_id"]})


SECRET_RE = re.compile(r"\b(?:sk|pk|ghp|xox[baprs]|AIza)[A-Za-z0-9_\-]{8,}\b")
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(r"https?://[^\s)]+")
SENSED_RE = re.compile(r"\bSensed\b", re.IGNORECASE)


def sanitize_digest(raw: str) -> str:
    text = raw
    text = SECRET_RE.sub("[REDACTED_SECRET]", text)
    text = UUID_RE.sub("[REDACTED_ID]", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = URL_RE.sub("[REDACTED_URL]", text)
    text = SENSED_RE.sub("[legacy-product]", text)
    return text


def cmd_digest_publish(args: argparse.Namespace) -> None:
    store = Store()
    raw_content = args.content
    if args.content_file:
        raw_content = Path(args.content_file).read_text()
    if raw_content is None:
        raise SystemExit("provide --content or --content-file")
    content = sanitize_digest(raw_content)
    digest_id = args.digest_id or new_id("digest")
    payload = {
        "digest_id": digest_id,
        "week_start": args.week_start,
        "title": args.title,
        "content": content,
        "sanitized": True,
    }
    event = store.append_event(
        "learning_digest.published",
        product_arg(args),
        "learning_digest",
        digest_id,
        args.actor,
        payload,
    )
    store.conn.execute(
        """
        INSERT INTO learning_digests
          (digest_id, product_slug, week_start, title, content, sanitized, published_event_id, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (digest_id, product_arg(args), args.week_start, args.title, content, event["event_id"], utc_now()),
    )
    store.conn.commit()

    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_slug = re.sub(r"[^a-z0-9-]+", "-", args.title.lower()).strip("-") or digest_id
        out_path = out_dir / f"{args.week_start}-{safe_slug}.md"
        out_path.write_text(f"# {args.title}\n\n{content}\n")
        payload["path"] = str(out_path)
    print_json({**payload, "event_id": event["event_id"]})


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--product-slug", default=None)


def add_ovi_component_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--week-start", required=True)
    parser.add_argument("--verified-value", type=float)
    parser.add_argument("--captain-attention-minutes", type=float, default=0)
    parser.add_argument("--captain-decisions", type=float, default=0)
    parser.add_argument("--spend-usd", type=float, default=0)
    parser.add_argument("--policy-violations", type=float, default=0)
    parser.add_argument("--verification-debt", type=float, default=0)
    parser.add_argument("--safety-debt", type=float, default=0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="org-runtime",
        description="Outcome-to-OVI organization runtime vertical slice.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Examples:
              org-runtime.py outcomes propose --title "Improve autonomy" --metric-name verified_value --target-value 10
              org-runtime.py outcomes ratify outcome_abc --ratified-by captain
              org-runtime.py missions compile outcome_abc --title "Autonomy slice" --node-title "Publish OVI"
            """
        ),
    )
    sub = parser.add_subparsers(dest="area", required=True)

    org_event = sub.add_parser("org-event")
    org_event_sub = org_event.add_subparsers(dest="cmd", required=True)
    p = org_event_sub.add_parser("append")
    add_common(p)
    p.add_argument("--type", required=True)
    p.add_argument("--aggregate-type", required=True)
    p.add_argument("--aggregate-id")
    p.add_argument("--actor", default="system")
    p.add_argument("--source", default="cli")
    p.add_argument("--payload")
    p.add_argument("--supersedes-event-id")
    p.set_defaults(func=cmd_event_append)
    p = org_event_sub.add_parser("list")
    add_common(p)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_event_list)

    outcomes = sub.add_parser("outcomes")
    outcomes_sub = outcomes.add_subparsers(dest="cmd", required=True)
    p = outcomes_sub.add_parser("propose")
    add_common(p)
    p.add_argument("--outcome-id")
    p.add_argument("--title", required=True)
    p.add_argument("--metric-name", required=True)
    p.add_argument("--target-value", type=float, required=True)
    p.add_argument("--current-value", type=float, default=0)
    p.add_argument("--unit", default="points")
    p.add_argument("--actor", default="cos")
    p.set_defaults(func=cmd_outcome_propose)
    p = outcomes_sub.add_parser("ratify")
    p.add_argument("outcome_id")
    p.add_argument("--ratified-by", default="captain")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_outcome_ratify)
    p = outcomes_sub.add_parser("list")
    add_common(p)
    p.set_defaults(func=cmd_outcome_list)

    missions = sub.add_parser("missions")
    missions_sub = missions.add_subparsers(dest="cmd", required=True)
    p = missions_sub.add_parser("compile")
    p.add_argument("outcome_id")
    p.add_argument("--mission-id")
    p.add_argument("--node-id")
    p.add_argument("--title", required=True)
    p.add_argument("--node-title", required=True)
    p.add_argument("--owner-role", default="cos")
    p.add_argument("--actor", default="cos")
    p.set_defaults(func=cmd_mission_compile)
    p = missions_sub.add_parser("compile-plan")
    p.add_argument("outcome_id")
    p.add_argument("--plan-file", required=True)
    p.add_argument("--mission-id")
    p.add_argument("--actor", default="cos")
    p.set_defaults(func=cmd_mission_compile_plan)
    p = missions_sub.add_parser("status")
    p.add_argument("mission_id")
    p.set_defaults(func=cmd_mission_status)
    p = missions_sub.add_parser("native-task-packets")
    p.add_argument("mission_id")
    p.set_defaults(func=cmd_mission_native_task_packets)
    p = missions_sub.add_parser("complete")
    p.add_argument("node_id")
    p.add_argument("--verified-value", type=float, required=True)
    p.add_argument("--verification-summary", required=True)
    p.add_argument("--actor", default="cos")
    p.set_defaults(func=cmd_mission_complete)

    claude_tasks = sub.add_parser("claude-tasks")
    claude_tasks_sub = claude_tasks.add_subparsers(dest="cmd", required=True)
    p = claude_tasks_sub.add_parser("list")
    add_common(p)
    p.add_argument("--status", choices=("created", "completed"))
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_claude_tasks_list)
    p = claude_tasks_sub.add_parser("show")
    add_common(p)
    p.add_argument("task_id")
    p.set_defaults(func=cmd_claude_tasks_show)

    tasks = sub.add_parser("tasks")
    tasks_sub = tasks.add_subparsers(dest="cmd", required=True)
    p = tasks_sub.add_parser("drift-report")
    add_common(p)
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(func=cmd_tasks_drift_report)

    gaps = sub.add_parser("gaps")
    gaps_sub = gaps.add_subparsers(dest="cmd", required=True)
    p = gaps_sub.add_parser("list")
    add_common(p)
    p.add_argument("--status")
    p.add_argument("--json", action="store_true", help="(output is always JSON; flag accepted for callers)")
    p.set_defaults(func=cmd_gaps_list)
    p = gaps_sub.add_parser("show")
    add_common(p)
    p.add_argument("gap_id")
    p.set_defaults(func=cmd_gaps_show)
    p = gaps_sub.add_parser("propose")
    add_common(p)
    p.add_argument("gap_id")
    p.add_argument("--summary", required=True)
    p.add_argument("--approach", required=True)
    p.add_argument("--touches", default="")
    p.add_argument("--actor", default="cabinet")
    p.set_defaults(func=cmd_gaps_propose)
    p = gaps_sub.add_parser("approve")
    add_common(p)
    p.add_argument("gap_id")
    p.add_argument("--note", default="")
    p.add_argument("--actor", default="captain")
    p.set_defaults(func=cmd_gaps_approve)
    p = gaps_sub.add_parser("decline")
    add_common(p)
    p.add_argument("gap_id")
    p.add_argument("--reason", default="")
    p.add_argument("--actor", default="captain")
    p.set_defaults(func=cmd_gaps_decline)
    p = gaps_sub.add_parser("resolve")
    add_common(p)
    p.add_argument("gap_id")
    p.add_argument("--resolution", required=True)
    p.add_argument("--actor", default="cabinet")
    p.set_defaults(func=cmd_gaps_resolve)

    roles = sub.add_parser("roles")
    roles_sub = roles.add_subparsers(dest="cmd", required=True)
    p = roles_sub.add_parser("define")
    add_common(p)
    p.add_argument("--role", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--charter", required=True)
    p.add_argument("--current-focus", default="")
    p.add_argument("--authority-level", default="mission_executor")
    p.add_argument("--capability", action="append")
    p.add_argument("--state", choices=("active", "inactive"), default="active")
    p.add_argument("--officer-session-slug")
    p.add_argument("--actor", default="cos")
    p.set_defaults(func=cmd_roles_define)
    p = roles_sub.add_parser("list")
    add_common(p)
    p.set_defaults(func=cmd_roles_list)
    p = roles_sub.add_parser("show")
    add_common(p)
    p.add_argument("--role", required=True)
    p.set_defaults(func=cmd_roles_show)
    p = roles_sub.add_parser("bind-memory")
    add_common(p)
    p.add_argument("--role", required=True)
    p.add_argument("--memory-path", required=True)
    p.add_argument("--memory-kind", default="tier2")
    p.add_argument("--binding-id")
    p.add_argument("--actor", default="cos")
    p.set_defaults(func=cmd_roles_bind_memory)
    p = roles_sub.add_parser("record-eval")
    add_common(p)
    p.add_argument("--role", required=True)
    p.add_argument("--eval-id")
    p.add_argument("--eval-name", required=True)
    p.add_argument("--score", type=float, required=True)
    passed_group = p.add_mutually_exclusive_group()
    passed_group.add_argument("--passed", dest="passed", action="store_true")
    passed_group.add_argument("--failed", dest="passed", action="store_false")
    p.set_defaults(passed=None)
    p.add_argument("--evidence", required=True)
    p.add_argument("--mission-id")
    p.add_argument("--hat-id")
    p.add_argument("--actor", default="evaluator")
    p.set_defaults(func=cmd_roles_record_eval)
    p = roles_sub.add_parser("recommend")
    add_common(p)
    p.add_argument("--role", required=True)
    p.add_argument("--recommendation-id")
    p.add_argument("--actor", default="evaluator")
    p.set_defaults(func=cmd_roles_recommend)
    p = roles_sub.add_parser("evolve")
    add_common(p)
    p.add_argument("--role", required=True)
    p.add_argument("--charter")
    p.add_argument("--current-focus")
    p.add_argument("--authority-level")
    p.add_argument("--add-capability", action="append")
    p.add_argument("--ratified-by")
    p.add_argument("--approval-note", default="")
    p.add_argument("--actor", default="cos")
    p.set_defaults(func=cmd_roles_evolve)
    p = roles_sub.add_parser("assign-hat")
    p.add_argument("--mission-id", required=True)
    p.add_argument("--node-id")
    p.add_argument("--role", required=True)
    p.add_argument("--hat-id")
    p.add_argument("--assignment-id")
    p.add_argument("--hat-name", required=True)
    p.add_argument("--purpose", required=True)
    p.add_argument("--actor", default="cos")
    p.set_defaults(func=cmd_roles_assign_hat)
    p = roles_sub.add_parser("show-lineage")
    add_common(p)
    p.add_argument("--role", required=True)
    p.set_defaults(func=cmd_roles_show_lineage)

    ovi = sub.add_parser("ovi")
    ovi_sub = ovi.add_subparsers(dest="cmd", required=True)
    p = ovi_sub.add_parser("compute")
    add_common(p)
    add_ovi_component_args(p)
    p.set_defaults(func=cmd_ovi_compute)
    p = ovi_sub.add_parser("publish")
    add_common(p)
    add_ovi_component_args(p)
    p.add_argument("--actor", default="cos")
    p.set_defaults(func=cmd_ovi_publish)

    digest = sub.add_parser("digest")
    digest_sub = digest.add_subparsers(dest="cmd", required=True)
    p = digest_sub.add_parser("publish-sanitized")
    add_common(p)
    p.add_argument("--digest-id")
    p.add_argument("--week-start", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--content")
    p.add_argument("--content-file")
    p.add_argument("--output-dir")
    p.add_argument("--actor", default="cos")
    p.set_defaults(func=cmd_digest_publish)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
