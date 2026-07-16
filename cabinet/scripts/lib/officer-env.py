#!/usr/bin/env python3
"""Parse the narrow environment that an officer session is allowed to inherit.

The officer launchers used to ``source cabinet/.env`` under ``set -a``.  That
made every value in the shared secret store visible to an officer, including
the dashboard password used to sign Captain sessions and verdicts.  This
parser is intentionally small and dependency-free: it understands ordinary
dotenv assignments, never executes the file, and emits only a reviewed
allowlist.

Output is shell-quoted assignments for the launcher (not for the officer
process itself).  ``officer-env.sh`` builds the final ``env -i`` boundary.
"""

from __future__ import annotations

import argparse
import re
import shlex
import sys
from pathlib import Path


# POSIX/shell environment names may contain either case.  The reviewed
# allowlists below decide what reaches an officer; syntax validation must not
# reject the lowercase proxy aliases that egress-guard deliberately emits for
# clients that ignore the uppercase variants.
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Non-credential runtime settings every officer may receive. Credential names
# live in MCP_ENV_ALLOWLIST below and are selected only when the officer's
# immutable mcp-scope.yml entry grants the corresponding server.
BASE_ENV_ALLOWLIST = frozenset(
    {
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_URL",
        "CABINET_PREFIX",
        "CABINET_ID",
        "CABINET_MODE",
        "CABINET_MCP_TRANSPORT",
        "CABINET_MCP_PORT",
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
        "CAPTAIN_TELEGRAM_ID",
        "CAPTAIN_TELEGRAM_CHAT_ID",
        "TELEGRAM_HQ_CHAT_ID",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
    }
)

# An API/database credential reaches an officer only when the named MCP is in
# that officer's attested scope. This does not make a parent-visible credential
# as strong as a separate broker, but it prevents the previous "every secret to
# every officer" collapse and keeps process reach aligned with declared reach.
MCP_ENV_ALLOWLIST: dict[str, frozenset[str]] = {
    "notion": frozenset({"NOTION_API_KEY"}),
    "vercel": frozenset({"VERCEL_TOKEN"}),
    "make": frozenset({"MAKE_MCP_TOKEN"}),
    "neon": frozenset({"NEON_API_KEY", "NEON_CONNECTION_STRING", "DATABASE_URL"}),
    "library": frozenset({"NEON_CONNECTION_STRING", "DATABASE_URL", "VOYAGE_API_KEY"}),
    "brain": frozenset(
        {
            "SCREENPIPE_API_AUTH_KEY",
            "OBSIDIAN_VAULT_PATH",
            "SCREENPIPE_DATA_DIR",
            "VOYAGE_API_KEY",
        }
    ),
    "brave-search": frozenset({"BRAVE_SEARCH_API_KEY"}),
    "exa": frozenset({"EXA_API_KEY"}),
    "perplexity": frozenset({"PERPLEXITY_API_KEY"}),
    "monday": frozenset({"MONDAY_API_TOKEN"}),
    "telegram": frozenset({"ELEVENLABS_API_KEY"}),
    # The CUA overlay supports multiple model backends.  Keep the keys scoped
    # to the CUA grant, but project every backend credential its shipped MCP
    # config may reference.  Omitting these made the structural grant look
    # present while the server booted with an empty ${ANTHROPIC_API_KEY}.
    "cua": frozenset(
        {
            "CUA_MODEL_BACKEND",
            "MAPBOX_TOKEN",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "GOOGLE_API_KEY",
        }
    ),
    "cua-driver": frozenset(
        {
            "CUA_MODEL_BACKEND",
            "MAPBOX_TOKEN",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "GOOGLE_API_KEY",
        }
    ),
    "claude-in-chrome": frozenset(
        {"CABINET_CHROME_PROFILE_DIR", "CABINET_CHROME_DEBUG_PORT"}
    ),
}
OFFICER_ENV_ALLOWLIST = BASE_ENV_ALLOWLIST | frozenset().union(
    *MCP_ENV_ALLOWLIST.values()
)

# These names are authority credentials, not officer integrations.  Keep this
# independent of the allowlist so a future broadening cannot silently include
# them.  The shell launcher also scrubs inherited copies before doing any work.
FORBIDDEN_EXACT = frozenset(
    {
        "DASHBOARD_PASSWORD",
        "NEXTAUTH_SECRET",
        "AUTH_SECRET",
        "SESSION_SECRET",
        "VERDICT_SECRET",
        "CABINET_SESSION_SIGNING_SECRET",
        "CABINET_VERDICT_SIGNING_SECRET",
        "ONBOARDING_WEBHOOK_SECRET",
        "TELEGRAM_WEBHOOK_SECRET",
        "CABINET_CAPTAIN_CHANNEL",
    }
)


def _parse_value(raw: str, *, line_no: int) -> str:
    """Parse one dotenv RHS without expansion or command execution."""

    lexer = shlex.shlex(raw, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        parts = list(lexer)
    except ValueError as exc:
        raise ValueError(f"line {line_no}: malformed quoted value: {exc}") from exc
    if not parts:
        return ""
    if len(parts) != 1:
        raise ValueError(
            f"line {line_no}: unquoted whitespace in value; quote the whole value"
        )
    # Deliberately no ${VAR}, backtick, or $() expansion.  A dotenv file is
    # data, not shell code.
    return parts[0]


def parse_dotenv(path: Path, accepted: set[str] | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_no, original in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"line {line_no}: expected KEY=VALUE")
        key, raw = line.split("=", 1)
        key = key.strip()
        if not _KEY_RE.fullmatch(key):
            raise ValueError(f"line {line_no}: invalid environment name {key!r}")
        if accepted is not None and key not in accepted:
            # Unknown settings never reach the officer and cannot make a
            # malformed shell-looking value denial-of-service the launcher.
            continue
        values[key] = _parse_value(raw.strip(), line_no=line_no)
    return values


def parse_mcp_scope(path: Path, officer: str) -> set[str]:
    """Read the repo's deliberately simple inline-list MCP scope format.

    This mirrors the hook's parser without importing YAML. Duplicate officer
    entries, missing inline lists, or an unlisted officer fail closed.
    """

    universal: set[str] = set()
    officer_mcps: set[str] | None = None
    in_agents = False
    current: str | None = None
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"universal:\s*\[([^\]]*)\]\s*", raw)
        if match:
            universal = {item.strip() for item in match.group(1).split(",") if item.strip()}
            continue
        if re.fullmatch(r"agents:\s*", raw):
            in_agents = True
            current = None
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*:\s*", raw):
            in_agents = False
            current = None
            continue
        if not in_agents:
            continue
        agent_match = re.fullmatch(r"  ([a-z0-9][a-z0-9-]{0,63}):\s*", raw)
        if agent_match:
            current = agent_match.group(1)
            continue
        mcp_match = re.fullmatch(r"    mcps:\s*\[([^\]]*)\]\s*", raw)
        if mcp_match and current == officer:
            if officer_mcps is not None:
                raise ValueError(f"duplicate MCP scope for officer {officer!r}")
            officer_mcps = {
                item.strip() for item in mcp_match.group(1).split(",") if item.strip()
            }
    if officer_mcps is None:
        raise ValueError(f"officer {officer!r} has no agents entry in {path}")
    return officer_mcps | universal


def allowed_names(
    values: dict[str, str],
    officer: str,
    project: str = "",
    mcp_scope: set[str] | None = None,
    observe_only: bool = False,
) -> set[str]:
    names = set(BASE_ENV_ALLOWLIST)
    for server in mcp_scope or set():
        names.update(MCP_ENV_ALLOWLIST.get(server, ()))
    officer_upper = officer.upper().replace("-", "_")
    # Observe-only boots no Telegram plugin/MCP, but the local cabinet-comms
    # server still needs one launcher-resolved bot token for its fixed
    # Captain/current-message reply seam. Raw aliases remain launcher-only;
    # officer-env.sh forwards only the resolved TELEGRAM_BOT_TOKEN.
    if "telegram" in (mcp_scope or set()) or observe_only:
        names.update(
            {
                "TELEGRAM_BOT_TOKEN",
                "TELEGRAM_CEO_TOKEN",
                f"TELEGRAM_{officer_upper}_TOKEN",
                f"TELEGRAM_BOT_TOKEN_{officer_upper}",
            }
        )
    # CEO bot names are selected later by start-officer.sh.  Restrict dynamic
    # names to the declared project/cabinet rather than exposing every lane's
    # bot token to the launcher.
    for slug in (project, values.get("CABINET_ID", "")):
        if ("telegram" in (mcp_scope or set()) or observe_only) and slug and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug):
            names.add(f"TELEGRAM_{slug.upper().replace('-', '_')}_CEO_TOKEN")
    return names - FORBIDDEN_EXACT


def render(
    path: Path,
    officer: str,
    project: str = "",
    scope_file: Path | None = None,
    observe_only: bool = False,
) -> str:
    officer_upper = officer.upper().replace("-", "_")
    potential = set(OFFICER_ENV_ALLOWLIST)
    potential.update(
        {
            # Both launchers document these narrow Telegram fallbacks.  They
            # still survive selection only for a telegram-scoped officer.
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CEO_TOKEN",
            f"TELEGRAM_{officer_upper}_TOKEN",
            f"TELEGRAM_BOT_TOKEN_{officer_upper}",
        }
    )
    # A project/cabinet CEO token is narrowed after CABINET_ID is parsed.  CEO
    # aliases are the only reviewed dynamic family and remain launcher-only.
    for original in path.read_text(encoding="utf-8").splitlines():
        candidate = original.strip()
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        key = candidate.split("=", 1)[0].strip()
        if re.fullmatch(r"TELEGRAM_[A-Z0-9_]+_CEO_TOKEN", key):
            potential.add(key)
    values = parse_dotenv(path, potential)
    scope = parse_mcp_scope(scope_file, officer) if scope_file else set()
    if observe_only:
        # The 72-hour posture boots only local trigger delivery and the fixed-
        # recipient comms seam. Credential projection uses this EFFECTIVE
        # scope too: no Neon/Vercel/Make/search/brain/CUA credential survives
        # merely because a static germline grant exists.
        scope = {"redis-trigger-channel", "cabinet-comms"}
    allowed = allowed_names(
        values, officer, project, scope, observe_only=observe_only)
    selected = {k: v for k, v in values.items() if k in allowed}
    forbidden = set(selected) & FORBIDDEN_EXACT
    if forbidden:  # defensive invariant; should be impossible
        raise ValueError(f"authority secrets selected: {sorted(forbidden)}")
    lines = [f"export {key}={shlex.quote(selected[key])}" for key in sorted(selected)]
    lines.append(
        "CABINET_OFFICER_ENV_NAMES=" + shlex.quote(" ".join(sorted(selected)))
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--officer", required=True)
    parser.add_argument("--project", default="")
    parser.add_argument("--scope-file", type=Path)
    parser.add_argument("--observe-only", action="store_true")
    args = parser.parse_args()
    try:
        print(
            render(
                args.path,
                args.officer,
                args.project,
                args.scope_file,
                observe_only=args.observe_only,
            )
        )
    except (OSError, ValueError) as exc:
        print(f"officer-env: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
