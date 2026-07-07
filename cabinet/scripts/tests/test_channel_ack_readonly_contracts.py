"""AUD-12 (audit #32) — channel-server source contracts.

Two structural contracts, pinned as source ratchets (same style as the
launcher-hardcode / axis ratchets — the servers are bun/TS processes, so the
Python suite pins the CONTRACT in the source rather than spawning redis):

1. redis-trigger-channel NEVER ACKs (consumer-side ACK): the channel used to
   XACK the instant it emitted the MCP notification, so a crash between the
   notification push and the officer's wake turn silently LOST the trigger.
   The ACK now belongs to the consumer side — the officer's trigger_ack (or
   the post-tool-use XAUTOCLAIM safety net that feeds it). A reintroduced
   channel-side xAck/xTrim is a regression to at-most-once delivery.

2. library-mcp's 6 read tools carry MCP ``readOnlyHint`` annotations, and its
   4 mutating tools do NOT.

Run: python3 -m pytest cabinet/scripts/tests/test_channel_ack_readonly_contracts.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TRIGGER_CHANNEL = REPO / "cabinet/channels/redis-trigger-channel/index.ts"
LIBRARY_MCP = REPO / "cabinet/channels/library-mcp/index.ts"
TRIGGERS_LIB = REPO / "cabinet/scripts/lib/triggers.sh"

READ_TOOLS = [
    "library_list_spaces",
    "library_get_record",
    "library_get_backlinks",
    "library_graph_data",
    "library_search",
    "library_list_records",
]
WRITE_TOOLS = [
    "library_create_space",
    "library_create_record",
    "library_update_record",
    "library_delete_record",
]


class TestConsumerSideAck:
    def test_channel_never_acks(self):
        src = TRIGGER_CHANNEL.read_text()
        assert "xAck(" not in src, (
            "redis-trigger-channel must NOT ACK on notification emit — "
            "delivery is not processing (AUD-12, audit #32). ACK belongs to "
            "the officer's trigger_ack / the post-tool-use safety net."
        )

    def test_channel_never_trims(self):
        src = TRIGGER_CHANNEL.read_text()
        assert "xTrim(" not in src, (
            "channel-side XTRIM can delete entries that are still pending "
            "under consumer-side ACK; trimming lives in trigger_ack (post-"
            "processing) only."
        )

    def test_channel_documents_the_contract(self):
        src = TRIGGER_CHANNEL.read_text()
        assert "consumer-side ACK" in src, (
            "the ACK contract comment must survive edits — it is the only "
            "in-file defense against someone 'fixing' the missing ACK back in"
        )

    def test_triggers_lib_no_stale_auto_ack_claim(self):
        # Docs-track-code: the safety-net comment used to assert the channel
        # AUTO-ACKs on push; that claim is now false and must stay gone.
        src = TRIGGERS_LIB.read_text()
        assert "AUTO-ACKs the" not in src, (
            "triggers.sh still documents the retired channel auto-ACK "
            "behavior — update the trigger_read_safety_net comment"
        )
        assert "trigger_ack()" in src  # the consumer-side ACK path itself


def _tool_blocks(src: str) -> dict[str, str]:
    """Split the ListTools tool-definition array into per-tool source blocks,
    keyed by tool name (block runs to the next `name: "library_` or EOF)."""
    defs_start = src.index("ListToolsRequestSchema")
    defs_end = src.index("CallToolRequestSchema", defs_start)
    region = src[defs_start:defs_end]
    hits = list(re.finditer(r'name:\s*"(library_[a-z_]+)"', region))
    blocks: dict[str, str] = {}
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(region)
        blocks[m.group(1)] = region[m.start():end]
    return blocks


class TestReadOnlyHints:
    def test_exactly_ten_tools_defined(self):
        blocks = _tool_blocks(LIBRARY_MCP.read_text())
        assert sorted(blocks) == sorted(READ_TOOLS + WRITE_TOOLS)

    def test_all_six_read_tools_carry_read_only_hint(self):
        blocks = _tool_blocks(LIBRARY_MCP.read_text())
        missing = [t for t in READ_TOOLS if "readOnlyHint: true" not in blocks[t]]
        assert not missing, f"read tools missing readOnlyHint annotation: {missing}"

    def test_write_tools_do_not_carry_read_only_hint(self):
        blocks = _tool_blocks(LIBRARY_MCP.read_text())
        wrong = [t for t in WRITE_TOOLS if "readOnlyHint" in blocks[t]]
        assert not wrong, f"mutating tools must not claim readOnlyHint: {wrong}"
