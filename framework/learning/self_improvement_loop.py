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
    python3 -m framework.learning.self_improvement_loop --dry-run      # detect+plan, NO writes anywhere
    python3 -m framework.learning.self_improvement_loop --report-only  # propose+validate, apply WITHHELD
    python3 -m framework.learning.self_improvement_loop --json         # JSON report
    python3 -m framework.learning.self_improvement_loop --skip-evals   # auto-apply without running validation evals

``--dry-run`` is the strongest no-side-effects mode: the loop computes
proposals, hat candidates, and induction clusters in memory and prints a
summary. It writes NO events to the ledger, NO proposal YAMLs to disk, and
NO draft skill files. Use this to preview what the loop would do.

``--skip-evals`` short-circuits the validation gate to "always pass" —
proposals, hat graduations, and skill drafts are applied WITHOUT running
scenario evals or golden eval shells. Intended for development and
debugging the loop itself; not for normal operation. The decision is
recorded in event payloads as ``validation_skipped: true`` so audits can
distinguish auto-applied-after-validation from auto-applied-without.

``--report-only`` (audit-ratified soak mode, 2026-07-07) sits BETWEEN the
two: the propose + validation stages RUN for real, but every apply /
promote / graduate mutation is withheld. Concretely: patterns are detected
and amendments drafted in memory (no proposal YAMLs, no
``role_charter_changed`` — the writer path stays dark), the scenario +
golden-eval validation gate executes exactly as live (its loud-red exit-3
contract included), hat candidates come from the read-only
``graduation_candidates()``, skill induction only counts clusters (no
draft files), capability gaps route with ``dry_run=True``, and neither
``adapt_role`` nor ``gate.ratify`` nor any status stamp is touched. Unlike
``--dry-run`` it EMITS the real bracketing events — the
``self_improvement_loop_started`` / ``self_improvement_loop_completed``
pair carries ``report_only: true`` (key absent on normal runs, so the
default event shape is unchanged) plus a ``would_apply`` summary
(proposal ids, hat candidates, skill-draft count) so the ledger and the
weekly review can see exactly what auto-apply WOULD have done. The fleet
wrapper ``cabinet/cron/self-improvement-loop.sh`` maps the ``REPORT_ONLY``
environment variable (services.yml row env) onto this flag. When both
``--dry-run`` and ``--report-only`` are passed, dry-run wins (it is the
strongest no-side-effects mode and writes no events at all).
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

# [SOV-8/D15] Proposal kinds that carry a CODE DIFF. These never reach the
# role-adapt apply path (_apply_proposal) — the Evidence Gate ratifies them
# (evidence only, applies nothing; germline apply stays Captain-manual).
_CODE_DIFF_KINDS = frozenset({"code_change", "code_diff"})


def _resolve_posture_safe() -> str:
    """Lazy posture read — ANY failure answers guardian, so the no-config
    world stays bit-identical [D15/D16]."""
    try:
        from framework.authority.posture import resolve_posture
        return resolve_posture()
    except Exception:  # noqa: BLE001
        return "guardian"


def _is_code_diff_proposal(proposal: dict[str, Any]) -> bool:
    """True when suggested_change carries a code diff (by kind or by a
    non-empty `diff` field) — the class _apply_proposal must never touch."""
    suggested = proposal.get("suggested_change") or {}
    if suggested.get("kind") in _CODE_DIFF_KINDS:
        return True
    return bool(str(suggested.get("diff") or "").strip())


def _route_code_diff_through_gate(
    proposal: dict[str, Any],
    parent_event_id: str,
    actor: str,
    emit_fn: Any = None,
) -> tuple[str, str]:
    """[SOV-8/D15] Route a code-diff proposal through gate.ratify (S0-S5,
    evidence only — NEVER _apply_proposal, never adapt_role). The pack's
    verdict becomes the proposal status (`gate_pass|gate_fail|gate_refused`);
    the pack itself is what a Captain unlock window (or the DARK apply lane,
    once armed) consumes. Fail-safe: a broken gate parks the proposal for
    the Captain instead of applying anything."""
    suggested = proposal.get("suggested_change") or {}
    try:
        from framework.learning import gate
        pack = gate.ratify({
            "id": proposal.get("proposal_id"),
            "gap_id": proposal.get("gap_id"),
            "lane": proposal.get("lane"),
            "summary": suggested.get("rationale") or proposal.get("proposal_id"),
            "diff": str(suggested.get("diff") or ""),
            "workdir": suggested.get("workdir"),
        }, actor=actor)
    except Exception as e:  # noqa: BLE001
        return "pending_captain_approval", f"gate unavailable: {e}"
    if emit_fn is not None:
        emit_fn("digest_published", actor=actor, parent_id=parent_event_id,
                payload={
                    "kind": "gate_evidence",
                    "proposal_id": proposal.get("proposal_id"),
                    "pack_id": pack.get("pack_id"),
                    "verdict": pack.get("verdict"),
                })
    return (f"gate_{pack.get('verdict')}",
            f"evidence pack {pack.get('pack_id')} (gate applies nothing)")


def _noop_emit(event_type: str, actor: str, payload: dict[str, Any] | None = None,
               parent_id: str | None = None) -> dict[str, Any]:
    """Drop-in replacement for ``emit`` that writes nothing.

    Used in ``--dry-run`` mode so the loop can plan without polluting the
    ledger. Returns a synthetic event dict (only the ``id`` field is used
    by callers as ``parent_id`` for child events; everything else is a stub).
    """
    return {
        "id": f"dryrun-{uuid.uuid4()}",
        "event_type": event_type,
        "actor": actor,
        "payload": payload or {},
        "parent_id": parent_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": True,
    }


def _cabinet_root() -> Path:
    return Path(os.environ.get("CABINET_ROOT", _FRAMEWORK_ROOT))


def _proposals_dir() -> Path:
    return _cabinet_root() / "instance" / "roles" / "proposals"


def _golden_evals_dir() -> Path:
    return _cabinet_root() / "memory" / "golden-evals" / "framework"


# ---------------------------------------------------------------------------
# Application journal — SAFEGUARD (a) of the Captain's 2026-07-26 arming ruling
# ---------------------------------------------------------------------------
#
# The Captain armed auto-apply (REPORT_ONLY=0) with the risk stated, so every
# application must be individually REVERSIBLE and LOGGED: what changed, why,
# the evidence it cited, and the exact inverse. One append-only JSONL row per
# application; `cabinet/scripts/self-improvement-journal.py --undo <id>` is the
# one-command revert. Runtime path (cabinet/logs/* is gitignored), OUTSIDE both
# the event ledger and the evidence plane — this is an operator surface, not a
# second source of truth. Journalling is BEST-EFFORT-LOUD: a write failure
# prints and never aborts the application, because a half-applied loop is worse
# than an unlogged one; the org events remain the durable record either way.

JOURNAL_REL = "cabinet/logs/self-improvement-applications.jsonl"


def _journal_path() -> Path:
    return _cabinet_root() / JOURNAL_REL


def _journal_application(
    kind: str,
    role_slug: str,
    change: dict[str, Any],
    undo: dict[str, Any],
    proposal_id: str | None,
    evidence: str | None,
    rationale: str | None,
    loop_id: str | None = None,
) -> str | None:
    """Append one reversible-application row. Returns its application_id."""
    application_id = f"sia-{uuid.uuid4().hex[:12]}"
    row = {
        "application_id": application_id,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "loop_id": loop_id,
        "proposal_id": proposal_id,
        "role_slug": role_slug,
        "kind": kind,              # what class of change was applied
        "change": change,          # what changed (before/after values)
        "evidence": evidence,      # the evidence it cited
        "rationale": rationale,    # why
        "undo": undo,              # the exact inverse, executable by the CLI
        "reverted": False,
    }
    try:
        path = _journal_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"self-improvement: WARN application journal write failed: {e}")
        return None
    return application_id


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
    # FAIL CLOSED on zero relevant scenarios (audit #27, same discipline as the
    # golden-eval shells gate #21 below): an unseeded preset makes
    # run_all_scenarios() return [], and a "no scenarios -> pass" no-op lets the
    # self-improvement validation gate report green WITHOUT measuring adaptation
    # discipline. Zero scenarios is an unseeded/broken box, not a pass. Every
    # shipping preset that runs this gate must carry a role/learning measurement
    # seed (presets/*/measurement/scenarios/).
    all_passed = all(r.passed for r in relevant) if relevant else False
    return all_passed, [r.to_dict() for r in relevant]


def _run_golden_eval_shells() -> tuple[bool, list[dict[str, Any]]]:
    """Run the framework safety shell tests (kill-switch, spending, stop-guard).

    Each shell test prints its own pass/fail; we capture exit codes and a
    short tail of stdout for the report. FAIL CLOSED on zero shells (audit
    #21): an absent OR empty golden-evals dir means the safety gate has
    nothing to check, and a "no shells → pass" no-op let the validation gate
    validate clean while the scenario setup had repointed CABINET_ROOT at an
    empty temp dir. shells_run=0 is a broken box, not a pass.
    """
    gdir = _golden_evals_dir()
    shells = sorted(gdir.glob("*.sh")) if gdir.exists() else []
    if not shells:
        return False, [{
            "script": None, "passed": False, "shells_run": 0,
            "error": f"no golden-eval safety shells under {gdir} "
                     f"(shells_run=0) — failing closed",
        }]
    results: list[dict[str, Any]] = []
    all_passed = True
    for sh in shells:
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
    finally:
        for k, v in snapshot.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    # #21: run the golden safety shells ONLY AFTER the scenario evals'
    # CABINET_ROOT mutation is restored above, so they glob the REAL
    # golden-evals dir (not a scenario's empty temp root, which made the gate
    # validate clean on a shells_run=0 no-op).
    gold_ok, gold = _run_golden_eval_shells()
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
    emit_fn: Any = emit,
    validation_skipped: bool = False,
    loop_id: str | None = None,
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

    # Pre-image for the reversible-application journal (safeguard (a)): the
    # inverse of an authority_change is only expressible against the value that
    # was there BEFORE the write, and nothing downstream records it.
    authority_before = role.get("authority_level")
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
                    _journal_application(
                        "capability_added", role_slug,
                        {"capability": cap, "hat": tmpl.get("name")},
                        {"op": "capability_removed", "role_slug": role_slug, "capability": cap},
                        proposal.get("proposal_id"),
                        f"proposal {proposal['proposal_id']}",
                        suggested.get("rationale"), loop_id,
                    )
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
                _journal_application(
                    "authority_change", role_slug,
                    {"authority_level_before": authority_before,
                     "authority_level_after": scope},
                    {"op": "authority_change", "role_slug": role_slug,
                     "authority_level": authority_before},
                    proposal.get("proposal_id"),
                    f"proposal {proposal['proposal_id']}",
                    suggested.get("rationale"), loop_id,
                )
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
                    _journal_application(
                        "capability_added", role_slug,
                        {"capability": cap, "quality_hat": True},
                        {"op": "capability_removed", "role_slug": role_slug, "capability": cap},
                        proposal.get("proposal_id"),
                        f"proposal {proposal['proposal_id']}",
                        suggested.get("rationale"), loop_id,
                    )
        else:
            return False, f"kind={kind} has no auto-apply handler"
    except Exception as e:  # noqa: BLE001
        return False, f"adapt_role failed: {e}"

    if not changes_applied:
        return False, "nothing concrete to apply"

    emit_fn("role_evolved", actor=actor, parent_id=parent_event_id, payload={
        "role_slug": role_slug,
        "proposal_id": proposal["proposal_id"],
        "failure_type": (proposal.get("trigger") or {}).get("failure_type"),
        "kind": kind,
        "changes_applied": changes_applied,
        "captain_auto_ratified": True,
        "validation_skipped": validation_skipped,
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
    emit_fn: Any = emit,
    validation_skipped: bool = False,
    loop_id: str | None = None,
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
                _journal_application(
                    "capability_added", role_slug,
                    {"capability": cap, "hat_slug": c.get("hat_slug"),
                     "via": "hat_graduation"},
                    {"op": "capability_removed", "role_slug": role_slug, "capability": cap},
                    None,
                    (f"hat used {c.get('uses')} times across "
                     f"{c.get('missions')} missions without OVI regression"),
                    "Hat graduation criteria met (R8 auto-apply)", loop_id,
                )
            except Exception:  # noqa: BLE001
                # adapt_role already idempotent for duplicate caps; ignore and continue
                continue
        if promoted_caps:
            emit_fn("role_hat_promoted", actor=actor, parent_id=parent_event_id, payload={
                **c,
                "status": "auto_applied",
                "captain_auto_ratified": True,
                "validation_skipped": validation_skipped,
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


def _auto_validate_skills(
    drafted_paths: list[Path],
    parent_event_id: str,
    actor: str,
    emit_fn: Any = emit,
    loop_id: str | None = None,
) -> list[dict[str, Any]]:
    """[SOV-8 §3 "skill promotion via CoS loop"] Sovereign, evals-green only:
    flip well-formed drafts to `status: validated` via
    skill_induction.promote_draft (a Ring-2 same-uid file rewrite — no root)
    and emit the notify_after tell. Callers gate on posture + the validation
    gate; this helper never checks them again."""
    from framework.learning.skill_induction import promote_draft
    validated: list[dict[str, Any]] = []
    for p in drafted_paths:
        ok, _reason = _validate_skill_draft(p)
        if not ok:
            continue
        if not promote_draft(p, promoted_by=actor):
            continue  # not in draft status (already validated/retired)
        emit_fn("skill_promoted", actor=actor, parent_id=parent_event_id, payload={
            "skill_slug": p.stem,
            "skill_path": str(p),
            "status": "auto_validated",
            "posture": "sovereign",
            "captain_auto_ratified": True,
            "ratification_note": (
                "Sovereign posture: validation evals green ⇒ draft "
                "auto-promoted to status: validated (this event is the "
                "notify_after tell)."
            ),
        })
        _journal_application(
            "skill_validated", p.stem,
            {"skill_path": str(p), "status_before": "draft",
             "status_after": "validated"},
            {"op": "skill_status", "skill_path": str(p), "status": "draft"},
            None, "validation evals green (sovereign posture)",
            "Sovereign posture: draft auto-promoted to status: validated",
            loop_id,
        )
        validated.append({"skill_slug": p.stem, "skill_path": str(p)})
    return validated


def _apply_skill_inductions(
    drafted_paths: list[Path],
    parent_event_id: str,
    actor: str,
    emit_fn: Any = emit,
    validation_skipped: bool = False,
) -> list[dict[str, Any]]:
    promoted: list[dict[str, Any]] = []
    for p in drafted_paths:
        ok, reason = _validate_skill_draft(p)
        if not ok:
            continue
        emit_fn("skill_promoted", actor=actor, parent_id=parent_event_id, payload={
            "skill_slug": p.stem,
            "skill_path": str(p),
            "status": "draft_promoted",
            "captain_auto_ratified": True,
            "validation_skipped": validation_skipped,
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
    skip_evals: bool = False,
    report_only: bool = False,
) -> dict[str, Any]:
    """Execute the closed self-improvement loop. Returns a structured report.

    The report shape is suitable for ``--json`` CLI output and includes the
    parent loop event id so an auditor can pull every child event with one
    replay filter.

    Args:
        window_days: rolling window for eval failure patterns.
        min_occurrences: minimum eval-failure cluster size to propose on.
        actor: actor slug stamped on emitted events.
        dry_run: when True, the loop writes NO events, NO proposal YAMLs, and
            NO draft skill files. The report still lists what *would* have
            been done. Use this to preview.
        skip_evals: when True, bypass the scenario + golden-eval validation
            gate. All applicable proposals/hats/skills auto-apply without
            running the safety nets. For dev/debug only — production runs
            must keep validation on. Decision is stamped into emitted event
            payloads as ``validation_skipped: true``.
        report_only: when True (audit-ratified soak mode), run the propose
            + validation stages for real but WITHHOLD every apply / promote
            / graduate mutation. Bracketing events still emit, carrying
            ``report_only: true`` plus a ``would_apply`` summary, so the
            ledger records exactly what auto-apply would have done. Zero
            disk writes outside the event ledger. ``dry_run=True`` takes
            precedence (strongest no-side-effects mode).
    """
    # Bind emit: dry-run uses a no-op so the loop computes everything in
    # memory but writes nothing to the ledger. Report-only keeps the REAL
    # emitter — the whole point is a ledger-visible record of the pass.
    emit_fn = _noop_emit if dry_run else emit

    loop_id = str(uuid.uuid4())
    started_payload: dict[str, Any] = {
        "loop_id": loop_id,
        "window_days": window_days,
        "min_occurrences": min_occurrences,
        "dry_run": dry_run,
        "skip_evals": skip_evals,
    }
    if report_only:
        # Conditional key: absent on normal runs so the pre-report-only
        # event payload shape stays byte-identical.
        started_payload["report_only"] = True
    started = emit_fn("self_improvement_loop_started", actor=actor,
                      payload=started_payload)
    parent_id = started["id"]

    # Stage 1 — generate evolution proposals from patterns -------------------
    # In dry-run we use the read-only pattern detector + build proposals in
    # memory; the writer (`propose_from_patterns`) both writes YAML and emits
    # role_charter_changed events, which would violate dry-run's no-writes
    # contract. Report-only shares the in-memory path: proposals are computed
    # + classified (and land in the would_apply summary) but nothing is
    # written to instance/roles/proposals/ until auto-apply is armed.
    proposed: list[tuple[Path | str, dict[str, Any]]]
    if dry_run or report_only:
        from framework.measurement.eval_pattern_detector import detect_patterns
        patterns = detect_patterns(
            window_days=window_days,
            min_occurrences=min_occurrences,
        )
        # Synthesize in-memory proposals using the same template path so the
        # dry-run report has matching shape — but use a placeholder path so
        # downstream code that opens the file knows to fall back to the dict.
        from framework.roles.evolution import draft_amendment
        proposed = []
        for pat in patterns:
            try:
                amendment = draft_amendment(pat)
            except Exception:  # noqa: BLE001
                amendment = {
                    "proposal_id": f"{pat['role_slug']}-{pat['failure_type']}",
                    "role_slug": pat["role_slug"],
                    "trigger": {"failure_type": pat["failure_type"]},
                    "suggested_change": {},
                }
            placeholder = f"<dry-run-proposal-{amendment.get('proposal_id', 'unknown')}>"
            proposed.append((placeholder, amendment))
    else:
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
    if proposed and not dry_run and not skip_evals:
        gate_ok, gate_detail = _validation_gate()
    elif skip_evals:
        gate_detail = {"skipped": "skip_evals"}

    for path, pat in proposed:
        if dry_run or report_only:
            # In dry-run/report-only, `pat` is the in-memory amendment dict
            # (from draft_amendment); path is a placeholder string. Skip the
            # file-read; use the dict directly.
            proposal = pat
        elif _yaml_load is None:
            proposal_report.append({
                "proposal_id": Path(path).stem,
                "status": "skipped_no_yaml",
            })
            continue
        else:
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

        if report_only:
            # REPORT_ONLY: classify what the live loop WOULD have done.
            # No status stamping (paths are in-memory placeholders), no
            # gate.ratify evidence packs, no adapt_role — observation only.
            # The gate result used here is REAL (evaluated above).
            if not concrete:
                record["status"] = "would_stay_pending"
                record["skip_reason"] = why
            elif _is_code_diff_proposal(proposal):
                record["status"] = "would_route_to_gate"
            elif not gate_ok:
                record["status"] = "would_block_by_validation"
                record["validation_failures"] = {
                    "scenario_passed": gate_detail.get("scenario_passed"),
                    "golden_passed": gate_detail.get("golden_passed"),
                }
            else:
                record["status"] = "would_auto_apply"
            proposal_report.append(record)
            continue

        if not concrete:
            _stamp_proposal_status(Path(path), "pending_captain_approval",
                                   f"self-improvement-loop: not auto-applied ({why})")
            record["status"] = "pending_captain_approval"
            proposal_report.append(record)
            continue

        if _is_code_diff_proposal(proposal):
            # [SOV-8/D15] code diffs NEVER reach _apply_proposal — the
            # Evidence Gate ratifies them (evidence only, applies nothing).
            status, detail = _route_code_diff_through_gate(
                proposal, parent_id, actor, emit_fn=emit_fn)
            _stamp_proposal_status(Path(path), status,
                                   f"self-improvement-loop: {detail}")
            record["status"] = status
            record["gate_detail"] = detail
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

        applied, reason = _apply_proposal(
            proposal, parent_id, actor,
            emit_fn=emit_fn, validation_skipped=skip_evals, loop_id=loop_id,
        )
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
    if dry_run or report_only:
        # In dry-run/report-only, fall back to the read-only API so we don't
        # emit proposal events (propose_graduations emits role_hat_promoted).
        from framework.roles.hat_graduation import graduation_candidates
        hat_candidates = graduation_candidates()
        if report_only and hat_candidates and not proposed and not skip_evals:
            # Mirror the live loop's gate discipline: when hats are the first
            # thing needing validation this run, the gate still RUNS in
            # report-only — only the graduation apply is withheld.
            gate_ok, gate_detail = _validation_gate()
    else:
        # propose_graduations both detects + emits role_hat_promoted (proposal)
        hat_candidates = propose_graduations(actor=actor)
        if hat_candidates:
            # Apply each candidate (idempotent inside adapt_role).
            # Re-run gate only if it wasn't already evaluated above.
            if not proposed and not skip_evals:
                gate_ok, gate_detail = _validation_gate()
            if gate_ok or skip_evals:
                hat_applied = _apply_hat_graduations(
                    hat_candidates, parent_id, actor,
                    emit_fn=emit_fn, validation_skipped=skip_evals,
                    loop_id=loop_id,
                )

    # Stage 3 — skill induction ---------------------------------------------
    drafted_paths: list[Path] = []
    skill_promoted: list[dict[str, Any]] = []
    skill_validated: list[dict[str, Any]] = []
    if not dry_run and not report_only:
        drafted_paths = induce_drafts(actor=actor)
        if drafted_paths:
            skill_promoted = _apply_skill_inductions(
                drafted_paths, parent_id, actor,
                emit_fn=emit_fn, validation_skipped=skip_evals,
            )
        # [SOV-8 §3] sovereign only: validation-evals-green ⇒ auto-promote
        # drafts to status:validated (Ring-2 file, no root); the emitted
        # skill_promoted event is the notify_after tell. Guardian (or any
        # posture-read failure) never enters this branch — bit-identical.
        if (drafted_paths and not skip_evals
                and _resolve_posture_safe() == "sovereign"):
            gate_was_evaluated = bool(proposed) or bool(hat_candidates)
            if not gate_was_evaluated:
                gate_ok, gate_detail = _validation_gate()
            if gate_ok:
                skill_validated = _auto_validate_skills(
                    drafted_paths, parent_id, actor, emit_fn=emit_fn,
                    loop_id=loop_id)
    else:
        # Dry-run / report-only: cluster without writing draft files —
        # memory/skills/evolved/ stays untouched until auto-apply is armed.
        from framework.learning.skill_induction import _cluster_records  # noqa: SLF001
        from framework.learning.experience import list_records
        clusters = _cluster_records(
            list_records(),
            min_size=3,
            scope_filter={"this_role", "cabinet_wide"},
        )
        drafted_paths = [Path(f"<dry-run-cluster-{i}>") for i, _ in enumerate(clusters)]

    # Stage 3.5 — route open capability gaps (self-extension) ----------------
    # procedure gaps → auto_skilling; tool/integration gaps → proposal to the
    # Captain. NOTHING installs here — installs wait for an explicit approval
    # (capability_gaps.can_install, fail-closed). Isolated: never breaks the loop.
    try:
        from framework.learning.capability_gaps import route_open_gaps
        gap_routing = route_open_gaps(dry_run=dry_run or report_only)
    except Exception as exc:  # noqa: BLE001
        gap_routing = {"error": str(exc), "auto_skilling": [], "proposed": [], "skipped": []}

    # Stage 4 — completion event --------------------------------------------
    if dry_run:
        validation_gate_report: dict[str, Any] = {"skipped": "dry_run"}
    elif skip_evals:
        validation_gate_report = {"skipped": "skip_evals"}
    else:
        validation_gate_report = gate_detail
    summary = {
        "loop_id": loop_id,
        "window_days": window_days,
        "min_occurrences": min_occurrences,
        "dry_run": dry_run,
        "skip_evals": skip_evals,
        "validation_gate": validation_gate_report,
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
        "capability_gaps": {
            "auto_skilling": len(gap_routing.get("auto_skilling", [])),
            "proposed_to_captain": len(gap_routing.get("proposed", [])),
            "skipped": len(gap_routing.get("skipped", [])),
        },
    }
    if skill_validated:
        # Sovereign-only key: absent in guardian so the completed-event
        # payload stays byte-identical to the pre-posture world there.
        summary["skill_induction"]["auto_validated"] = len(skill_validated)
        summary["skill_induction"]["auto_validated_detail"] = skill_validated
    if report_only:
        # Conditional keys (absent on normal runs — payload shape unchanged
        # there): the ledger-visible record of what auto-apply WOULD have
        # done this run, consumed by the weekly review before REPORT_ONLY
        # is flipped off.
        summary["report_only"] = True
        summary["would_apply"] = {
            "proposals": [
                r.get("proposal_id") for r in proposal_report
                if r.get("status") == "would_auto_apply"
            ],
            "hat_graduations": [
                {
                    "role_slug": c.get("role_slug"),
                    "hat_slug": c.get("hat_slug"),
                    "capabilities_to_promote": c.get("capabilities_to_promote", []),
                }
                for c in hat_candidates
            ] if (gate_ok or skip_evals) else [],
            "skill_drafts": len(drafted_paths),
        }
    emit_fn("self_improvement_loop_completed", actor=actor, parent_id=parent_id, payload=summary)
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
    parser.add_argument(
        "--dry-run", action="store_true",
        help=("Plan only — write NO events, NO proposal YAMLs, NO draft "
              "skill files. The report describes what would have been done. "
              "Use to preview a loop run safely."),
    )
    parser.add_argument(
        "--skip-evals", action="store_true",
        help=("Bypass the validation gate (scenario evals + golden eval "
              "shells); apply learnings without safety checks. For "
              "development / debugging the loop itself — NOT for normal "
              "operation. Emitted events are stamped validation_skipped: true."),
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help=("Audit-ratified soak mode: run propose + validation for real "
              "but WITHHOLD every apply/promote/graduate mutation. Emits the "
              "bracketing events with report_only: true plus a would_apply "
              "summary (proposal ids, hat candidates, skill-draft count). "
              "The fleet wrapper maps env REPORT_ONLY=1 onto this flag. "
              "--dry-run takes precedence when both are given."),
    )
    parser.add_argument("--json", action="store_true",
                        help="Emit the structured report as JSON to stdout.")
    args = parser.parse_args(argv)

    summary = run_loop(
        window_days=args.window_days,
        min_occurrences=args.min_occurrences,
        dry_run=args.dry_run,
        skip_evals=args.skip_evals,
        report_only=args.report_only,
    )

    # Loud-red gate (T2-arm-schedules review fix, 2026-07-07): a RED
    # validation gate parks every concrete proposal (blocked_by_validation)
    # and stops hat graduations — if that state exits 0 with no marker, the
    # armed 6h LaunchAgent shows green in launchctl and the no-silent-cron
    # watchdog floor reads clean while the growth engine is structurally
    # dead (exactly the silent-failure class the watchdog exists to catch).
    # So: when the gate WAS evaluated this run and failed, emit ONE stderr
    # line carrying the watchdog's "FATAL" JOB_ERROR_MARKERS token (the
    # marker scan pages on it) and exit 3 (non-zero launchd last-exit —
    # the launchctl scan pages on that too). Runs where the gate never
    # evaluated (nothing to validate), --dry-run, and --skip-evals keep
    # exiting 0. role-evals-weekly.sh wraps its inline invocation in
    # `|| echo` so the weekly chain is unaffected.
    gate = summary.get("validation_gate") or {}
    gate_evaluated = ("scenario_passed" in gate) or ("golden_passed" in gate)
    gate_red = gate_evaluated and not (
        bool(gate.get("scenario_passed", True))
        and bool(gate.get("golden_passed", True)))
    if gate_red:
        failing_shells = [
            str(r.get("script"))
            for r in (gate.get("golden_evals") or [])
            if isinstance(r, dict) and not r.get("passed")
        ]
        print(
            "self-improvement-loop: FATAL validation gate RED "
            f"(scenario_passed={gate.get('scenario_passed')}, "
            f"golden_passed={gate.get('golden_passed')}"
            + (f"; failing shells: {', '.join(failing_shells)}"
               if failing_shells else "")
            + ") — nothing auto-applied; proposals are parked "
              "blocked_by_validation until the gate is green again. "
              "Exiting 3 so launchd/watchdog page instead of logging green.",
            file=sys.stderr,
        )

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return 3 if gate_red else 0

    print("\n=== Self-improvement loop ===")
    print(f"  loop_id:           {summary['loop_id']}")
    print(f"  dry_run:           {summary['dry_run']}")
    print(f"  skip_evals:        {summary['skip_evals']}")
    print(f"  proposals:         {summary['proposals']['generated']} generated, "
          f"{summary['proposals']['auto_applied']} auto-applied, "
          f"{summary['proposals']['pending_captain']} pending Captain")
    print(f"  hat graduations:   {summary['hat_graduations']['candidates']} candidates, "
          f"{summary['hat_graduations']['applied']} applied")
    print(f"  skill induction:   {summary['skill_induction']['drafted']} drafted, "
          f"{summary['skill_induction']['promoted']} promoted")
    if not args.dry_run and not args.skip_evals:
        gate = summary["validation_gate"] or {}
        print(f"  validation gate:   scenario_passed={gate.get('scenario_passed')}, "
              f"golden_passed={gate.get('golden_passed')}")
    elif args.skip_evals:
        print("  validation gate:   SKIPPED (--skip-evals)")
    if args.report_only and not args.dry_run:
        # The would-apply summary, written to the loop's log target (launchd
        # stdout). Human lines first, then ONE grep-able JSON line so audits
        # and the weekly review can machine-read the pass.
        wa = summary.get("would_apply") or {}
        gate = summary.get("validation_gate") or {}
        print("  REPORT-ONLY:       propose + validate ran; every apply/"
              "promote/graduate mutation WITHHELD (flip REPORT_ONLY=0 to arm)")
        print(f"  would auto-apply proposals: {wa.get('proposals', [])}")
        print(f"  would graduate hats:        {wa.get('hat_graduations', [])}")
        print(f"  would draft skills:         {wa.get('skill_drafts', 0)}")
        print("REPORT_ONLY_SUMMARY: " + json.dumps({
            "loop_id": summary.get("loop_id"),
            "would_apply": wa,
            "validation_gate": {
                "scenario_passed": gate.get("scenario_passed"),
                "golden_passed": gate.get("golden_passed"),
            },
            "proposals": [
                {"proposal_id": r.get("proposal_id"), "status": r.get("status")}
                for r in (summary.get("proposals") or {}).get("detail", [])
            ],
        }, default=str))
    return 3 if gate_red else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
