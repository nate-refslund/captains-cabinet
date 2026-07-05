"""install-extensions.sh × validate-extension.sh — the §6.4 loader wiring
(axes spec docs/plans/cabinet-axes-spec-2026-07-05.md §6.4,
.claude/rules/axes-contract.md §2; the AX-8 fix).

Proves the captain-instance guarantee MECHANICALLY, end-to-end through the
real installer script: every declared extension with a local directory runs
through cabinet/scripts/validate-extension.sh BEFORE it is installed or
rendered; failures are SKIPPED fail-closed (a failing mcp never lands in
extra-mcps.json; a failing local plugin never reaches `claude plugin
install`) and file a kind=decision need; dir-less declarations install
exactly as before (back-compat — e.g. the live brain MCP). The gate script
itself is resolved from the installer's own directory, never from
CABINET_ROOT, so a re-pointed root cannot swap in a forged gate.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_INSTALLER = _REPO_ROOT / "cabinet" / "scripts" / "install-extensions.sh"
_SKILL = _REPO_ROOT / ".claude" / "skills" / "extend-cabinet" / "SKILL.md"


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _valid_ext(base: Path, name: str = "goodext", kind: str = "mcp") -> Path:
    """A minimal extension dir that passes all three validate-extension
    gates (manifest.json so the fixture needs no yaml dependency)."""
    ext = base / name
    _write(ext / "server.py", (
        "def run(resolved_axes):\n"
        "    # extensions RECEIVE resolved axis values — no axis reads\n"
        "    return 0\n"
    ))
    _write(ext / "manifest.json", json.dumps({
        "name": name,
        "version": "0.1.0",
        "kind": kind,
        "action_types": [],
        "risk_classes": [],
        "undo_contract": "none",
        "entrypoints": {"serve": "server.py"},
    }))
    return ext


def _axis_branching_ext(base: Path, name: str = "badext",
                        kind: str = "mcp") -> Path:
    """Valid manifest but an axis-branching module — the linter must refuse."""
    ext = _valid_ext(base, name, kind)
    _write(ext / "evil.py", (
        "def pick(posture):\n"
        "    if posture == 'sovereign':\n"
        "        return 'wide'\n"
        "    return 'narrow'\n"
    ))
    return ext


def _declare(root: Path, doc: dict) -> None:
    # JSON is a YAML subset — parses under the installer's yaml.safe_load.
    _write(root / "instance" / "config" / "extensions.yml", json.dumps(doc))


def _run_installer(root: Path, extra_env: "dict | None" = None):
    env = dict(os.environ)
    env.pop("CABINET_EXTENSIONS_FILE", None)
    env.update({
        "CABINET_ROOT": str(root),
        # Let the skip path actually file needs, into the tmp root's ledger —
        # and keep the need_filed event out of the real event log.
        "CABINET_NEEDS_WIRED": "1",
        "CABINET_EVENT_LOG_DIR": str(root / "events"),
        "CABINET_FRAMEWORK_STORE_MIRROR": "0",
    })
    env.update(extra_env or {})
    return subprocess.run(
        ["bash", str(_INSTALLER)],
        capture_output=True, text=True, timeout=300, env=env,
    )


def _servers(root: Path) -> dict:
    return json.loads(
        (root / "instance" / "config" / "extra-mcps.json").read_text()
    )["mcpServers"]


def _needs_rows(root: Path) -> "list[dict]":
    ledger = root / "shared" / "interfaces" / "needs-ledger.jsonl"
    if not ledger.exists():
        return []
    return [json.loads(line)
            for line in ledger.read_text().splitlines() if line.strip()]


def _claude_shim(base: Path) -> "tuple[Path, Path]":
    """A fake `claude` CLI on PATH that logs every invocation — proves what
    the installer did (or refused to do) without a real plugin install."""
    bindir = base / "bin"
    log = base / "claude-calls.log"
    shim = _write(bindir / "claude",
                  "#!/bin/bash\necho \"$@\" >> '%s'\nexit 0\n" % log)
    shim.chmod(0o755)
    return bindir, log


# ---------------------------------------------------------------------------
# MCP lane — gate before render
# ---------------------------------------------------------------------------

class TestMcpGate:
    def test_valid_dir_mcp_renders(self, tmp_path):
        ext = _valid_ext(tmp_path)
        root = tmp_path / "cab"
        _declare(root, {"mcps": [
            {"name": "goodext", "command": "python3",
             "args": [str(ext / "server.py")], "dir": str(ext)},
        ]})
        r = _run_installer(root)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "passed the validate-extension gate" in r.stdout
        assert "goodext" in _servers(root)

    def test_axis_branching_mcp_skipped_and_need_filed(self, tmp_path):
        ext = _axis_branching_ext(tmp_path)
        root = tmp_path / "cab"
        _declare(root, {"mcps": [
            {"name": "badext", "command": "python3",
             "args": [str(ext / "server.py")], "dir": str(ext)},
        ]})
        r = _run_installer(root)
        assert r.returncode == 0, r.stdout + r.stderr  # skip, never abort
        assert "FAILED the validate-extension gate" in r.stdout
        assert "badext" not in _servers(root)  # fail-closed: never bound
        rows = _needs_rows(root)
        assert any(row.get("action_type") == "extension_manifest"
                   and "badext" in (row.get("why") or "")
                   for row in rows), rows

    def test_missing_manifest_mcp_skipped(self, tmp_path):
        ext = _valid_ext(tmp_path, "nomanifest")
        (ext / "manifest.json").unlink()
        root = tmp_path / "cab"
        _declare(root, {"mcps": [
            {"name": "nomanifest", "command": "python3",
             "args": ["x.py"], "dir": str(ext)},
        ]})
        r = _run_installer(root)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "nomanifest" not in _servers(root)

    def test_nonexistent_dir_mcp_skipped_and_need_filed(self, tmp_path):
        root = tmp_path / "cab"
        _declare(root, {"mcps": [
            {"name": "ghost", "command": "python3", "args": ["x.py"],
             "dir": str(tmp_path / "does-not-exist")},
        ]})
        r = _run_installer(root)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "ghost" not in _servers(root)
        assert any("ghost" in (row.get("why") or "")
                   for row in _needs_rows(root))

    def test_dirless_mcp_renders_as_before(self, tmp_path):
        """Back-compat: an mcp with no `dir:` (remote / opaque command) has
        nothing to scan locally and renders exactly as pre-gate."""
        root = tmp_path / "cab"
        _declare(root, {"mcps": [
            {"name": "brain", "command": "python3.12",
             "args": ["/some/server.py"]},
        ]})
        r = _run_installer(root)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "brain" in _servers(root)
        assert _needs_rows(root) == []

    def test_mixed_declaration_only_failing_mcp_excluded(self, tmp_path):
        good = _valid_ext(tmp_path, "goodext")
        bad = _axis_branching_ext(tmp_path, "badext")
        root = tmp_path / "cab"
        _declare(root, {"mcps": [
            {"name": "goodext", "command": "python3", "args": ["a.py"],
             "dir": str(good)},
            {"name": "badext", "command": "python3", "args": ["b.py"],
             "dir": str(bad)},
            {"name": "brain", "command": "python3.12", "args": ["c.py"]},
        ]})
        r = _run_installer(root)
        assert r.returncode == 0, r.stdout + r.stderr
        servers = _servers(root)
        assert set(servers) == {"goodext", "brain"}


# ---------------------------------------------------------------------------
# Plugin lane — gate before any `claude plugin ...` command
# ---------------------------------------------------------------------------

class TestPluginGate:
    def test_failing_local_plugin_never_reaches_claude(self, tmp_path):
        ext = _axis_branching_ext(tmp_path, "badplug", kind="skill")
        bindir, log = _claude_shim(tmp_path)
        root = tmp_path / "cab"
        _declare(root, {"plugins": [
            {"name": "badplug", "source": str(ext), "optional": False},
        ]})
        r = _run_installer(
            root, {"PATH": "%s:%s" % (bindir, os.environ["PATH"])})
        assert r.returncode == 0, r.stdout + r.stderr  # skipped, not aborted
        assert "FAILED the validate-extension gate" in r.stdout
        calls = log.read_text() if log.exists() else ""
        assert "plugin install" not in calls
        assert "marketplace add" not in calls
        assert any("badplug" in (row.get("why") or "")
                   for row in _needs_rows(root))

    def test_passing_local_plugin_reaches_claude_install(self, tmp_path):
        ext = _valid_ext(tmp_path, "goodplug", kind="skill")
        bindir, log = _claude_shim(tmp_path)
        root = tmp_path / "cab"
        _declare(root, {"plugins": [
            {"name": "goodplug", "source": str(ext), "optional": False},
        ]})
        r = _run_installer(
            root, {"PATH": "%s:%s" % (bindir, os.environ["PATH"])})
        assert r.returncode == 0, r.stdout + r.stderr
        assert "passed the validate-extension gate" in r.stdout
        calls = log.read_text()
        assert "plugin marketplace add %s" % ext in calls
        assert "plugin install goodplug" in calls


# ---------------------------------------------------------------------------
# The routing claims of axes-contract.md §2 — pinned mechanically
# ---------------------------------------------------------------------------

class TestRoutingClaims:
    def test_extend_cabinet_skill_routes_through_the_gate(self):
        """axes-contract.md §2: 'The extend-cabinet skill routes every
        captain through it' — the skill must name the gate + the manifest
        schema as a mandatory step."""
        text = _SKILL.read_text()
        assert "validate-extension.sh" in text
        assert "extension-manifest.schema.json" in text

    def test_installer_wires_the_gate(self):
        """axes-contract.md §2: 'loaders skip manifest-invalid extensions
        fail-closed and file a need' — the installer must invoke the gate
        script and the needs filing seam."""
        text = _INSTALLER.read_text()
        assert "validate-extension.sh" in text
        assert "gate_extension" in text
        assert "file_extension_need" in text
        assert "needs.file_need" in text
