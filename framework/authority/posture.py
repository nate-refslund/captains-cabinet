"""Posture selection kernel [FI-1] — reads Captain-locked instance/config/posture.yml.

Posture is a *selection dimension* of the ONE authority matrix, never a second
enforcement story: verdict semantics live in the germline floor
(`framework/policies/authority-matrix.yml`); THIS module only answers "which
posture table applies here?" from the Captain-locked ruling file.

Fail-safe polarity (D6): **guardian is the answer to every ambiguity** —
absent, unparseable, schema-invalid (closed keys — anything unknown is
corrupt), deployment mismatch, or not schg-locked all resolve `guardian`,
which is today's exact behavior. Captain signature = filesystem, not crypto
(D5): the runtime attestation is `os.stat().st_flags & stat.SF_IMMUTABLE`
(macOS `schg`, root-only to clear); non-Darwin attests False.

Env may only NARROW: `CABINET_POSTURE=guardian` is the emergency drop-brake
and wins over any config; `CABINET_POSTURE=sovereign` is IGNORED — env can
never widen. There is NO dev/test bypass of the lock attestation (the
`CABINET_POSTURE_UNLOCKED_OK` override was killed — REDTEAM/ALIGNMENT
critical); tests inject `is_locked_fn` and point roots at tmp trees they own.

Purity mirrors `framework.authority.lane` [FIX-4] + the action_exec loader
semantics: named env reads only (CABINET_POSTURE / CABINET_ID / CABINET_ROOT),
`yaml.safe_load` on one fixed root-relative path, zero policy_engine imports,
no subprocess. A corrupt/unlocked ruling files a deduped need (best-effort,
lazy import, gated by `needs.needs_enabled()` so the guardian default world
stays bit-identical).
"""
from __future__ import annotations

import os
import stat as stat_mod
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

GUARDIAN = "guardian"
SOVEREIGN = "sovereign"
POSTURES = frozenset({GUARDIAN, SOVEREIGN})
FLAVORS = frozenset({"org", "personal"})

# FI-1 / FI-5 defaults. Guardian's step budget is FORCED, never config-tunable.
DEFAULT_HARD_MULTIPLIER = 10
GUARDIAN_MAX_AUTO_EXEC_STEPS = 2
DEFAULT_SOVEREIGN_MAX_AUTO_EXEC_STEPS = 5

# Closed key set — an unknown key is CORRUPT, not ignored (fail toward guardian).
_POSTURE_KEYS = {
    "version", "status", "ruled_at", "basis", "deployment",
    "flavor", "posture", "lanes", "caps", "max_auto_exec_steps",
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
# schg attestation (D5 — signing is filesystem, not crypto)
# ---------------------------------------------------------------------------

def is_locked(path: str | Path) -> bool:
    """True iff `path` carries the macOS system-immutable flag (`schg`).

    `os.stat().st_flags & stat.SF_IMMUTABLE` per FI-1. Non-Darwin platforms
    have no schg ⇒ False (the ruling cannot be attested there). Stat failure
    ⇒ False. Never raises.
    """
    if sys.platform != "darwin":
        return False
    try:
        st = os.stat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_flags", 0) & stat_mod.SF_IMMUTABLE)


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


def load_posture_config(
    root: str | Path | None = None,
    *,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
    file_needs: bool = True,
) -> dict[str, Any] | None:
    """Load + validate posture.yml; None on every not-attestable condition.

    Evaluation order (FI-1): present ∧ parseable ∧ schema-valid ∧
    deployment==CABINET_ID ∧ schg-locked. Absent and deployment-mismatch are
    SILENT (the legitimate guardian-default / another-deployment's-file
    states); unparseable/corrupt/unlocked file a deduped need. `file_needs=False`
    is the internal no-side-effect read (needs_enabled uses it to break the
    resolve→file_need→needs_enabled cycle).
    """
    path = posture_path(root)
    try:
        if not path.exists():
            return None
    except OSError:
        return None
    try:
        import yaml  # deferred — available in the cabinet runtime + CI
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        if file_needs:
            _file_config_need(root, f"posture.yml is unparseable: {exc}")
        return None
    err = validation_error(data)
    if err:
        if file_needs:
            _file_config_need(root, f"posture.yml is corrupt: {err}")
        return None
    if str(data["deployment"]) != cabinet_id():
        # Another deployment's ruling synced onto this machine — treated
        # absent (⇒ guardian), not corrupt: normal in a multi-deployment repo.
        return None
    if not (is_locked_fn or is_locked)(path):
        if file_needs:
            _file_config_need(
                root,
                "posture.yml exists but is not schg-locked — ruling not "
                "attested; resolving guardian until the Captain locks it "
                "(sudo chflags schg)",
            )
        return None
    return data


def resolve_posture(
    lane: str | None = None,
    *,
    root: str | Path | None = None,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
    file_needs: bool = True,
) -> str:
    """The posture this deployment (optionally: this lane) runs under.

    Returns `sovereign` IFF the ruling file is present ∧ schema-valid ∧
    deployment==CABINET_ID ∧ schg-locked AND the effective (lane-overridden)
    posture says so. Everything else is `guardian`. `CABINET_POSTURE=guardian`
    narrows unconditionally; `CABINET_POSTURE=sovereign` (or any other value)
    is ignored — env can only narrow, never widen.
    """
    if os.environ.get("CABINET_POSTURE") == GUARDIAN:
        return GUARDIAN
    cfg = load_posture_config(root, is_locked_fn=is_locked_fn, file_needs=file_needs)
    if cfg is None:
        return GUARDIAN
    lanes = cfg.get("lanes") or {}
    if lane is not None and lane in lanes:
        return lanes[lane]
    return cfg["posture"]


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
    """MAX_AUTO_EXEC_STEPS for a posture: guardian is FORCED 2 (FI-1 —
    `max_auto_exec_steps` is sovereign-only); sovereign reads the attested
    ruling (default 5). A sovereign claim without an attestable ruling
    narrows back to the guardian budget."""
    if posture != SOVEREIGN:
        return GUARDIAN_MAX_AUTO_EXEC_STEPS
    cfg = load_posture_config(root, is_locked_fn=is_locked_fn, file_needs=False)
    if cfg is None:
        return GUARDIAN_MAX_AUTO_EXEC_STEPS
    return cfg.get("max_auto_exec_steps") or DEFAULT_SOVEREIGN_MAX_AUTO_EXEC_STEPS
