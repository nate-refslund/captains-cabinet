"""AUD-2 (audit #6/#33) — model-fallback-pager functional + wiring contracts.

The pager is the loud half of AUD-2: a Notification hook that stamps
``cabinet:model-fallback:<officer>`` and pages the Chair when the CLI reports
model-fallback engagement. It lives in cabinet/scripts/hooks-src/ (NOT the
schg-locked hooks/ dir) and is wired via .claude/settings.local.json (local
settings layer, gitignored) — so these tests exercise the real script with
transport fakes on PATH, and only validate the local wiring when the file
exists (clean checkouts/CI have no settings.local.json by design).

Run: python3.12 -m pytest cabinet/scripts/tests/test_model_fallback_pager.py -q
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
PAGER = REPO / "cabinet/scripts/hooks-src/model-fallback-pager.sh"
LOCAL_SETTINGS = REPO / ".claude/settings.local.json"

FALLBACK_EVENT = {
    "session_id": "s-1",
    "transcript_path": "/tmp/t.jsonl",
    "cwd": str(REPO),
    "hook_event_name": "Notification",
    "message": "Model unavailable — falling back to claude-opus-4-8 for this session",
}

BENIGN_EVENT = {
    "session_id": "s-2",
    "transcript_path": "/tmp/t.jsonl",
    "cwd": str(REPO),
    "hook_event_name": "Notification",
    "message": "Claude needs your permission to use Bash",
}


def _write_fake(bin_dir: Path, name: str, body: str) -> None:
    p = bin_dir / name
    p.write_text("#!/bin/bash\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _fake_transports(bin_dir: Path, log_dir: Path, nx_result: str = "OK") -> None:
    """Fake redis-cli + curl that append argv to log files and answer success."""
    redis_log = log_dir / "redis.log"
    curl_log = log_dir / "curl.log"
    _write_fake(
        bin_dir,
        "redis-cli",
        f'echo "$@" >> "{redis_log}"\n'
        # NX SET (debounce) answers nx_result; plain SET answers OK.
        f'case "$*" in *" NX "*|*" NX") echo "{nx_result}";; *) echo OK;; esac\n',
    )
    _write_fake(bin_dir, "curl", f'echo "$@" >> "{curl_log}"\necho \'{{"ok":true}}\'\n')


def _run(
    payload,
    bin_dir: Path,
    extra_env: dict | None = None,
    keep_tools: bool = False,
) -> subprocess.CompletedProcess:
    """Run the real pager with the shim dir FIRST on PATH.

    keep_tools=False strips the system dirs that carry redis-cli/curl is not
    possible portably, so instead the shim dir always wins by PATH order; the
    'transports absent' case passes an empty shim dir AND masks the real
    binaries with failing stubs.
    """
    env = os.environ.copy()
    env.pop("CABINET_FALLBACK_PAGE_DEBOUNCE_SECS", None)
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "OFFICER_NAME": "comms-officer",
            "TELEGRAM_COS_TOKEN": "dummy-token",
            "CAPTAIN_TELEGRAM_ID": "424242",
        }
    )
    if extra_env:
        env.update(extra_env)
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        ["bash", str(PAGER)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


class TestPagerFunctional:
    def test_fallback_event_stamps_and_pages(self, tmp_path):
        bin_dir, log_dir = tmp_path / "bin", tmp_path / "log"
        bin_dir.mkdir(), log_dir.mkdir()
        _fake_transports(bin_dir, log_dir)

        proc = _run(FALLBACK_EVENT, bin_dir)
        assert proc.returncode == 0, proc.stderr

        redis_calls = (log_dir / "redis.log").read_text()
        assert "cabinet:model-fallback:comms-officer" in redis_calls
        assert "EX 604800" in redis_calls  # stamp TTL
        assert "page-debounce" in redis_calls  # debounce gate consulted

        curl_calls = (log_dir / "curl.log").read_text()
        assert "sendMessage" in curl_calls
        assert "chat_id=424242" in curl_calls
        assert "Model fallback engaged" in curl_calls
        assert "officer=comms-officer" in curl_calls

    def test_benign_notification_is_silent(self, tmp_path):
        bin_dir, log_dir = tmp_path / "bin", tmp_path / "log"
        bin_dir.mkdir(), log_dir.mkdir()
        _fake_transports(bin_dir, log_dir)

        proc = _run(BENIGN_EVENT, bin_dir)
        assert proc.returncode == 0, proc.stderr
        assert not (log_dir / "redis.log").exists(), "benign event must not touch redis"
        assert not (log_dir / "curl.log").exists(), "benign event must not page"

    def test_debounce_suppresses_page_not_stamp(self, tmp_path):
        bin_dir, log_dir = tmp_path / "bin", tmp_path / "log"
        bin_dir.mkdir(), log_dir.mkdir()
        # NX SET answers empty (key already present) -> page suppressed.
        _fake_transports(bin_dir, log_dir, nx_result="")

        proc = _run(FALLBACK_EVENT, bin_dir)
        assert proc.returncode == 0, proc.stderr
        redis_calls = (log_dir / "redis.log").read_text()
        assert "cabinet:model-fallback:comms-officer" in redis_calls  # stamp still lands
        assert not (log_dir / "curl.log").exists(), "debounced run must not page"
        assert "debounced" in proc.stderr

    def test_debounce_zero_disables_gate(self, tmp_path):
        bin_dir, log_dir = tmp_path / "bin", tmp_path / "log"
        bin_dir.mkdir(), log_dir.mkdir()
        _fake_transports(bin_dir, log_dir, nx_result="")  # NX would suppress...

        proc = _run(
            FALLBACK_EVENT, bin_dir, extra_env={"CABINET_FALLBACK_PAGE_DEBOUNCE_SECS": "0"}
        )
        assert proc.returncode == 0, proc.stderr
        assert (log_dir / "curl.log").exists(), "debounce=0 must page every time"

    def test_empty_stdin_exits_zero(self, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        proc = _run("", bin_dir)
        assert proc.returncode == 0

    def test_transports_missing_still_exits_zero(self, tmp_path):
        """redis-cli/curl unusable -> hook must stay non-blocking (exit 0)."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _write_fake(bin_dir, "redis-cli", "exit 127\n")
        _write_fake(bin_dir, "curl", "exit 127\n")
        proc = _run(FALLBACK_EVENT, bin_dir)
        assert proc.returncode == 0, proc.stderr

    def test_env_file_fallback_resolves_token(self, tmp_path):
        """Unset env creds -> parsed from $CABINET_ROOT/cabinet/.env (names only)."""
        bin_dir, log_dir = tmp_path / "bin", tmp_path / "log"
        bin_dir.mkdir(), log_dir.mkdir()
        _fake_transports(bin_dir, log_dir)
        root = tmp_path / "root"
        (root / "cabinet").mkdir(parents=True)
        (root / "cabinet/.env").write_text(
            "SOMETHING_ELSE=x\nTELEGRAM_COS_TOKEN=envfile-token\nCAPTAIN_TELEGRAM_ID=99\n"
        )

        proc = _run(
            FALLBACK_EVENT,
            bin_dir,
            extra_env={
                "TELEGRAM_COS_TOKEN": "",
                "CAPTAIN_TELEGRAM_ID": "",
                "CABINET_ROOT": str(root),
            },
        )
        assert proc.returncode == 0, proc.stderr
        curl_calls = (log_dir / "curl.log").read_text()
        assert "envfile-token" in curl_calls
        assert "chat_id=99" in curl_calls

    def test_title_only_match_pages(self, tmp_path):
        """Engagement text may arrive in .title rather than .message."""
        bin_dir, log_dir = tmp_path / "bin", tmp_path / "log"
        bin_dir.mkdir(), log_dir.mkdir()
        _fake_transports(bin_dir, log_dir)
        event = dict(BENIGN_EVENT)
        event["message"] = ""
        event["title"] = "Fallback model engaged"
        proc = _run(event, bin_dir)
        assert proc.returncode == 0, proc.stderr
        assert (log_dir / "curl.log").exists()


class TestWiringContracts:
    def test_script_exists_outside_germline_hooks_dir(self):
        assert PAGER.is_file(), "pager script missing"
        assert os.access(PAGER, os.X_OK), "pager must be executable"
        assert "scripts/hooks-src" in str(PAGER), (
            "pager must live in hooks-src/ — cabinet/scripts/hooks/ is schg germline"
        )

    def test_never_uses_eval_on_message(self):
        src = PAGER.read_text()
        assert "eval " not in src, "notification content must never be eval'd"
        assert 'parse_mode="' not in src and "-d parse_mode" not in src, (
            "page is plain text — no parse_mode, no entity interpretation"
        )

    def test_local_settings_wiring_when_present(self):
        """Live-box ratchet: validate wiring iff the local layer exists.

        .claude/settings.local.json is gitignored (Claude Code convention), so
        clean checkouts/CI skip; on the deployed box the wiring must parse and
        point at this script under a Notification hook with a timeout.
        """
        if not LOCAL_SETTINGS.exists():
            pytest.skip("no local settings layer on this checkout (expected in CI)")
        cfg = json.loads(LOCAL_SETTINGS.read_text())
        notif = cfg.get("hooks", {}).get("Notification", [])
        cmds = [
            " ".join([h.get("command", "")] + h.get("args", []))
            for entry in notif
            for h in entry.get("hooks", [])
        ]
        assert any("model-fallback-pager.sh" in c for c in cmds), (
            "settings.local.json exists but does not wire the fallback pager"
        )
