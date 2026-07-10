"""framework.comms — the channel-agnostic Captain-comms foundation.

The cabinet talks to its Captain through ONE seam — the ``ChannelAdapter``
Protocol (channel_adapter.py) — and a channel (Telegram today) is an ADAPTER
behind it (adapters/). Officers reach it through the Comms MCP (mcp/, C2),
which routes every call through ``framework.attention.gate`` (charter, dedup,
quiet-hours, standing-cards, T2) and the feed journal.

FOUNDATION-FIRST: nothing here names a launcher or a channel except inside
``adapters/telegram.py``. ``get_channel()`` binds the adapter from
``instance/config/sources.yml``; a clean-room / Flavor-B box binds the null
adapter and every tool degrades to a logged no-op. Spec:
docs/plans/cabinet-comms-mcp-spec-2026-07-09.md.
"""
