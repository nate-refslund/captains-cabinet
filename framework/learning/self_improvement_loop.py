"""Self-improvement closed loop — turns eval signal into applied learning.

R8 of the convergence plan. The Cabinet has all the parts of a learning loop
already implemented:

  * ``framework.measurement.role_eval_runner`` — runs role evals, emits
    ``eval_passed`` / ``eval_failed`` events
  * ``framework.measurement.eval_pattern_detector`` — clusters failures
  * ``framework.roles.evolution`` — drafts charter amendment proposals
  * ``framework.roles.hat_graduation`` — promotes hats with ≥N uses
  * ``framework.learning.skill_induction`` — drafts skills from experience
    record clusters
  * ``framework.measurement.scenario_runner`` — validates the org-as-a-system
  * ``memory/golden-evals/framework/*.sh`` — safety guard tests

…but pre-R8 they did not chain together. ``role-evals-weekly.sh`` ran evals
plus pattern detection and then exited; nothing consumed the resulting
proposals or candidates. This module ties the chain end-to-end and
**auto-applies** validated learnings (per the user directive that the
framework MUST NOT require Captain mid-loop approval).

Loop shape::

    eval results
       │  (role_eval_runner — already happened upstream when this is called
       │   from the weekly cron, or we invoke it here for ad-hoc runs)
       ▼
    pattern detection
       │  (eval_pattern_detector.detect_patterns)
       ▼
    evolution proposal
       │  (roles.evolution.propose_from_patterns → instance/roles/proposals/)
       ▼
    validation gate
       │  (scenario evals — role + learning categories  +  golden eval shells)
       ▼
    AUTO-APPLY accepted proposals
       │  (roles.lifecycle.adapt_role  +  emit role_evolved with
       │   captain_auto_ratified=True)
       │
       ▼
    hat graduation candidates
       │  (roles.hat_graduation.propose_graduations
       │   → validate → adapt_role(capability_added) per granted cap
       │   → emit role_hat_promoted with status=auto_applied)
       ▼
    skill induction
       │  (learning.skill_induction.induce_drafts → memory/skills/evolved/)
       │   → validation = file exists, frontmatter parses, body non-empty
       │   → emit skill_promoted with status=draft_promoted
       ▼
    loop completed

Every stage emits an event so the dashboard, audits, and the Captain can
replay what was auto-applied at any time. The ``self_improvement_loop_started``
and ``self_improvement_loop_completed`` events bracket each run so multiple
auto-applied changes inside the same loop can be grouped by ``parent_id``.

The loop is conservative by construction:

  1. A proposal is only **applied** if it is fully specified (no ``<TODO:>``
     placeholders) and passes validation. The default suggestion templates in
     ``roles.evolution`` are skeletons with ``<TODO:>`` markers — those are
     skipped, with the proposal staying on disk as ``pending_captain_approval``
     for manual review later.
  2. Hat graduations only proceed for hats that have at least one concrete
     capability to promote — otherwise there is nothing to apply.
  3. Skill induction always writes drafts (never auto-promotes them to
     ``validated`` status); the validation gate only confirms the draft is
     well-formed and emits ``skill_promoted`` so dashboards see the new draft.

CLI::

    python3 -m framework.learning.self_improvement_loop                # full loop
    python3 -m framework.learning.self_improvement_loop --dry-run      # detect+plan, no writes
    python3 -m framework.learning.self_improvement_loop --json         # JSON report
    python3 -m framework.learning.self_improvement_loop --skip-evals   # don't re-run role evals
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure framework root is importable when invoked as a module or script.
_FRAMEWORK_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit  # noqa: E402
from framework.learning.skill_induction import induce_drafts  # noqa: E402
from framework.measurement.scenario_runner import run_all as run_all_scenarios  # noqa: E402
from framework.roles.evolution import propose_from_patterns  # noqa: E402
from framework.roles.hat_graduation import propose_graduations  # noqa: E402
from framework.roles.lifecycle import adapt_role, load_role  # noqa: E402

try:  # YAML is already a hard dep of the framework — guarded for paranoid envs
    from yaml import safe_dump as _yaml_dump
    from yaml import safe_load as _yaml_load
except ImportError:  # pragma: no cover — defended just in case
    _yaml_load = None  # type: ignore[assignment]
    _yaml_dump = None  # type: ignore[assignment]


_TODO_RE = re.compile(r"<TODO:[^>]*>")


def _cabinet_root() -> Path:
    return Path(os.environ.get("CABINET_ROOT", _FRAMEWORK_ROOT))


def _proposals_dir() -> Path:
    return _cabinet_root() / "instance" / "roles" / "proposals"


def _golden_evals_dir() -> Path:
    return _cabinet_root() / "memory" / "golden-evals" / "framework"


# ---------------------------------------------------------------------------
# Validation gate
# ---------------------------------------------------------------------------


def _run_scenario_evals_for_validation() -> tuple[bool, list[dict[str, Any]]]:
    """Run the role + learning scenario evals as the org-level safety gate.

    Returns (all_passed, results-as-dict-list). Other scenario categories
    (mission, policy, memory, recovery, outcome) are out of scope — we are
    validating that adapting roles and applying learning doesn't break the
    org's adaptation discipline itself.
    """
    relevant = []
    for category in ("role", "learning"):
        relevant.extend(run_all_scenarios(category=category))
    all_passed = all(r.passed for r in relevant) if relevant else True
    return all_passed, [r.to_dict() for r in relevant]


def _run_golden_eval_shells() -> tuple[bool, list[dict[str, Any]]]:
    """Run the framework safety shell tests (kill-switch, spending, stop-guard).

    Each shell test prints its own pass/fail; we capture exit codes and a
    short tail of stdout for the report. If the directory is missing or
    empty we treat the gate as a no-op (passed=True, results=[]).
    """
    gdir = _golden_evals_dir()
    if not gdir.exists():
        return True, []
    results: list[dict[str, Any]] = []
    all_passed = True
    for sh in sorted(gdir.glob("*.sh")):
        try:
            cp = subprocess.run(
                ["/bin/bash", str(sh)],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "CABINET_SUPPRESS_OUTPUT": "1"},
            )
            passed = cp.returncode == 0
            results.append({
                "script": sh.name,
                "passed": passed,
                "returncode": cp.returncode,
                "stdout_tail": (cp.stdout or "").strip().splitlines()[-5:],
                "stderr_tail": (cp.stderr or "").strip().splitlines()[-5:],
            })
            if not passed:
                all_passed = False
        except Exception as e:  # noqa: BLE001
            results.append({"script": sh.name, "passed": False, "error": str(e)})
            all_passed = False
    return all_passed, results


def _validation_gate() -> tuple[bool, dict[str, Any]]:
    """Combined scenario + golden eval gate. Cached per loop run.

    Critically, scenario evals (e.g. ``role_adaptation``, ``role_retirement``)
    mutate ``CABINET_ROOT`` and ``CABINET_EVENT_LOG_DIR`` in their setup
    functions so they can run in temp dirs without touching the live ledger.
    That mutation persists in ``os.environ`` after they finish, which would
    bleed into the rest of the loop (lifecycle calls would resolve to a
    deleted temp dir, every role would appear "not loadable"). We snapshot
    and restore the affected env vars so the gate is a pure observation.
    """
    snapshot_keys = ("CABINET_ROOT", "CABINET_EVENT_LOG_DIR")
    snapshot = {k: os.environ.get(k) for k in snapshot_keys}
    try:
        scen_ok, scen = _run_scenario_evals_for_validation()
        gold_ok, gold = _run_golden_eval_shells()
    finally:
        for k, v in snapshot.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return scen_ok and gold_ok, {
        "scenario_evals": scen,
        "golden_evals": gold,
        "scenario_passed": scen_ok,
        "golden_passed": gold_ok,
    }


# ---------------------------------------------------------------------------
# Proposal application
# ---------------------------------------------------------------------------


def _proposal_is_concrete(proposal: dict[str, Any]) -> tuple[bool, str]:
    """A proposal is auto-applicable only if it has no <TODO:> placeholders.

    Captain-decision proposals (`scope_confusion`, `runtime_error`,
    `unspecified`) are also held back — they require human judgement, not a
    code path.
    """
    suggested = proposal.get("suggested_change") or {}
    kind = suggested.get("kind")
    if kind in ("captain_decision_split_or_refocus",
                "engineering_investigation",
                "annotate_evals"):
        return False, f"kind={kind} requires Captain decision"

    serialized = json.dumps(proposal, default=str)
    if _TODO_RE.search(serialized):
        return False, "contains <TODO:> placeholders"
    return True, "ok"


def _apply_proposal(
    proposal: dict[str, Any],
    parent_event_id: str,
    actor: str,
) -> tuple[bool, str]:
    """Apply one concrete proposal to the role on disk.

    Returns (applied, reason). Emits role_evolved on success.
    """
    role_slug = proposal["role_slug"]
    suggested = proposal["suggested_change"]
    kind = suggested.get("kind")

    role = load_role(role_slug)
    if role is None:
        return False, f"role {role_slug} not loadable"

    changes_applied: list[dict[str, Any]] = []
    try:
        if kind == "add_hat":
            tmpl = suggested.get("hat_template") or {}
            for cap in tmpl.get("capabilities", []):
                if cap and not str(cap).startswith("<TODO"):
                    adapt_role(
                        role_slug,
                        adaptation_type="capability_added",
                        description=f"self-improvement: added {cap} (from hat {tmpl.get('name')})",
                        changes={"capability": cap},
                        evidence=f"proposal {proposal['proposal_id']}",
                        rationale=suggested.get("rationale"),
                        approved_by="self_improvement_loop",
                    )
                    changes_applied.append({"capability_added": cap})
        elif kind == "expand_authority":
            scope = (suggested.get("authority_template") or {}).get("scope_to_add")
            if scope and not str(scope).startswith("<TODO"):
                adapt_role(
                    role_slug,
                    adaptation_type="authority_change",
                    description=f"self-improvement: expanded authority ({scope})",
                    changes={"authority_level": scope},
                    evidence=f"proposal {proposal['proposal_id']}",
                    rationale=suggested.get("rationale"),
                    approved_by="self_improvement_loop",
                )
                changes_applied.append({"authority_change": scope})
        elif kind == "add_quality_hat":
            for cap in (suggested.get("hat_template") or {}).get("capabilities", []):
                if cap and not str(cap).startswith("<TODO"):
                    adapt_role(
                        role_slug,
                        adaptation_type="capability_added",
                        description=f"self-improvement: added quality-review capability {cap}",
                        changes={"capability": cap},
                        evidence=f"proposal {proposal['proposal_id']}",
                        rationale=suggested.get("rationale"),
                        approved_by="self_improvement_loop",
                    )
                    changes_applied.append({"capability_added": cap})
        else:
            return False, f"kind={kind} has no auto-apply handler"
    except Exception as e:  # noqa: BLE001
        return False, f"adapt_role failed: {e}"

    if not changes_applied:
        return False, "nothing concrete to apply"

    emit("role_evolved", actor=actor, parent_id=parent_event_id, payload={
        "role_slug": role_slug,
        "proposal_id": proposal["proposal_id"],
        "failure_type": (proposal.get("trigger") or {}).get("failure_type"),
        "kind": kind,
        "changes_applied": changes_applied,
        "captain_auto_ratified": True,
        "ratification_note": (
            "Captain auto-ratified via self-improvement loop per framework "
            "directive (no manual approval required)."
        ),
    })
    return True, "applied"


def _stamp_proposal_status(proposal_path: Path, status: str, note: str) -> None:
    """Rewrite the proposal YAML to record the loop's verdict."""
    if not proposal_path.exists() or _yaml_load is None or _yaml_dump is None:
        return
    try:
        with open(proposal_path) as f:
            data = _yaml_load(f) or {}
    except Exception:  # noqa: BLE001
        return
    data["status"] = status
    data["self_improvement_loop"] = {
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
    }
    with open(proposal_path, "w") as f:
        _yaml_dump(data, f, sort_keys=False, default_flow_style=False)


# ---------------------------------------------------------------------------
# Hat graduation application
# ---------------------------------------------------------------------------


def _apply_hat_graduations(
    candidates: list[dict[str, Any]],
    parent_event_id: str,
    actor: str,
) -> list[dict[str, Any]]:
    """Promote each hat's capabilities to base capabilities on the role."""
    applied: list[dict[str, Any]] = []
    for c in candidates:
        role_slug = c["role_slug"]
        if load_role(role_slug) is None:
            continue
        promoted_caps: list[str] = []
        for cap in c.get("capabilities_to_promote", []):
            if not cap:
                continue
            try:
                adapt_role(
                    role_slug,
                    adaptation_type="capability_added",
                    description=f"self-improvement: hat {c['hat_slug']} graduated → {cap}",
                    changes={"capability": cap},
                    evidence=(
                        f"hat used {c['uses']} times across "
                        f"{c['missions']} missions without OVI regression"
                    ),
                    rationale="Hat graduation criteria met (R8 auto-apply)",
                    approved_by="self_improvement_loop",
                )
                promoted_caps.append(cap)
            except Exception:  # noqa: BLE001
                # adapt_role already idempotent for duplicate caps; ignore and continue
                continue
        if promoted_caps:
            emit("role_hat_promoted", actor=actor, parent_id=parent_event_id, payload={
                **c,
                "status": "auto_applied",
                "captain_auto_ratified": True,
                "capabilities_promoted": promoted_caps,
            })
            applied.append({
                "role_slug": role_slug,
                "hat_slug": c["hat_slug"],
                "capabilities_promoted": promoted_caps,
            })
    return applied


# ---------------------------------------------------------------------------
# Skill promotion (draft passes well-formedness gate)
# ---------------------------------------------------------------------------


def _validate_skill_draft(path: Path) -> tuple[bool, str]:
    """A draft is 'promoted' to a tracked draft if file is well-formed."""
    if not path.exists():
        return False, "missing"
    try:
        text = path.read_text()
    except OSError as e:
        return False, f"unreadable: {e}"
    if not text.strip():
        return False, "empty"
    # Frontmatter check: must start with ---
    if not text.lstrip().startswith("---"):
        return False, "no frontmatter"
    # Must have a body after the frontmatter close
    parts = text.split("---", 2)
    if len(parts) < 3 or not parts[2].strip():
        return False, "no body after frontmatter"
    return True, "ok"


def _apply_skill_inductions(
    drafted_paths: list[Path],
    parent_event_id: str,
    actor: str,
) -> list[dict[str, Any]]:
    promoted: list[dict[str, Any]] = []
    for p in drafted_paths:
        ok, reason = _validate_skill_draft(p)
        if not ok:
            continue
        emit("skill_promoted", actor=actor, parent_id=parent_event_id, payload={
            "skill_slug": p.stem,
            "skill_path": str(p),
            "status": "draft_promoted",
            "captain_auto_ratified": True,
            "ratification_note": (
                "Draft skill auto-promoted to tracked draft in memory/skills/evolved/. "
                "CoS still owns final validation → status:validated before formal use."
            ),
        })
        promoted.append({"skill_slug": p.stem, "skill_path": str(p)})
    return promoted


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_loop(
    window_days: int = 28,
    min_occurrences: int = 3,
    actor: str = "self_improvement_loop",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute the closed self-improvement loop. Returns a structured report.

    The report shape is suitable for ``--json`` CLI output and includes the
    parent loop event id so an auditor can pull every child event with one
    replay filter.
    """
    loop_id = str(uuid.uuid4())
    started = emit("self_improvement_loop_started", actor=actor, payload={
        "loop_id": loop_id,
        "window_days": window_days,
        "min_occurrences": min_occurrences,
        "dry_run": dry_run,
    })
    parent_id = started["id"]

    # Stage 1 — generate evolution proposals from patterns -------------------
    proposed = propose_from_patterns(
        window_days=window_days,
        min_occurrences=min_occurrences,
        actor=actor,
    )

    proposal_report: list[dict[str, Any]] = []
    applied_proposals: list[dict[str, Any]] = []

    # One validation gate per loop is enough (the org doesn't change between
    # proposals applied in the same loop — and running the scenario evals
    # per proposal would be quadratic for no value).
    gate_ok = True
    gate_detail: dict[str, Any] = {}
    if proposed and not dry_run:
        gate_ok, gate_detail = _validation_gate()

    for path, pat in proposed:
        if _yaml_load is None:
            proposal_report.append({
                "proposal_id": Path(path).stem,
                "status": "skipped_no_yaml",
            })
            continue
        try:
            with open(path) as f:
                proposal = _yaml_load(f) or {}
        except Exception as e:  # noqa: BLE001
            proposal_report.append({
                "proposal_id": Path(path).stem,
                "status": "unreadable",
                "error": str(e),
            })
            continue

        concrete, why = _proposal_is_concrete(proposal)
        record: dict[str, Any] = {
            "proposal_id": proposal.get("proposal_id"),
            "role_slug": proposal.get("role_slug"),
            "failure_type": (proposal.get("trigger") or {}).get("failure_type"),
            "kind": (proposal.get("suggested_change") or {}).get("kind"),
            "concrete": concrete,
            "concrete_reason": why,
            "path": str(path),
        }

        if dry_run:
            record["status"] = "planned" if concrete else "skipped_skeleton"
            proposal_report.append(record)
            continue

        if not concrete:
            _stamp_proposal_status(Path(path), "pending_captain_approval",
                                   f"self-improvement-loop: not auto-applied ({why})")
            record["status"] = "pending_captain_approval"
            proposal_report.append(record)
            continue

        if not gate_ok:
            _stamp_proposal_status(Path(path), "blocked_by_validation",
                                   "self-improvement-loop: validation gate failed")
            record["status"] = "blocked_by_validation"
            record["validation_failures"] = {
                "scenario_passed": gate_detail.get("scenario_passed"),
                "golden_passed": gate_detail.get("golden_passed"),
            }
            proposal_report.append(record)
            continue

        applied, reason = _apply_proposal(proposal, parent_id, actor)
        if applied:
            _stamp_proposal_status(Path(path), "auto_applied",
                                   "self-improvement-loop: auto-applied (captain-ratified)")
            record["status"] = "auto_applied"
            applied_proposals.append(record)
        else:
            _stamp_proposal_status(Path(path), "pending_captain_approval",
                                   f"self-improvement-loop: auto-apply skipped ({reason})")
            record["status"] = "skipped_unapplicable"
            record["skip_reason"] = reason
        proposal_report.append(record)

    # Stage 2 — hat graduations ----------------------------------------------
    hat_candidates: list[dict[str, Any]] = []
    hat_applied: list[dict[str, Any]] = []
    if dry_run:
        # In dry-run, fall back to the read-only API so we don't emit events
        from framework.roles.hat_graduation import graduation_candidates
        hat_candidates = graduation_candidates()
    else:
        # propose_graduations both detects + emits role_hat_promoted (proposal)
        hat_candidates = propose_graduations(actor=actor)
        if hat_candidates:
            # Apply each candidate (idempotent inside adapt_role).
            # Re-run gate only if it wasn't already evaluated above.
            if not proposed:
                gate_ok, gate_detail = _validation_gate()
            if gate_ok:
                hat_applied = _apply_hat_graduations(hat_candidates, parent_id, actor)

    # Stage 3 — skill induction ---------------------------------------------
    drafted_paths: list[Path] = []
    skill_promoted: list[dict[str, Any]] = []
    if not dry_run:
        drafted_paths = induce_drafts(actor=actor)
        if drafted_paths:
            skill_promoted = _apply_skill_inductions(drafted_paths, parent_id, actor)
    else:
        # Dry-run: cluster without writing
        from framework.learning.skill_induction import _cluster_records  # noqa: SLF001
        from framework.learning.experience import list_records
        clusters = _cluster_records(
            list_records(),
            min_size=3,
            scope_filter={"this_role", "cabinet_wide"},
        )
        drafted_paths = [Path(f"<dry-run-cluster-{i}>") for i, _ in enumerate(clusters)]

    # Stage 4 — completion event --------------------------------------------
    summary = {
        "loop_id": loop_id,
        "window_days": window_days,
        "min_occurrences": min_occurrences,
        "dry_run": dry_run,
        "validation_gate": gate_detail if not dry_run else {"skipped": "dry_run"},
        "proposals": {
            "generated": len(proposed),
            "auto_applied": len(applied_proposals),
            "pending_captain": sum(
                1 for p in proposal_report if p.get("status") == "pending_captain_approval"
            ),
            "blocked_by_validation": sum(
                1 for p in proposal_report if p.get("status") == "blocked_by_validation"
            ),
            "detail": proposal_report,
        },
        "hat_graduations": {
            "candidates": len(hat_candidates),
            "applied": len(hat_applied),
            "detail": hat_applied,
        },
        "skill_induction": {
            "drafted": len(drafted_paths),
            "promoted": len(skill_promoted),
            "detail": skill_promoted,
        },
    }
    emit("self_improvement_loop_completed", actor=actor, parent_id=parent_id, payload=summary)
    summary["parent_event_id"] = parent_id
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Close the Cabinet self-improvement loop "
                    "(proposals → validation → auto-apply → hats → skills).",
    )
    parser.add_argument("--window-days", type=int, default=28)
    parser.add_argument("--min-occurrences", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect proposals/candidates without applying changes.")
    parser.add_argument("--json", action="store_true",
                        help="Emit the structured report as JSON to stdout.")
    args = parser.parse_args(argv)

    summary = run_loop(
        window_days=args.window_days,
        min_occurrences=args.min_occurrences,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return 0

    print("\n=== Self-improvement loop ===")
    print(f"  loop_id:           {summary['loop_id']}")
    print(f"  dry_run:           {summary['dry_run']}")
    print(f"  proposals:         {summary['proposals']['generated']} generated, "
          f"{summary['proposals']['auto_applied']} auto-applied, "
          f"{summary['proposals']['pending_captain']} pending Captain")
    print(f"  hat graduations:   {summary['hat_graduations']['candidates']} candidates, "
          f"{summary['hat_graduations']['applied']} applied")
    print(f"  skill induction:   {summary['skill_induction']['drafted']} drafted, "
          f"{summary['skill_induction']['promoted']} promoted")
    if not args.dry_run:
        gate = summary["validation_gate"] or {}
        print(f"  validation gate:   scenario_passed={gate.get('scenario_passed')}, "
              f"golden_passed={gate.get('golden_passed')}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
