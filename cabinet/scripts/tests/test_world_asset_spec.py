"""Tests for cabinet/scripts/world-asset-spec.py (spec-gen).

Golden mini grammar fixtures (fixtures/world-asset-spec/) exercise the REAL
schemas: the mini ladders file passes the real world-growth-validate.py.
Pinned here: stable entry ids, per-ladder era dedupe, mode-aware rung
expansion (tier/flag vs count), literal-'none' rung skip, covered_by
suppression, staged flags, counts consistency, byte-identical determinism,
validator refusal on malformed ladders, unknown-key warnings vs
missing-required errors, era-filter semantics, markdown structure.

No network, no repo-state writes — everything under tmp_path.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "world-asset-spec.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "world-asset-spec"

_spec = importlib.util.spec_from_file_location("world_asset_spec", SCRIPT)
was = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(was)

SUPPLEMENT = """\
schema: cabinet.world.asset-worklist-supplement/v1
version: 1
districts:
  ladders: {flagpole: village_core, outbuildings: law_observatory_fields, berths: harbor}
  morphology: {memory_store: village_core, hats_earned: ui_props}
coverage: {memory_store: outbuildings}
meanings: {flagpole: "Mini flagpole."}
size_overrides: {ladder.outbuildings: 96x112}
animated: {ladder.flagpole: 2}
"""


def run(tmp_path, eras=None, supplement_text=SUPPLEMENT, ladders=None,
        morphology=None, show=None, argv_extra=None):
    supp = tmp_path / "supp.yml"
    supp.write_text(supplement_text)
    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"
    argv = [
        "--ladders", str(ladders or FIXTURES / "mini-ladders.yml"),
        "--morphology", str(morphology or FIXTURES / "mini-morphology.yml"),
        "--show-grammar", str(show or FIXTURES / "mini-show-grammar.yml"),
        "--supplement", str(supp),
        "--out-json", str(out_json),
        "--out-md", str(out_md),
    ]
    if eras:
        argv += ["--eras", eras]
    if argv_extra:
        argv += argv_extra
    rc = was.main(argv)
    return rc, out_json, out_md


def entries_by_id(out_json: Path) -> dict:
    doc = json.loads(out_json.read_text())
    return doc, {e["id"]: e for e in doc["entries"]}


# ── pre-flight truth gate ───────────────────────────────────────────────────

def test_preflight_refuses_malformed_ladders(tmp_path, capsys):
    bad = tmp_path / "bad-ladders.yml"
    bad.write_text((FIXTURES / "mini-ladders.yml").read_text()
                   .replace("commits_since_genesis", "made_up_metric"))
    rc, out_json, out_md = run(tmp_path, ladders=bad)
    assert rc == 2
    assert not out_json.exists() and not out_md.exists()
    err = capsys.readouterr().err
    assert "REFUSED" in err and "made_up_metric" in err


# ── expansion law ───────────────────────────────────────────────────────────

def test_expansion_ids_modes_and_flags(tmp_path, capsys):
    rc, out_json, out_md = run(tmp_path)
    assert rc == 0
    doc, by_id = entries_by_id(out_json)
    assert doc["schema"] == "cabinet.world.asset-worklist/v1"

    # era dedupe: pennant_cloth serves camp+hamlet as ONE family
    fam = by_id["ladder.flagpole.pennant_cloth.bare_pole"]
    assert fam["eras"] == ["camp", "hamlet"]
    # flag mode: 3 families x 2 rungs = 6 flagpole entries
    assert sum(1 for i in by_id if i.startswith("ladder.flagpole.")) == 6

    # literal 'none' rung skipped; kept rungs expand per family (4 x 2 = 8)
    assert not any(i.endswith(".none") for i in by_id)
    assert "ladder.outbuildings.leanto.coop" in by_id
    assert sum(1 for i in by_id if i.startswith("ladder.outbuildings.")) == 8

    # count mode: one entry per family, no rung component, rendered-Nx note
    berth = by_id["ladder.berths.mooring_post"]
    assert berth["mode"] == "count" and berth["rung_state"] is None
    assert any("rendered up to 2x" in n for n in berth["notes"])
    assert sum(1 for i in by_id if i.startswith("ladder.berths.")) == 4

    # covered_by suppression (test supplement covers memory_store via outbuildings)
    mem = by_id["morph.memory_store.day0"]
    assert mem["covered_by"] == "ladder.outbuildings" and mem["day0"] is False
    assert any("no new art" in n for n in mem["notes"])

    # staged flags: dark morphology + staged fauna (priority), landed fauna not
    assert by_id["morph.hats_earned.day0"]["staged"] is True
    cat = by_id["anim.fauna.cat"]
    assert cat["staged"] is True and any("PRIORITY" in n for n in cat["notes"])
    assert by_id["anim.fauna.dog"]["staged"] is False

    # meta axis morphology entry excluded
    assert "morph.era_vocabulary.day0" not in by_id

    # day-0 flags: rung-0 camp families only; officers yes, apprentices no
    assert by_id["ladder.flagpole.pennant_cloth.bare_pole"]["day0"] is True
    assert by_id["ladder.flagpole.flag.bare_pole"]["day0"] is False
    assert by_id["ladder.flagpole.pennant_cloth.pennant"]["day0"] is False
    assert by_id["anim.actor.officer_work"]["day0"] is True
    assert by_id["anim.actor.apprentice_work"]["day0"] is False

    # voyage cross-ref: no new art, covered by the harbor_boat ladder
    voyage = by_id["anim.voyage.harbor_boat"]
    assert voyage["covered_by"] == "ladder.harbor_boat" and voyage["size"] is None

    # supplement hints: size override + animated frames ride prefix match
    assert by_id["ladder.outbuildings.leanto.coop"]["size"] == {"w": 96, "h": 112}
    assert fam["animated"] is True and fam["frames"] == 2

    # fog carries no sprite art — section note, not an entry
    assert any("fog" in n for n in doc["section_notes"]["animation"])
    assert "anim.weather.rain_strip" in by_id
    assert not any(i.startswith("anim.weather.fog") for i in by_id)

    # sources recorded as sha256 over all four inputs
    assert len(doc["sources"]) == 4
    assert all(len(v) == 64 for v in doc["sources"].values())


def test_counts_consistency(tmp_path):
    rc, out_json, _ = run(tmp_path)
    assert rc == 0
    doc, by_id = entries_by_id(out_json)
    c = doc["counts"]
    assert c["total"] == len(doc["entries"]) == 44
    assert c["ladder"] == 18 and c["morphology"] == 2 and c["animation"] == 24
    assert c["ladder"] + c["morphology"] + c["animation"] + c["extra"] == c["total"]
    assert c["covered_no_new_art"] == sum(1 for e in doc["entries"] if e["covered_by"]) == 2
    assert c["new_art"] == c["total"] - c["covered_no_new_art"]
    assert c["day0"] == sum(1 for e in doc["entries"] if e["day0"])
    assert c["by_district"] == {"village_core": 7, "harbor": 4,
                                "law_observatory_fields": 8, "ui_props": 1}


# ── determinism ─────────────────────────────────────────────────────────────

def test_determinism_byte_identical(tmp_path):
    rc, out_json, out_md = run(tmp_path)
    assert rc == 0
    first = (out_json.read_bytes(), out_md.read_bytes())
    rc2, out_json2, out_md2 = run(tmp_path)
    assert rc2 == 0
    assert (out_json2.read_bytes(), out_md2.read_bytes()) == first


# ── schema drift honesty ────────────────────────────────────────────────────

def test_unknown_key_warns_generation_proceeds(tmp_path, capsys):
    drifted = tmp_path / "drifted-ladders.yml"
    drifted.write_text((FIXTURES / "mini-ladders.yml").read_text()
                       .replace("    mode: flag\n", "    mode: flag\n    bogus_knob: 7\n"))
    rc, out_json, _ = run(tmp_path, ladders=drifted)
    assert rc == 0 and out_json.exists()
    err = capsys.readouterr().err
    assert "WARN" in err and "bogus_knob" in err


def test_missing_required_key_errors(tmp_path, capsys):
    # vocab is optional to the growth validator but REQUIRED by spec-gen
    # (no vocab = no art families) — missing required must be an error.
    broken = tmp_path / "novocab-ladders.yml"
    text = (FIXTURES / "mini-ladders.yml").read_text()
    text = text.replace(
        "    vocab: {camp: pennant_cloth, hamlet: pennant_cloth, town: flag, beyond_bay: crested_flag}\n",
        "")
    broken.write_text(text)
    rc, out_json, _ = run(tmp_path, ladders=broken)
    assert rc == 2 and not out_json.exists()
    assert "vocab" in capsys.readouterr().err


def test_unmapped_district_warns_and_files_unassigned(tmp_path, capsys):
    supp = SUPPLEMENT.replace(", berths: harbor", "")
    rc, out_json, out_md = run(tmp_path, supplement_text=supp)
    assert rc == 0
    _, by_id = entries_by_id(out_json)
    assert by_id["ladder.berths.mooring_post"]["district"] == "unassigned"
    assert "no district mapping" in capsys.readouterr().err
    assert "## Unassigned" in out_md.read_text()


def test_supplement_untruthful_coverage_refused(tmp_path, capsys):
    supp = SUPPLEMENT.replace("coverage: {memory_store: outbuildings}",
                              "coverage: {memory_store: no_such_ladder}")
    rc, _, _ = run(tmp_path, supplement_text=supp)
    assert rc == 2
    assert "no_such_ladder" in capsys.readouterr().err


def test_supplement_off_grid_size_refused(tmp_path, capsys):
    supp = SUPPLEMENT.replace("96x112", "33x32")
    rc, _, _ = run(tmp_path, supplement_text=supp)
    assert rc == 2
    assert "33x32" in capsys.readouterr().err


# ── era filter (the per-phase artist checklist) ─────────────────────────────

def test_era_filter_town_only(tmp_path):
    rc, out_json, _ = run(tmp_path, eras="town")
    assert rc == 0
    doc, by_id = entries_by_id(out_json)
    assert doc["era_filter"] == ["town"]
    assert doc["counts"]["total"] == 5
    assert all("town" in e["eras"] for e in doc["entries"])
    assert doc["counts"]["morphology"] == 0 and doc["counts"]["animation"] == 0


def test_era_filter_camp_carries_agnostic_sections(tmp_path):
    rc, out_json, _ = run(tmp_path, eras="camp")
    assert rc == 0
    doc, by_id = entries_by_id(out_json)
    assert doc["counts"]["ladder"] == 5
    assert doc["counts"]["morphology"] == 2 and doc["counts"]["animation"] == 24
    assert "morph.hats_earned.day0" in by_id and "anim.fauna.dog" in by_id


def test_era_filter_unknown_era_refused(tmp_path, capsys):
    rc, _, _ = run(tmp_path, eras="renaissance")
    assert rc == 2
    assert "renaissance" in capsys.readouterr().err


def test_era_filter_refuses_canonical_default_paths(tmp_path, capsys):
    supp = tmp_path / "supp.yml"
    supp.write_text(SUPPLEMENT)
    rc = was.main([
        "--ladders", str(FIXTURES / "mini-ladders.yml"),
        "--morphology", str(FIXTURES / "mini-morphology.yml"),
        "--show-grammar", str(FIXTURES / "mini-show-grammar.yml"),
        "--supplement", str(supp),
        "--eras", "town",
    ])
    assert rc == 2
    assert "canonical" in capsys.readouterr().err


# ── markdown checklist ──────────────────────────────────────────────────────

def test_markdown_phase_structure(tmp_path):
    rc, out_json, out_md = run(tmp_path)
    assert rc == 0
    doc = json.loads(out_json.read_text())
    md = out_md.read_text()
    assert "GENERATED by `cabinet/scripts/world-asset-spec.py`" in md
    # phase headings in the art brief's order (only populated phases render)
    pos_village = md.index("## Phase 1 — Village core")
    pos_harbor = md.index("## Phase 2 — Harbor")
    pos_law = md.index("## Phase 3 — Law / Observatory / Fields")
    pos_ui = md.index("## Phase 5 — UI & props")
    pos_anim = md.index("## Animation families (separate section)")
    assert pos_village < pos_harbor < pos_law < pos_ui < pos_anim
    # every entry renders exactly one checkbox row
    assert md.count("- [ ] ") == doc["counts"]["total"]
    # no-art weather states surface as a note in the animation section
    assert "> NOTE:" in md and "fog" in md
    # tags render
    assert "[STAGED — priority]" in md and "[covered → ladder.outbuildings]" in md
