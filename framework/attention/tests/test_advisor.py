"""advisor — the "Noticed" lane (onboarding design 2026-07-14 Phase 1).

Contracts under test: the charter's advisory class is briefing-route only
(never ping-now, never a floor class); the V1 detectors are deterministic
and honest (fire on real conditions, stay quiet on absence/unverifiable);
budgets are charter data (max_per_briefing / cooldown_days / max_open) with
every suppression reasoned; and NOTHING ACTIVATES — the pass writes only its
own state file under CABINET_ATTENTION_DIR.

Hermetic: tmp_path roots + CABINET_ATTENTION_DIR monkeypatch — no network,
no LLM, never the checkout's own instance/.
"""
import json

import yaml

from framework.attention import advisor, charter

NOW = "2026-07-14T12:00:00Z"

ANSWERS = {
    "version": 1,
    "cabinet": {"id": "acme-hq", "mode": "single", "org_shape": "portfolio"},
    "lanes": [{"name": "Demo", "slug": "demo", "repos": []}],
}


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_proposals(root, *, doc_ts, rows):
    doc = {"schema": "cabinet.outcomes-proposed/v1", "deployment": "acme-hq",
           "proposed_at": doc_ts, "outcomes": rows}
    return _write(root, "instance/config/outcomes-proposed.yml",
                  yaml.safe_dump(doc, sort_keys=False))


def _draft(cid, **extra):
    return {"id": cid, "name": cid, "status": "draft",
            "captain_ratified": False, **extra}


def _finding(fid, detector="aging-drafts", **extra):
    return {"id": fid, "kind": "advisory", "detector": detector,
            "evidence": f"evidence for {fid}", "action": "do something",
            **extra}


# ---------------------------------------------------------------------------
# The advisory class — charter data, briefing-route only.
# ---------------------------------------------------------------------------
def test_default_charter_advisory_class_never_pings():
    ch = charter.load_default()
    charter.validate_charter(ch)   # budgets must satisfy the schema
    r = charter.resolve({"kind": "advisory", "title": "noticed x"}, ch)
    assert r["class_id"] == "advisory"
    assert r["route"] == "next-briefing"       # never direct-now
    assert r["silent"] is True
    assert r["floor"] is False                 # never pierces quiet hours
    assert "advisory" not in r["quiet_hours"]["floor_classes"]
    assert r["budget"] == {"max_per_briefing": 3, "cooldown_days": 14,
                           "max_open": 7}


# ---------------------------------------------------------------------------
# Detector (b) — aging drafts.
# ---------------------------------------------------------------------------
def test_aging_drafts_fires_on_old_draft(tmp_path):
    _write_proposals(tmp_path, doc_ts="2026-07-01T00:00:00Z",
                     rows=[_draft("a"), _draft("b")])
    found = advisor.detect_aging_drafts(tmp_path, now=NOW)
    assert len(found) == 1                     # ONE summary card, not a nag each
    assert found[0]["id"] == "advisory-aging-drafts"
    assert "2 draft outcome card(s)" in found[0]["evidence"]
    assert "outcomes.yml" in found[0]["action"]  # the ratify path is named


def test_aging_drafts_quiet_on_fresh_ratified_or_absent(tmp_path):
    assert advisor.detect_aging_drafts(tmp_path, now=NOW) == []   # no file
    _write_proposals(tmp_path, doc_ts="2026-07-13T00:00:00Z",
                     rows=[_draft("fresh")])
    assert advisor.detect_aging_drafts(tmp_path, now=NOW) == []   # 1d old
    _write_proposals(tmp_path, doc_ts="2026-06-01T00:00:00Z", rows=[
        {"id": "done", "name": "done", "status": "active",
         "captain_ratified": True}])
    assert advisor.detect_aging_drafts(tmp_path, now=NOW) == []   # ratified


def test_aging_drafts_row_level_timestamp_beats_doc_level(tmp_path):
    # Old document, but the row itself was merged in yesterday → quiet.
    _write_proposals(tmp_path, doc_ts="2026-06-01T00:00:00Z",
                     rows=[_draft("new", proposed_at="2026-07-13T00:00:00Z")])
    assert advisor.detect_aging_drafts(tmp_path, now=NOW) == []


def test_aging_drafts_unparseable_timestamp_is_honest_skip(tmp_path):
    _write_proposals(tmp_path, doc_ts="not-a-date", rows=[_draft("a")])
    assert advisor.detect_aging_drafts(tmp_path, now=NOW) == []


# ---------------------------------------------------------------------------
# Detector (c) — stack-gap with ready-to-apply scope-diff text.
# ---------------------------------------------------------------------------
def _stack_root(tmp_path, *, scope_yml, repo_deps):
    root = tmp_path
    repo = root / "repos" / "demo"
    (repo).mkdir(parents=True)
    (repo / "package.json").write_text(json.dumps(
        {"name": "demo", "dependencies": repo_deps}), encoding="utf-8")
    answers = {**ANSWERS,
               "lanes": [{"name": "Demo", "slug": "demo",
                          "repos": [str(repo)]}]}
    _write(root, "instance/config/cabinet-init.answers.yml",
           yaml.safe_dump(answers, sort_keys=False))
    if scope_yml is not None:
        _write(root, "cabinet/mcp-scope.yml", scope_yml)
    return root


def test_stack_gap_fires_with_scope_diff_text(tmp_path):
    root = _stack_root(
        tmp_path,
        scope_yml="agents:\n  demo-ceo:\n    mcps: [library]\n",
        repo_deps={"@neondatabase/serverless": "1", "next": "15"})
    found = advisor.detect_stack_gaps(root)
    assert len(found) == 1
    f = found[0]
    assert f["id"] == "advisory-stack-gap-demo"
    assert "neon" in f["evidence"] and "vercel" in f["evidence"]
    # The ready-to-apply diff TEXT (computed read-only; never written by us).
    assert "demo-ceo" in f["scope_diff"] and "neon" in f["scope_diff"]
    assert "GERMLINE" in f["action"]           # the Captain applies it


def test_stack_gap_quiet_when_grant_present(tmp_path):
    root = _stack_root(
        tmp_path,
        scope_yml="agents:\n  demo-ceo:\n    mcps: [neon, vercel]\n",
        repo_deps={"@neondatabase/serverless": "1", "next": "15"})
    assert advisor.detect_stack_gaps(root) == []


def test_stack_gap_quiet_when_scope_file_unverifiable(tmp_path):
    # Absent scope file → grant absence unverifiable → NO nag (honest skip).
    root = _stack_root(tmp_path, scope_yml=None,
                       repo_deps={"@neondatabase/serverless": "1"})
    assert advisor.detect_stack_gaps(root) == []


def test_stack_gap_skips_lanes_without_local_repo(tmp_path):
    answers = {**ANSWERS, "lanes": [{"name": "Remote", "slug": "remote",
                                     "repos": ["https://github.com/x/y"]}]}
    _write(tmp_path, "instance/config/cabinet-init.answers.yml",
           yaml.safe_dump(answers, sort_keys=False))
    _write(tmp_path, "cabinet/mcp-scope.yml",
           "agents:\n  remote-ceo:\n    mcps: []\n")
    assert advisor.detect_stack_gaps(tmp_path) == []


# ---------------------------------------------------------------------------
# The pass — budgets as charter data, reasoned suppressions, closure hygiene.
# ---------------------------------------------------------------------------
def _fence(monkeypatch, tmp_path):
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(tmp_path / "attention"))


def test_run_advisor_emits_items_and_writes_only_its_state(tmp_path, monkeypatch):
    _fence(monkeypatch, tmp_path)
    ch = charter.load_default()
    res = advisor.run_advisor(tmp_path, now=NOW, charter=ch,
                              findings=[_finding("advisory-x")])
    assert res["emitted"] == ["advisory-x"] and res["suppressed"] == []
    item = res["items"][0]
    assert item["kind"] == "advisory"          # rides the advisory class
    assert item["urgency_tier"] == "batch"     # never ping-now
    assert "👁 Noticed" in item["payload"]["summary"]
    # NOTHING ACTIVATES: only the advisor's own state file was written.
    assert (tmp_path / "attention" / "advisor-state.json").is_file()
    from framework.onboarding import genesis
    assert not (tmp_path / genesis.PROPOSALS_REL).parent.exists()
    assert advisor.load_state()["advisory-x"]["status"] == "open"


def test_run_advisor_cooldown_suppresses_repeat(tmp_path, monkeypatch):
    _fence(monkeypatch, tmp_path)
    ch = charter.load_default()
    advisor.run_advisor(tmp_path, now="2026-07-10T00:00:00Z", charter=ch,
                        findings=[_finding("advisory-x")])
    res = advisor.run_advisor(tmp_path, now=NOW, charter=ch,   # 4d later < 14d
                              findings=[_finding("advisory-x")])
    assert res["emitted"] == []
    assert res["suppressed"] == [{"id": "advisory-x", "reason": "cooldown (14d)"}]


def test_run_advisor_max_per_briefing_cap(tmp_path, monkeypatch):
    _fence(monkeypatch, tmp_path)
    findings = [_finding(f"advisory-{i}") for i in range(5)]
    res = advisor.run_advisor(tmp_path, now=NOW, charter=charter.load_default(),
                              findings=findings)
    assert len(res["emitted"]) == 3            # charter budget: max_per_briefing 3
    assert [s["reason"] for s in res["suppressed"]] == \
        ["max_per_briefing (3)"] * 2


def test_run_advisor_max_open_cap(tmp_path, monkeypatch):
    _fence(monkeypatch, tmp_path)
    ch = charter.load_default()
    state = {f"advisory-old-{i}": {"last_emitted": NOW, "status": "open",
                                   "detector": "aging-drafts"}
             for i in range(7)}
    # 7 already open (cap) — but they must count as CURRENT findings, else
    # closure hygiene frees the slots. New finding → suppressed on max_open.
    findings = [_finding(f"advisory-old-{i}") for i in range(7)] + \
        [_finding("advisory-new")]
    res = advisor.run_advisor(tmp_path, now=NOW, charter=ch,
                              findings=findings, state=state, save=False)
    assert {"id": "advisory-new", "reason": "max_open (7)"} in res["suppressed"]
    assert "advisory-new" not in res["emitted"]


def test_run_advisor_closure_hygiene(tmp_path, monkeypatch):
    _fence(monkeypatch, tmp_path)
    ch = charter.load_default()
    advisor.run_advisor(tmp_path, now="2026-06-01T00:00:00Z", charter=ch,
                        findings=[_finding("advisory-x")])
    res = advisor.run_advisor(tmp_path, now=NOW, charter=ch, findings=[])
    assert res["closed"] == ["advisory-x"]     # condition gone → closed
    assert advisor.load_state()["advisory-x"]["status"] == "closed"


def test_run_advisor_end_to_end_over_real_detectors(tmp_path, monkeypatch):
    """Integration: a root with an aging draft AND a stack gap → two advisory
    items through real detectors, budgets, and state."""
    _fence(monkeypatch, tmp_path)
    root = _stack_root(
        tmp_path,
        scope_yml="agents:\n  demo-ceo:\n    mcps: [library]\n",
        repo_deps={"@neondatabase/serverless": "1"})
    _write_proposals(root, doc_ts="2026-06-20T00:00:00Z", rows=[_draft("a")])
    res = advisor.run_advisor(root, now=NOW, charter=charter.load_default())
    assert sorted(res["emitted"]) == ["advisory-aging-drafts",
                                      "advisory-stack-gap-demo"]
    assert all(i["urgency_tier"] == "batch" for i in res["items"])
    # Propose-only invariant: the pass created no compiler-readable file.
    from framework.onboarding import genesis
    assert not (root / genesis.PROPOSALS_REL).with_name("outcomes.yml").exists()
