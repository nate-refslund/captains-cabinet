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

    def capabilities(self) -> dict:
        # Telegram supports the full surface; forum topics depend on the bot
        # having topic-mode enabled, but open_thread already degrades on error.
        return {c: True for c in (
            "send", "edit", "react", "poll", "set_status", "pin", "thread",
            "answer_tap", "download_inbound")}

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
        # channel.py has no set-reaction helper yet (the poller sets the receipt
        # reaction); the LLM-contextual react is a thin sanctioned call added at
        # C3 when the officer surface lands. Until then: advertised, no-op-safe.
        return unsupported("react")

    def poll(self, question, options, *, multi=False, silent=False, feed_meta=None):
        return channel.send_poll(question, options, allows_multiple_answers=multi,
                                 silent=silent, feed_meta=feed_meta)

    def set_status(self, kind="typing"):
        # "thinking" maps to the typing action until streaming-draft (C4) lands.
        action = "typing" if kind in ("typing", "thinking") else str(kind)
        return channel.set_typing(action)

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
        """Channel-neutral ``buttons`` (list of {text, data} rows) → Telegram
        inline_keyboard. None ⇒ None (plain message)."""
        if not buttons:
            return None
        rows = buttons if buttons and isinstance(buttons[0], list) else [buttons]
        return {"inline_keyboard": [
            [{"text": str(b.get("text", "")), "callback_data": str(b.get("data", ""))[:64]}
             for b in row] for row in rows]}
