"""The genesis brief asks about a BUSINESS, never about presumed products.

ONBOARD-2 writes the org's first grounding record. Its prompt used to ask for
a "company/market/product research brief ... for the product lanes below" and
to instruct the model to cover "what the product most plausibly is" and never
invent facts "about these particular products". For a cabinet run by a legal
practice or a charity, every one of those words is a wrong premise baked into
the very first thing the org ever learns about itself.

The property asserted here is the one the brief exists to deliver: whatever
kind of business hatched this cabinet, the prompt describes THAT business in
its own declared words and presupposes nothing about what it sells.

Hermetic: pure prompt construction, no subprocess, no network.

Provenance: authored per the 2026-07-07 full-autonomy grant.
"""
from __future__ import annotations

import pytest

from framework.onboarding import genesis

LEGAL_PRACTICE = {
    "version": 1,
    "captain": {"name": "Ada", "timezone": "Europe/Madrid",
                "telegram_chat_id": "12345678"},
    "cabinet": {"id": "harbour-hq", "mode": "single", "org_shape": "portfolio"},
    "lanes": [
        {"name": "Shipping Contracts", "slug": "shipping-contracts",
         "does": "Contract review for freight operators",
         "serves": "Three Nordic shipping lines",
         "owes": "A five-day turnaround on every filed review"},
        {"name": "Compliance Filings", "slug": "compliance-filings",
         "does": "Quarterly regulatory filings",
         "serves": "The same three clients",
         "owes": "Every filing before its statutory deadline"},
    ],
    "autonomy": {"posture": "propose_first", "flavor": "org"},
}


def test_a_non_software_business_is_asked_about_in_its_own_words():
    prompt = genesis.build_brief_prompt(LEGAL_PRACTICE)
    for phrase in ("Contract review for freight operators",
                   "Three Nordic shipping lines",
                   "A five-day turnaround on every filed review",
                   "Every filing before its statutory deadline"):
        assert phrase in prompt, f"the brief never mentions: {phrase}"


def test_the_prompt_presupposes_no_product():
    """A legal practice's brief must not contain the word at all — every
    occurrence would be the prompt's own scaffolding, since the answers carry
    none."""
    prompt = genesis.build_brief_prompt(LEGAL_PRACTICE)
    assert "product" not in prompt.lower(), (
        "the brief still presumes products: "
        + "; ".join(ln for ln in prompt.splitlines() if "product" in ln.lower()))


def test_the_prompt_says_outright_not_to_assume_software():
    prompt = genesis.build_brief_prompt(LEGAL_PRACTICE).lower()
    assert "never assume it builds or sells software" in prompt


def test_a_cabinet_with_no_lanes_is_told_so_without_the_word():
    prompt = genesis.build_brief_prompt({**LEGAL_PRACTICE, "lanes": []})
    assert "- (no lanes declared yet)" in prompt
    assert "product" not in prompt.lower()


def test_a_software_lane_still_carries_its_repos():
    """Company-shaping is not estate-stripping: a lane that declared repos
    still hands them to the research organ."""
    answers = {**LEGAL_PRACTICE, "lanes": [
        {"name": "Filing Portal", "slug": "filing-portal",
         "does": "The client filing portal", "repos": ["harbour/portal"]}]}
    prompt = genesis.build_brief_prompt(answers)
    assert "repos: harbour/portal" in prompt
    assert "The client filing portal" in prompt


@pytest.mark.parametrize("leak", ["12345678", "TELEGRAM"])
def test_names_only_contract_is_unchanged(leak):
    """Regression guard, not a new behaviour: the prompt still carries no
    address and no env-var noise now that it carries free prose too."""
    assert leak not in genesis.build_brief_prompt(LEGAL_PRACTICE)


def test_the_library_grounding_card_no_longer_promises_a_product_brief():
    cards = genesis.propose_outcome_cards(LEGAL_PRACTICE)
    grounding = next(c for c in cards if c["id"] == "proposed-library-grounding")
    assert "product" not in (grounding["name"] + grounding["what"]).lower()
    assert "company and market brief" in grounding["name"]
