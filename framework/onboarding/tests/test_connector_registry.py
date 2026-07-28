"""The connector registry, the seed field, the probe executor, and the join.

WHAT WAS BROKEN, and why every arm below is shaped as a both-directions test.
``journey._entry_grants`` read a state key (``entry_grants``) that NOTHING in
the tree ever wrote. ``connectors`` was therefore permanently empty, so
``ENTRY_MODE_CONNECTED`` — "sources are connected, so sweep them, derive, and
ASSERT with a citation", the exact mechanism of the Captain's 2026-07-26
ruling — could not be reached in production by any sequence of operator
actions. Two of three advertised modes worked; the one the direction is about
did not. In the same surface, the seed question was PRINTED with no action able
to carry an answer, and ``seed_probes`` returned proposals no code anywhere
executed.

So the arms here do not check that a registry exists. They check that the mode
FIRES through the public ``act`` API only, that each probe REFUSES at its
degenerate end (a ``.git`` whose HEAD resolves to nothing is not a repository;
an export that parses to zero rows is a file, not a tracker), and that the join
is a genuine cross-source claim — the same prose without the export produces
nothing, which is what makes it unreproducible by the single ``git grep`` that
reproduced two of the three pre-existing detectors.

Hermetic: tmp_path only, no network, no subprocess, no Redis.
"""
from __future__ import annotations

import json

import pytest

from framework.onboarding import journey, research


def _base(tmp_path, *, allow_hosts=None, enforce=True):
    """A cabinet root with an egress ceiling, located by the module's OWN
    constant — a test that re-spells the instance path both duplicates the
    framework→instance seam and adds a layer-separation violation for a string
    the code already owns."""
    base = tmp_path / "cabinet"
    egress = base / research._EGRESS_REL
    egress.parent.mkdir(parents=True, exist_ok=True)
    hosts = "[]" if not allow_hosts else json.dumps(list(allow_hosts))
    egress.write_text(
        f"enforce: {'true' if enforce else 'false'}\nallow_hosts: {hosts}\n",
        encoding="utf-8",
    )
    return base


def _git(root, *, head="ref: refs/heads/main", ref_value="a" * 40, packed=False):
    git = root / ".git"
    (git / "refs" / "heads").mkdir(parents=True, exist_ok=True)
    (git / "HEAD").write_text(head + "\n", encoding="utf-8")
    if ref_value is None:
        return git
    if packed:
        (git / "packed-refs").write_text(
            f"# pack-refs with: peeled\n{ref_value} refs/heads/main\n", encoding="utf-8"
        )
    else:
        (git / "refs" / "heads" / "main").write_text(ref_value + "\n", encoding="utf-8")
    return git


def _repo_probe(root):
    """The repo probe as the registry itself reaches it."""
    return research._probe_repo(root)


def _estate(tmp_path, *, tracker=True, repo=True, name="estate"):
    root = tmp_path / name
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "runbook.md").write_text(
        "# Release runbook\n\n"
        "- BLOCKED: the staging certificate renewal needs finance approval\n",
        encoding="utf-8",
    )
    if tracker:
        (root / "tracker-export.csv").write_text(
            "id,title,status,assignee\n"
            "ENG-1,Upgrade the payments SDK,In Progress,mara\n"
            "ENG-2,Document the release runbook,In Progress,mara\n",
            encoding="utf-8",
        )
    if repo:
        _git(root)
    return root


def _run_to_dividend(base, source, **overrides):
    request = {
        "surface": "cli", "action": "propose_window", "action_id": "w-1",
        "source": str(source), "purpose": "Learn how releases work here",
        "ownership": "self", "authority_basis": "my own folder",
    }
    request.update(overrides)
    out = journey.act(request, base)
    return journey.act(
        {"surface": "cli", "action": "ratify_charter", "action_id": "r-1",
         "charter_hash": out["state"]["charter"]["hash"]},
        base,
    )


# ── The writer that did not exist ────────────────────────────────────────────


def test_entry_grants_has_a_writer_and_the_connected_mode_fires_end_to_end(tmp_path):
    """The whole unit, through the public API only.

    Nothing here reaches into a private helper or hands ``entry_grants`` in: an
    operator grants a folder, the folder happens to contain a repository and a
    tracker export, and the mode the direction is about becomes reachable
    because two probes ANSWERED. On the pre-change module this test cannot pass
    at all — no code path writes the key it reads.
    """
    base = _base(tmp_path)
    source = _estate(tmp_path)

    ungranted = journey.snapshot(base)
    assert ungranted["card"]["entry"]["mode"] == journey.ENTRY_MODE_UNGRANTED
    assert ungranted["state"]["entry_grants"] == {
        "connectors": [], "local_files": False, "web": False
    }

    out = _run_to_dividend(base, source)
    grants = out["state"]["entry_grants"]
    assert grants["local_files"] is True
    assert any(n.startswith("repo:") for n in grants["connectors"])
    assert any(n.startswith("tracker_export:") for n in grants["connectors"])

    assert journey.entry_mode(grants) == journey.ENTRY_MODE_CONNECTED
    forward = journey.act(
        {"surface": "cli", "action": "continue", "action_id": "c-1"}, base
    )
    plan = forward["card"]["entry"]
    assert plan["mode"] == journey.ENTRY_MODE_CONNECTED
    assert plan["opening_move"] == "sweep_and_assert"
    # The connected mode does not ask what the sources already answer.
    assert plan["seed_question"] is None


def test_grants_are_reprobed_on_snapshot_so_a_lost_connector_stops_granting(tmp_path):
    """A registry that only refreshes on write would keep offering a dead estate."""
    base = _base(tmp_path)
    source = _estate(tmp_path)
    _run_to_dividend(base, source)
    assert journey.snapshot(base)["state"]["entry_grants"]["connectors"]

    (source / "tracker-export.csv").unlink()
    for path in sorted((source / ".git").rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    (source / ".git").rmdir()

    after = journey.snapshot(base)["state"]
    assert after["entry_grants"]["connectors"] == []
    assert after["entry_grants"]["local_files"] is True
    reasons = {(r["kind"], r["reason"]) for r in after["connector_probes"]["refused"]}
    assert ("repo", "no_git_dir") in reasons
    assert ("tracker_export", "export_missing") in reasons, (
        "a row count persisted at ratification is a fact about the past; the "
        "registry must re-stat the file or it is a declaration, not a probe"
    )
    assert journey.entry_mode(after["entry_grants"]) == journey.ENTRY_MODE_SEEDED


# ── Each probe refuses at its degenerate end ─────────────────────────────────


def test_a_repo_is_connected_only_when_its_head_actually_resolves(tmp_path):
    """A ``.git`` directory is a claim; a resolved object id is a fact."""
    live = tmp_path / "live"
    live.mkdir()
    _git(live)
    assert _repo_probe(live)["connected"] is True

    packed = tmp_path / "packed"
    packed.mkdir()
    _git(packed, ref_value="b" * 40, packed=True)
    assert _repo_probe(packed)["connected"] is True, "a freshly cloned repo packs its refs"

    for name, kwargs, reason in (
        ("dangling", {"ref_value": None}, "git_head_unresolvable"),
        ("garbage", {"ref_value": "not-a-sha"}, "git_head_unresolvable"),
        ("escaping", {"head": "ref: refs/../../etc/passwd"}, "git_head_unresolvable"),
        ("detached-junk", {"head": "zzzz", "ref_value": None}, "git_head_unresolvable"),
    ):
        root = tmp_path / name
        root.mkdir()
        _git(root, **kwargs)
        row = _repo_probe(root)
        assert row["connected"] is False and row["reason"] == reason, name

    bare = tmp_path / "bare"
    bare.mkdir()
    assert _repo_probe(bare)["reason"] == "no_git_dir"
    assert research._probe_repo(None)["reason"] == "no_ratified_source"


def test_the_web_grant_is_the_egress_ceiling_and_it_fails_closed(tmp_path):
    """An unknown ceiling reads as CLOSED. Absence is never permission."""
    empty = _base(tmp_path / "a")
    assert research._probe_web(empty)["reason"] == "egress_closed_no_allowed_hosts"

    missing = tmp_path / "b" / "cabinet"
    missing.mkdir(parents=True)  # a cabinet root with no egress ceiling at all
    assert research._probe_web(missing)["reason"] == "egress_config_absent"

    broken = _base(tmp_path / "c")
    (broken / research._EGRESS_REL).write_text(": [", encoding="utf-8")
    assert research._probe_web(broken)["reason"] == "egress_config_unreadable"

    open_hosts = _base(tmp_path / "d", allow_hosts=["api.example.com"])
    assert research._probe_web(open_hosts)["connected"] is True
    unenforced = _base(tmp_path / "e", enforce=False)
    assert research._probe_web(unenforced)["connected"] is True


def test_a_reachable_web_never_puts_entry_into_the_connected_mode(tmp_path):
    """``web`` names no estate, so it cannot back an assert-with-citation."""
    base = _base(tmp_path, allow_hosts=["api.example.com"])
    registry = research.probe_connectors(base, source_root=None, ratified=False)
    assert registry["grants"]["web"] is True
    assert registry["grants"]["connectors"] == []
    assert journey.entry_mode(registry["grants"]) == journey.ENTRY_MODE_SEEDED


def test_an_export_that_parsed_no_rows_is_a_file_not_a_connection(tmp_path):
    base = _base(tmp_path)
    registry = research.probe_connectors(
        base, source_root=None, ratified=True,
        exports=[{"path": "empty.csv", "rows": 0}, {"path": "real.csv", "rows": 4}],
    )
    assert registry["grants"]["connectors"] == ["tracker_export:real.csv"]
    assert any(r["reason"] == "export_parsed_no_rows" for r in registry["refused"])


def test_every_probe_that_did_not_answer_carries_its_reason(tmp_path):
    """A silent skip makes "nothing is connected" and "I never looked" identical."""
    base = _base(tmp_path)
    registry = research.probe_connectors(base, source_root=None, ratified=False)
    assert registry["connected"] == []
    reasons = {(r["kind"], r["reason"]) for r in registry["refused"]}
    assert reasons == {
        ("repo", "no_ratified_source"),
        ("web", "egress_closed_no_allowed_hosts"),
    }


def test_the_mcp_estate_is_deliberately_not_a_connector(tmp_path):
    """The cabinet's own declared servers are the WRONG SUBJECT.

    Counting them would let a cabinet that has connected nothing of the
    operator's world enter the connected mode and assert about an estate it
    never read — the defect the altitude direction gate named by file and line.
    """
    base = _base(tmp_path)
    (base / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"github": {}, "neon": {}}}), encoding="utf-8"
    )
    assert research.inventory_mcp_estate(str(base), consent=True)["servers"]
    assert research.probe_connectors(base, ratified=False)["grants"]["connectors"] == []


# ── The tracker export is recognised by SHAPE, never by name ─────────────────


def _entry(path, text):
    return {"path": path, "sha256": "0" * 64, "lines": text.splitlines()}


def test_a_tracker_export_is_recognised_by_shape_not_by_filename():
    named_but_prose = _entry("tasks.csv", "Just some notes\nand another line\n")
    assert journey._tracker_rows(named_but_prose) == []

    no_status = _entry("rows.csv", "id,title\n1,Do the thing\n")
    assert journey._tracker_rows(no_status) == []

    real = _entry("anything.csv", "key,summary,state\nENG-1,Ship the thing,Open\n")
    assert journey._tracker_rows(real) == [
        {"id": "ENG-1", "title": "Ship the thing", "status": "open"}
    ]

    as_json = _entry(
        "export.json",
        json.dumps([{"id": "T-1", "title": "Ship the thing", "status": "Done"}]),
    )
    assert journey._tracker_rows(as_json) == [
        {"id": "T-1", "title": "Ship the thing", "status": "done"}
    ]

    wrapped = _entry(
        "export.json",
        json.dumps({"issues": [{"key": "T-2", "name": "Other", "status": "Open"}]}),
    )
    assert journey._tracker_rows(wrapped)[0]["id"] == "T-2"

    assert journey._tracker_rows(_entry("notes.md", "id,title,status\n")) == []


# ── The join: the value is the JOIN, not the vault ───────────────────────────


def test_the_join_needs_both_sources_and_cites_both(tmp_path):
    """The finding is unreachable from either source alone.

    That is the whole bound the refuted ingest experiment imposed: of its four
    findings ONE needed more than one file and ZERO needed more than one
    system, and two of the three existing detectors are reproduced exactly by
    ``git grep -E 'TODO|FIXME|URGENT|BLOCKED'``. This one is not.
    """
    prose = _entry(
        "docs/runbook.md",
        "# Runbook\n- BLOCKED: the staging certificate renewal needs finance approval\n",
    )
    export = _entry(
        "tracker.csv",
        "id,title,status\nENG-1,Upgrade the payments SDK,In Progress\n",
    )

    alone, state = journey._untracked_commitment([prose])
    assert alone == []
    assert state == {"ran": False, "reason": "no_tracker_export_in_window"}

    joined, state = journey._untracked_commitment([prose, export])
    assert state["ran"] is True and state["open_rows_checked"] == 1
    assert len(joined) == 1
    finding = joined[0]
    assert finding["kind"] == "untracked_commitment"
    cited = {c["path"] for c in finding["citations"]}
    assert cited == {"docs/runbook.md", "tracker.csv"}, (
        "without the export citation the negative half of the claim — no open "
        "row accounts for this — is a negative nobody can check"
    )


def test_the_join_stays_quiet_when_an_open_row_already_accounts_for_it():
    prose = _entry(
        "docs/plan.md", "TODO: rotate the staging certificate before cutover\n"
    )
    tracked = _entry(
        "tracker.csv", "id,title,status\nENG-9,Rotate the staging certificate,Open\n"
    )
    findings, state = journey._untracked_commitment([prose, tracked])
    assert state["ran"] is True
    assert findings == []


def test_a_closed_row_does_not_account_for_an_open_commitment():
    """The tracker saying "done" while the document says "blocked" IS the finding."""
    prose = _entry("docs/plan.md", "BLOCKED: rotate the staging certificate\n")
    closed = _entry(
        "tracker.csv", "id,title,status\nENG-9,Rotate the staging certificate,Done\n"
    )
    findings, _ = journey._untracked_commitment([prose, closed])
    assert [f["kind"] for f in findings] == ["untracked_commitment"]


def test_a_one_word_commitment_is_too_thin_to_claim_a_miss():
    prose = _entry("docs/plan.md", "TODO: cutover\n")
    export = _entry("tracker.csv", "id,title,status\nENG-1,Something else,Open\n")
    findings, state = journey._untracked_commitment([prose, export])
    assert state["ran"] is True
    assert findings == []


def test_the_join_wins_the_dividend_over_the_single_source_marker(tmp_path):
    """A cross-source claim outranks the operator's own handwriting."""
    base = _base(tmp_path)
    source = _estate(tmp_path)
    out = _run_to_dividend(base, source)
    dividend = out["state"]["first_dividend"]
    assert dividend["finding"]["kind"] == "untracked_commitment"
    assert dividend["join"]["ran"] is True
    assert len(dividend["finding"]["citations"]) == 2


# ── Detector honesty ─────────────────────────────────────────────────────────


def test_the_dividend_names_the_detectors_that_ran_not_a_constant(tmp_path):
    """``detectors`` was a hardcoded list naming a detector that could not fire.

    ``_command_drift`` returns nothing AT ALL without a package.json in the
    window, so every dividend from a window without one advertised a disabled
    sensor as a live one — the same class as a coverage statistic that conceals
    its own loss, one layer down.
    """
    base = _base(tmp_path)
    source = _estate(tmp_path, tracker=False, repo=False)
    dividend = _run_to_dividend(base, source)["state"]["first_dividend"]
    assert "software_command_drift" not in dividend["detectors"]
    assert {"name": "software_command_drift", "reason": "no_package_json_in_window"} \
        in dividend["detectors_skipped"]
    assert {"name": "untracked_commitment", "reason": "no_tracker_export_in_window"} \
        in dividend["detectors_skipped"]


def test_a_negative_discloses_the_detectors_that_could_not_run(tmp_path):
    """Reading every file proves nothing about a question nobody could ask."""
    base = _base(tmp_path)
    source = tmp_path / "quiet"
    source.mkdir()
    (source / "README.md").write_text("# quiet\n\nNothing notable here.\n", encoding="utf-8")
    dividend = _run_to_dividend(base, source)["state"]["first_dividend"]
    assert dividend["finding"]["kind"] == "orientation_map"
    summary = dividend["finding"]["summary"]
    assert "I could not run" in summary
    assert "software_command_drift" in summary and "untracked_commitment" in summary


# ── The seed question now has a field, and the probes have an executor ───────


@pytest.mark.parametrize(
    "grants",
    [
        {},
        {"local_files": True},
        {"web": True},
        {"local_files": True, "web": True},
    ],
)
def test_every_printed_seed_question_carries_the_action_that_answers_it(grants):
    """A question with no way to answer it is a dead end wearing an invitation."""
    plan = journey.entry_plan(grants)
    assert plan["seed_question"] == journey.SEED_QUESTION
    answering = [a for a in plan["next_actions"] if a["action"] == "answer_seed"]
    assert len(answering) == 1
    assert answering[0]["input"] == "seed", (
        "a surface must be told this needs a text field, not a button"
    )


def test_the_connected_mode_asks_no_seed_question_and_offers_no_seed_field():
    plan = journey.entry_plan({"connectors": ["tracker_export:x.csv"]})
    assert plan["seed_question"] is None
    assert [a["action"] for a in plan["next_actions"]] == ["propose_window"]


def test_answering_the_seed_runs_the_probes_and_records_what_they_found(tmp_path):
    base = _base(tmp_path)
    source = tmp_path / "notes"
    (source / "sub").mkdir(parents=True)
    (source / "sub" / "payments-release.md").write_text("# payments\n", encoding="utf-8")
    (source / "README.md").write_text("# notes\n", encoding="utf-8")
    _run_to_dividend(base, source)
    onward = journey.act(
        {"surface": "cli", "action": "continue", "action_id": "c-1"}, base
    )
    assert onward["card"]["entry"]["mode"] == journey.ENTRY_MODE_SEEDED

    out = journey.act(
        {"surface": "cli", "action": "answer_seed", "action_id": "s-1",
         "seed": "I look after payments releases"},
        base,
    )
    discovery = out["card"]["entry"]["discovery"]
    assert discovery["terms"], "the seed must become searchable terms"
    executed = discovery["executed"]
    assert executed["schema"] == journey.PROBE_RESULT_SCHEMA
    found = {m for row in executed["executed"] for m in row["matches"]}
    assert "sub/payments-release.md" in found
    assert out["state"]["seed"]["text"] == "I look after payments releases"
    assert "went looking" in out["card"]["body"]


def test_an_empty_seed_is_refused_and_a_long_one_is_bounded(tmp_path):
    base = _base(tmp_path)
    with pytest.raises(journey.JourneyError) as excinfo:
        journey.act(
            {"surface": "cli", "action": "answer_seed", "action_id": "s-1", "seed": "   "},
            base,
        )
    assert excinfo.value.code == "seed_required"

    out = journey.act(
        {"surface": "cli", "action": "answer_seed", "action_id": "s-2",
         "seed": "payments " * 400},
        base,
    )
    assert len(out["state"]["seed"]["text"]) == journey.MAX_SEED_CHARS


def test_a_probe_pattern_from_operator_text_can_never_become_a_traversal(tmp_path):
    """The operator's own words reach this pattern; a separator would escape."""
    source = tmp_path / "window"
    source.mkdir()
    (source / "safe.md").write_text("x\n", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret-plan.md").write_text("x\n", encoding="utf-8")

    result = journey._execute_probes(
        source,
        [
            {"kind": "local_name_match", "pattern": "../outside/*"},
            {"kind": "local_name_match", "pattern": "ci/cd*"},
            {"kind": "local_name_match", "pattern": "/etc/passwd"},
            {"kind": "local_name_match", "pattern": "safe*"},
        ],
    )
    assert [r["pattern"] for r in result["executed"]] == ["safe*"]
    assert {r["reason"] for r in result["deferred"]} == {"pattern_unsafe"}
    assert result["complete"] is False


def test_the_executor_never_matches_a_sensitive_or_hidden_or_symlinked_file(tmp_path):
    """Three separate refusals, and each fixture may trip only ITS OWN one.

    The first version of this arm named every fixture ``*salary*``, so the
    sensitivity refusal alone answered for all three and deleting either the
    hidden-name guard or the symlink guard left it green: a test naming three
    controls while pinning one. Each name below is refusable on exactly one
    ground, and the plain file proves the probe still matches when nothing
    refuses — otherwise an executor that returned ``[]`` unconditionally would
    pass this too.
    """
    source = tmp_path / "window"
    (source / "hidden").mkdir(parents=True)
    (source / "plain-notes.md").write_text("a\n", encoding="utf-8")
    (source / ".dotted-notes.md").write_text("a\n", encoding="utf-8")  # hidden only
    (source / "salary-notes.md").write_text("a\n", encoding="utf-8")  # sensitive only
    outside = tmp_path / "elsewhere-notes.md"
    outside.write_text("a\n", encoding="utf-8")
    (source / "linked-notes.md").symlink_to(outside)  # symlink only

    result = journey._execute_probes(source, [{"kind": "local_name_match", "pattern": "*notes*"}])
    matches = result["executed"][0]["matches"]
    assert matches == ["plain-notes.md"], f"the executor surfaced a refused path: {matches}"


# ── A partial search is never reported as a whole one ────────────────────────


def test_a_search_that_stopped_at_its_limit_is_not_a_complete_run(tmp_path):
    """``complete`` read only ``deferred``, so a truncated probe passed as whole.

    ``_name_matches`` already returned ``truncated`` and already recorded it per
    probe; nothing consulted it. A window with more matches than
    ``MAX_PROBE_HITS`` therefore reported ``complete: True`` and an operator
    sentence naming a hit count that was the CAP, not the count.
    """
    source = tmp_path / "window"
    source.mkdir()
    for index in range(journey.MAX_PROBE_HITS + 5):
        (source / f"payments-{index:02d}.md").write_text("a\n", encoding="utf-8")

    result = journey._execute_probes(
        source, [{"kind": "local_name_match", "pattern": "*payments*"}]
    )
    assert result["executed"][0]["truncated"] is True
    assert len(result["executed"][0]["matches"]) == journey.MAX_PROBE_HITS
    assert result["deferred"] == [], "nothing was deferred — truncation is the only defect here"
    assert result["complete"] is False, (
        "a probe that stopped partway through the window has not searched it"
    )
    assert "stopped at my limit" in journey._discovery_note(result)


def test_a_truncated_search_never_tells_the_operator_nothing_is_there(tmp_path, monkeypatch):
    """The unearned negative, in the smallest frame this surface has.

    Zero hits plus an early stop rendered as "I went looking in that folder and
    nothing matched by name" — a claim about a folder the probe never finished
    reading, on a card whose whole purpose is to say what it does not know. The
    entry cap is shrunk rather than simulated: the truncation below is produced
    by the real walk, not by a fixture hand-written in the shape being asserted.
    """
    monkeypatch.setattr(journey, "MAX_PROBE_ENTRIES", 2)
    source = tmp_path / "window"
    source.mkdir()
    for index in range(6):
        (source / f"unrelated-{index}.md").write_text("a\n", encoding="utf-8")

    result = journey._execute_probes(
        source, [{"kind": "local_name_match", "pattern": "*payments*"}]
    )
    assert result["executed"][0]["matches"] == []
    assert result["executed"][0]["truncated"] is True
    assert result["complete"] is False
    note = journey._discovery_note(result)
    assert "nothing matched by name" in note, "the negative itself still belongs on the card"
    assert "stopped at my limit before the end of that folder" in note, (
        "a negative from an unfinished search must carry that it was unfinished"
    )


def test_a_probe_class_that_did_not_run_is_reported_never_dropped(tmp_path):
    """"Found nothing" must never be claimed on behalf of a probe that did not run."""
    source = tmp_path / "window"
    source.mkdir()
    result = journey._execute_probes(
        source,
        [{"kind": "web_search", "query": "payments releases"},
         {"kind": "local_name_match", "pattern": "*payments*"}],
    )
    assert [r["kind"] for r in result["deferred"]] == ["web_search"]
    assert result["deferred"][0]["reason"] == "no_egress_in_the_onboarding_core"
    assert result["complete"] is False


def test_probes_are_deferred_when_there_is_no_ratified_window(tmp_path):
    result = journey._execute_probes(None, [{"kind": "local_name_match", "pattern": "*x*"}])
    assert result["executed"] == []
    assert result["deferred"][0]["reason"] == "no_ratified_first_window"
    assert result["complete"] is False


def test_a_seed_cannot_conjure_a_reach_that_was_never_granted(tmp_path):
    """No web grant, no web probe — the seed widens nothing."""
    base = _base(tmp_path)
    out = journey.act(
        {"surface": "cli", "action": "answer_seed", "action_id": "s-1",
         "seed": "I look after payments releases"},
        base,
    )
    discovery = out["card"]["entry"]["discovery"]
    assert discovery["probes"] == []
    assert discovery["executed"]["executed"] == []
