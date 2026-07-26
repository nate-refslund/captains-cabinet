from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / "cabinet/scripts/hooks/pre-tool-use.sh"
ACK = ROOT / "cabinet/scripts/hooks/observe-ack.sh"
CONTROL = ROOT / "cabinet/scripts/observe-only.sh"
MAC_LAUNCHER = ROOT / "cabinet/scripts/start-officer-mac.sh"
LEGACY_LAUNCHER = ROOT / "cabinet/scripts/start-officer.sh"


def _root(tmp_path: Path, marker: str | None = "active\n") -> Path:
    root = tmp_path / "root"
    (root / "instance/config").mkdir(parents=True)
    if marker is not None:
        (root / "instance/config/observe-only").write_text(marker)
    return root


def _hook(root: Path, tool: str, tool_input: dict, env: dict | None = None):
    # The hook's kill-switch probe is intentionally global in production. Unit
    # tests must not inherit the workstation's live Redis posture, so provide a
    # hermetic redis-cli that reports a reachable control plane with no active
    # kill switch. Tests that need another Redis behavior can still override
    # PATH through env.
    #
    # It must ANSWER the reader's frame, not just exit 0: killswitch-read.sh
    # proves the read with a nonce sandwich (ECHO <n1> / GET key / ECHO <n2>)
    # and treats an unanswered probe as INDETERMINATE == stopped, because
    # redis-cli prints NOAUTH/NOPERM/WRONGTYPE/LOADING on stdout with exit 0.
    # Replaying the ECHO argument and answering GET with an empty value is the
    # honest "reachable, nothing armed" posture; it can never mask a real stop.
    fake_bin = root / ".test-bin"
    fake_bin.mkdir(exist_ok=True)
    fake_redis = fake_bin / "redis-cli"
    fake_redis.write_text(
        "#!/bin/sh\n"
        'while IFS= read -r l; do case "$l" in "ECHO "*) echo "${l#ECHO }";;'
        ' *) echo "";; esac; done\n',
        encoding="utf-8",
    )
    fake_redis.chmod(0o755)
    hook_env = {
        **os.environ,
        "CABINET_ROOT": str(root),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        **(env or {}),
    }
    return subprocess.run(
        ["/bin/bash", str(HOOK)],
        input=json.dumps({"tool_name": tool, "tool_input": tool_input}),
        text=True,
        capture_output=True,
        env=hook_env,
        timeout=20,
    )


def test_active_marker_blocks_native_mutation_bash_and_untyped_mcp(tmp_path: Path):
    root = _root(tmp_path)
    for tool, payload in (
        ("Edit", {"file_path": "README.md"}),
        ("Bash", {"command": "cat README.md"}),
        ("Task", {"prompt": "change it"}),
        ("mcp__neon__run_sql", {"sql": "SELECT 1"}),
        ("WebFetch", {"url": "https://unattested.example"}),
        ("WebSearch", {"query": "unattested native egress"}),
    ):
        result = _hook(root, tool, payload)
        assert result.returncode == 2, (tool, result.stderr)
        assert "OBSERVE-ONLY BLOCK" in result.stderr


def test_observe_only_allows_only_closed_receipt_ack_shape(tmp_path: Path):
    root = _root(tmp_path)
    allowed = _hook(
        root,
        "Bash",
        {"command": ("cabinet/scripts/hooks/observe-ack.sh 1720000" + "000000-0 1720000" + "000001-2")},
    )
    assert allowed.returncode == 0, allowed.stderr

    for command in (
        "cabinet/scripts/hooks/observe-ack.sh",
        "cabinet/scripts/hooks/observe-ack.sh nope",
        "cabinet/scripts/hooks/observe-ack.sh 1-0; redis-cli FLUSHALL",
        "env OFFICER_NAME=cos cabinet/scripts/hooks/observe-ack.sh 1-0",
        "/bin/bash cabinet/scripts/hooks/observe-ack.sh 1-0",
        "cabinet/scripts/hooks/observe-ack.sh 1-0 > /tmp/receipt",
    ):
        result = _hook(root, "Bash", {"command": command})
        assert result.returncode == 2, (command, result.stderr)
        assert "OBSERVE-ONLY BLOCK" in result.stderr


def test_receipt_ack_is_bound_to_inherited_officer_and_reports_redis_result(tmp_path: Path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "redis-calls"
    fake_redis = fake_bin / "redis-cli"
    fake_redis.write_text(
        "#!/bin/bash\n"
        "echo \"$*\" >> \"$FAKE_REDIS_CALLS\"\n"
        "case \" $* \" in\n"
        "  *\" XACK \"*) echo \"${FAKE_XACK_RESULT:-1}\" ;;\n"
        "  *\" XINFO GROUPS \"*) printf 'name\\nofficer-alpha\\nlast-delivered-id\\n9-0\\n' ;;\n"
        "  *\" XTRIM \"*) echo 0 ;;\n"
        "esac\n"
    )
    fake_redis.chmod(0o755)
    base_env = {
        **os.environ,
        "CABINET_ROOT": str(ROOT),
        "CABINET_OBSERVE_ONLY": "1",
        "OFFICER_NAME": "alpha",
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_REDIS_CALLS": str(calls),
    }

    first = subprocess.run(
        ["/bin/bash", str(ACK), "1720000" + "000000-0"],
        env={**base_env, "FAKE_XACK_RESULT": "1"},
        text=True, capture_output=True, timeout=10,
    )
    assert first.returncode == 0, first.stderr
    assert "newly_acknowledged=1" in first.stdout
    assert ("XACK cabinet:triggers:alpha officer-alpha 1720000" + "000000-0") in calls.read_text()

    repeat = subprocess.run(
        ["/bin/bash", str(ACK), "1720000" + "000000-0"],
        env={**base_env, "FAKE_XACK_RESULT": "0"},
        text=True, capture_output=True, timeout=10,
    )
    assert repeat.returncode == 0, repeat.stderr
    assert "already_clear=1" in repeat.stdout

    invalid_officer = subprocess.run(
        ["/bin/bash", str(ACK), "1720000" + "000000-0"],
        env={**base_env, "OFFICER_NAME": "../cos"},
        text=True, capture_output=True, timeout=10,
    )
    assert invalid_officer.returncode == 2
    assert "valid OFFICER_NAME" in invalid_officer.stderr


def test_invalid_marker_fails_closed_even_for_read(tmp_path: Path):
    result = _hook(_root(tmp_path, "maybe\n"), "Read", {"file_path": "README.md"})
    assert result.returncode == 2
    assert "marker is present but invalid" in result.stderr


def test_dangling_marker_symlink_fails_closed_in_control_and_hook(tmp_path: Path):
    root = _root(tmp_path, None)
    marker = root / "instance/config/observe-only"
    marker.symlink_to(root / "missing-marker-target")
    env = {**os.environ, "CABINET_ROOT": str(root)}
    status = subprocess.run(
        ["/bin/bash", str(CONTROL), "status"], env=env,
        text=True, capture_output=True, timeout=10,
    )
    assert status.returncode != 0
    assert status.stdout.strip() == "invalid"
    result = _hook(root, "Read", {"file_path": "README.md"})
    assert result.returncode == 2
    assert "marker is present but invalid" in result.stderr


def test_both_launchers_unconditionally_validate_marker_with_control_script():
    """Absent/active/dangling all flow through the one tested state parser."""
    for launcher in (MAC_LAUNCHER, LEGACY_LAUNCHER):
        text = launcher.read_text(encoding="utf-8")
        assert "observe-only.sh" in text
        assert ' status)"' in text
        assert "invalid observe-only marker" in text
        assert 'if [ -e "$OBSERVE_ONLY_MARKER" ]' not in text
        assert "gen-officer-mcp-config.py" in text
        assert "--observe-only" in text
        assert "--strict-mcp-config" in text


def test_both_base_configs_register_local_observe_comms_server():
    for config in (ROOT / ".mcp.json", ROOT / ".mcp.json.mac-native"):
        servers = json.loads(config.read_text())["mcpServers"]
        assert "redis-trigger-channel" in servers
        assert "cabinet-comms" in servers
        assert "framework/comms/mcp/server.py" in " ".join(
            servers["cabinet-comms"]["args"])


def test_process_cap_is_sticky_after_marker_removal(tmp_path: Path):
    result = _hook(
        _root(tmp_path, None),
        "Write",
        {"file_path": "x", "content": "y"},
        {"CABINET_OBSERVE_ONLY": "1"},
    )
    assert result.returncode == 2
    assert "OBSERVE-ONLY BLOCK" in result.stderr


def test_native_secret_reads_block_direct_and_realpath_aliases(tmp_path: Path):
    root = _root(tmp_path, None)
    product = tmp_path / "product"
    product.mkdir()
    product_env = product / ".env.production"
    product_env.write_text("TOKEN=product-secret\n")
    shared = tmp_path / "master" / "credentials.data"
    shared.parent.mkdir()
    shared.write_text("TOKEN=master-secret\n")
    (root / "instance/config/platform.yml").write_text(
        f"shared_env_path: {shared}\ngit_repos:\n  - {product}\n"
    )
    alias = tmp_path / "innocent-name"
    alias.symlink_to(product_env)

    for path in (product_env, alias, shared):
        result = _hook(root, "Read", {"file_path": str(path)})
        assert result.returncode == 2, (path, result.stderr)
        assert "role-scoped environment projection" in result.stderr

    glob = _hook(root, "Glob", {"path": str(product), "pattern": "**/.env*"})
    assert glob.returncode == 2


def test_captain_control_enable_status_disable_roundtrip(tmp_path: Path):
    root = _root(tmp_path, None)
    env = {**os.environ, "CABINET_ROOT": str(root)}
    enabled = subprocess.run(
        ["/bin/bash", str(CONTROL), "enable"], env=env,
        text=True, capture_output=True, timeout=10,
    )
    assert enabled.returncode == 0, enabled.stderr
    marker = root / "instance/config/observe-only"
    assert marker.read_text() == "active\n"
    status = subprocess.run(
        ["/bin/bash", str(CONTROL), "status"], env=env,
        text=True, capture_output=True, timeout=10,
    )
    assert status.stdout.strip() == "active"
    disabled = subprocess.run(
        ["/bin/bash", str(CONTROL), "disable"], env=env,
        text=True, capture_output=True, timeout=10,
    )
    assert disabled.returncode == 0, disabled.stderr
    assert not marker.exists()


def test_observe_control_and_ack_shellcheck_clean():
    if shutil.which("shellcheck") is None:
        return
    result = subprocess.run(
        ["shellcheck", "-S", "warning", str(CONTROL), str(ACK)],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
