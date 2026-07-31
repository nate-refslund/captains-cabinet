"""CABINET_ENV — the dev | runtime safety switch (fail-safe by default).

The default is **dev**, so any unconfigured session — a developer, a test, this
build session — is SANDBOXED:
  * ``allow_sends()`` is False, so the live dispatch adapter NEVER sends (no
    queue_draft) even on an 'approve'. Acting for real is opt-in, not opt-out.
  * ``ledger_dir()`` points at a separate ``-dev`` directory, so a dev run can
    never pollute the production proof ledger that drives the ladder.

The runtime (``start-officer``) must set ``CABINET_ENV=runtime`` explicitly to
enable production-ledger writes + gated sends. This module is the single switch
the live code + launch scripts consult; ``consequence.py`` is untouched (it
already honours ``CABINET_EVENT_LOG_DIR``, which the runtime launch sets from
``ledger_dir()``).
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_DEV = "dev"
_RUNTIME = "runtime"


def cabinet_env() -> str:
    """The active environment: 'runtime' only when explicitly set; else 'dev'."""
    val = (os.environ.get("CABINET_ENV") or "").strip().lower()
    return _RUNTIME if val == _RUNTIME else _DEV


def is_runtime() -> bool:
    return cabinet_env() == _RUNTIME


def allow_sends() -> bool:
    """True ONLY in the runtime. The live dispatch adapter must gate every
    outbound (queue_draft) on this — so dev/test/build sessions cannot send,
    regardless of how an 'approve' was routed."""
    return is_runtime()


def ledger_dir() -> Path:
    """The consequence-ledger directory for this environment.

    An explicit ``CABINET_EVENT_LOG_DIR`` always wins (the runtime launch sets it).
    Otherwise: the durable per-user ledger for runtime, and a distinct ``-dev``
    sibling for dev — so dev proof can never mix into the production ledger.
    """
    explicit = os.environ.get("CABINET_EVENT_LOG_DIR")
    if explicit:
        return Path(explicit).expanduser()
    base = Path.home() / ".cabinet" / "ledger"
    return base if is_runtime() else base.with_name("ledger-dev")


def _cabinet_root() -> Path:
    """The deployment root — ``CABINET_ROOT`` env, else this file's repo root
    (``framework/env.py`` → parents[1]). No hardcoded absolute path (the old
    ``_captain_tz`` reader baked in an absolute home path — a launcher leak this
    resolver deliberately avoids)."""
    return Path(os.environ.get("CABINET_ROOT") or str(Path(__file__).resolve().parents[1]))


# Cache: captain_name is read once per process (config does not change under a
# running officer; a restart re-reads). None ⇒ not yet resolved.
_captain_name_cache: "str | None" = None


def captain_name(default: str = "Captain") -> str:
    """The Captain's display name for this deployment — the FOUNDATION resolver
    that lets framework code address the launcher WITHOUT hardcoding a name.

    Reads ``captain_name`` from ``instance/config/platform.yml`` (portfolio /
    live deployments), else ``instance/config/product.yml`` (single-product
    ``work`` deployments), per CLAUDE.md → "Talking to the Captain". Any
    absence / parse failure falls back to ``default`` ("Captain") — a generic
    deployment stays generic, never crashes, and never leaks another
    launcher's name. Framework code that greets/represents the Captain calls
    this instead of a string literal."""
    global _captain_name_cache
    if _captain_name_cache is not None:
        return _captain_name_cache
    name = default
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("captain_name")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("captain_name")   # product.yml nests it
            if isinstance(val, str) and val.strip():
                name = val.strip()
                break
    except Exception:
        name = default
    _captain_name_cache = name
    return name


# Cache: captain_role is read once per process (same lifecycle as captain_name;
# config is stable under a running officer, a restart re-reads). None ⇒ unresolved.
_captain_role_cache: "str | None" = None


def captain_role(default: str = "the Captain") -> str:
    """The Captain's role/title for this deployment — the sibling of
    ``captain_name()`` that lets framework code name the launcher's ROLE (e.g.
    in a decision-cell LLM prompt) WITHOUT hardcoding it (this deployment's is
    "Head-of-Tech").

    Reads ``captain_role`` from ``instance/config/platform.yml`` (portfolio /
    live deployments), else ``instance/config/product.yml`` (single-product
    ``work`` deployments), exactly like ``captain_name()``. Any absence / parse
    failure falls back to ``default`` ("the Captain") — a generic deployment
    stays generic, never crashes, and never leaks another launcher's role.
    Framework code that names the Captain's role in a runtime string calls this
    instead of a string literal."""
    global _captain_role_cache
    if _captain_role_cache is not None:
        return _captain_role_cache
    role = default
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("captain_role")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("captain_role")   # product.yml nests it
            if isinstance(val, str) and val.strip():
                role = val.strip()
                break
    except Exception:
        role = default
    _captain_role_cache = role
    return role


# Cache: captain_slug is read once per process (same lifecycle as captain_name).
# None ⇒ unresolved — the role token "captain" is a VALID resolved default (not a
# personal name), so the sentinel is None, never "".
_captain_slug_cache: "str | None" = None


def captain_slug(default: str = "captain") -> str:
    """The OWNER slug that marks a row (an ``officer_tasks`` row) as the
    Captain's — the resolver the reminder arm uses to route a Captain-owned
    due row to the needs-ledger card surface instead of an officer's Redis
    stream, WITHOUT hardcoding a personal name (product/captain-agnostic law).

    The value is a ROLE token, not a display name: the generic default is the
    literal ``captain`` — the SAME slug the /tasks ETL already stamps on
    founder rows (``cabinet/scripts/lib/etl-common.py`` — "caller checks slug
    == 'captain'") and the events schema uses for the Captain actor
    (``framework/events/schema.sql``). It is deliberately distinct from
    ``captain_name()`` (which is the DISPLAY name shown to the Captain): a slug
    is an identity key that lives in a DB column and must stay stable + generic.

    Resolution order: the env override ``CABINET_CAPTAIN_SLUG`` (an explicit
    per-process override, mirroring ``tasks_board``'s ``CABINET_TASKS_BOARD``) →
    ``captain_slug`` in ``instance/config/platform.yml`` (else ``product.yml`` /
    nested ``product.captain_slug``) → the generic ``default`` (``"captain"``).
    Any absence / parse failure falls back to ``default`` — a generic
    deployment resolves ``captain``, never crashes, never leaks a launcher's
    name. NB: the FIRST call's resolution — fallback included — is cached for
    the process, so every caller must pass a uniform ``default``."""
    global _captain_slug_cache
    if _captain_slug_cache is not None:
        return _captain_slug_cache
    env_override = (os.environ.get("CABINET_CAPTAIN_SLUG") or "").strip()
    if env_override:
        _captain_slug_cache = env_override
        return env_override
    slug = str(default)
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("captain_slug")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("captain_slug")   # product.yml nests it
            if isinstance(val, str) and val.strip():
                slug = val.strip()
                break
    except Exception:
        slug = str(default)
    _captain_slug_cache = slug
    return slug


# Cache: org_domains is read once per process (same lifecycle as captain_name;
# config is stable under a running officer, a restart re-reads). None ⇒
# unresolved — the EMPTY tuple is a VALID resolved value (a generic deployment
# with no org), so the sentinel is None, never ().
_org_domains_cache: "tuple[str, ...] | None" = None


def org_domains(default: "tuple[str, ...]" = ()) -> "tuple[str, ...]":
    """The org's internal email domains for this deployment — the resolver that
    lifts the action-classifier's internal-vs-external recipient list OUT of the
    universal-base ``framework`` code into instance config, so framework carries
    no launcher's domains.

    Reads the ``org_domains`` list from ``instance/config/platform.yml``
    (portfolio / live deployments), else ``instance/config/product.yml``
    (single-product ``work`` deployments; also accepts a nested
    ``product.org_domains``). Each entry is stripped + lowercased (the
    is_internal predicate compares against an already-lowercased recipient
    domain) and order is preserved. Any absence / parse failure / empty list
    falls back to ``default`` — the EMPTY tuple — so a generic deployment treats
    EVERY recipient as external (the conservative comms ceiling / always-gated),
    never crashes, and never leaks another launcher's org. The classifier's
    is_internal predicate is unchanged; only the domain SOURCE moved here."""
    global _org_domains_cache
    if _org_domains_cache is not None:
        return _org_domains_cache
    domains = tuple(default)
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("org_domains")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("org_domains")   # product.yml nests it
            if isinstance(val, (list, tuple)):
                cleaned = tuple(
                    d.strip().lower() for d in val
                    if isinstance(d, str) and d.strip())
                if cleaned:
                    domains = cleaned
                    break
    except Exception:
        domains = tuple(default)
    _org_domains_cache = domains
    return domains


# The Captain's recipient EXCLUSION ruling — the carve-back on org_domains().
# org_domains IS the allowlist ("which domains count as internal"); it has no
# granularity below a domain and no way to say "not this one", so a listed
# domain admits every address at it and (under `inherit`) every subdomain of
# it, forever. This resolver is the one place an exclusion can be stated.
# DENY_ALL_RECIPIENTS is the corruption sentinel: an exclusion file that EXISTS
# but cannot be read is NEVER silently ignored — every recipient classifies
# external until it is repaired (the act-first-surfaces contract, mirrored from
# framework/frontdoor/action_exec.py's _DENY_ALL_SENTINEL).
DENY_ALL_RECIPIENTS = "*"
_RECIPIENT_EXCLUSIONS_REL = "instance/config/recipient-exclusions.yml"
_RECIPIENT_EXCLUSIONS_MAX_BYTES = 1 << 20
# Characters that make a deny value UNMATCHABLE against the tokens the
# classifier compares (it splits a recipient field on [\s,;] and keeps every
# other character glued), so a row carrying one would silently exclude nothing.
_INERT_DENY_RE = re.compile(r"[\s,;<>]")
_recipient_policy_cache: "dict | None" = None


def _parse_recipient_exclusions(path: Path) -> dict:
    """Parse the ruled exclusion file, RAISING on any content damage.

    Damage is anything that could silently SHRINK the Captain's exclusion set:
    a non-mapping document, a dropped ``denylist`` key, a ``denylist`` that is
    not a list, a row that is not a mapping, a row carrying neither or both of
    ``address``/``domain``, an empty value, or a value whose shape contradicts
    its key (an ``address`` with no ``@``, a ``domain`` with one). An
    explicitly empty ``denylist: []`` is the Captain's ruled posture, not
    damage. ``why:`` is required by the file's documented convention and is
    deliberately NOT enforced here — a forgotten ``why`` must not turn an
    urgent exclusion into a deny-all outage (act-first-surfaces treats its own
    ``why:`` the same way).

    A MISSING ``subdomain_matching`` key is likewise not damage: it defaults to
    ``strict``, the TIGHTER reading, so its absence can only narrow. That is
    the asymmetry — a dropped key fails closed only where dropping it would
    loosen. An unrecognized VALUE is damage and raises."""
    import yaml  # local: keep env.py import-light for the safety switches

    # NB: _Strict derives from SafeLoader, so `yaml.load(..., Loader=_Strict)`
    # is safe_load plus two REFUSALS — it constructs no arbitrary types and a
    # `!!python/` tag still raises (pinned by a test arm). It is not
    # yaml.load's default unsafe loader.
    class _Strict(yaml.SafeLoader):
        """SafeLoader that refuses a repeated key and refuses aliases.

        yaml.safe_load takes LAST-WINS on a duplicate mapping key with no
        error, so appending a second `denylist: []` below a populated one
        empties the Captain's exclusion set while every original row still
        reads intact above it — the silent shrink this parser exists to
        refuse, and the shape a careless append produces. Aliases are refused
        for a different reason: this file is meant to be audited by eye, and
        an exclusion list whose real content is assembled from anchors
        elsewhere in the document cannot be."""

        def compose_node(self, parent, index):
            if self.check_event(yaml.events.AliasEvent):
                raise ValueError("YAML aliases are not accepted here")
            return super().compose_node(parent, index)

        def construct_mapping(self, node, deep=False):
            seen = set()
            for key_node, _ in node.value:
                key = self.construct_object(key_node, deep=deep)
                if key in seen:
                    raise ValueError("duplicate key %r" % (key,))
                seen.add(key)
            return super().construct_mapping(node, deep=deep)

    raw = path.read_bytes()
    if len(raw) > _RECIPIENT_EXCLUSIONS_MAX_BYTES:
        # parsed at import of a germline module: an oversized file would stall
        # every classification at startup. Refusing it fails CLOSED.
        raise ValueError("recipient-exclusions.yml is implausibly large")
    data = yaml.load(raw.decode("utf-8"), Loader=_Strict)
    if not isinstance(data, dict):
        raise ValueError("recipient-exclusions.yml is not a mapping")
    if "denylist" not in data:
        raise ValueError("recipient-exclusions.yml missing 'denylist' key")
    rows = data["denylist"]
    if rows is not None and not isinstance(rows, list):
        raise ValueError("'denylist' is not a list")
    deny: list = []
    for row in (rows or []):
        if not isinstance(row, dict):
            raise ValueError("denylist row is not a mapping: %r" % (row,))
        keys = [k for k in ("address", "domain") if k in row]
        if len(keys) != 1:
            raise ValueError("denylist row needs exactly one of address/domain")
        val = row[keys[0]]
        if not isinstance(val, str) or not val.strip():
            raise ValueError("denylist row has an empty %s" % keys[0])
        val = val.strip().lower()
        if (keys[0] == "address") != ("@" in val):
            raise ValueError("denylist %s has the wrong shape: %r" % (keys[0], val))
        # A row that can never MATCH is worse than no row: the Captain reads
        # his exclusion as live and it excludes nothing. The classifier
        # compares against tokens split on [\s,;], so any value carrying a
        # separator is inert; so is the display-name form pasted out of a mail
        # client (`<display> <list@org>`); so is a domain with a leading
        # dot, which matches neither `dom == pat` nor `dom.endswith("." + pat)`.
        # Refuse all three LOUDLY rather than silently accepting a dud.
        if _INERT_DENY_RE.search(val) or val.startswith(".") or val.endswith("."):
            raise ValueError("denylist %s can never match: %r" % (keys[0], val))
        deny.append(val)
    mode = data.get("subdomain_matching", "strict")
    if not isinstance(mode, str):
        raise ValueError("subdomain_matching must be a string, got %r" % (mode,))
    mode = mode.strip().lower()   # a caps typo must not take the org to deny-all
    if mode not in ("strict", "inherit"):
        raise ValueError("unknown subdomain_matching %r" % (mode,))
    return {"deny": tuple(deny), "subdomains": mode}


def recipient_policy() -> dict:
    """The recipient exclusion policy: ``{"deny": tuple, "subdomains": str}``.

    ``deny`` entries are lowercased; one containing ``@`` is a full ADDRESS
    (exact match), one without is a DOMAIN (matching it and every subdomain of
    it — a broader deny is the safe direction). ``subdomains`` is ``strict``
    (a recipient domain is internal only if it EXACTLY equals a listed
    org_domain) or ``inherit`` (exact or any subdomain — the pre-2026-07-27
    framework behaviour, now opt-in).

    Reads ``instance/config/recipient-exclusions.yml`` under the deployment
    root. File ABSENT ⇒ empty denylist. File PRESENT but unparseable or damaged
    ⇒ ``{"deny": (DENY_ALL_RECIPIENTS,)}`` — fail CLOSED, every recipient
    external until repaired. Never raises; cached like org_domains()."""
    global _recipient_policy_cache
    if _recipient_policy_cache is not None:
        return _recipient_policy_cache
    policy = {"deny": (), "subdomains": "strict"}
    try:
        path = _cabinet_root() / _RECIPIENT_EXCLUSIONS_REL
        # lexists, not exists: a DANGLING symlink at this path is a file that
        # is PRESENT and unreadable — damaged — not absent. exists() follows
        # the link and would report absent, silently dropping the exclusions.
        if os.path.lexists(path):
            policy = _parse_recipient_exclusions(path)
    except Exception:
        policy = {"deny": (DENY_ALL_RECIPIENTS,), "subdomains": "strict"}
    _recipient_policy_cache = policy
    return policy


def signal_tells(project: str = "", default: "dict | None" = None, *,
                 env_json: "str | None" = None) -> dict:
    """Per-lane TELLS for the verified-noise discriminator (``framework.frontdoor.
    signal_discriminator``) — the resolver that keeps the discriminator LOGIC
    lane-agnostic by receiving the launcher-specific tells (prod hosts, staging/bot
    patterns, smoke paths) as a RESOLVED value.

    Read from the ``CABINET_SENTRY_TELLS`` env var (JSON), which the briefing wrapper
    (``cabinet/scripts/run-frontdoor-briefing.sh`` — a cabinet/ script, free to read
    instance/) populates from ``instance/config/signals.yml`` for the configured Sentry
    project. This is the SAME env-graft seam as ``CABINET_SENTRY_ORG`` / ``_PROJECT`` —
    framework/ never reads instance config directly, so the framework→instance boundary
    stays clean. Any absence / invalid JSON FAILS CLOSED to ``default`` (empty dict) —
    with which the discriminator can only suppress a FROZEN issue by recency or return
    INCONCLUSIVE (emit); it never suppresses a fresh un-attributable error. Never raises.
    ``env_json`` overrides the env read for tests; ``project`` is advisory (the wrapper
    has already scoped the env to the one configured project)."""
    fallback = {} if default is None else default
    raw = env_json if env_json is not None else os.environ.get("CABINET_SENTRY_TELLS", "")
    if not raw:
        return fallback
    try:
        import json  # local: keep env.py import-light for the safety switches
        data = json.loads(raw)
    except Exception:
        return fallback
    if not isinstance(data, dict):
        return fallback
    # The wrapper exports the bare tells dict for the single configured project; tolerate
    # a {project: tells} map too (index by project) in case the whole table is exported.
    if project and isinstance(data.get(project), dict):
        return data[project]
    return data


# Cache: tasks_board is read once per process (same lifecycle as captain_name).
# None ⇒ unresolved — the empty string is a VALID resolved value (a generic
# deployment with no board configured), so the sentinel is None, never "".
_tasks_board_cache: "str | None" = None


def tasks_board(default: str = "") -> str:
    """The Monday 'Tasks' board id lane-created work lands on for this
    deployment — the resolver that lifts the board id OUT of the universal-base
    ``framework`` code (``action_exec.DEFAULT_TASKS_BOARD``, the act-first
    canary's synthetic probe board) into instance config.

    Resolution order: the env override ``CABINET_TASKS_BOARD`` (an explicit
    per-process override, mirroring ``action_exec``'s existing
    ``ACTION_LANE_DEFAULT_BOARD``) → ``tasks_board`` in
    ``instance/config/platform.yml`` (else ``product.yml`` / nested
    ``product.tasks_board``) → the generic ``default`` (``""``). A generic
    deployment with NO board configured resolves ``""`` — the executor's
    ``board.isdigit()`` guard then refuses the create with a clear error rather
    than silently landing on another launcher's board (fail-closed, never
    leak)."""
    global _tasks_board_cache
    if _tasks_board_cache is not None:
        return _tasks_board_cache
    env_override = (os.environ.get("CABINET_TASKS_BOARD") or "").strip()
    if env_override:
        _tasks_board_cache = env_override
        return env_override
    board = str(default)
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("tasks_board")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("tasks_board")   # product.yml nests it
            if val is not None and str(val).strip():
                board = str(val).strip()
                break
    except Exception:
        board = str(default)
    _tasks_board_cache = board
    return board


# Cache: officers is read once per process (same lifecycle as captain_name;
# config is stable under a running officer, a restart re-reads). None ⇒
# unresolved — the EMPTY tuple is a VALID resolved value (a deployment with no
# roster configured), so the sentinel is None, never ().
_officers_cache: "tuple[str, ...] | None" = None


def officers(default: "tuple[str, ...]" = ()) -> "tuple[str, ...]":
    """The instance officer roster — the resolver that lifts officer-name
    literals (delegate/investigation whitelists, prompt-spec officer enums,
    build-time roster defaults) OUT of the universal-base ``framework`` code
    into instance data, so framework carries no launcher's lane names
    (PC-E-LOCKSTEP instance-split).

    Reads the officer column of ``cabinet/officer-capabilities.conf``
    (``officer:capability`` rows; ``#`` comments and blank lines skipped),
    deduplicated GLOBALLY preserving FIRST-SEEN FILE ORDER (a bash twin must
    dedup globally too — ``awk '!seen[$1]++'``, NOT adjacent-only ``uniq``,
    or a conf with non-contiguous officer blocks would make the two resolvers
    disagree), keeping :func:`deploys_code_officer` file-order stable. The
    conf is schg-locked germline on a live deployment: this resolver only
    READS it.

    Any absence / unreadable file / empty column falls back to ``default`` —
    the EMPTY tuple — so a deployment with no roster resolves () and consumers
    fail LOUDLY at their own seam (delegate_work rejects every officer, a
    prompt enum renders empty), never a baked-in literal roster, never another
    launcher's officers. NB: the FIRST call's resolution — fallback included —
    is cached for the process, so every caller must pass a uniform ``default``
    (all in-repo callers pass the empty one)."""
    global _officers_cache
    if _officers_cache is not None:
        return _officers_cache
    names: "tuple[str, ...]" = tuple(default)
    try:
        p = _cabinet_root() / "cabinet" / "officer-capabilities.conf"
        seen: list = []
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or ":" not in s:
                continue
            officer = s.split(":", 1)[0].strip()
            if officer and officer not in seen:
                seen.append(officer)
        if seen:
            names = tuple(seen)
    except Exception:
        names = tuple(default)
    _officers_cache = names
    return names


# Cache: deploys_code_officer is read once per process (same lifecycle as
# officers). None ⇒ unresolved — the empty string is a VALID resolved value (a
# roster with no deploys_code holder), so the sentinel is None, never "".
_deploys_code_officer_cache: "str | None" = None


def deploys_code_officer(default: str = "") -> str:
    """The FIRST officer (conf file order) holding the ``deploys_code``
    capability in ``cabinet/officer-capabilities.conf`` — the probe officer
    eval/verification surfaces use instead of hardcoding a lane CEO's name
    (PC-E-LOCKSTEP instance-split; bash twin: ``cabinet_deploys_code_officer``).

    Absence / unreadable conf / no holder falls back to ``default`` — the
    empty string — so a deployment with no deploying officer resolves "" and
    the consumer fails loudly at its own seam (an eval prints FAIL), never a
    baked-in officer name. NB: the FIRST call's resolution — fallback included
    — is cached for the process, so every caller must pass a uniform
    ``default``."""
    global _deploys_code_officer_cache
    if _deploys_code_officer_cache is not None:
        return _deploys_code_officer_cache
    holder = str(default)
    try:
        p = _cabinet_root() / "cabinet" / "officer-capabilities.conf"
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or ":" not in s:
                continue
            officer, _, cap = s.partition(":")
            if officer.strip() and cap.strip() == "deploys_code":
                holder = officer.strip()
                break
    except Exception:
        holder = str(default)
    _deploys_code_officer_cache = holder
    return holder


# Cache: chair_officer is read once per process (same lifecycle as officers).
# None ⇒ unresolved — the empty string is a VALID resolved value (a deployment
# with no roster), so the sentinel is None, never "".
_chair_officer_cache: "str | None" = None


def chair_officer(default: str = "") -> str:
    """The FIRST role in the deployment's roster (conf file order) — the
    resolver every "whose act is this by default" site consults instead of
    naming a role.

    A default actor is unavoidable: an act recorded against nobody cannot be
    graduated, demoted or undone, because the ledger cell key is
    (actor, lane, action_type). What IS avoidable is the framework choosing
    WHICH actor, which is a fact about one operator's org shape. A sole
    operator has one role; a large deployment has many; the framework knows
    only that a roster exists and that its first entry is the one the
    deployment listed first.

    Reads the same roster :func:`officers` reads, so the two can never
    disagree, and returns its first entry. Absence / unreadable roster /
    empty roster falls back to ``default`` — the EMPTY string — so a
    deployment with no roster resolves "" and consumers keep their own
    literal-free fallback, never a baked-in role name. NB: the FIRST call's
    resolution — fallback included — is cached for the process, so every
    caller must pass a uniform ``default`` (all in-repo callers pass the
    empty one)."""
    global _chair_officer_cache
    if _chair_officer_cache is not None:
        return _chair_officer_cache
    try:
        roster = officers()
        name = roster[0] if roster else str(default)
    except Exception:
        name = str(default)
    _chair_officer_cache = name
    return name


# Cache: declared_operations is read once per process (same lifecycle as
# officers). None ⇒ unresolved — the EMPTY tuple is a VALID resolved value (a
# deployment that declared none), so the sentinel is None, never ().
_declared_operations_cache: "tuple[dict, ...] | None" = None

# A declared operation id is NAMESPACED — exactly one "/", both halves
# non-empty. That single shape is what makes the deployment's vocabulary
# structurally un-collidable with the framework's own flat vocabulary, so
# opening the vocabulary can never silently redefine a framework member. It is
# the same never-overload law the extension-manifest plane already applies to
# its own operation ids.
_DECLARED_OP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$")
# An invocation token is one bare word — the program/verb a call arrives as.
# Whitespace or a shell metacharacter would make the match a parse, not a
# lookup, and a parse is where this kind of thing goes wrong.
_DECLARED_OP_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def declared_operations(default: "tuple[dict, ...]" = ()) -> "tuple[dict, ...]":
    """The operations THIS deployment performs, as declared by this deployment.

    The framework owns the CLASSES OF CONSEQUENCE (reversible, undoable,
    outward, irreversible …) and the verdict each class earns. It does not own
    the LIST OF OPERATIONS that fall in each class: that list is a fact about
    the work an operator does, and a framework that ships one is a framework
    that only fits the operator it was written for. Everything an operator does
    that the framework cannot name classifies as unclassified, which is
    permanently propose-only — so without this seam the autonomy ladder cannot
    move at all outside the work the shipped vocabulary happens to describe.

    Reads ``instance/config/operations.yml``::

        operations:
          - id: <namespace>/<name>     # namespaced, hence un-collidable
            invoked_as: [<token>, ...] # how the call arrives (program/tool)
            risk_class: <class>        # which class of consequence it is

    SHAPE is validated here; MEMBERSHIP of ``risk_class`` is validated where
    the classes are known (the authority matrix), because this resolver must
    stay a leaf. A malformed row is DROPPED, never repaired: a dropped
    operation stays unclassified and therefore propose-only, so every failure
    mode of this file narrows autonomy. Absence / unreadable / unparseable ⇒
    ``default`` — the EMPTY tuple — i.e. exactly the behaviour of a deployment
    that declared nothing. Rows are returned in file order; a duplicate id or a
    duplicate invocation token is dropped (first wins) so the mapping is a
    function. NB: the FIRST call's resolution is cached for the process."""
    global _declared_operations_cache
    if _declared_operations_cache is not None:
        return _declared_operations_cache
    rows: "tuple[dict, ...]" = tuple(default)
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        p = _cabinet_root() / "instance/config/operations.yml"
        data = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else None
        raw = (data or {}).get("operations") if isinstance(data, dict) else None
        out: list = []
        seen_ids: set = set()
        seen_tokens: set = set()
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            oid = item.get("id")
            rc = item.get("risk_class")
            toks = item.get("invoked_as")
            if not isinstance(oid, str) or not _DECLARED_OP_ID_RE.match(oid.strip()):
                continue
            oid = oid.strip()
            if oid in seen_ids:
                continue
            if not isinstance(rc, str) or not rc.strip():
                continue
            if not isinstance(toks, (list, tuple)) or not toks:
                continue
            clean = []
            for t in toks:
                if not isinstance(t, str):
                    continue
                t = t.strip()
                if not t or not _DECLARED_OP_TOKEN_RE.match(t):
                    continue
                if t.lower() in seen_tokens:
                    continue
                clean.append(t)
            if not clean:
                continue
            seen_ids.add(oid)
            seen_tokens.update(t.lower() for t in clean)
            out.append({"id": oid, "invoked_as": tuple(clean),
                        "risk_class": rc.strip()})
        if out:
            rows = tuple(out)
    except Exception:
        rows = tuple(default)
    _declared_operations_cache = rows
    return rows


def is_declared_operation_id(value: "str | None") -> bool:
    """True when ``value`` has the namespaced shape a deployment-declared
    operation id must have. The one predicate every consumer shares, so
    "is this the deployment's vocabulary or the framework's?" is answered in
    exactly one place."""
    return isinstance(value, str) and bool(_DECLARED_OP_ID_RE.match(value.strip()))


# Cache: lanes is read once per process (same lifecycle as captain_name;
# config is stable under a running officer, a restart re-reads). None ⇒
# unresolved — the EMPTY tuple is a VALID resolved value (a deployment with no
# contexts configured), so the sentinel is None, never ().
_lanes_cache: "tuple[str, ...] | None" = None


def lanes(default: "tuple[str, ...]" = ()) -> "tuple[str, ...]":
    """The instance lane enum — the sorted first top-level ``slug:`` scalar per
    ``instance/config/contexts/*.yml`` (a file without one, e.g. ``_default.yml``,
    is skipped). The parse mirrors ``run_action_lane._context_slugs`` byte-for-
    byte (minimal ``slug:`` line scan, no yaml dep, robust to a partially-written
    file) so the two can merge at a germline window without a behavior change.

    Deliberately does NOT filter on ``active:`` flags — on the launching
    instance some contexts carry ``active: false`` (R2-pending declarations)
    while their lane officers RUN LIVE, so an active-filtered enum would
    silently drop running lanes (the recon-named trap). Consumers needing
    activation state must read it at their own seam.

    Unreadable dir / no slugs falls back to ``default`` — the EMPTY tuple — so
    a deployment with no contexts resolves () and consumers fail honestly at
    their own seam (a world renders mist, a gate files under its stable
    catch-all), never an invented lane list. NB: the FIRST call's resolution —
    fallback included — is cached for the process, so every caller must pass a
    uniform ``default``."""
    global _lanes_cache
    if _lanes_cache is not None:
        return _lanes_cache
    slugs: set = set()
    try:
        # NB: single "instance/config/..." path literal (not split segments) —
        # same form as the platform.yml readers above, so the layer-separation
        # gate's exact-token heuristic doesn't flag this by-design config read.
        for f in sorted((_cabinet_root() / "instance/config/contexts").glob("*.yml")):
            try:
                for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s = line.strip()
                    if s.startswith("slug:"):
                        val = s.split(":", 1)[1].strip().strip('"').strip("'").lower()
                        if val:
                            slugs.add(val)
                        break
            except OSError:
                continue
    except OSError:
        pass
    _lanes_cache = tuple(sorted(slugs)) if slugs else tuple(default)
    return _lanes_cache


# Cache: lane_default is read once per process (same lifecycle as captain_name).
# None ⇒ unresolved — the empty string is a VALID resolved value (a generic
# deployment with no default lane ruling), so the sentinel is None, never "".
_lane_default_cache: "str | None" = None


def lane_default(default: str = "") -> str:
    """The lane stamped on action-lane proposals whose LLM output omitted a
    lane — the resolver that lifts a Captain ruling (encoded for the launching
    instance as ``lane_default`` in instance config) OUT of the universal-base
    ``framework`` signature default (``action_lane.propose_actions`` —
    PC-E-LOCKSTEP pair (e)) into instance data.

    Reads ``lane_default`` from ``instance/config/platform.yml`` (else
    ``product.yml`` / nested ``product.lane_default``). Absence / parse failure
    falls back to ``default`` — the empty string — which the acting runner's
    lane normalization files under the stable ``adhoc`` catch-all cell: a
    generic deployment never inherits another launcher's default lane and
    never crashes. NB: the FIRST call's resolution — fallback included — is
    cached for the process, so every caller must pass a uniform ``default``."""
    global _lane_default_cache
    if _lane_default_cache is not None:
        return _lane_default_cache
    lane = str(default)
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("lane_default")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("lane_default")   # product.yml nests it
            if val is not None and str(val).strip():
                lane = str(val).strip()
                break
    except Exception:
        lane = str(default)
    _lane_default_cache = lane
    return lane


# Cache: captain_timezone is read once per process (same lifecycle as
# captain_name; config is stable under a running officer, a restart re-reads).
# None ⇒ unresolved.
_captain_timezone_cache: "str | None" = None


def captain_timezone(default: str = "UTC") -> str:
    """The Captain's IANA timezone NAME for this deployment — THE one timezone
    resolver (TZ unification, silent-defaults audit C, 2026-07-18): the
    attention gate's quiet-hours/briefing-slot math, the comms-surface
    engine's horizon clock, the outcome-watchdog's slot math and the
    personal-source adapter's 'today' boundary all resolve through here, so
    the framework can never disagree with itself about the Captain's clock
    (the gate/engine used to fall to UTC while the launchd wrappers fell to
    Europe/Berlin — two clocks, silently different quiet-hours math).

    Reads ``captain_timezone`` from ``instance/config/platform.yml`` (portfolio /
    live deployments), else ``instance/config/product.yml`` (single-product
    ``work`` deployments; also accepts a nested ``product.captain_timezone``),
    exactly like ``captain_role()``. The configured name must load in
    ``zoneinfo`` — an unloadable name counts as unconfigured. Absence / parse
    failure / empty / unloadable falls back to ``default`` — **UTC**,
    announced with ONE loud stderr warn line per process (the cache
    suppresses repeats): quiet-hours and briefing-slot math SHIFTS with this
    value, so the fallback must never be silent, and the universal-base layer
    ships no captain's geography (product/captain-agnostic doctrine
    2026-07-14 — supersedes the old silent ``Europe/Berlin`` fallback; a real
    deployment sets the key, ``platform.yml.example`` ships it). Returns a
    bare IANA name string, never a tzinfo: the caller owns the name→zoneinfo
    lookup and its own UTC fail-safe if tzdata itself is unavailable."""
    global _captain_timezone_cache
    if _captain_timezone_cache is not None:
        return _captain_timezone_cache
    tz = ""
    source = "instance/config/platform.yml"
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("captain_timezone")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("captain_timezone")   # product.yml nests it
            if isinstance(val, str) and val.strip():
                tz = val.strip()
                source = rel
                break
    except Exception:
        tz = ""
    warn = ""
    if tz:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tz)
        except Exception:
            warn = (f"framework.env: captain_timezone {tz!r} ({source}) is not "
                    f"a loadable IANA zone — falling back to {default}; "
                    f"quiet-hours + briefing-slot math runs on {default} until "
                    "it is fixed")
            tz = ""
    if not tz:
        if not warn:
            warn = ("framework.env: captain_timezone is not set in "
                    "instance/config/platform.yml — falling back to "
                    f"{default}; quiet-hours + briefing-slot math runs on "
                    f"{default} until it is configured")
        print(warn, file=sys.stderr)
        tz = default
    _captain_timezone_cache = tz
    return tz


# Cache: briefing_times is read once per process (same lifecycle as
# captain_timezone). None ⇒ unresolved.
_briefing_times_cache: "tuple[str, ...] | None" = None

# The framework fleet default — the SAME slots the watchdog registry's
# _BRIEF_DEFAULTS and the services.yml fallback-mirror row carry.
_BRIEFING_TIMES_DEFAULT = ("07:30", "19:30")

_HHMM_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _normalize_briefing_slot(val) -> "str | None":
    """One briefing slot → canonical zero-padded ``"HH:MM"``, else None.
    Accepts ``"HH:MM"`` / ``"H:MM"`` strings and ints 0..1439: PyYAML loads a
    bare (unquoted) time token whose hour starts 1-9 as a YAML-1.1 sexagesimal
    int (``19:30`` → 1170); a leading-zero form like ``07:30`` stays a string.
    Ints are rescued here as minutes-since-midnight, so a missing quote can
    never silently drop or shift a slot."""
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        if 0 <= val < 24 * 60:
            return f"{val // 60:02d}:{val % 60:02d}"
        return None
    if isinstance(val, str):
        m = _HHMM_RE.match(val.strip())
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return f"{hour:02d}:{minute:02d}"
    return None


def briefing_times(default: "tuple[str, ...]" = _BRIEFING_TIMES_DEFAULT) -> "tuple[str, ...]":
    """The Captain's briefing wall-clock slots (``"HH:MM"``, Captain-local) —
    THE one source of truth for briefing times (silent-defaults audit C,
    2026-07-18). Read by: the attention gate + the comms-surface engine as
    the ``CABINET_BRIEFING_TIMES`` env default, and by
    ``cabinet/scripts/generate-plists.py`` to stamp the
    ``com.cabinet.frontdoor-briefing`` StartCalendarInterval. Two surfaces
    MIRROR it and are parity-pinned by
    ``cabinet/scripts/tests/test_briefing_time_parity.py``: the calendar row
    in ``cabinet/services.yml`` (the no-config fallback) and the ``briefing:``
    block in ``instance/config/watchdog.yml`` (the watchdog keeps its own
    no-PyYAML parser — survival contract — so it cannot import this
    resolver).

    Reads ``briefing_times`` from ``instance/config/platform.yml`` (else
    ``product.yml``, also nested under ``product.``): a list of QUOTED
    ``"HH:MM"`` strings or one CSV string ``"07:30,19:30"``. An unquoted time
    token whose hour starts 1-9 is YAML-1.1 sexagesimal (PyYAML loads ``19:30``
    as int 1170; a leading-zero ``07:30`` stays a string) — such ints are
    rescued as minutes-since-midnight. Entries failing HH:MM validation are
    dropped; a key that is present but yields NO valid slot warns once on
    stderr and falls back to ``default``; an ABSENT key falls back silently
    (07:30/19:30 IS the framework fleet default, matching the watchdog
    registry's ``_BRIEF_DEFAULTS``). Order preserved, duplicates dropped."""
    global _briefing_times_cache
    if _briefing_times_cache is not None:
        return _briefing_times_cache
    raw = None
    source = ""
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("briefing_times")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("briefing_times")   # product.yml nests it
            if val is not None:
                raw = val
                source = rel
                break
    except Exception:
        raw = None
    times: "list[str]" = []
    if raw is not None:
        if isinstance(raw, str):
            items = raw.split(",")
        elif isinstance(raw, (list, tuple)):
            items = list(raw)
        else:
            items = [raw]
        for item in items:
            slot = _normalize_briefing_slot(item)
            if slot is not None and slot not in times:
                times.append(slot)
        if not times:
            print(f"framework.env: briefing_times in {source or 'instance config'} "
                  f"has no valid HH:MM slot (got {repr(raw)[:80]}) — falling "
                  f"back to {','.join(default)}; quote the slots — an unquoted "
                  "H:MM whose hour starts 1-9 (e.g. 19:30) is a YAML "
                  "sexagesimal int", file=sys.stderr)
    result = tuple(times) if times else tuple(default)
    _briefing_times_cache = result
    return result


# ---------------------------------------------------------------------------
# Captain availability — THE declared time budget (Captain ruling 2026-07-26)
# ---------------------------------------------------------------------------
# The org fits the declared budget, never the reverse. Onboarding asks how much
# of the Captain's day the cabinet gets; the answer is a first-class instance
# value, adjustable later from the phone. Consumers (the Captain-Seat Review's
# emission bar, the comms-surface pacing cap) judge cost RELATIVE to it.
#
# UNKNOWN IS A LEGAL STATE and means exactly: "the org does not know how much
# of the Captain it is entitled to." A consumer must treat it CONSERVATIVELY —
# keep its own shipped default — and must never invent a number to stand in
# for an answer nobody gave. (The paid case is the 1/3-scored briefing: a
# placeholder that pretends to be an answer is worse than an honest absence.)

#: The canonical mode table: ``(mode, minutes_per_day, human label)``, ordered
#: least→most available. THE one source of truth — the onboarding question, the
#: Telegram verb's grammar and every renderer read it instead of restating the
#: prose, so changing a band here changes every surface at once.
#:
#: ``full_time``'s 480 is the framework's stated reading of "a full working
#: day"; a Captain who means something else states the number outright
#: ("availability 6h"), which always wins over the band.
AVAILABILITY_MODES: "tuple[tuple[str, int, str], ...]" = (
    ("away", 0, "away — nothing but a genuine emergency reaches me"),
    ("minimal", 10, "minimal — about 10 minutes a day"),
    ("part_time", 30, "part-time — about 30 minutes a day"),
    ("substantial", 120, "substantial — about 2 hours a day"),
    ("full_time", 480, "full-time — the cabinet is my main seat"),
)

#: Upper bound for a declared budget: minutes in a day. A larger number is a
#: typo, not a ruling, and is refused rather than clamped.
AVAILABILITY_MAX_MINUTES = 24 * 60

#: The unknown reading, returned whenever nothing is declared. Callers get the
#: same key set in every state, so `result["minutes_per_day"] is None` is the
#: ONE unknown test — never a missing key, never a KeyError.
_AVAILABILITY_UNKNOWN = {"minutes_per_day": None, "mode": None,
                         "source": None, "set_at": None}


def availability_modes() -> "tuple[str, ...]":
    """The fixed verb enum, in table order."""
    return tuple(m for m, _minutes, _label in AVAILABILITY_MODES)


def availability_minutes_for_mode(mode) -> "int | None":
    """Minutes/day for a canonical mode, else None (an unknown verb is never
    silently mapped onto a number)."""
    want = str(mode if mode is not None else "").strip().lower()
    for name, minutes, _label in AVAILABILITY_MODES:
        if name == want:
            return minutes
    return None


def availability_mode_for_minutes(minutes) -> "str | None":
    """The mode BAND a minutes/day figure falls in, else None. The band is the
    smallest table entry whose minutes are >= the figure (so 20 min/day reads
    as part_time, not minimal); anything above the largest band reads as the
    largest. Used for rendering only — a declared number is always the value."""
    try:
        n = int(minutes)
    except (TypeError, ValueError):
        return None
    for name, band, _label in AVAILABILITY_MODES:
        if n <= band:
            return name
    return AVAILABILITY_MODES[-1][0]


def captain_availability_path() -> Path:
    """The ADJUSTMENT store path — where a later ruling ("availability 20m" on
    Telegram, or the dashboard once it can write) lands.

    Sibling of ``comms_charter_path`` / ``comms_surface_path``: the
    ``CABINET_CAPTAIN_AVAILABILITY_FILE`` env override wins (tests, and the
    repo-root conftest's pytest fence), else
    ``instance/config/captain-availability.yml`` under the deployment root.
    Keeping the ``instance/`` reference HERE — the sanctioned layer-crossing
    seam — is what the layer-separation gate expects."""
    env_override = (os.environ.get("CABINET_CAPTAIN_AVAILABILITY_FILE") or "").strip()
    if env_override:
        return Path(env_override).expanduser()
    return _cabinet_root() / "instance/config/captain-availability.yml"


def cabinet_init_answers_path() -> Path:
    """The cabinet-init ANSWERS file — the interview's own output and the
    generator's input (``cabinet/scripts/generate-instance.py``, whose
    ``--answers`` flag defaults to the same relative path).

    Sibling of ``comms_charter_path``: ``CABINET_INIT_ANSWERS`` env override
    wins (tests / a non-default interview run), else
    ``instance/config/cabinet-init.answers.yml`` under the deployment root.
    Exists so an onboarding module in ``framework/`` can record an answer
    WITHOUT spelling an instance path of its own — this resolver is the
    sanctioned crossing."""
    env_override = (os.environ.get("CABINET_INIT_ANSWERS") or "").strip()
    if env_override:
        return Path(env_override).expanduser()
    return _cabinet_root() / "instance/config/cabinet-init.answers.yml"


# Cache: captain_availability is read once per process (same lifecycle as
# briefing_times — config is stable under a running officer; a restart, or an
# explicit cache reset in a test, re-reads). None ⇒ unresolved. The UNKNOWN
# reading is a real resolved value and IS cached, so the sentinel is None.
_captain_availability_cache: "dict | None" = None


def _availability_entry(raw) -> "dict | None":
    """One store/config row → a validated reading, else None.

    A row must yield a usable minutes figure: an explicit
    ``minutes_per_day`` (0..1440) wins, else the row's ``mode`` supplies the
    band's minutes. A row with neither — or with an out-of-range number, or an
    unknown mode and no number — is REFUSED, not repaired: a budget the org
    cannot read must read as absent so the next-oldest ruling (or the honest
    unknown) stands, never as a number nobody declared."""
    if not isinstance(raw, dict):
        return None
    mode = raw.get("mode")
    mode = str(mode).strip().lower() if isinstance(mode, str) and mode.strip() else None
    if mode is not None and availability_minutes_for_mode(mode) is None:
        mode = None                      # unknown verb: drop it, never guess
    minutes = raw.get("minutes_per_day")
    if isinstance(minutes, bool):        # bool is an int subclass — never a budget
        minutes = None
    if isinstance(minutes, (int, float)) and float(minutes).is_integer():
        minutes = int(minutes)
        if not 0 <= minutes <= AVAILABILITY_MAX_MINUTES:
            minutes = None
    else:
        minutes = None
    if minutes is None and mode is not None:
        minutes = availability_minutes_for_mode(mode)
    if minutes is None:
        return None
    return {"minutes_per_day": minutes, "mode": mode, "source": None,
            "set_at": _availability_stamp(raw.get("at"))}


def _availability_stamp(value) -> "str | None":
    """One ``at:`` field → a UTC ISO ``...Z`` string, else None.

    PyYAML loads an UNQUOTED ``2026-07-26T21:30:00Z`` as a ``datetime``, not a
    string (the same YAML-retyping class the briefing-slot rescue handles), so a
    naive isinstance-str check silently dropped every timestamp the phone verb
    wrote. Both shapes are accepted; anything else is None rather than a
    stringified repr."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, datetime):
        at = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return None


def captain_availability() -> dict:
    """How much of the Captain's day this cabinet is entitled to.

    Returns ``{"minutes_per_day": int|None, "mode": str|None,
    "source": "adjusted"|"onboarding"|None, "set_at": iso|None}`` — the same
    keys in every state. ``minutes_per_day is None`` (and ``source is None``)
    means UNKNOWN: nobody has declared a budget. Unknown is legal and
    documented; a consumer keeps its own conservative default and never
    substitutes a made-up figure.

    Precedence, highest first:

    1. the ADJUSTMENT store ``instance/config/captain-availability.yml``
       (``captain_availability_path()``) — an append-only ``entries:`` list,
       LATEST VALID ROW WINS. This is what the Telegram verb writes, so a
       ruling from the Captain's phone always beats what onboarding stamped.
    2. ``captain_availability_minutes_per_day`` (+ optional
       ``captain_availability_mode``) in ``instance/config/platform.yml``, else
       ``product.yml`` / nested ``product.`` — the value cabinet-init stamped.
    3. all-None (unknown).

    Never raises: an unreadable or malformed file counts as absent at that
    level and the next level decides."""
    global _captain_availability_cache
    if _captain_availability_cache is not None:
        return dict(_captain_availability_cache)

    result = dict(_AVAILABILITY_UNKNOWN)
    try:
        import yaml  # local: keep env.py import-light for the safety switches

        # (1) the adjustment store — latest valid entry wins.
        store = captain_availability_path()
        try:
            if store.exists():
                doc = yaml.safe_load(store.read_text(encoding="utf-8")) or {}
                entries = doc.get("entries") if isinstance(doc, dict) else None
                if isinstance(entries, list):
                    for raw in reversed(entries):
                        got = _availability_entry(raw)
                        if got is not None:
                            got["source"] = "adjusted"
                            result = got
                            break
        except Exception:  # noqa: BLE001 — a corrupt store is an absent store
            pass

        # (2) the onboarding stamp in platform.yml / product.yml.
        if result["minutes_per_day"] is None:
            root = _cabinet_root()
            for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
                p = root / rel
                try:
                    if not p.exists():
                        continue
                    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                nested = data.get("product") if isinstance(data.get("product"), dict) else {}
                minutes = data.get("captain_availability_minutes_per_day",
                                   nested.get("captain_availability_minutes_per_day"))
                mode = data.get("captain_availability_mode",
                                nested.get("captain_availability_mode"))
                got = _availability_entry({"minutes_per_day": minutes, "mode": mode})
                if got is not None:
                    got["source"] = "onboarding"
                    result = got
                    break
    except Exception:  # noqa: BLE001 — no config read may break the resolver
        result = dict(_AVAILABILITY_UNKNOWN)

    _captain_availability_cache = dict(result)
    return dict(result)


def render_availability(reading: "dict | None" = None) -> str:
    """One plain line for a reading — the shape every surface prints, so the
    pack, the phone reply and the dashboard cannot describe the same value
    three different ways."""
    r = captain_availability() if reading is None else reading
    if not r or r.get("minutes_per_day") is None:
        return ("no declared availability — the org does not know how much of "
                "the captain it is entitled to")
    mode = r.get("mode") or availability_mode_for_minutes(r["minutes_per_day"])
    return (f"{r['minutes_per_day']} min/day  mode={mode or 'unstated'}  "
            f"source={r.get('source') or 'unknown'}")


# ---------------------------------------------------------------------------
# Captain dates — DATED COMMITMENTS HE SET (Captain-Seat finding 1, 2026-07-26)
# ---------------------------------------------------------------------------
# A DATE THE CAPTAIN SETS MUST BE IMPOSSIBLE FOR THE ORG TO FORGET. The paid
# case: he set a release date, and it appeared in ZERO of the next twelve days
# of briefings — nothing in the org held it, so nothing could surface it. The
# briefing already renders commitments the Captain owes OTHER people (from the
# personal-source adapter) and dated follow-ups the ORG wrote down; a date HE
# declared had no store, no resolver and no reader at all.
#
# This resolver is the sibling of captain_availability(): one path owned here so
# writer and readers cannot drift, module-cached like every other config read,
# and NEVER raising. The documented fallback is an EMPTY LIST — "no dates
# declared", which is a legal state and means exactly that. An unreadable or
# malformed store also reads as empty at that level, so a broken file can never
# invent a deadline.
#
# APPEND-ONLY, LATEST ROW PER id WINS. `date done`/`date move` append a new row
# carrying the same id and a later status rather than editing history, so what
# he said and when stays readable. A move ALSO appends a fresh id whose
# ``supersedes`` names the row it replaced.

#: The status enum. ``open`` = the org still owes him this date; ``done`` = he
#: closed it; ``moved`` = superseded by a later row (whose ``supersedes`` points
#: back here). A row with any other word is REFUSED, not repaired — which fails
#: in the SAFE direction: an unreadable ``done`` leaves the date OPEN and still
#: visible, never silently disappeared.
CAPTAIN_DATE_STATUSES: "tuple[str, ...]" = ("open", "done", "moved")

#: Label cap. The label is the only field carrying his free text as a VALUE (it
#: is what the briefing prints), so it is length-capped at the writer and
#: re-capped here — a reader that trusted an unbounded field would let one
#: message dominate a briefing.
CAPTAIN_DATE_LABEL_MAX = 120

#: Ids are writer-minted handles, never free text: they ride phone replies and
#: prefix-selectors, so the shape is pinned here and validated on read.
_CAPTAIN_DATE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_CAPTAIN_DATE_ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def captain_dates_path() -> Path:
    """The dated-commitment store — where ``date 2026-08-13 <label>`` lands.

    Sibling of ``captain_availability_path``: the ``CABINET_CAPTAIN_DATES_FILE``
    env override wins (tests, and the repo-root conftest's pytest fence), else
    ``instance/config/captain-dates.yml`` under the deployment root. Keeping the
    ``instance/`` reference HERE — the sanctioned layer-crossing seam — is what
    the layer-separation gate expects."""
    env_override = (os.environ.get("CABINET_CAPTAIN_DATES_FILE") or "").strip()
    if env_override:
        return Path(env_override).expanduser()
    return _cabinet_root() / "instance/config/captain-dates.yml"


# Cache: same lifecycle as _captain_availability_cache — read once per process,
# cleared explicitly by a writer (cabinet/scripts/lib/captain_dates.py) or a
# test. None ⇒ unresolved; the EMPTY LIST is a real resolved value and IS
# cached, so the sentinel has to be None.
_captain_dates_cache: "list | None" = None


def _captain_date_iso(value) -> "str | None":
    """One ``date:`` field → a ``YYYY-MM-DD`` string, else None.

    PyYAML loads an unquoted ``2026-08-13`` as a ``datetime.date``, not a string
    (the same YAML-retyping class ``_availability_stamp`` handles), so a naive
    isinstance-str check would silently drop every date the phone verb wrote.
    Both shapes are accepted; a string must be a real calendar date — ``month:
    13`` is refused rather than carried as text nothing can compare."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        m = _CAPTAIN_DATE_ISO_RE.match(value.strip())
        if not m:
            return None
        try:
            return date(int(m.group(1)), int(m.group(2)),
                        int(m.group(3))).isoformat()
        except ValueError:
            return None
    return None


def _captain_date_entry(raw) -> "dict | None":
    """One store row → a validated entry, else None.

    A row must carry a usable id, a real calendar date, a non-empty label and a
    known status. A row missing any of those is REFUSED, not repaired: a date
    the org cannot read must read as ABSENT so an earlier valid row for the same
    id still stands, never as a deadline nobody set. (Direction matters: a
    refused ``done`` row leaves the date open and visible — the failure mode this
    whole store exists to prevent is a date going quiet, so every refusal errs
    toward still showing it.)"""
    if not isinstance(raw, dict):
        return None
    rid = raw.get("id")
    rid = rid.strip() if isinstance(rid, str) else None
    if not rid or not _CAPTAIN_DATE_ID_RE.match(rid):
        return None
    when = _captain_date_iso(raw.get("date"))
    if when is None:
        return None
    label = raw.get("label")
    if isinstance(label, (int, float)) and not isinstance(label, bool):
        label = str(label)                # an all-digit label YAML retyped
    label = label.strip()[:CAPTAIN_DATE_LABEL_MAX] if isinstance(label, str) else ""
    if not label:
        return None
    status = raw.get("status")
    status = status.strip().lower() if isinstance(status, str) else ""
    if status not in CAPTAIN_DATE_STATUSES:
        return None
    supersedes = raw.get("supersedes")
    supersedes = supersedes.strip() if isinstance(supersedes, str) else ""
    if supersedes and not _CAPTAIN_DATE_ID_RE.match(supersedes):
        supersedes = ""
    source = raw.get("source")
    source = source.strip()[:40] if isinstance(source, str) else ""
    return {"id": rid, "date": when, "label": label, "status": status,
            "set_at": _availability_stamp(raw.get("at")),
            "source": source or None, "supersedes": supersedes or None}


def captain_dates() -> list:
    """Every dated commitment the Captain has declared, folded to current state.

    Returns a list of ``{"id", "date", "label", "status", "set_at", "source",
    "supersedes"}`` dicts sorted by date then id (a total, stable order so every
    surface lists them the same way). The DOCUMENTED FALLBACK IS ``[]`` — no
    store, an empty store, a corrupt store or a store with no valid row all read
    as "no dates declared". Never raises.

    Folding: rows are append-only, so the LAST valid row for an id is that id's
    current state (``date done`` / ``date move`` append rather than edit). Rows
    the validator refuses are skipped, which leaves the previous row for that id
    standing.

    Source: ``instance/config/captain-dates.yml``
    (``captain_dates_path()``) — the same one-resolver discipline as the
    availability dial, so the phone writer and every reader cannot drift."""
    global _captain_dates_cache
    if _captain_dates_cache is not None:
        return [dict(row) for row in _captain_dates_cache]

    folded: "dict[str, dict]" = {}
    try:
        import yaml  # local: keep env.py import-light for the safety switches

        store = captain_dates_path()
        if store.exists():
            doc = yaml.safe_load(store.read_text(encoding="utf-8")) or {}
            entries = doc.get("entries") if isinstance(doc, dict) else None
            if isinstance(entries, list):
                for raw in entries:
                    got = _captain_date_entry(raw)
                    if got is not None:
                        folded[got["id"]] = got
    except Exception:  # noqa: BLE001 — a corrupt store is an absent store
        folded = {}

    result = sorted(folded.values(), key=lambda r: (r["date"], r["id"]))
    _captain_dates_cache = [dict(row) for row in result]
    return [dict(row) for row in result]


def captain_open_dates() -> list:
    """The OPEN dates only — what the org still owes him, soonest first.

    This is the reader every consumer wants: a ``done`` or ``moved`` row is
    history, and an empty list means he has no live dates (the honest degenerate
    end — consumers render NOTHING for it, never a placeholder)."""
    return [row for row in captain_dates() if row.get("status") == "open"]


def render_captain_date(row: dict, *, today: "str | None" = None) -> str:
    """One plain line for one date — the shape EVERY surface prints, so the
    briefing, the phone reply and the Captain-seat pack cannot describe the same
    date three different ways.

    ``<label>: <date> (in N days)`` while it is ahead; ``(today)`` on the day;
    and PAST DUE renders LOUDER — an ``OVERDUE`` marker leads the line — because
    the failure this store exists to prevent is a date going quiet, and the
    quietest possible failure is a passed date rendered like any other row.

    ``today`` (``YYYY-MM-DD``) is injectable so callers and tests are
    clock-free; the default is today in UTC."""
    label = str(row.get("label") or "").strip() or "(unlabelled)"
    when = _captain_date_iso(row.get("date"))
    if when is None:
        return f"{label}: (no readable date)"
    ref = _captain_date_iso(today) if today else None
    if ref is None:
        ref = datetime.now(timezone.utc).date().isoformat()
    delta = (date.fromisoformat(when) - date.fromisoformat(ref)).days
    if delta > 0:
        return f"{label}: {when} (in {delta} day{'s' if delta != 1 else ''})"
    if delta == 0:
        return f"{label}: {when} (today)"
    late = -delta
    return (f"OVERDUE by {late} day{'s' if late != 1 else ''} — "
            f"{label}: {when}")


# Cache: shared_env_path is read once per process (same lifecycle as
# captain_name). None ⇒ unresolved — the empty string is a VALID resolved value
# (a generic deployment with no shared credential file), so the sentinel is
# None, never "".
_shared_env_path_cache: "str | None" = None


def shared_env_path(default: str = "") -> str:
    """The filesystem path to the shared credentials ``.env`` file the action
    lane loads MONDAY_API_TOKEN / MONDAY_API_KEY (and friends) from — the
    resolver that lifts the personal-source adapter's ``_shared/.env``
    credential path OUT of the universal-base ``framework`` code
    (``action_exec._load_shared_env`` + ``actfirst_canary``'s env-perms check)
    into instance config, so framework carries no launcher's adapter-specific
    path (source-adapter boundary §5, Tier-2 credential reparent).

    Resolution order: the env override ``CABINET_SHARED_ENV`` (an explicit
    per-process override, mirroring ``tasks_board``'s ``CABINET_TASKS_BOARD``) →
    ``shared_env_path`` in ``instance/config/platform.yml`` (else ``product.yml``
    / nested ``product.shared_env_path``) → the generic ``default`` (``""``). A
    generic deployment with NO shared env configured resolves ``""`` — the
    caller then SKIPS loading (no credentials; the action lane's Monday calls
    fail closed with a clear "not set" error rather than reading another
    launcher's file). The value is returned verbatim; a leading ``~`` is the
    caller's to ``expanduser`` (mirrors retro's resolution). Byte-identical on
    this instance to the removed home-relative shared-env read."""
    global _shared_env_path_cache
    if _shared_env_path_cache is not None:
        return _shared_env_path_cache
    env_override = (os.environ.get("CABINET_SHARED_ENV") or "").strip()
    if env_override:
        _shared_env_path_cache = env_override
        return env_override
    path = str(default)
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("shared_env_path")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("shared_env_path")   # product.yml nests it
            if val is not None and str(val).strip():
                path = str(val).strip()
                break
    except Exception:
        path = str(default)
    _shared_env_path_cache = path
    return path


# Cache: retro_pipe_dir is read once per process (same lifecycle as
# captain_name). None ⇒ unresolved — the empty string is a VALID resolved value
# (a generic deployment with no retrodiction scoring lib), so the sentinel is
# None, never "".
_retro_pipe_dir_cache: "str | None" = None


def retro_pipe_dir(default: str = "") -> str:
    """The filesystem path to the retrodiction SCORING pipe dir (the dir holding
    ``lib.py``) the fidelity EvaluationEngine (``framework.fidelity.retro``)
    loads its leak-safe scoring logic from — the resolver that lifts the
    personal-source adapter's ``retrodiction`` path OUT of the universal-base
    ``framework`` shim into instance config, so framework carries no launcher's
    adapter-specific path (source-adapter boundary §5, the parallel EVALUATION
    seam). The SCORING functions stay in framework (they ARE the
    EvaluationEngine, not the sensing seam); only the PATH resolves here.

    Reads ``retro_pipe_dir`` from ``instance/config/platform.yml`` (else
    ``product.yml`` / nested ``product.retro_pipe_dir``), exactly like
    ``tasks_board()`` MINUS the env override — ``retro.py`` keeps reading its own
    historical ``CABINET_RETRO_PIPE_DIR`` override so THAT behavior is
    byte-identical. Any absence / parse failure / empty value falls back to
    ``default`` (``""``); ``retro.py`` treats ``""`` as "no retrodiction lib
    configured" (``retro_available()`` → False, the stub raises with guidance on
    first use). The value is returned verbatim; the caller ``expanduser``s."""
    global _retro_pipe_dir_cache
    if _retro_pipe_dir_cache is not None:
        return _retro_pipe_dir_cache
    path = str(default)
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("retro_pipe_dir")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("retro_pipe_dir")   # product.yml nests it
            if val is not None and str(val).strip():
                path = str(val).strip()
                break
    except Exception:
        path = str(default)
    _retro_pipe_dir_cache = path
    return path


# Cache: vault_dir is read once per process (same lifecycle as captain_name).
# None ⇒ unresolved — the EMPTY string is a VALID resolved value (a generic
# deployment with no vault), so the sentinel is None, never "".
_vault_dir_cache: "str | None" = None


def vault_dir(default: str = "") -> str:
    """The captain's brain/notes VAULT directory for this deployment — the
    resolver that lifts the vault path OUT of the universal-base ``framework``
    code (the fidelity decision-cell's Decisions corpus dir; on Flavor-A the
    adapter's personal-source vault) into instance config, so framework names no
    launcher's vault path — and, crucially, no adapter-specific vault env key
    that a clean-room box does not set (source-adapter boundary §5, Tier-2 path
    reparent).

    Resolution order: the env override ``CABINET_VAULT_DIR`` (an explicit
    per-process override, mirroring ``tasks_board``'s ``CABINET_TASKS_BOARD``) →
    ``vault_dir`` in ``instance/config/platform.yml`` (else ``product.yml`` /
    nested ``product.vault_dir``) → the generic ``default`` (``""``). A non-empty
    value is ``~``-expanded to an absolute path. A generic deployment with NO
    vault configured resolves ``""`` — the caller then treats the corpus as empty
    (fail-closed: no vault ⇒ no cases), never crashes, and never leaks another
    launcher's vault. On THIS deployment platform.yml carries the brain vault
    dir, so the Decisions corpus resolves byte-identically to the removed
    hardcode."""
    global _vault_dir_cache
    if _vault_dir_cache is not None:
        return _vault_dir_cache
    env_override = (os.environ.get("CABINET_VAULT_DIR") or "").strip()
    if env_override:
        _vault_dir_cache = os.path.expanduser(env_override)
        return _vault_dir_cache
    resolved = default
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("vault_dir")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("vault_dir")   # product.yml nests it
            if isinstance(val, str) and val.strip():
                resolved = val.strip()
                break
    except Exception:
        resolved = default
    _vault_dir_cache = os.path.expanduser(resolved) if resolved else resolved
    return _vault_dir_cache


# Cache: state_dir is read once per process (same lifecycle as captain_name).
# None ⇒ unresolved — the EMPTY string is a VALID resolved value (a generic
# deployment with no personal-source state dir), so the sentinel is None, never "".
_state_dir_cache: "str | None" = None


def state_dir(default: str = "") -> str:
    """The deployment's PERSONAL-SOURCE runtime-state directory — the resolver
    that lifts the personal-source adapter's ``state`` path OUT of the
    universal-base ``framework`` code (the fidelity decision-cache + the
    autonomy-outcomes ledger; the outcome-watchdog's watched brain-pipe dir)
    into instance config, so framework names no launcher's state path
    (source-adapter boundary §5, Tier-2 path reparent).

    Resolution order: the env override ``CABINET_STATE_DIR`` (an explicit
    per-process override) → ``state_dir`` in ``instance/config/platform.yml``
    (else ``product.yml`` / nested ``product.state_dir``) → the generic
    ``default`` (``""``). A non-empty value is ``~``-expanded to an absolute
    path. A generic deployment with NO state dir configured resolves ``""``: a
    caller that needs a writable dir substitutes its OWN generic fallback (e.g.
    ``~/.cabinet/state``), and the outcome-watchdog treats ``""`` as
    'nothing to watch' (the Flavor-B degrade). On THIS deployment platform.yml
    carries the brain state dir, so the cache/outcomes/watched paths resolve
    byte-identically to the removed hardcodes."""
    global _state_dir_cache
    if _state_dir_cache is not None:
        return _state_dir_cache
    env_override = (os.environ.get("CABINET_STATE_DIR") or "").strip()
    if env_override:
        _state_dir_cache = os.path.expanduser(env_override)
        return _state_dir_cache
    resolved = default
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("state_dir")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("state_dir")   # product.yml nests it
            if isinstance(val, str) and val.strip():
                resolved = val.strip()
                break
    except Exception:
        resolved = default
    _state_dir_cache = os.path.expanduser(resolved) if resolved else resolved
    return _state_dir_cache


# Cache: git_repos is read once per process (same lifecycle as captain_name;
# config is stable under a running officer, a restart re-reads). None ⇒
# unresolved — the EMPTY tuple is a VALID resolved value (a deployment with no
# git corpus configured), so the sentinel is None, never ().
_git_repos_cache: "tuple[Path, ...] | None" = None


def git_repos(default: "tuple[Path, ...]" = ()) -> "tuple[Path, ...]":
    """The Captain's product/infra git repos mined for the fidelity decision
    cell's git-derived DecisionCases — the resolver that lifts the repo list
    OUT of the universal-base ``framework`` code (``decision_cell``'s default
    git corpus) into instance config, so framework names no launcher's repos
    (product/captain-agnostic instance-split; the ``org_domains()`` precedent
    — a list-valued config with no env override).

    Reads the ``git_repos`` list from ``instance/config/platform.yml`` (else
    ``product.yml``; also accepts a nested ``product.git_repos``). Each entry
    is ``~``-expanded to an absolute ``Path``; order is preserved. Any absence
    / parse failure / empty list falls back to ``default`` — the EMPTY tuple —
    so a generic deployment mines NO git repos for the corpus (fail-closed:
    the corpus is decisions-only, never crashes, never scans another
    launcher's repos). ``decision_cell.build_decision_corpus`` passes this as
    ITS default when the caller supplies no explicit ``repos=``."""
    global _git_repos_cache
    if _git_repos_cache is not None:
        return _git_repos_cache
    repos: "tuple[Path, ...]" = tuple(default)
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        root = _cabinet_root()
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = root / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("git_repos")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("git_repos")   # product.yml nests it
            if isinstance(val, (list, tuple)):
                cleaned = tuple(
                    Path(r).expanduser() for r in val
                    if isinstance(r, str) and r.strip())
                if cleaned:
                    repos = cleaned
                    break
    except Exception:
        repos = tuple(default)
    _git_repos_cache = repos
    return repos


def watchdog_config_path(default: str = "") -> str:
    """The path to the outcome-watchdog's deployment table file — the resolver
    that lifts the ``instance/config/watchdog.yml`` path OUT of the universal-base
    ``framework`` watchdog registry (egg R017 moved the DATA there; this moves
    the framework's knowledge of WHERE through the one ratified env seam), so
    ``framework/watchdog`` carries no instance path tokens.

    Resolution order: the env override ``CABINET_WATCHDOG_CONFIG`` (an explicit
    per-process override, ``~``-expanded, mirroring ``shared_env_path``'s
    ``CABINET_SHARED_ENV``) → ``<root>/instance/config/watchdog.yml`` under the
    deployment root — the fixed Captain-owned config location, same
    joined-literal seam idiom as ``captain_name()``'s platform.yml read → the
    generic ``default`` (``""``) on any failure. Returns a PATH only, never
    parsed content: the registry owns its stdlib parse + generic fail-safe
    defaults (survival contract), so an absent/unreadable file — or ``""`` —
    degrades to the same generic tables as before (briefing 07:30/19:30, empty
    roster, empty pipe table, full catalog). Deliberately uncached: it is a
    pure path computation (no yaml), read once at registry import."""
    env_override = (os.environ.get("CABINET_WATCHDOG_CONFIG") or "").strip()
    if env_override:
        return os.path.expanduser(env_override)
    try:
        return str(_cabinet_root() / "instance/config/watchdog.yml")
    except Exception:
        return str(default)


def liveness_config_path(default: str = "") -> str:
    """The path to the Captain-contact dead-man's deployment table — the same
    seam idiom as ``watchdog_config_path``, so ``framework/liveness`` carries no
    instance path tokens.

    Resolution order: the env override ``CABINET_LIVENESS_CONFIG`` (explicit
    per-process, ``~``-expanded) → ``<root>/instance/config/liveness.yml`` →
    the generic ``default`` (``""``) on any failure. Returns a PATH only: the
    emitter owns its stdlib parse and its INERT fail-safe (survival contract),
    so an absent/unreadable file — or ``""`` — simply means this deployment
    pings nothing, which is the correct default for a fresh clone. Deliberately
    uncached: a pure path computation, no yaml."""
    env_override = (os.environ.get("CABINET_LIVENESS_CONFIG") or "").strip()
    if env_override:
        return os.path.expanduser(env_override)
    try:
        return str(_cabinet_root() / "instance/config/liveness.yml")
    except Exception:
        return str(default)


def fleetwatch_config_path(default: str = "") -> str:
    """The path to the FLEET dead-man's expectation table — the sibling seam to
    ``liveness_config_path``, so ``cabinet/scripts/fleet-deadman.py`` carries no
    instance path tokens either.

    Resolution order: ``CABINET_FLEETWATCH_CONFIG`` → ``<root>/instance/config/
    fleetwatch.yml`` → ``default``. Path only; the watcher owns its stdlib parse
    and its UNARMED fail-safe, so an absent file means "expect nothing", which
    reads as UNKNOWN/``unarmed`` and never as a fleet that is alive."""
    env_override = (os.environ.get("CABINET_FLEETWATCH_CONFIG") or "").strip()
    if env_override:
        return os.path.expanduser(env_override)
    try:
        return str(_cabinet_root() / "instance/config/fleetwatch.yml")
    except Exception:
        return str(default)


def fleet_liveness_dir(default: str = "") -> str:
    """Where fleet pulses and the fleet verdict live. ONE store per box:
    ``CABINET_FLEETWATCH_STATE_DIR`` (explicit, ``~``-expanded) →
    ``~/.cabinet/liveness``.

    DELIBERATELY OUTSIDE THE REPO and outside any service. The store must outlive
    every process that writes to it — the entire premise of a dead-man — so it
    cannot sit in a datastore (any datastore is itself a watched process on the
    watched box) nor in a working tree a clone or worktree can move under it.

    IT IS STEERED BY NOTHING A LAUNCHD PLIST MAY OR MAY NOT CARRY, and both
    halves of that rule were paid for. It does not ride ``ledger_dir()``, which
    honours ``CABINET_EVENT_LOG_DIR`` — set by the fleet's plists, not the
    watcher's (caught while attacking this function, before it shipped). And it
    no longer rides ``CABINET_ENV``, which shipped splitting the fleet's own
    writers from EACH OTHER: ``officer.cos-inbound`` sets it and pulsed to
    ``liveness/``; ``outcome-watchdog`` carries no ``EnvironmentVariables`` dict
    at all and pulsed to ``liveness-dev/``; the watcher scanned ``liveness/``. A
    maximally healthy fleet therefore read a confident, permanent DEAD. That was
    defended in this docstring as failing safe — "a false page, never a false
    all-clear" — which measured against the real plists is not conservative but
    non-functional, and 43 of 51 archived plists would have inherited it.

    Setting the variable on the writers was the obvious repair and was REJECTED:
    ``CABINET_ENV`` also gates ``allow_sends()`` and ``ledger_dir()``, so arming
    the dead-man that way would switch on outbound sends and move the consequence
    ledger for a job that asked for neither. A liveness fix may not smuggle in an
    outward-facing behaviour change.

    THE COST OF ONE STORE IS ACCEPTED AND BOUNDED: a hand-run sweep can hold a
    source "fresh" for at most its expected window, and staleness reclaims it.
    The pulse records the tree that wrote it and the verdict reports it, so a
    pulse from a clone is visible. It is deliberately NOT filtered on — rejecting
    foreign origins would put the watcher's own tree back into the resolution,
    which is this defect wearing a new variable. Isolation stays EXPLICIT via
    ``CABINET_FLEETWATCH_STATE_DIR``, which every test already uses."""
    override = (os.environ.get("CABINET_FLEETWATCH_STATE_DIR") or "").strip()
    if override:
        return os.path.expanduser(override)
    try:
        return str(Path.home() / ".cabinet" / "liveness")
    except Exception:
        return str(default)


def active_preset(default: str = "work") -> str:
    """The ACTIVE preset slug for this deployment — the resolver that lifts the
    ``instance/config/active-preset`` read OUT of universal-base ``framework``
    code (the onboarding planner's preset-defaults loader) into the one
    ratified env seam. The preset's CONTENT stays layer payload the caller
    locates (framework never knows where ``presets/`` lives — see
    ``framework.onboarding.plan.load_preset_defaults``); only the Captain-owned
    instance-side POINTER resolves here.

    Resolution order: the env override ``CABINET_ACTIVE_PRESET`` (an explicit
    per-process override) → the first non-empty content of
    ``<root>/instance/config/active-preset`` (same joined-literal seam idiom as
    ``captain_name()``) → the generic ``default`` (``"work"`` — the SAME
    fallback ``cabinet/scripts/load-preset.sh`` uses, so an unconfigured
    deployment resolves identically on both sides of the seam). Any parse/read
    failure falls back to ``default`` — never crashes, never leaks another
    launcher's preset. Returned verbatim (no slug validation): the caller owns
    its own traversal guard before using the slug as a path segment.
    Deliberately uncached: a single tiny file read (no yaml), called once per
    onboarding run."""
    env_override = (os.environ.get("CABINET_ACTIVE_PRESET") or "").strip()
    if env_override:
        return env_override
    try:
        p = _cabinet_root() / "instance/config/active-preset"
        if p.is_file():
            declared = p.read_text(encoding="utf-8").strip()
            if declared:
                return declared
    except Exception:
        pass
    return default


# The tasks/coordination context-slug shape gate (FW-073 launcher allowlist +
# my-tasks.sh CLI gate, Spec 038 §4.8): [a-z0-9][a-z0-9-]*, max 32 chars.
# Compiled once; static pattern (no dynamic construction, no ReDoS surface).
_CONTEXT_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")


def _context_slug_ok(val: str) -> bool:
    """True when ``val`` is a well-formed context slug. Config values are
    UNTRUSTED data — a non-conforming candidate is treated as unresolved (its
    rung is skipped), never returned, so ``../``, ``$(...)``, ``;`` etc. can
    never reach a path join, a psql var, or an env export."""
    return bool(val) and _CONTEXT_SLUG_RE.fullmatch(val) is not None


def active_context(officer: "str | None" = None, default: str = "",
                   root: "Path | str | None" = None) -> str:
    """The tasks/coordination context slug for this session — the resolver
    that fixes the CONFIG SPLIT (audit 2026-07-16): the tasks subsystem keyed
    off ``instance/config/active-project.txt`` alone, but preset deployments
    (e.g. the portfolio shape) declare lanes via ``instance/config/contexts/``
    and never write that file, so ``officer_tasks`` was structurally unusable
    there. Twin of ``cabinet/scripts/lib/lanes.sh cabinet_resolve_context``
    (keep rung-for-rung parity — test-pinned by
    ``cabinet/scripts/lib/tests/test_resolve_context_sh.py``) and of the
    dashboard's ``src/lib/active-context.ts`` (which has no officer rung).

    Rungs — first candidate passing :func:`_context_slug_ok` wins; a
    non-conforming value skips its rung (never returned):

      1. ``CABINET_CONTEXT`` env (session/launchd scope)
      2. ``instance/config/active-project.txt`` (single-product deployments)
      3. officer→lane derivation (``officer`` given): exact slug match in the
         declared-lane enum, else the LONGEST lane ``L`` with
         ``officer == "L-<anything>"`` (portfolio ``<lane>-ceo`` officers —
         no suffix literal is hardcoded, so any preset's per-lane officer
         naming resolves)
      4. the single declared lane, when the enum has exactly one
      5. the Captain-ruled ``lane_default`` (platform.yml / product.yml),
         only when it IS a declared lane

    The declared-lane enum is the first top-level ``slug:`` scalar per
    ``instance/config/contexts/*.yml`` — the SAME minimal line-scan as
    :func:`lanes` / ``run_action_lane._context_slugs`` (re-implemented here
    rather than called so this resolver is ``root``-injectable and UNCACHED:
    ``active-project.txt`` / env can change under a long-lived process, and
    the lanes() process cache would pin the first fixture a test resolved).
    Preset-awareness is via the preset's MATERIALIZED shape (contexts enum +
    roster naming), never by parsing ``presets/`` — framework stays
    layer-clean and product-agnostic.

    No resolution falls back to ``default`` — the EMPTY string — and every
    consumer fails LOUD at its own seam with a remedy naming the rungs
    (``officer_tasks.context_slug`` is NOT NULL; a silent invented context
    would misfile coordination state). Never raises. ``root`` overrides
    ``_cabinet_root()`` for tests/embedders."""
    base = Path(root).expanduser() if root else _cabinet_root()

    # R1 — session env (whitespace-stripped, shape-gated).
    cand = "".join((os.environ.get("CABINET_CONTEXT") or "").split())
    if _context_slug_ok(cand):
        return cand

    # R2 — active-project.txt (whitespace-stripped, shape-gated).
    try:
        p = base / "instance/config/active-project.txt"
        if p.is_file():
            cand = "".join(p.read_text(encoding="utf-8").split())
            if _context_slug_ok(cand):
                return cand
    except Exception:
        pass

    # R3–R5 — preset-derived, all off the declared-lane enum.
    slugs: set = set()
    try:
        for f in sorted((base / "instance/config/contexts").glob("*.yml")):
            try:
                for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s = line.strip()
                    if s.startswith("slug:"):
                        val = s.split(":", 1)[1].strip().strip('"').strip("'").lower()
                        if val:
                            slugs.add(val)
                        break
            except OSError:
                continue
    except OSError:
        pass
    lanes_enum = sorted(slugs)
    if lanes_enum:
        if officer:
            best = ""
            for lane in lanes_enum:
                if not _context_slug_ok(lane):
                    continue
                if officer == lane:
                    best = lane
                    break
                if officer.startswith(lane + "-") and len(lane) > len(best):
                    best = lane
            if best:
                return best
        if len(lanes_enum) == 1 and _context_slug_ok(lanes_enum[0]):
            return lanes_enum[0]
        cand = _lane_default_uncached(base)
        if _context_slug_ok(cand) and cand in lanes_enum:
            return cand
    return default


def _lane_default_uncached(base: Path) -> str:
    """Root-injectable, uncached read of the ``lane_default`` scalar —
    :func:`active_context`'s R5 source. Same key logic as
    :func:`lane_default` (platform.yml, else product.yml, top-level or nested
    under ``product:``) but bypasses that resolver's process cache and fixed
    root, for the same reasons active_context itself is uncached. Absence /
    parse failure ⇒ ``""`` (the rung is skipped); never raises."""
    try:
        import yaml  # local: keep env.py import-light for the safety switches
        for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
            p = base / rel
            try:
                if not p.exists():
                    continue
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            val = data.get("lane_default")
            if val is None and isinstance(data.get("product"), dict):
                val = data["product"].get("lane_default")   # product.yml nests it
            if val is not None and str(val).strip():
                return str(val).strip()
    except Exception:
        pass
    return ""


# Cache: org_vault_dir is read once per process (same lifecycle as
# vault_dir). None ⇒ unresolved — the EMPTY string is a VALID resolved value
# (a deployment with no org corpus), so the sentinel is None, never "".
_org_vault_dir_cache: "str | None" = None


def org_vault_dir(default: str = "") -> str:
    """The cabinet's VAULT — the org's own knowledge-corpus directory
    (``vault/``, Captain-ratified 2026-07-16 as the default vault; the
    directory and this resolver were formerly named product-brain).

    Where ``vault_dir()`` above resolves the captain's PERSONAL brain (an
    external notes vault, absent on clean-room org boxes), this resolver names
    the ORG's OWN knowledge — architecture, decisions, incidents, deploy
    notes, designs, plans, any captain/org doc (see ``vault/README.md``) —
    written by officers via normal file writes and gathered by
    ``run_action_lane.gather_signals``'s corpus sections. The DISTINCT name is
    deliberate: reusing ``vault_dir`` for the org corpus would have silently
    repointed the personal-vault seam (fidelity Decisions corpus, flavor-A
    gather) at the in-repo corpus.

    Resolution order:
      1. env ``CABINET_ORG_VAULT_DIR`` (explicit per-process override,
         mirroring ``vault_dir``'s ``CABINET_VAULT_DIR``; honored verbatim)
      2. env ``CABINET_PRODUCT_BRAIN_DIR`` — the pre-rename alias, still
         honored so existing deployments/launchers keep resolving
      3. the ``org_vault_dir`` key in ``instance/config/platform.yml`` (else
         ``product.yml``) IF the directory it names exists — the key
         generate-instance.py stamps; relative values resolve against the
         repo root, absolute/``~`` values are honored as-is, so a captain
         relocates the corpus by editing config
      4. the legacy ``product_brain_dir`` key — same semantics, still honored
         so a hand-edited pre-rename config keeps working
      5. ``<repo>/vault`` IF that directory exists (the corpus ships in-repo,
         so any checkout that carries it resolves with zero config)
      6. legacy ``<repo>/product-brain`` IF it exists (un-migrated checkout)
      7. the generic ``default`` (``""``).
    A non-empty value is ``~``-expanded. Every non-env arm is existence-gated,
    so a deployment with NO corpus (or a configured path that does not exist)
    resolves ``""``/the next arm — the caller then treats the corpus sections
    as empty (fail-closed: no corpus ⇒ no sections), never crashes, and never
    scans another launcher's paths."""
    global _org_vault_dir_cache
    if _org_vault_dir_cache is not None:
        return _org_vault_dir_cache
    for env_name in ("CABINET_ORG_VAULT_DIR", "CABINET_PRODUCT_BRAIN_DIR"):
        env_override = (os.environ.get(env_name) or "").strip()
        if env_override:
            _org_vault_dir_cache = os.path.expanduser(env_override)
            return _org_vault_dir_cache
    resolved = default
    try:
        root = _cabinet_root()
        # platform.yml / product.yml key (stamped by generate-instance.py);
        # the new key name wins, the legacy key is honored after it.
        try:
            import yaml  # local: keep env.py import-light for the safety switches
            for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
                p = root / rel
                try:
                    if not p.exists():
                        continue
                    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                val = None
                for key in ("org_vault_dir", "product_brain_dir"):
                    cand_val = data.get(key)
                    if cand_val is None and isinstance(data.get("product"), dict):
                        cand_val = data["product"].get(key)
                    if isinstance(cand_val, str) and cand_val.strip():
                        val = cand_val
                        break
                if isinstance(val, str) and val.strip():
                    cand_str = os.path.expanduser(val.strip())
                    cand_path = Path(cand_str)
                    if not cand_path.is_absolute():
                        cand_path = root / cand_str
                    if cand_path.is_dir():
                        _org_vault_dir_cache = str(cand_path)
                        return _org_vault_dir_cache
                    break  # key set but dir absent → fall through (fail-closed)
        except Exception:
            pass
        for rel_default in ("vault", "product-brain"):
            cand = root / rel_default
            if cand.is_dir():
                resolved = str(cand)
                break
    except Exception:
        resolved = default
    _org_vault_dir_cache = os.path.expanduser(resolved) if resolved else resolved
    return _org_vault_dir_cache


def product_brain_dir(default: str = "") -> str:
    """DEPRECATED pre-2026-07-16 name of :func:`org_vault_dir` — a working
    alias, kept because the schg-locked germline acting lane
    (``framework/acting/run_action_lane.py``) imports this symbol and can only
    be modernized in a Captain unlock window (and out-of-tree scripts may
    still call it). New code calls ``org_vault_dir()``; resolution — including
    the legacy ``CABINET_PRODUCT_BRAIN_DIR`` env alias — is identical."""
    return org_vault_dir(default)


def comms_charter_path() -> Path:
    """The instance Comms Charter path (attention-gateway P4).

    The FOUNDATION resolver for the attention gateway's routing policy: an
    explicit ``CABINET_CHARTER_PATH`` env override wins (per-process / tests),
    else ``instance/config/comms-charter.yml`` under the deployment root. This
    keeps the ``instance/`` reference on framework.env — the sanctioned
    layer-crossing seam — instead of hardcoded in framework/attention (the
    layer-separation gate rejects a raw instance path elsewhere in framework).
    The caller (framework.attention.charter) loads the conservative framework
    default when this path is absent or invalid, so a clean-room box with no
    instance charter still routes."""
    env_override = (os.environ.get("CABINET_CHARTER_PATH") or "").strip()
    if env_override:
        return Path(env_override).expanduser()
    # Full relative-path string (env.py house style — a bare "instance" path
    # segment trips the layer-separation heuristic; the joined string, like
    # the platform.yml readers above, does not).
    return _cabinet_root() / "instance/config/comms-charter.yml"


def comms_surface_path() -> Path:
    """The instance comms-surface config path (captain-surface TG engine).

    Sibling of ``comms_charter_path`` — the FOUNDATION resolver for the
    pacing/pin/briefing-card engine's instance bindings (cap, ask-first vs
    auto-push, dashboard URL). ``CABINET_SURFACE_CONFIG_PATH`` env override
    wins (tests / per-process), else ``instance/config/comms-surface.yml``
    under the deployment root. The caller
    (``framework.comms.surface.config``) falls back to quiet foundation
    defaults when the file is absent or invalid, so a clean-room box runs
    unconfigured. Keeping the ``instance/`` reference HERE — the sanctioned
    layer-crossing seam — is what the layer-separation gate expects."""
    env_override = (os.environ.get("CABINET_SURFACE_CONFIG_PATH") or "").strip()
    if env_override:
        return Path(env_override).expanduser()
    return _cabinet_root() / "instance/config/comms-surface.yml"
