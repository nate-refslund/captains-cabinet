"""cabinet-doctor.sh does not false-RED a pristine portfolio hatch on the
three first-boot classes (fresh-hatch #58 + #59):

  * scope grants (§5): a non-deployed product-lane's grant is DROPPED (roster-
    gated, not asserted); a rostered agent's grant to an unregistered server is
    a WARN (degraded capability), never DEAD;
  * MCP env (§3): a shipped BASE connector (.mcp.json) with an unresolved env
    is an optional WARN, never DEAD (a local-only hatch has no cloud keys);
  * officer liveness (§1): a not-loaded on-demand CONSULTANT is a SKIP, never
    DEAD (deploy-mac.sh never installs a keepalive job for consultants).

We run the REAL doctor against a scratch CABINET_ROOT with an isolated HOME (so
§5 reads no real ~/.claude.json) and a closed Redis port (so it cannot touch
the live store / heartbeat). The doctor legitimately DEADs other unrelated
classes on a bare fixture (its own "NOT DESIGNED TO GREEN IN ISOLATION" caveat)
— we assert ONLY on the three classes above, keyed to fixture-invented slugs so
the result is independent of whatever the host's launchd is actually running.

Run: python3.12 -m pytest cabinet/scripts/tests/test_doctor_fresh_hatch_green.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml  # noqa: F401  (proves the interpreter running the doctor has it)

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCTOR = REPO_ROOT / "cabinet" / "scripts" / "cabinet-doctor.sh"
LIB_ROSTER = REPO_ROOT / "cabinet" / "scripts" / "lib_roster.py"


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "cabinet" / "scripts").mkdir(parents=True)
    # the doctor's §1/§5 import lib_roster from <root>/cabinet/scripts — use the
    # EDITED module under test so on_demand + the roster gate are exercised.
    shutil.copy(LIB_ROSTER, root / "cabinet" / "scripts" / "lib_roster.py")

    # roster: a full-time Chair + an on-demand consultant lane (fake slug).
    (root / "instance" / "config").mkdir(parents=True)
    (root / "instance" / "config" / "roster.yml").write_text(
        "roster:\n"
        "  cos:\n"
        "    type: fulltime\n"
        "  lane-a-ceo:\n"
        "    type: consultant\n",
        encoding="utf-8")

    # no non-officer services — officers are merged in from the roster.
    (root / "cabinet" / "services.yml").write_text("services: []\n", encoding="utf-8")

    # mcp-scope: cos (rostered) grants an unregistered `brain` -> WARN; the
    # NON-rostered lane-z-ceo grants a unique `zonly-mcp` -> roster-gated away.
    (root / "cabinet" / "mcp-scope.yml").write_text(
        "cabinet: main\n"
        "agents:\n"
        "  cos:\n"
        "    mcps: [brain]\n"
        "  lane-z-ceo:\n"
        "    mcps: [zonly-mcp]\n"
        "universal: []\n",
        encoding="utf-8")

    # a BASE connector referencing an env with no default and no value set.
    (root / ".mcp.json").write_text(json.dumps({
        "mcpServers": {
            "neon": {"command": "npx", "args": ["-y", "neon"],
                     "env": {"NEON_API_KEY": "${NEON_API_KEY}"}}}
    }), encoding="utf-8")

    (tmp_path / "home").mkdir()   # isolated HOME (no real ~/.claude.json)
    return root


def _run_doctor(tmp_path: Path):
    root = _fixture(tmp_path)
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(root)
    env["HOME"] = str(tmp_path / "home")            # hermetic §5 registration
    env["CABINET_PYTHON"] = sys.executable          # yaml-capable interpreter
    env["REDIS_HOST"] = "127.0.0.1"
    env["REDIS_PORT"] = "6399"                       # closed -> never touch live Redis
    # keep yaml resolvable for the doctor's subprocess python even under the
    # pinned HOME (user-site would otherwise vanish — house lesson).
    env["PYTHONPATH"] = str(Path(yaml.__file__).resolve().parents[1]) + \
        os.pathsep + env.get("PYTHONPATH", "")
    env.pop("NEON_API_KEY", None)
    env.pop("CABINET_SOURCE_REPO", None)             # else it overrides CABINET_ROOT
    proc = subprocess.run(
        ["bash", str(DOCTOR)],
        capture_output=True, text=True, env=env, timeout=120)
    return proc.stdout + proc.stderr


def _lines(out: str, pattern: str) -> list[str]:
    return [ln for ln in out.splitlines() if pattern in ln]


def test_consultant_officer_is_skipped_not_dead(tmp_path):
    out = _run_doctor(tmp_path)
    # the on-demand consultant (fake slug -> never in the host's launchd) must
    # SKIP, not DEAD.
    dead = [ln for ln in out.splitlines()
            if ln.startswith("DEAD") and "officer-lane-a-ceo" in ln]
    assert not dead, f"consultant false-DEADed:\n{out}"
    skips = [ln for ln in out.splitlines()
             if ln.startswith("SKIP") and "officer-lane-a-ceo" in ln
             and "on-demand" in ln]
    assert skips, f"expected an on-demand SKIP for the consultant:\n{out}"


def test_scope_grants_never_dead_on_fresh_hatch(tmp_path):
    out = _run_doctor(tmp_path)
    dead_scope = [ln for ln in out.splitlines()
                  if ln.startswith("DEAD") and "scope grant" in ln]
    assert not dead_scope, f"a scope grant was DEAD on a fresh hatch:\n{out}"
    # cos's rostered-but-unregistered `brain` grant degrades to WARN
    assert any(ln.startswith("WARN") and "scope grant brain" in ln
               for ln in out.splitlines()), out
    # the non-deployed lane's grant was roster-gated away entirely (no line)
    assert not _lines(out, "zonly-mcp"), (
        f"a non-deployed lane's grant leaked into the doctor output:\n{out}")


def test_base_mcp_env_is_warn_not_dead(tmp_path):
    out = _run_doctor(tmp_path)
    dead_neon = [ln for ln in out.splitlines()
                 if ln.startswith("DEAD") and "mcp neon" in ln]
    assert not dead_neon, f"a base-layer MCP with a missing env was DEAD:\n{out}"
    assert any(ln.startswith("WARN") and "mcp neon" in ln and "optional connector" in ln
               for ln in out.splitlines()), out
