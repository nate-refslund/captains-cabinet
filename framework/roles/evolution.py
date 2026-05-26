"""Role evolution proposal generator — converts failure patterns into draft amendments.

Phase 2.3 of the convergence plan. Reads pattern flags from
``framework.measurement.eval_pattern_detector`` and writes draft YAML
amendments to ``instance/roles/proposals/`` for Captain review.

The generator produces SKELETONS — enough structured context that a Captain
review (manual or AI-assisted) can decide whether to ratify. Heuristics map
failure_type → suggested change:

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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit
from framework.measurement.eval_pattern_detector import detect_patterns
from framework.roles.lifecycle import load_role


# Map failure_type → (suggestion_kind, suggestion_template) used to seed the
# proposal skeleton. Skeletons are intentionally underspecified — Captain
# fills in the gaps; this module only ensures the right shape lands on disk.
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
            "name": "quality_review_<TODO>",
            "description": "Pre-flight quality check on outputs in this domain",
            "capabilities": ["reviews_<TODO>"],
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


def propose_one(
    pattern: dict[str, Any],
    actor: str = "role_evolution",
    cabinet_root: str | None = None,
) -> Path:
    """Write a draft amendment to disk + emit event. Returns the file path.

    If a proposal with the same proposal_id already exists, it is overwritten
    (latest pattern data wins). This is intentional — re-running the cron
    after the Captain has touched the proposal would otherwise litter the
    proposals dir with duplicates.
    """
    proposals_dir = _proposals_dir(cabinet_root)
    proposals_dir.mkdir(parents=True, exist_ok=True)

    amendment = draft_amendment(pattern, cabinet_root=cabinet_root)
    proposal_id = amendment["proposal_id"]
    proposal_path = proposals_dir / f"{proposal_id}.yml"

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
) -> list[tuple[Path, dict[str, Any]]]:
    """Detect patterns and emit a draft proposal for each. Returns the list."""
    patterns = detect_patterns(
        window_days=window_days,
        min_occurrences=min_occurrences,
    )
    out: list[tuple[Path, dict[str, Any]]] = []
    for pat in patterns:
        path = propose_one(pat, actor=actor, cabinet_root=cabinet_root)
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

    proposed = propose_from_patterns(
        window_days=args.window_days,
        min_occurrences=args.min_occurrences,
    )

    if args.json:
        print(json.dumps([
            {
                "proposal_path": str(p),
                "proposal_id": pat["role_slug"] + "-" + pat["failure_type"].replace("_", "-"),
                "role_slug": pat["role_slug"],
                "failure_type": pat["failure_type"],
                "count": pat["count"],
            }
            for p, pat in proposed
        ], indent=2))
    elif not proposed:
        print(
            f"role-evolution: no patterns to propose "
            f"(window={args.window_days}d, threshold={args.min_occurrences})"
        )
    else:
        print(f"role-evolution: {len(proposed)} proposal(s) drafted")
        for path, pat in proposed:
            print(f"  → {path}  [{pat['role_slug']}, {pat['failure_type']}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
