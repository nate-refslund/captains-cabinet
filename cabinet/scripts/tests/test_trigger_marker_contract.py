"""The emitted marker and the detected marker must be THE SAME STRING.

WHY THIS FILE EXISTS (2026-07-26 control-plane fail-open sweep). Two sides of
one contract had drifted apart with nothing holding them together:

  * ``cabinet/scripts/lib/triggers.sh`` printed, on a failed XADD,
    ``trigger_send WARN: XADD to <stream> failed ... — trigger NOT queued``
  * ``framework/watchdog/registry.py`` JOB_ERROR_MARKERS — the tuple the
    outcome-watchdog's ``no-silent-cron-failure`` log-tail scan actually greps
    for — contained ``"trigger NOT pushed"`` and ``"trigger_send failed"``.

Neither marker was in the emitted line. Every dropped trigger was therefore
invisible to the only thing watching for dropped triggers, and the golden eval
covering this path passed the whole time because its regex was BROADER than the
marker list the detector uses (it matched ``trigger_send WARN``, a string no
detector looks at). Sensor green, control blind.

The defect was the DRIFT, not either spelling — so this test pins the two to
each other rather than pinning either one to a literal:

  * it IMPORTS ``JOB_ERROR_MARKERS`` from the registry (never re-types it), so
    editing the detector's list re-aims this test automatically;
  * it DRIVES ``trigger_send`` for real against a dead port and greps the
    stderr it actually produced, so a rewording of the shell line is caught by
    execution rather than by a static string compare that could itself drift.

Change either side without the other and this fails.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TRIGGERS_LIB = REPO / "cabinet" / "scripts" / "lib" / "triggers.sh"

sys.path.insert(0, str(REPO))
from framework.watchdog.registry import JOB_ERROR_MARKERS  # noqa: E402


def _dead_port() -> int:
    """A port with nothing listening: bind, read the number, close it."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    return port


def _run_trigger_send_against(port: int, script_body: str | None = None):
    """Drive trigger_send with the control plane unreachable. The wake path is
    stubbed so the test never touches tmux, and OFFICER_NAME is synthetic."""
    env = dict(os.environ)
    env.update(
        CABINET_ROOT=str(REPO),
        CABINET_SOURCE_REPO=str(REPO),
        REDIS_HOST="127.0.0.1",
        REDIS_PORT=str(port),
        TRIG_REDIS_HOST="127.0.0.1",
        TRIG_REDIS_PORT=str(port),
        OFFICER_NAME="marker-contract-test",
    )
    body = script_body or (
        '. "$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"\n'
        "trigger_wake_officer() { :; }\n"
        'trigger_send "marker-contract-target" "probe — plane is down" >/dev/null\n'
    )
    return subprocess.run(
        ["bash", "-c", body],
        text=True,
        capture_output=True,
        env=env,
        check=False,
        timeout=30,
    )


@pytest.fixture(scope="module")
def failed_send():
    if not TRIGGERS_LIB.is_file():
        pytest.skip("triggers.sh not present")
    result = _run_trigger_send_against(_dead_port())
    assert result.returncode != 0, (
        "trigger_send must FAIL when the XADD could not be queued; "
        f"rc={result.returncode} stderr={result.stderr!r}"
    )
    return result


def test_failed_trigger_send_emits_a_marker_the_detector_actually_scans_for(failed_send):
    """The load-bearing assertion: the line trigger_send really printed carries
    a token from the registry's OWN marker tuple. Not a re-typed copy of it."""
    hits = [m for m in JOB_ERROR_MARKERS if m in failed_send.stderr]
    assert hits, (
        "A failed trigger_send produced stderr that carries NONE of the "
        "outcome-watchdog's JOB_ERROR_MARKERS, so the watchdog's log-tail scan "
        "cannot see it — a dropped trigger would be silent.\n"
        f"  markers the detector scans for: {list(JOB_ERROR_MARKERS)}\n"
        f"  stderr actually emitted:        {failed_send.stderr.strip()!r}"
    )


def test_the_marker_the_watchdog_scan_would_hit_is_reproducible_end_to_end(failed_send):
    """Runs the detector's own selection logic (registry.py:1133) over the
    emitted line, so this test fails if the SCAN — not just the string — stops
    matching (e.g. if the marker moved into a line the scan filters out)."""
    from framework.watchdog.registry import _is_watchdog_self_report_line

    lines = [
        ln for ln in failed_send.stderr.splitlines()
        if not _is_watchdog_self_report_line(ln)
    ]
    tail = "\n".join(lines[-25:])
    hit = next((mk for mk in JOB_ERROR_MARKERS if mk in tail), None)
    assert hit is not None, (
        "The watchdog's exact tail-scan (last 25 lines, self-report lines "
        "filtered) finds no marker in the stderr a failed trigger_send emits.\n"
        f"  scanned tail: {tail!r}"
    )


def test_the_emitted_line_still_names_the_stream_and_the_sender(failed_send):
    """Guards the other direction: a future edit that satisfies the marker
    contract by printing a bare marker word, dropping the diagnostic content an
    operator needs, is not an acceptable way to make this file pass."""
    assert "trigger NOT queued" in failed_send.stderr
    assert "marker-contract-target" in failed_send.stderr
    assert "marker-contract-test" in failed_send.stderr


def test_a_successful_send_stays_silent_on_stderr(tmp_path):
    """Negative control — the marker must appear ONLY on failure. Without this,
    a line printed unconditionally would pass every assertion above while
    flooding the watchdog with permanent false positives."""
    import shutil
    import time

    if not shutil.which("redis-server"):
        pytest.skip("redis-server required")
    port = _dead_port()
    proc = subprocess.Popen(
        ["redis-server", "--bind", "127.0.0.1", "--port", str(port),
         "--protected-mode", "no", "--save", "", "--appendonly", "no",
         "--dir", str(tmp_path)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            probe = subprocess.run(
                ["redis-cli", "-h", "127.0.0.1", "-p", str(port), "PING"],
                text=True, capture_output=True, check=False)
            if probe.stdout.strip() == "PONG":
                break
            time.sleep(0.05)
        else:
            pytest.skip("redis-server did not come up")

        result = _run_trigger_send_against(port)
        assert result.returncode == 0, f"healthy send failed: {result.stderr!r}"
        leaked = [m for m in JOB_ERROR_MARKERS if m in result.stderr]
        assert not leaked, (
            f"a SUCCESSFUL trigger_send emitted watchdog error markers {leaked}: "
            f"{result.stderr!r}"
        )
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_registry_marker_tuple_is_non_empty():
    """Degenerate-end guard: if JOB_ERROR_MARKERS were ever emptied, every
    assertion above would pass vacuously in the 'no leak' direction and fail
    loudly in the 'has a marker' direction — pin the tuple as non-empty so the
    failure names the real cause."""
    assert len(JOB_ERROR_MARKERS) > 0
    assert all(isinstance(m, str) and m for m in JOB_ERROR_MARKERS)
