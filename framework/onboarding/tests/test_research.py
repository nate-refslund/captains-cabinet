"""research_repo — read a LOCAL product repo into a profile. No network, no secrets."""
import json

from framework.onboarding import research


def _mk_repo(tmp_path, *, pkg=None, readme=None, claude=None, mcp=None, env=None, remote=None):
    if pkg is not None:
        (tmp_path / "package.json").write_text(json.dumps(pkg))
    if readme is not None:
        (tmp_path / "README.md").write_text(readme)
    if claude is not None:
        d = tmp_path / ".claude"; d.mkdir(exist_ok=True)
        (d / "settings.json").write_text(json.dumps(claude))
    if mcp is not None:
        (tmp_path / ".mcp.json").write_text(json.dumps(mcp))
    if env is not None:
        (tmp_path / ".env").write_text(env)
    if remote is not None:
        g = tmp_path / ".git"; g.mkdir(exist_ok=True)
        (g / "config").write_text(f'[remote "origin"]\n\turl = {remote}\n')
    return tmp_path


def test_reads_name_and_summary(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "acme-shop"},
             readme="# Acme Shop\n\nDemo storefront platform.\n\nmore.")
    p = research.research_repo(str(tmp_path))
    assert p["name"] == "acme-shop"
    assert "demo storefront" in p["summary"].lower()


def test_detects_stack_from_deps(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x",
                            "dependencies": {"next": "15", "@neondatabase/serverless": "1"}})
    p = research.research_repo(str(tmp_path))
    assert "nextjs" in p["stack"] and "neon" in p["stack"]


def test_detects_plugins_from_claude_and_mcp(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x"},
             claude={"enabledPlugins": ["dev-tasks@dev-tasks-marketplace"]},
             mcp={"mcpServers": {"corridor": {}, "neon": {}}})
    p = research.research_repo(str(tmp_path))
    assert "dev-tasks" in p["plugins"]
    assert "corridor" in p["plugins"]


def test_normalizes_git_remote(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x"}, remote="https://github.com/acme-org/x.git")
    assert research.research_repo(str(tmp_path))["repo_url"] == "https://github.com/acme-org/x"


def test_normalizes_ssh_remote(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x"}, remote="git@github.com:acme-org/x.git")
    assert research.research_repo(str(tmp_path))["repo_url"] == "https://github.com/acme-org/x"


def test_never_surfaces_env_secrets(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x"}, env="SECRET_TOKEN=supersecretvalue\n")
    blob = json.dumps(research.research_repo(str(tmp_path)))
    assert "supersecretvalue" not in blob  # .env is never read


def test_has_claude_flag(tmp_path):
    _mk_repo(tmp_path, pkg={"name": "x"})
    assert research.research_repo(str(tmp_path))["has_claude"] is False
    _mk_repo(tmp_path, pkg={"name": "x"}, claude={})
    assert research.research_repo(str(tmp_path))["has_claude"] is True
