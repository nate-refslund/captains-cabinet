"""The oracle, and the two things the ranking was reported to do and did not.

WHY THE ESTATE IS SYNTHESISED HERE. A ranking can only be graded against a
known-good answer, and the only known-good answers this program has are one
operator's — three names on one estate. An arm pinned to those three would pass
by reproducing a list, which is the failure this whole module exists to avoid:
right for one estate, a fiction for the next. So the estate is GENERATED, over
many seeds, with the answer PLANTED by construction; the test asserts that the
mechanism finds what was planted, never that it reproduces anything. Nothing
below contains a real name, a real word or a domain-specific noun, and the
generator is deliberately built from nonsense syllables so that no property can
accidentally rest on English, on Danish, or on what any of the strings mean.

The arms come in both directions, because an oracle that cannot report a miss
is a rubber stamp: the same generator is used to build estates where the planted
answer is genuinely unreachable, and the oracle is required to say so.
"""
from __future__ import annotations

import random

import pytest

from framework.onboarding import salience

_SYLLABLES = ("ka", "ro", "mi", "tu", "zen", "vo", "lu", "pex", "dra", "nio",
              "fal", "qui", "sem", "byr", "tok", "wex", "gan", "hul")


def _word(rng: random.Random, taken: set[str]) -> str:
    """A pronounceable nonsense word of ranking length, never repeated."""
    while True:
        word = "".join(rng.choice(_SYLLABLES) for _ in range(3))
        if word not in taken and len(word) >= 6:
            taken.add(word)
            return word


#: Every row is stamped inside one recency band and across enough distinct days
#: for every clock to be admitted. Deliberate: a spread of ages would make the
#: arms below depend on which random rows happened to be freshest, and they are
#: about the discount and the join, not about recency. The recency mechanism has
#: its own arms elsewhere and this generator must not silently re-test it.
_NOW = "2026-09-30T00:00:00Z"


def _day(i: int) -> str:
    return f"2026-09-{24 + i % 6:02d}T09:00:00Z"


def _estate(seed: int, *, connectors: int = 4, per_connector: int = 24,
            plant_spans: tuple[tuple[int, ...], ...] = ((0, 1), (2, 3))) -> dict:
    """One synthetic estate with a known answer planted in it.

    * every connector gets its own FURNITURE word on more than a quarter of its
      rows, and that word also appears twice in two other connectors — so it is
      a genuine cross-connector competitor and would out-rank the plant if its
      occurrences were not discounted;
    * the ANSWER is planted as two fragments wearing unrelated words, each
      recurring in the connectors named by ``plant_spans``, so their union is
      the widest-spanning thing in the estate and neither fragment alone is;
    * everything else is unique noise.
    """
    rng = random.Random(seed)
    taken: set[str] = set()
    names = [f"conn{i}" for i in range(connectors)]
    furniture = [_word(rng, taken) for _ in names]
    fragments = [_word(rng, taken) for _ in plant_spans]
    rows: list[dict] = []
    stamp = 0
    for index, connector in enumerate(names):
        for i in range(per_connector):
            stamp += 1
            body = _word(rng, taken)
            head = f"{furniture[index]}-" if i < per_connector // 2 else ""
            rows.append({"connector": connector, "name": f"{head}{body}",
                         "updated": _day(stamp)})
        # the furniture word leaks into two other connectors, which is what
        # makes it rankable at all
        for other in range(connectors):
            if other == index:
                continue
            stamp += 1
            rows.append({"connector": names[other],
                         "name": f"{furniture[index]}-{_word(rng, taken)}",
                         "updated": _day(stamp)})
    for fragment, span in zip(fragments, plant_spans):
        for where in span:
            stamp += 1
            rows.append({"connector": names[where],
                         "name": f"{fragment}-{_word(rng, taken)}",
                         "updated": _day(stamp)})
    rng.shuffle(rows)
    return {"rows": rows, "fragments": fragments, "furniture": furniture,
            "connectors": names}


def _joiner(labels):
    """A stand-in for judgment: it is HANDED the estate's own names and answers
    with the group it recognises. The real one is a model reading the same
    payload; what is pinned here is the contract between them, not the model."""
    def join(proposal):
        assert proposal["schema"] == salience.SALIENCE_JOIN_SCHEMA
        offered = {c["label"] for c in proposal["candidates"]}
        return [[label for label in labels if label in offered]]
    return join


def _label_carrying(ranking, token):
    for cluster in ranking["clusters"]:
        if token in cluster["tokens"]:
            return cluster["label"]
    return None


# --- the oracle finds the operator's OWN answer, on any estate ---------------


@pytest.mark.parametrize("seed", range(12))
def test_judgment_joins_the_split_answer_and_the_oracle_finds_it(seed):
    """THE FIRST REPORTED-AND-FALSE CLAIM, pinned so it cannot be reported again.

    Measured on the live estate: one entity was ranked as FIVE candidates at
    ranks 6, 11, 21, 33 and 34 because each system writes its name differently,
    and a report said they had merged. They had not — nothing had asked anyone.
    Names cannot join them and no stemming table may try; a reader looking at
    the names can, and that reader is the ``join``.
    """
    estate = _estate(seed)
    cold = salience.rank(estate["rows"], now=_NOW)
    labels = [_label_carrying(cold, fragment) for fragment in estate["fragments"]]
    assert all(labels), "the generator failed to plant two rankable fragments"
    assert labels[0] != labels[1], "the plant merged on its own; nothing to join"

    joined = salience.rank(estate["rows"], join=_joiner(labels),
                           now=_NOW)
    graded = salience.check(joined, [estate["fragments"][0]], top=3)
    assert graded["verdict"] == "all_offered", graded
    assert graded["answers"][0]["position"] == 1, graded["answers"][0]
    # and it is ONE candidate now, spanning every connector the fragments did
    winner = joined["clusters"][0]
    assert set(winner["connectors"]) == set(estate["connectors"])
    assert all(fragment in winner["tokens"] for fragment in estate["fragments"])


@pytest.mark.parametrize("seed", range(12))
def test_the_furniture_word_is_discounted_and_still_reachable(seed):
    """THE SECOND REPORTED-AND-FALSE CLAIM. Three identity-shaped candidates were
    reported demoted and were in fact removed outright, with the reason
    ``connector_furniture`` — the same removal that, measured on the live estate,
    deletes a correct answer because an owner's name and a real target are the
    same string. Discounting keeps both facts; deleting keeps neither, and
    reports nothing."""
    estate = _estate(seed)
    ranking = salience.rank(estate["rows"], now=_NOW)
    discounted = {row["token"] for row in ranking["discounted"]}
    assert set(estate["furniture"]) <= discounted, "the noise was not even measured"
    reachable = {t for c in ranking["clusters"] for t in c["tokens"]}
    reachable |= {t for c in ranking["not_candidates"] for t in c["tokens"]}
    gone = [word for word in estate["furniture"] if word not in reachable]
    assert gone == [], f"discounted words were deleted, not demoted: {gone}"


@pytest.mark.parametrize("seed", range(12))
def test_the_answer_outranks_the_noise_that_looks_like_it(seed):
    """The furniture word spans three connectors and out-volumes the plant; the
    plant spans four and is explained by nothing. If the discount did not bite,
    the estate's filing structure would be the shortlist."""
    estate = _estate(seed)
    labels = [_label_carrying(salience.rank(estate["rows"], now=_NOW),
                              fragment) for fragment in estate["fragments"]]
    ranking = salience.rank(estate["rows"], join=_joiner(labels),
                            now=_NOW)
    order = [c["label"] for c in ranking["clusters"]]
    answer = order.index(_label_carrying(ranking, estate["fragments"][0]))
    for word in estate["furniture"]:
        noise = _label_carrying(ranking, word)
        assert noise is None or order.index(noise) > answer, word


# --- and it reports a miss, which is the half that makes it an oracle --------


def test_an_answer_living_in_one_system_is_reported_lost_not_ranked_low():
    """The distinction the whole instrument exists to draw. A name that recurs
    inside a single system is not a candidate here and never will be —
    recurrence ACROSS systems is the signal — and an operator hunting for it is
    owed "this could not be ranked", not a shrug about it being far down."""
    estate = _estate(3, plant_spans=((0,), (1,)))
    ranking = salience.rank(estate["rows"], now=_NOW)
    graded = salience.check(ranking, [estate["fragments"][0]], top=3)
    assert graded["verdict"] == "lost"
    assert graded["answers"][0]["verdict"] == "not_a_candidate"
    assert graded["answers"][0]["position"] is None
    assert "one system" in graded["answers"][0]["why"]


def test_an_answer_the_sweep_never_saw_is_reported_as_never_seen():
    estate = _estate(5)
    ranking = salience.rank(estate["rows"], now=_NOW)
    graded = salience.check(ranking, ["zzzzqqqq-nothing-like-this"], top=3)
    assert graded["verdict"] == "lost"
    assert graded["answers"][0]["verdict"] == "never_seen"


def test_the_oracle_separates_below_the_cut_from_lost():
    """Two failures that look identical in a shortlist and need opposite fixes:
    one is a cut that is too short, the other is an answer the mechanism cannot
    represent at all."""
    estate = _estate(7)
    ranking = salience.rank(estate["rows"], now=_NOW)
    deep = ranking["clusters"][-1]["label"]
    graded = salience.check(ranking, [deep], top=1)
    assert graded["verdict"] == "reached_but_below_the_cut"
    assert graded["answers"][0]["verdict"] == "below_the_cut"
    assert graded["answers"][0]["position"] == len(ranking["clusters"])


def test_the_oracle_refuses_anything_that_is_not_a_ranking():
    with pytest.raises(salience.SalienceError):
        salience.check({"schema": "something-else"}, ["x"])


def test_the_oracle_grades_nothing_as_nothing_rather_than_as_success():
    """The degenerate end. An empty answer key must not read as a clean pass —
    that is the unearned green this program keeps finding in its own sensors."""
    estate = _estate(11)
    ranking = salience.rank(estate["rows"], now=_NOW)
    assert salience.check(ranking, [])["verdict"] == "nothing_to_check"
    assert salience.check(ranking, ["ab"])["answers"][0]["verdict"] == "unrankable_name"


# --- the join seam: what it hands over, and what it refuses to take back -----


def test_the_proposal_carries_the_estates_own_names_unmodified_and_no_scores():
    """Judgment needs the SURFACE FORM — one system writes a name solid, another
    hyphenates it, a third prefixes a year — and a tokenized or lowercased
    payload destroys exactly the evidence it was sent to read. It is also shown
    no scores: a judge told the ranking's answer is not checking it."""
    rows = [{"connector": "a", "name": "North-Bay Website 2026", "updated": "2026-05-01"},
            {"connector": "b", "name": "northbay.example", "updated": "2026-05-02"}]
    ranking = salience.rank(rows, now="2026-05-03T00:00:00Z")
    proposal = salience.join_proposal(ranking["clusters"])
    every = [name for c in proposal["candidates"] for name in c["names"]]
    assert "North-Bay Website 2026" in every
    assert "northbay.example" in every
    for candidate in proposal["candidates"]:
        assert "score" not in candidate and "rows" not in candidate


def test_a_join_naming_a_candidate_that_was_never_ranked_is_refused_and_recorded():
    """An answer naming something the ranking never produced has not read the
    estate. Accepting it would let an unbounded string into the ranking's own
    vocabulary; dropping it silently would hide a judgment that misfired."""
    estate = _estate(2)
    ranking = salience.rank(estate["rows"],
                            join=lambda p: [["not-a-real-candidate", "nor-this"]],
                            now=_NOW)
    assert ranking["joined"] and ranking["joined"][0]["accepted"] is False
    assert ranking["joined"][0]["reason"] == "names_a_candidate_that_was_never_ranked"
    plain = salience.rank(estate["rows"], now=_NOW)
    assert [c["label"] for c in ranking["clusters"]] == \
        [c["label"] for c in plain["clusters"]]


def test_a_join_that_names_one_candidate_joins_nothing_and_says_so():
    estate = _estate(4)
    first = salience.rank(estate["rows"], now=_NOW)["clusters"][0]["label"]
    ranking = salience.rank(estate["rows"], join=lambda p: [[first]],
                            now=_NOW)
    assert ranking["joined"][0] == {"labels": [first], "accepted": False,
                                    "reason": "joins_nothing"}


def test_a_join_that_is_not_something_to_ask_is_refused_before_anything_runs():
    estate = _estate(6)
    with pytest.raises(salience.SalienceError):
        salience.rank(estate["rows"], join="a string is not a judgment")


def test_the_union_keeps_a_name_the_operator_would_recognise():
    """Measured: the first working join labelled the union with the two-row
    scrap nobody calls it, because the label rule prefers the RAREST member —
    correct inside a cluster the row sets built, wrong across candidates a
    judgment joined. The widest of the joined candidates names the union."""
    estate = _estate(8)
    cold = salience.rank(estate["rows"], now=_NOW)
    labels = [_label_carrying(cold, f) for f in estate["fragments"]]
    sizes = {c["label"]: c["rows"] for c in cold["clusters"]}
    joined = salience.rank(estate["rows"], join=_joiner(labels),
                           now=_NOW)
    union = next(c for c in joined["clusters"]
                 if all(f in c["tokens"] for f in estate["fragments"]))
    assert union["label"] in labels
    assert sizes[union["label"]] == max(sizes[label] for label in labels)
