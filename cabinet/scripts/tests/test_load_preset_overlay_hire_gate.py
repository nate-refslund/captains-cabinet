"""load-preset.sh: instance/agents/ overlays are HIRED-gated (roster-authz, 2026-07-26).

`.claude/agents/` is the boot-loadable surface. load-preset.sh's own contract
says the single source of truth for hired-vs-scaffold is `cabinet/mcp-scope.yml`
(`agents:` = hired) — and step 1 (preset agents) honours it. Step 2 (instance
overlays) did not: it copied EVERY `instance/agents/*.md` regardless, so
`.claude/agents/` could claim officers the deployment never hired.

That was invisible while the instance generator rostered every lane CEO
unconditionally. Once it stopped (a lane CEO is hired only when the germline
pair authorizes it), the inert role definitions still landed in
`.claude/agents/` and `audit-role-parity.sh` correctly reported "agent file
with NO active registry row" on an otherwise healthy fresh hatch.

Pins: an un-hired overlay is staged and NOT loaded; a hired overlay still
wins; a stale derived copy is removed only when it is provably the loader's own
unmodified output; a hand-edited one is preserved and reported.

Run: python3.12 -m pytest cabinet/scripts/tests/test_load_preset_overlay_hire_gate.py -q
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_LOAD_PRESET = _SCRIPTS_DIR / "load-preset.sh"
_POSTURE_EXAMPLE = _REPO_ROOT / "instance" / "config" / "posture.yml.example"
_LADDER_EXAMPLE = _REPO_ROOT / "instance" / "config" / "trust-ladder.yml.example"

MCP_SCOPE = """\
cabinet: test
agents:
  cos:
    mcps: [telegram]
  hired-lane-ceo:
    mcps: []
"""


def _scratch_root(tmp_path: Path) -> Path:
    """Scratch CABINET_ROOT with a preset, an mcp-scope hiring cos +
    hired-lane-ceo, and TWO instance overlays — one hired, one not."""
    root = tmp_path / "root"
    (root / "framework").mkdir(parents=True)
    (root / "framework" / "constitution-base.md").write_text("# base\n")
    (root / "framework" / "safety-boundaries-base.md").write_text("# base\n")
    preset = root / "presets" / "work"
    (preset / "agents").mkdir(parents=True)
    (preset / "preset.yml").write_text("name: work\n")
    (preset / "agents" / "cos.md").write_text("---\nname: cos\n---\npreset chair\n")
    (root / "cabinet" / "scripts").mkdir(parents=True)
    (root / "cabinet" / "mcp-scope.yml").write_text(MCP_SCOPE)
    # load-preset.sh runs the parity audit only when it is executable AT the
    # scratch root — without this copy the parity assertion below is vacuous.
    shutil.copy(_SCRIPTS_DIR / "audit-role-parity.sh",
                root / "cabinet" / "scripts" / "audit-role-parity.sh")
    (root / "cabinet" / "scripts" / "audit-role-parity.sh").chmod(0o755)
    agents = root / "instance" / "agents"
    agents.mkdir(parents=True)
    (agents / "hired-lane-ceo.md").write_text("---\nname: hired\n---\nhired lane\n")
    (agents / "pending-lane-ceo.md").write_text("---\nname: pending\n---\npending lane\n")
    cfg = root / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "active-preset").write_text("work\n")
    shutil.copy(_POSTURE_EXAMPLE, cfg / "posture.yml.example")
    shutil.copy(_LADDER_EXAMPLE, cfg / "trust-ladder.yml.example")
    # A registry for exactly the HIRED officers. Without this dir
    # audit-role-parity.sh SKIPs (exit 2) and the parity assertion below would
    # pass vacuously — the registry is what makes it a real check.
    active = root / "instance" / "roles" / "active"
    active.mkdir(parents=True)
    (active / "cos.yml").write_text(
        "slug: cos\nstatus: active\nofficer_type: consultant\n")
    (active / "hired-lane-ceo.yml").write_text(
        "slug: hired-lane-ceo\nstatus: active\nofficer_type: consultant\n")
    return root


def _run(root: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CABINET_ROOT"] = str(root)
    env["CABINET_RUNTIME_DIR"] = str(tmp_path / "runtime")
    for k in ("NEON_CONNECTION_STRING", "DATABASE_URL", "CABINET_ID", "CABINET_MODE"):
        env.pop(k, None)
    return subprocess.run(
        ["bash", str(_LOAD_PRESET)],
        cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_unhired_overlay_is_not_loaded(tmp_path):
    """The property: an officer the deployment has not hired must not appear on
    the boot-loadable surface."""
    root = _scratch_root(tmp_path)
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr
    loaded = root / ".claude" / "agents"
    assert not (loaded / "pending-lane-ceo.md").exists(), (
        f"an un-hired overlay was loaded into .claude/agents/:\n{p.stderr}")
    assert "staged, not loaded: pending-lane-ceo.md" in p.stderr


def test_hired_overlay_still_wins(tmp_path):
    """Non-regression: the overlay mechanism itself is untouched for officers
    that ARE hired — that is what step 2 exists for."""
    root = _scratch_root(tmp_path)
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr
    target = root / ".claude" / "agents" / "hired-lane-ceo.md"
    assert target.is_file(), p.stderr
    assert target.read_text() == (root / "instance/agents/hired-lane-ceo.md").read_text()
    assert "Instance agent override: hired-lane-ceo.md" in p.stderr


def test_stale_loader_written_copy_is_removed_when_hire_is_revoked(tmp_path):
    """Hire, load, un-hire, re-load: the derived copy the loader itself wrote
    must not linger claiming an officer that is no longer hired."""
    root = _scratch_root(tmp_path)
    assert _run(root, tmp_path).returncode == 0
    target = root / ".claude" / "agents" / "hired-lane-ceo.md"
    assert target.is_file()

    scope = root / "cabinet" / "mcp-scope.yml"
    scope.write_text(MCP_SCOPE.replace("  hired-lane-ceo:\n    mcps: []\n", ""))
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr
    assert not target.exists(), (
        f"stale derived agent survived a revoked hire:\n{p.stderr}")
    assert "removed the stale derived copy" in p.stderr


def test_hand_edited_copy_is_never_discarded(tmp_path):
    """Fail-safe: only provably loader-written bytes are removed. A file that
    differs from the .gen.sha marker may carry hand edits and is preserved."""
    root = _scratch_root(tmp_path)
    assert _run(root, tmp_path).returncode == 0
    target = root / ".claude" / "agents" / "hired-lane-ceo.md"
    marker = root / ".claude" / "agents" / ".hired-lane-ceo.md.gen.sha"
    assert marker.read_text().strip() == _sha(target)
    target.write_text("---\nname: hired\n---\nHAND EDITED\n")

    scope = root / "cabinet" / "mcp-scope.yml"
    scope.write_text(MCP_SCOPE.replace("  hired-lane-ceo:\n    mcps: []\n", ""))
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr
    assert target.is_file(), "hand-edited file was destroyed"
    assert "HAND EDITED" in target.read_text()
    assert "left in place" in p.stderr


def test_scope_read_failure_never_strips_a_hired_officer(tmp_path):
    """The hire gate added a DESTRUCTIVE path to this step, and
    list_hired_agents returns empty for two very different reasons: "nobody is
    hired" and "I could not read the authorization file". Conflating them turns
    a read failure into a silent de-hiring of everyone — the officer disappears
    from the boot-loadable surface and the loader still reports success.

    Step 1 already refuses to act on that condition (ERROR + skip); this pins
    that step 2 does too. Absence of evidence is not evidence of absence when
    the action is deletion."""
    root = _scratch_root(tmp_path)
    assert _run(root, tmp_path).returncode == 0
    target = root / ".claude" / "agents" / "hired-lane-ceo.md"
    assert target.is_file()

    (root / "cabinet" / "mcp-scope.yml").unlink()
    p = _run(root, tmp_path)
    assert target.is_file(), (
        "a read failure on the authorization file stripped a HIRED officer off "
        f"the boot surface:\n{p.stderr}")
    assert "cannot determine hired agents" in p.stderr, p.stderr


def test_unreadable_agents_section_never_strips_a_hired_officer(tmp_path):
    """Same guard, the other trigger: the file exists but yields no `agents:`
    mapping (truncated, renamed section, edited by hand). Still a read failure,
    still not a licence to delete."""
    root = _scratch_root(tmp_path)
    assert _run(root, tmp_path).returncode == 0
    target = root / ".claude" / "agents" / "hired-lane-ceo.md"
    assert target.is_file()

    (root / "cabinet" / "mcp-scope.yml").write_text("cabinet: test\n")
    p = _run(root, tmp_path)
    assert target.is_file(), (
        f"an empty/unparseable agents: section stripped a hired officer:\n{p.stderr}")
    assert "cannot determine hired agents" in p.stderr, p.stderr


def test_revocation_still_removes_the_stale_copy(tmp_path):
    """Non-regression guard on the guard: a REAL un-hire (the file is readable
    and simply no longer lists the officer) must still take the derived copy
    down. The fix must distinguish 'not hired' from 'cannot tell', not collapse
    both into 'do nothing'."""
    root = _scratch_root(tmp_path)
    assert _run(root, tmp_path).returncode == 0
    target = root / ".claude" / "agents" / "hired-lane-ceo.md"
    assert target.is_file()

    scope = root / "cabinet" / "mcp-scope.yml"
    scope.write_text(MCP_SCOPE.replace("  hired-lane-ceo:\n    mcps: []\n", ""))
    p = _run(root, tmp_path)
    assert not target.exists(), p.stderr
    assert "removed the stale derived copy" in p.stderr


def test_role_parity_is_clean_for_a_pending_lane(tmp_path):
    """The end-to-end consequence: with the un-hired overlay off the loadable
    surface, audit-role-parity.sh has nothing to report about it — a fresh
    hatch that legitimately leaves a lane un-hired is not called DRIFT.
    (The registry in the fixture makes the audit RUN rather than SKIP; without
    it this would pass vacuously.)"""
    root = _scratch_root(tmp_path)
    p = _run(root, tmp_path)
    assert p.returncode == 0, p.stderr
    assert "role-parity: SKIP" not in p.stderr, "the audit skipped — test is vacuous"
    assert "pending-lane-ceo: hired agent file with NO active registry row" \
        not in p.stderr, p.stderr
    assert "Role-registry parity: OK" in p.stderr, p.stderr
