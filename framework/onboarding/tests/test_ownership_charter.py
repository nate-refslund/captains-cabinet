"""The ownership ceiling on the real First Window journey.

These arms drive `journey.act` rather than a reimplementation, so they bind the
product code path. Every one of them fails against pre-change code: before
2026-07-27 `propose_window` accepted a source with no ownership field at all,
the Charter had no ownership block, the scanner counted every sensitivity
refusal in one bucket, and no record of a completed read survived a purge.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from framework.onboarding import journey

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def estate(tmp_path: Path, name: str) -> Path:
    target = tmp_path / "sources" / name
    shutil.copytree(FIXTURES / name, target)
    return target


def propose(root: Path, source: Path, *, ownership="self", basis="my own machine", **extra):
    request = {
        "action": "propose_window",
        "action_id": extra.pop("action_id", "own-propose-1"),
        "surface": "test",
        "source": str(source),
        "purpose": "Find one thing that will bite me.",
        "relationship_destination": "reversible",
        "ownership": ownership,
        "authority_basis": basis,
    }
    request.update(extra)
    return journey.act(request, root, now="2026-07-27T10:00:00Z")


def ratify(root: Path, proposed: dict, *, action_id="own-ratify-1"):
    return journey.act(
        {
            "action": "ratify_charter",
            "action_id": action_id,
            "surface": "test",
            "expected_revision": proposed["state"]["revision"],
            "charter_hash": proposed["state"]["charter"]["hash"],
        },
        root,
        now="2026-07-27T10:00:01Z",
    )


class TestRefuseNeverDefault:
    @pytest.mark.parametrize("ownership", [None, "", "unknown", "probably mine"])
    def test_an_unclassifiable_source_is_refused_before_anything_is_read(
        self, tmp_path, ownership, monkeypatch
    ):
        source = estate(tmp_path, "software-product")

        def no_scan(*_a, **_k):
            raise AssertionError("nothing may be read before the source is classified")

        monkeypatch.setattr(journey, "_scan_source", no_scan)
        with pytest.raises(journey.JourneyError) as exc:
            propose(tmp_path, source, ownership=ownership)
        assert exc.value.code in {"ownership_unclassified", "ownership_class_unknown"}
        assert journey.snapshot(tmp_path)["state"]["stage"] == "welcome"

    def test_a_missing_authority_basis_is_refused(self, tmp_path):
        source = estate(tmp_path, "software-product")
        with pytest.raises(journey.JourneyError) as exc:
            propose(tmp_path, source, basis="")
        assert exc.value.code == "authority_basis_required"

    def test_the_refusal_is_recorded_as_an_event_not_a_silent_skip(self, tmp_path):
        source = estate(tmp_path, "software-product")
        with pytest.raises(journey.JourneyError):
            propose(tmp_path, source, ownership=None)
        events = journey._read_events(tmp_path)
        assert all(e.get("action") != "propose_window" for e in events)
        assert journey.snapshot(tmp_path)["state"]["source"] is None


class TestCharterCarriesOwnership:
    @pytest.mark.parametrize("ownership,adapters,egress", [
        ("self", "allowed", "allow"),
        ("employer", "refused", "record_and_allow"),
        ("third_party", "refused", "per_item_approval"),
    ])
    def test_permission_block_is_derived_from_the_class(
        self, tmp_path, ownership, adapters, egress
    ):
        source = estate(tmp_path, "software-product")
        payload = propose(tmp_path, source, ownership=ownership)["state"]["charter"]["payload"]
        assert payload["source"]["ownership"] == ownership
        assert payload["permission"]["write_capable_adapters"] == adapters
        assert payload["permission"]["egress"] == egress
        assert payload["permission"]["writes_to_source"] is False

    def test_ownership_is_inside_the_hash_the_captain_approves(self, tmp_path):
        source = estate(tmp_path, "software-product")
        mine = propose(tmp_path / "a", source, ownership="self")["state"]["charter"]["hash"]
        theirs = propose(
            tmp_path / "b", source, ownership="employer", basis="my own machine"
        )["state"]["charter"]["hash"]
        assert mine != theirs, (
            "a charter approved for the operator's own folder must not be "
            "replayable against an employer's under the same fingerprint"
        )

    def test_the_charter_states_what_the_framework_cannot_enforce(self, tmp_path):
        source = estate(tmp_path, "software-product")
        payload = propose(tmp_path, source)["state"]["charter"]["payload"]
        assert payload["attestation"]["verified_by_framework"] is False
        assert "cannot verify" in payload["attestation_limit"]

    def test_the_approval_card_shows_the_class_back_in_plain_words(self, tmp_path):
        source = estate(tmp_path, "software-product")
        card = propose(tmp_path, source, ownership="employer", basis="my seat")["card"]
        assert "my employer's" in card["body"]
        assert "my seat" in card["body"]


class TestSensitivityClassesRefuseByClass:
    def _estate_with_sensitive_names(self, tmp_path: Path) -> Path:
        source = tmp_path / "sources" / "mixed"
        source.mkdir(parents=True)
        (source / "README.md").write_text("# Ordinary\nnothing to see\n", encoding="utf-8")
        (source / "payroll-2026.csv").write_text("name,amount\na,1\n", encoding="utf-8")
        (source / "employee-records.md").write_text("# people\n", encoding="utf-8")
        (source / "customer-export.csv").write_text("email\na@b.c\n", encoding="utf-8")
        (source / "subpoena-notes.md").write_text("# legal\n", encoding="utf-8")
        (source / "due-diligence.md").write_text("# deal\n", encoding="utf-8")
        (source / "credentials.txt").write_text("token\n", encoding="utf-8")
        return source

    def test_each_class_is_refused_and_counted_under_its_own_name(self, tmp_path):
        source = self._estate_with_sensitive_names(tmp_path)
        proposed = propose(tmp_path, source)
        ratify(tmp_path, proposed)
        manifest = json.loads(
            (tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).read_text(encoding="utf-8")
        )
        refused = manifest["scan_statistics"]["refused_by_sensitivity_class"]
        assert refused == {
            "credentials": 1, "personnel": 1, "compensation": 1,
            "customer_pii": 1, "legal": 1, "corporate_finance": 1,
        }
        assert manifest["scan_statistics"]["refusals_total"] == 6
        assert [f["path"] for f in manifest["files"]] == ["README.md"]

    def test_an_untouched_class_reads_as_zero_not_as_absent(self, tmp_path):
        """A missing key is indistinguishable from "never checked"."""
        source = estate(tmp_path, "software-product")
        proposed = propose(tmp_path, source)
        ratify(tmp_path, proposed)
        manifest = json.loads(
            (tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).read_text(encoding="utf-8")
        )
        refused = manifest["scan_statistics"]["refused_by_sensitivity_class"]
        assert set(refused) == set(journey.SENSITIVITY_CLASSES)
        assert sum(refused.values()) == 0

    def test_the_charter_names_the_classes_before_the_read(self, tmp_path):
        source = estate(tmp_path, "software-product")
        payload = propose(tmp_path, source)["state"]["charter"]["payload"]
        assert payload["exclusions"]["sensitivity_classes"] == list(journey.SENSITIVITY_CLASSES)


class TestAccessRecordSurvivesTheRead:
    def test_the_record_is_written_at_the_read_with_class_basis_and_refusals(self, tmp_path):
        source = estate(tmp_path, "enterprise-employee")
        proposed = propose(
            tmp_path, source, ownership="employer", basis="read access granted to my seat"
        )
        ratify(tmp_path, proposed)
        records = sorted((tmp_path / journey.ACCESS_RECORDS_REL).glob("access-*.json"))
        assert len(records) == 1
        record = json.loads(records[0].read_text(encoding="utf-8"))
        assert record["ownership"] == "employer"
        assert record["authority_basis"] == "read access granted to my seat"
        assert record["source_root"] == str(source.resolve())
        assert record["charter_hash"] == proposed["state"]["charter"]["hash"]
        assert record["entry_count"] > 0
        assert set(record["refusals"]) == set(journey.SENSITIVITY_CLASSES)
        assert record["purge_receipt"] is None

    def test_the_record_survives_a_purge_and_carries_its_receipt(self, tmp_path):
        source = estate(tmp_path, "software-product")
        proposed = propose(tmp_path, source)
        ratify(tmp_path, proposed)
        journey.act(
            {
                "action": "purge",
                "action_id": "own-purge-1",
                "surface": "test",
                "confirmation": "PURGE",
            },
            tmp_path,
            now="2026-07-27T11:00:00Z",
        )
        assert not (tmp_path / journey.DATA_REL / journey.CHARTER_NAME).exists()
        assert not (tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).exists()
        records = sorted((tmp_path / journey.ACCESS_RECORDS_REL).glob("access-*.json"))
        assert len(records) == 1
        record = json.loads(records[0].read_text(encoding="utf-8"))
        assert record["purge_receipt"] == "own-purge-1"
        assert record["ownership"] == "self"
        assert record["entry_count"] > 0

    def test_the_purge_still_removes_every_source_path(self, tmp_path):
        """Both promises are kept: the trail survives, the path does not."""
        source = estate(tmp_path, "software-product")
        proposed = propose(tmp_path, source)
        ratify(tmp_path, proposed)
        journey.act(
            {
                "action": "purge",
                "action_id": "own-purge-2",
                "surface": "test",
                "confirmation": "PURGE",
            },
            tmp_path,
            now="2026-07-27T11:00:00Z",
        )
        record_path = next((tmp_path / journey.ACCESS_RECORDS_REL).glob("access-*.json"))
        record = json.loads(record_path.read_text(encoding="utf-8"))
        assert record["source_root"] is None
        assert record["source_root_redacted_by_purge"] is True
        assert len(record["source_root_sha256"]) == 64
        assert str(source.resolve()) not in record_path.read_text(encoding="utf-8")

    def test_the_record_holds_no_file_contents(self, tmp_path):
        source = estate(tmp_path, "software-product")
        (source / "canary.md").write_text("UNIQUE-CANARY-STRING-9d2f\n", encoding="utf-8")
        proposed = propose(tmp_path, source)
        ratify(tmp_path, proposed)
        blob = "".join(
            p.read_text(encoding="utf-8")
            for p in (tmp_path / journey.ACCESS_RECORDS_REL).glob("access-*.json")
        )
        assert "UNIQUE-CANARY-STRING-9d2f" not in blob
        assert "canary.md" not in blob


class TestEgressGateOnTheOneCard:
    def _dividend_card(self, tmp_path: Path, ownership: str) -> dict:
        source = estate(tmp_path, "software-product")
        proposed = propose(tmp_path, source, ownership=ownership, basis="stated basis")
        return ratify(tmp_path, proposed)["card"]

    def test_the_operators_own_content_leaves_unchanged(self, tmp_path):
        card = self._dividend_card(tmp_path, "self")
        assert card["egress"]["disposition"] == "allow"
        assert card["egress"]["withheld"] == 0
        assert all("withheld_reason" not in c for c in card["evidence"])

    def test_employer_content_leaves_with_the_disposition_recorded(self, tmp_path):
        card = self._dividend_card(tmp_path, "employer")
        assert card["egress"]["disposition"] == "record_and_allow"
        assert card["egress"]["withheld"] == 0
        assert card["evidence"] and all(c["excerpt"] for c in card["evidence"])

    def test_third_party_words_are_withheld_while_the_citation_stays_visible(self, tmp_path):
        card = self._dividend_card(tmp_path, "third_party")
        assert card["egress"]["disposition"] == "per_item_approval"
        assert card["egress"]["withheld"] == len(card["evidence"]) > 0
        for citation in card["evidence"]:
            assert citation["excerpt"] == journey.WITHHELD_EXCERPT
            assert citation["withheld_reason"] == "egress_refused_without_per_item_approval"
            assert citation["path"] and citation["line"]
        assert "not the operator's" not in card["title"]
        assert "someone else's" in card["body"]

    def test_a_pre_ownership_journey_is_treated_as_the_strictest_case(self, tmp_path):
        """Degenerate end: a state with no class must not render as `allow`."""
        source = estate(tmp_path, "software-product")
        proposed = propose(tmp_path, source)
        result = ratify(tmp_path, proposed)
        legacy = json.loads(json.dumps(result["state"]))
        legacy["source"].pop("ownership")
        card = journey._card(legacy)
        assert card["egress"]["ownership"] == "unclassified"
        assert card["egress"]["disposition"] == "per_item_approval"
        assert card["egress"]["withheld"] > 0

    def test_an_approved_citation_is_released(self, tmp_path):
        source = estate(tmp_path, "software-product")
        proposed = propose(tmp_path, source, ownership="third_party", basis="client drive")
        result = ratify(tmp_path, proposed)
        state = json.loads(json.dumps(result["state"]))
        first = result["card"]["evidence"][0]
        state["egress_approved"] = [f"{first['path']}:{first['line']}"]
        card = journey._card(state)
        assert card["egress"]["withheld"] == len(card["evidence"]) - 1
        assert card["evidence"][0]["excerpt"] != journey.WITHHELD_EXCERPT
