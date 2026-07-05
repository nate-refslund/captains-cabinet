"""Standing-grants kernel [FI-2] — ceilings-only, fail-closed, Captain-locked.

A standing grant is the ONLY way a hard-ceiling row (`external_comms`,
`deploy_prod`, `spend`, `secrets`, `network_write`, `credentials_grant`)
resolves to an attributed allow in the sovereign posture (D2) — never an
unconditional `auto`, any posture. Grants live in Captain-locked
`instance/config/standing-grants.yml` and change ONLY via `grant-apply.sh`
in an unlock window (D7 — no runtime writer exists here on purpose).

Fail-safe polarity (D6): absent / unparseable / NOT-schg-locked ⇒ `[]` +
deduped need. Per-row validation line-drops anything malformed (+ need) and
keeps the rest. **never_grant (Captain ruling 2026-07-05 — external-comms
grantability is INSTANCE-scoped, never flavor-structural):** the old
`flavor=personal ⇒ external_comms refused` gate is deleted; instead, rows
whose risk_class ∈ the posture.yml `never_grant:` list are dropped
fail-closed at load + ONE deduped kind=decision need per class (asking for
a never-granted class is noise — never a recurring grant-request need).
The Captain's personal instance keeps its exact prior behavior via config
(`never_grant: [external_comms]`, ACT-AND-DRAFT); the framework stops
encoding one captain's policy.

`check()` enforces ALL of (FI-2): deployment==CABINET_ID ∧ ceiling class ∧
action_type ∈ action_types ∧ lane match ∧ not expired (≤90d horizon enforced
at load) ∧ not revoked (file flag OR Redis tombstone
`cabinet:grant:revoked:<id>` — **Redis unreachable ⇒ treated revoked**) ∧
rate not exhausted (`cabinet:grant:count:<id>:<date>` — **unreadable ⇒ not
granted**) ∧ no active Captain veto ∧ the class **hard-scope predicate**
(recipient∈allowlist / amount≤max_eur_per_day / vendor∈allowlist — a missing
context field FAILS the predicate: no allow without executor-supplied scope
data, per the REDTEAM never-allow-without-enforcing-executor rule).

v1 dormancy: no ceiling executor stamps ceiling action_types yet, so this
path is INERT at the acting lane until a scope-enforcing executor lands with
its own tests. Redis default backend mirrors `actfirst_canary` (subprocess
redis-cli, injectable) but RAISES on failure so "unreachable" is
distinguishable from "key absent" — unreachable must narrow, never pass.
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

from framework.authority.posture import (  # noqa: E402
    cabinet_id, cabinet_root, is_locked, load_posture_config, posture_path,
)

# The six hard-ceiling risk classes — grants are CEILINGS-ONLY. Static so the
# kernel stays deterministic when the matrix is unreadable; pinned to the
# shipped floor's `hard_ceiling` list by test_grants (drift = test failure).
CEILING_RISK_CLASSES = frozenset({
    "external_comms", "deploy_prod", "spend",
    "secrets", "network_write", "credentials_grant",
})

# ≤90d expiry horizon at grant time (FI-2; renewal auto-files a need).
MAX_EXPIRY_HORIZON_DAYS = 90

_TOMBSTONE_PREFIX = "cabinet:grant:revoked:"
_COUNT_PREFIX = "cabinet:grant:count:"
_COUNT_TTL_S = 172800  # day-keyed counter; TTL just reaps old keys

# Closed per-row shape — every key required, anything extra is a line-drop.
_GRANT_KEYS = {
    "id", "deployment", "risk_class", "action_types", "lanes", "scope",
    "rate", "expires", "granted_by", "granted_at", "basis", "revoked",
}
_SCOPE_KEYS = {"recipient_allowlist", "max_eur_per_day", "vendor_allowlist"}
_RATE_KEYS = {"max_per_day"}


# ---------------------------------------------------------------------------
# Paths + time
# ---------------------------------------------------------------------------

def grants_path(root: str | Path | None = None) -> Path:
    """instance/config/standing-grants.yml under the cabinet root."""
    return cabinet_root(root) / "instance" / "config" / "standing-grants.yml"


def _to_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        # A bare date expires at ITS midnight — the narrower reading.
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _now(now: Any = None) -> datetime:
    return _to_dt(now) or datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Redis (injected; subprocess default RAISES on unreachable — fail-closed)
# ---------------------------------------------------------------------------

def _redis(*args: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    proc = subprocess.run(["redis-cli", "-h", host, *args],
                          capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        raise RuntimeError(
            f"redis-cli {args[0]} failed: {proc.stderr.strip() or proc.returncode}")
    out = proc.stdout.strip()
    return "" if out in ("", "(nil)") else out


def _default_redis_get(key: str) -> str:
    return _redis("GET", key)


def _default_redis_incr(key: str) -> str:
    return _redis("INCR", key)


def _default_redis_expire(key: str, ttl_s: int) -> None:
    _redis("EXPIRE", key, str(int(ttl_s)))


def _default_is_vetoed(action_type: str | None) -> bool:
    # Lazy — the veto registry lives in the frontdoor package; an import or
    # read failure propagates and the caller treats it as vetoed (fail-closed).
    from framework.frontdoor.veto_registry import is_vetoed
    return is_vetoed(action_type)


# ---------------------------------------------------------------------------
# Needs filing (best-effort, deduped, gated by needs_enabled inside needs)
# ---------------------------------------------------------------------------

def _file_need(root, why: str, *, risk_class=None, action_type="standing_grants_config",
               filed_by="grants.loader",
               unblocks="standing-grant resolution (empty grants until repaired)") -> None:
    try:
        from framework.authority import needs
        needs.file_need(
            "decision",
            risk_class=risk_class,
            action_type=action_type,
            why=why,
            unblocks=unblocks,
            filed_by=filed_by,
            root=root,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# never_grant — instance-scoped class refusal (Captain ruling 2026-07-05)
# ---------------------------------------------------------------------------

def _parse_never_grant(raw: Any) -> frozenset[str] | None:
    """Absent key ⇒ empty set; list of non-empty strings ⇒ that set;
    anything else ⇒ None (malformed — the caller narrows to ALL ceilings)."""
    if raw is None:
        return frozenset()
    if isinstance(raw, list) and all(
            isinstance(x, str) and x.strip() for x in raw):
        return frozenset(x.strip() for x in raw)
    return None


def _never_grant_classes(
    root: str | Path | None = None,
    *,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
) -> frozenset[str]:
    """The Captain's `never_grant` risk-class set from posture.yml.

    Fail-closed shape (constraint: ambiguity narrows, never widens):
    - absent file ⇒ empty set — the documented default (all six ceiling
      classes grantable; the grants file keeps its OWN schg attestation);
    - attested valid ruling ⇒ its list;
    - present-but-unattested/corrupt ruling ⇒ never_grant is still honored
      from a raw parse — a narrowing key is fail-safe even unsigned (the
      CABINET_POSTURE narrow-only doctrine). Tampering cannot widen: the
      maximum reachable surface equals the no-file default;
    - unparseable file / non-mapping / malformed never_grant value ⇒ ALL
      ceiling classes (grants are ceilings-only, so this drops every row).

    SEAM (AX-1, same wave): once the posture schema grows the optional
    `never_grant` key, the attested-ruling read below returns it directly;
    the raw-parse fallback keeps this correct while that lands (pre-AX-1 a
    ruling carrying never_grant is an unknown key ⇒ corrupt ⇒ None from
    load_posture_config).
    """
    cfg = load_posture_config(root, is_locked_fn=is_locked_fn,
                              file_needs=False)
    if cfg is not None:
        parsed = _parse_never_grant(cfg.get("never_grant"))
        return CEILING_RISK_CLASSES if parsed is None else parsed
    path = posture_path(root)
    try:
        if not path.exists():
            return frozenset()
    except OSError:
        return CEILING_RISK_CLASSES  # cannot even probe — never widen
    try:
        import yaml  # deferred — available in the cabinet runtime + CI
        data = yaml.safe_load(path.read_text())
    except Exception:
        return CEILING_RISK_CLASSES  # ruling exists but is unreadable
    if not isinstance(data, dict):
        return CEILING_RISK_CLASSES
    parsed = _parse_never_grant(data.get("never_grant"))
    return CEILING_RISK_CLASSES if parsed is None else parsed


# ---------------------------------------------------------------------------
# Per-row validation (closed shape; invalid rows are line-dropped + need)
# ---------------------------------------------------------------------------

def _is_str_list(v: Any) -> bool:
    return (isinstance(v, list) and bool(v)
            and all(isinstance(x, str) and x.strip() for x in v))


def _row_error(g: Any) -> str | None:
    """First violation for a grant row, or None when valid."""
    if not isinstance(g, dict):
        return "grant row is not a mapping"
    extra = set(g) - _GRANT_KEYS
    if extra:
        return f"unknown keys: {sorted(extra)}"
    missing = _GRANT_KEYS - set(g)
    if missing:
        return f"missing keys: {sorted(missing)}"
    gid = g["id"]
    if not isinstance(gid, str) or not gid.startswith("GRANT-") or len(gid) <= len("GRANT-"):
        return "id must be a non-empty 'GRANT-…' string"
    for k in ("deployment", "granted_by", "basis"):
        if not isinstance(g[k], str) or not g[k].strip():
            return f"{k} must be a non-empty string"
    if g["risk_class"] not in CEILING_RISK_CLASSES:
        # Grants are ceilings-only — a non-ceiling grant is structurally void.
        return (f"risk_class '{g['risk_class']}' is not a hard-ceiling class "
                f"(grants are ceilings-only)")
    if not _is_str_list(g["action_types"]):
        return "action_types must be a non-empty list of strings"
    if not _is_str_list(g["lanes"]) or "*" in g["lanes"]:
        # Narrowest-scope doctrine: never lane:'*' — name the lanes.
        return "lanes must be a non-empty list of named lanes (never '*')"
    scope = g["scope"]
    if not isinstance(scope, dict) or (set(scope) - _SCOPE_KEYS):
        return f"scope must be a mapping with keys ⊆ {sorted(_SCOPE_KEYS)}"
    for lk in ("recipient_allowlist", "vendor_allowlist"):
        lv = scope.get(lk)
        if lv is not None and not (isinstance(lv, list)
                                   and all(isinstance(x, str) for x in lv)):
            return f"scope.{lk} must be a list of strings"
    cap = scope.get("max_eur_per_day")
    if cap is not None and (not isinstance(cap, (int, float))
                            or isinstance(cap, bool) or cap < 0):
        return "scope.max_eur_per_day must be a non-negative number"
    rate = g["rate"]
    if (not isinstance(rate, dict) or set(rate) != _RATE_KEYS
            or not isinstance(rate["max_per_day"], int)
            or isinstance(rate["max_per_day"], bool) or rate["max_per_day"] < 1):
        return "rate must be {max_per_day: <positive int>}"
    granted_at = _to_dt(g["granted_at"])
    expires = _to_dt(g["expires"])
    if granted_at is None:
        return "granted_at must be a timestamp"
    if expires is None:
        return "expires must be a date/timestamp"
    if expires <= granted_at:
        return "expires must be after granted_at"
    if (expires - granted_at) > timedelta(days=MAX_EXPIRY_HORIZON_DAYS):
        return f"expiry horizon exceeds {MAX_EXPIRY_HORIZON_DAYS}d (FI-2)"
    if not isinstance(g["revoked"], bool):
        return "revoked must be a boolean"
    return None


# ---------------------------------------------------------------------------
# Loader — fail-closed to []
# ---------------------------------------------------------------------------

def load_grants(
    root: str | Path | None = None,
    *,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
    file_needs: bool = True,
) -> list[dict[str, Any]]:
    """The valid grant rows, or `[]` on any file-level failure (D6).

    Absent / unparseable / not-schg-locked ⇒ [] + deduped need. Malformed
    rows are line-dropped (+ need), the rest survive. Rows whose risk_class
    ∈ posture.yml `never_grant` are dropped fail-closed + ONE deduped
    kind=decision need per class (Captain ruling 2026-07-05: grantability is
    instance-scoped — the flavor-structural external_comms refusal is gone).
    """
    path = grants_path(root)
    need = _file_need if file_needs else (lambda *a, **k: None)
    try:
        if not path.exists():
            need(root, "standing-grants.yml is absent — grants resolve empty")
            return []
    except OSError:
        return []
    if not (is_locked_fn or is_locked)(path):
        need(root, "standing-grants.yml exists but is not schg-locked — "
                   "not attested; grants resolve empty until the Captain "
                   "locks it (sudo chflags schg)")
        return []
    try:
        import yaml  # deferred — available in the cabinet runtime + CI
        data = yaml.safe_load(path.read_text())
    except Exception as exc:
        need(root, f"standing-grants.yml is unparseable: {exc}")
        return []
    if (not isinstance(data, dict) or data.get("version") != 1
            or isinstance(data.get("version"), bool)
            or not isinstance(data.get("grants"), list)
            or set(data) - {"version", "grants"}):
        need(root, "standing-grants.yml is corrupt: expected "
                   "{version: 1, grants: [...]} exactly")
        return []

    never = _never_grant_classes(root, is_locked_fn=is_locked_fn)

    out: list[dict[str, Any]] = []
    needed_classes: set[str] = set()  # one decision need per class per pass
    for g in data["grants"]:
        err = _row_error(g)
        if err:
            gid = g.get("id") if isinstance(g, dict) else None
            need(root, f"standing grant {gid or '<no id>'} line-dropped: {err}",
                 action_type="standing_grants_row")
            continue
        if g["risk_class"] in never:
            # Instance-scoped refusal (Captain ruling 2026-07-05): the class
            # is on this Captain's never_grant list — drop fail-closed and
            # file ONE decision need per class, never a grant-request need.
            if g["risk_class"] not in needed_classes:
                needed_classes.add(g["risk_class"])
                need(root,
                     f"standing grant(s) for '{g['risk_class']}' dropped: "
                     f"the class is in the Captain's never_grant list "
                     f"(posture.yml)",
                     risk_class=g["risk_class"],
                     action_type="never_grant_refusal",
                     unblocks="nothing until the Captain removes the class "
                              "from never_grant (unlock ritual) — deliberate "
                              "instance policy, not a repairable fault")
            continue
        out.append(g)
    return out


# ---------------------------------------------------------------------------
# Hard-scope predicates (missing context ⇒ FAIL — never allow unverified)
# ---------------------------------------------------------------------------

def _hard_scope_ok(risk_class: str, scope: dict[str, Any],
                   context: dict[str, Any] | None) -> tuple[bool, str]:
    ctx = context or {}
    if risk_class == "external_comms":
        recipient = ctx.get("recipient")
        if not isinstance(recipient, str) or not recipient.strip():
            return False, "hard-scope: no recipient in context (fail-closed)"
        allow = scope.get("recipient_allowlist") or []
        if any(fnmatch.fnmatchcase(recipient.strip().lower(), str(p).lower())
               for p in allow):
            return True, ""
        return False, f"hard-scope: recipient '{recipient}' not in allowlist"
    if risk_class == "spend":
        amt = ctx.get("amount_eur")
        if not isinstance(amt, (int, float)) or isinstance(amt, bool) or amt < 0:
            return False, "hard-scope: no amount_eur in context (fail-closed)"
        cap = scope.get("max_eur_per_day")
        if (isinstance(cap, (int, float)) and not isinstance(cap, bool)
                and amt <= cap):
            return True, ""
        return False, f"hard-scope: amount {amt} EUR exceeds max_eur_per_day"
    vendor = ctx.get("vendor")
    if not isinstance(vendor, str) or not vendor.strip():
        return False, "hard-scope: no vendor in context (fail-closed)"
    allow = {str(v).strip().lower() for v in (scope.get("vendor_allowlist") or [])}
    if vendor.strip().lower() in allow:
        return True, ""
    return False, f"hard-scope: vendor '{vendor}' not in allowlist"


# ---------------------------------------------------------------------------
# check / covers
# ---------------------------------------------------------------------------

def _match(
    risk_class: str,
    action_type: str,
    *,
    lane: str | None,
    root: str | Path | None,
    now: Any,
    context: dict[str, Any] | None,
    grants: list[dict[str, Any]] | None,
    is_locked_fn,
    redis_get,
    is_vetoed_fn,
    file_needs: bool,
    require_scope: bool,
    require_rate: bool,
) -> dict[str, Any]:
    if risk_class not in CEILING_RISK_CLASSES:
        # Ceilings-only: a check for a non-ceiling class is a wiring bug —
        # never grantable, and worth a deduped signal.
        if file_needs:
            _file_need(root,
                       f"grants.check called for non-ceiling risk_class "
                       f"'{risk_class}' (action_type {action_type}) — wiring "
                       f"bug or matrix drift",
                       risk_class=risk_class, action_type=action_type,
                       filed_by="grants.check")
        return {"granted": False, "grant_id": None,
                "reason": f"'{risk_class}' is not a hard-ceiling class — "
                          f"standing grants are ceilings-only"}
    try:
        vetoed = (is_vetoed_fn or _default_is_vetoed)(action_type)
    except Exception:
        vetoed = True  # unreadable veto registry narrows, never widens
    if vetoed:
        return {"granted": False, "grant_id": None,
                "reason": f"action_type '{action_type}' is under an active "
                          f"Captain veto (or the registry is unreadable)"}

    rows = grants if grants is not None else load_grants(
        root, is_locked_fn=is_locked_fn, file_needs=file_needs)
    nowdt = _now(now)
    cid = cabinet_id()
    get = redis_get or _default_redis_get
    today = nowdt.strftime("%Y-%m-%d")
    reasons: list[str] = []

    for g in rows:
        gid = g.get("id")
        if g.get("deployment") != cid:
            continue
        if g.get("risk_class") != risk_class:
            continue
        if action_type not in (g.get("action_types") or []):
            continue
        if lane is None or lane not in (g.get("lanes") or []):
            reasons.append(f"{gid}: lane '{lane}' not granted")
            continue
        if g.get("revoked"):
            reasons.append(f"{gid}: revoked (file flag)")
            continue
        expires = _to_dt(g.get("expires"))
        if expires is None or nowdt >= expires:
            reasons.append(f"{gid}: expired")
            continue
        try:
            tomb = get(_TOMBSTONE_PREFIX + str(gid))
        except Exception:
            reasons.append(f"{gid}: revocation tombstone unreadable "
                           f"(Redis down) — treated revoked")
            continue
        if tomb:
            reasons.append(f"{gid}: revoked (tombstone)")
            continue
        if require_rate:
            try:
                raw = get(f"{_COUNT_PREFIX}{gid}:{today}")
                used = int(raw) if raw else 0
            except Exception:
                reasons.append(f"{gid}: rate counter unreadable — not granted")
                continue
            if used >= int((g.get("rate") or {}).get("max_per_day") or 0):
                reasons.append(f"{gid}: daily rate exhausted ({used})")
                continue
        if require_scope:
            ok, why = _hard_scope_ok(risk_class, g.get("scope") or {}, context)
            if not ok:
                reasons.append(f"{gid}: {why}")
                continue
        return {"granted": True, "grant_id": gid,
                "reason": f"standing grant {gid} matched "
                          f"({risk_class}/{action_type}, lane {lane})"}
    return {"granted": False, "grant_id": None,
            "reason": "; ".join(reasons) or "no matching standing grant"}


def check(
    risk_class: str,
    action_type: str,
    *,
    lane: str | None,
    root: str | Path | None = None,
    now: Any = None,
    context: dict[str, Any] | None = None,
    grants: list[dict[str, Any]] | None = None,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
    redis_get: Optional[Callable[[str], str]] = None,
    is_vetoed_fn: Optional[Callable[[str | None], bool]] = None,
    file_needs: bool = True,
) -> dict[str, Any]:
    """FI-2 allow decision → {granted, grant_id, reason}. THE only path a
    ceiling row may resolve to an allow, and it enforces every condition —
    including the class hard-scope predicate against `context`
    ({recipient|amount_eur|vendor}); missing context fails closed."""
    return _match(
        risk_class, action_type, lane=lane, root=root, now=now,
        context=context, grants=grants, is_locked_fn=is_locked_fn,
        redis_get=redis_get, is_vetoed_fn=is_vetoed_fn, file_needs=file_needs,
        require_scope=True, require_rate=True,
    )


def covers(
    risk_class: str,
    action_type: str,
    *,
    lane: str | None,
    root: str | Path | None = None,
    now: Any = None,
    grants: list[dict[str, Any]] | None = None,
    is_locked_fn: Optional[Callable[[Path], bool]] = None,
    redis_get: Optional[Callable[[str], str]] = None,
    is_vetoed_fn: Optional[Callable[[str | None], bool]] = None,
) -> dict[str, Any]:
    """Structural coverage (for `needs.cross_check_grants`): everything
    `check` enforces EXCEPT the per-item hard-scope predicate and today's
    rate counter, which are act-time data. NEVER an allow path — a covered
    need closes, the act itself still goes through `check`."""
    return _match(
        risk_class, action_type, lane=lane, root=root, now=now,
        context=None, grants=grants, is_locked_fn=is_locked_fn,
        redis_get=redis_get, is_vetoed_fn=is_vetoed_fn, file_needs=False,
        require_scope=False, require_rate=False,
    )


def record_use(
    grant_id: str,
    *,
    now: Any = None,
    redis_incr: Optional[Callable[[str], str]] = None,
    redis_expire: Optional[Callable[[str, int], None]] = None,
) -> bool:
    """Count an attributed allow against the day-keyed rate counter.

    Best-effort (returns False on failure): the READ side is the enforcement
    — an uncountable use leaves the counter unreadable or stale, and the next
    `check` fails closed on unreadable counters.
    """
    key = f"{_COUNT_PREFIX}{grant_id}:{_now(now).strftime('%Y-%m-%d')}"
    try:
        (redis_incr or _default_redis_incr)(key)
        (redis_expire or _default_redis_expire)(key, _COUNT_TTL_S)
        return True
    except Exception as exc:
        print(f"grants: WARN record_use failed for {grant_id}: {exc}",
              file=sys.stderr)
        return False
