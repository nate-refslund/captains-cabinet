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

System Python is 3.9.6; stdlib + one framework leaf template constant
(framework.frontdoor.calendar_template.CALENDAR_EVENT_SCRIPT, imported call-time
inside _classify_bash so module load stays cycle-free) [GERM-2].
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
    "task_status_move", "label", "tier2_note",
    "draft_only", "local_edit",
    # investigation_run — read-only evidence gathering (PRO-7). Moment-1 intent:
    # in the enum + reversible, propose-first (reversible/unmeasured →
    # propose_only, so it never acts unattended without earned graduation).
    "investigation_run",
}
# pm_write — reversible-with-undo (act_with_undo class) [GERM-2]. board_status
# MOVES here out of _REVERSIBLE; the ledger cell key is (actor, lane,
# action_type), so the string is unchanged and its history follows it.
_PM_WRITE = {"task_create", "board_status"}
# calendar_write — reversible-with-undo (act_with_undo class) [GERM-2].
_CALENDAR_WRITE = {"calendar_event_create"}
# comms
# officer_dispatch is internal_comms but a DISTINCT cell from internal_message
# (RT-B4) — a delegate dispatch is org-internal machine handoff, never an
# outbound colleague message; it stamps its own graduable cell and stays
# propose-first (internal_comms's graduated verdict is dormant per M1).
_INTERNAL_COMMS = {"internal_message", "internal_email", "officer_dispatch"}
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
    | _PM_WRITE
    | _CALENDAR_WRITE
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

    # --- GERM-2: calendar write (calendar_write / external_comms) [RT-B2] --
    # An osascript Calendar write. Attendee/invitee-bearing -> external_comms
    # ceiling: inviting a human SENDS mail (a dedicated CI test pins this). A
    # write byte-matching the lane executor's event template -> the
    # reversible-with-undo calendar_event_create; any OTHER Calendar osascript
    # stays AMBIGUOUS (propose-defaulting) — only the lane's own template acts.
    if "osascript" in low and "calendar" in low:
        if re.search(r"\battendee|\binvitee|make new attendee", low):
            return "external_message"
        from framework.frontdoor.calendar_template import CALENDAR_EVENT_SCRIPT
        if CALENDAR_EVENT_SCRIPT in command:
            return "calendar_event_create"
        return AMBIGUOUS

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

# The Monday GraphQL mutation fields we recognize. The create pair is the ONLY
# act-first-eligible set; everything else is a status write (board_status) or a
# ceiling. Fixed vocabulary — an unrecognized mutation field forces the ceiling.
_MONDAY_CREATE_OPS = frozenset({"create_item", "create_update"})
_MONDAY_STATUS_OPS = frozenset({
    "change_column_value", "change_multiple_column_values",
    "change_simple_column_value", "change_item_column_values",
})
_MONDAY_KNOWN_OPS = frozenset({
    "create_item", "create_update", "create_subitem", "create_board",
    "create_group", "create_column", "duplicate_item", "archive_item",
    "delete_item", "delete_update", "move_item_to_board", "move_item_to_group",
    "change_column_value", "change_multiple_column_values",
    "change_simple_column_value", "change_item_column_values",
})
_MONDAY_OP_RE = re.compile(r"\b(" + "|".join(sorted(_MONDAY_KNOWN_OPS)) + r")\b")

# [KILLED #4 fix — checkpoint 2026-07-04 §4] Generic mutation-field extraction
# for body-bearing tools. The old detector was findall over the fixed
# vocabulary above, so an OUT-OF-VOCAB destructive field (delete_board,
# duplicate_group, any future op) was invisible: "create_item + delete_board"
# extracted {create_item}, passed the pure-create subset test below, and
# classified task_create (act_with_undo) — the generic API tool then executed
# BOTH. These three patterns make extraction vocabulary-INDEPENDENT so an
# unknown field can never hide behind a known one:
#   * _GQL_STRING_RE — escape-aware double-quoted GraphQL string literals. An
#     executable field can never live inside a string literal, so stripping
#     them first only removes non-executable text (and stops prose args like
#     item_name: "call mom (later)" from being read as fields). Fail
#     direction: an unbalanced quote leaves text UNstripped -> extraction sees
#     more -> ceiling.
#   * _GQL_OP_HEADER_RE — a WELL-FORMED operation header (keyword + optional
#     operation name + optional variable defs, immediately before "{"). Only
#     this provably-inert header is stripped so an operation NAME is not read
#     as a field; anything malformed stays in place and lands in extraction ->
#     out-of-vocab -> ceiling (fail-closed).
#   * _GQL_FIELD_RE — every identifier called with arguments ("ident(").
#     Deliberate over-capture (sub-selection fields with args, malformed
#     fragments, parens outside strings): extra members can only break the
#     pure-create/pure-status subset carve-outs and force the ceiling —
#     over-capture can never soften a verdict. Directives (@skip(...)) and
#     variables ($x(...)) are excluded by the lookbehind.
# [re-verify KILLED #4] Block strings MUST be stripped BEFORE regular strings:
# a GraphQL block string """a"b""" carries a lone " that a double-quote-only
# stripper mis-pairs, swallowing real fields after it (e.g. delete_board(...))
# and softening the verdict. This matches a """...""" span whose content is any
# char except a " that begins a closing """ — so the inner lone " in """a"b"""
# stays inside the span and the closing """ terminates it correctly.
_GQL_BLOCKSTRING_RE = re.compile(r'"""(?:[^"]|"(?!""))*"""')
_GQL_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')
# GraphQL "#" line comments are ignored tokens and may sit between a field
# Name and its "(" — strip them so an out-of-vocab op can't hide behind one.
_GQL_COMMENT_RE = re.compile(r"#[^\n]*")
_GQL_OP_HEADER_RE = re.compile(
    r"\b(?:mutation|query|subscription)\b\s*"
    r"(?:[A-Za-z_][A-Za-z0-9_]*\s*)?"      # optional operation name
    r"(?:\([^)]*\)\s*)?"                   # optional variable definitions
    r"(?=\{)",
    re.IGNORECASE,
)
# Between a field Name and its Arguments GraphQL permits ignored tokens —
# whitespace AND commas (comments already stripped). "[\s,]*" tolerates
# "delete_board,(" and "delete_board (" so no op hides in the gap.
_GQL_FIELD_RE = re.compile(r"(?<![@$\w])([A-Za-z_][A-Za-z0-9_]*)[\s,]*\(")

# A synthetic op that is in NO carve-out set — returned when the body cannot be
# cleaned to a balanced state, so the caller forces the mcp_post ceiling.
_UNPARSEABLE_OP = "__unbalanced_body__"


def _monday_body_ops(body: str) -> "set[str]":
    """ALL mutation-field candidates in a generic GraphQL body: known-vocab
    mentions UNION every generically-extracted "identifier(" token. The union
    keeps the smuggle test honest — a field the vocabulary has never heard of
    still lands in the set, fails the subset carve-outs, and forces the
    mcp_post ceiling [KILLED #4].

    Fail-closed cleaning order (block strings → regular strings → comments →
    op header), then a balance check: if a residual unbalanced " survives, the
    body is un-cleanable and we return the _UNPARSEABLE_OP sentinel (ceiling)
    rather than trust a mis-paired extraction."""
    stripped = _GQL_BLOCKSTRING_RE.sub(" ", body)
    stripped = _GQL_STRING_RE.sub(" ", stripped)
    stripped = _GQL_COMMENT_RE.sub(" ", stripped)
    stripped = _GQL_OP_HEADER_RE.sub(" ", stripped)
    ops = set(_MONDAY_OP_RE.findall(stripped)) | set(_GQL_FIELD_RE.findall(stripped))
    # A lone " left after string-stripping means the quotes never balanced —
    # extraction cannot be trusted; force the ceiling (fail-closed).
    if '"' in stripped:
        ops.add(_UNPARSEABLE_OP)
    return ops


# [re-verify round 2] A synthetic op that is in NO carve-out set — returned for
# EVERY generic raw-GraphQL-body Monday call so it always lands at the ceiling.
_RAW_BODY_OP = "__raw_graphql_body__"


def _monday_mutation_ops(tool_name: str, tool_input: dict[str, Any]) -> "set[str] | None":
    """The SET of Monday mutation ops a call performs, or None if it is not a
    Monday mutation.

    ALLOWLIST INVERSION [re-verify round 2, 2026-07-04]: only shape (1) — a
    NAMED per-op MCP tool whose op IS its tool-name suffix — can earn the soft
    act_with_undo class, because the op is structurally unambiguous and cannot
    carry a smuggled second op. Shape (2) — a generic API tool
    (all_monday_api / all_api_write) or a raw curl GraphQL POST carrying an
    arbitrary body — is ALWAYS the ceiling: parsing an adversarial GraphQL
    string with regex is unwinnable (BOM / zero-width bytes between a field and
    its "(", escaped block-string delimiters, aliases, fragments, directives —
    each defeated a prior denylist patch). We stop parsing it and refuse to
    soften a raw body at all. This costs nothing real: the action LANE's own
    creates execute through deliver_action + ACTION_TYPE_MAP (never this
    classifier path), and an officer's raw Monday call has no business acting
    unattended. Reads (get_*/search/board_insights) and non-Monday tools -> None.
    """
    tn = tool_name.lower()
    is_monday_tool = "monday" in tn
    has_body = bool(" ".join(
        str(tool_input.get(k, "")) for k in ("query", "body", "graphql", "mutation")).strip())
    if not is_monday_tool and not (has_body and "monday" in str(tool_input.get("query", "")).lower()):
        # A raw curl to api.monday.com still lands here via the Bash path (see
        # _classify_bash) — this MCP helper only fires for monday-named tools.
        if not is_monday_tool:
            return None
    # (1) named per-op tool: the op is the tool-name suffix — unambiguous, may
    # earn the soft class if it is a create/status op (subset test in caller).
    for op in _MONDAY_KNOWN_OPS:
        if tn.endswith("__" + op) or tn.endswith("_" + op):
            return {op}
    # (2) generic API / raw-body tool: NEVER softened — a raw GraphQL body can
    # smuggle any op, so it always forces the ceiling (fail-closed, un-parsed).
    if has_body or "all_api" in tn or "all_monday_api" in tn:
        return {_RAW_BODY_OP}
    return None


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

    # --- GERM-2: Monday mutations — FULL-MATCH carve-outs [RT-B2] ----------
    # Placed ABOVE mcp_post (order matters): a PURE create maps to the
    # reversible-with-undo task_create; a pure status write to board_status;
    # ANY other or MIXED Monday mutation (a create batched with a delete, a
    # people/assignee op, an unknown field, or an unparseable body) does NOT
    # earn the softer class — it falls to the network_write ceiling. An
    # attacker cannot smuggle a dangerous op inside a "create" batch to soften
    # the verdict: body extraction is vocabulary-INDEPENDENT [KILLED #4], so an
    # out-of-vocab field (delete_board, duplicate_group, a future op) lands in
    # `ops`, fails both subset tests, and forces the ceiling.
    ops = _monday_mutation_ops(tool_name, tool_input)
    if ops is not None:
        if ops and ops <= _MONDAY_CREATE_OPS:
            return "task_create"
        if ops and ops <= _MONDAY_STATUS_OPS:
            return "board_status"
        return "mcp_post"        # mixed / unknown / empty -> ceiling (fail-closed)

    # --- board / task status (reversible) ---------------------------------
    # (residual: non-Monday board tools; Monday handled above.)
    if "board" in tn and "monday" not in tn and (
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
