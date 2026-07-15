"""framework.comms.adapters.telegram — the Telegram ChannelAdapter (C1).

The ONLY module (besides framework/frontdoor/channel.py, the one door) that
names Telegram. It maps the channel-neutral ``ChannelAdapter`` methods onto the
existing gated ``channel.py`` primitives, so every send still inherits
allow_sends(), token-scrub, chunking, transport-retry, and the feed journal.
Nothing here talks to the Bot API directly — it delegates to channel.py, which
keeps the one-door CI tripwire satisfied.
"""
from __future__ import annotations

from framework.comms.channel_adapter import unsupported
from framework.frontdoor import channel


class TelegramAdapter:
    """Bind once per process (via framework.comms.get_channel)."""

    name = "telegram"

    # Reserved draft id for the ephemeral "Thinking…" status (set_status).
    _STATUS_DRAFT_ID = 1

    def capabilities(self) -> dict:
        # Telegram supports the full surface; forum topics depend on the bot
        # having topic-mode enabled, but open_thread already degrades on error.
        # download_inbound is NOT advertised — the method is still a no-op (the
        # poller owns inbound file fetch today); a missing key ⇒ unsupported, so
        # advertised capabilities and method bodies stay in lockstep (honest).
        return {c: True for c in (
            "send", "edit", "react", "poll", "set_status", "pin", "thread",
            "answer_tap", "draft", "rich", "observe_reply_current",
            "observe_react_current")}

    def send(self, body, *, silent=False, reply_to=None, thread_id=None,
             effect_id=None, buttons=None, markdown=False, feed_meta=None):
        return channel.send(body, silent=silent, reply_to=reply_to,
                            thread_id=thread_id, effect_id=effect_id,
                            reply_markup=self._kb(buttons), markdown=markdown,
                            feed_meta=feed_meta)

    def edit(self, message_id, body, *, buttons=None, markdown=False, feed_meta=None):
        return channel.edit_message(message_id, body, reply_markup=self._kb(buttons),
                                    markdown=markdown, feed_meta=feed_meta)

    def react(self, message_id, emoji):
        # The LLM-contextual react (supersedes the poller's instant receipt
        # reaction) via channel.set_reaction (setMessageReaction, C3).
        return channel.set_reaction(message_id, emoji)

    def observe_reply_current(self, text):
        return channel.reply_current_observe_only(text)

    def observe_react_current(self, emoji):
        return channel.react_current_observe_only(emoji)

    def poll(self, question, options, *, multi=False, silent=False, feed_meta=None):
        return channel.send_poll(question, options, allows_multiple_answers=multi,
                                 silent=silent, feed_meta=feed_meta)

    def set_status(self, kind="typing"):
        # "thinking" shows the REAL "Thinking…" via an ephemeral draft
        # (sendMessageDraft, empty text) — the brief typing bubble is only for
        # "typing". The draft auto-expires (~30s); the officer's send_card posts
        # the persisted message.
        if kind == "thinking":
            return channel.send_draft(self._STATUS_DRAFT_ID, "")
        return channel.set_typing("typing")

    def send_draft(self, draft_id, text="", *, thread_id=None):
        return channel.send_draft(draft_id, text, thread_id=thread_id)

    def send_rich(self, markdown=None, *, html=None, silent=False,
                  buttons=None, feed_meta=None):
        return channel.send_rich(markdown, html=html, silent=silent,
                                 reply_markup=self._kb(buttons), feed_meta=feed_meta)

    def pin(self, message_id, *, silent=True):
        return channel.pin(message_id, silent=silent)

    def unpin(self, message_id=None):
        return channel.unpin(message_id)

    def open_thread(self, name):
        return channel.open_thread(name)

    def answer_tap(self, tap_id, toast=""):
        return channel.answer_callback(tap_id, toast)

    def download_inbound(self, ref):
        # Inbound download lives in the poller today (getFile → inbox); exposing
        # it as an adapter method is C3 officer-surface work.
        return unsupported("download_inbound")

    @staticmethod
    def _kb(buttons):
        """Channel-neutral ``buttons`` (list of {text, data} tap buttons and/or
        {text, url} link buttons, as one row or a list of rows) → Telegram
        inline_keyboard. None ⇒ None (plain message). A ``url`` key wins over
        ``data`` (a button is one or the other, never both)."""
        if not buttons:
            return None
        rows = buttons if buttons and isinstance(buttons[0], list) else [buttons]
        kb = []
        for row in rows:
            out = []
            for b in row:
                if b.get("url"):
                    out.append({"text": str(b.get("text", "")),
                                "url": str(b.get("url", ""))})
                else:
                    out.append({"text": str(b.get("text", "")),
                                "callback_data": str(b.get("data", ""))[:64]})
            kb.append(out)
        return {"inline_keyboard": kb}
