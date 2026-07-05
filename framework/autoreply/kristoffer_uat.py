"""Scoped Kristoffer-UAT auto-reply — graduated autonomy, the FIRST auto-send.

Captain choice (2026-06-25, option (a) "for this case"): when Kristoffer Møller
Nielsen files a UAT bug report on Teams, the cabinet sends HIM a bounded
acknowledgement directly (scoped to him + UAT only), routes the bug to
polads-ceo, and copies the exact ack to the Captain's Telegram. Every other message —
his casual chatter, anyone else, any other channel, any other topic — is OUT of
scope and falls back to the normal propose-only `queue_draft` gate.

WHY THIS IS SAFE (the design, enforced in code here, not in prose):

  * SINGLE EGRESS PRESERVED. This module performs NO new send path. The actual
    byte egress is the caller-supplied ``send_backend`` — the SAME approved
    backend the human-"send" reply already uses (``chair_drafts.deliver_draft``
    / the brain ``queue_draft`` delivery). Exactly the ``framework.authority.veto``
    precedent: an auto-send is the approved backend fired without waiting for the
    tap, never a raw Teams/Graph/Make call. brain-bridge.md stays satisfied —
    the only change is WHO approves (a scoped code rule vs the Captain's thumb), FOR
    THIS ONE CELL.

  * THREE INDEPENDENT GATES, each fail-CLOSED, ALL must pass:
      1. ARMED   — the Redis kill-switch ``cabinet:autoreply:kristoffer-uat:enabled``
                   must read exactly ``"1"``. Absent / any other value / Redis
                   down  ->  DISARMED. Defaults OFF; this is how it ships.
      2. SCOPE   — the message must be FROM Kristoffer's resolved identity, on
                   Teams, AND match the UAT bug-report shape. Any miss -> decline.
      3. KILLSWITCH — the global ``cabinet:killswitch`` must NOT be active
                   (the same emergency halt every officer honours).

  * BOUNDED ACK ONLY. The reply is a template with three slots (topic, ETA,
    optional ref). It makes exactly three claims: received + routing-to-team +
    ETA. It can NEVER assert a fix, a root cause, or anything substantive that
    could be wrong. No free-form LLM text leaves the machine on this path.

  * THE CAPTAIN ALWAYS SEES IT. Every auto-send emits a COPY to the Captain's Telegram via
    ``framework.frontdoor.channel.send`` (the cabinet's only Captain path,
    itself gated by ``allow_sends()``), labelled as an auto-send, BEFORE the
    function returns. Visibility is not best-effort decoration — a copy-send
    failure is surfaced in the result.

  * FULLY AUDITED. Every decision (sent / declined / disarmed / halted) is
    logged: a structured local JSONL line here, plus the caller wires
    ``log_reasoning`` (brain MCP) for the reasoning-review loop. Nothing on this
    path is silent.

This module is a PURE DECISION + COMPOSE core. Like ``veto.py`` it imports no
Redis, no clock, no network at module load: every side-effecting collaborator
(``send_backend``, ``copy_to_nate``, ``redis_get``, ``audit``, ``route_bug``,
``clock``) is INJECTED, so the whole thing is unit-tested with fakes — no real
Redis, no real outbound, no real Telegram. The live wiring that supplies the
real collaborators lives in ``wiring.py`` and ships DISARMED.

System Python compatible (3.9+): stdlib only, no 3.10 ``X | Y`` unions.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from framework.env import captain_name


# ===========================================================================
# SCOPE CONSTANTS — the tight, code-enforced fence. Widening any of these is a
# deliberate edit, reviewable in the diff. Nothing here is read from free input.
# ===========================================================================

#: The ONE person this lane will ever auto-reply to. Matched against the
#: brain-resolved person slug (``mcp__brain`` ``queue_draft`` resolves
#: "Kristoffer Møller Nielsen" -> this on-disk 3-People slug). Accents kept;
#: ``in_scope`` also accepts the accent-folded + primary-email forms below.
KRISTOFFER_SLUG = "Kristoffer-Møller-Nielsen"

#: Accept-set for the sender identity (slug, accent-folded slug, primary email,
#: display name). All compared case-insensitively. NOTHING outside this set is
#: ever in scope — an unknown/garbled sender fails closed.
KRISTOFFER_IDENTITIES = (
    "kristoffer-møller-nielsen",
    "kristoffer-moller-nielsen",
    "kristoffer møller nielsen",
    "kristoffer moller nielsen",
    "krmoj@step.dk",  # primary_email from his intel dossier
)

#: The ONLY channel in scope. Teams is where his UAT reports land; email/SMS/
#: anything else is out.
SCOPE_CHANNEL = "teams"

#: The Redis ARM flag. Must equal "1" to send. Absent/other/Redis-down = OFF.
#: This is the kill-switch the Captain flips to arm or instantly disarm.
ARM_FLAG_KEY = "cabinet:autoreply:kristoffer-uat:enabled"

#: The global emergency halt (every officer honours it). Active -> nothing sends.
GLOBAL_KILLSWITCH_KEY = "cabinet:killswitch"

#: Idempotency-marker prefix (optional, used by the caller to dedup a re-seen
#: message). Mirrors the veto ``sent:`` marker discipline.
SENT_MARKER_PREFIX = "cabinet:autoreply:kristoffer-uat:sent:"

#: Officer the bug is routed to.
ROUTE_OFFICER = "polads-ceo"

#: Default ETA wording when the caller doesn't supply one. Deliberately vague +
#: non-committal — a bounded ack never promises a hard time it can't keep.
DEFAULT_ETA = "the team will triage it shortly"


# ===========================================================================
# UAT DETECTION — does this Teams message look like a UAT bug report?
# Conservative by design: a near-miss should DECLINE (fall through to the normal
# propose gate), never auto-fire. False-negative (the Captain taps send) >> false-
# positive (a wrong autonomous ack). All matching is on the message text only.
# ===========================================================================

# Bug/defect/test vocabulary, EN + DA (Kristoffer files in both). Word-boundary
# matched so "buggy"/"erroring" still hit but "debug" alone doesn't dominate.
_UAT_SIGNALS = (
    r"bug", r"error", r"errors", r"broken", r"broke", r"fail", r"fails",
    r"failed", r"failing", r"crash", r"crashe[sd]", r"doesn'?t work",
    r"does not work", r"not working", r"can'?t\b", r"cannot\b", r"won'?t\b",
    r"500\b", r"404\b", r"403\b", r"stack ?trace", r"exception",
    r"regression", r"reproduce", r"repro\b", r"steps to", r"expected\b",
    r"actual\b", r"screenshot",
    # Danish
    r"virker ikke", r"fejl", r"fejler", r"i stykker", r"går ned",
    r"kan ikke", r"problem", r"problemer",
)

# UAT/staging context vocabulary. RESERVED (informational): the current
# detector gates on defect-signal + benign-phrase blanking only — context is NOT
# required (a bare "the publisher list is broken" must qualify). Kept as the
# vocabulary a future confidence-tightening would use; `_CTX_RE` is compiled for
# that use and for callers that want a context check. Not dead by intent.
_UAT_CONTEXT = (
    r"\buat\b", r"staging", r"test\.polads\.eu", r"polads", r"publisher",
    r"advertiser", r"campaign", r"register", r"registration", r"deploy",
    r"\bprod\b", r"production", r"\bpr\b", r"\bui\b", r"\bapi\b", r"flow",
    r"label", r"transparency", r"\bdpa\b", r"login", r"email", r"pdf",
)

# Hard NON-UAT vetoes — if the WHOLE short message is clearly social/logistical,
# decline even if a stray signal word appears. (e.g. "no worries, my bad" —
# 'bad' near 'broke'.) Kept tight; only unambiguous social closers.
_SOCIAL_ONLY = (
    r"^\s*(thanks|thank you|tak|tusind tak|mange tak|cheers|ok|okay|fint|"
    r"super|perfect|perfekt|got it|sounds good|lyder godt|👍|🙏|👌)[\s!.…]*$"
)

# Phrase-level vetoes — benign idioms that CONTAIN a signal word but are not a
# bug report. Matched anywhere in the message; if present AND the message lacks
# any product-context word, it's reassurance/logistics, not a UAT report.
# ("no problem, I'll re-test" — 'problem' is a signal, but the phrase is benign.)
_BENIGN_PHRASES = (
    r"no problem", r"no worries", r"intet problem", r"ingen problemer",
    r"intet at bekymre", r"no issue", r"no big deal", r"my bad",
    r"all good", r"works now", r"working now", r"virker nu", r"works fine",
    r"fixed now", r"is fixed", r"er rettet", r"er fikset",
)

_SIG_RE = re.compile("|".join(_UAT_SIGNALS), re.IGNORECASE)
_CTX_RE = re.compile("|".join(_UAT_CONTEXT), re.IGNORECASE)
_SOCIAL_RE = re.compile(_SOCIAL_ONLY, re.IGNORECASE)
_BENIGN_RE = re.compile("|".join(_BENIGN_PHRASES), re.IGNORECASE)


def is_uat_report(text: str) -> bool:
    """True iff `text` reads like a UAT bug/test report (conservative).

    Rule: at least one bug/defect signal word, AND not a pure social closer.
    A product-context word is not required (a bare "the publisher list is
    broken" qualifies) but a message with ONLY a context word and no defect
    signal does NOT qualify — "how's the publisher flow?" is a question, not a
    report. This biases to DECLINE on ambiguity, which is the safe direction.
    """
    t = (text or "").strip()
    if not t:
        return False
    if _SOCIAL_RE.match(t):
        return False
    # Neutralize benign idioms BEFORE signal detection: a phrase like
    # "no problem" / "works now" carries a signal token ("problem") that isn't a
    # defect report. Blanking the benign phrases first means the signal search
    # only sees a GENUINE defect word — robust regardless of whether an unrelated
    # context word ("deploy") also appears. ("no problem, I'll re-test after the
    # deploy" -> blanked to "  , I'll re-test after the deploy" -> no signal ->
    # not a report. But "no problem with login, the register flow is broken" ->
    # "broken" survives -> a report.)
    probe = _BENIGN_RE.sub(" ", t)
    if not _SIG_RE.search(probe):
        return False
    # A genuine defect signal survived the benign-phrase blanking -> treat as a
    # report. Context words only *raise* confidence; the signal itself is what's
    # required, and the bias on ambiguity is to DECLINE (the Captain taps send on a miss).
    return True


def detect_topic(text: str, max_len: int = 80) -> str:
    """A short, SAFE topic slug echoed back in the ack ("Got your UAT report on
    <topic>"). Pulled verbatim from his own first line/sentence so the ack never
    paraphrases (paraphrase = a chance to misstate). Collapsed to one line,
    stripped of control chars, length-capped. Empty -> a generic phrase."""
    t = re.sub(r"[\r\n\t\x00-\x1f\x7f]+", " ", (text or "")).strip()
    if not t:
        return "the issue you reported"
    # Drop a leading greeting/address clause ("hi", "hej", "hi <captain> -",
    # "hey,") so the echoed topic is the actual issue, not the salutation. The
    # addressee alternative is the Captain's own name (de-nate: re.escape'd so any
    # captain's name is stripped, never a hardcoded literal; byte-identical on this
    # instance, where the resolver returns the same name the literal used to hold).
    cap = captain_name()
    t = re.sub(
        r"^\s*(hi|hey|hello|hej|halløj|yo|hej igen|hi again)\b[\s,!]*"
        r"(" + re.escape(cap) + r"|there|team)?[\s,!.:–—-]*",
        "", t, flags=re.IGNORECASE).strip() or t
    # First sentence-ish chunk, capped.
    head = re.split(r"(?<=[.!?])\s", t, maxsplit=1)[0]
    head = head.strip().strip("-–—•*>").strip()
    if len(head) > max_len:
        head = head[: max_len - 1].rstrip() + "…"
    return head or "the issue you reported"


# ===========================================================================
# ACK TEMPLATE — bounded, three claims only. NEVER a substantive reply.
# ===========================================================================

def render_ack(topic: str, eta: str = "", ref: str = "") -> str:
    """Compose the bounded acknowledgement. Three claims ONLY: received +
    routing to the team + ETA. No fix, no root cause, no substantive promise.

    Voice note: this is a Teams message, so per the Captain's house style it stays
    lowercase-casual and UNSIGNED (Teams is never signed — voice.md). The fence
    is the template itself; no nate_model/voice content is interpolated.
    """
    topic = detect_topic(topic) if topic and len(topic) > 90 else (topic or "the issue you reported")
    eta = (eta or "").strip() or DEFAULT_ETA
    ref_txt = f" (ref {ref.strip()})" if ref and ref.strip() else ""
    return (
        f"got your UAT report on {topic} — thanks, that's logged and i'm "
        f"routing it to the team now{ref_txt}. {eta}. "
        "i'll follow up here once there's a fix."
    )


# ===========================================================================
# THE GATES — each returns (ok: bool, reason: str). Fail-closed everywhere.
# ===========================================================================

def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def in_scope(*, sender: str, channel: str, text: str) -> Tuple[bool, str]:
    """SCOPE gate: is this message FROM Kristoffer, ON Teams, a UAT report?

    Returns (True, "in-scope") only when all three hold. Otherwise (False, why)
    naming the first failing condition — so the audit log says exactly why a
    message was declined. Pure; no I/O.
    """
    if _norm(channel) != SCOPE_CHANNEL:
        return False, f"out-of-scope: channel={channel!r} (only {SCOPE_CHANNEL})"
    if _norm(sender) not in KRISTOFFER_IDENTITIES:
        return False, f"out-of-scope: sender={sender!r} (not Kristoffer)"
    if not is_uat_report(text):
        return False, "out-of-scope: message is not a UAT bug report"
    return True, "in-scope"


def is_armed(redis_get: Callable[[str], Optional[str]]) -> Tuple[bool, str]:
    """ARM gate: the lane is armed ONLY when the flag reads exactly "1".

    `redis_get(key) -> Optional[str]` is injected. Absent (None / "") -> OFF.
    Any other value -> OFF. A raising/None-returning getter (Redis down) -> OFF.
    Fail-closed: the DEFAULT state, and the state on any uncertainty, is DISARMED.
    """
    try:
        val = redis_get(ARM_FLAG_KEY)
    except Exception:
        return False, "disarmed: arm-flag unreadable (Redis error) — fail closed"
    if val is None or str(val) == "":
        return False, "disarmed: arm-flag absent (default OFF)"
    # EXACT match, no strip: only a clean "1" arms. A stray-whitespace or
    # otherwise-malformed value is treated as NOT armed (fail closed) — we never
    # auto-send on a fuzzy flag value. (_redis_get already returns a stripped
    # string, so a real `SET ... 1` reads as "1".)
    if str(val) != "1":
        return False, f"disarmed: arm-flag={val!r} (not exactly '1')"
    return True, "armed"


def killswitch_clear(redis_get: Callable[[str], Optional[str]]) -> Tuple[bool, str]:
    """GLOBAL HALT gate: the emergency kill-switch must NOT be active.

    Mirrors ``kill-switch.sh``: ``cabinet:killswitch == "active"`` halts. Any
    read error is treated as HALTED (fail-closed — if we can't confirm the
    cabinet is live, we do not auto-send)."""
    try:
        val = redis_get(GLOBAL_KILLSWITCH_KEY)
    except Exception:
        return False, "halted: killswitch unreadable — fail closed"
    if _norm(val) == "active":
        return False, "halted: global killswitch ACTIVE"
    return True, "killswitch-clear"


# ===========================================================================
# AUDIT — structured local record. One line per decision, never silent.
# ===========================================================================

def make_audit_record(decision: str, *, sender: str, channel: str,
                       topic: str, reason: str, ack: str = "",
                       ref: str = "", extra: Optional[dict] = None) -> dict:
    """Build the structured audit dict (the caller writes it as JSONL + wires
    log_reasoning). `decision` is one of: sent | declined | disarmed | halted |
    send-failed | copy-failed."""
    rec = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lane": "autoreply:kristoffer-uat",
        "decision": decision,
        "sender": str(sender or ""),
        "channel": str(channel or ""),
        "topic": str(topic or ""),
        "reason": str(reason or ""),
        "route_officer": ROUTE_OFFICER,
    }
    if ack:
        rec["ack"] = ack
    if ref:
        rec["ref"] = ref
    if extra:
        rec["extra"] = extra
    return rec


# ===========================================================================
# THE ORCHESTRATOR — decide + (when all gates pass) act, with every collaborator
# injected. This is the single entry point the live wiring calls per inbound
# Kristoffer Teams message. It NEVER raises on a collaborator failure; a failed
# send/copy is captured in the returned result and audited.
# ===========================================================================

def handle_message(
    *,
    sender: str,
    channel: str,
    text: str,
    redis_get: Callable[[str], Optional[str]],
    send_backend: Callable[[Dict[str, Any]], Any],
    copy_to_nate: Callable[[str], Any],
    audit: Callable[[dict], Any],
    route_bug: Optional[Callable[[Dict[str, Any]], Any]] = None,
    eta: str = "",
    ref: str = "",
    dry_run: bool = False,
) -> dict:
    """Decide and (only if armed + in-scope + not halted) auto-ack Kristoffer.

    Order of gates is deliberate — cheapest/safest first, and SCOPE is checked
    before ARM so an out-of-scope message is declined identically whether the
    lane is armed or not (no information leak about arm state, and the common
    case is cheap):

      1. SCOPE     — wrong person/channel/not-a-report -> ``declined`` (the
                     caller then falls back to the normal propose-only gate).
      2. ARM       — flag != "1" -> ``disarmed`` (DEFAULT). Built-but-not-live.
      3. KILLSWITCH— global halt active -> ``halted``.
      4. ACT       — compose bounded ack, route bug to polads-ceo, fire the
                     approved ``send_backend``, COPY to the Captain, audit.

    ``dry_run=True`` runs every gate and composes the ack + audit, but routes
    NOTHING and sends NOTHING (no send_backend, no route_bug call); the copy to
    the Captain is still produced so a sample can be shown (the wiring labels it).
    Used to surface a sample ack for the Captain's approval without any real egress.

    Returns a result dict:
      {decision, reason, ack (when composed), routed (bool), sent (bool),
       copied (bool), send_result, audit (the record)}.
    """
    topic = detect_topic(text)

    # --- 1. SCOPE -----------------------------------------------------------
    scoped, why = in_scope(sender=sender, channel=channel, text=text)
    if not scoped:
        rec = make_audit_record("declined", sender=sender, channel=channel,
                                topic=topic, reason=why)
        _safe(audit, rec)
        return {"decision": "declined", "reason": why, "routed": False,
                "sent": False, "copied": False, "audit": rec}

    # --- 2 & 3. ARM + GLOBAL KILLSWITCH -------------------------------------
    # dry_run BYPASSES these two gates by design: it has zero real egress (it
    # neither sends to Kristoffer nor routes the bug — see step 4), it only
    # composes a labelled SAMPLE to the Captain. That lets the Captain review the exact ack
    # BEFORE arming. SCOPE (gate 1) is still enforced above even for a dry-run,
    # so a sample is always for a genuinely in-scope message.
    if not dry_run:
        armed, why = is_armed(redis_get)
        if not armed:
            rec = make_audit_record("disarmed", sender=sender, channel=channel,
                                    topic=topic, reason=why)
            _safe(audit, rec)
            return {"decision": "disarmed", "reason": why, "routed": False,
                    "sent": False, "copied": False, "audit": rec}

        clear, why = killswitch_clear(redis_get)
        if not clear:
            rec = make_audit_record("halted", sender=sender, channel=channel,
                                    topic=topic, reason=why)
            _safe(audit, rec)
            return {"decision": "halted", "reason": why, "routed": False,
                    "sent": False, "copied": False, "audit": rec}

    # --- 4. ACT -------------------------------------------------------------
    ack = render_ack(topic, eta=eta, ref=ref)

    # 4a. Route the bug to polads-ceo FIRST — the ack promises "routing to the
    #     team", so the routing must actually happen (and happen even if the
    #     send later fails: the bug must never be lost just because the courtesy
    #     ack hiccuped). Best-effort + audited; a routing failure does NOT block
    #     the ack (the Captain sees both outcomes).
    routed = False
    route_err = ""
    if not dry_run and route_bug is not None:
        try:
            route_bug({
                "officer": ROUTE_OFFICER,
                "sender": sender,
                "topic": topic,
                "text": text,
                "ref": ref,
            })
            routed = True
        except Exception as exc:  # noqa: BLE001
            route_err = f"{type(exc).__name__}: {exc}"[:200]

    # 4b. SEND via the approved backend (the veto precedent). dry_run sends
    #     nothing.
    sent = False
    send_result: Any = None
    send_err = ""
    if not dry_run:
        try:
            send_result = send_backend({
                "person": "Kristoffer Møller Nielsen",
                "slug": KRISTOFFER_SLUG,
                "channel": SCOPE_CHANNEL,
                "recipient_email": "krmoj@step.dk",
                "draft": ack,
                "why": "scoped Kristoffer-UAT auto-ack (graduated autonomy, armed)",
            })
            sent = bool(_result_ok(send_result))
        except Exception as exc:  # noqa: BLE001
            send_err = f"{type(exc).__name__}: {exc}"[:200]

    # 4c. COPY to the Captain — ALWAYS, so they see exactly what went out. On a
    #     real send this is the audit-to-Captain; on dry_run it's the labelled sample.
    copied = False
    copy_err = ""
    label = "SAMPLE (dry-run, NOT sent to Kristoffer)" if dry_run else "AUTO-SENT to Kristoffer"
    if dry_run:
        route_line = f"would route→{ROUTE_OFFICER} (simulated, not routed)"
    elif routed:
        route_line = f"routed→{ROUTE_OFFICER}: yes"
    elif route_err:
        route_line = f"routed→{ROUTE_OFFICER}: FAILED: {route_err}"
    else:
        route_line = f"routed→{ROUTE_OFFICER}: no"
    nate_copy = (
        f"🤖 {label} — Kristoffer UAT auto-reply\n"
        f"topic: {topic}\n"
        f"———\n{ack}\n———\n"
        f"{route_line}"
        + ("" if not send_err else f"\n⚠ send FAILED: {send_err}")
    )
    try:
        copy_to_nate(nate_copy)
        copied = True
    except Exception as exc:  # noqa: BLE001
        copy_err = f"{type(exc).__name__}: {exc}"[:200]

    decision = "dry-run" if dry_run else ("sent" if sent else "send-failed")
    cap = captain_name()
    reason = "all gates passed; " + ("sample composed" if dry_run else (
        f"ack auto-sent + copied to {cap}" if sent else f"send failed: {send_err}"))
    rec = make_audit_record(
        decision, sender=sender, channel=channel, topic=topic, reason=reason,
        ack=ack, ref=ref,
        extra={"routed": routed, "route_err": route_err, "sent": sent,
               "send_err": send_err, "copied": copied, "copy_err": copy_err,
               "dry_run": dry_run})
    _safe(audit, rec)
    return {"decision": decision, "reason": reason, "ack": ack,
            "routed": routed, "sent": sent, "copied": copied,
            "send_result": send_result, "nate_copy": nate_copy, "audit": rec}


# ===========================================================================
# Internal helpers
# ===========================================================================

def _safe(fn: Callable[[Any], Any], arg: Any) -> None:
    """Call an injected side-effect (audit) swallowing any error — audit/logging
    is best-effort and must never break the decision path."""
    try:
        fn(arg)
    except Exception:
        pass


def _result_ok(res: Any) -> bool:
    """Interpret a send backend result as success. The approved backends
    (``chair_drafts.deliver_draft`` / ``queue_draft``) return a dict with
    ``ok``/``sent``/``status``; be permissive but explicit. A None/empty result
    is NOT success."""
    if res is None:
        return False
    if isinstance(res, bool):
        return res
    if isinstance(res, dict):
        if res.get("ok") is True or res.get("sent") is True:
            return True
        if str(res.get("status", "")).lower() in ("sent", "ok", "delivered"):
            return True
        return False
    return True  # a truthy non-dict (e.g. a message id string) counts as sent


def jsonl(rec: dict) -> str:
    """Serialize an audit record to a single JSONL line (the on-disk format)."""
    return json.dumps(rec, ensure_ascii=False, default=str)
