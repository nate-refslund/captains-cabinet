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
    ``work`` deployments), per CLAUDE.md → "Addressing the Captain". Any
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
    launcher's officers."""
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
    baked-in officer name."""
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
    catch-all), never an invented lane list."""
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
    never crashes."""
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


def captain_timezone(default: str = "Europe/Berlin") -> str:
    """The Captain's IANA timezone NAME for this deployment — the resolver that
    lifts the 'today'-boundary timezone OUT of the universal-base ``framework``
    acting code (``screenpipe_adapter._captain_tz``) into instance config, so
    framework carries no hand-read of ``instance/config/platform.yml``.

    Reads ``captain_timezone`` from ``instance/config/platform.yml`` (portfolio /
    live deployments), else ``instance/config/product.yml`` (single-product
    ``work`` deployments; also accepts a nested ``product.captain_timezone``),
    exactly like ``captain_role()``. Any absence / parse failure / empty value
    falls back to ``default`` — the generic Central-European ``Europe/Berlin``
    (CET/CEST, DST-aware), the SAME fallback the removed hand-reader carried, so
    the greeting-of-the-day boundary stays byte-identical. Returns a bare IANA
    name string, never a tzinfo: the caller owns the name→zoneinfo lookup and
    its own UTC fail-safe if the name is unloadable."""
    global _captain_timezone_cache
    if _captain_timezone_cache is not None:
        return _captain_timezone_cache
    tz = default
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
                break
    except Exception:
        tz = default
    _captain_timezone_cache = tz
    return tz


# Cache: shared_env_path is read once per process (same lifecycle as
# captain_name). None ⇒ unresolved — the empty string is a VALID resolved value
# (a generic deployment with no shared credential file), so the sentinel is
# None, never "".
_shared_env_path_cache: "str | None" = None


def shared_env_path(default: str = "") -> str:
    """The filesystem path to the shared credentials ``.env`` file the action
    lane loads MONDAY_API_TOKEN / MONDAY_API_KEY (and friends) from — the
    resolver that lifts the ``~/.screenpipe/pipes/_shared/.env`` credential path
    OUT of the universal-base ``framework`` code (``action_exec._load_shared_env``
    + ``actfirst_canary``'s env-perms check) into instance config, so framework
    carries no launcher's ``.screenpipe`` path (source-adapter boundary §5,
    Tier-2 credential reparent).

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
    ``~/.screenpipe/pipes/retrodiction`` path OUT of the universal-base
    ``framework`` shim into instance config, so framework carries no launcher's
    ``.screenpipe`` path (source-adapter boundary §5, the parallel EVALUATION
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
    """The captain's brain/Obsidian VAULT directory for this deployment — the
    resolver that lifts the vault path OUT of the universal-base ``framework``
    code (the fidelity decision-cell's Decisions corpus dir; on Flavor-A the
    screenpipe brain vault) into instance config, so framework names no
    launcher's vault path — and, crucially, no screenpipe-specific vault env key
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
    that lifts the ``~/.screenpipe/state`` path OUT of the universal-base
    ``framework`` code (the fidelity decision-cache + the autonomy-outcomes
    ledger; the outcome-watchdog's watched brain-pipe dir) into instance config,
    so framework names no launcher's state path (source-adapter boundary §5,
    Tier-2 path reparent).

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


# Cache: product_brain_dir is read once per process (same lifecycle as
# vault_dir). None ⇒ unresolved — the EMPTY string is a VALID resolved value
# (a deployment with no org corpus), so the sentinel is None, never "".
_product_brain_dir_cache: "str | None" = None


def product_brain_dir(default: str = "") -> str:
    """The ORG's product-brain markdown corpus directory — the flavor-B twin of
    ``vault_dir()``. Where the vault is the captain's PERSONAL brain (absent on
    clean-room org boxes, where ``vault_dir()`` fail-closes to ``""`` and the
    lane gathers zero vault sections), the product-brain corpus is the ORG's
    OWN knowledge (architecture, decisions, incidents, deploy notes — the
    plan-B B4.14 corpus), written by officers via normal file writes and
    gathered by ``run_action_lane.gather_signals``'s corpus sections.

    Resolution order: the env override ``CABINET_PRODUCT_BRAIN_DIR`` (an
    explicit per-process override, mirroring ``vault_dir``'s
    ``CABINET_VAULT_DIR``) → the ``product_brain_dir`` key in
    ``instance/config/platform.yml`` (else ``product.yml``) IF the directory it
    names exists — the key generate-instance.py stamps; relative values resolve
    against the repo root, absolute/``~`` values are honored as-is, so a
    captain relocates the corpus by editing config (review fix 2026-07-07: the
    stamped key used to be dead config that nothing read) → ``<repo>/
    product-brain`` IF that directory exists (the corpus ships in-repo, so any
    checkout that carries it resolves it with zero config) → the generic
    ``default`` (``""``). A non-empty value is ``~``-expanded. Every non-env
    arm is existence-gated, so a deployment with NO corpus (or a configured
    path that does not exist) resolves ``""``/the next arm — the caller then
    treats the corpus sections as empty (fail-closed: no corpus ⇒ no
    sections), never crashes, and never scans another launcher's paths."""
    global _product_brain_dir_cache
    if _product_brain_dir_cache is not None:
        return _product_brain_dir_cache
    env_override = (os.environ.get("CABINET_PRODUCT_BRAIN_DIR") or "").strip()
    if env_override:
        _product_brain_dir_cache = os.path.expanduser(env_override)
        return _product_brain_dir_cache
    resolved = default
    try:
        root = _cabinet_root()
        # platform.yml / product.yml key (stamped by generate-instance.py).
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
                val = data.get("product_brain_dir")
                if val is None and isinstance(data.get("product"), dict):
                    val = data["product"].get("product_brain_dir")
                if isinstance(val, str) and val.strip():
                    cand_str = os.path.expanduser(val.strip())
                    cand_path = Path(cand_str)
                    if not cand_path.is_absolute():
                        cand_path = root / cand_str
                    if cand_path.is_dir():
                        _product_brain_dir_cache = str(cand_path)
                        return _product_brain_dir_cache
                    break  # key set but dir absent → fall through (fail-closed)
        except Exception:
            pass
        cand = root / "product-brain"
        if cand.is_dir():
            resolved = str(cand)
    except Exception:
        resolved = default
    _product_brain_dir_cache = os.path.expanduser(resolved) if resolved else resolved
    return _product_brain_dir_cache


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
