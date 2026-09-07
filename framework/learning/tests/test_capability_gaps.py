"""Tests for the self-extension capability-gap loop.

The non-negotiable property under test: the install gate FAILS CLOSED. No
approval event → no install, ever, including on bad input / ceiling touches.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.learning.capability_gaps import (  # noqa: E402
    classify, infer_touches, load_autonomy, AutonomyPolicy, HARD_CEILING_TOUCHES,
    can_auto_apply, can_install, record_gap, propose_gap, approve_gap,
    decline_gap, resolve_gap, project_gaps, gap_id_for, gap_id_for_key,
    route_open_gaps, STRUCTURAL_KINDS, VALID_KINDS, _jaccard, _tokens,
    STATUS_OPEN, STATUS_PENDING, STATUS_APPROVED, STATUS_DECLINED, STATUS_RESOLVED,
)


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")  # no Store in tests
    monkeypatch.setenv("CABINET_PRODUCT_SLUG", "testprod")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path / "events"


# ---------------------------------------------------------------------------
# Classification — safe default toward propose
# ---------------------------------------------------------------------------

class TestClassify:
    def test_procedure(self):
        assert classify("how to refine a task before implementing") == "procedure"
        assert classify("the standard workflow for shipping a PR") == "procedure"

    def test_tool(self):
        assert classify("query the Stripe API for MRR") in ("tool", "integration")
        assert classify("fetch data from an external endpoint") in ("tool", "integration")

    def test_integration(self):
        assert classify("connect to Salesforce with oauth credentials") == "integration"

    def test_ambiguous_defaults_to_propose_not_auto(self):
        # No clear signal → must NOT be 'procedure' (which would auto-skill).
        assert classify("do the thing with the stuff") != "procedure"
        assert classify("") != "procedure"


class TestInferTouches:
    def test_secrets(self):
        assert "secrets" in infer_touches("read the API key from the vault")

    def test_spending(self):
        assert "spending" in infer_touches("charge the customer's card")

    def test_external_comms(self):
        assert "external_comms" in infer_touches("send email to the customer")

    def test_declared_union(self):
        t = infer_touches("nothing special", declared=["production"])
        assert "production" in t

    def test_clean_need_no_touches(self):
        assert infer_touches("summarize the meeting notes") == set()


# ---------------------------------------------------------------------------
# Autonomy policy — missing/broken file yields SAFE defaults
# ---------------------------------------------------------------------------

class TestAutonomyPolicy:
    def test_defaults_are_conservative(self):
        p = AutonomyPolicy()
        assert p.defaults["procedure"] == "auto"
        assert p.defaults["tool"] == "propose"
        assert p.defaults["integration"] == "propose"

    def test_missing_file_safe_defaults(self, tmp_path):
        p = load_autonomy(cabinet_root=tmp_path)  # no autonomy.yml present
        assert p.defaults["tool"] == "propose"
        assert HARD_CEILING_TOUCHES <= p.ceiling

    def test_file_cannot_narrow_hard_ceiling(self, tmp_path):
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        # Even a malicious file claiming an empty ceiling can't remove the floor.
        (cfg / "autonomy.yml").write_text(
            "defaults:\n  tool: auto\nhard_ceiling:\n  always_propose_if_touches: []\n"
        )
        p = load_autonomy(cabinet_root=tmp_path)
        assert HARD_CEILING_TOUCHES <= p.ceiling  # floor still present

    def test_file_can_widen_ceiling(self, tmp_path):
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "autonomy.yml").write_text(
            "hard_ceiling:\n  always_propose_if_touches:\n    - custom_risk\n"
        )
        p = load_autonomy(cabinet_root=tmp_path)
        assert "custom_risk" in p.ceiling
        assert HARD_CEILING_TOUCHES <= p.ceiling

    def test_ambiguous_defaults_to_auto_is_refused(self, tmp_path):
        # The knob is consumed, but 'auto' cannot invert the human-in-loop
        # invariant — the file value is refused, the safe default stands.
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "autonomy.yml").write_text(
            "classifier:\n  ambiguous_defaults_to: auto\n")
        p = load_autonomy(cabinet_root=tmp_path)
        assert p.ambiguous_defaults_to == "propose"
        assert p.ambiguous_kind == "tool"

    def test_ambiguous_kind_wired_into_classify(self, tmp_path):
        # The policy knob actually reaches classify(): an ambiguous need
        # resolves to the propose kind, never 'procedure'.
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "autonomy.yml").write_text(
            "classifier:\n  ambiguous_defaults_to: propose\n")
        p = load_autonomy(cabinet_root=tmp_path)
        assert classify("do the thing with the stuff", ambiguous_default=p.ambiguous_kind) == "tool"

    def test_classify_refuses_procedure_as_ambiguous_default(self):
        # Even a caller passing 'procedure' cannot make ambiguity auto-skill.
        assert classify("do the thing with the stuff",
                        ambiguous_default="procedure") != "procedure"


# ---------------------------------------------------------------------------
# can_auto_apply — only 'auto' kind with no ceiling touch
# ---------------------------------------------------------------------------

class TestCanAutoApply:
    def test_procedure_no_touch_auto(self, tmp_path):
        p = load_autonomy(cabinet_root=tmp_path)
        assert can_auto_apply("procedure", set(), p) is True

    def test_tool_is_propose_not_auto(self, tmp_path):
        p = load_autonomy(cabinet_root=tmp_path)
        assert can_auto_apply("tool", set(), p) is False

    def test_procedure_touching_ceiling_blocked(self, tmp_path):
        p = load_autonomy(cabinet_root=tmp_path)
        # Even a procedure can't auto if it somehow touches secrets.
        assert can_auto_apply("procedure", {"secrets"}, p) is False

    def test_unknown_kind_blocked(self, tmp_path):
        p = load_autonomy(cabinet_root=tmp_path)
        assert can_auto_apply("wat", set(), p) is False

    def test_bad_input_fails_closed(self):
        assert can_auto_apply(None, None, None) is False  # type: ignore


# ---------------------------------------------------------------------------
# can_install — THE GATE. Fails closed.
# ---------------------------------------------------------------------------

class TestInstallGateFailsClosed:
    def test_no_approval_no_install(self):
        record_gap("query the Stripe API", recorded_by="cto")
        gid = gap_id_for("query the Stripe API")
        # No approval event → must be False.
        assert can_install(gid, touches=set()) is False

    def test_approval_unlocks_install(self):
        record_gap("pull GitHub stars count", recorded_by="cto")
        gid = gap_id_for("pull GitHub stars count")
        approve_gap(gid)
        assert can_install(gid, touches=set()) is True

    def test_decline_after_approve_locks_again(self):
        record_gap("read the analytics dashboard", recorded_by="cro")
        gid = gap_id_for("read the analytics dashboard")
        approve_gap(gid)
        decline_gap(gid, reason="changed my mind")
        assert can_install(gid, touches=set()) is False

    def test_reapprove_after_decline_unlocks(self):
        record_gap("scrape competitor pricing", recorded_by="cro")
        gid = gap_id_for("scrape competitor pricing")
        decline_gap(gid)
        approve_gap(gid)
        assert can_install(gid, touches=set()) is True

    def test_ceiling_touch_blocks_even_with_approval(self):
        record_gap("send invoices to customers", recorded_by="coo")
        gid = gap_id_for("send invoices to customers")
        approve_gap(gid)
        # Touches external_comms + spending → blocked even though approved.
        assert can_install(gid, touches={"external_comms"}) is False
        assert can_install(gid, touches={"spending"}) is False

    def test_empty_gap_id_fails_closed(self):
        assert can_install("", touches=set()) is False

    def test_unknown_gap_fails_closed(self):
        assert can_install("gap-doesnotexist", touches=set()) is False


# ---------------------------------------------------------------------------
# Record + dedup + projection
# ---------------------------------------------------------------------------

class TestRecordAndProject:
    def test_record_creates_open_gap(self):
        g = record_gap("connect to Notion via API", recorded_by="cos")
        assert g["status"] == STATUS_OPEN
        gaps = project_gaps(product_slug="testprod")
        assert any(x["gap_id"] == g["gap_id"] for x in gaps)

    def test_dedup_increments_hit_count(self):
        # Same wall, slightly different phrasing (the realistic recurrence) —
        # Jaccard >= 0.6 so they collapse to one gap with hit_count incremented.
        record_gap("pull MRR from the Stripe billing API", recorded_by="cro")
        record_gap("pull MRR from the Stripe billing API each month", recorded_by="cpo")
        gaps = project_gaps(product_slug="testprod")
        stripe = [g for g in gaps if "mrr" in g["need"].lower()]
        assert len(stripe) == 1
        assert stripe[0]["hit_count"] >= 2

    def test_dedup_does_not_false_merge_distinct_apis(self):
        # Guards the 0.6 threshold: "query the X API" for different X must NOT
        # merge (intersection {query,api} / union = 0.5 < 0.6).
        record_gap("query the Stripe API", recorded_by="cto")
        record_gap("query the GitHub API", recorded_by="cto")
        gaps = project_gaps(product_slug="testprod")
        assert len(gaps) == 2

    def test_distinct_gaps_not_merged(self):
        record_gap("read rows from the Stripe billing API", recorded_by="cto")
        record_gap("write a retro after each sprint", recorded_by="cos")
        gaps = project_gaps(product_slug="testprod")
        assert len(gaps) == 2

    def test_full_lifecycle_propose_approve_resolve(self):
        g = record_gap("integrate with the Linear GraphQL API", recorded_by="cpo")
        gid = g["gap_id"]
        propose_gap(gid, summary="Add a Linear MCP", approach="npx linear-mcp")
        assert _status(gid) == STATUS_PENDING
        approve_gap(gid)
        assert _status(gid) == STATUS_APPROVED
        resolve_gap(gid, resolution="mcp: linear")
        g2 = _get(gid)
        assert g2["status"] == STATUS_RESOLVED
        assert g2["resolution"] == "mcp: linear"

    def test_decline_path(self):
        g = record_gap("build a custom CRM scraper", recorded_by="cro")
        gid = g["gap_id"]
        propose_gap(gid, summary="scraper MCP", approach="...")
        decline_gap(gid, reason="use the official API instead")
        g2 = _get(gid)
        assert g2["status"] == STATUS_DECLINED
        assert g2["decline_reason"] == "use the official API instead"

    def test_resolved_gap_does_not_dedup_block_new(self):
        g = record_gap("one-off data export", recorded_by="cto")
        resolve_gap(g["gap_id"], resolution="skill: data-export")
        # A new, similar need after resolution creates a fresh gap (resolved
        # ones are excluded from dedup).
        g2 = record_gap("one-off data export again please", recorded_by="cto")
        assert g2["status"] == STATUS_OPEN


class TestRouteOpenGaps:
    def test_procedure_routed_to_auto_skilling(self, tmp_path):
        from framework.learning.capability_gaps import route_open_gaps, load_autonomy
        record_gap("the standard checklist for shipping a PR", kind="procedure", recorded_by="cto")
        out = route_open_gaps(product_slug="testprod", policy=load_autonomy(cabinet_root=tmp_path))
        assert len(out["auto_skilling"]) == 1
        assert out["proposed"] == []

    def test_tool_routed_to_proposal(self, tmp_path):
        from framework.learning.capability_gaps import route_open_gaps, load_autonomy
        record_gap("query the Stripe billing API for MRR", kind="integration", recorded_by="cto")
        out = route_open_gaps(product_slug="testprod", policy=load_autonomy(cabinet_root=tmp_path))
        assert len(out["proposed"]) == 1
        # routed gap is now pending_captain
        assert _get(out["proposed"][0])["status"] == STATUS_PENDING

    def test_ceiling_procedure_is_proposed_not_auto(self, tmp_path):
        from framework.learning.capability_gaps import route_open_gaps, load_autonomy
        # A 'procedure' that touches secrets must NOT auto-skill — it proposes.
        record_gap("rotate the API keys each week", kind="procedure",
                   recorded_by="coo", touches=["secrets"])
        out = route_open_gaps(product_slug="testprod", policy=load_autonomy(cabinet_root=tmp_path))
        assert out["auto_skilling"] == []
        assert len(out["proposed"]) == 1

    def test_dry_run_emits_nothing(self, tmp_path):
        from framework.learning.capability_gaps import route_open_gaps, load_autonomy
        record_gap("connect to the HubSpot API", kind="integration", recorded_by="cro")
        before = [g["status"] for g in project_gaps(product_slug="testprod")]
        route_open_gaps(product_slug="testprod", policy=load_autonomy(cabinet_root=tmp_path), dry_run=True)
        after = [g["status"] for g in project_gaps(product_slug="testprod")]
        assert before == after  # no status change in dry-run


def _status(gid: str) -> str:
    return _get(gid)["status"]


def _get(gid: str) -> dict:
    for g in project_gaps(product_slug="testprod"):
        if g["gap_id"] == gid:
            return g
    raise AssertionError(f"gap {gid} not found")


# `_ROOT` above is <repo>/framework (it is a sys.path seed). The repo root is
# what a child process needs on its path, and what a source path resolves from.
_REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Structural kinds — recorded, rendered, and otherwise LEFT ALONE
# (contract §3 + A3.1; "surface-only: route_open_gaps never proposes or
# notifies for them")
# ---------------------------------------------------------------------------

class TestStructuralKinds:
    def test_structural_kinds_surface_only(self, tmp_path):
        """A structural kind survives recording AND is never routed anywhere.

        Pre-change this fails at the first assert: "skill" is not a valid kind,
        so record_gap classifies the need instead — landing it in a propose
        kind, which route_open_gaps then turns into a Captain ask.
        """
        notified = []
        for kind, key in (("skill", "holder:outcome-a:task-001"),
                          ("authority", "authority:outcome-a:task-002"),
                          ("information", "information:outcome-a:task-003")):
            g = record_gap(
                "no holder on the roster for %s of outcome-a" % key,
                kind=kind, recorded_by="supervisor", dedup_key=key)
            assert g["kind"] == kind, "record_gap dropped the structural kind"

        out = route_open_gaps(product_slug="testprod",
                              policy=load_autonomy(cabinet_root=tmp_path),
                              notify_fn=lambda g, summary: notified.append(g))

        assert out["proposed"] == [], "a structural gap reached the Captain"
        assert out["auto_skilling"] == [], "a structural gap entered the auto lane"
        assert out["skipped"] == [], "a structural gap read as an unroutable error"
        assert len(out["surfaced"]) == 3
        assert notified == [], "a structural gap fired a notification"
        # ...and routing left every one of them exactly where it was.
        assert [g["status"] for g in project_gaps(product_slug="testprod")] == \
            [STATUS_OPEN] * 3

    def test_structural_kind_never_auto_applies_even_when_the_file_says_auto(
            self, tmp_path):
        """The auto veto is structural, not configured.

        Red arm is the naive widening (VALID_KINDS extended, no veto): the
        policy file below then grants an auto lane to a kind that has none.
        """
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "autonomy.yml").write_text(
            "defaults:\n  skill: auto\n  authority: auto\n  information: auto\n")
        policy = load_autonomy(cabinet_root=tmp_path)
        for kind in sorted(STRUCTURAL_KINDS):
            assert can_auto_apply(kind, set(), policy) is False

    def test_classify_never_resolves_an_ambiguity_to_a_structural_kind(self):
        """An ambiguous need must reach the Captain, not go quiet."""
        for kind in sorted(STRUCTURAL_KINDS):
            assert classify("", "", ambiguous_default=kind) == "tool"

    def test_module_parses_under_python_39_grammar(self):
        """A0.3: the pull path can be imported by the box's own python3 (3.9)."""
        rel = "framework/learning/capability_gaps.py"
        source = (_REPO_ROOT / rel).read_text()
        ast.parse(source, filename=rel, feature_version=(3, 9))


# ---------------------------------------------------------------------------
# Keyed dedupe — identity, and it bypasses the similarity scan both ways
# (A3.1)
# ---------------------------------------------------------------------------

def _events(event_type: str) -> list:
    from framework.events.emitter import replay
    return replay(event_types=[event_type])


class TestKeyedDedup:
    def test_keyed_reobservation_records_once_and_never_merges(self):
        """Two subjects, three passes each: 2 recorded, 0 merged.

        The pre-change path emits one `capability_gap_merged` per pass, so a
        supervisor scanning every 90 s writes a merge storm for one standing
        condition.
        """
        for _ in range(3):
            for task in ("task-001", "task-002"):
                record_gap("no holder on the roster for %s of outcome-a" % task,
                           kind="skill", recorded_by="supervisor",
                           dedup_key="holder:outcome-a:%s" % task)

        assert len(_events("capability_gap_recorded")) == 2
        assert _events("capability_gap_merged") == []
        gaps = project_gaps(product_slug="testprod")
        assert len(gaps) == 2
        assert {g["gap_id"] for g in gaps} == {
            gap_id_for_key("holder:outcome-a:task-001"),
            gap_id_for_key("holder:outcome-a:task-002"),
        }

    def test_keyed_gap_is_never_a_merge_target(self):
        """The scan cannot swallow a keyed gap — proven on needs that WOULD merge."""
        a = "no holder on the roster for task-001 of outcome-a"
        b = "no holder on the roster for task-002 of outcome-a"
        # The premise of the test, asserted rather than assumed: without the
        # key these two are over the 0.6 similarity threshold.
        assert _jaccard(_tokens(a), _tokens(b)) >= 0.6

        record_gap(a, kind="skill", recorded_by="supervisor",
                   dedup_key="holder:outcome-a:task-001")
        record_gap(b, recorded_by="officer")  # unkeyed, near-identical

        assert _events("capability_gap_merged") == []
        assert len(project_gaps(product_slug="testprod")) == 2

    def test_keyed_record_is_not_merged_into_an_unkeyed_lookalike(self):
        """The other direction: a keyed record never runs the scan at all."""
        record_gap("no holder on the roster for task-001 of outcome-a",
                   recorded_by="officer")  # unkeyed first
        g = record_gap("no holder on the roster for task-002 of outcome-a",
                       kind="skill", recorded_by="supervisor",
                       dedup_key="holder:outcome-a:task-002")

        assert g["gap_id"] == gap_id_for_key("holder:outcome-a:task-002")
        assert _events("capability_gap_merged") == []
        assert len(project_gaps(product_slug="testprod")) == 2

    def test_a_closed_keyed_gap_reopens_on_re_observation(self):
        """Degenerate end: silence is only for a LIVE gap, never a closed one."""
        key = "holder:outcome-a:task-001"
        need = "no holder on the roster for task-001 of outcome-a"
        g = record_gap(need, kind="skill", recorded_by="supervisor", dedup_key=key)
        resolve_gap(g["gap_id"], resolution="role joined the roster")
        assert _get(g["gap_id"])["status"] == STATUS_RESOLVED

        again = record_gap(need, kind="skill", recorded_by="supervisor",
                           dedup_key=key)
        assert again["gap_id"] == g["gap_id"]
        assert _get(g["gap_id"])["status"] == STATUS_OPEN
        assert len(_events("capability_gap_recorded")) == 2

    def test_empty_key_is_no_key(self):
        """Degenerate end: a blank key falls back to the similarity path."""
        g = record_gap("read the quarterly numbers from the finance system",
                       recorded_by="officer", dedup_key="   ")
        assert g["gap_id"] == gap_id_for(
            "read the quarterly numbers from the finance system")


# ---------------------------------------------------------------------------
# The concurrency arm (A3.1): 2 tasks x 8 concurrent observers => 2 recorded,
# 0 merged. Subprocesses, so the lock is exercised across processes — the way
# the officer hook runs it (a fresh python per tick).
# ---------------------------------------------------------------------------

_OBSERVER = """
import os, sys, time
sys.path.insert(0, os.environ["REPO"])
from framework.learning.capability_gaps import record_gap

deadline = float(os.environ["DEADLINE"])
delay = deadline - time.time()
if delay > 0:
    time.sleep(delay)
record_gap(os.environ["NEED"], kind="skill", recorded_by="observer",
           dedup_key=os.environ["KEY"])
"""


class TestKeyedDedupUnderConcurrency:
    def test_two_subjects_eight_observers_each_record_once(self, tmp_path):
        worker = tmp_path / "observer.py"
        worker.write_text(_OBSERVER)

        env = os.environ.copy()
        # A0.4: pin the ledger explicitly — unset, every child gets its own.
        env["CABINET_EVENT_LOG_DIR"] = os.environ["CABINET_EVENT_LOG_DIR"]
        env["CABINET_FRAMEWORK_STORE_MIRROR"] = "0"
        env["CABINET_PRODUCT_SLUG"] = "testprod"
        env["REPO"] = str(_REPO_ROOT)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env.pop("PYTEST_CURRENT_TEST", None)
        env.pop("DATABASE_URL", None)
        env["DEADLINE"] = str(time.time() + 3.0)

        procs = []
        for task in ("task-001", "task-002"):
            for _ in range(8):
                child = dict(env)
                child["KEY"] = "holder:outcome-a:%s" % task
                child["NEED"] = "no holder on the roster for %s of outcome-a" % task
                procs.append(subprocess.Popen(
                    [sys.executable, str(worker)], env=child,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE))

        failures = []
        for pr in procs:
            out, err = pr.communicate(timeout=180)
            if pr.returncode != 0:
                failures.append(err.decode()[-400:])
        assert failures == [], failures[:2]

        recorded = _events("capability_gap_recorded")
        assert len(recorded) == 2, [e["payload"]["gap_id"] for e in recorded]
        assert _events("capability_gap_merged") == []
        assert len(project_gaps(product_slug="testprod")) == 2
