"""B2.3 GitHub probe — FIXTURED only (zero live gh/git). The reference tests."""
from __future__ import annotations

from framework.acting import loop
from framework.probes import correlation as c
from framework.probes import lib
from framework.probes import probe_github as pg


# --- pure classify + _checks_green ------------------------------------------

def test_checks_green_parsing():
    assert pg._checks_green([{"conclusion": "SUCCESS"}, {"conclusion": "SKIPPED"}])
    assert not pg._checks_green([{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}])
    assert not pg._checks_green([])                    # empty ≠ green
    assert pg._checks_green([{"state": "success"}])    # state-form, case-insensitive


def test_classify_truth_table():
    merged = {"state": "MERGED", "mergedAt": "2026-07-03T02:00:00Z",
              "statusCheckRollup": [{"conclusion": "SUCCESS"}]}
    assert pg.classify(merged, reverted=False)[:2] == ("ok", "merged")
    # revert supersedes even a merged PR
    assert pg.classify(merged, reverted=True)[:2] == ("failed", "reverted")
    open_green = {"state": "OPEN", "statusCheckRollup": [{"conclusion": "SUCCESS"}]}
    assert pg.classify(open_green, reverted=False)[:2] == ("unknown", "ci_green")
    open_pending = {"state": "OPEN", "statusCheckRollup": [{"conclusion": "PENDING"}]}
    assert pg.classify(open_pending, reverted=False)[:2] == ("unknown", "held")
    closed = {"state": "CLOSED"}
    assert pg.classify(closed, reverted=False)[:2] == ("unknown", "held")


# --- fixtured client ---------------------------------------------------------

class FakeGh:
    def __init__(self, prs, views, reverts=frozenset(), commits=("sha1",)):
        self._prs, self._views = prs, views
        self._reverts, self._commits = set(reverts), list(commits)

    def trailer_prs(self, repo):
        return self._prs

    def pr_view(self, repo, number):
        return self._views.get(number, {})

    def reverts(self, repo, since_days=14):
        return self._reverts

    def local_commits_since(self, window="1 hour ago"):
        return self._commits


def _decided(cid, subject="pr-thread"):
    p = loop.proposal_event(actor={"kind": "officer", "id": "polads-ceo"},
                            lane="feature-impl", subject=subject,
                            ts="2026-07-03T01:00:00Z", refs=[c.ref_for(cid)])
    p["proposal"]["decision"] = "approved"
    p["proposal"]["decided_at"] = "2026-07-03T01:00:00Z"
    return p


def test_run_probe_emits_merged_ok():
    cid = c.mint()
    body = f"Implements the thing\n\n{c.git_trailer(cid)}"
    prs = [{"number": 42, "body": body, "merge_sha": "abc123"}]
    views = {42: {"state": "MERGED", "mergedAt": "2026-07-03T02:00:00Z",
                  "statusCheckRollup": [{"conclusion": "SUCCESS"}]}}
    emitted = []
    r = pg.run_probe(repo="o/r", client=FakeGh(prs, views), rows=[_decided(cid)],
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "pinged")
    assert r["fresh"] is True
    assert len(r["emitted"]) == 1 and r["emitted"][0]["status"] == "ok"
    assert emitted[0]["status"] == "ok" and emitted[0]["probe_status"] == "merged"


def test_run_probe_revert_emits_failed():
    cid = c.mint()
    prs = [{"number": 7, "body": c.git_trailer(cid), "merge_sha": "deadbee"}]
    views = {7: {"state": "MERGED", "mergedAt": "2026-07-01T00:00:00Z",
                 "statusCheckRollup": [{"conclusion": "SUCCESS"}]}}
    emitted = []
    r = pg.run_probe(repo="o/r", client=FakeGh(prs, views, reverts={7}),
                     rows=[_decided(cid)],
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "failed"
    assert emitted[0]["probe_status"] == "reverted"


def test_run_probe_freshness_silent_source_pages_no_emit():
    # no trailer-PRs found but local commits landed → not fresh: hc fail, no emit
    pinged = []
    r = pg.run_probe(repo="o/r", client=FakeGh([], {}, commits=["s1", "s2"]),
                     rows=[], emit=lambda **kw: pinged.append(("emit",)),
                     hc=lambda slug, fail=False: pinged.append(("hc", fail)))
    assert r["fresh"] is False
    assert ("hc", True) in pinged and ("emit",) not in pinged


def test_run_probe_unattributable_cid_skipped():
    cid = c.mint()  # a valid trailer, but NO matching decided proposal in rows
    prs = [{"number": 9, "body": c.git_trailer(cid), "merge_sha": None}]
    views = {9: {"state": "MERGED", "mergedAt": "t", "statusCheckRollup": []}}
    emitted = []
    r = pg.run_probe(repo="o/r", client=FakeGh(prs, views), rows=[],  # empty ledger
                     emit=lib.emit_outcome, hc=lambda *a, **k: "")
    assert r["emitted"] == [] and r["skipped"][0]["reason"] == "unattributable-cid"


def _record(sink, **kw):
    sink.append(kw)
    return {"emitted": True, "status": kw["status"], "probe_status": kw["probe_status"]}
