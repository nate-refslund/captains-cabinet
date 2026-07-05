"""Posture selection kernel [FI-1] — reads Captain-locked instance/config/posture.yml.

Posture is a *selection dimension* of the ONE authority matrix, never a second
enforcement story: verdict semantics live in the germline floor
(`framework/policies/authority-matrix.yml`); THIS module only answers "which
posture table applies here?" from the Captain-locked ruling file.

Fail-safe polarity (D6): **guardian is the answer to every ambiguity** —
absent, unparseable, schema-invalid (closed keys — anything unknown is
corrupt), deployment mismatch, or not schg-locked all resolve `guardian`,
which is today's exact behavior. Captain signature = filesystem, not crypto
(D5): on the macbook/mac_mini targets the runtime attestation is
`os.lstat().st_flags & stat.SF_IMMUTABLE` (macOS `schg`, root-only to clear;
a symlink is never attestable, and the ruling path itself is
realpath-contained so a link cannot borrow another file's lock); non-Darwin
attests False there. Since AX-4 (axes spec §3) `is_locked` DISPATCHES on the
deployment target: `docker` attests via the `ro_mount` backend (the host's
read-only bind mount, probed in-container), and an unknown target fails
closed to schg semantics.

THREE LEVELS since the axes build (spec 2026-07-05 §1) with a selection
ASYMMETRY: `sovereign` (widening) requires the fully attested ruling;
`earn_up` (narrowing — its table may only narrow vs guardian, validated in
matrix.py) is honored even from a valid-but-UNLOCKED ruling. Narrowing is
fail-safe by construction, so it needs no attestation.

Env may only NARROW: `CABINET_POSTURE=guardian` is the emergency drop-brake
and `CABINET_POSTURE=earn_up` narrows further — both apply as a
min-by-permissiveness CAP (env can never widen an earn_up ruling back to
guardian); `CABINET_POSTURE=sovereign` is IGNORED. A second narrow-only cap
is the `instance/config/posture-narrow` file (single word guardian|earn_up,
deliberately NOT locked — the Captain's binder verb writes it). There is NO
dev/test bypass of the lock attestation (the `CABINET_POSTURE_UNLOCKED_OK`
override was killed — REDTEAM/ALIGNMENT critical); tests inject
`is_locked_fn` and point roots at tmp trees they own.

Purity mirrors `framework.authority.lane` [FIX-4] + the action_exec loader
semantics: named env reads only (CABINET_POSTURE / CABINET_ID / CABINET_ROOT),
`yaml.safe_load` on one fixed root-relative path, zero policy_engine imports,
no subprocess. A corrupt/unlocked ruling files a deduped need (best-effort,
lazy import, gated by `needs.needs_enabled()` so the guardian default world
stays bit-identical).
"""
from __future__ import annotations

import errno
import os
import re
import stat as stat_mod
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

EARN_UP = "earn_up"
GUARDIAN = "guardian"
SOVEREIGN = "sovereign"
POSTURES = frozenset({EARN_UP, GUARDIAN, SOVEREIGN})
FLAVORS = frozenset({"org", "personal"})
DEPLOYMENT_TARGETS = frozenset({"macbook", "mac_mini", "docker"})

# Posture-level permissiveness for the narrow-only comparisons (min = the
# narrower). Ordered by the STATIC tables: earn_up (all propose_only below the
# ceilings) < guardian (trust-first rows act day-one) < sovereign. Runtime
# ladder lifts (AX-2) never move a posture's rank.
POSTURE_PERMISSIVENESS = {EARN_UP: 0, GUARDIAN: 1, SOVEREIGN: 2}

# The narrow-only vocab: what env/`posture-narrow` may cap to. Sovereign is
# deliberately absent — no runtime surface may WIDEN.
_NARROW_CAPS = frozenset({GUARDIAN, EARN_UP})

# FI-1 / FI-5 defaults. Guardian's step budget is FORCED, never config-tunable.
DEFAULT_HARD_MULTIPLIER = 10
GUARDIAN_MAX_AUTO_EXEC_STEPS = 2
DEFAULT_SOVEREIGN_MAX_AUTO_EXEC_STEPS = 5

# Closed key set — an unknown key is CORRUPT, not ignored (fail toward guardian).
# `never_grant` + `deployment_target` are OPTIONAL (axes build): old files
# without them stay valid; AX-3 (grants loader) and AX-4 (attestation
# backends) consume them off the ruling object.
_POSTURE_KEYS = {
    "version", "status", "ruled_at", "basis", "deployment",
    "flavor", "posture", "lanes", "caps", "max_auto_exec_steps",
    "never_grant", "deployment_target",
}
_POSTURE_REQUIRED = (
    "version", "status", "ruled_at", "basis", "deployment", "flavor", "posture",
)
_CAPS_KEYS = {"hard_multiplier"}


# ---------------------------------------------------------------------------
# Roots + paths (mirrors matrix.matrix_path: arg → CABINET_ROOT env → repo root)
# ---------------------------------------------------------------------------

def cabinet_id() -> str:
    """This deployment's id — CABINET_ID env, default 'main' (mission-compiler
    convention). posture.yml only applies when its `deployment` equals this."""
    return os.environ.get("CABINET_ID", "main")


def cabinet_root(root: str | Path | None = None) -> Path:
    """Resolve the cabinet root: explicit arg → CABINET_ROOT env → repo root.
    No interpolation from untrusted input — fixed relative suffixes only."""
    if root is not None:
        return Path(root)
    return Path(os.environ.get("CABINET_ROOT") or str(_FRAMEWORK_ROOT))


def posture_path(root: str | Path | None = None) -> Path:
    """instance/config/posture.yml under the cabinet root (germline + schg)."""
    return cabinet_root(root) / "instance" / "config" / "posture.yml"


def narrow_cap_path(root: str | Path | None = None) -> Path:
    """instance/config/posture-narrow — the narrow-only runtime cap file.
    Deliberately NOT in the lock set: it can only narrow, so tampering is
    fail-safe; the Captain's binder verb writes it."""
    return cabinet_root(root) / "instance" / "config" / "posture-narrow"


def posture_config_present(root: str | Path | None = None) -> bool:
    """True iff a posture.yml exists at all (even an invalid one). The acting
    lane keys its legacy-vs-matrix-wire branch on THIS, so a corrupt file still
    routes through the matrix wire — where resolve_posture() says guardian and
    guardian-table routing equals today's mechanical outcome (P4)."""
    try:
        return posture_path(root).exists()
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Attestation backends (D5 — signing is filesystem, not crypto; AX-4 — the
# deployment target selects WHICH filesystem mechanism carries the signature)
# ---------------------------------------------------------------------------

# target → backend NAME (public data — axes are data, never code branches).
# schg is macOS-only; the docker target's boundary is the HOST's read-only
# bind mounts. An unknown target dispatches schg, the fail-closed backend
# (it attests False anywhere the Captain could not have chflags'd the file).
ATTESTATION_BACKEND_BY_TARGET = {
    "macbook": "schg",
    "mac_mini": "schg",
    "docker": "ro_mount",
}

# /proc/mounts (module-level so tests can re-point it, like _DOCKERENV).
_PROC_MOUNTS = Path("/proc/mounts")

# Open-append probe errnos that mean "the filesystem refused the write"
# (spec §3). Anything else — ENOENT, EISDIR, ELOOP, ENXIO, EPERM, … — is
# ambiguity, and ANY ambiguity ⇒ not attested.
_RO_PROBE_ERRNOS = (errno.EROFS, errno.EACCES)


def _is_locked_schg(path: str | Path) -> bool:
    """The macOS `schg` backend (macbook / mac_mini) — the pre-axes attestation
    byte-for-byte: `os.lstat().st_flags & stat.SF_IMMUTABLE` per FI-1 — lstat,
    never following a symlink: a link could otherwise borrow the attestation
    of any schg-locked file it points at (forge vector; axes-build Corridor
    constraint). A symlink is never attestable. Non-Darwin platforms have no
    schg ⇒ False (the ruling cannot be attested there). Stat failure ⇒ False.
    Never raises.
    """
    if sys.platform != "darwin":
        return False
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat_mod.S_ISLNK(st.st_mode):
        return False
    return bool(getattr(st, "st_flags", 0) & stat_mod.SF_IMMUTABLE)


def _unescape_mountpoint(field: str) -> str:
    # /proc/mounts octal-escapes space/tab/newline/backslash in mountpoint
    # fields (\040 \011 \012 \134).
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), field)


def _mount_is_ro(real_path: str) -> bool:
    """True iff /proc/mounts is present AND the longest-prefix mount containing
    `real_path` carries the `ro` option (exact match included — a docker
    single-file bind mount lists the FILE itself as the mountpoint). An
    absent/unreadable /proc/mounts is AMBIGUITY ⇒ False: requiring the mount
    table, not just an EACCES probe, is what stops a same-uid chmod-444 file
    from self-attesting off-Linux. Never raises."""
    try:
        lines = _PROC_MOUNTS.read_text().splitlines()
    except OSError:
        return False
    best = None  # (mountpoint, options) of the longest containing mount
    for line in lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        mnt = _unescape_mountpoint(parts[1])
        contains = real_path == mnt or \
            real_path.startswith(mnt.rstrip("/") + "/")
        if contains and (best is None or len(mnt) > len(best[0])):
            best = (mnt, parts[3])
    if best is None:
        return False
    return "ro" in best[1].split(",")


def _is_locked_ro_mount(path: str | Path) -> bool:
    """The docker `ro_mount` backend: attested iff the file physically cannot
    be written INSIDE the container because the HOST bind-mounted it read-only
    (spec §3 — lock/unlock ritual happens host-side; the container cannot
    remount at any privilege). Three fail-closed layers, ANY ambiguity ⇒
    False:

      1. symlink/traversal containment — lstat refuses a link; the probe runs
         on `os.path.realpath()`, regular files only;
      2. O_NOFOLLOW|O_NONBLOCK open-append probe expecting EROFS/EACCES (an
         open that SUCCEEDS proves writability; nothing is ever written);
      3. /proc/mounts must be present and show the containing mount `ro`.

    Never raises.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat_mod.S_ISLNK(st.st_mode):
        return False
    try:
        real = os.path.realpath(str(path))
        if not stat_mod.S_ISREG(os.stat(real).st_mode):
            return False
    except OSError:
        return False
    flags = (
        os.O_WRONLY | os.O_APPEND
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        fd = os.open(real, flags)
    except OSError as exc:
        if exc.errno not in _RO_PROBE_ERRNOS:
            return False
    else:
        os.close(fd)  # opened writable ⇒ demonstrably NOT read-only
        return False
    return _mount_is_ro(real)


# backend name → callable (private; tests re-point entries via setitem).
_BACKEND_FNS = {"schg": _is_locked_schg, "ro_mount": _is_locked_ro_mount}


def _declared_target(path: str | Path) -> Optional[str]:
    """`deployment_target` as declared by the YAML file at `path` itself —
    the ruling names the backend that attests it (gating this read on
    attestation would be circular). Deliberately unvalidated: a forged value
    can only select a backend that fails closed off its real platform (a
    docker claim finds no ro /proc/mounts entry on a Mac; a macbook claim
    finds no schg in a container). None on absent / unreadable / non-mapping
    / unknown value. Never raises."""
    try:
        import yaml  # deferred — same as the ruling reader
        data = yaml.safe_load(Path(path).read_text())
    except Exception:
        return None
    if isinstance(data, dict) and \
            data.get("deployment_target") in DEPLOYMENT_TARGETS:
        return data["deployment_target"]
    return None


def is_locked(path: str | Path, target: Optional[str] = None) -> bool:
    """True iff `path` is Captain-locked under this deployment's attestation
    backend (AX-4): macbook/mac_mini ⇒ `schg` (macOS system-immutable flag,
    root-only to clear); docker ⇒ `ro_mount` (host-side read-only bind
    mount). The target resolves: explicit arg → the deployment_target the
    file itself declares → environment inference (/.dockerenv ⇒ docker, else
    macbook); an UNKNOWN target dispatches schg — fail-closed. One-arg calls
    keep the pre-axes contract everywhere no deployment_target appears.
    Never raises.
    """
    if target is None:
        target = _declared_target(path) or infer_deployment_target()
    backend = ATTESTATION_BACKEND_BY_TARGET.get(target, "schg")
    return _BACKEND_FNS[backend](path)


def _is_real_ruling_path(path: Path, root: str | Path | None) -> bool:
    """Containment probe: the ruling must BE the real
    `<root>/instance/config/posture.yml` — no symlink or traversal anywhere in
    the instance/config suffix (a link in the root prefix itself, e.g. a
    symlinked /tmp, stays legitimate because the expected path resolves the
    root first). Failure is never attestable ⇒ callers refuse fail-closed."""
    try:
        expected = os.path.join(
            os.path.realpath(str(cabinet_root(root))),
            "instance", "config", "posture.yml",
        )
        return os.path.realpath(str(path)) == expected
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Schema validation (closed keys, closed vocab — corrupt ⇒ guardian)
# ---------------------------------------------------------------------------

def _is_timestampish(v: Any) -> bool:
    # yaml.safe_load parses `2026-07-05T00:00:00Z` into datetime already;
    # a quoted ISO string is equally acceptable.
    if isinstance(v, (datetime, date)):
        return True
    return isinstance(v, str) and bool(v.strip())


def validation_error(data: Any) -> str | None:
    """First schema violation as a string, or None when valid.

    Closed-key + closed-vocab: any unknown key, missing required key, or
    mistyped value makes the ruling CORRUPT (⇒ guardian + deduped need),
    never best-effort-parsed.
    """
    if not isinstance(data, dict):
        return "posture.yml is not a mapping"
    extra = set(data) - _POSTURE_KEYS
    if extra:
        return f"unknown keys: {sorted(extra)}"
    for k in _POSTURE_REQUIRED:
        if k not in data:
            return f"missing required key: {k}"
    if data["version"] != 1 or isinstance(data["version"], bool):
        return "version must be the integer 1"
    if data["status"] != "ruled":
        return "status must be 'ruled'"
    if not _is_timestampish(data["ruled_at"]):
        return "ruled_at must be an ISO-8601 timestamp"
    for k in ("basis", "deployment"):
        if not isinstance(data[k], str) or not data[k].strip():
            return f"{k} must be a non-empty string"
    if data["flavor"] not in FLAVORS:
        return f"flavor must be one of {sorted(FLAVORS)}"
    if data["posture"] not in POSTURES:
        return f"posture must be one of {sorted(POSTURES)}"
    lanes = data.get("lanes")
    if lanes is not None:
        if not isinstance(lanes, dict):
            return "lanes must be a mapping of lane -> posture"
        for lname, lposture in lanes.items():
            if not isinstance(lname, str) or not lname.strip():
                return "lanes keys must be non-empty lane slugs"
            if lposture not in POSTURES:
                return f"lanes.{lname} must be one of {sorted(POSTURES)}"
    caps = data.get("caps")
    if caps is not None:
        if not isinstance(caps, dict):
            return "caps must be a mapping"
        extra = set(caps) - _CAPS_KEYS
        if extra:
            return f"caps: unknown keys: {sorted(extra)}"
        hm = caps.get("hard_multiplier")
        if hm is not None and (
            not isinstance(hm, int) or isinstance(hm, bool) or hm < 1
        ):
            return "caps.hard_multiplier must be a positive integer"
    maes = data.get("max_auto_exec_steps")
    if maes is not None and (
        not isinstance(maes, int) or isinstance(maes, bool) or maes < 1
    ):
        return "max_auto_exec_steps must be a positive integer"
    ng = data.get("never_grant")
    if ng is not None:
        if not isinstance(ng, list):
            return "never_grant must be a list of risk classes"
        try:
            # Deferred + fail-closed: only rulings that CARRY never_grant pay
            # this import, so old files stay valid even if matrix breaks; an
            # unimportable vocabulary makes the key unvalidatable ⇒ corrupt.
            from framework.authority.matrix import RISK_CLASSES
        except Exception:
            return "never_grant present but the risk-class vocabulary is unavailable"
        for cls in ng:
            if not isinstance(cls, str) or cls not in RISK_CLASSES:
                # Closed vocab on purpose: a typo'd class would silently
                # protect NOTHING (fail-open) if best-effort-accepted.
                return (
                    f"never_grant entries must be matrix risk classes "
                    f"({sorted(RISK_CLASSES)}); got {cls!r}"
                )
    dt = data.get("deployment_target")
    if dt is not None and dt not in DEPLOYMENT_TARGETS:
        return f"deployment_target must be one of {sorted(DEPLOYMENT_TARGETS)}"
    return None


# ---------------------------------------------------------------------------
# Load + resolve
# ---------------------------------------------------------------------------

def _file_config_need(root: str | Path | None, why: str) -> None:
    """Deduped need on a corrupt/unlocked ruling — best-effort, NEVER raises.
    Lazy import (needs lazily reads posture back with file_needs=False, so
    there is no recursion). `action_type` is the dedup subject discriminator
    so posture- and grants-config needs keep distinct fingerprints."""
    try:
        from framework.authority import needs
        needs.file_need(
            "decision",
            action_type="posture_config",
            why=why,
            unblocks="sovereign posture resolution (guardian until repaired)",
            filed_by="posture.loader",
            root=root,
        )
    except Exception:
        pass


def _read_ruling(
    root: str | Path | None = None,
    *,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
    file_needs: bool = True,
) -> "tuple[dict[str, Any] | None, bool]":
    """(data, attested) — the axes-aware ruling read.

    `data` is the schema-valid, deployment-matched ruling even when only the
    LOCK attestation fails (attested=False) — resolve_posture honors the
    narrowing parts of an unattested ruling (earn_up), and the lock-free
    accessors (never_grant/deployment_target) read it too. (None, False) on
    absent / symlinked / unparseable / corrupt / mismatched.

    Evaluation order (FI-1): present ∧ real-path ∧ parseable ∧ schema-valid ∧
    deployment==CABINET_ID, then the schg attestation. Absent and
    deployment-mismatch are SILENT (the legitimate guardian-default /
    another-deployment's-file states); symlinked/unparseable/corrupt file a
    deduped need, and so does valid-but-unlocked UNLESS the ruling is pure
    earn_up (honored without attestation — nothing to repair). `file_needs=
    False` is the internal no-side-effect read (needs_enabled uses it to
    break the resolve→file_need→needs_enabled cycle).
    """
    path = posture_path(root)
    try:
        if not path.exists():
            return None, False
    except OSError:
        return None, False
    if not _is_real_ruling_path(path, root):
        if file_needs:
            _file_config_need(
                root,
                "posture.yml is not attestable: the path is not the real "
                "instance/config/posture.yml (symlink or traversal) — "
                "resolving guardian",
            )
        return None, False
    try:
        import yaml  # deferred — available in the cabinet runtime + CI
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        if file_needs:
            _file_config_need(root, f"posture.yml is unparseable: {exc}")
        return None, False
    err = validation_error(data)
    if err:
        if file_needs:
            _file_config_need(root, f"posture.yml is corrupt: {err}")
        return None, False
    if str(data["deployment"]) != cabinet_id():
        # Another deployment's ruling synced onto this machine — treated
        # absent (⇒ guardian), not corrupt: normal in a multi-deployment repo.
        return None, False
    if (is_locked_fn or is_locked)(path):
        return data, True
    named = {data["posture"], *(data.get("lanes") or {}).values()}
    if file_needs and named != {EARN_UP}:
        _file_config_need(
            root,
            "posture.yml exists but is not schg-locked — ruling not "
            "attested; resolving guardian until the Captain locks it "
            "(sudo chflags schg)",
        )
    return data, False


def load_posture_config(
    root: str | Path | None = None,
    *,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
    file_needs: bool = True,
) -> dict[str, Any] | None:
    """Load + validate posture.yml; None on every not-attestable condition
    (the pre-axes contract, unchanged: attested rulings only — earn_up's
    unattested narrowing is resolve_posture's business, never this reader's).
    """
    data, attested = _read_ruling(
        root, is_locked_fn=is_locked_fn, file_needs=file_needs
    )
    return data if attested else None


def _narrowest(*postures: str) -> str:
    return min(postures, key=lambda p: POSTURE_PERMISSIVENESS[p])


def narrow_cap(root: str | Path | None = None) -> str | None:
    """The `instance/config/posture-narrow` cap: None (absent = no cap) or a
    member of {guardian, earn_up}. Present-but-unrecognized content fails
    CLOSED to `earn_up` — the most restrictive cap: a corrupted narrowing
    request must never fail open to a wider posture than the Captain may
    have asked for. Never raises."""
    path = narrow_cap_path(root)
    try:
        if not path.exists():
            return None
        word = path.read_text().strip()
    except OSError:
        return EARN_UP
    return word if word in _NARROW_CAPS else EARN_UP


def resolve_posture(
    lane: str | None = None,
    *,
    root: str | Path | None = None,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
    file_needs: bool = True,
) -> str:
    """The posture this deployment (optionally: this lane) runs under.

    Three levels with a selection ASYMMETRY (axes spec §1): `sovereign` IFF
    the ruling file is present ∧ schema-valid ∧ deployment==CABINET_ID ∧
    schg-locked AND the effective (lane-overridden) posture says so;
    `earn_up` is a NARROWING choice honored even from a valid-but-unlocked
    ruling (an unattested ruling is capped at guardian, so only its earn_up
    answer survives). Everything else is `guardian`.

    Two narrow-only runtime caps then apply by min-permissiveness, in order:
    `CABINET_POSTURE` ∈ {guardian, earn_up} (=sovereign or garbage ignored —
    env can only narrow, and can never widen an earn_up ruling to guardian),
    then the `posture-narrow` file. The legacy env=guardian drop-brake never
    read the ruling at all, so its needs side-effects stay suppressed.
    """
    env_cap = os.environ.get("CABINET_POSTURE")
    if env_cap not in _NARROW_CAPS:
        env_cap = None
    cfg, attested = _read_ruling(
        root,
        is_locked_fn=is_locked_fn,
        file_needs=file_needs and env_cap != GUARDIAN,
    )
    resolved = GUARDIAN
    if cfg is not None:
        lanes = cfg.get("lanes") or {}
        effective = lanes[lane] if (lane is not None and lane in lanes) \
            else cfg["posture"]
        resolved = effective if attested else _narrowest(effective, GUARDIAN)
    if env_cap is not None:
        resolved = _narrowest(resolved, env_cap)
    cap = narrow_cap(root)
    if cap is not None:
        resolved = _narrowest(resolved, cap)
    return resolved


# ---------------------------------------------------------------------------
# Axes keys (AX-3 / AX-4 consumers: grants loader + attestation backends)
# ---------------------------------------------------------------------------

def _read_unattested(root: str | Path | None = None) -> dict[str, Any] | None:
    """Quiet, lock-free ruling read for the NARROWING/topology keys: a
    schema-valid, deployment-matched, real-path ruling regardless of the schg
    attestation; None otherwise. No needs are ever filed from this path."""
    data, _attested = _read_ruling(
        root, is_locked_fn=lambda p: True, file_needs=False
    )
    return data


def never_grant_classes(root: str | Path | None = None) -> frozenset[str]:
    """The Captain's `never_grant` risk classes (default: empty = all six
    ceiling classes grantable in sovereign). Honored even from an unattested
    ruling — dropping grant classes is a pure narrowing. A corrupt ruling
    reads as absent HERE (⇒ empty), which stays fail-closed because the same
    corruption already resolves the posture to guardian, where no standing
    grant is reachable (and grants.py additionally narrows a corrupt ruling
    to ALL ceiling classes on its own side)."""
    cfg = _read_unattested(root)
    if cfg is None:
        return frozenset()
    return frozenset(cfg.get("never_grant") or [])


# The docker topology sentinel (module-level so tests can re-point it).
_DOCKERENV = Path("/.dockerenv")


def infer_deployment_target() -> str:
    """Deployment target when the ruling doesn't say: `/.dockerenv` exists ⇒
    docker, else macbook (Darwin's answer — and the fail-closed answer on any
    unknown platform, because the macbook/schg attestation backend attests
    False off-Darwin ⇒ guardian)."""
    try:
        if _DOCKERENV.exists():
            return "docker"
    except OSError:
        pass
    return "macbook"


def deployment_target(root: str | Path | None = None) -> str:
    """This deployment's target axis value (macbook | mac_mini | docker).

    Read from a schema-valid, deployment-matched ruling WITHOUT requiring the
    lock attestation — the target selects WHICH attestation backend applies
    (AX-4), so gating it on attestation would be circular. Safe unattested: a
    forged target can only select a backend that fails closed off its real
    platform (schg attests False off-Darwin; ro_mount finds no read-only
    /proc mount on a Mac). Absent file/key ⇒ inferred."""
    cfg = _read_unattested(root)
    if cfg is not None:
        target = cfg.get("deployment_target")
        if target in DEPLOYMENT_TARGETS:
            return target
    return infer_deployment_target()


# ---------------------------------------------------------------------------
# Tunables (FI-1 / FI-5 consumers: acting lane + brakes)
# ---------------------------------------------------------------------------

def hard_multiplier(
    root: str | Path | None = None,
    *,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
) -> int:
    """`caps.hard_multiplier` from the attested ruling, default 10 (FI-5):
    the runaway mechanical hard-stop is per-kind/day cap × this."""
    cfg = load_posture_config(root, is_locked_fn=is_locked_fn, file_needs=False)
    if cfg is None:
        return DEFAULT_HARD_MULTIPLIER
    return (cfg.get("caps") or {}).get("hard_multiplier") or DEFAULT_HARD_MULTIPLIER


def max_auto_steps(
    posture: str,
    root: str | Path | None = None,
    *,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
) -> int:
    """MAX_AUTO_EXEC_STEPS for a posture: every non-sovereign posture
    (guardian, earn_up) is FORCED 2 (FI-1 — `max_auto_exec_steps` is
    sovereign-only); sovereign reads the attested ruling (default 5). A
    sovereign claim without an attestable ruling narrows back to the
    guardian budget."""
    if posture != SOVEREIGN:
        return GUARDIAN_MAX_AUTO_EXEC_STEPS
    cfg = load_posture_config(root, is_locked_fn=is_locked_fn, file_needs=False)
    if cfg is None:
        return GUARDIAN_MAX_AUTO_EXEC_STEPS
    return cfg.get("max_auto_exec_steps") or DEFAULT_SOVEREIGN_MAX_AUTO_EXEC_STEPS
