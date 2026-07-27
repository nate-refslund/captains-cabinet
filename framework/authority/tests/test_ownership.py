"""The ownership plane: refusal-on-unclassified, structural writes, graded egress.

Every arm here fails against pre-change code — there was no ownership plane at
all before 2026-07-27 — so the file's existence is its own negative control.
What the arms below add is the DEGENERATE end: absent, empty, null and unknown
inputs must refuse rather than pass, because "no class recorded" is the state
every source and every stored row predating this plane is in, and a plane that
waves those through is a label, not a control.
"""
from __future__ import annotations

import pytest

from framework.authority import ownership as own


class TestClassRefusal:
    @pytest.mark.parametrize("raw", [None, "", "   ", "unknown", "unclassified", "n/a", "tbd", "?"])
    def test_undecided_inputs_refuse_with_the_unclassified_code(self, raw):
        with pytest.raises(own.OwnershipRefusal) as exc:
            own.require_ownership(raw)
        assert exc.value.code == "ownership_unclassified"

    @pytest.mark.parametrize("raw", [0, 1, True, [], {}, ("self",)])
    def test_non_strings_refuse_rather_than_coerce(self, raw):
        with pytest.raises(own.OwnershipRefusal):
            own.require_ownership(raw)

    def test_an_unlisted_class_refuses_with_its_own_code(self):
        with pytest.raises(own.OwnershipRefusal) as exc:
            own.require_ownership("employers_maybe")
        assert exc.value.code == "ownership_class_unknown"
        assert exc.value.detail["accepted"] == list(own.OWNERSHIP_CLASSES)

    @pytest.mark.parametrize("raw,expected", [
        ("self", "self"), ("SELF", "self"), (" employer ", "employer"),
        ("third_party", "third_party"), ("third-party", "third_party"),
        ("Third Party", "third_party"),
    ])
    def test_accepted_spellings_normalize(self, raw, expected):
        assert own.require_ownership(raw) == expected

    def test_there_is_no_default_branch(self):
        """Whatever goes in, either a member comes out or it raises."""
        for raw in (None, "", "self", "nonsense", 5, object()):
            try:
                assert own.require_ownership(raw) in own.OWNERSHIP_CLASSES
            except own.OwnershipRefusal:
                pass


class TestAuthorityBasis:
    @pytest.mark.parametrize("raw", [None, "", "   ", 7, [], {}])
    def test_a_missing_basis_refuses(self, raw):
        with pytest.raises(own.OwnershipRefusal) as exc:
            own.require_authority_basis(raw)
        assert exc.value.code == "authority_basis_required"

    def test_an_overlong_basis_refuses(self):
        with pytest.raises(own.OwnershipRefusal) as exc:
            own.require_authority_basis("x" * (own.MAX_AUTHORITY_BASIS_CHARS + 1))
        assert exc.value.code == "authority_basis_too_long"

    def test_whitespace_is_collapsed_not_stripped_away(self):
        assert own.require_authority_basis("  my   own\nlaptop ") == "my own laptop"

    def test_the_operators_own_estate_still_needs_a_basis(self):
        """A class without a reason is an answer given to make a prompt go away."""
        with pytest.raises(own.OwnershipRefusal):
            own.open_ingest("self", "", attested_at="2026-07-27T00:00:00Z")


class TestWritesAreStructural:
    def test_only_the_operators_own_estate_permits_writes(self):
        assert own.writes_permitted("self") is True
        assert own.writes_permitted("employer") is False
        assert own.writes_permitted("third_party") is False

    def test_writes_permitted_takes_no_override_argument(self):
        """The structural claim, asserted against the signature itself.

        If a future edit adds `force=`/`allow=`/`read_only=`, this fails — which
        is the point: a flag that can be set is a flag that gets set.
        """
        import inspect

        params = list(inspect.signature(own.writes_permitted).parameters)
        assert params == ["ownership"]

    @pytest.mark.parametrize("cls", sorted(own.NON_OWNED_CLASSES))
    def test_require_write_permitted_refuses_every_non_owned_class(self, cls):
        with pytest.raises(own.OwnershipRefusal) as exc:
            own.require_write_permitted(cls, operation="push")
        assert exc.value.code == "write_refused_non_owned"
        assert exc.value.detail["ownership"] == cls

    def test_non_owned_set_is_derived_from_the_class_tuple(self):
        assert own.NON_OWNED_CLASSES == frozenset(own.OWNERSHIP_CLASSES) - {"self"}


class TestEgressIsGraded:
    def test_dispositions(self):
        assert own.egress_disposition("self") == own.EGRESS_ALLOW
        assert own.egress_disposition("employer") == own.EGRESS_RECORD_AND_ALLOW
        assert own.egress_disposition("third_party") == own.EGRESS_PER_ITEM_APPROVAL

    def test_every_class_has_a_declared_disposition(self):
        """A class missing from the table would be a silent allow."""
        assert set(own.EGRESS_BY_CLASS) == set(own.OWNERSHIP_CLASSES)

    def test_a_row_with_no_recorded_class_is_refused_not_passed(self):
        screened = own.screen_egress([{"id": "row-1"}, {"id": "row-2", "ownership": None}])
        assert screened["allowed"] == []
        assert [r["reason"] for r in screened["refused"]] == [
            "ownership_unclassified", "ownership_unclassified",
        ]

    def test_third_party_is_refused_until_approved_per_item(self):
        items = [{"id": "a", "ownership": "third_party"}, {"id": "b", "ownership": "third_party"}]
        first = own.screen_egress(items)
        assert len(first["refused"]) == 2
        second = own.screen_egress(items, approved_ids=["a"])
        assert [i["id"] for i in second["allowed"]] == ["a"]
        assert [r["id"] for r in second["refused"]] == ["b"]

    def test_the_empty_set_reports_that_it_screened_nothing(self):
        """Degenerate end: zero screened must not read as "everything allowed"."""
        screened = own.screen_egress([])
        assert screened == {"screened": 0, "allowed": [], "refused": []}

    def test_require_egress_refuses_the_whole_send_not_just_the_bad_items(self):
        items = [{"id": "ok", "ownership": "self"}, {"id": "no", "ownership": "third_party"}]
        with pytest.raises(own.OwnershipRefusal) as exc:
            own.require_egress_allowed(items, channel="telegram")
        assert exc.value.code == "egress_refused_non_owned"
        assert exc.value.detail["channel"] == "telegram"
        assert own.require_egress_allowed(items, approved_ids=["no"], channel="telegram") == items


class TestSensitivityClasses:
    @pytest.mark.parametrize("path,expected", [
        ("hr/payroll-2026.csv", "compensation"),
        ("people/employee-records/briar.md", "personnel"),
        ("finance/salaries.xlsx", "compensation"),
        ("crm/customer-export-eu.csv", "customer_pii"),
        ("legal/subpoena-2026-03.pdf", "legal"),
        ("board/due-diligence-summary.md", "corporate_finance"),
        ("deploy/.env.production", "credentials"),
        ("keys/server.pem", "credentials"),
    ])
    def test_each_class_refuses_under_its_own_name(self, path, expected):
        assert expected in own.sensitivity_classes(path)

    @pytest.mark.parametrize("path", [
        "src/ledger/reconcile.ts", "docs/team/roster.md", "README.md",
        "docs/runbooks/deploy-ledger-api.md", "package.json",
        "cabinet/config/cognitive-architecture-contract.yml",
    ])
    def test_ordinary_working_files_are_not_refused(self, path):
        """Precision is load-bearing: a detector that fires on ordinary docs is
        switched off within a week, and an off detector refuses nothing."""
        assert own.sensitivity_classes(path) == ()

    def test_the_empty_path_matches_nothing_rather_than_everything(self):
        assert own.sensitivity_classes("") == ()
        assert own.sensitivity_refusal("") is None
        assert own.sensitivity_classes(None) == ()

    def test_the_refusal_reason_is_stable_for_a_multi_class_path(self):
        classes = own.sensitivity_classes("hr/salary-tokens.csv")
        assert len(classes) > 1
        assert own.sensitivity_refusal("hr/salary-tokens.csv") == classes[0]
        assert own.sensitivity_refusal("hr/salary-tokens.csv") == own.SENSITIVITY_CREDENTIALS

    def test_the_class_list_covers_the_categories_the_ruling_named(self):
        assert set(own.SENSITIVITY_CLASSES) == {
            "credentials", "personnel", "compensation",
            "customer_pii", "legal", "corporate_finance",
        }


class TestAttestationAndRecord:
    def test_the_attestation_records_that_it_is_unverified(self):
        att = own.attestation("employer", "my seat's read access", attested_at="T")
        assert att["verified_by_framework"] is False
        assert "cannot verify" in att["limit"]

    def test_open_ingest_returns_the_class_basis_permissions_and_attestation(self):
        opened = own.open_ingest("employer", "read access granted to my seat", attested_at="T")
        assert opened["ownership"] == "employer"
        assert opened["permissions"]["write_capable_adapters"] == "refused"
        assert opened["permissions"]["read_only"] is True
        assert opened["attestation"]["verified_by_framework"] is False

    def test_permissions_are_derived_not_stored(self):
        assert own.source_permissions("self")["write_capable_adapters"] == "allowed"
        for cls in sorted(own.NON_OWNED_CLASSES):
            assert own.source_permissions(cls)["write_capable_adapters"] == "refused"
            assert own.source_permissions(cls)["writes_to_source"] is False

    def test_the_access_record_carries_refusals_with_their_classes(self):
        record = own.access_record(
            schema="cabinet.source-access-record/v1",
            source_root="/estate",
            ownership="employer",
            authority_basis="my seat",
            charter_hash="c" * 64,
            manifest_hash="m" * 64,
            entry_count=12,
            refusals={"compensation": 2, "credentials": 1},
            retention="not persisted",
            recorded_at="T",
        )
        assert record["refusals"] == {"compensation": 2, "credentials": 1}
        assert record["refusals_total"] == 3
        assert record["purge_receipt"] is None
        assert record["attestation_limit"] == own.ATTESTATION_LIMIT

    def test_the_record_refuses_to_be_built_for_an_unclassified_source(self):
        with pytest.raises(own.OwnershipRefusal):
            own.access_record(
                schema="s", source_root="/estate", ownership="", authority_basis="b",
                charter_hash="c", manifest_hash="m", entry_count=0, refusals={},
                retention="r", recorded_at="T",
            )

    def test_the_limit_is_stated_plainly_rather_than_implied(self):
        assert "cannot verify" in own.ATTESTATION_LIMIT
        assert "no-egress" in own.ATTESTATION_LIMIT
