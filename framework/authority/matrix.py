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
mistyped, missing, or extra raises `MatrixValidationError`. Three safety
invariants are enforced as hard rules, not prose:

  1. No prod/ceiling cell may resolve to `auto` [FIX-6]. A hard-ceiling row is
     `always_gated` for every state.
  2. The hard ceiling covers all six HARD_CEILING_TOUCHES members [FIX-7].
  3. TRUST-INVERSION floor [NATE-DECISION 2026-07-03/04 earn-demotion ruling,
     widened 2026-07-04 by fix wave wsqzqfpt5]: no reversible / act_with_undo
     class may be `propose_only` at `unmeasured` (trust is granted day-one and
     lost on demotion EVIDENCE — never pre-earned), and any acting-from-day-one
     row must land on `propose_only` at `demote` so the demotion path always
     has teeth. Enforced by `_validate_act_first_floor` so no future preset or
     instance merge can silently re-introduce earn-up.

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

from framework.authority.classifier import ACTION_TYPES, AMBIGUOUS  # noqa: E402
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
# draft_only = earn-up kept, NATE-DECISION: outbound-adjacent), the earn-up
# rows (internal_comms, deploy_nonprod), and the six execution-surface hard
# ceilings. Closed set: the YAML's risk_classes AND verdicts keys must equal
# it exactly (additionalProperties:false in both directions).
RISK_CLASSES = frozenset({
    "reversible", "read_only_dispatch", "draft_only",
    "pm_write", "calendar_write",
    "internal_comms", "external_comms",
    "deploy_nonprod", "deploy_prod", "spend",
    "secrets", "network_write", "credentials_grant",
})

# The verdicts a cell may carry.
VERDICTS = frozenset({
    "auto", "act_with_undo", "auto_with_veto_window", "notify_after",
    "propose_only", "always_gated", "classifier",
})

# Confidence states (F's graduation states). Non-ceiling rows must cover all
# five; ceiling rows use the "*" wildcard.
CONFIDENCE_STATES = frozenset({
    "unmeasured", "propose_only", "eligible", "graduated", "demote",
})

# TRUST-INVERSION beachhead pins [NATE-DECISION 2026-07-03/04, widened
# 2026-07-04 (wsqzqfpt5)]: the classes that act from day one, and the EXACT
# verdict each must carry at `unmeasured`. Name-anchored on purpose — these two
# rows are the doctrine's beachhead, so their unmeasured cells are pinned by
# equality (not merely "not propose_only"): `auto` here would be a WIDENING
# (dropping the undo/tell handle), `always_gated`/`propose_only` a silent
# earn-up regression. draft_only and deploy_nonprod are deliberately absent
# (NATE-DECISION: outbound-/prod-adjacent — they keep earn-up).
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
}
_POLICY_REQUIRED = (
    "name", "type", "message",
    "risk_classes", "hard_ceiling", "ceiling_frozenset_map", "verdicts",
    "veto_window_minutes", "deploy", "bars", "cooldown_days",
)
_RISK_CLASS_KEYS = {"action_types"}
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


def ceiling_members(policy: dict[str, Any]) -> set[str]:
    """The set of HARD_CEILING_TOUCHES members the matrix's ceiling map covers."""
    cmap = policy.get("ceiling_frozenset_map", {})
    if not isinstance(cmap, dict):
        raise MatrixValidationError("ceiling_frozenset_map must be a mapping")
    return set(cmap.values())


def no_ceiling_or_prod_auto(policy: dict[str, Any]) -> bool:
    """True iff NO hard-ceiling (incl. prod) row carries an `auto` verdict [FIX-6].

    Deterministic check the CI test calls directly.
    """
    verdicts = policy.get("verdicts", {})
    for rc in policy.get("hard_ceiling", []):
        for verdict in verdicts.get(rc, {}).values():
            if verdict == "auto":
                return False
    return True


def check_gate_actor_id_parity(officer: str = "cos") -> bool:
    """Parity probe: a synthetic acted row written with the CANONICAL bare-role
    actor id ({"kind": "officer", "id": "cos"}) must be visible to the gate's
    `read_cell_state("cos", ...)`. Deterministic check the CI test calls
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
        # (cabinet/scripts/lib is not a package — path-import, and force the
        # real yaml if a conftest stub leaked into sys.modules).
        lib_dir = _FRAMEWORK_ROOT / "cabinet" / "scripts" / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        if "yaml" in sys.modules and not hasattr(sys.modules["yaml"], "safe_load"):
            del sys.modules["yaml"]
        import policy_engine

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
    _validate_ceiling_map(policy["ceiling_frozenset_map"], hard_ceiling)
    _validate_verdicts(policy["verdicts"], hard_ceiling)
    _validate_act_first_floor(policy["verdicts"], hard_ceiling)
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
            if at not in _MAPPABLE_ACTION_TYPES:
                raise MatrixValidationError(
                    f"risk_classes.{name}: action_type '{at}' is not a member of "
                    f"the shared classifier ACTION_TYPES (minus the AMBIGUOUS "
                    f"backstop)"
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


def _validate_verdicts(verdicts: Any, hard_ceiling: set[str]) -> None:
    if not isinstance(verdicts, dict):
        raise MatrixValidationError("verdicts must be a mapping")
    if set(verdicts) != set(RISK_CLASSES):
        raise MatrixValidationError(
            f"verdicts must cover exactly {sorted(RISK_CLASSES)}, "
            f"got {sorted(verdicts)}"
        )

    for rc, states in verdicts.items():
        if not isinstance(states, dict) or not states:
            raise MatrixValidationError(f"verdicts.{rc} must be a non-empty mapping")
        for state, verdict in states.items():
            if verdict not in VERDICTS:
                raise MatrixValidationError(
                    f"verdicts.{rc}.{state}: '{verdict}' not in {sorted(VERDICTS)}"
                )

        if rc in hard_ceiling:
            # Hard-ceiling rows: wildcard-only AND always_gated for EVERY cell
            # (THE CI INVARIANT #2 [FIX-6]: no ceiling/prod cell may be auto).
            if set(states) != {"*"}:
                raise MatrixValidationError(
                    f"verdicts.{rc} is a hard-ceiling row and must use the "
                    f"single '*' wildcard, got {sorted(states)}"
                )
            for state, verdict in states.items():
                if verdict != "always_gated":
                    raise MatrixValidationError(
                        f"verdicts.{rc}.{state} = '{verdict}': hard-ceiling rows "
                        f"must be always_gated regardless of confidence"
                    )
        else:
            # Non-ceiling rows must cover all five confidence states explicitly.
            if set(states) != set(CONFIDENCE_STATES):
                raise MatrixValidationError(
                    f"verdicts.{rc} must cover all confidence states "
                    f"{sorted(CONFIDENCE_STATES)}, got {sorted(states)}"
                )


def _validate_act_first_floor(verdicts: dict, hard_ceiling: set[str]) -> None:
    """THE CI INVARIANT #3 — the trust-inversion floor [NATE-DECISION
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
                    f"day-one, lost on evidence; NATE-DECISION 2026-07-03/04)"
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
                    f"(NATE-DECISION 2026-07-04 — no earn-up re-introduction, "
                    f"no undo/tell-handle widening)"
                )
            if states.get("demote") != "propose_only":
                raise MatrixValidationError(
                    f"verdicts.{rc}.demote = '{states.get('demote')}': "
                    f"trust-first rows must demote to propose_only"
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
