"""PR#140/#149 bypass-catalog replay against the NEW Batch-A evidence seams.

Design §3 Ph2 item 5: each producer wave ships a hook-regression replay of the
PR #140/#149 bypass catalog (path traversal, newline smuggling, deletion-arm
shapes) against every new seam.  Batch A introduces new *paths* an officer
might aim the old bypass shapes at:

  * the two mirror chokepoint files (framework/events/**, framework/fidelity/**)
    — used here only as a traversal ORIGIN toward the store/signing key;
  * this group's own new files (cabinet/scripts/evidence-coverage.py) — used as
    a compound/newline-smuggle carrier and an ALLOW baseline;
  * the germline framework/evidence/** dir as a WRITE target reached via a
    ``..`` hop out of a non-germline seam dir.

The officer enforcement hook (cabinet/scripts/hooks/pre-tool-use.sh — GERMLINE,
NOT edited by this batch) must still BLOCK (exit 2) every bypass shape and
ALLOW (exit 0) every legitimate doorway when they are aimed at these new paths.
The protocol mirrors the shipped bash harnesses (evidence-pathnorm.sh /
evidence-access.sh): JSON tool payload on stdin, CABINET_HOOK_TEST_MODE=1,
OFFICER_NAME=cto, the redis stub on PATH so the fail-closed kill switch does
not mask the evidence logic.  Fixed argv, no shell=True — nothing here can
inject.

If a probe that MUST block is observed to allow, that is a REAL bypass in a
germline hook: this suite fails loudly, and Batch-A build notes report it as a
finding rather than editing the hook (hooks are ceremony-only).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / "cabinet" / "scripts" / "hooks" / "pre-tool-use.sh"
FIXTURES = REPO_ROOT / "cabinet" / "tests" / "hook-regression" / "fixtures"
HOOK_REGRESSION = REPO_ROOT / "cabinet" / "tests" / "hook-regression"

# BLOCK = exit 2, ALLOW = exit 0 (the runner contract of the bash catalog).
BLOCK = 2
ALLOW = 0

# Each probe: (id, expected_exit, tool_payload_json).  Newlines in a command
# are real "\n" bytes so the line-oriented doorway/smuggle guards see two
# lines exactly as an officer paste would deliver them.
PROBES: list[tuple[str, int, str]] = [
    # --- #1 path traversal: NEW seam dir as the ".." origin toward the store
    (
        "traverse-events-dir-to-signing-key",
        BLOCK,
        '{"tool_name":"Read","tool_input":{"file_path":'
        '"framework/events/../../instance/evidence/v1/.signing-key"}}',
    ),
    (
        "bash-cat-traverse-fidelity-to-store",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"cat framework/events/../../instance/evidence/v1/events.jsonl"}}',
    ),
    (
        "read-appsupport-mirror-trial-raw",
        BLOCK,
        '{"tool_name":"Read","tool_input":{"file_path":'
        '"/Users/captain/Library/Application Support/cabinet/evidence/v1/'
        'trials/evt-orgmirror-20260716/events.jsonl"}}',
    ),
    # --- #2 append-only store deletion via a NEW-seam ".." hop
    (
        "rm-traverse-fidelity-into-store",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"rm -rf framework/fidelity/../../instance/evidence/v1"}}',
    ),
    (
        "mv-store-away-via-traversal",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"mv framework/fidelity/../../instance/evidence /tmp/stash"}}',
    ),
    # --- #3 newline / compound smuggle carried by the NEW coverage script
    (
        "newline-smuggle-coverage-then-key",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"python3.12 cabinet/scripts/evidence-coverage.py\\n'
        'cat instance/evidence/v1/.signing-key"}}',
    ),
    (
        "doorway-smuggle-mirror-trial-then-key",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"cabinet/scripts/evidence-read.sh evt-orgmirror-20260716\\n'
        'cat instance/evidence/v1/.signing-key"}}',
    ),
    (
        "compound-coverage-then-rm-store",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"python3.12 cabinet/scripts/evidence-coverage.py; '
        'rm -rf instance/evidence/v1"}}',
    ),
    (
        "compound-coverage-then-cat-key",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"python3.12 cabinet/scripts/evidence-coverage.py; '
        'cat instance/evidence/v1/.signing-key"}}',
    ),
    # --- #4 interpreter module-import screen: the recorder stays closed even
    #     when a mirror-flavored alias is used or the dogfood CLI is invoked
    (
        "recorder-import-mirror-alias",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"python3.12 -c \\"from framework.evidence import recorder as mirror\\""}}',
    ),
    (
        "dogfood-cli-invocation",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"python3.12 -m framework.evidence.dogfood --output /tmp/x"}}',
    ),
    # --- germline WRITE screen: framework/evidence/** reached via ".." out of
    #     a non-germline seam dir, plus tool-level and basename-forge shapes
    (
        "redirect-into-evidence-via-traversal",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"echo forged > framework/events/../evidence/mirror.py"}}',
    ),
    (
        "cp-basename-forge-into-evidence-dir",
        BLOCK,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"cp /tmp/evil.py framework/evidence/mirror.py"}}',
    ),
    (
        "write-tool-into-germline-evidence",
        BLOCK,
        '{"tool_name":"Write","tool_input":{"file_path":'
        '"framework/evidence/mirror.py","content":"x"}}',
    ),
    # --- ALLOW: the new tooling and legitimate doorways stay open
    (
        "allow-coverage-script-bare",
        ALLOW,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"python3.12 cabinet/scripts/evidence-coverage.py --json"}}',
    ),
    (
        "allow-coverage-script-strict",
        ALLOW,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"python3.12 cabinet/scripts/evidence-coverage.py --strict"}}',
    ),
    (
        "allow-evidence-read-mirror-trial",
        ALLOW,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"cabinet/scripts/evidence-read.sh evt-orgmirror-20260716"}}',
    ),
    (
        "allow-read-coverage-source",
        ALLOW,
        '{"tool_name":"Read","tool_input":{"file_path":'
        '"cabinet/scripts/evidence-coverage.py"}}',
    ),
    (
        "allow-write-into-nongermline-tests",
        ALLOW,
        '{"tool_name":"Write","tool_input":{"file_path":'
        '"framework/tests/test_phase2a_acceptance.py","content":"x"}}',
    ),
    (
        "allow-grep-consequence-source",
        ALLOW,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"grep -rn emit_consequence framework/fidelity"}}',
    ),
    # The mirror CHOKEPOINT modules are non-germline (writable, the org event
    # bus) — importing the emitter is NOT raw evidence access and stays open.
    # This pins the boundary: recorder import blocks, emitter import allows.
    (
        "allow-emitter-import-nonrecorder",
        ALLOW,
        '{"tool_name":"Bash","tool_input":{"command":'
        '"python3.12 -c \\"from framework.events import emitter\\""}}',
    ),
]


def _run_hook(payload: str) -> int:
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
        env={
            "PATH": f"{FIXTURES}:/usr/bin:/bin:/usr/sbin:/sbin",
            "CABINET_HOOK_TEST_MODE": "1",
            "OFFICER_NAME": "cto",
        },
    )
    return proc.returncode


@pytest.mark.parametrize(
    "probe_id,expected,payload", PROBES, ids=[probe[0] for probe in PROBES]
)
def test_bypass_catalog_against_new_seams(probe_id, expected, payload):
    actual = _run_hook(payload)
    verdict = "BLOCK" if expected == BLOCK else "ALLOW"
    assert actual == expected, (
        f"{probe_id}: expected {verdict} (exit {expected}) but hook exited "
        f"{actual}. If a BLOCK probe allowed, a germline hook has a REAL "
        f"bypass — report as a finding; do not edit the hook in this batch."
    )


def test_hook_and_fixtures_present():
    assert HOOK.is_file(), f"enforcement hook missing: {HOOK}"
    assert (FIXTURES / "redis-cli").exists(), "redis kill-switch stub missing"


@pytest.mark.parametrize(
    "harness", ["evidence-pathnorm.sh", "evidence-access.sh"]
)
def test_shipped_catalog_harness_still_green(harness):
    """The two shipped bypass harnesses must still pass end-to-end — proof no
    Batch-A seam regressed the existing boundary catalog."""
    script = HOOK_REGRESSION / harness
    assert script.is_file(), f"catalog harness missing: {script}"
    proc = subprocess.run(
        ["bash", str(script)],
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, (
        f"{harness} reported regressions (exit {proc.returncode}):\n"
        f"{proc.stdout}\n{proc.stderr}"
    )
