"""Unit corpus for framework.attention.situation — every multi-spelling group
below replays the 24-cards-for-8-situations feed incident in the Testburg
fixture vocabulary (same story as the P1 replay corpus). These are the
spelling-drift shapes the old verbatim evidence-overlap check failed to match.
Canonical ids are LOWERCASE by contract (LLM case drift + macOS
case-insensitive FS)."""

from framework.attention.situation import (
    canonical_refs, situation_key, situations_overlap)

# The five drifted spellings of the deed-signing commitment evidence.
DEED_VARIANTS = [
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'Fredag den 10 juli klokken 14:50, Retten i Kageby'; reminder_set: false",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'Kageby courthouse, Friday 10 July 14:50, deed signing'",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Sigrid har booket tid hos retten i Kageby til underskrivelse af deede fredag d. 10. juli kl. 14:50",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Sigrid booked Kageby courthouse Friday 10 July 14:50; fulfilled_date 2026-06-22",
    "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'booket tid hos retten i Kageby … Fredag den 10 juli klokken 14:50'; reminder_set: false",
]


def test_deed_variants_all_share_canonical_refs():
    canon = [canonical_refs([v]) for v in DEED_VARIANTS]
    for c in canon:
        assert "6-commitments/owed_to_nate/cmt-fca6836e2844.md" in c
        assert "cmt-fca6836e2844" in c
    for i in range(len(canon)):
        for j in range(len(canon)):
            assert canon[i] & canon[j], (i, j)


def test_ref_prefix_and_cross_directory_same_commitment():
    # Observed: same commitment cited via owed_by AND owed_to paths, one with
    # a literal 'ref=' prefix. The bare cmt id must bridge them.
    a = canonical_refs(["ref=6-Commitments/owed_by_nate/cmt-d45d00936ac1.md"])
    b = canonical_refs(["6-Commitments/owed_to_nate/cmt-d45d00936ac1.md — Pia returning 2026-07-27"])
    assert "cmt-d45d00936ac1" in a and "cmt-d45d00936ac1" in b
    assert a & b


def test_bare_vs_annotated_path():
    bare = "6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md"
    annotated = "6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md — due 2026-07-08, reminder_set: false, status: open"
    assert canonical_refs([bare]) & canonical_refs([annotated])


def test_multi_ref_string_yields_every_ref():
    s = ("6-Commitments/owed_to_nate/cmt-540d7a19bffd.md — Ida answered, "
         "6-Commitments/owed_to_nate/cmt-781c7a756d51.md — same topic, fulfilled 2026-07-06, "
         "6-Commitments/owed_to_nate/cmt-0ac4d1192cae.md — Ida's suggestion")
    c = canonical_refs([s])
    assert {"cmt-540d7a19bffd", "cmt-781c7a756d51", "cmt-0ac4d1192cae"} <= c
    assert "6-commitments/owed_to_nate/cmt-781c7a756d51.md" in c


def test_ampersand_and_dated_decision_paths():
    c = canonical_refs([
        "5-Reflections/Decisions/2026-07-06-Four-proofs-required-before-commercialization-substrate-API-key-SDK-unit.md — four proof gates listed",
        "9-Codebases/Toolbox/commits.md — commits cc49aa2920 and 151890fc0c flagged ⚠️ no Monday id",
    ])
    assert "5-reflections/decisions/2026-07-06-four-proofs-required-before-commercialization-substrate-api-key-sdk-unit.md" in c
    assert "9-codebases/toolbox/commits.md" in c


def test_different_files_do_not_overlap():
    a = canonical_refs(["9-Codebases/Toolbox/commits.md — commits cc49aa2920"])
    b = canonical_refs(["9-Codebases/exampleco-dk/commits.md — commits 6a4ff7a4a5"])
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
        "monday:42424242 moved to Done",
        "see https://Example.com/Path?x=1 for details",
    ])
    assert "cabinet-proposal-id:0f3a9b2c4d5e6f70" in c
    assert "6e945a46-eccb-435c-a927-19a8b5252ea0" in c
    assert "monday:42424242" in c
    assert "https://example.com/Path?x=1" in c


def test_normalization_slashes_quotes():
    a = canonical_refs(["`6-Commitments//owed_to_nate/cmt-fca6836e2844.md`"])
    assert "6-commitments/owed_to_nate/cmt-fca6836e2844.md" in a


def test_non_string_and_none_inputs_are_safe():
    assert canonical_refs(None) == frozenset()
    assert canonical_refs([None, 42, {"path": "y"}]) == frozenset()
    assert canonical_refs(12345) == frozenset()   # non-iterable


def test_situation_key_stable_and_ref_order_free():
    k1 = situation_key([DEED_VARIANTS[0]])
    k2 = situation_key([DEED_VARIANTS[0]])
    assert k1 == k2 and k1.startswith("sit-")
    # same canonical set, different raw spelling -> same key
    assert situation_key([DEED_VARIANTS[1]]) == k1


def test_situation_key_falls_back_to_subject_slug_when_refless():
    k = situation_key(["pure prose"], subject="Order Product Mastery Book!")
    assert k == "slug:order-product-mastery-book"


# --- adversarial-review regressions (gauntlet 2026-07-08) --------------------


def test_large_covered_set_is_fully_canonicalized_and_deterministic():
    """The item-count cap silently truncated the covered set in hash order —
    dedup flickered with PYTHONHASHSEED and no-op'd at production ledger
    size. Every item must contribute, regardless of iteration order."""
    filler = [f"prose filler number {i}" for i in range(200)]
    real = "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — reminder_set: false"
    for ordering in (filler + [real], [real] + filler,
                     filler[:100] + [real] + filler[100:]):
        c = canonical_refs(ordering)
        assert "cmt-fca6836e2844" in c
    assert canonical_refs(set(filler + [real])) >= {"cmt-fca6836e2844"}


def test_per_string_cap_is_live_but_leading_refs_survive():
    """One hostile mega-string is capped at 10k chars: a ref hidden past the
    cap is NOT extracted (bounded cost), a ref before the cap IS."""
    beyond = "prose " * 4_000 + "6-Commitments/x/cmt-abcdef123456.md"
    within = "6-Commitments/x/cmt-abcdef123456.md " + "prose " * 4_000
    assert canonical_refs([beyond]) == frozenset()
    assert "cmt-abcdef123456" in canonical_refs([within])


def test_md_extension_end_guard_no_phantom_live_path():
    """commits.md.bak-20260705 / post.mdx / commits.md-old / commits.md~ must
    NOT extract the live sibling's path — that byte-identical phantom
    suppressed real cards (verified)."""
    assert canonical_refs(["restore 9-Codebases/Toolbox/commits.md.bak-20260705"]) == frozenset()
    assert canonical_refs(["docs/blog/post.mdx"]) == frozenset()
    assert canonical_refs(["9-Codebases/Toolbox/commits.md-old kept"]) == frozenset()
    assert canonical_refs(["editor left 9-Codebases/Toolbox/commits.md~ around"]) == frozenset()
    # sentence-final punctuation after .md still matches
    assert "9-codebases/toolbox/commits.md" in canonical_refs(
        ["see 9-Codebases/Toolbox/commits.md."])


def test_parenthesized_citation_matches_plain_spelling():
    plain = canonical_refs(["9-Codebases/Toolbox/commits.md"])
    paren = canonical_refs(["traceability gap (9-Codebases/Toolbox/commits.md)"])
    link = canonical_refs(["[commits](9-Codebases/Toolbox/commits.md)"])
    assert plain & paren
    assert plain & link
    # names with balanced parens keep them
    assert canonical_refs(["5-Monday/AI-Workspace/Reflections-&-Research.md"])


def test_url_normalization_drift_forms_overlap():
    base = canonical_refs(["https://bakery.example.com/portal"])
    assert canonical_refs(["see https://bakery.example.com/portal."]) & base
    assert canonical_refs(["https://bakery.example.com/portal/"]) & base
    assert canonical_refs(["HTTPS://BAKERY.EXAMPLE.COM/portal"]) & base
    # pathless URL with sentence dot
    assert canonical_refs(["see https://bakery.example.com."]) & canonical_refs(["https://bakery.example.com"])


def test_monday_spellings_from_live_corpus():
    # 1234567890/1234567891 are sequential board-id DUMMIES: the _BOARD/_MONDAY
    # extractors require the real 9-10 digit id shape, so a shorter fake would
    # skip the tested path (shape-mandated fixture; never a real board id).
    assert "monday:1234567890" in canonical_refs(["monday: 1234567890"])
    assert "monday:1234567890" in canonical_refs(["the ✔ Todos board `1234567890`"])
    assert "monday:1234567891" in canonical_refs(["Tasks board 1234567891 in AI Workspace"])
    # short digit runs near 'board' are not ids; nor are compact dates
    assert canonical_refs(["Sprint 12 board review"]) == frozenset()
    assert canonical_refs(["board 20260708 retro notes"]) == frozenset()


def test_cabinet_scheme_ids_and_need_ids():
    c = canonical_refs([
        "veto:bakery/external-send blocked",
        "undo-journal:jid-20260707-0042 reversed",
        "thread:emails/louis-beaumont",
        "filed NEED-a3f2b1c4 for the captain",
    ])
    assert "veto:bakery/external-send" in c
    assert "undo-journal:jid-20260707-0042" in c
    assert "thread:emails/louis-beaumont" in c
    assert "need-a3f2b1c4" in c
    # sentence-final punctuation must not fork the id (review cp1 Low-2)
    assert "undo-journal:jid-20260707-0042" in canonical_refs(
        ["reversed undo-journal:jid-20260707-0042."])
    # prose must NOT mint ids: hyphenated words, hex-alphabet words (Low nit)
    assert canonical_refs(["on a need-to-know basis"]) == frozenset()
    assert canonical_refs(["the need-added flag"]) == frozenset()


def test_path_grade_classifier():
    from framework.attention.situation import path_grade
    assert path_grade("6-commitments/x/cmt-abcdef123456.md")
    # URLs ending in .md are id-grade, not vault paths (review cp1 Low-3)
    assert not path_grade("https://x.eu/docs/readme.md")
    assert not path_grade("cmt-abcdef123456")
    assert not path_grade("monday:42424242")


def test_uppercase_cmt_id_collapses_to_lowercase():
    assert "cmt-fca6836e2844" in canonical_refs(["follow-up on CMT-FCA6836E2844"])


def test_known_limitation_space_bearing_meeting_filenames():
    """DOCUMENTED LIMITATION (not a target): space-bearing 2-Meetings/
    filenames lose their path identity (the class excludes spaces to avoid
    gluing prose). Id-grade refs in the same string still carry identity."""
    c = canonical_refs(["2-Meetings/2026-07-07 - Bakery Scrum.md — cmt-abcdef123456 discussed"])
    assert "cmt-abcdef123456" in c
    assert not any(x.startswith("2-meetings/") for x in c)
