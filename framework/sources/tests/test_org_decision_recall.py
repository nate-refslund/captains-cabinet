"""W7 — recall in the decision path for the ORG shape (2026-07-09).

The CG-2 gather seam (run_action_lane._source_parts, dark behind
``CABINET_GATHER_VIA_SOURCE=1``) drives ALL memory recall off
``open_commitments()`` rows. ``OrgSource`` used to answer the honest empty
there, so an org deployment ran the decision path MEMORY-BLIND even though
``search()`` over ``cabinet_memory`` was live — the memory-audit P0
(recall never reaches the proposer; ``recall_drops`` frozen at 0 because
recall never RUNS).

These tests pin the fix — the org's open commitments ARE its
Captain-ratified ACTIVE outcomes (real config, read-only) — and the shadow
parity of the seam end-to-end: outcomes → OPEN COMMITMENT blocks → topic-
anchored ``search()`` → content_ts-fenced CONTEXT blocks, while flag-OFF
stays byte-identical to the extracted vault walk (pinned by
test_gather_via_source; re-asserted here for the OrgSource binding).
"""
from __future__ import annotations

import datetime as dt

import pytest

import framework.sources as fsources
from framework.acting import run_action_lane as ral
from framework.sources.org import OrgSource, _lane_from_outcome_id

AS_OF = dt.datetime(2026, 7, 9, 12, 0, 0, tzinfo=dt.timezone.utc)

OUTCOMES_YML = """\
outcomes:
  - id: outcome-polads-001
    name: "PolAds v1.0 staging closeout and production release"
    status: active
  - id: outcome-polads-005
    name: "Draft outcome that must not surface"
    status: draft
  - id: outcome-stephie-001
    name: "Achieved outcome that must not surface"
    status: achieved
  - id: outcome-system-self-003
    name: "Evidence engine verdict supply"
    lane: system-self
    status: active
"""


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.delenv("CABINET_GATHER_VIA_SOURCE", raising=False)
    monkeypatch.delenv("CABINET_ORG_MEMORY_TYPES", raising=False)
    monkeypatch.delenv("CABINET_ORG_SEARCH_LIMIT", raising=False)
    monkeypatch.delenv("CABINET_ORG_MIN_SCORE", raising=False)


@pytest.fixture()
def org_root(tmp_path, monkeypatch):
    (tmp_path / "instance/config").mkdir(parents=True)
    (tmp_path / "instance/config/outcomes.yml").write_text(OUTCOMES_YML)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("NEON_CONNECTION_STRING", "postgres://dummy.invalid/db")
    return tmp_path


class TestOpenCommitments:
    def test_active_outcomes_surface_as_owed_to_captain(self, org_root):
        rows = OrgSource().open_commitments("owed_to_captain")
        ids = [r["id"] for r in rows]
        assert ids == ["outcome-polads-001", "outcome-system-self-003"]
        r = rows[0]
        assert r["person"] == "polads" and r["slug"] == "polads"
        assert r["text"].startswith("PolAds v1.0")
        assert r["path"] == "instance/config/outcomes.yml#outcome-polads-001"
        assert r["direction"] == "owed_to_captain"
        # explicit lane field wins over id-derived lane
        assert rows[1]["person"] == "system-self"

    def test_owed_by_captain_stays_honest_empty(self, org_root):
        assert OrgSource().open_commitments("owed_by_captain") == []

    def test_missing_file_fails_closed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        assert OrgSource().open_commitments("owed_to_captain") == []

    def test_malformed_yaml_fails_closed(self, org_root):
        (org_root / "instance/config/outcomes.yml").write_text("{: not yaml [")
        assert OrgSource().open_commitments("owed_to_captain") == []

    def test_capped_at_eight(self, org_root):
        body = "outcomes:\n" + "".join(
            f"  - id: outcome-l{i}-00{i}\n    name: 'O{i}'\n    status: active\n"
            for i in range(12))
        (org_root / "instance/config/outcomes.yml").write_text(body)
        assert len(OrgSource().open_commitments("owed_to_captain")) == 8

    def test_lane_derivation(self):
        assert _lane_from_outcome_id("outcome-polads-001") == "polads"
        assert _lane_from_outcome_id("outcome-system-self-002") == "system-self"
        assert _lane_from_outcome_id("weird-shape") == ""


# hybrid 8-col memory_search TSV: one fenceable pre-as_of hit, one future
# leak, one clockless row — only the first may reach the proposer.
_TSV = (
    "captain_decision\tcos\t2026-07-01 09:30\t0.912\t0.870\tcaptain"
    "\tDecided: PolAds staging CI fix ships via PR 419\tdec-42\n"
    "captain_decision\tcos\t2026-08-01 09:30\t0.9\t0.9\tcaptain"
    "\tFUTURE leak decision\tdec-future\n"
    "working_note\tcto\tundated\t0.8\t0.8\tderived"
    "\tclockless note must be excluded\tnote-x\n"
)


class TestSeamShadowParity:
    def test_flag_on_org_source_puts_recall_in_the_decision_path(
            self, org_root, monkeypatch, tmp_path):
        queries = []

        def run_search(query, types_csv, limit, min_score):
            queries.append(query)
            return _TSV

        src = OrgSource(run_search=run_search)
        monkeypatch.setattr(fsources, "get_source", lambda: src)
        monkeypatch.setenv("CABINET_GATHER_VIA_SOURCE", "1")
        monkeypatch.setattr(ral, "product_brain_dir", lambda: "")

        out = ral.gather_signals(AS_OF, vault=tmp_path / "no-vault")

        # the org's own open work is the commitments section
        assert ("--- OPEN COMMITMENT ref=instance/config/outcomes.yml"
                "#outcome-polads-001 ---") in out
        # …and it seeded topic-anchored cabinet_memory recall (CONTEXT)
        assert "--- CONTEXT ref=dec-42 ---" in out
        assert "PolAds staging CI fix" in out
        # the content_ts fence held: future + clockless rows never surface
        assert "FUTURE leak decision" not in out
        assert "clockless note" not in out
        # search was topic-anchored (outcome text travels in the query)
        assert queries and "PolAds v1.0" in queries[0]

    def test_flag_off_org_binding_never_reaches_the_seam(
            self, org_root, monkeypatch, tmp_path):
        def _boom():
            raise AssertionError("get_source must not be called flag-off")
        monkeypatch.setattr(fsources, "get_source", _boom)
        monkeypatch.setattr(ral, "product_brain_dir", lambda: "")
        ral.gather_signals(AS_OF, vault=tmp_path / "no-vault")  # no raise
