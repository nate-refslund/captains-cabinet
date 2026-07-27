"""A cost surface must never emit a number it could not source.

WHY THIS FILE EXISTS (2026-07-26 control-plane fail-open sweep). With the
control plane unreachable, `cabinet/cron/cost-summary.sh` sent the Captain's
group:

    💰 Cabinet cost summary <date>
      cos: $0.00
      ...
    Total: $0.00

exit 0, stderr empty — measured BYTE-IDENTICAL to a true zero-spend day. The
outage rendered as a legitimate business result, on the one automated surface
that reaches him personally. `cost-report.sh` did the same and added a wrong
innocent cause ("stop-hook may not have fired yet"), which is worse than
silence: it tells the reader to stop looking.

Every test here DRIVES THE REAL SCRIPTS against a real redis-server on an
ephemeral port (never 6379, never the live plane), and against a port with
nothing listening. The load-bearing assertion is not "the wording changed" but
that the two outputs are DISTINGUISHABLE — which is the property that was
absent, and the only one that helps the reader.

The outbound sender is stubbed to a file, so the digest bytes are captured
exactly as they would be sent and nothing leaves the machine.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
COST_SUMMARY = REPO / "cabinet" / "cron" / "cost-summary.sh"
COST_REPORT = REPO / "cabinet" / "scripts" / "cost-report.sh"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def live_port(tmp_path):
    if not shutil.which("redis-server") or not shutil.which("redis-cli"):
        pytest.skip("redis-server and redis-cli required")
    port = _free_port()
    proc = subprocess.Popen(
        ["redis-server", "--bind", "127.0.0.1", "--port", str(port),
         "--protected-mode", "no", "--save", "", "--appendonly", "no",
         "--dir", str(tmp_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            r = subprocess.run(["redis-cli", "-h", "127.0.0.1", "-p", str(port), "PING"],
                               text=True, capture_output=True, check=False)
            if r.stdout.strip() == "PONG":
                break
            time.sleep(0.05)
        else:
            pytest.skip("redis-server did not come up")
        yield port
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)


@pytest.fixture
def sandbox_repo(tmp_path):
    """A repo copy whose outbound sender is a file-writing stub, plus a small
    officer roster. Nothing here can reach Telegram."""
    root = tmp_path / "repo"
    root.mkdir()
    for rel in ("cabinet/cron", "cabinet/scripts/lib", "instance/roles/active"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copy2(COST_SUMMARY, root / "cabinet/cron/cost-summary.sh")
    shutil.copy2(COST_REPORT, root / "cabinet/scripts/cost-report.sh")
    # Copied only if it exists, deliberately: the sandbox must mirror the repo
    # as it IS. Hard-requiring the helper here would turn "the repo has no
    # fail-closed read" into a fixture ERROR instead of a test FAILURE, and an
    # arm that errors for a different reason than the one it names is not
    # evidence about the code.
    helper = REPO / "cabinet/scripts/lib/plane-read.sh"
    if helper.is_file():
        shutil.copy2(helper, root / "cabinet/scripts/lib/plane-read.sh")
    sender = root / "cabinet/scripts/send-to-group.sh"
    sender.write_text('#!/bin/bash\nprintf "%s\\n" "$1" > "$SENDBOX"\nexit 0\n')
    sender.chmod(0o755)
    for slug in ("cos", "cto"):
        (root / "instance/roles/active" / f"{slug}.yml").write_text(f"slug: {slug}\n")
    return root


def _run_summary(sandbox_repo, port, tmp_path, name):
    out = tmp_path / f"sent-{name}.txt"
    env = dict(os.environ)
    env.update(CABINET_SOURCE_REPO=str(sandbox_repo), REDIS_HOST="127.0.0.1",
               REDIS_PORT=str(port), SENDBOX=str(out))
    r = subprocess.run(["bash", str(sandbox_repo / "cabinet/cron/cost-summary.sh")],
                       env=env, text=True, capture_output=True, timeout=60)
    return (out.read_text() if out.exists() else ""), r


def _seed(port, **fields):
    today = subprocess.run(["date", "-u", "+%Y-%m-%d"], text=True,
                           capture_output=True, check=True).stdout.strip()
    args = []
    for k, v in fields.items():
        args += [k, str(v)]
    subprocess.run(["redis-cli", "-h", "127.0.0.1", "-p", str(port),
                    "HSET", f"cabinet:cost:tokens:daily:{today}", *args],
                   capture_output=True, check=False)


# ── cost-summary.sh — the surface that reaches the Captain ──────────────────

def test_dead_plane_digest_is_DISTINGUISHABLE_from_a_true_zero_spend_day(
        sandbox_repo, live_port, tmp_path):
    """THE regression this whole change exists to prevent. Before the fix these
    two byte-compared equal."""
    zero_msg, zero_r = _run_summary(sandbox_repo, live_port, tmp_path, "zero")
    dead_msg, dead_r = _run_summary(sandbox_repo, _free_port(), tmp_path, "dead")
    assert zero_msg.strip(), "healthy zero-spend day produced no digest at all"
    assert dead_msg.strip(), "dead plane produced no message at all"
    assert zero_msg != dead_msg, (
        "the dead-plane message is byte-identical to a true zero-spend digest — "
        "the Captain cannot tell an outage from a quiet day.\n"
        f"  both were:\n{zero_msg}"
    )


def test_dead_plane_digest_contains_NO_dollar_figure(sandbox_repo, tmp_path):
    """'Never emit a number it cannot source' — stated as a check on the bytes
    actually sent, not on the wording."""
    msg, _ = _run_summary(sandbox_repo, _free_port(), tmp_path, "nofig")
    assert "0.00" not in msg, f"a dead plane still reported a dollar figure:\n{msg}"
    assert "Total:" not in msg, f"a dead plane still reported a total:\n{msg}"
    low = msg.lower()
    assert "unavailable" in low and "unreachable" in low, msg


def test_dead_plane_writes_a_watchdog_visible_marker_to_stderr(sandbox_repo, tmp_path):
    """The failure must also be visible to the outcome-watchdog's log-tail scan,
    which greps for JOB_ERROR_MARKERS. Before the fix stderr was EMPTY."""
    import sys
    sys.path.insert(0, str(REPO))
    from framework.watchdog.registry import JOB_ERROR_MARKERS

    _msg, r = _run_summary(sandbox_repo, _free_port(), tmp_path, "marker")
    hits = [m for m in JOB_ERROR_MARKERS if m in r.stderr]
    assert hits, (
        "a failed cost digest left nothing in stderr that the outcome-watchdog "
        f"scans for.\n  markers: {list(JOB_ERROR_MARKERS)}\n  stderr: {r.stderr!r}")


def test_healthy_plane_with_real_spend_still_reports_the_real_numbers(
        sandbox_repo, live_port, tmp_path):
    """Negative control: fail-closed must not mean fail-always. Without this, a
    script that unconditionally printed 'unavailable' would pass every
    assertion above."""
    _seed(live_port, cos_cost_micro=4_500_000, cto_cost_micro=1_250_000)
    msg, r = _run_summary(sandbox_repo, live_port, tmp_path, "spend")
    assert "4.50" in msg and "1.25" in msg, msg
    assert "5.75" in msg, f"total not summed: {msg}"
    assert "unavailable" not in msg.lower(), msg


def test_healthy_plane_with_no_spend_still_reports_a_real_zero(
        sandbox_repo, live_port, tmp_path):
    """The legitimate zero must survive. ABSENT-after-a-proven-live-plane is
    the ONLY zero this design accepts, and it must still render."""
    msg, _ = _run_summary(sandbox_repo, live_port, tmp_path, "realzero")
    assert "Total: $0.00" in msg, msg
    assert "unavailable" not in msg.lower(), msg


def test_a_shimmed_redis_cli_cannot_forge_a_zero_spend_digest(
        sandbox_repo, tmp_path, monkeypatch):
    """A fake redis-cli that answers everything with an empty line — the shape
    that defeated the old `2>/dev/null` read — must not produce a $0.00
    digest."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    shim = fake_bin / "redis-cli"
    shim.write_text("#!/bin/bash\necho\nexit 0\n")
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ['PATH']}")
    msg, _ = _run_summary(sandbox_repo, _free_port(), tmp_path, "shim")
    assert "0.00" not in msg, f"a shimmed client forged a zero-spend digest:\n{msg}"


def test_missing_helper_does_not_fall_back_to_the_silent_zero(tmp_path):
    """If plane-read.sh is absent the job must report unavailable, NOT quietly
    revert to the old coercion. A fix that only works while a file exists is
    not a fix."""
    root = tmp_path / "norepo"
    (root / "cabinet/cron").mkdir(parents=True)
    (root / "instance/roles/active").mkdir(parents=True)
    shutil.copy2(COST_SUMMARY, root / "cabinet/cron/cost-summary.sh")
    (root / "instance/roles/active/cos.yml").write_text("slug: cos\n")
    (root / "cabinet/scripts").mkdir(parents=True, exist_ok=True)
    sender = root / "cabinet/scripts/send-to-group.sh"
    sender.write_text('#!/bin/bash\nprintf "%s\\n" "$1" > "$SENDBOX"\nexit 0\n')
    sender.chmod(0o755)
    out = tmp_path / "sent.txt"
    env = dict(os.environ)
    env.update(CABINET_SOURCE_REPO=str(root), REDIS_HOST="127.0.0.1",
               REDIS_PORT=str(_free_port()), SENDBOX=str(out))
    subprocess.run(["bash", str(root / "cabinet/cron/cost-summary.sh")],
                   env=env, text=True, capture_output=True, timeout=60)
    msg = out.read_text() if out.exists() else ""
    assert "0.00" not in msg, f"missing helper degraded to a silent zero:\n{msg}"
    assert "unavailable" in msg.lower(), msg


# ── cost-report.sh — the false zero plus the invented innocent cause ────────

def _run_report(sandbox_repo, port):
    env = dict(os.environ)
    env.update(CABINET_SOURCE_REPO=str(sandbox_repo), REDIS_HOST="127.0.0.1",
               REDIS_PORT=str(port))
    return subprocess.run(
        ["bash", str(sandbox_repo / "cabinet/scripts/cost-report.sh"), "--daily"],
        env=env, text=True, capture_output=True, timeout=60)


def test_report_on_a_dead_plane_says_unavailable_and_names_no_cause_it_did_not_diagnose(
        sandbox_repo):
    r = _run_report(sandbox_repo, _free_port())
    assert "stop-hook may not have fired yet" not in r.stdout, (
        "the invented innocent cause is back — it names a benign reason for a "
        "failure that was never diagnosed")
    assert "UNAVAILABLE" in r.stdout.upper(), r.stdout
    assert r.returncode != 0, "an unreadable report must not exit 0"


def test_report_on_a_live_but_empty_ledger_is_distinguishable_from_a_dead_plane(
        sandbox_repo, live_port):
    dead = _run_report(sandbox_repo, _free_port())
    empty = _run_report(sandbox_repo, live_port)
    assert dead.stdout != empty.stdout
    assert empty.returncode == 0
    assert "verified reachable" in empty.stdout, empty.stdout


def test_report_with_real_spend_prints_the_real_total(sandbox_repo, live_port):
    _seed(live_port, cos_input=1000, cos_output=200, cos_cost_micro=4_500_000)
    r = _run_report(sandbox_repo, live_port)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "TOTAL: $4.50" in r.stdout, r.stdout
