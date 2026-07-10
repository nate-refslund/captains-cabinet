"""B2.4 Vercel probe — FIXTURED only (zero live Vercel/git). Fleet-replica tests."""
from __future__ import annotations

from framework.acting import loop
from framework.probes import correlation as c
from framework.probes import lib
from framework.probes import probe_vercel as pv

_NOW = 2_000_000_000_000                       # a fixed "now" in epoch ms
_STABLE = _NOW - pv.STABILITY_MS - 60_000      # ready 61 min ago → past the window
_IN_WINDOW = _NOW - 60_000                      # ready 1 min ago → inside the window


# --- pure timing + join helpers ---------------------------------------------

def test_alias_stable_arithmetic():
    assert pv._alias_stable(_STABLE, _NOW)                    # 61 min → stable
    assert not pv._alias_stable(_IN_WINDOW, _NOW)             # 1 min → still stabilizing
    assert not pv._alias_stable(_NOW - pv.STABILITY_MS + 1, _NOW)   # just under → not yet
    assert not pv._alias_stable(None, _NOW)                   # no signal ≠ stable
    assert not pv._alias_stable(_NOW, None)
    assert not pv._alias_stable(True, _NOW)                   # bool is not a timestamp


def test_cid_for_deployment_meta_first_then_trailer():
    cid = c.mint()
    # 1. primary: the --meta cabinetProposalId stamp on the deployment
    assert pv.cid_for_deployment({"meta": {c.VERCEL_META_KEY: cid}}) == cid
    # 2. fallback: the commit-message trailer carried in meta.githubCommitMessage
    dep_msg = {"meta": {"githubCommitMessage": f"fix thing\n\n{c.git_trailer(cid)}"}}
    assert pv.cid_for_deployment(dep_msg) == cid
    # 3. fallback: resolve the commit sha → message → trailer
    dep_sha = {"meta": {"githubCommitSha": "abc1234"}}
    assert pv.cid_for_deployment(
        dep_sha, resolve_sha=lambda s: f"msg\n\n{c.git_trailer(cid)}") == cid
    # 4. nothing joinable, and a malformed (non-cid) meta value does NOT join
    assert pv.cid_for_deployment({"meta": {}}) is None
    assert pv.cid_for_deployment({"meta": {c.VERCEL_META_KEY: "not-a-cid"}}) is None


def test_classify_truth_table():
    ready = {"readyState": "READY"}
    assert pv.classify(ready, rolled_back=False, alias_stable=True)[:2] == ("ok", "deploy_ready")
    assert pv.classify(ready, rolled_back=False, alias_stable=False)[:2] == ("unknown", "stabilizing")
    # rollback supersedes even a stable READY
    assert pv.classify(ready, rolled_back=True, alias_stable=True)[:2] == ("failed", "rolled_back")
    assert pv.classify({"readyState": "ERROR"}, rolled_back=False, alias_stable=False)[:2] \
        == ("failed", "deploy_error")
    assert pv.classify({"state": "BUILDING"}, rolled_back=False, alias_stable=False)[:2] \
        == ("unknown", "held")


# --- fixtured client ---------------------------------------------------------

class FakeVercel:
    def __init__(self, deps, rolled=frozenset(), commits=("sha1",), now_ms=_NOW,
                 commit_msgs=None):
        self._deps, self._rolled = deps, set(rolled)
        self._commits, self._now = list(commits), now_ms
        self._commit_msgs = commit_msgs or {}

    def deployments(self, product, limit=50):
        return self._deps

    def rolled_back_uids(self, product, since_days=14):
        return self._rolled

    def commit_message(self, sha):
        return self._commit_msgs.get(sha)

    def local_commits_since(self, window="15 minutes ago"):
        return self._commits

    def now_ms(self):
        return self._now


def _decided(cid, subject="vercel-deploy"):
    p = loop.proposal_event(actor={"kind": "officer", "id": "bakery-ceo"},
                            lane="deploy", subject=subject,
                            ts="2026-07-03T01:00:00Z", refs=[c.ref_for(cid)])
    p["proposal"]["decision"] = "approved"
    p["proposal"]["decided_at"] = "2026-07-03T01:00:00Z"
    return p


def _record(sink, **kw):
    sink.append(kw)
    return {"emitted": True, "status": kw["status"], "probe_status": kw["probe_status"]}


def test_run_probe_emits_deploy_ready_ok():
    cid = c.mint()
    deps = [{"uid": "dpl_1", "readyState": "READY",
             "meta": {c.VERCEL_META_KEY: cid}, "ready": _STABLE}]
    emitted = []
    r = pv.run_probe(product="politiske-annoncer", client=FakeVercel(deps),
                     rows=[_decided(cid)],
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "pinged")
    assert r["fresh"] is True
    assert len(r["emitted"]) == 1 and r["emitted"][0]["status"] == "ok"
    assert emitted[0]["status"] == "ok" and emitted[0]["probe_status"] == "deploy_ready"
    assert emitted[0]["source"] == "vercel" and emitted[0]["confidence"] == "high"


def test_run_probe_rollback_emits_failed():
    cid = c.mint()
    deps = [{"uid": "dpl_7", "readyState": "READY",
             "meta": {c.VERCEL_META_KEY: cid}, "ready": _STABLE}]
    emitted = []
    r = pv.run_probe(product="politiske-annoncer",
                     client=FakeVercel(deps, rolled={"dpl_7"}),
                     rows=[_decided(cid)],
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "failed"
    assert emitted[0]["probe_status"] == "rolled_back"


def test_run_probe_in_window_ready_is_unknown_no_evidence():
    cid = c.mint()
    deps = [{"uid": "dpl_9", "readyState": "READY",
             "meta": {c.VERCEL_META_KEY: cid}, "ready": _IN_WINDOW}]
    emitted = []
    r = pv.run_probe(product="p", client=FakeVercel(deps), rows=[_decided(cid)],
                     emit=lambda **kw: _record(emitted, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "unknown"
    assert emitted[0]["probe_status"] == "stabilizing"
    assert emitted[0]["evidence"] is None          # unknown MUST carry no evidence


def test_run_probe_freshness_silent_source_pages_no_emit():
    # git shows pushes but Vercel returned an EMPTY list → not fresh: hc fail, no emit
    pinged = []
    r = pv.run_probe(product="p", client=FakeVercel([], commits=["s1", "s2"]),
                     rows=[], emit=lambda **kw: pinged.append(("emit",)),
                     hc=lambda slug, fail=False: pinged.append(("hc", fail)))
    assert r["fresh"] is False
    assert ("hc", True) in pinged and ("emit",) not in pinged


def test_run_probe_no_cid_deploy_skipped():
    # a deploy with no stamped meta and no resolvable trailer → skipped, not emitted
    deps = [{"uid": "dpl_ext", "readyState": "READY", "meta": {}, "ready": _STABLE}]
    r = pv.run_probe(product="p", client=FakeVercel(deps), rows=[],
                     emit=lib.emit_outcome, hc=lambda *a, **k: "")
    assert r["emitted"] == [] and r["skipped"][0]["reason"] == "no-cid"


def test_run_probe_unattributable_cid_skipped():
    cid = c.mint()   # valid stamped cid, but NO matching decided proposal in rows
    deps = [{"uid": "dpl_x", "readyState": "READY",
             "meta": {c.VERCEL_META_KEY: cid}, "ready": _STABLE}]
    r = pv.run_probe(product="p", client=FakeVercel(deps), rows=[],   # empty ledger
                     emit=lib.emit_outcome, hc=lambda *a, **k: "")
    assert r["emitted"] == [] and r["skipped"][0]["reason"] == "unattributable-cid"
