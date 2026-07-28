"""The PostToolUse hook's secret redaction had no sensor. Now it has one.

WHY THIS FILE EXISTS. ``cabinet/scripts/hooks/post-tool-use.sh`` writes every
tool call's input and truncated output to ``memory/logs/<date>.jsonl``, which
is durable, backed up by the daily drill, and (for anything that reaches the
memory store) embedded by a third-party embeddings API. ``redact_secrets()``
is the only thing standing between an officer running ``cat cabinet/.env`` and
that credential living in the log forever. Until 2026-07-28 nothing tested it,
and a survey of this deployment's own logs found real credentials on disk:
every ``*_TOKEN`` / ``*_API_KEY`` / ``*_SECRET`` name was correctly redacted,
and every ``*_WEBHOOK`` name was not — because a webhook URL carries no
token-ish word in its NAME even though the URL itself IS the capability.

WIRED TO THE LIVE ARTIFACT, not to a copy. The test extracts the shell function
out of the real hook and runs it, so a future edit to the hook is what this
test measures. A fixture reimplementation would only ever assert that the
fixture agrees with itself.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
HOOK = REPO / "cabinet" / "scripts" / "hooks" / "post-tool-use.sh"

# Every value below is SYNTHETIC. Real credentials never appear in a fixture.
SECRET_SHAPES = [
    ("env assignment: api token",
     "MONDAY_API_TOKEN=eyJhbGciOiJIUzI1NiJ9.SYNTHETICSYNTHETIC.abcdefghijklmnop"),
    ("env assignment: api key",
     "VOYAGE_API_KEY=pa-SYNTHETIC0000000000000000000000000000000"),
    ("env assignment: bare token name",
     "VERCEL_TOKEN=vcpSYNTHETIC0000000000000000000000000000000000"),
    ("env assignment: secret name",
     "CABINET_PEER_SECRET_PERSONAL=SYNTHETIC00000000000000000000"),
    ("telegram bot token", "TELEGRAM_BOT_TOKEN=1234567890:AASYNTHsyntheticSYNTHETICsynthetic00"),
    ("github classic pat", "GITHUB_PAT=ghp_SYNTHETIC000000000000000000000000000"),
    ("url-embedded password",
     "NEON_CONNECTION_STRING=postgresql://user:SYNTHPASSWORD@ep-x.aws.neon.tech/neondb"),
    ("json body", '{"api_key": "SYNTHETIC0000000000000000000000"}'),
    ("authorization header", "Authorization: Bearer SYNTHETIC0000000000000000000000"),
    # --- the 2026-07-28 finding: capability URLs -----------------------------
    ("make webhook assignment",
     "MSGRAPH_SEND_WEBHOOK=https://hook.eu2.make.com/synth0000000000000000000000000"),
    ("make webhook assignment (write lane)",
     "MSGRAPH_WRITE_WEBHOOK=https://hook.eu2.make.com/synth0000000000000000000000000"),
    ("make webhook quoted in prose",
     "Write scenario 9437751 is ACTIVE (webhook "
     "`https://hook.eu2.make.com/synth0000000000000000000000000`) and wired."),
    ("make webhook in a json body",
     '{"webhook": "https://hook.eu2.make.com/synth0000000000000000000000000"}'),
    ("slack incoming webhook",
     "https://hooks.slack.com/services/T00000000/B00000000/SYNTHETIC0000000000000000"),
    ("discord webhook",
     "https://discord.com/api/webhooks/000000000000000000/SYNTHETIC00000000000000000"),
]

# Ordinary tool output that must survive intact — over-redaction destroys the
# log's whole reason to exist, and a log nobody can read gets turned off.
INNOCUOUS = [
    "ok: 3133 passed, 0 failed",
    "modified:   framework/acting/action_lane.py",
    "https://github.com/nate-refslund/captains-cabinet/pull/265",
    "https://api.monday.com/v2",
    "if (token == expected) { return true }",
    "authToken = await getSession()",
    "grep -n 'webhook' cabinet/scripts/hooks/post-tool-use.sh",
]


def _redact(payload: str) -> str:
    """Run the REAL redact_secrets() out of the live hook."""
    script = (
        f'eval "$(sed -n \'/^redact_secrets() {{/,/^}}$/p\' {HOOK!s})"\n'
        'redact_secrets\n'
    )
    proc = subprocess.run(
        ["bash", "-c", script], input=payload, capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"hook function failed: {proc.stderr[:300]}"
    return proc.stdout


def test_the_extractor_is_not_vacuous():
    """If the sed extraction stopped matching, every assertion below would be
    measuring an empty function. Prove the function was actually loaded."""
    assert HOOK.is_file(), f"the live hook moved: {HOOK}"
    out = _redact("Authorization: Bearer SYNTHETIC0000000000000000000000")
    assert "[REDACTED]" in out, "redact_secrets() was not loaded from the hook"


@pytest.mark.parametrize("label,payload", SECRET_SHAPES, ids=[s[0] for s in SECRET_SHAPES])
def test_secret_shapes_are_redacted(label, payload):
    out = _redact(payload)
    assert "[REDACTED]" in out, f"{label}: nothing was redacted"
    assert "SYNTH" not in out.upper().replace("SYNTHETIC-OK", ""), (
        f"{label}: the secret span survived redaction -> {out.strip()!r}"
    )


@pytest.mark.parametrize("payload", INNOCUOUS)
def test_ordinary_tool_output_survives(payload):
    assert _redact(payload).strip() == payload, "over-redacted ordinary output"


def test_webhook_host_stays_legible_so_the_log_is_still_useful():
    """Redaction eats the secret path token, not the endpoint's identity — an
    operator must still be able to see WHICH integration was touched."""
    out = _redact(
        "hitting https://hook.eu2.make.com/synth0000000000000000000000000 now")
    assert "hook.eu2.make.com" in out and "[REDACTED]" in out
    assert "synth00000" not in out
