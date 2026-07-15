from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[4]
PARSER = ROOT / "cabinet" / "scripts" / "lib" / "officer-env.py"
SHELL_LIB = ROOT / "cabinet" / "scripts" / "lib" / "officer-env.sh"


def _module():
    spec = importlib.util.spec_from_file_location("officer_env", PARSER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scope(tmp_path: Path, *, cto: str = "notion, telegram") -> Path:
    path = tmp_path / "mcp-scope.yml"
    path.write_text(
        "agents:\n"
        "  cto:\n"
        f"    mcps: [{cto}]\n"
        "  cro:\n"
        "    mcps: [monday, telegram]\n"
        "universal: [library]\n"
    )
    return path


def test_parser_is_allowlist_only_and_never_executes_dotenv(tmp_path: Path):
    marker = tmp_path / "executed"
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "NOTION_API_KEY='notion value'",
                "DASHBOARD_PASSWORD=captain-secret",
                "CABINET_SESSION_SIGNING_SECRET=session-secret",
                "CABINET_VERDICT_SIGNING_SECRET=verdict-secret",
                "TELEGRAM_WEBHOOK_SECRET=webhook-secret",
                "CABINET_CAPTAIN_CHANNEL=1",
                "TELEGRAM_CTO_TOKEN=cto-token",
                "TELEGRAM_CRO_TOKEN=cro-token",
                f"UNKNOWN='$(touch {marker})'",
            ]
        )
    )
    rendered = _module().render(env, "cto", scope_file=_scope(tmp_path))
    assert "NOTION_API_KEY" in rendered
    assert "TELEGRAM_CTO_TOKEN" in rendered
    assert "DASHBOARD_PASSWORD" not in rendered
    assert "SIGNING_SECRET" not in rendered
    assert "TELEGRAM_WEBHOOK_SECRET" not in rendered
    assert "CABINET_CAPTAIN_CHANNEL" not in rendered
    assert "TELEGRAM_CRO_TOKEN" not in rendered
    assert "UNKNOWN" not in rendered
    assert not marker.exists()


def test_clean_prefix_drops_inherited_authority_and_raw_role_tokens(tmp_path: Path):
    root = tmp_path / "root"
    (root / "cabinet").mkdir(parents=True)
    _scope_file = _scope(tmp_path)
    (root / "cabinet/mcp-scope.yml").write_text(_scope_file.read_text())
    env = tmp_path / ".env"
    env.write_text("NOTION_API_KEY=n-key\nTELEGRAM_CTO_TOKEN=t-key\n")
    command = f"""
      set -e
      source {SHELL_LIB!s}
      export CABINET_ROOT={root!s}
      export DASHBOARD_PASSWORD=do-not-pass
      export CABINET_VERDICT_SIGNING_SECRET=do-not-pass-either
      export TELEGRAM_WEBHOOK_SECRET=do-not-pass-webhook
      officer_env_scrub_authority
      officer_env_load_file {env!s} cto
      export OFFICER_NAME=cto TELEGRAM_BOT_TOKEN="$TELEGRAM_CTO_TOKEN"
      prefix="$(officer_env_command_prefix)"
      eval "$prefix /usr/bin/env"
    """
    result = subprocess.run(
        ["/bin/bash", "-c", command], text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr
    child = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )
    assert child["NOTION_API_KEY"] == "n-key"
    assert child["TELEGRAM_BOT_TOKEN"] == "t-key"
    assert "TELEGRAM_CTO_TOKEN" not in child
    assert "DASHBOARD_PASSWORD" not in child
    assert "CABINET_VERDICT_SIGNING_SECRET" not in child
    assert "TELEGRAM_WEBHOOK_SECRET" not in child


def test_dotenv_shell_syntax_is_data_not_code(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("NOTION_API_KEY='$(printf compromised)'\n")
    rendered = _module().render(env, "cto", scope_file=_scope(tmp_path))
    assert "$(printf compromised)" in rendered
    result = subprocess.run(
        ["/bin/bash", "-c", f"{rendered}\nprintf '%s' \"$NOTION_API_KEY\""],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.stdout == "$(printf compromised)"


def test_credentials_follow_declared_mcp_scope(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "NOTION_API_KEY=notion\n"
        "VERCEL_TOKEN=vercel\n"
        "MAKE_MCP_TOKEN=make\n"
        "MONDAY_API_TOKEN=monday\n"
        "NEON_CONNECTION_STRING=postgresql://library\n"
        "TELEGRAM_CTO_TOKEN=telegram\n"
    )
    rendered = _module().render(env, "cto", scope_file=_scope(tmp_path))
    assert "NOTION_API_KEY" in rendered
    assert "NEON_CONNECTION_STRING" in rendered  # universal library
    assert "TELEGRAM_CTO_TOKEN" in rendered
    assert "VERCEL_TOKEN" not in rendered
    assert "MAKE_MCP_TOKEN" not in rendered
    assert "MONDAY_API_TOKEN" not in rendered


def test_cua_backend_credentials_and_launcher_telegram_fallbacks_project(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "CUA_MODEL_BACKEND=anthropic\n"
        "ANTHROPIC_API_KEY=anthropic\n"
        "OPENAI_API_KEY=openai\n"
        "GOOGLE_API_KEY=google\n"
        "TELEGRAM_BOT_TOKEN=bare-bot\n"
        "TELEGRAM_CEO_TOKEN=bare-ceo\n"
    )
    rendered = _module().render(
        env,
        "cto",
        scope_file=_scope(tmp_path, cto="cua, telegram"),
    )
    for name in (
        "CUA_MODEL_BACKEND",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CEO_TOKEN",
    ):
        assert f"export {name}=" in rendered


def test_cua_and_bare_telegram_credentials_stay_scoped(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "ANTHROPIC_API_KEY=anthropic\n"
        "TELEGRAM_BOT_TOKEN=bare-bot\n"
        "TELEGRAM_CEO_TOKEN=bare-ceo\n"
    )
    rendered = _module().render(
        env,
        "cto",
        scope_file=_scope(tmp_path, cto="notion"),
    )
    assert "ANTHROPIC_API_KEY" not in rendered
    assert "TELEGRAM_BOT_TOKEN" not in rendered
    assert "TELEGRAM_CEO_TOKEN" not in rendered


def test_observe_only_effective_scope_scrubs_every_remote_mcp_credential(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text(
        "CUA_MODEL_BACKEND=anthropic\n"
        "ANTHROPIC_API_KEY=anthropic\n"
        "OPENAI_API_KEY=openai\n"
        "GOOGLE_API_KEY=google\n"
        "MAPBOX_TOKEN=mapbox\n"
        "NOTION_API_KEY=notion\n"
        "VERCEL_TOKEN=vercel\n"
        "MAKE_MCP_TOKEN=make\n"
        "NEON_API_KEY=neon\n"
        "BRAVE_SEARCH_API_KEY=brave\n"
        "EXA_API_KEY=exa\n"
        "SCREENPIPE_API_AUTH_KEY=brain\n"
        "TELEGRAM_BOT_TOKEN=bot\n"
    )
    rendered = _module().render(
        env,
        "cto",
        scope_file=_scope(
            tmp_path,
            cto=("cua, cua-driver, telegram, notion, vercel, make, neon, "
                 "brave-search, exa, brain"),
        ),
        observe_only=True,
    )
    for name in (
        "CUA_MODEL_BACKEND",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "MAPBOX_TOKEN",
        "NOTION_API_KEY",
        "VERCEL_TOKEN",
        "MAKE_MCP_TOKEN",
        "NEON_API_KEY",
        "BRAVE_SEARCH_API_KEY",
        "EXA_API_KEY",
        "SCREENPIPE_API_AUTH_KEY",
    ):
        assert name not in rendered
    assert "TELEGRAM_BOT_TOKEN" in rendered


def test_observe_child_gets_one_resolved_token_and_no_remote_credentials(tmp_path: Path):
    root = tmp_path / "root"
    (root / "cabinet").mkdir(parents=True)
    (root / "cabinet/mcp-scope.yml").write_text(
        _scope(tmp_path, cto="telegram, neon, vercel, notion").read_text())
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_CTO_TOKEN=role-token\n"
        "TELEGRAM_BOT_TOKEN=bare-token\n"
        "NOTION_API_KEY=notion\n"
        "VERCEL_TOKEN=vercel\n"
        "NEON_API_KEY=neon\n"
    )
    command = f"""
      set -e
      source {SHELL_LIB!s}
      export CABINET_ROOT={root!s} CABINET_OBSERVE_ONLY=1
      officer_env_load_file {env!s} cto
      export TELEGRAM_BOT_TOKEN="$TELEGRAM_CTO_TOKEN"
      prefix="$(officer_env_command_prefix)"
      eval "$prefix /usr/bin/env"
    """
    result = subprocess.run(
        ["/bin/bash", "-c", command], text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    child = dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    assert child["TELEGRAM_BOT_TOKEN"] == "role-token"
    assert "TELEGRAM_CTO_TOKEN" not in child
    for name in ("NOTION_API_KEY", "VERCEL_TOKEN", "NEON_API_KEY"):
        assert name not in child


def test_unlisted_officer_fails_closed(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("NOTION_API_KEY=notion\n")
    with pytest.raises(ValueError, match="has no agents entry"):
        _module().render(env, "ghost", scope_file=_scope(tmp_path))


def test_one_shot_launcher_keeps_secret_out_of_argv_and_unlinks(tmp_path: Path):
    secret = "credential-that-must-not-enter-tmux-history"
    command = f"printf '%s' {secret}"
    create = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f'source {SHELL_LIB!s}; officer_env_write_one_shot_launcher "$1" "$2"',
            "launcher-test",
            str(tmp_path / "launch"),
            command,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert create.returncode == 0, create.stderr
    launcher = Path(create.stdout.strip())
    assert launcher.is_file()
    assert stat.S_IMODE(launcher.stat().st_mode) == 0o700
    # tmux receives only `/bin/bash <path>`; the value stays in the transient
    # file and the file disappears before the officer command runs.
    argv = [
        "/usr/bin/env",
        "-i",
        f"HOME={os.environ.get('HOME', '')}",
        f"PATH={os.environ.get('PATH', '')}",
        "/bin/bash",
        "--noprofile",
        "--norc",
        str(launcher),
    ]
    assert secret not in " ".join(argv)
    run = subprocess.run(argv, text=True, capture_output=True, check=False)
    assert run.returncode == 0, run.stderr
    assert run.stdout == secret
    assert not launcher.exists()
