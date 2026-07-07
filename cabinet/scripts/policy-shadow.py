#!/usr/bin/env python3
"""Typed policy shadow evaluator.

This is deliberately not authoritative yet. It reads the same hook input shape
as pre-tool-use.sh, emits a structured allow/block decision, and can append the
decision into org_events for parity analysis.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from org_runtime import Store  # noqa: E402

# The engine lives at framework/authority/policy_engine (CG-14 pull-down
# 2026-07-07) — put the repo root on sys.path (this script is
# cabinet/scripts/policy-shadow.py, so root = two parents up) and import the
# package form; the engine itself still honors CABINET_ROOT for deployment
# path resolution. Imported lazily-tolerant: if the engine is absent the
# authority emission is skipped and the regex shadow is unaffected.
_REPO_ROOT = SCRIPT_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
try:  # pragma: no cover - import-time wiring, exercised via the shadow tests
    from framework.authority import policy_engine  # noqa: E402
except Exception:  # noqa: BLE001 - shadow must stay importable regardless
    policy_engine = None  # type: ignore[assignment]


PRODUCT = os.environ.get("ORG_RUNTIME_PRODUCT", "captains-cabinet")

# T7 [FIX-2 Stage 0]: the authority-matrix shadow emits the typed VERDICT under
# its own policy_version so the parity harness can exercise it independently of
# the legacy regex shadow (which keeps "shadow-v1"). SHADOW ONLY — never blocks.
AUTHORITY_SHADOW_VERSION = "authority-shadow-v1"


def read_input() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {"tool_name": "", "tool_input": {}}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"tool_name": "", "tool_input": {}, "_error": f"invalid JSON: {exc}"}
    if not isinstance(data, dict):
        return {"tool_name": "", "tool_input": {}, "_error": "input must be object"}
    data.setdefault("tool_input", {})
    return data


def command(tool_input: dict[str, Any]) -> str:
    return str(tool_input.get("command") or "")


def file_path(tool_input: dict[str, Any]) -> str:
    return str(tool_input.get("file_path") or tool_input.get("path") or "")


# Policy types the LEGACY-enforcing shadow decision routes through. This is
# EXACTLY the set the live main() loop would block on — authority_matrix is
# excluded (it is shadow-verdict-only; in A0 _eval_authority_matrix blocks every
# action, so including it here would make .decision block everything).
_LEGACY_ENFORCING_TYPES = frozenset({
    "binary_block",
    "destructive_rm",
    "command_contains",
    "path_block",
    "bash_write_to_path",
    "tier2_isolation",
})


def _shadow_cabinet_root() -> str | None:
    """Resolve the repo root for policy loading WITHOUT depending on CABINET_ROOT
    being exported. The parity harness + test-policy-shadow.sh invoke the shadow
    standalone with CABINET_ROOT unset, in which case policy_engine.load_policies
    would default to /opt/founders-cabinet and load ZERO policies. Reuse the
    engine's own _authority_root() (honors CABINET_ROOT, else walks up from the
    engine file to the repo root) so the shadow and the engine resolve the SAME
    root — one source of truth, no dynamic path math here. Returns None if the
    engine is unavailable (caller falls back to the regex shadow).
    """
    if policy_engine is None:
        return None
    env_root = os.environ.get("CABINET_ROOT")
    if env_root:
        return env_root
    resolver = getattr(policy_engine, "_authority_root", None)
    if resolver is None:
        return None
    try:
        return str(resolver())
    except Exception:  # noqa: BLE001 - shadow must never raise
        return None


def _reason_token(policy: dict[str, Any]) -> str:
    """Stable reason token for a matched policy: the kebab name → snake_case
    (e.g. no-production-deploy → no_production_deploy, which CONTAINS the legacy
    'production_deploy' token the shadow tests assert on)."""
    name = str(policy.get("name") or policy.get("type") or "policy")
    return name.replace("-", "_")


def _engine_decision(hook: dict[str, Any], officer: str) -> dict[str, Any] | None:
    """Route .decision through policy_engine.evaluate_policy() over the loaded
    typed policies (first-match-wins, mirroring the live main() loop). Returns
    the shadow-v1-shaped result dict, or None if the engine cannot be used
    (import missing / no root) so the caller falls back to the regex shadow.

    Fail-safe: any exception → None (regex fallback). authority_matrix policies
    are skipped. A policiesless load (empty root) yields decision=allow.
    """
    if policy_engine is None:
        return None
    evaluate_policy = getattr(policy_engine, "evaluate_policy", None)
    load_policies = getattr(policy_engine, "load_policies", None)
    if evaluate_policy is None or load_policies is None:
        return None

    tool_name = str(hook.get("tool_name") or "")
    tool_input = hook.get("tool_input") if isinstance(hook.get("tool_input"), dict) else {}

    try:
        policies = load_policies(_shadow_cabinet_root())
    except Exception:  # noqa: BLE001 - shadow must never raise
        return None

    try:
        for policy in policies:
            if not isinstance(policy, dict):
                continue
            if policy.get("type") not in _LEGACY_ENFORCING_TYPES:
                continue  # skip authority_matrix (shadow-only) + non-legacy
            result = evaluate_policy(policy, tool_name, tool_input, officer)
            if result:
                token = _reason_token(policy)
                return {
                    "decision": "block",
                    "reason": token,
                    "reasons": [token],
                    "officer": officer,
                    "policy_version": "shadow-v1",
                }
    except Exception:  # noqa: BLE001 - shadow must never raise
        return None

    return {
        "decision": "allow",
        "reason": "no_shadow_rule_matched",
        "officer": officer,
        "policy_version": "shadow-v1",
    }


def decision(hook: dict[str, Any]) -> dict[str, Any]:
    """SHADOW .decision — now routed through the typed policy engine.

    Parity fix (2026-07-03, docs/policy-shadow-parity-proof-v2-2026-07-03.md):
    the old self-contained regex here was strictly weaker than the live hook on
    the covered rules (missed adversarial rm-root / perl-i / sed-i / tar product
    writes, over-matched read-from-workspace). We now delegate to
    policy_engine.evaluate_policy() over the loaded typed policies — the SAME
    engine that already gets those rules right — so the shadow decision tracks
    the typed engine (and, for the migrated stateless rules, the live hook).
    SHADOW-ONLY: this changes only the recorded shadow decision, never a live
    allow/block (pre-tool-use.sh does not invoke this engine).

    Shape is unchanged (policy_version 'shadow-v1', decision allow|block). If the
    engine is unavailable for any reason, fall back to the historical regex
    shadow (_regex_decision) so the shadow never crashes and never regresses to
    a bare allow-on-error.
    """
    officer = os.environ.get("OFFICER") or os.environ.get("OFFICER_NAME") or "unknown"

    if hook.get("_error"):
        return {"decision": "allow", "reason": hook["_error"], "officer": officer, "policy_version": "shadow-v1"}

    engine_result = _engine_decision(hook, officer)
    if engine_result is not None:
        return engine_result

    # Engine unavailable (import failed / no root / raised) — historical regex.
    return _regex_decision(hook, officer)


def _regex_decision(hook: dict[str, Any], officer: str) -> dict[str, Any]:
    """Historical self-contained regex shadow. Retained as the fail-safe path
    when the typed engine cannot be loaded. NOTE: strictly weaker than the engine
    on the covered rules (see decision() docstring) — used only as a fallback."""
    tool_name = str(hook.get("tool_name") or "")
    tool_input = hook.get("tool_input") if isinstance(hook.get("tool_input"), dict) else {}
    reasons: list[str] = []

    if tool_name == "Bash":
        cmd = command(tool_input)
        if re.search(r"\bvercel\s+(deploy|--prod)\b", cmd):
            reasons.append("production_deploy_requires_captain_approval")
        if re.search(r"\b(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE|DELETE\s+FROM)\b", cmd):
            reasons.append("destructive_database_operation_requires_captain_approval")
        if re.search(r"(^|[;&|]\s*)rm\s+-[A-Za-z]*r[A-Za-z]*f?[A-Za-z]*\s+/", cmd):
            reasons.append("destructive_filesystem_operation")
        if officer not in ("cto", "unknown") and re.search(r"/workspace/[a-z0-9][a-z0-9-]*/", cmd):
            if re.search(r"(>|tee\s+|sed\s+.*\s-i|cp\s+|mv\s+|rsync\s+|patch\s+|perl\s+.*\s-i|tar\s+)", cmd):
                reasons.append("non_cto_product_workspace_write")

    if tool_name in ("Edit", "Write"):
        path = file_path(tool_input)
        if path.endswith(".env") or "/.env" in path:
            reasons.append("env_files_read_only")
        if officer not in ("cto", "unknown") and re.search(r"^/workspace/[a-z0-9][a-z0-9-]*/", path):
            reasons.append("non_cto_product_workspace_write")
        if "instance/memory/tier2/" in path and officer not in ("unknown",):
            expected = f"instance/memory/tier2/{officer}/"
            if expected not in path:
                reasons.append("officer_tier2_isolation")

    if reasons:
        return {
            "decision": "block",
            "reason": ",".join(reasons),
            "reasons": reasons,
            "officer": officer,
            "policy_version": "shadow-v1",
        }
    return {"decision": "allow", "reason": "no_shadow_rule_matched", "officer": officer, "policy_version": "shadow-v1"}


def _find_authority_policy() -> dict[str, Any] | None:
    """Return the single authority_matrix policy from the layered policy stack,
    or None if the engine/policies are unavailable. Reads via the engine's
    `load_policies()` (yaml.safe_load only, no shell, no dynamic path math).
    """
    if policy_engine is None:
        return None
    try:
        for policy in policy_engine.load_policies():
            if isinstance(policy, dict) and policy.get("type") == "authority_matrix":
                return policy
    except Exception:  # noqa: BLE001 - shadow must never raise
        return None
    return None


def authority_decision(hook: dict[str, Any]) -> dict[str, Any] | None:
    """Compute the SHADOW authority-matrix verdict for a tool call.

    Reuses the engine's shared `classify_action` / `risk_of` / `read_cell_state`
    / `resolve_verdict` / `resolve_gate_posture` (one source of truth — the
    verdict here is identical to what `_eval_authority_matrix` would gate on).
    Returns a typed verdict record (NOT a block) or None when authority cannot
    be evaluated.

    FAIL-SAFE spine (mirrors the gate): hard-ceiling risk_class -> always_gated
    (a SOVEREIGN posture ceiling row may resolve `standing_grant` instead —
    probed SIDE-EFFECT-FREE: no need filed, no rate use counted; the record
    carries the grant_id / would-be need_id [SOV-3]); unknown/unmapped
    action_type or unmeasured cell -> propose_only; a quarantined floor
    (`_validation_failed`, D8) -> propose_only. With no posture config the
    resolution is byte-identical to the guardian gate. SHADOW ONLY — this
    never blocks.
    """
    if policy_engine is None or hook.get("_error"):
        return None
    policy = _find_authority_policy()
    if policy is None:
        return None

    tool_name = str(hook.get("tool_name") or "")
    tool_input = hook.get("tool_input") if isinstance(hook.get("tool_input"), dict) else {}
    officer = os.environ.get("OFFICER") or os.environ.get("OFFICER_NAME") or "unknown"

    classify_action = getattr(policy_engine, "classify_action", None)
    resolve_lane = getattr(policy_engine, "resolve_lane", None)
    if classify_action is None or resolve_lane is None:
        return None
    # Posture-aware engine surface [SOV-3] — getattr-guarded like the names
    # above so the shadow stays importable against an older engine.
    resolve_gate_posture = getattr(policy_engine, "resolve_gate_posture", None)
    standing_grant_resolution = getattr(policy_engine, "standing_grant_resolution", None)
    grant_context = getattr(policy_engine, "_grant_context", None)

    try:
        action_type = classify_action(tool_name, tool_input)
        risk_class = policy_engine.risk_of(action_type, policy.get("risk_classes"))
        lane = resolve_lane()
        posture = resolve_gate_posture(lane) if resolve_gate_posture else "guardian"
        postures = policy.get("postures")
        grant_id = None
        need_id = None

        if policy.get("_validation_failed"):
            # load_policies quarantined the merged floor (D8) — the gate
            # resolves propose-only fail-closed; mirror it.
            verdict = "propose_only"
            state = None
        elif risk_class is None:
            # Unknown / ambiguous / unmapped action -> fail-safe propose_only.
            verdict = "propose_only"
            state = None
        elif isinstance(policy.get("hard_ceiling"), list) and risk_class in policy["hard_ceiling"]:
            # Hard ceiling short-circuit — ignores confidence, fail-closed.
            verdict = "always_gated"
            state = None
            if posture != "guardian" and standing_grant_resolution is not None:
                ceiling_verdict = policy_engine.resolve_verdict(
                    policy.get("verdicts"), risk_class, "*",
                    posture=posture, postures=postures,
                )
                if ceiling_verdict == "standing_grant":
                    probe = standing_grant_resolution(
                        risk_class, action_type, lane=lane,
                        context=grant_context(tool_input) if grant_context else None,
                        officer=officer, act=False,
                    )
                    if probe.get("available"):
                        verdict = "standing_grant"
                        grant_id = probe.get("grant_id")
                        need_id = None if probe.get("granted") else probe.get("need_id")
                    # else: kernel unavailable — the gate degrades the row to
                    # plain always_gated; the record mirrors that.
        else:
            state = policy_engine.read_cell_state(officer, lane, action_type)
            if resolve_gate_posture is not None:
                verdict = policy_engine.resolve_verdict(
                    policy.get("verdicts"), risk_class, state,
                    posture=posture, postures=postures,
                )
                if verdict == "standing_grant":
                    # Misplaced on a non-ceiling row — the gate fails closed
                    # to propose (only posture ceiling rows may carry it).
                    verdict = "propose_only"
            else:
                verdict = policy_engine.resolve_verdict(
                    policy.get("verdicts"), risk_class, state
                )
    except Exception:  # noqa: BLE001 - shadow must never raise
        return None

    return {
        "decision": "shadow",  # never a live allow/block — this is a verdict record
        "verdict": verdict,
        "action_type": action_type,
        "risk_class": risk_class,
        "confidence_state": state,
        "posture": posture,
        "grant_id": grant_id,
        "need_id": need_id,
        "officer": officer,
        "policy_version": AUTHORITY_SHADOW_VERSION,
    }


def _append_shadow_event(result: dict[str, Any], hook: dict[str, Any]) -> None:
    """Append one shadow decision record to org_events. Caller guards failures."""
    store = Store()
    payload = {
        "shadow_decision": result,
        "tool_name": hook.get("tool_name"),
        "tool_input": hook.get("tool_input"),
    }
    store.append_event(
        "policy.shadow_decision",
        PRODUCT,
        "policy_shadow",
        f"{result['officer']}:{hook.get('tool_name', 'unknown')}",
        result["officer"],
        payload,
        source="pre-tool-use-shadow",
    )


def maybe_record(result: dict[str, Any], hook: dict[str, Any]) -> None:
    if os.environ.get("ORG_POLICY_SHADOW_RECORD", "1") == "0":
        return
    try:
        _append_shadow_event(result, hook)
    except Exception as exc:  # noqa: BLE001 - shadow path must never block tools.
        if os.environ.get("ORG_POLICY_SHADOW_VERBOSE") == "1":
            print(f"policy-shadow: WARN failed to record event: {exc}", file=sys.stderr)


def maybe_record_authority(hook: dict[str, Any]) -> None:
    """Compute + record the authority-matrix shadow verdict, fully guarded so a
    failure NEVER affects the regex shadow path or blocks a tool."""
    if os.environ.get("ORG_POLICY_SHADOW_RECORD", "1") == "0":
        return
    try:
        result = authority_decision(hook)
        if result is None:
            return
        _append_shadow_event(result, hook)
    except Exception as exc:  # noqa: BLE001 - shadow path must never block tools.
        if os.environ.get("ORG_POLICY_SHADOW_VERBOSE") == "1":
            print(f"policy-shadow: WARN failed to record authority verdict: {exc}", file=sys.stderr)


def main() -> int:
    hook = read_input()
    result = decision(hook)
    maybe_record(result, hook)
    # T7: ALSO emit the typed authority-matrix verdict (shadow-only, guarded).
    maybe_record_authority(hook)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
