#!/usr/bin/env python3
"""Bridge Claude Code native task hooks into the org runtime.

This script is intentionally hook-safe: warn mode records what it can and
nudges for missing Cabinet metadata without blocking Claude Code. Enforcement
can be enabled later with CABINET_TASK_BRIDGE_MODE=enforce.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from org_runtime import DEFAULT_LANE, Store, as_json, utc_now  # noqa: E402


SOURCE = "claude-task-hook"
REQUIRED_METADATA = (
    "mission_id",
    "node_id",
    "owner_role",
    "acceptance_criteria",
    "evidence_required",
    "verifier_role",
    "risk_level",
)
KEY_ALIASES = {
    "mission": "mission_id",
    "mission id": "mission_id",
    "mission_id": "mission_id",
    "node": "node_id",
    "node id": "node_id",
    "node_id": "node_id",
    "role": "owner_role",
    "owner role": "owner_role",
    "owner_role": "owner_role",
    "acceptance": "acceptance_criteria",
    "acceptance criteria": "acceptance_criteria",
    "acceptance_criteria": "acceptance_criteria",
    "evidence": "evidence_required",
    "evidence required": "evidence_required",
    "evidence_required": "evidence_required",
    "verifier": "verifier_role",
    "verifier role": "verifier_role",
    "verifier_role": "verifier_role",
    "risk": "risk_level",
    "risk level": "risk_level",
    "risk_level": "risk_level",
}
LABEL_RE = re.compile(r"(?im)^\s*(?:[-*]\s*)?([a-zA-Z_ ][a-zA-Z0-9_ -]*)\s*[:=]\s*(.+?)\s*$")
BRACKET_RE = re.compile(r"\[(mission|mission_id|node|node_id|role|owner_role|risk|risk_level):\s*([^\]]+)\]", re.I)


def first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def nested_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalized_key(raw: str) -> str | None:
    return KEY_ALIASES.get(raw.strip().lower().replace("-", " "))


def clean_value(raw: str) -> str:
    return raw.strip().strip("`").strip()


def parse_metadata(*texts: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for text in texts:
        if not text:
            continue
        for match in LABEL_RE.finditer(text):
            key = normalized_key(match.group(1))
            if key:
                metadata[key] = clean_value(match.group(2))
        for match in BRACKET_RE.finditer(text):
            key = normalized_key(match.group(1))
            if key:
                metadata[key] = clean_value(match.group(2))
    return {key: value for key, value in metadata.items() if value}


def hook_event_name(data: dict[str, Any]) -> str:
    event = first_text(data.get("hook_event_name"), data.get("event"), os.environ.get("CLAUDE_HOOK_EVENT_NAME"))
    if event:
        return event
    tool_name = first_text(data.get("tool_name"))
    if tool_name in {"TaskCreate", "TaskCreated"}:
        return "TaskCreated"
    if tool_name in {"TaskComplete", "TaskCompleted"}:
        return "TaskCompleted"
    return ""


def task_payload(data: dict[str, Any]) -> dict[str, Any]:
    task = nested_dict(data.get("task"))
    tool_input = nested_dict(data.get("tool_input"))
    description = first_text(
        data.get("task_description"),
        data.get("description"),
        task.get("description"),
        tool_input.get("task_description"),
        tool_input.get("description"),
    )
    subject = first_text(
        data.get("task_subject"),
        data.get("subject"),
        data.get("title"),
        task.get("subject"),
        task.get("title"),
        tool_input.get("task_subject"),
        tool_input.get("subject"),
        tool_input.get("title"),
    )
    metadata = parse_metadata(subject, description, json.dumps(tool_input, sort_keys=True))
    return {
        "task_id": first_text(data.get("task_id"), data.get("id"), task.get("id"), tool_input.get("task_id")),
        "session_id": first_text(data.get("session_id")),
        "transcript_path": first_text(data.get("transcript_path")),
        "cwd": first_text(data.get("cwd")),
        "task_subject": subject,
        "task_description": description,
        "teammate_name": first_text(data.get("teammate_name"), task.get("teammate_name")),
        "team_name": first_text(data.get("team_name"), task.get("team_name")),
        "metadata": metadata,
        "raw": data,
    }


def actor_for(data: dict[str, Any], task: dict[str, Any]) -> str:
    return first_text(
        os.environ.get("OFFICER_NAME"),
        os.environ.get("CABINET_OFFICER"),
        os.environ.get("OFFICER"),
        os.environ.get("CLAUDE_AGENT_NAME"),
        task.get("teammate_name"),
        data.get("teammate_name"),
        "unknown",
    )


def lane_slug() -> str:
    # ENV VAR NAMES keep their pre-rename spelling so a running deployment
    # keeps resolving; only the column and the constant were renamed.
    return first_text(os.environ.get("ORG_RUNTIME_LANE"), os.environ.get("ORG_RUNTIME_PRODUCT"),
                      os.environ.get("DEFAULT_PRODUCT"), DEFAULT_LANE)


def missing_metadata(metadata: dict[str, str]) -> list[str]:
    return [key for key in REQUIRED_METADATA if not metadata.get(key)]


def emit_system_message(message: str, **extra: Any) -> None:
    print(json.dumps({"systemMessage": message, **extra}, sort_keys=True))


def emit_block_message(message: str) -> None:
    print(message, file=sys.stderr)


def metadata_message(missing: list[str]) -> str:
    return (
        "Cabinet task metadata missing: "
        + ", ".join(missing)
        + ". Add mission_id, node_id, owner_role, acceptance_criteria, "
        "evidence_required, verifier_role, and risk_level to the Claude Task."
    )


def write_projection(
    store: Store,
    lane: str,
    task: dict[str, Any],
    event: dict[str, Any],
    status: str,
    actor: str,
) -> None:
    now = utc_now()
    existing = store.row(
        "SELECT * FROM claude_native_tasks WHERE lane_slug = ? AND task_id = ?",
        (lane, task["task_id"]),
    )
    existing_metadata = existing.get("metadata", {}) if existing else {}
    metadata = {**existing_metadata, **task["metadata"]}
    created_event_id = (
        event["event_id"]
        if status == "created"
        else existing.get("created_event_id") if existing else None
    )
    completed_event_id = (
        event["event_id"]
        if status == "completed"
        else existing.get("completed_event_id") if existing else None
    )
    created_at = existing.get("created_at") if existing else now
    completed_at = now if status == "completed" else existing.get("completed_at") if existing else None
    store.conn.execute(
        """
        INSERT INTO claude_native_tasks
          (lane_slug, task_id, session_id, transcript_path, cwd, task_subject,
           task_description, status, actor, teammate_name, team_name, mission_id,
           node_id, owner_role, acceptance_criteria, evidence_required, verifier_role,
           risk_level, metadata_json, created_event_id, completed_event_id, created_at,
           updated_at, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(lane_slug, task_id) DO UPDATE SET
          session_id = excluded.session_id,
          transcript_path = excluded.transcript_path,
          cwd = excluded.cwd,
          task_subject = excluded.task_subject,
          task_description = excluded.task_description,
          status = excluded.status,
          actor = excluded.actor,
          teammate_name = excluded.teammate_name,
          team_name = excluded.team_name,
          mission_id = excluded.mission_id,
          node_id = excluded.node_id,
          owner_role = excluded.owner_role,
          acceptance_criteria = excluded.acceptance_criteria,
          evidence_required = excluded.evidence_required,
          verifier_role = excluded.verifier_role,
          risk_level = excluded.risk_level,
          metadata_json = excluded.metadata_json,
          created_event_id = excluded.created_event_id,
          completed_event_id = excluded.completed_event_id,
          updated_at = excluded.updated_at,
          completed_at = excluded.completed_at
        """,
        (
            lane,
            task["task_id"],
            task["session_id"] or (existing.get("session_id") if existing else None),
            task["transcript_path"] or (existing.get("transcript_path") if existing else None),
            task["cwd"] or (existing.get("cwd") if existing else None),
            task["task_subject"] or (existing.get("task_subject") if existing else ""),
            task["task_description"] or (existing.get("task_description") if existing else ""),
            status,
            actor,
            task["teammate_name"] or (existing.get("teammate_name") if existing else None),
            task["team_name"] or (existing.get("team_name") if existing else None),
            metadata.get("mission_id"),
            metadata.get("node_id"),
            metadata.get("owner_role"),
            metadata.get("acceptance_criteria"),
            metadata.get("evidence_required"),
            metadata.get("verifier_role"),
            metadata.get("risk_level"),
            as_json(metadata),
            created_event_id,
            completed_event_id,
            created_at,
            now,
            completed_at,
        ),
    )
    store.conn.commit()


def handle(data: dict[str, Any]) -> int:
    event_name = hook_event_name(data)
    if event_name not in {"TaskCreated", "TaskCompleted"}:
        return 0

    task = task_payload(data)
    mode = first_text(os.environ.get("CABINET_TASK_BRIDGE_MODE"), "warn").lower()
    if not task["task_id"]:
        message = "Cabinet task bridge could not record this Claude task because task_id was missing."
        if mode == "enforce":
            emit_block_message(message)
            return 2
        emit_system_message(message)
        return 0

    lane = lane_slug()
    actor = actor_for(data, task)
    status = "completed" if event_name == "TaskCompleted" else "created"
    missing = missing_metadata(task["metadata"]) if status == "created" else []
    if missing and mode == "enforce":
        emit_block_message(metadata_message(missing))
        return 2

    payload = {
        "task_id": task["task_id"],
        "session_id": task["session_id"],
        "transcript_path": task["transcript_path"],
        "cwd": task["cwd"],
        "task_subject": task["task_subject"],
        "task_description": task["task_description"],
        "teammate_name": task["teammate_name"],
        "team_name": task["team_name"],
        "status": status,
        "metadata": task["metadata"],
        "missing_metadata": missing,
    }

    store = Store()
    event = store.append_event(
        f"claude_task.{status}",
        lane,
        "claude_native_task",
        task["task_id"],
        actor,
        payload,
        source=SOURCE,
    )
    write_projection(store, lane, task, event, status, actor)

    if missing:
        message = metadata_message(missing)
        emit_system_message(message, missing_metadata=missing)
    return 0


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            raise ValueError("hook payload must be a JSON object")
        return handle(data)
    except Exception as exc:  # pragma: no cover - hook safety path
        message = f"Cabinet task bridge failed open: {exc}"
        if os.environ.get("CABINET_TASK_BRIDGE_STRICT") == "1":
            print(message, file=sys.stderr)
            return 1
        emit_system_message(message)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
