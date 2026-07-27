"""Tests for the typed policy SHADOW evaluator [T7].

Design: framework/docs/authority-matrix-design-2026-06-19.md §7 FIX-2 Stage 0.

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
import signal
import sqlite3
import sys
import tempfile
import time
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


@pytest.fixture(autouse=True)
def _synthetic_org_domains(monkeypatch):
    """Pin the internal-domain set to the synthetic fixture domain so the
    internal/external comms classification is hermetic — never coupled to
    this deployment's instance/config org_domains value (classifier freezes
    env.org_domains() at import time, so patch the module constant; same
    pattern as framework/authority/tests/test_classifier.py)."""
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from framework.authority import classifier as _clf

    monkeypatch.setattr(_clf, "_INTERNAL_DOMAINS", ("testburg.example",))


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
                {"recipient": "casey@testburg.example", "channel": "teams"},
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


# ===================================================================
# SOVEREIGN POSTURE MIRROR [SOV-3]
# ===================================================================
# The shadow record mirrors the posture-aware gate: it gains posture /
# grant_id / need_id fields, resolves sovereign verdicts from the floor's
# postures table, and probes standing_grant ceiling rows SIDE-EFFECT-FREE
# (no need filed, no rate use counted — the shadow is a recorder). Guardian
# default world: identical verdicts, posture="guardian". Never blocks.


class _FakeGrants:
    def __init__(self, granted=False, grant_id=None):
        self.granted = granted
        self.grant_id = grant_id
        self.check_calls = []
        self.use_calls = []

    def check(self, risk_class, action_type, *, lane, context=None,
              file_needs=True, **kw):
        self.check_calls.append({"file_needs": file_needs})
        if self.granted:
            return {"granted": True, "grant_id": self.grant_id, "reason": "matched"}
        return {"granted": False, "grant_id": None,
                "reason": "no matching standing grant"}

    def record_use(self, grant_id, **kw):
        self.use_calls.append(grant_id)
        return True


class _FakeNeeds:
    def __init__(self, nid="NEED-feedbeef"):
        self.nid = nid
        self.file_calls = []

    def file_need(self, kind, **kw):
        self.file_calls.append(kind)
        return self.nid

    def need_id(self, kind, risk_class=None, action_type=None, lane=None):
        return self.nid


def _authority_records(db: str) -> list[dict]:
    return [
        e["shadow_decision"] for e in _events(db)
        if e.get("shadow_decision", {}).get("policy_version") == "authority-shadow-v1"
    ]


class TestPostureShadowMirror:
    """[SOV-3] the authority record carries posture/grant_id/need_id and
    mirrors the sovereign gate — while staying record-only."""

    def test_guardian_default_record_fields(self):
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            _run_shadow(
                mod,
                {"tool_name": "Edit", "tool_input": {"file_path": "/workspace/product/a.ts"}},
                db,
                officer="cto",
            )
            rec = _authority_records(db)[0]
        # RECONCILE 2026-07-05: kept both — guardian semantics for a
        # reversible Edit@unmeasured are act_with_undo under main's ratified
        # trust-inversion floor (the old propose_only pin was the pre-widening
        # earn-up guardian). The SOV-3 mirror obligation is unchanged: posture
        # recorded, no grant/need on the default path.
        assert rec["verdict"] == "act_with_undo"
        assert rec["posture"] == "guardian"
        assert rec["grant_id"] is None
        assert rec["need_id"] is None

    def test_guardian_ceiling_record_unchanged(self):
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            _run_shadow(
                mod,
                {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
                db,
                officer="cto",
            )
            rec = _authority_records(db)[0]
        assert rec["verdict"] == "always_gated"
        assert rec["posture"] == "guardian"
        assert rec["grant_id"] is None and rec["need_id"] is None

    def test_sovereign_ceiling_no_grant_records_need_fingerprint(self):
        mod = _load_shadow_module()
        pe = mod.policy_engine
        assert pe is not None
        fake_g = _FakeGrants(granted=False)
        fake_n = _FakeNeeds(nid="NEED-feedbeef")
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            with patch.object(pe, "_resolve_posture", lambda lane=None: "sovereign"), \
                    patch.object(pe, "_grants", fake_g), \
                    patch.object(pe, "_needs", fake_n):
                rc = _run_shadow(
                    mod,
                    {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
                    db,
                    officer="cto",
                )
            rec = _authority_records(db)[0]
        assert rc == 0  # never blocks
        assert rec["verdict"] == "standing_grant"
        assert rec["posture"] == "sovereign"
        assert rec["grant_id"] is None
        assert rec["need_id"] == "NEED-feedbeef"
        # SIDE-EFFECT-FREE probe: nothing filed, nothing counted, loader
        # config-needs suppressed.
        assert fake_n.file_calls == []
        assert fake_g.use_calls == []
        assert fake_g.check_calls == [{"file_needs": False}]

    def test_sovereign_ceiling_grant_match_records_grant_id(self):
        mod = _load_shadow_module()
        pe = mod.policy_engine
        fake_g = _FakeGrants(granted=True, grant_id="GRANT-abc")
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            with patch.object(pe, "_resolve_posture", lambda lane=None: "sovereign"), \
                    patch.object(pe, "_grants", fake_g), \
                    patch.object(pe, "_needs", _FakeNeeds()):
                _run_shadow(
                    mod,
                    {
                        "tool_name": "mcp__brain__queue_draft",
                        "tool_input": {"recipient": "out@example.com", "channel": "email"},
                    },
                    db,
                    officer="cos",
                )
            rec = _authority_records(db)[0]
        assert rec["verdict"] == "standing_grant"
        assert rec["grant_id"] == "GRANT-abc"
        assert rec["need_id"] is None
        assert fake_g.use_calls == []  # the shadow NEVER consumes rate budget

    def test_sovereign_kernel_unavailable_records_always_gated(self):
        mod = _load_shadow_module()
        pe = mod.policy_engine
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            with patch.object(pe, "_resolve_posture", lambda lane=None: "sovereign"), \
                    patch.object(pe, "_grants", None), \
                    patch.object(pe, "_needs", None):
                _run_shadow(
                    mod,
                    {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
                    db,
                    officer="cto",
                )
            rec = _authority_records(db)[0]
        # The gate degrades the row to plain always_gated — mirror it.
        assert rec["verdict"] == "always_gated"
        assert rec["posture"] == "sovereign"
        assert rec["grant_id"] is None and rec["need_id"] is None

    def test_sovereign_notify_after_recorded(self):
        mod = _load_shadow_module()
        pe = mod.policy_engine
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            with patch.object(pe, "_resolve_posture", lambda lane=None: "sovereign"):
                _run_shadow(
                    mod,
                    {
                        "tool_name": "mcp__brain__queue_draft",
                        "tool_input": {"recipient": "casey@testburg.example", "channel": "teams"},
                    },
                    db,
                    officer="cos",
                )
            rec = _authority_records(db)[0]
        assert rec["verdict"] == "notify_after"
        assert rec["posture"] == "sovereign"
        assert rec["risk_class"] == "internal_comms"

    def test_sovereign_reversible_records_auto(self):
        mod = _load_shadow_module()
        pe = mod.policy_engine
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            rc = None
            with patch.object(pe, "_resolve_posture", lambda lane=None: "sovereign"):
                rc = _run_shadow(
                    mod,
                    {"tool_name": "Edit", "tool_input": {"file_path": "/workspace/product/a.ts"}},
                    db,
                    officer="cto",
                )
            rec = _authority_records(db)[0]
        assert rc == 0  # record-only even on an auto verdict
        assert rec["verdict"] == "auto"
        assert rec["posture"] == "sovereign"


class TestMissingFloorShadowFailClosed:
    """[SOV-3 D8] a missing/unparseable authority floor surfaces in the shadow
    stream as a fail-closed propose_only record — never as SILENCE (no record
    at all was the fail-open blindspot: load_policies now synthesizes the
    quarantine stub, and the shadow mirrors its `_validation_failed`)."""

    @staticmethod
    def _root(tmp: str, floor_text: str | None = None) -> str:
        """A minimal CABINET_ROOT whose authority floor is missing (default)
        or unparseable (floor_text)."""
        root = os.path.join(tmp, "root")
        fw = Path(root) / "framework" / "policies"
        fw.mkdir(parents=True)
        if floor_text is not None:
            (fw / "authority-matrix.yml").write_text(floor_text)
        inst = Path(root) / "instance" / "config"
        inst.mkdir(parents=True)
        (inst / "active-preset").write_text("work")
        return root

    def test_deleted_floor_records_propose_only(self):
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            rc = _run_shadow(
                mod,
                {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
                db,
                officer="cto",
                CABINET_ROOT=self._root(tmp),
            )
            recs = _authority_records(db)
        assert rc == 0  # never blocks
        assert recs, "missing floor must record fail-closed, not fall silent"
        # Even a ceiling probe resolves propose_only: the quarantine wins
        # before the ceiling branch, exactly like the gate's step 0.
        assert recs[0]["verdict"] == "propose_only"
        assert recs[0]["posture"] == "guardian"
        assert recs[0]["grant_id"] is None and recs[0]["need_id"] is None

    def test_unparseable_floor_records_propose_only(self):
        mod = _load_shadow_module()
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "shadow.sqlite3")
            rc = _run_shadow(
                mod,
                {"tool_name": "Edit", "tool_input": {"file_path": "/workspace/product/a.ts"}},
                db,
                officer="cto",
                CABINET_ROOT=self._root(tmp, floor_text="this is not: valid: yaml: [[[["),
            )
            recs = _authority_records(db)
            regex = [
                e["shadow_decision"] for e in _events(db)
                if e.get("shadow_decision", {}).get("policy_version") == "shadow-v1"
            ]
        assert rc == 0
        assert recs and recs[0]["verdict"] == "propose_only"
        assert regex, "the legacy shadow decision must still emit"


class TestPolicyEvalTimeoutFailsClosed:
    """A typed-policy evaluation that will not finish must BLOCK, not fall back.

    WHY THIS MATTERS MORE THAN IT LOOKS. `_engine_decision` deliberately
    swallows every other exception and returns None, which drops the caller to
    the weaker regex shadow. For a TIMEOUT that fallback would be a bypass
    primitive: an input crafted to wedge the classifier would be evaluated by
    the fallback instead of by the policy that was supposed to judge it. It
    would also be a fail-open in the enforcer — allowing a call the gate never
    managed to assess. So the timeout arm is the one exception that blocks.

    The regex fix in policy_engine is the actual remedy; this is the net under
    it, for the wedging pattern nobody has found yet.
    """

    HOOK = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}

    def test_timeout_blocks_and_names_the_policy(self, monkeypatch):
        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", "0.25")

        def _never_returns(policy, tool_name, tool_input, officer):
            # 12x the budget: unambiguously a breach, but small enough that a
            # regression (bound removed) fails in seconds per policy instead of
            # turning this arm into a multi-minute hang.
            time.sleep(3)
            return None

        monkeypatch.setattr(mod.policy_engine, "evaluate_policy", _never_returns)
        started = time.monotonic()
        res = mod._engine_decision(self.HOOK, "cos")
        elapsed = time.monotonic() - started

        assert elapsed < 10, f"the bound did not fire — took {elapsed:.1f}s"
        assert res is not None, (
            "a timeout returned None, which drops to the weaker regex fallback "
            "— that is the fail-open this arm exists to prevent"
        )
        assert res["decision"] == "block", f"FAIL-OPEN on timeout: {res}"
        assert res["reason"].endswith("_eval_timeout"), res
        assert "did not finish" in res.get("detail", "")

    def test_budget_zero_disables_the_bound(self, monkeypatch):
        """0 means unbounded — the pre-2026-07-27 behaviour, for a bisect."""
        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", "0")
        assert mod._eval_budget() == 0.0
        calls = []
        monkeypatch.setattr(
            mod.policy_engine, "evaluate_policy",
            lambda *a: calls.append(1) or None,
        )
        res = mod._engine_decision(self.HOOK, "cos")
        assert calls, "policies must still be evaluated with the bound disabled"
        assert res is not None and res["decision"] == "allow"

    @pytest.mark.parametrize("raw", [
        "not-a-number", "-5", "",
        # NON-FINITE is the degenerate value that actually bites: `inf` parses
        # as a float, then setitimer raises OverflowError, which the blanket
        # handler turns into a silent fall-through to the weaker regex shadow.
        # One env var would have disabled the enforcing engine — and `0`, the
        # documented way to disable the bound, is safer than `inf` was.
        "inf", "-inf", "Infinity", "1e400", "nan",
    ])
    def test_malformed_budget_falls_back_to_the_default(self, monkeypatch, raw):
        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", raw)
        assert mod._eval_budget() == 2.0, f"{raw!r} produced a non-default budget"

    def test_absent_budget_is_the_default(self, monkeypatch):
        mod = _load_shadow_module()
        monkeypatch.delenv("CABINET_POLICY_EVAL_TIMEOUT", raising=False)
        assert mod._eval_budget() == 2.0

    def test_budget_is_clamped(self, monkeypatch):
        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", "99999")
        assert mod._eval_budget() == mod._EVAL_BUDGET_MAX

    def test_non_finite_budget_does_not_disable_the_engine(self, monkeypatch):
        """The end-to-end form of the arm above: an `inf` budget must still
        produce a real typed verdict, not a fall-through to the regex shadow."""
        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", "inf")
        res = mod._engine_decision(
            {"tool_name": "Bash",
             "tool_input": {"command": "sed -i 's/a/b/' /workspace/product/f.txt"}},
            "cpo",
        )
        assert res is not None, (
            "an inf budget dropped _engine_decision to the regex fallback — "
            "that is a one-env-var bypass of the typed enforcing engine"
        )
        assert res["decision"] == "block"

    def test_budget_is_total_not_per_policy(self, monkeypatch):
        """Eleven policies load; the guarantee must not be 11x the number.

        Every evaluation is made slow, so a per-policy bound would spend the
        budget once per policy before returning.
        """
        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", "1")
        monkeypatch.setattr(
            mod.policy_engine, "evaluate_policy",
            lambda *a: time.sleep(3) or None,
        )
        started = time.monotonic()
        res = mod._engine_decision(self.HOOK, "cos")
        elapsed = time.monotonic() - started
        assert res is not None and res["decision"] == "block"
        assert elapsed < 2.5, (
            f"took {elapsed:.1f}s for a 1s budget — the bound is being spent "
            f"once per policy instead of once per call"
        )

    def test_normal_evaluation_is_unaffected_by_the_bound(self, monkeypatch):
        """The bound must be invisible to every call that answers in time."""
        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", "5")
        res = mod._engine_decision(
            {"tool_name": "Bash", "tool_input": {"command": "echo hello"}}, "cos"
        )
        assert res is not None and res["decision"] == "allow"
        blocked = mod._engine_decision(
            {"tool_name": "Bash",
             "tool_input": {"command": "sed -i 's/a/b/' /workspace/product/f.txt"}},
            "cpo",
        )
        assert blocked is not None and blocked["decision"] == "block"
        assert not blocked["reason"].endswith("_eval_timeout"), blocked

    def test_alarm_handler_is_restored(self, monkeypatch):
        """A hook process must not leave a SIGALRM handler behind."""
        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", "5")
        before = signal.getsignal(signal.SIGALRM)
        mod._engine_decision(self.HOOK, "cos")
        assert signal.getsignal(signal.SIGALRM) is before
        assert signal.getitimer(signal.ITIMER_REAL)[0] == 0.0

    def test_alarm_state_is_clean_after_a_TIMEOUT(self, monkeypatch):
        """The arm above only walks the FAST path, so it cannot see the defect
        that actually existed: teardown after a real breach.

        A SIGALRM generated just before the timer is disarmed is delivered
        afterwards. If the armed-flag did not neutralise it, that straggler
        either escapes as an exception from an unrelated frame or — once the
        previous disposition (SIG_DFL in production) is restored — kills the
        process with signal 14. Both were reproduced before this arm existed.
        """
        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", "0.2")
        monkeypatch.setattr(
            mod.policy_engine, "evaluate_policy",
            lambda *a: time.sleep(3) or None,
        )
        before = signal.getsignal(signal.SIGALRM)
        res = mod._engine_decision(self.HOOK, "cos")
        assert res is not None and res["decision"] == "block"
        assert signal.getsignal(signal.SIGALRM) is before, "handler leaked"
        assert signal.getitimer(signal.ITIMER_REAL)[0] == 0.0, "itimer left armed"
        assert mod._EVAL_ALARM_ARMED is False, "armed flag left set"
        # A straggler arriving now must be swallowed, not raised and not fatal.
        mod._raise_eval_timeout(signal.SIGALRM, None)  # must NOT raise

    def test_repeated_timeouts_do_not_leak_state(self, monkeypatch):
        """Ten breaches in a row: no accumulation, no escape, no death."""
        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", "0.1")
        monkeypatch.setattr(
            mod.policy_engine, "evaluate_policy",
            lambda *a: time.sleep(2) or None,
        )
        for i in range(10):
            res = mod._engine_decision(self.HOOK, "cos")
            assert res is not None and res["decision"] == "block", f"iteration {i}"
            assert mod._EVAL_ALARM_ARMED is False, f"iteration {i}"

    def test_off_main_thread_degrades_without_crashing(self, monkeypatch):
        """SIGALRM needs the main thread; off it the call must still answer."""
        import threading as _t

        mod = _load_shadow_module()
        monkeypatch.setenv("CABINET_POLICY_EVAL_TIMEOUT", "2")
        out = {}

        def run():
            try:
                out["res"] = mod._engine_decision(self.HOOK, "cos")
            except Exception as exc:  # noqa: BLE001
                out["exc"] = exc

        th = _t.Thread(target=run)
        th.start()
        th.join(timeout=60)
        assert not th.is_alive(), "off-thread evaluation hung"
        assert "exc" not in out, f"off-thread evaluation raised {out.get('exc')!r}"
        assert out["res"] is not None and out["res"]["decision"] == "allow"
