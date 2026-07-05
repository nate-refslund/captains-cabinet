#!/usr/bin/env python3
"""generate-instance.py — deterministic instance-config generator for cabinet-init.

Reads the onboarding interview answers (written by the `cabinet-init` skill,
default `instance/config/cabinet-init.answers.yml`) and generates this
deployment's instance configuration. The generator is UNIVERSAL: it carries
no captain- or lane-specific data; everything deployment-specific comes from
the answers file and lands ONLY under `instance/`.

Generated (org_shape: portfolio):
  instance/config/contexts/<lane-slug>.yml      lane context declaration (active: false)
  instance/config/projects/<lane-slug>.yml      project config (activation: pending)
  instance/agents/<lane-slug>-ceo.md            lane-CEO role def rendered from
                                                presets/portfolio/agents/_lane-ceo.md.template
  instance/config/platform.yml                  captain keys updated + BEGIN/END-marked
                                                officers block (Chair fulltime, lane CEOs
                                                consultant; inline single-line format —
                                                officer-supervisor.sh greps this file)
  instance/config/roster.yml                    roster snippet for
                                                `bootstrap-roles.sh --roster instance/config/roster.yml`
  instance/config/posture.yml                   INERT posture RULING scaffold (only when
                                                absent — an existing ruling is never
                                                regenerated; sovereign amendment 2026-07-05)

Generated (org_shape: functional | custom): contexts + projects + captain keys
only — the functional preset ships its own five-officer roster (default
`bootstrap-roles.sh`, no --roster); custom shapes author agents/roster by hand.

Guardrails:
  * Writes ONLY under <root>/instance/ — every output path is realpath-resolved
    and prefix-checked; lane slugs are validated against a strict kebab-case
    pattern, so path-escape attempts ("../x", absolute paths) are refused.
  * NEVER writes secrets. All answer values are scanned for secret shapes
    (bot tokens, API keys, PEM blocks); a match aborts the run. Config files
    carry env-var NAMES and TOKEN-TBD placeholders; real values belong in the
    gitignored cabinet/.env.
  * Never clobbers hand-authored files: generated files carry a
    "generated-by: cabinet-init" marker; an existing file without the marker
    is refused (override with --force). platform.yml is only touched inside
    the BEGIN/END marker block + the three captain_* keys.
  * End-of-run validation: every written YAML (and the agent frontmatter)
    must parse; the run fails loud otherwise.

Idempotent: re-running with unchanged answers rewrites byte-identical files.

Usage:
  python3 cabinet/scripts/generate-instance.py [--answers PATH] [--root PATH]
                                               [--dry-run] [--force]
  python3 cabinet/scripts/generate-instance.py --example   # print a starter answers file
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKER = "generated-by: cabinet-init"
PLATFORM_BEGIN = "# BEGIN cabinet-init officers — generated; do not edit between markers."
PLATFORM_END = "# END cabinet-init officers"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &+._/()-]{0,79}$")
CHAT_ID_RE = re.compile(r"^-?\d{4,20}$")
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")

# Reserved ids: the functional officer set + loader-reserved names. A lane
# slug colliding with these would shadow hook/capability routing.
RESERVED_SLUGS = {"cos", "cto", "cpo", "cro", "coo", "main", "_template"}

ORG_SHAPES = ("portfolio", "functional", "custom")

# Secret shapes the generator refuses to persist anywhere. Config carries
# env-var NAMES only; values live in the gitignored cabinet/.env.
SECRET_PATTERNS = [
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}"),          # Telegram bot token
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),               # OpenAI/Anthropic-style key
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}"),           # Anthropic key
    re.compile(r"\bxox[abps]-[A-Za-z0-9-]{10,}"),         # Slack token
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),                # GitHub PAT (classic)
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),        # GitHub PAT (fine-grained)
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                  # AWS access key id
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),    # PEM private key
    re.compile(r"\bpostgres(ql)?://[^\s/@]+:[^\s/@]+@"),  # DSN with inline password
]

# Capability rows mirror cabinet/officer-capabilities.conf (portfolio
# section) — the conf file itself is germline; the captain adds rows there.
CHAIR_CAPABILITIES = "[logs_captain_decisions, reviews_specs, reviews_implementations, validates_deployments]"
LANE_CEO_CAPABILITIES = "[deploys_code, logs_captain_decisions]"

DEFAULT_MODEL = "claude-opus-4-8[1m]"

# Posture scaffold vocabulary (sovereign amendment 2026-07-05, FI-1).
POSTURE_FLAVORS = frozenset({"org", "personal"})
POSTURE_TARGETS = frozenset({"guardian", "sovereign"})

LANE_CEO_TEMPLATE_REL = "presets/portfolio/agents/_lane-ceo.md.template"
TEMPLATE_PLACEHOLDERS = ("{{LANE_NAME}}", "{{LANE_SLUG}}", "{{REPO}}", "{{BOARDS}}", "{{MODEL}}")


class GenerationError(Exception):
    """Validation/guardrail failure — abort without writing."""


# ---------------------------------------------------------------------------
# Answers loading + validation
# ---------------------------------------------------------------------------

def _scan_for_secrets(value, path="answers"):
    """Recursively refuse any answer value that looks like a real secret."""
    if isinstance(value, dict):
        for k, v in value.items():
            _scan_for_secrets(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _scan_for_secrets(v, f"{path}[{i}]")
    elif isinstance(value, str):
        for pat in SECRET_PATTERNS:
            if pat.search(value):
                raise GenerationError(
                    f"SECRET REFUSED at {path}: value matches a credential shape "
                    f"({pat.pattern}). Config files carry env-var NAMES only — put "
                    f"the real value in the gitignored cabinet/.env and reference "
                    f"it by name."
                )


def _req(d: dict, key: str, where: str) -> object:
    if key not in d or d[key] in (None, ""):
        raise GenerationError(f"answers missing required field: {where}.{key}")
    return d[key]


def load_answers(path: Path) -> dict:
    if not path.is_file():
        raise GenerationError(
            f"answers file not found: {path}\n"
            f"Run the cabinet-init skill to produce it, or start from:\n"
            f"  python3 cabinet/scripts/generate-instance.py --example > {path}"
        )
    try:
        answers = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise GenerationError(f"answers file is not valid YAML: {e}") from e
    if not isinstance(answers, dict):
        raise GenerationError("answers file must be a YAML mapping")

    _scan_for_secrets(answers)

    captain = answers.get("captain") or {}
    name = str(_req(captain, "name", "captain"))
    if "\n" in name or not NAME_RE.match(name):
        raise GenerationError(
            f"captain.name {name!r} must match {NAME_RE.pattern} (plain display name)"
        )
    tz = str(_req(captain, "timezone", "captain"))
    if tz != "UTC" and "/" not in tz:
        raise GenerationError(
            f"captain.timezone {tz!r} must be an IANA identifier (e.g. Europe/Madrid) or UTC"
        )
    chat_id = str(_req(captain, "telegram_chat_id", "captain"))
    if not CHAT_ID_RE.match(chat_id):
        raise GenerationError(
            f"captain.telegram_chat_id {chat_id!r} must be a numeric chat id "
            f"(it is an address, never a token)"
        )

    cabinet = answers.get("cabinet") or {}
    org_shape = str(cabinet.get("org_shape", "portfolio"))
    if org_shape not in ORG_SHAPES:
        raise GenerationError(f"cabinet.org_shape must be one of {ORG_SHAPES}, got {org_shape!r}")
    cab_id = str(cabinet.get("id", "main"))
    if not SLUG_RE.match(cab_id):
        raise GenerationError(f"cabinet.id {cab_id!r} must match {SLUG_RE.pattern}")
    model = str(cabinet.get("officer_model", DEFAULT_MODEL))
    if not re.match(r"^[a-z0-9][a-z0-9.\[\]-]{0,63}$", model):
        raise GenerationError(f"cabinet.officer_model {model!r} has an unexpected shape")

    lanes = answers.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise GenerationError("answers must declare at least one lane under lanes:")
    seen = set()
    for i, lane in enumerate(lanes):
        if not isinstance(lane, dict):
            raise GenerationError(f"lanes[{i}] must be a mapping")
        slug = str(_req(lane, "slug", f"lanes[{i}]"))
        if not SLUG_RE.match(slug):
            raise GenerationError(
                f"lanes[{i}].slug {slug!r} refused: must match {SLUG_RE.pattern} "
                f"(kebab-case; no slashes, dots, or path segments)"
            )
        if slug in RESERVED_SLUGS:
            raise GenerationError(f"lanes[{i}].slug {slug!r} is a reserved id")
        if slug in seen:
            raise GenerationError(f"duplicate lane slug: {slug!r}")
        seen.add(slug)
        lname = str(_req(lane, "name", f"lanes[{i}]"))
        if not NAME_RE.match(lname):
            raise GenerationError(
                f"lanes[{i}].name {lname!r} must match {NAME_RE.pattern} "
                f"(no ':', '#', or quotes — it is written into YAML scalars)"
            )
        repos = lane.get("repos") or []
        if not isinstance(repos, list):
            raise GenerationError(f"lanes[{i}].repos must be a list")
        boards = lane.get("boards") or []
        if not isinstance(boards, list):
            raise GenerationError(f"lanes[{i}].boards must be a list")

    integrations = answers.get("integrations") or {}
    tg = integrations.get("telegram") or {}
    for env_key in ("bot_token_env",):
        val = tg.get(env_key)
        if val and not ENV_NAME_RE.match(str(val)):
            raise GenerationError(
                f"integrations.telegram.{env_key} {val!r} must be an ENV VAR NAME "
                f"(UPPER_SNAKE), never a value"
            )
    for j, env_name in enumerate(integrations.get("mcp_env_names") or []):
        if not ENV_NAME_RE.match(str(env_name)):
            raise GenerationError(
                f"integrations.mcp_env_names[{j}] {env_name!r} must be an ENV VAR NAME (UPPER_SNAKE)"
            )

    # Posture answers (sovereign amendment 2026-07-05). Both optional; the
    # rendered posture.yml is an INERT scaffold either way (resolve_posture
    # demands the Captain's schg lock before anything changes).
    autonomy = answers.get("autonomy") or {}
    flavor = str(autonomy.get("flavor", "org"))
    if flavor not in POSTURE_FLAVORS:
        raise GenerationError(
            f"autonomy.flavor must be one of {sorted(POSTURE_FLAVORS)}, got {flavor!r}"
        )
    target = autonomy.get("target_posture")
    if target is not None and str(target) not in POSTURE_TARGETS:
        raise GenerationError(
            f"autonomy.target_posture must be one of {sorted(POSTURE_TARGETS)}, "
            f"got {target!r}"
        )

    return answers


# ---------------------------------------------------------------------------
# Path containment + atomic writes
# ---------------------------------------------------------------------------

def _instance_path(root: Path, *parts: str) -> Path:
    """Join parts under <root>/instance/ and refuse anything that escapes it."""
    instance_root = (root / "instance").resolve()
    candidate = (root / "instance").joinpath(*parts)
    resolved = candidate.resolve()
    if resolved != instance_root and instance_root not in resolved.parents:
        raise GenerationError(
            f"PATH REFUSED: {candidate} resolves outside {instance_root} — "
            f"the generator writes only under instance/"
        )
    return resolved


def _check_overwrite(path: Path, force: bool) -> None:
    """Refuse to clobber a file the generator does not own (no marker)."""
    if path.exists() and MARKER not in path.read_text(encoding="utf-8"):
        if not force:
            raise GenerationError(
                f"REFUSING to overwrite {path}: existing file lacks the "
                f"'{MARKER}' marker (hand-authored?). Re-run with --force to "
                f"overwrite, or move the file aside."
            )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# Renderers (hand-rendered text — exact formatting, no yaml.dump drift)
# ---------------------------------------------------------------------------

def _indent_block(text: str, indent: str = "  ") -> str:
    return "\n".join(indent + line if line.strip() else line for line in text.strip().splitlines())


def render_context(lane: dict) -> str:
    name = lane["name"]
    slug = lane["slug"]
    capacity = lane.get("capacity", "work")
    repos = ", ".join(str(r) for r in (lane.get("repos") or [])) or "(none declared)"
    boards = ", ".join(str(b) for b in (lane.get("boards") or [])) or "(none declared)"
    desc = lane.get("description") or (
        f"{name} lane. Repo(s): {repos}. Task board(s): {boards}. "
        f"Declared by cabinet-init for this instance; inactive until the "
        f"Captain explicitly activates it."
    )
    return f"""# {MARKER} — lane context declaration (regenerate via
# cabinet/scripts/generate-instance.py; answers in cabinet-init.answers.yml)
# DECLARATION NOTE (not activation): committing this file makes the slug
# immediately valid in pre-tool-use.sh's context_slug cache — the cache is
# built from instance/config/contexts/*.yml filenames and does NOT filter on
# active: false. No warroom rows, no officer routing, no activity start from
# this file alone; those require explicit activation by the Captain.
slug: {slug}
name: {name}
capacity: {capacity}
description: |
{_indent_block(desc)}
active: false
"""


def render_project(lane: dict, integrations: dict) -> str:
    name = lane["name"]
    slug = lane["slug"]
    repos = [str(r) for r in (lane.get("repos") or [])]
    repo = repos[0] if repos else ""
    extra_repos = ""
    if len(repos) > 1:
        extra_repos = (
            f"  # additional repos in this lane: {', '.join(repos[1:])}\n"
        )
    task_system = str(lane.get("task_system") or "none")
    boards = ", ".join(str(b) for b in (lane.get("boards") or []))
    neon_project = str(lane.get("neon_project") or "")
    vercel_project = str(lane.get("vercel_project") or "")
    vercel_comment = (
        f"  # vercel_project: {vercel_project} (NAME only — deploy config lives with the repo)\n"
        if vercel_project else ""
    )
    linear_team = str(lane.get("linear_team_key") or "")
    linear_url = str(lane.get("linear_workspace_url") or "")

    if task_system.startswith("plugin:"):
        plugin = task_system.split(":", 1)[1]
        tasks_block = f"""# =============================================================
# Tasks — DELIBERATELY ABSENT. No tasks: block / task-sync adapter for
# this project: the {plugin} plugin is the sanctioned task route for this
# lane (boards: {boards or 'see lane config'}). Do not add a duplicate
# adapter here — that duplication is by-design avoided.
# =============================================================
"""
    elif task_system == "none":
        tasks_block = """# =============================================================
# Tasks — no task system declared for this lane yet. Declare one via
# cabinet-init (task_system) or wire a task adapter when the lane needs it.
# =============================================================
"""
    else:
        tasks_block = f"""# =============================================================
# Tasks — task system: {task_system} (boards: {boards or 'n/a'}).
# Configure the matching adapter/section when the lane activates.
# =============================================================
"""

    tg = integrations.get("telegram") or {}
    ceo_bot = str(tg.get("ceo_bot") or "")
    # Canonical token var name: TELEGRAM_<OFFICER_UPPER>_TOKEN — what
    # start-officer-mac.sh resolves first (TELEGRAM_BOT_TOKEN_<UPPER> is a
    # supported legacy fallback).
    token_env = str(tg.get("bot_token_env") or "TELEGRAM_COS_TOKEN")

    return f"""# =============================================================
# Project: {name}
# =============================================================
# {MARKER} — deployment project config (regenerate via
# cabinet/scripts/generate-instance.py). status: pending — NOTHING
# activates from this file; the Captain runs switch/activate explicitly.
# =============================================================

product:
  name: {name}
  description: "{lane.get('one_liner') or name + ' lane'}"
  repo: {repo}
  repo_branch: {lane.get('repo_branch', 'main')}
  mount_path: /workspace/product   # mac-native checkout path decided at activation
{extra_repos}{vercel_comment}
activation:
  status: pending
  mode: existing_repo_url
  activated_at: ""
  activation_mission_id: ""
  notes: "Generated by cabinet-init; the Captain activates."

# =============================================================
# Notion — IDs stay empty unless this deployment uses Notion.
# =============================================================
notion:
  cabinet_hq_id: ""

  dashboard:
    page_id: ""
    decision_queue_db: ""
    daily_briefings_db: ""
    weekly_reports_db: ""

  business_brain:
    page_id: ""
    vision_id: ""
    strategy_brief_id: ""
    brand_guidelines_id: ""
    messaging_pillars_id: ""
    growth_guardrails_id: ""
    pricing_id: ""

  research_hub:
    page_id: ""
    research_briefs_db: ""
    competitive_intel_db: ""
    market_trends_db: ""

  product_hub:
    page_id: ""
    product_roadmap_db: ""
    feature_specs_db: ""
    user_feedback_db: ""

  engineering_hub:
    page_id: ""
    architecture_decisions_db: ""
    tech_debt_db: ""

  cabinet_ops:
    page_id: ""
    decision_journal_db: ""
    improvement_proposals_db: ""

  reference:
    page_id: ""

  archive:
    page_id: ""

# =============================================================
# Linear
# =============================================================
linear:
  team_key: "{linear_team}"
  workspace_url: "{linear_url}"

# =============================================================
# Neon — product database (NAME only; connection string in cabinet/.env)
# =============================================================
neon:
  project: {neon_project or '""'}

{tasks_block}
# =============================================================
# Telegram — single-bot coordinating surface (portfolio default)
# =============================================================
telegram:
  bot_mode: single_ceo
  ceo_officer: cos
  ceo_bot: "{ceo_bot}"             # TOKEN-TBD — token lives ONLY in cabinet/.env ({token_env})
  officers: {{}}                     # populated only if bot_mode is ever switched to multi_officer
"""


def render_agent(template_text: str, lane: dict, model: str) -> str:
    if not template_text.startswith("---\n"):
        raise GenerationError(f"unexpected template shape: {LANE_CEO_TEMPLATE_REL} must start with '---'")

    # Drop the template's leading archetype-explanation comment block (the
    # consecutive '#' lines right after '---') — it documents the TEMPLATE
    # contract (and mentions the literal placeholders), not the rendered role.
    lines = template_text.split("\n")
    body_start = 1
    while body_start < len(lines) and lines[body_start].lstrip().startswith("#"):
        body_start += 1
    stamped = (
        f"# {MARKER} — rendered from {LANE_CEO_TEMPLATE_REL};\n"
        f"# regenerate via cabinet/scripts/generate-instance.py (do not hand-edit\n"
        f"# this file back into a template).\n"
        f"# Hire the role: list {lane['slug']}-ceo under agents: in\n"
        f"# cabinet/mcp-scope.yml + add its rows to cabinet/officer-capabilities.conf\n"
        f"# (germline files — propose to the Captain), then seed via\n"
        f"# bootstrap-roles.sh --roster instance/config/roster.yml.\n"
    )
    rendered = "---\n" + stamped + "\n".join(lines[body_start:])

    repos = [str(r) for r in (lane.get("repos") or [])]
    boards = [str(b) for b in (lane.get("boards") or [])]
    substitutions = {
        "{{LANE_NAME}}": lane["name"],
        "{{LANE_SLUG}}": lane["slug"],
        "{{REPO}}": ", ".join(repos) if repos else "(no repo declared)",
        "{{BOARDS}}": ", ".join(boards) if boards else "(no boards declared)",
        # Same officer_model value render_roster stamps into roster.yml —
        # the agent frontmatter and the roster must never disagree.
        "{{MODEL}}": model,
    }
    for placeholder, value in substitutions.items():
        rendered = rendered.replace(placeholder, value)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", rendered)
    if leftover:
        raise GenerationError(
            f"template placeholders left unsubstituted: {sorted(set(leftover))} — "
            f"the template at {LANE_CEO_TEMPLATE_REL} has drifted from the "
            f"generator's contract {list(TEMPLATE_PLACEHOLDERS)}; update both together."
        )
    return rendered


def render_roster(lanes: list, model: str) -> str:
    lane_blocks = []
    for lane in lanes:
        lane_blocks.append(
            f"""  {lane['slug']}-ceo:
    title: {lane['name']} CEO
    type: consultant               # on-demand; spawned per trigger/mission, idle-stop
    model: {model}
    capabilities: {LANE_CEO_CAPABILITIES}
    authority_level: mission_executor
"""
        )
    # NOTE: keep ALL comments above the top-level `roster:` key — the
    # bootstrap-roles.sh awk parser closes the roster section on any
    # top-level line (including full-line comments).
    return f"""# {MARKER} — roster snippet for the portfolio shape.
# Seed it:  bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml
# Parser contract (bootstrap-roles.sh): 2-space role keys; 4-space
# title/model/capabilities/authority_level fields; `type:` is read by
# humans + the supervisor config and ignored by bootstrap. Capability
# lists mirror cabinet/officer-capabilities.conf — add matching rows
# there for every lane CEO (germline file: the Captain applies).
roster:
  cos:
    title: Chair
    type: fulltime                 # persistent session; supervisor auto-restarts
    model: {model}
    capabilities: {CHAIR_CAPABILITIES}
    authority_level: captain_proxy
{''.join(lane_blocks)}"""


def render_officers_block(lanes: list) -> str:
    lines = [
        PLATFORM_BEGIN,
        "# Regenerate: python3 cabinet/scripts/generate-instance.py",
        "# Inline single-line format is REQUIRED — officer-supervisor.sh greps",
        "# '^  <slug>:.*type:' on this file; block style would not be detected.",
        "officers:",
        "  cos: { type: fulltime }            # Chair — persistent, the single human surface",
    ]
    for lane in lanes:
        lines.append(
            f"  {lane['slug']}-ceo: {{ type: consultant }}   # lane CEO — on-demand, Telegram-dark"
        )
    lines.append(PLATFORM_END)
    return "\n".join(lines)


def _set_top_level_key(text: str, key: str, value: str) -> str:
    """Replace `key: ...` at column 0, preserving a trailing comment; append if absent."""
    pattern = re.compile(rf"^{re.escape(key)}:[^\n#]*(?P<comment>#[^\n]*)?$", re.MULTILINE)

    def _sub(m: re.Match) -> str:
        comment = m.group("comment")
        if comment:
            return f"{key}: {value}    {comment}"
        return f"{key}: {value}"

    new_text, n = pattern.subn(_sub, text, count=1)
    if n == 0:
        sep = "" if text.endswith("\n") else "\n"
        return f"{text}{sep}{key}: {value}\n"
    return new_text


def render_platform(existing: str, answers: dict, lanes: list, org_shape: str) -> str:
    captain = answers["captain"]
    text = existing
    text = _set_top_level_key(text, "captain_name", str(captain["name"]))
    text = _set_top_level_key(text, "captain_timezone", str(captain["timezone"]))
    text = _set_top_level_key(text, "captain_telegram_chat_id", f'"{captain["telegram_chat_id"]}"')

    if org_shape != "portfolio":
        return text

    block = render_officers_block(lanes)
    begin_count = text.count(PLATFORM_BEGIN)
    end_count = text.count(PLATFORM_END)
    if begin_count == 1 and end_count == 1:
        start = text.index(PLATFORM_BEGIN)
        end = text.index(PLATFORM_END) + len(PLATFORM_END)
        if end < start:
            raise GenerationError("platform.yml marker block is corrupt (END before BEGIN)")
        text = text[:start] + block + text[end:]
    elif begin_count == 0 and end_count == 0:
        # Refuse if an ACTIVE top-level officers: key exists outside our
        # markers — appending a second one would silently shadow it.
        for line in text.splitlines():
            if re.match(r"^officers:\s*(#.*)?$", line):
                raise GenerationError(
                    "platform.yml already has an unmanaged top-level 'officers:' "
                    "block — migrate it into the cabinet-init managed block "
                    "(remove it, then re-run) instead of letting two blocks shadow "
                    "each other."
                )
        sep = "" if text.endswith("\n") else "\n"
        text = f"{text}{sep}\n{block}\n"
    else:
        raise GenerationError(
            f"platform.yml marker block is corrupt ({begin_count} BEGIN / {end_count} END "
            f"markers) — repair the markers, then re-run."
        )
    return text


def resolve_target_posture(answers: dict) -> tuple[str, str]:
    """(posture, flavor) the scaffold should declare (sovereign amendment
    2026-07-05). Default guardian; an explicit `autonomy.target_posture`
    wins; otherwise a flavor-B Mini (org flavor + a `mini*` cabinet id)
    defaults to sovereign. flavor=personal is ALWAYS guardian at init —
    flavor-A lanes flip individually later, in an unlock window."""
    autonomy = answers.get("autonomy") or {}
    flavor = str(autonomy.get("flavor", "org"))
    target = autonomy.get("target_posture")
    if target is not None:
        posture = str(target)
    elif flavor == "org" and str((answers.get("cabinet") or {}).get("id", "main")).startswith("mini"):
        posture = "sovereign"
    else:
        posture = "guardian"
    if flavor == "personal":
        posture = "guardian"
    return posture, flavor


def render_posture(answers: dict) -> str:
    """The instance/config/posture.yml SCAFFOLD (FI-1 closed-key schema).

    INERT by construction: `resolve_posture` answers sovereign only for a
    present + schema-valid + deployment-matched + schg-LOCKED ruling, and
    this file is written unlocked — so generating it changes no behavior.
    The Captain ratifies by editing basis/ruled_at, committing, and running
    `sudo bash cabinet/scripts/germline-lock.sh lock` (the lock IS the
    signature, D5). ruled_at is a fixed epoch placeholder so re-runs stay
    byte-idempotent and an unratified scaffold is machine-obvious.
    """
    posture, flavor = resolve_target_posture(answers)
    cab_id = str((answers.get("cabinet") or {}).get("id", "main"))
    return f"""\
# {MARKER} — posture RULING scaffold (sovereign amendment 2026-07-05).
# INERT until the Captain ratifies: resolve_posture requires present +
# schema-valid + deployment==CABINET_ID + schg-locked; this scaffold is
# unlocked, so the deployment runs guardian (today's rules) regardless of the
# posture: value below. To ratify: set basis: to your ruling words, set
# ruled_at: to the real timestamp, commit, then
#   sudo bash cabinet/scripts/germline-lock.sh lock
# Emergency brake: CABINET_POSTURE=guardian in the environment (narrow-only).
# Closed key set — adding any other key makes the file CORRUPT (⇒ guardian).
version: 1
status: ruled
ruled_at: 1970-01-01T00:00:00Z   # placeholder — Captain sets the real ruling time
basis: "cabinet-init scaffold — guardian until the Captain ratifies by locking"
deployment: {cab_id}
flavor: {flavor}
posture: {posture}
"""


EXAMPLE_ANSWERS = """\
# instance/config/cabinet-init.answers.yml — cabinet-init interview answers.
# Written by the cabinet-init skill; consumed by cabinet/scripts/generate-instance.py.
# NAMES AND IDS ONLY — never tokens, keys, or connection strings (the
# generator refuses values that look like secrets; real values go in the
# gitignored cabinet/.env).
version: 1

captain:
  name: Ada                      # display name officers use
  timezone: Europe/Madrid        # IANA identifier
  telegram_chat_id: "12345678"   # numeric chat id (an address, not a secret)

cabinet:
  id: acme-hq                    # cabinet_id; 'main' for single-instance
  mode: single                   # single | multi (multi REQUIRES a non-'main' id)
  org_shape: portfolio           # portfolio | functional | custom
  officer_model: claude-opus-4-8[1m]

lanes:
  - name: Acme Storefront
    slug: acme-store
    repos: ["acme/storefront"]   # org/name or URL; first repo becomes product.repo
    task_system: "plugin:dev-tasks"   # plugin:<name> | linear | github-issues | none
    boards: ["1234567890"]       # board/team ids in the task system
    neon_project: acme-store-db  # NAME only
    vercel_project: storefront   # NAME only
  - name: Acme Labs
    slug: acme-labs
    repos: ["acme/labs"]
    task_system: linear
    linear_team_key: labs
    linear_workspace_url: https://linear.app/acme-labs
    boards: ["labs"]

# Guardian at init, always: propose-first everywhere, plus the hard ceiling
# (secrets / spend / external comms / production deploys never resolve
# UNCONDITIONAL auto in any posture). Graduation comes later from
# consequence-ledger evidence — see docs/consequence-ledger.md.
# The sovereign POSTURE is a post-init Captain ratification (amendment
# 2026-07-05, `apply sovereign posture`): the generator renders an INERT
# instance/config/posture.yml scaffold from the two optional keys below, and
# nothing changes until the Captain locks it (germline-lock.sh lock).
autonomy:
  posture: propose_first
  flavor: org                    # org | personal (personal ⇒ guardian scaffold, always)
  # target_posture: sovereign    # optional; default guardian ('mini*' org ids default sovereign)

integrations:
  telegram:
    ceo_bot: ""                          # bot USERNAME once created (TOKEN-TBD)
    bot_token_env: TELEGRAM_BOT_TOKEN_COS   # env var NAME; value in cabinet/.env
  mcp_env_names: []                      # extra env var NAMES officers need
"""


# ---------------------------------------------------------------------------
# Main generation pass
# ---------------------------------------------------------------------------

def generate(root: Path, answers_path: Path, dry_run: bool = False, force: bool = False) -> list:
    """Run the full generation pass. Returns the list of written paths."""
    root = root.resolve()
    answers = load_answers(answers_path)
    cabinet = answers.get("cabinet") or {}
    org_shape = str(cabinet.get("org_shape", "portfolio"))
    model = str(cabinet.get("officer_model", DEFAULT_MODEL))
    lanes = answers["lanes"]
    integrations = answers.get("integrations") or {}

    # ---- plan every output (path, content, validator) BEFORE writing ----
    outputs: list[tuple[Path, str, str]] = []  # (path, content, kind: yaml|agent-md)

    for lane in lanes:
        outputs.append((
            _instance_path(root, "config", "contexts", f"{lane['slug']}.yml"),
            render_context(lane), "yaml",
        ))
        outputs.append((
            _instance_path(root, "config", "projects", f"{lane['slug']}.yml"),
            render_project(lane, integrations), "yaml",
        ))

    if org_shape == "portfolio":
        template_path = root / LANE_CEO_TEMPLATE_REL
        if not template_path.is_file():
            raise GenerationError(
                f"lane-CEO template missing: {template_path} — the portfolio "
                f"preset must be present in this checkout (presets/portfolio/). "
                f"Without it no lane-CEO role can be generated."
            )
        template_text = template_path.read_text(encoding="utf-8")
        for lane in lanes:
            outputs.append((
                _instance_path(root, "agents", f"{lane['slug']}-ceo.md"),
                render_agent(template_text, lane, model), "agent-md",
            ))
        outputs.append((
            _instance_path(root, "config", "roster.yml"),
            render_roster(lanes, model), "yaml",
        ))

    platform_path = _instance_path(root, "config", "platform.yml")
    existing_platform = platform_path.read_text(encoding="utf-8") if platform_path.exists() else ""
    outputs.append((
        platform_path,
        render_platform(existing_platform, answers, lanes, org_shape), "yaml",
    ))

    # Posture scaffold (sovereign amendment 2026-07-05): rendered ONLY when
    # absent — an existing posture.yml is a Captain RULING (possibly ratified
    # + schg-locked) and is never regenerated, not even with --force.
    posture_path = _instance_path(root, "config", "posture.yml")
    posture_skipped = posture_path.exists()
    if not posture_skipped:
        outputs.append((posture_path, render_posture(answers), "yaml"))

    # ---- pre-write validation: every planned artifact must parse ----
    for path, content, kind in outputs:
        try:
            if kind == "yaml":
                yaml.safe_load(content)
            elif kind == "agent-md":
                parts = content.split("---", 2)
                if len(parts) < 3:
                    raise GenerationError(f"rendered agent {path.name} has no frontmatter")
                yaml.safe_load(parts[1])
        except yaml.YAMLError as e:
            raise GenerationError(f"generated content for {path} does not parse: {e}") from e

    # ---- overwrite guard (platform.yml is marker-managed, exempt) ----
    for path, _content, _kind in outputs:
        if path != platform_path:
            _check_overwrite(path, force)

    # ---- write (or report) ----
    written = []
    for path, content, _kind in outputs:
        rel = path.relative_to(root)
        if dry_run:
            print(f"[dry-run] would write {rel}")
        else:
            _atomic_write(path, content)
            print(f"wrote {rel}")
        written.append(path)

    # ---- end-of-run validation from disk ----
    if not dry_run:
        for path, _content, kind in outputs:
            on_disk = path.read_text(encoding="utf-8")
            if kind == "yaml":
                yaml.safe_load(on_disk)
            else:
                yaml.safe_load(on_disk.split("---", 2)[1])
        print("validation: all generated YAML parses")

    # ---- next steps ----
    tg = integrations.get("telegram") or {}
    token_env = str(tg.get("bot_token_env") or "TELEGRAM_COS_TOKEN")
    preset = "portfolio" if org_shape == "portfolio" else ("work" if org_shape == "functional" else "<your-preset>")
    print("\nNext steps (in order):")
    print(f"  1. echo {preset} > instance/config/active-preset")
    if org_shape == "portfolio":
        print("  2. PROPOSE germline edits to the Captain (Captain applies):")
        print("     - cabinet/mcp-scope.yml: list each lane CEO under agents:")
        print("     - cabinet/officer-capabilities.conf: add each lane CEO's rows")
        print("  3. Create the Chair bot via BotFather; put the TOKEN ONLY in")
        print(f"     cabinet/.env as {token_env}=... (canonical name:")
        print("     TELEGRAM_<OFFICER_UPPER>_TOKEN; config keeps TOKEN-TBD).")
        print("     Multi-cabinet deployments also set CABINET_MODE=multi +")
        print("     CABINET_ID=<deployment-id> in cabinet/.env — outcomes.yml")
        print("     missions only compile when CABINET_ID matches their")
        print("     deployment key.")
        print("  4. bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml")
        print("  5. bash cabinet/scripts/grant-mac-permissions.sh   # TCC grants (interactive)")
        print("  6. bash cabinet/scripts/load-preset.sh && deploy the Chair only")
        print("     (deploy-mac.sh — select the coordinating role; lane CEOs are on-demand)")
    else:
        print("  2. bash cabinet/scripts/bootstrap-roles.sh   # default functional seed")
        print("  3. bash cabinet/scripts/load-preset.sh, then deploy per docs/mac-mini-setup.md")
    print("  Nothing above activates lanes: contexts ship active: false and")
    print("  projects ship activation.status: pending until the Captain flips them.")
    if posture_skipped:
        print("  Posture: existing instance/config/posture.yml is a Captain ruling —")
        print("  left untouched (never regenerated, not even with --force).")
    else:
        p, f = resolve_target_posture(answers)
        print(f"  Posture: rendered instance/config/posture.yml scaffold (posture: {p},")
        print(f"  flavor: {f}) — INERT until the Captain ratifies by locking:")
        print("  edit basis/ruled_at, commit, then sudo bash cabinet/scripts/germline-lock.sh lock")
        print("  (unlocked/absent/mismatched always resolves guardian — today's rules).")
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--answers", default=None,
                        help="answers file (default: <root>/instance/config/cabinet-init.answers.yml)")
    parser.add_argument("--root", default=None,
                        help="repo root (default: two levels above this script)")
    parser.add_argument("--dry-run", action="store_true", help="plan + validate, write nothing")
    parser.add_argument("--force", action="store_true",
                        help="overwrite existing files that lack the generated-by marker")
    parser.add_argument("--example", action="store_true",
                        help="print a starter answers file to stdout and exit")
    args = parser.parse_args(argv)

    if args.example:
        sys.stdout.write(EXAMPLE_ANSWERS)
        return 0

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    answers_path = Path(args.answers).resolve() if args.answers else root / "instance/config/cabinet-init.answers.yml"

    try:
        generate(root, answers_path, dry_run=args.dry_run, force=args.force)
    except GenerationError as e:
        print(f"[generate-instance] ERROR: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
