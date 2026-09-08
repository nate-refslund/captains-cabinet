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

# Builtins that are types. `a | b` over ordinary values (sets, ints, flags) is
# legal in 3.9 and must NOT be flagged, so a union is only called a TYPE union
# when every leaf reads as a type: a builtin type name, a capitalised name or
# attribute, a subscript of one, or the bare `None` of `X | None` — which is
# never anything but a type union.
_BUILTIN_TYPE_NAMES = frozenset({
    "bool", "bytearray", "bytes", "complex", "dict", "float", "frozenset",
    "int", "list", "object", "range", "set", "str", "tuple", "type",
})


def _named_like_a_type(name: str) -> bool:
    # CamelCase or a builtin type. ALL_CAPS is a constant, not a type — this
    # clause is what keeps `os.O_RDWR | os.O_CREAT` out of the offender list.
    return name in _BUILTIN_TYPE_NAMES or (name[:1].isupper() and not name.isupper())


def _reads_as_a_type(node) -> bool:
    if isinstance(node, ast.Name):
        return _named_like_a_type(node.id)
    if isinstance(node, ast.Attribute):
        return _named_like_a_type(node.attr)
    if isinstance(node, ast.Subscript):
        return _reads_as_a_type(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _is_type_union(node)
    return False


def _is_none(node) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _is_type_union(node: ast.BinOp) -> bool:
    sides = (node.left, node.right)
    # A bare `None` inside a `|` is only ever `Optional`; otherwise every side
    # has to read as a type before the union is called one.
    if any(_is_none(s) for s in sides):
        return all(_is_none(s) or _reads_as_a_type(s) for s in sides)
    return all(_reads_as_a_type(s) for s in sides)


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

    def test_the_config_veto_alone_keeps_the_lane_unconfigurable(self, tmp_path):
        """ONE ARM PER VETO — the config half, on its own.

        The arm above passes if EITHER veto stands, so a single-veto deletion
        is invisible to it (the reviewer of cp3 reproduced exactly that:
        dropping `load_autonomy`'s ACTIONABLE_KINDS loop OR
        `can_auto_apply`'s STRUCTURAL_KINDS check, one at a time, left the
        whole suite green). This arm reads only what `load_autonomy` puts in
        the policy: a file that asks for an auto lane on a structural kind
        must leave `defaults` with no structural key at all, so the widening
        `for k in VALID_KINDS` reds here alone.
        """
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "autonomy.yml").write_text(
            "defaults:\n  skill: auto\n  authority: auto\n  information: auto\n")
        policy = load_autonomy(cabinet_root=tmp_path)
        assert set(policy.defaults) & STRUCTURAL_KINDS == set(), policy.defaults

    def test_the_gate_veto_alone_refuses_a_policy_that_already_says_auto(self):
        """ONE ARM PER VETO — the gate half, on its own.

        `load_autonomy` is not the only way a policy reaches `can_auto_apply`:
        the parameter is public and every caller may build its own. This arm
        hands the gate the exact state the config veto exists to prevent —
        `defaults` already carrying `<structural kind>: auto` — so it exercises
        `can_auto_apply`'s own refusal with the config veto out of the picture,
        and reds alone when that refusal is deleted.
        """
        for kind in sorted(STRUCTURAL_KINDS):
            policy = AutonomyPolicy(defaults={kind: "auto"})
            assert policy.defaults[kind] == "auto"  # the gate is not being fed a no-op
            assert can_auto_apply(kind, set(), policy) is False
            assert can_auto_apply(kind, None, policy) is False

    def test_classify_never_resolves_an_ambiguity_to_a_structural_kind(self):
        """An ambiguous need must reach the Captain, not go quiet."""
        for kind in sorted(STRUCTURAL_KINDS):
            assert classify("", "", ambiguous_default=kind) == "tool"

    def test_module_parses_under_python_39_grammar(self):
        """A0.3: the pull path can be imported by the box's own python3 (3.9)."""
        rel = "framework/learning/capability_gaps.py"
        source = (_REPO_ROOT / rel).read_text()
        ast.parse(source, filename=rel, feature_version=(3, 9))

    def test_module_evaluates_no_310_union_at_runtime(self):
        """A0.3, the half `feature_version` cannot see.

        `X | Y` is GRAMMAR-legal in every version — it is a BinOp — so the
        parse above passes a module that raises `TypeError: unsupported
        operand type(s) for |` the moment 3.9 imports it. The deferred
        annotation positions are safe (the module's `from __future__ import
        annotations` turns them into strings, asserted here rather than
        assumed); every OTHER position is evaluated, so this walks them.
        """
        rel = "framework/learning/capability_gaps.py"
        tree = ast.parse((_REPO_ROOT / rel).read_text(), filename=rel)

        assert any(
            isinstance(n, ast.ImportFrom) and n.module == "__future__"
            and any(a.name == "annotations" for a in n.names)
            for n in tree.body
        ), "annotations are evaluated without the future import"

        # Positions PEP 563 defers — the whole subtree, not just its root, so
        # a union nested inside `Dict[str, int | None]` is deferred too.
        deferred = set()
        for node in ast.walk(tree):
            roots = []
            if isinstance(node, (ast.AnnAssign, ast.arg)) and node.annotation:
                roots.append(node.annotation)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
                roots.append(node.returns)
            for root in roots:
                deferred.update(id(sub) for sub in ast.walk(root))

        offenders = [
            "line %d" % n.lineno
            for n in ast.walk(tree)
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)
            and id(n) not in deferred and _is_type_union(n)
        ]
        assert offenders == [], "3.10-only union evaluated at import: %s" % offenders


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


# ---------------------------------------------------------------------------
# The coupling this module carries into the pull path, made loud
# ---------------------------------------------------------------------------

class TestLedgerDirectoryCoupling:
    """`_gaps_lock` resolves its directory through the emitter's own resolver.

    The lock is only a lock if it sits where the ledger sits: two writers
    holding two different lock files serialize nothing. This module therefore
    imports `framework.events.emitter._event_log_dir` — a PRIVATE name — and a
    rename there breaks `capability_gaps` at IMPORT time, on a module the
    schg-locked hook imports on every officer tick.

    The import stays hard on purpose: a `try/except ImportError` fallback that
    guessed a directory would put the lock somewhere the ledger is not, which
    is a silent fail-open on a concurrency control — strictly worse than an
    import error a test can see. So the coupling is pinned here instead, with
    the fix in the failure text. Promoting `_event_log_dir` to a public
    accessor is an `emitter.py` change and `emitter.py` belongs to the claim
    unit at this commit; whoever lands that updates this test and the import
    together.
    """

    def test_the_lock_file_lands_in_the_ledger_directory(self, event_log_dir):
        record_gap("no holder on the roster for task-009 of outcome-a",
                   kind="skill", recorded_by="supervisor",
                   dedup_key="holder:outcome-a:task-009")

        from framework.learning.capability_gaps import _GAPS_LOCK_NAME

        lock = event_log_dir / _GAPS_LOCK_NAME
        assert lock.exists(), sorted(p.name for p in event_log_dir.iterdir())
        # ...the SAME directory the projection replays, not merely a plausible
        # one: the ledger the gap was written to is right beside it.
        assert list(event_log_dir.glob("events-*.jsonl")), \
            sorted(p.name for p in event_log_dir.iterdir())

    def test_the_private_emitter_symbol_this_module_imports_still_exists(self):
        """Fires in the case that matters: the rename landed WITH its import fix.

        A rename with no fix is already loud — `capability_gaps` fails at
        import and every test in this file errors. The silent case is the good
        citizen who renames `_event_log_dir` to a public accessor, updates the
        import in `capability_gaps.py`, and leaves this file's docstring
        describing a coupling that no longer exists. Then THIS goes red and
        says so.
        """
        import framework.events.emitter as emitter

        assert hasattr(emitter, "_event_log_dir"), (
            "framework/events/emitter.py no longer exports `_event_log_dir`. "
            "framework/learning/capability_gaps.py imports it at module scope "
            "for `_gaps_lock`, so this rename breaks the pull path at import "
            "time. Update that import in the SAME commit — and if the rename "
            "made it public, point this test at the public name."
        )


class TestTheLockOrderThisUnitCanActuallyPin:
    """`_gaps_lock`'s docstring fixes claims-lock -> gaps-lock -> ledger-lock.

    A3.1 says keyed records are taken "under the claims lock";
    `framework/missions/claims.py` does not exist at this commit, so the
    ordering sentence was written into the docstring against the day it does.
    The cp3 reviewer's note is exact: NOTHING asserted it, so an inversion
    introduced later would be caught by no sensor here.

    Half of it is unassertable from this unit and stays U2's — no call site
    holds a claims lock yet, so there is no order to observe. The OTHER half is
    the sentence this module makes about ITSELF ("nothing in this module ever
    takes a claims lock, so this module cannot invert it on its own"), and that
    is checkable today. Pinned here rather than left as prose, because a
    docstring promising a property is a claim surface.

    STATED LIMIT, so nobody reads this as more than it is: it proves only that
    the acquisition of a claims lock does not appear in THIS module. It cannot
    see an inversion introduced in claims.py or at a call site, and it is not a
    substitute for U2's ordering test at the site where the pull path holds the
    claims lock while recording a gap.
    """

    def test_this_module_never_acquires_a_claims_lock(self):
        rel = "framework/learning/capability_gaps.py"
        source = (_REPO_ROOT / rel).read_text()
        tree = ast.parse(source, filename=rel)

        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "claims" in node.module.split("."):
                    offenders.append(f"line {node.lineno}: from {node.module} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if "claims" in alias.name.split("."):
                        offenders.append(f"line {node.lineno}: import {alias.name}")
            elif isinstance(node, ast.Attribute) and "claim" in node.attr.lower() \
                    and "lock" in node.attr.lower():
                offenders.append(f"line {node.lineno}: .{node.attr}")
            elif isinstance(node, ast.Name) and "claim" in node.id.lower() \
                    and "lock" in node.id.lower():
                offenders.append(f"line {node.lineno}: {node.id}")

        assert not offenders, (
            "framework/learning/capability_gaps.py now reaches for a claims "
            "lock: " + "; ".join(offenders) + ". `_gaps_lock`'s docstring fixes "
            "the order as claims-lock -> gaps-lock -> ledger-lock; taking a "
            "claims lock from INSIDE this module can only take it after the "
            "gaps lock, which is the inversion. Move the acquisition out to "
            "the caller, and update that docstring in the same commit."
        )

    def test_the_ordering_sentence_is_still_in_the_docstring_it_binds(self):
        """The rule's only home today is prose, so pin the prose.

        Red when someone deletes the paragraph (or edits the order into a
        different one) without landing the call-site test that would replace
        it — which is exactly how a rule with no enforcement disappears.
        """
        from framework.learning.capability_gaps import _gaps_lock

        doc = (_gaps_lock.__doc__ or "").replace("\n", " ")
        doc = " ".join(doc.split())
        assert "claims-lock → gaps-lock → ledger-lock" in doc, doc
