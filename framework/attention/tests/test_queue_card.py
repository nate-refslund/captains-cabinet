"""Tests for framework.attention.queue_card — the Telegram skin.

Pinned: one standing card, silent send + DM pin, silent in-place edits,
no-op on unchanged render, re-send on a dead message id, NO ·pid· markers
(the summary card must never collide with the binder's marker grammar),
briefing section absent when nothing pends, refresh gated on sends.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from framework.attention import queue_card


def census(n=2, overflow=0, directions=1):
    decisions = []
    for i in range(n):
        decisions.append({
            "id": f"sit-{i}", "kind": "action-proposal", "state": "pending",
            "what": f"decision {i} · with a marker char to strip",
            "age_h": 20.0 + i, "deadline_iso": "2026-07-11T09:00:00Z"
            if i == 0 else None,
            "why_now": {"cost_of_delay": "high"},
        })
    return {
        "generated_at": "2026-07-10T09:00:00Z",
        "pending_captain_items": n + overflow,
        "pending_total": n + overflow + directions,
        "by_class": {"action-proposal": n + overflow, "need": directions},
        "overflow": overflow, "cap": 7, "admission_enforced": False,
        "decisions": decisions,
        "directions": [{"id": "need-1", "kind": "need", "what": "a need",
                        "age_h": 40.0, "why_now": {}}] * directions,
    }


class TestRender(unittest.TestCase):
    def test_card_lines_match_decisions_order(self):
        lines = queue_card.pinned_card_lines(census(3))
        self.assertEqual([i for i, _ in lines], ["sit-0", "sit-1", "sit-2"])

    def test_render_is_terse_and_marker_free(self):
        text = queue_card.render_pinned_card(census(2, overflow=3))
        self.assertIn("⚑ Needs you (5)", text)
        self.assertIn("+3 over the cap", text)
        self.assertIn("Directions (weekly): 1", text)
        self.assertNotIn("·", text)          # NEVER a bindable marker here
        self.assertIn("binder", text)
        self.assertLess(len(text), 1200)

    def test_empty_shelf_is_the_reward_state(self):
        text = queue_card.render_pinned_card(
            {"pending_captain_items": 0, "pending_total": 0})
        self.assertIn("nothing", text.lower())


class TestUpsert(unittest.TestCase):
    def _fns(self, sent, edited, pinned, mid=101, send_raises=False,
             edit_raises=False):
        def send_fn(text):
            if send_raises:
                raise RuntimeError("send down")
            sent.append(text)
            return {"status": "sent", "message_ids": [mid]}

        def edit_fn(m, text):
            if edit_raises:
                raise RuntimeError("message deleted")
            edited.append((m, text))
            return {"status": "edited"}

        def pin_fn(m):
            pinned.append(m)
            return {"ok": True}
        return send_fn, edit_fn, pin_fn

    def test_first_send_pins_then_edits_in_place(self):
        sent, edited, pinned = [], [], []
        state = {}
        s, e, p = self._fns(sent, edited, pinned)
        r1 = queue_card.update_pinned_card(census(1), send_fn=s, edit_fn=e,
                                           pin_fn=p, state=state)
        self.assertEqual(r1["status"], "sent")
        self.assertEqual(pinned, [101])
        # unchanged census → no-op (no edit spam)
        r2 = queue_card.update_pinned_card(census(1), send_fn=s, edit_fn=e,
                                           pin_fn=p, state=state)
        self.assertEqual(r2["status"], "unchanged")
        self.assertEqual(edited, [])
        # changed census → ONE silent in-place edit, same message id
        r3 = queue_card.update_pinned_card(census(2), send_fn=s, edit_fn=e,
                                           pin_fn=p, state=state)
        self.assertEqual(r3["status"], "edited")
        self.assertEqual(edited[0][0], 101)
        self.assertEqual(len(sent), 1)       # never a second message

    def test_dead_message_resends_and_repins(self):
        sent, edited, pinned = [], [], []
        state = {"message_id": 55, "render_hash": "stale"}
        s, e, p = self._fns(sent, edited, pinned, mid=102, edit_raises=True)
        r = queue_card.update_pinned_card(census(1), send_fn=s, edit_fn=e,
                                          pin_fn=p, state=state)
        self.assertEqual(r["status"], "sent")
        self.assertEqual(state["message_id"], 102)
        self.assertEqual(pinned, [102])

    def test_send_failure_is_a_status_never_a_raise(self):
        r = queue_card.update_pinned_card(
            census(1), send_fn=self._fns([], [], [], send_raises=True)[0],
            edit_fn=lambda *a: None, pin_fn=lambda m: None, state={})
        self.assertEqual(r["status"], "send-failed")


class TestBriefingSection(unittest.TestCase):
    def test_item_shape_matches_intake_contract(self):
        item = queue_card.briefing_needs_you_item(census(2))
        self.assertEqual(item["source"], "attention-queue")
        self.assertEqual(item["kind"], "needs-you")
        self.assertEqual(item["urgency_tier"], "batch")
        self.assertIn("⚑ Needs you (2)", item["payload"]["summary"])
        # renders as a titled section through the composer (multi-line)
        from framework.frontdoor.composer import render_item
        self.assertIn("attention-queue", render_item(item))

    def test_silent_when_nothing_pends(self):
        self.assertIsNone(queue_card.briefing_needs_you_item(
            {"pending_captain_items": 0, "decisions": [], "directions": []}))


class TestRefreshGates(unittest.TestCase):
    def test_kill_switch_env(self):
        with mock.patch.dict(os.environ, {"CABINET_QUEUE_CARD": "0"}):
            self.assertEqual(queue_card.refresh({})["status"], "disabled")

    def test_sends_disabled_never_touches_channel(self):
        with mock.patch.dict(os.environ, {"CABINET_QUEUE_CARD": "1"}), \
             mock.patch("framework.env.allow_sends", return_value=False):
            self.assertEqual(queue_card.refresh({})["status"], "sends-disabled")

    def test_state_persistence_roundtrip(self):
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.dict(os.environ, {"CABINET_ATTENTION_DIR": td}):
            sent, edited, pinned = [], [], []

            def send_fn(text):
                sent.append(text)
                return {"status": "sent", "message_ids": [7]}
            queue_card.update_pinned_card(
                census(1), send_fn=send_fn,
                edit_fn=lambda m, t: edited.append((m, t)),
                pin_fn=pinned.append)          # state=None → persists
            # a fresh call loads the persisted message id and edits in place
            queue_card.update_pinned_card(
                census(2), send_fn=send_fn,
                edit_fn=lambda m, t: edited.append((m, t)),
                pin_fn=pinned.append)
            self.assertEqual(len(sent), 1)
            self.assertEqual(edited[0][0], 7)


if __name__ == "__main__":
    unittest.main()
