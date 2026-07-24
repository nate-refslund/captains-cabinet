#!/usr/bin/env python3.12
"""cog4-dispatch-shadow.py — the SEPARATE shadow dispatch comparator (COG-4
§7.3; charter §4.5 L116 "a separate dispatcher"). SHADOW-ONLY: this CLI never
executes anything — per decision row of a served schedule it rechecks the
charter QUADRUPLE (authority, idempotency, snapshot freshness, remaining
resource budget — SF1: the parent charter's four bind over the ledger note's
triple) plus organ freshness, and APPENDS `would_dispatch|refused(reason)`
shadow decision records to a shadow log. The future cutover is a
pointer/adapter amendment that does NOT exist this phase: the pointer path
existing AT ALL refuses outright (§7.4 tripwire, exit 5).

THE SIX LIMBS, IN ORDER (§7.3; the W2 T2 corpus `test_cog4_sim_dispatch.py`
is the executable spec — its reference dispatcher pins every reason/limb
token emitted here):
  1. SERVE — the schedule is read through THE one kernel-bound loader
     (`framework.scheduler.serve.serve_schedule`, the F1 law): forged rows,
     an absent/empty `schedule_rows_hash` key (§6.3 MANDATORY-PRESENT), and
     counterfactual snapshot-binding mismatches all REFUSE there. This CLI
     never reads schedule rows around the loader. A refusal is CLASSIFIED:
     missing/unparseable artifacts => mode `safe_fallback` with the FIXED
     SAFE SCHEDULE (the services manifest's own cadence, echoed from the
     declared live state) and NEVER permission (§7.4); an integrity refusal
     over a parseable store => mode `serve_refused` with reason
     `rows_hash_key_absent | rows_hash_mismatch | snapshot_hash_mismatch |
     serve_refused:<kernel detail>`. (The availability probe reads bytes only
     to CLASSIFY the loader's refusal — it returns no rows and nothing is
     ever served from it.)
  2. SNAPSHOT FRESHNESS (N3) — recorded epoch wake-input hashes vs the
     DECLARED live hashes, compared symmetrically over the key UNION: ANY
     difference — including recorded-null-but-live-exists and
     live-null-but-recorded-exists — refuses the whole run
     (`stale_snapshot:<key>`). No `is not None and` skip-hole (§6.3).
  3. AUTHORITY (N5), read-only via EXACTLY the pinned §8.4 joint: a
     non-empty declared `ceiling` refuses (`authority:ceiling`); the risk
     class is RE-DERIVED via `risk_of(action_type, policy.risk_classes)`
     when the descriptor carries a compat action_type and the injected
     policy carries the mapping (an underivable action_type fail-safes to
     `authority:propose_only` — the engine's unknown-action law), else the
     descriptor's DECLARED `risk_class` drives; the verdict is
     `resolve_verdict(policy.verdicts, risk, cell_state, posture=,
     postures=)`; `act_with_undo` with a declared `undo_contract` of
     "none"/absent refuses (`authority:undo_gap`); anything outside the
     allow set {auto, act_with_undo, auto_with_veto_window, notify_after}
     refuses `authority:<verdict>` — propose_only, always_gated,
     classifier, standing_grant and every unknown token are all gated here
     (fail-safe). Predicates read risk_class/ceiling/undo_contract/verdict
     ONLY — never `capability` (§5.2 capability-blindness).
  4. BUDGET (N4) — cumulative would-dispatch cost vs the DECLARED live
     remaining budget: overflow refuses (`budget_overflow`) even though the
     planner admitted the row (`decision: select`). Refused rows consume no
     budget.
  5. ORGAN FRESHNESS — the organ manifest's declared
     `freshness_needs.max_staleness_seconds` vs the declared live output
     age: stale refuses (`stale_organ:age=<age>`, `staleness_flagged`) and
     is NEVER auto-permission to run (§12 sim 3). Live-eligibility rechecks
     ride between limbs 5 and 6 (the corpus placement): health-proof
     classification (a probe that RAN and exited non-zero is honestly
     `unhealthy`; only a probe that could not run is `crashed` — the sim-5
     S0 finding) honoring the manifest `fallback`
     (skip=>refused / safe_noop / escalate=>escalation_flagged);
     dependency availability (`dependency_unavailable:<dep>`); declared
     capability/MCP availability (`capability_unavailable:<cap>`) with the
     ORIGINAL capability identity preserved — never a silent substitution
     (§12 sim 9).
  6. IDEMPOTENCY (SF1) — the key is RE-DERIVED from the organ manifest's
     declared `idempotency.key_fields` over the {organ, operation, wake_id}
     context (sha256 of canonical JSON, the corpus dialect); a row-carried
     key is NEVER trusted; a key already present in the shadow log (or
     earlier in this run) refuses (`idempotency_replay`).

AUTHORITY-STATE MODES (the cog4-parity.py precedent, §5.3):
  * HERMETIC (default) — cell state via `graduation.evaluate((f"officer:
    {officer}", lane, action_type), ledger=<rows from --consequence-ledger,
    else []>, now=<--now, else evaluate's default>)`, folded through the
    fail-closed mapping `read_cell_state` pins (exception -> "demote";
    None -> "unmeasured"; out-of-vocabulary -> "demote"). Hermetic mode
    NEVER calls `_act_with_undo_gap` — its probes import the executor doors
    (framework.acting/frontdoor) at call time, exactly what a shadow
    comparator's run closure must exclude; the hermetic undo-gap check is
    the DESCRIPTOR-level one (declared undo_contract "none" under an
    act_with_undo verdict is a gap by declaration).
  * LIVE (`--live-joint`) — cell state via `read_cell_state()` (live
    consequence ledger) and an `act_with_undo` verdict additionally takes
    the `_act_with_undo_gap` fall-through (no mechanically viable undo
    plane -> `authority:undo_gap`). Live mode MAY load the executor doors
    through that call-time probe — operator use only, never the hermetic
    record.

INPUTS — every path CLI-injected (§4.4 layer law; framework holds no
defaults for this CLI): the schedule cache dir; the DECLARED live-state
JSON ({wake_input_hashes, wake_id, remaining_budget[, organ_output_age_
seconds, organ_health, organs_available, capabilities_available,
services_cadence]} — every member is data handed in, never an env/clock
read of this CLI's own); the organ-manifests JSON (object name->manifest or
a list of named manifests); the matrix-policy JSON (the `matrix_policy()`
document shape: verdicts / risk_classes / postures — derived OUTSIDE this
CLI because the §8.4 pin forbids the matrix module here; e.g.
`python3.12 -c "import json,sys; sys.path.insert(0,'.'); from
framework.authority.matrix import load_matrix, matrix_policy;
print(json.dumps(matrix_policy(load_matrix())))"`).

OUTPUT: one JSON outcome record on stdout — {"mode": dispatch |
serve_refused | stale_snapshot | safe_fallback | pointer_tripwire,
"reason", "records": [...], "safe_schedule", "wake_id", "counts",
"shadow_log"} — and the same records APPENDED to the shadow log
(default: <cache-dir>/shadow-log.jsonl) under an O_EXCL lock with the
kernel write discipline reimplemented stdlib-side (O_EXCL tmp + fsync +
os.replace; the §8.4 pin forbids a kernel import here). The CLI writes
ONLY the shadow log. Store literals ("snapshot.json", "schedule.jsonl",
"schedule-manifest.json", "schedule_rows_hash") are documented mirrors of
framework/scheduler/model.py — the model module is off this CLI's pin; the
authoritative integrity check is the kernel's, these names classify only.

EXIT CODES: 0 — served and rechecked (mode dispatch; individual rows may
still be refused — read the records); 2 — run-level integrity refusal
(serve_refused | stale_snapshot); 3 — setup failure (unreadable/malformed
inputs, held shadow-log lock); 4 — safe fallback (missing/corrupt store;
the fixed safe schedule, zero grants); 5 — the §7.4 pointer tripwire.

Imports are pinned symbol-for-symbol by `test_cog4_dispatch_ast_pin.py` /
`lib_cog4_ast_pins.dispatch_import_violations` (§8.4): stdlib | the
framework.scheduler.serve surface | {risk_of, resolve_verdict,
read_cell_state, _act_with_undo_gap} from framework.authority.policy_engine
| graduation.evaluate — so the dispatcher can never grow into an executor.

Provenance: authored per the 2026-07-07 full-autonomy grant + the
2026-07-20 cognitive-masterplan continuous grant; COG-4 W5 x1
(dispatch-shadow, Fable-for-execution named unit).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.scheduler.serve import (  # noqa: E402
    ScheduleRefused, serve_schedule)
from framework.authority.policy_engine import (  # noqa: E402
    risk_of, resolve_verdict, read_cell_state, _act_with_undo_gap)
from framework.fidelity.graduation import evaluate  # noqa: E402

# ---------------------------------------------------------------------------
# vocabulary (corpus-pinned tokens — test_cog4_sim_dispatch.py is the spec)
# ---------------------------------------------------------------------------
MODE_DISPATCH = "dispatch"
MODE_SERVE_REFUSED = "serve_refused"
MODE_STALE_SNAPSHOT = "stale_snapshot"
MODE_SAFE_FALLBACK = "safe_fallback"
MODE_POINTER_TRIPWIRE = "pointer_tripwire"

DECISION_WOULD = "would_dispatch"
DECISION_REFUSED = "refused"
DECISION_SAFE_NOOP = "safe_noop"
DECISION_ESCALATION = "escalation_flagged"

# The allow set — every other verdict token (propose_only, always_gated,
# classifier, standing_grant, and anything unknown) refuses fail-safe (N5).
ALLOW_VERDICTS = frozenset(
    {"auto", "act_with_undo", "auto_with_veto_window", "notify_after"})

# Mirror of policy_engine._CELL_STATES — a LITERAL because the symbol is
# outside this CLI's §8.4 import pin (the cog4-parity.py precedent).
_CELL_STATES = frozenset(
    {"unmeasured", "propose_only", "eligible", "graduated", "demote"})

# Documented mirrors of framework/scheduler/model.py store vocabulary (the
# model module is off this CLI's §8.4 pin). Used ONLY to classify a loader
# refusal / name the shadow log home — never to serve rows.
_SNAPSHOT_FILE = "snapshot.json"
_SCHEDULE_FILE = "schedule.jsonl"
_MANIFEST_FILE = "schedule-manifest.json"
_ROWS_HASH_KEY = "schedule_rows_hash"
_ROW_DECISION_SELECT = "select"

SHADOW_LOG_DEFAULT = "shadow-log.jsonl"
POINTER_DEFAULT = "~/.cabinet/state/cog4-dispatch-pointer"

_EXIT_BY_MODE = {
    MODE_DISPATCH: 0,
    MODE_SERVE_REFUSED: 2,
    MODE_STALE_SNAPSHOT: 2,
    MODE_SAFE_FALLBACK: 4,
    MODE_POINTER_TRIPWIRE: 5,
}


class SetupError(Exception):
    """A whole-run input defect (exit 3) — nothing was rechecked."""


# ---------------------------------------------------------------------------
# canonical bytes (the W2 corpus dialect: sort_keys, compact, ensure_ascii
# False — idempotency keys must reproduce the corpus derivation byte-exactly)
# ---------------------------------------------------------------------------
def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# health classification (§12 sim 5, incl. the S0 exit-1 finding)
# ---------------------------------------------------------------------------
def classify_health(outcome) -> str:
    """A probe that RAN and exited non-zero is an HONEST failing probe —
    `unhealthy` (positive evidence). Only a probe that could not run at all
    (absent record / probe_ran falsy) is `crashed` (no health information;
    absence recorded honestly, never invented)."""
    if not isinstance(outcome, dict) or not outcome.get("probe_ran"):
        return "crashed"
    return "healthy" if outcome.get("exit_code") == 0 else "unhealthy"


# ---------------------------------------------------------------------------
# the authority joint (hermetic | live — the cog4-parity.py two-mode idiom)
# ---------------------------------------------------------------------------
class _AuthorityJoint:
    """Read-only shadow-verdict derivation over the CLI-injected policy
    document. Pure calls into the pinned §8.4 symbols; predicates read the
    descriptor's enforcement members only — never `capability` (§5.2)."""

    def __init__(self, policy: dict, officer: str, lane: str | None,
                 posture: str | None, live_joint: bool,
                 ledger_rows: list, now: datetime | None) -> None:
        self.policy = policy
        self.officer = officer
        self.lane = lane
        self.posture = posture
        self.live_joint = live_joint
        self.ledger_rows = ledger_rows
        self.now = now

    def cell_state(self, action_type: str | None) -> str:
        if self.live_joint:
            return read_cell_state(self.officer, self.lane, action_type)
        cell = (f"officer:{self.officer}", self.lane, action_type)
        try:
            result = evaluate(cell, ledger=self.ledger_rows, now=self.now)
        except Exception:
            return "demote"          # cannot read the evidence plane
        if result is None:
            return "unmeasured"      # the legitimate no-evidence case
        state = (result or {}).get("state")
        return state if state in _CELL_STATES else "demote"

    def check(self, descriptor: dict) -> dict | None:
        """None = the authority limb passes; else a refusal detail dict
        {reason, verdict, ...} (N5: gated/ceiling/undo-gapped refuse)."""
        ceiling = descriptor.get("ceiling")
        if ceiling:
            # non-empty declared ceiling — the hard-ceiling short-circuit;
            # a malformed truthy value refuses the same way (fail-safe).
            return {"reason": "authority:ceiling", "verdict": "ceiling"}

        action_type = descriptor.get("action_type")
        if not (isinstance(action_type, str) and action_type):
            action_type = None

        risk = None
        risk_classes = self.policy.get("risk_classes")
        if action_type is not None and isinstance(risk_classes, dict):
            risk = risk_of(action_type, risk_classes)
            if risk is None:
                # the engine's unknown-action law: no risk_class => fail-safe
                # propose_only — the recheck could not validate the mapping.
                return {"reason": "authority:propose_only",
                        "verdict": "propose_only",
                        "detail": f"action_type {action_type!r} has no "
                                  "policy risk_class"}
        if risk is None:
            declared = descriptor.get("risk_class")
            risk = declared if isinstance(declared, str) and declared else None
        if risk is None:
            return {"reason": "authority:propose_only",
                    "verdict": "propose_only",
                    "detail": "no derivable risk_class (fail-safe)"}

        state = self.cell_state(action_type)
        verdict = resolve_verdict(
            self.policy.get("verdicts"), risk, state,
            posture=self.posture, postures=self.policy.get("postures"))

        if verdict == "act_with_undo":
            undo = descriptor.get("undo_contract")
            if not isinstance(undo, str) or not undo or undo == "none":
                # declared undo gap: the verdict requires an undo plane the
                # descriptor declares it does not have (N5).
                return {"reason": "authority:undo_gap", "verdict": "undo_gap",
                        "cell_state": state, "risk_class": risk}
            if self.live_joint and _act_with_undo_gap(action_type or "") is not None:
                # live mechanical-viability fall-through (policy-engine law).
                return {"reason": "authority:undo_gap", "verdict": "undo_gap",
                        "cell_state": state, "risk_class": risk}

        if verdict not in ALLOW_VERDICTS:
            return {"reason": f"authority:{verdict}", "verdict": verdict,
                    "cell_state": state, "risk_class": risk}
        return None


# ---------------------------------------------------------------------------
# store-refusal classification (availability vs integrity — §7.4 vs §6.3)
# ---------------------------------------------------------------------------
def _probe_availability(cache_dir: Path) -> str:
    """Classify ONLY (no rows are ever served from this probe): `missing` —
    any artifact absent; `corrupt` — any artifact unreadable/unparseable;
    `ok` — all three parse (the refusal was an integrity limb)."""
    paths = {name: cache_dir / name
             for name in (_SNAPSHOT_FILE, _SCHEDULE_FILE, _MANIFEST_FILE)}
    if not all(p.is_file() for p in paths.values()):
        return "missing"
    try:
        json.loads(paths[_SNAPSHOT_FILE].read_text(encoding="utf-8"))
        json.loads(paths[_MANIFEST_FILE].read_text(encoding="utf-8"))
        for line in paths[_SCHEDULE_FILE].read_text(
                encoding="utf-8").splitlines():
            if line.strip():
                json.loads(line)
    except FileNotFoundError:
        return "missing"
    except (OSError, ValueError, UnicodeDecodeError):
        return "corrupt"
    return "ok"


def _classify_refusal(cache_dir: Path, message: str) -> tuple[str, str]:
    """(mode, reason) for a ScheduleRefused: missing/corrupt => the §7.4 safe
    fallback; a parseable store => the §6.3 integrity token (mirroring the
    kernel limb order: absent key < rows-hash mismatch < snapshot binding)."""
    availability = _probe_availability(cache_dir)
    if availability != "ok":
        return MODE_SAFE_FALLBACK, f"store_{availability}"
    try:
        manifest = json.loads(
            (cache_dir / _MANIFEST_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):                      # raced away — conservative
        return MODE_SAFE_FALLBACK, "store_corrupt"
    key = manifest.get(_ROWS_HASH_KEY) if isinstance(manifest, dict) else None
    if not isinstance(key, str) or not key:
        return MODE_SERVE_REFUSED, "rows_hash_key_absent"
    if "rows-hash mismatch" in message:
        return MODE_SERVE_REFUSED, "rows_hash_mismatch"
    if "!= sha256(snapshot record)" in message:
        return MODE_SERVE_REFUSED, "snapshot_hash_mismatch"
    return MODE_SERVE_REFUSED, f"serve_refused:{message}"


# ---------------------------------------------------------------------------
# records
# ---------------------------------------------------------------------------
def _capability_of(row: dict) -> str:
    descriptor = row.get("descriptor")
    if isinstance(descriptor, dict):
        cap = descriptor.get("capability")
        if isinstance(cap, str) and cap:
            return cap
    operation = str(row.get("operation"))
    if "/" in operation:
        return operation
    return f"{row.get('organ')}/{operation}"


def _record(row: dict, decision: str, reason: str, limb: str, **extra) -> dict:
    descriptor = row.get("descriptor")
    rec = {
        "organ": row.get("organ"),
        "operation": row.get("operation"),
        "capability": _capability_of(row),
        "descriptor": dict(descriptor) if isinstance(descriptor, dict) else descriptor,
        "decision": decision,
        "reason": reason,
        "limb": limb,
        "planner_admitted": row.get("decision") == _ROW_DECISION_SELECT,
    }
    rec.update(extra)
    return rec


def _dep_tokens(value) -> list | None:
    """Normalize a deps declaration to prefix tokens: the real fold's
    {"organs": [...], "capabilities": [...]} object or the manifest/fixture
    prefix-list ("organ:<name>" | "<capability>"). None = unreadable."""
    if value is None:
        return []
    if isinstance(value, dict):
        organs = value.get("organs") or []
        caps = value.get("capabilities") or []
        if not isinstance(organs, list) or not isinstance(caps, list):
            return None
        return [f"organ:{o}" for o in organs] + [str(c) for c in caps]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return None


# ---------------------------------------------------------------------------
# the per-row limbs (3..6 + the live-eligibility rechecks)
# ---------------------------------------------------------------------------
def _recheck_rows(rows: list, live: dict, manifests: dict, joint: _AuthorityJoint,
                  replay_keys: set) -> list:
    records: list = []
    cumulative = 0
    seen = set(replay_keys)
    remaining = live["remaining_budget"]
    ages = live.get("organ_output_age_seconds") or {}
    health_ledger = live.get("organ_health") or {}
    organs_available = set(live.get("organs_available") or [])
    caps_available = set(live.get("capabilities_available") or [])

    for row in rows:
        organ = row.get("organ")

        # planner-deferred rows are recorded honestly and recheck nothing —
        # the planner never admitted them (no budget, no key, no grant).
        if row.get("decision") != _ROW_DECISION_SELECT:
            records.append(_record(
                row, DECISION_REFUSED,
                f"planner_deferred:{row.get('reason')}", "planner"))
            continue

        descriptor = row.get("descriptor")
        if not isinstance(descriptor, dict):
            records.append(_record(row, DECISION_REFUSED,
                                   "descriptor_unreadable", "authority"))
            continue

        # ---- limb 3: AUTHORITY (before budget — the §7.3 order) -----------
        refusal = joint.check(descriptor)
        if refusal is not None:
            reason = refusal.pop("reason")
            records.append(_record(row, DECISION_REFUSED, reason,
                                   "authority", **refusal))
            continue

        # ---- limb 4: BUDGET ----------------------------------------------
        units = row.get("budget_units")
        if not isinstance(units, int) or isinstance(units, bool) or units < 0:
            records.append(_record(row, DECISION_REFUSED,
                                   "budget_underivable", "budget"))
            continue
        if cumulative + units > remaining:
            records.append(_record(row, DECISION_REFUSED,
                                   "budget_overflow", "budget"))
            continue

        # ---- manifest presence (limbs 5/6 read it) ------------------------
        manifest_for = manifests.get(organ)
        if not isinstance(manifest_for, dict):
            records.append(_record(row, DECISION_REFUSED,
                                   f"organ_manifest_missing:{organ}",
                                   "eligibility"))
            continue

        # ---- limb 5: ORGAN FRESHNESS --------------------------------------
        freshness = manifest_for.get("freshness_needs")
        need = freshness.get("max_staleness_seconds") \
            if isinstance(freshness, dict) else None
        if not isinstance(need, (int, float)) or isinstance(need, bool):
            records.append(_record(row, DECISION_REFUSED,
                                   "freshness_underivable", "freshness"))
            continue
        age = ages.get(organ)
        if isinstance(age, (int, float)) and not isinstance(age, bool) \
                and age > need:
            records.append(_record(row, DECISION_REFUSED,
                                   f"stale_organ:age={age}", "freshness",
                                   staleness_flagged=True))
            continue

        # ---- live-eligibility rechecks (sims 5/6/9; corpus placement) -----
        health = classify_health(health_ledger.get(organ))
        if health != "healthy":
            fallback = manifest_for.get("fallback")
            if fallback == "safe_noop":
                records.append(_record(
                    row, DECISION_SAFE_NOOP,
                    f"health_{health}:fallback_safe_noop", "eligibility",
                    health=health, fallback=fallback))
            elif fallback == "escalate":
                records.append(_record(
                    row, DECISION_ESCALATION,
                    f"health_{health}:fallback_escalate", "eligibility",
                    health=health, fallback=fallback))
            else:
                records.append(_record(
                    row, DECISION_REFUSED,
                    f"health_{health}:fallback_skip", "eligibility",
                    health=health, fallback=fallback))
            continue

        row_tokens = _dep_tokens(row.get("deps"))
        manifest_tokens = _dep_tokens(manifest_for.get("dependencies"))
        if row_tokens is None or manifest_tokens is None:
            records.append(_record(row, DECISION_REFUSED,
                                   "deps_unreadable", "eligibility"))
            continue
        dep_missing = None
        for dep in sorted(set(row_tokens) | set(manifest_tokens)):
            if dep.startswith("organ:"):
                if dep.split(":", 1)[1] not in organs_available:
                    dep_missing = dep
                    break
            elif dep not in caps_available:
                dep_missing = dep
                break
        if dep_missing is not None:
            records.append(_record(row, DECISION_REFUSED,
                                   f"dependency_unavailable:{dep_missing}",
                                   "eligibility"))
            continue

        permissions = manifest_for.get("permissions") or []
        capability_missing = next(
            (p for p in permissions if p not in caps_available), None)
        if capability_missing is not None:
            records.append(_record(
                row, DECISION_REFUSED,
                f"capability_unavailable:{capability_missing}", "eligibility"))
            continue

        # ---- limb 6: IDEMPOTENCY (SF1 — re-derived, never trusted) --------
        discipline = manifest_for.get("idempotency")
        fields = discipline.get("key_fields") \
            if isinstance(discipline, dict) else None
        context = {"organ": organ, "operation": row.get("operation"),
                   "wake_id": live["wake_id"]}
        if (not isinstance(fields, list) or not fields
                or any(not isinstance(f, str) for f in fields)
                or any(f not in context for f in fields)):
            records.append(_record(row, DECISION_REFUSED,
                                   "idempotency_underivable", "idempotency"))
            continue
        key = _digest(_canon({f: context[f] for f in fields}))
        if key in seen:
            records.append(_record(row, DECISION_REFUSED,
                                   "idempotency_replay", "idempotency",
                                   idempotency_key=key))
            continue

        seen.add(key)
        cumulative += units
        records.append(_record(row, DECISION_WOULD, "all_limbs_green",
                               "none", idempotency_key=key))

    return records


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
def run_shadow_dispatch(cache_dir: Path, live: dict, manifests: dict,
                        joint: _AuthorityJoint, replay_keys: set) -> dict:
    """The §7.3 comparator over one served schedule. PURE over the store:
    reads via the one loader, returns the outcome dict, executes nothing;
    the caller owns the shadow-log append."""
    # ---- limb 1: SERVE (the one kernel-bound loader; F1) ------------------
    try:
        served = serve_schedule(cache_dir)
    except ScheduleRefused as exc:
        mode, reason = _classify_refusal(cache_dir, str(exc))
        outcome = {"mode": mode, "reason": reason, "records": [],
                   "safe_schedule": None, "serve_detail": str(exc)}
        if mode == MODE_SAFE_FALLBACK:
            # §7.4: the FIXED SAFE SCHEDULE (the services manifest's own
            # cadence, echoed from declared live state) — NEVER permission.
            outcome["safe_schedule"] = list(live.get("services_cadence") or [])
        return outcome

    # ---- limb 2: SNAPSHOT FRESHNESS (N3 — symmetric over the union) -------
    recorded = served["manifest"]["epoch"]["wake_input_hashes"]
    live_hashes = live["wake_input_hashes"]
    for key in sorted(set(recorded) | set(live_hashes)):
        if recorded.get(key) != live_hashes.get(key):
            return {"mode": MODE_STALE_SNAPSHOT,
                    "reason": f"stale_snapshot:{key}",
                    "records": [], "safe_schedule": None}

    # ---- limbs 3..6 per decision row --------------------------------------
    records = _recheck_rows(served["rows"], live, manifests, joint,
                            replay_keys)
    return {"mode": MODE_DISPATCH, "reason": None, "records": records,
            "safe_schedule": None,
            "schedule_rows_hash": served["schedule_rows_hash"]}


# ---------------------------------------------------------------------------
# shadow log (read for SF1 replay; atomic append — kernel discipline,
# stdlib-side)
# ---------------------------------------------------------------------------
def read_shadow_log(path: Path) -> list:
    if not path.exists():
        return []
    rows: list = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SetupError(f"shadow log {path} unreadable: "
                         f"{type(exc).__name__}") from None
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            raise SetupError(
                f"shadow log {path} line {lineno} is not JSON — a corrupt "
                "shadow record cannot gate replays; repair or move it") \
                from None
        if isinstance(row, dict):
            rows.append(row)
    return rows


def append_shadow_log(path: Path, new_rows: list) -> None:
    """Append records atomically: O_EXCL lock (losers fail LOUD, §7.5 idiom)
    + O_EXCL tmp + fsync + os.replace (the kernel (e) discipline,
    reimplemented stdlib-side — the §8.4 pin forbids a kernel import)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    try:
        lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SetupError(
            f"shadow-log lock held: {lock} exists — another dispatcher owns "
            "this log (losers fail loud, never race; delete the lock to "
            "recover from a crashed writer)") from None
    try:
        os.write(lock_fd, str(os.getpid()).encode("ascii"))
        existing = path.read_bytes() if path.exists() else b""
        payload = existing + b"".join(
            _canon(row) + b"\n" for row in new_rows)
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise SetupError(
                f"shadow-log tmp exists: {tmp} — a crashed writer left it; "
                "delete it to recover") from None
        try:
            os.write(tmp_fd, payload)
            os.fsync(tmp_fd)
        finally:
            os.close(tmp_fd)
        os.replace(tmp, path)
    finally:
        os.close(lock_fd)
        lock.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------
def _load_json(path_arg: str, name: str):
    try:
        return json.loads(Path(path_arg).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SetupError(f"{name} {path_arg!r} unreadable: "
                         f"{type(exc).__name__}: {exc}") from None


def load_live_state(path_arg: str) -> dict:
    live = _load_json(path_arg, "live-state file")
    if not isinstance(live, dict):
        raise SetupError("live-state file must be a JSON object")
    if not isinstance(live.get("wake_input_hashes"), dict):
        raise SetupError("live state needs wake_input_hashes (object; the "
                         "declared live hashes — values may be null)")
    wake_id = live.get("wake_id")
    if not isinstance(wake_id, str) or not wake_id:
        raise SetupError("live state needs a non-empty wake_id string")
    budget = live.get("remaining_budget")
    if not isinstance(budget, int) or isinstance(budget, bool):
        raise SetupError("live state needs an integer remaining_budget")
    for member, kind in (("organ_output_age_seconds", dict),
                         ("organ_health", dict),
                         ("organs_available", list),
                         ("capabilities_available", list),
                         ("services_cadence", list)):
        if member in live and not isinstance(live[member], kind):
            raise SetupError(f"live state {member} must be a "
                             f"{kind.__name__}")
    return live


def load_manifests(path_arg: str) -> dict:
    data = _load_json(path_arg, "organ-manifests file")
    if isinstance(data, list):
        out: dict = {}
        for entry in data:
            if not isinstance(entry, dict) or not isinstance(
                    entry.get("name"), str) or not entry["name"]:
                raise SetupError("organ-manifest list entries must be "
                                 "objects with a non-empty name")
            if entry["name"] in out:
                raise SetupError(
                    f"duplicate organ manifest {entry['name']!r}")
            out[entry["name"]] = entry
        return out
    if isinstance(data, dict):
        for name, manifest in data.items():
            if not isinstance(manifest, dict):
                raise SetupError(
                    f"organ manifest {name!r} must be an object")
        return data
    raise SetupError("organ-manifests file must be an object "
                     "{name: manifest} or a list of named manifests")


def load_policy(path_arg: str) -> dict:
    policy = _load_json(path_arg, "matrix-policy file")
    if not isinstance(policy, dict):
        raise SetupError("matrix-policy file must be a JSON object (the "
                         "matrix_policy() document shape)")
    return policy


def _load_ledger_rows(path_arg: str | None) -> list:
    if path_arg is None:
        return []
    rows: list = []
    text_source = _load_json_lines_text(path_arg)
    for lineno, line in enumerate(text_source.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise SetupError(f"consequence ledger {path_arg!r} line "
                             f"{lineno}: not JSON ({exc})") from None
        if not isinstance(row, dict):
            raise SetupError(f"consequence ledger {path_arg!r} line "
                             f"{lineno}: row is not an object")
        rows.append(row)
    return rows


def _load_json_lines_text(path_arg: str) -> str:
    try:
        return Path(path_arg).read_text(encoding="utf-8")
    except OSError as exc:
        raise SetupError(f"consequence ledger {path_arg!r} unreadable: "
                         f"{type(exc).__name__}") from None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cog4-dispatch-shadow.py",
        description="COG-4 §7.3 shadow dispatch comparator — serves the "
                    "schedule through the kernel loader, rechecks the "
                    "charter quadruple per decision row, appends "
                    "would_dispatch|refused records; NEVER executes.")
    p.add_argument("--cache-dir", required=True,
                   help="the schedule store dir (CLI-injected, §4.4)")
    p.add_argument("--live", required=True,
                   help="declared live-state JSON (wake_input_hashes, "
                        "wake_id, remaining_budget, ...)")
    p.add_argument("--organ-manifests", required=True,
                   help="organ manifests JSON ({name: manifest} or a list "
                        "of named manifests)")
    p.add_argument("--matrix-policy", required=True,
                   help="matrix policy JSON (the matrix_policy() document "
                        "shape — derived outside this CLI, see docstring)")
    p.add_argument("--shadow-log", default=None,
                   help=f"shadow decision log (default: "
                        f"<cache-dir>/{SHADOW_LOG_DEFAULT})")
    p.add_argument("--officer", default="cos",
                   help="graduation-cell officer identity (default: cos)")
    p.add_argument("--lane", default=None,
                   help="graduation-cell lane (default: none)")
    p.add_argument("--posture", default=None,
                   choices=("guardian", "earn_up", "sovereign"),
                   help="verdict-table posture (default: the guardian root)")
    p.add_argument("--consequence-ledger", default=None,
                   help="JSONL rows for graduation.evaluate's ledger seam "
                        "(hermetic mode; default: empty ledger)")
    p.add_argument("--now", default=None,
                   help="ISO timestamp pinning evaluate's clock "
                        "(hermetic mode)")
    p.add_argument("--live-joint", action="store_true",
                   help="use the LIVE authority joint (read_cell_state + "
                        "the _act_with_undo_gap fall-through) — machine-"
                        "state-dependent; may load the executor doors at "
                        "call time; operator use only")
    p.add_argument("--pointer-path", default=POINTER_DEFAULT,
                   help="the §7.4 cutover-pointer tripwire path (default: "
                        f"{POINTER_DEFAULT}; existing AT ALL refuses)")
    return p


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.live_joint and (args.consequence_ledger or args.now):
            raise SetupError("--live-joint reads the live joint; "
                             "--consequence-ledger/--now are hermetic-mode "
                             "seams — pick one mode")
        now = None
        if args.now is not None:
            try:
                now = datetime.fromisoformat(args.now)
            except ValueError as exc:
                raise SetupError(f"--now is not ISO-8601: {exc}") from None
            if now.tzinfo is None:
                raise SetupError("--now must carry a timezone offset")
        cache_dir = Path(args.cache_dir)
        live = load_live_state(args.live)
        manifests = load_manifests(args.organ_manifests)
        policy = load_policy(args.matrix_policy)
        ledger_rows = _load_ledger_rows(args.consequence_ledger)
        shadow_log = Path(args.shadow_log) if args.shadow_log \
            else cache_dir / SHADOW_LOG_DEFAULT
        pointer = Path(os.path.expanduser(args.pointer_path))
    except SetupError as exc:
        print(f"[cog4-dispatch-shadow] SETUP FAILURE: {exc}",
              file=sys.stderr)
        return 3

    wake_id = live.get("wake_id")

    # ---- the §7.4 tripwire: a cutover pointer existing AT ALL refuses -----
    if pointer.exists():
        outcome = {"mode": MODE_POINTER_TRIPWIRE,
                   "reason": f"pointer_tripwire:{pointer}",
                   "records": [], "safe_schedule": None,
                   "wake_id": wake_id, "shadow_log": str(shadow_log)}
        print(f"[cog4-dispatch-shadow] REFUSED — the §7.4 cutover pointer "
              f"exists at {pointer}: no pointer file may exist this phase "
              "(shadow-only; the cutover is a future amendment). Remove it "
              "and re-run the phase verify.", file=sys.stderr)
        try:
            append_shadow_log(shadow_log, [
                {"record_kind": "run", "mode": MODE_POINTER_TRIPWIRE,
                 "reason": outcome["reason"], "wake_id": wake_id}])
        except SetupError as exc:
            print(f"[cog4-dispatch-shadow] (tripwire record not appended: "
                  f"{exc})", file=sys.stderr)
        print(json.dumps(outcome, sort_keys=True))
        return _EXIT_BY_MODE[MODE_POINTER_TRIPWIRE]

    joint = _AuthorityJoint(policy, args.officer, args.lane, args.posture,
                            args.live_joint, ledger_rows, now)

    try:
        replay_keys = {row["idempotency_key"] for row in
                       read_shadow_log(shadow_log)
                       if isinstance(row.get("idempotency_key"), str)}
        outcome = run_shadow_dispatch(cache_dir, live, manifests, joint,
                                      replay_keys)
        outcome["wake_id"] = wake_id
        outcome["shadow_log"] = str(shadow_log)
        counts = {"rows": len(outcome["records"])}
        for rec in outcome["records"]:
            counts[rec["decision"]] = counts.get(rec["decision"], 0) + 1
        outcome["counts"] = counts

        appended = [{"record_kind": "run", "mode": outcome["mode"],
                     "reason": outcome["reason"], "wake_id": wake_id,
                     "schedule_rows_hash":
                         outcome.get("schedule_rows_hash")}]
        appended += [dict(rec, record_kind="decision", wake_id=wake_id)
                     for rec in outcome["records"]]
        append_shadow_log(shadow_log, appended)
    except SetupError as exc:
        print(f"[cog4-dispatch-shadow] SETUP FAILURE: {exc}",
              file=sys.stderr)
        return 3

    print(json.dumps(outcome, sort_keys=True))
    if outcome["mode"] != MODE_DISPATCH:
        print(f"[cog4-dispatch-shadow] {outcome['mode'].upper()} — "
              f"{outcome['reason']} (zero grants)", file=sys.stderr)
    return _EXIT_BY_MODE[outcome["mode"]]


if __name__ == "__main__":
    sys.exit(main())
