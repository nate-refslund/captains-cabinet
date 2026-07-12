"""framework.attention.verdicts — the equal-authority verdict door.

Pins (Ruling A, captain-decisions 2026-07-10):
  * revision fingerprint golden vectors (shared with the dashboard's TS
    implementation — cross-language drift breaks BOTH suites);
  * fail-closed freshness: absent/stale census, unknown pid, revision
    mismatch, already-decided — the wire is NEVER touched on any of them;
  * verb legality from census one_tap semantics (ritual sign-offs refused);
  * canonical grammar composition — the door speaks the org's own verbs;
  * 'later' NEVER reaches the wire for proposal cards (a non-verdict reply
    would EXPIRE the proposal — the exact opposite of 'come back later');
  * receipts + denials journal as attention-feed rows; a failed journal
    write is SURFACED on the result, never silent;
  * the JSON-over-stdio bridge round-trips.
"""
from __future__ import annotations

import io
import json
import unittest
from datetime import datetime, timezone

from framework.attention import plain, verdicts

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)

ROW = {
    "id": "sit-1", "kind": "action-proposal", "state": "pending",
    "pid": "prop-abc", "what": "Reply to Alice",
    "deadline_iso": "2026-07-12T10:00:00Z", "age_h": 5.0,
    "blast": {"class": "external", "reach": "external"},
    "blast_worst_case": "a message reaches a human outside the machine",
    "one_tap": {"approve": "direct", "veto": "direct", "defer": "direct"},
    "refs": ["cmt-4821"], "lane": "polads",
}
RITUAL_ROW = {
    **ROW, "id": "sit-2", "pid": "gl-hand-1", "kind": "germline-handback",
    "one_tap": {"approve": "ritual-print", "veto": "direct", "defer": "direct"},
}
NEED_ROW = {
    **ROW, "id": "need-a4f2", "pid": "NEED-a4f2", "kind": "need",
    "one_tap": {"approve": "direct", "veto": "direct", "defer": "direct"},
}


def census(rows=None, generated_at="2026-07-10T11:59:00Z"):
    return {"v": 1, "generated_at": generated_at,
            "decisions": list(rows or [ROW, RITUAL_ROW, NEED_ROW]),
            "directions": []}


def rev(row):
    return verdicts.revision_of(row)


class Journal:
    """Capture feed rows; optionally fail like a broken feed dir."""

    def __init__(self, fail=False):
        self.rows, self.fail, self._seq = [], fail, 100

    def __call__(self, row):
        if self.fail:
            raise OSError("feed dir unwritable")
        self._seq += 1
        stamped = dict(row)
        stamped["seq"] = self._seq
        self.rows.append(stamped)
        return stamped


class Wire:
    def __init__(self, result=None, exc=None):
        self.calls, self.result, self.exc = [], result, exc

    def __call__(self, text, quoted):
        self.calls.append((text, quoted))
        if self.exc:
            raise self.exc
        return self.result if self.result is not None else {
            "handled": True, "status": "decided", "verdict": "confirmed",
            "primary": "approve", "pid": "prop-abc",
            "delivery": {"ok": True, "via": "test", "dest": "board"}}


class TestRevision(unittest.TestCase):
    def test_golden_vectors_match_the_dashboard(self):
        self.assertEqual(
            rev({"pid": "prop-abc", "state": "pending", "what": "Reply to Alice",
                 "deadline_iso": "2026-07-12T10:00:00Z"}),
            "3c71acd88ad8ab07")
        self.assertEqual(
            rev({"pid": "prop-abc", "state": "pending", "what": None,
                 "deadline_iso": None}),
            "2b05d32c9837b8b4")

    def test_content_change_moves_the_revision(self):
        self.assertNotEqual(rev(ROW), rev({**ROW, "state": "surfaced"}))


class TestFreshness(unittest.TestCase):
    def test_ok(self):
        row, code, refreshed = verdicts.fresh_row(
            "prop-abc", rev(ROW), census=census(), now=NOW)
        self.assertEqual(code, "ok")
        self.assertEqual(row["pid"], "prop-abc")
        self.assertIsNone(refreshed)

    def test_gone_stale_decided(self):
        _, code, _ = verdicts.fresh_row("nope", "0" * 16, census=census(), now=NOW)
        self.assertEqual(code, "gone")
        _, code, refreshed = verdicts.fresh_row(
            "prop-abc", "f" * 16, census=census(), now=NOW)
        self.assertEqual(code, "stale")
        self.assertEqual(refreshed["pid"], "prop-abc")
        decided = {**ROW, "state": "acted"}
        _, code, _ = verdicts.fresh_row(
            "prop-abc", rev(decided), census=census([decided]), now=NOW)
        self.assertEqual(code, "decided")

    def test_stale_census_fails_closed(self):
        doc = census(generated_at="2026-07-10T10:00:00Z")  # 2h old
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "queue.json"
            p.write_text(json.dumps(doc), encoding="utf-8")
            self.assertIsNone(verdicts.read_census(p, now=NOW))
            fresh_doc = census()
            p.write_text(json.dumps(fresh_doc), encoding="utf-8")
            self.assertIsNotNone(verdicts.read_census(p, now=NOW))


class TestVerbLegality(unittest.TestCase):
    def test_ritual_refused(self):
        ok, code = verdicts.verb_allowed(RITUAL_ROW, "approve")
        self.assertFalse(ok)
        self.assertEqual(code, "ritual")

    def test_direct_and_per_item_allowed(self):
        self.assertTrue(verdicts.verb_allowed(ROW, "approve")[0])
        draft = {**ROW, "kind": "draft-outbound",
                 "one_tap": {**ROW["one_tap"], "approve": "per-item-approval"}}
        self.assertTrue(verdicts.verb_allowed(draft, "approve")[0])

    def test_missing_one_tap_is_not_here(self):
        ok, code = verdicts.verb_allowed({**ROW, "one_tap": None}, "approve")
        self.assertFalse(ok)
        self.assertEqual(code, "not_here")

    def test_unknown_verb(self):
        self.assertEqual(verdicts.verb_allowed(ROW, "maybe"), (False, "bad_verb"))


class TestCanonical(unittest.TestCase):
    def test_proposal_grammar(self):
        self.assertEqual(verdicts.canonical("approve", ROW),
                         ("approve", "·prop-abc·"))
        text, quoted = verdicts.canonical("no", ROW)
        self.assertTrue(text.startswith("skip: "))
        self.assertEqual(quoted, "·prop-abc·")

    def test_later_never_touches_the_wire_for_proposals(self):
        self.assertEqual(verdicts.canonical("later", ROW), (None, ""))

    def test_need_grammar(self):
        self.assertEqual(verdicts.canonical("approve", NEED_ROW),
                         ("grant NEED-a4f2", ""))
        self.assertEqual(verdicts.canonical("no", NEED_ROW),
                         ("deny NEED-a4f2", ""))
        self.assertEqual(verdicts.canonical("later", NEED_ROW),
                         ("later NEED-a4f2", ""))


class TestFire(unittest.TestCase):
    def test_approve_full_path(self):
        wire, journal = Wire(), Journal()
        res = verdicts.fire("prop-abc", "approve", rev(ROW),
                            census=census(), wire=wire, journal=journal)
        self.assertTrue(res["ok"])
        self.assertEqual(wire.calls, [("approve", "·prop-abc·")])
        self.assertEqual(res["receipt_seq"], 101)
        self.assertEqual(res["plain_result"], plain.RESULTS["approved_underway"])
        self.assertEqual(plain.lint(res["plain_result"]), [])
        row = journal.rows[0]
        self.assertEqual((row["direction"], row["kind"], row["source"]),
                         ("in", "verdict", "dashboard"))
        self.assertEqual((row["phase"], row["pid"], row["verb"]),
                         ("fire", "prop-abc", "approve"))

    def test_approve_delivery_failure_is_surfaced(self):
        wire = Wire(result={"handled": True, "status": "decided",
                            "verdict": "confirmed", "primary": "approve",
                            "delivery": {"ok": False, "error": "boom"}})
        res = verdicts.fire("prop-abc", "approve", rev(ROW),
                            census=census(), wire=wire, journal=Journal())
        self.assertTrue(res["ok"])
        self.assertEqual(res["plain_result"],
                         plain.RESULTS["approved_delivery_failed"])

    def test_no_records_a_skip(self):
        wire, journal = Wire(result={"handled": True, "status": "decided",
                                     "verdict": "unknown", "primary": "skip"}), Journal()
        res = verdicts.fire("prop-abc", "no", rev(ROW),
                            census=census(), wire=wire, journal=journal)
        self.assertTrue(res["ok"])
        self.assertTrue(wire.calls[0][0].startswith("skip: "))
        self.assertEqual(res["plain_result"], plain.RESULTS["declined"])

    def test_later_defers_without_the_wire(self):
        wire, journal = Wire(), Journal()
        res = verdicts.fire("prop-abc", "later", rev(ROW),
                            census=census(), wire=wire, journal=journal)
        self.assertTrue(res["ok"])
        self.assertTrue(res["deferred"])
        self.assertEqual(wire.calls, [])  # the load-bearing assertion
        self.assertEqual(journal.rows[0]["outcome"], "deferred")

    def test_need_later_falls_back_to_defer_when_wire_dark(self):
        wire = Wire(result={"handled": False, "reason": "no-pid"})
        res = verdicts.fire("NEED-a4f2", "later", rev(NEED_ROW),
                            census=census(), wire=wire, journal=Journal())
        self.assertTrue(res["ok"])
        self.assertTrue(res["deferred"])
        self.assertEqual(wire.calls, [("later NEED-a4f2", "")])

    def test_stale_refuses_before_the_wire(self):
        wire, journal = Wire(), Journal()
        res = verdicts.fire("prop-abc", "approve", "f" * 16,
                            census=census(), wire=wire, journal=journal)
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "stale")
        self.assertEqual(wire.calls, [])
        self.assertEqual(res["refreshed"]["revision"], rev(ROW))
        self.assertEqual(plain.lint(res["message"]), [])
        self.assertEqual(journal.rows[0]["phase"], "deny")

    def test_ritual_refused_before_the_wire(self):
        wire = Wire()
        res = verdicts.fire("gl-hand-1", "approve", rev(RITUAL_ROW),
                            census=census(), wire=wire, journal=Journal())
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "ritual")
        self.assertEqual(wire.calls, [])

    def test_unhandled_wire_is_honest_not_here(self):
        wire = Wire(result={"handled": False, "reason": "no-pending-match"})
        res = verdicts.fire("prop-abc", "approve", rev(ROW),
                            census=census(), wire=wire, journal=Journal())
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "not_here")
        self.assertEqual(plain.lint(res["message"]), [])

    def test_already_decided_at_the_wire(self):
        wire = Wire(result={"handled": True, "status": "already-decided"})
        res = verdicts.fire("prop-abc", "approve", rev(ROW),
                            census=census(), wire=wire, journal=Journal())
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "decided")

    def test_wire_exception_is_bridge_fail(self):
        wire = Wire(exc=RuntimeError("redis down"))
        res = verdicts.fire("prop-abc", "approve", rev(ROW),
                            census=census(), wire=wire, journal=Journal())
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "bridge_fail")

    def test_journal_failure_is_surfaced_never_silent(self):
        res = verdicts.fire("prop-abc", "later", rev(ROW),
                            census=census(), wire=Wire(), journal=Journal(fail=True))
        self.assertTrue(res["ok"])
        self.assertIsNone(res["receipt_seq"])
        self.assertEqual(res["journal_warn"], plain.MESSAGES["journal_warn"])


class TestBridgeStdio(unittest.TestCase):
    def test_journal_op(self):
        journal = Journal()
        res = verdicts.handle_request(
            {"op": "journal", "rows": [
                {"phase": "deny", "code": "csrf", "http_status": 403},
                {"phase": "arm", "pid": "prop-abc", "verb": "approve"}]},
            journal=journal)
        self.assertTrue(res["ok"])
        self.assertEqual(res["written"], 2)
        self.assertEqual(journal.rows[0]["code"], "csrf")
        self.assertEqual(journal.rows[0]["http_status"], 403)
        self.assertEqual(journal.rows[1]["phase"], "arm")

    def test_fire_op_validates_shape(self):
        res = verdicts.handle_request({"op": "fire", "pid": "", "verb": "approve",
                                       "revision": "x"})
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "bad_request")

    def test_main_round_trip(self):
        # A journal op through the real main() with an injected feed dir is
        # covered by the subprocess smoke below; here: malformed JSON in.
        out = io.StringIO()
        rc = verdicts.main(stdin=io.StringIO("this is not json"), stdout=out)
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(out.getvalue())["code"], "bad_request")

    def test_subprocess_smoke_journal(self):
        import os
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        repo = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items()
                   if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")}
            env["CABINET_FEED_DIR"] = d
            req = json.dumps({"op": "journal", "rows": [
                {"phase": "deny", "code": "rate_limited", "http_status": 429}]})
            proc = subprocess.run(
                [sys.executable, "-m", "framework.attention.verdicts"],
                input=req, capture_output=True, text=True, cwd=repo, env=env,
                timeout=30)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            res = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertTrue(res["ok"], res)
            feed_files = list(Path(d).glob("feed-*.jsonl"))
            self.assertEqual(len(feed_files), 1)
            row = json.loads(feed_files[0].read_text().strip())
            self.assertEqual(row["kind"], "verdict")
            self.assertEqual(row["source"], "dashboard")
            self.assertEqual(row["code"], "rate_limited")


if __name__ == "__main__":
    unittest.main()
