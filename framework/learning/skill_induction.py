"""Voyager-style skill induction — turn recurring experience patterns into draft skills.

Phase 7 of the convergence plan. When 3+ experience records share a common
trigger_signal + lesson_type + applicability_scope, the induction layer
treats that cluster as evidence the pattern is reusable and worth promoting
to the skill library.

Phase 7 ships a *deterministic clustering* version — same trigger_signal
substring or exact match by (lesson_type, applicability_scope) suffices.
Future work (Phase 7.5 / deployment-specific) can layer pgvector-based
semantic clustering on top once embeddings exist.

The induction layer DRAFTS the skill (writes to `memory/skills/evolved/`)
but never promotes it without a validation pass — that's the existing
golden-eval discipline owned by the CoS.

RUNNABLE DRAFTS (§4.2 upgrade, 2026-07-09): a draft used to ship an empty
"(Filled in by the CoS...)" Procedure skeleton — procedural memory that
wasn't executable, so the evolution-loop promotion gate had nothing real to
validate. `distill_procedure()` now extracts imperative steps
DETERMINISTICALLY from the cluster's own evidence bodies (no LLM — the
distillation is reviewable and replayable), and `derive_scenario()` mints
the first validation scenario from the newest evidence. Governance is
UNCHANGED and is what makes this safe: drafts land `status: draft` in the
hook-write-protected memory/skills tree, surface through the (REPORT_ONLY-
soaking) self-improvement loop as proposals, and only the existing
`promote_draft` gate — validation-evals-green, CoS-owned — flips them.
Induction still never self-promotes; golden evals remain the promotion bar.

Usage:
    from framework.learning.skill_induction import induce_drafts

    drafts = induce_drafts(min_cluster_size=3)
    # drafts is a list of Path objects pointing at written .md files
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit
from framework.learning.experience import list_records


DEFAULT_MIN_CLUSTER = 3
DEFAULT_SCOPE_FILTER = {"this_role", "cabinet_wide"}  # narrower scopes don't generalize


def _slugify(text: str) -> str:
    """Convert text to a kebab-case slug safe for filenames."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "lesson"


def _cluster_records(
    records: list[dict[str, Any]],
    min_size: int,
    scope_filter: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Group records by (lesson_type, trigger_signal). Return clusters ≥ min_size."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        if scope_filter and r.get("applicability_scope") not in scope_filter:
            continue
        key = (r.get("lesson_type") or "", r.get("trigger_signal") or "")
        if not key[0] or not key[1]:
            continue
        groups[key].append(r)

    clusters: list[dict[str, Any]] = []
    for (lesson_type, trigger), members in groups.items():
        if len(members) < min_size:
            continue
        actors = sorted({m.get("actor") for m in members if m.get("actor")})
        scopes = sorted({m.get("applicability_scope") for m in members})
        clusters.append({
            "lesson_type": lesson_type,
            "trigger_signal": trigger,
            "size": len(members),
            "actors": actors,
            "applicability_scopes": scopes,
            "sample_bodies": [m.get("body") for m in members[:3] if m.get("body")],
            "first_seen": min(m.get("created_at", "") for m in members),
            "last_seen": max(m.get("created_at", "") for m in members),
        })
    clusters.sort(key=lambda c: (-c["size"], c["lesson_type"], c["trigger_signal"]))
    return clusters


_IMPERATIVE_CUES = re.compile(
    r"(?i)\b(always|never|must(?: not)?|should(?: not)?|use|run|check|"
    r"prefer|avoid|ensure|verify|gather|read|write|wait|before|after|"
    r"instead|do not|don't)\b")
_MAX_STEPS = 7
_MIN_STEP_CHARS = 15
_MAX_STEP_CHARS = 300


def distill_procedure(bodies: list[str]) -> list[str]:
    """Imperative steps distilled DETERMINISTICALLY from evidence bodies.

    Sentence-splits each body and keeps directive sentences (imperative-cue
    match), deduped case-insensitively, capped at _MAX_STEPS. No LLM: the
    same evidence always distills to the same steps, so a reviewer can
    replay the derivation. Returns [] when the evidence carries no
    directive sentence — the caller then quotes the lessons verbatim as
    apply-this-lesson steps (a runnable floor, still evidence-grounded)."""
    steps: list[str] = []
    seen: set[str] = set()
    for body in bodies:
        for raw in re.split(r"(?<=[.!?])\s+|\n+", body or ""):
            sent = raw.strip().rstrip(".")
            if not (_MIN_STEP_CHARS <= len(sent) <= _MAX_STEP_CHARS):
                continue
            if not _IMPERATIVE_CUES.search(sent):
                continue
            key = sent.lower()
            if key in seen:
                continue
            seen.add(key)
            steps.append(sent)
            if len(steps) >= _MAX_STEPS:
                return steps
    return steps


def derive_scenario(cluster: dict[str, Any]) -> str:
    """The first validation scenario, minted from the newest evidence so the
    promotion gate has a concrete case to run (authoring more remains the
    validator's job)."""
    newest = (cluster.get("sample_bodies") or [""])[0] or ""
    newest = " ".join(newest.split())[:220]
    return (f"Scenario 1 (auto-derived): the signal "
            f"\"{cluster['trigger_signal']}\" appears again -> apply the "
            f"Procedure; success = the recorded failure mode does not recur "
            f"(evidence: {newest or 'see Origin section'}).")


def _skills_evolved_dir() -> Path:
    root = Path(os.environ.get("CABINET_ROOT", Path(__file__).parent.parent.parent))
    return root / "memory" / "skills" / "evolved"


def _draft_skill_yaml(cluster: dict[str, Any]) -> tuple[str, str]:
    """Build a RUNNABLE draft SKILL.md from a cluster. Returns (filename, body)."""
    slug = f"induced-{cluster['lesson_type']}-{_slugify(cluster['trigger_signal'])}"
    filename = f"{slug}.md"
    actors_str = ", ".join(cluster["actors"]) or "(unknown)"
    bodies_block = ""
    for i, b in enumerate(cluster["sample_bodies"], start=1):
        bodies_block += f"\n#### Sample evidence #{i}\n\n{b}\n"

    # §4.2: runnable draft — distill the procedure from the evidence itself.
    steps = distill_procedure(cluster.get("sample_bodies") or [])
    distilled = bool(steps)
    if not steps:
        steps = [f"Apply the recorded lesson: {' '.join((b or '').split())[:200]}"
                 for b in (cluster.get("sample_bodies") or []) if b][:_MAX_STEPS]
    steps_block = "\n".join(f"{i}. {st}." for i, st in enumerate(steps, 1)) \
        or "1. (no evidence bodies — validator must author the procedure)"
    scenario = derive_scenario(cluster)

    body = f"""---
name: {slug}
description: Induced skill from {cluster['size']} matching experience records — trigger: "{cluster['trigger_signal']}" ({cluster['lesson_type']}). Status: draft — must pass golden eval before promotion.
status: draft
author: skill_induction
date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
validated_against: []
usage_count: 0
induction:
  procedure_distilled: {str(distilled).lower()}
  distilled_steps: {len(steps)}
  cluster_size: {cluster['size']}
  trigger_signal: "{cluster['trigger_signal']}"
  lesson_type: {cluster['lesson_type']}
  applicability_scopes: {cluster['applicability_scopes']}
  actors: {cluster['actors']}
  first_seen: "{cluster['first_seen']}"
  last_seen: "{cluster['last_seen']}"
---

# Induced Skill: {cluster['trigger_signal']}

> **Status: DRAFT.** Generated by `framework.learning.skill_induction` from
> {cluster['size']} matching experience records by: {actors_str}. CoS must
> validate against a golden eval before promoting to `status: validated`.

## When to use

The signal "{cluster['trigger_signal']}" has been observed {cluster['size']}
times across {len(cluster['actors'])} officer(s). When you encounter the
same signal, this skill's procedure should apply.

## Procedure

{"Distilled DETERMINISTICALLY from the cluster's evidence bodies (replayable — no LLM). The validator edits, reorders, or extends during review; promotion still requires the eval below." if distilled else "No directive sentences in the evidence — each lesson is quoted as a runnable floor. The validator should rewrite these into imperative steps during review."}

{steps_block}

## Expected Outcome

The recurring signal "{cluster['trigger_signal']}" stops producing the
failure mode recorded in the evidence ({cluster['size']} occurrences,
{cluster['first_seen'][:10]} → {cluster['last_seen'][:10]}).

## Validation Scenarios

(Auto-derived scenario 1 below; author more before promotion if the
procedure carries more than one behavior.)

- {scenario}

## Origin

Induced from these experience records (matched on
lesson_type={cluster['lesson_type']} + trigger_signal="{cluster['trigger_signal']}"):
{bodies_block}
"""
    return filename, body


def induce_drafts(
    min_cluster_size: int = DEFAULT_MIN_CLUSTER,
    scope_filter: set[str] | None = None,
    actor: str = "skill_induction",
) -> list[Path]:
    """Cluster experience records → draft new skill files in memory/skills/evolved/.

    Returns the list of written file paths. Idempotent: if a DRAFT with the
    same induced slug exists, the file is overwritten with the latest cluster
    data (so re-running refreshes evidence). A skill that has left `status:
    draft` (promoted to validated, retired, ...) is NEVER overwritten —
    re-induction must not clobber promotion metadata or validator edits back
    to draft (only the CoS-owned promotion gate flips status, never this pass).
    """
    records = list_records()
    scope_filter = scope_filter or DEFAULT_SCOPE_FILTER
    clusters = _cluster_records(records, min_cluster_size, scope_filter)

    skills_dir = _skills_evolved_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for cluster in clusters:
        filename, body = _draft_skill_yaml(cluster)
        path = skills_dir / filename
        if path.exists() and draft_status(path) not in (None, "draft"):
            continue  # promoted/retired skill — never re-stamp back to draft
        path.write_text(body)
        written.append(path)
        emit("digest_published", actor=actor, payload={
            "kind": "skill_induction_draft",
            "skill_slug": path.stem,
            "cluster_size": cluster["size"],
            "lesson_type": cluster["lesson_type"],
            "trigger_signal": cluster["trigger_signal"],
        })
    return written


def draft_status(path: Path) -> str | None:
    """The frontmatter `status:` of a skill file, or None when unreadable /
    not a frontmatter skill. Read-only."""
    try:
        text = Path(path).read_text()
    except OSError:
        return None
    parts = text.split("---", 2)
    if len(parts) < 3 or text.lstrip()[:3] != "---":
        return None
    for line in parts[1].splitlines():
        if line.strip().startswith("status:"):
            return line.split(":", 1)[1].strip() or None
    return None


def promote_draft(path: Path, *, promoted_by: str = "self_improvement_loop") -> bool:
    """Flip a draft skill's frontmatter `status: draft` → `status: validated`
    [sovereign spec §3 "skill promotion via CoS loop": validation-evals-green
    ⇒ auto-promote]. A Ring-2 file rewrite under the same uid — no root, no
    germline. Returns True iff the flip landed; False (never raises) when the
    file is missing, malformed, or not in `draft` status (a validated or
    retired skill is never re-stamped)."""
    try:
        p = Path(path)
        text = p.read_text()
        parts = text.split("---", 2)
        if len(parts) < 3 or text.lstrip()[:3] != "---":
            return False
        fm_lines = parts[1].splitlines()
        flipped = False
        for i, line in enumerate(fm_lines):
            if line.strip() == "status: draft":
                fm_lines[i] = line.replace("status: draft", "status: validated")
                flipped = True
                break
        if not flipped:
            return False
        fm_lines.append(f"promoted_by: {promoted_by}")
        fm_lines.append(
            f"promoted_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
        p.write_text("---".join([parts[0], "\n".join(fm_lines) + "\n", parts[2]]))
        return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Induce draft skills from clusters of experience records."
    )
    parser.add_argument("--min-cluster-size", type=int, default=DEFAULT_MIN_CLUSTER)
    parser.add_argument("--all-scopes", action="store_true",
                        help="Include this_task + this_mission scopes too "
                             "(default: only this_role + cabinet_wide)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Cluster only; do not write drafts")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    scope_filter = None if args.all_scopes else DEFAULT_SCOPE_FILTER

    records = list_records()
    clusters = _cluster_records(records, args.min_cluster_size, scope_filter)

    if args.dry_run:
        out = clusters
    else:
        drafts = induce_drafts(
            min_cluster_size=args.min_cluster_size,
            scope_filter=scope_filter,
        )
        out = [{"cluster": c, "draft": str(d)} for c, d in zip(clusters, drafts)]

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    elif not clusters:
        print(f"skill-induction: no clusters of size ≥ {args.min_cluster_size}")
    else:
        print(f"skill-induction: {len(clusters)} cluster(s) "
              f"{'identified' if args.dry_run else 'drafted'}")
        for c in clusters:
            print(f"  → {c['lesson_type']} / \"{c['trigger_signal']}\" "
                  f"({c['size']} records, actors: {', '.join(c['actors'])})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
