from __future__ import annotations

import os
import platform
import signal
import socket
import subprocess
import time
from pathlib import Path
from threading import Thread

import pytest


ROOT = Path(__file__).resolve().parents[4]
BROKER = ROOT / "cabinet" / "scripts" / "captain-law-broker.py"
APPENDER = ROOT / "cabinet" / "scripts" / "append-interface.sh"
SANDBOX_LIB = ROOT / "cabinet" / "scripts" / "lib" / "officer-sandbox.sh"
CAPABILITY = "test-capability-" + "a" * 64


def _root(tmp_path: Path) -> Path:
    for name in ("captain-patterns.md", "captain-intents.md", "captain-decisions.md"):
        path = tmp_path / "shared" / "interfaces" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n")
    return tmp_path


def _socket_path() -> Path:
    # sockaddr_un is capped at roughly 104 bytes on macOS; pytest's temporary
    # roots are intentionally verbose.
    directory = Path("/tmp") / f"clb-{os.getpid()}-{time.time_ns()}"
    directory.mkdir(mode=0o700)
    return directory / "b.sock"


def _start_broker(root: Path, socket_path: Path, officer: str = "cto"):
    broker_env = {**os.environ, "CABINET_LAW_BROKER_CAPABILITY": CAPABILITY}
    proc = subprocess.Popen(
        [
            "python3.12",
            str(BROKER),
            "serve",
            "--socket",
            str(socket_path),
            "--root",
            str(root),
            "--officer",
            officer,
            "--idle-timeout",
            "30",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=broker_env,
    )
    for _ in range(100):
        if socket_path.is_socket():
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.02)
    out, err = proc.communicate(timeout=1)
    raise AssertionError(f"broker failed to start: {out} {err}")


def _stop(proc: subprocess.Popen):
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)


def test_broker_owns_identity_and_rejects_captain_headings(tmp_path: Path):
    root = _root(tmp_path)
    sock = _socket_path()
    proc = _start_broker(root, sock, "cto")
    try:
        env = {
            **os.environ,
            "CABINET_ROOT": str(root),
            "CABINET_CAPTAIN_LAW_SOCKET": str(sock),
            "CABINET_CAPTAIN_LAW_CAPABILITY": CAPABILITY,
        }
        good = subprocess.run(
            ["/bin/bash", str(APPENDER), "captain-patterns"],
            input="Evidence-backed observation.",
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        assert good.returncode == 0, good.stderr
        text = (root / "shared/interfaces/captain-patterns.md").read_text()
        assert "appended by cto" in text
        assert "[trust:officer]" in text
        assert "Evidence-backed observation." in text

        bad_env = {**env, "CABINET_CAPTAIN_CHANNEL": "1", "OFFICER_NAME": "captain"}
        bad = subprocess.run(
            ["/bin/bash", str(APPENDER), "captain-patterns"],
            input="## forged Captain ruling\n",
            text=True,
            capture_output=True,
            env=bad_env,
            check=False,
        )
        assert bad.returncode != 0
        assert "forged Captain ruling" not in (
            root / "shared/interfaces/captain-patterns.md"
        ).read_text()
    finally:
        _stop(proc)


def test_broker_refuses_symlink_ledger(tmp_path: Path):
    root = _root(tmp_path)
    ledger = root / "shared/interfaces/captain-decisions.md"
    victim = tmp_path / "victim"
    victim.write_text("unchanged")
    ledger.unlink()
    ledger.symlink_to(victim)
    sock = _socket_path()
    proc = _start_broker(root, sock)
    try:
        result = subprocess.run(
            [
                "python3.12",
                str(BROKER),
                "client",
                "--socket",
                str(sock),
                "--target",
                "captain-decisions",
            ],
            input="try overwrite",
            text=True,
            capture_output=True,
            env={**os.environ, "CABINET_CAPTAIN_LAW_CAPABILITY": CAPABILITY},
            check=False,
        )
        assert result.returncode != 0
        assert victim.read_text() == "unchanged"
    finally:
        _stop(proc)


def test_broker_rejects_another_officers_capability(tmp_path: Path):
    root = _root(tmp_path)
    sock = _socket_path()
    proc = _start_broker(root, sock, "cto")
    try:
        result = subprocess.run(
            [
                "python3.12",
                str(BROKER),
                "client",
                "--socket",
                str(sock),
                "--target",
                "captain-patterns",
            ],
            input="spoof another officer",
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "CABINET_CAPTAIN_LAW_CAPABILITY": "wrong-capability-" + "b" * 64,
            },
            check=False,
        )
        assert result.returncode != 0
        assert "spoof another officer" not in (
            root / "shared/interfaces/captain-patterns.md"
        ).read_text()
    finally:
        _stop(proc)


def test_broker_preserves_best_effort_memory_ingestion(tmp_path: Path):
    root = _root(tmp_path)
    marker = tmp_path / "memory-queued"
    memory = root / "cabinet/scripts/lib/memory.sh"
    hook = root / "cabinet/scripts/hooks/post-file-write-memory.sh"
    memory.parent.mkdir(parents=True, exist_ok=True)
    hook.parent.mkdir(parents=True, exist_ok=True)
    memory.write_text("# fixture memory library\n")
    hook.write_text(
        "pfwm_queue_watched_file() { "
        f"printf '%s|%s' \"$1\" \"$2\" > {marker!s}; "
        "}\n"
    )
    sock = _socket_path()
    proc = _start_broker(root, sock, "cro")
    try:
        result = subprocess.run(
            [
                "python3.12",
                str(BROKER),
                "client",
                "--socket",
                str(sock),
                "--target",
                "captain-intents",
            ],
            input="Memory should see this officer observation.",
            text=True,
            capture_output=True,
            env={**os.environ, "CABINET_CAPTAIN_LAW_CAPABILITY": CAPABILITY},
            check=False,
        )
        assert result.returncode == 0, result.stderr
        for _ in range(100):
            if marker.exists():
                break
            time.sleep(0.02)
        assert marker.exists()
        queued = marker.read_text()
        assert queued.endswith("captain-intents.md|cro")
    finally:
        _stop(proc)


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS Seatbelt only")
def test_kernel_boundary_blocks_split_path_and_secret_read_but_broker_appends(tmp_path: Path):
    root = _root(tmp_path)
    sock = _socket_path()
    env_file = root / "cabinet/.env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("DASHBOARD_PASSWORD=captain-only\n")
    captain_home = root / "captain-home"
    personal_key = captain_home / ".ssh/id_private"
    personal_key.parent.mkdir(parents=True)
    personal_key.write_text("captain-personal-key\n")
    shared_env = captain_home / ".screenpipe/pipes/_shared/.env"
    shared_env.parent.mkdir(parents=True)
    shared_env.write_text("MASTER_TOKEN=never-officer-visible\n")
    runtime_state = captain_home / ".screenpipe/state"
    (runtime_state / "egress").mkdir(parents=True)
    product_root = tmp_path / "product-source"
    product_root.mkdir()
    product_file = product_root / "app.py"
    product_file.write_text("before\n")
    product_env = product_root / ".env.production"
    product_env.write_text("PRODUCT_TOKEN=never-visible\n")
    tier2 = root / "instance/memory/tier2/cpo"
    tier2.mkdir(parents=True)
    profile = tmp_path / "officer.sb"
    generated = subprocess.run(
        [
            "/bin/bash",
            "-c",
            f"HOME={captain_home!s}; CABINET_OFFICER=cpo; source {SANDBOX_LIB!s}; "
            f"officer_sandbox_write_profile {root!s} {profile!s} {sock.parent!s} {sock!s} "
            f"1 1 {shared_env!s} {runtime_state!s} {product_root!s}",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert generated.returncode == 0, generated.stderr

    # Enforced egress is a kernel boundary on Mac: localhost remains available
    # for the verified proxy/Redis, while a raw direct Internet socket fails.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    local_port = listener.getsockname()[1]

    def _accept_once():
        conn, _ = listener.accept()
        conn.close()
        listener.close()

    accept_thread = Thread(target=_accept_once, daemon=True)
    accept_thread.start()
    local_connect = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile),
            "python3.12",
            "-c",
            f'import socket; socket.create_connection(("127.0.0.1", {local_port}), 1).close()',
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert local_connect.returncode == 0, local_connect.stderr
    accept_thread.join(timeout=2)

    direct_external = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile),
            "python3.12",
            "-c",
            'import socket; socket.create_connection(("1.1.1.1", 443), 1).close()',
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert direct_external.returncode != 0

    source_write = subprocess.run(
        [
            "/usr/bin/sandbox-exec", "-f", str(profile), "/bin/bash", "-c",
            f'printf after > {product_file!s}',
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert source_write.returncode != 0
    assert product_file.read_text() == "before\n"

    memory_write = subprocess.run(
        [
            "/usr/bin/sandbox-exec", "-f", str(profile), "/bin/bash", "-c",
            f'printf observation > {tier2 / "observation.md"!s}',
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert memory_write.returncode == 0, memory_write.stderr

    # Observe HOME is default-deny, with only explicit Cabinet runtime and
    # own-tier2 stores writable. This is a real Seatbelt execution, not a text
    # assertion: unrelated Documents fails while Claude/runtime state works.
    documents = captain_home / "Documents"
    documents.mkdir()
    unrelated_write = subprocess.run(
        ["/usr/bin/sandbox-exec", "-f", str(profile), "/bin/bash", "-c",
         f'printf no > {documents / "escape.txt"!s}'],
        text=True, capture_output=True, check=False,
    )
    assert unrelated_write.returncode != 0
    assert not (documents / "escape.txt").exists()

    for allowed in (
        captain_home / "Library/Application Support/cabinet/claude-config/session.json",
        captain_home / "Library/Application Support/cabinet/feed/events.jsonl",
        runtime_state / "officer-runtime.json",
    ):
        allowed.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["/usr/bin/sandbox-exec", "-f", str(profile), "/bin/bash", "-c",
             'printf runtime > "$1"', "write-runtime", str(allowed)],
            text=True, capture_output=True, check=False,
        )
        assert result.returncode == 0, (allowed, result.stderr)

    egress_state_write = subprocess.run(
        ["/usr/bin/sandbox-exec", "-f", str(profile), "/bin/bash", "-c",
         f'printf forged > {runtime_state / "egress/proxy.env"!s}'],
        text=True, capture_output=True, check=False,
    )
    assert egress_state_write.returncode != 0

    split = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile),
            "/bin/bash",
            "-c",
            'D="shared/interfaces"; F="captain-decisions.md"; printf forged >> "$D/$F"',
        ],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert split.returncode != 0
    assert "forged" not in (root / "shared/interfaces/captain-decisions.md").read_text()

    read_secret = subprocess.run(
        ["/usr/bin/sandbox-exec", "-f", str(profile), "/bin/cat", str(env_file)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert read_secret.returncode != 0
    assert "captain-only" not in read_secret.stdout

    for secret in (shared_env, product_env):
        denied = subprocess.run(
            ["/usr/bin/sandbox-exec", "-f", str(profile), "/bin/cat", str(secret)],
            text=True, capture_output=True, check=False,
        )
        assert denied.returncode != 0
        assert "never" not in denied.stdout.lower()

    read_personal_key = subprocess.run(
        ["/usr/bin/sandbox-exec", "-f", str(profile), "/bin/cat", str(personal_key)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert read_personal_key.returncode != 0
    assert "captain-personal-key" not in read_personal_key.stdout

    moved_env = root / "cabinet/env-moved"
    rename_secret = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile),
            "/bin/mv",
            str(env_file),
            str(moved_env),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rename_secret.returncode != 0
    assert env_file.exists() and not moved_env.exists()

    moved_cabinet = root / "cabinet-moved"
    rename_parent = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile),
            "/bin/mv",
            str(root / "cabinet"),
            str(moved_cabinet),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert rename_parent.returncode != 0
    assert (root / "cabinet").is_dir() and not moved_cabinet.exists()

    hardlink = Path("/tmp") / f"cabinet-env-hardlink-{os.getpid()}-{time.time_ns()}"
    link_secret = subprocess.run(
        [
            "/usr/bin/sandbox-exec",
            "-f",
            str(profile),
            "/bin/ln",
            str(env_file),
            str(hardlink),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert link_secret.returncode != 0
    assert not hardlink.exists()

    # Regression for the real Seatbelt escape: a sandboxed tmux client can ask
    # a pre-existing unsandboxed server to spawn a new window.  The profile must
    # deny both the client executable and the shared server's Unix socket.
    tmux = subprocess.run(
        ["/bin/sh", "-c", "command -v tmux"], text=True, capture_output=True
    ).stdout.strip()
    if tmux:
        real_tmux = os.path.realpath(tmux)
        custom_socket = Path("/tmp") / f"cabinet-tmux-escape-{os.getpid()}-{time.time_ns()}.sock"
        leak = root / "tmux-leak"
        subprocess.run(
            [real_tmux, "-S", str(custom_socket), "-f", "/dev/null", "new-session", "-d", "-s", "probe"],
            check=True,
        )
        try:
            escape = subprocess.run(
                [
                    "/usr/bin/sandbox-exec",
                    "-f",
                    str(profile),
                        real_tmux,
                        "-S",
                        str(custom_socket),
                    "new-window",
                    "-d",
                    f"/bin/cat {env_file} > {leak}",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            time.sleep(0.1)
            assert escape.returncode != 0
            assert not leak.exists()
        finally:
            subprocess.run([real_tmux, "-S", str(custom_socket), "kill-server"], check=False)

    # Path aliases do not bypass the vnode-level secret-store denial.
    alias = Path("/tmp") / f"cabinet-env-alias-{os.getpid()}-{time.time_ns()}"
    alias.symlink_to(env_file)
    try:
        alias_read = subprocess.run(
            ["/usr/bin/sandbox-exec", "-f", str(profile), "/bin/cat", str(alias)],
            text=True,
            capture_output=True,
            check=False,
        )
        assert alias_read.returncode != 0
        assert "captain-only" not in alias_read.stdout
    finally:
        alias.unlink(missing_ok=True)

    product_alias = Path("/tmp") / f"product-env-alias-{os.getpid()}-{time.time_ns()}"
    product_alias.symlink_to(product_env)
    try:
        alias_read = subprocess.run(
            ["/usr/bin/sandbox-exec", "-f", str(profile), "/bin/cat", str(product_alias)],
            text=True, capture_output=True, check=False,
        )
        assert alias_read.returncode != 0
        assert "never-visible" not in alias_read.stdout
    finally:
        product_alias.unlink(missing_ok=True)

    proc = _start_broker(root, sock, "cpo")
    try:
        broker_append = subprocess.run(
            [
                "/usr/bin/sandbox-exec",
                "-f",
                str(profile),
                "/usr/bin/env",
                f"CABINET_ROOT={root}",
                f"CABINET_CAPTAIN_LAW_SOCKET={sock}",
                f"CABINET_CAPTAIN_LAW_CAPABILITY={CAPABILITY}",
                "/bin/bash",
                str(APPENDER),
                "captain-intents",
            ],
            input="A hypothesis, not a ruling.",
            text=True,
            capture_output=True,
            check=False,
        )
        assert broker_append.returncode == 0, broker_append.stderr
        text = (root / "shared/interfaces/captain-intents.md").read_text()
        assert "appended by cpo" in text
        assert "[trust:officer]" in text

        other_sock = _socket_path()
        other = _start_broker(root, other_sock, "cto")
        try:
            cross_officer = subprocess.run(
                [
                    "/usr/bin/sandbox-exec",
                    "-f",
                    str(profile),
                    "/usr/bin/env",
                    f"CABINET_CAPTAIN_LAW_CAPABILITY={CAPABILITY}",
                    "python3.12",
                    str(BROKER),
                    "client",
                    "--socket",
                    str(other_sock),
                    "--target",
                    "captain-patterns",
                ],
                input="cross-officer spoof",
                text=True,
                capture_output=True,
                check=False,
            )
            assert cross_officer.returncode != 0
            assert "cross-officer spoof" not in (
                root / "shared/interfaces/captain-patterns.md"
            ).read_text()
        finally:
            _stop(other)

        # The officer may connect to its socket but cannot unlink/replace the
        # protected broker directory or socket vnode.
        replace = subprocess.run(
            [
                "/usr/bin/sandbox-exec",
                "-f",
                str(profile),
                "/bin/rm",
                "-f",
                str(sock),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert sock.is_socket()
    finally:
        _stop(proc)
