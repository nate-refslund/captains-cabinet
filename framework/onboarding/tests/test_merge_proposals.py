"""merge_proposals — the MERGE-BY-CARD-ID writer for outcomes-proposed.yml
(onboarding design 2026-07-14 Phase 1).

The contract under test: existing card bodies are preserved VERBATIM
(Captain edits win — genesis's write-once semantics extended to merges),
only NEW ids are appended, an unparseable existing file is never rewritten,
and nothing the writer does can activate (outcomes.yml is never touched).

Hermetic: tmp_path roots only — never the checkout's own instance/.
"""
import yaml

from framework.onboarding import genesis

ANSWERS = {
    "version": 1,
    "cabinet": {"id": "acme-hq", "mode": "single", "org_shape": "portfolio"},
    "lanes": [{"name": "Acme Storefront", "slug": "acme-store",
               "repos": ["acme/storefront"]}],
}


def _card(cid, what="do the thing"):
    return {"id": cid, "name": f"Card {cid}", "lane": None, "what": what,
            "why": "because", "proof_expected": "a receipt",
            "status": "draft", "captain_ratified": False,
            "proposed_by": "onboarding-genesis"}


def _read_doc(root):
    return yaml.safe_load((root / genesis.PROPOSALS_REL).read_text(encoding="utf-8"))


def _rows_by_id(root):
    return {r["id"]: r for r in _read_doc(root)["outcomes"]}


# ---------------------------------------------------------------------------
# Absent file — merge degrades to the write path.
# ---------------------------------------------------------------------------
def test_merge_into_absent_file_writes(tmp_path):
    res = genesis.merge_proposals([_card("a"), _card("b")], tmp_path,
                                  answers=ANSWERS, now="2026-07-14T00:00:00Z")
    assert res["written"] is True and res["added"] == 2
    rows = _rows_by_id(tmp_path)
    assert set(rows) == {"a", "b"}
    for r in rows.values():
        assert r["status"] == "draft" and r["captain_ratified"] is False


# ---------------------------------------------------------------------------
# The judge-confirmed collision: Captain edits must survive a merge.
# ---------------------------------------------------------------------------
def test_merge_preserves_captain_edited_bodies_and_appends_only_new(tmp_path):
    genesis.write_proposals([_card("a")], tmp_path, answers=ANSWERS,
                            now="2026-07-01T00:00:00Z")
    # The Captain edits the draft: rewrites `what`, adds a custom key.
    path = tmp_path / genesis.PROPOSALS_REL
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["outcomes"][0]["what"] = "CAPTAIN-EDITED what"
    doc["outcomes"][0]["captain_note"] = "keep this"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    # A later organ merges the SAME id (different body) + one new id.
    res = genesis.merge_proposals(
        [_card("a", what="regenerated — must NOT win"), _card("b")],
        tmp_path, answers=ANSWERS, now="2026-07-14T00:00:00Z")
    assert res["status"] == "merged" and res["added"] == 1

    rows = _rows_by_id(tmp_path)
    assert set(rows) == {"a", "b"}
    assert rows["a"]["what"] == "CAPTAIN-EDITED what"       # edit preserved
    assert rows["a"]["captain_note"] == "keep this"         # custom key survives
    assert rows["b"]["proposed_at"] == "2026-07-14T00:00:00Z"  # new row stamped
    assert _read_doc(tmp_path)["last_merged_at"] == "2026-07-14T00:00:00Z"


def test_merge_with_no_new_ids_leaves_file_byte_identical(tmp_path):
    genesis.write_proposals([_card("a")], tmp_path, answers=ANSWERS,
                            now="2026-07-01T00:00:00Z")
    path = tmp_path / genesis.PROPOSALS_REL
    before = path.read_bytes()
    res = genesis.merge_proposals([_card("a")], tmp_path, answers=ANSWERS)
    assert res["status"] == "no-new-cards" and res["written"] is False
    assert path.read_bytes() == before


def test_merge_preserves_existing_comment_header(tmp_path):
    genesis.write_proposals([_card("a")], tmp_path, answers=ANSWERS,
                            now="2026-07-01T00:00:00Z")
    path = tmp_path / genesis.PROPOSALS_REL
    path.write_text("# CAPTAIN HEADER — hands off\n" + path.read_text(
        encoding="utf-8").split("\n", 1)[1], encoding="utf-8")
    genesis.merge_proposals([_card("b")], tmp_path, answers=ANSWERS)
    assert path.read_text(encoding="utf-8").startswith(
        "# CAPTAIN HEADER — hands off")


# ---------------------------------------------------------------------------
# Honest refusal — an unparseable existing file is never clobbered.
# ---------------------------------------------------------------------------
def test_merge_refuses_unparseable_existing_file(tmp_path):
    path = tmp_path / genesis.PROPOSALS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("outcomes: {not: [valid, list", encoding="utf-8")
    before = path.read_bytes()
    res = genesis.merge_proposals([_card("a")], tmp_path, answers=ANSWERS)
    assert res["status"] == "unmergeable-existing" and res["written"] is False
    assert path.read_bytes() == before          # NEVER rewritten


# ---------------------------------------------------------------------------
# Nothing activates — the merge writer's structural safety.
# ---------------------------------------------------------------------------
def test_merge_never_touches_outcomes_yml_and_rows_stay_draft(tmp_path):
    genesis.write_proposals([_card("a")], tmp_path, answers=ANSWERS)
    genesis.merge_proposals([_card("b"), _card("c")], tmp_path, answers=ANSWERS)
    # The compiler-readable sibling was never created, let alone written.
    compiler_file = (tmp_path / genesis.PROPOSALS_REL).with_name("outcomes.yml")
    assert not compiler_file.exists()
    for r in _rows_by_id(tmp_path).values():
        assert r["status"] == "draft"
        assert r["captain_ratified"] is False
