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
#
# ASSEMBLED, NOT LITERAL — and do not "simplify" this back into one string. Two
# of these fixtures are convincing enough that the repo's own secret scanner
# flags them (gitleaks `generic-api-key` and `slack-webhook-url`), which is the
# scanner working. The alternative was allowlisting this whole file in
# .gitleaks.toml, which would mean a REAL secret pasted here later goes
# unscanned forever — an unacceptable trade in a file that exists because
# secrets leaked. Joining at runtime keeps the scanner at full strength over
# every line while the assertions still run against the exact byte sequence.
def _j(*parts: str) -> str:
    return "".join(parts)


SECRET_SHAPES = [
    ("env assignment: api token",
     _j("MONDAY_API_TOKEN=", "eyJhbGciOiJIUzI1NiJ9.SYNTHETICSYNTHETIC.abcdefghijklmnop")),
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
     _j("https://hooks.slack.com/", "services/T00000000/B00000000/SYNTHETIC0000000000000000")),
    ("discord webhook",
     "https://discord.com/api/webhooks/000000000000000000/SYNTHETIC00000000000000000"),
    # --- the 2026-07-29 finding: a value with NO token-ish name beside it ----
    # Every rule but #5 keys on a token-ish word in the adjacent NAME, so a
    # credential parked behind a two-letter variable was logged verbatim even
    # though rule 5 claimed the nameless class was handled. These four FAIL
    # against the pre-change hook. Sentry and PostHog carry unambiguous vendor
    # prefixes, so the fix is prefix-anchored and cost 0 new redactions across
    # 8.3 MB of this repo's tracked text. The class rule 5 still cannot reach
    # is stated as L1 in the hook, and pinned by the claim-surface test below.
    ("sentry org token, no name beside it",
     _j("sntrys_", "SYNTHETIC000000000000000000000000000000000000000000")),
    ("sentry user token behind a two-letter name",
     _j('ST="', "sntryu_", 'SYNTHETIC000000000000000000000000000000000000000000"')),
    ("posthog personal key behind a two-letter name",
     _j('PH="', "phx_", 'SYNTHETIC0000000000000000000000"')),
    ("posthog project key, no name beside it",
     _j("phc_", "SYNTHETIC0000000000000000000000")),
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
    # Controls for the 2026-07-29 vendor-prefix arms. The prefixes are short
    # enough to collide with ordinary words if the length bound or the
    # underscore ever gets relaxed, so pin the near-misses rather than trusting
    # the regex to stay tight.
    "phase_4 digest re-bound and verifying against HEAD",
    "commit 4c7d42e7f1a9b3c5d7e9f1a3b5c7d9e1f3a5b7c9 landed on master",
    "photos_api_v2 returned 200 in 0.34s",
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


def test_the_stated_limits_survive_in_the_live_hook():
    """The 2026-07-29 defect was a CLAIM defect, so this is its sensor.

    Rule 5 read "caught regardless of surrounding = or quotes" while covering
    four vendor prefixes, which invited the reading that a credential with no
    name beside it was handled. Three real ones were not. The fix closed what a
    prefix can close and WROTE DOWN the rest (L1: no prefix and no name; L2:
    separators other than `=`), because the alternative — a silent gap under a
    confident sentence — is the failure this hook keeps re-learning.

    A behavioural arm cannot pin a gap without also forbidding its fix, so this
    pins the claim surface instead: delete the caveat while the hole is still
    open and this goes red. If you CLOSE L1 or L2, rewrite the block and this
    test together — that edit is the point at which someone must re-measure the
    false-positive cost on ordinary output.
    """
    text = HOOK.read_text()
    assert "LIMITS — what redaction does NOT catch" in text, (
        "the LIMITS block was removed from the hook; either the gaps were "
        "closed (then update this test) or the claim silently widened again"
    )
    for marker in ("L1.", "L2."):
        assert marker in text, f"limit {marker} lost from the hook's claim surface"
    assert "do not read this rule" in text, (
        "rule 5's scope disclaimer was dropped — it is what stops the next "
        "reader assuming nameless credentials are covered"
    )


def test_webhook_host_stays_legible_so_the_log_is_still_useful():
    """Redaction eats the secret path token, not the endpoint's identity — an
    operator must still be able to see WHICH integration was touched."""
    out = _redact(
        "hitting https://hook.eu2.make.com/synth0000000000000000000000000 now")
    assert "hook.eu2.make.com" in out and "[REDACTED]" in out
    assert "synth00000" not in out
