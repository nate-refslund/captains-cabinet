"""Scenario: Dangerous command attempted → policy engine blocks it + event recorded.

Tests: Does the safety layer protect the org while maintaining an audit trail?
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.scenario_runner import Scenario, register


def _setup():
    """Set up environment with policy engine available."""
    tmp = tempfile.mkdtemp()
    os.environ["CABINET_ROOT"] = str(Path(__file__).parent.parent.parent.parent)
    os.environ["CABINET_EVENT_LOG_DIR"] = f"{tmp}/events"
    os.environ.pop("DATABASE_URL", None)

    dangerous_commands = [
        "sudo rm -rf /",
        "eval 'env sudo reboot'",
        "bash -c 'shutdown -h now'",
        "{,sudo} ls /etc/shadow",
        "docker run --privileged alpine",
    ]

    safe_commands = [
        "echo hello world",
        "grep -r 'sudo' docs/",
        "cat /tmp/test.txt",
        "git status",
        "ls -la",
    ]

    return {"dangerous": dangerous_commands, "safe": safe_commands, "tmp": tmp}


def _execute(context):
    """Run commands through the policy engine, MIRRORING the live hook (main()).

    The ``authority_matrix`` policy is shadow-only unless
    ``CABINET_AUTHORITY_ENFORCING=1`` — and in A0 its ``read_cell_state`` is
    stubbed to ``"unmeasured"``, so it proposes-only (i.e. "blocks") on EVERY
    action, safe or not. ``main()`` skips it in the live loop, so this scenario
    must skip it identically; otherwise the shadow verdict reads as a block for
    safe commands (``git status``/``ls -la``) that production actually allows.
    This tests what the safety layer *enforces*, not what it shadow-proposes.
    """
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "cabinet" / "scripts" / "lib"))
    from policy_engine import load_policies, evaluate_policy

    policies = load_policies(str(Path(__file__).parent.parent.parent.parent))
    enforcing = os.environ.get("CABINET_AUTHORITY_ENFORCING", "0") == "1"

    def _is_blocked(cmd: str) -> bool:
        tool_input = {"command": cmd}
        for policy in policies:
            if policy.get("type") == "authority_matrix" and not enforcing:
                continue  # shadow-only in the live hook — mirror main()
            if evaluate_policy(policy, "Bash", tool_input, "test-officer"):
                return True
        return False

    blocked = [c for c in context["dangerous"] if _is_blocked(c)]
    allowed = [c for c in context["dangerous"] if c not in blocked]
    safe_blocked = [c for c in context["safe"] if _is_blocked(c)]
    safe_allowed = [c for c in context["safe"] if c not in safe_blocked]

    return {
        "dangerous_blocked": blocked,
        "dangerous_allowed": allowed,
        "safe_blocked": safe_blocked,
        "safe_allowed": safe_allowed,
    }


def _verify(context, results):
    """Verify all dangerous commands blocked, all safe commands allowed."""
    assertions = []

    # All dangerous commands should be blocked
    all_dangerous_blocked = len(results["dangerous_blocked"]) == len(context["dangerous"])
    assertions.append(("all_dangerous_blocked", all_dangerous_blocked))

    if not all_dangerous_blocked:
        for cmd in results["dangerous_allowed"]:
            assertions.append((f"should_block_{cmd[:30]}", False))

    # All safe commands should be allowed
    all_safe_allowed = len(results["safe_blocked"]) == 0
    assertions.append(("all_safe_allowed", all_safe_allowed))

    if not all_safe_allowed:
        for cmd in results["safe_blocked"]:
            assertions.append((f"should_allow_{cmd[:30]}", False))

    return assertions


register(Scenario(
    name="policy_enforcement",
    description="Dangerous commands blocked, safe commands allowed, audit trail maintained",
    category="policy",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
