"""SURFACE-PARITY-LAW gate — one census, N skins, identical truth.

The war-room capability's parity test (egg-plan SURFACE-PARITY row: a
parity test per capability is that row's gate): ONE build_queue() census
must project the SAME items, in the SAME order, with the SAME glance int
through every skin:

  * the private census (what GET /api/attention/queue serves),
  * the shared/interfaces artifact (world chip / gantry / mailbox source),
  * the pinned Telegram queue card,
  * the "Needs you (N)" briefing section.

Also runs the seeder's plan logic against fixtures (C7 dedup-awareness:
live-covered items are never double-carded).
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from framework.attention import queue as q
from framework.attention import queue_card

NOW = datetime(2026, 7, 10, 9, 0, tzinfo=timezone.utc)


def matrix_stub(step):
    return {"deploy_prod": "gate",
            "external_send": "external_per_item"}.get(
        (step or {}).get("action_type"), "gate")


def _sit(i, deadline=None):
    key = f"sit-{i:02d}"
    return {
        "key": key, "aliases": [key], "refs": [f"cmt-{i:012x}"],
        "subject": f"situation {i}", "lane": "polads", "state": "pending",
        "live": True, "demotions": 0, "open_pids": [f"pid-{i}"],
        "pid": f"pid-{i}", "created_ts": f"2026-07-{9 - (i % 2):02d}T09:00:00Z",
        "last_ts": "2026-07-09T09:00:00Z",
        "last_surfaced_at": "2026-07-09T10:00:00Z",
        "standing_message_id": 100 + i, "class_id": "action-card",
        "urgency": None, "deadline_iso": deadline,
        "harm_class": "external_deadline" if deadline else "none",
        "blocked_leverage": 0, "kind": None, "filed_by": "officer:cos",
        "actions": ["action-card"],
        "counts": {"proposals": 1, "expiries": 0, "decided": 0,
                   "acted": 0, "sends": 1, "closures": 0},
    }


class TestSurfaceParity(unittest.TestCase):
    def _census(self):
        view = {}
        for i in range(4):
            view[f"sit-{i:02d}"] = _sit(
                i, deadline=f"2026-07-1{1 + i}T09:00:00Z")
        view["sit-99"] = _sit(99)   # clock-less → Directions
        return q.build_queue(
            now=NOW, view=view, needs_rows=[], t2_rows=[], redis_cards={},
            charter={}, resolve_step=matrix_stub, enforce_admission=True,
            file_overflow_need=lambda *a, **k: None)

    def test_one_census_every_skin_same_items_same_order(self):
        census = self._census()
        private = q.to_private_census(census)
        shared = q.to_shared_census(census)

        api_ids = [r["id"] for r in private["decisions"]]
        artifact_ids = [r["id"] for r in shared["decisions"]]
        card_ids = [i for i, _line in queue_card.pinned_card_lines(private)]

        self.assertEqual(api_ids, artifact_ids)
        self.assertEqual(api_ids, card_ids)
        # ranked order is the deterministic tuple: nearest deadline first
        self.assertEqual(api_ids, ["sit-00", "sit-01", "sit-02", "sit-03"])

        # the ONE glance int agrees everywhere (badge / SSE chip / card head)
        n = census["pending_captain_items"]
        self.assertEqual(private["pending_captain_items"], n)
        self.assertEqual(shared["pending_captain_items"], n)
        self.assertIn(f"⚑ Needs you ({n})",
                      queue_card.render_pinned_card(private))
        briefing = queue_card.briefing_needs_you_item(private, now=NOW)
        self.assertIn(f"⚑ Needs you ({n})", briefing["payload"]["summary"])
        self.assertEqual(briefing["payload"]["pending_captain_items"], n)

        # directions shelf agrees too
        self.assertEqual([r["id"] for r in private["directions"]],
                         [r["id"] for r in shared["directions"]])
        self.assertEqual(private["directions"][0]["id"], "sit-99")

    def test_shared_and_private_disagree_only_on_pii(self):
        census = self._census()
        private = q.to_private_census(census)
        shared = q.to_shared_census(census)
        for priv_row, shared_row in zip(private["decisions"],
                                        shared["decisions"]):
            self.assertEqual(priv_row["id"], shared_row["id"])
            self.assertEqual(priv_row["h"], shared_row["h"])
            self.assertEqual(priv_row["deadline_iso"],
                             shared_row["deadline_iso"])
            self.assertNotIn("what", shared_row)
            self.assertNotIn("pid", shared_row)


class TestSeederPlan(unittest.TestCase):
    def _load(self):
        import importlib.util
        from pathlib import Path
        p = Path(__file__).resolve().parents[3] / "cabinet/scripts/seed-war-room.py"
        spec = importlib.util.spec_from_file_location("seed_war_room", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_live_covered_items_skip(self):
        seeder = self._load()
        live = [{"subject": "Ship the PolAds v1.0 release checklist",
                 "refs": ["monday:5091706356"]}]
        actions = {i["slug"]: a for i, a, _w in seeder.plan(live)}
        self.assertEqual(actions["polads-v1-release"], "skip-live")
        self.assertEqual(actions["h0-germline-ritual"], "seed")

    def test_seed_anchor_makes_rerun_idempotent(self):
        seeder = self._load()
        seeded = [{"subject": "H0: arm the gateway",
                   "refs": ["thread:seed/h0-germline-ritual",
                            "kind:germline-handback"]}]
        actions = {i["slug"]: a for i, a, _w in seeder.plan(seeded)}
        self.assertEqual(actions["h0-germline-ritual"], "skip-seeded")

    def test_seeded_rows_carry_parseable_tags(self):
        seeder = self._load()
        from framework.attention import situations
        item = next(i for i in seeder.C7_ITEMS
                    if i["slug"] == "dg-just-coverage")
        refs = seeder.item_refs(item)
        self.assertEqual(situations.deadline_of(refs), "2026-07-14T07:00:00Z")
        self.assertIn("thread:seed/dg-just-coverage",
                      __import__("framework.attention.situation",
                                 fromlist=["canonical_refs"])
                      .canonical_refs(refs))


if __name__ == "__main__":
    unittest.main()
