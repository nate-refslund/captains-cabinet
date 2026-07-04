"""Tests for the typed policy SHADOW evaluator [T7].

Design: docs/authority-matrix-design-2026-06-19.md §7 FIX-2 Stage 0.

`cabinet/scripts/policy-shadow.py` is re-wired to import the policy engine and
emit an AUTHORITY-MATRIX verdict (auto | auto_with_veto_window | notify_after |
propose_only | always_gated) to org_events as `policy.shadow_decision` with
`policy_version='authority-shadow-v1'` — ALONGSIDE its unchanged regex shadow
decision (which keeps `policy_version='shadow-v1'`).

The hard invariant: SHADOW ONLY. The shadow never blocks (always exits 0) and
adds zero live behavior change. These tests assert:

  (a) the authority verdict is emitted as a typed value tagged
      `authority-shadow-v1`, and the fail-safe spine holds (hard-ceiling ->
      always_gated; unmeasured non-ceiling -> propose_only; A0 never emits
      `auto` for a real officer action);
  (b) the existing regex shadow decision path still works unchanged
      (`policy_version='shadow-v1'`, decision allow/block as before);
  (c) no live block — main() returns 0, never exits 2.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure the lib directory is importable (org_runtime, policy_engine live here).
_LIB_DIR = Path(__file__).parent.parent.resolve()
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

# Force the real yaml (conftest.py may stub it for ETL tests).
if "yaml" in sys.modules:
    _yaml_mod = sys.modules["yaml"]
    if not hasattr(_yaml_mod, "safe_load"):
        del sys.modules["yaml"]
        import yaml  # noqa: E402,F401

        sys.modules["yaml"] = sys.modules["yaml"]

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SHADOW_PATH = _REPO_ROOT / "cabinet" / "scripts" / "policy-shadow.py"


def _load_shadow_module():
    """Import the hyphenated policy-shadow.py as a module."""
    spec = importlib.util.spec_from_file_location("policy_shadow_under_test", _SHADOW_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _events(db_path: str, event_type: str = "policy.shadow_decision") -> list[dict]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT payload_json FROM org_events WHERE event_type=? ORDER BY created_at",
            (event_type,),
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(r[0]) for r in rows]


def _run_shadow(mod, hook: dict, db_path: str, officer: str = "cos", **env):
    """Drive policy-shadow.py main() end-to-end with stdin = hook JSON."""
    base_env = {
        "ORG_RUNTIME_DB": db_path,
        "ORG_RUNTIME_PRODUCT": "captains-cabinet",
        "ORG_POLICY_SHADOW_RECORD": "1",
        "OFFICER_NAME": officer,
        "CABINET_ROOT": str(_REPO_ROOT),
    }
    base_env.update(env)
    with patch.dict(os.environ, base_env, clear=False):
        os.environ.pop("OFFICER", None)
        with patch("sys.stdin", StringIO(json.dumps(hook))):
            with patch("sys.stdout", StringIO()):
                rc = mod.main()
    return rc


# Mirrors the matrix verdict vocabulary (framework/policies/authority-matrix.yml
# "verdict in {...}" header). act_with_undo + classifier joined 2026-07-04 with
# the trust-inversion germline batch — the shadow records resolve_verdict's
# output verbatim, so the typed set must track the matrix vocab exactly.
_TYPED_VERDICTS = {
    "auto",
    "act_with_undo",
    "auto_with_veto_window",
    "notify_after",
    "propose_only",
    "always_gated",
    "classifier",
}


class TestAuthorityShadowEmission:
    """(a) the authority verdict is emitted, typed, tagged authority-shadow-v1."""

    def test_emits_authority_verdict_with_version_tag(self):
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            _run_shadow(
                mod,
                {"tool_name": "Edit", "tool_input": {"file_path": "/workspace/product/a.ts"}},
                db,
                officer="cto",
            )
            evs = _events(db)
            authority = [
                e for e in evs
                if e.get("shadow_decision", {}).get("policy_version") == "authority-shadow-v1"
            ]
            assert authority, "expected an authority-shadow-v1 shadow_decision event"
            verdict = authority[0]["shadow_decision"].get("verdict")
            assert verdict in _TYPED_VERDICTS, f"verdict {verdict!r} not a typed verdict"

    def test_reversible_unmeasured_is_act_with_undo(self):
        # TRUST-INVERSION (germline batch 2026-07-04): a plain local edit ->
        # reversible -> unmeasured -> act_with_undo (trust granted day-one,
        # lost on demotion evidence — never earn-up). The shadow records the
        # verdict verbatim; the LIVE gate additionally allows only when the
        # undo plane is viable (policy_engine._act_with_undo_gap).
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            _run_shadow(
                mod,
                {"tool_name": "Edit", "tool_input": {"file_path": "/workspace/product/a.ts"}},
                db,
                officer="cto",
            )
            authority = [
                e["shadow_decision"] for e in _events(db)
                if e.get("shadow_decision", {}).get("policy_version") == "authority-shadow-v1"
            ]
            assert authority and authority[0]["verdict"] == "act_with_undo"

    def test_hard_ceiling_is_always_gated(self):
        # git push origin main -> deploy_prod (hard ceiling) -> always_gated.
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            _run_shadow(
                mod,
                {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
                db,
                officer="cto",
            )
            authority = [
                e["shadow_decision"] for e in _events(db)
                if e.get("shadow_decision", {}).get("policy_version") == "authority-shadow-v1"
            ]
            assert authority and authority[0]["verdict"] == "always_gated"

    def test_a0_never_emits_auto_for_real_actions(self):
        """The fail-closed invariant in the shadow stream: no probe yields a
        typed `auto` verdict at unmeasured confidence — act_with_undo is the
        ONLY acting verdict reachable there (trust-inversion, 2026-07-04),
        and it is a distinct typed verdict, never spelled `auto`."""
        mod = _load_shadow_module()
        probes = [
            ("Edit", {"file_path": "/workspace/product/a.ts"}),
            ("Bash", {"command": "git push origin feature/x"}),
            ("Bash", {"command": "git push origin main"}),
            ("Bash", {"command": "vercel deploy --prod"}),
            ("Bash", {"command": "stripe charge --amount 100"}),
            ("Bash", {"command": "cat /workspace/product/.env"}),
            (
                "mcp__brain__queue_draft",
                {"recipient": "sean@stepnetwork.dk", "channel": "teams"},
            ),
            (
                "mcp__brain__queue_draft",
                {"recipient": "out@example.com", "channel": "email"},
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            for tool_name, tool_input in probes:
                _run_shadow(
                    mod,
                    {"tool_name": tool_name, "tool_input": tool_input},
                    db,
                    officer="cto",
                )
            authority = [
                e["shadow_decision"] for e in _events(db)
                if e.get("shadow_decision", {}).get("policy_version") == "authority-shadow-v1"
            ]
            assert len(authority) == len(probes)
            for a in authority:
                assert a["verdict"] != "auto", f"A0 leaked auto: {a}"
                assert a["verdict"] in _TYPED_VERDICTS


class TestRegexShadowUnchanged:
    """(b) the existing regex shadow path still works, untouched."""

    def test_regex_shadow_block_still_emitted(self):
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            _run_shadow(
                mod,
                {"tool_name": "Bash", "tool_input": {"command": "vercel deploy --prod"}},
                db,
                officer="cto",
            )
            regex = [
                e["shadow_decision"] for e in _events(db)
                if e.get("shadow_decision", {}).get("policy_version") == "shadow-v1"
            ]
            assert regex, "expected the unchanged regex shadow-v1 decision"
            assert regex[0]["decision"] == "block"
            assert "production_deploy" in regex[0]["reason"]

    def test_regex_shadow_allow_still_emitted(self):
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            _run_shadow(
                mod,
                {"tool_name": "Bash", "tool_input": {"command": "echo hello"}},
                db,
                officer="cos",
            )
            regex = [
                e["shadow_decision"] for e in _events(db)
                if e.get("shadow_decision", {}).get("policy_version") == "shadow-v1"
            ]
            assert regex and regex[0]["decision"] == "allow"

    def test_decision_function_is_unchanged_shape(self):
        """decision() still returns the v1 regex shape (no authority leakage)."""
        mod = _load_shadow_module()
        res = mod.decision(
            {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
        )
        assert res["policy_version"] == "shadow-v1"
        assert res["decision"] == "allow"
        assert "verdict" not in res  # authority lives in its own emission


class TestNoLiveBlock:
    """(c) shadow never blocks — main() returns 0, never exits 2."""

    def test_main_returns_zero_on_ceiling_action(self):
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            rc = _run_shadow(
                mod,
                {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
                db,
                officer="cto",
            )
            assert rc == 0

    def test_main_never_raises_systemexit_2(self):
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            try:
                rc = _run_shadow(
                    mod,
                    {"tool_name": "Bash", "tool_input": {"command": "vercel deploy --prod"}},
                    db,
                    officer="cto",
                )
            except SystemExit as exc:  # pragma: no cover - would be a failure
                pytest.fail(f"shadow raised SystemExit({exc.code}) — must never block")
            assert rc == 0

    def test_authority_failure_never_breaks_shadow(self):
        """If authority computation cannot run (no policies found), the shadow
        still completes and still emits the regex decision (fail-safe)."""
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            # Point CABINET_ROOT at an empty dir -> no authority-matrix policy.
            empty_root = os.path.join(tmp, "empty")
            os.makedirs(empty_root)
            rc = _run_shadow(
                mod,
                {"tool_name": "Bash", "tool_input": {"command": "echo hello"}},
                db,
                officer="cos",
                CABINET_ROOT=empty_root,
            )
            assert rc == 0
            regex = [
                e["shadow_decision"] for e in _events(db)
                if e.get("shadow_decision", {}).get("policy_version") == "shadow-v1"
            ]
            assert regex, "regex shadow must still emit even when authority can't"
