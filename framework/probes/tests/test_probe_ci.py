"""B2.6 CI probe — FIXTURED only (zero live gh/git). Mirrors the B2.3 tests."""
from __future__ import annotations

from framework.acting import loop
from framework.fidelity.consequence import validate_consequence
from framework.probes import correlation as c
from framework.probes import lib
from framework.probes import probe_ci as pc


# --- pure classify -----------------------------------------------------------

def test_classify_truth_table():
    green = {"status": "completed", "conclusion": "SUCCESS"}
    assert pc.classify(green)[:2] == ("ok", "ci_green")
    for red in ("FAILURE", "TIMED_OUT", "CANCELLED"):
        run = {"status": "completed", "conclusion": red}
        assert pc.classify(run)[:2] == ("failed", "ci_red")
    # in-flight → unknown (queued / in_progress, null conclusion)
    assert pc.classify({"status": "in_progress", "conclusion": None})[:2] == ("unknown", "ci_running")
    assert pc.classify({"status": "queued", "conclusion": None})[:2] == ("unknown", "ci_running")
    # completed but non-terminal conclusion (neutral/skipped) → NOT a loss → unknown
    assert pc.classify({"status": "completed", "conclusion": "NEUTRAL"})[:2] == ("unknown", "ci_running")
    # ok/failed carry evidence; unknown does not
    assert pc.classify(green)[2]
    assert pc.classify({"status": "completed", "conclusion": "FAILURE"})[2]


# --- B2.10 pure test-file detection -----------------------------------------

def test_is_test_file_patterns():
    for p in ("tests/test_probe_ci.py", "framework/probes/tests/x.py",
              "pkg/foo_test.go", "src/foo.test.ts", "src/foo.spec.tsx",
              "app/__tests__/bar.js", "e2e/spec/login.spec.mjs"):
        assert pc._is_test_file(p), p
    # a mere "test" substring must NOT count as a test file
    for p in ("src/app/feature.ts", "README.md", "app/testimonials.ts",
              "src/latest.py", "lib/contest.js", ""):
        assert not pc._is_test_file(p), p


def test_touches_only_tests():
    assert pc._touches_only_tests(["tests/test_a.py", "b.spec.ts"]) is True
    assert pc._touches_only_tests(["tests/test_a.py", "src/app.ts"]) is False  # mixed
    assert pc._touches_only_tests([]) is False        # undeterminable ≠ test-only
    assert pc._touches_only_tests(["src/app.ts"]) is False


# --- fixtured client + helpers ----------------------------------------------

class FakeCi:
    def __init__(self, runs, msgs, files=None, commits=("sha1",)):
        self._runs, self._msgs = runs, dict(msgs)
        self._files = dict(files or {})
        self._commits = list(commits)

    def runs(self, repo, workflow):
        return self._runs

    def commit_message(self, sha):
        return self._msgs.get(sha, "")

    def changed_files(self, repo, sha):
        return self._files.get(sha, [])

    def local_commits_since(self, window="1 hour ago"):
        return self._commits


def _decided(cid, subject="ci-thread"):
    p = loop.proposal_event(actor={"kind": "officer", "id": "bakery-ceo"},
                            lane="feature-impl", subject=subject,
                            ts="2026-07-03T01:00:00Z", refs=[c.ref_for(cid)])
    p["proposal"]["decision"] = "approved"
    p["proposal"]["decided_at"] = "2026-07-03T01:00:00Z"
    return p


def _record(sink, **kw):
    sink.append(kw)
    return {"emitted": True, "status": kw["status"], "probe_status": kw["probe_status"]}


# --- run_probe: emit truth table --------------------------------------------

def test_run_probe_emits_ci_green_ok():
    cid = c.mint()
    body = f"feat: ship it\n\n{c.git_trailer(cid)}"
    runs = [{"databaseId": 501, "status": "completed", "conclusion": "SUCCESS",
             "headSha": "abc1234"}]
    calls = []
    r = pc.run_probe(repo="o/r", workflow="ci.yml",
                     client=FakeCi(runs, {"abc1234": body}, files={"abc1234": ["src/app/feature.ts"]}),
                     rows=[_decided(cid)],
                     emit=lambda **kw: _record(calls, **kw), hc=lambda *a, **k: "pinged")
    assert r["fresh"] is True
    e = r["emitted"][0]
    assert e["status"] == "ok" and e["probe_status"] == "ci_green"
    assert e["graduation_credit"] is True
    assert calls[0]["source"] == "ci" and calls[0]["confidence"] == "high"
    assert calls[0]["evidence"]                 # ok carries evidence
    assert calls[0]["extra_refs"] is None       # feature diff → keeps credit


def test_run_probe_emits_ci_red_failed():
    cid = c.mint()
    runs = [{"databaseId": 7, "status": "completed", "conclusion": "FAILURE",
             "headSha": "deadbee"}]
    calls = []
    r = pc.run_probe(repo="o/r", workflow="ci.yml",
                     client=FakeCi(runs, {"deadbee": c.git_trailer(cid)}),
                     rows=[_decided(cid)],
                     emit=lambda **kw: _record(calls, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "failed"
    assert r["emitted"][0]["probe_status"] == "ci_red"
    assert calls[0]["evidence"]                 # failed carries evidence


def test_run_probe_pending_emits_unknown_no_evidence():
    cid = c.mint()
    runs = [{"databaseId": 9, "status": "in_progress", "conclusion": None,
             "headSha": "beef111"}]
    calls = []
    r = pc.run_probe(repo="o/r", workflow="ci.yml",
                     client=FakeCi(runs, {"beef111": c.git_trailer(cid)}),
                     rows=[_decided(cid)],
                     emit=lambda **kw: _record(calls, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["status"] == "unknown"
    assert r["emitted"][0]["probe_status"] == "ci_running"
    assert calls[0]["evidence"] is None         # unknown → no evidence


# --- B2.10: test-only diff stamps graduation-credit:false -------------------

def test_run_probe_test_only_diff_stamps_no_graduation_credit():
    cid = c.mint()
    body = f"test: add coverage\n\n{c.git_trailer(cid)}"
    runs = [{"databaseId": 100, "status": "completed", "conclusion": "SUCCESS",
             "headSha": "abc1234"}]
    files = {"abc1234": ["tests/test_feature.py", "src/__tests__/x.spec.ts"]}
    calls = []
    r = pc.run_probe(repo="o/r", workflow="ci.yml",
                     client=FakeCi(runs, {"abc1234": body}, files=files),
                     rows=[_decided(cid)],
                     emit=lambda **kw: _record(calls, **kw), hc=lambda *a, **k: "")
    e = r["emitted"][0]
    assert e["status"] == "ok" and e["probe_status"] == "ci_green"
    assert e["graduation_credit"] is False           # green on tests-only ≠ feature evidence
    assert calls[0]["extra_refs"] == [pc.GRAD_CREDIT_FALSE_REF]


def test_run_probe_mixed_diff_keeps_graduation_credit():
    cid = c.mint()
    body = f"feat: real feature + its tests\n\n{c.git_trailer(cid)}"
    runs = [{"databaseId": 101, "status": "completed", "conclusion": "SUCCESS",
             "headSha": "fee1234"}]
    files = {"fee1234": ["src/app/feature.ts", "tests/test_feature.py"]}   # mixed
    calls = []
    r = pc.run_probe(repo="o/r", workflow="ci.yml",
                     client=FakeCi(runs, {"fee1234": body}, files=files),
                     rows=[_decided(cid)],
                     emit=lambda **kw: _record(calls, **kw), hc=lambda *a, **k: "")
    assert r["emitted"][0]["graduation_credit"] is True
    assert calls[0]["extra_refs"] is None


def test_graduation_ref_lands_in_refs_and_stays_schema_valid():
    """End-to-end through the REAL lib.emit_outcome (fake inner writer): the
    B2.10 ref lands in refs, the join survives, and the event is schema-legal."""
    cid = c.mint()
    captured = []
    r = lib.emit_outcome(cid=cid, status="ok", probe_status="ci_green", source="ci",
                         confidence="high", evidence="CI run completed with conclusion=SUCCESS",
                         extra_refs=[pc.GRAD_CREDIT_FALSE_REF],
                         rows=[_decided(cid)], emit=lambda **ev: captured.append(ev))
    assert r["emitted"] is True
    ev = captured[0]
    validate_consequence(ev)                                  # schema-legal WITH the ref
    assert pc.GRAD_CREDIT_FALSE_REF in ev["refs"]
    assert "probe-status:ci_green" in ev["refs"] and "probe:ci" in ev["refs"]
    assert c.cid_from_refs(ev["refs"]) == cid                 # join preserved
    assert ev["outcome"] == {"status": "ok",
                             "evidence": "CI run completed with conclusion=SUCCESS"}


# --- inherited guards: freshness (silent source) + RT#3 + no-cid ------------

def test_run_probe_freshness_silent_source_pages_no_emit():
    # runs empty but local commits landed → not fresh: hc fail, emit nothing.
    pinged = []
    r = pc.run_probe(repo="o/r", workflow="ci.yml",
                     client=FakeCi([], {}, commits=["s1", "s2"]),
                     rows=[], emit=lambda **kw: pinged.append(("emit",)),
                     hc=lambda slug, fail=False: pinged.append(("hc", fail)))
    assert r["fresh"] is False
    assert ("hc", True) in pinged and ("emit",) not in pinged


def test_run_probe_unattributable_cid_skipped():
    cid = c.mint()  # valid trailer, but NO matching decided proposal in rows
    runs = [{"databaseId": 3, "status": "completed", "conclusion": "SUCCESS",
             "headSha": "aaa111"}]
    r = pc.run_probe(repo="o/r", workflow="ci.yml",
                     client=FakeCi(runs, {"aaa111": c.git_trailer(cid)}),
                     rows=[],                       # empty ledger → RT#3
                     emit=lib.emit_outcome, hc=lambda *a, **k: "")
    assert r["emitted"] == []
    assert r["skipped"][0]["reason"] == "unattributable-cid"


def test_run_probe_no_trailer_skipped_no_cid():
    runs = [{"databaseId": 4, "status": "completed", "conclusion": "SUCCESS",
             "headSha": "nocid00"}]
    calls = []
    r = pc.run_probe(repo="o/r", workflow="ci.yml",
                     client=FakeCi(runs, {"nocid00": "no trailer in this message"}),
                     rows=[_decided(c.mint())],
                     emit=lambda **kw: _record(calls, **kw), hc=lambda *a, **k: "")
    assert r["emitted"] == []
    assert r["skipped"][0]["reason"] == "no-cid"
    assert calls == []                              # never reached emit
