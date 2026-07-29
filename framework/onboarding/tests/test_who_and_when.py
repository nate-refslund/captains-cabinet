"""The two claims a connector sweep makes without saying so.

That the activity it read is the OPERATOR'S, and that the period it covers is
REPRESENTATIVE of their work. Neither is settled by reading more rows, and both
are wrong often enough that the sweep must state its basis and, where it has
none, ask instead of assume.
"""
from __future__ import annotations

import json

import pytest

from framework.onboarding import journey, research


# --- who ---------------------------------------------------------------------


class TestOperatorIdentity:
    def test_the_operator_comes_from_the_record(self):
        who = research.operator_identity(
            {"operator": {"name": "A. Person", "handles": {"tracker": ["aperson"]}}})
        assert who["basis"] == "onboarding_record"
        assert who["handles"]["tracker"] == ["aperson"] and who["names"] == ["A. Person"]

    def test_an_absent_record_resolves_to_nothing_not_to_a_guess(self):
        """The alternative to an empty answer here is falling back to whatever a
        credential reports, which is the substitution this whole pair exists to
        prevent. Absent is a legitimate, disclosed state."""
        for record in (None, {}, {"operator": "not a mapping"}, {"operator": {}}):
            who = research.operator_identity(record)
            assert who["handles"] == {} and who["names"] == []
            assert who["basis"] == "onboarding_record"

    def test_an_unresolved_connector_claims_nothing_and_says_so(self):
        basis = research.attribution_basis(research.operator_identity({}), "tracker")
        assert basis["basis"] == "unresolved" and basis["identifies"] == []
        assert "not claiming" in basis["statement"]

    def test_a_resolved_claim_states_what_it_rests_on(self):
        who = research.operator_identity({"operator": {"handles": {"code": ["aperson"]}}})
        basis = research.attribution_basis(who, "code")
        assert basis["basis"] == "onboarding_record"
        assert "onboarding record" in basis["statement"] and "aperson" in basis["statement"]


# --- when --------------------------------------------------------------------


class TestPeriod:
    def test_the_period_is_the_rows_own_extent_never_a_chosen_window(self):
        rows = [{"connector": "t", "updated": "2026-01-05T00:00:00Z"},
                {"connector": "t", "updated": "2026-03-09"},
                {"connector": "t", "updated": None}]
        period = research.period_read(rows)
        assert (period["from"], period["to"]) == ("2026-01-05", "2026-03-09")
        assert (period["dated_rows"], period["rows"]) == (2, 3)
        assert period["dated_rows"] <= period["rows"]

    def test_no_dates_is_stated_as_no_period_rather_than_today(self):
        period = research.period_read([{"connector": "t", "updated": None}])
        assert period["from"] is None and "no period at all" in period["basis"]

    def test_an_unparseable_stamp_is_absent_never_now(self):
        assert research.period_read([{"connector": "t", "updated": "last tuesday"}])["from"] is None


class TestPresenceQuestion:
    def _rows(self, days, actor="aperson"):
        return [{"connector": "code", "name": f"n{i}", "updated": d, "actors": [actor]}
                for i, d in enumerate(days)]

    def test_a_gap_in_the_operators_own_activity_is_asked_never_concluded(self):
        who = research.operator_identity({"operator": {"handles": {"code": ["aperson"]}}})
        rows = self._rows(["2026-06-01", "2026-06-03", "2026-07-05", "2026-07-06"])
        question = research.presence_question(rows, who, research.period_read(rows))
        assert question["is_a_question"] is True and question["gap_days"] == 32
        assert question["question"].rstrip().endswith("?")
        assert "I was away" in question["options"]
        assert question["attribution"][0]["basis"] == "onboarding_record"

    def test_no_gap_is_claimed_where_the_operator_cannot_be_recognised(self):
        """An unattributable silence is not evidence about the operator. Treating
        it as such is the unearned negative in its purest form: the sweep would
        ask about somebody else's quiet fortnight as though it were theirs."""
        rows = self._rows(["2026-06-01", "2026-07-30"], actor="someone-else")
        who = research.operator_identity({"operator": {"handles": {"code": ["aperson"]}}})
        assert research.presence_question(rows, who, research.period_read(rows)) is None
        assert research.presence_question(rows, research.operator_identity({}),
                                          research.period_read(rows)) is None

    def test_a_continuous_period_asks_nothing(self):
        who = research.operator_identity({"operator": {"handles": {"code": ["aperson"]}}})
        rows = self._rows(["2026-07-01", "2026-07-04", "2026-07-08"])
        assert research.presence_question(rows, who, research.period_read(rows)) is None

    def test_the_longest_gap_is_the_one_asked_about(self):
        who = research.operator_identity({"operator": {"handles": {"code": ["aperson"]}}})
        rows = self._rows(["2026-01-01", "2026-01-20", "2026-05-01", "2026-05-20"])
        question = research.presence_question(rows, who, research.period_read(rows))
        assert (question["from"], question["to"]) == ("2026-01-20", "2026-05-01")


class TestWhoAndWhenLines:
    def test_the_period_sentence_names_its_assumption(self):
        block = research.who_and_when([{"connector": "t", "name": "a", "updated": "2026-07-01"}])
        assert any("assuming that period is representative" in line
                   for line in research.who_and_when_lines(block))

    def test_an_unresolved_connector_is_disclosed_not_omitted(self):
        """A disclosure that mentions only what it managed to resolve is how a
        partial read starts reading as a complete one."""
        block = research.who_and_when([{"connector": "tracker", "name": "a", "updated": None}])
        assert any("cannot tell which actor is you in tracker" in line
                   for line in research.who_and_when_lines(block))

    def test_an_undated_sweep_says_it_has_no_period(self):
        block = research.who_and_when([{"connector": "t", "name": "a", "updated": None}])
        assert any("no period at all" in line for line in research.who_and_when_lines(block))


# --- the sweep must carry an actor at all ------------------------------------


class TestActorSurvivesTheSweep:
    def _sweep(self, payload, *, actor_field=None):
        inventory = {"url": "https://code.example/repos", "method": "GET",
                     "items_path": "", "name_field": "name", "updated_field": "updated_at"}
        if actor_field:
            inventory["actor_field"] = actor_field
        return research.sweep_connectors(
            ".", specs=[{"name": "code", "credential_env": "TOK", "inventory": inventory}],
            env={"TOK": "x"}, ceiling={"connected": True},
            fetch=lambda request, timeout: (200, json.dumps(payload).encode("utf-8")))

    def test_the_row_keeps_its_actor(self):
        """It was extracted per item and then collapsed to a distinct COUNT,
        which answers "how many people" and structurally cannot answer "which of
        them is you" — so nothing downstream could separate the operator's own
        activity from anyone else's."""
        sweep = self._sweep([{"name": "alpha", "updated_at": "2026-07-01T00:00:00Z",
                              "owner": {"login": "aperson"}}], actor_field="owner.login")
        assert sweep["rows"] == [{"connector": "code", "name": "alpha",
                                  "updated": "2026-07-01T00:00:00Z", "actors": ["aperson"]}]

    def test_a_row_without_an_actor_carries_no_actor_key(self):
        """Absence stays absent. A blank actor would match a blank handle and
        silently attribute every unattributed row to the operator."""
        sweep = self._sweep([{"name": "alpha", "updated_at": "2026-07-01T00:00:00Z"}])
        assert sweep["rows"] and "actors" not in sweep["rows"][0]


# --- end to end through the real action --------------------------------------


def test_the_gathered_sweep_discloses_who_and_when(tmp_path, monkeypatch):
    """The disclosure the operator reads carries the period, its assumption, and
    every connector whose actors could not be resolved to them."""
    data = tmp_path / journey.DATA_REL
    data.mkdir(parents=True, exist_ok=True)
    (data / journey.STATE_NAME).write_text(json.dumps(journey._fresh_state()), encoding="utf-8")
    monkeypatch.setattr(journey.research, "sweep_connectors", lambda base: {
        "schema": "cabinet.connector-sweep/v1", "swept_at": "2026-07-29T00:00:00Z",
        "declared": 1, "calls": 1,
        "connectors": [{"name": "code", "connected": True, "items": 2}],
        "rows": [{"connector": "code", "name": "alpha", "updated": "2026-06-01", "actors": ["x"]},
                 {"connector": "code", "name": "beta", "updated": "2026-07-25", "actors": ["x"]}],
        "identities": [], "not_reached": [],
    })
    result = journey.act({"action": "gather_connectors", "surface": "dashboard",
                          "action_id": "g-1"}, tmp_path)
    disclosed = result["state"]["salience_rows"]["not_reached"]
    assert any("dated 2026-06-01 to 2026-07-25" in line for line in disclosed)
    assert any("assuming that period is representative" in line for line in disclosed)
    assert any("cannot tell which actor is you in code" in line for line in disclosed)
    who_when = result["state"]["connector_sweep"]["who_and_when"]
    assert who_when["operator"]["basis"] == "onboarding_record"
    assert who_when["attribution"][0]["basis"] == "unresolved"


def test_the_record_is_the_only_place_the_operator_comes_from(tmp_path, monkeypatch):
    """With a record naming the operator, the same rows produce a resolved basis
    and the gap becomes a question. Nothing asked a credential who anyone was."""
    record = tmp_path / "answers.yml"
    record.write_text("operator:\n  handles:\n    code: [x]\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_INIT_ANSWERS", str(record))
    data = tmp_path / journey.DATA_REL
    data.mkdir(parents=True, exist_ok=True)
    (data / journey.STATE_NAME).write_text(json.dumps(journey._fresh_state()), encoding="utf-8")
    monkeypatch.setattr(journey.research, "sweep_connectors", lambda base: {
        "schema": "cabinet.connector-sweep/v1", "swept_at": "2026-07-29T00:00:00Z",
        "declared": 1, "calls": 1, "connectors": [], "identities": [], "not_reached": [],
        "rows": [{"connector": "code", "name": "a", "updated": "2026-05-01", "actors": ["x"]},
                 {"connector": "code", "name": "b", "updated": "2026-07-25", "actors": ["x"]}],
    })
    result = journey.act({"action": "gather_connectors", "surface": "dashboard",
                          "action_id": "g-2"}, tmp_path)
    who_when = result["state"]["connector_sweep"]["who_and_when"]
    assert who_when["attribution"][0]["basis"] == "onboarding_record"
    assert who_when["presence_question"]["is_a_question"] is True
    assert any("Was that time away" in line
               for line in result["state"]["salience_rows"]["not_reached"])


# --- the promise the floors could break --------------------------------------


class TestIdentityIsDemotedNotFloored:
    """`salience` promises identity is DEMOTED, never deleted, because the same
    string can be the estate's own label AND one of its real targets. That
    promise was kept only against the identity path; the furniture and
    concentration floors reached the same token by another route and deleted it.
    """

    def _rows(self):
        # The shape that produced this live: one connector names every row
        # `<org>/<thing>`, so the org token is in 100% of that connector's rows.
        rows = [{"connector": "code", "name": f"northbay/{n}", "updated": "2026-07-01"}
                for n in ("alpha", "beta", "gamma", "delta", "epsilon",
                          "zeta", "eta", "theta", "northbay.example")]
        rows += [{"connector": "hosting", "name": n, "updated": "2026-07-02"}
                 for n in ("northbay.example", "alpha-live", "beta-live")]
        return rows

    def test_the_estate_name_survives_the_floor_and_is_demoted(self):
        from framework.onboarding import salience

        ranking = salience.rank(self._rows(), identities=["northbay"],
                                now="2026-07-03T00:00:00Z")
        carrying = [c for c in ranking["clusters"] if "northbay" in c["tokens"]]
        assert carrying, "the estate name was deleted by a floor, not demoted"
        assert carrying[0]["demoted"] is True
        assert "northbay" not in {str(f["token"]) for f in ranking["discounted"]}

    def test_without_the_identity_the_same_token_is_discounted_not_deleted(self):
        """The exemption is EARNED by being declared estate identity, not handed
        to every high-share token — otherwise the measurements would stop
        working. INVERTED 2026-07-29 and strengthened: the undeclared token used
        to be DELETED here, and the arm asserting the deletion is what let a
        second correct answer be lost on the live estate — the org owning 52 of
        56 repositories was never in the identity strings the connectors report
        about themselves, so the exemption never fired for it. Now it is
        discounted, and this pins that the discount still bites AND that the
        token is still named with its numbers rather than gone."""
        from framework.onboarding import salience

        ranking = salience.rank(self._rows(), now="2026-07-03T00:00:00Z")
        discounted = {str(f["token"]): f for f in ranking["discounted"]}
        assert "northbay" in discounted
        assert discounted["northbay"]["explained"] == 9
        named = [c for c in ranking["clusters"] + ranking["not_candidates"]
                 if "northbay" in c["tokens"]]
        assert named, "the undeclared token was deleted rather than discounted"
        assert named[0]["rows"] == 10  # every occurrence still counted and shown
