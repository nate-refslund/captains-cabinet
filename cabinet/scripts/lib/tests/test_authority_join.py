"""T1 — proves the policy engine consumes the ONE shared classify_action /
resolve_lane (the F+A join key), not a private copy.

This is the cross-tree half of the join-key contract: the gate side
(framework/authority/policy_engine.py, CG-14 pull-down) and the framework side
(framework.authority) must resolve to the SAME function objects, so the ledger
key and the verdict-table lookup can never disagree about an action_type.

See framework/docs/authority-matrix-design-2026-06-19.md FIX-1 / FIX-4.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Repo root importable — the engine is framework/authority/policy_engine
# (CG-14 pull-down 2026-07-07; the lib path-insert bootstrap is retired).
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Force the real yaml (conftest may stub it).
if "yaml" in sys.modules and not hasattr(sys.modules["yaml"], "safe_load"):
    del sys.modules["yaml"]
    import yaml  # noqa: F401

from framework.authority import policy_engine  # noqa: E402


def test_policy_engine_imported_shared_symbols():
    # The deferred import must have succeeded — the gate has the join key.
    assert policy_engine.classify_action is not None
    assert policy_engine.resolve_lane is not None


def test_same_object_as_framework_authority():
    from framework.authority.classifier import classify_action as fw_classify
    from framework.authority.lane import resolve_lane as fw_lane

    # Identity, not just equality: one source of truth, no duplicate copy.
    assert policy_engine.classify_action is fw_classify
    assert policy_engine.resolve_lane is fw_lane


def test_gate_classifies_ceiling_and_reversible_identically():
    # The gate produces the same action_type the emitter would stamp.
    assert policy_engine.classify_action(
        "Bash", {"command": "git push origin main"}
    ) == "git_push_main"
    assert policy_engine.classify_action(
        "Edit", {"file_path": "/x/.env"}
    ) == "env_write"
    assert policy_engine.classify_action(
        "Bash", {"command": "curl -X POST https://api.example.com -d '{}'"}
    ) == "mcp_post"
    assert policy_engine.classify_action(
        "Edit", {"file_path": "/workspace/product/src/app.ts"}
    ) == "local_edit"


def test_gate_resolve_lane_precedence(monkeypatch):
    monkeypatch.setenv("CABINET_LANE", "polads")
    monkeypatch.setenv("PROJECT", "stephie")
    assert policy_engine.resolve_lane() == "polads"
    monkeypatch.delenv("CABINET_LANE", raising=False)
    assert policy_engine.resolve_lane() == "stephie"
    monkeypatch.delenv("PROJECT", raising=False)
    assert policy_engine.resolve_lane() is None
