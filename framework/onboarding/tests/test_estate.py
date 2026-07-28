"""The DERIVED ESTATE — what the cabinet READ, and the gate ``lanes: []`` rides.

Hermetic: tmp_path roots and the REAL journey against a synthetic source
folder. No network, no LLM, no Redis, never the checkout's own instance/.

The load-bearing arms here are the ones that would pass on a broken build:
``derive_estate`` must work with the source folder DELETED (it re-derives from
ratified artifacts and performs no new read), the usability gate must accept an
EMPTY estate but refuse an absent or foreign one, and a lane derived from a
source the operator has not classified ``self`` must never be proposed
write-capable.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from framework.onboarding import estate, journey


def _make_source(base: Path, *, children: bool = True) -> Path:
    src = base / "granted"
    src.mkdir(parents=True)
    (src / "README.md").write_text("# Acme monorepo\n", encoding="utf-8")
    if children:
        (src / "storefront").mkdir()
        (src / "storefront" / "README.md").write_text(
            "# Storefront\n\nRun `make dev`.\n", encoding="utf-8")
        (src / "storefront" / "package.json").write_text(
            '{"name":"storefront"}\n', encoding="utf-8")
        (src / "labs").mkdir()
        (src / "labs" / "pyproject.toml").write_text(
            "[project]\nname='labs'\n", encoding="utf-8")
    return src


def _ratified_journey(root: Path, src: Path, *, ownership: str = "self") -> None:
    """The ingest ceiling REFUSES an unclassified source, so every fixture
    declares a class and its basis — exactly as an operator must."""
    proposal = journey.act({
        "action": "propose_window", "action_id": "e-propose", "surface": "test",
        "source": str(src), "purpose": "Find one release risk.",
        "relationship_destination": "reversible",
        "ownership": ownership,
        "authority_basis": "synthetic fixture folder created by this test",
    }, root, now="2026-07-26T00:00:00Z")
    journey.act({
        "action": "ratify_charter", "action_id": "e-ratify", "surface": "test",
        "expected_revision": proposal["state"]["revision"],
        "charter_hash": proposal["state"]["charter"]["hash"],
    }, root, now="2026-07-26T00:00:01Z")


ANSWERS = {"cabinet": {"id": "acme-hq"}, "mission": {"altitude": "contributor"}}


# ---------------------------------------------------------------------------
# derivation from a ratified First Window
# ---------------------------------------------------------------------------
def test_ratified_window_yields_one_cited_source_and_its_entities(tmp_path):
    src = _make_source(tmp_path)
    root = tmp_path / "root"
    _ratified_journey(root, src)
    doc = estate.derive_estate(root, answers=ANSWERS, run_id="r1",
                               now="2026-07-26T00:01:00Z")

    assert doc["schema"] == estate.SCHEMA
    assert doc["deployment"] == "acme-hq"
    assert doc["altitude"] == "contributor"
    assert len(doc["sources"]) == 1
    source = doc["sources"][0]
    assert source["source_root"] == str(src)   # the access-record field name
    assert source["read_only"] is True
    assert source["raw_contents_persisted"] is False
    assert source["charter_hash"] and source["manifest_hash"]
    assert source["entry_count"] >= 4
    # ASKED at the ingest ceiling and bound into the charter hash — this module
    # READS the answer rather than asking again or keeping a second vocabulary.
    assert source["ownership"] == "self"
    assert source["authority_basis"]
    assert source["attestation_limit"]        # what the framework cannot verify
    assert source["refusals_total"] == sum(source["refusals"].values())

    ids = {e["id"] for e in doc["entities"]}
    assert ids == {"storefront", "labs"}
    store = next(e for e in doc["entities"] if e["id"] == "storefront")
    # every entity is CITABLE: the operator can check the claim.
    assert store["evidence"], "an entity with no citation is a guess"
    assert all(c["path"].startswith("storefront/") for c in store["evidence"])
    assert all(c["sha256"] for c in store["evidence"])
    assert store["source_id"] == source["id"]


def test_no_file_body_is_ever_carried_into_the_estate(tmp_path):
    src = _make_source(tmp_path)
    (src / "storefront" / "SECRETS-LOOKING.md").write_text(
        "distinctive-body-token-xyz\n", encoding="utf-8")
    root = tmp_path / "root"
    _ratified_journey(root, src)
    doc = estate.derive_estate(root, answers=ANSWERS, now="2026-07-26T00:01:00Z")
    assert "distinctive-body-token-xyz" not in yaml.safe_dump(doc)


def test_derivation_performs_no_new_read_of_the_source(tmp_path):
    """THE structural claim: the estate re-derives from ratified artifacts, so
    it must produce the same document with the granted folder GONE. If this
    ever fails, something in the derivation path is opening the source — which
    is a read the Captain did not ratify at that moment."""
    src = _make_source(tmp_path)
    root = tmp_path / "root"
    _ratified_journey(root, src)
    before = estate.derive_estate(root, answers=ANSWERS, now="2026-07-26T00:01:00Z")
    shutil.rmtree(src)
    after = estate.derive_estate(root, answers=ANSWERS, now="2026-07-26T00:01:00Z")
    assert after == before
    assert after["sources"] and after["entities"]


def test_unratified_or_unbound_window_is_an_honest_empty(tmp_path):
    src = _make_source(tmp_path)
    root = tmp_path / "root"
    # proposed but NOT ratified: the charter is pending, so nothing was read.
    journey.act({
        "action": "propose_window", "action_id": "p1", "surface": "test",
        "source": str(src), "purpose": "Find one release risk.",
        "relationship_destination": "reversible", "ownership": "self",
        "authority_basis": "synthetic fixture folder created by this test",
    }, root, now="2026-07-26T00:00:00Z")
    doc = estate.derive_estate(root, answers=ANSWERS, now="2026-07-26T00:01:00Z")
    assert doc["sources"] == [] and doc["entities"] == []
    # ... and an honest empty is still a legitimate, USABLE artifact: it
    # records that discovery RAN, which is what the lanes gate asks.
    assert estate.estate_is_usable(doc, "acme-hq")[0] is True


def test_manifest_bound_to_a_different_charter_yields_no_source(tmp_path):
    src = _make_source(tmp_path)
    root = tmp_path / "root"
    _ratified_journey(root, src)
    mpath = root / estate.JOURNEY_DIR_REL / "first-window-manifest.json"
    import json
    manifest = json.loads(mpath.read_text())
    manifest["charter_hash"] = "0" * 64          # a superseded charter's read
    mpath.write_text(json.dumps(manifest), encoding="utf-8")
    doc = estate.derive_estate(root, answers=ANSWERS, now="2026-07-26T00:01:00Z")
    assert doc["sources"] == [], "a read not bound to the ratified charter counts for nothing"


def test_lone_root_marker_yields_the_root_but_children_replace_it(tmp_path):
    solo_root = tmp_path / "solo"
    src = _make_source(tmp_path / "solo-src", children=False)
    _ratified_journey(solo_root, src)
    doc = estate.derive_estate(solo_root, answers=ANSWERS, now="2026-07-26T00:01:00Z")
    assert [e["relative_path"] for e in doc["entities"]] == ["."]

    multi_root = tmp_path / "multi"
    src2 = _make_source(tmp_path / "multi-src", children=True)
    _ratified_journey(multi_root, src2)
    doc2 = estate.derive_estate(multi_root, answers=ANSWERS, now="2026-07-26T00:01:00Z")
    assert "." not in [e["relative_path"] for e in doc2["entities"]]


# ---------------------------------------------------------------------------
# the usability gate — what `lanes: []` is allowed to ride
# ---------------------------------------------------------------------------
def _valid_doc(**over) -> dict:
    doc = {"schema": estate.SCHEMA, "deployment": "acme-hq",
           "derived_at": "2026-07-26T00:00:00Z", "sources": [], "entities": []}
    doc.update(over)
    return doc


@pytest.mark.parametrize("doc,ok", [
    ({}, False),                                          # nobody ever looked
    (_valid_doc(schema="cabinet.something-else/v1"), False),
    (_valid_doc(derived_at=""), False),
    (_valid_doc(sources="not-a-list"), False),
    (_valid_doc(entities="not-a-list"), False),
    (_valid_doc(deployment="other-cabinet"), False),      # a FOREIGN artifact
    (_valid_doc(), True),                                 # empty but real
])
def test_usability_gate_arms(doc, ok):
    assert estate.estate_is_usable(doc, "acme-hq")[0] is ok


def test_usability_gate_reason_is_never_empty_on_refusal():
    for doc in ({}, _valid_doc(deployment="other")):
        usable, reason = estate.estate_is_usable(doc, "acme-hq")
        assert usable is False and reason.strip()


# ---------------------------------------------------------------------------
# proposed lanes — structural read-only for anything not operator-owned
# ---------------------------------------------------------------------------
def _doc_with_entity(ownership: str) -> dict:
    return _valid_doc(
        sources=[{"id": "first-window", "ownership": ownership}],
        entities=[{"id": "storefront", "name": "storefront",
                   "source_id": "first-window", "relative_path": "storefront",
                   "evidence": [{"path": "storefront/README.md", "sha256": "ab"}]}],
    )


@pytest.mark.parametrize("ownership,write_capable", [
    ("unclassified", False),   # legacy: a journey older than the ingest ceiling
    ("employer", False), ("third_party", False), ("self", True),
])
def test_only_self_owned_sources_propose_write_capable_lanes(ownership, write_capable):
    rows = estate.proposed_lanes(_doc_with_entity(ownership))
    assert len(rows) == 1
    assert rows[0]["write_capable_proposal"] is write_capable
    # The proposal itself is read-only regardless — ratification is where the
    # operator adds repos/boards, after declaring ownership.
    assert rows[0]["task_system"] == "none" and rows[0]["repos"] == []
    assert rows[0]["derived_from"]["evidence"], "a proposed lane must cite why"


def test_proposed_lanes_refuse_unslugged_and_reserved_ids():
    doc = _valid_doc(
        sources=[{"id": "first-window", "ownership": "self"}],
        entities=[{"id": "cos", "name": "cos", "source_id": "first-window"},
                  {"id": "Not A Slug", "name": "x", "source_id": "first-window"},
                  {"id": "ok-lane", "name": "ok", "source_id": "first-window"}],
    )
    assert [r["slug"] for r in estate.proposed_lanes(doc)] == ["ok-lane"]


def test_lanes_proposed_file_is_inert_and_teaches_ratification(tmp_path):
    res = estate.write_lanes_proposed(_doc_with_entity("self"), tmp_path,
                                      now="2026-07-26T00:00:00Z")
    path = Path(res["path"])
    assert path.name == "lanes-proposed.yml"
    # NOT the answers file and NOT outcomes.yml — nothing reads this to act.
    assert not (tmp_path / "instance/config/outcomes.yml").exists()
    assert not (tmp_path / "instance/config/cabinet-init.answers.yml").exists()
    text = path.read_text()
    assert "cabinet-init.answers.yml" in text        # says how to ratify
    doc = yaml.safe_load(text)
    assert doc["captain_ratified"] is False
    assert doc["schema"] == estate.LANES_PROPOSED_SCHEMA


# ---------------------------------------------------------------------------
# altitude — tolerant read here, loud refusal in the generator
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("answers,expected", [
    (None, None),
    ({}, None),
    ({"mission": None}, None),
    ({"mission": "not-a-dict"}, None),
    ({"mission": {}}, None),
    ({"mission": {"altitude": "typo-rung"}}, None),
    ({"mission": {"altitude": "Contributor"}}, "contributor"),
    ({"mission": {"altitude": "company"}}, "company"),
])
def test_altitude_of_is_tolerant(answers, expected):
    assert estate.altitude_of(answers) == expected


def test_write_then_load_roundtrips(tmp_path):
    doc = _doc_with_entity("self")
    estate.write_estate(doc, tmp_path)
    assert estate.load_estate(tmp_path) == doc


def test_load_estate_is_an_honest_empty_on_garbage(tmp_path):
    path = tmp_path / estate.ESTATE_REL
    path.parent.mkdir(parents=True)
    path.write_text("::not: yaml: [\n", encoding="utf-8")
    assert estate.load_estate(tmp_path) == {}


def test_an_employer_source_is_carried_and_proposes_read_only(tmp_path):
    """End to end through the REAL journey: a source the operator declares as
    their employer's rides the charter into the estate, and the lane derived
    from it is proposed read-only — the decision is
    framework.authority.ownership.writes_permitted, not a local `== self`."""
    src = _make_source(tmp_path)
    root = tmp_path / "root"
    _ratified_journey(root, src, ownership="employer")
    doc = estate.derive_estate(root, answers=ANSWERS, now="2026-07-26T00:01:00Z")
    assert doc["sources"][0]["ownership"] == "employer"
    rows = estate.proposed_lanes(doc)
    assert rows and all(r["write_capable_proposal"] is False for r in rows)
    assert all(r["task_system"] == "none" and r["repos"] == [] for r in rows)
