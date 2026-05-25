#!/usr/bin/env python3
"""Typed policy shadow evaluator.

This is deliberately not authoritative yet. It reads the same hook input shape
as pre-tool-use.sh, emits a structured allow/block decision, and can append the
decision into org_events for parity analysis.
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

from org_runtime import Store  # noqa: E402


PRODUCT = os.environ.get("ORG_RUNTIME_PRODUCT", "captains-cabinet")


def read_input() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {"tool_name": "", "tool_input": {}}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"tool_name": "", "tool_input": {}, "_error": f"invalid JSON: {exc}"}
    if not isinstance(data, dict):
        return {"tool_name": "", "tool_input": {}, "_error": "input must be object"}
    data.setdefault("tool_input", {})
    return data


def command(tool_input: dict[str, Any]) -> str:
    return str(tool_input.get("command") or "")


def file_path(tool_input: dict[str, Any]) -> str:
    return str(tool_input.get("file_path") or tool_input.get("path") or "")


def decision(hook: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(hook.get("tool_name") or "")
    tool_input = hook.get("tool_input") if isinstance(hook.get("tool_input"), dict) else {}
    officer = os.environ.get("OFFICER") or os.environ.get("OFFICER_NAME") or "unknown"
    reasons: list[str] = []

    if hook.get("_error"):
        return {"decision": "allow", "reason": hook["_error"], "officer": officer, "policy_version": "shadow-v1"}

    if tool_name == "Bash":
        cmd = command(tool_input)
        if re.search(r"\bvercel\s+(deploy|--prod)\b", cmd):
            reasons.append("production_deploy_requires_captain_approval")
        if re.search(r"\b(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE|DELETE\s+FROM)\b", cmd):
            reasons.append("destructive_database_operation_requires_captain_approval")
        if re.search(r"(^|[;&|]\s*)rm\s+-[A-Za-z]*r[A-Za-z]*f?[A-Za-z]*\s+/", cmd):
            reasons.append("destructive_filesystem_operation")
        if officer not in ("cto", "unknown") and re.search(r"/workspace/[a-z0-9][a-z0-9-]*/", cmd):
            if re.search(r"(>|tee\s+|sed\s+.*\s-i|cp\s+|mv\s+|rsync\s+|patch\s+|perl\s+.*\s-i|tar\s+)", cmd):
                reasons.append("non_cto_product_workspace_write")

    if tool_name in ("Edit", "Write"):
        path = file_path(tool_input)
        if "constitution/" in path:
            reasons.append("constitution_read_only")
        if path.endswith(".env") or "/.env" in path:
            reasons.append("env_files_read_only")
        if officer not in ("cto", "unknown") and re.search(r"^/workspace/[a-z0-9][a-z0-9-]*/", path):
            reasons.append("non_cto_product_workspace_write")
        if "instance/memory/tier2/" in path and officer not in ("unknown",):
            expected = f"instance/memory/tier2/{officer}/"
            if expected not in path:
                reasons.append("officer_tier2_isolation")

    if reasons:
        return {
            "decision": "block",
            "reason": ",".join(reasons),
            "reasons": reasons,
            "officer": officer,
            "policy_version": "shadow-v1",
        }
    return {"decision": "allow", "reason": "no_shadow_rule_matched", "officer": officer, "policy_version": "shadow-v1"}


def maybe_record(result: dict[str, Any], hook: dict[str, Any]) -> None:
    if os.environ.get("ORG_POLICY_SHADOW_RECORD", "1") == "0":
        return
    try:
        store = Store()
        payload = {
            "shadow_decision": result,
            "tool_name": hook.get("tool_name"),
            "tool_input": hook.get("tool_input"),
        }
        store.append_event(
            "policy.shadow_decision",
            PRODUCT,
            "policy_shadow",
            f"{result['officer']}:{hook.get('tool_name', 'unknown')}",
            result["officer"],
            payload,
            source="pre-tool-use-shadow",
        )
    except Exception as exc:  # noqa: BLE001 - shadow path must never block tools.
        if os.environ.get("ORG_POLICY_SHADOW_VERBOSE") == "1":
            print(f"policy-shadow: WARN failed to record event: {exc}", file=sys.stderr)


def main() -> int:
    hook = read_input()
    result = decision(hook)
    maybe_record(result, hook)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
