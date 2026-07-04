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
mistyped, missing, or extra raises `MatrixValidationError`. Two safety
invariants are enforced as hard rules, not prose:

  1. No prod/ceiling cell may resolve to `auto` [FIX-6]. A hard-ceiling row is
     `always_gated` for every state.
  2. The hard ceiling covers all six HARD_CEILING_TOUCHES members [FIX-7].

This is matrix-as-DATA only — no gate behavior, no exit codes, no live
side-effects. System Python is 3.9.6 with no `jsonschema` dependency, so the
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

# The nine risk classes (five spec + three execution-surface ceiling classes).
RISK_CLASSES = frozenset({
    "reversible", "pm_write", "calendar_write",
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
