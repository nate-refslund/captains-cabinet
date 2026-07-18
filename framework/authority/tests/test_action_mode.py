"""Autonomy-graded action seam — full matrix + fail-closed + mutant pins.

Captain law 2026-07-17: mode is a FUNCTION of the posture level
(guardian/earn_up → propose; act_then_tell → act_tell only with a proven
undo handle; sovereign → go), Ring-0 ALWAYS Captain regardless. Everything
unknown resolves propose. These tests pin the whole
posture × ring × reversibility matrix so ANY widening mutation —
a ring-0 arm that stops proposing, a shrunk RING0_CATEGORIES enumeration,
an act_tell granted without an undo handle, a fail-open unknown — goes red.

Hermetic: postures are passed explicitly or resolved against tmp roots the
test owns; the live instance ruling is never read.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import action_mode as AM
from framework.authority.posture import (
    EARN_UP,
    GUARDIAN,
    SOVEREIGN,
    posture_path,
)

VALID = {"ring": 2, "reversibility": "reversible", "category": "test-organ"}


def _desc(**over):
    d = dict(VALID)
    d.update(over)
    return d


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # The seam itself reads no env, but the posture resolver it defers to
    # does — tests own the whole environment.
    for var in ("CABINET_POSTURE", "CABINET_ID", "CABINET_ROOT"):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# The posture → mode law (valid descriptors, non-ring-0)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ring", [1, 2])
@pytest.mark.parametrize("rev", ["reversible", "irreversible"])
@pytest.mark.parametrize("posture,expected", [
    (GUARDIAN, "propose"),
    (EARN_UP, "propose"),
    (SOVEREIGN, "go"),
])
def test_posture_mode_matrix(ring, rev, posture, expected):
    d = _desc(ring=ring, reversibility=rev)
    decision = AM.action_decision(d, posture)
    assert decision.mode == expected
    assert decision.captain_card is False


def test_act_then_tell_requires_reversible_and_registered_undo():
    # The forward-compatible rung: act_tell ONLY with reversible + handle.
    with_undo = _desc(undo_handle="organ --undo <ledger-line>")
    assert AM.action_mode(with_undo, AM.ACT_THEN_TELL) == "act_tell"
    d = AM.action_decision(with_undo, AM.ACT_THEN_TELL)
    assert d == AM.ActionDecision("act_tell", False, "act-then-tell-with-undo")

    # No handle → refuse, degrade to propose.
    assert AM.action_mode(_desc(), AM.ACT_THEN_TELL) == "propose"
    assert (AM.action_decision(_desc(), AM.ACT_THEN_TELL).reason
            == "act-tell-refused-no-undo-handle")
    # Empty / whitespace / non-string handles are NOT handles.
    for bad in ("", "   ", None, 7, ["u"]):
        assert AM.action_mode(_desc(undo_handle=bad), AM.ACT_THEN_TELL) == "propose"
    # Irreversible can never act_tell, handle or not.
    d = AM.action_decision(
        _desc(reversibility="irreversible", undo_handle="x --undo"),
        AM.ACT_THEN_TELL)
    assert d.mode == "propose"
    assert d.reason == "act-tell-refused-irreversible"


def test_undo_handle_never_widens_other_postures():
    with_undo = _desc(undo_handle="organ --undo <ledger-line>")
    assert AM.action_mode(with_undo, GUARDIAN) == "propose"
    assert AM.action_mode(with_undo, EARN_UP) == "propose"
    assert AM.action_mode(with_undo, SOVEREIGN) == "go"


def test_ladder_does_not_define_act_then_tell_today():
    # Guard the docstring's claim: the ladder must not silently grow the
    # rung without this seam (and its eval) being revisited deliberately.
    from framework.authority.posture import POSTURES
    assert AM.ACT_THEN_TELL not in POSTURES


# ---------------------------------------------------------------------------
# RING-0 override — always propose + captain card, whatever the posture
# ---------------------------------------------------------------------------

ALL_POSTURES = [GUARDIAN, EARN_UP, SOVEREIGN, AM.ACT_THEN_TELL]


@pytest.mark.parametrize("posture", ALL_POSTURES)
@pytest.mark.parametrize("rev", ["reversible", "irreversible"])
def test_ring0_always_captain_carded_propose(posture, rev):
    d = _desc(ring=0, reversibility=rev, undo_handle="organ --undo x")
    decision = AM.action_decision(d, posture)
    assert decision == AM.ActionDecision("propose", True, "ring-0-captain-only")


@pytest.mark.parametrize("posture", ALL_POSTURES)
@pytest.mark.parametrize("category", sorted(AM.RING0_CATEGORIES))
def test_ring0_category_backstop_overrides_claimed_ring(posture, category):
    # Caller claims ring 2, but the category names the Captain-only plane:
    # the seam tightens the claim, never honors it.
    d = _desc(ring=2, category=category, undo_handle="organ --undo x")
    decision = AM.action_decision(d, posture)
    assert decision == AM.ActionDecision("propose", True, "ring-0-captain-only")


@pytest.mark.parametrize("variant", [
    "Claude Binary", "claude_binary", "  CLAUDE-BINARY  ",
    "Officer Model Routing", "spend_caps", "Spend  Caps", "GERMLINE",
    "constitution", "officer_model_routing",
])
def test_ring0_category_normalization_variants(variant):
    assert AM.action_mode(_desc(category=variant), SOVEREIGN) == "propose"
    assert AM.requires_captain_card(_desc(category=variant)) is True


def test_ring0_categories_enumeration_pinned_exactly():
    # Widening OR shrinking the Captain-only plane is a Captain amendment,
    # never a code default — equality, not subset.
    assert AM.RING0_CATEGORIES == frozenset({
        "constitution", "germline", "officer-model-routing",
        "claude-binary", "spend-caps",
    })


def test_mutant_ring_number_alone_forces_propose(monkeypatch):
    # Defense in depth: even with the category enumeration emptied (a
    # widening mutant), a declared ring 0 STILL proposes + cards.
    monkeypatch.setattr(AM, "RING0_CATEGORIES", frozenset())
    d = AM.action_decision(_desc(ring=0), SOVEREIGN)
    assert d == AM.ActionDecision("propose", True, "ring-0-captain-only")


def test_requires_captain_card_reads_no_posture():
    assert AM.requires_captain_card(_desc(ring=0)) is True
    assert AM.requires_captain_card(_desc(category="claude-binary")) is True
    assert AM.requires_captain_card(_desc()) is False


# ---------------------------------------------------------------------------
# Fail-closed arms — every unknown resolves propose
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("posture", ALL_POSTURES + [None])
@pytest.mark.parametrize("bad_ring", [None, "1", "0", 1.0, True, False, 3, -1, 99])
def test_unknown_ring_fails_closed(posture, bad_ring, monkeypatch, tmp_path):
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # None-posture arm stays hermetic
    d = _desc(ring=bad_ring, undo_handle="organ --undo x")
    decision = AM.action_decision(d, posture)
    assert decision.mode == "propose"
    # A bool/str "0" is NOT a ring-0 claim — but it must not card either;
    # it is unknown, and unknown is propose without ceremony.
    assert decision.captain_card is False
    assert decision.reason in ("unknown-ring",)


@pytest.mark.parametrize("bad_rev", [None, "", "maybe", "REVERSIBLE?", 1, ["reversible"]])
def test_unknown_reversibility_fails_closed(bad_rev):
    d = _desc(reversibility=bad_rev, undo_handle="organ --undo x")
    for posture in ALL_POSTURES:
        decision = AM.action_decision(d, posture)
        assert (decision.mode, decision.captain_card) == ("propose", False)
        assert decision.reason == "unknown-reversibility"


@pytest.mark.parametrize("bad_cat", [None, "", "   ", "___", 7, ["x"]])
def test_unknown_category_fails_closed(bad_cat):
    d = _desc(category=bad_cat)
    for posture in ALL_POSTURES:
        assert AM.action_decision(d, posture) == AM.ActionDecision(
            "propose", False, "unknown-category")


@pytest.mark.parametrize("bad_posture", [
    "", "Sovereign", "SOVEREIGN", "sovereign ", "root", "admin", "guardian2", 42,
])
def test_unknown_posture_fails_closed(bad_posture):
    assert AM.action_decision(_desc(), bad_posture) == AM.ActionDecision(
        "propose", False, "unknown-posture")


@pytest.mark.parametrize("bad_action", [None, 42, "ring=2", ["ring", 2], object()])
def test_invalid_descriptor_fails_closed(bad_action):
    assert AM.action_decision(bad_action, SOVEREIGN) == AM.ActionDecision(
        "propose", False, "invalid-descriptor")


def test_raising_resolver_fails_closed():
    def boom():
        raise RuntimeError("resolver down")
    decision = AM.action_decision(_desc(), resolve_fn=boom)
    assert decision == AM.ActionDecision("propose", False, "posture-resolve-failed")


def test_resolver_returning_garbage_fails_closed():
    for garbage in (None, 42, "sovereign!!", "act-now"):
        decision = AM.action_decision(_desc(), resolve_fn=lambda g=garbage: g)
        assert decision.mode == "propose"
        assert decision.reason == "unknown-posture"


def test_never_raises_on_garbage_sweep():
    postures = [None, GUARDIAN, SOVEREIGN, AM.ACT_THEN_TELL, "junk", 3]
    rings = [0, 1, 2, None, "x", True, 9]
    revs = ["reversible", "irreversible", None, "junk"]
    cats = ["ok-cat", "claude-binary", "", None]
    undos = [None, "", "organ --undo x"]
    for posture, ring, rev, cat, undo in itertools.product(
            postures, rings, revs, cats, undos):
        mode = AM.action_mode(
            {"ring": ring, "reversibility": rev, "category": cat,
             "undo_handle": undo},
            posture,
            resolve_fn=(lambda: GUARDIAN) if posture is None else None)
        assert mode in AM.MODES


# ---------------------------------------------------------------------------
# Live-resolver integration (tmp roots only) + purity
# ---------------------------------------------------------------------------

def test_none_posture_resolves_guardian_on_absent_ruling(tmp_path):
    # No posture.yml under the root → resolver says guardian → propose.
    assert AM.action_mode(_desc(), root=tmp_path) == "propose"


def test_none_posture_env_can_only_narrow(monkeypatch, tmp_path):
    monkeypatch.setenv("CABINET_POSTURE", "sovereign")  # IGNORED by resolver
    assert AM.action_mode(_desc(), root=tmp_path) == "propose"


def test_explicit_posture_wins_over_root(tmp_path):
    # Caller-resolved posture is trusted input (the caller ran the kernel).
    assert AM.action_mode(_desc(), SOVEREIGN, root=tmp_path) == "go"


def test_seam_is_pure_no_needs_filed_on_corrupt_ruling(tmp_path):
    # A corrupt ruling normally files a deduped need — the seam passes
    # file_needs=False, so resolution stays side-effect free. The ruling
    # path comes from the kernel's own resolver (layer-sep: no literal
    # instance path in framework code — the kernel owns that coupling).
    ruling = posture_path(tmp_path)
    ruling.parent.mkdir(parents=True)
    ruling.write_text("{not: [valid")  # unparseable
    before = {p for p in tmp_path.rglob("*")}
    assert AM.action_mode(_desc(), root=tmp_path) == "propose"
    after = {p for p in tmp_path.rglob("*")}
    assert before == after, "the seam must never write anything"


def test_decision_is_deterministic():
    a = AM.action_decision(_desc(), SOVEREIGN)
    b = AM.action_decision(_desc(), SOVEREIGN)
    assert a == b


# ---------------------------------------------------------------------------
# ring_for_repo_path — the cached immutable-core read
# ---------------------------------------------------------------------------

def _write_core(root: Path, text: str) -> None:
    pol = root / "framework" / "policies"
    pol.mkdir(parents=True, exist_ok=True)
    (pol / "immutable-core.yml").write_text(text)


FIXTURE_CORE = """
version: 1
lists: [germline-lock, hook-s5, hook-s5b, base-safety]
files:
  - path: a/locked-file.py
dirs:
  - path: locked/dir
runtime_appended:
  - path: logs/run/
  - path: shared/one-ledger.jsonl
hook_protected:
  - path: instance/config/hooked.yml
"""


def test_ring_for_repo_path_fixture_matrix(tmp_path):
    _write_core(tmp_path, FIXTURE_CORE)
    r = lambda p: AM.ring_for_repo_path(p, root=tmp_path)  # noqa: E731
    assert r("a/locked-file.py") == 0            # files entry
    assert r("locked/dir") == 0                  # dirs entry itself
    assert r("locked/dir/deep/x.py") == 0        # dir-cover
    assert r("logs/run/anything.jsonl") == 0     # trailing-slash runtime dir
    assert r("shared/one-ledger.jsonl") == 0     # runtime file entry
    assert r("instance/config/hooked.yml") == 0  # hook_protected entry
    assert r("a/free-file.py") == 2              # default ring
    assert r("locked/dir-sibling.py") == 2       # prefix must be a real dir
    assert AM.ring_for_repo_path("a/free-file.py", root=tmp_path, default=1) == 1


def test_ring_for_repo_path_unknown_on_missing_or_corrupt(tmp_path):
    # Missing enumeration → None (unknown), never "not ring 0".
    assert AM.ring_for_repo_path("a/b.py", root=tmp_path / "absent") is None
    corrupt = tmp_path / "corrupt-root"
    _write_core(corrupt, "files: 'not-a-list'\n")
    assert AM.ring_for_repo_path("a/b.py", root=corrupt) is None
    # Path traversal / empty / non-str are unknown too.
    _write_core(tmp_path, FIXTURE_CORE)
    assert AM.ring_for_repo_path("../a/b.py", root=tmp_path) is None
    assert AM.ring_for_repo_path("", root=tmp_path) is None
    assert AM.ring_for_repo_path(None, root=tmp_path) is None


def test_ring_for_repo_path_unknown_ring_proposes_downstream(tmp_path):
    ring = AM.ring_for_repo_path("a/b.py", root=tmp_path / "absent")  # None
    d = _desc(ring=ring)
    assert AM.action_mode(d, SOVEREIGN) == "propose"


def test_ring_for_repo_path_real_repo_enumeration():
    # The real enumeration must classify its own kernel as ring 0 — and this
    # very seam module (unlocked, ring 1+) as NOT ring 0.
    assert AM.ring_for_repo_path(
        "framework/authority/posture.py", root=_REPO_ROOT) == 0
    assert AM.ring_for_repo_path(
        "framework/policies/immutable-core.yml", root=_REPO_ROOT) == 0
    assert AM.ring_for_repo_path(
        "memory/golden-evals/eval-001-kill-switch.md", root=_REPO_ROOT) == 0
    assert AM.ring_for_repo_path(
        "framework/authority/action_mode.py", root=_REPO_ROOT) == 2
