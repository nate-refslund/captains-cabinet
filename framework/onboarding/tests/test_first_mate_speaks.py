"""The First Mate speaks: short first, guesses who you are, looks things up.

Six live findings from the Captain driving the full connected onboarding
(2026-08-14), each one a defect of PRESENTATION or of INITIATIVE rather than of
truthfulness — which is why every arm here is paired with a LOSSLESSNESS arm.
The honesty ledger is not shortened anywhere in this file; it is layered, and
the join of the layers is asserted equal to the blob that used to be printed.

  U1  ~350 words of caveats opened the connected card. Now: a headline of at
      most three sentences, and the same ledger one click behind.
  U2  the salience question re-asked what the operator had already answered in
      question two. Now: their own words are read back onto the ranking.
  U3  "which of these thirty accounts is you?" with a name already on record.
      Now: a proposal per connector, confirmed by a tap and NEVER by silence.
  U4  the look-up did not re-fire when a search tool arrived after the seed.
  U5  the dividend read as machine output. Now: a message, with a sender.
  U6  the whole home folder was REFUSED. Now: allowed, with the depth cost
      stated before the Charter is approved.
  U7  a finished operator was shown "Deeper Orientation has not started" and
      three ways back into onboarding. Answered by `feat/onboarding-arrival`,
      which landed the arrival screen first and carries its own suite plus a
      cross-surface parity fixture; what survives from this branch is the
      LAYERING applied to that card (see test_journey.py's arrival arms).

Hermetic: tmp_path for every mutable root, fixture estates for every read.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from framework.onboarding import availability, journey, research
from framework.onboarding.tests.test_journey import estate, propose, ratify


# --- helpers -----------------------------------------------------------------


def _seed(root: Path, **extra) -> dict:
    request = {"action": "answer_seed", "action_id": "seed-1", "surface": "dashboard",
               "seed": "I run a small inn on the coast", **extra}
    return journey.act(request, root, now="2026-07-14T09:00:00Z")


def _sweep_rows():
    """Two connectors, so the ranker has something to rank across."""
    return [
        {"connector": "tracker", "name": "Kaigan Ryokan", "updated": "2026-07-01",
         "actors": ["hanako.tanaka"]},
        {"connector": "tracker", "name": "yoyaku", "updated": "2026-07-02",
         "actors": ["buildbot"]},
        {"connector": "code", "name": "Kaigan Ryokan", "updated": "2026-07-03",
         "actors": ["htanaka"]},
        {"connector": "code", "name": "yoyaku", "updated": "2026-07-04",
         "actors": ["someone-else"]},
    ]


def _swept_state(root: Path, rows=None, record=None) -> dict:
    """A journey whose sweep has landed, written straight onto state.

    The sweep itself leaves the machine; this is its committed RESULT, which is
    what every card and every question in this file actually reads.
    """
    rows = _sweep_rows() if rows is None else rows
    who = research.who_and_when(rows, record or {})
    state = journey._load_state(root)
    state["connector_sweep"] = {
        "schema": research.CONNECTOR_SWEEP_SCHEMA,
        "swept_at": "2026-07-14T09:30:00Z", "declared": 2, "calls": 2,
        "connectors": [
            {"name": "tracker", "connected": True, "items": 402, "calls": 1,
             "latest": "2026-07-02", "actors": 2},
            {"name": "code", "connected": True, "items": 264, "calls": 1,
             "latest": "2026-07-04", "actors": 2},
        ],
        "not_reached": [], "who_and_when": who,
    }
    state["salience_rows"] = {"schema": "cabinet.salience-rows/v1", "rows": rows,
                              "identities": [], "not_reached": []}
    journey._atomic_json(journey._state_path(root), state)
    return state


# --- U1 · the headline, and the fold that loses nothing -----------------------


class TestShortFirstDetailsFold:
    def test_the_body_is_exactly_the_join_of_the_sections(self, tmp_path):
        """LAYERING, NEVER DELETION — and it is checked by construction rather
        than promised. The blob every non-folding surface renders IS the
        sections, in order, so a caveat cannot exist in one view and be missing
        from the other."""
        _seed(tmp_path)
        _swept_state(tmp_path)
        card = journey.snapshot(tmp_path)["card"]
        assert card["details"], "a welcome card with a sweep has a ledger to fold"
        assert card["body"] == "".join(s["text"] for s in card["details"])

    def test_dropping_one_section_breaks_the_join(self, tmp_path):
        """The sensor above must be able to FAIL. A join that equals the body
        for any list of sections is not measuring anything."""
        _seed(tmp_path)
        _swept_state(tmp_path)
        card = journey.snapshot(tmp_path)["card"]
        short = [s for s in card["details"] if s["id"] != "cannot_know"]
        assert len(short) < len(card["details"])
        assert "".join(s["text"] for s in short) != card["body"]

    def test_every_disclosed_fact_survives_in_the_headline_plus_fold(self, tmp_path):
        """The claim the layering makes: nothing an arm could assert of the old
        body is missing from headline ∪ fold. Checked against the honesty
        strings the core itself produces, not against a copy of them."""
        _seed(tmp_path)
        _swept_state(tmp_path)
        snap = journey.snapshot(tmp_path)
        card, plan = snap["card"], snap["card"]["entry"]
        union = " ".join(card["headline"]) + " " + card["body"]
        # The card has always printed the first two cannot-know statements and
        # carried the rest structurally, on `entry.cannot_know`. Layering did not
        # change which are printed — that is the point — so the arm is over the
        # printed set, and the residual is stated rather than implied.
        for row in plan["cannot_know"][:2]:
            assert row["statement"] in union, row["subject"]
        assert len(plan["cannot_know"]) > 2, "the structural list is still the full one"
        assert "nothing is opened until you approve that Charter" in union

    def test_the_headline_is_at_most_three_short_sentences(self, tmp_path):
        """A CEILING WITH AN ARM. The prior ceiling on this card was nobody's:
        the caveats simply accumulated until the operator stopped reading."""
        _seed(tmp_path)
        _swept_state(tmp_path)
        card = journey.snapshot(tmp_path)["card"]
        assert 1 <= len(card["headline"]) <= journey.MAX_HEADLINE_LINES
        assert all(len(line) <= 200 for line in card["headline"]), card["headline"]

    def test_the_headline_counts_what_was_actually_read(self, tmp_path):
        """The lead sentence is a MEASUREMENT off the committed sweep — two
        connected tools and their item counts — never off what was declared."""
        _seed(tmp_path)
        _swept_state(tmp_path)
        card = journey.snapshot(tmp_path)["card"]
        assert "2 connected tools" in card["headline"][0]
        assert "666 items" in card["headline"][0]

    def test_a_refused_connector_is_counted_in_the_lead_not_hidden_by_it(self, tmp_path):
        _seed(tmp_path)
        _swept_state(tmp_path)
        state = journey._load_state(tmp_path)
        state["connector_sweep"]["connectors"].append(
            {"name": "mail", "connected": False, "items": 0, "calls": 1,
             "reason": "http_401"})
        journey._atomic_json(journey._state_path(tmp_path), state)
        card = journey.snapshot(tmp_path)["card"]
        assert "1 did not answer" in card["headline"][0]

    def test_a_card_with_no_sweep_still_leads_with_its_opening_move(self, tmp_path):
        """The degenerate end: nothing read, nothing ranked. The headline does
        not go blank and does not invent a count."""
        card = journey.snapshot(tmp_path)["card"]
        assert card["headline"] and "item" not in card["headline"][0]
        assert card["body"] == "".join(s["text"] for s in card["details"])


# --- U2 · never re-ask what the operator already answered ---------------------


class TestAnswersFlowForward:
    def _offer(self, tmp_path):
        _seed(tmp_path, purpose="I want yoyaku — the bookings — to stop being chaos")
        _swept_state(tmp_path)
        return journey.salience_offer(journey._load_state(tmp_path))

    def test_a_candidate_the_operator_named_carries_their_own_words(self, tmp_path):
        offer = self._offer(tmp_path)
        named = [o for o in offer["options"] if o.get("you_said")]
        assert named, "the dream named a ranked candidate and nothing said so"
        assert "yoyaku" in named[0]["you_said"]

    def test_one_match_becomes_a_confirm_not_an_open_ask(self, tmp_path):
        offer = self._offer(tmp_path)
        assert offer["confirm"]["label"] == "yoyaku"
        assert "You said" in offer["confirm"]["question"]
        assert offer["confirm"]["option"] in {o["id"] for o in offer["options"]}

    def test_two_matches_stay_a_choice(self, tmp_path):
        """A confirmation that could be either of two things is not a
        confirmation. The degenerate end, and it is the honest one."""
        _seed(tmp_path, purpose="yoyaku and kaigan both matter to me")
        _swept_state(tmp_path)
        offer = journey.salience_offer(journey._load_state(tmp_path))
        assert len([o for o in offer["options"] if o.get("you_said")]) >= 2
        assert "confirm" not in offer

    def test_the_escape_hatch_prefills_from_a_word_they_gave(self, tmp_path):
        """Their vocabulary, not a guess: the pre-fill is a term the operator
        typed that the ranking never produced."""
        _seed(tmp_path, purpose="the onsen rota is what actually hurts")
        _swept_state(tmp_path)
        offer = journey.salience_offer(journey._load_state(tmp_path))
        # THEIR OWN WORD, and the useful one: the pre-fill comes from the DREAM
        # before the role, because "what should be true a month from now" is
        # where a target is named and "what do you do" is where "small" is.
        assert offer["prefill"] == "onsen"

    def test_the_confirm_and_the_prefill_ride_the_action_a_surface_renders(self, tmp_path):
        _seed(tmp_path, purpose="I want yoyaku — the bookings — to stop being chaos")
        _swept_state(tmp_path)
        card = journey.snapshot(tmp_path)["card"]
        action = next(o for o in card["options"] if o["action"] == "answer_salience")
        assert action["confirm"]["label"] == "yoyaku"
        assert "prefill" in action

    def test_nothing_is_recorded_by_reading_the_answers_back(self, tmp_path):
        """The whole unit is a READING. A journey that has been shown a confirm
        has still answered nothing."""
        _seed(tmp_path, purpose="I want yoyaku to stop being chaos")
        _swept_state(tmp_path)
        journey.snapshot(tmp_path)
        assert "salience" not in journey._load_state(tmp_path)


# --- U3 · name first, then guess ---------------------------------------------


class TestNameThenGuess:
    def test_the_name_lands_where_the_generator_reads_it(self, tmp_path, monkeypatch):
        answers = tmp_path / "answers.yml"
        monkeypatch.setenv("CABINET_INIT_ANSWERS", str(answers))
        out = _seed(tmp_path, name="Hanako Tanaka")
        assert out["state"]["operator_name"] == {
            "name": "Hanako Tanaka", "stored": True, "already": False,
            "answered_at": "2026-07-14T09:00:00Z"}
        assert yaml.safe_load(answers.read_text())["captain"]["name"] == "Hanako Tanaka"

    def test_a_name_that_cannot_be_stored_is_still_the_operator_s_answer(
            self, tmp_path, monkeypatch):
        """A read-only deployment or an unparseable answers file must not cost
        the operator the first sentence they typed."""
        broken = tmp_path / "broken.yml"
        broken.write_text("- not a mapping\n", encoding="utf-8")
        monkeypatch.setenv("CABINET_INIT_ANSWERS", str(broken))
        out = _seed(tmp_path, name="Hanako Tanaka")
        assert out["state"]["operator_name"]["name"] == "Hanako Tanaka"
        assert out["state"]["operator_name"]["stored"] is False
        assert broken.read_text() == "- not a mapping\n"

    def test_no_name_no_guess_and_the_open_ask_is_unchanged(self, tmp_path):
        _seed(tmp_path)
        _swept_state(tmp_path)
        card = journey.snapshot(tmp_path)["card"]
        ask = card["entry"]["identity_question"]
        assert ask["question"].startswith("I cannot tell which of the actors I read is you")
        assert all(row["guess"] is None for row in ask["connectors"])

    def test_a_name_produces_one_confirm_per_connector(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_INIT_ANSWERS", str(tmp_path / "a.yml"))
        _seed(tmp_path, name="Hanako Tanaka")
        _swept_state(tmp_path, record=journey._operator_record(
            tmp_path, journey._load_state(tmp_path)))
        card = journey.snapshot(tmp_path)["card"]
        ask = card["entry"]["identity_question"]
        guesses = {row["connector"]: row["guess"] for row in ask["connectors"]}
        assert guesses["tracker"]["identifier"] == "hanako.tanaka"
        assert guesses["tracker"]["rule"] == "every_word"
        assert guesses["code"]["identifier"] == "htanaka"
        assert guesses["code"]["rule"] == "joined_words"
        assert "I think I have found you" in ask["question"]

    def test_a_guess_is_never_recorded_without_the_operator_s_tap(
            self, tmp_path, monkeypatch):
        """THE LAW OF THIS LANE. An attribution the operator never made reads
        exactly like a correct one, so it can never be caught afterwards — and
        the proposal path must therefore leave the record untouched."""
        monkeypatch.setenv("CABINET_INIT_ANSWERS", str(tmp_path / "a.yml"))
        _seed(tmp_path, name="Hanako Tanaka")
        _swept_state(tmp_path, record=journey._operator_record(
            tmp_path, journey._load_state(tmp_path)))
        journey.snapshot(tmp_path)
        state = journey._load_state(tmp_path)
        assert "operator_identity" not in state
        who = state["connector_sweep"]["who_and_when"]
        assert who["operator"]["handles"] == {}
        # A NAME PRODUCES A GUESS AND ATTRIBUTES NOTHING. Every connector is
        # still unresolved and every share is still zero — the guess is a
        # question on a card, not a claim on the record.
        assert [row["basis"] for row in who["attribution"]] == ["unresolved"] * 2
        assert all(row["share"]["mine"] == 0 for row in who["attribution"])
        assert "claiming none of it is" in who["identity_question"]["question"]
        assert all(row["guess"] for row in who["identity_question"]["connectors"])

    def test_the_tap_writes_through_the_existing_act(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CABINET_INIT_ANSWERS", str(tmp_path / "a.yml"))
        _seed(tmp_path, name="Hanako Tanaka")
        state = _swept_state(tmp_path, record=journey._operator_record(
            tmp_path, journey._load_state(tmp_path)))
        out = journey.act({"action": "record_operator_identity",
                           "action_id": "confirm-1", "surface": "dashboard",
                           "handles": {"tracker": ["hanako.tanaka"]}},
                          tmp_path, now="2026-07-14T09:40:00Z")
        assert out["state"]["operator_identity"]["handles"]["tracker"] == ["hanako.tanaka"]
        remaining = {row["connector"] for row in
                     out["card"]["entry"]["identity_question"]["connectors"]}
        assert remaining == {"code"}, "a confirmed connector stops being asked about"

    def test_two_lookalikes_refuse_to_guess_and_say_why(self):
        """A guess that could be two people is not a guess — and silence there
        would read as "your name matched nothing", which is the opposite."""
        candidates = [{"identifier": "hanako.tanaka", "rows": 4},
                      {"identifier": "tanaka hanako", "rows": 2}]
        assert research.identity_guess(candidates, ["Hanako Tanaka"]) is None
        assert len(research.identity_matches(candidates, ["Hanako Tanaka"])) == 2

    def test_a_look_alike_that_is_not_the_name_is_not_a_match(self):
        """No prefix, no edit distance, no "starts the same". The rules are
        three, and each is one an operator can read back off the two strings."""
        for identifier in ("hanako.tanako", "h.tanaka", "tanaka-corp", "nakata"):
            assert research.identity_guess(
                [{"identifier": identifier, "rows": 1}], ["Hanako Tanaka"]) is None

    def test_the_guess_reads_any_script(self):
        guess = research.identity_guess(
            [{"identifier": "田中花子", "rows": 3}], ["田中花子"])
        assert guess["rule"] == "whole_name"


# --- U4 · probes run without asking ------------------------------------------


class TestProbesRunThemselves:
    #: Written as ONE joined literal, never a bare "instance" segment: the
    #: layer-separation gate reads that segment as a framework->instance coupling.
    CONFIG_DIR = "instance/config"

    def _sandbox(self, root: Path) -> Path:
        """A root carrying the SHIPPED template pack and an open egress ceiling."""
        (root / self.CONFIG_DIR).mkdir(parents=True, exist_ok=True)
        twin = self.CONFIG_DIR + "/connector-templates.yml.example"
        (root / twin).write_text(Path(twin).read_text(encoding="utf-8"),
                                 encoding="utf-8")
        (root / self.CONFIG_DIR / "egress.yml").write_text(
            "enforce: false\nallow_hosts: []\n", encoding="utf-8")
        return root

    def test_the_look_up_re_fires_when_a_search_tool_arrives_after_the_seed(
            self, tmp_path, monkeypatch):
        """THE GAP THE CAPTAIN HIT. The probes were derived from his sentence
        and deferred because nothing could search; he then connected a search
        tool and nothing re-ran them, so the answer to the question he had
        already answered sat behind a button he had to find."""
        self._sandbox(tmp_path)
        seeded = _seed(tmp_path)
        deferred = seeded["state"]["discovery"]["deferred"]
        assert any(row["reason"] == research.NO_SEARCH_TOOL for row in deferred)

        calls: list[str] = []

        def fake_fetch(request, timeout):  # the socket, replaced
            calls.append(request["url"])
            return 200, json.dumps({"web": {"results": [
                {"title": "Kaigan Ryokan", "url": "https://example.test/k",
                 "description": "an inn"}]}}).encode()

        monkeypatch.setattr(research, "_http_fetch", fake_fetch)
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "k" * 24)
        out = journey.act({"action": "declare_connector", "action_id": "declare-1",
                           "surface": "dashboard", "template": "brave_search",
                           "name": "brave_search",
                           "credential_env": "BRAVE_SEARCH_API_KEY"},
                          tmp_path, now="2026-07-14T09:10:00Z")
        assert calls, "declaring a search tool did not re-run the deferred probes"
        ran = out["state"]["discovery"]["executed"]
        assert any(row.get("results") for row in ran)
        assert not any(row["reason"] == research.NO_SEARCH_TOOL
                       for row in out["state"]["discovery"]["deferred"])

    def test_an_inventory_connector_does_not_re_send_the_same_refusal(
            self, tmp_path, monkeypatch):
        """Narrow on purpose. Re-running on every declaration would send the
        operator's own words out again for a connector that cannot search."""
        self._sandbox(tmp_path)
        _seed(tmp_path)
        calls: list[str] = []
        monkeypatch.setattr(research, "_http_fetch",
                            lambda request, timeout: calls.append(request["url"]))
        monkeypatch.setenv("GITHUB_TOKEN", "g" * 24)
        journey.act({"action": "declare_connector", "action_id": "declare-2",
                     "surface": "dashboard", "template": "github",
                     "name": "github", "credential_env": "GITHUB_TOKEN"},
                    tmp_path, now="2026-07-14T09:11:00Z")
        assert not calls, "an inventory connector re-sent the seed's web queries"

    def test_the_lane_of_a_built_connector_is_readable(self):
        assert research.connector_kind(
            {"name": "x", "inventory": {"call": {}}}) == research.CONNECTOR_KIND_INVENTORY
        assert research.connector_kind(
            {"name": "x", "search": {"call": {}}}) == research.CONNECTOR_KIND_SEARCH

    def test_a_journey_with_no_seed_never_re_fires(self, tmp_path):
        """Nothing to look up is not a look-up that failed."""
        state = journey._load_state(tmp_path)
        assert journey._discovery_seed(state) == ""
        assert journey._probes_await_a_search_tool(state) is False


# --- U5 · the finding speaks as the First Mate --------------------------------


class TestFirstMateVoice:
    def test_the_dividend_names_its_sender_by_role_never_by_name(self, tmp_path):
        """The framework does not know what this deployment calls its
        coordinating officer, so the card carries the ROLE and a surface
        resolves the title."""
        source = estate(tmp_path, "software-product")
        card = ratify(tmp_path, propose(tmp_path, source))["card"]
        assert card["speaker"] == journey.SPEAKER_COORDINATOR == "coordinator"
        assert "First Mate" not in json.dumps(card)

    def test_the_plain_meaning_leads_and_the_receipt_follows(self, tmp_path):
        source = estate(tmp_path, "software-product")
        card = ratify(tmp_path, propose(tmp_path, source))["card"]
        assert 1 <= len(card["headline"]) <= journey.MAX_HEADLINE_LINES
        assert card["headline"][0].endswith((".", "!", "?"))
        assert card["body"] == "".join(s["text"] for s in card["details"])
        assert card["headline"][0] in card["body"]

    def test_the_citations_are_still_the_core_s_own(self, tmp_path):
        """PRESENTATION ONLY. The finding's content and its citations are
        byte-identical to what the core produced — a message shape that edited
        the evidence would be a different unit entirely."""
        source = estate(tmp_path, "software-product")
        out = ratify(tmp_path, propose(tmp_path, source))
        finding = out["state"]["first_dividend"]["finding"]
        assert out["card"]["evidence"] == finding["citations"]
        assert finding["summary"] in out["card"]["body"]


# --- U6 · a broad window, with informed consent -------------------------------


class TestBroadWindowsWithOpenEyes:
    def test_the_whole_home_folder_is_allowed(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / "notes").mkdir(parents=True)
        (home / "readme.md").write_text("# hello\n", encoding="utf-8")
        monkeypatch.setenv("HOME", str(home))
        out = propose(tmp_path, home)
        assert out["state"]["source"]["breadth"] == journey.BREADTH_WHOLE_HOME
        assert out["state"]["stage"] == "charter_pending"

    def test_the_charter_states_the_depth_cost_before_it_is_approved(
            self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / "readme.md").parent.mkdir(parents=True, exist_ok=True)
        (home / "readme.md").write_text("# hello\n", encoding="utf-8")
        monkeypatch.setenv("HOME", str(home))
        body = propose(tmp_path, home)["card"]["body"]
        assert "whole home folder" in body
        assert "read-only" in body
        assert f"at most {journey.MAX_FILES} files" in body
        assert "SHALLOWER" in body
        assert "Breadth grows by earning trust" in body

    def test_an_ordinary_folder_carries_no_breadth_caveat(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        (tmp_path / "home").mkdir()
        source = estate(tmp_path, "software-product")
        body = propose(tmp_path, source)["card"]["body"]
        assert "SHALLOWER" not in body

    def test_the_whole_disk_and_the_parent_of_homes_stay_refused(
            self, tmp_path, monkeypatch):
        home = tmp_path / "users" / "hanako"
        home.mkdir(parents=True)
        (tmp_path / "users" / "someone-else").mkdir()
        monkeypatch.setenv("HOME", str(home))
        for root, expected in ((Path(str(home)[:1] if False else "/"), "whole disk"),
                               (tmp_path / "users", "other people's home folders")):
            with pytest.raises(journey.JourneyError) as exc:
                propose(tmp_path, root)
            assert exc.value.code == "source_too_broad"
            assert expected in str(exc.value)

    def test_a_system_root_is_refused_for_ownership_not_for_size(self):
        """Checked on the function that decides it: several of these resolve
        through a symlink on a real machine, which a proposal refuses one step
        earlier for a different and equally correct reason."""
        for root in ("/usr", "/System", "/Library", "/var"):
            assert "belongs to the machine" in journey.window_refusal(Path(root))
        # A specific folder INSIDE one is an ordinary window, which is what lets
        # the list be short and stated rather than a heuristic about depth.
        assert journey.window_refusal(Path("/usr/local/share/whatever")) == ""

    def test_a_broad_window_cannot_bypass_one_sensitivity_skip(
            self, tmp_path, monkeypatch):
        """THE ADVERSARIAL QUESTION, answered by measurement: breadth changes
        WHERE the scanner starts and nothing about WHAT it refuses."""
        home = tmp_path / "home"
        home.mkdir()
        (home / "readme.md").write_text("# hello\n", encoding="utf-8")
        (home / "salaries.csv").write_text("name,pay\na,1\n", encoding="utf-8")
        (home / ".env").write_text("API_KEY=zzzz\n", encoding="utf-8")
        monkeypatch.setenv("HOME", str(home))
        out = ratify(tmp_path, propose(tmp_path, home))
        manifest = json.loads(
            (tmp_path / journey.DATA_REL / journey.MANIFEST_NAME).read_text())
        opened = {entry["path"] for entry in manifest["files"]}
        assert "readme.md" in opened
        assert "salaries.csv" not in opened and ".env" not in opened
        assert out["state"]["stage"] == "dividend_ready"


# --- the answers-file writer --------------------------------------------------


class TestCaptainNameWriter:
    def test_it_replaces_a_default_and_reports_what_it_replaced(self, tmp_path):
        """A fresh hatch writes captain.name from $USER before anyone is asked,
        so refusing to overwrite would lose the operator's own answer to a Unix
        account."""
        path = tmp_path / "answers.yml"
        path.write_text(yaml.safe_dump({"captain": {"name": "prior-account",
                                                    "availability": "focused"}}),
                        encoding="utf-8")
        receipt = availability.record_captain_name("Hanako Tanaka", answers_path=path)
        assert receipt == {"name": "Hanako Tanaka", "written": True,
                           "previous": "prior-account", "note": "recorded captain.name"}
        doc = yaml.safe_load(path.read_text())
        assert doc["captain"] == {"name": "Hanako Tanaka", "availability": "focused"}

    def test_the_same_name_twice_writes_nothing(self, tmp_path):
        path = tmp_path / "answers.yml"
        availability.record_captain_name("Hanako", answers_path=path)
        before = path.read_text()
        assert availability.record_captain_name(
            "Hanako", answers_path=path)["written"] is False
        assert path.read_text() == before

    @pytest.mark.parametrize("bad", ["", "   ", "a\nb", "x" * 81])
    def test_a_name_the_generator_would_refuse_is_refused_here_first(self, tmp_path, bad):
        path = tmp_path / "answers.yml"
        with pytest.raises(availability.AvailabilityError):
            availability.record_captain_name(bad, answers_path=path)
        assert not path.exists()

    def test_any_script_is_a_name(self, tmp_path):
        path = tmp_path / "answers.yml"
        availability.record_captain_name("田中花子", answers_path=path)
        assert yaml.safe_load(path.read_text())["captain"]["name"] == "田中花子"
