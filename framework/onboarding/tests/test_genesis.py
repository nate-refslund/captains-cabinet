"""genesis (ONBOARD-1/2) — propose-only outcome cards + brief-or-honest-IOU.

Hermetic: tmp_path roots, injected run_fn/net_check_fn seams — no real
subprocess, no network, no Redis, and never the checkout's own instance/.

The one exception is the planted-canary arm at the bottom, which deliberately
exercises the REAL ``_default_run`` subprocess against a STUB ``claude`` shell
script under a FAKE $HOME — no network and no auth, but a real process, because
the property under test (what the child can reach) is not observable through
the injected seam.
"""
import os
import re
import stat
import subprocess
from pathlib import Path

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
    """INVERTED 2026-07-26 (ordering inversion, Captain ruling): a lane-less
    deployment used to derive 2 cards — both of them org ceremony, and the
    Captain's verdict on exactly that briefing was "the cards were
    irrelevant". A cabinet that has been told nothing and has read nothing now
    proposes the leftover-question card instead of saying nothing about the operator at
    all, so 0 lanes derives 3. The 2-4 band itself is unchanged."""
    one_lane = {**ANSWERS, "lanes": ANSWERS["lanes"][:1]}
    no_lanes = {**ANSWERS, "lanes": []}
    many = {**ANSWERS, "lanes": ANSWERS["lanes"] * 3}   # 6 declared lanes
    assert len(genesis.propose_outcome_cards(one_lane)) == 3
    assert len(genesis.propose_outcome_cards(no_lanes)) == 3
    ids = [c["id"] for c in genesis.propose_outcome_cards(no_lanes)]
    assert ids[0] == "proposed-read-your-world"
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


def test_cards_condition_on_role_and_dream_seams():
    """The stepped first run collects role and dream as two clean questions, and
    each lands on the seam genesis ALREADY reads: role -> the journey seed, dream
    -> mission.purpose. So genesis conditions on BOTH — richer than the one blurred
    seed — with no parallel field invented. Proven where own-words drive the
    probes (no lanes to fill them first): the dream conditions the probes when it
    is present, and the role conditions them on its own."""
    with_dream = {**ANSWERS, "lanes": [],
                  "mission": {"purpose": "A thriving ryokan by the quiet sea."},
                  "seed": "careful innkeeping"}
    dream_labels = " ".join(p["label"].lower() for p in genesis.recall_probes(
        with_dream, seed="careful innkeeping"))
    assert "ryokan" in dream_labels          # the dream (mission.purpose) conditions

    role_only = {**ANSWERS, "lanes": [], "seed": "careful innkeeping"}
    role_labels = " ".join(p["label"].lower() for p in genesis.recall_probes(
        role_only, seed="careful innkeeping"))
    assert "innkeeping" in role_labels       # the role (journey seed) conditions
    assert "ryokan" not in role_labels       # and the dream genuinely ADDS a subject


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
    # `recall` joined the return shape 2026-07-28 (empty here: nothing to probe
    # about a deployment whose answers do not exist).
    assert out == {"status": "no-answers", "path": None, "cards": 0,
                   "recall": {}}
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

    def run_fn(argv, *, timeout, cwd, env=None):
        seen["argv"], seen["timeout"], seen["cwd"] = argv, timeout, cwd
        seen["env"] = env
        return _Proc(0, "## Acme Storefront\nPlausibly an e-commerce product.")

    out = genesis.research_brief(tmp_path, run_fn=run_fn,
                                 net_check_fn=lambda: True,
                                 claude_path="/usr/local/bin/claude",
                                 now="2026-07-10T00:00:00Z")
    assert out["status"] == "delivered"
    body = (tmp_path / genesis.BRIEF_REL).read_text()
    assert "status: delivered" in body
    assert "Plausibly an e-commerce product." in body      # the REAL output
    # fixed argv, no shell: [claude, -p, prompt, --setting-sources project,local]
    assert seen["argv"][0] == "/usr/local/bin/claude"
    assert seen["argv"][1] == "-p" and len(seen["argv"]) == 5
    # OPERATOR-CONTEXT ISOLATION (see genesis.py). These three assertions are
    # the regression guard for a MEASURED leak: before the fix, a hatch of the
    # public egg produced a brief naming the operator's real employer and four
    # real products that exist nowhere in the egg tree.
    assert seen["argv"][3] == "--setting-sources"
    assert "user" not in seen["argv"][4].split(","), (
        "the `user` setting source re-opens ~/.claude/CLAUDE.md + personal memory")
    # cwd must NOT be the instance root: that root sits under $HOME, and the
    # CLI's CLAUDE.md ancestor walk would climb from it to the operator's own.
    assert seen["cwd"] != str(tmp_path)
    assert Path(seen["cwd"]).is_dir()
    assert not any(Path(seen["cwd"]).iterdir()), (
        "the genesis cwd must be EMPTY — any CLAUDE.md/.remember/.claude in it "
        "is auto-discovered project context")
    # HOME intact (macOS keychain/OAuth is HOME-anchored — a fake HOME or a
    # throwaway CLAUDE_CONFIG_DIR silently downgrades the organ to an IOU),
    # ANTHROPIC_API_KEY stripped (never silently bill pay-as-you-go).
    assert seen["env"]["HOME"] == os.environ["HOME"]
    assert "ANTHROPIC_API_KEY" not in seen["env"]
    assert "CLAUDE_CONFIG_DIR" not in seen["env"]


def test_brief_prompt_carries_names_only():
    prompt = genesis.build_brief_prompt(ANSWERS)
    assert "Acme Storefront" in prompt and "acme/storefront" in prompt
    assert "12345678" not in prompt          # chat id (an address) never needed
    assert "TELEGRAM" not in prompt          # no env-name noise either


@pytest.mark.parametrize("case,run_fn,expected_reason", [
    ("rc-nonzero", lambda a, *, timeout, cwd, env=None: _Proc(1, "", "please /login"),
     "non-zero"),
    ("empty-stdout", lambda a, *, timeout, cwd, env=None: _Proc(0, "   "), "no output"),
    ("timeout",
     lambda a, *, timeout, cwd, env=None: (_ for _ in ()).throw(
         subprocess.TimeoutExpired(cmd="claude", timeout=timeout)),
     "timed out"),
    ("start-failure",
     lambda a, *, timeout, cwd, env=None: (_ for _ in ()).throw(OSError("boom")),
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

    def must_not_run(argv, *, timeout, cwd, env=None):
        raise AssertionError("CLI must not be invoked when the binary is absent")

    out = genesis.research_brief(tmp_path, run_fn=must_not_run,
                                 net_check_fn=lambda: True, claude_path=None)
    assert out["status"] == "iou" and "not found" in out["reason"]


def test_brief_iou_when_network_down_without_invoking(tmp_path):
    _write_answers(tmp_path)

    def must_not_run(argv, *, timeout, cwd, env=None):
        raise AssertionError("CLI must not be invoked when the network is down")

    out = genesis.research_brief(tmp_path, run_fn=must_not_run,
                                 net_check_fn=lambda: False,
                                 claude_path="/x/claude")
    assert out["status"] == "iou" and "network" in out["reason"]


def test_brief_never_overwrites_delivered_but_upgrades_iou(tmp_path):
    _write_answers(tmp_path)
    # 1) an IOU lands first
    genesis.research_brief(tmp_path, run_fn=lambda a, *, timeout, cwd, env=None: _Proc(1),
                           net_check_fn=lambda: True, claude_path="/x/claude")
    assert "iou-queued" in (tmp_path / genesis.BRIEF_REL).read_text()
    # 2) a later successful run UPGRADES the IOU
    out = genesis.research_brief(
        tmp_path, run_fn=lambda a, *, timeout, cwd, env=None: _Proc(0, "real brief"),
        net_check_fn=lambda: True, claude_path="/x/claude")
    assert out["status"] == "delivered"
    # 3) a further run never clobbers the delivered brief
    out2 = genesis.research_brief(
        tmp_path, run_fn=lambda a, *, timeout, cwd, env=None: _Proc(0, "other text"),
        net_check_fn=lambda: True, claude_path="/x/claude")
    assert out2["status"] == "already-delivered"
    assert "real brief" in (tmp_path / genesis.BRIEF_REL).read_text()


def test_brief_timeout_env_knob_is_honored(tmp_path, monkeypatch):
    _write_answers(tmp_path)
    seen = {}

    def run_fn(argv, *, timeout, cwd, env=None):
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

    def run_fn(argv, *, timeout, cwd, env=None):
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
    genesis.research_brief(tmp_path, run_fn=lambda a, *, timeout, cwd, env=None: _Proc(1),
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


# ---------------------------------------------------------------------------
# OPERATOR-CONTEXT LEAK — the planted-canary arm.
#
# MEASURED 2026-07-26, on the real thing: a clean-room hatch of the PUBLIC egg,
# for a lane whose only name is the placeholder "First Lane" and which carries
# no product metadata at all, produced a research brief naming the operator's
# real employer and four real products that exist NOWHERE in the egg tree. The
# brief said so itself: "Inference from this deployment's ambient captain
# context (not from lane config)". That artifact is promoted as "the org's
# baseline understanding of its products and market" and indexed into org
# memory, so every hatched cabinet absorbed its operator's private notes.
#
# WHY A STUB, AND WHAT IT FAITHFULLY MODELS. The property under test is what
# the CHILD PROCESS can reach, which the injected run_fn seam cannot observe —
# so this arm runs the REAL `_default_run` against a stub `claude` shell
# script. The stub implements Claude Code's two DOCUMENTED discovery tiers and
# nothing else, so the assertion is about the isolation contract rather than
# about any CLI build:
#   (a) PROJECT tier  — always walk UP from $PWD collecting CLAUDE.md.
#   (b) USER-GLOBAL tier — load $HOME/.claude/CLAUDE.md ONLY when `user` is
#       among --setting-sources (absent flag == all sources, the CLI default).
# Modelling (b) as flag-conditional is the whole point: $HOME is deliberately
# left INTACT by the fix (the macOS keychain/OAuth is HOME-anchored, so a fake
# HOME or a throwaway CLAUDE_CONFIG_DIR silently downgrades the organ to an
# IOU). Mere filesystem reachability of ~/.claude/CLAUDE.md is therefore NOT
# the bug; loading it as a context source is.
#
# No network, no auth, no token spend: net_check_fn is stubbed and the fake
# CLI exits 0 with its own text.
# ---------------------------------------------------------------------------

_CANARY = "CANARY-7f3a91-OPERATOR-EMPLOYER-DO-NOT-LEAK"

_STUB_CLAUDE = r"""#!/bin/bash
# Faithful stub of the two documented CLAUDE.md discovery tiers.
sources="all"
prev=""
for a in "$@"; do
  [ "$prev" = "--setting-sources" ] && sources="$a"
  prev="$a"
done
echo "STUB-CWD=$PWD"
echo "STUB-SOURCES=$sources"
# (a) PROJECT tier: ancestor walk from $PWD, always active.
d="$PWD"
while [ -n "$d" ] && [ "$d" != "/" ]; do
  [ -f "$d/CLAUDE.md" ] && cat "$d/CLAUDE.md"
  [ -f "$d/.claude/CLAUDE.md" ] && cat "$d/.claude/CLAUDE.md"
  d="$(dirname "$d")"
done
# (b) USER-GLOBAL tier: only when the `user` source is in scope.
case ",$sources," in
  *,user,*|*,all,*) [ -f "$HOME/.claude/CLAUDE.md" ] && cat "$HOME/.claude/CLAUDE.md" ;;
esac
echo "STUB-END"
"""


def _plant_canary_home(tmp_path):
    """A fake $HOME carrying the canary in BOTH reachable positions, with the
    instance root nested UNDER it — the real-world shape RES-002 names (the
    cabinet lives under $HOME, so an ancestor walk from it climbs to the
    operator's personal notes)."""
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text(
        f"# personal notes\nMy employer is {_CANARY}.\n", encoding="utf-8")
    (home / "CLAUDE.md").write_text(
        f"# personal notes\nMy employer is {_CANARY}.\n", encoding="utf-8")
    root = home / "cabinet"
    root.mkdir()
    _write_answers(root)
    stub = tmp_path / "bin" / "claude"
    stub.parent.mkdir(parents=True)
    stub.write_text(_STUB_CLAUDE, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return home, root, stub


def test_genesis_cannot_read_a_planted_string_from_a_fake_home(tmp_path, monkeypatch):
    """The regression guard: a genesis run must not be able to reach a canary
    planted in the operator's personal CLAUDE.md."""
    home, root, stub = _plant_canary_home(tmp_path)
    monkeypatch.setenv("HOME", str(home))

    out = genesis.research_brief(root, net_check_fn=lambda: True,
                                 claude_path=str(stub),
                                 now="2026-07-26T00:00:00Z")

    assert out["status"] == "delivered", (
        f"the stub CLI must succeed, else this arm proves nothing: {out}")
    body = (root / genesis.BRIEF_REL).read_text(encoding="utf-8")
    assert "STUB-END" in body, "the real subprocess path did not run"
    assert _CANARY not in body, (
        "OPERATOR CONTEXT LEAKED into the genesis research brief — the very "
        "artifact promoted as the org's baseline understanding of its market")


def test_the_canary_arm_is_not_vacuous(tmp_path, monkeypatch):
    """NEGATIVE CONTROL. A sensor nobody has tried to defeat is an assumption.

    Drive the SAME stub the pre-fix way — cwd = the instance root, no
    --setting-sources — and the canary MUST come back. If this ever stops
    leaking, the stub stopped modelling the discovery it exists to model, and
    the arm above would be passing vacuously.
    """
    home, root, stub = _plant_canary_home(tmp_path)
    monkeypatch.setenv("HOME", str(home))

    proc = genesis._default_run([str(stub), "-p", "prompt"],
                                timeout=30, cwd=str(root),
                                env={**os.environ, "HOME": str(home)})

    assert proc.returncode == 0
    assert _CANARY in proc.stdout, (
        "the pre-fix invocation no longer leaks the canary — the stub is not "
        "modelling CLAUDE.md discovery any more, so the positive arm is vacuous")


# ---------------------------------------------------------------------------
# ONBOARD-1 — the ORDERING INVERSION: cards from what the cabinet READ
# ---------------------------------------------------------------------------
LANELESS = {**ANSWERS, "lanes": []}

ESTATE_DOC = {
    "schema": "cabinet.derived-estate/v1",
    "deployment": "acme-hq",
    "derived_at": "2026-07-26T00:00:00Z",
    # THE PRODUCER'S OWN SHAPE, not a hand-rolled one. This fixture used to
    # carry `root` and `refusals` as a list of {reason, count} — a shape
    # `estate.py` never writes. The consumer was coded against the fixture, so
    # its refusal count was structurally 0 on every real sweep while this test
    # went green: a sensor wired to something other than the control. The
    # canonical record is `framework.authority.ownership.access_record`:
    # `source_root`, `refusals` as a class->count MAPPING, and a pre-summed
    # `refusals_total`. test_estate_provenance_fields_match_the_real_record
    # below now pins that agreement so it cannot drift again.
    "sources": [{"id": "first-window", "kind": "local_folder",
                 "source_root": "/granted", "ownership": "unclassified",
                 "refusals": {"sensitive_name": 2}, "refusals_total": 2}],
    "entities": [
        {"id": "storefront", "name": "storefront", "kind": "project",
         "source_id": "first-window", "relative_path": "storefront",
         "evidence": [{"path": "storefront/README.md", "sha256": "aa"}]},
        {"id": "labs", "name": "labs", "kind": "project",
         "source_id": "first-window", "relative_path": "labs",
         "evidence": [{"path": "labs/pyproject.toml", "sha256": "bb"}]},
    ],
}


def test_estate_entities_become_subject_cards_with_their_citation():
    cards = genesis.propose_outcome_cards(LANELESS, estate=ESTATE_DOC)
    subject = [c for c in cards if c["derived_from"] == "estate"]
    assert [c["lane"] for c in subject] == ["storefront", "labs"]
    assert "storefront/README.md" in subject[0]["why"]     # cited, not asserted
    assert "reading your world, not by asking" in subject[0]["why"]
    for card in cards:                                     # propose-only holds
        assert card["status"] == "draft" and card["captain_ratified"] is False


def test_declared_lanes_win_over_derived_entities():
    """The Captain's own declaration outranks a derivation of the same thing —
    and a derived entity never duplicates a declared lane's slug."""
    answers = {**ANSWERS, "lanes": [{"name": "Storefront", "slug": "storefront"}]}
    cards = genesis.propose_outcome_cards(answers, estate=ESTATE_DOC)
    subject = [c for c in cards if c["derived_from"] in ("answers", "estate")]
    assert [c["lane"] for c in subject] == ["storefront", "labs"]
    assert subject[0]["derived_from"] == "answers"
    assert len({c["id"] for c in cards}) == len(cards)


def test_residual_card_asks_the_three_underivable_questions_not_the_company():
    cards = genesis.propose_outcome_cards(LANELESS)
    residual = next(c for c in cards if c["id"] == "proposed-read-your-world")
    assert residual["derived_from"] == "residual"
    why = residual["why"].lower()
    assert "yours to grant" in why            # (a) authority
    assert "matters to you this week" in why  # (b) salience
    assert "never touch" in why               # (c) limits
    assert "how i can best serve you" in why  # the seed question — never a dead end
    # The question the system must never ask again.
    for card in cards:
        assert "what is your company" not in card["why"].lower()
        assert "tell us what your company" not in card["what"].lower()


def test_residual_card_distinguishes_read_nothing_from_found_nothing():
    nothing_read = genesis.propose_outcome_cards(LANELESS)[0]["why"]
    empty_estate = dict(ESTATE_DOC, entities=[])
    read_found_none = genesis.propose_outcome_cards(
        LANELESS, estate=empty_estate)[0]["why"]
    assert "have not read anything" in nothing_read
    assert "found nothing" in read_found_none


# --- altitude reaches PROPOSED-CARD DERIVATION (or it is decoration) --------
def _proofs(answers, **kw):
    return [c["proof_expected"] for c in genesis.propose_outcome_cards(answers, **kw)]


def test_altitude_reshapes_the_subject_proof_line():
    low = {**ANSWERS, "mission": {"altitude": "contributor"}}
    high = {**ANSWERS, "mission": {"altitude": "company"}}
    low_proof = _proofs(low)[0]
    high_proof = _proofs(high)[0]
    assert low_proof != high_proof
    # Low altitude: reach + proposal quality, never permission the operator
    # does not hold (the six ceiling classes belong to their employer).
    assert "written proposal" in low_proof and "owns the decision" in low_proof
    assert "shipped change" not in low_proof
    assert "shipped change" in high_proof


@pytest.mark.parametrize("rung,proposal_shaped", [
    ("contributor", True), ("project", True), ("team", True),
    ("function", False), ("company", False),
])
def test_every_rung_maps_to_exactly_one_proof_shape(rung, proposal_shaped):
    answers = {**ANSWERS, "mission": {"altitude": rung}}
    assert ("written proposal" in _proofs(answers)[0]) is proposal_shaped


def test_absent_or_unknown_altitude_derives_the_pre_altitude_cards():
    """Unknown is a first-class answer: nobody was asked, so nothing changes."""
    baseline = genesis.propose_outcome_cards(ANSWERS)
    for mission in (None, {}, {"altitude": None}, {"altitude": "vice-president"}):
        assert genesis.propose_outcome_cards({**ANSWERS, "mission": mission}) == baseline


def test_estate_reaches_the_staging_file_and_is_recorded_as_provenance(tmp_path):
    from framework.onboarding import estate as estate_mod
    _write_answers(tmp_path, LANELESS)
    estate_mod.write_estate(ESTATE_DOC, tmp_path)
    out = genesis.run_genesis_proposal(tmp_path, now="2026-07-26T00:00:00Z")
    assert out["status"] == "written" and out["cards"] == 4
    doc = yaml.safe_load((tmp_path / genesis.PROPOSALS_REL).read_text())
    assert estate_mod.ESTATE_REL in doc["derived_from"]
    assert {r["derived_from"] for r in doc["outcomes"]} == {"estate", "system"}


def test_a_foreign_estate_is_ignored_not_consumed(tmp_path):
    """An artifact derived for another deployment must not feed this one's
    cards — the same gate the generator applies to lanes: []."""
    from framework.onboarding import estate as estate_mod
    _write_answers(tmp_path, LANELESS)
    estate_mod.write_estate(dict(ESTATE_DOC, deployment="someone-else"), tmp_path)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-26T00:00:00Z")
    doc = yaml.safe_load((tmp_path / genesis.PROPOSALS_REL).read_text())
    assert [r["id"] for r in doc["outcomes"]][0] == "proposed-read-your-world"


def test_estate_intake_item_shows_provenance_including_refusals(tmp_path):
    from framework.onboarding import estate as estate_mod
    _write_answers(tmp_path, LANELESS)
    estate_mod.write_estate(ESTATE_DOC, tmp_path)
    items = genesis.genesis_intake_items(tmp_path, now="2026-07-26T00:00:00Z")
    card = next(i for i in items if i["kind"] == "genesis-estate")
    summary = card["payload"]["summary"]
    assert "1 source(s)" in summary and "2 entity(ies)" in summary
    assert "2 refused" in summary           # silent skips destroy auditability
    assert "unclassified" in summary
    assert card["urgency_tier"] == "fyi"    # information; nothing acts on it


def test_estate_provenance_fields_match_the_real_record(tmp_path):
    """The consumer must read keys the PRODUCER actually writes.

    Built from ``access_record`` itself — the one function that defines the
    per-source shape — rather than from a hand-written dict, because the
    hand-written dict is exactly how this drifted: the briefing summed a
    mapping as if it were a list and reported 0 refusals for every real sweep,
    and the fixture agreed with the bug. Feeding the genuine record proves the
    count and the root survive the trip to the operator.
    """
    from framework.authority.ownership import access_record
    from framework.onboarding import estate as estate_mod

    record = access_record(
        schema=estate_mod.SCHEMA, source_root="/granted/notes",
        ownership="self", authority_basis="owner",
        charter_hash="c" * 64, manifest_hash="m" * 64, entry_count=9,
        refusals={"sensitive_name": 2, "too_large": 3},
        retention="paths, hashes and counts only; no file contents persisted",
        recorded_at="2026-07-26T00:00:00Z",
    )
    row = {"id": "first-window", "kind": "local_folder", "label": "notes"}
    row.update(record)
    _write_answers(tmp_path, LANELESS)
    estate_mod.write_estate(dict(ESTATE_DOC, sources=[row]), tmp_path)

    items = genesis.genesis_intake_items(tmp_path, now="2026-07-26T00:00:00Z")
    summary = next(i for i in items if i["kind"] == "genesis-estate")["payload"]["summary"]
    assert "5 refused" in summary        # 2 + 3, not the structural 0
    assert "/granted/notes" in summary   # source_root, not the label fallback


def test_estate_provenance_never_claims_a_citation_it_did_not_earn(tmp_path):
    """The FYI line may only say the cards derive from the estate when one does.

    Nothing in the shipped chain runs formation.sh before the first briefing
    and ``write_proposals`` is write-once, so the ordinary ordering leaves
    cards that predate the estate. Asserting the citation anyway is the
    unearned claim this unit exists to remove, one surface up.
    """
    from framework.onboarding import estate as estate_mod
    _write_answers(tmp_path, LANELESS)

    # (a) proposals written with NO estate → no card can derive from one.
    genesis.run_genesis_proposal(tmp_path, now="2026-07-26T00:00:00Z")
    estate_mod.write_estate(ESTATE_DOC, tmp_path)
    why = next(i for i in genesis.genesis_intake_items(tmp_path, now="2026-07-26T00:00:00Z")
               if i["kind"] == "genesis-estate")["context"]["why"]
    assert "No card above derives from it" in why
    assert "with citations" not in why

    # (b) estate present BEFORE the proposals are written → the claim is earned.
    (tmp_path / genesis.PROPOSALS_REL).unlink()
    genesis.run_genesis_proposal(tmp_path, now="2026-07-26T00:00:00Z")
    why = next(i for i in genesis.genesis_intake_items(tmp_path, now="2026-07-26T00:00:00Z")
               if i["kind"] == "genesis-estate")["context"]["why"]
    assert "with citations" in why


def test_no_estate_artifact_means_no_estate_item(tmp_path):
    _write_answers(tmp_path, LANELESS)
    items = genesis.genesis_intake_items(tmp_path, now="2026-07-26T00:00:00Z")
    assert not [i for i in items if i["kind"] == "genesis-estate"]


# ---------------------------------------------------------------------------
# RECALL — the briefing READS what recall already holds (2026-07-28).
#
# THE MEASUREMENT THAT PRODUCED THESE ARMS. An agent ran the genuine hatch path
# end to end and scored the resulting first briefing 1 of 3 — "read it, no
# value". Recall on that box was LIVE (available() True; probes returned dated,
# cited hits) and its notes folder held a live incident spread across three
# files. Every card in the briefing was composed from the answers file alone,
# because nothing in the genesis chain ever called get_source().
#
# Each arm below fails against the pre-change code by construction — there was
# no recall parameter, no probe, and no citation anywhere to assert on.
# ---------------------------------------------------------------------------
class _FakeSource:
    """A PersonalSource-shaped stub over a fixed corpus. NOT the degenerate
    'return nothing' stub: a stub that answers nothing would make every arm
    below pass while asserting the defect."""

    def __init__(self, corpus=None, available=True, raises=False):
        self.corpus = corpus if corpus is not None else _CORPUS
        self._available = available
        self._raises = raises
        self.queries = []

    def available(self):
        if self._raises:
            raise RuntimeError("backend down")
        return self._available

    def search(self, handle, *, topic=None):
        self.queries.append(handle)
        terms = {w.lower() for w in re.findall(r"[a-z0-9_]{3,}", handle.lower())}
        hits = [h for h in self.corpus
                if terms & {w.lower() for w in
                            re.findall(r"[a-z0-9_]{3,}", (h["text"] + " " + h["ref"]).lower())}]
        return {"hits": hits, "topic_terms": None}


_CORPUS = [
    {"source": "local", "ref": "incidents/2026-07-21-latency.md#Impact",
     "path": "incidents/2026-07-21-latency.md", "heading": "Impact",
     "text": "Impact tax_quote p99 climbed to 1.9s after the billing migration "
             "cutover on storefront checkout.",
     "base_score": 0.42, "who": "", "ts": "2026-07-21T00:00:00Z",
     "content_ts": "2026-07-21T00:00:00Z"},
    {"source": "local", "ref": "decisions/2026-07-14-billing.md#Rollback window",
     "path": "decisions/2026-07-14-billing.md", "heading": "Rollback window",
     "text": "Rollback window The billing migration rollback window closes "
             "2026-07-31 for storefront.",
     "base_score": 0.55, "who": "", "ts": "2026-07-14T00:00:00Z",
     "content_ts": "2026-07-14T00:00:00Z"},
    {"source": "local", "ref": "slo/error-budget.md#July",
     "path": "slo/error-budget.md", "heading": "July",
     "text": "July The storefront error budget burns out 2026-07-30 at the "
             "current latency; a further regression triggers a freeze.",
     "base_score": 0.31, "who": "", "ts": None, "content_ts": "2026-07-01T00:00:00Z"},
]


def _recall_for(answers=ANSWERS, **kw):
    return genesis.probe_recall(answers, kw.pop("focus_text", None), **kw)


def test_probe_recall_asks_the_bound_seam_about_declared_subjects():
    src = _FakeSource()
    got = _recall_for(source=src)
    assert got["consulted"] is True and got["available"] is True
    assert got["probes"] == ["Acme Storefront", "Acme Labs"]
    assert src.queries, "the seam was never asked anything"
    assert got["hits_total"] > 0


def test_recall_hits_reach_the_card_with_file_and_date_citations():
    """The property the 1-of-3 briefing lacked: a claim the operator can open
    and check. Every cite carries a ref AND a derived date."""
    cards = genesis.propose_outcome_cards(ANSWERS, recall=_recall_for(source=_FakeSource()))
    card = cards[0]
    assert card["derived_from"] == "recall"
    assert "incidents/2026-07-21-latency.md#Impact" in card["what"]
    assert "dated 2026-07-21" in card["what"]
    assert card["recall_refs"], "no citation list on a recall-derived card"
    # The operator's own words, verbatim, with the file beside them.
    assert "tax_quote p99 climbed" in card["why"]
    assert "incidents/2026-07-21-latency.md#Impact" in card["why"]


def test_the_card_names_the_join_across_distinct_files_newest_first():
    """The value is the JOIN — several of the operator's own files, dated, in
    time order, with the wording they share. Score order buried the live note
    behind whichever page repeated the query terms most."""
    card = genesis.propose_outcome_cards(
        ANSWERS, recall=_recall_for(source=_FakeSource()))[0]
    what = card["what"]
    first = what.index("incidents/2026-07-21-latency.md")
    second = what.index("decisions/2026-07-14-billing.md")
    third = what.index("slo/error-budget.md")
    assert first < second < third, "citations are not in newest-first order"
    # The caption carries HOW MANY of the cited files share the words. Here
    # the join is genuine but partial (2 of the 3), and saying "Shared
    # wording:" flat would assert something the third cited file does not
    # show — the operator finds that out by opening it.
    assert "Shared wording (in 2 of the 3): " in what and "migration" in what
    assert "2026-07-01 … 2026-07-21" in what      # the span, stated
    assert "3 of your own notes" in card["name"]  # named after what was FOUND


def test_one_entry_per_file_never_two_headings_of_the_same_note():
    """Two headings out of one note are ONE source; listing both reads as a
    join that is not there."""
    twin = dict(_CORPUS[0], ref="incidents/2026-07-21-latency.md#What we know",
                heading="What we know", base_score=0.9)
    recall = _recall_for(source=_FakeSource(corpus=[twin] + _CORPUS))
    subject = recall["subjects"][0]
    assert len(subject["files"]) == len(set(subject["files"]))


def test_quote_drops_the_heading_the_citation_already_names():
    card = genesis.propose_outcome_cards(
        ANSWERS, recall=_recall_for(source=_FakeSource()))[0]
    assert '"Impact tax_quote' not in card["why"], (
        "the heading is quoted twice — once in the cite, once inside the quote")
    assert '"tax_quote p99' in card["why"]


def test_no_recall_derives_byte_identical_cards():
    """An unearned citation is the defect this removes. Recall that answered
    nothing must change NOTHING — including a seam that is down."""
    baseline = genesis.propose_outcome_cards(ANSWERS)
    for source in (_FakeSource(corpus=[]), _FakeSource(available=False),
                   _FakeSource(raises=True)):
        got = genesis.propose_outcome_cards(
            ANSWERS, recall=_recall_for(source=source))
        assert got == baseline
        assert all("recall_refs" not in c for c in got), (
            "an empty citation list is still a citation key — a card that "
            "cited nothing must carry none")
    assert genesis.propose_outcome_cards(ANSWERS, recall=None) == baseline


def test_a_broken_seam_is_recorded_never_raised():
    got = _recall_for(source=_FakeSource(raises=True))
    assert got["available"] is False and "RuntimeError" in (got["error"] or "")


def test_recall_probe_is_skippable_by_env(monkeypatch):
    monkeypatch.setenv("CABINET_GENESIS_RECALL", "0")
    got = genesis.probe_recall(ANSWERS)
    assert got["consulted"] is False and "CABINET_GENESIS_RECALL=0" in got["error"]


def test_recall_is_not_probed_for_a_foreign_root(tmp_path, monkeypatch):
    """get_source() answers for CABINET_ROOT and no other tree. Probing the
    live checkout's binding on behalf of a scratch instance would attribute one
    deployment's recall to another."""
    monkeypatch.delenv("CABINET_GENESIS_RECALL", raising=False)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path / "elsewhere"))
    got = genesis.probe_recall(ANSWERS, root=tmp_path)
    assert got["consulted"] is False and "CABINET_ROOT" in (got["error"] or "")


def test_probes_are_derived_never_invented():
    """No declaration and no estate ⇒ no probe. A probe invented here is the
    guessing the read-don't-ask direction removes."""
    assert genesis.recall_probes(LANELESS) == []
    assert genesis.recall_probes(ANSWERS)[0]["label"] == "Acme Storefront"


def test_altitude_reaches_the_subject_what_not_only_the_proof():
    """The measured leftover: the WHAT line ended "verified deploy/close" at
    EVERY rung — precisely the authority an IC does not hold, i.e. the altitude
    failure the proof line was already fixed for, one layer down."""
    low = genesis.propose_outcome_cards({**ANSWERS, "mission": {"altitude": "contributor"}})
    high = genesis.propose_outcome_cards({**ANSWERS, "mission": {"altitude": "company"}})
    assert "verified deploy/close" not in low[0]["what"]
    assert "written proposal" in low[0]["what"]
    assert "verified deploy/close" in high[0]["what"]


def test_recall_card_closes_at_the_operators_altitude():
    recall = _recall_for(source=_FakeSource())
    low = genesis.propose_outcome_cards(
        {**ANSWERS, "mission": {"altitude": "contributor"}}, recall=recall)[0]
    high = genesis.propose_outcome_cards(
        {**ANSWERS, "mission": {"altitude": "company"}}, recall=recall)[0]
    assert "whoever owns the decision" in low["what"]
    assert "ship the change it argues for" in high["what"]


def test_recall_refs_are_persisted_only_when_earned(tmp_path):
    _write_answers(tmp_path)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-28T00:00:00Z",
                                 source=_FakeSource())
    rows = yaml.safe_load(
        (tmp_path / genesis.PROPOSALS_REL).read_text())["outcomes"]
    cited = [r for r in rows if r.get("recall_refs")]
    assert cited, "no row records the notes it was composed from"
    assert all("recall_refs" not in r for r in rows if r["derived_from"] == "system")


def test_briefing_card_shows_the_refs_the_operator_can_open(tmp_path):
    _write_answers(tmp_path)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-28T00:00:00Z",
                                 source=_FakeSource())
    items = genesis.genesis_intake_items(tmp_path, now="2026-07-28T00:00:00Z",
                                         source=_FakeSource())
    for it in items:
        intake.validate_item(it)
    cards = [i["payload"]["summary"] for i in items if i["kind"] == "outcome-proposal"]
    assert any("FROM YOUR NOTES: incidents/2026-07-21-latency.md#Impact" in c
               for c in cards)


def test_recall_provenance_item_states_live_unbound_and_unconsulted(tmp_path):
    """The surface that makes the false positive visible. Its NEGATIVE arms are
    the load-bearing ones: a briefing silent about recall is indistinguishable
    from one whose recall was answering out of the framework's own docs."""
    _write_answers(tmp_path)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-28T00:00:00Z",
                                 source=_FakeSource())

    def _item(**kw):
        items = genesis.genesis_intake_items(tmp_path, now="2026-07-28T00:00:00Z", **kw)
        return next(i for i in items if i["kind"] == "genesis-recall")

    live = _item(source=_FakeSource())
    assert "Recall: live" in live["payload"]["summary"]
    assert "incidents/2026-07-21-latency.md#Impact" in live["payload"]["summary"]

    class _Unbound(_FakeSource):
        def available(self):
            return False

        def binding_status(self):
            return {"declared": False, "root": None, "exists": False, "notes": 0}

    unbound = _item(source=_Unbound())
    body = unbound["payload"]["summary"]
    assert "bound to NOTHING" in body and "sources.notes_root" in body
    assert "vault/" in unbound["context"]["why"]        # names what went wrong


def test_recall_item_absent_on_a_bare_root(tmp_path):
    """Honest empty holds: no answers, no deployment, no recall claim."""
    assert genesis.genesis_intake_items(tmp_path) == []


def test_a_live_but_empty_recall_is_not_reported_as_a_stale_ordering(tmp_path):
    """FOUND BY A REAL CLEAN-ROOM HATCH, 2026-07-28, not by this suite.

    An org box whose backend held nothing about the declared lane rendered
    "recall answered, but NO card above derives from it: the proposals on file
    were written before this run" — blaming an ORDERING problem for an EMPTY
    one, and telling the operator to re-run genesis for a result that cannot
    change. Nothing was cited because there was nothing to cite. Three live
    sub-states, three sentences; conflating the last two is the same
    unearned-claim defect the estate item was already corrected for."""
    _write_answers(tmp_path)
    empty = _FakeSource(corpus=[])
    genesis.run_genesis_proposal(tmp_path, now="2026-07-28T00:00:00Z",
                                 source=empty)
    item = next(i for i in genesis.genesis_intake_items(
        tmp_path, now="2026-07-28T00:00:00Z", source=empty)
        if i["kind"] == "genesis-recall")
    why = item["context"]["why"]
    assert "held NOTHING" in why
    assert "written before this run" not in why, (
        "an EMPTY recall answer was reported as a STALE one — the operator is "
        "sent to re-run genesis for a result that cannot change")

    # …and the stale-ordering sentence must still fire when it IS the truth:
    # recall answers, but the proposals on file predate this run.
    (tmp_path / genesis.PROPOSALS_REL).unlink()
    genesis.run_genesis_proposal(tmp_path, now="2026-07-28T00:00:00Z",
                                 source=_FakeSource(corpus=[]))
    stale = next(i for i in genesis.genesis_intake_items(
        tmp_path, now="2026-07-28T00:00:00Z", source=_FakeSource())
        if i["kind"] == "genesis-recall")
    assert "written before this run" in stale["context"]["why"]


def test_shared_wording_is_checkable_in_the_files_the_card_prints():
    """FOUND BY A HOSTILE PASS ON THE LANDED UNIT, 2026-07-28, and reproduced
    through the real adapter and the real ``first-briefing.sh --local`` chain.

    ``_join_terms`` was fed all ``_MAX_RECALL_HITS`` (8) hits while the card
    prints at most ``_MAX_RECALL_FILES`` (3) of them, so any corpus answering
    from four or more files could caption three cited notes with a term that
    appears in NONE of them. Measured: notes about widget alignment, invoice
    numbering and onboarding copy, captioned "Shared wording: kubernetes" — a
    word living only in two older notes the card never showed. The operator
    finds that out by doing exactly what the card told them to do.

    THE ARM IS THE PROPERTY, NOT THE STRING: every shared term must occur in at
    least ``_MIN_JOIN_FILES`` of the files the card actually cites."""
    def _hit(path, heading, body, ts):
        return {"source": "local", "ref": f"{path}#{heading}", "path": path,
                "heading": heading, "text": f"{heading}\n{body}",
                "base_score": 0.5, "who": "", "ts": ts, "content_ts": ts}

    corpus = [
        _hit("a-newest.md", "Alpha", "Alpha storefront covers widget alignment only.",
             "2026-07-21T00:00:00Z"),
        _hit("b-newer.md", "Beta", "Beta storefront covers invoice numbering only.",
             "2026-07-20T00:00:00Z"),
        _hit("c-new.md", "Gamma", "Gamma storefront covers onboarding copy only.",
             "2026-07-19T00:00:00Z"),
        _hit("d-old.md", "Delta", "Delta storefront is entirely kubernetes autoscaling.",
             "2026-01-02T00:00:00Z"),
        _hit("e-old.md", "Eps", "Eps storefront is entirely kubernetes ingress.",
             "2026-01-01T00:00:00Z"),
    ]
    recall = _recall_for(source=_FakeSource(corpus=corpus))
    subject = recall["subjects"][0]
    cited_blobs = [h["heading"] + " " + h["text"] for h in corpus
                   if h["path"] in subject["files"]]
    assert len(subject["files"]) == genesis._MAX_RECALL_FILES
    for term in subject["shared_terms"]:
        carriers = sum(1 for blob in cited_blobs if term in blob.lower())
        assert carriers >= genesis._MIN_JOIN_FILES, (
            f"the card captions its citations 'Shared wording: {term}' but "
            f"{term!r} appears in {carriers} of the files it prints — the "
            "operator cannot check it by opening them")
    # …and the same term set still reaches the card body, unchanged in shape.
    card = genesis.propose_outcome_cards(ANSWERS, recall=recall)[0]
    assert "kubernetes" not in card["what"]


def test_a_join_the_cited_files_really_share_is_still_named():
    """The narrowing must not silence the honest case: terms two of the CITED
    files share are still reported (guards against 'fix' by deletion)."""
    recall = _recall_for(source=_FakeSource())
    assert "migration" in (recall["subjects"][0]["shared_terms"] or [])


def test_shared_wording_is_never_the_chunk_heading_the_citation_prints():
    """MEASURED 2026-07-28 through the real ``first-briefing.sh --local`` chain
    against a real Obsidian vault, on the Captain's own estate.

    ``_join_terms`` built its term blob as ``heading + " " + text`` while
    adapters chunk as ``heading + "\\n" + body`` — so the heading was counted
    TWICE and, being shared by every note that carries it, outranked real
    words. Three daily notes cited as ``1-Daily/<date>.md#Summary`` rendered:

        Shared wording: verification, network, summary, active

    ``summary`` is the markdown heading the citation already prints beside the
    term, present in the BODY of none of the three. The card tells the operator
    that a boundary label the cabinet itself chose is their own recurring
    wording — the same machinery-as-material defect ``_strip_frontmatter``
    removed one layer down, and ``_quote_of`` already strips for the quote.

    THE ARM IS THE PROPERTY: a term captioned as shared must occur in at least
    ``_MIN_JOIN_FILES`` of the cited files' BODIES, not their headings."""
    def _hit(path, heading, body, ts):
        return {"source": "local", "ref": f"{path}#{heading}", "path": path,
                "heading": heading, "text": f"{heading}\n{body}",
                "base_score": 0.5, "who": "", "ts": ts, "content_ts": ts}

    corpus = [
        _hit("1-Daily/2026-07-02.md", "Summary",
             "Storefront verification ran against the payment network.",
             "2026-07-02T00:00:00Z"),
        _hit("1-Daily/2026-06-03.md", "Summary",
             "Storefront verification queue drained; network latency fine.",
             "2026-06-03T00:00:00Z"),
        _hit("1-Daily/2026-05-30.md", "Summary",
             "Storefront verification backlog and the network cutover.",
             "2026-05-30T00:00:00Z"),
    ]
    recall = _recall_for(source=_FakeSource(corpus=corpus))
    subject = recall["subjects"][0]
    bodies = {h["path"]: h["text"].split("\n", 1)[1].lower() for h in corpus}
    assert len(subject["files"]) == genesis._MAX_RECALL_FILES
    assert subject["shared_terms"], "the honest join must survive the fix"
    assert "summary" not in subject["shared_terms"], (
        "the card captions the operator's notes 'Shared wording: summary' — "
        "that is the chunk heading the citation already names, not their words")
    for term in subject["shared_terms"]:
        carriers = sum(1 for body in bodies.values() if term in body)
        assert carriers >= genesis._MIN_JOIN_FILES, (
            f"{term!r} is captioned as shared wording but appears in "
            f"{carriers} of the cited files' BODIES")


def test_the_quote_and_the_join_read_the_same_body():
    """One helper, so the two operator-facing uses of a hit's words cannot
    drift into disagreeing about what the operator actually wrote."""
    hit = {"path": "n.md", "ref": "n.md#Summary", "heading": "Summary",
           "text": "Summary\nThe cutover moved billing to the new network.",
           "content_ts": "2026-07-02T00:00:00Z", "base_score": 0.5}
    body = genesis._body_of(hit)
    assert not body.strip().lower().startswith("summary")
    assert "cutover moved billing" in body
    assert not genesis._quote_of(hit).lower().startswith("summary")


def test_an_estate_card_recall_enriched_still_counts_as_estate_provenance(tmp_path):
    """FOUND BY A HOSTILE PASS ON THE LANDED UNIT, 2026-07-28.

    ``_estate_subject_cards`` relabelled its card ``derived_from: recall``
    whenever recall answered for that entity. The estate provenance item counts
    ``derived_from == "estate"``, so the count fell to zero and the briefing
    told the operator "No card above derives from it: the proposals on file
    were written before this estate existed. Re-run genesis" — about a card
    composed FROM that estate in that same run. An ordering story told about a
    card with no ordering problem: the same unearned-claim defect the recall
    item was corrected for, one surface over. Recall provenance for such a card
    rides ``recall_refs``, which is what the recall item counts, so both
    sentences can be true at once.

    ONE ENTITY, NOT ``ESTATE_DOC``'s TWO (corrected by the review pass on this
    fix, 2026-07-28). ``ESTATE_DOC`` carries ``storefront`` AND ``labs``, and
    the fake corpus answers only for ``storefront`` — so ``labs`` kept
    ``derived_from: estate`` even against the pre-fix bytes, the estate count
    never reached zero, and the two operator-facing assertions below PASSED on
    the defect they name. Measured: with the label assertions removed and the
    pre-fix ``"recall" if subject else "estate"`` restored, this body was green.
    The arm was pinning the label and nothing else, while its docstring claimed
    the briefing sentence. A single answered entity is the shape that actually
    drives the count to zero, so the "Re-run genesis" assertion is now the
    sensor it says it is.

    THE TWO LABEL ASSERTIONS ARE BACK (2026-07-28, second pass). That
    measurement — "with the label assertions removed … the body was green" —
    was run by editing them out, and the edit LANDED: the arm reached master
    reading ``assert entity_rows  # label asserts NEUTERED``, so the row's
    ``derived_from`` and its ``recall_refs`` were unpinned by the very commit
    that proved the sentence. Measurement scaffolding is not a fix. Both
    assertions hold on this fixture and are restored beside the sentence
    arms; each covers what the other cannot (the label alone passed on the
    defect, and the sentence alone leaves the row shape unpinned)."""
    from framework.onboarding import estate as estate_mod
    _write_answers(tmp_path, LANELESS)
    estate_mod.write_estate(
        {**ESTATE_DOC,
         "entities": [e for e in ESTATE_DOC["entities"]
                      if e["id"] == "storefront"]}, tmp_path)
    live = _FakeSource(corpus=[dict(h, ref=h["ref"], text=h["text"] + " storefront")
                               for h in _CORPUS])
    genesis.run_genesis_proposal(tmp_path, now="2026-07-28T00:00:00Z", source=live)

    rows = yaml.safe_load(
        (tmp_path / genesis.PROPOSALS_REL).read_text())["outcomes"]
    entity_rows = [r for r in rows if r["id"] == "proposed-storefront-first-proof"]
    assert entity_rows and entity_rows[0]["derived_from"] == "estate"
    assert entity_rows[0]["recall_refs"], (
        "the recall citations must still be recorded on the row")

    items = genesis.genesis_intake_items(tmp_path, now="2026-07-28T00:00:00Z",
                                         source=live)
    estate_why = next(i for i in items
                      if i["kind"] == "genesis-estate")["context"]["why"]
    assert "No card above derives from it" not in estate_why, (
        "a card written FROM this estate, in this run, was reported as "
        "predating it — and the operator sent to re-run genesis for nothing")
    assert "with citations" in estate_why
    recall_why = next(i for i in items
                      if i["kind"] == "genesis-recall")["context"]["why"]
    assert "composed from it" in recall_why, (
        "the recall item must still see its own contribution to that card")


# ---------------------------------------------------------------------------
# 2026-07-29 — four claims the card was making that its own citations do not
# support. Each was reproduced through the real `first-briefing.sh --local`
# chain on a 138-note folder before it was written, and each arm here fails
# against the pre-change bytes.
# ---------------------------------------------------------------------------

_TABLE_CORPUS = [
    {"source": "local", "ref": "notes/locked-set.md#Ceremony set",
     "path": "notes/locked-set.md", "heading": "Ceremony set",
     "text": "Ceremony set\n"
             "These are inside the storefront locked set and require the unlock ceremony\n"
             "to update on an\n"
             "armed Mac:\n"
             "\n"
             "| Path | Locked via | Change |\n"
             "|---|---|---|\n"
             "| `a/recorder.py` | `a` dir | typed error, external mutex |\n",
     "base_score": 0.6, "who": "", "ts": "2026-07-16T00:00:00Z",
     "content_ts": "2026-07-16T00:00:00Z"},
    {"source": "local", "ref": "notes/tables-only.md#Set",
     "path": "notes/tables-only.md", "heading": "Set",
     "text": "Set\n| Path | storefront Locked via |\n|---|---|\n| `b/x.py` | `b` dir |\n",
     "base_score": 0.5, "who": "", "ts": "2026-07-15T00:00:00Z",
     "content_ts": "2026-07-15T00:00:00Z"},
]


def test_the_quote_is_prose_never_a_markdown_table():
    """The WHY line's whole job is to be the operator's own checkable sentence:
    "I did not ask you for this, I read it: …". Measured on a real hatch, it
    quoted a markdown TABLE back at them —
    "| Path | Locked via | Change | |---|---|---| | `framework/evidence/…" —
    the cabinet's rendering machinery presented as their material, which is the
    same class as the frontmatter and heading strips one layer down."""
    recall = _recall_for(source=_FakeSource(corpus=_TABLE_CORPUS))
    quote = recall["subjects"][0]["quote"]
    assert quote, "a chunk holding real prose must still yield a quote"
    assert "|" not in quote, f"the quote is markup, not a sentence: {quote!r}"
    assert quote.startswith("These are inside the storefront locked set"), quote


def test_a_wrapped_sentence_is_not_severed_mid_clause():
    """The short-line floor exists to reject standalone fragments; applied to
    every line it also cuts a hard-wrapped paragraph, and the card then quotes
    the operator mid-sentence with no ellipsis."""
    recall = _recall_for(source=_FakeSource(corpus=_TABLE_CORPUS))
    assert recall["subjects"][0]["quote"].endswith("armed Mac:"), (
        "a wrapped sentence lost its continuation line: "
        f"{recall['subjects'][0]['quote']!r}"
    )


def test_the_quote_citation_names_the_file_the_words_came_from():
    """The quote may now walk past a cited hit that holds no prose. Its
    citation has to walk with it, or the card attributes one file's words to
    another — a citation that does not support what it is printed beside."""
    corpus = [_TABLE_CORPUS[1], _TABLE_CORPUS[0]]   # table-only file is NEWER? no: order by ts
    corpus[0] = dict(_TABLE_CORPUS[1], ts="2026-07-20T00:00:00Z",
                     content_ts="2026-07-20T00:00:00Z")
    recall = _recall_for(source=_FakeSource(corpus=corpus))
    subject = recall["subjects"][0]
    assert subject["quote"].startswith("These are inside the storefront locked set")
    assert "notes/locked-set.md" in subject["quote_cite"], (
        "the citation names a file the quoted words are not in: "
        f"{subject['quote_cite']!r}"
    )
    assert "notes/tables-only.md" in subject["top_cite"], (
        "the newest cited file should still head the citation list"
    )

    # AND THE RENDERED WHY LINE, not only the dict it is composed from
    # (2026-07-29, review). `quote_cite` alone leaves `_recall_why` free to
    # print `top_cite` again: reverting that one line puts the quoted words
    # under a file that does not contain them, and every arm in this suite
    # stayed green while the real `first-briefing.sh --local` chain rendered
    # the false attribution. The sensor has to sit on the line the operator
    # reads.
    card = next(c for c in genesis.propose_outcome_cards(ANSWERS, recall=recall)
                if "of your own notes" in c.get("name", ""))
    assert subject["quote"][:40] in card["why"], card["why"]
    assert subject["quote_cite"] in card["why"], card["why"]
    assert subject["top_cite"] not in card["why"], (
        "the WHY line credits the newest hit, not the file the quoted words "
        "are in: " + card["why"]
    )


def test_no_card_claims_the_operator_never_read_their_own_notes():
    """"never read together" was the headline of every join card. It is an
    assertion about the operator's own reading history and nothing the cabinet
    can read shows it — offered as a finding, on the first line they see."""
    cards = genesis.propose_outcome_cards(ANSWERS, recall=_recall_for(source=_FakeSource()))
    blob = " ".join(f"{c.get('name','')} {c.get('what','')} {c.get('why','')}"
                    for c in cards)
    assert "never read together" not in blob, blob
    assert "read together" not in blob, blob


def test_the_headline_dates_only_the_notes_that_carry_a_date():
    """Three cited files with one derivable content_ts rendered "3 of your own
    notes (2026-07-21)" while two of the three citation lines below it said
    "(undated)" — the headline dating notes the card itself refuses to date."""
    corpus = [dict(_CORPUS[0]),
              dict(_CORPUS[1], ts=None, content_ts=None),
              dict(_CORPUS[2], ts=None, content_ts=None)]
    cards = genesis.propose_outcome_cards(
        ANSWERS, recall=_recall_for(source=_FakeSource(corpus=corpus)))
    join = [c for c in cards if "of your own notes" in c.get("name", "")]
    assert join, [c.get("name") for c in cards]
    name = join[0]["name"]
    assert "1 of them dated 2026-07-21" in name, name
    assert "(2026-07-21)" not in name, (
        "the headline dates all three notes while two are undated: " + name
    )


# ---------------------------------------------------------------------------
# 2026-07-30 — DERIVATIONS FOLLOW THE OPERATOR'S CURRENT ANSWERS.
#
# Both defects below were measured on a live agnostic-proof hatch, through the
# answers file's OWN sanctioned refinement path: `--defaults` hatch, edit
# instance/config/cabinet-init.answers.yml, re-run generate-instance.py, re-run
# `first-briefing.sh --local`.
#
#   M7  Neither derived artifact could notice its INPUT had moved. The
#       proposals file is write-once (the Captain may have edited the drafts)
#       and a delivered brief is idempotent (a re-run must not burn a CLI
#       call), so after the operator replaced the placeholder lane with her
#       real one the briefing still said "You staked First Lane as a lane at
#       genesis" over a Library baseline researching the placeholder label.
#   M8  The proof language was software-shaped whatever the org was. A lane at
#       COMPANY altitude declaring `task_system: none` and `repos: []` was
#       handed "traced end-to-end: task → change → verified deploy/close" and
#       "A closed task in the lane's task system linked to the shipped change"
#       — named by the framework, contradicted by the card's own inputs.
# ---------------------------------------------------------------------------
DEFAULTS_ANSWERS = {
    "version": 1,
    "captain": {"name": "Ada", "timezone": "UTC", "telegram_chat_id": "12345678"},
    "cabinet": {"id": "main", "mode": "single", "org_shape": "portfolio"},
    # The `--defaults` lane, verbatim in shape: a placeholder name, no
    # repository and no task system (generate-instance.render_default_answers).
    "lanes": [{"name": "First Lane", "slug": "first-lane", "repos": [],
               "task_system": "none", "boards": []}],
    "autonomy": {"posture": "propose_first", "flavor": "org"},
}
REFINED_ANSWERS = {
    **DEFAULTS_ANSWERS,
    "lanes": [{"name": "The Kitchen", "slug": "kitchen", "repos": [],
               "task_system": "none", "boards": []}],
    "mission": {"purpose": "Guests leave rested and fed.",
                "altitude": "company"},
}


def _rows(root):
    return yaml.safe_load((root / genesis.PROPOSALS_REL).read_text())["outcomes"]


def _doc(root):
    return yaml.safe_load((root / genesis.PROPOSALS_REL).read_text())


def _hatch_then_refine(root, refined=None):
    """The measured path: hatch on the defaults, then refine the answers."""
    _write_answers(root, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(root, now="2026-07-30T00:00:00Z")
    _write_answers(root, refined if refined is not None else REFINED_ANSWERS)
    return genesis.run_genesis_proposal(root, now="2026-07-30T01:00:00Z")


# --- M7: the proposals file ------------------------------------------------
def test_refined_answers_rederive_the_cards_from_the_current_lane(tmp_path):
    """THE MEASURED DEFECT. The stale card must GO, not merely be joined by a
    fresh one: a briefing that carries both tells the operator about a lane she
    deleted, beside the one she wrote."""
    out = _hatch_then_refine(tmp_path)
    assert out["status"] == "rederived", out
    ids = [r["id"] for r in _rows(tmp_path)]
    assert "proposed-kitchen-first-proof" in ids, ids
    assert "proposed-first-lane-first-proof" not in ids, ids
    blob = " ".join(f"{r['name']} {r['why']}" for r in _rows(tmp_path))
    assert "First Lane" not in blob, blob
    assert "You staked The Kitchen as a lane at genesis" in blob, blob
    assert "Guests leave rested and fed." in blob, blob


def test_unchanged_answers_rederive_nothing(tmp_path):
    """Idempotence is the contract this seam had to leave standing: an equal
    digest must not touch a byte, or every re-run churns the file and burns a
    CLI call for nothing."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    path = tmp_path / genesis.PROPOSALS_REL
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    out = genesis.run_genesis_proposal(tmp_path, now="2026-07-30T02:00:00Z")
    assert out["status"] == "kept-existing", out
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime, "the file was rewritten in place"
    assert "rederived_at" not in _doc(tmp_path)


def test_the_digest_is_recorded_on_the_proposals_and_on_every_row(tmp_path):
    """A seam whose sensor is not written down cannot fire on the next run."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    doc = _doc(tmp_path)
    assert doc[genesis.ANSWERS_DIGEST_KEY] == genesis.answers_digest(tmp_path)
    assert len(doc[genesis.ANSWERS_DIGEST_KEY]) == 64
    for row in doc["outcomes"]:
        assert len(str(row[genesis.ROW_DIGEST_KEY])) == 64, row["id"]
        assert row["proposed_by"] == "onboarding-genesis", row["id"]


def test_a_ratified_row_survives_rederivation_byte_identical(tmp_path):
    """A ratified row is the Captain's answer, never genesis's draft."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    doc = _doc(tmp_path)
    doc["outcomes"][0]["captain_ratified"] = True
    ratified = dict(doc["outcomes"][0])
    (tmp_path / genesis.PROPOSALS_REL).write_text(
        yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    _write_answers(tmp_path, REFINED_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T01:00:00Z")
    rows = _rows(tmp_path)
    kept = [r for r in rows if r["id"] == ratified["id"]]
    assert kept == [ratified], kept
    assert any(r["id"] == "proposed-kitchen-first-proof" for r in rows)


def test_an_operator_edited_draft_survives_rederivation(tmp_path):
    """"Operator-edited" is defined as "no longer what the recorded derivation
    produced" — a comparison, not a marker anybody has to remember to set."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    doc = _doc(tmp_path)
    lane_row = next(r for r in doc["outcomes"] if r["lane"] == "first-lane")
    lane_row["what"] = "Rewritten by hand: teach one new dish, start to finish."
    edited = dict(lane_row)
    (tmp_path / genesis.PROPOSALS_REL).write_text(
        yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    _write_answers(tmp_path, REFINED_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T01:00:00Z")
    rows = _rows(tmp_path)
    assert [r for r in rows if r["id"] == edited["id"]] == [edited]
    assert any(r["id"] == "proposed-kitchen-first-proof" for r in rows)


def test_a_row_with_no_recorded_digest_is_never_rewritten(tmp_path):
    """Unknown provenance is not permission to rewrite — the back-compat end,
    and the same rule that protects a row another organ merged in."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    doc = _doc(tmp_path)
    for row in doc["outcomes"]:
        row.pop(genesis.ROW_DIGEST_KEY, None)
    before = [dict(r) for r in doc["outcomes"]]
    (tmp_path / genesis.PROPOSALS_REL).write_text(
        yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    _write_answers(tmp_path, REFINED_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T01:00:00Z")
    rows = _rows(tmp_path)
    assert rows[:len(before)] == before, "an undigested row was rewritten"


def test_a_file_predating_the_seam_keeps_the_write_once_behaviour(tmp_path):
    """No recorded document digest ⇒ staleness is UNKNOWN, and unknown is not
    stale: the file is left exactly as write-once always left it."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    doc = _doc(tmp_path)
    doc.pop(genesis.ANSWERS_DIGEST_KEY)
    (tmp_path / genesis.PROPOSALS_REL).write_text(
        yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    path = tmp_path / genesis.PROPOSALS_REL
    before = path.read_bytes()

    _write_answers(tmp_path, REFINED_ANSWERS)
    out = genesis.run_genesis_proposal(tmp_path, now="2026-07-30T01:00:00Z")
    assert out["status"] == "kept-existing", out
    assert path.read_bytes() == before


def test_an_unparseable_answers_file_never_wipes_the_drafts(tmp_path):
    """Degenerate end. The bytes still hash — so the digest MOVES — but there
    are no answers to derive from, and a re-derivation from nothing would
    replace real drafts with an empty file."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    path = tmp_path / genesis.PROPOSALS_REL
    before = path.read_bytes()
    (tmp_path / genesis.ANSWERS_REL).write_text("lanes: [unclosed\n",
                                                encoding="utf-8")
    out = genesis.run_genesis_proposal(tmp_path, now="2026-07-30T01:00:00Z")
    assert out["status"] == "no-answers", out
    assert path.read_bytes() == before


def test_an_absent_answers_file_yields_no_digest_and_no_rewrite(tmp_path):
    """Degenerate end. "" is an honest cannot-tell and never reads as
    staleness — the check that stops an empty root from clearing a real file."""
    assert genesis.answers_digest(tmp_path) == ""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    path = tmp_path / genesis.PROPOSALS_REL
    before = path.read_bytes()
    (tmp_path / genesis.ANSWERS_REL).unlink()
    assert genesis.write_proposals(
        [], tmp_path)["status"] == "kept-existing"
    assert path.read_bytes() == before


def test_refining_the_lanes_away_leaves_no_lane_card_behind(tmp_path):
    """Degenerate end: an EMPTY lanes list. The re-derivation drops the stale
    lane card and proposes the leftover-question card in its place — the
    2-4 band holds and nothing about the deleted lane survives."""
    out = _hatch_then_refine(tmp_path, {**DEFAULTS_ANSWERS, "lanes": []})
    assert out["status"] == "rederived", out
    rows = _rows(tmp_path)
    assert [r["id"] for r in rows] == ["proposed-read-your-world",
                                       "proposed-library-grounding",
                                       "proposed-captain-loop"]
    assert "First Lane" not in yaml.safe_dump(rows)


# --- M7: the research brief ------------------------------------------------
def _delivered(root, body="A brief about the FIRST LANE.", now=None,
               claude_path="/nonexistent/claude-stub"):
    return genesis.research_brief(
        root, run_fn=lambda a, *, timeout, cwd, env=None: _Proc(0, body),
        net_check_fn=lambda: True, claude_path=claude_path, now=now)


def test_refined_answers_supersede_the_delivered_brief(tmp_path):
    """The Library baseline researched the placeholder label and stayed the
    org's baseline after the operator replaced it. Superseded, never
    overwritten: the old brief is MOVED to the dated _pre-adopt archive and the
    replacement names it."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    first = _delivered(tmp_path, now="2026-07-30T00:00:00Z")
    assert first["status"] == "delivered"
    assert genesis.answers_digest(tmp_path) in (tmp_path / genesis.BRIEF_REL).read_text()

    _write_answers(tmp_path, REFINED_ANSWERS)
    again = _delivered(tmp_path, body="A brief about THE KITCHEN.",
                       now="2026-07-30T01:00:00Z")
    assert again["status"] == "delivered", again
    archived = tmp_path / again["superseded"]
    assert archived.is_file(), again
    assert "_pre-adopt-" in again["superseded"], again["superseded"]
    assert "FIRST LANE" in archived.read_text()          # nothing deleted
    live = (tmp_path / genesis.BRIEF_REL).read_text()
    assert "THE KITCHEN" in live
    assert f"supersedes: {again['superseded']}" in live
    assert genesis.answers_digest(tmp_path) in live


def test_an_unchanged_answers_file_never_re_runs_the_brief(tmp_path):
    """The cost bound. A second run on unchanged answers must not touch the
    file and must not reach the CLI at all."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    _delivered(tmp_path, now="2026-07-30T00:00:00Z")
    path = tmp_path / genesis.BRIEF_REL
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns

    def must_not_run(*a, **kw):  # pragma: no cover — the assertion IS the test
        raise AssertionError("the CLI was invoked for unchanged answers")

    out = genesis.research_brief(tmp_path, run_fn=must_not_run,
                                 net_check_fn=lambda: True,
                                 claude_path="/nonexistent/claude-stub",
                                 now="2026-07-30T02:00:00Z")
    assert out["status"] == "already-delivered", out
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == mtime


def test_a_delivered_brief_with_no_recorded_digest_is_left_intact(tmp_path):
    """Degenerate end. Unknown provenance is not permission to archive
    somebody's Library baseline."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    _delivered(tmp_path, now="2026-07-30T00:00:00Z")
    path = tmp_path / genesis.BRIEF_REL
    path.write_text("\n".join(
        ln for ln in path.read_text().splitlines()
        if not ln.startswith(genesis.ANSWERS_DIGEST_KEY + ":")), encoding="utf-8")
    before = path.read_bytes()
    _write_answers(tmp_path, REFINED_ANSWERS)
    out = _delivered(tmp_path, body="never written", now="2026-07-30T01:00:00Z")
    assert out["status"] == "already-delivered", out
    assert path.read_bytes() == before


def test_an_absent_brief_writes_normally_even_with_a_digest_on_file(tmp_path):
    """Degenerate end: the proposals file records a digest but the brief was
    deleted. Nothing to supersede — the ordinary write path runs."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    assert not (tmp_path / genesis.BRIEF_REL).exists()
    out = _delivered(tmp_path, now="2026-07-30T01:00:00Z")
    assert out["status"] == "delivered" and "superseded" not in out, out


def test_a_superseded_brief_falls_back_to_the_honest_iou(tmp_path):
    """The re-run rides the SAME path, honest IOU included: no CLI means the
    IOU note, with the archive still named. Never fake content, and never a
    brief about a deployment that no longer exists."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    _delivered(tmp_path, now="2026-07-30T00:00:00Z")
    _write_answers(tmp_path, REFINED_ANSWERS)
    out = genesis.research_brief(tmp_path, run_fn=lambda *a, **k: _Proc(1),
                                 net_check_fn=lambda: True, claude_path=None,
                                 now="2026-07-30T01:00:00Z")
    assert out["status"] == "iou", out
    assert (tmp_path / out["superseded"]).is_file()
    live = (tmp_path / genesis.BRIEF_REL).read_text()
    assert genesis.IOU_LINE in live
    assert "FIRST LANE" not in live


# --- M8: the proof language derives from what the org declared -------------
_SOFTWARE_SHAPED = ("task", "deploy", "shipped", "repo")


def _lane_card(answers, **kw):
    cards = genesis.propose_outcome_cards(answers, **kw)
    return next(c for c in cards if c.get("lane"))


def test_a_lane_with_no_task_system_and_no_repos_gets_neutral_proof():
    """MEASURED: an inn at COMPANY altitude, `task_system: none`, `repos: []`,
    told its proof was "A closed task in the lane's task system linked to the
    shipped change" and its WHAT "task → change → verified deploy/close". The
    card's own inputs SAY there is neither."""
    card = _lane_card(REFINED_ANSWERS)
    text = f"{card['name']} {card['what']} {card['proof_expected']}".lower()
    for token in _SOFTWARE_SHAPED:
        assert token not in text, f"{token!r} survives in: {text}"
    # It still asks for something observable and verifiable, in the framework's
    # own completion vocabulary — a neutral card is not a vague one.
    assert "receipt" in card["proof_expected"]
    assert "org journal" in card["proof_expected"]
    assert "how you checked it held" in card["proof_expected"]


def test_a_declared_task_system_keeps_todays_wording_byte_identical():
    """The regression pin. Conditioning on the card's inputs must not touch a
    deployment that declared a task system and a repository."""
    card = _lane_card(ANSWERS)
    assert card["proof_expected"] == (
        "A closed task in the lane's task system linked to the shipped change "
        "in acme/storefront, plus the action's receipt (what/why/undo) in the "
        "org journal.")
    assert card["what"] == (
        "One reviewed, Captain-approved improvement in Acme Storefront traced "
        "end-to-end: task → change → verified deploy/close.")
    assert card["name"] == (
        "First verifiable improvement shipped in the Acme Storefront lane")


@pytest.mark.parametrize("lane,software", [
    ({"name": "L", "slug": "l", "repos": [], "task_system": "none"}, False),
    ({"name": "L", "slug": "l", "repos": []}, False),               # absent key
    ({"name": "L", "slug": "l", "repos": [], "task_system": "None"}, False),
    ({"name": "L", "slug": "l", "repos": ["a/b"], "task_system": "none"}, True),
    ({"name": "L", "slug": "l", "repos": [], "task_system": "linear"}, True),
])
def test_each_declared_surface_maps_to_exactly_one_proof_shape(lane, software):
    """Absent is read as `none` — the generator's own normalisation — so a key
    nobody filled in and a key filled in with "none" say the same thing, and
    invisible case never flips the shape."""
    card = _lane_card({**DEFAULTS_ANSWERS, "lanes": [lane]})
    assert ("closed task" in card["proof_expected"]) is software, card


def test_the_rendered_briefing_card_carries_the_neutral_language(tmp_path):
    """Through the surface the operator actually reads — the composed intake
    item — not only the derivation that feeds it."""
    _write_answers(tmp_path, REFINED_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    items = genesis.genesis_intake_items(tmp_path, now="2026-07-30T00:00:00Z")
    lane_item = next(i["payload"]["summary"] for i in items
                     if "The Kitchen" in i["payload"]["summary"])
    for token in _SOFTWARE_SHAPED:
        assert token not in lane_item.lower(), f"{token!r} in: {lane_item}"
    assert "PROOF-expected: The action's receipt" in lane_item


def test_an_unreadable_proposals_file_is_refused_not_rewritten(tmp_path):
    """Degenerate end, found by attacking the rewrite: the re-derivation
    ITERATES `outcomes`, so a doc carrying a live digest and a mangled
    `outcomes` would be written back as its own keys — a clobber dressed as a
    re-derivation. Same honest refusal merge_proposals already makes."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    doc = _doc(tmp_path)
    doc["outcomes"] = {"not": "a list"}
    path = tmp_path / genesis.PROPOSALS_REL
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    before = path.read_bytes()

    _write_answers(tmp_path, REFINED_ANSWERS)
    out = genesis.run_genesis_proposal(tmp_path, now="2026-07-30T01:00:00Z")
    assert out["status"] == "kept-existing", out
    assert path.read_bytes() == before

    path.write_text("outcomes: [unclosed\n", encoding="utf-8")
    assert genesis.run_genesis_proposal(
        tmp_path, now="2026-07-30T02:00:00Z")["status"] == "kept-existing"
    assert path.read_text() == "outcomes: [unclosed\n"


def test_the_row_digest_round_trips_through_a_non_latin_lane(tmp_path):
    """The pristine test is a comparison across a YAML round-trip, so it is
    only as good as that round-trip. A lane written in the operator's own
    script (allow_unicode on the way out, ensure_ascii=False in the digest) has
    to still read as untouched, or every non-Latin deployment would have its
    own genesis drafts treated as hand-edited and never re-derived."""
    jp = {**DEFAULTS_ANSWERS,
          "lanes": [{"name": "焼き菓子の棚", "slug": "tana", "repos": [],
                     "task_system": "none"}]}
    _write_answers(tmp_path, jp)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    row = next(r for r in _rows(tmp_path) if r["lane"] == "tana")
    assert "焼き菓子の棚" in row["name"]
    assert genesis._regeneration_safe(row), row

    _write_answers(tmp_path, REFINED_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T01:00:00Z")
    assert "tana" not in [r["lane"] for r in _rows(tmp_path)]


def test_an_estate_card_gets_the_neutral_proof_too(tmp_path):
    """The helper is shared, so the fix has to be judged on every card that
    calls it. An entity the cabinet READ declares no task system and no
    repository — the software-shaped proof was unearned there before this
    change too, and leaving it would be a partial fix relabelled as covered."""
    from framework.onboarding import estate as estate_mod
    _write_answers(tmp_path, {**DEFAULTS_ANSWERS, "lanes": []})
    estate_mod.write_estate(ESTATE_DOC, tmp_path)
    card = next(c for c in genesis.propose_outcome_cards(
        {**DEFAULTS_ANSWERS, "lanes": []},
        estate=estate_mod.load_estate(tmp_path)) if c.get("lane"))
    assert card["derived_from"] == "estate", card
    for token in _SOFTWARE_SHAPED:
        assert token not in card["proof_expected"].lower(), card["proof_expected"]
    assert "org journal" in card["proof_expected"]


def test_an_empty_card_list_never_deletes_the_drafts(tmp_path):
    """Degenerate end, found by attacking the writer rather than the caller:
    the re-derivation KEEPS what it cannot rewrite and REPLACES the rest, so an
    empty card list would drop every pristine draft and add nothing back — a
    wipe wearing a re-derivation's name. run_genesis_proposal returns
    `no-cards` before it gets here; the guard is on the writer because a caller
    that does not know the rule cannot break it."""
    _write_answers(tmp_path, DEFAULTS_ANSWERS)
    genesis.run_genesis_proposal(tmp_path, now="2026-07-30T00:00:00Z")
    path = tmp_path / genesis.PROPOSALS_REL
    before = path.read_bytes()
    _write_answers(tmp_path, REFINED_ANSWERS)
    out = genesis.write_proposals([], tmp_path, answers=REFINED_ANSWERS)
    assert out["status"] == "kept-existing", out
    assert path.read_bytes() == before
    # …and the same root with real cards still re-derives, so the guard cannot
    # pass by disabling the seam.
    assert genesis.run_genesis_proposal(
        tmp_path, now="2026-07-30T01:00:00Z")["status"] == "rederived"
