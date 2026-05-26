"""Reflexion-structured experience records.

Phase 7 of the convergence plan. The Cabinet's per-task learning loop already
fires (via `cabinet/scripts/record-experience.sh` and `post-tool-use.sh`).
This module adds the *Reflexion-style structured* shape: each record carries
a `lesson_type`, `trigger_signal`, and `applicability_scope` so future
sessions can match against past lessons by *kind* and *context*, not just
free-text similarity.

Schema:
  - `id`               UUID
  - `actor`            officer slug
  - `lesson_type`      enum: blocker | optimization | pattern | anti_pattern | surprise
  - `trigger_signal`   short noun phrase — what called this lesson into being
                       (e.g. "PR rejected for missing tests", "OVI dropped 5%
                       after charter change")
  - `applicability_scope`  enum: this_task | this_mission | this_role | cabinet_wide
  - `body`             markdown — the actual lesson
  - `evidence`         optional URL/path to the artifact that proves it
  - `created_at`       ISO 8601

Records emit an `experience_recorded` event so OVI's learning_rate component
counts them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit, replay


VALID_LESSON_TYPES = frozenset({
    "blocker",         # something blocked progress; document the workaround
    "optimization",    # found a faster/cleaner way
    "pattern",         # reusable approach worth promoting to a skill
    "anti_pattern",    # something to avoid in the future
    "surprise",        # unexpected behavior worth recording
})

VALID_APPLICABILITY_SCOPES = frozenset({
    "this_task",       # only relevant inside this task; consume + discard
    "this_mission",    # carry across tasks of this mission
    "this_role",       # promote to the role's tier-2 working notes
    "cabinet_wide",    # promote to memory/skills/evolved/ as a draft skill
})


def _records_dir() -> Path:
    """Path where structured experience records live (JSONL, append-only)."""
    root = Path(os.environ.get("CABINET_ROOT", Path(__file__).parent.parent.parent))
    return root / "memory" / "experience_records"


def record(
    actor: str,
    lesson_type: str,
    trigger_signal: str,
    body: str,
    applicability_scope: str = "this_role",
    evidence: str | None = None,
) -> dict[str, Any]:
    """Create + persist a structured experience record. Emits experience_recorded event.

    Returns the full record dict.
    """
    if lesson_type not in VALID_LESSON_TYPES:
        raise ValueError(
            f"Invalid lesson_type: {lesson_type!r}. Valid: {sorted(VALID_LESSON_TYPES)}"
        )
    if applicability_scope not in VALID_APPLICABILITY_SCOPES:
        raise ValueError(
            f"Invalid applicability_scope: {applicability_scope!r}. "
            f"Valid: {sorted(VALID_APPLICABILITY_SCOPES)}"
        )

    rec = {
        "id": str(uuid.uuid4()),
        "actor": actor,
        "lesson_type": lesson_type,
        "trigger_signal": trigger_signal,
        "applicability_scope": applicability_scope,
        "body": body,
        "evidence": evidence,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    records_dir = _records_dir()
    records_dir.mkdir(parents=True, exist_ok=True)
    out_file = records_dir / f"records-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    with open(out_file, "a") as f:
        f.write(json.dumps(rec) + "\n")

    emit("experience_recorded", actor=actor, payload={
        "record_id": rec["id"],
        "lesson_type": lesson_type,
        "trigger_signal": trigger_signal,
        "applicability_scope": applicability_scope,
        "has_evidence": evidence is not None,
    })

    return rec


def list_records(
    actor: str | None = None,
    lesson_type: str | None = None,
    scope: str | None = None,
) -> list[dict[str, Any]]:
    """Read all records, optionally filtered."""
    records_dir = _records_dir()
    if not records_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for jl in sorted(records_dir.glob("records-*.jsonl")):
        with open(jl) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if actor and rec.get("actor") != actor:
                    continue
                if lesson_type and rec.get("lesson_type") != lesson_type:
                    continue
                if scope and rec.get("applicability_scope") != scope:
                    continue
                out.append(rec)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record a structured experience (Reflexion-style)."
    )
    parser.add_argument("--actor", required=True, help="Officer slug")
    parser.add_argument("--lesson-type", required=True, choices=sorted(VALID_LESSON_TYPES))
    parser.add_argument("--trigger-signal", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--scope", default="this_role", choices=sorted(VALID_APPLICABILITY_SCOPES))
    parser.add_argument("--evidence", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rec = record(
        actor=args.actor,
        lesson_type=args.lesson_type,
        trigger_signal=args.trigger_signal,
        body=args.body,
        applicability_scope=args.scope,
        evidence=args.evidence,
    )

    if args.json:
        print(json.dumps(rec, indent=2))
    else:
        print(f"experience: recorded {rec['id'][:8]} "
              f"({rec['lesson_type']} / {rec['applicability_scope']})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
