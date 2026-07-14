"""Reflexion-structured experience records.

Phase 7 of the convergence plan. The Cabinet's per-task learning loop already
fires (via `cabinet/scripts/record-experience.sh` and `post-tool-use.sh`).
This module adds the *Reflexion-style structured* shape: each record carries
a `lesson_type`, `trigger_signal`, and `applicability_scope` so future
sessions can match against past lessons by *kind* and *context*, not just
free-text similarity.

Store (UNIFIED 2026-07-04, lane/learn-0705): ONE canonical directory —
`$CABINET_ROOT/memory/tier3/experience-records/` — holding TWO formats side
by side:
  - `records-*.jsonl`            — structured records written by `record()` here
  - `YYYY-MM-DD-<officer>-*.md`  — markdown records written by the fleet's
                                   habitual writer, `cabinet/scripts/
                                   record-experience.sh` (hook-nudged)
`list_records()` reads BOTH (the md files are adapted into the structured
shape at read time — see `_parse_md_record`), so skill induction and the
self-improvement loop see every record regardless of which writer produced it.

Schema:
  - `id`               UUID (jsonl) / file stem (md)
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
counts them. (`record-experience.sh` emits the same event for md records —
block 1c there — so the event ledger counts BOTH write paths.)
"""

from __future__ import annotations

import argparse
import json
import os
import re
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
    """Canonical experience-record store — `memory/tier3/experience-records/`.

    UNIFICATION (2026-07-04, lane/learn-0705): this module originally used
    `memory/experience_records/` while the fleet's actual writer
    (`cabinet/scripts/record-experience.sh`, block 1) wrote markdown records
    to `memory/tier3/experience-records/`. The two paths never met, so
    `list_records()` — the input to skill_induction and the self-improvement
    loop — was permanently empty even as real records accumulated (24 on
    disk at unification time). Canonical-path decision: keep the tier3 dir —
    it is the one with existing data, it matches the CLAUDE.md Memory
    Protocol ("Tier 3 (episodic): memory/tier3/"), and the reflection/retro
    skills (`memory/skills/individual-reflection.md`,
    `memory/skills/cross-officer-retro.md`) already list it by that path.
    Both formats coexist here (`records-*.jsonl` from this module,
    `YYYY-MM-DD-<officer>-*.md` from the shell writer); the filename
    patterns cannot collide.
    """
    root = Path(os.environ.get("CABINET_ROOT", Path(__file__).parent.parent.parent))
    return root / "memory" / "tier3" / "experience-records"


def _legacy_records_dir() -> Path:
    """Pre-unification JSONL location (`memory/experience_records/`).

    Kept ONLY so `_migrate_legacy_store()` can heal deployments that
    accumulated structured records at the old path before 2026-07-04.
    Nothing writes here anymore.
    """
    root = Path(os.environ.get("CABINET_ROOT", Path(__file__).parent.parent.parent))
    return root / "memory" / "experience_records"


def _migrate_legacy_store() -> None:
    """One-shot, idempotent healing: move legacy JSONL into the canonical dir.

    Why lazy (called from `record()` / `list_records()`) instead of an
    operator step: the unification must hold on EVERY deployment that pulls
    this commit (Mac Mini targets, clean-room clones) without a hands-on
    migration — the same additive/self-healing migration discipline the
    screenpipe pipes use. Cost once migrated: a single `is_dir()` check.

    Collision-safe: a same-named canonical file gets the legacy lines
    APPENDED (JSONL is append-only by contract, so concatenation is
    lossless), then the legacy file is removed. Best-effort by design — a
    failed move leaves files in place for the next call; the reader must
    never crash because healing hiccuped.
    """
    legacy = _legacy_records_dir()
    try:
        if not legacy.is_dir():
            return
        canonical = _records_dir()
        # Paranoia: never "migrate" a dir onto itself (mis-set CABINET_ROOT
        # or symlinked memory/ could alias the two paths).
        if legacy.resolve() == canonical.resolve():
            return
        for src in sorted(legacy.glob("records-*.jsonl")):
            canonical.mkdir(parents=True, exist_ok=True)
            dst = canonical / src.name
            if dst.exists():
                with open(src) as fin, open(dst, "a") as fout:
                    fout.write(fin.read())
                src.unlink()
            else:
                src.rename(dst)
        # Drain a lone .gitkeep too (a hand-scaffolded legacy dir would
        # otherwise never empty and the is_dir() fast-path would re-glob on
        # every call — checkpoint-review finding, cp1 #3). Then drop the dir.
        # rmdir refuses on non-empty (any OTHER stray file is left for a
        # human) — that refusal is fine: the retained dir merely costs one
        # empty glob per call, never correctness.
        gitkeep = legacy / ".gitkeep"
        if gitkeep.exists() and sum(1 for _ in legacy.iterdir()) == 1:
            gitkeep.unlink()
        try:
            legacy.rmdir()
        except OSError:
            pass
    except OSError:
        # Healing is best-effort: never let a migration hiccup break
        # record() or list_records(). Anything left behind retries next call.
        pass


# ---------------------------------------------------------------------------
# Shell-written markdown records (cabinet/scripts/record-experience.sh)
# ---------------------------------------------------------------------------
# The fleet's habitual writer is the SHELL script (the post-tool-use hook
# nudges officers toward it; golden eval eval-004 asserts its md-file
# contract), and it writes MARKDOWN, not JSONL. Unification decision
# (2026-07-04): adapt the READER instead of converting the files — a
# one-shot md→jsonl conversion would fix the past but re-sever the stream on
# the very next shell-written record, and running two writers into one
# format invites races. Parsing at read time makes shell records first-class
# skill-induction input forever, with zero change to the write path the
# fleet already exercises.

# Field lines in the md contract look like: `- **Officer:** acme-ceo`
_MD_FIELD_RE = re.compile(r"^-\s+\*\*(Officer|Date|Outcome|Tags):\*\*\s*(.*)$")

# Outcome → lesson_type mapping. The md contract records a task OUTCOME
# (success|failure|partial|escalated — validated by record-experience.sh)
# while the structured shape wants a Reflexion lesson KIND. Deterministic
# mapping, documented here as the single source of truth:
#   success             → pattern       (an approach that worked — reuse candidate)
#   failure             → anti_pattern  (what not to repeat)
#   partial | escalated → blocker       (progress was impeded; the record is the wall)
_OUTCOME_TO_LESSON_TYPE = {
    "success": "pattern",
    "failure": "anti_pattern",
    "partial": "blocker",
    "escalated": "blocker",
}

# The shell script writes this placeholder when no lessons were passed —
# treat it as absent rather than feeding boilerplate into induction bodies.
_MD_NO_LESSONS_PLACEHOLDER = "No specific lessons noted."

# Only the record contract's own headings open a section. Record bodies
# quote arbitrary text (task output, error dumps) that may itself contain
# `## Something` lines — treating those as section starts would silently
# truncate what/lessons at the first embedded heading (checkpoint-review
# finding, cp1 #4). Keys are the normalized first word of each contract
# heading as written by record-experience.sh block 1.
_MD_KNOWN_SECTIONS = frozenset({"task", "what", "lessons", "counterfactual"})


def _parse_md_record(path: Path) -> dict[str, Any] | None:
    """Adapt one shell-written markdown record into the structured shape.

    Field mapping (md contract → Reflexion schema):
      Officer                  → actor
      Date                     → created_at (already ISO-8601 UTC)
      Outcome                  → lesson_type via _OUTCOME_TO_LESSON_TYPE
      ## Task (first line)     → trigger_signal (what called the lesson into
                                 being; recurring identical task lines are
                                 exactly what induction should cluster on)
      ## Lessons Learned (+ ## What Happened as context) → body
      (fixed)                  → applicability_scope = "this_role" — the md
                                 contract has no scope field; this_role is
                                 the same default `record()` uses AND is
                                 inside skill_induction's DEFAULT_SCOPE_FILTER,
                                 so shell records are induction-eligible.
      file path                → evidence; file stem → id (stable, unique —
                                 the shell names files <date>-<officer>-<epoch>-<pid>.md)

    Tolerant by design: sections may be absent (records written before the
    counterfactual feature lack that section) and a file that isn't an
    experience record at all (no `Officer` field) returns None — the reader
    skips it rather than crashing the learning loop on one bad file.
    """
    try:
        text = path.read_text()
    except OSError:
        return None

    fields: dict[str, str] = {}
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            # Normalize heading → key ("## Counterfactual (one change → 10x)"
            # keys as "counterfactual"). Only CONTRACT headings switch
            # sections — an embedded `## Step 2` inside quoted task output
            # stays body text (see _MD_KNOWN_SECTIONS rationale).
            key = line[3:].strip().lower().split(" ")[0]
            if key in _MD_KNOWN_SECTIONS:
                current = key
                sections.setdefault(current, [])
                continue
        # Field lines are only honored in the PREAMBLE (before the first
        # `## ` section) — record bodies quote arbitrary text (task output,
        # error dumps), and a `- **Officer:** ...` line inside a section
        # must not spoof/overwrite the record's attribution.
        if current is None:
            m = _MD_FIELD_RE.match(line.strip())
            if m:
                fields[m.group(1).lower()] = m.group(2).strip()
                continue
        if current is not None:
            sections[current].append(line)

    actor = fields.get("officer", "")
    if not actor:
        return None  # not an experience record (or corrupt) — skip, don't crash

    def _section(key: str) -> str:
        return "\n".join(sections.get(key, [])).strip()

    task = _section("task")
    what = _section("what")
    lessons = _section("lessons")
    if lessons == _MD_NO_LESSONS_PLACEHOLDER:
        lessons = ""

    # Body = the lesson first, then what-happened as evidence/context (both
    # surface in induced-draft `sample_bodies`, where the CoS validates).
    body = "\n\n".join(part for part in (lessons, what) if part)

    outcome = fields.get("outcome", "").lower()
    return {
        "id": path.stem,
        "actor": actor,
        "lesson_type": _OUTCOME_TO_LESSON_TYPE.get(outcome, "surprise"),
        # First non-empty Task line; empty stays empty — such a record still
        # lists, and skill_induction._cluster_records already drops empty
        # trigger keys, so it degrades gracefully instead of mis-clustering.
        "trigger_signal": task.splitlines()[0].strip() if task else "",
        "applicability_scope": "this_role",
        "body": body,
        "evidence": str(path),
        "created_at": fields.get("date", ""),
        # Extra md-only context, additive — dict consumers ignore unknown keys.
        "outcome": outcome,
        "tags": [t.strip() for t in fields.get("tags", "").split(",") if t.strip()],
        "source_format": "markdown",
    }


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

    _migrate_legacy_store()  # heal pre-2026-07-04 stores before writing (see docstring)
    records_dir = _records_dir()
    records_dir.mkdir(parents=True, exist_ok=True)
    out_file = records_dir / f"records-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    with open(out_file, "a") as f:
        f.write(json.dumps(rec) + "\n")

    emit("experience_recorded", actor=actor, payload={
        # experience_id: the emitter's aggregate map (emitter.py _AGGREGATE_MAP,
        # "experience_recorded" → ("experience", "experience_id")) keys the
        # Store mirror on this — without it every record aggregated as
        # "unknown". record_id kept for existing consumers.
        "experience_id": rec["id"],
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
    """Read all records — BOTH formats in the canonical dir — optionally filtered.

    Sources merged (see module docstring for the 2026-07-04 unification):
      1. `records-*.jsonl` — structured records written by `record()`.
      2. `*.md`            — shell-written records adapted via `_parse_md_record`
                             (this is what makes the fleet's real experience
                             visible to skill induction at all).
    Output is sorted by `created_at` so the merge is deterministic across
    formats (ISO-8601 sorts lexically; records lacking a timestamp sort first).
    """
    _migrate_legacy_store()  # heal pre-2026-07-04 stores before reading (see docstring)
    records_dir = _records_dir()
    if not records_dir.exists():
        return []

    def _passes(rec: dict[str, Any]) -> bool:
        if actor and rec.get("actor") != actor:
            return False
        if lesson_type and rec.get("lesson_type") != lesson_type:
            return False
        if scope and rec.get("applicability_scope") != scope:
            return False
        return True

    out: list[dict[str, Any]] = []
    for jl in sorted(records_dir.glob("records-*.jsonl")):
        with open(jl) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    # One torn/corrupt line (e.g. crash mid-append) must not
                    # blind the learning loop to every other record.
                    continue
                if _passes(rec):
                    out.append(rec)

    # Shell-written markdown records — same store, second format. Unparseable
    # files return None from the adapter and are skipped (never crash the
    # loop on one bad file). `.gitkeep` and friends don't match the glob.
    for md in sorted(records_dir.glob("*.md")):
        rec_md = _parse_md_record(md)
        if rec_md is not None and _passes(rec_md):
            out.append(rec_md)

    # Z → +00:00 before comparing: jsonl stamps are `...+00:00`
    # (datetime.isoformat) while shell md stamps are `...Z`; raw lexical
    # order would interleave the two representations wrongly at close
    # timestamps (checkpoint-review finding, cp1 #6). Both denote UTC, so
    # the normalization makes the sort chronologically honest.
    out.sort(key=lambda r: (r.get("created_at") or "").replace("Z", "+00:00"))
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
