"""framework.comms.channel_adapter — the ONE channel-neutral seam (C1).

A ``ChannelAdapter`` abstracts "which channel the cabinet reaches the Captain
on." Its vocabulary is comms, never telegram: ``send``, ``edit``, ``react``,
``poll``, ``set_status``, ``pin``/``unpin``, ``open_thread``, ``answer_tap``,
``download_inbound``, ``capabilities``. The gate (charter/dedup/quiet-hours/T2)
sits ABOVE the adapter; the adapter is just the transport.

``capabilities()`` lets an adapter advertise what it supports so a consumer
degrades gracefully — a channel without polls returns ``{"poll": False}`` and
the ``poll`` tool becomes a logged no-op, never an error. Every method returns
a dict with at least ``status`` + ``sent`` (mirroring channel.py), so callers
never need channel-specific knowledge.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


# The capability keys an adapter may advertise. A missing key ⇒ unsupported.
CAPABILITIES = (
    "send", "edit", "react", "poll", "set_status", "pin", "thread",
    "answer_tap", "download_inbound", "draft", "rich",
)


@runtime_checkable
class ChannelAdapter(Protocol):
    """The channel-neutral transport seam. Every method is fail-soft (returns
    a status dict, never raises) and gated by the adapter's own send-guard."""

    def capabilities(self) -> dict:
        """``{cap: bool}`` for each key in ``CAPABILITIES`` — what this channel
        supports on this deployment."""
        ...

    def send(self, body: str, *, silent: bool = False, reply_to: "int | None" = None,
             thread_id: "int | None" = None, effect_id: "str | None" = None,
             buttons: "list | None" = None, markdown: bool = False,
             feed_meta: "dict | None" = None) -> dict:
        """Send one message to the Captain. Returns ``{status, sent,
        message_ids}``."""
        ...

    def edit(self, message_id: int, body: str, *, buttons: "list | None" = None,
             markdown: bool = False, feed_meta: "dict | None" = None) -> dict:
        """Edit a standing message in place (no notification)."""
        ...

    def react(self, message_id: int, emoji: str) -> dict:
        """Set a single reaction on a message (the LLM-contextual layer)."""
        ...

    def poll(self, question: str, options: list, *, multi: bool = False,
             silent: bool = False, feed_meta: "dict | None" = None) -> dict:
        """Send a native select/poll. Returns ``{status, sent, message_ids}``."""
        ...

    def set_status(self, kind: str = "typing") -> dict:
        """Show an ephemeral status (``typing`` / ``thinking``)."""
        ...

    def send_draft(self, draft_id: int, text: str = "", *,
                   thread_id: "int | None" = None) -> dict:
        """Stream a live draft (the real "Thinking…"). Empty text = placeholder;
        same ``draft_id`` animates. Ephemeral — finalize with ``send``."""
        ...

    def send_rich(self, markdown: "str | None" = None, *, html: "str | None" = None,
                  silent: bool = False, buttons: "list | None" = None,
                  feed_meta: "dict | None" = None) -> dict:
        """Send a Rich Message (tables, collapsibles). Exactly one of
        ``markdown``/``html``. A persisted message, feed-journaled."""
        ...

    def pin(self, message_id: int, *, silent: bool = True) -> dict:
        ...

    def unpin(self, message_id: "int | None" = None) -> dict:
        ...

    def open_thread(self, name: str) -> dict:
        """Open a per-lane thread; returns ``{..., thread_id}`` when supported."""
        ...

    def answer_tap(self, tap_id: str, toast: str = "") -> dict:
        """Acknowledge an inline-button tap."""
        ...

    def download_inbound(self, ref: str) -> dict:
        """Fetch a Captain-sent file to a local path; ``{status, path}``."""
        ...


def unsupported(cap: str) -> dict:
    """The canonical fail-soft return when an adapter lacks a capability — a
    logged no-op shape, never an error the officer must handle."""
    return {"status": "unsupported", "sent": False, "capability": cap}
