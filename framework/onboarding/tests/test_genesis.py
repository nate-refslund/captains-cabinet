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
