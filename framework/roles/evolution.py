"""Role evolution proposal generator — converts failure patterns into draft amendments.

Phase 2.3 of the convergence plan. Reads pattern flags from
``framework.measurement.eval_pattern_detector`` and writes draft YAML
amendments to ``instance/roles/proposals/`` for Captain review.

A pattern whose only candidate is a SKELETON — a template still carrying a
``<TODO:`` marker, or one of the three kinds that ask someone to decide rather
than describe a change — writes NO file and emits NO event. One keyed
capability gap is recorded instead and ``propose_one`` returns None: an
operator can act on "no concrete candidate exists here", and cannot act on a
form. Heuristics map failure_type → suggested change:

  missing_skill     → propose adding a hat with capability targeting the gap
  wrong_authority   → propose extending charter authority_boundaries
  scope_confusion   → flag for Captain decision (split or refocus the role)
  quality_gap       → propose adding a quality_review hat
  runtime_error     → flag for engineering investigation (not a role change)

Captain DM is **stubbed** in this phase: a `role_evolution_proposed` event
is emitted to the ledger; Phase 3 wires Telegram delivery.

Usage:
    from framework.roles.evolution import propose_from_patterns

    paths = propose_from_patterns(actor="role_eval_cron")
    # paths is a list of (proposal_path, pattern_dict) tuples
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit
from framework.learning.capability_gaps import record_gap
from framework.measurement.eval_pattern_detector import detect_patterns
from framework.roles.lifecycle import load_role


# The placeholder marker, and the one definition both sides screen on: the
# writer below refuses to WRITE one, and the loop's auto-apply gate
# (self_improvement_loop._proposal_is_concrete) refuses to APPLY one. Kept
# here, next to the templates that carry it, so the two can never drift —
# which is what makes the markers a fail-closed default rather than decoration
# (contract §6, amendment A6.1: stripping them from the templates below makes
# every template-derived add_hat / expand_authority auto-applicable).
TODO_RE = re.compile(r"<TODO:[^>]*>")

# Kinds that ask a person to decide. They carry no change to apply, so a file
# plus a role_charter_changed event announce something nobody can act on.
_THINK_ONLY_KINDS = frozenset({
    "captain_decision_split_or_refocus",
    "engineering_investigation",
    "annotate_evals",
})

# failure_type → capability-gap kind. These three kinds are surface-only:
# route_open_gaps counts them and routes them nowhere (contract §3) — a
# missing skill, permission or fact is not something this loop can build.
_GAP_KIND_BY_FAILURE = {
    "missing_skill": "skill",
    "quality_gap": "skill",
    "wrong_authority": "authority",
}
_DEFAULT_GAP_KIND = "information"


# Map failure_type → (suggestion_kind, suggestion_template). Every SHIPPED
# template is a skeleton — it carries a `<TODO:` marker or a decide-this kind —
# so none of them reaches disk any more: each becomes one capability gap (§6).
# The markers are load-bearing rather than decoration, and stay: they are what
# holds a template-derived amendment back from auto-apply (A6.1). A template
# with every field filled in still writes and emits exactly as before.
_SUGGESTION_TEMPLATES: dict[str, dict[str, Any]] = {
    "missing_skill": {
        "kind": "add_hat",
        "rationale": "Eval failures suggest a recurring skill gap. Adding a hat "
                     "with focused capabilities is the lowest-friction adaptation.",
        "hat_template": {
            "name": "<TODO: short hat name>",
            "description": "<TODO: what the hat lets this role do>",
            "capabilities": ["<TODO: new capability tags>"],
            "expires_at": None,
        },
    },
    "wrong_authority": {
        "kind": "expand_authority",
        "rationale": "Evals failed because the role's charter didn't cover the "
                     "action. Captain to decide whether to extend authority "
                     "or remove the action from the eval set.",
        "authority_template": {
            "scope_to_add": "<TODO: describe scope>",
            "reasoning": "<TODO: why this is safe to grant>",
        },
    },
    "scope_confusion": {
        "kind": "captain_decision_split_or_refocus",
        "rationale": "Multiple failure modes suggest the role's scope is too "
                     "broad. Captain to decide: split into two roles, refocus, "
                     "or merge into a sibling.",
        "options": [
            "split_into_two_roles",
            "refocus_existing_role",
            "merge_into_sibling",
        ],
    },
    "quality_gap": {
        "kind": "add_quality_hat",
        "rationale": "Output meets functional requirements but misses quality bar.",
        "hat_template": {
            "name": "quality_review_<TODO: domain>",
            "description": "Pre-flight quality check on outputs in this domain",
            "capabilities": ["reviews_<TODO: domain tag>"],
            "expires_at": None,
        },
    },
    "runtime_error": {
        "kind": "engineering_investigation",
        "rationale": "Runtime errors are framework bugs, not role-charter issues.",
        "next_step": "Open a Cabinet framework GitHub issue.",
    },
    "unspecified": {
        "kind": "annotate_evals",
        "rationale": "Failures aren't annotated with a failure_type — improve "
                     "the affected evals' verify() return values first.",
        "next_step": "Update the failing evals to include failure_type tuples.",
    },
}


def _proposals_dir(cabinet_root: str | None = None) -> Path:
    if cabinet_root is None:
        cabinet_root = os.environ.get(
            "CABINET_ROOT",
            str(Path(__file__).parent.parent.parent),
        )
    return Path(cabinet_root) / "instance" / "roles" / "proposals"


def _slugify_pattern(pattern: dict[str, Any]) -> str:
    """Stable kebab-case id derived from role + failure_type."""
    return f"{pattern['role_slug']}-{pattern['failure_type'].replace('_', '-')}"


def _serialize_yaml(data: dict[str, Any]) -> str:
    """Minimal YAML emitter sufficient for proposals (avoid adding deps)."""
    try:
        import yaml as _yaml
        return _yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    except (ImportError, AttributeError):
        # Fallback to JSON wrapped in YAML's allowed superset
        return json.dumps(data, indent=2)


def draft_amendment(
    pattern: dict[str, Any],
    cabinet_root: str | None = None,
) -> dict[str, Any]:
    """Build a YAML-serializable proposal dict for a flagged pattern."""
    role_slug = pattern["role_slug"]
    failure_type = pattern["failure_type"]

    # Current charter (if the role still exists). Retired roles can still
    # have patterns flagged — we'll just include null in those cases.
    try:
        role = load_role(role_slug, cabinet_root=cabinet_root)
    except TypeError:
        # Older signature
        role = load_role(role_slug)
    current_charter = {
        "mission": role.get("charter") if role else None,
        "capabilities": role.get("capabilities") if role else None,
        "authority_level": role.get("authority_level") if role else None,
        "status": role.get("status") if role else None,
    }

    template = _SUGGESTION_TEMPLATES.get(failure_type, _SUGGESTION_TEMPLATES["unspecified"])

    return {
        "proposal_id": _slugify_pattern(pattern),
        "role_slug": role_slug,
        "proposed_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_captain_approval",
        "trigger": {
            "failure_type": failure_type,
            "count": pattern["count"],
            "first_seen": pattern["first_seen"],
            "last_seen": pattern["last_seen"],
            "eval_names": pattern["eval_names"],
            "sample_failed_assertions": pattern.get("sample_failed_assertions", []),
        },
        "current_charter": current_charter,
        "suggested_change": template,
    }


def skeleton_reason(amendment: dict[str, Any]) -> str | None:
    """Why this amendment is a skeleton, or None when it is concrete."""
    kind = (amendment.get("suggested_change") or {}).get("kind")
    if kind in _THINK_ONLY_KINDS:
        return f"kind={kind} carries no change to apply"
    if TODO_RE.search(json.dumps(amendment, default=str)):
        return "contains <TODO:> placeholders"
    return None


def propose_one(
    pattern: dict[str, Any],
    actor: str = "role_evolution",
    cabinet_root: str | None = None,
    gaps_out: list[dict[str, Any]] | None = None,
) -> Path | None:
    """Write a draft amendment to disk + emit event. Returns the file path.

    A SKELETON amendment writes nothing, emits nothing and returns None: it
    records one capability gap keyed on (role, failure_type), so the same
    unanswerable pattern costs one row however often it is observed.

    If a proposal with the same proposal_id already exists, it is overwritten
    (latest pattern data wins). This is intentional — re-running the cron
    after the Captain has touched the proposal would otherwise litter the
    proposals dir with duplicates.
    """
    amendment = draft_amendment(pattern, cabinet_root=cabinet_root)
    proposal_id = amendment["proposal_id"]
    proposal_path = _proposals_dir(cabinet_root) / f"{proposal_id}.yml"

    why = skeleton_reason(amendment)
    if why is not None:
        role_slug = amendment["role_slug"]
        failure_type = pattern["failure_type"]
        gap = record_gap(
            need=f"no concrete improvement candidate for {role_slug}: {failure_type}",
            kind=_GAP_KIND_BY_FAILURE.get(failure_type, _DEFAULT_GAP_KIND),
            evidence=json.dumps(amendment.get("trigger") or {}, default=str),
            recorded_by=actor,
            dedup_key=f"evolution:{role_slug}:{failure_type}",
        )
        if gaps_out is not None:
            gaps_out.append({
                "gap_id": gap.get("gap_id"),
                "role_slug": role_slug,
                "failure_type": failure_type,
                "kind": gap.get("kind"),
                "reason": why,
                # A skeleton written before this behaviour landed. Nothing
                # rewrites or applies it; the count is how an operator learns
                # it is still sitting there.
                "existing_skeleton": proposal_path.exists(),
            })
        return None

    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(_serialize_yaml(amendment))

    emit("role_charter_changed", actor=actor, payload={
        "role_slug": amendment["role_slug"],
        "proposal_id": proposal_id,
        "proposal_path": str(proposal_path),
        "status": "pending_captain_approval",
        "failure_type": pattern["failure_type"],
        "trigger_count": pattern["count"],
    })

    return proposal_path


def propose_from_patterns(
    window_days: int = 28,
    min_occurrences: int = 3,
    actor: str = "role_evolution",
    cabinet_root: str | None = None,
    gaps_out: list[dict[str, Any]] | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    """Detect patterns and propose. Returns the WRITTEN proposals only.

    `gaps_out`, when given, collects one dict per skeleton pattern routed to a
    capability gap — the caller's only channel to them, since the return value
    stays exactly what its name says.
    """
    patterns = detect_patterns(
        window_days=window_days,
        min_occurrences=min_occurrences,
    )
    out: list[tuple[Path, dict[str, Any]]] = []
    for pat in patterns:
        path = propose_one(pat, actor=actor, cabinet_root=cabinet_root,
                           gaps_out=gaps_out)
        if path is not None:
            out.append((path, pat))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate role evolution proposals from eval failure patterns."
    )
    parser.add_argument("--window-days", type=int, default=28)
    parser.add_argument("--min-occurrences", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    gaps: list[dict[str, Any]] = []
    proposed = propose_from_patterns(
        window_days=args.window_days,
        min_occurrences=args.min_occurrences,
        gaps_out=gaps,
    )

    if args.json:
        # An object, not the bare proposal list it used to print: a run whose
        # patterns all became gaps has something to report and `[]` said none.
        print(json.dumps({
            "proposals": [
                {
                    "proposal_path": str(p),
                    "proposal_id": pat["role_slug"] + "-" + pat["failure_type"].replace("_", "-"),
                    "role_slug": pat["role_slug"],
                    "failure_type": pat["failure_type"],
                    "count": pat["count"],
                }
                for p, pat in proposed
            ],
            "gaps": gaps,
        }, indent=2))
    elif not proposed and not gaps:
        print(
            f"role-evolution: no patterns to propose "
            f"(window={args.window_days}d, threshold={args.min_occurrences})"
        )
    else:
        print(f"role-evolution: {len(proposed)} proposal(s) drafted, "
              f"{len(gaps)} gap(s) recorded")
        for path, pat in proposed:
            print(f"  → {path}  [{pat['role_slug']}, {pat['failure_type']}]")
        for gap in gaps:
            print(f"  ◇ {gap['gap_id']}  [{gap['role_slug']}, "
                  f"{gap['failure_type']}, {gap['kind']}] {gap['reason']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
