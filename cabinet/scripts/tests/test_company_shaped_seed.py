"""The seed surface asks about a COMPANY, not about a software estate.

The schema under instance/ was already company-agnostic. The FIRST
CONVERSATION was not: the answers template asked every lane for repos, a task
system, board ids, a database project and a hosting project, and asked nothing
about customers, obligations or people. A consultancy, a household or a
services business has none of the former and all of the latter — so the seed
surface was where "it started as a product tool" actually survived.

These tests assert what the questionnaire EXISTS to deliver: that a business
which ships no software can be onboarded, and that the org's first written
description of itself is the business — what it does, who it serves, what it
owes — rather than an inventory of empty estate slots. The estate questions
still exist; they are now a branch that opens for software lanes only, and the
software arm below is what stops that becoming a deletion.

Fictional businesses throughout (a coffee-machine repair firm, a legal
practice) — the fixtures double as the universality proof.

S0: python3.12, tmp_path roots, no network.

Provenance: authored per the 2026-07-07 full-autonomy grant.
"""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import pytest
import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

spec = _ilu.spec_from_file_location("generate_instance_company_shape",
                                    _SCRIPTS_DIR / "generate-instance.py")
gi = _ilu.module_from_spec(spec)
spec.loader.exec_module(gi)

# The contract, stated HERE rather than read back off the module under
# test: a test that asks the generator what its own question set is can
# never notice the question set being wrong. SHAPE_MAX_LEN is read with a
# fallback so this file collects (and its behaviour arms run and FAIL)
# against a build that predates the constant.
SHAPE_KEYS = ("does", "serves", "owes")
ESTATE_KEYS = ("repos", "task_system", "boards", "neon_project", "vercel_project")
SHAPE_MAX_LEN = getattr(gi, "SHAPE_MAX_LEN", 400)

PLATFORM_FIXTURE = """\
captain_name: Placeholder
captain_timezone: UTC
captain_telegram_chat_id: "0000"
"""

SERVICES_LANE = {
    "name": "Service Contracts",
    "slug": "service-contracts",
    "does": "Scheduled servicing and callouts for contract customers",
    "serves": "The 40 sites on an annual contract",
    "owes": "A same-week callout and a written service record per visit",
}

SOFTWARE_LANE = {
    "name": "Booking App",
    "slug": "booking-app",
    "does": "The customer booking and callout-tracking app",
    "serves": "Contract customers booking their own callouts",
    "owes": "Same-day booking confirmation",
    "repos": ["repairco/booking-app"],
    "task_system": "plugin:dev-tasks",
    "boards": ["12345678"],
}


def services_answers(**over) -> dict:
    answers = {
        "version": 1,
        "captain": {"name": "Ada", "timezone": "Europe/Madrid",
                    "telegram_chat_id": "12345678"},
        "company": {
            "does": "We repair and service commercial coffee machines",
            "serves": "Cafes, offices and two hotel groups on service contracts",
            "owes": "A same-week callout on every contract site",
        },
        "cabinet": {"id": "repairco", "mode": "single", "org_shape": "portfolio",
                    "officer_model": "claude-opus-4-8[1m]"},
        "lanes": [dict(SERVICES_LANE)],
        "autonomy": {"posture": "propose_first", "flavor": "org"},
        "integrations": {"telegram": {"ceo_bot": "", "bot_token_env": "TELEGRAM_COS_TOKEN"},
                         "mcp_env_names": []},
    }
    answers.update(over)
    return answers


@pytest.fixture()
def root(tmp_path) -> Path:
    for rel in ("instance/config/contexts", "instance/config/projects",
                "instance/agents", "presets/portfolio/agents"):
        (tmp_path / rel).mkdir(parents=True)
    (tmp_path / "presets/portfolio/agents/_lane-ceo.md.template").write_text(
        (_REPO_ROOT / "presets/portfolio/agents/_lane-ceo.md.template").read_text())
    (tmp_path / "instance/config/platform.yml").write_text(PLATFORM_FIXTURE)
    return tmp_path


def run_gen(root: Path, answers: dict) -> None:
    path = root / "instance/config/cabinet-init.answers.yml"
    path.write_text(yaml.safe_dump(answers, sort_keys=False, allow_unicode=True))
    gi.generate(root, path)


def context_of(root: Path, slug: str) -> dict:
    return yaml.safe_load((root / f"instance/config/contexts/{slug}.yml").read_text())


# ---------------------------------------------------------------------------
# A business that ships no software gets described as a business
# ---------------------------------------------------------------------------

def test_services_lane_is_described_by_what_it_does_serves_and_owes(root):
    run_gen(root, services_answers())
    desc = context_of(root, "service-contracts")["description"]
    assert "Scheduled servicing and callouts for contract customers" in desc
    assert "The 40 sites on an annual contract" in desc
    assert "A same-week callout and a written service record per visit" in desc


def test_services_lane_carries_no_empty_estate_inventory(root):
    """The pre-change generator recited "Repo(s): (none declared). Task
    board(s): (none declared)." for EVERY lane. For a repair firm that is not
    a description, it is a list of things it is failing to have."""
    run_gen(root, services_answers())
    desc = context_of(root, "service-contracts")["description"]
    for token in ("Repo(s)", "repo(s)", "Task board(s)", "task board(s)",
                  "none declared", "Software estate"):
        assert token not in desc, f"services lane still recites {token!r}: {desc}"


def test_the_lanes_own_words_become_the_project_description(root):
    run_gen(root, services_answers())
    project = yaml.safe_load(
        (root / "instance/config/projects/service-contracts.yml").read_text())
    assert project["product"]["description"] == SERVICES_LANE["does"]


def test_a_lane_inherits_the_companys_answers_when_it_restates_none(root):
    """A single-lane cabinet IS the business; it should not have to say the
    same three things twice to be described."""
    bare = {"name": "Whole Business", "slug": "whole-business"}
    run_gen(root, services_answers(lanes=[bare]))
    desc = context_of(root, "whole-business")["description"]
    assert "We repair and service commercial coffee machines" in desc
    assert "Cafes, offices and two hotel groups on service contracts" in desc


# ---------------------------------------------------------------------------
# The estate branch is a BRANCH, not a deletion
# ---------------------------------------------------------------------------

def test_software_lane_still_gets_its_estate_recorded(root):
    answers = services_answers(lanes=[dict(SERVICES_LANE), dict(SOFTWARE_LANE)])
    run_gen(root, answers)
    desc = context_of(root, "booking-app")["description"]
    assert "Software estate" in desc
    assert "repairco/booking-app" in desc
    assert "12345678" in desc
    # ...and it is still described as a business first
    assert "The customer booking and callout-tracking app" in desc


def test_the_two_lanes_of_one_company_render_differently(root):
    """The branch has teeth only if the estate arm and the services arm are
    not the same text."""
    run_gen(root, services_answers(lanes=[dict(SERVICES_LANE), dict(SOFTWARE_LANE)]))
    assert "Software estate" in context_of(root, "booking-app")["description"]
    assert "Software estate" not in context_of(root, "service-contracts")["description"]


# ---------------------------------------------------------------------------
# What a stranger actually sees: the shipped questionnaire
# ---------------------------------------------------------------------------

def test_shipped_example_asks_the_company_questions():
    example = yaml.safe_load(gi.EXAMPLE_ANSWERS)
    assert isinstance(example.get("company"), dict), "the example asks nothing about the company"
    for key in SHAPE_KEYS:
        assert str(example["company"].get(key) or "").strip(), f"company.{key} unanswered"


def test_shipped_example_shows_a_lane_with_no_software_estate():
    """The template teaches by shape. If every lane in it declares repos and
    boards, the interview will ask every lane for repos and boards."""
    lanes = yaml.safe_load(gi.EXAMPLE_ANSWERS)["lanes"]
    estate_free = [ln for ln in lanes if not any(ln.get(k) for k in ESTATE_KEYS)]
    assert estate_free, "every lane in the example declares a software estate"
    for lane in estate_free:
        for key in SHAPE_KEYS:
            assert str(lane.get(key) or "").strip(), (
                f"the estate-free lane {lane.get('slug')!r} answers no {key}")


def test_shipped_example_still_generates_end_to_end(root):
    path = root / "instance/config/cabinet-init.answers.yml"
    path.write_text(gi.EXAMPLE_ANSWERS)
    gi.generate(root, path)
    assert (root / "instance/config/roster.yml").is_file()


def test_defaults_lane_asks_the_questions_and_answers_none(root):
    """The zero-question hatch must SURFACE the three questions (so a captain
    sees what is missing) and invent no answers for them."""
    answers = yaml.safe_load(gi.render_default_answers("Ada"))
    assert set(SHAPE_KEYS) <= set(answers["company"])
    assert all(not answers["company"][k] for k in SHAPE_KEYS)
    gi.generate(root, _write(root, answers))
    desc = context_of(root, answers["lanes"][0]["slug"])["description"]
    assert "Not described yet" in desc
    assert "none declared" not in desc


def _write(root: Path, answers: dict) -> Path:
    path = root / "instance/config/cabinet-init.answers.yml"
    path.write_text(yaml.safe_dump(answers, sort_keys=False, allow_unicode=True))
    return path


# ---------------------------------------------------------------------------
# The new questions never break an old answers file, and never leak
# ---------------------------------------------------------------------------

def test_answers_without_any_company_shape_still_generate(root):
    """Back-compat guard: files written before these questions existed."""
    answers = services_answers()
    answers.pop("company")
    answers["lanes"] = [{"name": "Legacy Lane", "slug": "legacy-lane",
                         "repos": ["repairco/legacy"], "task_system": "none"}]
    run_gen(root, answers)
    assert context_of(root, "legacy-lane")["description"]


@pytest.mark.parametrize("bad", [
    ["a list"], {"nested": "map"}, 42, "line one\nline two", "x" * (SHAPE_MAX_LEN + 1),
])
def test_a_malformed_company_answer_refuses_loudly(root, bad):
    answers = services_answers()
    answers["company"]["does"] = bad
    with pytest.raises(gi.GenerationError, match="company.does"):
        run_gen(root, answers)


@pytest.mark.parametrize("bad", ["line one\nline two", ["a list"]])
def test_a_malformed_lane_answer_refuses_loudly(root, bad):
    answers = services_answers()
    answers["lanes"][0]["owes"] = bad
    with pytest.raises(gi.GenerationError, match=r"lanes\[0\].owes"):
        run_gen(root, answers)


def test_a_secret_shaped_company_answer_is_still_refused(root):
    """The new free-prose fields ride the same secret gate as everything else."""
    answers = services_answers()
    answers["company"]["owes"] = "we owe them the key sk-ANTHROPICLOOKALIKEKEY01"
    with pytest.raises(gi.GenerationError, match="SECRET REFUSED at answers.company.owes"):
        run_gen(root, answers)


def test_the_skill_asks_the_company_questions_before_the_estate_ones():
    """The questionnaire itself, not just the generator that consumes it."""
    skill = (_REPO_ROOT / ".claude/skills/cabinet-init/SKILL.md").read_text()
    for phrase in ("What does this business actually do?",
                   "Who does it do that for?",
                   "What does it owe them?"):
        assert phrase in skill, f"the interview never asks: {phrase}"
    company_at = skill.index("What does this business actually do?")
    estate_at = skill.index("**Repo(s)**")
    assert company_at < estate_at, "the estate questions come before the company ones"
    assert "ask only when the answers imply software" in skill.lower()
