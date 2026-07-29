"""Authority matrix loader + fail-closed validator (the matrix as DATA) [T5].

`framework/policies/authority-matrix.yml` is the canonical, Captain-readable
policy *document* — risk-class rows × confidence-state columns → verdict. This
module is the thin, germline loader/validator that reads it and schema-checks
it against the TWO sources of truth it must agree with:

  * `framework.authority.classifier.ACTION_TYPES` — the ONE shared action-type
    enum the gate and the consequence emitter both use. Every action_type the
    matrix maps to a risk_class must be a member (minus the AMBIGUOUS backstop,
    which deliberately has no risk_class and falls through to propose-only).
  * `framework.learning.capability_gaps.HARD_CEILING_TOUCHES` — the code-level
    hard-ceiling backstop. `ceiling_frozenset_map.values()` must equal it
    EXACTLY (all six members, never a self-fulfilling "mappable subset")
    [FIX-7].

FAIL-CLOSED (Corridor + design §error-handling): the loader/validator NEVER
silently passes a malformed or autonomy-widening matrix — anything unknown,
mistyped, missing, or extra raises `MatrixValidationError`. Four safety
invariants are enforced as hard rules, not prose:

  1. No prod/ceiling cell may resolve to `auto` [FIX-6]. A hard-ceiling row is
     `always_gated` for every state (a POSTURE table may narrow that to the
     conditional `standing_grant` — never to `auto`).
  2. The hard ceiling covers all six HARD_CEILING_TOUCHES members [FIX-7].
  3. TRUST-INVERSION floor [CAPTAIN-RULING 2026-07-03/04 earn-demotion ruling,
     widened 2026-07-04 by fix wave wsqzqfpt5]: no reversible / act_with_undo
     class may be `propose_only` at `unmeasured` (trust is granted day-one and
     lost on demotion EVIDENCE — never pre-earned), and any acting-from-day-one
     row must land on `propose_only` at `demote` so the demotion path always
     has teeth. Enforced by `_validate_act_first_floor` so no future preset or
     instance merge can silently re-introduce earn-up.
  4. The OPTIONAL `postures:` key (sovereign build spec 2026-07-04 §2.1) may
     only define FULL verdict tables for known non-default postures
     (`sovereign` in v1; + `earn_up` since the axes build). A
     `postures.guardian` key is REJECTED — the root `verdicts` table IS
     guardian and is never redefined. Posture ceiling rows are wildcard-only
     in {always_gated, standing_grant} (`auto` structurally impossible in
     EVERY posture), `standing_grant` never appears in the root table or on a
     non-ceiling row, and the demote column is posture-invariant vs the root
     table (evidence beats posture). Together with invariant 3 the two
     compose, never trade off: no posture makes a demote cell act, and the
     trust-inversion floor holds on the root/guardian table in every posture.
     (RECONCILE 2026-07-05: kept both — HEAD's trust-inversion floor [#3] +
     sovereign's posture rules [#4].)
  5. EARN_UP-ONLY-NARROWS [axes spec 2026-07-05 §1]: every `postures.earn_up`
     cell must be no more permissive than the corresponding root/guardian
     cell on the VERDICT_PERMISSIVENESS ordering, and `standing_grant` is
     forbidden anywhere in earn_up (ceilings stay always_gated). A table that
     can only narrow is fail-safe by construction — this is what makes
     earn_up selectable WITHOUT attestation in the posture kernel.

This is matrix-as-DATA only — no gate behavior and no live side-effects on
import or load. The one opt-in exception is `check_gate_actor_id_parity()`
(and the `__main__` CI probe that calls it): it writes two SYNTHETIC
consequence rows to a private temp ledger (CABINET_EVENT_LOG_DIR re-pointed
for the probe duration, restored in `finally`) to prove a bare-role acted row
is visible to the gate's `read_cell_state` — it can never touch the live
audit ledger. System Python is 3.9.6 with no `jsonschema` dependency, so the
validator is hand-rolled (additionalProperties:false at every level), mirroring
`framework/fidelity/consequence.py`. The loader uses `yaml.safe_load` (no
arbitrary object construction) and reads only an explicit, caller-controlled
path — no interpolation from untrusted input.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

from framework import env  # noqa: E402 — declared-operation shape predicate
from framework.authority.classifier import (  # noqa: E402
    ACTION_TYPES,
    AMBIGUOUS,
    CEILING_CLASS_ACTION_TYPES,
)
from framework.learning.capability_gaps import HARD_CEILING_TOUCHES  # noqa: E402


class MatrixValidationError(Exception):
    """Raised when the authority matrix violates its schema or a safety
    invariant. Fail-closed: any malformed/widening matrix raises, never passes.
    """


# ---------------------------------------------------------------------------
# Canonical vocab (the closed sets the validator enforces)
# ---------------------------------------------------------------------------

# The thirteen risk classes: the trust-first act-with-undo classes
# (reversible, pm_write, calendar_write), the 2026-07-04 split-outs from the
# old reversible bucket (read_only_dispatch = act-and-tell investigation runs;
# draft_only = act-and-tell draft composition since CAPTAIN-RULING 2026-07-26,
# earn-up before that), the earn-up rows (internal_comms, deploy_nonprod), and
# the six execution-surface hard ceilings. Closed set: the YAML's risk_classes AND verdicts keys must equal
# it exactly (additionalProperties:false in both directions).
RISK_CLASSES = frozenset({
    "reversible", "read_only_dispatch", "draft_only",
    "pm_write", "calendar_write",
    "internal_comms", "external_comms",
    "deploy_nonprod", "deploy_prod", "spend",
    "secrets", "network_write", "credentials_grant",
})

# The verdicts a cell may carry. `standing_grant` is legal ONLY on a
# hard-ceiling row of a posture table (never in the root/guardian table, never
# on a non-ceiling row): auto IFF a Captain-signed, locked, unexpired,
# unrevoked standing grant with a satisfied hard-scope predicate exists — else
# file a NEED and gate [D2].
VERDICTS = frozenset({
    "auto", "act_with_undo", "auto_with_veto_window", "notify_after",
    "propose_only", "always_gated", "classifier", "standing_grant",
})

# Non-default postures the floor may define full verdict tables for (§2.1;
# earn_up joined in the axes build, spec 2026-07-05 §1). Guardian is NEVER a
# member — the root `verdicts` table IS guardian, and the validator rejects a
# `postures.guardian` key outright [D1].
POSTURES = frozenset({"earn_up", "sovereign"})

# Verdict permissiveness — the earn_up narrows-validator's ruler (AX-1 frozen
# ordering). act_with_undo and notify_after share a rank (both act-first with
# a different oversight handle). `standing_grant` deliberately carries NO
# rank: it is ceiling-row-only, forbidden in earn_up and in the root table,
# so it is never orderable against them.
VERDICT_PERMISSIVENESS = {
    "always_gated": 0,
    "propose_only": 1,
    "classifier": 2,
    "auto_with_veto_window": 3,
    "act_with_undo": 4,
    "notify_after": 4,
    "auto": 5,
}

# Confidence states (F's graduation states). Non-ceiling rows must cover all
# five; ceiling rows use the "*" wildcard.
CONFIDENCE_STATES = frozenset({
    "unmeasured", "propose_only", "eligible", "graduated", "demote",
})

# TRUST-INVERSION beachhead pins [CAPTAIN-RULING 2026-07-03/04, widened
# 2026-07-04 (wsqzqfpt5)]: the classes that act from day one, and the EXACT
# verdict each must carry at `unmeasured`. Name-anchored on purpose — these two
# rows are the doctrine's beachhead, so their unmeasured cells are pinned by
# equality (not merely "not propose_only"): `auto` here would be a WIDENING
# (dropping the undo/tell handle), `always_gated`/`propose_only` a silent
# earn-up regression. deploy_nonprod is deliberately absent (CAPTAIN-RULING:
# prod-adjacent — it keeps earn-up). draft_only ALSO acts from day one since
# CAPTAIN-RULING 2026-07-26 (notify_after at every non-demote state — see the
# YAML's draft_only row) but is deliberately NOT pinned here: this dict defends
# the preset/instance MERGE channel, and load_policies already REFUSES any
# preset/instance policy typed authority_matrix or named authority-matrix
# outright (policy_engine._is_authority_matrix_policy; the instance policy dir
# is schg-locked besides), so for this row the only remaining channel is a
# direct edit of the floor file — which the shipped-table pins in
# framework/authority/tests/test_matrix.py + test_matrix_postures.py catch.
# Adding a fourth entry would also breach the framework production-line budget
# (cognitive-architecture-census, at its ceiling), and a safety pin is not
# worth buying with a raised threshold.
_TRUST_FIRST_UNMEASURED = {
    "reversible": "act_with_undo",
    "read_only_dispatch": "notify_after",
}

# The action_types the matrix is allowed to map (the shared enum minus the
# propose-defaulting AMBIGUOUS backstop — it has no risk_class on purpose).
_MAPPABLE_ACTION_TYPES = frozenset(ACTION_TYPES) - {AMBIGUOUS}

# additionalProperties:false key sets.
_ROOT_KEYS = {"version", "policies"}
_ROOT_REQUIRED = ("version", "policies")
_POLICY_KEYS = {
    "name", "type", "message", "description",
    "risk_classes", "hard_ceiling", "ceiling_frozenset_map", "verdicts",
    "veto_window_minutes", "deploy", "bars", "cooldown_days",
    "postures",  # OPTIONAL (back-compat): per-posture verdict tables [§2.1]
}
_POLICY_REQUIRED = (
    "name", "type", "message",
    "risk_classes", "hard_ceiling", "ceiling_frozenset_map", "verdicts",
    "veto_window_minutes", "deploy", "bars", "cooldown_days",
)
_RISK_CLASS_KEYS = {"action_types"}
_POSTURE_ENTRY_KEYS = {"verdicts"}
_DEPLOY_KEYS = {"safe_globs", "high_risk_globs"}
_BAR_KEYS = {"match_rate", "samples", "max_divergent_last10", "recency_clean_days"}


# ---------------------------------------------------------------------------
# Path + load
# ---------------------------------------------------------------------------

def matrix_path(cabinet_root: str | None = None) -> Path:
    """Return the framework-floor authority-matrix.yml path.

    Resolves from `cabinet_root` (arg → CABINET_ROOT env → the repo root this
    module ships in). No interpolation from untrusted input — a fixed relative
    suffix under a controlled root.
    """
    if cabinet_root is None:
        cabinet_root = os.environ.get("CABINET_ROOT") or str(_FRAMEWORK_ROOT)
    return Path(cabinet_root) / "framework" / "policies" / "authority-matrix.yml"


def load_matrix(path: str | None = None, *, validate: bool = True) -> dict[str, Any]:
    """Load + (by default) validate the authority matrix YAML.

    `path` is an explicit file path; when omitted the framework floor is used.
    Uses `yaml.safe_load` (no arbitrary Python object construction). Raises
    `MatrixValidationError` on a missing/unreadable file or a YAML parse error,
    and (when `validate`) on any schema/invariant violation. Fail-closed: a
    caller that does not catch the error gets no matrix, never a partial one.
    """
    import yaml  # deferred — available in the cabinet runtime + CI

    p = Path(path) if path is not None else matrix_path()
    try:
        text = p.read_text()
    except OSError as exc:
        raise MatrixValidationError(f"cannot read authority matrix at {p}: {exc}")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MatrixValidationError(f"authority matrix is not valid YAML: {exc}")

    # Join the deployment's declared operations onto the floor BEFORE
    # validation, so what is validated is what the gate will read. A
    # deployment that declared none gets a byte-identical floor.
    try:
        bind_declared_operations(matrix_policy(data))
    except Exception:
        pass                                  # unbound ⇒ propose-only, never wider

    if validate:
        validate_matrix(data)
    return data


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

def matrix_policy(data: dict[str, Any]) -> dict[str, Any]:
    """Return the single `authority_matrix`-typed policy entry.

    Raises if absent or duplicated — the floor ships exactly one.
    """
    if not isinstance(data, dict) or not isinstance(data.get("policies"), list):
        raise MatrixValidationError("matrix has no policies list")
    matches = [
        p for p in data["policies"]
        if isinstance(p, dict) and p.get("type") == "authority_matrix"
    ]
    if len(matches) != 1:
        raise MatrixValidationError(
            f"expected exactly one authority_matrix policy, found {len(matches)}"
        )
    return matches[0]


def bind_declared_operations(policy: dict[str, Any]) -> dict[str, Any]:
    """Bind this deployment's declared operations into the floor's risk
    classes, in place, and return the policy.

    The floor decides the CLASSES of consequence and what each earns; the
    deployment decides which of its operations fall in them. This is the join,
    and it is the whole reason the ladder can move for work the shipped
    vocabulary does not describe.

    Fail-closed at every step, because every drop here leaves an operation
    unclassified and therefore propose-only:
      * a row whose declared class is not a class this floor has is DROPPED —
        binding it anywhere else would be the framework guessing;
      * an id already mapped (to any class) is DROPPED — the mapping stays a
        function, and a declaration can never re-point an existing binding;
      * a non-namespaced id is DROPPED — the shape is what keeps the two
        vocabularies from colliding;
      * any exception at all leaves the floor exactly as it shipped.
    """
    try:
        rows = env.declared_operations()
        if not rows:
            return policy
        risk_classes = policy.get("risk_classes")
        if not isinstance(risk_classes, dict):
            return policy
        already = {
            at
            for rc in risk_classes.values() if isinstance(rc, dict)
            for at in (rc.get("action_types") or [])
        }
        for row in rows:
            oid, rc_name = row["id"], row["risk_class"]
            if oid in already or not env.is_declared_operation_id(oid):
                continue
            entry = risk_classes.get(rc_name)
            if not isinstance(entry, dict) or not isinstance(
                    entry.get("action_types"), list):
                continue
            entry["action_types"].append(oid)
            already.add(oid)
    except Exception:
        return policy
    return policy


def ceiling_members(policy: dict[str, Any]) -> set[str]:
    """The set of HARD_CEILING_TOUCHES members the matrix's ceiling map covers."""
    cmap = policy.get("ceiling_frozenset_map", {})
    if not isinstance(cmap, dict):
        raise MatrixValidationError("ceiling_frozenset_map must be a mapping")
    return set(cmap.values())


def no_ceiling_or_prod_auto(policy: dict[str, Any]) -> bool:
    """True iff NO hard-ceiling (incl. prod) row carries an `auto` verdict [FIX-6].

    Sweeps the root/guardian table AND every `postures.*` table — the
    invariant holds in EVERY posture. Deterministic check the CI test calls
    directly.
    """
    tables = [policy.get("verdicts", {})]
    postures = policy.get("postures", {})
    if isinstance(postures, dict):
        for entry in postures.values():
            if isinstance(entry, dict) and isinstance(entry.get("verdicts"), dict):
                tables.append(entry["verdicts"])
    for verdicts in tables:
        for rc in policy.get("hard_ceiling", []):
            for verdict in verdicts.get(rc, {}).values():
                if verdict == "auto":
                    return False
    return True


def check_gate_actor_id_parity(officer: "str | None" = None) -> bool:
    """Parity probe: a synthetic acted row written with the CANONICAL bare-role
    actor id ({"kind": "officer", "id": <bare role>}) must be visible to the
    gate's `read_cell_state(<bare role>, ...)`. The role defaults to the
    deployment's own first roster entry (env.chair_officer), never a name this
    module supplies. Deterministic check the CI test calls
    directly (peer of `no_ceiling_or_prod_auto`) — NEVER called by the
    load/validate paths.

    WHY [germline batch 2026-07-04]: the gate query composes the graduation
    cell key as "officer:" + role (policy_engine.read_cell_state →
    graduation.evaluate(("officer:cos", lane, action_type))), while emitters
    stamp {"kind", "id"} that graduation flattens to "kind:id". A double-
    prefixed emitter id ("officer:cos" instead of the bare "cos") therefore
    flattens to "officer:officer:cos" and SEVERS the cell's evidence from the
    gate — demotion evidence silently stops reaching the very query that must
    see it. This probe proves the wire end-to-end through the REAL stack
    (consequence.emit_consequence schema validation → JSONL ledger →
    read_ledger → compute_ratios → graduation.evaluate → read_cell_state):

      * canonical row (id="cos", lane "parity-canonical") → state must NOT be
        "unmeasured" (one confirmed/verdict_human sample makes the cell
        measured; with the default bar it lands "propose_only");
      * control row with the DEFECT shape (id="officer:cos", lane
        "parity-control") → state MUST stay "unmeasured", proving the probe
        actually distinguishes severed evidence (guards against a future read
        path that ignored the actor entirely, which would make the positive
        leg pass vacuously).

    CONTAINMENT (Corridor-reviewed): the two synthetic rows are written to a
    fresh private temp dir by re-pointing CABINET_EVENT_LOG_DIR for the probe
    duration only — saved and restored (or removed) in `finally`, temp dir
    deleted — so the probe can never write the LIVE audit ledger
    (~/Library/Application Support/cabinet/). CABINET_SIM_MODE is popped for
    the duration so the SIE-7 sim-quarantine cannot mark/filter the synthetic
    rows and skew the read. Fail-closed by construction: any import error,
    emit rejection, or read failure surfaces as a False return (read_cell_state
    itself resolves exceptions to "unmeasured", which fails the canonical leg).

    Returns True iff BOTH legs hold.
    """
    officer = officer or env.chair_officer()
    import shutil
    import tempfile
    from datetime import datetime, timezone

    saved_log = os.environ.get("CABINET_EVENT_LOG_DIR")
    saved_sim = os.environ.get("CABINET_SIM_MODE")
    tmp = tempfile.mkdtemp(prefix="cabinet-actor-parity-")
    try:
        os.environ["CABINET_EVENT_LOG_DIR"] = tmp
        os.environ.pop("CABINET_SIM_MODE", None)

        from framework.fidelity import consequence

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # Two schema-valid acted rows: identical everywhere except the actor id
        # shape (+ lane/subject so identities never collapse via last-write-
        # wins). review.source="verdict_human" so the confirm is a scored
        # sample under the flavor-A promotion split; action_type is a widened
        # reversible kind, exercising the exact cell the doctrine acts on.
        for actor_id, lane, subject in (
            (officer, "parity-canonical", "parity probe — canonical bare-role row"),
            (f"officer:{officer}", "parity-control", "parity probe — double-prefixed control row"),
        ):
            consequence.emit_consequence(
                ts=ts,
                actor={"kind": "officer", "id": actor_id},
                lane=lane,
                action="parity-probe synthetic acted row",
                subject=subject,
                action_type="task_status_move",
                # evidence is REQUIRED for status ok (consequence.py
                # _validate_invariants) — the probe rides the real schema.
                outcome={"status": "ok",
                         "evidence": "synthetic parity-probe row (temp ledger)"},
                review={"verdict": "confirmed", "source": "verdict_human"},
            )

        # Import the LIVE gate helper exactly as the shipped CI tests do
        # (CG-14 pull-down: the engine is framework/authority/policy_engine —
        # package import; still force the real yaml if a conftest stub leaked
        # into sys.modules).
        if "yaml" in sys.modules and not hasattr(sys.modules["yaml"], "safe_load"):
            del sys.modules["yaml"]
        from framework.authority import policy_engine

        canonical = policy_engine.read_cell_state(
            officer, "parity-canonical", "task_status_move")
        control = policy_engine.read_cell_state(
            officer, "parity-control", "task_status_move")
        return canonical != "unmeasured" and control == "unmeasured"
    finally:
        # Restore the exact prior env (absent stays absent) + drop the temp
        # ledger — the probe leaves zero trace either way.
        if saved_log is None:
            os.environ.pop("CABINET_EVENT_LOG_DIR", None)
        else:
            os.environ["CABINET_EVENT_LOG_DIR"] = saved_log
        if saved_sim is not None:
            os.environ["CABINET_SIM_MODE"] = saved_sim
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Validation (hand-rolled, fail-closed, additionalProperties:false everywhere)
# ---------------------------------------------------------------------------

def _reject_extra(obj: dict, allowed: set, where: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise MatrixValidationError(
            f"{where}: additional properties not allowed: {sorted(extra)}"
        )


def _require(obj: dict, keys: tuple, where: str) -> None:
    for k in keys:
        if k not in obj:
            raise MatrixValidationError(f"{where}: missing required field: {k}")


def _is_nonneg_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0


def validate_matrix(data: Any) -> None:
    """Validate the authority matrix. Raises MatrixValidationError on any
    violation; returns None on pass. Fail-closed by construction.
    """
    if not isinstance(data, dict):
        raise MatrixValidationError("matrix must be a mapping")

    _require(data, _ROOT_REQUIRED, "root")
    _reject_extra(data, _ROOT_KEYS, "root")

    if data["version"] != 1 or isinstance(data["version"], bool):
        raise MatrixValidationError("version must be the integer 1")
    if not isinstance(data["policies"], list) or not data["policies"]:
        raise MatrixValidationError("policies must be a non-empty list")

    policy = matrix_policy(data)
    _validate_policy(policy)


def _validate_policy(policy: dict[str, Any]) -> None:
    _require(policy, _POLICY_REQUIRED, "policy")
    _reject_extra(policy, _POLICY_KEYS, "policy")

    if policy["type"] != "authority_matrix":
        raise MatrixValidationError("policy.type must be 'authority_matrix'")
    if not isinstance(policy["name"], str) or not policy["name"]:
        raise MatrixValidationError("policy.name must be a non-empty string")
    if not isinstance(policy["message"], str) or not policy["message"]:
        raise MatrixValidationError("policy.message must be a non-empty string")

    _validate_risk_classes(policy["risk_classes"])
    hard_ceiling = _validate_hard_ceiling(policy["hard_ceiling"])
    _validate_ceiling_class_mapping(policy["risk_classes"], hard_ceiling)
    _validate_ceiling_map(policy["ceiling_frozenset_map"], hard_ceiling)
    _validate_verdicts(policy["verdicts"], hard_ceiling)
    # RECONCILE 2026-07-05: kept both — HEAD's trust-inversion floor check
    # (invariant #3, root table) + sovereign's posture-table check (#4).
    _validate_act_first_floor(policy["verdicts"], hard_ceiling)
    _validate_postures(policy)
    _validate_veto_window(policy["veto_window_minutes"])
    _validate_deploy(policy["deploy"])
    _validate_bars(policy["bars"])
    _validate_cooldowns(policy["cooldown_days"])


def _validate_risk_classes(risk_classes: Any) -> None:
    if not isinstance(risk_classes, dict):
        raise MatrixValidationError("risk_classes must be a mapping")
    if set(risk_classes) != set(RISK_CLASSES):
        raise MatrixValidationError(
            f"risk_classes must be exactly {sorted(RISK_CLASSES)}, "
            f"got {sorted(risk_classes)}"
        )

    mapped: set[str] = set()
    for name, rc in risk_classes.items():
        if not isinstance(rc, dict):
            raise MatrixValidationError(f"risk_classes.{name} must be a mapping")
        _reject_extra(rc, _RISK_CLASS_KEYS, f"risk_classes.{name}")
        ats = rc.get("action_types")
        if not isinstance(ats, list) or not ats:
            raise MatrixValidationError(
                f"risk_classes.{name}.action_types must be a non-empty list"
            )
        for at in ats:
            # The framework's own vocabulary, or a NAMESPACED operation this
            # deployment declared. Namespacing is what keeps the two apart:
            # a declaration can never collide with, shadow or redefine a
            # framework member, so opening the vocabulary cannot silently
            # re-point an existing binding. Anything that is neither is a
            # typo, and a typo binds nothing while reading as a binding.
            if at not in _MAPPABLE_ACTION_TYPES and not env.is_declared_operation_id(at):
                raise MatrixValidationError(
                    f"risk_classes.{name}: action_type '{at}' is neither a member of "
                    f"the shared classifier ACTION_TYPES (minus the AMBIGUOUS "
                    f"backstop) nor a namespaced deployment-declared operation id"
                )
            if at in mapped:
                raise MatrixValidationError(
                    f"action_type '{at}' is mapped to more than one risk_class"
                )
            mapped.add(at)

    # Every mappable action_type must be covered — no orphaned enum member.
    missing = _MAPPABLE_ACTION_TYPES - mapped
    if missing:
        raise MatrixValidationError(
            f"action_types not mapped to any risk_class: {sorted(missing)}"
        )


def _validate_hard_ceiling(hard_ceiling: Any) -> set[str]:
    if not isinstance(hard_ceiling, list) or not hard_ceiling:
        raise MatrixValidationError("hard_ceiling must be a non-empty list")
    hc = set(hard_ceiling)
    if len(hc) != len(hard_ceiling):
        raise MatrixValidationError("hard_ceiling contains duplicates")
    unknown = hc - set(RISK_CLASSES)
    if unknown:
        raise MatrixValidationError(
            f"hard_ceiling references unknown risk_classes: {sorted(unknown)}"
        )
    return hc


def _validate_ceiling_class_mapping(
    risk_classes: Any, hard_ceiling: set[str]
) -> None:
    """THE CI INVARIANT #6 — the hard-ceiling class MAPPING is pinned, not just
    the fact that every action_type is mapped exactly ONCE.

    WHY: the gate's ceiling short-circuit is risk_class-KEYED
    (`policy_engine._eval_authority_matrix` step 2, `risk_class in
    hard_ceiling`), so "mapped exactly once" left a fail-open in the enforcer
    itself — TWO, both reproduced against pre-change code:

      a. relocate the KIND — moving `external_email` off `external_comms` onto
         a non-ceiling row validated clean, and a real send then rode the
         ordinary confidence path (onto `draft_only`/`read_only_dispatch` it
         reached the notify_after allow-branch: ALLOW at `unmeasured`);
      b. relocate the CEILING — leaving the kind where it is but re-pointing
         which ROW NAME `hard_ceiling` + the frozenset map carry also
         validated clean, and also allowed.

    Both close against ONE declared source, `CEILING_CLASS_ACTION_TYPES`
    (values derived from the classifier sets that already exist — no second
    list to drift): the ceiling class NAMES must equal `hard_ceiling` [b], and
    each ceiling row's action_types must equal its declared set [a].

    Fail-closed at every degenerate end — an empty declared set, an absent or
    non-list `action_types`, a missing row, or a malformed `risk_classes` all
    RAISE rather than compare vacuously.
    """
    if not isinstance(risk_classes, dict):
        raise MatrixValidationError("risk_classes must be a mapping")
    if set(CEILING_CLASS_ACTION_TYPES) != hard_ceiling:
        raise MatrixValidationError(
            "hard_ceiling must be exactly the declared ceiling classes "
            f"{sorted(CEILING_CLASS_ACTION_TYPES)}, got {sorted(hard_ceiling)} "
            "— the gate's ceiling short-circuit is risk_class-keyed, so moving "
            "which row carries a ceiling would silently un-gate it"
        )
    for rc, declared in CEILING_CLASS_ACTION_TYPES.items():
        if not declared:
            raise MatrixValidationError(  # never assert against an empty set
                f"declared ceiling action_types for '{rc}' are empty — the "
                f"mapping pin would be vacuous"
            )
        row = risk_classes.get(rc)
        ats = row.get("action_types") if isinstance(row, dict) else None
        if not isinstance(ats, list) or not ats:
            raise MatrixValidationError(
                f"risk_classes.{rc}.action_types must be a non-empty list "
                f"(hard-ceiling row)"
            )
        # The framework's own ceiling members must be present and UNMOVED:
        # the gate's ceiling short-circuit is risk_class-keyed, so relocating
        # one off its row silently un-gates it. What the row MAY additionally
        # carry is a namespaced operation this deployment declared — and only
        # in this direction, because a ceiling row is always-gated, so adding
        # to it can only NARROW autonomy. Without that, every ceiling protects
        # exactly the operations the shipped vocabulary happens to name: an
        # operator whose irreversible acts are not in that list gets a ceiling
        # with no members in their world, which reads as protection and is not.
        extras = frozenset(ats) - declared
        if not declared <= frozenset(ats):
            raise MatrixValidationError(
                f"risk_classes.{rc}.action_types must contain exactly "
                f"{sorted(declared)} of the framework's own kinds, got "
                f"{sorted(set(ats))} — a hard-ceiling kind may never be "
                f"relocated off its ceiling row"
            )
        stray = sorted(a for a in extras if not env.is_declared_operation_id(a))
        if stray:
            raise MatrixValidationError(
                f"risk_classes.{rc}.action_types carries {stray}, which is "
                f"neither one of this row's framework kinds nor a namespaced "
                f"deployment-declared operation id"
            )


def _validate_ceiling_map(cmap: Any, hard_ceiling: set[str]) -> None:
    if not isinstance(cmap, dict):
        raise MatrixValidationError("ceiling_frozenset_map must be a mapping")
    # Keys must be exactly the hard_ceiling rows.
    if set(cmap) != hard_ceiling:
        raise MatrixValidationError(
            "ceiling_frozenset_map keys must equal hard_ceiling "
            f"({sorted(hard_ceiling)}), got {sorted(cmap)}"
        )
    # Every value must be a real frozenset member.
    for k, v in cmap.items():
        if v not in HARD_CEILING_TOUCHES:
            raise MatrixValidationError(
                f"ceiling_frozenset_map['{k}'] = '{v}' is not a member of "
                f"HARD_CEILING_TOUCHES {sorted(HARD_CEILING_TOUCHES)}"
            )
    # THE CI INVARIANT #1 [FIX-7]: cover ALL SIX members, not a subset.
    if set(cmap.values()) != set(HARD_CEILING_TOUCHES):
        raise MatrixValidationError(
            "ceiling_frozenset_map must cover every HARD_CEILING_TOUCHES member "
            f"{sorted(HARD_CEILING_TOUCHES)}; got {sorted(set(cmap.values()))}"
        )


def _validate_verdicts(
    verdicts: Any,
    hard_ceiling: set[str],
    *,
    posture_table: bool = False,
    where: str = "verdicts",
) -> None:
    """Validate one FULL verdicts table (the root/guardian table by default).

    `posture_table=True` validates a `postures.*` table instead [§2.1]: the
    shape rules are identical EXCEPT ceiling rows may narrow `always_gated` to
    the conditional `standing_grant` (never anything wider — `auto` stays
    structurally impossible). `standing_grant` is forbidden in the root table
    and on any non-ceiling row in every mode. `where` only prefixes messages.
    """
    if not isinstance(verdicts, dict):
        raise MatrixValidationError(f"{where} must be a mapping")
    if set(verdicts) != set(RISK_CLASSES):
        raise MatrixValidationError(
            f"{where} must cover exactly {sorted(RISK_CLASSES)}, "
            f"got {sorted(verdicts)}"
        )

    for rc, states in verdicts.items():
        if not isinstance(states, dict) or not states:
            raise MatrixValidationError(f"{where}.{rc} must be a non-empty mapping")
        for state, verdict in states.items():
            if verdict not in VERDICTS:
                raise MatrixValidationError(
                    f"{where}.{rc}.{state}: '{verdict}' not in {sorted(VERDICTS)}"
                )
            if verdict == "standing_grant":
                # standing_grant is a posture-table, hard-ceiling-only verdict
                # (grant-or-need, never unconditional). The root/guardian
                # table may NOT contain it [D2].
                if not posture_table:
                    raise MatrixValidationError(
                        f"{where}.{rc}.{state}: 'standing_grant' is forbidden "
                        f"in the root/guardian verdicts table"
                    )
                if rc not in hard_ceiling:
                    raise MatrixValidationError(
                        f"{where}.{rc}.{state}: 'standing_grant' is only legal "
                        f"on a hard-ceiling row"
                    )

        if rc in hard_ceiling:
            # Hard-ceiling rows: wildcard-only AND always_gated for EVERY cell
            # (THE CI INVARIANT #2 [FIX-6]: no ceiling/prod cell may be auto).
            # A posture table may narrow to {always_gated, standing_grant}.
            if set(states) != {"*"}:
                raise MatrixValidationError(
                    f"{where}.{rc} is a hard-ceiling row and must use the "
                    f"single '*' wildcard, got {sorted(states)}"
                )
            for state, verdict in states.items():
                if posture_table:
                    if verdict not in ("always_gated", "standing_grant"):
                        raise MatrixValidationError(
                            f"{where}.{rc}.{state} = '{verdict}': posture-table "
                            f"hard-ceiling rows must be always_gated or "
                            f"standing_grant (auto is structurally impossible)"
                        )
                elif verdict != "always_gated":
                    raise MatrixValidationError(
                        f"{where}.{rc}.{state} = '{verdict}': hard-ceiling rows "
                        f"must be always_gated regardless of confidence"
                    )
        else:
            # Non-ceiling rows must cover all five confidence states explicitly.
            if set(states) != set(CONFIDENCE_STATES):
                raise MatrixValidationError(
                    f"{where}.{rc} must cover all confidence states "
                    f"{sorted(CONFIDENCE_STATES)}, got {sorted(states)}"
                )


# RECONCILE 2026-07-05: kept both validator defs — HEAD's
# _validate_act_first_floor (trust-inversion floor, invariant #3) AND
# sovereign's _validate_postures (posture-table axis, invariant #4).
def _validate_act_first_floor(verdicts: dict, hard_ceiling: set[str]) -> None:
    """THE CI INVARIANT #3 — the trust-inversion floor [CAPTAIN-RULING
    2026-07-03/04 earn-demotion ruling; widened to the reversible beachhead
    2026-07-04 (fix wave wsqzqfpt5)].

    Runs AFTER _validate_verdicts, so non-ceiling rows are guaranteed to carry
    all five confidence states. Three hard rules, each fail-closed:

      a. ANY non-ceiling row that grants `act_with_undo` anywhere must grant it
         at `unmeasured` too, and must land on `propose_only` at `demote`.
         Trust-with-undo is day-one-or-not-at-all (never pre-earned via a
         graduated-only grant), and demotion evidence must always have a safe
         landing — a `demote` cell that still acts would make the demotion
         wire decorative.
      b. The beachhead rows (`reversible`, `read_only_dispatch`) are pinned by
         EQUALITY at `unmeasured` (see _TRUST_FIRST_UNMEASURED for why
         equality, not just "not propose_only") and must demote → propose_only.
      c. No beachhead row may be moved under the hard ceiling — an always_gated
         wildcard would be the same silent earn-up regression wearing a
         stricter costume (and these classes are definitionally reversible /
         read-only, never ceiling material).

    WHY a validator and not a review note: presets/instances merge over the
    floor by name (load_policies), so a later layer could quietly ship
    `reversible: {unmeasured: propose_only}` and re-introduce earn-up — the
    exact posture the Captain ruled OUT. Deliberate tension with the header's
    "presets may narrow" rule: for trust-first classes, narrowing happens
    through demotion EVIDENCE (the demote state), not by config re-pinning;
    re-gating them is a germline amendment (this validator), never a preset
    override. The runtime stays fail-safe independently of this check: the
    policy_engine allow-branch grants act_with_undo only when a registered
    inverse exists AND the undo journal is reachable, else propose-only.
    """
    for rc, states in verdicts.items():
        if rc in hard_ceiling:
            if rc in _TRUST_FIRST_UNMEASURED:
                raise MatrixValidationError(  # rule (c)
                    f"'{rc}' is a trust-first class and may not be moved under "
                    f"the hard ceiling (always_gated would silently re-gate an "
                    f"act-from-day-one row)"
                )
            continue  # genuine ceiling rows are fully covered by invariant #2
        if not isinstance(states, dict):
            continue  # unreachable after _validate_verdicts; defensive only

        grants_undo = "act_with_undo" in set(states.values())
        pinned = _TRUST_FIRST_UNMEASURED.get(rc)

        # rule (a): act_with_undo is day-one-or-not-at-all + demotes safely.
        if grants_undo:
            if states.get("unmeasured") != "act_with_undo":
                raise MatrixValidationError(
                    f"verdicts.{rc}: grants act_with_undo but is "
                    f"'{states.get('unmeasured')}' at unmeasured — earn-up on a "
                    f"reversible/act_with_undo class is ruled out (trust granted "
                    f"day-one, lost on evidence; CAPTAIN-RULING 2026-07-03/04)"
                )
            if states.get("demote") != "propose_only":
                raise MatrixValidationError(
                    f"verdicts.{rc}.demote = '{states.get('demote')}': an "
                    f"act_with_undo row must demote to propose_only — demotion "
                    f"evidence is the ONLY way down and must land fail-safe"
                )

        # rule (b): the beachhead rows are pinned exactly.
        if pinned is not None:
            if states.get("unmeasured") != pinned:
                raise MatrixValidationError(
                    f"verdicts.{rc}.unmeasured = '{states.get('unmeasured')}': "
                    f"the trust-inversion floor pins this cell to '{pinned}' "
                    f"(CAPTAIN-RULING 2026-07-04 — no earn-up re-introduction, "
                    f"no undo/tell-handle widening)"
                )
            if states.get("demote") != "propose_only":
                raise MatrixValidationError(
                    f"verdicts.{rc}.demote = '{states.get('demote')}': "
                    f"trust-first rows must demote to propose_only"
                )


def _validate_postures(policy: dict[str, Any]) -> None:
    """Validate the OPTIONAL `postures` policy key (the posture-table axis).

    Absent key ⇒ no-op — a postures-less legacy floor validates unchanged
    (back-compat). Present ⇒ fail-closed [§2.1/D1]:

      * keys must be a subset of POSTURES; a `guardian` key raises outright
        (the root `verdicts` table IS guardian and is never redefined);
      * each entry is exactly `{verdicts: <FULL table>}`, validated with
        `_validate_verdicts(posture_table=True)`;
      * demote is posture-invariant: every non-ceiling row's demote cell must
        equal the root table's (a posture never softens the demote floor —
        evidence beats posture).

    Callable standalone on a merged policy dict (the runtime gate validates
    with the SAME code as CI [D8]), so it re-checks the root shapes it
    compares against instead of assuming a prior `_validate_policy` pass.
    """
    if not isinstance(policy, dict) or "postures" not in policy:
        return
    postures = policy["postures"]
    if not isinstance(postures, dict) or not postures:
        raise MatrixValidationError("postures must be a non-empty mapping")
    if "guardian" in postures:
        raise MatrixValidationError(
            "postures.guardian is forbidden — the root verdicts table IS the "
            "guardian posture and is never redefined"
        )
    unknown = set(postures) - POSTURES
    if unknown:
        raise MatrixValidationError(
            f"postures keys must be a subset of {sorted(POSTURES)}, "
            f"got unknown: {sorted(unknown)}"
        )

    # Standalone-call safety: the root shapes the posture tables validate
    # against must themselves be well-formed here, not assumed.
    hard_ceiling = policy.get("hard_ceiling")
    root_verdicts = policy.get("verdicts")
    if not isinstance(hard_ceiling, list) or not isinstance(root_verdicts, dict):
        raise MatrixValidationError(
            "postures require a well-formed hard_ceiling list + root verdicts "
            "mapping to validate against"
        )
    hc = set(hard_ceiling)

    for name, entry in postures.items():
        if not isinstance(entry, dict):
            raise MatrixValidationError(f"postures.{name} must be a mapping")
        _require(entry, ("verdicts",), f"postures.{name}")
        _reject_extra(entry, _POSTURE_ENTRY_KEYS, f"postures.{name}")
        table = entry["verdicts"]
        _validate_verdicts(
            table, hc, posture_table=True, where=f"postures.{name}.verdicts"
        )
        if name == "earn_up":
            _validate_earn_up_narrows(table, root_verdicts)
        # Demote invariance [§2.1] — checked after the shape pass, so every
        # non-ceiling row is known to carry an explicit demote cell.
        for rc, states in table.items():
            if rc in hc:
                continue
            root_row = root_verdicts.get(rc)
            if not isinstance(root_row, dict) or "demote" not in root_row:
                raise MatrixValidationError(
                    f"postures.{name}.verdicts.{rc}: root verdicts row has no "
                    f"demote cell to hold the demote invariant against"
                )
            if states["demote"] != root_row["demote"]:
                raise MatrixValidationError(
                    f"postures.{name}.verdicts.{rc}.demote = "
                    f"'{states['demote']}' drifts from the root table's "
                    f"'{root_row['demote']}' — demote is posture-invariant"
                )


def _validate_earn_up_narrows(table: dict, root_verdicts: dict) -> None:
    """THE CI INVARIANT #5 — the `postures.earn_up` table may only NARROW vs
    the root/guardian table [axes spec 2026-07-05 §1], machine-checked
    cell-by-cell on VERDICT_PERMISSIVENESS. This is what makes earn_up
    selectable WITHOUT attestation in the posture kernel: a table that can
    only narrow is fail-safe by construction.

    Runs AFTER `_validate_verdicts(posture_table=True)`, so shapes hold (full
    class coverage, five states per non-ceiling row, single-'*' ceilings) and
    every verdict is a VERDICTS member. Two hard rules on top of the shared
    posture rules (demote invariance vs root stays with the generic pass in
    `_validate_postures`):

      a. `standing_grant` is forbidden ANYWHERE in earn_up — ceilings stay
         plain always_gated (grants are a sovereign surface; earn_up climbs
         through Captain-granted rungs, never through standing grants).
      b. rank(earn_up cell) <= rank(root cell), every cell. Equality is legal
         (narrow-or-equal); any widening is a hard validation error, so no
         future merge can quietly turn the cautious start into an act-first
         table. All autonomy above this floor comes from the trust-ladder
         overlay at run time (AX-2), never from the table.
    """
    for rc, states in table.items():
        root_row = root_verdicts.get(rc)
        if not isinstance(root_row, dict):
            raise MatrixValidationError(
                f"postures.earn_up.verdicts.{rc}: no root/guardian row to "
                f"narrow against"
            )
        for state, verdict in states.items():
            if verdict == "standing_grant":
                raise MatrixValidationError(  # rule (a)
                    f"postures.earn_up.verdicts.{rc}.{state}: "
                    f"'standing_grant' is forbidden in earn_up — ceilings "
                    f"stay always_gated (grants are a sovereign surface)"
                )
            root_verdict = root_row.get(state, root_row.get("*"))
            if root_verdict not in VERDICT_PERMISSIVENESS:
                # Only reachable on a malformed standalone call (the root
                # table never carries standing_grant) — fail closed anyway.
                raise MatrixValidationError(
                    f"postures.earn_up.verdicts.{rc}.{state}: root verdict "
                    f"{root_verdict!r} is not orderable on "
                    f"VERDICT_PERMISSIVENESS"
                )
            if VERDICT_PERMISSIVENESS[verdict] > VERDICT_PERMISSIVENESS[root_verdict]:
                raise MatrixValidationError(  # rule (b)
                    f"postures.earn_up.verdicts.{rc}.{state} = '{verdict}' "
                    f"is more permissive than the root/guardian "
                    f"'{root_verdict}' — earn_up may only narrow"
                )


def _validate_veto_window(v: Any) -> None:
    if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
        raise MatrixValidationError("veto_window_minutes must be a positive integer")


def _validate_deploy(deploy: Any) -> None:
    if not isinstance(deploy, dict):
        raise MatrixValidationError("deploy must be a mapping")
    _reject_extra(deploy, _DEPLOY_KEYS, "deploy")
    for key in ("safe_globs", "high_risk_globs"):
        globs = deploy.get(key)
        if not isinstance(globs, list) or not globs:
            raise MatrixValidationError(f"deploy.{key} must be a non-empty list")
        for g in globs:
            if not isinstance(g, str) or not g:
                raise MatrixValidationError(f"deploy.{key} entries must be non-empty strings")


def _validate_bars(bars: Any) -> None:
    if not isinstance(bars, dict) or "default" not in bars:
        raise MatrixValidationError("bars must be a mapping with a 'default' entry")
    for name, bar in bars.items():
        if not isinstance(bar, dict):
            raise MatrixValidationError(f"bars.{name} must be a mapping")
        _reject_extra(bar, _BAR_KEYS, f"bars.{name}")
        _require(bar, tuple(_BAR_KEYS), f"bars.{name}")
        mr = bar["match_rate"]
        if not isinstance(mr, (int, float)) or isinstance(mr, bool) or not (0 <= mr <= 1):
            raise MatrixValidationError(f"bars.{name}.match_rate must be in [0, 1]")
        for k in ("samples", "max_divergent_last10", "recency_clean_days"):
            val = bar[k]
            if not isinstance(val, int) or isinstance(val, bool) or val < 0:
                raise MatrixValidationError(f"bars.{name}.{k} must be a non-negative integer")


def _validate_cooldowns(cooldowns: Any) -> None:
    if not isinstance(cooldowns, dict) or "default" not in cooldowns:
        raise MatrixValidationError("cooldown_days must be a mapping with a 'default' entry")
    for name, days in cooldowns.items():
        if not isinstance(days, int) or isinstance(days, bool) or days < 0:
            raise MatrixValidationError(f"cooldown_days.{name} must be a non-negative integer")


# ---------------------------------------------------------------------------
# __main__ CI probe — `python3 framework/authority/matrix.py`
# ---------------------------------------------------------------------------
# One-command proof for the germline batch: (1) the shipped floor passes the
# full validator (incl. the trust-inversion floor, invariant #3), and (2) the
# bare-role actor-id parity holds through the live gate stack. Writes ONLY to
# the probe's private temp ledger (see check_gate_actor_id_parity's
# containment note) — never the live audit ledger. Exit 0 = both PASS.

if __name__ == "__main__":  # pragma: no cover — CI convenience entrypoint
    try:
        load_matrix()  # validates the shipped floor; raises on any violation
        print("authority-matrix floor validation: PASS")
    except MatrixValidationError as exc:
        print(f"authority-matrix floor validation: FAIL — {exc}")
        sys.exit(1)
    _parity_ok = check_gate_actor_id_parity()
    print("gate actor-id parity (bare-role acted row visible): "
          + ("PASS" if _parity_ok else "FAIL"))
    sys.exit(0 if _parity_ok else 1)
