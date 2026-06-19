"""OAuth-only headless Claude call for the fidelity harness.

The locked architecture (docs/fidelity-harness-design-2026-06-18.md §59-72)
reaches Claude via the OAuth/Code path everywhere — the judge runs as a
`claude -p` headless agent billing the Max pool (CLAUDE_CODE_OAUTH_TOKEN in
CI). There is NO ANTHROPIC_API_KEY. This module is the drop-in replacement for
retrodiction's curl+x-api-key raw_llm / call_llm, preserving the
(payload, system) call shape so JUDGE_SYSTEM and judge_decision are reused
verbatim.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any

from framework.fidelity.retro import parse_json_block

_DEFAULT_MODEL = "claude-sonnet-4-6"
_TIMEOUT_S = 185

# LEAK ISOLATION (verified 2026-06-19): `claude -p` is a full Claude Code agent
# that auto-discovers the project's CLAUDE.md, .remember/ session buffer, and
# SessionStart hooks from its cwd. Run from the cabinet, the eval LLM (officer
# AND judge) therefore inherits POST-CUTOFF, this-session context — an
# out-of-band leak that bypasses the payload-level cutoff fence entirely (a bare
# `claude -p` from the cabinet returned the held-out answer, citing .remember).
# We run the eval LLM from a CLEAN temp cwd so it auto-discovers no project
# context, while leaving HOME intact so keychain/OAuth auth still works.
# RESIDUAL (graduation-blocker, see task #5 + design §leak): the user-global
# ~/.claude/CLAUDE.md still loads regardless of cwd; --bare would skip it but
# also disables keychain reads (kills OAuth). Hardening = a surrogate HOME that
# exposes only the auth marker, not CLAUDE.md.
_EVAL_CWD = None


def _eval_cwd() -> str:
    """A clean working dir for the eval `claude -p`, isolated from the cabinet
    project context (CLAUDE.md / .remember / SessionStart hooks). Created once
    per process; empty by construction so no CLAUDE.md is auto-discovered."""
    global _EVAL_CWD
    if _EVAL_CWD is None or not os.path.isdir(_EVAL_CWD):
        _EVAL_CWD = tempfile.mkdtemp(prefix="fidelity_eval_clean_")
    return _EVAL_CWD


class OAuthUnavailableError(RuntimeError):
    """Raised when neither an interactive OAuth login nor
    CLAUDE_CODE_OAUTH_TOKEN is available for headless invocation."""


def _build_argv(system: str, model: str) -> list[str]:
    """Construct the `claude -p` headless argv. The system prompt is appended
    (never a positional); the user payload is piped on stdin by the caller. No
    API-key flag is ever added — auth is OAuth (token in env or logged-in
    session)."""
    return [
        "claude", "-p",
        "--model", model,
        "--append-system-prompt", system,
        "--output-format", "text",
    ]


def oauth_raw_llm(payload: str, system: str, max_tokens: int = 1500,
                  model: str = _DEFAULT_MODEL) -> str | None:
    """Plain-text Claude call via `claude -p` (OAuth). Drop-in for
    retrodiction.raw_llm — same (payload, system) shape. Returns text or None.
    max_tokens is accepted for signature parity; `claude -p` manages its own
    output budget."""
    argv = _build_argv(system, model)
    # Inherit env so CLAUDE_CODE_OAUTH_TOKEN (CI) or the local OAuth session is
    # used. Strip ANTHROPIC_API_KEY so a stray key can never silently bill the
    # pay-as-you-go path instead of the Max pool.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    # Optional CLEAN EVAL HOME (user-global leak hardening, task #5). Point
    # CABINET_EVAL_HOME at a HOME where a DEDICATED clone Claude account is
    # logged in and which carries NO personal ~/.claude/CLAUDE.md /
    # screenpipe-memories.md / ~/.claude.json — that closes the user-global
    # context leak (the project/.remember leak is already closed by _eval_cwd).
    # Unset = inherit the real HOME: project context is still cwd-isolated, but
    # user-global memory loads, so live scores are NOT yet graduation-clean.
    _eval_home = os.environ.get("CABINET_EVAL_HOME")
    if _eval_home and os.path.isdir(_eval_home):
        env["HOME"] = _eval_home
    try:
        r = subprocess.run(
            argv, input=payload, capture_output=True, text=True,
            timeout=_TIMEOUT_S, env=env, cwd=_eval_cwd(),  # leak isolation
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if r.returncode != 0:
        return None
    out = (r.stdout or "").strip()
    return out or None


def oauth_json_llm(payload: str, system: str, max_tokens: int = 400,
                   model: str = _DEFAULT_MODEL, attempts: int = 2
                   ) -> dict[str, Any] | None:
    """JSON Claude call via OAuth. Drop-in for cl.call_llm — pass as the `llm=`
    arg to retrodiction.judge_decision. Returns the parsed dict or None.

    Retries once on an unparseable/empty result: `claude -p` is occasionally
    non-deterministic about emitting clean JSON (this surfaced live as an
    intermittent intent_verdict='error'). A single retry absorbs that transient
    flake; a persistent failure still returns None (the caller's error path)."""
    for _ in range(max(1, attempts)):
        text = oauth_raw_llm(payload, system, max_tokens=max_tokens, model=model)
        parsed = parse_json_block(text)
        if parsed is not None:
            return parsed
    return None
