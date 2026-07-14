"""genesis (ONBOARD-1/2) — propose-only outcome cards + brief-or-honest-IOU.

Hermetic: tmp_path roots, injected run_fn/net_check_fn seams — no real
subprocess, no network, no Redis, and never the checkout's own instance/.
"""
import subprocess

import pytest
import yaml

from framework.frontdoor import intake
from framework.onboarding import genesis

ANSWERS = {
    "version": 1,
    "captain": {"name": "Ada", "timezone": "Europe/Madrid",
                "telegram_chat_id": "12345678"},
    "cabinet": {"id": "acme-hq", "mode": "single", "org_shape": "portfolio",
                "officer_model": "claude-opus-4-8[1m]"},
    "lanes": [
        {"name": "Acme Storefront", "slug": "acme-store",
         "repos": ["acme/storefront"], "task_system": "plugin:dev-tasks"},
        {"name": "Acme Labs", "slug": "acme-labs", "repos": ["acme/labs"],
         "task_system": "linear"},
    ],
    "autonomy": {"posture": "propose_first", "flavor": "org"},
}


def _write_answers(root, answers=ANSWERS):
    path = root / genesis.ANSWERS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(answers, sort_keys=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# ONBOARD-1 — card derivation (pure)
# ---------------------------------------------------------------------------
def test_two_lanes_yield_four_cards_all_draft():
    cards = genesis.propose_outcome_cards(ANSWERS)
    assert len(cards) == 4                      # 2 lane + library + captain-loop
    assert len({c["id"] for c in cards}) == 4   # unique ids
    for c in cards:
        assert c["status"] == "draft"
        assert c["captain_ratified"] is False   # NEVER pre-ratified
        assert c["what"] and c["why"] and c["proof_expected"]  # the card lines


def test_card_count_band_is_two_to_four():
    one_lane = {**ANSWERS, "lanes": ANSWERS["lanes"][:1]}
    no_lanes = {**ANSWERS, "lanes": []}
    many = {**ANSWERS, "lanes": ANSWERS["lanes"] * 3}   # 6 declared lanes
    assert len(genesis.propose_outcome_cards(one_lane)) == 3
    assert len(genesis.propose_outcome_cards(no_lanes)) == 2
    assert len(genesis.propose_outcome_cards(many)) == 4    # capped


def test_lane_cards_cite_the_declared_lane():
    cards = genesis.propose_outcome_cards(ANSWERS)
    lane_cards = [c for c in cards if c["lane"]]
    assert {c["lane"] for c in lane_cards} == {"acme-store", "acme-labs"}
    store = next(c for c in lane_cards if c["lane"] == "acme-store")
    assert "Acme Storefront" in store["name"]
    assert "acme/storefront" in store["why"]        # repo NAME in provenance


def test_focus_letter_anchors_the_why():
    focus = "Explore Acme Storefront first; never touch billing without me."
    cards = genesis.propose_outcome_cards(ANSWERS, focus)
    store = next(c for c in cards if c["lane"] == "acme-store")
    assert "focus letter" in store["why"]
    loop = next(c for c in cards if c["id"] == "proposed-captain-loop")
    assert "Explore Acme Storefront first" in loop["why"]   # honest excerpt


def test_no_cabinet_id_is_honest_empty():
    assert genesis.propose_outcome_cards({"lanes": ANSWERS["lanes"]}) == []


def test_duplicate_lane_slugs_yield_unique_card_ids():
    dup = {**ANSWERS, "lanes": [ANSWERS["lanes"][0], dict(ANSWERS["lanes"][0])]}
    cards = genesis.propose_outcome_cards(dup)
    ids = [c["id"] for c in cards]
    assert len(ids) == len(set(ids))            # ids are keys — never collide
    assert "proposed-acme-store-first-proof" in ids
    assert "proposed-acme-store-first-proof-2" in ids


# ---------------------------------------------------------------------------
# ONBOARD-1 — mission-conditioned derivation (Phase 2, purpose-first interview)
# ---------------------------------------------------------------------------
MISSION = {
    "purpose": "Make ad-transparency compliance effortless for publishers.",
    "success_90d": "Three publishers live on the transparency flow.",
    "never_touch": ["production deploys without review", "billing data"],
}


def test_mission_conditions_every_card_class():
    cards = genesis.propose_outcome_cards({**ANSWERS, "mission": dict(MISSION)})
    assert len(cards) == 4                       # conditioning, never new cards
    store = next(c for c in cards if c["lane"] == "acme-store")
    assert MISSION["purpose"] in store["why"]    # lane card cites the mission
    library = next(c for c in cards if c["id"] == "proposed-library-grounding")
    assert MISSION["purpose"] in library["why"]
    loop = next(c for c in cards if c["id"] == "proposed-captain-loop")
    assert MISSION["success_90d"] in loop["why"]         # the 90-day bar
    assert "never touches" in loop["why"]                # the standing constraint
    assert "production deploys without review" in loop["why"]
    for c in cards:                              # propose-only holds, always
        assert c["status"] == "draft" and c["captain_ratified"] is False


def test_missionless_answers_derive_identical_cards():
    """The mission block only ever ADDS conditioning: absent/None/malformed
    mission keys all derive exactly the pre-Phase-2 cards (--defaults answers
    carry no mission, so the fast lane's genesis output stays byte-stable)."""
    baseline = genesis.propose_outcome_cards(ANSWERS)
    for answers in ({**ANSWERS, "mission": None},
                    {**ANSWERS, "mission": "not-a-dict"},
                    {**ANSWERS, "mission": {}},
                    {**ANSWERS, "mission": {"never_touch": "not-a-list"}}):
        assert genesis.propose_outcome_cards(answers) == baseline


def test_mission_and_focus_letter_compose_not_compete():
    focus = "Explore Acme Storefront first."
    cards = genesis.propose_outcome_cards(
        {**ANSWERS, "mission": dict(MISSION)}, focus)
    loop = next(c for c in cards if c["id"] == "proposed-captain-loop")
    assert MISSION["success_90d"] in loop["why"]
    assert "Explore Acme Storefront first" in loop["why"]   # both anchor


def test_mission_excerpts_flattened_capped_and_never_touch_bounded():
    mission = {
        "purpose": "  spread\n over \t lines  " + "pad " * 60,   # >160 chars
        "never_touch": ["a", "", "b", "c", "d"],                 # blanks dropped
    }
    cards = genesis.propose_outcome_cards({**ANSWERS, "mission": mission})
    store = next(c for c in cards if c["lane"] == "acme-store")
    assert "spread over lines" in store["why"]   # whitespace flattened
    assert "\n" not in store["why"]
    quoted = store["why"].split('The mission it serves: "', 1)[1]
    assert len(quoted.rstrip('"')) <= 160        # excerpt capped
    loop = next(c for c in cards if c["id"] == "proposed-captain-loop")
    assert "a; b; c." in loop["why"]             # first 3 only, blanks gone
    assert "; d" not in loop["why"]


def test_run_genesis_proposal_carries_mission_into_staging(tmp_path):
    _write_answers(tmp_path, {**ANSWERS, "mission": dict(MISSION)})
    out = genesis.run_genesis_proposal(tmp_path, now="2026-07-14T00:00:00Z")
    assert out["status"] == "written" and out["cards"] == 4
    path = tmp_path / genesis.PROPOSALS_REL
    assert path.name == "outcomes-proposed.yml"  # still the inert filename
    doc = yaml.safe_load(path.read_text())
    whys = " | ".join(str(r.get("why")) for r in doc["outcomes"])
    assert MISSION["purpose"] in whys            # purpose reaches the staging file
    assert MISSION["success_90d"] in whys
    for row in doc["outcomes"]:                  # nothing pre-ratified, ever
        assert row["status"] == "draft"
        assert row["captain_ratified"] is False


# ---------------------------------------------------------------------------
# ONBOARD-1 — the staging file (propose-only, structurally inert)
# ---------------------------------------------------------------------------
def test_write_proposals_targets_the_inert_filename(tmp_path):
    cards = genesis.propose_outcome_cards(ANSWERS)
    res = genesis.write_proposals(cards, tmp_path, answers=ANSWERS,
                                  now="2026-07-10T00:00:00Z")
    assert res["written"] is True
    path = tmp_path / genesis.PROPOSALS_REL
    assert path.is_file()
    # The compiler's filename gate reads ONLY outcomes.yml — never this file.
    assert path.name == "outcomes-proposed.yml"
    assert not (tmp_path / "instance/config/outcomes.yml").exists()

    doc = yaml.safe_load(path.read_text())
    assert doc["deployment"] == "acme-hq"
    assert len(doc["outcomes"]) == 4
    for row in doc["outcomes"]:
        assert row["status"] == "draft"
        assert row["captain_ratified"] is False
        assert row["measurable_criteria"]        # schema-shaped for ratification
        assert row["what"] and row["why"] and row["proof_expected"]
    assert genesis.GENERATED_MARKER in path.read_text()


def test_write_proposals_never_clobbers_existing(tmp_path):
    path = tmp_path / genesis.PROPOSALS_REL
    path.parent.mkdir(parents=True)
    path.write_text("outcomes: []\n# captain edited\n", encoding="utf-8")
    res = genesis.write_proposals(genesis.propose_outcome_cards(ANSWERS),
                                  tmp_path, answers=ANSWERS)
    assert res["status"] == "kept-existing"
    assert "captain edited" in path.read_text()   # untouched


def test_run_genesis_proposal_end_to_end(tmp_path):
    _write_answers(tmp_path)
    (tmp_path / genesis.FOCUS_REL).write_text("Focus: prove the store lane.",
                                              encoding="utf-8")
    out = genesis.run_genesis_proposal(tmp_path, now="2026-07-10T00:00:00Z")
    assert out["status"] == "written" and out["cards"] == 4
    doc = yaml.safe_load((tmp_path / genesis.PROPOSALS_REL).read_text())
    assert genesis.FOCUS_REL in doc["derived_from"]
    # idempotent second run keeps (possibly captain-edited) drafts
    again = genesis.run_genesis_proposal(tmp_path)
    assert again["status"] == "kept-existing"


def test_run_genesis_proposal_without_answers_fails_loud_not_fake(tmp_path):
    out = genesis.run_genesis_proposal(tmp_path)
    assert out == {"status": "no-answers", "path": None, "cards": 0}
    assert not (tmp_path / genesis.PROPOSALS_REL).exists()   # no invented file


# ---------------------------------------------------------------------------
# ONBOARD-2 — brief delivered / honest IOU
# ---------------------------------------------------------------------------
class _Proc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_brief_delivered_writes_real_cli_output(tmp_path):
    _write_answers(tmp_path)
    seen = {}

    def run_fn(argv, *, timeout, cwd):
        seen["argv"], seen["timeout"], seen["cwd"] = argv, timeout, cwd
        return _Proc(0, "## Acme Storefront\nPlausibly an e-commerce product.")

    out = genesis.research_brief(tmp_path, run_fn=run_fn,
                                 net_check_fn=lambda: True,
                                 claude_path="/usr/local/bin/claude",
                                 now="2026-07-10T00:00:00Z")
    assert out["status"] == "delivered"
    body = (tmp_path / genesis.BRIEF_REL).read_text()
    assert "status: delivered" in body
    assert "Plausibly an e-commerce product." in body      # the REAL output
    # fixed argv, no shell: [claude, -p, prompt]
    assert seen["argv"][0] == "/usr/local/bin/claude"
    assert seen["argv"][1] == "-p" and len(seen["argv"]) == 3
    assert seen["cwd"] == str(tmp_path)


def test_brief_prompt_carries_names_only():
    prompt = genesis.build_brief_prompt(ANSWERS)
    assert "Acme Storefront" in prompt and "acme/storefront" in prompt
    assert "12345678" not in prompt          # chat id (an address) never needed
    assert "TELEGRAM" not in prompt          # no env-name noise either


@pytest.mark.parametrize("case,run_fn,expected_reason", [
    ("rc-nonzero", lambda a, *, timeout, cwd: _Proc(1, "", "please /login"),
     "non-zero"),
    ("empty-stdout", lambda a, *, timeout, cwd: _Proc(0, "   "), "no output"),
    ("timeout",
     lambda a, *, timeout, cwd: (_ for _ in ()).throw(
         subprocess.TimeoutExpired(cmd="claude", timeout=timeout)),
     "timed out"),
    ("start-failure",
     lambda a, *, timeout, cwd: (_ for _ in ()).throw(OSError("boom")),
     "failed to start"),
])
def test_brief_failures_write_honest_iou(tmp_path, case, run_fn, expected_reason):
    _write_answers(tmp_path)
    out = genesis.research_brief(tmp_path, run_fn=run_fn,
                                 net_check_fn=lambda: True,
                                 claude_path="/x/claude", timeout=5)
    assert out["status"] == "iou", case
    body = (tmp_path / genesis.BRIEF_REL).read_text()
    assert genesis.IOU_LINE in body                    # the honest promise
    assert "status: iou-queued" in body
    assert expected_reason in out["reason"]


def test_brief_iou_when_cli_missing_without_invoking(tmp_path):
    _write_answers(tmp_path)

    def must_not_run(argv, *, timeout, cwd):
        raise AssertionError("CLI must not be invoked when the binary is absent")

    out = genesis.research_brief(tmp_path, run_fn=must_not_run,
                                 net_check_fn=lambda: True, claude_path=None)
    assert out["status"] == "iou" and "not found" in out["reason"]


def test_brief_iou_when_network_down_without_invoking(tmp_path):
    _write_answers(tmp_path)

    def must_not_run(argv, *, timeout, cwd):
        raise AssertionError("CLI must not be invoked when the network is down")

    out = genesis.research_brief(tmp_path, run_fn=must_not_run,
                                 net_check_fn=lambda: False,
                                 claude_path="/x/claude")
    assert out["status"] == "iou" and "network" in out["reason"]


def test_brief_never_overwrites_delivered_but_upgrades_iou(tmp_path):
    _write_answers(tmp_path)
    # 1) an IOU lands first
    genesis.research_brief(tmp_path, run_fn=lambda a, *, timeout, cwd: _Proc(1),
                           net_check_fn=lambda: True, claude_path="/x/claude")
    assert "iou-queued" in (tmp_path / genesis.BRIEF_REL).read_text()
    # 2) a later successful run UPGRADES the IOU
    out = genesis.research_brief(
        tmp_path, run_fn=lambda a, *, timeout, cwd: _Proc(0, "real brief"),
        net_check_fn=lambda: True, claude_path="/x/claude")
    assert out["status"] == "delivered"
    # 3) a further run never clobbers the delivered brief
    out2 = genesis.research_brief(
        tmp_path, run_fn=lambda a, *, timeout, cwd: _Proc(0, "other text"),
        net_check_fn=lambda: True, claude_path="/x/claude")
    assert out2["status"] == "already-delivered"
    assert "real brief" in (tmp_path / genesis.BRIEF_REL).read_text()


def test_brief_timeout_env_knob_is_honored(tmp_path, monkeypatch):
    _write_answers(tmp_path)
    seen = {}

    def run_fn(argv, *, timeout, cwd):
        seen["timeout"] = timeout
        return _Proc(0, "brief")

    monkeypatch.setenv("CABINET_GENESIS_BRIEF_TIMEOUT", "17")
    genesis.research_brief(tmp_path, run_fn=run_fn, net_check_fn=lambda: True,
                           claude_path="/x/claude")
    assert seen["timeout"] == 17


@pytest.mark.parametrize("bad", ["abc", "", "-5", "0", "9.5"])
def test_brief_timeout_malformed_env_falls_back_not_crashes(tmp_path, monkeypatch, bad):
    _write_answers(tmp_path)
    seen = {}

    def run_fn(argv, *, timeout, cwd):
        seen["timeout"] = timeout
        return _Proc(0, "brief")

    monkeypatch.setenv("CABINET_GENESIS_BRIEF_TIMEOUT", bad)
    out = genesis.research_brief(tmp_path, run_fn=run_fn,
                                 net_check_fn=lambda: True,
                                 claude_path="/x/claude")
    assert out["status"] == "delivered"          # no traceback over a bad knob
    assert seen["timeout"] == genesis._DEFAULT_BRIEF_TIMEOUT


def test_net_target_env_override_and_malformed_port_fallback(monkeypatch):
    monkeypatch.delenv("CABINET_GENESIS_NET_HOST", raising=False)
    monkeypatch.delenv("CABINET_GENESIS_NET_PORT", raising=False)
    assert genesis._net_target() == (genesis._NET_HOST, genesis._NET_PORT)
    monkeypatch.setenv("CABINET_GENESIS_NET_HOST", "proxy.example.internal")
    monkeypatch.setenv("CABINET_GENESIS_NET_PORT", "8443")
    assert genesis._net_target() == ("proxy.example.internal", 8443)
    monkeypatch.setenv("CABINET_GENESIS_NET_PORT", "not-a-port")
    assert genesis._net_target() == ("proxy.example.internal", genesis._NET_PORT)
    monkeypatch.setenv("CABINET_GENESIS_NET_HOST", "   ")
    assert genesis._net_target()[0] == genesis._NET_HOST   # blank host → default


# ---------------------------------------------------------------------------
# The briefing gather — composer-shaped items, honest empties
# ---------------------------------------------------------------------------
def test_genesis_intake_items_shape_and_content(tmp_path):
    _write_answers(tmp_path)
    (tmp_path / genesis.FOCUS_REL).write_text("Prove the store lane first.",
                                              encoding="utf-8")
    genesis.run_genesis_proposal(tmp_path)
    genesis.research_brief(tmp_path, run_fn=lambda a, *, timeout, cwd: _Proc(1),
                           net_check_fn=lambda: True, claude_path="/x/claude")

    items = genesis.genesis_intake_items(tmp_path, now="2026-07-10T00:00:00Z")
    for it in items:
        intake.validate_item(it)             # canonical intake shape holds

    cards = [i for i in items if i["kind"] == "outcome-proposal"]
    assert len(cards) == 4
    for c in cards:
        s = c["payload"]["summary"]
        assert s.startswith("📜 Proposed outcome:")
        assert "WHAT:" in s and "WHY:" in s and "PROOF-expected:" in s
        assert "captain_ratified: false" in s      # propose-only, visibly

    briefs = [i for i in items if i["kind"] == "genesis-brief"]
    assert len(briefs) == 1
    assert genesis.IOU_LINE in briefs[0]["payload"]["summary"]   # honest IOU

    focus = [i for i in items if i["kind"] == "genesis-focus"]
    assert len(focus) == 1


def test_genesis_intake_items_honest_empty_on_bare_root(tmp_path):
    assert genesis.genesis_intake_items(tmp_path) == []


def test_contribute_fund_fyi_card_renders_once_and_propose_only(tmp_path):
    """The contribution design's single placement: ONE genesis-contribute FYI
    card per genesis briefing — propose-only, never an activatable outcome,
    absent entirely on bare roots (asked once, never nagged)."""
    _write_answers(tmp_path)
    genesis.run_genesis_proposal(tmp_path)
    items = genesis.genesis_intake_items(tmp_path, now="2026-07-10T00:00:00Z")
    for it in items:
        intake.validate_item(it)                 # canonical shape holds

    cards = [i for i in items if i["kind"] == "genesis-contribute"]
    assert len(cards) == 1                       # exactly once, never repeated
    card = cards[0]
    assert card["urgency_tier"] == "fyi"         # information — never action
    s = card["payload"]["summary"]
    assert "cabinet-feedback" in s               # the contribute pointer
    assert "opencollective.com/captains-cabinet" in s    # the fund pointer
    assert "Propose-only" in s                   # says so, visibly
    assert "asked once" in s                     # never-nag contract, visibly
    # It must never read as an activatable outcome card: not the proposal
    # kind, and never the literal the first-briefing receipt gate counts.
    assert card["kind"] != "outcome-proposal"
    assert "Proposed outcome:" not in s
    # Asked once at GENESIS only — a bare root renders no ask at all.
    assert genesis.genesis_intake_items(tmp_path / "bare") == []
