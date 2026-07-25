#!/usr/bin/env python3.12
"""attention-well-spent.py — the Captain-facing north-star instrument.

THE QUESTION: of the Captain's measured minutes, what share went to decisions
ONLY HE could make?

WHY THIS WORDING (the finding this module answers).  The org's stated north
star was `verified_outcomes_per_captain_minute`.  That string was computed
NOWHERE — its only occurrences were `instance/config/directions.yml` and a
dashboard test asserting the string is present in the YAML.  What WAS computed
pointed the other way:

  * `framework/ovi/compute.py` counts Captain-input events as
    `captain_attention_cost`, weighted `direction: inverse` in
    `framework/ovi/components.yml` — FEWER Captain events mechanically score
    HIGHER.
  * `cabinet/scripts/lib/org_runtime.py` `burden_index()` takes
    `--captain-attention-minutes` as a DECLARED input defaulting to 0, and
    `ovi = verified_value / burden` — so declaring zero Captain minutes and a
    high `--verified-value` maximises the number, with `--evidence` optional on
    `cabinet/scripts/work-graph-complete.sh`.
  * `framework/attention/queue.py` `demoted_kinds()` demotes producers whose
    cards keep expiring, and `framework/constitution-base.md` §5 tells officers
    to "Minimize Captain interrupts".

So the metric as worded rewarded MINIMISING the founder's involvement — the
formal opposite of the ruling that the cabinet runs the company TOGETHER WITH
him.  Nothing anywhere counted the questions that should have been asked.

THIS INSTRUMENT INVERTS THAT, and every inversion is a property you can shoot
at:

  P1  UNDER-ASKING IS A FAILURE, not a win.  A hard-ceiling action that
      EXECUTED without a Captain verdict is an `unasked` row and the floor
      reads `breached` — RED, whatever the share says.
  P2  GOING QUIET CANNOT RAISE THE READING.  Suppressing cards can only leave
      the share flat or breach the floor; and a window with org activity and
      ZERO Captain touches is itself a breach (the silent-window rule).
  P3  SELF-ATTESTATION COUNTS ZERO.  A `work_item_verified` emitted by an actor
      that also emitted the `work_item_completed` for that task, with no
      independent probe ref, is rejected.
  P4  THE DENOMINATOR IS MEASURED, NEVER DECLARED.  It is derived from observed
      ledger interactions priced by a published constant table.  No flag, no
      payload field, no CLI argument lets a producer set its own contribution.
  P5  CARD SPAM LOWERS THE SHARE.  An expired card is priced above zero: it
      cost queue-time and produced nothing.

THE MUST-ASK FLOOR IS NOT OURS TO WEAKEN.  It is read at runtime from the
`hard_ceiling` risk classes in `framework/policies/authority-matrix.yml` —
"always-gated regardless of confidence", and `framework/policies/` is an
schg-locked germline directory.  This module holds no editable copy of the
floor: shrinking it means editing a system-immutable file.  An unreadable or
empty matrix is a HARD ERROR, never a green reading.

COVERAGE IS PART OF THE ANSWER.  `action_type` is nullable on the consequence
schema, so "not stamped" would otherwise be a free way to leave the floor.  An
executed row with no `action_type` lands in `unclassified_executed` and the
floor reads `unprovable` (AMBER): you cannot claim the floor held over rows
whose class you never recorded.

REPORT-ONLY — the standing law.  Evidence-derived aggregates are monitoring
metrics and kill criteria ONLY: never officer-visible scores, never inputs to
generation or selection (`memory/golden-evals/eval-025-never-a-score.md`,
`cabinet/evals/never-a-score/`).  This module therefore:

  * lives in `cabinet/`, NOT `framework/` — officer-plane code cannot import
    what is not on its import path;
  * emits nothing (no `emit()`, no ledger write, no event type);
  * refuses to write its report anywhere inside the repo tree, so its output
    can never quietly become a file some selector reads.

`cabinet/scripts/tests/test_attention_well_spent.py` pins all of the above,
including a guard that no `framework/` or `presets/` file names this module.

HONEST LIMITS (named, not hidden):
  * a probe ref is a POINTER, not a re-execution — the instrument checks that a
    ref is shaped like an independently recorded artifact, not that the
    artifact says what the officer claims.  It is still strictly stronger than
    today's optional free-prose `--evidence`, because a forged pointer is
    falsifiable by anyone who follows it.
  * Ring-0 governance categories (`framework/authority/action_mode.py`
    `RING0_CATEGORIES`) are NOT in the v1 floor: the consequence schema carries
    no field that classifies a row into one.  The v1 floor is exactly the
    ratified hard-ceiling set.  That gap is stated here rather than papered
    over.
  * The floor sees ACTIONS THAT RAN (`outcome.status` ok/failed).  A must-ask
    row whose outcome was never recorded is neither a breach nor a hold — it is
    invisible to v1.  The symmetric "just don't stamp it" evasion on the CLASS
    axis IS closed (`unclassified_executed` ⇒ `unprovable`); the one on the
    OUTCOME axis is not, because the obvious fix — treating every undecided
    must-ask proposal as suspect — would fire on every card legitimately
    awaiting the Captain right now, and a instrument that cries wolf gets
    ignored.  Closing it properly needs a staleness clock, which is its own
    change.

Usage:
    python3.12 cabinet/scripts/attention-well-spent.py --window-days 7
    python3.12 cabinet/scripts/attention-well-spent.py --json
    python3.12 cabinet/scripts/attention-well-spent.py --out /tmp/aws.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

try:
    from yaml import safe_load as _yaml_load
except ImportError:  # pragma: no cover - yaml is a hard dep everywhere in CI
    import yaml as _yaml_mod

    _yaml_load = _yaml_mod.safe_load


SCHEMA_VERSION = "attention-well-spent/v1"
INSTRUMENT = "attention_well_spent"

#: The one sentence that must survive every refactor of this file.
SURFACE_DOCTRINE = (
    "REPORT-ONLY Captain-facing instrument: monitoring and kill criteria only, "
    "never an officer-visible score, never an input to generation or selection."
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "cabinet" / "config" / "attention-well-spent.yml"
DEFAULT_MATRIX = REPO_ROOT / "framework" / "policies" / "authority-matrix.yml"

#: The real verdicts a human renders at the approval gate. Mirrors
#: framework/attention/situations.py _CAPTAIN_DECISIONS.
CAPTAIN_DECISIONS = frozenset({"approved", "edited", "rejected"})
#: A card that reached the queue and died there. Attention spent, value zero.
EXPIRED = "expired"
#: outcome.status values that mean the action actually ran.
EXECUTED_STATUSES = frozenset({"ok", "failed"})

#: Captain org-event types that are Captain-only BY CONSTRUCTION: declaring a
#: goal, ratifying an outcome and setting a boundary are acts of the authority
#: root, which is the definition of "only he could make it".
AUTHORITY_ROOT_EVENTS = frozenset({
    "captain_goal_declared",
    "captain_outcome_ratified",
    "captain_boundary_set",
})
#: A logged decision carries no authority-root guarantee — it is classified by
#: the action_type recorded on it, and counts as unclassified when absent.
CLASSIFIED_CAPTAIN_EVENTS = frozenset({"captain_decision_logged", "captain_gate_bounced"})
CAPTAIN_EVENT_TYPES = tuple(sorted(AUTHORITY_ROOT_EVENTS | CLASSIFIED_CAPTAIN_EVENTS))

#: Hard cap on any single string we scan. Ledger text is officer/LLM-written;
#: one hostile mega-string must cost O(cap), not O(input).
_MAX_SCAN_CHARS = 4096


class LawUnreadable(RuntimeError):
    """The must-ask floor could not be derived from the authority matrix.

    Fail LOUD: an instrument that cannot read its own law must never report a
    reading. Silence here would be exactly the failure mode the instrument
    exists to catch.
    """


# ---------------------------------------------------------------------------
# The must-ask floor — read from the ratified, schg-locked authority matrix
# ---------------------------------------------------------------------------


def load_must_ask_law(matrix_path: "str | Path | None" = None) -> dict[str, Any]:
    """Derive the must-ask floor from framework/policies/authority-matrix.yml.

    Returns ``{"risk_classes": {...}, "action_types": frozenset,
    "class_of": {action_type: risk_class}}`` where ``risk_classes`` is the
    matrix's own ``hard_ceiling`` list ("always-gated regardless of
    confidence") and ``action_types`` is the union of those classes'
    ``action_types``.

    This module keeps NO editable copy of the floor. Narrowing it means editing
    a file under ``framework/policies/``, which is schg-locked germline.
    """
    path = Path(matrix_path) if matrix_path is not None else DEFAULT_MATRIX
    try:
        raw = _yaml_load(path.read_text())
    except FileNotFoundError as exc:
        raise LawUnreadable(f"authority matrix not found: {path}") from exc
    except Exception as exc:  # malformed YAML — never degrade to "no floor"
        raise LawUnreadable(f"authority matrix unreadable: {path}: {exc}") from exc

    policy = _find_matrix_policy(raw)
    if policy is None:
        raise LawUnreadable(f"no policy block with hard_ceiling + risk_classes in {path}")

    ceiling = policy.get("hard_ceiling")
    risk_classes = policy.get("risk_classes")
    if not isinstance(ceiling, list) or not ceiling:
        raise LawUnreadable(f"hard_ceiling missing or empty in {path}")
    if not isinstance(risk_classes, Mapping) or not risk_classes:
        raise LawUnreadable(f"risk_classes missing or empty in {path}")

    class_of: dict[str, str] = {}
    for rc in ceiling:
        block = risk_classes.get(rc)
        types = (block or {}).get("action_types") if isinstance(block, Mapping) else None
        if not isinstance(types, list) or not types:
            raise LawUnreadable(
                f"hard_ceiling class {rc!r} has no action_types in {path}")
        for action_type in types:
            class_of[str(action_type)] = str(rc)

    return {
        "source": str(path),
        "risk_classes": [str(rc) for rc in ceiling],
        "action_types": frozenset(class_of),
        "class_of": class_of,
    }


def _find_matrix_policy(raw: Any) -> "Mapping | None":
    """Locate the policy mapping carrying hard_ceiling + risk_classes.

    The matrix ships as a policy document whose exact nesting is not this
    module's business; we walk it and take the first block that carries both
    keys, so a re-nesting of the germline file does not silently zero the floor.
    """
    stack: list[Any] = [raw]
    while stack:
        node = stack.pop()
        if isinstance(node, Mapping):
            if "hard_ceiling" in node and "risk_classes" in node:
                return node
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


_CONFIG_DEFAULTS: dict[str, Any] = {
    "minute_costs": {"decided": 6, "expired": 1, "captain_event": 3},
    "captain_actors": ["captain"],
    "probe_ref_prefixes": ["https://github.com/", "eval:", "probe:", "run:"],
    "probe_ref_min_length": 12,
    "share_amber_below": 0.5,
    "silent_window_min_actions": 1,
}


def load_config(config_path: "str | Path | None" = None) -> dict[str, Any]:
    """Load the published constant table. Absent file → shipped defaults."""
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG
    cfg = json.loads(json.dumps(_CONFIG_DEFAULTS))  # deep copy of plain data
    if not path.exists():
        return cfg
    loaded = _yaml_load(path.read_text()) or {}
    if not isinstance(loaded, Mapping):
        raise ValueError(f"attention-well-spent config is not a mapping: {path}")
    for key, value in loaded.items():
        if key == "minute_costs" and isinstance(value, Mapping):
            cfg["minute_costs"].update({str(k): float(v) for k, v in value.items()})
        elif key in cfg:
            cfg[key] = value
    return cfg


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def _clip(text: Any) -> str:
    return str(text or "")[:_MAX_SCAN_CHARS]


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_ts(value: Any) -> "datetime | None":
    """Parse an ISO-8601 stamp to an aware UTC datetime, else None.

    Ledger stamps are not guaranteed UTC-normalized, and ISO strings with
    different offsets do NOT sort lexicographically in real time order — a
    `+02:00` stamp inside the window would be dropped by a naive string
    compare. Window membership is decided on parsed instants; an unparseable
    stamp is treated as out of window (honest exclusion, never a silent
    inclusion of an undatable row).
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _in_window(value: Any, since: datetime, until: datetime) -> bool:
    dt = _parse_ts(value)
    return dt is not None and since <= dt <= until


def _row_action_type(row: Mapping) -> "str | None":
    at = row.get("action_type")
    if isinstance(at, str) and at.strip():
        return at.strip()
    return None


def _row_executed(row: Mapping) -> bool:
    outcome = row.get("outcome")
    if not isinstance(outcome, Mapping):
        return False
    return str(outcome.get("status") or "") in EXECUTED_STATUSES


def _row_decision(row: Mapping) -> "str | None":
    proposal = row.get("proposal")
    if not isinstance(proposal, Mapping):
        return None
    decision = proposal.get("decision")
    return decision if isinstance(decision, str) and decision else None


def _row_gated(row: Mapping) -> bool:
    proposal = row.get("proposal")
    return isinstance(proposal, Mapping) and bool(proposal.get("required"))


def _row_identity(row: Mapping) -> str:
    actor = row.get("actor")
    actor_id = (
        f"{actor.get('kind')}:{actor.get('id')}" if isinstance(actor, Mapping) else str(actor)
    )
    return f"{row.get('ts', '')}|{actor_id}|{row.get('action', '')}|{row.get('subject', '')}"


def is_probe_ref(value: Any, cfg: Mapping) -> bool:
    """True when ``value`` is shaped like a pointer to an independently
    recorded artifact rather than free prose.

    Literal prefixes only — never a config-supplied regex over ledger text.
    A ref must also be whitespace-free and long enough to be an id: "looks
    good" and "https://github.com/" alone are prose, not evidence.
    """
    text = _clip(value).strip()
    if len(text) < int(cfg.get("probe_ref_min_length", 12)):
        return False
    if any(ch.isspace() for ch in text):
        return False
    prefixes = cfg.get("probe_ref_prefixes") or []
    return any(text.startswith(str(p)) for p in prefixes if str(p))


# ---------------------------------------------------------------------------
# The computation
# ---------------------------------------------------------------------------


def compute(
    *,
    window_days: int = 7,
    now: "datetime | None" = None,
    config: "Mapping | None" = None,
    law: "Mapping | None" = None,
    consequence_rows: "Iterable[Mapping] | None" = None,
    org_events: "Iterable[Mapping] | None" = None,
    config_path: "str | Path | None" = None,
    matrix_path: "str | Path | None" = None,
) -> dict[str, Any]:
    """Compute the attention-well-spent reading for a rolling window.

    Rows may be injected (tests, replays); when they are not, they are read
    from the live ledgers through their canonical read paths.
    """
    cfg = dict(config) if config is not None else load_config(config_path)
    the_law = dict(law) if law is not None else load_must_ask_law(matrix_path)
    must_ask: frozenset = frozenset(the_law["action_types"])
    class_of: Mapping = the_law["class_of"]

    until = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    since = until - timedelta(days=int(window_days))
    since_iso, until_iso = _iso(since), _iso(until)

    rows = list(consequence_rows) if consequence_rows is not None else _read_consequence(since_iso)
    events = list(org_events) if org_events is not None else _read_org_events(since_iso)
    rows = [r for r in rows
            if isinstance(r, Mapping) and _in_window(r.get("ts"), since, until)]
    events = [e for e in events
              if isinstance(e, Mapping) and _in_window(e.get("created_at"), since, until)]

    costs = cfg["minute_costs"]
    captain_actors = {str(a) for a in (cfg.get("captain_actors") or [])}

    # --- denominator: measured Captain touches -----------------------------
    touches: list[dict[str, Any]] = []

    for row in rows:
        decision = _row_decision(row)
        if decision in CAPTAIN_DECISIONS:
            kind, minutes = "decided", float(costs.get("decided", 0))
        elif decision == EXPIRED:
            kind, minutes = "expired", float(costs.get("expired", 0))
        else:
            continue
        action_type = _row_action_type(row)
        touches.append({
            "source": "consequence",
            "kind": kind,
            "identity": _row_identity(row),
            "action_type": action_type,
            "captain_only": action_type in must_ask if action_type else False,
            "risk_class": class_of.get(action_type) if action_type else None,
            "minutes": minutes,
        })

    for event in events:
        if str(event.get("actor") or "") not in captain_actors:
            continue  # never take an officer's word for who acted
        event_type = str(event.get("event_type") or "")
        if event_type not in CAPTAIN_EVENT_TYPES:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        action_type = _row_action_type(payload)
        if event_type in AUTHORITY_ROOT_EVENTS:
            captain_only, risk_class = True, "authority_root"
        else:
            captain_only = bool(action_type) and action_type in must_ask
            risk_class = class_of.get(action_type) if action_type else None
        touches.append({
            "source": "org_event",
            "kind": "captain_event",
            "identity": str(event.get("id") or event_type),
            "event_type": event_type,
            "action_type": action_type,
            "captain_only": captain_only,
            "risk_class": risk_class,
            "minutes": float(costs.get("captain_event", 0)),
        })

    measured_minutes = round(sum(t["minutes"] for t in touches), 4)
    captain_only_minutes = round(sum(t["minutes"] for t in touches if t["captain_only"]), 4)
    share = (captain_only_minutes / measured_minutes) if measured_minutes > 0 else None

    by_kind: dict[str, int] = {}
    for t in touches:
        by_kind[t["kind"]] = by_kind.get(t["kind"], 0) + 1

    # --- the must-ask floor -------------------------------------------------
    unasked: list[dict[str, Any]] = []
    unclassified_executed: list[str] = []
    executed_actions = 0
    for row in rows:
        if not _row_executed(row):
            continue
        executed_actions += 1
        action_type = _row_action_type(row)
        if action_type is None:
            unclassified_executed.append(_row_identity(row))
            continue
        if action_type not in must_ask:
            continue
        if _row_decision(row) in CAPTAIN_DECISIONS:
            continue
        unasked.append({
            "identity": _row_identity(row),
            "action_type": action_type,
            "risk_class": class_of.get(action_type),
            "gated": _row_gated(row),
            "decision": _row_decision(row),
            "why": "hard-ceiling action executed without a Captain verdict",
        })

    org_actions = executed_actions + sum(
        1 for e in events if str(e.get("event_type") or "") == "work_item_completed")
    silent_window = (
        org_actions >= int(cfg.get("silent_window_min_actions", 1)) and not touches)

    if unasked or silent_window:
        floor = "breached"
    elif unclassified_executed:
        floor = "unprovable"
    else:
        floor = "held"

    # --- verified outcomes: never an officer's own emit ---------------------
    verified = _count_verified_outcomes(events, cfg, captain_actors)

    # --- verdict (kill criteria, not a score) -------------------------------
    why: list[str] = []
    if floor == "breached":
        verdict = "red"
        if unasked:
            why.append(
                f"{len(unasked)} hard-ceiling action(s) executed with no Captain "
                f"verdict — the must-ask floor is breached")
        if silent_window:
            why.append(
                f"{org_actions} org action(s) executed and the Captain was touched "
                f"zero times — a silent window is under-asking, not a clean sheet")
    elif org_actions == 0 and not touches:
        verdict = "unmeasured"
        why.append("no org activity and no Captain touches in the window — honest absence")
    elif floor == "unprovable":
        verdict = "amber"
        why.append(
            f"{len(unclassified_executed)} executed row(s) carry no action_type — the "
            f"floor cannot be proven held over rows whose class was never recorded")
    elif share is not None and share < float(cfg.get("share_amber_below", 0.5)):
        verdict = "amber"
        why.append(
            f"only {share:.0%} of measured Captain minutes went to decisions only he "
            f"could make")
    else:
        verdict = "green"
        why.append("must-ask floor held and the Captain's minutes went where they had to")
    if verified["counted"] == 0 and verified["self_attested_rejected"] > 0:
        why.append(
            f"{verified['self_attested_rejected']} self-attested verification(s) "
            f"rejected — an officer verifying its own work counts zero")

    return {
        "schema_version": SCHEMA_VERSION,
        "instrument": INSTRUMENT,
        "surface": SURFACE_DOCTRINE,
        "window": {"days": int(window_days), "since": since_iso, "until": until_iso},
        "law": {
            "source": the_law["source"],
            "risk_classes": list(the_law["risk_classes"]),
            "action_types": sorted(must_ask),
        },
        "denominator": {
            "measured_minutes": measured_minutes,
            "touches": len(touches),
            "by_kind": by_kind,
            "declared_inputs": [],  # structural: nothing here is declarable
        },
        "numerator": {
            "captain_only_minutes": captain_only_minutes,
            "touches": sum(1 for t in touches if t["captain_only"]),
        },
        "share": (round(share, 4) if share is not None else None),
        "under_asking": {
            "must_ask_floor": floor,
            "unasked": unasked,
            "unclassified_executed": unclassified_executed,
            "silent_window": silent_window,
            "org_actions": org_actions,
        },
        "verified_outcomes": verified,
        "verdict": verdict,
        "why": why,
    }


def _count_verified_outcomes(
    events: Iterable[Mapping], cfg: Mapping, captain_actors: "set[str]"
) -> dict[str, Any]:
    """Count outcomes verified by a probe, a counterparty, or the Captain.

    An actor verifying a task it also completed, with no probe ref, is
    SELF-ATTESTATION and counts zero — that is the whole degenerate strategy
    the old metric rewarded.
    """
    completed_actors: dict[str, set[str]] = {}
    verified_events: list[Mapping] = []
    ratified_tasks: set[str] = set()
    for event in events:
        event_type = str(event.get("event_type") or "")
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        task_id = str(payload.get("task_id") or "")
        if event_type == "work_item_completed" and task_id:
            completed_actors.setdefault(task_id, set()).add(str(event.get("actor") or ""))
        elif event_type == "work_item_verified" and task_id:
            verified_events.append(event)
        elif (event_type == "captain_outcome_ratified"
              and str(event.get("actor") or "") in captain_actors and task_id):
            ratified_tasks.add(task_id)

    by_attestor: dict[str, int] = {}
    counted: set[str] = set()
    rejected = 0
    for event in verified_events:
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        task_id = str(payload.get("task_id") or "")
        actor = str(event.get("actor") or "")
        doers = completed_actors.get(task_id, set())
        if actor in captain_actors or task_id in ratified_tasks:
            attestor = "captain"
        elif doers and actor not in doers:
            attestor = "counterparty"
        elif is_probe_ref(payload.get("evidence_path"), cfg) or is_probe_ref(
                payload.get("evidence_text"), cfg):
            attestor = "probe"
        else:
            rejected += 1
            continue
        by_attestor[attestor] = by_attestor.get(attestor, 0) + 1
        counted.add(task_id)

    return {
        "counted": len(counted),
        "self_attested_rejected": rejected,
        "by_attestor": by_attestor,
        "completions": len(completed_actors),
    }


# ---------------------------------------------------------------------------
# Ledger readers — canonical read paths, imported lazily so this module stays
# import-inert for tests that inject rows.
# ---------------------------------------------------------------------------


def _read_consequence(since_iso: str) -> list[dict[str, Any]]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from framework.fidelity.consequence import read_ledger  # noqa: PLC0415

    return read_ledger(since=since_iso)


def _read_org_events(since_iso: str) -> list[dict[str, Any]]:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from framework.events.emitter import replay  # noqa: PLC0415

    return replay(
        since=since_iso,
        event_types=list(CAPTAIN_EVENT_TYPES)
        + ["work_item_completed", "work_item_verified"],
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def resolve_out_path(raw: str) -> Path:
    """Resolve ``--out`` and REFUSE any destination inside the repo tree.

    An instrument that can write into the repo is an instrument that can be
    turned into a selection input by landing its output where some consumer
    reads it. The never-a-score law says this reading may be monitoring and
    kill criteria only, so the report leaves the tree or goes to stdout.
    """
    path = Path(raw).expanduser()
    resolved = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    root = REPO_ROOT.resolve()
    if resolved == root or root in resolved.parents:
        raise SystemExit(
            f"attention-well-spent: refusing to write inside the repo tree: {resolved}\n"
            f"  {SURFACE_DOCTRINE}\n"
            f"  Write outside {root}, or print to stdout.")
    return resolved


def _render_text(report: Mapping) -> str:
    share = report["share"]
    share_txt = "n/a" if share is None else f"{share:.0%}"
    lines = [
        "Attention well spent — how much of your time only you could have spent",
        f"  window        : {report['window']['days']}d "
        f"({report['window']['since'][:10]} → {report['window']['until'][:10]})",
        f"  verdict       : {report['verdict'].upper()}",
        f"  well spent    : {share_txt} of {report['denominator']['measured_minutes']:g} "
        f"measured minutes across {report['denominator']['touches']} touches",
        f"  must-ask floor: {report['under_asking']['must_ask_floor']}",
    ]
    for row in report["under_asking"]["unasked"]:
        lines.append(f"    NOT ASKED  {row['risk_class']}/{row['action_type']}  {row['identity']}")
    if report["under_asking"]["silent_window"]:
        lines.append(
            f"    SILENT WINDOW  {report['under_asking']['org_actions']} action(s), 0 touches")
    lines.append(
        f"  verified      : {report['verified_outcomes']['counted']} counted, "
        f"{report['verified_outcomes']['self_attested_rejected']} self-attested rejected")
    lines.extend(f"  why           : {w}" for w in report["why"])
    lines.append(f"  surface       : {report['surface']}")
    return "\n".join(lines)


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        prog="attention-well-spent",
        description=(
            "Captain-facing instrument: the share of measured Captain minutes spent "
            "on decisions only he could make. REPORT-ONLY — never a selection input."),
    )
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument("--config", default=None, help="published constant table")
    parser.add_argument("--matrix", default=None, help="authority matrix (the must-ask floor)")
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    parser.add_argument("--out", default=None, help="write the JSON report OUTSIDE the repo tree")
    args = parser.parse_args(argv)

    out_path = resolve_out_path(args.out) if args.out else None
    try:
        report = compute(
            window_days=args.window_days,
            config_path=args.config,
            matrix_path=args.matrix,
        )
    except LawUnreadable as exc:
        print(f"attention-well-spent: {exc}", file=sys.stderr)
        return 2

    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n")
    if args.json or out_path is None:
        print(json.dumps(report, indent=2) if args.json else _render_text(report))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
