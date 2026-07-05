"""framework.channels — channel-adapter plugins [AX-5] (axes spec §4).

One uniform contract per outbound channel (`contract.ChannelAdapter`):
`send()` journaled to the event ledger, `classify(recipient)` from the
instance org-domain config (`instance/config/channels.yml`, fail-closed
external), an explicit `undo_contract` (none | delete_window(seconds)), and
a declared capability subset of {send, receive, edit, delete, react}.

Shipped adapters: `TeamsAdapter` + `OutlookAdapter` (transport-injectable —
the default transport is the brain-MCP `queue_draft` stub per
.claude/rules/brain-bridge.md; they never call Graph/SMTP directly) and
`SlackAdapter` (stdlib urllib behind a transport seam, live path gated on
framework.env.allow_sends()).

Arena/sim mocks live in `framework.channels.mocks` — deliberately NOT
re-exported here: a harness opts into mocks explicitly, and live code must
never bind them by accident (no live sends in experiments — the
evolution-engine invariant).

Extension manifests (AX-6 schema
framework/schemas/extension-manifest.schema.json) ship one-per-adapter in
`manifests/<name>.json`, with entrypoints relative to THIS package
directory; a loader binding an adapter as a captain extension places the
manifest at the extension root beside the module files (the
cabinet/scripts/validate-extension.sh shape — the tests prove each shipped
manifest passes that gate end-to-end).
"""
from __future__ import annotations

import sys
from pathlib import Path

_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

from framework.channels.contract import (
    CAPABILITIES,
    EXTERNAL,
    INTERNAL,
    ChannelAdapter,
    ChannelCapabilityError,
    ChannelConfigError,
    ChannelDeleteError,
    ChannelError,
    ChannelSendError,
    UndoContract,
    channels_config_path,
    classify_recipient,
    load_org_domains,
    queue_draft_stub,
)
from framework.channels.outlook import OutlookAdapter
from framework.channels.slack import SlackAdapter
from framework.channels.teams import TeamsAdapter

# channel name -> live adapter class (loader binding surface; the sim
# counterpart is mocks.MOCKS_BY_CHANNEL).
ADAPTERS_BY_CHANNEL = {
    TeamsAdapter.name: TeamsAdapter,
    OutlookAdapter.name: OutlookAdapter,
    SlackAdapter.name: SlackAdapter,
}

__all__ = [
    "ADAPTERS_BY_CHANNEL",
    "CAPABILITIES",
    "EXTERNAL",
    "INTERNAL",
    "ChannelAdapter",
    "ChannelCapabilityError",
    "ChannelConfigError",
    "ChannelDeleteError",
    "ChannelError",
    "ChannelSendError",
    "OutlookAdapter",
    "SlackAdapter",
    "TeamsAdapter",
    "UndoContract",
    "channels_config_path",
    "classify_recipient",
    "load_org_domains",
    "queue_draft_stub",
]
