"""framework.comms.adapters.null — the fail-closed no-op ChannelAdapter.

Bound on a deployment with no channel configured (clean-room / Flavor-B /
headless). Every method is a logged no-op advertising no capabilities, so
``framework/comms`` stays runnable and every officer tool degrades cleanly
instead of crashing. The sister of ``framework.sources.NullPersonalSource``.
"""
from __future__ import annotations

import sys

from framework.comms.channel_adapter import unsupported


class NullAdapter:
    name = "null"

    def capabilities(self) -> dict:
        return {}

    def _noop(self, method: str) -> dict:
        print(f"[comms] no channel bound — '{method}' is a no-op "
              f"(set instance/config/sources.yml channel:)", file=sys.stderr)
        return unsupported(method)

    def send(self, *a, **k): return self._noop("send")
    def edit(self, *a, **k): return self._noop("edit")
    def react(self, *a, **k): return self._noop("react")
    def observe_reply_current(self, *a, **k): return self._noop("observe_reply_current")
    def observe_react_current(self, *a, **k): return self._noop("observe_react_current")
    def poll(self, *a, **k): return self._noop("poll")
    def set_status(self, *a, **k): return self._noop("set_status")
    def pin(self, *a, **k): return self._noop("pin")
    def unpin(self, *a, **k): return self._noop("unpin")
    def open_thread(self, *a, **k): return self._noop("open_thread")
    def answer_tap(self, *a, **k): return self._noop("answer_tap")
    def download_inbound(self, *a, **k): return self._noop("download_inbound")
    def send_draft(self, *a, **k): return self._noop("send_draft")
    def send_rich(self, *a, **k): return self._noop("send_rich")
