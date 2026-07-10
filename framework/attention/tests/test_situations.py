"""Tests for framework.attention.situations — the §4.2 derived view.

Pinned behaviors:
  * one situation per canonical ref-set (H1 identity dedup at the fold);
  * lifecycle fold: open → surfaced/pending → decided/acted → resolved;
  * H5 re-type: an expired proposal DEMOTES (stays live), never resolves;
  * demotions past the demote path park as dormant (census, not shelf);
  * closure feed rows are the closing VERB (H2);
  * Captain reversal (undo journal) re-opens an acted/decided situation;
  * deadline:/harm:/leverage: ref tags parse, prose deadlines cannot.
"""
from __future__ import annotations

import unittest

from framework.attention import situations
from framework.attention.situation import situation_key

REF = "cmt-fca6836e2844"
TS0 = "2026-07-08T10:00:00Z"
TS1 = "2026-07-08T11:00:00Z"
TS2 = "2026-07-08T12:00:00Z"
TS3 = "2026-07-08T13:00:00Z"


def prop_row(ts=TS0, subject="sign deed", refs=(REF,), decision=None,
             action="action-card", actor_id="cos", outcome=None):
    row = {
        "ts": ts, "actor": {"kind": "officer", "id": actor_id}, "lane": "l",
        "action": action, "subject": subject, "refs": list(refs),
        "proposal": {"required": True, "decision": decision},
    }
    if decision is not None:
        row["proposal"]["decided_at"] = ts
    if outcome is not None:
        row["outcome"] = outcome
    return row


def derive(ledger=(), journal=(), feed=(), standing=None):
    return situations.derive(ledger_rows=list(ledger),
                             journal_rows=list(journal),
                             feed_rows=list(feed), standing=standing or {})


class TestIdentityFold(unittest.TestCase):
    def test_same_refs_one_situation(self):
        # Three differently-phrased cards sharing one commitment id → ONE
        # situation (the H1 76→31 collapse, at the fold).
        view = derive(ledger=[
            prop_row(TS0, "sign the deed", [f"vault/x.md — note, {REF}"]),
            prop_row(TS1, "deed signing reminder", [REF]),
            prop_row(TS2, "bring passport for signing", [f"{REF} (again)"]),
        ])
        self.assertEqual(len(view), 1)
        sit = next(iter(view.values()))
        self.assertEqual(sit["counts"]["proposals"], 3)
        self.assertEqual(len(sit["open_pids"]), 3)
        self.assertTrue(sit["live"])

    def test_feed_row_keyed_by_alias_folds_into_merged_situation(self):
        # Two revisions of one situation (superset refs) merge; a feed row
        # keyed by the LATER revision's exact key lands on the merged row.
        r1 = prop_row(TS0, "s", [REF])
        r2 = prop_row(TS1, "s", [REF, "vault/notes/x.md"])
        alias = situation_key([REF, "vault/notes/x.md"], "s")
        view = derive(ledger=[r1, r2],
                      feed=[{"seq": 1, "ts": TS2, "direction": "out",
                             "kind": "action-card", "situation_key": alias,
                             "telegram_message_id": 9}])
        self.assertEqual(len(view), 1)
        sit = next(iter(view.values()))
        self.assertEqual(sit["standing_message_id"], 9)
        self.assertIn(alias, sit["aliases"])

    def test_path_only_overlap_never_merges(self):
        # A rolling digest .md hosts many situations — path-grade overlap is
        # NOT identity (the documented false-positive vector).
        view = derive(ledger=[
            prop_row(TS0, "a", ["5-monday/digest.md", "cmt-aaaaaaaaaaaa"]),
            prop_row(TS1, "b", ["5-monday/digest.md", "cmt-bbbbbbbbbbbb"]),
        ])
        self.assertEqual(len(view), 2)

    def test_refless_items_stay_separate(self):
        view = derive(ledger=[
            prop_row(TS0, "subject one", ["just prose"]),
            prop_row(TS1, "subject two", ["other prose"]),
        ])
        self.assertEqual(len(view), 2)


class TestLifecycle(unittest.TestCase):
    def test_open_then_surfaced_then_pending(self):
        key = situation_key([REF], "s")
        open_only = derive(ledger=[prop_row()])
        self.assertEqual(open_only[key]["state"], "open")

        surfaced = derive(
            ledger=[prop_row()],
            feed=[{"seq": 1, "ts": TS1, "direction": "out", "kind": "action-card",
                   "situation_key": key, "telegram_message_id": 77}])
        self.assertEqual(surfaced[key]["state"], "pending")
        self.assertEqual(surfaced[key]["standing_message_id"], 77)
        self.assertEqual(surfaced[key]["last_surfaced_at"], TS1)

    def test_captain_decision_closes(self):
        key = situation_key([REF], "s")
        view = derive(ledger=[prop_row(TS0, decision="approve",
                                       outcome={"status": "ok",
                                                "evidence": "sent"})])
        self.assertEqual(view[key]["state"], "decided")
        self.assertFalse(view[key]["live"])

    def test_acted_row_is_world_proof(self):
        key = situation_key([REF], "s")
        view = derive(ledger=[
            {"ts": TS1, "actor": {"kind": "officer", "id": "cos"}, "lane": "l",
             "action": "acted:calendar_event_create", "subject": "s",
             "refs": [REF],
             "outcome": {"status": "ok", "evidence": "event uuid"}},
        ])
        self.assertEqual(view[key]["state"], "acted")
        self.assertFalse(view[key]["live"])

    def test_closure_feed_row_resolves(self):
        key = situation_key([REF], "s")
        view = derive(
            ledger=[prop_row(TS0, decision="skip")],
            feed=[{"seq": 2, "ts": TS2, "direction": "in", "kind": "closure",
                   "situation_key": key}])
        self.assertEqual(view[key]["state"], "resolved")
        self.assertFalse(view[key]["live"])

    def test_open_proposal_newer_than_closure_stays_live(self):
        key = situation_key([REF], "s")
        view = derive(
            ledger=[prop_row(TS3)],   # fresh open proposal after the closure
            feed=[{"seq": 2, "ts": TS2, "direction": "in", "kind": "closure",
                   "situation_key": key}])
        self.assertTrue(view[key]["live"])


class TestH5ExpiryRetype(unittest.TestCase):
    def test_expired_demotes_but_stays_live(self):
        key = situation_key([REF], "s")
        view = derive(ledger=[prop_row(TS0, decision="expired")])
        sit = view[key]
        self.assertEqual(sit["demotions"], 1)
        self.assertEqual(sit["counts"]["expiries"], 1)
        self.assertTrue(sit["live"], "H5: expiry must NOT close the situation")

    def test_expiries_past_path_park_dormant(self):
        rows = [prop_row(f"2026-07-0{i}T10:00:00Z", decision="expired")
                for i in range(1, 6)]   # 5 expiries ≥ parked tier (4)
        key = situation_key([REF], "s")
        view = derive(ledger=rows)
        self.assertEqual(view[key]["state"], "dormant")
        self.assertFalse(view[key]["live"])
        # Parked still counts in the census (never deleted).
        self.assertIn(key, view)

    def test_open_pid_beside_old_expiries_stays_pending_shape(self):
        key = situation_key([REF], "s")
        view = derive(ledger=[prop_row(TS0, decision="expired"),
                              prop_row(TS2)])
        self.assertTrue(view[key]["live"])
        self.assertEqual(view[key]["demotions"], 1)
        self.assertIsNotNone(view[key]["pid"])


class TestReversal(unittest.TestCase):
    def test_reversed_act_reopens(self):
        cid = "cabinet-proposal-id:aabbccdd1122"
        acted = {"ts": TS1, "actor": {"kind": "officer", "id": "cos"},
                 "lane": "l", "action": "acted:calendar_event_create",
                 "subject": "s", "refs": [REF, cid],
                 "outcome": {"status": "ok", "evidence": "uuid"}}
        journal = [{"jid": "j1", "cid": "aabbccdd1122", "status": "reversed",
                    "ts": TS2}]
        key = situation_key([REF, cid], "s")
        view = derive(ledger=[acted], journal=journal)
        self.assertEqual(view[key]["state"], "open")
        self.assertTrue(view[key]["live"])


class TestRefTags(unittest.TestCase):
    def test_deadline_tag_parses_real_iso_only(self):
        key = situation_key([REF], "s")
        view = derive(ledger=[prop_row(
            refs=[REF, "deadline:2026-07-14T09:00:00Z"])])
        self.assertEqual(view[key]["deadline_iso"], "2026-07-14T09:00:00Z")
        self.assertEqual(view[key]["harm_class"], "external_deadline")

        prose = derive(ledger=[prop_row(refs=[REF, "deadline:today"])])
        self.assertIsNone(prose[situation_key([REF], "s")]["deadline_iso"])

    def test_harm_kind_leverage_tags(self):
        key = situation_key([REF], "s")
        view = derive(ledger=[prop_row(refs=[
            REF, "harm:value_decay", "kind:germline-handback", "leverage:3"])])
        sit = view[key]
        self.assertEqual(sit["harm_class"], "value_decay")
        self.assertEqual(sit["kind"], "germline-handback")
        self.assertEqual(sit["blocked_leverage"], 3)

    def test_no_deadline_means_harm_none(self):
        key = situation_key([REF], "s")
        view = derive(ledger=[prop_row()])
        self.assertEqual(view[key]["harm_class"], "none")
        self.assertIsNone(view[key]["deadline_iso"])


class TestStandingMapAndCensus(unittest.TestCase):
    def test_standing_map_backfills_message_id(self):
        key = situation_key([REF], "s")
        view = derive(ledger=[prop_row()],
                      standing={key: {"message_id": 42, "state": "open",
                                      "class_id": "action-card", "ts": TS1}})
        self.assertEqual(view[key]["standing_message_id"], 42)
        self.assertEqual(view[key]["class_id"], "action-card")
        self.assertEqual(view[key]["state"], "pending")   # surfaced + open pid

    def test_live_situations_ordering(self):
        view = derive(ledger=[
            prop_row(TS2, "b", ["cmt-bbbbbbbbbbbb"]),
            prop_row(TS0, "a", ["cmt-aaaaaaaaaaaa"]),
            prop_row(TS1, "closed", ["cmt-cccccccccccc"], decision="skip"),
        ])
        live = situations.live_situations(view)
        self.assertEqual([s["subject"] for s in live], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
