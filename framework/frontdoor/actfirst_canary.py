"""TI-7 — canaries + breakers + caps: the plane that guards the act-first guard.

Wave-2 L3 of the 2026-07-04 trust-inversion pivot (grand-plan §3 WAVE 2 L3,
impl-plan §2.3). The act-first machinery grants the reversible class unattended
writes; THIS module is the mechanical brake on that grant. It never acts on the
real estate for real — it only:

  1. CANARY   — a weekly synthetic create→verify→reverse→verify per act-first
                kind, JOURNAL-ONLY (``canary:true``), emitting ZERO consequence
                events (a canary must never look like real acting). Uses the
                executor's forward ops + ``action_undo.reverse`` through injected
                transports. Failure OR cannot-run ⇒ freeze that kind.
  2. KIND BREAKER — trailing-7d undo-rate > 25% at >= 8 acted samples of an
                action_type ⇒ freeze it (cooldown 14, NO auto-unfreeze; CRIT-5).
  3. SILENCE BREAKER [RT-A6] — 30 consecutive zero-human-touch acts of a kind ⇒
                propose_only until one human digest interaction on that kind (the
                undo premise stays unverified otherwise).
  4. CAPS     — estate 40/day + per-kind 20/day, fail-closed counters.
  5. CID-ECHO — an act that gets captured and re-proposed (act→capture→act) is
                detected via its correlation id and suppressed.
  6. VETO AUDIT [RT-B7] — weekly captain-vetoes.yml ↔ ledger diff, page on any
                divergence between the veto registry and what the ledger acted.

Everything is DARK: consumed by the act-first gate (TI-3, a later wave) via the
predicates here (``is_frozen`` / ``is_silenced`` / ``cap_check``); nothing here is
scheduled or enforcing yet. No LLM anywhere — deterministic code reading the
ledger + the undo journal.

Stdlib-only, importable under system Python 3.9.6 (``from __future__`` + Optional
annotations, no runtime ``X | Y`` unions). Every external effect (Redis, Monday,
AppleScript) is an INJECTED callable with a lazy production default, so tests
never touch a live backend. Freeze/silence read fail-closed: an unreachable
Redis narrows the perimeter (treated frozen / silenced), never widens it.
"""
from __future__ import annotations

import json
import os
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from framework.frontdoor import action_undo
from framework.probes import correlation
from framework.fidelity.consequence import read_ledger

# --- constants ---------------------------------------------------------------

# Blast bounds (safety-spine §6). Loaded from the instance act-first knobs
# (instance/config/act-first-surfaces.yml caps) with these conservative hard
# fallbacks — tighten never loosen.
ESTATE_CAP_PER_DAY = 40
PER_KIND_CAP_PER_DAY = 20
# Cap-counter TTL: 48h so a counter key outlives its UTC day even across a late
# sweep, then self-expires (the day rolls the key over anyway).
CAP_KEY_TTL_S = 172800

# Kind breaker (grand-plan §7 kill criteria): a trailing window, a rate, a floor.
KIND_BREAKER_WINDOW_DAYS = 7
KIND_BREAKER_MAX_UNDO_RATE = 0.25
KIND_BREAKER_MIN_ACTS = 8
# Cooldown recorded on the freeze for observability. The freeze itself has NO
# auto-unfreeze (action_undo.freeze / CRIT-5): a kind is un-frozen ONLY by a
# manually-triggered green canary. So the cooldown is a re-arm note, not a timer
# that lifts the freeze — an already-frozen kind is simply never re-frozen.
KIND_BREAKER_COOLDOWN_DAYS = 14

# Silence breaker [RT-A6]: consecutive zero-human-touch acts of a kind before it
# drops to propose_only (the undo premise is unverified — fail toward propose).
SILENCE_BREAKER_THRESHOLD = 30

# The canary label prefix — a loud, greppable marker on every synthetic artifact
# so a canary item/event is never mistaken for real work by a human either.
CANARY_PREFIX = "[cabinet-canary]"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACT_FIRST_SURFACES = _REPO_ROOT / "instance" / "config" / "act-first-surfaces.yml"
# TI-4 (a later wave) lands this file. Absent today ⇒ zero vetoes ⇒ no divergence
# (the audit degrades gracefully rather than erroring).
_CAPTAIN_VETOES = _REPO_ROOT / "shared" / "interfaces" / "captain-vetoes.yml"
# The Plan-A pipes env — the perms target for the weekly 0600 check.
_SHARED_ENV = Path.home() / ".screenpipe" / "pipes" / "_shared" / ".env"


# --- time helpers ------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(ts: Optional[str]) -> datetime:
    try:
        return datetime.strptime(ts or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _date(now: Optional[str] = None) -> str:
    return _parse(now).strftime("%Y-%m-%d") if now else \
        datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_ago(now: Optional[str], days: int) -> str:
    base = _parse(now) if now else datetime.now(timezone.utc)
    return (base - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- Redis (injected; lazy subprocess default — never the sole authority) ----

def _redis(*args: str) -> str:
    host = os.environ.get("REDIS_HOST", "localhost")
    out = subprocess.run(["redis-cli", "-h", host, *args],
                         capture_output=True, text=True, timeout=10).stdout.strip()
    return "" if out in ("", "(nil)") else out


def _default_redis_incr(key: str) -> str:
    return _redis("INCR", key)


def _default_redis_expire(key: str, ttl_s: int) -> None:
    _redis("EXPIRE", key, str(int(ttl_s)))


def _default_redis_set(key: str, value: str, ttl_s: Optional[int]) -> None:
    args = ["SET", key, value]
    if ttl_s:
        args += ["EX", str(int(ttl_s))]
    _redis(*args)


def _default_redis_get(key: str) -> str:
    return _redis("GET", key)


def _default_redis_del(key: str) -> None:
    _redis("DEL", key)


# --- act-first kind key ------------------------------------------------------
# The gate (TI-3) freezes / checks per STEP action_type; the ledger's undo-rate
# keys on action_type too. So the breaker/canary key on the classifier
# action_type, resolved through the ONE shared source (action_undo.action_type_for
# → action_lane.step_action_type). Pre-germline a dormant type resolves to None,
# so we fall back to the step-kind string — but by the time canaries run for real
# (post-flip, after Moment 2) every act-first type is a live enum, so the real
# freeze key is always the action_type. One resolution, imported by TI-3 too.

def kind_key(step_kind: str) -> str:
    """The freeze/breaker key for a step kind — its classifier action_type when
    live, else the step-kind string (dormant-enum fallback)."""
    return action_undo.action_type_for(step_kind) or step_kind


# The (step_kind, backend) pairs a canary could probe. The actual canary set is
# filtered to the act-first-ELIGIBLE members (registered non-``none`` inverse +
# not an excluded backend), so delegate_work and apple_reminders are auto-dropped
# and the set stays correct as the perimeter evolves — a canary covers exactly
# the kinds that can act unattended, which is exactly the set needing undo proof.
_CANARY_CANDIDATES = (
    ("monday_task_create", "monday"),
    ("monday_task_update", "monday"),
    ("reminder_create", "calendar"),
)


def canary_kinds() -> List[tuple]:
    """The (step_kind, backend) pairs a canary runs against — exactly the
    act-first-eligible set (action_undo.act_first_eligible)."""
    return [(k, b) for (k, b) in _CANARY_CANDIDATES
            if action_undo.act_first_eligible(k, b)]


# --- caps (fail-closed) ------------------------------------------------------

def load_caps(config_path: Optional[Path] = None) -> Dict[str, int]:
    """The per-day estate + per-kind caps from the instance act-first knobs, with
    the hard fallbacks. A missing / broken file degrades to the fallbacks (never
    a wider cap)."""
    try:
        import yaml
        data = yaml.safe_load(Path(config_path or _ACT_FIRST_SURFACES).read_text())
        caps = ((data or {}).get("caps") or {})
        estate = ((caps.get("estate") or {}).get("max_acts_per_day"))
        per_kind = ((caps.get("per_kind") or {}).get("max_acts_per_day"))
        return {"estate": int(estate) if estate else ESTATE_CAP_PER_DAY,
                "per_kind": int(per_kind) if per_kind else PER_KIND_CAP_PER_DAY}
    except Exception:
        return {"estate": ESTATE_CAP_PER_DAY, "per_kind": PER_KIND_CAP_PER_DAY}


def count_key(date: str, kind: str) -> str:
    return "cabinet:actfirst:count:" + date + ":" + str(kind)


def estate_key(date: str) -> str:
    return "cabinet:actfirst:count:" + date + ":estate"


def incr_and_check(kind: str, *,
                   redis_incr: Optional[Callable[[str], str]] = None,
                   redis_expire: Optional[Callable[[str, int], None]] = None,
                   caps: Optional[Dict[str, int]] = None,
                   now: Optional[str] = None) -> Dict[str, Any]:
    """Count one act (INCR the per-kind + estate day counters, EX 172800) and
    return whether it is within cap. INCR-then-compare, so a downgraded act still
    consumed its count (conservative). Fail-closed: any Redis error ⇒
    ``ok:False`` (the act downgrades to propose_only — an uncountable act never
    proceeds unattended)."""
    caps = caps or load_caps()
    date = _date(now)
    inc = redis_incr or _default_redis_incr
    exp = redis_expire or _default_redis_expire
    try:
        kc = int(inc(count_key(date, kind)) or 0)
        ec = int(inc(estate_key(date)) or 0)
        exp(count_key(date, kind), CAP_KEY_TTL_S)
        exp(estate_key(date), CAP_KEY_TTL_S)
    except Exception as e:
        return {"ok": False, "kind": kind,
                "reason": "cap counter unavailable — fail-closed to propose_only",
                "error": str(e)[:120]}
    if kc > caps["per_kind"]:
        return {"ok": False, "kind": kind, "kind_count": kc, "estate_count": ec,
                "reason": "per-kind cap " + str(caps["per_kind"]) + "/day exceeded"}
    if ec > caps["estate"]:
        return {"ok": False, "kind": kind, "kind_count": kc, "estate_count": ec,
                "reason": "estate cap " + str(caps["estate"]) + "/day exceeded"}
    return {"ok": True, "kind": kind, "kind_count": kc, "estate_count": ec}


def cap_check(kind: str, *,
              redis_get: Optional[Callable[[str], str]] = None,
              caps: Optional[Dict[str, int]] = None,
              now: Optional[str] = None) -> Dict[str, Any]:
    """Read-only cap peek (GET, no INCR) — a pre-flight check the gate can run
    before deciding to act. Fail-closed on any Redis error."""
    caps = caps or load_caps()
    date = _date(now)
    get = redis_get or _default_redis_get
    try:
        kc = int(get(count_key(date, kind)) or 0)
        ec = int(get(estate_key(date)) or 0)
    except Exception as e:
        return {"ok": False, "kind": kind,
                "reason": "cap counter unavailable — fail-closed to propose_only",
                "error": str(e)[:120]}
    if kc >= caps["per_kind"]:
        return {"ok": False, "kind": kind, "kind_count": kc, "estate_count": ec,
                "reason": "per-kind cap reached"}
    if ec >= caps["estate"]:
        return {"ok": False, "kind": kind, "kind_count": kc, "estate_count": ec,
                "reason": "estate cap reached"}
    return {"ok": True, "kind": kind, "kind_count": kc, "estate_count": ec}


# --- ledger view: acted rows -------------------------------------------------

def _acted_rows(ledger: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The unattended-act rows: ``proposal.required is False`` (the RT-B1 acted
    marker — a propose card carries ``required:true``) AND a real stamped
    action_type. Canary artifacts never emit consequence events, so the ledger is
    canary-free by construction; the marker filter keeps it robust regardless."""
    out: List[Dict[str, Any]] = []
    for ev in ledger:
        if not isinstance(ev, dict):
            continue
        if (ev.get("proposal") or {}).get("required") is not False:
            continue
        if not ev.get("action_type"):
            continue
        out.append(ev)
    return out


def _is_human_touched(ev: Dict[str, Any]) -> bool:
    """A human digest interaction landed on this acted card: a confirm or an undo
    carries ``review.source == 'verdict_human'``. A machine TTL verdict
    (verdict_judge) or an untouched card is NOT a human touch."""
    return (ev.get("review") or {}).get("source") == "verdict_human"


# --- kind breaker ------------------------------------------------------------

def undo_rate(action_type: str, *, ledger: Optional[List[Dict[str, Any]]] = None,
              now: Optional[str] = None,
              window_days: int = KIND_BREAKER_WINDOW_DAYS) -> Dict[str, Any]:
    """Trailing-window undo-rate for one action_type: undone / acts, where an
    undone act carries ``review.verdict == 'wrong'`` (a Captain undo or a
    machine-detected silent revert — either way the act did not stick). ``rate``
    is None when there are no acts (an unmeasured kind, never a silent 0.0)."""
    ledger = read_ledger() if ledger is None else ledger
    lo = _days_ago(now, window_days)
    rows = [ev for ev in _acted_rows(ledger)
            if ev.get("action_type") == action_type and ev.get("ts", "") >= lo]
    acts = len(rows)
    undone = sum(1 for ev in rows if (ev.get("review") or {}).get("verdict") == "wrong")
    return {"action_type": action_type, "acts": acts, "undone": undone,
            "rate": (undone / acts) if acts else None,
            "window_days": window_days}


def run_kind_breaker(*, ledger: Optional[List[Dict[str, Any]]] = None,
                     redis_set: Optional[Callable[[str, str, Optional[int]], None]] = None,
                     redis_get: Optional[Callable[[str], str]] = None,
                     action_types: Optional[List[str]] = None,
                     now: Optional[str] = None) -> Dict[str, Any]:
    """Freeze any action_type whose trailing-7d undo-rate breaches the bar at the
    sample floor. Freeze is durable + fail-closed (action_undo.freeze) with no
    auto-unfreeze; an already-frozen kind is skipped (the cooldown is implicit —
    a frozen kind can only be re-armed by a manual green canary)."""
    ledger = read_ledger() if ledger is None else ledger
    if action_types is None:
        action_types = sorted({ev.get("action_type") for ev in _acted_rows(ledger)
                                if ev.get("action_type")})
    frozen: List[Dict[str, Any]] = []
    evaluated: Dict[str, Dict[str, Any]] = {}
    for at in action_types:
        r = undo_rate(at, ledger=ledger, now=now)
        evaluated[at] = r
        if r["acts"] >= KIND_BREAKER_MIN_ACTS \
                and (r["rate"] or 0.0) > KIND_BREAKER_MAX_UNDO_RATE:
            if action_undo.is_frozen(at, redis_get=redis_get):
                continue                        # already frozen — no duplicate freeze
            reason = ("kind-breaker: undo-rate {:.2f} over {} acts "
                      "(> {} @ >= {}); cooldown {}d, no auto-unfreeze").format(
                r["rate"], r["acts"], KIND_BREAKER_MAX_UNDO_RATE,
                KIND_BREAKER_MIN_ACTS, KIND_BREAKER_COOLDOWN_DAYS)
            action_undo.freeze(at, reason, redis_set=redis_set, now=now)
            frozen.append({"action_type": at, "reason": reason, **r})
    return {"frozen": frozen, "evaluated": evaluated}


# --- silence breaker [RT-A6] -------------------------------------------------

def silence_state(action_type: str, *,
                  ledger: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Consecutive zero-human-touch acts of a kind, newest-first. ``silenced`` is
    True once the count reaches the threshold — and it self-clears the moment a
    recent card carries a human touch (re-derived each run), so ONE digest
    interaction on the kind restores it to act-first."""
    ledger = read_ledger() if ledger is None else ledger
    rows = [ev for ev in _acted_rows(ledger) if ev.get("action_type") == action_type]
    rows.sort(key=lambda e: e.get("ts", ""), reverse=True)      # newest first
    consec = 0
    for ev in rows:
        if _is_human_touched(ev):
            break
        consec += 1
    return {"action_type": action_type, "consecutive_untouched": consec,
            "silenced": consec >= SILENCE_BREAKER_THRESHOLD}


def run_silence_breaker(*, ledger: Optional[List[Dict[str, Any]]] = None,
                        redis_set: Optional[Callable[[str, str, Optional[int]], None]] = None,
                        redis_del: Optional[Callable[[str], None]] = None,
                        action_types: Optional[List[str]] = None,
                        now: Optional[str] = None) -> Dict[str, Any]:
    """Recompute per-kind silence from the ledger and publish the
    ``cabinet:actfirst:silenced:<kind>`` flags the gate reads. A kind that
    crossed the threshold is SET; one that has since been touched is DEL'd (the
    self-clear). Publishing is best-effort — the derived state is the truth."""
    ledger = read_ledger() if ledger is None else ledger
    if action_types is None:
        action_types = sorted({ev.get("action_type") for ev in _acted_rows(ledger)
                                if ev.get("action_type")})
    rset = redis_set or _default_redis_set
    rdel = redis_del or _default_redis_del
    silenced: List[Dict[str, Any]] = []
    cleared: List[str] = []
    for at in action_types:
        st = silence_state(at, ledger=ledger)
        key = "cabinet:actfirst:silenced:" + str(at)
        try:
            if st["silenced"]:
                rset(key, _now(), None)
                silenced.append(st)
            else:
                rdel(key)
                cleared.append(at)
        except Exception:
            pass                                # derived state is authoritative
    return {"silenced": silenced, "cleared": cleared}


def is_silenced(kind: str, *,
                redis_get: Optional[Callable[[str], str]] = None) -> bool:
    """Fail-closed silence read for the gate: an unreachable Redis ⇒ True
    (propose_only — the safe direction, exactly like is_frozen)."""
    get = redis_get or _default_redis_get
    try:
        return bool(get("cabinet:actfirst:silenced:" + str(kind)))
    except Exception:
        return True


# --- act-first freeze read/write (ONE import surface for the gate + executor) -

def is_frozen(kind: str, *,
              redis_get: Optional[Callable[[str], str]] = None) -> bool:
    """Fail-closed frozen read (delegates to action_undo — the freeze owner).
    Re-exported here so TI-3 imports every act-first predicate from one module."""
    return action_undo.is_frozen(kind, redis_get=redis_get)


def freeze(step_kind: str, reason: str, *,
           redis_set: Optional[Callable[[str, str, Optional[int]], None]] = None,
           now: Optional[str] = None) -> Dict[str, Any]:
    """Freeze an act-first kind by its BREAKER KEY — ``kind_key`` resolves the
    classifier action_type when the enum is live (e.g. monday_task_update →
    board_status), else the step-kind string — then delegates to
    ``action_undo.freeze`` (durable JSONL mirror first, best-effort Redis, NO
    auto-unfreeze). One write surface so the executor's quarantine paths (e.g.
    the prestate-clobber dead-letter) freeze exactly the key the TI-3 gate and
    the breakers check."""
    return action_undo.freeze(kind_key(step_kind), reason,
                              redis_set=redis_set, now=now)


# --- cid-echo suppression ----------------------------------------------------

def own_acted_cids(*, ledger: Optional[List[Dict[str, Any]]] = None) -> frozenset:
    """The correlation ids of OUR OWN acted cards (from the acted ledger rows).
    Pre-flip there are none, so the echo filter is a no-op until acting begins."""
    ledger = read_ledger() if ledger is None else ledger
    cids = set()
    for ev in _acted_rows(ledger):
        c = correlation.cid_from_refs(ev.get("refs"))
        if c:
            cids.add(c)
    return frozenset(cids)


def is_cid_echo(text: str, own_cids) -> bool:
    """True iff ``text`` carries one of our own acted cids — an artifact we
    created that got captured back into the vault and is now re-proposed as a
    signal (the act→capture→act loop). Uses correlation.extract's strict,
    prefix-anchored read, so untrusted text cannot smuggle a false-positive id."""
    if not own_cids:
        return False
    c = correlation.extract(text or "")
    return bool(c and c in own_cids)


def filter_cid_echoes(items: List[Any], own_cids, *, text_of: Callable[[Any], str],
                      log: Optional[Callable[[str], None]] = None) -> List[Any]:
    """Drop items whose text is a cid-echo of our own act; log every suppression
    (SEC-4 RT-A12 — no silent drops). Empty own_cids ⇒ everything kept."""
    if not own_cids:
        return list(items)
    kept: List[Any] = []
    for it in items:
        txt = text_of(it)
        if is_cid_echo(txt, own_cids):
            if log:
                log("suppressed: cid-echo " + str(correlation.extract(txt))
                    + " — our own act re-captured (act->capture->act loop)")
        else:
            kept.append(it)
    return kept


# --- veto <-> ledger divergence audit [RT-B7] --------------------------------

def load_vetoes(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The captain-veto registry entries. TI-4 (a later wave) lands the file;
    absent / broken ⇒ [] (no vetoes ⇒ no divergence, graceful)."""
    try:
        import yaml
        data = yaml.safe_load(Path(path or _CAPTAIN_VETOES).read_text())
    except Exception:
        return []
    vs = data.get("vetoes") if isinstance(data, dict) else data
    return [v for v in (vs or []) if isinstance(v, dict)]


def _veto_matches(veto: Dict[str, Any], ev: Dict[str, Any]) -> bool:
    """Deterministic scope match against an acted event — action_type and/or lane
    only (fields carried on the ledger event), NEVER an LLM slug [RT-A10]. A veto
    scoped solely to a board (not a ledger-event field) can't be confirmed from
    the ledger alone and does not match here (surfaced separately as unverifiable
    rather than silently cleared)."""
    scope = veto.get("scope") or {}
    at = scope.get("action_type") or scope.get("kind")
    lane = scope.get("lane")
    if not (at or lane):
        return False                            # board-only / empty scope: not ledger-matchable
    if at and ev.get("action_type") != at:
        return False
    if lane and ev.get("lane") != lane:
        return False
    return True


def veto_ledger_divergences(*, vetoes: Optional[List[Dict[str, Any]]] = None,
                            ledger: Optional[List[Dict[str, Any]]] = None
                            ) -> List[Dict[str, Any]]:
    """The dangerous divergence [RT-B7]: an ACTIVE veto whose scope matches an
    acted event that occurred AT OR AFTER the veto was set — i.e. the lane acted
    on something the Captain vetoed (an enforcement gap). Each is a page."""
    vetoes = load_vetoes() if vetoes is None else vetoes
    ledger = read_ledger() if ledger is None else ledger
    acted = _acted_rows(ledger)
    out: List[Dict[str, Any]] = []
    for v in vetoes:
        if (v.get("status") or "active") != "active":
            continue
        vts = v.get("ts") or ""
        for ev in acted:
            if ev.get("ts", "") >= vts and _veto_matches(v, ev):
                out.append({
                    "veto_id": v.get("id"),
                    "acted_ts": ev.get("ts"),
                    "action_type": ev.get("action_type"),
                    "lane": ev.get("lane"),
                    "subject": ev.get("subject"),
                    "reason": "acted event matches an ACTIVE veto scope at/after "
                              "it was set — enforcement gap",
                })
    return out


# --- env-file perms check (cheap local hygiene, weekly) ----------------------

def env_perms_finding(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """A finding if the shared env file is group/other-readable (looser than
    0600). None when tight or absent. Deterministic, local, no secrets read."""
    p = Path(path or _SHARED_ENV)
    try:
        mode = p.stat().st_mode & 0o777
    except OSError:
        return None
    if mode & 0o077:
        return {"path": str(p), "mode": oct(mode),
                "reason": "env file is group/other-accessible — should be 0600"}
    return None


# --- synthetic canary: create -> verify -> reverse -> verify (journal-only) ---

def _canary_pid(step_kind: str) -> str:
    return "canary-" + step_kind + "-" + uuid.uuid4().hex[:12]


def _canary_actor() -> Dict[str, str]:
    # CANONICAL ACTOR ID (germline batch, 2026-07-04): the id is the BARE role
    # ("cos"), never "officer:cos" — consumers compose the query key as
    # "officer:" + role, so a pre-prefixed id yields "officer:officer:cos" and
    # severs canary/journal rows from the demotion-evidence reads. One emitter
    # contract across every module; the kind field already carries "officer".
    return {"kind": "officer", "id": "cos"}


def _journal_canary(pid: str, step: int, step_kind: str, backend: str, *,
                    created: Dict[str, Any], payload: Dict[str, Any],
                    prestate: Optional[Dict[str, Any]] = None,
                    now: Optional[str] = None) -> Dict[str, Any]:
    """Write ONE committed canary journal row (``canary:true``) — so the TTL
    sweep and the breaker skip it (a canary must never look like real acting)."""
    row = action_undo.new_row(
        pid=pid, cid="", step=step, kind=step_kind, backend=backend,
        lane="canary", subject=CANARY_PREFIX + " undo probe", actor=_canary_actor(),
        prestate=prestate or {}, created=created,
        inverse=action_undo.inverse_for(step_kind, backend, payload, created, prestate or {}),
        executed_at=now or _now(), canary=True)
    return action_undo.journal_step(row)


def _reverse_ok(res: Dict[str, Any]) -> bool:
    return bool(res.get("ok")) and not res.get("manual_cleanup") and not res.get("dead_letters")


def _canary_monday_create(pid: str, *, monday_post: Callable, osascript: Callable,
                          redis_del: Callable, board: str, date: str,
                          now: Optional[str]) -> Dict[str, Any]:
    from framework.frontdoor import action_exec
    payload = {"board_id": board,
               "title": CANARY_PREFIX + " undo probe " + date,
               "description": "synthetic undo-capability probe — safe to ignore; auto-reversed"}
    created = action_exec._exec_monday_create(payload, monday_post)
    if not created.get("monday_id"):
        raise RuntimeError("canary create returned no item id")
    _journal_canary(pid, 1, "monday_task_create", "monday",
                    created=created, payload=payload, now=now)
    res = action_undo.reverse(pid, monday_post=monday_post, osascript=osascript,
                              redis_del=redis_del, now=now)
    return {"created": created, "reverse": res}


# The pre-discovery hardcoded probe target ("status" column, label "Done").
# Kept ONLY as the fallback when column discovery gets no board data back — a
# minimal fake backend (tests/test_actfirst_canary.py FakeMonday answers only
# item reads + generic ids, no "boards" key) or a degraded API that answers
# without erroring. The literals are load-bearing for the fixture contract:
# the tests seed column "status" with text "Done" (clean roundtrip) / "Blocked"
# (drift → dead-letter → freeze). On a REAL board lacking that column the
# update still errors → the canary still freezes — fail-closed unchanged.
_LEGACY_PROBE_TARGET = {"col": "status", "mode": "label", "value": "Done"}


def _first_existing_label(settings_str: Optional[str]) -> Optional[str]:
    """The first non-empty label defined on a status column (parsed from its
    Monday ``settings_str`` JSON; digit keys in numeric index order so repeated
    canaries deterministically write the same label). None when unparseable or
    none defined — the caller then SKIPS that column, because writing a label
    the board does not define would, via the executor's mandatory
    ``create_labels_if_missing:true`` (action_exec.py:630, the People-board
    label-write gotcha), permanently add a canary label to the BOARD SCHEMA —
    a mutation the item-level compare-restore reverse does not undo."""
    try:
        parsed = json.loads(settings_str or "")
    except (ValueError, TypeError):
        return None
    labels = parsed.get("labels") if isinstance(parsed, dict) else None
    if not isinstance(labels, dict):
        return None

    def _order(k):
        # Monday label keys are the column's numeric indexes as strings; sort
        # digits numerically first, anything exotic after, lexicographically.
        s = str(k)
        return (0, int(s), "") if s.isdigit() else (1, 0, s)

    for k in sorted(labels, key=_order):
        v = labels.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _discover_probe_target(monday_post: Callable, board: str) -> Dict[str, Any]:
    """Pick a board_status probe target the TARGET BOARD actually supports.

    2026-07-04 fix: the probe used to hardcode column id ``status``, which
    board 5091706356 LACKS — Monday answered "This column ID doesn't exist for
    the board", so every weekly AND manual canary failed and the fail-closed
    freeze could never be lifted by a green run (freeze contract: no
    auto-unfreeze, action_undo.freeze:701). Discovery reads the board's own
    columns (read-only query; the board id travels as a GraphQL VARIABLE, never
    interpolated into the query body — same injection discipline as
    action_undo.query_columns:316) and picks, in order:

      1. a status-type column carrying an EXISTING label → label probe (the
         real board_status shape; an existing label leaves the board schema
         untouched despite ``create_labels_if_missing:true``);
      2. a date-type column → date probe (same executor loop and the
         ``kind:"date"`` compare-restore leg, action_undo._restore_one_column:412);
      3. otherwise → note probe (``set.note`` → create_update, reversed by
         delete_update via the journaled note_update_id) — every board supports
         item updates, so this is the universal reversible mutation of the same
         forward op; weaker (no column compare-restore leg exercised) but still
         a genuine create→verify→reverse proof, so it is the LAST resort;
      4. no boards/columns data in the response at all → the legacy
         ``status``/"Done" target (_LEGACY_PROBE_TARGET — fixtured fakes and
         degraded APIs; a real board that then rejects the column still fails
         → freezes).

    A discovery call that RAISES is deliberately NOT caught here: it propagates
    to run_canary's per-kind try/except → cannot-run → freeze. Discovery only
    CHOOSES the probe target — it can never lift, skip, or soften a freeze."""
    data = monday_post(
        "query($board: [ID!]) {"
        " boards(ids: $board) { columns { id type settings_str } } }",
        {"board": [str(board)]})
    boards = (data or {}).get("boards") or []
    first = boards[0] if boards and isinstance(boards[0], dict) else {}
    cols = first.get("columns") or []
    if not cols:
        return dict(_LEGACY_PROBE_TARGET)
    date_col: Optional[str] = None
    for c in cols:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        ctype = str(c.get("type") or "").lower()
        # "status" is the current API column-type enum; "color" is the legacy
        # name for the same class (Nate's boards carry ids like color_mm34crny).
        if ctype in ("status", "color"):
            label = _first_existing_label(c.get("settings_str"))
            if label:
                return {"col": str(c["id"]), "mode": "label", "value": label}
        elif ctype == "date" and date_col is None:
            date_col = str(c["id"])
    if date_col:
        return {"col": date_col, "mode": "date", "value": None}
    return {"col": None, "mode": "note", "value": None}


def _canary_board_status(pid: str, *, monday_post: Callable, osascript: Callable,
                         redis_del: Callable, board: str, date: str,
                         now: Optional[str]) -> Dict[str, Any]:
    """board_status needs a target: create a throwaway canary item, mutate it
    per the DISCOVERED probe target (_discover_probe_target — the board's own
    columns decide; the old hardcoded "status" id froze the kind permanently on
    boards without it), reverse (compare-restore / delete-update), then archive
    the throwaway (teardown). The UPDATE is the probe under test; scaffolding
    failure — discovery error or setup create — counts as cannot-run."""
    from framework.frontdoor import action_exec
    # Discover BEFORE the setup create: a discovery failure then freezes without
    # leaving an orphan throwaway item behind.
    target = _discover_probe_target(monday_post, board)
    setup = action_exec._exec_monday_create(
        {"board_id": board, "title": CANARY_PREFIX + " board_status probe " + date}, monday_post)
    item = setup.get("monday_id")
    if not item:
        raise RuntimeError("canary board_status setup returned no item id")
    if target["mode"] == "label":
        # prestate is keyed on the SAME discovered column id the write and the
        # inverse resolve (action_exec._exec_monday_update:624 and
        # action_undo._restore_args:339 both honor ``set.{col}_column``) — one
        # id end-to-end, or compare-restore would inspect the wrong column.
        prestate = action_undo.query_columns(monday_post, item, [target["col"]])
        upd_payload = {"monday_id": item, "board_id": board,
                       "set": {"status": target["value"],
                               "status_column": target["col"]}}
    elif target["mode"] == "date":
        prestate = action_undo.query_columns(monday_post, item, [target["col"]])
        upd_payload = {"monday_id": item, "board_id": board,
                       "set": {"due": date, "due_column": target["col"]}}
    else:
        # note probe: no column is touched, so there is no prestate to capture —
        # the inverse is delete_update by the journaled note_update_id
        # (action_undo._restore_args:349 → _inv_monday_compare_restore:447).
        prestate = {}
        upd_payload = {"monday_id": item, "board_id": board,
                       "set": {"note": CANARY_PREFIX
                               + " board_status note probe — auto-reversed"}}
    out = action_exec._exec_monday_update(upd_payload, monday_post)
    _journal_canary(pid, 1, "monday_task_update", "monday",
                    created=out, payload=upd_payload, prestate=prestate, now=now)
    res = action_undo.reverse(pid, monday_post=monday_post, osascript=osascript,
                              redis_del=redis_del, now=now)
    # teardown: archive the throwaway (best-effort — a lingering canary item is
    # loud-labelled and harmless; it does not fail the probe verdict).
    try:
        monday_post("mutation($item: ID!) { archive_item(item_id: $item) { id } }",
                    {"item": str(item)})
    except Exception:
        pass
    return {"created": out, "reverse": res, "probe_target": target}


def _canary_calendar(pid: str, *, monday_post: Callable, osascript: Callable,
                     redis_del: Callable, board: str, date: str,
                     now: Optional[str]) -> Dict[str, Any]:
    from framework.frontdoor import action_exec
    # 03:00 the next day on the local Cabinet calendar (RT-A7 pin) — off-hours,
    # attendee-free, and reversed immediately.
    due = (_parse(now) + timedelta(days=1)).strftime("%Y-%m-%dT03:00")
    prev = os.environ.get("ACTION_LANE_CALENDAR")
    os.environ["ACTION_LANE_CALENDAR"] = "Cabinet"
    try:
        payload = {"title": CANARY_PREFIX + " undo probe " + date, "due_iso": due,
                   "notes": "synthetic undo-capability probe — auto-reversed"}
        created = action_exec._exec_calendar_event(payload, osascript)
    finally:
        if prev is None:
            os.environ.pop("ACTION_LANE_CALENDAR", None)
        else:
            os.environ["ACTION_LANE_CALENDAR"] = prev
    if not created.get("uid"):
        raise RuntimeError("canary calendar create returned no uid")
    _journal_canary(pid, 1, "reminder_create", "calendar",
                    created=created, payload=payload, now=now)
    res = action_undo.reverse(pid, monday_post=monday_post, osascript=osascript,
                              redis_del=redis_del, now=now)
    return {"created": created, "reverse": res}


_CANARY_HANDLERS = {
    "monday_task_create": _canary_monday_create,
    "monday_task_update": _canary_board_status,
    "reminder_create": _canary_calendar,
}


def run_canary(*, monday_post: Callable, osascript: Callable,
               redis_set: Optional[Callable[[str, str, Optional[int]], None]] = None,
               redis_get: Optional[Callable[[str], str]] = None,
               redis_del: Optional[Callable[[str], None]] = None,
               board: str = "5091706356", now: Optional[str] = None) -> Dict[str, Any]:
    """The weekly synthetic canary: for each act-first-eligible kind, create a
    synthetic artifact, verify it landed, reverse it, verify the reverse. ANY
    failure or cannot-run ⇒ freeze that kind's action_type (no auto-unfreeze).
    Transports are injected (fixtured in tests); ZERO consequence events emitted.
    Returns per-kind results + the frozen set + alert lines for the Chair/health
    surface (wiring those pings is a later, scheduled wave)."""
    date = _date(now)
    rdel = redis_del or _default_redis_del
    results: List[Dict[str, Any]] = []
    frozen: List[str] = []
    alerts: List[str] = []
    for step_kind, backend in canary_kinds():
        fk = kind_key(step_kind)
        pid = _canary_pid(step_kind)
        handler = _CANARY_HANDLERS.get(step_kind)
        entry: Dict[str, Any] = {"kind": step_kind, "action_type": fk, "backend": backend}
        try:
            if handler is None:
                raise RuntimeError("no canary handler for " + step_kind)
            r = handler(pid, monday_post=monday_post, osascript=osascript,
                        redis_del=rdel, board=board, date=date, now=now)
            ok = _reverse_ok(r.get("reverse") or {})
            entry.update({"ok": ok, "created": bool((r.get("created") or {})),
                          "reverse": r.get("reverse")})
            if r.get("probe_target"):
                # which column/mode the board_status probe actually exercised
                # (discovered per board, 2026-07-04) — the operator verifying a
                # manual green canary needs this to trust the lift.
                entry["probe_target"] = r["probe_target"]
            if not ok:
                raise RuntimeError("canary reverse did not cleanly complete")
        except Exception as e:
            entry.update({"ok": False, "error": str(e)[:200]})
            if not action_undo.is_frozen(fk, redis_get=redis_get):
                action_undo.freeze(fk, "canary failed/cannot-run: " + str(e)[:200],
                                   redis_set=redis_set, now=now)
                frozen.append(fk)
            alerts.append("CANARY FAILED — froze " + fk + " (" + step_kind + "): "
                          + str(e)[:160] + " — unfreeze only via a manual green canary")
        results.append(entry)
    return {"results": results, "frozen": frozen, "alerts": alerts, "date": date}


# --- weekly bundle -----------------------------------------------------------

def run_weekly(*, monday_post: Callable, osascript: Callable,
               ledger: Optional[List[Dict[str, Any]]] = None,
               redis_set: Optional[Callable[[str, str, Optional[int]], None]] = None,
               redis_get: Optional[Callable[[str], str]] = None,
               redis_del: Optional[Callable[[str], None]] = None,
               board: str = "5091706356", now: Optional[str] = None) -> Dict[str, Any]:
    """One weekly guard pass: canary + kind breaker + silence breaker + veto
    audit + env-perms. Pure orchestration over the injected transports; the
    scheduled runner (a later wave) wires the Chair/healthchecks pings from the
    ``alerts`` / ``pages`` it returns."""
    ledger = read_ledger() if ledger is None else ledger
    canary = run_canary(monday_post=monday_post, osascript=osascript,
                        redis_set=redis_set, redis_get=redis_get, redis_del=redis_del,
                        board=board, now=now)
    breaker = run_kind_breaker(ledger=ledger, redis_set=redis_set,
                              redis_get=redis_get, now=now)
    silence = run_silence_breaker(ledger=ledger, redis_set=redis_set,
                                 redis_del=redis_del, now=now)
    divergences = veto_ledger_divergences(ledger=ledger)
    perms = env_perms_finding()
    pages: List[str] = list(canary["alerts"])
    for d in divergences:
        pages.append("VETO DIVERGENCE — " + str(d.get("veto_id")) + " matched an "
                     "acted " + str(d.get("action_type")) + " on lane "
                     + str(d.get("lane")) + " at " + str(d.get("acted_ts")))
    if perms:
        pages.append("ENV PERMS — " + perms["reason"] + " (" + perms["mode"] + ")")
    return {"canary": canary, "breaker": breaker, "silence": silence,
            "veto_divergences": divergences, "env_perms": perms, "pages": pages}
