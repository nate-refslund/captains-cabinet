"""Tests for the self-extension capability-gap loop.

The non-negotiable property under test: the install gate FAILS CLOSED. No
approval event → no install, ever, including on bad input / ceiling touches.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.learning.capability_gaps import (  # noqa: E402
    classify, infer_touches, load_autonomy, AutonomyPolicy, HARD_CEILING_TOUCHES,
    can_auto_apply, can_install, record_gap, propose_gap, approve_gap,
    decline_gap, resolve_gap, project_gaps, gap_id_for,
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
