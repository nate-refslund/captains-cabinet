"""A component that cannot reach its operator must not report itself healthy.

The cost was paid before the probe existed. An officer booted with no channel,
logged an error, kept running, kept reporting healthy, and its one escalation
sat unread for five days while every liveness surface stayed green -- because
every one of them was answering "is the process alive?".

These arms exist so that cannot recur silently. The one that matters most is
`test_a_configured_but_silent_channel_is_not_healthy`: that is the exact state
the five days were spent in.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework.probes.operator_reach import (
    DEGRADED,
    HEALTHY,
    INCIDENT,
    MUTE,
    REACHABLE,
    UNCONFIGURED,
    configured_channels,
    is_healthy,
    probe,
    verdict,
)


class WhatCountsAsConfigured(unittest.TestCase):
    def test_a_declared_channel_is_found(self) -> None:
        self.assertEqual(
            configured_channels({"SOMETHING_OPERATOR_CHANNEL": "an-address"}),
            ["something"],
        )

    def test_an_EMPTY_value_is_not_a_configured_channel(self) -> None:
        # THE shape of the five silent days: every variable name existed and
        # every value was blank, and a presence check called that configured.
        self.assertEqual(configured_channels({"SOMETHING_OPERATOR_CHANNEL": ""}), [])
        self.assertEqual(configured_channels({"SOMETHING_OPERATOR_CHANNEL": "   "}), [])

    def test_unrelated_variables_are_ignored(self) -> None:
        self.assertEqual(configured_channels({"HOME": "/x", "PATH": "/y"}), [])

    def test_no_value_is_ever_returned(self) -> None:
        # A health report is a thing people paste into chats. Names only.
        found = configured_channels({"SOMETHING_OPERATOR_CHANNEL": "s3cret-address"})
        self.assertNotIn("s3cret-address", str(found))


class TheThreeStates(unittest.TestCase):
    def test_a_channel_that_answers_is_healthy(self) -> None:
        result = probe(["a"], ask=lambda _c: True)
        self.assertEqual(result["state"], REACHABLE)
        self.assertEqual(result["health"], HEALTHY)
        self.assertTrue(is_healthy(result))

    def test_a_configured_but_silent_channel_is_not_healthy(self) -> None:
        # The five days, in one arm. Configured, not answering, previously
        # reported as fine by everything that looked.
        result = probe(["a"], ask=lambda _c: False)
        self.assertEqual(result["state"], MUTE)
        self.assertEqual(result["health"], INCIDENT)
        self.assertFalse(is_healthy(result))

    def test_no_channel_at_all_is_degraded_not_an_incident(self) -> None:
        # A fresh cabinet legitimately has none yet. Telling someone their
        # brand-new cabinet is BROKEN is how a first run teaches people to
        # ignore warnings -- but it still is not healthy.
        result = probe([], ask=lambda _c: True)
        self.assertEqual(result["state"], UNCONFIGURED)
        self.assertEqual(result["health"], DEGRADED)
        self.assertFalse(is_healthy(result))

    def test_the_two_unhealthy_states_are_distinguishable(self) -> None:
        # Collapsing them would make the common harmless case read the same as
        # the serious one, and the serious one is why this exists.
        silent = probe(["a"], ask=lambda _c: False)
        none = probe([], ask=lambda _c: True)
        self.assertNotEqual(silent["state"], none["state"])
        self.assertNotEqual(silent["health"], none["health"])
        self.assertNotEqual(silent["say"], none["say"])

    def test_one_answering_channel_is_enough(self) -> None:
        result = probe(["a", "b"], ask=lambda c: c == "b")
        self.assertTrue(is_healthy(result))
        self.assertEqual(result["answered"], ["b"])
        self.assertEqual(result["silent"], ["a"])

    def test_a_raising_probe_counts_as_silence(self) -> None:
        # An exception is the loudest possible "did not answer". Treating it as
        # anything else puts the fail-open straight back.
        def boom(_channel):
            raise RuntimeError("transport is down")

        result = probe(["a"], ask=boom)
        self.assertEqual(result["health"], INCIDENT)
        self.assertFalse(is_healthy(result))


class TheDefault(unittest.TestCase):
    def test_verdict_with_no_probe_never_claims_health(self) -> None:
        # Fail-closed by construction: a caller who forgets to pass a round
        # trip gets "not reachable", never a free pass.
        self.assertFalse(is_healthy(verdict({"A_OPERATOR_CHANNEL": "x"})))

    def test_is_healthy_is_strict_about_every_other_word(self) -> None:
        # `!= incident` would let `degraded` read as healthy, which is the
        # softer half of the same lie.
        for health in (DEGRADED, INCIDENT, "unknown", "", None):
            with self.subTest(health):
                self.assertFalse(is_healthy({"health": health}))
        self.assertTrue(is_healthy({"health": HEALTHY}))

    def test_the_probe_opens_no_socket_of_its_own(self) -> None:
        # The transport belongs to the caller. If this module ever grew one,
        # the arms above would stop being able to drive every outcome.
        source = (Path(__file__).resolve().parents[1] / "operator_reach.py").read_text()
        for forbidden in ("import socket", "import requests", "urllib", "http.client"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
