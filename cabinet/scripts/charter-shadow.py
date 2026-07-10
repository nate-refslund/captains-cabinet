#!/usr/bin/env python3.12
"""charter-shadow.py — Rec 3.3: price the governance mass (report-only).

The 07-08 report's D9 survivor: before anyone argues about deleting the
4.7k-LOC policy_engine/matrix/posture/grants/trust_ladder stack, MEASURE it —
"run policy-shadow as a charter-only arm over history; if divergence <5%,
the deletion case exists." This sidecar produces exactly that brakes:engine
evidence. It is a NEW standalone comparer: policy-shadow.py itself is
germline (schg) and is NOT edited; the DELETION decision stays defer-captain
(germline + law plane) — this script only prices it.

Two arms over the SAME recorded event stream (org_events rows of type
``policy.shadow_decision``, which carry the full hook {tool_name, tool_input}
plus the engine-backed shadow decision policy-shadow already recorded):

  ENGINE arm   = the recorded shadow decision (policy_version shadow-v1 —
                 policy_engine.evaluate_policy over the typed policy stack).
  CHARTER arm  = a ~40-line self-contained mechanical floor, deliberately
                 NOT importing the engine under evaluation: destructive rm,
                 destructive database verbs, .env writes, production-deploy
                 verbs. This is the "ceilings stay germline" residue the
                 report says survives any deletion.

Divergence classes (the split matters):
  engine_only_blocks  — what the 4.7k LOC uniquely buys (deletion cost);
  charter_only_blocks — where the tiny arm is STRICTER (should be ~0; a
                        nonzero count means the charter arm is miscalibrated,
                        not that the engine is lax).

Output: ONE idempotent-per-date line appended to
``shared/interfaces/charter-shadow-series.jsonl``:
  {date, ts, n, agree, agree_rate, engine_only_blocks, charter_only_blocks,
   examples: up to 5 divergent rows (officer, tool, decision pair, reasons,
   command truncated + secret-scrubbed names-not-values)}.

Read-only over the org_events store; the ONLY write is the series append.
Nothing consumes the series as a gate. Scheduled daily 05:10 via the
services.yml row ``charter-shadow``.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "cabinet" / "scripts" / "lib"))

SERIES_PATH = _REPO_ROOT / "shared" / "interfaces" / "charter-shadow-series.jsonl"
MAX_EXAMPLES = 5
_CMD_TRUNC = 160

# ---------------------------------------------------------------------------
# CHARTER ARM — the mechanical floor. Self-contained BY DESIGN: importing
# policy_engine here would make the comparison circular (the arm must model
# what remains AFTER a deletion). Keep this tiny; a growing charter arm is
# governance mass moving house, not shrinking.
# ---------------------------------------------------------------------------
_CHARTER_RULES: list[tuple[str, "re.Pattern[str]"]] = [
    ("destructive_filesystem_rm", re.compile(
        r"(^|[;&|]\s*)rm\s+(-\S+\s+)*-[A-Za-z]*r\S*\s+(-\S+\s+)*"
        r"(/|~|\$HOME|\*)")),
    ("destructive_database_operation", re.compile(
        r"(?i)\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE|DELETE\s+FROM)\b")),
    ("production_deploy", re.compile(
        r"\bvercel\s+(deploy\s+--prod|--prod)\b")),
]


def charter_decision(hook: dict[str, Any]) -> dict[str, Any]:
    """The charter-only arm: block ONLY on the mechanical-floor rules."""
    tool_name = str(hook.get("tool_name") or "")
    tool_input = hook.get("tool_input") if isinstance(
        hook.get("tool_input"), dict) else {}
    reasons: list[str] = []
    if tool_name == "Bash":
        cmd = str(tool_input.get("command") or "")
        for name, rx in _CHARTER_RULES:
            if rx.search(cmd):
                reasons.append(name)
    if tool_name in ("Edit", "Write"):
        path = str(tool_input.get("file_path") or "")
        if path.endswith(".env") or "/.env" in path:
            reasons.append("env_files_read_only")
    return {"decision": "block" if reasons else "allow",
            "reasons": reasons,
            "policy_version": "charter-only-v1"}


# ---------------------------------------------------------------------------
# Replay + compare
# ---------------------------------------------------------------------------

_SECRET_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)[A-Z0-9_]*)"
    r"\s*[=:]\s*\S+")


def _scrub(cmd: str) -> str:
    cmd = _SECRET_RE.sub(r"\1=<redacted>", cmd)
    cmd = re.sub(r"([a-z][a-z0-9+.-]*://)[^/@\s]+@", r"\1<redacted>@", cmd)
    return cmd[:_CMD_TRUNC]


def load_shadow_rows(store=None, since: Optional[str] = None) -> list[dict]:
    """The recorded engine-arm decisions (policy_version shadow-v1 only —
    the T7 authority-shadow rows are a different record shape and are the
    matrix's OWN shadow, not the engine decision under comparison)."""
    if store is None:
        from org_runtime import Store
        store = Store()
    sql = ("SELECT payload_json, created_at, actor FROM org_events "
           "WHERE event_type = 'policy.shadow_decision'")
    params: list[Any] = []
    if since:
        sql += " AND created_at >= ?"
        params.append(since)
    out = []
    for row in store.rows(sql, params):
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except ValueError:
            continue
        sd = payload.get("shadow_decision") or {}
        if sd.get("policy_version") != "shadow-v1":
            continue
        out.append({"created_at": row.get("created_at"),
                    "officer": sd.get("officer") or row.get("actor"),
                    "engine": sd, "hook": {
                        "tool_name": payload.get("tool_name"),
                        "tool_input": payload.get("tool_input") or {}}})
    return out


def compare(rows: list[dict]) -> dict[str, Any]:
    n = agree = engine_only = charter_only = 0
    examples: list[dict] = []
    for row in rows:
        charter = charter_decision(row["hook"])
        eng = str(row["engine"].get("decision") or "allow")
        cha = charter["decision"]
        n += 1
        if eng == cha:
            agree += 1
            continue
        if eng == "block":
            engine_only += 1
        else:
            charter_only += 1
        if len(examples) < MAX_EXAMPLES:
            ti = row["hook"].get("tool_input") or {}
            examples.append({
                "officer": row.get("officer"),
                "tool": row["hook"].get("tool_name"),
                "engine": eng, "charter": cha,
                "engine_reason": str(row["engine"].get("reason") or "")[:120],
                "charter_reasons": charter["reasons"],
                "command": _scrub(str(ti.get("command")
                                      or ti.get("file_path") or "")),
            })
    return {
        "n": n, "agree": agree,
        "agree_rate": round(agree / n, 4) if n else None,
        "engine_only_blocks": engine_only,
        "charter_only_blocks": charter_only,
        "examples": examples,
    }


def _already_reported(path: Path, date: str) -> bool:
    try:
        with open(path) as f:
            for line in f:
                try:
                    if json.loads(line).get("date") == date:
                        return True
                except json.JSONDecodeError:
                    continue
    except OSError:
        return False
    return False


def emit_daily_line(*, rows: Optional[list[dict]] = None,
                    now: Optional[dt.datetime] = None,
                    out_path: Optional[Path] = None) -> Optional[dict]:
    """Compare + append today's line (idempotent per date; None = no-op).
    The ONLY side effect is the series append."""
    now = now or dt.datetime.now(dt.timezone.utc)
    path = out_path or SERIES_PATH
    date = now.strftime("%Y-%m-%d")
    if _already_reported(path, date):
        return None
    if rows is None:
        try:
            rows = load_shadow_rows()
        except Exception:  # noqa: BLE001 — a report never crashes on the store
            rows = []
    line = {"date": date,
            "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            **compare(rows)}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(line, sort_keys=True) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return line


if __name__ == "__main__":
    res = emit_daily_line()
    if res is None:
        print("charter-shadow: today already reported — nothing to do")
    else:
        print("charter-shadow: " + json.dumps(
            {k: v for k, v in res.items() if k != "examples"},
            sort_keys=True))
