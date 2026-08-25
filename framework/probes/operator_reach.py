"""Can this cabinet reach the person it answers to?

Nothing in this tree asked that question until 2026-08-25, and the cost was
measured before the probe was written: an officer booted with no channel,
logged `[ERROR] Continuing WITHOUT --channels`, kept running, kept reporting
itself healthy, and its one escalation to the operator sat unread in a terminal
pane for five days. Every liveness surface was green throughout, because every
one of them was answering "is the process alive?".

    A component that cannot reach the person it answers to must not
    report itself healthy.

That is the whole rule, and it is deliberately stated without naming a
transport. A cabinet reaches its operator through whatever it was configured
with; the framework's business is whether SOMETHING is configured and provably
working, never which product it is. A probe that named a vendor would be a rule
that cannot be stated without naming a tool, and those do not belong here.

THREE STATES, AND WHY NOT TWO.

    reachable    a channel is configured and answered when asked
    mute         a channel is configured and did NOT answer
    unconfigured no channel is configured at all

`mute` and `unconfigured` are different facts and must not be collapsed. A
fresh cabinet legitimately has no channel yet -- the operator has not set one
up, and telling them their brand-new cabinet is BROKEN is how a first-run
experience teaches people to ignore warnings. A configured channel that has
stopped answering is a live incident. Reporting both as "not healthy" with the
same words would make the common, harmless case indistinguishable from the
serious one, and the serious one is the whole reason this exists.

WHAT COUNTS AS PROOF. A credential being present in a file is not reach --
that is precisely the mistake that produced the five silent days, where every
variable name existed and the values were empty. Proof is a round trip: ask the
channel who it is, and require an answer. `probe` takes that round trip as a
callable so this module never opens a socket of its own, which keeps it
testable and keeps the transport where it belongs.
"""

from __future__ import annotations

import os
from typing import Any, Callable

REACHABLE = "reachable"
MUTE = "mute"
UNCONFIGURED = "unconfigured"

# Health words, chosen so a caller cannot accidentally read `mute` as fine.
HEALTHY = "healthy"
DEGRADED = "degraded"
INCIDENT = "incident"


def configured_channels(env: dict[str, str] | None = None) -> list[str]:
    """Which operator channels this deployment declares.

    Read from the environment by SHAPE, not by a hardcoded list of products:
    anything named `<SOMETHING>_OPERATOR_CHANNEL` or carrying both a
    `*_TOKEN`/`*_KEY` and an operator address counts. The names are returned;
    no value is ever returned, logged or included in a verdict, because a
    health report is a thing people paste into chats.
    """
    env = env if env is not None else dict(os.environ)
    declared: list[str] = []
    for name, value in sorted(env.items()):
        if not value or not value.strip():
            # An empty value is NOT a configured channel. This is the exact
            # shape of the five silent days: every variable existed, every
            # value was blank, and a presence check called it configured.
            continue
        if name.endswith("_OPERATOR_CHANNEL"):
            declared.append(name[: -len("_OPERATOR_CHANNEL")].lower())
    return declared


def probe(
    channels: list[str],
    ask: Callable[[str], bool],
) -> dict[str, Any]:
    """Ask each configured channel whether it answers. Never opens a socket.

    `ask(channel) -> bool` performs the round trip. It is injected so this
    module has no transport knowledge at all, and so the arms that pin this
    behaviour can drive every outcome without a network.

    A raising `ask` counts as NOT answering. An exception is the loudest
    possible "did not answer", and treating it as anything else would put the
    fail-open right back where it was.
    """
    if not channels:
        return {
            "state": UNCONFIGURED,
            "health": DEGRADED,
            "channels": [],
            "answered": [],
            "silent": [],
            "say": ("No way to reach you is set up yet, so this cabinet cannot tell "
                    "you when something goes wrong."),
        }
    answered, silent = [], []
    for channel in channels:
        try:
            (answered if ask(channel) else silent).append(channel)
        except Exception:
            silent.append(channel)
    if answered:
        return {
            "state": REACHABLE,
            "health": HEALTHY,
            "channels": channels,
            "answered": answered,
            "silent": silent,
            "say": "This cabinet can reach you.",
        }
    return {
        "state": MUTE,
        "health": INCIDENT,
        "channels": channels,
        "answered": [],
        "silent": silent,
        "say": ("This cabinet is set up to reach you and cannot. Anything it needs "
                "to tell you is going nowhere."),
    }


def verdict(
    env: dict[str, str] | None = None,
    ask: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """The whole check. Health is never `healthy` unless a channel answered."""
    channels = configured_channels(env)
    return probe(channels, ask or (lambda _channel: False))


def is_healthy(result: dict[str, Any]) -> bool:
    """The one predicate callers should use.

    Deliberately not `result["health"] != "incident"`. A caller writing that
    themselves would let `degraded` read as healthy, and an unconfigured
    cabinet claiming health is the softer half of the same lie.
    """
    return result.get("health") == HEALTHY
