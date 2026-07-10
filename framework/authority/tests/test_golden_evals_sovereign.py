"""Enforcing spines for golden evals 016-019 (sovereign amendment, spec §6).

Each eval markdown under memory/golden-evals/ narrates a Captain-readable
invariant; this file proves it against the REAL shipped artifacts:

  eval-016  posture-guardian-parity      — every attestation failure resolves
            guardian; gate block strings byte-identical to the A0 goldens.
  eval-017  sovereign-ceiling-grant-or-need — D2: block+deduped-NEED without a
            grant; attributed allow only under a live grant; ceilings never
            resolve unconditional auto in ANY posture (behavioral, not a
            literal-string check).
  eval-018  posture-env-cannot-widen     — CABINET_POSTURE=sovereign alone is
            ignored; unlocked grants file loads []; officer writes to the
            attestation configs are hook-blocked.
  eval-019  immutable-core-gate-refusal  — gate.ratify refuses a Ring-0 diff
            at S0; the root apply lane ships DARK with unprivileged verify
            (no root pytest, hooksPath=/dev/null).

Kernel injection follows the SOV-1/SOV-3 conventions: tmp CABINET roots,
`is_locked_fn` stubs, and `patch.object` on the gate's module globals — no
Redis, no network, no root.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import policy_engine as PE  # noqa: E402
from framework.authority.policy_engine import _eval_authority_matrix  # noqa: E402
from framework.authority import grants as G  # noqa: E402
from framework.authority import matrix as M  # noqa: E402
from framework.authority import needs as N  # noqa: E402
from framework.authority import posture as P  # noqa: E402

LOCKED = lambda p: True  # noqa: E731
UNLOCKED = lambda p: False  # noqa: E731

_CEILINGS = (
    "external_comms", "deploy_prod", "spend",
    "secrets", "network_write", "credentials_grant",
)

# The A0 golden block strings (evals 011-015) — the guardian bytes that every
# attestation-failure state must reproduce exactly.
_GOLDEN_EXTERNAL = (
    "GATED (hard ceiling: external_comms) — draft via queue_draft, never auto."
)
_GOLDEN_CEILING = "GATED (hard ceiling: {rc}) — propose to Captain; no auto path."

# One probe per ceiling, classify_action-positive (mirrors test_golden_evals_a0).
_CEILING_PROBES = {
    "external_comms": (
        "mcp__brain__queue_draft",
        {"recipient": "outsider@gmail.com", "body": "hi", "channel": "teams"},
    ),
    "deploy_prod": ("Bash", {"command": "git push origin main"}),
    "spend": ("Bash", {"command": "stripe charge --amount 5000"}),
    "secrets": ("Write", {"file_path": "/workspace/product/.env", "content": "X=1"}),
    "network_write": ("mcp__some__create_post", {}),
    "credentials_grant": ("Bash", {"command": "oauth grant token"}),
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in ("CABINET_POSTURE", "CABINET_NEEDS_WIRED", "CABINET_ID",
                "CABINET_ROOT", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))


def _matrix_policy() -> dict:
    return M.matrix_policy(M.load_matrix())


def _write_posture(root: Path, **overrides) -> Path:
    cfg = {
        "version": 1, "status": "ruled", "ruled_at": "2026-07-05T00:00:00Z",
        "basis": "test ruling", "deployment": "main", "flavor": "org",
        "posture": "sovereign",
    }
    cfg.update(overrides)
    d = root / "instance" / "config"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "posture.yml"
    p.write_text(yaml.safe_dump(cfg))
    return p


class _FakeGrants:
    def __init__(self, granted=False, grant_id=None):
        self.granted, self.grant_id = granted, grant_id
        self.use_calls: list = []

    def check(self, risk_class, action_type, *, lane, context=None,
              file_needs=True, **kw):
        if self.granted:
            return {"granted": True, "grant_id": self.grant_id,
                    "reason": f"standing grant {self.grant_id} matched"}
        return {"granted": False, "grant_id": None,
                "reason": "no matching standing grant"}

    def record_use(self, grant_id, **kw):
        self.use_calls.append(grant_id)
        return True


class _FakeNeeds:
    def __init__(self):
        self.file_calls: list = []

    def file_need(self, kind, *, risk_class=None, action_type=None, lane=None,
                  **kw):
        self.file_calls.append((kind, risk_class, action_type, lane))
        return N.need_id(kind, risk_class, action_type, lane)

    def need_id(self, kind, risk_class=None, action_type=None, lane=None):
        return N.need_id(kind, risk_class, action_type, lane)


def _sovereign():
    return patch.object(PE, "_resolve_posture", lambda lane=None: "sovereign")


# -- hook probes shared by eval-018/019 (subprocess; callers skip when the
#    control plane is unreachable, because the killswitch fail-closed check
#    masks the germline arm) --------------------------------------------------

_HOOK = _REPO_ROOT / "cabinet" / "scripts" / "hooks" / "pre-tool-use.sh"


def _run_hook(payload: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ, OFFICER="cto")
    env.pop("CABINET_AUTHORITY_ENFORCING", None)
    return subprocess.run(
        ["bash", str(_HOOK)], input=json.dumps(payload),
        capture_output=True, text=True, env=env, cwd=str(_REPO_ROOT),
        timeout=60,
    )


def _control_plane_up() -> bool:
    probe = _run_hook({"tool_name": "Bash", "tool_input": {"command": "true"}})
    return probe.returncode == 0


# ---------------------------------------------------------------------------
# eval-016 — posture guardian parity
# ---------------------------------------------------------------------------

class TestEval016GuardianParity:
    def test_every_attestation_failure_resolves_guardian(self, tmp_path):
        # absent
        assert P.resolve_posture(root=tmp_path) == "guardian"
        # corrupt: unparseable
        d = tmp_path / "instance" / "config"
        d.mkdir(parents=True)
        (d / "posture.yml").write_text("posture: [unclosed")
        assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"
        # corrupt: unknown key (closed schema)
        _write_posture(tmp_path, extra_key="nope")
        assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"
        # deployment mismatch
        _write_posture(tmp_path, deployment="mini-other")
        assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"
        # unknown posture value
        _write_posture(tmp_path, posture="root")
        assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"
        # valid but UNLOCKED
        _write_posture(tmp_path)
        assert P.resolve_posture(root=tmp_path, is_locked_fn=UNLOCKED) == "guardian"

    def test_gate_block_strings_byte_identical_under_failure_states(self):
        """With the kernel resolving guardian (any failure state), every
        ceiling block string equals the recorded A0 golden byte-for-byte."""
        pol = _matrix_policy()
        for resolver in (
            None,                                   # kernel module absent
            lambda lane=None: "guardian",           # explicit guardian
            lambda lane=None: (_ for _ in ()).throw(RuntimeError("down")),
        ):
            with patch.object(PE, "_resolve_posture", resolver):
                for rc, (tool, ti) in _CEILING_PROBES.items():
                    result = _eval_authority_matrix(pol, tool, ti, "cto")
                    expected = (
                        _GOLDEN_EXTERNAL if rc == "external_comms"
                        else _GOLDEN_CEILING.format(rc=rc)
                    )
                    assert result == expected, (rc, resolver)

    def test_resolve_verdict_three_variant_equality(self):
        """P1 spine: no-kwargs == posture='guardian' == inert-postures-present."""
        pol = _matrix_policy()
        v, p = pol["verdicts"], pol["postures"]
        for rc in _CEILINGS + ("reversible", "internal_comms", "deploy_nonprod"):
            for state in ("unmeasured", "propose_only", "eligible",
                          "graduated", "demote"):
                base = PE.resolve_verdict(v, rc, state)
                assert PE.resolve_verdict(v, rc, state,
                                          posture="guardian", postures=p) == base
                assert PE.resolve_verdict(v, rc, state,
                                          posture=None, postures=p) == base


# ---------------------------------------------------------------------------
# eval-017 — sovereign ceiling: grant or need, never unconditional auto
# ---------------------------------------------------------------------------

class TestEval017GrantOrNeed:
    def test_empty_grants_all_six_block_and_file_deduped_needs(self):
        pol = _matrix_policy()
        fake_n = _FakeNeeds()
        with _sovereign(), patch.object(PE, "_grants", _FakeGrants()), \
                patch.object(PE, "_needs", fake_n):
            ids = {}
            for rc, (tool, ti) in _CEILING_PROBES.items():
                result = _eval_authority_matrix(pol, tool, ti, "cto")
                assert result is not None, f"{rc} must block without a grant"
                assert f"GATED (standing_grant: {rc})" in result
                m = re.search(r"NEED-[0-9a-f]{8}", result)
                assert m, f"{rc} block must carry the filed NEED id"
                ids[rc] = m.group(0)
                # re-probe: deterministic content fingerprint ⇒ same id (dedup)
                again = _eval_authority_matrix(pol, tool, ti, "cto")
                assert ids[rc] in again
            assert len(set(ids.values())) == len(ids), "need ids are per-class"

    def test_matching_grant_allows_attributed_and_rate_counted(self):
        pol = _matrix_policy()
        fake_g = _FakeGrants(granted=True, grant_id="GRANT-test")
        with _sovereign(), patch.object(PE, "_grants", fake_g), \
                patch.object(PE, "_needs", _FakeNeeds()):
            tool, ti = _CEILING_PROBES["external_comms"]
            assert _eval_authority_matrix(pol, tool, ti, "cto") is None
        assert fake_g.use_calls == ["GRANT-test"]

    def test_degraded_grant_states_block_via_real_kernel(self, tmp_path):
        """Tombstone / expiry / hard-scope violation each ⇒ not granted,
        proven against the REAL grants kernel on a tmp tree."""
        base_row = {
            "id": "GRANT-x", "deployment": "main",
            "risk_class": "external_comms", "action_types": ["external_email"],
            "lanes": ["bakery"],
            "scope": {"recipient_allowlist": ["*@testburg.example"]},
            "rate": {"max_per_day": 10}, "expires": "2099-01-01",
            "granted_by": "Captain (Ada)",
            "granted_at": "2026-07-05T00:00:00Z",
            "basis": "NEED-1a2b3c4d", "revoked": False,
        }
        common = dict(
            lane="bakery", root=tmp_path, is_locked_fn=LOCKED,
            is_vetoed_fn=lambda at: False, file_needs=False,
            context={"recipient": "x@testburg.example"},
            redis_get=lambda k: "",
        )
        # live grant sanity: it CAN grant when everything holds
        ok = G.check("external_comms", "external_email",
                     grants=[dict(base_row)], **common)
        assert ok["granted"] is True and ok["grant_id"] == "GRANT-x"
        # tombstoned (Redis revocation key present)
        res = G.check("external_comms", "external_email",
                      grants=[dict(base_row)],
                      **{**common, "redis_get":
                         lambda k: "1" if "revoked" in k else ""})
        assert res["granted"] is False
        # expired
        res = G.check("external_comms", "external_email",
                      grants=[dict(base_row, expires="2026-01-01")], **common)
        assert res["granted"] is False
        # hard-scope violation: recipient outside the allowlist
        res = G.check("external_comms", "external_email",
                      grants=[dict(base_row)],
                      **{**common, "context": {"recipient": "x@gmail.com"}})
        assert res["granted"] is False
        # missing scope context fails closed
        res = G.check("external_comms", "external_email",
                      grants=[dict(base_row)], **{**common, "context": {}})
        assert res["granted"] is False

    def test_ceilings_never_unconditional_auto_in_any_posture_table(self):
        """The behavioral invariant (replaces the weak literal-'auto' string
        check): every ceiling row in the ROOT table and in EVERY posture table
        resolves only to always_gated or the CONDITIONAL standing_grant."""
        pol = _matrix_policy()
        tables = {"root": pol["verdicts"]}
        for name, entry in (pol.get("postures") or {}).items():
            tables[f"postures.{name}"] = entry["verdicts"]
        for tname, table in tables.items():
            for rc in _CEILINGS:
                row = table[rc]
                assert set(row) == {"*"}, (tname, rc)
                assert row["*"] in ("always_gated", "standing_grant"), (tname, rc)
                assert row["*"] != "auto"
        assert M.no_ceiling_or_prod_auto(pol) is True

    def test_gate_never_allows_a_ceiling_without_grants_in_any_posture(self):
        pol = _matrix_policy()
        for resolver in (None, lambda lane=None: "guardian",
                         lambda lane=None: "sovereign"):
            with patch.object(PE, "_resolve_posture", resolver), \
                    patch.object(PE, "_grants", None), \
                    patch.object(PE, "_needs", None):
                for rc, (tool, ti) in _CEILING_PROBES.items():
                    assert _eval_authority_matrix(pol, tool, ti, "cto") is not None


# ---------------------------------------------------------------------------
# eval-018 — env cannot widen
# ---------------------------------------------------------------------------

class TestEval018EnvCannotWiden:
    def test_env_sovereign_alone_is_ignored(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CABINET_POSTURE", "sovereign")
        assert P.resolve_posture(root=tmp_path) == "guardian"          # absent
        _write_posture(tmp_path)
        assert P.resolve_posture(root=tmp_path,
                                 is_locked_fn=UNLOCKED) == "guardian"  # unlocked
        # env cannot substitute for the lock; only the attested file chain can
        assert P.resolve_posture(root=tmp_path,
                                 is_locked_fn=LOCKED) == "sovereign"

    def test_env_guardian_narrows_even_an_attested_sovereign_ruling(
            self, monkeypatch, tmp_path):
        _write_posture(tmp_path)
        monkeypatch.setenv("CABINET_POSTURE", "guardian")
        assert P.resolve_posture(root=tmp_path, is_locked_fn=LOCKED) == "guardian"

    def test_no_unlock_bypass_env_exists(self):
        """The killed CABINET_POSTURE_UNLOCKED_OK must never reappear as a
        READ env var (the docstring documenting the kill is allowed)."""
        src = (_REPO_ROOT / "framework" / "authority" / "posture.py").read_text()
        for line in src.splitlines():
            if "CABINET_POSTURE_UNLOCKED_OK" in line:
                assert "environ" not in line and "getenv" not in line, line
        # And the ONLY env var the resolver consults is CABINET_POSTURE.
        env_reads = re.findall(
            r"environ(?:\.get)?\(\s*['\"](CABINET_[A-Z_]+)", src
        )
        assert set(env_reads) <= {"CABINET_POSTURE", "CABINET_ID",
                                  "CABINET_ROOT", "CABINET_NEEDS_WIRED"}, env_reads

    def test_unlocked_grants_file_loads_empty(self, tmp_path):
        d = tmp_path / "instance" / "config"
        d.mkdir(parents=True)
        (d / "standing-grants.yml").write_text(yaml.safe_dump({
            "version": 1,
            "grants": [{
                "id": "GRANT-forged", "deployment": "main",
                "risk_class": "spend", "action_types": ["purchase"],
                "lanes": ["bakery"], "scope": {"max_eur_per_day": 100000},
                "rate": {"max_per_day": 100}, "expires": "2099-01-01",
                "granted_by": "attacker", "granted_at": "2026-07-05T00:00:00Z",
                "basis": "NEED-deadbeef", "revoked": False,
            }],
        }))
        assert G.load_grants(tmp_path, is_locked_fn=UNLOCKED,
                             file_needs=False) == []

    @pytest.mark.parametrize("rel", [
        "instance/config/posture.yml",
        "instance/config/standing-grants.yml",
    ])
    def test_officer_writes_to_attestation_configs_hook_blocked(self, rel):
        if not _control_plane_up():
            pytest.skip("Redis control plane unreachable — killswitch "
                        "fail-closed masks the germline arm")
        # Edit tool
        r = _run_hook({"tool_name": "Edit", "tool_input": {
            "file_path": f"/x/{rel}", "old_string": "a", "new_string": "b"}})
        assert r.returncode == 2, r.stderr
        # write-shaped bash
        r = _run_hook({"tool_name": "Bash", "tool_input": {
            "command": f"echo forged > {rel}"}})
        assert r.returncode == 2, r.stderr
        # read stays allowed
        r = _run_hook({"tool_name": "Bash", "tool_input": {
            "command": f"cat {rel}"}})
        assert r.returncode == 0, r.stderr


# ---------------------------------------------------------------------------
# eval-019 — immutable-core gate refusal + dark apply lane
# ---------------------------------------------------------------------------

class TestEval019GateRefusal:
    def test_gate_ratify_refuses_ring0_diff_at_s0(self, tmp_path, monkeypatch):
        from framework.learning import gate as GATE
        # tmp root carrying the REAL Ring-0 enumeration — ratify writes its
        # evidence pack under root, which must never be the repo itself.
        core = tmp_path / "framework" / "policies"
        core.mkdir(parents=True)
        (core / "immutable-core.yml").write_text(
            (_REPO_ROOT / "framework" / "policies" / "immutable-core.yml")
            .read_text()
        )
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        diff = (
            "--- a/framework/authority/policy_engine.py\n"
            "+++ b/framework/authority/policy_engine.py\n"
            "@@ -1 +1 @@\n-x\n+y\n"
        )
        ran = []
        pack = GATE.ratify(
            {"id": "p1", "diff": diff, "summary": "forge the gate"},
            root=tmp_path,
            runner=lambda stage, spec: ran.append(stage) or
            {"status": "pass", "detail": "should never run"},
        )
        assert pack["verdict"] == "refused"
        s0 = pack["stages"][0]
        assert s0["stage"] == "S0_scope" and s0["status"] == "refused"
        assert ran == [], "no verify stage may run after an S0 refusal"

    def test_dark_daemon_not_loaded_by_any_setup_script(self):
        """gate-apply plist ships DARK: no setup/deploy script loads it."""
        hits = subprocess.run(
            ["grep", "-rl", "com.cabinet.gate-apply",
             str(_REPO_ROOT / "cabinet" / "scripts"),
             str(_REPO_ROOT / "cabinet" / "services.yml")],
            capture_output=True, text=True,
        ).stdout.splitlines()
        loaders = [
            h for h in hits
            if h.endswith((".sh", ".py")) and "gate-apply.sh" not in h
            # The germline ENFORCEMENT files NAME the plist in order to
            # schg-lock / hook-block it (SOV-9a) — naming is not loading;
            # the launchctl-load sweep in test_gate_apply_dark.py still
            # covers both files.
            and not h.endswith("germline-lock.sh")
            and not h.endswith("pre-tool-use.sh")
            # The egg exporter NAMES the plist to rewrite its EXPORT COPY
            # portable-dark (PC-E R160 amendment) — packaging, not loading:
            # it copies nothing to /Library/LaunchDaemons, bootstraps
            # nothing, never ships in the egg, and the launchctl-load
            # sweep in test_gate_apply_dark.py still covers it.
            and not h.endswith("egg-export.sh")
            and not h.endswith("test_egg_export.py")
        ]
        assert loaders == [], f"setup scripts must not load the dark daemon: {loaders}"
        # services.yml may DOCUMENT the darkness but never schedule it
        services = yaml.safe_load(
            (_REPO_ROOT / "cabinet" / "services.yml").read_text()
        )
        for svc in services.get("services", []):
            assert svc.get("label") != "com.cabinet.gate-apply", (
                "the dark daemon must not be a scheduled service"
            )

    @pytest.mark.parametrize("rel", [
        "cabinet/scripts/gate-apply.sh",
        "cabinet/launchd/com.cabinet.gate-apply.plist",
        "shared/interfaces/gate-apply-watch.jsonl",
    ])
    def test_officer_writes_to_apply_lane_hook_blocked(self, rel):
        """SOV-9a: the ROOT-EXECUTED apply lane — the script (sudo + dark
        daemon), the LaunchDaemon definition, and the watch ledger whose rows
        cmd_watch executes as a root `git apply -R` — is germline: officer
        Write and write-shaped Bash are hook-blocked, reads stay allowed
        (mirrors eval-018's attestation-config probes)."""
        if not _control_plane_up():
            pytest.skip("Redis control plane unreachable — killswitch "
                        "fail-closed masks the germline arm")
        r = _run_hook({"tool_name": "Write", "tool_input": {
            "file_path": f"/x/{rel}", "content": "forged"}})
        assert r.returncode == 2, r.stderr
        r = _run_hook({"tool_name": "Bash", "tool_input": {
            "command": f"echo forged > {rel}"}})
        assert r.returncode == 2, r.stderr
        r = _run_hook({"tool_name": "Bash", "tool_input": {
            "command": f"cat {rel}"}})
        assert r.returncode == 0, r.stderr

    def test_apply_lane_verify_is_unprivileged_and_hookless(self):
        src = (_REPO_ROOT / "cabinet" / "scripts" / "gate-apply.sh").read_text()
        assert "core.hooksPath=/dev/null" in src
        # The verify path drops root BEFORE any pytest can run (exec sudo -u
        # $VERIFY_USER re-invokes verify unprivileged; test mode refuses).
        assert re.search(r'sudo -u "\$VERIFY_USER"', src), (
            "verify must drop to the unprivileged VERIFY_USER when root"
        )
        # pytest lives ONLY in the verify function — never in the root apply.
        funcs = re.split(r"^(cmd_[a-z_]+\(\))", src, flags=re.M)
        bodies = {funcs[i].rstrip("()"): funcs[i + 1]
                  for i in range(1, len(funcs) - 1, 2)}
        assert re.search(r"\bpytest\b", bodies["cmd_verify"])
        for name, body in bodies.items():
            if name != "cmd_verify":
                assert not re.search(r"\bpytest\b", body), (
                    f"pytest must not appear in {name} (root-reachable)"
                )
        # The root drop happens BEFORE the pytest inside cmd_verify.
        vbody = bodies["cmd_verify"]
        assert vbody.index('sudo -u "$VERIFY_USER"') < vbody.index("pytest")
