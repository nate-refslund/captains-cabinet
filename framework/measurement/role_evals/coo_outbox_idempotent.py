"""Eval: COO — outbox queue idempotency by key.

Tests the **quality** of the COO role's cross-system-write discipline.
A failure signals `quality_gap` — duplicate writes to external systems
(Notion / Linear / monday) under retry pressure.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.role_eval_runner import RoleEval, register


def _setup():
    tmp = tempfile.mkdtemp()
    os.environ["CABINET_EVENT_LOG_DIR"] = f"{tmp}/events"
    return {"tmp": tmp}


def _execute(ctx):
    from framework.outbox.relay import queue
    from framework.events.emitter import replay

    # Queue the same op twice with the same idempotency key
    first = queue("stub", {"x": 1}, actor="coo", idempotency_key="op-A")
    second = queue("stub", {"x": 2}, actor="coo", idempotency_key="op-A")  # would-be duplicate
    third = queue("stub", {"x": 3}, actor="coo", idempotency_key="op-B")   # different key

    queued = replay(event_types=["outbox_queued"])

    return {
        "first": first,
        "second": second,
        "third": third,
        "queued_count": len(queued),
    }


def _verify(ctx, results):
    return [
        ("dup_key_returns_original_id", results["first"] == results["second"], "quality_gap"),
        ("different_key_creates_new", results["first"] != results["third"], "quality_gap"),
        ("only_two_events_emitted", results["queued_count"] == 2, "quality_gap"),
    ]


register(RoleEval(
    name="coo_outbox_idempotent",
    role_slug="coo",
    category="quality",
    description="COO outbox queue dedupes by idempotency_key without re-emitting events.",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
