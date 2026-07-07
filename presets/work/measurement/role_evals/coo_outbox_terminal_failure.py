"""Eval: COO — outbox handles terminal failures without infinite retry.

Tests the **authority** of the COO role to enforce a "fail fast on
misconfiguration" policy. A failure signals `wrong_authority` — the
outbox would loop forever on a bad destination.
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
    from framework.outbox.relay import queue, dispatch_pending, _pending_queue

    queue("destination-that-does-not-exist", {"x": 1}, actor="coo")
    first = dispatch_pending()
    pending_after_first = len(_pending_queue())
    second = dispatch_pending()  # should be a no-op
    pending_after_second = len(_pending_queue())

    return {
        "first_dispatch": first,
        "second_dispatch": second,
        "pending_after_first": pending_after_first,
        "pending_after_second": pending_after_second,
    }


def _verify(ctx, results):
    return [
        ("first_marks_skipped",
         results["first_dispatch"] == {"dispatched": 0, "failed": 0, "skipped": 1},
         "wrong_authority"),
        ("pending_drained_after_first",
         results["pending_after_first"] == 0,
         "wrong_authority"),
        ("second_dispatch_noop",
         results["second_dispatch"] == {"dispatched": 0, "failed": 0, "skipped": 0},
         "wrong_authority"),
    ]


register(RoleEval(
    name="coo_outbox_terminal_failure",
    role_slug="coo",
    category="authority",
    description="COO outbox fails terminally on misconfigured destination (no retry loop).",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
