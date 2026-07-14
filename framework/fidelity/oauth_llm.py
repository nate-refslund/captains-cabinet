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

import json
import os
import subprocess
import tempfile
from typing import Any

from framework.fidelity.retro import parse_json_block

_DEFAULT_MODEL = "claude-sonnet-4-6"
_TIMEOUT_S = 185

# Structured-output default for judge calls (AUD-11, audit #31): every judge
# rubric expects a free-form JSON object, so the CLI-side contract is simply
# "a JSON object" — --json-schema makes the CLI itself enforce/repair that,
# which is what killed the old parse-retry loop.
_ANY_OBJECT_SCHEMA: dict = {"type": "object"}

# Supplementary cost signal (B5.8 credit governance): the --output-format json
# envelope carries total_cost_usd per call. The PRIMARY meter stays the OAuth
# usage API — these module counters are best-effort telemetry only.
LAST_COST_USD: float | None = None
TOTAL_COST_USD: float = 0.0


def _record_cost(cost: Any) -> None:
    global LAST_COST_USD, TOTAL_COST_USD
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        LAST_COST_USD = float(cost)
        TOTAL_COST_USD += float(cost)

# LEAK ISOLATION (verified 2026-06-19): `claude -p` is a full Claude Code agent
# that auto-discovers BOTH (a) project context — CLAUDE.md, .remember/ session
# buffer, SessionStart hooks from its cwd — and (b) user-global context —
# ~/.claude/CLAUDE.md (screenpipe-memories) + ~/.claude.json. Run from the
# cabinet, the eval LLM (officer AND judge) inherits POST-CUTOFF, this-session
# context — an out-of-band leak past the payload-level cutoff fence (a bare
# `claude -p` from the cabinet returned the held-out answer, citing .remember;
# and the user-global memory leaked an answer to an internal-product-name
# probe). BOTH tiers are now closed:
#   (a) PROJECT tier: run the eval LLM from a CLEAN temp cwd (_eval_cwd) so it
#       auto-discovers no project CLAUDE.md/.remember/hooks.
#   (b) USER-GLOBAL tier: pass `--setting-sources project,local` so the `user`
#       source (~/.claude/CLAUDE.md + memory) is NOT loaded. Verified: the
#       internal-product-name probe returns UNKNOWN with the flag, AUTH_OK still works — HOME is
#       left intact so the macOS keychain / OAuth is untouched (overriding HOME
#       breaks the keychain, the dead end the earlier CABINET_EVAL_HOME approach
#       hit). No clean-HOME, no separate login, no keychain risk.
_SETTING_SOURCES = "project,local"  # drop `user` -> no user-global CLAUDE.md/memory
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


def _build_argv(system: str, model: str, output_format: str = "text",
                json_schema: dict | None = None) -> list[str]:
    """Construct the `claude -p` headless argv. The system prompt is appended
    (never a positional); the user payload is piped on stdin by the caller. No
    API-key flag is ever added — auth is OAuth (token in env or logged-in
    session). With output_format="json" + a json_schema, the CLI returns a
    result envelope whose `structured_output` is schema-validated JSON."""
    argv = [
        "claude", "-p",
        "--model", model,
        "--append-system-prompt", system,
        "--setting-sources", _SETTING_SOURCES,  # drop user-global memory (leak)
        "--output-format", output_format,
    ]
    if json_schema is not None:
        argv += ["--json-schema", json.dumps(json_schema)]
    return argv


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
    # Strip ANTHROPIC_API_KEY so a stray key can never silently bill the
    # pay-as-you-go path instead of the Max pool. HOME is left INTACT — the
    # macOS keychain / OAuth is HOME-anchored, and overriding it breaks auth
    # (the keychain-not-found dead end). The user-global leak is closed by the
    # --setting-sources flag in _build_argv, not by a fake HOME.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    try:
        r = subprocess.run(
            argv, input=payload, capture_output=True, text=True,
            timeout=_TIMEOUT_S, env=env, cwd=_eval_cwd(),  # project-tier isolation
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if r.returncode != 0:
        return None
    out = (r.stdout or "").strip()
    return out or None


def oauth_json_llm(payload: str, system: str, max_tokens: int = 400,
                   model: str = _DEFAULT_MODEL,
                   schema: dict | None = None) -> dict[str, Any] | None:
    """JSON Claude call via OAuth. Drop-in for cl.call_llm — pass as the `llm=`
    arg to retrodiction.judge_decision. Returns the parsed dict or None.

    AUD-11 (audit #31): judge calls now use `--output-format json
    --json-schema` so the CLI enforces valid JSON structurally
    (`structured_output` in the result envelope) — this replaced the old
    2-attempt parse-retry loop over fenced text (the intermittent
    intent_verdict='error' flake). `schema` defaults to the permissive
    any-object schema; pass a rubric-specific one to tighten. Auth stays
    OAuth-ONLY by design (NO --bare: bare mode never reads OAuth/keychain and
    would leave judges with no auth path — judges must bill the Max pool).
    The envelope's total_cost_usd is recorded in LAST_COST_USD/TOTAL_COST_USD
    as a supplementary B5.8 signal. max_tokens is accepted for signature
    parity; `claude -p` manages its own output budget."""
    argv = _build_argv(system, model, output_format="json",
                       json_schema=schema if schema is not None
                       else _ANY_OBJECT_SCHEMA)
    # Same env/cwd isolation as oauth_raw_llm: strip ANTHROPIC_API_KEY (Max
    # pool only), keep HOME (keychain), run from the clean temp cwd.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    try:
        r = subprocess.run(
            argv, input=payload, capture_output=True, text=True,
            timeout=_TIMEOUT_S, env=env, cwd=_eval_cwd(),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if r.returncode != 0:
        return None
    try:
        envelope = json.loads((r.stdout or "").strip() or "null")
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(envelope, dict) or envelope.get("is_error"):
        return None
    _record_cost(envelope.get("total_cost_usd"))
    structured = envelope.get("structured_output")
    if isinstance(structured, dict):
        return structured
    # Defensive single-pass fallback (no retry loop): older CLIs / edge cases
    # put the text answer in `result` — parse a fenced block once.
    result_text = envelope.get("result")
    if isinstance(result_text, str) and result_text.strip():
        parsed = parse_json_block(result_text)
        if isinstance(parsed, dict):
            return parsed
    return None
