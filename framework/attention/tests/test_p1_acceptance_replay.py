"""P1 acceptance (spec §8): the REAL card corpus observed on the Captain's
feed 2026-07-07 10:03Z → 2026-07-08 03:25Z collapses to its true situation
count under canonical-ref grouping. Each entry is (card_slug, [evidence
strings verbatim from the feed])."""
from framework.attention.situation import situations_overlap

OBSERVED_CARDS = [
    ("create-tracking-tasks-for-all-four-commercialization-proof-gates",
     ["5-Reflections/Decisions/2026-07-06-Four-proofs-required-before-commercialization-substrate-API-key-SDK-unit.md — four proof gates listed",
      "5-Reflections/Decisions/2026-07-06-Consumer-subscription-substrate-is-contractually-dead.md — API-key SDK is only durable substrate"]),
    ("calendar-block-testament-signing-at-kolding-courthouse-fri-10-july-14-50",
     ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'Fredag den 10 juli klokken 14:50, Retten i Kolding'; reminder_set: false"]),
    ("toolbox-commits-cc49aa29-151890fc-missing-monday-ids",
     ["9-Codebases/Toolbox/commits.md — commits cc49aa2920 and 151890fc0c flagged ⚠️ no Monday id"]),
    ("will-signing-kolding-courthouse-fri-10-july-14-50",
     ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'Kolding courthouse, Friday 10 July 14:50, testament signing'"]),
    ("advertiser-sign-off-on-publisher-filled-details-decision-not-recorded",
     ["6-Commitments/owed_to_nate/cmt-540d7a19bffd.md — Anna answered whether advertiser must sign off on publisher-filled targeting/delivery details",
      "6-Commitments/owed_to_nate/cmt-781c7a756d51.md — same topic, fulfilled 2026-07-06",
      "6-Commitments/owed_to_nate/cmt-0ac4d1192cae.md — Anna's suggestion on advertiser sign-off in licensing/agreement flow"]),
    ("product-brain-architecture-md-is-empty-template-both-live-products-undocumented",
     ["product-brain/architecture.md — status: template, all placeholders unfilled",
      "9-Codebases/Toolbox/deployment.md — live prod stack documented in deployment digest but not in product-brain",
      "9-Codebases/Dev-Tasks-Plugin/deployment.md — same"]),
    ("testament-signing-at-kolding-courthouse-friday-10-july-14-50",
     ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Solveig har booket tid hos retten i Kolding til underskrivelse af testamente fredag d. 10. juli kl. 14:50",
      "6-Commitments/owed_to_nate/cmt-fca6836e2844.md — reminder_set: false"]),
    ("reminder-testament-signing-at-kolding-courthouse-friday-10-july-14-50",
     ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — Solveig booked Kolding courthouse Friday 10 July 14:50; fulfilled_date 2026-06-22"]),
    ("toolbox-commits-missing-monday-ids-trace-gap",
     ["9-Codebases/Toolbox/commits.md — commits cc49aa2920 and 151890fc0c both flagged ⚠️ no Monday id"]),
    ("testament-signing-kolding-courthouse-fri-10-jul-14-50-calendar-block-needed",
     ["6-Commitments/owed_to_nate/cmt-fca6836e2844.md — 'booket tid hos retten i Kolding … Fredag den 10 juli klokken 14:50'; reminder_set: false"]),
    ("chase-just-political-advertising-portals-connection-details-due-2026-07-08",
     ["6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md"]),
    ("polads-encode-advertiser-sign-off-policy-publisher-fills-advertiser-optional",
     ["6-Commitments/owed_to_nate/cmt-b54c519f5c3e.md"]),
    ("order-product-mastery-book-for-office-tomas-due-before-iben-returns-2026-07-27",
     ["ref=6-Commitments/owed_by_nate/cmt-d45d00936ac1.md"]),
    ("capture-polads-liability-decision-advertiser-confirmation-of-publisher-filled-fi",
     ["ref=6-Commitments/owed_to_nate/cmt-b54c519f5c3e.md"]),
    ("chase-just-political-advertising-portals-connection-details-due-8-jul",
     ["6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md — due 2026-07-08, reminder_set: false, status: open"]),
    ("commits-missing-monday-ids-traceability-gap-in-stepnetwork-dk-toolbox",
     ["9-Codebases/stepnetwork-dk/commits.md — commits 6a4ff7a4a5, 01bb6b18fc",
      "9-Codebases/Toolbox/commits.md — commits 151890fc0c, cc49aa2920"]),
    ("commits-missing-monday-item-ids-traceability-gap",
     ["9-Codebases/Toolbox/commits.md — commits cc49aa2920, 151890fc0c flagged ⚠️ no Monday id",
      "9-Codebases/stepnetwork-dk/commits.md — commits 01bb6b18fc, 6a4ff7a4a5 flagged ⚠️ no Monday id"]),
    ("track-and-execute-census-keyframe-writer-as-first-e0-build-task",
     ["5-Reflections/Decisions/2026-07-07-Census-keyframe-writer-is-the-first-E0-build-task.md"]),
    ("fill-polads-architecture-doc-before-ec-integration-lands",
     ["product-brain/architecture.md", "product-brain/README.md",
      "6-Commitments/owed_to_nate/cmt-dead64477e1e.md"]),
    ("ec-dg-just-connection-details-due-today-chase-if-not-received",
     ["6-Commitments/owed_to_nate/cmt-dead64477e1e.md — status:open, due 2026-07-08",
      "6-Commitments/owed_to_nate/cmt-66b9806f4e9c.md — status:open, due 2026-07-08",
      "6-Commitments/owed_to_nate/cmt-8ab5d6355d15.md — status:open, due 2026-07-08"]),
    ("book-order-product-mastery-for-tomas-reminder-before-iben-returns-27-jul",
     ["6-Commitments/owed_by_nate/cmt-d45d00936ac1.md — status:open, due 2026-07-27, reminder_set:false",
      "6-Commitments/owed_to_nate/cmt-d45d00936ac1.md — Iben returning 2026-07-27"]),
    ("styria-sign-off-answer-update-polads-advertiser-publisher-liability-spec",
     ["6-Commitments/owed_to_nate/cmt-b54c519f5c3e.md — fulfilled 2026-07-07, Anna answered: publisher fills targeting/delivery, optional advertiser confirmation"]),
    ("stepnetwork-dk-commits-missing-monday-ids-traceability-gap",
     ["9-Codebases/stepnetwork-dk/commits.md"]),
]


def _group_by_overlap(cards):
    parent = list(range(len(cards)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            if situations_overlap(cards[i][1], cards[j][1]):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(cards)):
        groups.setdefault(find(i), []).append(cards[i][0])
    return list(groups.values())


def test_observed_feed_collapses_to_true_situation_count():
    groups = _group_by_overlap(OBSERVED_CARDS)
    # 23 presented cards -> a handful of real situations (spec §8: <=8).
    assert len(groups) <= 8, groups

    by_slug = {slug: g for g in groups for slug in g}
    # All five same-day testament spellings land in ONE group.
    testament = by_slug["calendar-block-testament-signing-at-kolding-courthouse-fri-10-july-14-50"]
    assert len([s for s in testament if "signing" in s or "testament" in s]) >= 5
    # The EC chase pair + the triple-commitment variant collapse together.
    assert (by_slug["chase-just-political-advertising-portals-connection-details-due-2026-07-08"]
            is by_slug["ec-dg-just-connection-details-due-today-chase-if-not-received"])
    # Both book cards collapse despite owed_by/owed_to + ref= spelling drift.
    assert (by_slug["order-product-mastery-book-for-office-tomas-due-before-iben-returns-2026-07-27"]
            is by_slug["book-order-product-mastery-for-tomas-reminder-before-iben-returns-27-jul"])


def test_first_card_would_have_suppressed_every_followup():
    """Chronological replay of the LIVE semantics: a suppressed proposal
    writes no ledger row, so its refs do NOT join the covered set (exactly
    like run_action_lane — only presented cards cover). Two bridge cards
    (stepnetwork+toolbox commits; polads-architecture+EC commitment) are
    themselves suppressed by one of their refs, so their OTHER ref later
    presents once on its own — honest under P1; transitive merge is P4's
    standing-card job. 23 observed cards -> 10 first-presentations, and the
    worst offender (testament: 5 same-day cards) collapses to EXACTLY ONE."""
    covered: set = set()
    presented = []
    for slug, evidence in OBSERVED_CARDS:
        if situations_overlap(evidence, covered):
            continue
        presented.append(slug)
        covered.update(evidence)
    assert len(presented) == 10, presented
    assert sum("testament" in s or "signing" in s for s in presented) == 1
    # EC chase: first card presents, the re-worded chase and the
    # triple-commitment variant are both suppressed.
    ec = [s for s in presented if "connection-details" in s]
    assert ec == ["chase-just-political-advertising-portals-connection-details-due-2026-07-08"]
    # Book pair: owed_by/owed_to + ref= drift collapses to one presentation.
    assert sum("product-mastery" in s or "book-order" in s for s in presented) == 1
