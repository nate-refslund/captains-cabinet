"""framework.comms.tools — the LLM-native Comms tool surface (C2 core).

The pure dispatch behind the Comms MCP: each tool routes an officer's request
through ``framework.attention.gate`` (charter class, dedup, quiet-hours,
standing-card, T2) and the bound ``ChannelAdapter`` (channel-agnostic), then
the feed journals it. So an officer's ``send_card`` inherits the ENTIRE gateway
automatically and CANNOT bypass the charter, the one door, or the external-
comms floor. This module is the logic; ``framework/comms/mcp`` (the server) is
the thin stdio/http wrapper around it.

Every tool is fail-soft (returns a dict, never raises) and channel-neutral
(it talks to the adapter, never Telegram). A tool whose capability the bound
adapter lacks returns the adapter's ``unsupported`` no-op.
"""
from __future__ import annotations

from framework.comms.get_channel import get_channel


# Observe replies must remain one Telegram message.  The transport's normal
# send path deliberately chunks at 3900 characters; keeping the dedicated
# observe seam at or below that threshold prevents one permitted tool call from
# fanning out into an arbitrary number of Captain notifications.
OBSERVE_REPLY_MAX_CHARS = 3900
OBSERVE_REACTION_MAX_CHARS = 8


def _adapter(adapter=None):
    return adapter if adapter is not None else get_channel()


def _cap(adapter, name: str) -> bool:
    try:
        return bool(adapter.capabilities().get(name))
    except Exception:
        return False


def send_card(*, subject: str, situation: str = "", kind: str = "action-card",
              lane: "str | None" = None, evidence: "list | None" = None,
              urgency: "str | None" = None, steps: "list | None" = None,
              state: str = "open", deadline_iso: "str | None" = None,
              pid_marker: "str | None" = None, injection_suspect: bool = False,
              chair_review: bool = False, escalation: "dict | None" = None,
              buttons: "list | None" = None,
              adapter=None, ch=None, now=None) -> dict:
    """Present a card to the Captain — the officer gives the STRUCTURED situation
    (subject/situation/steps/evidence); the gate renders the terse card, dedups
    it into a standing card, honors quiet hours, and (chair_review) routes an
    exceptional one to T2. Delivery is the bound adapter, so it is channel-
    agnostic and feed-journaled.

    The card's IDENTITY is content-derived — ``situation_key(evidence, subject)``.
    Re-sending the SAME subject+evidence with an updated ``state``/``steps`` is the
    UPDATE path: the gate finds the existing standing card and EDITS that one
    message in place (no duplicate). ``edit_card`` is the named alias for that.

    ``escalation`` is the tiered-escalation exhaustion proof
    (``{"lane_tried", "chair_tried", "needs_captain_because"}`` — §3.9): when
    the escalation gate is armed, a NEW open decision card without it BOUNCES
    back to you (``status="bounced"`` + what's missing) instead of reaching
    the Captain — fix it at your tier or attach the proof.

    ``buttons`` (one-card-one-decision surface): channel-neutral inline
    controls — a row (or rows) of ``{text, data}`` tap buttons / ``{text,
    url}`` link buttons, rendered by the bound adapter when the gate's
    decision is a direct send/edit. Charter routing (briefing, quiet hours,
    dedup-suppress) is untouched by their presence, and buttons are NOT part
    of the render-hash identity — a buttons-only change with identical text
    suppresses as no-change (flip ``state``/text to force the edit)."""
    from framework.attention import gate
    a = _adapter(adapter)
    item = {"kind": kind, "subject": subject, "situation": situation,
            "lane": lane, "evidence": list(evidence or []), "urgency": urgency,
            "steps": list(steps or []), "state": state, "deadline_iso": deadline_iso,
            "pid_marker": pid_marker, "injection_suspect": bool(injection_suspect),
            "escalation": escalation,
            "buttons": (list(buttons) if buttons else None)}
    return gate.submit(item, send_fn=a.send, edit_fn=a.edit,
                       chair_review=chair_review, ch=ch, now=now)


def edit_card(*, subject: str, evidence: "list | None" = None, situation: str = "",
              steps: "list | None" = None, state: str = "done", lane: "str | None" = None,
              buttons: "list | None" = None, adapter=None, ch=None, now=None) -> dict:
    """Update a standing card in place (e.g. flip a step to done). Re-describe the
    SAME situation — the same ``subject`` + ``evidence`` that created the card, so
    the gate's identity path (``situation_key(evidence, subject)``) finds the
    existing message — with the new ``state``/``steps``. The gate then EDITS that
    one message instead of posting a new card. Identity is content-derived, so
    subject+evidence MUST match the original send_card, or a fresh card results.
    ``buttons`` replaces the card's inline controls on the edit (None clears)."""
    return send_card(subject=subject, evidence=evidence, situation=situation,
                     steps=steps, state=state, lane=lane, buttons=buttons,
                     adapter=adapter, ch=ch, now=now)


def react(*, message_id: int, emoji: str, adapter=None) -> dict:
    """Set a single CONTEXTUAL reaction on a message (the LLM layer that
    supersedes the poller's instant deterministic receipt-react)."""
    a = _adapter(adapter)
    if not _cap(a, "react"):
        from framework.comms.channel_adapter import unsupported
        return unsupported("react")
    return a.react(int(message_id), str(emoji))


def reply_current(*, text: str, adapter=None) -> dict:
    """Observe-only reply to the latest Captain inbound.

    Deliberately accepts no recipient or message id.  The adapter resolves the
    watchdog-owned current message and the transport pins the Captain chat.
    """
    body = str(text)
    if not body or len(body) > OBSERVE_REPLY_MAX_CHARS:
        return {
            "status": "error",
            "sent": False,
            "error": f"text must be 1..{OBSERVE_REPLY_MAX_CHARS} characters",
        }
    a = _adapter(adapter)
    if not _cap(a, "observe_reply_current"):
        from framework.comms.channel_adapter import unsupported
        return unsupported("observe_reply_current")
    return a.observe_reply_current(body)


def react_current(*, emoji: str, adapter=None) -> dict:
    """Observe-only reaction to the latest Captain inbound; no id parameter."""
    value = str(emoji)
    if not value or len(value) > OBSERVE_REACTION_MAX_CHARS:
        return {
            "status": "error",
            "sent": False,
            "error": "emoji must be one supported Telegram reaction",
        }
    a = _adapter(adapter)
    if not _cap(a, "observe_react_current"):
        from framework.comms.channel_adapter import unsupported
        return unsupported("observe_react_current")
    return a.observe_react_current(value)


def poll(*, question: str, options: list, multi: bool = False,
         silent: bool = False, adapter=None) -> dict:
    """Ask the Captain an AskUserQuestion-style select (native poll)."""
    a = _adapter(adapter)
    if not _cap(a, "poll"):
        from framework.comms.channel_adapter import unsupported
        return unsupported("poll")
    return a.poll(str(question), list(options), multi=bool(multi), silent=bool(silent),
                  feed_meta={"kind": "poll"})


def set_status(*, kind: str = "typing", adapter=None) -> dict:
    """Show an ephemeral status (typing / thinking) while composing."""
    a = _adapter(adapter)
    if not _cap(a, "set_status"):
        return {"status": "unsupported", "sent": False}
    return a.set_status(str(kind))


def pin(*, message_id: int, adapter=None) -> dict:
    a = _adapter(adapter)
    if not _cap(a, "pin"):
        from framework.comms.channel_adapter import unsupported
        return unsupported("pin")
    return a.pin(int(message_id))


def unpin(*, message_id: "int | None" = None, adapter=None) -> dict:
    return _adapter(adapter).unpin(message_id)


def open_thread(*, lane: str, adapter=None) -> dict:
    """Open a per-lane thread in the Captain's DM (returns thread_id)."""
    a = _adapter(adapter)
    if not _cap(a, "thread"):
        from framework.comms.channel_adapter import unsupported
        return unsupported("thread")
    return a.open_thread(str(lane))


def answer_tap(*, tap_id: str, toast: str = "", adapter=None) -> dict:
    return _adapter(adapter).answer_tap(str(tap_id), str(toast))


def stream_thinking(*, draft_id: int = 1, text: str = "", thread_id=None, adapter=None) -> dict:
    """Show/stream the real "Thinking…" draft while composing. Empty text shows
    the "Thinking…" placeholder; call again with the SAME draft_id to stream the
    reply as it forms. Ephemeral (~30s) — the persisted message is a later
    send_card. Gate-exempt like set_status (it is a status, not a message)."""
    a = _adapter(adapter)
    if not _cap(a, "draft"):
        from framework.comms.channel_adapter import unsupported
        return unsupported("draft")
    return a.send_draft(int(draft_id), str(text or ""), thread_id=thread_id)


def send_rich_card(*, markdown: "str | None" = None, html: "str | None" = None,
                   silent: bool = False, buttons: "list | None" = None, adapter=None) -> dict:
    """Send a Rich Message — tables, collapsible <details>, task lists — for a
    report or a multi-step course-of-action that reads best as a table. Exactly
    ONE of markdown/html. A DIRECT presentation send (parallel to send_document):
    it carries the full safety gate (allow_sends + scrub + feed-journal) but is
    NOT dedup-gated — the situation-dedup standing-card path is send_card."""
    a = _adapter(adapter)
    if not _cap(a, "rich"):
        from framework.comms.channel_adapter import unsupported
        return unsupported("rich")
    return a.send_rich(markdown, html=html, silent=silent, buttons=buttons,
                       feed_meta={"kind": "rich"})


def read_feed(*, consumer: "str | None" = None, cursor: int = 0, max_n: int = 200) -> dict:
    """The never-re-read cursor read of the outbound/inbound feed (P3). Returns
    ``{rows, cursor}`` — the officer's window into what the Captain has already
    been shown, so it never re-surfaces a handled situation.

    Two modes:
      * ``consumer`` (recommended) — a stable id (e.g. the officer's role). The
        feed AUTO-MANAGES this consumer's durable cursor: each call loads the
        stored cursor, returns only rows NEW since the last read, and persists
        the advance. The officer never tracks a cursor itself.
      * ``cursor`` (raw) — pass the int you last held; get it back advanced.
        For stateless callers that manage their own cursor.
    ``consumer`` must match ``[a-z0-9_-]+`` (the feed's path-traversal fence)."""
    try:
        from framework.attention import feed
        if consumer:
            start = feed.load_cursor(consumer)
            rows, new_cursor = feed.feed_since(start, max_n=int(max_n))
            feed.store_cursor(consumer, new_cursor)
        else:
            rows, new_cursor = feed.feed_since(int(cursor), max_n=int(max_n))
        return {"status": "ok", "rows": rows, "cursor": new_cursor}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e), "rows": [], "cursor": cursor}


# The tool registry the MCP server (C2 wrapper) dispatches on. Kept here so the
# server stays a thin transport and the surface is testable without a client.
TOOLS = {
    "send_card": send_card, "edit_card": edit_card, "react": react,
    "reply_current": reply_current, "react_current": react_current,
    "poll": poll, "set_status": set_status, "pin": pin, "unpin": unpin,
    "open_thread": open_thread, "answer_tap": answer_tap, "read_feed": read_feed,
    "stream_thinking": stream_thinking, "send_rich_card": send_rich_card,
}


def dispatch(tool: str, args: dict) -> dict:
    """Call one tool by name with kwargs. Unknown tool → error dict (never
    raises); a tool that raises internally is caught and surfaced."""
    fn = TOOLS.get(tool)
    if fn is None:
        return {"status": "error", "error": f"unknown comms tool: {tool}"}
    try:
        return fn(**(args or {}))
    except TypeError as e:
        return {"status": "error", "error": f"bad args for {tool}: {e}"}
    except Exception as e:  # noqa: BLE001 — a tool must never crash the server
        return {"status": "error", "error": f"{tool} failed: {e}"}
