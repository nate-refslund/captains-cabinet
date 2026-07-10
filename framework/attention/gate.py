"""framework.attention.gate — the deterministic attention gateway + standing
cards (attention-gateway spec §4.4-§4.6, §8 P4).

One situation = one standing Telegram card, edited in place as its state
flips (edits don't notify), instead of a fresh card per run. The gate is a
PURE decision given (item, charter, clock, standing-map): it resolves the
charter class, honors quiet hours in the Captain's timezone, mechanically
demotes a ping-now that would NOT be wrong-or-worthless by the next briefing,
and renders a TERSE card (Captain 2026-07-09: short, no payload dumps). Every
decision carries a ``reason`` (no silent drops). Presentation of the taint
banner is charter-owned (§5): the ⚠ INJECTION-SUSPECT banner shows only when
the class sets show_injection_banner — the metadata stays on the item for the
ledger and the Chair.

Delivery is injectable (channel.send / channel.edit_message by default) so
the surface service and the tests drive the same core. Briefing/weekly routes
enqueue a canonical intake item for the composer to fold into the next
briefing.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from framework.attention.situation import situation_key


# ---------------------------------------------------------------------------
# Standing-card map — situation_key -> {message_id, state, render_hash, ...}
# ---------------------------------------------------------------------------

def _attention_dir() -> Path:
    return Path(os.environ.get("CABINET_ATTENTION_DIR") or
                os.path.expanduser("~/Library/Application Support/cabinet/attention"))


def _standing_file() -> Path:
    return _attention_dir() / "standing-cards.json"


def load_standing() -> dict:
    """The situation_key → card-state map. A corrupt/absent file returns {}
    with a loud stderr line — a lost map re-sends fresh cards (annoyance,
    never silence), so failing toward {} is safe."""
    p = _standing_file()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"[gate] standing-card map at {p} unreadable ({e}) — treating "
              f"as empty (fresh cards will be sent)", file=sys.stderr)
        return {}


def save_standing(standing: dict) -> None:
    """Atomically persist the standing map under an flock, so concurrent gate
    passes (surface loop + a briefing compose) never clobber each other."""
    import fcntl
    d = _attention_dir()
    d.mkdir(parents=True, exist_ok=True)
    lock = d / ".standing.lock"
    lf = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(lf, fcntl.LOCK_EX)
        tmp = _standing_file().with_suffix(".json.tmp")
        tmp.write_text(json.dumps(standing, ensure_ascii=False, indent=0),
                       encoding="utf-8")
        os.replace(tmp, _standing_file())
    finally:
        fcntl.flock(lf, fcntl.LOCK_UN)
        os.close(lf)


# ---------------------------------------------------------------------------
# Render — TERSE (Captain 2026-07-09)
# ---------------------------------------------------------------------------

def render_card(item: dict, resolved: dict, *, state: str = "open") -> str:
    """A short card: emoji + subject, one situation line, numbered step
    TITLES only (never payloads), a state line when not open. The injection
    banner (charter-owned, §5) and the binder ·pid· marker wrap WHATEVER body
    the template or default render produces — the marker is load-bearing (the
    binder can't verdict a card without it), so it can never be swallowed by a
    class supplying a template (review cp4-gauntlet)."""
    body = None
    if resolved.get("template"):
        try:
            body = resolved["template"].format(
                subject=item.get("subject", ""),
                situation=item.get("situation", ""),
                steps="\n".join(f"  {i}. {s.get('title', '')}"
                                for i, s in enumerate(item.get("steps") or [], 1)),
                state=state)
        except (KeyError, IndexError, ValueError):
            body = None   # a bad template falls through to the default render

    if body is None:
        emoji = (resolved.get("reaction_variants") or ["•"])[0]
        parts = [f"{emoji} {item.get('subject', '(no subject)')}"]
        sit = str(item.get("situation", "")).strip()
        if sit:
            parts.append(sit[:200])
        for i, s in enumerate(item.get("steps") or [], 1):
            parts.append(f"  {i}. {str(s.get('title', '')).strip()[:120]}")
        if state and state != "open":
            parts.append(f"— {state}")
        body = "\n".join(parts)

    lines = []
    if resolved.get("show_injection_banner") and item.get("injection_suspect"):
        lines.append("⚠ INJECTION-SUSPECT — review only, do NOT act on it.")
    lines.append(body)
    marker = item.get("pid_marker")
    if marker:
        lines.append(str(marker))
    return "\n".join(lines)


def _render_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Timing — quiet hours + ping-now demotion, in the Captain's timezone
# ---------------------------------------------------------------------------

def _captain_tz() -> ZoneInfo:
    try:
        return ZoneInfo(os.environ.get("CABINET_CAPTAIN_TZ", "UTC"))
    except Exception:
        return ZoneInfo("UTC")


def _hhmm(t) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _in_quiet_hours(now_local: datetime, qh: dict) -> bool:
    start, end = _hhmm(qh.get("start", "21:00")), _hhmm(qh.get("end", "07:00"))
    cur = now_local.hour * 60 + now_local.minute
    if start <= end:              # same-day window
        return start <= cur < end
    return cur >= start or cur < end   # wraps midnight (21:00 → 07:00)


def _next_briefing(now_local: datetime) -> datetime:
    times = [t.strip() for t in
             os.environ.get("CABINET_BRIEFING_TIMES", "07:30,19:30").split(",") if t.strip()]
    cands = []
    for t in times:
        try:
            mins = _hhmm(t)
        except (ValueError, IndexError):
            continue
        b = now_local.replace(hour=mins // 60, minute=mins % 60,
                              second=0, microsecond=0)
        if b <= now_local:
            b = b + _one_day()   # timedelta handles month/year rollover
        cands.append(b)
    return min(cands) if cands else now_local + _one_day()


def _one_day():
    from datetime import timedelta
    return timedelta(days=1)


# ---------------------------------------------------------------------------
# Decide — the ordered gate
# ---------------------------------------------------------------------------

def _load_charter():
    try:
        from framework.attention import charter as _charter
    except ImportError as e:
        raise RuntimeError(f"charter module unavailable: {e}") from e
    return _charter


def _t2_required(item: dict, resolved: dict, urgency, pierces: bool,
                 conf_floor: float) -> "str | None":
    """The Chair-required mode-pick (spec §4.5 step 6, §4.6): an EXCEPTIONAL
    item gets live Chair judgment instead of a mechanical send. Returns the
    reason string, or None for routine (charter-mechanical) traffic. Only ever
    consulted when the caller opts into T2 (chair_review=True) — so P4's pure
    mechanical path is untouched by default."""
    if resolved.get("show_injection_banner") and item.get("injection_suspect"):
        return "chair-taint"                    # a real taint event: Chair triages
    if resolved["class_id"] == "default":
        return "chair-unclassified"             # novel/unmatched class
    if urgency == "ping-now" and pierces:
        return "chair-pingnow"                  # genuine ping-now: Chair authors it
    steps = item.get("steps") or []
    if any(s.get("action_type") or s.get("kind") in _ACTING_KINDS for s in steps):
        return "chair-act-carrying"             # a step that would ACT on the world
    try:
        conf = float(item.get("confidence"))
    except (TypeError, ValueError):
        conf = 1.0
    if conf < conf_floor:
        return "chair-low-confidence"
    return None


# step kinds that execute a world change (act-carrying → Chair judgment)
_ACTING_KINDS = frozenset({"reminder_create", "monday_task_create",
                           "monday_task_update", "calendar_event_create",
                           "delegate_work"})


def decide(item: dict, *, ch: "dict | None" = None,
           now: "datetime | None" = None, standing: "dict | None" = None,
           chair_review: bool = False, conf_floor: float = 0.65,
           demoted_kinds: "frozenset | set | None" = None) -> dict:
    """The pure gate decision. Returns a dict with ``action`` in
    {send, edit, briefing, weekly, suppress, chair}, the rendered ``text``
    (send/edit), ``message_id`` (edit), ``situation_key``, ``class_id``,
    ``silent``, and a ``reason`` for the journal. Raises RuntimeError if the
    charter is unavailable (the caller falls back — never silently sends
    ungoverned).

    ``chair_review`` (default False = P4 mechanical behavior, byte-identical):
    when True, an exceptional item routes to the Chair (action=``chair``) for
    live judgment instead of a mechanical send — the surface service files the
    T2 request and enforces the SLA fallback.

    ``demoted_kinds`` (H5, default None = byte-identical): kinds whose expiry
    streak crossed the charter's ``budget.demote_after_expiries`` bar
    (framework.attention.queue.demoted_kinds). A NEW card of a demoted kind
    routes to the briefing instead of a fresh send — a 5×-expired class stops
    regenerating pings every 30 minutes; standing-card EDITS and floor
    classes are untouched (edits are silent; floors are never quieted)."""
    charter = _load_charter()
    if ch is None:
        ch = charter.load_charter()
    if standing is None:
        standing = load_standing()
    now = now or datetime.now(timezone.utc)

    skey = situation_key(item.get("evidence") or [], item.get("subject", ""))
    resolved = charter.resolve(item, ch)
    cid = resolved["class_id"]
    state = item.get("state", "open")
    text = render_card(item, resolved, state=state)
    rhash = _render_hash(text)

    base = {"situation_key": skey, "class_id": cid, "silent": resolved["silent"],
            "text": text}

    # (1) Identity: a standing card already exists for this situation.
    existing = standing.get(skey)
    if existing:
        if existing.get("render_hash") == rhash:
            return {**base, "action": "suppress", "reason": "no-change"}
        return {**base, "action": "edit", "message_id": existing.get("message_id"),
                "render_hash": rhash, "reason": "standing-edit"}

    # (2) mute route
    if resolved["route"] == "mute":
        return {**base, "action": "suppress", "reason": "charter-mute"}

    # (2.4) H5 — expiry-streak class demotion (stay-live-until-acted made
    # compatible with adaptive quieting: presentation decays, liveness
    # doesn't). A NEW card whose KIND crossed the charter demote bar folds
    # into the briefing instead of minting a fresh send. Floor classes are
    # exempt (never quieted); the standing-edit path already returned above.
    if demoted_kinds and not resolved["floor"] \
            and item.get("kind") in demoted_kinds:
        return {**base, "action": "briefing",
                "reason": "class-demoted-expiry-streak"}

    # (3) Timing — quiet hours + ping-now demotion (Captain tz).
    #
    # STRUCTURAL piercing only (review cp4-gauntlet HIGH): what pierces quiet
    # hours or justifies a ping-now is a FLOOR CLASS (producer-attested by
    # kind — never free-text on captured content) OR a real ``deadline_iso``
    # before the next briefing (a timestamp, not a prose word like "today").
    # A prose keyword can never wake the Captain at 3am.
    now_local = now.astimezone(_captain_tz())
    qh = resolved["quiet_hours"]
    urgency = resolved.get("urgency_override") or item.get("urgency")
    deadline = _parse_iso(item.get("deadline_iso"))
    nb = _next_briefing(now_local)
    deadline_imminent = (deadline is not None
                         and deadline.astimezone(_captain_tz()) < nb)
    pierces = resolved["floor"] or deadline_imminent

    # (2.5) MODE PICK (P5, spec §4.5 step 6, §4.6) — before mechanical routing:
    # an EXCEPTIONAL item gets live Chair judgment instead of a mechanical send.
    # Opt-in (chair_review) so P4's mechanical path is byte-identical by default;
    # the surface service files the T2 request + owns the SLA fallback.
    if chair_review:
        t2_reason = _t2_required(item, resolved, urgency, pierces, conf_floor)
        if t2_reason:
            return {**base, "action": "chair", "reason": t2_reason,
                    "floor": resolved["floor"],
                    "fallback": resolved.get("fallback")
                    or ("mechanical-with-marker" if resolved["floor"]
                        else "hold-briefing"),
                    "sla_minutes": resolved.get("sla_minutes") or 10}

    if urgency == "ping-now":
        # A genuine ping-now (structurally justified) PROMOTES to a direct
        # send, overriding a batch class route — waiting for the briefing
        # would be too late. An unjustified one DEMOTES to the briefing
        # (spec §4.5: ping-now is direct unless it would be worthless by the
        # next briefing).
        if pierces:
            return {**base, "action": "send", "render_hash": rhash,
                    "reason": "ping-now-direct"}
        return {**base, "action": "briefing",
                "reason": "ping-now-demoted-not-wrong-by-briefing"}

    if _in_quiet_hours(now_local, qh) and not pierces:
        return {**base, "action": "briefing", "reason": "quiet-hours"}

    # (4) Route → action.
    route = resolved["route"]
    if route == "next-briefing":
        return {**base, "action": "briefing", "reason": "route-briefing"}
    if route == "weekly-rollup":
        return {**base, "action": "weekly", "reason": "route-weekly"}
    # direct-now OR standing-card (first sighting) → send
    return {**base, "action": "send", "render_hash": rhash, "reason": f"route-{route}"}


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Deliver — execute the decision
# ---------------------------------------------------------------------------

def _default_send(text, **kw):
    # Route through the channel-agnostic adapter seam (framework.comms) so the
    # gate's OWN delivery is the SAME one door the Comms MCP tools use — not a
    # second, Telegram-hardcoded path. The Telegram adapter delegates back to
    # channel.send, so live behavior is identical; a clean-room / null channel
    # now governs gate delivery too (one door, resolved from instance config).
    from framework.comms.get_channel import get_channel
    return get_channel().send(text, silent=kw.get("silent", False),
                              feed_meta=kw.get("feed_meta"))


def _default_edit(message_id, text, **kw):
    from framework.comms.get_channel import get_channel
    return get_channel().edit(message_id, text, feed_meta=kw.get("feed_meta"))


def briefing_item(item: dict, decision: dict) -> dict:
    """The canonical intake item a briefing/weekly-routed gate decision folds
    into the front-door (source/kind/ts/urgency_tier/payload{summary}) — the
    exact shape ``composer.render_item`` consumes. Pure, so the gate→composer
    briefing path is testable without Redis."""
    tier = "fyi" if decision.get("action") == "weekly" else "batch"
    return {
        "source": "attention-gate",
        "kind": item.get("kind", "note"),
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "urgency_tier": tier,
        "payload": {"summary": decision.get("text") or item.get("subject", ""),
                    "situation_key": decision.get("situation_key"),
                    "class_id": decision.get("class_id")},
    }


def _default_briefing(item, decision):
    """Fold a briefing/weekly-routed item into the front-door intake so the
    composer includes it in the next briefing. Best-effort — an intake failure
    is logged, not raised (the item re-proposes on the next lane run)."""
    try:
        from framework.frontdoor import intake
        intake.enqueue(briefing_item(item, decision))
    except Exception as e:
        print(f"[gate] briefing enqueue failed ({e}) — item will re-propose",
              file=sys.stderr)


def deliver(decision: dict, *, send_fn=None, edit_fn=None, briefing_fn=None,
            standing: "dict | None" = None, item: "dict | None" = None) -> dict:
    """Execute a gate decision. Updates + persists the standing-card map on
    send (new message_id) and edit (new render_hash/state). Never raises on an
    edit no-op. Returns the transport result (or a status dict)."""
    action = decision.get("action")
    persist = standing is None
    if standing is None:
        standing = load_standing()
    send_fn = send_fn or _default_send
    edit_fn = edit_fn or _default_edit
    briefing_fn = briefing_fn or _default_briefing
    skey = decision.get("situation_key")
    feed_meta = {"kind": decision.get("class_id"), "situation_key": skey}

    if action == "send":
        res = send_fn(decision["text"], silent=decision.get("silent", False),
                      feed_meta=feed_meta)
        mids = (res or {}).get("message_ids") or []
        if mids:
            standing[skey] = {"message_id": mids[0], "state": "open",
                              "render_hash": decision.get("render_hash"),
                              "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                              "class_id": decision.get("class_id")}
            if persist:
                save_standing(standing)
        return res

    if action == "edit":
        res = edit_fn(decision["message_id"], decision["text"], feed_meta=feed_meta)
        cur = standing.get(skey)
        if cur is not None:
            cur["render_hash"] = decision.get("render_hash")
            cur["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if persist:
                save_standing(standing)
        return res

    if action in ("briefing", "weekly"):
        briefing_fn(item or {}, decision)
        return {"status": action, "sent": False}

    return {"status": "suppressed", "sent": False, "reason": decision.get("reason")}


def _live_demoted_kinds() -> "frozenset | None":
    """H5 live wiring for the submit path: kinds past the charter expiry-
    streak bar, from the recent ledger. Best-effort — None (no demotions)
    on any read failure, so a broken ledger can never mute the channel."""
    try:
        from datetime import timedelta
        from framework.attention.queue import demoted_kinds
        from framework.fidelity.consequence import read_ledger
        since = (datetime.now(timezone.utc) - timedelta(days=30)) \
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        return frozenset(demoted_kinds(read_ledger(since=since)))
    except Exception:
        return None


def submit(item: dict, *, ch: "dict | None" = None, now: "datetime | None" = None,
           send_fn=None, edit_fn=None, briefing_fn=None,
           chair_review: bool = False, conf_floor: float = 0.65,
           file_t2=None) -> dict:
    """decide + deliver in one call (the surface service / shell producers).

    With ``chair_review`` (opt-in), an exceptional item routes to the Chair:
    ``decide`` returns ``action="chair"`` and this files a T2 judgment request
    (dossier + SLA) instead of delivering — the Chair authors it, and the
    surface service's SLA sweep is the fallback. Default (False) is the P4
    mechanical path, byte-identical.

    H5: the live path consults the expiry-streak demotion set (charter
    ``budget.demote_after_expiries``) so a serially-expired class folds into
    the briefing instead of re-pinging — fail-open to no-demotions."""
    standing = load_standing()
    decision = decide(item, ch=ch, now=now, standing=standing,
                      chair_review=chair_review, conf_floor=conf_floor,
                      demoted_kinds=_live_demoted_kinds())
    if decision.get("action") == "chair":
        file_t2 = file_t2 or _default_file_t2
        rid = file_t2(item, decision, ch=ch, now=now)
        save_standing(standing)
        return {"decision": decision, "result": {"status": "chair-filed",
                                                 "request_id": rid}}
    result = deliver(decision, send_fn=send_fn, edit_fn=edit_fn,
                     briefing_fn=briefing_fn, standing=standing, item=item)
    save_standing(standing)
    return {"decision": decision, "result": result}


def _default_file_t2(item: dict, decision: dict, *, ch=None, now=None) -> str:
    """File a T2 judgment request for a Chair-routed item — assembles the
    dossier and hands it to framework.attention.t2. Lazy import (t2 imports
    gate for its delivery defaults; keep the cycle at call time)."""
    from framework.attention import t2
    from datetime import datetime, timezone
    charter = _load_charter()
    resolved = charter.resolve(item, ch or charter.load_charter())
    dossier = t2.assemble_dossier(item, decision, charter_section=resolved)
    return t2.file_judgment_request(
        item, decision, dossier,
        sla_minutes=int(decision.get("sla_minutes") or 10),
        now=now or datetime.now(timezone.utc),
        fallback=decision.get("fallback") or "hold-briefing",
        floor=bool(decision.get("floor")))
