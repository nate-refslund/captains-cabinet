"""`propose_only` and `always_gated` are no longer OPERATIONALLY IDENTICAL.

THE DEFECT (direction gate 2026-07-27, arm A). `main()` exits 2 on ANY
non-None result, so a verdict meaning "above your bar — ask, and the chain
proceeds without this step" and a verdict meaning "hard ceiling, no auto path
exists" produced the same caller-visible refusal. The vocabulary was richer
than enforcement could express, which is why the enforcing flip measured as
52,659 refusals (75.66%) when only 11,570 of them are ceilings.

WHAT THIS FILE PINS, and the order matters:

  1. The SIX HARD CEILINGS STILL REFUSE. This change makes a refusal
     legible as a proposal, so the ONLY thing between it and a disaster is
     that the ceiling classes are excluded from that treatment. There is one
     arm per class — external_comms, deploy_prod, spend, secrets,
     network_write, credentials_grant — written as if someone were trying to
     slip one through: each asserts the block, the EXACT guardian byte
     string, kind==GATE, and that no `capability` need was filed that could
     make it read as grantable headroom.
  2. The two verdicts are distinguishable by a STRUCTURED FIELD, never by a
     substring of prose.
  3. NO WIDENING. Exit codes are unchanged and every guardian message stays
     byte-identical: a propose verdict still withholds the step, because the
     unclassified bucket that dominates it is byte-indistinguishable from its
     hostile twins.

Every arm here FAILS against pre-change code: `.kind` does not exist on a
plain `str`, and the pre-change engine files nothing on the propose path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import matrix as M  # noqa: E402
from framework.authority import needs as N  # noqa: E402
from framework.authority import policy_engine as PE  # noqa: E402

_ENGINE = _REPO_ROOT / "framework" / "authority" / "policy_engine.py"

# The six hard ceilings, with the house-vetted probe for each and the exact
# guardian string it has always emitted (kept byte-identical by this change —
# these are the same goldens test_guardian_parity pins).
_CEILINGS = {
    "external_comms": (
        "mcp__brain__queue_draft",
        {"recipient": "outsider@gmail.com", "body": "hi", "channel": "teams"},
        "GATED (hard ceiling: external_comms) — draft via queue_draft, never auto.",
    ),
    "deploy_prod": (
        "Bash", {"command": "git push origin main"},
        "GATED (hard ceiling: deploy_prod) — propose to Captain; no auto path.",
    ),
    "spend": (
        "Bash", {"command": "stripe charge --amount 5000"},
        "GATED (hard ceiling: spend) — propose to Captain; no auto path.",
    ),
    "secrets": (
        "Write", {"file_path": "/workspace/product/.env", "content": "X=1"},
        "GATED (hard ceiling: secrets) — propose to Captain; no auto path.",
    ),
    "network_write": (
        "mcp__some__create_post", {},
        "GATED (hard ceiling: network_write) — propose to Captain; no auto path.",
    ),
    "credentials_grant": (
        "Bash", {"command": "oauth grant token"},
        "GATED (hard ceiling: credentials_grant) — propose to Captain; no auto path.",
    ),
}

# A cell the matrix genuinely floors at propose_only (deploy_nonprod at an
# unmeasured confidence state) and the unclassified fail-safe.
_PROPOSE_PROBE = ("Bash", {"command": "git push origin feature-x"})
_UNCLASSIFIED_PROBE = ("Bash", {"command": "gh secret set FOO --body bar"})


@pytest.fixture(autouse=True)
def _root(monkeypatch, tmp_path):
    """A tmp deployment with the shipped floor and NO posture config, with
    needs filing ON (the enforcing world this change is about).

    Nothing here writes a live safety switch: the needs ledger and the
    filing markers are runtime state under a throwaway root.
    """
    for var in ("CABINET_POSTURE", "CABINET_NEEDS_WIRED", "CABINET_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_AUTHORITY_ENFORCING", "1")
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    pol_dir = tmp_path / "framework" / "policies"
    pol_dir.mkdir(parents=True)
    (pol_dir / "authority-matrix.yml").write_text(
        (_REPO_ROOT / "framework" / "policies" / "authority-matrix.yml").read_text()
    )
    (tmp_path / "shared" / "interfaces").mkdir(parents=True)
    return tmp_path


def _policy() -> dict:
    return M.matrix_policy(M.load_matrix(
        str(_REPO_ROOT / "framework" / "policies" / "authority-matrix.yml")
    ))


def _ledger_rows(root: Path) -> list[dict]:
    p = Path(N.ledger_path(str(root)))
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


# ---------------------------------------------------------------------------
# 1. THE SIX HARD CEILINGS STILL REFUSE — one arm per class
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("risk_class", sorted(_CEILINGS))
def test_hard_ceiling_still_refuses(risk_class, _root):
    """Each ceiling class still terminates, with its exact guardian bytes.

    This is the arm that matters most in this file. A ceiling that started
    reading as `propose` would be counted as grantable headroom and would
    have its step treated as withheld-but-askable — the exact way an
    outbound/deploy/spend/secret action could be slipped through a change
    whose whole purpose is to soften refusals.
    """
    tool, tool_input, golden = _CEILINGS[risk_class]
    result = PE._eval_authority_matrix(_policy(), tool, tool_input, "cto")

    assert result is not None, f"{risk_class} ceiling ALLOWED — catastrophic"
    assert str(result) == golden, f"{risk_class} guardian bytes changed"
    assert PE.decision_kind(result) == PE.GATE, (
        f"{risk_class} resolved kind={PE.decision_kind(result)!r}, not GATE — "
        f"a ceiling must never be counted as a grantable proposal"
    )
    assert PE.decision_kind(result) != PE.PROPOSE
    assert PE.decision_kind(result) != PE.UNCLASSIFIED


@pytest.mark.parametrize("risk_class", sorted(_CEILINGS))
def test_hard_ceiling_files_no_capability_need(risk_class, _root):
    """A ceiling refusal files no `capability` need.

    `capability` is the kind the propose path files, and it is the kind an
    operator reads as "the fleet wants this and could be granted it". A
    ceiling is never that, so it must not appear there — otherwise granting
    the ledger row would look like a route around the ceiling.

    NON-VACUOUS BY CONSTRUCTION: filing is proven live in THIS root first.
    Without that, a root where filing is broken (or disabled) would pass
    this arm while proving nothing at all — the degenerate-end failure.
    """
    pol = _policy()
    PE._eval_authority_matrix(pol, *_PROPOSE_PROBE, "cto")
    baseline = [r for r in _ledger_rows(_root) if r.get("kind") == "capability"]
    assert baseline, (
        "filing is not live in this root — the ceiling arm below would pass "
        "vacuously"
    )

    tool, tool_input, _ = _CEILINGS[risk_class]
    PE._eval_authority_matrix(pol, tool, tool_input, "cto")
    caps = [r for r in _ledger_rows(_root) if r.get("kind") == "capability"]
    offending = [r for r in caps if r.get("risk_class") == risk_class]
    assert offending == [], (
        f"{risk_class} ceiling filed a capability need: {offending!r}"
    )
    assert len(caps) == len(baseline), (
        f"{risk_class} ceiling appended to the capability ledger"
    )


@pytest.mark.parametrize("risk_class", sorted(_CEILINGS))
def test_hard_ceiling_still_exits_two(risk_class, _root):
    """End-to-end: the ceiling still terminates the tool call at the hook."""
    tool, tool_input, _ = _CEILINGS[risk_class]
    env = dict(os.environ)
    env.update({
        "CABINET_ROOT": str(_root),
        "CABINET_AUTHORITY_ENFORCING": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OFFICER": "cto",
    })
    proc = subprocess.run(
        [sys.executable, str(_ENGINE)],
        input=json.dumps({"tool_name": tool, "tool_input": tool_input}),
        capture_output=True, text=True, env=env, cwd=str(_REPO_ROOT),
    )
    assert proc.returncode == 2, (
        f"{risk_class} ceiling exited {proc.returncode}, not 2 — the step ran"
    )
    assert "GATED (hard ceiling" in proc.stderr


# ---------------------------------------------------------------------------
# 2. THE COLLAPSE IS CLOSED — propose and gate are distinguishable
# ---------------------------------------------------------------------------

def test_propose_and_gate_are_no_longer_identical(_root):
    """The defect itself: the two verdicts now differ on a structured field."""
    pol = _policy()
    propose = PE._eval_authority_matrix(pol, *_PROPOSE_PROBE, "cto")
    gate = PE._eval_authority_matrix(
        pol, _CEILINGS["deploy_prod"][0], _CEILINGS["deploy_prod"][1], "cto"
    )
    assert propose is not None and gate is not None
    assert PE.decision_kind(propose) == PE.PROPOSE
    assert PE.decision_kind(gate) == PE.GATE
    assert PE.decision_kind(propose) != PE.decision_kind(gate)


def test_unclassified_is_its_own_kind(_root):
    """The 71.5% bucket is NOT reported as a governed proposal.

    Calling "the classifier cannot see this" a proposal would dress an
    unmeasured hole as a decision — so it carries its own kind and is
    counted on its own.
    """
    result = PE._eval_authority_matrix(_policy(), *_UNCLASSIFIED_PROBE, "cto")
    assert result is not None
    assert PE.decision_kind(result) == PE.UNCLASSIFIED
    assert PE.decision_kind(result) != PE.PROPOSE


def test_propose_files_a_need_naming_the_cell(_root):
    """A propose verdict leaves a durable, deduped trace of what was refused."""
    result = PE._eval_authority_matrix(_policy(), *_PROPOSE_PROBE, "cto")
    assert PE.decision_kind(result) == PE.PROPOSE
    assert result.need_id, "propose filed no need id"
    caps = [r for r in _ledger_rows(_root) if r.get("kind") == "capability"]
    assert caps, "propose verdict filed no capability need"
    assert caps[-1]["risk_class"] == "deploy_nonprod"
    assert caps[-1]["status"] == "open"


def test_propose_refiling_is_rate_limited(_root):
    """Re-refusing the same cell does not append a row per tool call.

    `file_need` costs ~100ms (its emit re-verifies the evidence trial), and
    this gate runs on EVERY tool call over a corpus where a live flip
    withholds ~41k steps. Unbounded filing would be both a latency
    regression on the hot path and an unbounded ledger.
    """
    pol = _policy()
    for _ in range(6):
        PE._eval_authority_matrix(pol, *_PROPOSE_PROBE, "cto")
    caps = [r for r in _ledger_rows(_root) if r.get("kind") == "capability"]
    assert len(caps) == 1, f"expected 1 rate-limited row, got {len(caps)}"


def test_distinct_cells_file_distinct_needs(_root):
    """Two different refused cells must produce two DIFFERENT need ids.

    MUTANT THIS KILLS: `_propose_need_marker` returning a constant path. Every
    arm above uses one probe, so a constant marker suppresses every cell after
    the first and the whole suite still passes — while the ledger collapses to
    a single row and the "enumerated list of what the fleet is denied" becomes
    one arbitrary entry.
    """
    pol = _policy()
    a = PE._eval_authority_matrix(pol, *_PROPOSE_PROBE, "cto")
    b = PE._eval_authority_matrix(pol, *_UNCLASSIFIED_PROBE, "cto")
    assert a.need_id and b.need_id
    assert a.need_id != b.need_id, "two distinct cells collapsed to one need"
    caps = [r for r in _ledger_rows(_root) if r.get("kind") == "capability"]
    assert len({r["id"] for r in caps}) == 2, (
        f"expected 2 distinct needs on the ledger, got {[r['id'] for r in caps]}"
    )


def test_unclassified_actually_files(_root):
    """The 71.5% blind spot leaves a record.

    MUTANT THIS KILLS: the UNCLASSIFIED branch filing nothing. `test_unclassified_is_its_own_kind`
    only checks the kind, so a branch that labels correctly and records
    nothing passes — and the code comment's promise that the blind spot is
    recorded becomes false.
    """
    result = PE._eval_authority_matrix(_policy(), *_UNCLASSIFIED_PROBE, "cto")
    assert result.need_id, "unclassified filed no need"
    caps = [r for r in _ledger_rows(_root) if r.get("kind") == "capability"]
    assert [r for r in caps if r.get("risk_class") == "unclassified"], (
        f"no unclassified capability row on the ledger: {caps!r}"
    )


def test_refiling_resumes_after_the_window(monkeypatch, _root):
    """The rate limit is a WINDOW, not a permanent mute.

    MUTANT THIS KILLS: `_PROPOSE_REFILE_SECONDS = 10**12`. The rate-limit arm
    only proves suppression WITHIN the window, so an infinite window passes it
    while the need is never re-filed again and `count`/`last_seen` freeze.
    """
    pol = _policy()
    PE._eval_authority_matrix(pol, *_PROPOSE_PROBE, "cto")
    before = len(_ledger_rows(_root))
    monkeypatch.setattr(PE, "_PROPOSE_REFILE_SECONDS", 0)
    PE._eval_authority_matrix(pol, *_PROPOSE_PROBE, "cto")
    assert len(_ledger_rows(_root)) > before, (
        "the window elapsed and the need was still never re-filed"
    )


def test_future_dated_marker_does_not_mute_the_need_forever(_root):
    """A marker dated in the future must degrade to re-file, never to silence.

    The marker is officer-writable runtime state outside the hook's protected
    set, so `time.time() - mtime` alone lets a clock skew — or a deliberate
    `touch -t 2036` — satisfy `< window` forever and permanently suppress the
    audit record while the step keeps being refused.
    """
    pol = _policy()
    first = PE._eval_authority_matrix(pol, *_PROPOSE_PROBE, "cto")
    marker = PE._propose_need_marker(first.need_id)
    assert marker and os.path.exists(marker)
    future = time.time() + 365 * 24 * 3600
    os.utime(marker, (future, future))
    before = len(_ledger_rows(_root))
    PE._eval_authority_matrix(pol, *_PROPOSE_PROBE, "cto")
    assert len(_ledger_rows(_root)) > before, (
        "a future-dated marker silenced the need permanently"
    )


def test_floor_without_a_usable_hard_ceiling_is_corrupt_not_permissive(_root):
    """A malformed `hard_ceiling` must GATE every class, never propose it.

    Without this, ceiling classes fall through to the step-6 collapse and get
    labelled PROPOSE — filing a `capability` need that reads "grant
    autonomous external_message for this lane". A change whose thesis is
    "a refusal becomes legible as a proposal" must never put *grant me
    outbound comms* on the Captain's deny surface.

    The last case is the sharp one: a list that is well-formed but OMITS this
    class. The canonical set decides, not the floor's own list.
    """
    for broken in ({}, {"hard_ceiling": []}, {"hard_ceiling": "external_comms"},
                   {"hard_ceiling": {"a": 1}}, {"hard_ceiling": ["spend"]}):
        pol = _policy()
        pol.pop("hard_ceiling", None)
        pol.update(broken)
        tool, tool_input, _ = _CEILINGS["external_comms"]
        result = PE._eval_authority_matrix(pol, tool, tool_input, "cto")
        assert result is not None, f"{broken!r} ALLOWED a ceiling"
        assert PE.decision_kind(result) == PE.GATE, (
            f"{broken!r} resolved a ceiling to "
            f"{PE.decision_kind(result)!r}, not GATE"
        )
    caps = [r for r in _ledger_rows(_root) if r.get("kind") == "capability"]
    assert not [r for r in caps if r.get("risk_class") in _CEILINGS], (
        f"a malformed floor filed a ceiling as grantable: {caps!r}"
    )


def test_undo_gap_is_not_filed_as_a_capability_request(_root):
    """An undo-plane outage must not read as "grant me this autonomy".

    The remedy for a missing inverse is registering one, not granting the
    officer the action. Filing it under the capability wording asks the
    Captain to grant away a broken undo plane.
    """
    nid = PE._file_propose_need(
        "pm_write", "task_create", "cto", "cto",
        why="undo plane unusable for task_create (lane cto): no inverse",
    )
    assert nid
    rows = [r for r in _ledger_rows(_root) if r.get("id") == nid]
    assert rows and "undo plane unusable" in rows[-1]["why"], (
        f"undo-gap need filed with the capability wording: {rows!r}"
    )


def test_gate_decision_survives_copy_and_pickle(_root):
    """copy/deepcopy/pickle must not raise where a plain `str` round-tripped."""
    import copy as _copy
    import pickle as _pickle
    d = PE.GateDecision("PROPOSE-ONLY (x) — y", PE.PROPOSE, "NEED-abc12345")
    for made in (_copy.copy(d), _copy.deepcopy(d), _pickle.loads(_pickle.dumps(d))):
        assert made == str(d)
        assert made.kind == PE.PROPOSE
        assert made.need_id == "NEED-abc12345"


# ---------------------------------------------------------------------------
# 3. NO WIDENING — the step is still withheld, the bytes are still guardian's
# ---------------------------------------------------------------------------

def test_propose_still_withholds_the_step(_root):
    """A propose verdict does NOT let the tool run.

    The unclassified bucket is byte-indistinguishable from `bash
    send-to-group.sh` (a Telegram POST), `gh api -X POST .../comments` and
    `python3 -c "...smtplib..."`. Anything that let a propose verdict execute
    would ship exactly the widening the direction gate refused.
    """
    for probe in (_PROPOSE_PROBE, _UNCLASSIFIED_PROBE):
        env = dict(os.environ)
        env.update({
            "CABINET_ROOT": str(_root),
            "CABINET_AUTHORITY_ENFORCING": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "OFFICER": "cto",
        })
        proc = subprocess.run(
            [sys.executable, str(_ENGINE)],
            input=json.dumps({"tool_name": probe[0], "tool_input": probe[1]}),
            capture_output=True, text=True, env=env, cwd=str(_REPO_ROOT),
        )
        assert proc.returncode == 2, (
            f"propose verdict for {probe[1]!r} exited {proc.returncode} — "
            f"the step RAN. This is the widening that must never ship."
        )


def test_guardian_propose_bytes_unchanged(_root):
    """The propose message is byte-identical to the pre-change guardian gate."""
    result = PE._eval_authority_matrix(_policy(), *_PROPOSE_PROBE, "cto")
    assert str(result).startswith("PROPOSE-ONLY (deploy_nonprod, confidence=")
    assert "unmeasured" in str(result)
    assert "filed NEED-" not in str(result), (
        "the need id leaked into the guardian block string — parity broken"
    )


def test_gate_decision_is_str_compatible(_root):
    """Every existing consumer sees the exact `str` it always saw.

    ~100 call sites and assertions depend on `evaluate_policy` returning
    `str | None` — truthiness in main() and policy-shadow, `.startswith`,
    `in`, print. Nothing was weakened to buy the new field.
    """
    d = PE.GateDecision("PROPOSE-ONLY (x) — y", PE.PROPOSE, "NEED-abc12345")
    assert isinstance(d, str)
    assert bool(d) is True
    assert d == "PROPOSE-ONLY (x) — y"
    assert d.startswith("PROPOSE-ONLY")
    assert "x" in d
    assert f"{d}" == "PROPOSE-ONLY (x) — y"
    assert json.loads(json.dumps({"m": d}))["m"] == "PROPOSE-ONLY (x) — y"
    assert d.kind == PE.PROPOSE and d.need_id == "NEED-abc12345"


def test_legacy_typed_policy_results_have_no_kind(_root):
    """A legacy typed block is not silently reclassified as a proposal."""
    pol = {
        "type": "binary_block", "name": "no-curl",
        "binaries": ["curl"], "message": "no curl",
    }
    result = PE.evaluate_policy(pol, "Bash", {"command": "curl https://x"}, "cto")
    assert result, "the legacy rule stopped blocking"
    assert PE.decision_kind(result) is None
