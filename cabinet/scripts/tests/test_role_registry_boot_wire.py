"""W6/§4.3-4 — the live role-registry boot wire + pre-flip parity audit
(2026-07-09).

The R8 self-improvement loop (6h REPORT_ONLY soak) evolves roles into
instance/roles/active/*.yml, but officer boot prompts read
.claude/agents/*.md only — the registry was a DEAD WIRE no session ever
read. These tests pin:

  * officer_role_registry_clause (lib/officer-boot.sh) is DARK by default
    (no flag → no clause; flag without a registry file → no clause) and
    emits the registry path when armed;
  * both boot-prompt assemblers (start-officer-mac.sh + start-officer.sh)
    actually call the clause (grep-level lock — the wire must not silently
    fall out of a future prompt rewrite);
  * audit-role-parity.sh: exit 0 on parity, exit 1 on each contamination
    class (fulltime role without an agent file; split model pin; orphan
    agent file), exit 2 when there is no registry to audit — the flag flip
    is gated on exit 0.

All offline (bash + fixture trees in tmp_path).

Run: python3.12 -m pytest cabinet/scripts/tests/test_role_registry_boot_wire.py -q
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
BOOT_LIB = _SCRIPTS_DIR / "lib/officer-boot.sh"
AUDIT = _SCRIPTS_DIR / "audit-role-parity.sh"


def _clause(root: Path, officer: str, flag: str | None) -> str:
    env_prefix = (f"export CABINET_BOOT_ROLES_ACTIVE={flag}; "
                  if flag is not None else "")
    out = subprocess.run(
        ["bash", "-c",
         f"unset CABINET_BOOT_ROLES_ACTIVE; {env_prefix}"
         f"source '{BOOT_LIB}' && officer_role_registry_clause '{root}' '{officer}'"],
        capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return out.stdout


@pytest.fixture()
def role_tree(tmp_path):
    (tmp_path / "instance/roles/active").mkdir(parents=True)
    (tmp_path / ".claude/agents").mkdir(parents=True)
    return tmp_path


def _role_yml(root, slug, model="claude-opus-4-8[1m]", officer_type="fulltime",
              status="active"):
    (root / f"instance/roles/active/{slug}.yml").write_text(
        f"slug: {slug}\ntitle: T\nstatus: {status}\nmodel: {model}\n"
        f"officer_type: {officer_type}\ncapabilities: []\nhats: []\n")


def _agent_md(root, slug, model="claude-opus-4-8[1m]"):
    (root / f".claude/agents/{slug}.md").write_text(
        f"---\nname: {slug}\nmodel: {model}\n---\n\n# {slug}\n")


class TestBootClause:
    def test_dark_by_default(self, role_tree):
        _role_yml(role_tree, "cos")
        assert _clause(role_tree, "cos", None) == ""
        assert _clause(role_tree, "cos", "0") == ""

    def test_armed_flag_without_registry_file_stays_silent(self, role_tree):
        assert _clause(role_tree, "cos", "1") == ""

    def test_armed_flag_with_registry_file_emits_clause(self, role_tree):
        _role_yml(role_tree, "cos")
        clause = _clause(role_tree, "cos", "1")
        assert "instance/roles/active/cos.yml" in clause
        assert clause.startswith(" "), "clause must splice cleanly into the prompt"

    def test_both_boot_assemblers_call_the_clause(self):
        for script in ("start-officer-mac.sh", "start-officer.sh"):
            text = (_SCRIPTS_DIR / script).read_text()
            assert "officer_role_registry_clause" in text, (
                f"{script} lost the registry clause — the R8 soak observes a "
                "dead wire again (W6/§4.3-4)")


def _audit(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(AUDIT)], capture_output=True, text=True, timeout=60,
        env={"CABINET_ROOT": str(root), "PATH": "/usr/bin:/bin:/opt/homebrew/bin"})


class TestParityAudit:
    def test_parity_ok(self, role_tree):
        _role_yml(role_tree, "cos")
        _agent_md(role_tree, "cos")
        r = _audit(role_tree)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "OK" in r.stdout

    def test_consultant_without_agent_file_is_fine(self, role_tree):
        _role_yml(role_tree, "cos")
        _agent_md(role_tree, "cos")
        _role_yml(role_tree, "advisor", officer_type="consultant")
        assert _audit(role_tree).returncode == 0

    def test_fulltime_role_without_agent_file_is_drift(self, role_tree):
        _role_yml(role_tree, "cos")
        _agent_md(role_tree, "cos")
        _role_yml(role_tree, "comms-officer")
        r = _audit(role_tree)
        assert r.returncode == 1
        assert "comms-officer" in r.stdout and "NO .claude/agents" in r.stdout

    def test_split_model_pin_is_drift(self, role_tree):
        _role_yml(role_tree, "cos", model="claude-fable-5")
        _agent_md(role_tree, "cos", model="claude-opus-4-8[1m]")
        r = _audit(role_tree)
        assert r.returncode == 1
        assert "model pin split" in r.stdout

    def test_orphan_agent_file_is_drift(self, role_tree):
        _role_yml(role_tree, "cos")
        _agent_md(role_tree, "cos")
        _agent_md(role_tree, "ghost")
        r = _audit(role_tree)
        assert r.returncode == 1
        assert "ghost" in r.stdout and "NO active registry row" in r.stdout

    def test_no_registry_dir_exits_2(self, tmp_path):
        r = _audit(tmp_path)
        assert r.returncode == 2
        assert "SKIP" in r.stdout

    def test_load_preset_runs_the_audit_warn_only(self):
        text = (_SCRIPTS_DIR / "load-preset.sh").read_text()
        assert "audit-role-parity.sh" in text, (
            "load-preset.sh no longer surfaces registry parity after "
            "populating .claude/agents/")
        assert "do NOT flip CABINET_BOOT_ROLES_ACTIVE=1" in text
