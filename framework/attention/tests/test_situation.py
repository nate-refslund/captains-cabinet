"""Unit corpus for framework.attention.situation — every multi-spelling group
below was OBSERVED verbatim on the Captain's feed 2026-07-07/08 (the 24-cards-
for-8-situations incident). These are the exact strings the old verbatim
evidence-overlap check failed to match."""

from framework.attention.situation import (
    canonical_refs, situation_key, situations_overlap)

# The five observed spellings of the testament commitment evidence.
TESTAMENT_VARIANTS = [
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'Fredag den 10 juli klokken 14:50, Retten i Kolding'; reminder_set: false",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'Kolding courthouse, Friday 10 July 14:50, testament signing'",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Solveig har booket tid hos retten i Kolding til underskrivelse af testamente fredag d. 10. juli kl. 14:50",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Solveig booked Kolding courthouse Friday 10 July 14:50; fulfilled_date 2026-06-22",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'booket tid hos retten i Kolding … Fredag den 10 juli klokken 14:50'; reminder_set: false",
]


def test_testament_variants_all_share_canonical_refs():
    canon = [canonical_refs([v]) for v in TESTAMENT_VARIANTS]
    for c in canon:
        assert "6-Commitments/owed_to_nate/cmt-fca6836e2844.md" in c
        assert "cmt-fca6836e2844" in c
    for i in range(len(canon)):
        for j in range(len(canon)):
            assert canon[i] & canon[j], (i, j)


def test_ref_prefix_and_cross_directory_same_commitment():
    # Observed: same commitment cited via owed_by AND owed_to paths, one with
    # a literal 'ref=' prefix. The bare cmt id must bridge them.
    a = canonical_refs(["ref=6-Commitments/owed_by_nate/cmt-d45d00936ac1.md"])
    b = canonical_refs(["6-Commitments/owed_to_nate/cmt-d45d00936ac1.md — Iben returning 2026-07-27"])
    assert "cmt-d45d00936ac1" in a and "cmt-d45d00936ac1" in b
    assert a & b


def test_bare_vs_annotated_path():
    bare = "6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md"
    annotated = "6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md — due 2026-07-08, reminder_set: false, status: open"
    assert canonical_refs([bare]) & canonical_refs([annotated])


def test_multi_ref_string_yields_every_ref():
    s = ("6-Commitments/owed_to_nate/cmt-540d7a19bffd.md — Anna answered, "
         "6-Commitments/owed_to_nate/cmt-781c7a756d51.md — same topic, fulfilled 2026-07-06, "
         "6-Commitments/owed_to_nate/cmt-0ac4d1192cae.md — Anna's suggestion")
    c = canonical_refs([s])
    assert {"cmt-540d7a19bffd", "cmt-781c7a756d51", "cmt-0ac4d1192cae"} <= c
    assert "6-Commitments/owed_to_nate/cmt-781c7a756d51.md" in c


def test_ampersand_and_dated_decision_paths():
    c = canonical_refs([
        "5-Reflections/Decisions/2026-07-06-Four-proofs-required-before-commercialization-substrate-API-key-SDK-unit.md — four proof gates listed",
        "9-Codebases/Toolbox/commits.md — commits cc49aa2920 and 151890fc0c flagged ⚠️ no Monday id",
    ])
    assert "5-Reflections/Decisions/2026-07-06-Four-proofs-required-before-commercialization-substrate-API-key-SDK-unit.md" in c
    assert "9-Codebases/Toolbox/commits.md" in c


def test_different_files_do_not_overlap():
    a = canonical_refs(["9-Codebases/Toolbox/commits.md — commits cc49aa2920"])
    b = canonical_refs(["9-Codebases/stepnetwork-dk/commits.md — commits 6a4ff7a4a5"])
    assert not (a & b)


def test_prose_only_yields_empty_and_never_overlaps():
    prose = canonical_refs(["the Captain mentioned this in passing yesterday"])
    assert prose == frozenset()
    assert not situations_overlap(
        ["the Captain mentioned this in passing yesterday"],
        ["the Captain mentioned this in passing yesterday"])


def test_correlation_uuid_monday_and_url_forms():
    c = canonical_refs([
        "cabinet-proposal-id:0f3a9b2c4d5e6f70",
        "event 6E945A46-ECCB-435C-A927-19A8B5252EA0 created",
        "monday:5091706356 moved to Done",
        "see https://Example.com/Path?x=1 for details",
    ])
    assert "cabinet-proposal-id:0f3a9b2c4d5e6f70" in c
    assert "6e945a46-eccb-435c-a927-19a8b5252ea0" in c
    assert "monday:5091706356" in c
    assert "https://example.com/Path?x=1" in c


def test_normalization_slashes_quotes_and_truncation():
    a = canonical_refs(["`6-Commitments//owed_to_nate/cmt-fca6836e2844.md`"])
    assert "6-Commitments/owed_to_nate/cmt-fca6836e2844.md" in a
    # Inputs are hard-capped so a hostile mega-string cannot balloon the set.
    huge = "x" * 500_000
    assert canonical_refs([huge]) == frozenset()


def test_non_string_and_none_inputs_are_safe():
    assert canonical_refs(None) == frozenset()
    assert canonical_refs([None, 42, {"path": "y"}]) == frozenset()


def test_situation_key_stable_and_ref_order_free():
    k1 = situation_key([TESTAMENT_VARIANTS[0]])
    k2 = situation_key([TESTAMENT_VARIANTS[0]])
    assert k1 == k2 and k1.startswith("sit-")
    # same canonical set, different raw spelling -> same key
    assert situation_key([TESTAMENT_VARIANTS[1]]) == k1


def test_situation_key_falls_back_to_subject_slug_when_refless():
    k = situation_key(["pure prose"], subject="Order Product Mastery Book!")
    assert k == "slug:order-product-mastery-book"
