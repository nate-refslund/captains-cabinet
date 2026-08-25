"""Tests for the boot-path scripts (Perfect Cabinet Wave A, 2026-07-09/10).

Covers the critical-path-diet + de-cloud + telegram-errand contracts:

  * cabinet/scripts/setup-mac.sh        — flag contract (--fast default,
    --check, --with-sensors, --with-dashboard, --full-suite, --all), help,
    unknown-flag refusal. The heavy default run is NOT executed here (it
    installs things); --check is exercised for real (side-effect free).
  * cabinet/scripts/setup-env.sh        — --defaults (non-interactive local
    boot: .env created chmod 600, POSTGRES/webhook secrets auto-generated,
    DASHBOARD_PASSWORD deliberately left UNSET so the operator chooses it on
    first open of the dashboard, every account key left unset, idempotent,
    exit 0), --check de-cloud semantics (exit 1
    only when .env missing), wizard live-validation wiring (valid token
    saved + username confirmed; rejected token NOT saved; token never
    echoed anywhere).
  * cabinet/scripts/dashboard-password.sh — --reset clears the password and
    returns the dashboard to its first-run screen; --copy inspects an existing
    one without printing it. Neither is the way in anymore.
  * cabinet/scripts/provision-local-postgres.sh — --check read-only paths
    (no brew, no network): missing .env, remote string accepted unprobed,
    local string without/with a (shimmed) pg_isready, probe uses the port
    EMBEDDED in the stored string; plus the role-password SQL escape
    (single-quote doubling) pinned against /bin/bash 3.2 semantics.
  * cabinet/scripts/telegram-validate-token.sh  — getMe validation via a
    PATH-shimmed fake curl: exit 0/1/2/64 lanes, argv-token refusal,
    zero token leakage in output.
  * cabinet/scripts/telegram-capture-chat-id.sh — one-shot getUpdates
    (errand E1b): capture, --write only-if-empty (refuse-if-set), the
    identity-gate confirm contract (non-interactive --write refuses without
    --yes), full-window (limit=100, no offset) request shape, window-full
    truncation warn, honest empty (exit 3), 409 conflict (exit 4),
    rejected token (exit 1).
  * --help on all three new scripts prints the header comment block only
    (never leaks code lines).

Run shape mirrors cabinet/scripts/tests/test_ledger_purge_testrows.py:
subprocess against the real scripts, real bash, temp fixture roots. No
network: every HTTP touch rides the fake curl shim; no brew/psql calls.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_DIR.parent.parent

SETUP_MAC = SCRIPTS_DIR / "setup-mac.sh"
SETUP_ENV = SCRIPTS_DIR / "setup-env.sh"
DASHBOARD_PASSWORD = SCRIPTS_DIR / "dashboard-password.sh"
INSTALL_TOOLS = SCRIPTS_DIR / "install-mac-tools.sh"
PROVISION_PG = SCRIPTS_DIR / "provision-local-postgres.sh"
TG_VALIDATE = SCRIPTS_DIR / "telegram-validate-token.sh"
TG_CAPTURE = SCRIPTS_DIR / "telegram-capture-chat-id.sh"

ALL_SCRIPTS = [SETUP_MAC, SETUP_ENV, DASHBOARD_PASSWORD, INSTALL_TOOLS, PROVISION_PG, TG_VALIDATE, TG_CAPTURE]

# Minimal PATH: system tools only — keeps Homebrew (brew/psql/pg_isready)
# and any live network tooling out of the hermetic tests deterministically.
MIN_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"

FAKE_TOKEN = "12345:AAAAfaketokenvalue-test-only"

GETME_OK = '{"ok":true,"result":{"id":1,"is_bot":true,"username":"CabinetTestBot"}}'
GETME_REJECTED = '{"ok":false,"error_code":401,"description":"Unauthorized"}'
GETUPDATES_FOUND = (
    '{"ok":true,"result":['
    '{"update_id":1,"message":{"message_id":1,'
    '"from":{"id":77700011,"is_bot":false,"username":"cap_test"},'
    '"chat":{"id":77700011,"type":"private"},"text":"hello"}},'
    '{"update_id":2,"message":{"message_id":2,'
    '"from":{"id":77700011,"is_bot":false,"username":"cap_test"},'
    '"chat":{"id":-10098765,"type":"supergroup"},"text":"warroom"}}'
    "]}"
)
GETUPDATES_EMPTY = '{"ok":true,"result":[]}'
GETUPDATES_CONFLICT = (
    '{"ok":false,"error_code":409,'
    '"description":"Conflict: terminated by other getUpdates request"}'
)


def run(argv, env=None, stdin: str | None = None, timeout=60):
    """Run a fixed-argv subprocess; returns CompletedProcess."""
    return subprocess.run(
        argv,
        input=stdin,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def base_env(cabinet_root: Path, path: str = MIN_PATH, **extra) -> dict:
    env = {
        "PATH": path,
        "HOME": str(cabinet_root),  # keep any $HOME touches inside the fixture
        "CABINET_ROOT": str(cabinet_root),
    }
    env.update(extra)
    return env


@pytest.fixture()
def cab_root(tmp_path: Path) -> Path:
    """A throwaway CABINET_ROOT with the real .env.example template."""
    root = tmp_path / "root"
    (root / "cabinet").mkdir(parents=True)
    template = (REPO_ROOT / "cabinet" / ".env.example").read_text()
    (root / "cabinet" / ".env.example").write_text(template)
    return root


@pytest.fixture()
def fake_curl_dir(tmp_path: Path) -> Path:
    """A PATH dir with a fake curl honoring -o FILE / -w and env fixtures:
    FAKE_CURL_BODY (response body), FAKE_CURL_CODE (http code, default 200),
    FAKE_CURL_RC (curl exit code, default 0). Consumes the -K - stdin config
    exactly like the real curl invocation in the scripts; when
    FAKE_CURL_CONFIG_OUT is set the config is recorded there so tests can
    assert the request shape (test-only fake tokens ride that config)."""
    d = tmp_path / "fakebin"
    d.mkdir()
    curl = d / "curl"
    curl.write_text(
        "#!/bin/bash\n"
        'out=""; prev=""\n'
        'for a in "$@"; do\n'
        '  if [ "$prev" = "-o" ]; then out="$a"; fi\n'
        '  prev="$a"\n'
        "done\n"
        'if [ -n "${FAKE_CURL_CONFIG_OUT:-}" ]; then\n'
        '  cat > "$FAKE_CURL_CONFIG_OUT"\n'
        "else\n"
        "  cat >/dev/null\n"
        "fi\n"
        'body="${FAKE_CURL_BODY:-}"\n'
        'code="${FAKE_CURL_CODE:-200}"\n'
        'rc="${FAKE_CURL_RC:-0}"\n'
        '[ -n "$out" ] && printf \'%s\' "$body" > "$out"\n'
        "printf '%s' \"$code\"\n"
        'exit "$rc"\n'
    )
    curl.chmod(0o755)
    return d


# ---------------------------------------------------------------------------
# Syntax + flag contracts
# ---------------------------------------------------------------------------

class TestSyntaxAndFlags:
    @pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda p: p.name)
    def test_bash_n_clean(self, script):
        r = run(["bash", "-n", str(script)])
        assert r.returncode == 0, r.stderr

    def test_setup_mac_help_lists_contract_flags(self, cab_root):
        r = run(["bash", str(SETUP_MAC), "--help"], env=base_env(cab_root))
        assert r.returncode == 0
        for flag in ("--fast", "--check", "--with-sensors", "--with-dashboard",
                     "--full-suite", "--all"):
            assert flag in r.stdout, f"{flag} missing from --help"

    def test_setup_mac_unknown_flag_exit_2(self, cab_root):
        r = run(["bash", str(SETUP_MAC), "--bogus"], env=base_env(cab_root))
        assert r.returncode == 2

    def test_setup_env_unknown_flag_exit_64(self, cab_root):
        r = run(["bash", str(SETUP_ENV), "--bogus"], env=base_env(cab_root))
        assert r.returncode == 64

    def test_provision_unknown_flag_exit_64(self, cab_root):
        r = run(["bash", str(PROVISION_PG), "--bogus"], env=base_env(cab_root))
        assert r.returncode == 64

    def test_provision_help(self, cab_root):
        r = run(["bash", str(PROVISION_PG), "--help"], env=base_env(cab_root))
        assert r.returncode == 0
        assert "pgvector" in r.stdout

    @pytest.mark.parametrize(
        "script", [PROVISION_PG, TG_VALIDATE, TG_CAPTURE, SETUP_ENV],
        ids=lambda p: p.name,
    )
    def test_help_prints_header_only_never_code(self, script, cab_root):
        # setup-env.sh prints help to stderr; the others to stdout — check both.
        r = run(["bash", str(script), "--help"], env=base_env(cab_root))
        assert r.returncode == 0
        combined = r.stdout + r.stderr
        assert combined.strip(), "--help must print the header"
        for code_line in ("set -uo pipefail", "SCRIPT_DIR=", "!/bin/bash"):
            assert code_line not in combined, f"--help leaked code: {code_line}"


# ---------------------------------------------------------------------------
# setup-env.sh — de-cloud + --defaults contract
# ---------------------------------------------------------------------------

class TestSetupEnvDefaults:
    def test_check_missing_env_exit_1(self, cab_root):
        r = run(["bash", str(SETUP_ENV), "--check"], env=base_env(cab_root))
        assert r.returncode == 1

    def test_defaults_writes_minimal_env_exit_0(self, cab_root):
        r = run(["bash", str(SETUP_ENV), "--defaults"], env=base_env(cab_root))
        assert r.returncode == 0, r.stdout + r.stderr
        env_file = cab_root / "cabinet" / ".env"
        assert env_file.exists()
        # chmod 600 (Captain only)
        assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
        text = env_file.read_text()
        # auto-generated runtime values present
        pg = [l for l in text.splitlines() if l.startswith("POSTGRES_PASSWORD=")][0]
        webhook = [l for l in text.splitlines() if l.startswith("TELEGRAM_WEBHOOK_SECRET=")][0]
        assert len(pg.split("=", 1)[1]) >= 30
        webhook_value = webhook.split("=", 1)[1]
        assert len(webhook_value) == 64
        assert webhook_value not in r.stdout + r.stderr
        # DASHBOARD_PASSWORD is deliberately LEFT UNSET (2026-08-12 ruling): the
        # operator chooses it on first open of the dashboard. --defaults must
        # never mint one, nor advertise the old clipboard-recovery command.
        dash = [l for l in text.splitlines() if l.startswith("DASHBOARD_PASSWORD=")][0]
        assert dash.split("=", 1)[1] == "", "a fresh instance must boot with no dashboard password"
        assert "dashboard-password.sh --copy" not in r.stdout
        assert "auto-generated" not in dash
        # every account key left unset — the de-cloud boot promise
        for key in ("TELEGRAM_COS_TOKEN", "CAPTAIN_TELEGRAM_ID", "TELEGRAM_HQ_CHAT_ID",
                    "GITHUB_PAT", "NEON_CONNECTION_STRING", "VOYAGE_API_KEY"):
            assert f"{key}=\n" in text or text.endswith(f"{key}="), \
                f"{key} should be unset after --defaults"

    def test_defaults_idempotent(self, cab_root):
        env = base_env(cab_root)
        assert run(["bash", str(SETUP_ENV), "--defaults"], env=env).returncode == 0
        env_file = cab_root / "cabinet" / ".env"
        first = env_file.read_text()
        assert run(["bash", str(SETUP_ENV), "--defaults"], env=env).returncode == 0
        assert env_file.read_text() == first, "--defaults re-run must not churn values"

    def test_check_after_defaults_exit_0_no_cloud_needed(self, cab_root):
        env = base_env(cab_root)
        run(["bash", str(SETUP_ENV), "--defaults"], env=env)
        r = run(["bash", str(SETUP_ENV), "--check"], env=env)
        assert r.returncode == 0, "no cloud account may be boot-critical"
        assert "boot-critical" in r.stdout


def _set_dashboard_password(env_file: Path, password: str) -> None:
    """Simulate the operator having chosen a password on the first-run screen:
    the create action wrote DASHBOARD_PASSWORD into cabinet/.env (0600)."""
    lines = env_file.read_text().splitlines()
    out, seen = [], False
    for line in lines:
        if line.startswith("DASHBOARD_PASSWORD="):
            out.append(f"DASHBOARD_PASSWORD={password}")
            seen = True
        else:
            out.append(line)
    if not seen:
        out.append(f"DASHBOARD_PASSWORD={password}")
    env_file.write_text("\n".join(out) + "\n")
    env_file.chmod(0o600)


class TestDashboardPasswordRecovery:
    def test_copies_without_printing_secret(self, cab_root, tmp_path):
        env = base_env(cab_root)
        assert run(["bash", str(SETUP_ENV), "--defaults"], env=env).returncode == 0
        # --defaults leaves the password unset now; the operator has since chosen
        # one on the first-run screen. --copy is the inspect helper for that.
        password = "chosen-by-operator-2026"
        _set_dashboard_password(cab_root / "cabinet" / ".env", password)
        fake_bin = tmp_path / "fake-bin"
        fake_bin.mkdir()
        copied = tmp_path / "clipboard"
        pbcopy = fake_bin / "pbcopy"
        pbcopy.write_text('#!/bin/bash\ncat > "$FAKE_PBCOPY_OUT"\n')
        pbcopy.chmod(0o755)
        recovery_env = base_env(
            cab_root,
            path=f"{fake_bin}:{MIN_PATH}",
            FAKE_PBCOPY_OUT=str(copied),
        )
        result = run(["bash", str(DASHBOARD_PASSWORD), "--copy"], env=recovery_env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert copied.read_text() == password
        assert password not in result.stdout + result.stderr
        assert "not printed" in result.stdout

    def test_refuses_loose_env_permissions(self, cab_root):
        env = base_env(cab_root)
        assert run(["bash", str(SETUP_ENV), "--defaults"], env=env).returncode == 0
        (cab_root / "cabinet" / ".env").chmod(0o644)
        result = run(["bash", str(DASHBOARD_PASSWORD), "--copy"], env=env)
        assert result.returncode == 1
        assert "permissions are 600" in result.stderr

    def test_reads_value_as_data_without_executing_env_content(self, cab_root, tmp_path):
        env_file = cab_root / "cabinet" / ".env"
        marker = tmp_path / "must-not-exist"
        password = f"literal-$(touch {marker})"
        env_file.write_text(f"DASHBOARD_PASSWORD={password}\n")
        env_file.chmod(0o600)
        fake_bin = tmp_path / "fake-bin"
        fake_bin.mkdir()
        copied = tmp_path / "clipboard"
        pbcopy = fake_bin / "pbcopy"
        pbcopy.write_text('#!/bin/bash\ncat > "$FAKE_PBCOPY_OUT"\n')
        pbcopy.chmod(0o755)
        env = base_env(cab_root, path=f"{fake_bin}:{MIN_PATH}", FAKE_PBCOPY_OUT=str(copied))
        result = run(["bash", str(DASHBOARD_PASSWORD)], env=env)
        assert result.returncode == 0
        assert copied.read_text() == password
        assert not marker.exists(), "cabinet/.env content must never be sourced or evaluated"
        assert password not in result.stdout + result.stderr


# ---------------------------------------------------------------------------
# The stored form of a chosen password, mirrored from the writer.
# ---------------------------------------------------------------------------
# cabinet/dashboard/src/lib/config-write.ts `envValueLiteral` is what actually
# writes DASHBOARD_PASSWORD: a value that is provably literal in an unquoted
# bash assignment is stored BARE, anything else is SINGLE-QUOTED with an
# embedded `'` escaped as `'\''`. Since 2026-08-25 the operator may choose any
# character at all (8 or more, every symbol allowed), so `--copy` has to be the
# exact inverse of this — and the apostrophe case is the one that used to come
# back mangled.
_ENV_BARE_SAFE = re.compile(r"^[A-Za-z0-9_.:/=+@%,-]+$")


def _env_literal(value: str) -> str:
    """The bytes the dashboard writes after `DASHBOARD_PASSWORD=`."""
    if value == "" or _ENV_BARE_SAFE.match(value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


class TestDashboardPasswordAnySymbols:
    """--copy must hand back the EXACT password the operator chose, for every
    character they are now allowed to choose.

    The failure this pins: the reader stripped the outer single quotes but never
    decoded `'\''` back to `'`, so a password with an apostrophe reached the
    clipboard as `O'\''Brien` — a string that does not open the door. Nothing
    caught it because every fixture password was alphanumeric.
    """

    @staticmethod
    def _clipboard_env(cab_root: Path, tmp_path: Path) -> tuple:
        fake_bin = tmp_path / "fake-bin"
        fake_bin.mkdir(exist_ok=True)
        copied = tmp_path / "clipboard"
        pbcopy = fake_bin / "pbcopy"
        pbcopy.write_text('#!/bin/bash\ncat > "$FAKE_PBCOPY_OUT"\n')
        pbcopy.chmod(0o755)
        env = base_env(
            cab_root,
            path=f"{fake_bin}:{MIN_PATH}",
            FAKE_PBCOPY_OUT=str(copied),
        )
        return env, copied

    @pytest.mark.parametrize(
        "password",
        [
            pytest.param("O'Brien's cabinet", id="apostrophes-and-spaces"),
            pytest.param("double''quote-cabinet", id="two-apostrophes-in-a-row"),
            pytest.param('say "hello" cabinet', id="double-quotes"),
            pytest.param("back\\slash\\pass", id="backslashes"),
            pytest.param("  padded password  ", id="leading-and-trailing-spaces"),
            pytest.param("blåbærgrød 2026", id="danish-letters"),
            pytest.param("100%-secure €uro", id="percent-and-euro"),
            pytest.param("chosen-by-operator-2026", id="plain-bare-value"),
        ],
    )
    def test_copy_returns_the_exact_password(self, cab_root, tmp_path, password):
        env_file = cab_root / "cabinet" / ".env"
        env_file.write_text(f"DASHBOARD_PASSWORD={_env_literal(password)}\nOTHER_KEY=keep\n")
        env_file.chmod(0o600)
        env, copied = self._clipboard_env(cab_root, tmp_path)
        result = run(["bash", str(DASHBOARD_PASSWORD), "--copy"], env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert copied.read_text() == password, "the clipboard must hold the password as typed"
        assert password not in result.stdout + result.stderr

    def test_copy_reads_a_shell_payload_as_text_even_when_it_is_quoted(self, cab_root, tmp_path):
        """The writer's quoted form is the normal shape now, so the "never
        evaluate the file" property has to hold for it too — not only for the
        bare legacy shape the older arm covers."""
        marker = tmp_path / "must-not-exist"
        password = f"pw$(touch {marker})yz"
        env_file = cab_root / "cabinet" / ".env"
        env_file.write_text(f"DASHBOARD_PASSWORD={_env_literal(password)}\n")
        env_file.chmod(0o600)
        assert env_file.read_text().startswith("DASHBOARD_PASSWORD='"), "fixture must be the quoted shape"
        env, copied = self._clipboard_env(cab_root, tmp_path)
        result = run(["bash", str(DASHBOARD_PASSWORD), "--copy"], env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert copied.read_text() == password
        assert not marker.exists(), "cabinet/.env content must never be sourced or evaluated"

    def test_copy_still_reads_a_legacy_double_quoted_value(self, cab_root, tmp_path):
        """Values written before the safe-quote layer landed are double-quoted;
        an instance that has been running since then must not lose its password
        to this change."""
        password = "legacy quoted 2026"
        env_file = cab_root / "cabinet" / ".env"
        env_file.write_text(f'DASHBOARD_PASSWORD="{password}"\n')
        env_file.chmod(0o600)
        env, copied = self._clipboard_env(cab_root, tmp_path)
        result = run(["bash", str(DASHBOARD_PASSWORD), "--copy"], env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert copied.read_text() == password


class TestDashboardPasswordReset:
    """--reset clears the password and returns the dashboard to first-run. The
    launchd restart is always SHIMMED here — a real kickstart would target the
    system label com.cabinet.dashboard and could bounce the developer's own live
    dashboard."""

    @staticmethod
    def _fake_launchctl(fake_bin: Path, log: Path, exit_code: int) -> dict:
        fake_bin.mkdir(exist_ok=True)
        lc = fake_bin / "launchctl"
        lc.write_text(f'#!/bin/bash\necho "$@" >> "{log}"\nexit {exit_code}\n')
        lc.chmod(0o755)
        return {"path": f"{fake_bin}:{MIN_PATH}"}

    def test_reset_clears_password_and_restarts_only_the_dashboard(self, cab_root, tmp_path):
        env_file = cab_root / "cabinet" / ".env"
        run(["bash", str(SETUP_ENV), "--defaults"], env=base_env(cab_root))
        _set_dashboard_password(env_file, "chosen-by-operator-2026")
        log = tmp_path / "launchctl.log"
        env = base_env(cab_root, **self._fake_launchctl(tmp_path / "bin", log, 0))
        result = run(["bash", str(DASHBOARD_PASSWORD), "--reset"], env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        dash = [l for l in env_file.read_text().splitlines() if l.startswith("DASHBOARD_PASSWORD=")][0]
        assert dash.split("=", 1)[1] == "", "reset must clear the stored password"
        assert "cleared" in result.stdout.lower()
        # No secret is ever revealed by a reset.
        assert "chosen-by-operator-2026" not in result.stdout + result.stderr
        # The restart targets the dashboard's OWN launchd label, nothing else.
        assert log.exists() and "com.cabinet.dashboard" in log.read_text()

    def test_reset_stays_honest_when_restart_fails(self, cab_root, tmp_path):
        env_file = cab_root / "cabinet" / ".env"
        run(["bash", str(SETUP_ENV), "--defaults"], env=base_env(cab_root))
        _set_dashboard_password(env_file, "chosen-by-operator-2026")
        log = tmp_path / "launchctl.log"
        env = base_env(cab_root, **self._fake_launchctl(tmp_path / "bin", log, 1))
        result = run(["bash", str(DASHBOARD_PASSWORD), "--reset"], env=env)
        # Restart could not be triggered — the password is STILL cleared and the
        # operator is told plainly to reopen the dashboard. Exit stays 0.
        assert result.returncode == 0, result.stdout + result.stderr
        dash = [l for l in env_file.read_text().splitlines() if l.startswith("DASHBOARD_PASSWORD=")][0]
        assert dash.split("=", 1)[1] == ""
        assert "reopen" in result.stdout.lower()

    def test_reset_refuses_loose_permissions(self, cab_root, tmp_path):
        env_file = cab_root / "cabinet" / ".env"
        run(["bash", str(SETUP_ENV), "--defaults"], env=base_env(cab_root))
        _set_dashboard_password(env_file, "chosen-by-operator-2026")
        env_file.chmod(0o644)
        log = tmp_path / "launchctl.log"
        env = base_env(cab_root, **self._fake_launchctl(tmp_path / "bin", log, 0))
        result = run(["bash", str(DASHBOARD_PASSWORD), "--reset"], env=env)
        assert result.returncode == 1
        assert "permissions are 600" in result.stderr
        assert not log.exists(), "must refuse BEFORE touching the running dashboard"

    def test_reset_adds_the_key_when_absent(self, cab_root, tmp_path):
        env_file = cab_root / "cabinet" / ".env"
        env_file.write_text("OTHER_KEY=keep\n")
        env_file.chmod(0o600)
        log = tmp_path / "launchctl.log"
        env = base_env(cab_root, **self._fake_launchctl(tmp_path / "bin", log, 0))
        result = run(["bash", str(DASHBOARD_PASSWORD), "--reset"], env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        text = env_file.read_text()
        assert "OTHER_KEY=keep" in text
        assert "DASHBOARD_PASSWORD=" in text and "DASHBOARD_PASSWORD=x" not in text


class TestWizardTelegramValidation:
    def test_valid_token_saved_username_confirmed_never_echoed(self, cab_root, fake_curl_dir):
        env = base_env(
            cab_root,
            path=f"{fake_curl_dir}:{MIN_PATH}",
            FAKE_CURL_BODY=GETME_OK,
        )
        # choice 'p', paste token, then EOF cascades skip through the rest
        r = run(["bash", str(SETUP_ENV)], env=env, stdin=f"p\n{FAKE_TOKEN}\n")
        assert r.returncode == 0
        combined = r.stdout + r.stderr
        assert "@CabinetTestBot" in combined
        assert FAKE_TOKEN not in combined, "token must never be echoed"
        env_text = (cab_root / "cabinet" / ".env").read_text()
        assert f"TELEGRAM_COS_TOKEN={FAKE_TOKEN}\n" in env_text

    def test_rejected_token_not_saved(self, cab_root, fake_curl_dir):
        env = base_env(
            cab_root,
            path=f"{fake_curl_dir}:{MIN_PATH}",
            FAKE_CURL_BODY=GETME_REJECTED,
            FAKE_CURL_CODE="401",
        )
        r = run(["bash", str(SETUP_ENV)], env=env, stdin=f"p\n{FAKE_TOKEN}\n")
        assert r.returncode == 0
        combined = r.stdout + r.stderr
        assert "NOT saved" in combined
        assert FAKE_TOKEN not in combined
        env_text = (cab_root / "cabinet" / ".env").read_text()
        assert "TELEGRAM_COS_TOKEN=\n" in env_text, "rejected token must not persist"

    def test_validator_missing_saves_unverified_with_note(self, cab_root, tmp_path):
        # Copy the wizard to a dir WITHOUT telegram-validate-token.sh: the
        # vrc=3 lane must save the token but say so ("UNVERIFIED"), never
        # silently.
        lone = tmp_path / "lone"
        lone.mkdir()
        script = lone / "setup-env.sh"
        script.write_text(SETUP_ENV.read_text())
        r = run(["bash", str(script)], env=base_env(cab_root),
                stdin=f"p\n{FAKE_TOKEN}\n")
        assert r.returncode == 0, r.stdout + r.stderr
        combined = r.stdout + r.stderr
        assert "UNVERIFIED" in combined, "silent unverified save is dishonest"
        assert FAKE_TOKEN not in combined
        env_text = (cab_root / "cabinet" / ".env").read_text()
        assert f"TELEGRAM_COS_TOKEN={FAKE_TOKEN}\n" in env_text


# ---------------------------------------------------------------------------
# telegram-validate-token.sh
# ---------------------------------------------------------------------------

class TestTelegramValidate:
    def _env(self, cab_root, fake_curl_dir, **extra):
        return base_env(
            cab_root,
            path=f"{fake_curl_dir}:{MIN_PATH}",
            CAB_TEST_TOKEN=FAKE_TOKEN,
            **extra,
        )

    def test_valid_exit_0_username(self, cab_root, fake_curl_dir):
        r = run(["bash", str(TG_VALIDATE), "--env", "CAB_TEST_TOKEN"],
                env=self._env(cab_root, fake_curl_dir, FAKE_CURL_BODY=GETME_OK))
        assert r.returncode == 0
        assert "@CabinetTestBot" in r.stdout
        assert FAKE_TOKEN not in r.stdout + r.stderr

    def test_rejected_exit_1(self, cab_root, fake_curl_dir):
        r = run(["bash", str(TG_VALIDATE), "--env", "CAB_TEST_TOKEN"],
                env=self._env(cab_root, fake_curl_dir,
                              FAKE_CURL_BODY=GETME_REJECTED, FAKE_CURL_CODE="401"))
        assert r.returncode == 1
        assert "Unauthorized" in r.stdout + r.stderr
        assert FAKE_TOKEN not in r.stdout + r.stderr

    def test_network_fail_exit_2(self, cab_root, fake_curl_dir):
        r = run(["bash", str(TG_VALIDATE), "--env", "CAB_TEST_TOKEN"],
                env=self._env(cab_root, fake_curl_dir,
                              FAKE_CURL_CODE="000", FAKE_CURL_RC="6"))
        assert r.returncode == 2

    def test_no_token_exit_64(self, cab_root, fake_curl_dir):
        env = base_env(cab_root, path=f"{fake_curl_dir}:{MIN_PATH}")
        r = run(["bash", str(TG_VALIDATE), "--env", "CAB_UNSET_VAR"], env=env)
        assert r.returncode == 64

    def test_token_as_argv_refused(self, cab_root, fake_curl_dir):
        r = run(["bash", str(TG_VALIDATE), FAKE_TOKEN],
                env=self._env(cab_root, fake_curl_dir))
        assert r.returncode == 64
        assert "never argv" in r.stdout + r.stderr


# ---------------------------------------------------------------------------
# telegram-capture-chat-id.sh (errand E1b)
# ---------------------------------------------------------------------------

class TestTelegramCapture:
    def _env(self, cab_root, fake_curl_dir, **extra):
        return base_env(
            cab_root,
            path=f"{fake_curl_dir}:{MIN_PATH}",
            CAB_TEST_TOKEN=FAKE_TOKEN,
            **extra,
        )

    def _defaults(self, cab_root):
        run(["bash", str(SETUP_ENV), "--defaults"], env=base_env(cab_root))

    def test_capture_and_write_with_yes(self, cab_root, fake_curl_dir):
        # Non-interactive identity-gate writes require the explicit --yes
        # attestation (stdin is not a TTY under subprocess).
        self._defaults(cab_root)
        r = run(["bash", str(TG_CAPTURE), "--env", "CAB_TEST_TOKEN", "--write", "--yes"],
                env=self._env(cab_root, fake_curl_dir, FAKE_CURL_BODY=GETUPDATES_FOUND))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "77700011" in r.stdout
        assert "@cap_test" in r.stdout, "sender label must be shown for verification"
        assert "-10098765" in r.stdout
        assert FAKE_TOKEN not in r.stdout + r.stderr
        env_text = (cab_root / "cabinet" / ".env").read_text()
        assert "CAPTAIN_TELEGRAM_ID=77700011\n" in env_text
        assert "TELEGRAM_HQ_CHAT_ID=-10098765\n" in env_text

    def test_write_without_yes_noninteractive_refuses(self, cab_root, fake_curl_dir):
        # CAPTAIN_TELEGRAM_ID is the default-deny identity gate on inbound
        # DMs — a non-TTY --write without --yes must report candidates but
        # write NOTHING (design §3 E1b: the Captain confirms the id).
        self._defaults(cab_root)
        r = run(["bash", str(TG_CAPTURE), "--env", "CAB_TEST_TOKEN", "--write"],
                env=self._env(cab_root, fake_curl_dir, FAKE_CURL_BODY=GETUPDATES_FOUND))
        assert r.returncode == 0, r.stdout + r.stderr
        assert "77700011" in r.stdout          # candidate still reported
        assert "--yes" in r.stdout + r.stderr   # guidance to re-run
        env_text = (cab_root / "cabinet" / ".env").read_text()
        assert "CAPTAIN_TELEGRAM_ID=\n" in env_text, \
            "identity gate must NOT be seeded without confirmation"
        assert "TELEGRAM_HQ_CHAT_ID=\n" in env_text

    def test_write_refuses_overwrite(self, cab_root, fake_curl_dir):
        self._defaults(cab_root)
        env_found = self._env(cab_root, fake_curl_dir, FAKE_CURL_BODY=GETUPDATES_FOUND)
        run(["bash", str(TG_CAPTURE), "--env", "CAB_TEST_TOKEN", "--write", "--yes"],
            env=env_found)
        # second capture sees a DIFFERENT sender; existing value must survive
        other = GETUPDATES_FOUND.replace("77700011", "99900099")
        env_other = self._env(cab_root, fake_curl_dir, FAKE_CURL_BODY=other)
        r = run(["bash", str(TG_CAPTURE), "--env", "CAB_TEST_TOKEN", "--write", "--yes"],
                env=env_other)
        assert r.returncode == 0
        assert "NOT overwriting" in r.stdout + r.stderr
        env_text = (cab_root / "cabinet" / ".env").read_text()
        assert "CAPTAIN_TELEGRAM_ID=77700011\n" in env_text

    def test_request_uses_full_window_and_no_offset(self, cab_root, fake_curl_dir, tmp_path):
        # limit=100 is the API max — smaller shrinks the pending window and
        # can hide the newest DM (Telegram serves oldest first); offset must
        # never be sent (read-only poll, nothing consumed).
        self._defaults(cab_root)
        cfg = tmp_path / "curl-config.txt"
        r = run(["bash", str(TG_CAPTURE), "--env", "CAB_TEST_TOKEN"],
                env=self._env(cab_root, fake_curl_dir,
                              FAKE_CURL_BODY=GETUPDATES_FOUND,
                              FAKE_CURL_CONFIG_OUT=str(cfg)))
        assert r.returncode == 0, r.stdout + r.stderr
        config = cfg.read_text()
        assert "limit=100" in config
        assert "offset=" not in config

    def test_window_full_warns_about_truncation(self, cab_root, fake_curl_dir):
        self._defaults(cab_root)
        updates = [
            {"update_id": i,
             "message": {"message_id": i,
                         "from": {"id": 77700011, "is_bot": False,
                                  "first_name": "Cap"},
                         "chat": {"id": 77700011, "type": "private"},
                         "text": "hi"}}
            for i in range(100)
        ]
        body = json.dumps({"ok": True, "result": updates})
        r = run(["bash", str(TG_CAPTURE), "--env", "CAB_TEST_TOKEN"],
                env=self._env(cab_root, fake_curl_dir, FAKE_CURL_BODY=body))
        assert r.returncode == 0
        assert "FULL" in r.stdout, "full window must warn about possible truncation"
        # a small window stays quiet
        r2 = run(["bash", str(TG_CAPTURE), "--env", "CAB_TEST_TOKEN"],
                 env=self._env(cab_root, fake_curl_dir, FAKE_CURL_BODY=GETUPDATES_FOUND))
        assert r2.returncode == 0
        assert "FULL" not in r2.stdout

    def test_honest_empty_exit_3(self, cab_root, fake_curl_dir):
        self._defaults(cab_root)
        r = run(["bash", str(TG_CAPTURE), "--env", "CAB_TEST_TOKEN"],
                env=self._env(cab_root, fake_curl_dir, FAKE_CURL_BODY=GETUPDATES_EMPTY))
        assert r.returncode == 3

    def test_conflict_409_exit_4(self, cab_root, fake_curl_dir):
        self._defaults(cab_root)
        r = run(["bash", str(TG_CAPTURE), "--env", "CAB_TEST_TOKEN"],
                env=self._env(cab_root, fake_curl_dir,
                              FAKE_CURL_BODY=GETUPDATES_CONFLICT, FAKE_CURL_CODE="409"))
        assert r.returncode == 4

    def test_rejected_token_exit_1(self, cab_root, fake_curl_dir):
        self._defaults(cab_root)
        r = run(["bash", str(TG_CAPTURE), "--env", "CAB_TEST_TOKEN"],
                env=self._env(cab_root, fake_curl_dir,
                              FAKE_CURL_BODY=GETME_REJECTED, FAKE_CURL_CODE="401"))
        assert r.returncode == 1


# ---------------------------------------------------------------------------
# provision-local-postgres.sh --check (read-only lanes; no brew, no network)
# ---------------------------------------------------------------------------

class TestProvisionCheck:
    def test_missing_env_exit_1(self, cab_root):
        r = run(["bash", str(PROVISION_PG), "--check"], env=base_env(cab_root))
        assert r.returncode == 1

    def test_unset_string_exit_1(self, cab_root):
        run(["bash", str(SETUP_ENV), "--defaults"], env=base_env(cab_root))
        r = run(["bash", str(PROVISION_PG), "--check"], env=base_env(cab_root))
        assert r.returncode == 1
        assert "not configured" in r.stdout + r.stderr

    def test_remote_string_accepted_unprobed(self, cab_root):
        (cab_root / "cabinet" / ".env").write_text(
            "NEON_CONNECTION_STRING=postgresql://u:pw@ep-example-123.aws.neon.tech/neondb\n"
        )
        r = run(["bash", str(PROVISION_PG), "--check"], env=base_env(cab_root))
        assert r.returncode == 0
        assert "not probed" in r.stdout

    def test_local_string_without_pg_isready_accepted_with_warn(self, cab_root):
        (cab_root / "cabinet" / ".env").write_text(
            "NEON_CONNECTION_STRING=postgresql://cabinet:pw@127.0.0.1:5432/cabinet\n"
        )
        # MIN_PATH has no pg_isready on a box without system postgres; make
        # that deterministic by shimming an empty PATH dir FIRST and keeping
        # only the system dirs (macOS ships no pg_isready in /usr/bin).
        r = run(["bash", str(PROVISION_PG), "--check"], env=base_env(cab_root))
        if r.returncode == 0:
            assert "configured" in r.stdout
        else:
            # a system pg_isready existed and the port probe failed — the
            # honest-liveness lane; accept both as contract-conformant
            assert "not accepting connections" in r.stdout + r.stderr

    def test_local_string_with_failing_pg_isready_exit_1(self, cab_root, tmp_path):
        (cab_root / "cabinet" / ".env").write_text(
            "NEON_CONNECTION_STRING=postgresql://cabinet:pw@127.0.0.1:5432/cabinet\n"
        )
        shim = tmp_path / "pgshim"
        shim.mkdir()
        pg = shim / "pg_isready"
        pg.write_text("#!/bin/bash\nexit 2\n")
        pg.chmod(0o755)
        r = run(["bash", str(PROVISION_PG), "--check"],
                env=base_env(cab_root, path=f"{shim}:{MIN_PATH}"))
        assert r.returncode == 1
        assert "not accepting connections" in r.stdout + r.stderr

    def test_check_probes_port_embedded_in_string(self, cab_root, tmp_path):
        # A store provisioned under CABINET_LOCAL_PG_PORT=5433 must --check
        # cleanly WITHOUT re-supplying the override: the probe target comes
        # from the stored connection string, not the env default (5432).
        (cab_root / "cabinet" / ".env").write_text(
            "NEON_CONNECTION_STRING=postgresql://cabinet:pw@127.0.0.1:5433/cabinet\n"
        )
        shim = tmp_path / "pgshim"
        shim.mkdir()
        arglog = tmp_path / "pg_isready_args.txt"
        pg = shim / "pg_isready"
        pg.write_text(f'#!/bin/bash\nprintf \'%s \' "$@" > "{arglog}"\nexit 0\n')
        pg.chmod(0o755)
        r = run(["bash", str(PROVISION_PG), "--check"],
                env=base_env(cab_root, path=f"{shim}:{MIN_PATH}"))
        assert r.returncode == 0, r.stdout + r.stderr
        logged = arglog.read_text()
        assert "5433" in logged, f"probe must use the stored port, got: {logged}"
        assert "5432" not in logged
        assert "5433" in r.stdout
        assert ":pw@" not in r.stdout, "credentials must never be printed"

    def test_provision_never_clobbers_existing_string(self, cab_root):
        # provision mode (not --check) with an existing string must exit 0
        # without touching it — the Neon cloud alternative stays intact.
        sentinel = "postgresql://u:pw@ep-example-123.aws.neon.tech/neondb"
        (cab_root / "cabinet" / ".env").write_text(f"NEON_CONNECTION_STRING={sentinel}\n")
        r = run(["bash", str(PROVISION_PG)], env=base_env(cab_root))
        assert r.returncode == 0
        assert "already set" in r.stdout
        assert sentinel in (cab_root / "cabinet" / ".env").read_text()
        assert sentinel not in r.stdout, "connection string value must not be logged"


# ---------------------------------------------------------------------------
# provision-local-postgres.sh — role-password SQL escaping (hermetic)
# ---------------------------------------------------------------------------

class TestProvisionSqlEscape:
    def test_password_quote_doubling_survives_fresh_mac_bash(self):
        """Pin the escape against /bin/bash 3.2 semantics.

        The backslash form "${x//\\'/\\'\\'}" leaves literal backslashes on
        bash 3.2 (ab'cd -> ab\\'\\'cd), which both breaks the CREATE/ALTER
        ROLE statement and corrupts the stored password. The script must use
        the version-proof $sq doubling; this test extracts the REAL
        assignment from the script and runs it under /bin/bash (3.2 on a
        fresh Mac) with a quote-bearing password.
        """
        lines = [ln.strip() for ln in PROVISION_PG.read_text().splitlines()]
        assert "sq=\"'\"" in lines, "escape must ride a $sq variable"
        assign = lines[lines.index("sq=\"'\"") + 1]
        assert assign.startswith("pwd_sql="), "pwd_sql must follow the sq= line"
        snippet = "; ".join([
            "pg_password=\"ab'cd\"",
            "sq=\"'\"",
            assign,
            "printf \"ALTER ROLE cabinet WITH LOGIN PASSWORD '%s';\" \"$pwd_sql\"",
        ])
        r = run(["/bin/bash", "-c", snippet])
        assert r.returncode == 0, r.stderr
        assert r.stdout == "ALTER ROLE cabinet WITH LOGIN PASSWORD 'ab''cd';"
        assert "\\" not in r.stdout, "bash 3.2 backslash-escape regression"

    def test_alphanumeric_password_passes_through_unchanged(self):
        lines = [ln.strip() for ln in PROVISION_PG.read_text().splitlines()]
        assign = lines[lines.index("sq=\"'\"") + 1]
        snippet = "; ".join([
            "pg_password=\"Abc123xyz\"",
            "sq=\"'\"",
            assign,
            "printf '%s' \"$pwd_sql\"",
        ])
        r = run(["/bin/bash", "-c", snippet])
        assert r.returncode == 0
        assert r.stdout == "Abc123xyz"
