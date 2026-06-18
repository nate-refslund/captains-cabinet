"""Anti-leakage guard — the sacred boundary
(docs/fidelity-harness-design-2026-06-18.md §214-225).

The officer-under-test must see NOTHING timestamped >= cutoff_ts. The brain
bridge has no cutoff parameter today, so the guard is implemented OUTSIDE the
MCP. F1 uses two LIVE guards: (1) assert the reconstructed thread is strictly
pre-cutoff, and (2) post-scan the officer's decision text for leaked
post-cutoff signals. filter_mcp_result is the THIRD guard, built + tested here
but reserved for F4 when the live brain chain is wired (F1 has no live MCP
chain). Any breach hard-fails the case — we never silently score a leaked case
(§238).
"""

from __future__ import annotations

import re
import sys
from typing import Any

# Keys whose value is a timestamp we compare against the cutoff.
_TS_KEYS = ("ts", "date", "edit_date", "reply_ts", "created_at", "resolved_ts")
_ISO_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?"
)


class LeakageDetectedError(RuntimeError):
    """A post-cutoff timestamp or held-out artifact crossed the guard. The
    case is hard-failed and never scored."""


def _item_ts(item: dict) -> str | None:
    for k in _TS_KEYS:
        v = item.get(k)
        if isinstance(v, str) and _ISO_RE.match(v):
            return v
    return None


def filter_mcp_result(result: Any, cutoff_ts: str) -> Any:
    """Recursively drop any dict/list item whose timestamp is >= cutoff_ts.
    ISO timestamps sort lexicographically, so string compare is correct for
    same-offset UTC. Logs each redaction to stderr for the audit trail.

    F4 hook: this is the live-MCP-result redactor. F1 does NOT call it
    (no live brain chain); F1's live guards are assert_thread_pre_cutoff +
    scan_for_leaks."""
    if isinstance(result, dict):
        ts = _item_ts(result)
        if ts is not None and ts >= cutoff_ts:
            print(f"[leakguard] redacted post-cutoff item ts={ts} >= {cutoff_ts}",
                  file=sys.stderr)
            return None
        return {k: filter_mcp_result(v, cutoff_ts) for k, v in result.items()}
    if isinstance(result, list):
        out = []
        for item in result:
            filtered = filter_mcp_result(item, cutoff_ts)
            if filtered is None:
                continue
            out.append(filtered)
        return out
    return result


def assert_thread_pre_cutoff(thread_before: list[dict], cutoff_ts: str) -> None:
    """Hard-fail if any reconstructed message is timestamped >= cutoff_ts.
    Equal-ts is a leak (mirrors retrodiction test_cutoff_no_post_reply_leakage)."""
    for m in thread_before:
        d = m.get("date") or ""
        if d and d >= cutoff_ts:
            raise LeakageDetectedError(
                f"thread message dated {d} >= cutoff {cutoff_ts} (case is leaked)")


def scan_for_leaks(decision_text: str, thread_before: list[dict],
                   cutoff_ts: str) -> list[str]:
    """Post-decision scan: flag any ISO timestamp in the officer's output that
    is >= cutoff_ts (the officer cannot legitimately know a post-cutoff time).
    Returns leaked signal strings or [] if clean."""
    leaks: list[str] = []
    for ts in _ISO_RE.findall(decision_text or ""):
        if ts >= cutoff_ts:
            leaks.append(ts)
    return leaks
