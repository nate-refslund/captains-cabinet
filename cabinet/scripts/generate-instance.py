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
                                                — the HIRE record. Carries the
                                                Chair plus ONLY those lane CEOs
                                                the germline pair already
                                                authorizes (see "Hiring is
                                                authorization-gated" below).
  instance/config/posture.yml                   INERT posture RULING scaffold (only when
                                                absent — an existing ruling is never
                                                regenerated; sovereign amendment 2026-07-05)
  instance/config/sources.yml                   personal-sensing seam binding — see the
                                                emission rule below
  instance/config/platform.yml                  also gains an `org_vault_dir:` key
                                                (only when absent, and only when no
                                                legacy `product_brain_dir:` key already
                                                carries a hand-edited value) defaulting
                                                to `vault` — RELATIVE to the deployment
                                                root, i.e. <root>/vault (never an
                                                absolute machine path: generated config
                                                stays relocatable + launcher-free).
                                                Canonical resolver:
                                                framework.env.org_vault_dir(), which
                                                honors CABINET_ORG_VAULT_DIR (legacy
                                                CABINET_PRODUCT_BRAIN_DIR alias), then
                                                THIS key (relative → resolved against
                                                CABINET_ROOT, existence-gated; legacy
                                                product_brain_dir key honored after it),
                                                then the in-repo <root>/vault directory

  instance/config/active-project.txt            the first lane's slug (only when
                                                absent — an existing deployment's
                                                active project is operator state
                                                and is never touched). Read by
                                                bootstrap-roles.sh (product slug)
                                                and start-officer-mac.sh
                                                (CABINET_LANE); without it a
                                                fresh hatch's bootstrap-roles
                                                exits 1.

Generated (org_shape: functional | custom): contexts + projects + captain keys
only — the functional preset ships its own five-officer roster (default
`bootstrap-roles.sh`, no --roster); custom shapes author agents/roster by hand.
(active-project.txt is emitted for every shape.)

Hiring is authorization-gated (roster-authz, 2026-07-26). An officer is only
usable if cabinet/officer-capabilities.conf grants it capability rows AND
cabinet/mcp-scope.yml lists it under `agents:` — without those, every
capability-gated behavior is off and pre-tool-use.sh rejects every mcp__* call
it makes. Both files are GERMLINE: this generator and hatch.sh never write
them (hatch-lib/errands.sh errand 1, "Captain's hands only"). So the generator
reads them as the authorization surface and ROSTERS ONLY WHAT THEY COVER. A
lane whose CEO is not yet authorized still gets its context, project and agent
file (all inert) and is recorded as PENDING in roster.yml + printed as
paste-ready germline rows; the hatch completes Chair-only and GREEN, and
re-running the generator after the Captain applies the rows hires the lane CEO.
Before this gate the generator hired `<lane>-ceo` unconditionally, which the
Captain was structurally forbidden to authorize inside the automated hatch —
and framework/tests/test_roster_conf_lockstep.py then failed the deployment
for the resulting lockout (a gate the hatch could not satisfy).

Adopting a clone that ships another deployment's instance/ (--adopt): a fresh
captain hatching from a clone that carries a PREVIOUS deployment's committed
instance/ (hand-authored sources.yml, an unmanaged officers block in
platform.yml, live contexts/projects) would otherwise hit marker refusals one
file at a time and hand-edit another captain's config on day one. `--adopt`
archives each conflicting file to instance/_pre-adopt-<UTC-stamp>/<relpath>
(inside instance/, path-contained, nothing deleted) and generates fresh. An
existing posture.yml is STILL never touched (Captain ruling), and --adopt never
widens what --force would not: it only relocates files the generator was about
to refuse over. When a refusal fires on an instance/ whose platform.yml carries
a DIFFERENT captain than the answers (the inherited-clone signal), the refusal
message names the previous captain and teaches --adopt as the fix.

Defaults fast lane (--defaults, init-fastlane 2026-07-09): a zero-question
non-interactive hatch for a stranger/demo deployment. Writes a marker-stamped
consent-safe answers file (captain from --captain-name, else $USER, else
"Captain"; timezone UTC placeholder; chat id "0000" placeholder; cabinet
id main/single/portfolio; one placeholder lane `first-lane`; autonomy
propose_first + flavor org + target_posture guardian; env-var NAMES only)
and then runs the EXACT same generation path as the interview. It never
overwrites an interview-written answers file (no marker => refusal teaching
--adopt, which archives it like every other adopted file; --force
deliberately does NOT override this one refusal — the answers file is the
captain's interview record, and archive-over-clobber is the only honest
path); a marker-stamped defaults answers file is rewritten (the generator
owns it). The answers TARGET must be named `*.answers.yml` — the one
filename shape no generated instance file can occupy — so a custom
--answers can never aim the defaults write at a generator output
(posture.yml, platform.yml, sources.yml, roster.yml, active-project.txt,
contexts/, projects/), marker-stamped or not. All existing guardrails
(path jail, secret refusal, marker overwrite protection, idempotency)
apply unchanged. The full interview stays the default lane for real
captains.

sources.yml emission rule (Wave-1 OrgSource, 2026-07-07): the answers'
`autonomy.flavor` key is the signal for whether this deployment has a personal
(captain screenpipe/vault) sensing estate — that is the axis's literal meaning
(axes-contract; org_shape is officer TOPOLOGY and says nothing about estates).
  * flavor != personal (i.e. `org`, the default): emit a generated-by-marked
    instance/config/sources.yml binding `framework.sources.org:OrgSource`, so a
    fresh org instance gets real recall instead of fail-closing to
    NullPersonalSource (zero hits). No `dispatch:` is emitted — get_dispatch()
    fail-closes to NullPersonalDispatch (draft-capture-only), correct for a box
    with no personal actuator estate.
  * flavor == personal (Flavor-A): emit a generated-by-marked sources.yml
    binding `framework.sources.local:LocalNotesSource` with the `local_root:`
    THE ANSWERS DECLARE (`sources.notes_root`). CHANGED 2026-07-28: that value
    used to be HARDCODED to `vault`, which the answers file had no way to
    override — and `vault/` on a fresh clone is the CABINET'S OWN SHIPPED DOCS
    (vault/README.md, vault/architecture.md are tracked). So a personal hatch
    silently bound the framework's documentation as the operator's notes and
    reported `available() True`: a confident false positive. When the answers
    declare nothing, `local_root:` is emitted COMMENTED OUT, the adapter
    resolves UNSET, and recall reports honestly unavailable rather than
    answering out of a plausible-looking wrong folder. CHANGED 2026-07-27: this
    used to emit NOTHING, which fail-closed the ONE flavor shaped for a
    non-company operator to NullPersonalSource — available() False, search()
    {"hits": []} — i.e. the personal preset shipped inert. A captain who
    binds a richer personal adapter by hand still wins: the file is
    marker-guarded like every other, so a hand-authored binding is REFUSED,
    never clobbered. Still no `dispatch:` — the local adapter is structurally
    read-only (framework/sources/local.py has no write side at all), so
    writes stay draft-capture-only on both flavors.
An existing sources.yml follows the standard marker convention: with the
generated-by marker it is rewritten byte-identically; without it (hand-authored,
e.g. a live Flavor-A binding) the run REFUSES rather than clobbering
(--force overrides, as everywhere else).

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
                                               [--dry-run] [--force] [--adopt]
  python3 cabinet/scripts/generate-instance.py --defaults [--captain-name NAME] [--adopt]
                                               # zero-question fast lane: write a
                                               # defaults answers file, then generate
  python3 cabinet/scripts/generate-instance.py --example   # print a starter answers file
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import json
import sys
import tempfile
from datetime import datetime, timezone
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

# Availability dial (Captain ruling 2026-07-26). The verb enum and its minute
# bands come from framework.env — THE one source of truth — so a band change
# never has to be mirrored here. The generator accepts EVERY canonical mode
# (including `away`: a captain who is away at init has made a real declaration);
# the interview's own question offers the narrower set it makes sense to ASK.
# An ABSENT key stays absent: unknown is a legal state, never a default.
_FRAMEWORK_ROOT = str(Path(__file__).resolve().parents[2])
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)
from framework import env as _fenv  # noqa: E402  (after the sys.path insert)
from framework.onboarding import estate as _estate  # noqa: E402

AVAILABILITY_VERBS = frozenset(_fenv.availability_modes())

# The operator's RUNG (Captain ruling 2026-07-26 — the north star is an AIM,
# not an entry bar). Fixed verb enum, sourced from framework.onboarding.estate
# so the vocabulary has ONE home: a developer inside a large company occupies
# `contributor`, and the cabinet must be valuable there. ABSENT is a
# first-class answer meaning UNKNOWN — never defaulted, never invented — and
# an unknown altitude reproduces the pre-altitude behaviour exactly.
ALTITUDES = frozenset(_estate.ALTITUDES)

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

# The AUTHORIZATION surface for a hire (roster-authz, 2026-07-26). Both are
# germline — this generator and hatch.sh NEVER write them (hatch-lib/errands.sh
# errand 1: "Captain's hands only") — so the generator READS them and hires
# only officers they already cover. An officer rostered without a capability
# row and an `agents:` row is a silent capability/MCP-scope lockout, and
# framework/tests/test_roster_conf_lockstep.py fails the deployment for it.
OFFICER_CONF_REL = "cabinet/officer-capabilities.conf"
MCP_SCOPE_REL = "cabinet/mcp-scope.yml"
# The coordinating officer id. Reserved (see RESERVED_SLUGS) so no lane can
# shadow it; hatch.sh's own proof steps name it directly.
CHAIR_SLUG = "cos"

DEFAULT_MODEL = "claude-opus-4-8[1m]"

# Defaults fast lane (--defaults): the fixed consent-safe answers set. All
# placeholders are syntactically valid (they pass load_answers) and obviously
# placeholders — honest defaults, never invented captain data.
DEFAULTS_CAPTAIN_FALLBACK = "Captain"
DEFAULTS_LANE_NAME = "First Lane"
DEFAULTS_LANE_SLUG = "first-lane"
DEFAULTS_CHAT_ID_PLACEHOLDER = "0000"

# Posture scaffold vocabulary (sovereign amendment 2026-07-05, FI-1).
POSTURE_FLAVORS = frozenset({"org", "personal"})
POSTURE_TARGETS = frozenset({"guardian", "sovereign"})

# The org-box recall binding emitted into instance/config/sources.yml (see the
# module-docstring emission rule). Resolver contract: framework.sources
# _load_bound() reads `adapter: "<module>:<Class>"` and importlib-loads it;
# framework/sources/ is one of its two trusted module trees.
ORG_SOURCE_ADAPTER = "framework.sources.org:OrgSource"

# The personal-box recall binding. Same resolver contract, different backend:
# OrgSource reads cabinet_memory (needs a connection string + an embedding
# provider), which a laptop with a notes folder has neither of, so binding it
# there would fail-close to the same zero hits the null adapter gives. The
# local adapter reads ONE declared folder and is structurally read-only.
LOCAL_SOURCE_ADAPTER = "framework.sources.local:LocalNotesSource"

# platform.yml key naming the org's knowledge-corpus dir — the cabinet VAULT
# (vault/, Captain-ratified 2026-07-16; formerly product-brain/). Canonical
# resolver: framework.env.org_vault_dir() (CABINET_ORG_VAULT_DIR env override,
# legacy CABINET_PRODUCT_BRAIN_DIR alias, else THIS platform.yml key — relative
# values resolve against the repo root, existence-gated; the legacy
# product_brain_dir key is honored after it — else the in-repo <root>/vault
# directory, else the legacy <root>/product-brain, else ""). The generator
# stamps the key (only when absent, and never when a legacy product_brain_dir
# key already exists — a hand-edited legacy value must keep winning) so the
# deployment's corpus location is declared in config alongside state_dir and
# the captain keys, and a captain relocates the corpus by editing it.
# The stamped VALUE is relative to the deployment root ("vault" ⇒
# <root>/vault, the resolver's own default) — never an absolute
# machine path, so generated config stays relocatable and launcher-free.
ORG_VAULT_KEY = "org_vault_dir"
ORG_VAULT_DEFAULT = "vault"
LEGACY_ORG_VAULT_KEY = "product_brain_dir"   # pre-rename key, suppression-checked

# The answers key a PERSONAL deployment declares its own notes folder under —
# the one folder framework.sources.local:LocalNotesSource reads, read-only.
# THERE IS NO DEFAULT, deliberately (2026-07-28). `local_root:` used to be
# hardcoded to ORG_VAULT_DEFAULT with no answers-file override at all, so a
# fresh personal hatch bound <root>/vault — the cabinet's OWN shipped docs, two
# tracked files — and `available()` returned True over the framework's
# documentation. An operator cannot tell that apart from working recall, which
# makes it worse than the honest empty it replaced. Undeclared now emits the
# key commented out; resolve_root() returns None and recall says so.
SOURCES_KEY = "sources"
NOTES_ROOT_KEY = "notes_root"
# Refuses control characters, NUL, and a bare empty/whitespace value. A path
# is otherwise unconstrained on purpose: an operator's notes folder is usually
# an ABSOLUTE machine path ("~/Documents/notes"), which is exactly what the
# adapter's resolve_root() expanduser()s and jails. instance/config/ is
# deployment-local, so an absolute path here never enters the shipped tree.
NOTES_ROOT_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,4096}$")

# The presets tree location, repo-root-relative. The CABINET layer owns this
# knowledge (same as load-preset.sh): framework code must not hardcode where
# presets/ lives (layer-separation gate), so framework.onboarding's CLI
# resolves its --presets-dir default FROM this constant (via the same
# importlib load onboard._default_render already uses for the renderer).
PRESETS_DIR_REL = "presets"

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


def load_answers(path: Path, root: Path | None = None) -> dict:
    """Load + validate the answers. ``root`` is the deployment root the
    derived-estate artifact is read from for the lanes-derivable gate below;
    it defaults to two levels above this script, which is the deployment root
    in every non-scratch run."""
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
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
    # OPTIONAL availability dial (Captain ruling 2026-07-26). ABSENT is a
    # first-class answer meaning UNKNOWN — "the org does not know how much of
    # the captain it is entitled to" — so this key is never defaulted or
    # invented here. A PRESENT value must be one of the fixed verbs; a typo
    # refuses loudly rather than silently stamping a budget nobody declared.
    availability = captain.get("availability")
    if availability is not None:
        verb = str(availability).strip().lower()
        if verb not in AVAILABILITY_VERBS:
            raise GenerationError(
                f"captain.availability {availability!r} must be one of "
                f"{sorted(AVAILABILITY_VERBS)} (fixed verb enum) — omit the "
                f"key entirely to leave availability unknown"
            )

    cabinet = answers.get("cabinet") or {}
    org_shape = str(cabinet.get("org_shape", "portfolio"))
    if org_shape not in ORG_SHAPES:
        raise GenerationError(f"cabinet.org_shape must be one of {ORG_SHAPES}, got {org_shape!r}")
    # OPTIONAL preset choice (2026-07-17, developer-preset wave). Never a
    # default flip: absent → the org_shape default (portfolio/work) in the
    # printed next steps. Shape-validated only — the preset rail accepts
    # free slugs (framework.env.active_preset / load-preset.sh), so shipped
    # names (work, portfolio, developer, personal) and custom slugs both
    # pass; SLUG_RE already refuses path segments and `_template` (leading
    # underscore). Used ONLY in the printed activation step — no file writes.
    preset_choice = cabinet.get("preset")
    if preset_choice is not None:
        if not SLUG_RE.match(str(preset_choice)):
            raise GenerationError(
                f"cabinet.preset {preset_choice!r} must be a preset slug "
                f"(kebab-case, e.g. work | portfolio | developer | personal)"
            )
    cab_id = str(cabinet.get("id", "main"))
    if not SLUG_RE.match(cab_id):
        raise GenerationError(f"cabinet.id {cab_id!r} must match {SLUG_RE.pattern}")
    model = str(cabinet.get("officer_model", DEFAULT_MODEL))
    if not re.match(r"^[a-z0-9][a-z0-9.\[\]-]{0,63}$", model):
        raise GenerationError(f"cabinet.officer_model {model!r} has an unexpected shape")

    # OPTIONAL mission block (purpose-first interview). The generator ignores
    # purpose/success_90d/never_touch — genesis conditions cards on them — but
    # it OWNS answers validation, so a mistyped altitude refuses loudly here
    # rather than silently resolving to UNKNOWN and quietly selecting the
    # wrong preset. An absent block and an absent altitude both stay unknown.
    mission = answers.get("mission")
    if isinstance(mission, dict) and mission.get("altitude") is not None:
        verb = str(mission.get("altitude")).strip().lower()
        if verb not in ALTITUDES:
            raise GenerationError(
                f"mission.altitude {mission.get('altitude')!r} must be one of "
                f"{sorted(ALTITUDES)} (the operator's rung — omit the key "
                f"entirely to leave it unknown)"
            )

    # LANES ARE DERIVABLE (ordering inversion, Captain ruling 2026-07-26).
    # This refusal used to be absolute — "answers must declare at least one
    # lane" — and a lane IS a product, so a developer inside a large company
    # could only invent one or take the --defaults placeholder. Now an EMPTY
    # lane list is legal WHEN DISCOVERY HAS RUN for this deployment: the
    # derived-estate artifact is the proof that the cabinet looked, and the
    # lanes it found are proposed in instance/config/lanes-proposed.yml for
    # the Captain to ratify into this file. An empty estate still passes —
    # "I looked and found nothing" is a legitimate lane-less state, answered
    # by the briefing's read-your-world card, not by a fabricated lane. What
    # stays refused is lanes: [] with NO artifact at all: nobody ever looked.
    lanes = answers.get("lanes")
    if not isinstance(lanes, list):
        raise GenerationError("answers lanes: must be a list")
    if not lanes:
        deployment = str((answers.get("cabinet") or {}).get("id", "main"))
        usable, reason = _estate.estate_is_usable(
            _estate.load_estate(root), deployment)
        if not usable:
            raise GenerationError(
                f"answers declare no lanes and no usable derived estate "
                f"({reason}). Either add a lane under lanes:, or let the "
                f"cabinet READ your world first — grant a First Window and "
                f"run `bash cabinet/scripts/formation.sh`, which derives "
                f"{_estate.ESTATE_REL} and proposes lanes in "
                f"{_estate.LANES_PROPOSED_REL}."
            )
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

    # OPTIONAL recall scope (2026-07-28). `sources.notes_root` is the ONE
    # folder a personal deployment grants the local read-only adapter. ABSENT
    # is a first-class answer meaning "nobody granted a folder yet" — never
    # defaulted here, because the default this replaced (`vault`) silently
    # bound the cabinet's own shipped docs and reported working recall.
    sources_block = answers.get(SOURCES_KEY)
    if sources_block is not None:
        if not isinstance(sources_block, dict):
            raise GenerationError(
                f"answers {SOURCES_KEY}: must be a mapping "
                f"(e.g. {SOURCES_KEY}:\n  {NOTES_ROOT_KEY}: ~/notes)"
            )
        notes_root = sources_block.get(NOTES_ROOT_KEY)
        if notes_root is not None:
            value = str(notes_root)
            if not NOTES_ROOT_RE.match(value.strip()) or not value.strip():
                raise GenerationError(
                    f"{SOURCES_KEY}.{NOTES_ROOT_KEY} {notes_root!r} must be a "
                    f"single-line filesystem path (absolute, ~-prefixed, or "
                    f"relative to the deployment root) — omit the key entirely "
                    f"to leave recall UNSET, which reports honestly unavailable"
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


def _check_overwrite(path: Path, force: bool, hint: str = "") -> None:
    """Refuse to clobber a file the generator does not own (no marker).

    ``hint`` (optional) is appended to the refusal so the message can teach
    the right fix — e.g. the inherited-instance --adopt suggestion."""
    if path.exists() and MARKER not in path.read_text(encoding="utf-8"):
        if not force:
            msg = (
                f"REFUSING to overwrite {path}: existing file lacks the "
                f"'{MARKER}' marker (hand-authored?). Re-run with --force to "
                f"overwrite, or move the file aside."
            )
            if hint:
                msg += "\n" + hint
            raise GenerationError(msg)


def _existing_captain_name(root: Path) -> str:
    """Best-effort read of the CURRENT instance's captain (the top-level
    `captain_name:` key in instance/config/platform.yml). Read-only; used
    solely as the inherited-instance signal for refusal messages — a value
    differing from the incoming answers' captain means this instance/ likely
    belongs to a previous deployment and --adopt is the fix."""
    platform = root / "instance" / "config" / "platform.yml"
    if not platform.is_file():
        return ""
    try:
        text = platform.read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"^captain_name:\s*([^#\n]*)", text, re.MULTILINE)
    if not m:
        return ""
    return m.group(1).strip().strip("'\"")


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
  description: {_yaml_free(lane.get('one_liner') or name + ' lane')}
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
  team_key: {_yaml_free(linear_team)}
  workspace_url: {_yaml_free(linear_url)}

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
  ceo_bot: {_yaml_free(ceo_bot)}             # TOKEN-TBD — token lives ONLY in cabinet/.env ({token_env})
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
        f"# This role definition is INERT until the role is hired. To hire it:\n"
        f"# list {lane['slug']}-ceo under agents: in cabinet/mcp-scope.yml + add its\n"
        f"# rows to cabinet/officer-capabilities.conf (germline files — propose to\n"
        f"# the Captain), then RE-RUN generate-instance.py (which is what adds it to\n"
        f"# instance/config/roster.yml — the generator never rosters an officer those\n"
        f"# two files do not authorize) and seed via\n"
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


def _conf_officer_column(path: Path) -> set:
    """Officer slugs in cabinet/officer-capabilities.conf's `officer:capability`
    column. Mirrors framework.env.officers()'s documented parse (skip blank /
    `#` / no-colon lines, take the text left of the first colon) rather than
    importing it: env.officers() caches process-globally against a FIXED
    resolved path, so it cannot be pointed at an arbitrary root. Same mirroring
    rationale as framework/tests/test_roster_conf_lockstep.py's own parser.

    REFUSES a padded row (leading or trailing whitespace), naming file and
    line. This parser only *reads* authorization; the hooks that ENFORCE it are
    line-anchored — post-tool-use.sh's has_capability() is
    `grep -q "^${OFFICER}:${cap}$"` and pre-captain-dm.sh's gate is
    `grep -qxF "${OFFICER}:captain_rules_retrieval"`. Both miss a padded row.
    A lenient read here would therefore be MORE PERMISSIVE than the greps that
    decide at runtime: the generator would hire the officer while every
    capability gate stayed silently off — the exact silent lockout this whole
    authorization gate exists to prevent, re-created one indent deep. Loud
    beats silent, so a padded row is an error, not a slug."""
    if not path.is_file():
        return set()
    out = set()
    for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        if line != s:
            raise GenerationError(
                f"{path}:{lineno}: capability row {line!r} is padded with "
                f"whitespace. Rows in {OFFICER_CONF_REL} must start at column 0 "
                f"and end at the capability, because the hooks that enforce "
                f"capabilities match whole lines "
                f"(post-tool-use.sh `grep -q \"^officer:capability$\"`, "
                f"pre-captain-dm.sh `grep -qxF`). A padded row authorizes "
                f"NOTHING at runtime, so reading it as authorization would hire "
                f"an officer straight into a silent capability lockout. Strip "
                f"the whitespace, then re-run."
            )
        officer = s.split(":", 1)[0].strip()
        if officer:
            out.add(officer)
    return out


def _scope_agent_keys(path: Path) -> set:
    """Hired-agent keys in cabinet/mcp-scope.yml's `agents:` mapping. A
    `scaffolds:` entry is deliberately NOT authorization — that section means
    "scope reserved, NOT hired" by the file's own contract."""
    if not path.is_file():
        return set()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise GenerationError(
            f"{path}: could not parse the MCP scope file ({exc}) — the hatch "
            f"cannot tell which officers are authorized. Fix the YAML first."
        )
    agents = (data or {}).get("agents") or {}
    return set(agents.keys()) if isinstance(agents, dict) else set()


def authorized_officers(root: Path) -> set:
    """The officer slugs THIS deployment can actually authorize: present in
    cabinet/officer-capabilities.conf's officer column AND in
    cabinet/mcp-scope.yml's `agents:` mapping.

    Both are required, because each one alone is a silent lockout: no
    capability row ⇒ every capability-gated behavior is off for that officer;
    no `agents:` row ⇒ pre-tool-use.sh rejects every mcp__* call the officer's
    session makes. framework/tests/test_roster_conf_lockstep.py asserts exactly
    this pair over a live roster.yml.

    Both files are GERMLINE — hatch.sh and this generator never write them
    (cabinet/scripts/hatch-lib/errands.sh errand 1: "Captain's hands only").
    So the generator reads them as the authorization surface and hires only
    what they already cover; an absent file authorizes nothing (fail-closed —
    inability to prove authorization is never permission)."""
    return (_conf_officer_column(root / OFFICER_CONF_REL)
            & _scope_agent_keys(root / MCP_SCOPE_REL))


def split_lane_hires(root: Path, lanes: list) -> tuple:
    """(hired, pending) lanes for `lanes`, in lane order.

    `hired` lands in roster.yml (bootstrap-roles.sh seeds it, deploy-mac.sh
    derives the fleet from it); `pending` is printed as paste-ready germline
    rows and recorded as a comment block in roster.yml. Re-running the
    generator after the Captain applies the rows promotes a pending lane CEO
    to hired — the errand closes itself, and no errand ever blocks the hatch.

    The Chair (`cos`) is not a lane hire: it is the cabinet's own coordinating
    surface, named directly by hatch.sh's own proof steps, and every shipped
    germline pair carries its rows. It is therefore always rostered — but when
    BOTH germline files are present and neither authorizes it, that is a
    stripped/broken authorization surface and the run REFUSES rather than
    hiring a Chair the deployment cannot authorize."""
    authorized = authorized_officers(root)
    conf_path, scope_path = root / OFFICER_CONF_REL, root / MCP_SCOPE_REL
    if (conf_path.is_file() and scope_path.is_file()
            and CHAIR_SLUG not in authorized):
        raise GenerationError(
            f"the Chair ({CHAIR_SLUG}) is not authorized by this checkout's "
            f"germline pair — it needs capability rows in {OFFICER_CONF_REL} "
            f"AND an `agents:` entry in {MCP_SCOPE_REL}. Rostering it anyway "
            f"would be a silent capability/MCP-scope lockout on the one "
            f"officer the whole hatch depends on. Add the rows (Captain "
            f"applies germline files), then re-run."
        )
    hired, pending = [], []
    for lane in lanes:
        (hired if f"{lane['slug']}-ceo" in authorized else pending).append(lane)
    return hired, pending


# Section delimiters inside the printed block. They are COMMENTS in both
# target formats (`#` starts a comment in officer-capabilities.conf and in
# YAML), so a Captain who pastes the block including its headers still gets a
# valid file — the block is copy-paste all the way down, not copy-paste-then-
# hand-edit. Tests split the block on these exact strings.
CONF_ROWS_HEADER = f"# --- {OFFICER_CONF_REL} — append these rows ---"
SCOPE_ROWS_HEADER = (f"# --- {MCP_SCOPE_REL} — add under the existing "
                     f"'agents:' key ---")


def germline_rows_for(lane_slugs: list) -> str:
    """Paste-ready germline rows that would authorize `lane_slugs`, exactly as
    the two germline files want them. Printed for the Captain (errand 1) and
    never written by this generator. `mcps: []` is deliberate: an empty scope
    is fail-closed, and which servers a lane needs is the Captain's call.

    INDENTATION IS THE CONTRACT, not cosmetics (fixed 2026-07-26; the first
    cut of this function got both blocks wrong and the errand could not close
    itself):

    * conf rows start at COLUMN 0. cabinet/officer-capabilities.conf is not
      YAML — the hooks that enforce capabilities match whole lines
      (post-tool-use.sh `grep -q "^officer:capability$"`, pre-captain-dm.sh
      `grep -qxF`). An indented row authorizes nothing at runtime, so a lane
      pasted that way is hired with every capability gate silently OFF.
    * mcp-scope keys sit at 2 spaces (siblings of the existing `agents:`
      children) with their fields at 4. Printed one level deeper, the paste
      nests the new officer INSIDE the previous agent's mapping — the lane is
      still un-hired and its neighbour's scope is corrupted too.

    cabinet/scripts/tests/test_generate_instance.py's paste-and-rerun arm
    applies this block byte-for-byte and then re-runs the generator, so the
    format is pinned by the errand actually closing, not by a substring."""
    caps = [c.strip() for c in LANE_CEO_CAPABILITIES.strip("[] ").split(",")]
    caps = [c for c in caps if c]
    if not caps:
        raise GenerationError(
            "LANE_CEO_CAPABILITIES parsed to zero capabilities — the printed "
            "germline rows would authorize nothing; fix the constant.")
    lines = [CONF_ROWS_HEADER]
    for slug in lane_slugs:
        for cap in caps:
            lines.append(f"{slug}-ceo:{cap}")
    lines.append(SCOPE_ROWS_HEADER)
    for slug in lane_slugs:
        lines.append(f"  {slug}-ceo:")
        lines.append("    mcps: []            # add the servers THIS lane needs")
        lines.append("    rationale: >")
        lines.append("      Lane CEO — scope chosen by the Captain.")
    return "\n".join(lines)


def render_roster(lanes: list, model: str, root: Path) -> str:
    """roster.yml — the HIRE record.

    A lane CEO is emitted ONLY when the germline pair already authorizes it
    (see authorized_officers). Hiring an officer with no capability row and no
    MCP scope row is a silent capability/MCP-scope lockout — the bug class
    framework/tests/test_roster_conf_lockstep.py exists to catch — and the
    generator cannot fix it itself, because writing those two files is the
    Captain's act. So it does not create the debt: unauthorized lanes are
    recorded as PENDING (their context/project/agent files still generate,
    inert), the Chair-only hatch completes green, and re-running after the
    Captain pastes the rows hires them."""
    hired, pending = split_lane_hires(root, lanes)
    lane_blocks = []
    for lane in hired:
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
    pending_block = ""
    if pending:
        pending_lines = "\n".join(f"#   {lane['slug']}-ceo" for lane in pending)
        pending_block = f"""
#
# PENDING AUTHORIZATION — generated but NOT hired by this roster:
{pending_lines}
# A lane CEO is hired only once BOTH germline files carry its rows
# (cabinet/officer-capabilities.conf capability rows + cabinet/mcp-scope.yml
# agents: entry). Hiring one without them is a silent capability/MCP-scope
# lockout, so this generator refuses to create that debt — it never writes
# germline files (the Captain applies them). The lane's context/project/agent
# files ARE generated (inert). Paste the rows generate-instance.py printed,
# then re-run it: the pending CEO moves into the roster below."""
    return f"""# {MARKER} — roster snippet for the portfolio shape.
# Seed it:  bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml
# Parser contract (bootstrap-roles.sh): 2-space role keys; 4-space
# title/model/capabilities/authority_level fields; `type:` is read by
# humans + the supervisor config and ignored by bootstrap. Capability
# lists mirror cabinet/officer-capabilities.conf — add matching rows
# there for every lane CEO (germline file: the Captain applies).{pending_block}
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


def render_sources() -> str:
    """instance/config/sources.yml for an ORG-flavor deployment (see the
    module-docstring emission rule). Binds the framework-side OrgSource so a
    fresh org instance has real recall; deliberately NO `dispatch:` key — the
    write seam fail-closes to NullPersonalDispatch (draft-capture-only)."""
    return f"""\
# {MARKER} — personal-sensing seam binding for an ORG-flavor deployment
# (regenerate via cabinet/scripts/generate-instance.py; emitted because the
# answers declare autonomy.flavor != personal — an org box has no captain
# screenpipe/vault estate, so recall binds the cabinet's OWN memory estate).
#
# framework.sources.get_source() reads `adapter: "<module>:<Class>"` from this
# file, importlib-loads the module (framework/sources/ is a trusted adapter
# tree), instantiates the class, and binds it as the PersonalSource framework
# CORE queries. Without this file the deployment fail-closes to
# NullPersonalSource — honest, but ZERO recall on every gather.
adapter: {ORG_SOURCE_ADAPTER}

# No dispatch: binding — an org box has no personal WRITE/actuator estate.
# framework.sources.get_dispatch() fail-closes to NullPersonalDispatch: every
# write no-ops and the egress lanes degrade to draft-capture-only.
"""


def declared_notes_root(answers: dict) -> str | None:
    """The operator's declared notes folder (``sources.notes_root``), or None.

    ONE resolution, so the renderer and the printed next steps cannot drift.
    None means UNSET — nobody granted a folder — and every caller must treat
    that as a scope that was never granted, never as a path to guess at."""
    block = answers.get(SOURCES_KEY)
    if not isinstance(block, dict):
        return None
    value = block.get(NOTES_ROOT_KEY)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def render_sources_personal(local_root: str | None) -> str:
    """instance/config/sources.yml for a PERSONAL-flavor deployment.

    Emitted since 2026-07-27: before this, `flavor: personal` emitted no
    sources.yml at all, so the one flavor shaped for an operator who does not
    run a company fail-closed to NullPersonalSource — zero recall on every
    gather.

    ``local_root`` is whatever the answers declared (``sources.notes_root``),
    read by framework.sources.local.resolve_root(); it may be absolute,
    ~-prefixed, or relative to the deployment root. ``None`` means the answers
    declared NOTHING, and the key is then emitted COMMENTED OUT so the adapter
    resolves UNSET. That case used to be impossible: the value was hardcoded to
    `vault`, i.e. the cabinet's own shipped docs, and a personal box reported
    live recall over the framework's documentation (measured 2026-07-28). An
    honest unavailable is worth more than a plausible wrong folder, because the
    operator can act on the first and cannot even see the second."""
    if local_root:
        root_line = f"local_root: {local_root}"
    else:
        root_line = (
            "# local_root: /path/to/your/notes\n"
            "#\n"
            "# UNSET — the answers file declared no `sources.notes_root`, so no\n"
            "# folder has been granted. The adapter resolves NO root, available()\n"
            "# returns False, and every gather reports honestly empty. Point it\n"
            "# somewhere by declaring sources.notes_root in\n"
            "# instance/config/cabinet-init.answers.yml and re-running\n"
            "# cabinet/scripts/generate-instance.py, by uncommenting the line\n"
            "# above, or by exporting CABINET_LOCAL_SOURCE_ROOT.\n"
            "#\n"
            "# There is deliberately NO default. Until 2026-07-28 this fell back\n"
            "# to <root>/vault — the cabinet's OWN shipped documentation — and\n"
            "# reported working recall over it, which an operator cannot tell\n"
            "# apart from their own notes."
        )
    return f"""\
# {MARKER} — personal-sensing seam binding for a PERSONAL-flavor deployment
# (regenerate via cabinet/scripts/generate-instance.py; emitted because the
# answers declare autonomy.flavor: personal — a personal box has no
# cabinet_memory estate, so recall binds a folder of notes instead).
#
# framework.sources.get_source() reads `adapter: "<module>:<Class>"` from this
# file, importlib-loads the module (framework/sources/ is a trusted adapter
# tree), instantiates the class, and binds it as the PersonalSource framework
# CORE queries. Without this file the deployment fail-closes to
# NullPersonalSource — honest, but ZERO recall on every gather.
adapter: {LOCAL_SOURCE_ADAPTER}

# The ONE folder the adapter reads — YOUR notes, declared in the answers file
# as sources.notes_root. Absolute, ~-prefixed, or relative to this deployment
# root; all three are honored.
# Bounds are the adapter's, not this file's: text extensions only, a file cap,
# a per-file byte cap, hidden dirs skipped, and every path realpath-jailed
# inside this root (a symlink out of the folder is skipped, never followed).
# CABINET_LOCAL_SOURCE_ROOT overrides this at runtime.
{root_line}

# No dispatch: binding, and it is not an omission. framework/sources/local.py
# has NO write side — a folder pointed at material the operator does not own
# can be recalled but never written back, and no setting here can change that.
# get_dispatch() fail-closes to NullPersonalDispatch (draft-capture-only).
"""


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


def _set_top_level_key_if_absent(text: str, key: str, value: str, comment: str = "") -> str:
    """Append `key: value` at top level ONLY when no such key exists yet.

    Unlike ``_set_top_level_key`` this never replaces: it is used for keys the
    generator has no answers-file source for (e.g. ``org_vault_dir``), so a
    captain's hand-edited value must survive every re-run."""
    if re.search(rf"^{re.escape(key)}:", text, re.MULTILINE):
        return text
    suffix = f"    {comment}" if comment else ""
    sep = "" if text.endswith("\n") else "\n"
    return f"{text}{sep}{key}: {value}{suffix}\n"


def _yaml_str(value: str) -> str:
    """Render ``value`` as a YAML scalar that round-trips as EXACTLY that
    string. Plain-safe values emit bare (byte-stable for every existing
    config, and shell greppers — e.g. hooks/post-tool-use.sh's awk — keep
    seeing unquoted names). Values YAML would silently retype — captain
    names like "yes"/"Null" (bool/null), "0000" (int), "2026-01-01" (date) —
    emit double-quoted, because a name that loads back as True is invented
    data. Quoting needs no escaping: every call site is NAME_RE-validated,
    and NAME_RE forbids '"' and '\\'."""
    try:
        if yaml.safe_load(value) == value:
            return value
    except yaml.YAMLError:
        pass
    return f'"{value}"'


def _yaml_free(value: str) -> str:
    """A YAML double-quoted scalar for ARBITRARY FREE TEXT — one-liners, URLs,
    bot usernames — that is NOT NAME_RE-validated. Unlike ``_yaml_str`` (which
    assumes no ``"``/``\\`` and does NO escaping), this properly escapes quotes,
    backslashes, and control chars so a stray quote can't abort generation and a
    backslash can't silently mutate the stored value (egg-hatch-engine-5).
    ``json.dumps`` output is a valid YAML double-quoted scalar (YAML's dq style
    is a JSON-string superset); ``ensure_ascii=False`` keeps unicode readable."""
    return json.dumps(str(value), ensure_ascii=False)


def render_platform(existing: str, answers: dict, lanes: list, org_shape: str,
                    org_vault: str) -> str:
    captain = answers["captain"]
    text = existing
    text = _set_top_level_key(text, "captain_name", _yaml_str(str(captain["name"])))
    text = _set_top_level_key(text, "captain_timezone", str(captain["timezone"]))
    text = _set_top_level_key(text, "captain_telegram_chat_id", f'"{captain["telegram_chat_id"]}"')
    # Availability dial — stamped ONLY when the interview recorded an answer.
    # No answer ⇒ no key ⇒ framework.env.captain_availability() resolves the
    # honest UNKNOWN, and every consumer keeps its own conservative default.
    # Writing a placeholder number here would be the 1/3-briefing failure: a
    # value that pretends to be an answer nobody gave. A later phone ruling
    # lands in instance/config/captain-availability.yml and OUTRANKS these keys,
    # so a re-run of the generator can never demote what the captain re-dialled.
    availability = str(captain.get("availability") or "").strip().lower()
    if availability in AVAILABILITY_VERBS:
        minutes = _fenv.availability_minutes_for_mode(availability)
        text = _set_top_level_key(text, "captain_availability_minutes_per_day",
                                  str(minutes))
        text = _set_top_level_key(text, "captain_availability_mode", availability)
    # Org vault (knowledge corpus) dir — only when absent, and only when no
    # legacy product_brain_dir key is already present (the resolver honors the
    # legacy key AFTER the new one, so stamping org_vault_dir above a
    # hand-edited legacy value would silently override that curation). Value
    # is RELATIVE to the deployment root. Canonical resolver:
    # framework.env.org_vault_dir() (CABINET_ORG_VAULT_DIR env override,
    # legacy CABINET_PRODUCT_BRAIN_DIR alias, else THIS key — existence-gated
    # — else <root>/vault, else the legacy <root>/product-brain).
    if not re.search(rf"^{re.escape(LEGACY_ORG_VAULT_KEY)}:", text, re.MULTILINE):
        text = _set_top_level_key_if_absent(
            text, ORG_VAULT_KEY, f'"{org_vault}"',
            comment="# org vault (knowledge corpus) dir, relative to CABINET_ROOT — read "
                    "by framework.env.org_vault_dir() (CABINET_ORG_VAULT_DIR overrides)",
        )

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
                # Wording contract: starts with "REFUSING to overwrite" — the
                # cue hatch.sh greps to offer/perform the --adopt path.
                raise GenerationError(
                    "REFUSING to overwrite platform.yml: it already has an "
                    "unmanaged top-level 'officers:' block — a previous "
                    "deployment's config in an inherited clone? Re-run with "
                    "--adopt to archive the whole file to "
                    "instance/_pre-adopt-<stamp>/ (nothing deleted) and render "
                    "fresh. Otherwise migrate the block into the cabinet-init "
                    "managed block (remove it, then re-run) instead of letting "
                    "two blocks shadow each other."
                )
        sep = "" if text.endswith("\n") else "\n"
        text = f"{text}{sep}\n{block}\n"
    else:
        raise GenerationError(
            f"platform.yml marker block is corrupt ({begin_count} BEGIN / {end_count} END "
            f"markers) — repair the markers, then re-run."
        )
    return text


def resolve_preset(answers: dict) -> tuple[str, str]:
    """``(preset, basis)`` — THE preset resolution, for every caller.

    Before this there were TWO mappings: this generator's printed next step and
    hatch.sh's own org_shape switch, which had already drifted — hatch.sh wrote
    `portfolio` even when the answers said `cabinet.preset: developer`. One
    function, called by both, is the fix; hatch.sh now shells to
    ``--print-preset`` rather than re-deriving it.

    Precedence, and each rung is a real declaration rather than a guess:
      1. ``cabinet.preset`` — the captain named a preset. Always wins.
      2. ``mission.altitude`` in {contributor, project} → ``personal``.
         ALTITUDE MUST REACH PRESET SELECTION or it is decoration (direction
         gate, 2026-07-26). ``presets/personal`` is the kit written for exactly
         those rungs — "someone who owns a project, not a company; a developer
         inside a large organisation" — and it is the ONE shipped preset that
         stands up no C-suite. It stays OPT-IN: declaring your rung is a
         choice, not a default flip, and (1) overrides it.
      3. ``cabinet.org_shape`` — today's default (portfolio → portfolio,
         functional → work, custom → unmapped).

    CORRECTED 2026-07-27: this mapped the low rungs to ``developer`` while
    ``presets/personal/`` was a placeholder whose README forbade activating it,
    and it said so as an honest gap. The sibling personal-preset landing closed
    that gap, so "closest fit" became "wrong fit": `developer` is a flat copy of
    `work` and stands up the C-suite this altitude does not have."""
    cabinet = answers.get("cabinet") or {}
    explicit = cabinet.get("preset")
    if explicit:
        return str(explicit), "cabinet.preset"
    mission = answers.get("mission")
    altitude = ""
    if isinstance(mission, dict):
        altitude = str(mission.get("altitude") or "").strip().lower()
    if altitude in ("contributor", "project"):
        return "personal", "mission.altitude"
    org_shape = str(cabinet.get("org_shape", "portfolio"))
    if org_shape == "portfolio":
        return "portfolio", "cabinet.org_shape"
    if org_shape == "functional":
        return "work", "cabinet.org_shape"
    return "", "cabinet.org_shape"


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
  availability: part_time        # OPTIONAL time budget the org fits into:
                                 #   away | minimal | part_time | substantial |
                                 #   full_time  (0 / 10 / 30 / 120 / 480 min per
                                 #   day). OMIT the key to leave it UNKNOWN —
                                 #   a legal state; adjust any time from the
                                 #   phone with "availability 20m".

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
    boards: ["12345678"]       # board/team ids in the task system
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
# consequence-ledger evidence — see framework/docs/consequence-ledger.md.
# The sovereign POSTURE is a post-init Captain ratification (amendment
# 2026-07-05, `apply sovereign posture`): the generator renders an INERT
# instance/config/posture.yml scaffold from the two optional keys below, and
# nothing changes until the Captain locks it (germline-lock.sh lock).
# flavor also gates WHICH recall binding instance/config/sources.yml carries:
# org (the default) binds framework.sources.org:OrgSource (the cabinet's own
# memory estate); personal binds framework.sources.local:LocalNotesSource over
# a declared notes folder, read-only. Both are emitted; a hand-authored
# sources.yml is refused, never clobbered.
autonomy:
  posture: propose_first
  flavor: org                    # org | personal (personal ⇒ guardian scaffold, always)
  # target_posture: sovereign    # optional; default guardian ('mini*' org ids default sovereign)

# The ONE folder a PERSONAL deployment grants recall, read-only. OPTIONAL and
# with NO DEFAULT: omit it and recall resolves UNSET — available() False, every
# gather honestly empty — which is the correct state for a folder nobody
# granted. It used to default to `vault`, i.e. the cabinet's own shipped docs,
# so a personal box reported working recall over the framework's own
# documentation. Ignored on flavor: org (that binds the cabinet's memory
# estate instead).
# sources:
#   notes_root: ~/Documents/notes

integrations:
  telegram:
    ceo_bot: ""                          # bot USERNAME once created (TOKEN-TBD)
    bot_token_env: TELEGRAM_BOT_TOKEN_COS   # env var NAME; value in cabinet/.env
  mcp_env_names: []                      # extra env var NAMES officers need
"""


# ---------------------------------------------------------------------------
# Defaults fast lane (--defaults) — zero questions, one confirm
# ---------------------------------------------------------------------------

def default_captain_name(explicit: str | None) -> str:
    """Resolve the defaults-lane captain name: --captain-name, else $USER,
    else the honest fallback "Captain". An EXPLICIT name failing NAME_RE
    refuses loud (the captain asked for it, so a silent substitute would be
    invented data); an unusable ambient $USER falls back silently (it was
    never asked for)."""
    if explicit is not None:
        name = explicit.strip()
        if not name or "\n" in name or not NAME_RE.match(name):
            raise GenerationError(
                f"--captain-name {explicit!r} must match {NAME_RE.pattern} "
                f"(plain display name)"
            )
        return name
    ambient = (os.environ.get("USER") or "").strip()
    if ambient and NAME_RE.match(ambient):
        return ambient
    return DEFAULTS_CAPTAIN_FALLBACK


def render_default_answers(captain_name: str, altitude: str | None = None) -> str:
    """The --defaults answers file: a fixed, consent-safe, syntactically valid
    answers set (guardian + propose-first, org flavor, portfolio shape, one
    placeholder lane, env-var NAMES only). Marker-stamped: the generator owns
    it and a --defaults re-run rewrites it; edit it and re-run WITHOUT
    --defaults (or run the cabinet-init interview, which loads it and asks
    only about gaps) to refine. The name scalar rides ``_yaml_str`` so a
    YAML-reserved name ("yes", "Null", "0000") round-trips as that exact
    string instead of silently retyping to True/None/0."""
    captain_scalar = _yaml_str(captain_name)
    # The ONE thing --defaults now asks-without-asking. An absent --altitude
    # emits NO mission block at all, so the zero-question hatch stays
    # byte-identical to before; a declared rung is a real answer and reaches
    # preset selection + card derivation.
    mission_block = ""
    if altitude:
        mission_block = (
            "\n# The operator's RUNG (--altitude). It is not a title: it is what\n"
            "# the operator can DECIDE, which bounds what a proposed outcome's\n"
            "# proof can be. genesis reads it for card derivation; resolve_preset\n"
            "# reads it for preset selection. Omit it and it stays unknown.\n"
            f"mission:\n  altitude: {altitude}\n\n"
        )
    return f"""\
# {MARKER} — DEFAULTS fast lane (generate-instance.py --defaults).
# A consent-safe answers set written with ZERO questions asked: guardian
# posture, propose-first, org flavor, portfolio shape, one placeholder lane.
# Placeholder values are marked below. To refine: edit this file and re-run
# WITHOUT --defaults (a --defaults re-run REWRITES this file — it carries the
# generated-by marker, so the generator owns it), or run the cabinet-init
# interview skill, which loads it and asks only about gaps/changes.
version: 1

captain:
  name: {captain_scalar}
  timezone: UTC                  # placeholder — set your IANA zone (e.g. Europe/Madrid)
  telegram_chat_id: "{DEFAULTS_CHAT_ID_PLACEHOLDER}"       # placeholder address (not a secret) — set your numeric chat id
  # availability: DELIBERATELY ABSENT. Nobody was asked how much of their day
  # the cabinet may use, so there is no answer to record — availability stays
  # UNKNOWN, which is a legal state every consumer handles conservatively.
  # A placeholder number here would be a value pretending to be an answer (the
  # named failure of the 1/3-scored briefing). Set it whenever you like, from
  # your phone: "availability 20m" / "availability part_time".

{mission_block}cabinet:
  id: main                       # single-instance default
  mode: single
  org_shape: portfolio           # one Chair + on-demand lane CEOs
  officer_model: {DEFAULT_MODEL}

lanes:
  - name: {DEFAULTS_LANE_NAME}             # placeholder lane — rename to your first real product
    slug: {DEFAULTS_LANE_SLUG}
    repos: []
    task_system: none
    boards: []

# Consent-safe autonomy: guardian, propose-first everywhere; the hard
# ceilings (secrets / spend / external comms / production deploys) never
# resolve unconditional auto in any posture. flavor: org binds OrgSource
# recall and declares NO personal estate. target_posture is EXPLICITLY
# guardian so nothing in the defaults lane can scaffold sovereign.
autonomy:
  posture: propose_first
  flavor: org
  target_posture: guardian

integrations:
  telegram:
    ceo_bot: ""                        # bot USERNAME once created (TOKEN-TBD)
    bot_token_env: TELEGRAM_COS_TOKEN  # env var NAME; the token VALUE goes in cabinet/.env
  mcp_env_names: []
"""


def prepare_default_answers(root: Path, answers_path: Path, captain_name: str | None,
                            adopt: bool = False, dry_run: bool = False,
                            altitude: str | None = None) -> tuple[Path, Path | None]:
    """--defaults: materialize the defaults answers set at ``answers_path``
    and return ``(path_for_generate, tmp_path_or_None)``. Zero prompts.

    Rules (all existing doctrine, applied to the one new write):
      * The answers WRITE stays inside the instance/ jail — a --answers path
        resolving outside <root>/instance/ is refused.
      * The target filename must end with ``.answers.yml`` — the one
        namespace no generated instance file can occupy (the outputs are
        fixed names like posture.yml/platform.yml/active-project.txt, and
        SLUG_RE forbids dots in context/project slugs) — so --defaults can
        never rewrite a generator output even when it carries the marker.
        Unconditional shape rule: neither --force nor --adopt widens it.
      * An existing answers file WITHOUT the generated-by marker is an
        interview-written (or a previous deployment's) record: REFUSE with
        the fix — naming the previous captain when platform.yml records a
        different one (the inherited-clone signal) — unless --adopt, which
        archives it to instance/_pre-adopt-<stamp>/<relpath> (nothing
        deleted) first. --force deliberately does NOT override this one
        refusal: the file is the captain's interview record, and
        archive-over-clobber is the only honest path (everywhere else
        --force keeps its usual marker-override meaning).
      * With the marker, the file is generator-owned and is rewritten
        (idempotent: unchanged inputs => byte-identical content).
      * --dry-run writes NOTHING into the repo: the defaults land in a
        tempfile (returned as tmp_path for the caller to unlink).
    """
    root = root.resolve()
    instance_root = (root / "instance").resolve()
    resolved = answers_path.resolve()
    if resolved != instance_root and instance_root not in resolved.parents:
        raise GenerationError(
            f"PATH REFUSED: --defaults writes the answers file, and the "
            f"generator writes only under instance/ — {answers_path} resolves "
            f"outside {instance_root}. Use the default answers path or one "
            f"under instance/."
        )
    if resolved.is_dir():
        raise GenerationError(f"--answers {answers_path} is a directory, not an answers file")
    if not resolved.name.endswith(".answers.yml"):
        # Namespace fence, not a marker check — deliberately NOT worded
        # "REFUSING to overwrite" (hatch.sh greps that cue to offer --adopt,
        # the wrong fix here). Without it, a marker-stamped generator output
        # (e.g. the posture.yml RULING scaffold — never touched once written,
        # Captain ruling) would read as "generator-owned answers file" and be
        # rewritten, permanently: generate() then sees it existing and skips
        # re-rendering. --force does not apply — shape rule, not overwrite.
        raise GenerationError(
            f"ANSWERS PATH REFUSED: --defaults writes the answers file and "
            f"requires a '*.answers.yml' filename — {answers_path} could "
            f"collide with a generated instance file (posture.yml, "
            f"platform.yml, sources.yml, roster.yml, active-project.txt, "
            f"contexts/, projects/). Use the default "
            f"instance/config/cabinet-init.answers.yml or another "
            f"*.answers.yml path under instance/."
        )
    rel = resolved.relative_to(root)

    name = default_captain_name(captain_name)
    content = render_default_answers(name, altitude)

    needs_archive = resolved.exists() and MARKER not in resolved.read_text(encoding="utf-8")
    if needs_archive and not adopt:
        msg = (
            f"REFUSING to overwrite {resolved}: existing answers file "
            f"lacks the '{MARKER}' marker — an interview-written (or a "
            f"previous deployment's) record. Run WITHOUT --defaults to "
            f"generate from it, or re-run with --defaults --adopt to "
            f"archive it to instance/_pre-adopt-<stamp>/ (nothing "
            f"deleted) and start from defaults."
        )
        prior = _existing_captain_name(root)
        if prior and prior != name:
            msg += (
                f"\nThis instance/ looks inherited from a previous "
                f"deployment (platform.yml captain_name: {prior!r}; "
                f"--defaults would set captain {name!r})."
            )
        raise GenerationError(msg)

    # Banner only after every refusal check — a refused run should show the
    # refusal, not a happy-path narration above it.
    print(f"defaults fast lane: captain {name!r} · timezone UTC (placeholder) · "
          f"cabinet 'main' (single, portfolio) · posture guardian/propose-first · "
          f"flavor org · lane '{DEFAULTS_LANE_SLUG}' (placeholder) — zero questions; "
          f"edit {rel} and re-run without --defaults to refine.")

    if needs_archive:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = instance_root / f"_pre-adopt-{stamp}" / resolved.relative_to(instance_root)
        if dry_run:
            print(f"[dry-run] would adopt-archive {rel} -> "
                  f"{dest.relative_to(root)} (answers file without marker)")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(resolved), str(dest))
            print(f"adopt-archived {rel} -> {dest.relative_to(root)} "
                  f"(answers file without marker)")

    if dry_run:
        fd, tmp = tempfile.mkstemp(prefix=".cabinet-init-defaults.", suffix=".yml")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"[dry-run] would write {rel} (defaults answers)")
        return Path(tmp), Path(tmp)

    _atomic_write(resolved, content)
    print(f"wrote {rel} (defaults answers)")
    return resolved, None


# ---------------------------------------------------------------------------
# Main generation pass
# ---------------------------------------------------------------------------

def generate(root: Path, answers_path: Path, dry_run: bool = False, force: bool = False,
             adopt: bool = False) -> list:
    """Run the full generation pass. Returns the list of written paths."""
    root = root.resolve()
    answers = load_answers(answers_path, root)
    cabinet = answers.get("cabinet") or {}
    org_shape = str(cabinet.get("org_shape", "portfolio"))
    model = str(cabinet.get("officer_model", DEFAULT_MODEL))
    lanes = answers["lanes"]
    integrations = answers.get("integrations") or {}

    # Inherited-instance signal: an existing platform.yml carrying a DIFFERENT
    # captain than the answers means this instance/ likely shipped from a
    # previous deployment — when a marker refusal fires, teach --adopt (the
    # built fix) instead of leaving the new captain at --force/hand-edits.
    prior_captain = _existing_captain_name(root)
    new_captain = str((answers.get("captain") or {}).get("name", ""))
    inherited_hint = ""
    if not adopt and prior_captain and prior_captain != new_captain:
        inherited_hint = (
            f"This instance/ looks inherited from a previous deployment "
            f"(platform.yml captain_name: {prior_captain!r}, answers say "
            f"{new_captain!r}) — re-run with --adopt to archive its "
            f"conflicting files under instance/_pre-adopt-<stamp>/ (nothing "
            f"deleted) and generate fresh."
        )

    # ---- adoption plumbing (--adopt; see module docstring) ----
    # Conflicting files a previous deployment left behind are ARCHIVED (never
    # deleted) under instance/_pre-adopt-<UTC-stamp>/<relpath>. Path-contained:
    # both source and destination resolve under <root>/instance/.
    instance_root = (root / "instance").resolve()
    adopt_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    adopt_root = _instance_path(root, f"_pre-adopt-{adopt_stamp}")
    adopted: set[Path] = set()

    def _adopt_aside(path: Path, reason: str) -> None:
        rel = path.relative_to(instance_root)
        dest = adopt_root / rel
        if dry_run:
            print(f"[dry-run] would adopt-archive instance/{rel} -> "
                  f"{adopt_root.relative_to(root)}/{rel} ({reason})")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dest))
            print(f"adopt-archived instance/{rel} -> "
                  f"{adopt_root.relative_to(root)}/{rel} ({reason})")
        adopted.add(path)

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
            render_roster(lanes, model, root), "yaml",
        ))

    platform_path = _instance_path(root, "config", "platform.yml")
    existing_platform = platform_path.read_text(encoding="utf-8") if platform_path.exists() else ""
    # --adopt: a platform.yml carrying an unmanaged top-level officers: block is
    # a previous deployment's config — archive the whole file and render fresh
    # (captain keys + managed block) instead of asking the new captain to
    # hand-edit another captain's platform.yml. (Corrupt marker blocks still
    # fail loud in render_platform — adoption never papers over corruption.)
    if (adopt and existing_platform and org_shape == "portfolio"
            and PLATFORM_BEGIN not in existing_platform
            and any(re.match(r"^officers:\s*(#.*)?$", line)
                    for line in existing_platform.splitlines())):
        _adopt_aside(platform_path, "unmanaged top-level officers: block")
        existing_platform = ""
    outputs.append((
        platform_path,
        render_platform(existing_platform, answers, lanes, org_shape,
                        org_vault=ORG_VAULT_DEFAULT), "yaml",
    ))

    # Personal-sensing seam binding (module-docstring emission rule). BOTH
    # flavors now get a live binding: org boxes bind the cabinet's own memory
    # estate (OrgSource), personal boxes bind a folder of notes
    # (LocalNotesSource). Before 2026-07-27 the personal branch emitted
    # nothing and that deployment fail-closed to NullPersonalSource — zero
    # recall — which is why the personal preset shipped inert. The standard
    # overwrite guard below still protects a hand-authored sources.yml (no
    # marker ⇒ refuse without --force), so a captain's own richer adapter is
    # never clobbered by this emission.
    flavor = str((answers.get("autonomy") or {}).get("flavor", "org"))
    sources_adapter = (ORG_SOURCE_ADAPTER if flavor != "personal"
                       else LOCAL_SOURCE_ADAPTER)
    # THE ANSWERS DECLARE THE SCOPE (2026-07-28). Undeclared stays undeclared:
    # render_sources_personal(None) emits the key commented out, so recall
    # reports unavailable instead of binding the cabinet's own docs.
    notes_root = declared_notes_root(answers)
    sources_body = (render_sources() if flavor != "personal"
                    else render_sources_personal(notes_root))
    outputs.append((
        _instance_path(root, "config", "sources.yml"),
        sources_body, "yaml",
    ))

    # Posture scaffold (sovereign amendment 2026-07-05): rendered ONLY when
    # absent — an existing posture.yml is a Captain RULING (possibly ratified
    # + schg-locked) and is never regenerated, not even with --force.
    posture_path = _instance_path(root, "config", "posture.yml")
    posture_skipped = posture_path.exists()
    if not posture_skipped:
        outputs.append((posture_path, render_posture(answers), "yaml"))

    # Active project (only when absent — an existing deployment's active
    # project is operator state, never regenerated). bootstrap-roles.sh reads
    # it for the product slug (exits 1 without it on a fresh hatch) and
    # start-officer-mac.sh reads it for the CABINET_LANE export; the first
    # declared lane is the natural initial value.
    active_project_path = _instance_path(root, "config", "active-project.txt")
    active_project_skipped = active_project_path.exists()
    # NO LANES, NO INVENTED SLUG. A lane-less deployment has no product to be
    # active in, and writing a placeholder here is the exact failure the
    # ordering inversion exists to remove: a value pretending to be an answer.
    # bootstrap-roles.sh then says what it always says — pass --product-slug or
    # set this file — and the next-steps block below names the ratification
    # path that fills it honestly.
    active_project_written = not active_project_skipped and bool(lanes)
    if active_project_written:
        outputs.append((active_project_path, f"{lanes[0]['slug']}\n", "text"))

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
        if path == platform_path or path in adopted:
            continue
        if (adopt and path.exists()
                and MARKER not in path.read_text(encoding="utf-8")):
            _adopt_aside(path, "no generated-by marker")
            continue
        _check_overwrite(path, force, inherited_hint)

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
            elif kind == "agent-md":
                yaml.safe_load(on_disk.split("---", 2)[1])
            # kind == "text" (active-project.txt): plain slug, nothing to parse
        print("validation: all generated YAML parses")

    # ---- next steps ----
    tg = integrations.get("telegram") or {}
    token_env = str(tg.get("bot_token_env") or "TELEGRAM_COS_TOKEN")
    # An explicit (validated) cabinet.preset answer wins; else the org_shape
    # default. The developer preset stays OPT-IN — surfaced as a choice for
    # the functional shape below, never substituted as the default.
    explicit_preset = cabinet.get("preset")
    preset, preset_basis = resolve_preset(answers)
    preset = preset or "<your-preset>"
    print("\nNext steps (in order):")
    print(f"  1. echo {preset} > instance/config/active-preset")
    if preset_basis == "mission.altitude":
        print("     (selected from mission.altitude — your declared rung. The")
        print("      personal preset is the one shipped kit with NO C-suite:")
        print("      Navigator, Librarian, Reviewer for one operator who owns a")
        print("      project, not a company. Override with cabinet.preset.)")
    if org_shape == "functional" and preset_basis == "cabinet.org_shape":
        print("     (work is the default. Shipping a software/web/app product? The")
        print("      OPTIONAL developer preset is the software product-kind kit —")
        print("      presets/developer/README.md; activate with")
        print("      echo developer > instance/config/active-preset)")
    if org_shape == "portfolio":
        _, pending_lanes = split_lane_hires(root, lanes)
        if pending_lanes:
            pending_slugs = [str(lane["slug"]) for lane in pending_lanes]
            print("  2. OPTIONAL — nothing else here waits on it. NOT rostered "
                  "(not hired):")
            print(f"     {', '.join(s + '-ceo' for s in pending_slugs)}")
            print("     Their lane files are generated and inert. They stay "
                  "unhired until")
            print(f"     BOTH germline files authorize them — a roster hire "
                  f"without those")
            print("     rows is a silent capability/MCP-scope lockout, so the "
                  "generator")
            print("     will not create it. To hire: PROPOSE these exact rows to "
                  "the")
            print("     Captain (germline = Captain applies), then re-run this "
                  "generator.")
            print("     Paste each block VERBATIM into the file its header "
                  "names — the")
            print("     indentation is load-bearing (the capability hooks match "
                  "whole")
            print("     lines; the scope keys must be siblings under `agents:`). "
                  "The")
            print("     headers are comments in both files, so pasting them is "
                  "harmless.")
            print(germline_rows_for(pending_slugs))
        else:
            print("  2. Germline authorization: every lane CEO already has its "
                  "rows in")
            print(f"     {OFFICER_CONF_REL} + {MCP_SCOPE_REL} — all rostered, "
                  f"nothing to propose.")
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
        print("  3. bash cabinet/scripts/load-preset.sh, then deploy per cabinet/docs/mac-mini-setup.md")
    print("  Nothing above activates lanes: contexts ship active: false and")
    print("  projects ship activation.status: pending until the Captain flips them.")
    if active_project_skipped:
        print("  Active project: existing instance/config/active-project.txt left")
        print("  untouched (operator state — never regenerated).")
    elif active_project_written:
        print(f"  Active project: wrote instance/config/active-project.txt = "
              f"{lanes[0]['slug']} (bootstrap-roles.sh reads it for the product")
        print("  slug; edit it any time to switch the active lane).")
    else:
        print("  Active project: NOT written — this deployment declares no lanes,")
        print("  and a placeholder slug would be a value pretending to be an")
        print(f"  answer. Ratify a lane from {_estate.LANES_PROPOSED_REL} into")
        print("  the answers file and re-run, or set the file yourself.")
    if adopted:
        print(f"  Adopted: {len(adopted)} previous-deployment file(s) archived under")
        print(f"  {adopt_root.relative_to(root)}/ — review, then delete when confident.")
    if posture_skipped:
        print("  Posture: existing instance/config/posture.yml is a Captain ruling —")
        print("  left untouched (never regenerated, not even with --force).")
    else:
        p, f = resolve_target_posture(answers)
        print(f"  Posture: rendered instance/config/posture.yml scaffold (posture: {p},")
        print(f"  flavor: {f}) — INERT until the Captain ratifies by locking:")
        print("  edit basis/ruled_at, commit, then sudo bash cabinet/scripts/germline-lock.sh lock")
        print("  (unlocked/absent/mismatched always resolves guardian — today's rules).")
    print(f"  Recall: instance/config/sources.yml binds {sources_adapter}")
    print(f"  (autonomy.flavor: {flavor}). No dispatch: binding — writes fail-close to")
    print("  draft-capture-only.")
    if sources_adapter == LOCAL_SOURCE_ADAPTER:
        if notes_root:
            print(f"  Recall reads {notes_root} (declared as "
                  f"{SOURCES_KEY}.{NOTES_ROOT_KEY}) — read-only, no write side")
            print("  at all. Re-run this generator after moving it.")
        else:
            print("  Recall is UNSET: no folder was granted, so it reports")
            print("  unavailable and every gather is honestly empty. Declare")
            print(f"  {SOURCES_KEY}.{NOTES_ROOT_KEY} in the answers file and re-run "
                  f"(or export")
            print("  CABINET_LOCAL_SOURCE_ROOT). There is no default on purpose —")
            print("  the old one bound this repo's own docs and looked like it worked.")
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
    parser.add_argument("--adopt", action="store_true",
                        help="archive (never delete) a previous deployment's conflicting "
                             "instance files to instance/_pre-adopt-<stamp>/ and generate "
                             "fresh — the fresh-captain path for a clone that ships "
                             "another deployment's instance/")
    parser.add_argument("--defaults", action="store_true",
                        help="zero-question fast lane: write a consent-safe defaults "
                             "answers file (guardian/propose-first, org flavor, portfolio "
                             "shape, one placeholder lane; captain from --captain-name, "
                             "else $USER) and generate from it — no prompts; the full "
                             "interview (cabinet-init skill) stays the default lane")
    parser.add_argument("--captain-name", default=None, metavar="NAME",
                        help="captain display name for --defaults "
                             "(default: $USER, else 'Captain')")
    parser.add_argument("--altitude", default=None, metavar="RUNG",
                        help="operator rung for --defaults: "
                             + " | ".join(sorted(ALTITUDES))
                             + " (omit to leave it unknown)")
    parser.add_argument("--example", action="store_true",
                        help="print a starter answers file to stdout and exit")
    parser.add_argument("--print-preset", action="store_true", dest="print_preset",
                        help="print the resolved preset slug for the answers file "
                             "and exit (the ONE resolution; hatch.sh calls this "
                             "instead of re-deriving it). Exit 3 when no preset "
                             "maps (custom shape).")
    args = parser.parse_args(argv)

    if args.example:
        sys.stdout.write(EXAMPLE_ANSWERS)
        return 0

    if args.captain_name is not None and not args.defaults:
        print("[generate-instance] ERROR: --captain-name requires --defaults",
              file=sys.stderr)
        return 2
    if args.altitude is not None:
        if not args.defaults:
            print("[generate-instance] ERROR: --altitude requires --defaults "
                  "(otherwise set mission.altitude in the answers file)",
                  file=sys.stderr)
            return 2
        if args.altitude not in ALTITUDES:
            print(f"[generate-instance] ERROR: --altitude {args.altitude!r} must "
                  f"be one of {sorted(ALTITUDES)}", file=sys.stderr)
            return 2

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    answers_path = Path(args.answers).resolve() if args.answers else root / "instance/config/cabinet-init.answers.yml"

    if args.print_preset:
        # Read-only: resolve and print, write nothing. Full validation still
        # runs, so a broken answers file fails here exactly as it would at
        # generation — the hatch must not select a preset from answers the
        # generator would then refuse.
        try:
            preset, basis = resolve_preset(load_answers(answers_path, root))
        except GenerationError as e:
            print(f"[generate-instance] ERROR: {e}", file=sys.stderr)
            return 2
        if not preset:
            print("[generate-instance] ERROR: no preset maps to this answers "
                  "file (custom org_shape and no cabinet.preset) — set "
                  "instance/config/active-preset yourself", file=sys.stderr)
            return 3
        print(preset)
        return 0

    tmp_answers: Path | None = None
    try:
        if args.defaults:
            answers_path, tmp_answers = prepare_default_answers(
                root, answers_path, args.captain_name,
                adopt=args.adopt, dry_run=args.dry_run,
                altitude=args.altitude)
        generate(root, answers_path, dry_run=args.dry_run, force=args.force,
                 adopt=args.adopt)
    except GenerationError as e:
        print(f"[generate-instance] ERROR: {e}", file=sys.stderr)
        return 2
    finally:
        if tmp_answers is not None and tmp_answers.exists():
            tmp_answers.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
