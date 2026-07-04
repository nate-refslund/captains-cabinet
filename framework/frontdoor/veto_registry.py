"""veto_registry.py — TI-4: the Captain's persistent, unforgeable veto registry.

A veto is the sharpest of the estate's demotion teeth (grand plan §5.4): Nate's
``never:`` on an act-first kind removes it from ``act_with_undo`` FOREVER, and
his ``lift veto-NNN`` restores it. This module is the durable home of that
verdict — everything above it (the binder grammar, the proposer pre-filter, the
executor hard-stop, the weekly ledger↔yml divergence audit) reads or writes
through this one API so the meaning of "vetoed" can never fork.

Source of truth is the git-tracked, Captain-verbatim, **germline-protected**
YAML file (``shared/interfaces/captain-vetoes.yml`` by default; overridable via
``CABINET_CAPTAIN_VETOES``). Redis (``cabinet:vetoes:*``) is only a rebuilt
cache — never the sole authority — and a rebuild FAILURE fails CLOSED (act-first
off that run), so an unreadable registry narrows the perimeter, never widens it.

Invariants (do not weaken):
  * **Deterministic scope only** [RT-A10] — a veto binds ``action_type`` +
    ``board`` / ``content_family`` (+ the ``lane`` it was seen on), matched by
    exact field equality. NEVER an LLM slug or free text: paraphrase can neither
    add nor widen a veto. A scope carrying no enforceable field is refused.
  * **Cell demotion, not slug filter** [RT-A10] — a ``never:`` on an act-first
    kind demotes the whole ``(actor, lane, action_type)`` graduation cell out of
    ``act_with_undo`` (``demote_cell_for_veto`` / ``cell_matches``), not merely
    one card.
  * **Monotonic, no expiry, lift-only** — ids never repeat; rows are never
    deleted (a retired veto is stamped ``lifted_at`` + ``status: lifted``);
    silence never clears a veto.
  * **One row shape for every reader** [Tier-0 #7 schema reconcile] — the
    writer stamps BOTH field dialects on each row: the registry's own
    ``recorded_at``/``lifted_at`` and the canary divergence-audit's
    ``ts``/``status`` (``actfirst_canary.veto_ledger_divergences`` reads the
    latter). Activeness honors either dialect, and only positive lift
    evidence counts (an unknown ``status`` is NOT a lift — fail toward
    enforcing the veto).
  * **Audited** — every record/lift emits a consequence-ledger audit event.

System note: the act-first machinery runs as UNHOOKED launchd processes, so this
module's file write is the sanctioned registry path (the pre-tool-use hook
write-protects the yml against *officer* Bash/Edit, not this API). stdlib +
PyYAML only (system convention; ``yaml.safe_load`` is used repo-wide).
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
# shared/interfaces/ is the canonical home: it is the grand-plan germline-
# write-protected path (CAPTAIN MOMENT 1, RT-B7), it is where actfirst_canary's
# RT-B7 divergence audit reads, and it sits with the other Captain-verbatim
# artifacts (captain-decisions/patterns/intents). Overridable via
# CABINET_CAPTAIN_VETOES. (An earlier draft used instance/config — reconciled.)
_DEFAULT_VETO_FILE = _REPO_ROOT / "shared" / "interfaces" / "captain-vetoes.yml"

# Redis cache namespace (grand plan: cabinet:vetoes:*). The health sentinel is
# how a separate/unhooked process (the action lane) learns the cache is fresh;
# a missing/"fail" sentinel => act-first off that run (fail-closed).
_CACHE_PREFIX = "cabinet:vetoes:"
_CACHE_SENTINEL = "cabinet:vetoes:__cache__"
_CACHE_TTL_S = 3600  # rebuilt at each lane start; the TTL bounds staleness

# The deterministic fields a veto scope may bind — NEVER an LLM slug [RT-A10].
_SCOPE_FIELDS: Tuple[str, ...] = ("action_type", "board", "content_family", "lane")
# The subset that makes a veto ENFORCEABLE. A scope with none of these matches
# nothing — a catch-all veto (which would veto the whole estate) is refused.
_ENFORCEABLE_FIELDS: Tuple[str, ...] = ("action_type", "board", "content_family")

_DEFAULT_HEADER = (
    "# captain-vetoes.yml — THE CAPTAIN'S VETO REGISTRY (TI-4)\n"
    "# Captain-authored, verbatim, germline-protected, monotonic, lift-only,\n"
    "# no expiry. Written only by framework/frontdoor/veto_registry.py on Nate's\n"
    "# CAPTAIN_TELEGRAM_ID-gated verbs. Scope is derived from deterministic\n"
    "# fields (action_type + board / content-hash family), never a slug.\n"
)


class VetoRegistryError(Exception):
    """A veto could not be recorded/read (malformed file, refused scope)."""


# --- paths + time ------------------------------------------------------------

def veto_file_path() -> Path:
    """The active veto file — ``CABINET_CAPTAIN_VETOES`` override, else the
    canonical ``shared/interfaces/captain-vetoes.yml``. Exposed so every consumer
    (canary divergence audit, tests, a future path reconciliation) resolves the
    SAME file instead of hardcoding a second literal."""
    env = os.environ.get("CABINET_CAPTAIN_VETOES")
    return Path(env) if env else _DEFAULT_VETO_FILE


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- scope hygiene [RT-A10] --------------------------------------------------

def _clean_scope(scope: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Keep ONLY the deterministic scope fields with non-empty string values;
    drop everything else (free text, slugs, unknown keys). This is the single
    chokepoint that makes a veto un-widenable by paraphrase."""
    if not isinstance(scope, dict):
        return {}
    out: Dict[str, str] = {}
    for k in _SCOPE_FIELDS:
        v = scope.get(k)
        if isinstance(v, str):
            v = v.strip()
        if v not in (None, "", {}, []):
            out[k] = str(v)
    return out


def _is_enforceable(scope: Dict[str, str]) -> bool:
    return any(scope.get(f) for f in _ENFORCEABLE_FIELDS)


# --- yaml doc load/save (header-preserving, atomic) --------------------------

def _empty_doc() -> Dict[str, Any]:
    return {"version": 1, "next_id": 1, "vetoes": []}


def _veto_num(vid: Any) -> int:
    try:
        return int(str(vid).rsplit("-", 1)[-1])
    except (ValueError, TypeError):
        return 0


def _next_from(vetoes: List[Any]) -> int:
    mx = 0
    for v in vetoes:
        if isinstance(v, dict):
            mx = max(mx, _veto_num(v.get("id", "")))
    return mx + 1


def _load_doc(path: Optional[Path] = None) -> Dict[str, Any]:
    """Parse the veto doc. Missing file => empty doc (fail toward "no vetoes"
    is safe: enforcement over an empty registry blocks nothing, and act-first is
    separately gated on a fresh cache). A MALFORMED file raises — it must never
    silently collapse into an empty set (that would fail OPEN, dropping a live
    veto); the caller (record/lift → binder passthrough; rebuild → fail-closed)
    handles it."""
    p = Path(path) if path else veto_file_path()
    if not p.exists():
        return _empty_doc()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise VetoRegistryError(f"malformed veto file {p}: {e}") from e
    if data is None:
        return _empty_doc()
    if isinstance(data, list):                       # tolerate a bare list
        return {"version": 1, "next_id": _next_from(data), "vetoes": data}
    if not isinstance(data, dict):
        raise VetoRegistryError(f"veto file {p} is not a mapping or list")
    vetoes = data.get("vetoes") or []
    if not isinstance(vetoes, list):
        raise VetoRegistryError(f"veto file {p}: 'vetoes' must be a list")
    return {
        "version": data.get("version", 1),
        "next_id": data.get("next_id") or _next_from(vetoes),
        "vetoes": vetoes,
    }


def _read_header(p: Path) -> str:
    """Preserve the file's leading comment block across writes — the header is
    Captain-authored contract text and must survive a record/lift rewrite."""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return _DEFAULT_HEADER
    header: List[str] = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("#") or s == "":
            header.append(ln)
        else:
            break
    while header and header[-1].strip() == "":
        header.pop()
    return ("\n".join(header) + "\n") if header else _DEFAULT_HEADER


def _save_doc(p: Path, doc: Dict[str, Any]) -> None:
    """Header + body, written atomically (tmp + os.replace)."""
    header = _read_header(p)
    body = yaml.safe_dump(
        {"version": doc.get("version", 1),
         "next_id": doc.get("next_id", 1),
         "vetoes": doc.get("vetoes", [])},
        sort_keys=False, allow_unicode=True, default_flow_style=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(header + "\n" + body, encoding="utf-8")
    os.replace(tmp, p)


# --- public read API ---------------------------------------------------------

def load_vetoes(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """All veto rows (active AND lifted), in record order."""
    return [v for v in _load_doc(path).get("vetoes", []) if isinstance(v, dict)]


def _is_lifted(v: Dict[str, Any]) -> bool:
    """A row is lifted iff EITHER dialect positively says so: the registry's
    own ``lifted_at`` stamp OR the canary-audit ``status: lifted`` field
    [Tier-0 #7 schema reconcile]. Honoring both means the enforcement plane
    and the weekly divergence audit can never disagree about activeness. An
    unknown/mangled ``status`` is NOT lift evidence — the veto stays enforced
    (fail-closed)."""
    if v.get("lifted_at"):
        return True
    return str(v.get("status") or "").strip().lower() == "lifted"


def active_vetoes(path: Optional[Path] = None,
                  vetoes: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Non-lifted, enforceable vetoes only — what the perimeter actually binds."""
    rows = vetoes if vetoes is not None else load_vetoes(path)
    return [v for v in rows if isinstance(v, dict) and not _is_lifted(v)
            and _is_enforceable(_clean_scope(v.get("scope")))]


def is_vetoed(action_type: Optional[str], board: Optional[str] = None,
              content_family: Optional[str] = None, *,
              vetoes: Optional[List[Dict[str, Any]]] = None,
              path: Optional[Path] = None) -> bool:
    """True iff an active veto binds this action by DETERMINISTIC-FIELD match
    [RT-A10]. A SET scope field must equal the corresponding arg; an UNSET scope
    field is a wildcard. This is the shared predicate the proposer pre-filter and
    the executor hard-stop both import — matching is content-blind and slug-free,
    so it is identical on both layers and impossible to reword around."""
    for v in active_vetoes(path=path, vetoes=vetoes):
        sc = _clean_scope(v.get("scope"))
        if sc.get("action_type") and sc["action_type"] != (action_type or ""):
            continue
        if sc.get("board") and sc["board"] != (board or ""):
            continue
        if sc.get("content_family") and sc["content_family"] != (content_family or ""):
            continue
        return True
    return False


def matching_vetoes(action_type: Optional[str], board: Optional[str] = None,
                    content_family: Optional[str] = None, *,
                    vetoes: Optional[List[Dict[str, Any]]] = None,
                    path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The active vetoes that bind this action (for telling WHICH veto blocked)."""
    out = []
    for v in active_vetoes(path=path, vetoes=vetoes):
        sc = _clean_scope(v.get("scope"))
        if sc.get("action_type") and sc["action_type"] != (action_type or ""):
            continue
        if sc.get("board") and sc["board"] != (board or ""):
            continue
        if sc.get("content_family") and sc["content_family"] != (content_family or ""):
            continue
        out.append(v)
    return out


# --- cell demotion [RT-A10] --------------------------------------------------

def demote_cell_for_veto(scope: Dict[str, Any]) -> Dict[str, Any]:
    """Map a veto scope to a graduation cell-demotion directive.

    A graduation ``cell = (actor_id, lane, action_type)``. RT-A10: a ``never:``
    on an act-first KIND demotes the whole cell out of ``act_with_undo`` across
    ALL actors — the KIND is the ``action_type``. Returns a directive whose
    ``None`` fields are wildcards; ``board``/``content_family`` are NOT cell
    dimensions, so a board-only veto yields no cell-level demotion here (it is
    enforced by ``is_vetoed`` at act time instead — see ``cell_matches``). The
    graduation/gate layer consumes this; this module only exposes it."""
    scope = _clean_scope(scope)
    return {
        "actor_id": None,                          # all actors
        "lane": scope.get("lane"),                 # None => all lanes
        "action_type": scope.get("action_type"),   # the vetoed KIND (or None)
    }


def cell_matches(cell: Tuple[Optional[str], Optional[str], Optional[str]],
                 directive: Dict[str, Any]) -> bool:
    """True if a graduation cell falls under a demotion directive. A directive
    with NO ``action_type`` demotes no cell — a board/content-only veto is
    enforced by ``is_vetoed`` at act time, never by nuking the whole matrix, so
    an all-wildcard directive is a no-op here (safe by construction)."""
    actor_id, lane, action_type = cell
    if not directive.get("action_type"):
        return False
    if directive["action_type"] != action_type:
        return False
    if directive.get("lane") and directive["lane"] != lane:
        return False
    if directive.get("actor_id") and directive["actor_id"] != actor_id:
        return False
    return True


def render_veto_prompt_block(vetoes: Optional[List[Dict[str, Any]]] = None, *,
                             path: Optional[Path] = None) -> str:
    """Active vetoes as a hard-rule prompt block for the proposer's injection
    layer (three-layer enforcement (a): pre-filter + prompt). Empty string when
    there are no active vetoes so a caller can drop it cleanly."""
    rows = active_vetoes(path=path, vetoes=vetoes)
    if not rows:
        return ""
    lines = ["CAPTAIN VETOES — hard rules; NEVER propose or act on a match:"]
    for v in rows:
        sc = _clean_scope(v.get("scope"))
        parts = " ".join(f"{k}={sc[k]}" for k in _SCOPE_FIELDS if sc.get(k))
        verbatim = (v.get("verbatim") or "").strip()[:160]
        lines.append(f"  - {v.get('id')}: {parts}"
                     + (f"  «{verbatim}»" if verbatim else ""))
    return "\n".join(lines)


# --- ledger audit ------------------------------------------------------------

def _default_emit(**ev: Any) -> Any:
    from framework.fidelity.consequence import emit_consequence
    return emit_consequence(**ev)


def _audit(emit: Optional[Callable[..., Any]], *, action: str, vid: str,
           scope: Dict[str, str], verbatim: str, ts: str) -> None:
    """Emit a consequence-ledger audit event for a veto/lift. Fail-safe: the yml
    is the source of truth, so an audit failure never blocks the write. The
    event carries no ``action_type`` (left unstamped, a legal absence) so it can
    never land in a real graduation cell or the pending-proposal set."""
    fn = emit or _default_emit
    evidence = f"{vid} scope={scope}"
    if verbatim:
        evidence = f"{evidence} «{verbatim[:200]}»"
    try:
        fn(ts=ts,
           actor={"kind": "officer", "id": "veto-registry"},
           lane=None,
           action=action,
           subject=f"veto:{vid}",
           outcome={"status": "ok", "evidence": evidence[:500]},
           refs=[f"veto:{vid}"])
    except Exception:
        pass


# --- public write API (monotonic, no expiry, lift-only) ----------------------

def record_veto(scope: Dict[str, Any], verbatim_text: str,
                ts: Optional[str] = None, *, path: Optional[Path] = None,
                emit: Optional[Callable[..., Any]] = None) -> Dict[str, Any]:
    """Append a veto. Monotonic id (``veto-NNN``), no expiry, lift-only. Rejects
    a scope with no enforceable deterministic field (a catch-all veto). Writes
    the yml atomically and emits a ledger audit event. Raises VetoRegistryError
    on a refused scope or an unreadable/malformed file — the binder wraps this so
    Captain-DM passthrough is never broken."""
    clean = _clean_scope(scope)
    if not _is_enforceable(clean):
        raise VetoRegistryError(
            "a veto must bind at least one deterministic field "
            f"({', '.join(_ENFORCEABLE_FIELDS)}) — refused catch-all veto")
    p = Path(path) if path else veto_file_path()
    doc = _load_doc(p)
    vid = f"veto-{int(doc.get('next_id') or _next_from(doc['vetoes'])):03d}"
    recorded_at = ts or _now_iso()
    veto = {
        "id": vid,
        "scope": clean,
        "verbatim": (verbatim_text or "").strip()[:1000],
        "recorded_at": recorded_at,
        "lifted_at": None,
        # [Tier-0 #7 schema reconcile] The canary divergence audit reads
        # ``ts``/``status``; the registry historically wrote only
        # recorded_at/lifted_at, so the weekly audit never saw the rows it was
        # auditing (a lifted veto still audited as active; the at-or-after
        # timestamp check vacuous on a missing ts). Stamp BOTH dialects at the
        # single writer so every reader agrees on the same row.
        "ts": recorded_at,
        "status": "active",
        "source": "captain",
    }
    doc["vetoes"].append(veto)
    doc["next_id"] = _veto_num(vid) + 1
    _save_doc(p, doc)
    _audit(emit, action="captain-veto", vid=vid, scope=clean,
           verbatim=veto["verbatim"], ts=veto["recorded_at"])
    return veto


def lift_veto(veto_id: str, ts: Optional[str] = None, *,
              path: Optional[Path] = None,
              emit: Optional[Callable[..., Any]] = None) -> Optional[Dict[str, Any]]:
    """Retire a veto by id — stamps ``lifted_at`` (never deletes the row).
    Idempotent (an already-lifted veto is returned unchanged). Returns None if
    the id is unknown."""
    p = Path(path) if path else veto_file_path()
    doc = _load_doc(p)
    found = next((v for v in doc["vetoes"]
                  if isinstance(v, dict) and v.get("id") == veto_id), None)
    if found is None:
        return None
    if found.get("lifted_at"):
        return found                       # idempotent — already lifted
    found["lifted_at"] = ts or _now_iso()
    found["status"] = "lifted"   # keep the canary-audit dialect in sync [Tier-0 #7]
    _save_doc(p, doc)
    _audit(emit, action="captain-veto-lift", vid=veto_id,
           scope=_clean_scope(found.get("scope")),
           verbatim=found.get("verbatim", ""), ts=found["lifted_at"])
    return found


# --- Redis cache (rebuilt at lane start; fail-closed) ------------------------

def _redis(*args: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    out = subprocess.run(["redis-cli", "-h", host, *args],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    return "" if out in ("", "(nil)") else out


def _default_redis_set(key: str, value: str, ttl_s: Optional[int]) -> None:
    args = ["SET", key, value]
    if ttl_s is not None:
        args += ["EX", str(int(ttl_s))]
    _redis(*args)


def _default_redis_get(key: str) -> str:
    return _redis("GET", key)


def _default_redis_del(key: str) -> None:
    _redis("DEL", key)


def _default_redis_scan(pattern: str) -> List[str]:
    host = os.environ.get("REDIS_HOST", "localhost")
    out = subprocess.run(
        ["redis-cli", "-h", host, "--scan", "--pattern", pattern],
        capture_output=True, text=True, timeout=10).stdout
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def rebuild_cache(vetoes: Optional[List[Dict[str, Any]]] = None, *,
                  redis_set: Optional[Callable[[str, str, Optional[int]], None]] = None,
                  redis_del: Optional[Callable[[str], None]] = None,
                  redis_scan: Optional[Callable[[str], List[str]]] = None,
                  ttl_s: int = _CACHE_TTL_S) -> Dict[str, Any]:
    """Rebuild ``cabinet:vetoes:*`` from the yml and stamp the health sentinel.

    Called at action-lane start. On success every active veto is cached and the
    sentinel reads ``ok``. On ANY failure (unreadable/malformed yml, redis down)
    it returns ``ok=False`` and best-effort marks the sentinel ``fail`` — the
    lane reads that (or a missing sentinel) as **act-first off this run**
    (fail-closed): an unverifiable veto set must never allow an unattended act."""
    rset = redis_set or _default_redis_set
    rdel = redis_del or _default_redis_del
    rscan = redis_scan or _default_redis_scan
    try:
        active = active_vetoes(vetoes=vetoes)
        for key in rscan(_CACHE_PREFIX + "*"):
            if key != _CACHE_SENTINEL:
                rdel(key)
        for v in active:
            rset(_CACHE_PREFIX + str(v["id"]),
                 json.dumps(v, ensure_ascii=False), ttl_s)
        rset(_CACHE_SENTINEL, "ok", ttl_s)
        return {"ok": True, "count": len(active)}
    except Exception as e:
        try:
            rset(_CACHE_SENTINEL, "fail", ttl_s)
        except Exception:
            pass
        return {"ok": False, "error": str(e)[:200]}


def veto_cache_ready(redis_get: Optional[Callable[[str], str]] = None) -> bool:
    """True only if the last ``rebuild_cache`` succeeded and is unexpired. A
    missing/``fail``/unreadable sentinel => not ready => act-first off
    (fail-closed). The action lane calls this before acting unattended."""
    get = redis_get or _default_redis_get
    try:
        return get(_CACHE_SENTINEL) == "ok"
    except Exception:
        return False
