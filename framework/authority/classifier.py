"""Shared deterministic action classifier — the F+A join key [FIX-1].

`classify_action(tool_name, tool_input) -> action_type` is the SINGLE canonical
mapping from a raw tool call to an `action_type` enum string. It is used by:

  * the consequence emitter (F) — stamps `action_type` so the ledger keys
    cells on `(actor, lane, action_type)` (replacing the free-text `action`
    key), and
  * the policy-engine gate (A) — looks up the verdict for that action_type's
    risk_class.

One classifier, one source of truth, so the ledger and the verdict table can
never disagree about what an action *is*.

Discipline (docs/authority-matrix-design-2026-06-19.md §2, FIX-1/FIX-7):

  * **Deterministic + pure.** Same input → same output, no IO, no mutation of
    `tool_input`. (Lane resolution lives in `lane.py`, the only env reader.)
  * **Fail-safe.** Ambiguous / unknown actions resolve to `AMBIGUOUS` — a
    distinct, visible, propose-defaulting value — NOT silently to `local_edit`.
    Only a positively-local / no-egress signal yields `local_edit`.
  * **Positive ceiling classification.** The always-gated execution-surface
    classes — secrets (.env / secret-store access), network_write (live
    mutating MCP/HTTP POST/PUT/DELETE), credentials_grant (oauth / token
    grant) — are matched by explicit positive rules and can NEVER fall into
    the `AMBIGUOUS` backstop. This is the fail-closed spine: the gate must see
    these as their ceiling class regardless of anything else.

System Python is 3.9.6; only stdlib is used.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# The action_type enum surface (single source of truth)
# ---------------------------------------------------------------------------

# The visible, propose-defaulting backstop for anything we cannot positively
# classify. Distinct from local_edit so an unknown action is never silently
# treated as a harmless local edit (fail-safe, no-silent-caps).
AMBIGUOUS = "ambiguous"

# reversible risk_class members
_REVERSIBLE = {
    "task_status_move", "board_status", "label", "tier2_note",
    "draft_only", "local_edit",
}
# comms
_INTERNAL_COMMS = {"internal_message", "internal_email"}
_EXTERNAL_COMMS = {"external_message", "external_email"}
# deploy
_DEPLOY = {
    "vercel_deploy_preview", "git_push_nonmain",
    "vercel_deploy_prod", "git_push_main",
}
# spend (ceiling)
_SPEND = {"purchase", "provision_paid", "billing"}
# secrets (ceiling)
_SECRETS = {"secret_read", "secret_write", "env_write"}
# network_write (ceiling)
_NETWORK_WRITE = {"mcp_post", "mcp_put", "mcp_delete"}
# credentials_grant (ceiling)
_CREDENTIALS_GRANT = {"oauth_grant", "token_grant"}

# The execution-surface ceiling action_types that MUST be positively
# classified (never the AMBIGUOUS backstop) [FIX-7].
CEILING_ACTION_TYPES = frozenset(_SECRETS | _NETWORK_WRITE | _CREDENTIALS_GRANT)

# Every valid action_type the classifier can return.
ACTION_TYPES = frozenset(
    _REVERSIBLE
    | _INTERNAL_COMMS
    | _EXTERNAL_COMMS
    | _DEPLOY
    | _SPEND
    | _SECRETS
    | _NETWORK_WRITE
    | _CREDENTIALS_GRANT
    | {AMBIGUOUS}
)


# ---------------------------------------------------------------------------
# Helpers — small, pure string predicates
# ---------------------------------------------------------------------------

_INTERNAL_DOMAINS = (
    "stepnetwork.dk", "jfmedier.dk", "jysk-fynske-medier.dk",
    "polads.eu", "refslund.ai", "step.dk",
)

_DOTENV_RE = re.compile(r"(^|/)\.env(\.[\w.-]+)?$")
# Command-scan variant: find a .env token anywhere on a command line,
# bounded on the left by start/space/quote/= and on the right by a path
# separator, whitespace, redirect, quote, or end. Used by _classify_bash
# (a relative `.env.local` after a space must still register as secrets).
_DOTENV_CMD_RE = re.compile(r"(?:^|[\s=\'\"/])\.env(?:\.[\w.-]+)?(?=$|[\s\'\";&|>)])")
_LOCALHOST_RE = re.compile(r"(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])")
_URL_RE = re.compile(r"https?://([^/\s'\"]+)")


def _command(tool_input: dict[str, Any]) -> str:
    cmd = tool_input.get("command")
    return cmd if isinstance(cmd, str) else ""


def _file_path(tool_input: dict[str, Any]) -> str:
    for k in ("file_path", "path"):
        v = tool_input.get(k)
        if isinstance(v, str) and v:
            return v
    return ""


def _is_dotenv(path: str) -> bool:
    return bool(_DOTENV_RE.search(path))


def _recipient(tool_input: dict[str, Any]) -> str:
    for k in ("recipient", "to", "recipient_email", "email"):
        v = tool_input.get(k)
        if isinstance(v, str):
            return v
    return ""


def _is_internal_recipient(recipient: str) -> bool:
    rec = recipient.strip().lower()
    if not rec or "@" not in rec:
        return False
    domain = rec.rsplit("@", 1)[-1]
    return any(domain == d or domain.endswith("." + d) for d in _INTERNAL_DOMAINS)


def _curl_method(command: str) -> str | None:
    """Return the HTTP verb a curl invocation uses, or None if not curl.

    Recognizes -X/--request VERB; defaults a curl with a body (-d/--data/
    --data-*/-F/--form/-T/--upload-file) to POST.
    """
    if not re.search(r"\bcurl\b", command):
        return None
    m = re.search(r"(?:-X|--request)\s+([A-Za-z]+)", command)
    if m:
        return m.group(1).upper()
    if re.search(r"(?:-d|--data\b|--data-[\w-]+|-F\b|--form\b|-T\b|--upload-file)", command):
        return "POST"
    return "GET"


def _command_targets_remote(command: str) -> bool:
    """True iff a command's URL(s) point at a non-local endpoint.

    Conservative: if a URL is present and NONE of them are localhost, treat as
    remote (egress). A command with no URL is not classified as network egress.
    """
    urls = _URL_RE.findall(command)
    if not urls:
        return False
    return not all(_LOCALHOST_RE.search(u) for u in urls)


# ---------------------------------------------------------------------------
# classify_action — the join key
# ---------------------------------------------------------------------------

def classify_action(tool_name: str, tool_input: dict[str, Any] | None) -> str:
    """Map a raw tool call to a deterministic `action_type` enum string.

    See module docstring for the fail-safe / positive-ceiling contract. Order
    of checks matters: ceiling classes are tested BEFORE the reversible/local
    and ambiguous fallbacks so a dangerous action can never escape into a
    softer class.
    """
    tool_name = tool_name or ""
    if not isinstance(tool_input, dict):
        tool_input = {}

    command = _command(tool_input)
    file_path = _file_path(tool_input)

    # === Bash command dispatch =============================================
    if tool_name == "Bash":
        if command:
            return _classify_bash(command)
        # Bash with no command — nothing to act on → propose (visible), not
        # silently local.
        return AMBIGUOUS

    # === File tools ========================================================
    if tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        if file_path:
            # CEILING: writing a .env / dotenv file is a secrets action.
            if _is_dotenv(file_path):
                return "env_write"
            if _is_tier2(file_path):
                return "tier2_note"
            return "local_edit"
        return "local_edit"

    if tool_name in ("Read", "Grep", "Glob", "LS"):
        # Read-only / introspection — reversible local, no egress.
        return "local_edit"

    # === MCP tool dispatch =================================================
    if tool_name.startswith("mcp__") or "__" in tool_name:
        mcp = _classify_mcp(tool_name, tool_input)
        if mcp is not None:
            return mcp

    # === Unknown / unmatched ==============================================
    return AMBIGUOUS


def _is_tier2(path: str) -> bool:
    return "instance/memory/tier2/" in path.replace("\\", "/")


# ---------------------------------------------------------------------------
# Bash classification
# ---------------------------------------------------------------------------

def _classify_bash(command: str) -> str:
    cmd = command.strip()
    low = cmd.lower()

    # --- CEILING: secrets (.env / secret-store access) --------------------
    # vercel env mutation (add/set/create/rm/remove) → platform secret write;
    # `vercel env pull` exfiltrates the secret set to a local file → read.
    if re.search(r"\bvercel\b.*\benv\b\s+(add|set|create|rm|remove)", low):
        return "env_write"
    if re.search(r"\bvercel\b.*\benv\b\s+pull\b", low):
        return "secret_read"
    # ANY touch of a .env path is a secrets-ceiling action — fail CLOSED so a
    # secrets resource NEVER falls through to local_edit (auto-eligible). A
    # write / in-place editor verb (sed -i, dd, truncate, tee, redirects, cp,
    # mv, install, python open(...,'w')) → secret_write; else a read.
    if _DOTENV_CMD_RE.search(low):
        if re.search(r">>?|\btee\b|\bcp\b|\bmv\b|\bsed\b\s+-i|\bdd\b|\btruncate\b|\binstall\b|open\([^)]*['\"]w", low):
            return "secret_write"
        return "secret_read"

    # --- CEILING: credentials_grant (oauth / token grant) -----------------
    if re.search(r"\boauth\b.*\bgrant\b|\bgrant\b.*\boauth\b", low):
        return "oauth_grant"
    if re.search(r"\b(auth\s+token|token\s+grant|create[- ]token|grant[- ]token)\b", low):
        return "token_grant"
    if re.search(r"\btoken\b.*\bgrant\b|\bgrant\b.*\btoken\b", low):
        return "token_grant"

    # --- CEILING: spend (real money) --------------------------------------
    if re.search(r"\bbilling\b", low):
        return "billing"
    if re.search(r"\b(charge|purchase|buy|subscribe)\b", low) or \
       re.search(r"\bstripe\b.*\bcharge", low) or \
       re.search(r"\bdomains?\b\s+buy\b", low):
        return "purchase"

    # --- CEILING: network_write (live mutating HTTP verbs) ----------------
    method = _curl_method(cmd)
    if method in ("POST", "PUT", "DELETE", "PATCH") and _command_targets_remote(cmd):
        return {"POST": "mcp_post", "PATCH": "mcp_post",
                "PUT": "mcp_put", "DELETE": "mcp_delete"}[method]

    # --- deploy: git push -------------------------------------------------
    if re.search(r"\bgit\b.*\bpush\b", low):
        return _classify_git_push(cmd)

    # --- deploy: vercel ---------------------------------------------------
    if re.search(r"\bvercel\b", low) and (
        "deploy" in low or "--prod" in low or "--target" in low
    ):
        if "--prod" in low:
            return "vercel_deploy_prod"
        if "preview" in low:
            return "vercel_deploy_preview"
        # bare `vercel deploy` → preview by default
        return "vercel_deploy_preview"

    # --- everything else local / reversible / no-egress -------------------
    return "local_edit"


_BRANCH_REFSPEC_RE = re.compile(r"(?:HEAD:)?(?:refs/heads/)?(\S+)$")


def _classify_git_push(command: str) -> str:
    """Resolve a `git push` to prod (main/master) vs nonprod branch.

    Fail-conservative: a bare `git push` (no explicit branch) is treated as a
    push to the default branch → prod. Only an explicit non-main/master branch
    refspec downgrades to nonprod.
    """
    # Tokenize off the push, dropping flags and their obvious values.
    after = re.split(r"\bpush\b", command, maxsplit=1)[1] if "push" in command else ""
    tokens = [t for t in after.split() if t]
    positionals: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("-"):
            # flags like --force, -u, --set-upstream; -u/--set-upstream take
            # no value here (remote/branch are positionals), so just skip flag
            i += 1
            continue
        positionals.append(t)
        i += 1

    # positionals are typically [remote, refspec]. The refspec (last) carries
    # the branch; if absent, it's a bare push → default branch → prod.
    if len(positionals) >= 2:
        # Strip a force-push '+' prefix + surrounding quotes BEFORE the branch
        # match: `git push origin +main` is still a (history-REWRITING) push to
        # main. The bare `+branch` refspec form previously leaked to nonprod.
        refspec = positionals[-1].strip("'\"").lstrip("+")
        # strip a "src:dst" — the destination (after ':') is the branch pushed
        if ":" in refspec:
            refspec = refspec.rsplit(":", 1)[-1]
        m = _BRANCH_REFSPEC_RE.search(refspec)
        branch = (m.group(1) if m else refspec).lstrip("+")
        if branch in ("main", "master"):
            return "git_push_main"
        return "git_push_nonmain"

    if len(positionals) == 1:
        # Could be just a remote (`git push origin`) → bare push to tracked
        # branch → conservative prod; OR a branch on the default remote.
        only = positionals[0].strip("'\"").lstrip("+")
        if only in ("main", "master"):
            return "git_push_main"
        if only in ("origin", "upstream") or "/" not in only:
            # remote name or tracked-branch push → conservative prod
            return "git_push_main"
        return "git_push_nonmain"

    # bare `git push` → default branch → prod (conservative)
    return "git_push_main"


# ---------------------------------------------------------------------------
# MCP classification
# ---------------------------------------------------------------------------

def _classify_mcp(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """Classify an MCP tool call. Returns None if not positively matched (the
    caller then falls through to the AMBIGUOUS backstop)."""
    tn = tool_name.lower()

    # --- brain queue_draft → comms (internal vs external by recipient) ----
    if "queue_draft" in tn:
        recipient = _recipient(tool_input)
        channel = str(tool_input.get("channel", "")).lower()
        is_email = "email" in channel or "mail" in channel
        if _is_internal_recipient(recipient):
            return "internal_email" if is_email else "internal_message"
        # Unknown / external recipient → external (conservative ceiling).
        return "external_email" if is_email else "external_message"

    # --- CEILING: credentials_grant (oauth / authentication) --------------
    if "complete_authentication" in tn or "authenticate" in tn:
        return "oauth_grant"
    if "oauth" in tn:
        return "oauth_grant"
    if "credential" in tn and ("create" in tn or "grant" in tn):
        return "token_grant"

    # --- CEILING: spend (paid provisioning) -------------------------------
    if "create_project" in tn and ("neon" in tn or "vercel" in tn):
        return "provision_paid"
    if "buy" in tn or "purchase" in tn or "billing" in tn:
        if "billing" in tn:
            return "billing"
        return "purchase"

    # --- board / task status (reversible) ---------------------------------
    if ("monday" in tn or "board" in tn) and (
        "change_item_column" in tn or "column_value" in tn or "status" in tn
    ):
        return "board_status"
    if "linear" in tn and "update_issue" in tn:
        return "task_status_move"
    if "dev_tasks" in tn and ("updatetask" in tn or "update_task" in tn):
        return "task_status_move"

    # --- CEILING: network_write (live mutating MCP verbs) -----------------
    # A generic MCP tool whose verb is a live mutation (post/put/delete/
    # create/update on a remote resource). Checked AFTER the known reversible
    # board/task writes above so a Monday status move is not misread as a raw
    # network mutation.
    if re.search(r"(^|_)post(_|$)", tn) or "post_resource" in tn:
        return "mcp_post"
    if re.search(r"(^|_)put(_|$)", tn):
        return "mcp_put"
    if re.search(r"(^|_)delete(_|$)", tn):
        return "mcp_delete"

    return None
