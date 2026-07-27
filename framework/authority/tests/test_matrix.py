"""T5 — the authority matrix as DATA: loader + fail-closed validator + the
two CI invariants (ceiling coverage of all six HARD_CEILING_TOUCHES members,
and no prod/ceiling cell resolving to `auto`).

The matrix YAML (`framework/policies/authority-matrix.yml`) is the canonical
Captain-ratified policy *document*; `framework/authority/matrix.py` is the
thin loader/validator that schema-checks it against the ONE shared
`classify_action` enum (`ACTION_TYPES`) and the code-level hard-ceiling
backstop (`HARD_CEILING_TOUCHES`). No gate behavior here — T5 is matrix-as-data
only (SHADOW-ONLY, fail-closed). See docs/authority-matrix-design-2026-06-19.md
§1 Component 1 + §2 + FIX-6/FIX-7 + the Reconciliation table.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

# Repo root on sys.path so the framework package imports cleanly (same
# convention as the sibling authority/fidelity tests).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import matrix as M
from framework.authority.classifier import ACTION_TYPES, AMBIGUOUS
from framework.learning.capability_gaps import HARD_CEILING_TOUCHES

# Verdicts that the matrix may assign.
_VERDICTS = {
    "auto",
    "act_with_undo",
    "auto_with_veto_window",
    "notify_after",
    "propose_only",
    "always_gated",
    "classifier",
}
_CONFIDENCE_STATES = {"unmeasured", "propose_only", "eligible", "graduated", "demote"}
_HARD_CEILING_ROWS = {
    "external_comms",
    "deploy_prod",
    "spend",
    "secrets",
    "network_write",
    "credentials_grant",
}


@pytest.fixture()
def loaded():
    """The shipped framework floor matrix, loaded + validated."""
    return M.load_matrix()


# ---------------------------------------------------------------------------
# 1. The shipped floor file loads + validates
# ---------------------------------------------------------------------------

class TestShippedFloor:
    def test_floor_file_exists(self):
        assert (M.matrix_path()).is_file()

    def test_floor_loads_and_validates(self, loaded):
        # load_matrix must validate; a bad floor would raise.
        assert loaded["version"] == 1
        assert isinstance(loaded["policies"], list)

    def test_floor_has_authority_matrix_policy(self, loaded):
        pol = M.matrix_policy(loaded)
        assert pol["name"] == "authority-matrix"
        assert pol["type"] == "authority_matrix"

    def test_floor_covers_all_thirteen_risk_classes(self, loaded):
        # [GERM-2] +pm_write +calendar_write (act_with_undo classes).
        # 2026-07-04 trust-inversion split-outs: +read_only_dispatch
        # (investigation_run, notify_after) +draft_only (its own class,
        # outbound-adjacent; earn-up until CAPTAIN-RULING 2026-07-26 moved it
        # to notify_after) moved OUT of reversible.
        pol = M.matrix_policy(loaded)
        expected = {
            "reversible", "read_only_dispatch", "draft_only",
            "pm_write", "calendar_write",
            "internal_comms", "external_comms",
            "deploy_nonprod", "deploy_prod", "spend",
            "secrets", "network_write", "credentials_grant",
        }
        assert set(pol["risk_classes"]) == expected
        assert set(pol["verdicts"]) == expected
        # keep the count claim honest with matrix.RISK_CLASSES (closed set)
        assert expected == set(M.RISK_CLASSES)

    def test_veto_window_is_seven(self, loaded):
        pol = M.matrix_policy(loaded)
        assert pol["veto_window_minutes"] == 7

    def test_deploy_globs_present(self, loaded):
        pol = M.matrix_policy(loaded)
        assert pol["deploy"]["safe_globs"]
        assert pol["deploy"]["high_risk_globs"]
        # the dangerous domains the design enumerates are present
        joined = "\n".join(pol["deploy"]["high_risk_globs"])
        for needle in ("migrations", "auth", "payment", ".env", "policies/"):
            assert needle in joined

    def test_bars_and_cooldowns_present(self, loaded):
        pol = M.matrix_policy(loaded)
        assert pol["bars"]["default"]["match_rate"] == 0.85
        assert pol["cooldown_days"]["default"] == 14
        assert pol["cooldown_days"]["internal_comms"] == 21
        assert pol["cooldown_days"]["deploy_nonprod"] == 21


# ---------------------------------------------------------------------------
# 2. action_type coverage — every classifier output (except the ambiguous
#    backstop) maps to exactly one risk_class; no stray action_types.
# ---------------------------------------------------------------------------

class TestActionTypeCoverage:
    def test_every_real_action_type_is_mapped(self, loaded):
        pol = M.matrix_policy(loaded)
        mapped: set[str] = set()
        for rc in pol["risk_classes"].values():
            mapped.update(rc["action_types"])
        # AMBIGUOUS is the propose-defaulting backstop — deliberately NOT in
        # the matrix (it has no risk_class; it falls through to propose-only).
        expected = set(ACTION_TYPES) - {AMBIGUOUS}
        assert mapped == expected

    def test_no_action_type_outside_the_classifier_enum(self, loaded):
        pol = M.matrix_policy(loaded)
        for rc in pol["risk_classes"].values():
            for at in rc["action_types"]:
                assert at in ACTION_TYPES, at

    def test_no_action_type_mapped_to_two_risk_classes(self, loaded):
        pol = M.matrix_policy(loaded)
        seen: dict[str, str] = {}
        for name, rc in pol["risk_classes"].items():
            for at in rc["action_types"]:
                assert at not in seen, (at, seen[at], name)
                seen[at] = name


# ---------------------------------------------------------------------------
# 3. THE CI INVARIANT #1 — full hard-ceiling coverage [FIX-7]
# ---------------------------------------------------------------------------

class TestCeilingCoverage:
    def test_ceiling_map_covers_all_six_frozenset_members(self, loaded):
        pol = M.matrix_policy(loaded)
        # The exact assertion the task names: all six, not a "mappable subset".
        assert set(pol["ceiling_frozenset_map"].values()) == set(HARD_CEILING_TOUCHES)

    def test_ceiling_map_keys_equal_hard_ceiling_list(self, loaded):
        pol = M.matrix_policy(loaded)
        assert set(pol["ceiling_frozenset_map"]) == set(pol["hard_ceiling"])
        assert set(pol["hard_ceiling"]) == _HARD_CEILING_ROWS

    def test_validator_helper_returns_the_six(self, loaded):
        pol = M.matrix_policy(loaded)
        assert M.ceiling_members(pol) == set(HARD_CEILING_TOUCHES)
        assert len(HARD_CEILING_TOUCHES) == 6


# ---------------------------------------------------------------------------
# 4. THE CI INVARIANT #2 — no prod/ceiling cell resolves to `auto` [FIX-6]
# ---------------------------------------------------------------------------

class TestNoCeilingAuto:
    def test_no_hard_ceiling_row_has_an_auto_cell(self, loaded):
        pol = M.matrix_policy(loaded)
        for rc in pol["hard_ceiling"]:
            verdicts = pol["verdicts"][rc]
            for state, verdict in verdicts.items():
                assert verdict != "auto", (rc, state)

    def test_every_hard_ceiling_row_is_always_gated(self, loaded):
        pol = M.matrix_policy(loaded)
        for rc in pol["hard_ceiling"]:
            verdicts = pol["verdicts"][rc]
            # hard ceiling = always_gated for every state (incl the "*" wildcard)
            for state, verdict in verdicts.items():
                assert verdict == "always_gated", (rc, state, verdict)

    def test_deploy_prod_never_auto(self, loaded):
        pol = M.matrix_policy(loaded)
        assert "auto" not in set(pol["verdicts"]["deploy_prod"].values())

    def test_helper_no_ceiling_auto(self, loaded):
        pol = M.matrix_policy(loaded)
        # the deterministic helper the CI test calls
        assert M.no_ceiling_or_prod_auto(pol) is True


# ---------------------------------------------------------------------------
# 5. Verdict-table shape — confidence states + verdict enum + wildcard
# ---------------------------------------------------------------------------

class TestVerdictShape:
    def test_all_verdict_values_in_enum(self, loaded):
        pol = M.matrix_policy(loaded)
        for rc, states in pol["verdicts"].items():
            for state, verdict in states.items():
                assert verdict in _VERDICTS, (rc, state, verdict)

    def test_non_ceiling_rows_cover_all_confidence_states(self, loaded):
        pol = M.matrix_policy(loaded)
        for rc, states in pol["verdicts"].items():
            if rc in pol["hard_ceiling"]:
                continue
            assert set(states) == _CONFIDENCE_STATES, rc

    def test_ceiling_rows_use_wildcard(self, loaded):
        pol = M.matrix_policy(loaded)
        for rc in pol["hard_ceiling"]:
            assert set(pol["verdicts"][rc]) == {"*"}

    def test_reversible_is_act_with_undo_trust_first(self, loaded):
        # TRUST-INVERSION (2026-07-04, earn-demotion ruling — supersedes the
        # old reversible earn-up pin auto@graduated/propose_only@unmeasured,
        # which _validate_act_first_floor now hard-rejects): act_with_undo at
        # every non-demote state, propose_only at demote (evidence is the
        # only way down, and it must land fail-safe).
        pol = M.matrix_policy(loaded)
        for state in ("unmeasured", "propose_only", "eligible", "graduated"):
            assert pol["verdicts"]["reversible"][state] == "act_with_undo", state
        assert pol["verdicts"]["reversible"]["demote"] == "propose_only"
        # read_only_dispatch mirrors the posture with notify_after (read-only,
        # act-and-tell); draft_only joined it on CAPTAIN-RULING 2026-07-26
        # (was the earn-up ladder auto@graduated / propose_only elsewhere).
        for state in ("unmeasured", "propose_only", "eligible", "graduated"):
            assert pol["verdicts"]["read_only_dispatch"][state] == "notify_after", state
        assert pol["verdicts"]["read_only_dispatch"]["demote"] == "propose_only"
        for state in ("unmeasured", "propose_only", "eligible", "graduated"):
            assert pol["verdicts"]["draft_only"][state] == "notify_after", state
        assert pol["verdicts"]["draft_only"]["demote"] == "propose_only"

    def test_internal_comms_graduated_is_veto_window(self, loaded):
        pol = M.matrix_policy(loaded)
        assert pol["verdicts"]["internal_comms"]["graduated"] == "auto_with_veto_window"

    def test_deploy_nonprod_uses_classifier_for_eligible_plus(self, loaded):
        pol = M.matrix_policy(loaded)
        assert pol["verdicts"]["deploy_nonprod"]["graduated"] == "classifier"
        assert pol["verdicts"]["deploy_nonprod"]["eligible"] == "classifier"
        assert pol["verdicts"]["deploy_nonprod"]["unmeasured"] == "propose_only"


# ---------------------------------------------------------------------------
# 6. Fail-closed validation — malformed data RAISES (never silently passes)
# ---------------------------------------------------------------------------

class TestFailClosed:
    def _base(self, loaded):
        return copy.deepcopy(loaded)

    def test_wrong_version_raises(self, loaded):
        d = self._base(loaded)
        d["version"] = 2
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_missing_version_raises(self, loaded):
        d = self._base(loaded)
        del d["version"]
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_extra_top_level_key_raises(self, loaded):
        d = self._base(loaded)
        d["surprise"] = True
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_extra_policy_key_raises(self, loaded):
        d = self._base(loaded)
        M.matrix_policy(d)["surprise"] = 1
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_unknown_action_type_raises(self, loaded):
        d = self._base(loaded)
        M.matrix_policy(d)["risk_classes"]["reversible"]["action_types"].append("teleport")
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_unknown_verdict_raises(self, loaded):
        d = self._base(loaded)
        M.matrix_policy(d)["verdicts"]["reversible"]["graduated"] = "yolo"
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_unknown_confidence_state_raises(self, loaded):
        d = self._base(loaded)
        M.matrix_policy(d)["verdicts"]["reversible"]["sometimes"] = "auto"
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_ceiling_row_with_auto_raises(self, loaded):
        d = self._base(loaded)
        # try to widen autonomy on a hard-ceiling row → must be rejected
        M.matrix_policy(d)["verdicts"]["spend"] = {"*": "auto"}
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_prod_row_auto_raises(self, loaded):
        d = self._base(loaded)
        M.matrix_policy(d)["verdicts"]["deploy_prod"] = {"*": "auto"}
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_incomplete_ceiling_map_raises(self, loaded):
        d = self._base(loaded)
        M.matrix_policy(d)["ceiling_frozenset_map"].pop("secrets")
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_ceiling_map_value_outside_frozenset_raises(self, loaded):
        d = self._base(loaded)
        M.matrix_policy(d)["ceiling_frozenset_map"]["secrets"] = "not_a_member"
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_hard_ceiling_not_matching_map_raises(self, loaded):
        d = self._base(loaded)
        M.matrix_policy(d)["hard_ceiling"] = ["spend"]
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_bad_veto_window_raises(self, loaded):
        d = self._base(loaded)
        M.matrix_policy(d)["veto_window_minutes"] = 0
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_negative_cooldown_raises(self, loaded):
        d = self._base(loaded)
        M.matrix_policy(d)["cooldown_days"]["default"] = -1
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_missing_required_policy_field_raises(self, loaded):
        d = self._base(loaded)
        del M.matrix_policy(d)["verdicts"]
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_non_dict_raises(self):
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(["not", "a", "dict"])

    def test_missing_risk_class_verdict_row_raises(self, loaded):
        # a risk_class present in risk_classes but absent from verdicts
        d = self._base(loaded)
        del M.matrix_policy(d)["verdicts"]["reversible"]
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)


# ---------------------------------------------------------------------------
# 7. Loader hardening — yaml.safe_load, no path escape, missing file raises
# ---------------------------------------------------------------------------

class TestLoaderHardening:
    def test_load_missing_file_raises(self, tmp_path):
        with pytest.raises(M.MatrixValidationError):
            M.load_matrix(str(tmp_path / "does-not-exist.yml"))

    def test_load_validates_by_default(self, tmp_path):
        # a syntactically-loadable but semantically-invalid file must raise
        bad = tmp_path / "bad.yml"
        bad.write_text(
            "version: 1\n"
            "policies:\n"
            "  - name: authority-matrix\n"
            "    type: authority_matrix\n"
            "    message: x\n"
            "    risk_classes: {}\n"
            "    hard_ceiling: []\n"
            "    ceiling_frozenset_map: {}\n"
            "    verdicts: {}\n"
            "    veto_window_minutes: 7\n"
            "    deploy: {safe_globs: [], high_risk_globs: []}\n"
            "    bars: {default: {match_rate: 0.85, samples: 20, "
            "max_divergent_last10: 1, recency_clean_days: 14}}\n"
            "    cooldown_days: {default: 14}\n"
        )
        with pytest.raises(M.MatrixValidationError):
            M.load_matrix(str(bad))

    def test_load_uses_safe_load_not_arbitrary_objects(self, tmp_path, monkeypatch):
        # A YAML python/object tag must NOT construct an object (safe_load).
        evil = tmp_path / "evil.yml"
        evil.write_text("version: !!python/object/apply:os.system ['echo pwned']\n")
        with pytest.raises(Exception):
            M.load_matrix(str(evil))


class TestActWithUndoNeverCeiling:
    def test_act_with_undo_never_on_a_ceiling_row(self, loaded):
        # [GERM-2] the six hard ceilings can NEVER carry act_with_undo, and the
        # two new reversible-with-undo classes are never themselves ceilings.
        pol = M.matrix_policy(loaded)
        for rc in pol["hard_ceiling"]:
            assert "act_with_undo" not in set(pol["verdicts"][rc].values()), rc
        assert "pm_write" not in pol["hard_ceiling"]
        assert "calendar_write" not in pol["hard_ceiling"]


# ---------------------------------------------------------------------------
# 8. CAPTAIN-RULING 2026-07-26 — draft_only is act-and-tell, ceilings unmoved
# ---------------------------------------------------------------------------
# "the act first (except for emailing real people…)": COMPOSING a draft moved
# off the earn-up ladder onto notify_after (act-then-tell) at every non-demote
# state, in the root/guardian table AND the sovereign one. earn_up is
# deliberately untouched (narrowing stays legal) and every hard ceiling is
# untouched, so DELIVERING a draft is exactly as gated as it was.
#
# Arm 1 (TestDraftOnlyActThenTell) FAILS against pre-change code: the shipped
# row was auto@graduated + propose_only at the other four.
# Arm 2 (TestDraftWideningDidNotMoveTheCeilings) proves the walls held. It is
# mutation-checked, not merely shape-asserted: each assertion is paired with a
# synthetic matrix in which the wall IS moved, and the validator must reject
# it — otherwise the arm could pass on a matrix that no longer enforces
# anything (a sensor wired to nothing).

_DRAFT_ACT_STATES = ("unmeasured", "propose_only", "eligible", "graduated")


class TestDraftOnlyActThenTell:
    """The ruling landed in BOTH tables that grant it, and nowhere else."""

    def test_root_guardian_draft_only_is_notify_after(self, loaded):
        pol = M.matrix_policy(loaded)
        row = pol["verdicts"]["draft_only"]
        for state in _DRAFT_ACT_STATES:
            assert row[state] == "notify_after", state
        assert row["demote"] == "propose_only"

    def test_sovereign_draft_only_is_notify_after(self, loaded):
        pol = M.matrix_policy(loaded)
        row = pol["postures"]["sovereign"]["verdicts"]["draft_only"]
        for state in _DRAFT_ACT_STATES:
            assert row[state] == "notify_after", state
        assert row["demote"] == "propose_only"

    def test_draft_only_row_mirrors_read_only_dispatch(self, loaded):
        # The two act-and-tell classes carry the SAME ladder — one rule to
        # reason about, no per-class special case.
        pol = M.matrix_policy(loaded)
        for table in (pol["verdicts"], pol["postures"]["sovereign"]["verdicts"]):
            assert table["draft_only"] == table["read_only_dispatch"]

    def test_earn_up_draft_only_still_proposes(self, loaded):
        # earn_up was NOT widened — the cautious start still proposes, which
        # the narrows-validator permits (narrow-or-equal).
        pol = M.matrix_policy(loaded)
        row = pol["postures"]["earn_up"]["verdicts"]["draft_only"]
        for state in _DRAFT_ACT_STATES + ("demote",):
            assert row[state] == "propose_only", state

    def test_draft_only_needs_no_registered_inverse(self, loaded):
        # notify_after is NOT act_with_undo: the engine's undo-gap check never
        # runs for it, so the row must not claim act_with_undo anywhere (that
        # would silently demand an inverse draft_only deliberately lacks).
        pol = M.matrix_policy(loaded)
        for table in (pol["verdicts"], pol["postures"]["sovereign"]["verdicts"]):
            assert "act_with_undo" not in set(table["draft_only"].values())


class TestDraftWideningDidNotMoveTheCeilings:
    """The hard ceilings are exactly where they were — proven, not assumed."""

    def test_every_ceiling_row_is_always_gated_in_root(self, loaded):
        pol = M.matrix_policy(loaded)
        assert set(pol["hard_ceiling"]) == _HARD_CEILING_ROWS
        for rc in _HARD_CEILING_ROWS:
            assert pol["verdicts"][rc] == {"*": "always_gated"}, rc

    def test_external_comms_never_acts_in_any_posture(self, loaded):
        # The class that carries a real send. always_gated everywhere; the
        # sovereign table may only narrow it to the CONDITIONAL standing_grant
        # (grant-or-file-a-NEED), never to any act verdict.
        pol = M.matrix_policy(loaded)
        assert pol["verdicts"]["external_comms"] == {"*": "always_gated"}
        for name, entry in pol["postures"].items():
            cell = entry["verdicts"]["external_comms"]
            assert set(cell) == {"*"}, name
            assert cell["*"] in ("always_gated", "standing_grant"), name
            assert cell["*"] not in ("auto", "notify_after",
                                     "act_with_undo", "auto_with_veto_window")

    def test_no_ceiling_or_prod_auto_still_holds(self, loaded):
        assert M.no_ceiling_or_prod_auto(M.matrix_policy(loaded)) is True

    def test_ceiling_coverage_still_complete(self, loaded):
        pol = M.matrix_policy(loaded)
        assert M.ceiling_members(pol) == set(HARD_CEILING_TOUCHES)

    def test_send_action_types_stayed_on_the_ceiling(self, loaded):
        # The widened class owns EXACTLY the one non-egress action_type. If a
        # send kind ever drifted into draft_only it would inherit notify_after
        # — this is the assertion that would catch it.
        pol = M.matrix_policy(loaded)
        assert pol["risk_classes"]["draft_only"]["action_types"] == ["draft_only"]
        assert set(pol["risk_classes"]["external_comms"]["action_types"]) == {
            "external_message", "external_email"}

    def test_a_comms_call_classifies_by_recipient_not_by_draft_framing(self):
        # THE send-path proof at the live classifier: `queue_draft` is the
        # draft-shaped tool, yet an outside recipient classifies it into the
        # external_comms CEILING. classify_action has no branch that returns
        # "draft_only" at all, so no classifier-reachable path can wear the
        # widened class to reach a real person.
        from framework.authority.classifier import classify_action
        for recipient, expected in (
            ("client@example.org", "external_email"),
            ("", "external_email"),  # unresolvable ⇒ fail-closed to external
        ):
            got = classify_action(
                "mcp__brain__queue_draft",
                {"channel": "email", "recipient": recipient, "body": "x"},
            )
            assert got == expected, (recipient, got)

    # --- the mutation sensors: the walls are ENFORCED, not just shaped -----

    def test_every_egress_action_type_sits_on_a_ceiling_row(self, loaded):
        # THE wall this widening leans on: the gate's ceiling short-circuit is
        # keyed on `risk_class in hard_ceiling`, so a send kind is gated only
        # for as long as it MAPS to a ceiling class. Every outbound-comms kind
        # the classifier can emit must therefore sit on a hard-ceiling row.
        #
        # KNOWN VALIDATOR GAP (pre-existing, present identically on master —
        # this assertion is the sensor that covers it): validate_matrix checks
        # that every action_type is mapped exactly once, but NOT which class it
        # is mapped to, so relocating `external_email` into a non-ceiling class
        # validates clean and would reach the notify_after allow-branch. Fixing
        # that in the validator needs new framework production lines against a
        # census budget already at its ceiling, so it is recorded in the CG-35
        # amendment doc as an open item rather than silently closed here. A CI
        # test is a real sensor for it: the floor is germline + schg-locked and
        # load_policies REFUSES any preset/instance authority_matrix, so a
        # direct edit of this file is the only channel, and it lands here.
        from framework.authority.classifier import _EXTERNAL_COMMS
        # Not vacuous at the degenerate end: an empty/shrunk egress set would
        # make the loop below assert nothing at all.
        assert _EXTERNAL_COMMS == {"external_message", "external_email"}
        pol = M.matrix_policy(loaded)
        ceiling = set(pol["hard_ceiling"])
        placement = {
            at: name
            for name, rc in pol["risk_classes"].items()
            for at in rc["action_types"]
        }
        for at in _EXTERNAL_COMMS:
            assert placement[at] in ceiling, (at, placement[at])
            assert placement[at] == "external_comms", at

    def test_letting_external_comms_act_is_rejected(self, loaded):
        for verdict in ("auto", "notify_after"):
            d = copy.deepcopy(loaded)
            M.matrix_policy(d)["verdicts"]["external_comms"] = {"*": verdict}
            with pytest.raises(M.MatrixValidationError):
                M.validate_matrix(d)

    def test_letting_a_sovereign_ceiling_act_is_rejected(self, loaded):
        d = copy.deepcopy(loaded)
        posture = M.matrix_policy(d)["postures"]["sovereign"]["verdicts"]
        posture["external_comms"] = {"*": "notify_after"}
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_draft_only_demote_must_still_land_fail_safe(self, loaded):
        # Demote is posture-invariant: drifting the sovereign row's demote off
        # the root's is a hard error, so evidence still beats posture.
        d = copy.deepcopy(loaded)
        pol = M.matrix_policy(d)
        pol["postures"]["sovereign"]["verdicts"]["draft_only"]["demote"] = "notify_after"
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)
