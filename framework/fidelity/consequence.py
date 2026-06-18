"""F0 — consequence-event emitter + ledger reader (shared fidelity infra).

Emits the normalized `consequence-event` shape
(framework/schemas/consequence-event.schema.json) to an append-only JSONL
ledger, validating every event against the real schema first. Graduation
math reads ONLY this ledger (see docs/consequence-ledger.md). This module is
the first consumer per docs/fidelity-harness-design-2026-06-18.md §5.

Storage mirrors framework/events/emitter.py BUT uses a DISTINCT filename
family so the two ledgers never collide in the shared dir: one file per UTC
day at $CABINET_EVENT_LOG_DIR/consequence-events-YYYY-MM-DD.jsonl,
json.dumps(event, default=str) + newline, append-only. (events/emitter.py
owns events-YYYY-MM-DD.jsonl in the same dir.) Enrichment (decision/outcome/
review landing later) is a SUPERSEDING event with the same
(actor, action, subject, ts) identity tuple; the reader takes the last write
per identity (last-write-wins).

System Python is 3.9.6 with no `jsonschema` dependency, so validation is
hand-rolled against this ONE schema (additionalProperties:false everywhere +
the three documented cross-field invariants).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schemas"
    / "consequence-event.schema.json"
)
SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text())


class ConsequenceValidationError(ValueError):
    """Raised when a consequence event violates the schema or its invariants."""


def _consequence_log_dir() -> Path:
    """Resolve the JSONL consequence-ledger directory.

    Mirrors framework/events/emitter.py:_event_log_dir(): CABINET_EVENT_LOG_DIR
    wins; default is the durable per-user location (NOT /tmp, which is wiped).
    """
    return Path(os.environ.get(
        "CABINET_EVENT_LOG_DIR",
        os.path.expanduser("~/Library/Application Support/cabinet/events"),
    ))
