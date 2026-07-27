"""A4 — Mechanical low-risk deploy classifier (Component 6, NON-PROD only).

`classify_deploy` is the deterministic gate the `deploy_nonprod` verdict
`classifier` branch calls (`_eval_authority_matrix`, §Component 2). It is
MECHANICAL, not judged: it returns `"auto"` iff ALL of the following hold,
else `"propose_only"` (fail-closed):

  1. Every changed file matches a `deploy.safe_globs` entry.
  2. NO changed file matches a `deploy.high_risk_globs` entry
     (migrations / schema / auth / payment / stripe / billing / neon /
     vercel / .env / policies / base-schemas).
  3. CI status == ``success``.
  4. The latest preview deployment state == ``READY``.

Per FIX-6 the auto output targets PREVIEW/STAGING ONLY — a prod deploy can
NEVER resolve to auto. `classify_deploy` independently re-checks the target
(via the shared `classify_action`, plus an explicit `target` field) and
fail-closes to `"propose_only"` on any prod signal, so even if the caller
mis-routes a prod command into this branch it cannot leak an auto verdict.

FAIL-CLOSED everywhere: any unreadable signal (a diff/CI/preview fn that
raises or returns an unknown value), an unknown glob set, an empty diff, an
unrecognized file that matches no safe glob, or the regex backstop firing on
an unknown top-level dir containing a `.sql` / auth / payment / credential
token -> `"propose_only"`.

The three real signals (git diff, GitHub CI status, Vercel preview state) are
INJECTED as pure functions (`git_diff_fn`, `ci_status_fn`, `preview_state_fn`),
each taking `tool_input` and returning its value — so this module makes NO real
git / GitHub / Vercel calls and is fully testable with fakes.

Standalone (SHADOW-ONLY): this module is NOT wired into `policy_engine` or the
`pre-tool-use.sh` hook here — integration is a later Captain-authorized pass.
See docs/authority-matrix-design-2026-06-19.md §Component 6 + FIX-6.
"""
from __future__ import annotations

import fnmatch
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

# Repo root on sys.path so the shared classifier imports cleanly when this
# module is used standalone (same convention as the sibling judge modules).
_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

from framework.authority.classifier import (  # noqa: E402
    _DEPLOY_PROD as _PROD_ACTION_TYPES,
    classify_action,
)

# The two verdict strings this classifier may return.
AUTO = "auto"
PROPOSE_ONLY = "propose_only"

# Action_types that mean a PROD deploy target (the never-auto frozenset rows)
# are imported above from the classifier's _DEPLOY_PROD — ONE declared source,
# shared with the authority matrix's deploy_prod ceiling pin.

# Tokens an explicit `target` field may carry to mean production.
_PROD_TARGET_TOKENS = ("prod", "production", "live", "main", "master")

# Required CI / preview success sentinels.
_CI_SUCCESS = "success"
_PREVIEW_READY = "READY"

# Regex backstop: an unknown new top-level dir whose path carries a `.sql`
# extension or an auth / payment / credential token is treated conservatively
# as high-risk even when no enumerated glob matches it [FIX-6 gotcha].
_BACKSTOP_RE = re.compile(
    r"(?:\.sql$)"
    r"|(?:(?:^|/)(?:auth|authentication|oauth|jwt|payment|payments|"
    r"stripe|billing|checkout|subscription|secret|secrets|credential|"
    r"credentials|token)\w*)",
    re.IGNORECASE,
)


def matches_any_glob(path: str, globs: Sequence[str]) -> bool:
    """True iff `path` matches any glob in `globs`.

    Supports the `**` (any number of path segments, including zero) and `*`
    (a single segment, fnmatch semantics) wildcards used in the matrix's
    `safe_globs` / `high_risk_globs`. Matching is anchored to the full path.
    """
    if not isinstance(path, str) or not path:
        return False
    norm = _normpath(path)
    for glob in globs or ():
        if not isinstance(glob, str) or not glob:
            continue
        if _glob_match(norm, glob):
            return True
    return False


def _glob_match(path: str, glob: str) -> bool:
    """Match `path` against a single glob with `**` support.

    `**` matches any sequence of characters including `/` (zero or more path
    segments); a lone `*` matches within a single segment. Falls back to
    fnmatch for the no-`**` case. A leading `**/` also matches a bare filename
    at the root (e.g. `**/*.md` matches `a.md`).
    """
    if "**" not in glob:
        return fnmatch.fnmatchcase(path, glob)

    # Translate the glob to a regex, treating `**` specially.
    regex = _glob_to_regex(glob)
    if re.match(regex, path):
        return True
    # `**/` as a prefix should also match a root-level file (zero leading dirs).
    if glob.startswith("**/"):
        return _glob_match(path, glob[3:])
    return False


def _glob_to_regex(glob: str) -> str:
    out = ["^"]
    i = 0
    n = len(glob)
    while i < n:
        c = glob[i]
        if c == "*":
            if i + 1 < n and glob[i + 1] == "*":
                # `**` -> any chars incl. `/`
                out.append(".*")
                i += 2
                # consume an immediately-following `/` so `**/x` matches `x`
                if i < n and glob[i] == "/":
                    out.append("(?:.*/)?")
                    i += 1
                continue
            # single `*` -> any chars except `/`
            out.append("[^/]*")
            i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(c))
        i += 1
    out.append("$")
    return "".join(out)


def _safe_call(fn: Callable[[dict], Any], tool_input: dict) -> Any:
    """Invoke an injected signal fn; any exception -> sentinel that gates."""
    try:
        return fn(tool_input)
    except Exception:
        return _UNREADABLE


_UNREADABLE = object()


def _targets_prod(tool_input: dict) -> bool:
    """Fail-conservative prod-target detection.

    True if the shared classifier resolves the call to a prod deploy
    action_type, OR an explicit `target`/`environment` field names production.
    Used as an independent backstop so this NON-PROD-only classifier can never
    emit auto for a prod command, regardless of how it was routed [FIX-6].
    """
    if not isinstance(tool_input, dict):
        # Unknown shape -> conservative: treat as prod (gate).
        return True

    # Explicit target field.
    for key in ("target", "environment", "env"):
        val = tool_input.get(key)
        if isinstance(val, str):
            low = val.strip().lower()
            if any(tok in low for tok in _PROD_TARGET_TOKENS):
                return True

    # Shared classifier — deploy commands arrive as Bash tool calls.
    try:
        action_type = classify_action("Bash", tool_input)
    except Exception:
        return True  # classifier unreadable -> conservative gate
    if action_type in _PROD_ACTION_TYPES:
        return True
    return False


def classify_deploy(
    tool_input: dict,
    deploy_cfg: Any,
    *,
    git_diff_fn: Callable[[dict], Any],
    ci_status_fn: Callable[[dict], Any],
    preview_state_fn: Callable[[dict], Any],
) -> str:
    """Decide the `deploy_nonprod` classifier verdict: `"auto"` | `"propose_only"`.

    Returns `"auto"` ONLY when the target is non-prod AND all four low-risk
    signals hold; otherwise `"propose_only"` (fail-closed). See module docstring.

    Args:
        tool_input: the raw tool call (carries the deploy command/target).
        deploy_cfg: the matrix `deploy` block — `{safe_globs, high_risk_globs}`.
        git_diff_fn: pure fn(tool_input) -> list[str] of changed file paths.
        ci_status_fn: pure fn(tool_input) -> CI state str ("success" == green).
        preview_state_fn: pure fn(tool_input) -> Vercel preview state
            ("READY" == ready).
    """
    # (0) Prod target can NEVER auto — independent of every other signal.
    if _targets_prod(tool_input):
        return PROPOSE_ONLY

    # Deploy config must be a dict carrying both glob lists.
    if not isinstance(deploy_cfg, dict):
        return PROPOSE_ONLY
    safe_globs = deploy_cfg.get("safe_globs")
    high_risk_globs = deploy_cfg.get("high_risk_globs")
    if not isinstance(safe_globs, list) or not safe_globs:
        return PROPOSE_ONLY
    if not isinstance(high_risk_globs, list):
        return PROPOSE_ONLY

    # (1)+(2) Diff scope: every file safe, no file high-risk, none backstopped.
    changed = _safe_call(git_diff_fn, tool_input)
    if changed is _UNREADABLE or not isinstance(changed, (list, tuple)):
        return PROPOSE_ONLY
    if len(changed) == 0:
        # No changed files is not a positive low-risk signal.
        return PROPOSE_ONLY
    for f in changed:
        if not isinstance(f, str) or not f:
            return PROPOSE_ONLY
        if matches_any_glob(f, high_risk_globs):
            return PROPOSE_ONLY
        if _backstop_high_risk(f):
            return PROPOSE_ONLY
        if not matches_any_glob(f, safe_globs):
            # Unrecognized file: not provably safe -> gate.
            return PROPOSE_ONLY

    # (3) CI must be green.
    ci = _safe_call(ci_status_fn, tool_input)
    if ci is _UNREADABLE or not isinstance(ci, str) or ci.strip().lower() != _CI_SUCCESS:
        return PROPOSE_ONLY

    # (4) Preview deployment must be READY.
    preview = _safe_call(preview_state_fn, tool_input)
    if (
        preview is _UNREADABLE
        or not isinstance(preview, str)
        or preview.strip().upper() != _PREVIEW_READY
    ):
        return PROPOSE_ONLY

    return AUTO


def _backstop_high_risk(path: str) -> bool:
    """Regex backstop for an unknown new top-level dir.

    A path whose name carries a `.sql` extension or an auth / payment /
    credential / secret token is treated as high-risk even when no enumerated
    glob matches it — so a newly-introduced risky domain (e.g. `iam/`) gates
    until the Captain extends `high_risk_globs` explicitly [FIX-6 gotcha].
    """
    norm = _normpath(path)
    return bool(_BACKSTOP_RE.search(norm))


def _normpath(path: str) -> str:
    """Normalize a path for matching: forward slashes, strip a leading `./`.

    Only a literal `./` prefix is stripped — leading dots in a dotfile name
    (e.g. `.eslintrc.json`, `.env`) are preserved.
    """
    norm = path.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm
