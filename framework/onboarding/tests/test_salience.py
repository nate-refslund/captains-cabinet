"""The salience sweep: what it ranks, what it refuses, and what it discloses.

Every arm here was written against a MEASURED failure — the ranking was run on
a real 665-name estate across four connectors before any of this was pinned, and
each floor below exists because that run produced something wrong without it.
The degenerate ends are tested as hard as the happy path: an empty estate, a
dead clock, a coverage-less ranking and a one-connector name are where a
ranking quietly becomes an assertion nobody earned.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from framework.onboarding import research, salience


def _rows(*triples):
    return [{"connector": c, "name": n, "updated": u} for c, n, u in triples]


def _spread(connector, names, start_day=1):
    """Rows whose timestamps span enough distinct days to pass the clock check."""
    return [
        {"connector": connector, "name": name,
         "updated": f"2026-0{1 + (i + start_day) // 28}-{(i + start_day) % 28 + 1:02d}T09:00:00Z"}
        for i, name in enumerate(names)
    ]


# --- the primitive ----------------------------------------------------------


def test_a_hyphenated_name_and_a_solid_one_produce_the_same_token():
    """The fragment problem, measured: an estate writing ``north-bay-website``
    in one system and ``northbay.example`` in another produced ``north`` and
    ``bay`` — the OWNER's own name, ranked first and third by pure noise — and
    never produced ``northbay`` at all. The adjacent-pair compound is what lets
    the specific token exist to beat its own generic fragments."""
    tokens = salience.tokenize("north-bay-website")
    assert "northbay" in tokens
    assert "baywebsite" in tokens
    assert "northbay" in salience.tokenize("northbay.example")
    # and the short fragments are floored by length, not by a stopword list
    assert "bay" not in salience.tokenize("northbay.example")


def test_tokens_are_not_invented_for_an_empty_or_junk_name():
    for junk in (None, "", "   ", "a-b-c", 17, {"x": 1}):
        assert salience.tokenize(junk) == [] or all(
            len(t) >= 4 for t in salience.tokenize(junk)
        )


def test_the_words_in_a_name_survive_the_floor_that_the_ranking_applies():
    """THE SPLIT, AND WHY IT EXISTS. ``tokenize`` answers "what may be ranked";
    ``name_tokens`` answers "which words is this name made of". They were one
    function, and ``journey._window_binding`` — a comparison of an ANSWER against
    a FOLDER NAME, which is the second question — got the first one's answer:
    nothing at all for a short product, an acronym or an initialism, so a control
    meant to refuse one window refused every window.

    Both directions are pinned, because a floor lifted everywhere is the same
    defect from the other side: the ranker would then rank two-letter fragments.
    """
    assert salience.tokenize("BH") == []
    assert salience.name_tokens("BH") == ["bh"]
    assert salience.name_tokens("qsd-archive") == ["qsd", "archive", "qsdarchive"]
    # the compounds are still emitted, and are still what joins a hyphenated
    # name to a solid one
    assert "northbay" in salience.name_tokens("north-bay-website")
    # and a name with nothing in it invents nothing either way
    for junk in (None, "", "   ", 17, {"x": 1}):
        assert salience.name_tokens(junk) == [] or all(
            t.isalnum() for t in salience.name_tokens(junk)
        )


def test_the_ranking_vocabulary_is_exactly_the_floored_name_words():
    """The regression fence on the other side of the split. Every score, every
    cluster, every discount and the oracle itself read ``tokenize``, so a change
    that leaked the floor-free list into the ranker would re-rank a real estate
    silently. The relationship is pinned as an identity over a corpus of the
    shapes this ranker actually meets, rather than as a sentence in a docstring.
    """
    corpus = [
        "BH", "QSD archive", "north-bay-website", "northbay.example", "a-b-c-d",
        "Subitems of Blue Harbour", "org/thing", "acme_corp-2026", "12/34",
        "Green Lantern brief", "x", "", None, 17, "é-ü", "ab.cd", "A" * 80,
    ]
    for name in corpus:
        assert salience.tokenize(name) == [
            token for token in salience.name_tokens(name)
            if len(token) >= salience._MIN_TOKEN_LEN
        ], name


# --- the floors, and the proof that they are MEASURED -----------------------


def test_a_word_is_discounted_for_its_share_not_for_being_that_word():
    """The same string is furniture in one estate and a candidate in another.

    This is the whole reason there is no stopword list: ``widget`` counts for
    less when it labels a quarter of a connector's rows and counts fully when it
    does not, and no line of code knows what ``widget`` means.
    """
    furniture = _spread("tracker", [f"widget {i}" for i in range(10)]) + \
        _spread("repo", ["widget-core", "other-thing"], start_day=5)
    ranking = salience.rank(furniture)
    discounted = {row["token"]: row for row in ranking["discounted"]}
    assert "widget" in discounted
    assert discounted["widget"]["explained"] == 10  # the tracker's ten, and only those
    assert discounted["widget"]["unexplained"] == 1

    sparse = _spread("tracker", ["widget core"] + [f"unrelated {i}" for i in range(20)]) + \
        _spread("repo", ["widget-core", "other-thing"], start_day=5)
    ranking = salience.rank(sparse)
    assert "widget" not in {row["token"] for row in ranking["discounted"]}
    assert any("widget" in c["tokens"] for c in ranking["clusters"])


def test_a_discounted_word_is_still_reachable_and_never_removed():
    """THE RULE THAT WAS BROKEN TWICE, and the second time by the fix for the
    first. A floor that DROPS a token loses a correct answer in silence: the
    candidate stops existing and nothing downstream can name what went. So the
    discount is checked from the other end — every discounted token is still
    findable in the ranking, as a candidate or as a named non-candidate with its
    numbers, and never merely absent."""
    rows = _spread("tracker", [f"widget {i}" for i in range(10)]) + \
        _spread("repo", ["widget-core", "gadget-core"], start_day=5)
    ranking = salience.rank(rows)
    assert ranking["discounted"], "nothing was discounted; this fixture proves nothing"
    reachable = {t for c in ranking["clusters"] for t in c["tokens"]}
    reachable |= {t for c in ranking["not_candidates"] for t in c["tokens"]}
    missing = [d["token"] for d in ranking["discounted"] if d["token"] not in reachable]
    assert missing == [], f"discounted tokens vanished from the ranking: {missing}"


def test_a_token_living_almost_entirely_in_one_system_is_that_systems_structure():
    """Measured: ``tasks`` scored 34 with 29 hits inside one tracker — a filing
    word, not a thing that spans systems. Concentration catches it without
    knowing the word, and only above a volume floor so a small real entity is
    never called structure."""
    rows = _spread("tracker", [f"Tasks {i}" for i in range(12)]) + \
        _spread("repo", ["tasks-mcp"], start_day=9)
    discounted = {r["token"]: r["reason"] for r in salience.rank(rows)["discounted"]}
    assert discounted.get("tasks") in {"single_system_structure", "connector_furniture"}


def test_the_span_is_counted_over_what_the_filing_does_not_explain():
    """Measured on the live estate: one tracker's filing word reached rank 4 of
    51 on a three-connector span, two of whose connectors contributed two rows
    between them. A system whose own filing explains every occurrence there is
    not evidence that the name recurs ACROSS systems, so it does not vote in the
    span either — and the raw span is still reported beside it."""
    rows = _spread("tracker", [f"Tasks {i}" for i in range(12)]) + \
        _spread("repo", ["tasks-mcp"], start_day=9) + \
        _spread("db", ["tasks-db"], start_day=15)
    ranking = salience.rank(rows)
    carrying = [c for c in ranking["clusters"] if "tasks" in c["tokens"]]
    short = [c for c in ranking["not_candidates"] if "tasks" in c["tokens"]]
    seen = (carrying or short)[0]
    assert len(seen["connectors"]) == 3          # where the word appears
    assert len(seen["connectors_standing"]) == 2  # where it appears unexplained


def test_the_operators_own_name_is_demoted_and_never_deleted():
    """BOTH directions, because a delete floor passes the first one.

    Measured: the estate's owner name was ALSO the name of one of its real
    targets. A floor that removes identity tokens erases the target to
    suppress the noise. Demotion keeps both facts — the cluster stays visible,
    ranked below what it would be worth if it were not also the owner's name.
    """
    rows = _spread("tracker", ["Acme Website", "Acme Ops"]) + \
        _spread("repo", ["acme-website", "acme-tools"], start_day=6) + \
        _spread("db", ["acme-website-db"], start_day=12)
    plain = salience.rank(rows)
    demoted = salience.rank(rows, identities=["Acme Incorporated"])
    before = [c for c in plain["clusters"] if "acme" in c["tokens"]]
    after = [c for c in demoted["clusters"] if "acme" in c["tokens"]]
    assert len(before) == 1
    # NOT DELETED — still ranked, still carries its evidence
    assert len(after) == 1
    assert after[0]["demoted"] is True and after[0]["identity_match"] == ["acme"]
    assert after[0]["examples"]
    # and genuinely demoted: strictly lower score than without the identity
    assert after[0]["score"] < before[0]["score"]
    # A DEMOTION IS A PROPORTION, NOT AN ANNIHILATION. A factor of zero also
    # satisfies "still ranked, still carries its evidence" while sorting the
    # estate's own name below every candidate in the list — deletion by
    # arithmetic, wearing this arm's green tick. The score staying positive is
    # what makes the demoted candidate reachable at all.
    assert after[0]["score"] > 0


def test_a_name_in_one_connector_is_never_a_candidate():
    """Recurrence ACROSS systems is the entire signal. A 6,000-row dump that
    lives in one system self-excludes with no size rule anywhere — item counts
    never enter the score."""
    rows = _spread("tracker", [f"Contacts {i}" for i in range(3)] + ["Solo Thing"])
    assert all(len(c["connectors"]) >= 2 for c in salience.rank(rows)["clusters"])
    assert "solo" not in {c["label"] for c in salience.rank(rows)["clusters"]}


# --- the clock, which is a sensor and is tested as one ----------------------


def test_a_clock_that_does_not_discriminate_is_refused_and_says_so():
    """Measured: one connector's twenty rows resolved THREE distinct days —
    control-plane metadata, not use. Multiplying a score by a constant is a
    rename, not a ranking, so the clock is refused and the refusal is reported.
    """
    dead = [
        {"connector": "db", "name": f"proj-{i}", "updated": "2026-07-01T00:00:00Z"}
        for i in range(10)
    ] + [
        {"connector": "db", "name": f"proj-{i}", "updated": "2026-07-02T00:00:00Z"}
        for i in range(10, 20)
    ]
    verdict = salience.admissible_clocks(salience.normalize_rows(dead))["db"]
    assert verdict["admitted"] is False
    assert verdict["reason"] == "clock_does_not_discriminate"
    assert verdict["distinct_days"] == 2

    alive = _spread("db", [f"proj-{i}" for i in range(20)])
    assert salience.admissible_clocks(salience.normalize_rows(alive))["db"]["admitted"]


def test_a_clock_missing_from_most_rows_is_refused_too():
    rows = [{"connector": "repo", "name": f"r-{i}", "updated": None} for i in range(9)]
    rows.append({"connector": "repo", "name": "r-9", "updated": "2026-07-01T00:00:00Z"})
    verdict = salience.admissible_clocks(salience.normalize_rows(rows))["repo"]
    assert verdict["admitted"] is False
    assert verdict["reason"] == "clock_absent_on_most_rows"


def test_the_refused_clock_actually_changes_the_score_it_is_refused_from():
    """A disclosure nobody wired to the arithmetic is decoration. A cluster
    living only in a dead-clock connector scores at the neutral band — neither
    rewarded for a fake freshness nor punished for the connector's defect."""
    dead_stamp = "2026-07-28T00:00:00Z"
    rows = [{"connector": "db", "name": f"acme-{i}", "updated": dead_stamp}
            for i in range(6)]
    rows += [{"connector": "cache", "name": f"acme-{i}", "updated": dead_stamp}
             for i in range(6)]
    ranking = salience.rank(rows, now="2026-07-28T12:00:00Z")
    cluster = [c for c in ranking["clusters"] if c["label"] == "acme"][0]
    assert cluster["recency_measured"] is False
    assert cluster["recency_weight"] == salience._RECENCY_UNKNOWN
    # the same rows with a discriminating clock DO earn the fresh band
    live = salience.rank(
        _spread("db", [f"acme-{i}" for i in range(6)]) +
        [{"connector": "cache", "name": "acme-x", "updated": "2026-07-27T00:00:00Z"}] +
        _spread("cache", [f"acme-{i}" for i in range(6)], start_day=3),
        now="2026-07-28T12:00:00Z",
    )
    assert any(c["recency_measured"] for c in live["clusters"])


# --- clustering and the answered alias --------------------------------------


def test_two_words_that_always_appear_together_are_one_candidate():
    rows = _spread("tracker", ["Blue Harbour plan", "Blue Harbour ops"]) + \
        _spread("repo", ["blue-harbour"], start_day=7)
    ranking = salience.rank(rows)
    labels = [c["label"] for c in ranking["clusters"]]
    assert len([lbl for lbl in labels if lbl in {"blue", "harbour", "blueharbour"}]) == 1


def test_an_answered_alias_joins_two_candidates_the_names_could_not():
    """The measured limit of names-only ranking, and its repair.

    On the real estate the entity spanning the MOST connectors was scored as two
    three-connector candidates because its tracker and its code call it
    different words. No string function joins them. The operator's answer does —
    and the merged candidate then outranks both halves, which is the loop
    closing.
    """
    rows = _spread("tracker", ["Quay Tickets", "Quay Board"]) + \
        _spread("repo", ["v0-harbour-lantern", "harbour.lantern.site"], start_day=5) + \
        _spread("db", ["harbour-lantern"], start_day=9) + \
        _spread("host", ["quay-insights"], start_day=13)
    cold = salience.rank(rows)
    cold_labels = [c["label"] for c in cold["clusters"]]
    assert "quay" in cold_labels and "harbourlantern" in cold_labels
    split_score = max(c["score"] for c in cold["clusters"]
                      if c["label"] in {"quay", "harbourlantern"})

    warm = salience.rank(rows, aliases=[["quay", "harbour-lantern"]])
    merged = [c for c in warm["clusters"] if "quay" in c["tokens"]]
    assert len(merged) == 1
    assert len(merged[0]["connectors"]) == 4
    assert merged[0]["score"] > split_score


def test_an_alias_only_merges_what_the_ranking_already_named():
    """PAID REGRESSION. The escape hatch takes free text, so an operator writes
    a sentence — "Quay, which the repos CALL harbour-lantern". Matching
    that against every token in every cluster pulled in an unrelated cluster
    whose rows contained the word "call", and the junk ranked second. Only
    cluster LABELS may be merged; a word matching nothing is a target, not a
    merge."""
    rows = _spread("tracker", ["Quay Tickets"]) + \
        _spread("repo", ["v0-harbour-lantern", "network-call-tracking"], start_day=4) + \
        _spread("db", ["harbour-lantern", "call-tracking-db"], start_day=8) + \
        _spread("host", ["quay-insights", "call-tracking"], start_day=12)
    sentence = ["Quay", "which the repos call harbour-lantern"]
    warm = salience.rank(rows, aliases=[sentence])
    merged = [c for c in warm["clusters"] if "quay" in c["tokens"]][0]
    assert "quay" in merged["tokens"] and "harbourlantern" in merged["tokens"]
    # the innocent bystander did NOT get absorbed by the word "call"
    assert "calltracking" not in merged["tokens"]
    assert any("call" in c["tokens"] or "calltracking" in c["tokens"]
               for c in warm["clusters"] if c is not merged)


def _three_names_for_one_thing():
    """A LOPSIDED estate: three candidates of deliberately different weights.

    Row counts are 4 / 3 / 2 so no symmetric rule can produce the right answer
    by accident — the union keeps the WIDEST name, which is ``alpha`` and is not
    the name the second answer is anchored on. That asymmetry is the whole point
    of the fixture: it is what makes the second answer fall on the floor when
    answers are applied one at a time instead of being unioned first.
    """
    return (
        _rows(("tracker", "alpha-plan", None), ("tracker", "alpha-ops", None),
              ("repo", "alpha-web", None), ("repo", "alpha-api", None),
              ("docs", "bravo-handbook", None), ("docs", "bravo-runbook", None),
              ("db", "bravo-store", None),
              ("host", "charlie-live", None), ("queue", "charlie-jobs", None))
    )


def test_two_answers_about_one_thing_are_one_answer():
    """THE ANSWER THAT WAS SILENTLY LOST. A union keeps ONE of the names it
    joined, so an operator who says "alpha is bravo" and later "bravo is
    charlie" leaves the second answer pointed at a label the first answer
    consumed — and applying answers one at a time drops it on the floor while
    the shortlist looks fine.

    Identity is transitive because that is what "the same thing" MEANS, not
    because two strings resembled each other: nothing here compares names, the
    components are built from the operator's own answers.
    """
    rows = _three_names_for_one_thing()
    cold = {c["label"] for c in salience.rank(rows)["clusters"]}
    assert {"alpha", "bravo", "charlie"} <= cold

    warm = salience.rank(rows, aliases=[["alpha", "bravo"], ["bravo", "charlie"]])
    carrying = [c for c in warm["clusters"]
                if {"alpha", "bravo", "charlie"} <= set(c["tokens"])]
    assert len(carrying) == 1, "the second answer was dropped"
    assert len(carrying[0]["connectors"]) == 6
    assert not [c for c in warm["clusters"] if c is not carrying[0]
                and {"bravo", "charlie"} & set(c["tokens"])]

    # ORDER-INDEPENDENT, which is the property that makes it a closure rather
    # than a lucky sequence: the same answers in the other order, same result.
    other_way = salience.rank(rows, aliases=[["charlie", "bravo"], ["bravo", "alpha"]])
    assert [c["tokens"] for c in other_way["clusters"]] == \
        [c["tokens"] for c in warm["clusters"]]


def test_an_answer_naming_one_candidate_or_none_joins_nothing():
    """THE DEGENERATE END of the union. A typed word matching a single candidate
    is a target, not a merge, and a word matching none is neither — both leave
    the ranking exactly as the names left it rather than quietly forming a
    one-member group that changes a label."""
    rows = _three_names_for_one_thing()
    cold = salience.rank(rows)
    for nothing in ([["alpha"]], [["nothing-here"]], [[]], [["alpha", "alpha"]]):
        warm = salience.rank(rows, aliases=nothing)
        assert [c["tokens"] for c in warm["clusters"]] == \
            [c["tokens"] for c in cold["clusters"]]


def test_a_learned_merge_is_appended_deduped_and_never_overwritten():
    """The store is what makes an answer outlive the answer after it. Appending
    is the whole contract; the dedup is there because a loop that re-offers the
    same estate would otherwise grow one row per re-confirmation."""
    first = salience.learn_merge(None, ["alpha", "bravo"], now="2026-07-30T00:00:00Z",
                                 answer="alpha")
    assert first["schema"] == salience.SALIENCE_MERGE_SCHEMA
    assert first["groups"][0]["labels"] == ["alpha", "bravo"]

    second = salience.learn_merge(first, ["charlie", "delta"],
                                  now="2026-07-31T00:00:00Z", answer="charlie")
    assert [row["labels"] for row in second["groups"]] == \
        [["alpha", "bravo"], ["charlie", "delta"]]

    # the same fact answered twice, in the other order, is still one row
    again = salience.learn_merge(second, ["bravo", "alpha"],
                                 now="2026-08-01T00:00:00Z")
    assert len(again["groups"]) == 2

    # and a group that joins nothing never enters the record
    assert salience.learn_merge(again, ["alpha"], now="x")["groups"] == \
        again["groups"]
    assert salience.learn_merge(None, [], now="x")["groups"] == []
    # a padded name is the same name — otherwise it is stored in a shape that
    # can never match a label and the row is a merge that will never fire
    assert salience.learn_merge(again, [" alpha ", "bravo\n"],
                                now="x")["groups"] == again["groups"]
    assert salience.learned_merges({"groups": [{"labels": [" a b ", "c d "]}]}) == \
        [["a b", "c d"]]


def test_reading_the_store_survives_a_row_it_cannot_use():
    """READ FORGIVINGLY, because this is read on every render of the operator's
    card: a card that refuses to draw over one unusable historical row takes the
    whole surface down to protect an ordering."""
    assert salience.learned_merges(None) == []
    assert salience.learned_merges({"groups": "not a list"}) == []
    assert salience.learned_merges({"groups": [
        {"labels": ["alpha", "bravo"]},
        {"labels": ["only-one"]},
        {"labels": []},
        "not a row",
        {"no_labels": True},
    ]}) == [["alpha", "bravo"]]


# --- the ask, and its degenerate ends ---------------------------------------


def test_the_merge_question_reaches_past_the_cut_and_echoes_what_it_learned():
    """THE SPLIT IS USUALLY NOT ON SCREEN. Measured, one entity stood as five
    candidates at ranks 6, 11, 21, 33 and 34 — so a merge answerable only over
    the shown three cannot reach the split it exists to fix. Every ranked
    candidate is nameable, and what has already been learned is said back,
    because once two candidates are one the second name is gone from the
    shortlist and that is indistinguishable from the answer being ignored.
    """
    ranking = salience.rank(_three_names_for_one_thing())
    ask = salience.offer(ranking, top=1,
                         learned=[["alpha", "bravo"], ["short"]])
    shown = [o["id"] for o in ask["options"]
             if o["id"] != salience.ESCAPE_OPTION_ID]
    nameable = [c["id"] for c in ask["merge"]["candidates"]]
    assert len(shown) == 1 and len(nameable) == len(ranking["clusters"]) >= 3
    assert set(shown) < set(nameable)
    assert ask["merge"]["field"] == "same_as"
    # echoed back — and a stored group that joins nothing is not echoed as one
    assert ask["merge"]["learned"] == [{"labels": ["alpha", "bravo"]}]


def test_an_offer_refuses_to_exist_without_a_record_of_what_was_read():
    """The unearned clean negative, structurally prevented. A ranking that never
    recorded its coverage cannot become an offer — it would present a shortlist
    as the result of a survey nobody ran."""
    with pytest.raises(salience.SalienceError) as excinfo:
        salience.offer({"schema": salience.SALIENCE_SCHEMA, "clusters": [],
                        "coverage": {}})
    assert excinfo.value.code == "coverage_missing"
    with pytest.raises(salience.SalienceError):
        salience.offer({"schema": "something-else", "coverage": {"connectors": ["a"]}})
    with pytest.raises(salience.SalienceError):
        salience.offer(salience.rank([]))


def test_the_escape_hatch_is_present_even_when_the_ranking_found_nothing():
    """Measured on the real estate, the operator's own answers landed at ranks
    1, 4 and 8 of 47 — so an offer without a way to say "none of these" converts
    a likely miss into a wrong answer the operator had to accept. It is never
    conditional on the ranking's confidence."""
    rows = _spread("tracker", ["Alpha thing"]) + _spread("repo", ["alpha-thing"], start_day=4)
    offer = salience.offer(salience.rank(rows), top=0)
    assert [o["id"] for o in offer["options"]] == [salience.ESCAPE_OPTION_ID]
    assert offer["options"][0]["input"] == "seed"


def test_the_offer_states_the_cut_the_floors_and_the_dead_clock():
    """The sentence the operator actually reads. Without it a three-item list
    reads as a survey of everything."""
    rows = _spread("tracker", [f"Alpha {i}" for i in range(4)] +
                   [f"Beta {i}" for i in range(4)] + [f"Gamma {i}" for i in range(4)] +
                   [f"Delta {i}" for i in range(4)])
    rows += _spread("repo", ["alpha-x", "beta-x", "gamma-x", "delta-x"], start_day=6)
    rows += [{"connector": "db", "name": f"alpha-{i}", "updated": "2026-07-01T00:00:00Z"}
             for i in range(8)]
    offer = salience.offer(salience.rank(rows), top=2,
                           not_reached=["one workspace refused the read"])
    line = offer["not_reached"]
    assert "showing the top 2" in line
    assert "Ranked names only, never contents" in line
    assert "no usable last-touched clock on db" in line
    assert "one workspace refused the read" in line
    assert line.endswith(".")


def test_every_candidate_carries_the_names_that_produced_it():
    """A score the operator cannot audit is not evidence; the names are."""
    rows = _spread("tracker", ["Blue Harbour plan"]) + \
        _spread("repo", ["blue-harbour", "blue-harbour-api"], start_day=5) + \
        _spread("db", ["blue-harbour-db"], start_day=9)
    offer = salience.offer(salience.rank(rows))
    candidate = offer["options"][0]
    assert "blue-harbour" in candidate["why"]
    assert "tracker:" in candidate["why"] and "repo:" in candidate["why"]
    assert candidate["aliases"]


def test_an_empty_estate_ranks_nothing_and_pretends_nothing():
    ranking = salience.rank([])
    assert ranking["clusters"] == []
    assert ranking["coverage"]["rows"] == 0
    assert ranking["coverage"]["connectors"] == []
    for junk in (None, [None, 17, {}, {"connector": "x"}, {"name": "y"}]):
        assert salience.rank(junk)["clusters"] == []


# --- the standing requirement -----------------------------------------------


_KIND_WORDS = (
    "product", "project", "client", "customer", "campaign", "case",
    "vessel", "shelf", "collection", "account_kind", "entity_type",
)


def test_the_module_contains_no_taxonomy_of_entity_kinds():
    """THE HARD REQUIREMENT, checked mechanically rather than promised.

    "For a salesperson it could be clients, for a librarian something entirely
    else." The moment a kind word appears in an identifier or a literal, the
    ranker is right for one estate and wrong for the next — this program deleted
    three hand-maintained lists in a single week for exactly that reason. Prose
    may DISCUSS the kinds it refuses to encode, so docstrings are excluded and
    code is not.
    """
    source = Path(salience.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in docstrings:
                continue
            for word in _KIND_WORDS:
                if word in node.value.lower():
                    offenders.append((word, node.value[:60]))
        if isinstance(node, ast.Name):
            for word in _KIND_WORDS:
                if word in node.id.lower():
                    offenders.append((word, node.id))
    assert offenders == [], f"entity-kind taxonomy leaked into code: {offenders}"


def test_the_kind_word_guard_would_actually_fire():
    """The guard above is a sensor; this is the sensor's own both-directions
    check. A guard that cannot fail is a disabled test wearing a green tick."""
    tree = ast.parse('X = "our product list"\n')
    hits = [
        word for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        for word in _KIND_WORDS if word in node.value.lower()
    ]
    assert hits == ["product"]


def test_a_credentialed_sweep_must_consult_the_egress_ceiling_first(tmp_path):
    """FAIL-CLOSED, and the reason is not hypothetical: this deployment's
    ceiling is ``enforce: true`` with an empty allow list, so a sweep that did
    not ask would discover it as a wall of failures instead of a disclosed
    not-reached line."""
    # The ceiling's location has ONE home (``research._EGRESS_REL``); naming it
    # again here would be a second answer to where the switch lives, and the
    # layer-separation gate is right to refuse a framework file that hardcodes
    # a deployment path.
    ceiling = tmp_path / research._EGRESS_REL
    ceiling.parent.mkdir(parents=True)
    assert salience.sweep_ceiling(tmp_path)["permitted"] is False
    assert salience.sweep_ceiling(tmp_path)["reason"] == "egress_config_absent"
    ceiling.write_text("enforce: true\nallow_hosts: []\n", encoding="utf-8")
    closed = salience.sweep_ceiling(tmp_path)
    assert closed["permitted"] is False
    assert closed["reason"] == "egress_closed_no_allowed_hosts"
    ceiling.write_text(
        "enforce: true\nallow_hosts: [api.example.test]\n", encoding="utf-8")
    assert salience.sweep_ceiling(tmp_path)["permitted"] is True


def test_rows_come_from_what_was_already_granted_and_nothing_else():
    """No credential lives in this module. Rows arrive from a block someone
    already lawfully produced, or from probes this journey already ran."""
    rows, identities = salience.rows_from_state({
        "salience_rows": {"rows": _rows(("tracker", "Alpha", None)),
                          "identities": ["Acme"]},
        "connector_probes": {"connected": [
            {"kind": "repo", "name": "repo:blue-harbour", "connected": True},
            {"kind": "web", "name": "web", "connected": True},
            {"kind": "tracker_export", "name": "tracker_export:a/b/board.csv"},
        ]},
    })
    names = {(r["connector"], r["name"]) for r in rows}
    assert ("repo", "blue-harbour") in names
    assert ("tracker_export", "board.csv") in names
    assert not any(r["connector"] == "web" for r in rows)
    assert identities == ["Acme"]
    assert salience.rows_from_state({}) == ([], [])
    assert salience.rows_from_state(None) == ([], [])


def test_the_owner_stamped_on_a_row_is_an_identity_string_too():
    """UNSENSORED UNTIL NOW, and load-bearing. A connector's identity call asks
    the CREDENTIAL who it is; the owner stamped on each row says who the estate
    belongs to, and measured on a live estate those were different words — the
    owner of most of one connector's rows never entered the demotion set, so the
    estate's own name was read as a candidate rather than as its own name.

    Removing this harvest left the whole salience suite green while changing the
    live outcome, which is a disabled sensor by this program's own definition.
    Both properties are pinned here: the owner ARRIVES, and it arrives ONCE — the
    field is read per ROW, so an estate stamping one owner across hundreds of
    rows must not hand its caller hundreds of copies of one fact.
    """
    rows = [{"connector": "repo", "name": f"quay-{i}", "actors": ["Harbour Trust"]}
            for i in range(40)]
    rows.append({"connector": "repo", "name": "quay-x",
                 "actors": ["Harbour Trust", "Lantern Works"]})
    _, identities = salience.rows_from_state(
        {"salience_rows": {"rows": rows, "identities": ["Given Name"]}})
    assert identities == ["Given Name", "Harbour Trust", "Lantern Works"]

    # and it reaches the ranking as a DEMOTION, which is the only reason the
    # harvest exists: the same string is the estate's own name and a real target
    estate = _spread("tracker", ["Harbour Trust plan", "Harbour Trust ops"]) + \
        _spread("repo", ["harbour-trust-site"], start_day=6)
    stamped = [dict(row, actors=["Harbour Trust"]) for row in estate]
    plain = salience.rank(estate)
    rows_out, harvested = salience.rows_from_state(
        {"salience_rows": {"rows": stamped}})
    demoted = salience.rank(rows_out, identities=harvested)
    carrying = [c for c in demoted["clusters"] if "harbour" in c["tokens"]]
    assert carrying and carrying[0]["demoted"] is True
    assert carrying[0]["score"] < [c for c in plain["clusters"]
                                   if "harbour" in c["tokens"]][0]["score"]
