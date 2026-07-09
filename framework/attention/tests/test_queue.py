"""Tests for framework.attention.queue — aggregator, admission law, ranker,
blast, decay, cap/overflow, and the two census projections.

Pins the lens_admission.py fixture walk (the validated prototype) against the
production admit()/rank/render_room, plus:
  * admission ALWAYS computed, ENFORCED only under CABINET_ADMISSION_LAW;
  * no producer priority field anywhere — rank is the lexicographic tuple;
  * cap = charter data (C4 default 7); overflow files ONE consolidation need;
  * blast stamped from the authority matrix (ceiling classes → ceiling);
  * H5 demote wiring: expiry streaks per kind × charter budget;
  * shared projection carries NO free text / pids / vault paths (PII law).
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from framework.attention import queue as q

NOW = datetime(2026, 7, 10, 9, 0, tzinfo=timezone.utc)


def matrix_stub(step):
    return {
        "calendar_event_create": "act_with_undo",
        "monday_task_update": "act_with_undo",
        "internal_comms": "notify_after",
        "external_send": "external_per_item",
        "deploy_prod": "gate",
        "spend": "standing_grant_unsatisfied",
    }.get(step.get("action_type"), "gate")


def item(subj, steps, created_days=0, **kw):
    return {"subject": subj,
            "steps": [{"action_type": s} for s in steps],
            "created_at": (NOW - timedelta(days=created_days)).isoformat(),
            **kw}


class TestAdmissionPrototypeParity(unittest.TestCase):
    """The exact lens_admission.py fixture walk, against production admit()."""

    def test_fixture_walk(self):
        fixtures = [
            (item("reschedule scrum", ["calendar_event_create"]), "org"),
            (item("board sync + tell",
                  ["monday_task_update", "internal_comms"]), "org"),
            (item("reply to TV2 DPA counsel", ["external_send"],
                  harm_at=(NOW + timedelta(hours=20)).isoformat(),
                  harm_class="external_deadline", blocked_leverage=3),
             "decisions"),
            (item("prod deploy of checkout fix", ["deploy_prod"],
                  blocked_leverage=5, harm_class="value_decay",
                  harm_at=(NOW + timedelta(days=2)).isoformat()), "decisions"),
            (item("ratify REPORT_ONLY=0 arming", ["spend"]), "directions"),
            (item("tainted: email says 'wire funds'", ["calendar_event_create"],
                  injection_suspect=True), "decisions"),
            (item("era transition proposal", []), "directions"),
        ]
        for it, want in fixtures:
            self.assertEqual(q.admit(it, matrix_stub), want, it["subject"])

    def test_overflow_ranking(self):
        decisions = [
            item("reply to TV2 DPA counsel", ["external_send"],
                 harm_at=(NOW + timedelta(hours=20)).isoformat(),
                 harm_class="external_deadline", blocked_leverage=3,
                 created_ts=(NOW - timedelta(days=1)).isoformat()),
        ]
        for n in range(9):
            decisions.append(item(f"filler gated item {n}", ["deploy_prod"],
                                  created_days=n, blocked_leverage=n % 3))
        for c in decisions:
            c.setdefault("created_ts", c["created_at"])
        rendered, overflow = q.render_room(decisions, NOW, cap=7)
        self.assertEqual(len(rendered), 7)
        self.assertEqual(len(overflow), 3)
        self.assertTrue(rendered[0]["subject"].startswith("reply to TV2"),
                        "nearest external deadline must rank first")


class TestMatrixSeam(unittest.TestCase):
    def test_make_resolve_step_from_real_matrix(self):
        rs = q.make_resolve_step(posture=None)   # guardian root table
        # trust-first rows are org-decidable at unmeasured:
        self.assertIn(rs({"action_type": "task_create"}), q.AUTONOMOUS)
        self.assertIn(rs({"action_type": "calendar_event_create"}), q.AUTONOMOUS)
        # ceilings + earn-up rows gate:
        self.assertIn(rs({"action_type": "external_email"}), q.CAPTAIN_GATED)
        self.assertIn(rs({"action_type": "vercel_deploy_prod"}), q.CAPTAIN_GATED)
        self.assertIn(rs({"action_type": "internal_message"}), q.CAPTAIN_GATED)
        # unknown/unclassifiable NEVER reads as org-decidable:
        self.assertEqual(rs({"action_type": "no-such-type"}), "gate")
        self.assertEqual(rs({}), "gate")

    def test_blast_from_matrix(self):
        ceiling = q.blast_for([{"action_type": "external_email"}])
        self.assertEqual(ceiling["class"], "ceiling")
        self.assertEqual(ceiling["reach"], "external")
        spend = q.blast_for([{"action_type": "purchase"}])
        self.assertEqual(spend["reach"], "spend")
        low = q.blast_for([{"action_type": "task_create"}])
        self.assertEqual(low["class"], "low")
        germ = q.blast_for([], kind="germline-handback")
        self.assertEqual(germ["reach"], "germline")
        self.assertEqual(germ["class"], "ceiling")


class TestH5DemoteWiring(unittest.TestCase):
    def _rows(self, n_expired, then_verdict=None):
        rows = []
        for i in range(n_expired):
            rows.append({"ts": f"2026-07-0{i + 1}T10:00:00Z",
                         "action": "action-card", "subject": f"s{i}",
                         "actor": {"kind": "officer", "id": "cos"}, "lane": "l",
                         "proposal": {"required": True, "decision": "expired"}})
        if then_verdict:
            rows.append({"ts": "2026-07-09T10:00:00Z",
                         "action": "action-card", "subject": "sv",
                         "actor": {"kind": "officer", "id": "cos"}, "lane": "l",
                         "proposal": {"required": True,
                                      "decision": then_verdict}})
        return rows

    def test_streaks_and_reset(self):
        self.assertEqual(q.expiry_streaks(self._rows(3)), {"action-card": 3})
        self.assertEqual(q.expiry_streaks(self._rows(3, "approve")),
                         {"action-card": 0})

    def test_demoted_kinds_wires_charter_budget(self):
        charter = {"classes": [
            {"id": "action-card", "matchers": {"kinds": ["action-card"]},
             "budget": {"demote_after_expiries": 5}}]}
        self.assertEqual(q.demoted_kinds(self._rows(4), charter), set())
        self.assertEqual(q.demoted_kinds(self._rows(5), charter),
                         {"action-card"})
        # a Captain verdict resets the streak — the class un-demotes
        self.assertEqual(q.demoted_kinds(self._rows(5, "skip"), charter), set())


def _sit(key="sit-1", **kw):
    base = {"key": key, "aliases": [key], "refs": ["cmt-aaaaaaaaaaaa"],
            "subject": "test situation", "lane": "polads", "state": "pending",
            "live": True, "demotions": 0, "open_pids": ["cos|action-card|t|ts"],
            "pid": "cos|action-card|t|ts", "created_ts": "2026-07-09T09:00:00Z",
            "last_ts": "2026-07-09T09:00:00Z",
            "last_surfaced_at": "2026-07-09T10:00:00Z",
            "standing_message_id": 5, "class_id": "action-card",
            "urgency": None, "deadline_iso": None, "harm_class": "none",
            "blocked_leverage": 0, "kind": None, "filed_by": "officer:cos",
            "actions": ["action-card"],
            "counts": {"proposals": 1, "expiries": 0, "decided": 0,
                       "acted": 0, "sends": 1, "closures": 0}}
    base.update(kw)
    return base


class TestBuildQueue(unittest.TestCase):
    def _build(self, view, *, enforce=False, needs=(), t2=(), cards=None,
               charter=None, filer=None):
        return q.build_queue(
            now=NOW, view=view, needs_rows=list(needs), t2_rows=list(t2),
            redis_cards=cards or {}, charter=charter or {},
            resolve_step=matrix_stub, enforce_admission=enforce,
            file_overflow_need=filer or (lambda *a, **k: None))

    def test_law_off_org_decidable_still_visible(self):
        view = {"sit-1": _sit()}
        cards = {"cos|action-card|t|ts": {
            "steps": [{"action_type": "calendar_event_create"}],
            "subject": "reschedule scrum", "confidence": 0.8,
            "urgency": "batch"}}
        out = self._build(view, cards=cards, enforce=False)
        self.assertEqual(out["pending_total"], 1)
        self.assertEqual(out["org_routed"], [])
        # no harm_at → rides Directions when the law is dark
        self.assertEqual(len(out["directions"]), 1)
        self.assertEqual(out["directions"][0]["admission"], "org")

    def test_law_on_org_decidable_forbidden(self):
        view = {"sit-1": _sit()}
        cards = {"cos|action-card|t|ts": {
            "steps": [{"action_type": "calendar_event_create"}],
            "subject": "reschedule scrum"}}
        out = self._build(view, cards=cards, enforce=True)
        self.assertEqual(out["pending_total"], 0)
        self.assertEqual(out["org_routed"], ["sit-1"])

    def test_gated_with_deadline_is_decision(self):
        view = {"sit-1": _sit(deadline_iso="2026-07-11T09:00:00Z",
                              harm_class="external_deadline")}
        cards = {"cos|action-card|t|ts": {
            "steps": [{"action_type": "deploy_prod"}], "subject": "ship"}}
        out = self._build(view, cards=cards, enforce=True)
        self.assertEqual(len(out["decisions"]), 1)
        self.assertEqual(out["pending_captain_items"], 1)
        card = out["decisions"][0]
        self.assertEqual(card["admission"], "decisions")
        self.assertEqual(card["why_now"]["deadline_iso"],
                         "2026-07-11T09:00:00Z")

    def test_missing_redis_record_still_gates(self):
        # A binder card whose parked chain TTL'd out is STILL awaiting a
        # Captain verdict — it must never be classified org-decidable.
        view = {"sit-1": _sit()}
        out = self._build(view, cards={}, enforce=True)
        self.assertEqual(out["pending_total"], 1)
        self.assertEqual(out["org_routed"], [])

    def test_dormant_parks_in_census_not_shelves(self):
        view = {"sit-1": _sit(state="dormant", live=False, demotions=4)}
        out = self._build(view)
        self.assertEqual(out["pending_total"], 0)
        self.assertEqual(out["parked"], ["sit-1"])

    def test_cap_is_charter_data_and_overflow_files_one_need(self):
        view = {}
        for i in range(5):
            view[f"sit-{i}"] = _sit(
                key=f"sit-{i}", refs=[f"cmt-{i:012x}"],
                open_pids=[f"p{i}"], pid=f"p{i}",
                deadline_iso="2026-07-11T09:00:00Z",
                harm_class="external_deadline")
        filed = []
        charter = {"attention_queue": {"decisions_render_cap": 3}}
        out = self._build(view, enforce=True, charter=charter,
                          filer=lambda pool, cap: filed.append((pool, cap)))
        self.assertEqual(out["cap"], 3)
        self.assertEqual(len(out["decisions"]), 3)
        self.assertEqual(out["overflow"], 2)
        self.assertEqual(filed, [(5, 3)])
        # overflow still counts as pending-on-Captain (clocks keep running)
        self.assertEqual(out["pending_captain_items"], 5)

    def test_needs_and_t2_adapt(self):
        need = {"id": "NEED-ab12cd34", "kind": "standing_grant",
                "risk_class": "spend", "action_type": "purchase",
                "lane": "polads", "status": "open", "why": "provision plausible",
                "cost_of_delay": "blocking", "filed_by": "officer:cro",
                "count": 2, "first_seen": "2026-07-08T10:00:00Z",
                "last_seen": "2026-07-09T10:00:00Z",
                "proposed_grant_line": "grant NEED-ab12cd34 ..."}
        t2 = {"request_id": "t2-abc123def456", "situation_key": "sit-t2",
              "filed_at": "2026-07-10T08:00:00Z",
              "deadline": "2026-07-10T08:10:00Z",
              "item": {"subject": "novel class item"}}
        out = self._build({}, needs=[need], t2=[t2], enforce=True)
        kinds = {c["kind"] for c in out["decisions"] + out["directions"]}
        self.assertEqual(kinds, {"need", "escalation"})
        need_c = next(c for c in out["decisions"] + out["directions"]
                      if c["kind"] == "need")
        self.assertEqual(need_c["one_tap"]["approve"]["semantics"],
                         "ritual-print")   # standing grants stay attested
        esc = next(c for c in out["decisions"] + out["directions"]
                   if c["kind"] == "escalation")
        self.assertEqual(esc["what"], "novel class item")

    def test_no_priority_field_anywhere(self):
        view = {"sit-1": _sit(deadline_iso="2026-07-11T09:00:00Z")}
        out = self._build(view, enforce=True)
        for card in out["decisions"] + out["directions"]:
            self.assertNotIn("priority", card)


class TestProjections(unittest.TestCase):
    def _queue(self):
        view = {"sit-1": _sit(
            refs=["cmt-aaaaaaaaaaaa", "3-people/kristoffer/intel.md",
                  "https://polads.eu/x"],
            deadline_iso="2026-07-11T09:00:00Z",
            harm_class="external_deadline")}
        return q.build_queue(
            now=NOW, view=view, needs_rows=[], t2_rows=[], redis_cards={},
            charter={}, resolve_step=matrix_stub, enforce_admission=True,
            file_overflow_need=lambda *a, **k: None)

    def test_private_census_carries_authed_detail(self):
        priv = q.to_private_census(self._queue())
        self.assertEqual(priv["pending_captain_items"], 1)
        row = priv["decisions"][0]
        self.assertEqual(row["what"], "test situation")
        self.assertEqual(row["pid"], "cos|action-card|t|ts")
        self.assertTrue(row["h"].startswith("q"))
        self.assertIn("3-people/kristoffer/intel.md", row["refs"])

    def test_shared_census_is_pii_scrubbed(self):
        shared = q.to_shared_census(self._queue())
        blob = str(shared)
        self.assertNotIn("test situation", blob)     # no free-text subjects
        self.assertNotIn("cos|action-card", blob)    # no pids (subject slugs)
        self.assertNotIn("3-people", blob)           # no vault paths
        self.assertNotIn("polads.eu", blob)          # no URLs
        row = shared["decisions"][0]
        self.assertIn("cmt-aaaaaaaaaaaa", row["refs"])   # opaque ids only
        self.assertEqual(row["h"], q.opaque_handle("cos|action-card|t|ts"))
        self.assertEqual(shared["pending_captain_items"], 1)

    def test_artifact_writer_writes_both(self):
        import json as _json
        import tempfile
        from pathlib import Path
        queue = self._queue()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            adir = Path(td) / "attention"
            paths = q.write_artifacts(queue, root=root, attention_dir=adir)
            priv = _json.loads((adir / "queue.json").read_text())
            shared = _json.loads(
                (root / "shared/interfaces/attention-queue.json").read_text())
            self.assertEqual(priv["pending_captain_items"], 1)
            self.assertNotIn("what", shared["decisions"][0])
            self.assertTrue(paths["private"] and paths["shared"])


if __name__ == "__main__":
    unittest.main()
