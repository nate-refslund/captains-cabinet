"""Anti-leakage guard — the sacred boundary
(docs/fidelity-harness-design-2026-06-18.md §214-225).

The officer-under-test must see NOTHING timestamped >= cutoff_ts. The brain
bridge has no cutoff parameter today, so the guard is implemented OUTSIDE the
MCP. F1 uses two LIVE guards: (1) assert the reconstructed thread is strictly
pre-cutoff, and (2) post-scan the officer's decision text for leaked
post-cutoff signals. filter_mcp_result is the THIRD guard: built + tested here
and now LIVE on the F4 path (officer_runner.gather_cutoff_context runs every
admitted brain source through it). It only fences structured, ts-keyed
records — un-fenceable sources (brief prose, mtime-only search hits, dated
dossier sections) are excluded at the source, never relied on this guard. Any
breach hard-fails the case — we never silently score a leaked case (§238).
"""

from __future__ import annotations

import datetime as _dt
import re
import sys
from typing import Any

# Keys whose value is a CONTENT-CREATION timestamp we compare against the
# cutoff. The commitment keys (source_date, resolved_ts) are included so the F4
# open_commitments source is genuinely guard-walkable (design §2.1) — a
# commitment whose source_date / resolved_ts is at-or-after the cutoff is a
# post-cutoff record and must be dropped.
#
# `due` is DELIBERATELY EXCLUDED: a due date is legitimate as-of-cutoff
# knowledge (the Captain can know "this is due next Friday" at the cutoff), NOT a
# content-creation timestamp. Including it wrongly DROPS a genuinely open
# commitment whose source_date is empty and whose due is in the future —
# _item_ts returns the FIRST matching key, so an empty source_date is skipped
# and the future `due` is taken as the record's timestamp, failing the fence.
_TS_KEYS = ("ts", "date", "edit_date", "reply_ts", "created_at",
            "resolved_ts", "source_date")
_ISO_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?"
)
# Anchored ISO date-or-datetime, used ONLY for the _item_ts candidate gate so a
# bare ``date`` (which ``date.isoformat()`` renders as YYYY-MM-DD, no ``T``) is
# still a fence-able content timestamp. _ISO_RE itself stays datetime-only — it
# is relied on by scan_for_leaks / _content_ts / the thread assertion, which
# must not start matching bare dates embedded in free text.
_ITEM_TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?)?$"
)


class LeakageDetectedError(RuntimeError):
    """A post-cutoff timestamp or held-out artifact crossed the guard. The
    case is hard-failed and never scored."""


def _item_ts(item: dict) -> str | None:
    """Return the gating content-creation timestamp for a record, or None.

    Audit finding #2a fixed two bugs:
      (a) a DATETIME/date-typed value (e.g. an mtime-derived ts, or a
          ``resolved_ts`` carried as a ``datetime``) failed ``isinstance(v, str)``
          and silently bypassed the cutoff fence (returned None -> not dropped).
          Each value is now coerced to ISO via ``.isoformat()`` before the
          ``_ISO_RE`` check.
      (b) the old loop returned on the FIRST key examined, so an empty / wrong
          earlier key (e.g. an empty ``source_date``) shadowed a later
          post-cutoff key (e.g. ``resolved_ts``), letting a leaked record
          through. We now scan ALL keys and collect every valid candidate.

    ISO timestamps (same-offset UTC) sort lexicographically, so returning the
    MAX candidate makes "any candidate >= cutoff is catchable" without giving
    ``_item_ts`` the cutoff: if the latest candidate is >= cutoff the fence
    drops the record; if the latest is < cutoff every candidate is, so the
    record is legitimately kept. (``due`` is excluded from ``_TS_KEYS`` so a
    future due date never gates — see the module note above.)"""
    candidates: list[str] = []
    for k in _TS_KEYS:
        v = item.get(k)
        if isinstance(v, (_dt.datetime, _dt.date)):
            v = v.isoformat()
        if isinstance(v, str) and _ITEM_TS_RE.match(v):
            candidates.append(v)
    if not candidates:
        return None
    return max(candidates)


def filter_mcp_result(result: Any, cutoff_ts: str) -> Any:
    """Recursively drop any dict/list item whose timestamp is >= cutoff_ts.
    ISO timestamps sort lexicographically, so string compare is correct for
    same-offset UTC. Logs each redaction to stderr for the audit trail.

    This is the live-MCP-result redactor. It is LIVE on the F4 path
    (officer_runner.gather_cutoff_context runs every admitted brain source
    through it); the F1 path (run_case gather=None) does not gather and so
    relies only on assert_thread_pre_cutoff + scan_for_leaks. It fences only
    structured, ts-keyed records — un-fenceable sources are excluded before
    they reach this guard."""
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
