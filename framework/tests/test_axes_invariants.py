"""Axis-matrix invariant suite — the 18-combo sweep [AX-6, spec §6.3].

The membrane invariants run parametrized across ALL 3 autonomy levels × 2
flavors × 3 deployment targets = 18 combos, over the RESOLVED policy: a
tmp-root ``instance/config/posture.yml`` per combo, resolved through the REAL
kernels (posture kernel with injected ``is_locked_fn`` — no chflags, no root,
no Redis; the shipped, validated authority-matrix floor; the grants loader).
They are table lookups — the full sweep costs seconds and makes cross-axis
coupling impossible to land silently:

  * ceilings never unconditional-auto (always_gated / conditional
    standing_grant only; non-sovereign strictly always_gated);
  * demote always narrows (never wider than any live state; posture-invariant
    vs the root table);
  * earn_up ≤ root cell-by-cell on the FROZEN verdict-permissiveness ordering
    (+ the static earn_up floor is all-propose_only below the ceilings);
  * never_grant classes are refused by the grants loader in EVERY combo;
  * sovereign requires attestation (unattested ⇒ guardian; earn_up is a
    narrowing choice honored even unattested);
  * flavor / deployment_target NEVER change verdict resolution — byte-equal
    verdict maps across those axes for a fixed level.

Engine parity is asserted for every posture table the gate supports
(``policy_engine._POSTURE_TABLES`` ∪ guardian) so AX-2's earn_up wire extends
coverage automatically when it lands.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import policy_engine as PE  # noqa: E402
from framework.authority import grants as G  # noqa: E402
from framework.authority import matrix as M  # noqa: E402
from framework.authority import posture as P  # noqa: E402

LOCKED = lambda p: True  # noqa: E731
UNLOCKED = lambda p: False  # noqa: E731

# The three axes, pinned as SPEC literals (a vocab test diffs them against the
# kernel constants — drift in either direction fails).
LEVELS = ("earn_up", "guardian", "sovereign")
FLAVORS = ("personal", "org")
TARGETS = ("macbook", "mac_mini", "docker")
COMBOS = tuple(itertools.product(LEVELS, FLAVORS, TARGETS))
COMBO_IDS = ["-".join(c) for c in COMBOS]

CEILINGS = tuple(sorted(G.CEILING_RISK_CLASSES))
STATES = tuple(sorted(M.CONFIDENCE_STATES))
RANK = M.VERDICT_PERMISSIVENESS


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for var in ("CABINET_POSTURE", "CABINET_NEEDS_WIRED", "CABINET_ID",
                "CABINET_ROOT", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))


@pytest.fixture(scope="module")
def policy():
    # Anchor to THIS repo's shipped floor explicitly: module-scoped fixtures
    # instantiate before function-scoped autouse env-cleaners, so an ambient
    # CABINET_ROOT (e.g. leaked by an earlier suite) must never redirect what
    # this suite is defined to test.
    floor = _REPO_ROOT / "framework" / "policies" / "authority-matrix.yml"
    return M.matrix_policy(M.load_matrix(str(floor)))


def _write_ruling(root: Path, level: str, flavor: str, target: str,
                  **overrides) -> Path:
    cfg = {
        "version": 1, "status": "ruled", "ruled_at": "2026-07-05T00:00:00Z",
        "basis": "axes 18-combo invariant suite", "deployment": "main",
        "flavor": flavor, "posture": level, "deployment_target": target,
    }
    cfg.update(overrides)
    # Path built from the kernel's own resolver (layer-separation gate:
    # no literal instance token here; test_posture.py pins the location).
    p = P.posture_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(cfg))
    return p


def _resolved(root, **kw):
    return P.resolve_posture(root=root, file_needs=False, **kw)


def _table(policy: dict, posture_name: str) -> dict:
    """The FULL verdicts table a resolved posture selects — guardian IS the
    root table (never a postures.guardian key), per the kernel contract."""
    if posture_name == "guardian":
        return policy["verdicts"]
    return policy["postures"][posture_name]["verdicts"]


def _verdict_map(table: dict) -> dict:
    return {
        (rc, st): PE.resolve_verdict(table, rc, st)
        for rc in sorted(M.RISK_CLASSES)
        for st in STATES
    }


# ---------------------------------------------------------------------------
# Vocab + shape
# ---------------------------------------------------------------------------

def test_the_sweep_is_exactly_three_by_two_by_three():
    assert len(COMBOS) == 18
    assert set(LEVELS) == set(P.POSTURES)
    assert set(FLAVORS) == set(P.FLAVORS)
    assert set(TARGETS) == set(P.DEPLOYMENT_TARGETS)


def test_frozen_verdict_permissiveness_ordering():
    """AX-1 frozen ordering (lanes consume, never redefine): always_gated(0)
    < propose_only < classifier < auto_with_veto_window < {act_with_undo,
    notify_after} < auto(5); standing_grant deliberately unranked."""
    assert RANK["always_gated"] == 0
    assert RANK["always_gated"] < RANK["propose_only"] < RANK["classifier"] \
        < RANK["auto_with_veto_window"] < RANK["act_with_undo"] < RANK["auto"]
    assert RANK["act_with_undo"] == RANK["notify_after"]
    assert RANK["auto"] == 5
    assert "standing_grant" not in RANK


# ---------------------------------------------------------------------------
# The 18-combo membrane invariants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level,flavor,target", COMBOS, ids=COMBO_IDS)
def test_ceilings_never_unconditional_auto(policy, tmp_path, level, flavor,
                                           target):
    _write_ruling(tmp_path, level, flavor, target)
    resolved = _resolved(tmp_path, is_locked_fn=LOCKED)
    assert resolved == level  # attested ruling is honored on every axis point
    table = _table(policy, resolved)
    for rc in CEILINGS:
        row = table[rc]
        assert set(row) == {"*"}, (resolved, rc)
        verdict = row["*"]
        assert verdict != "auto"
        assert verdict in ("always_gated", "standing_grant"), (resolved, rc)
        if resolved != "sovereign":
            # standing_grant is a sovereign surface — guardian AND earn_up
            # ceilings stay plain always_gated.
            assert verdict == "always_gated", (resolved, rc)
    assert M.no_ceiling_or_prod_auto(policy) is True


@pytest.mark.parametrize("level,flavor,target", COMBOS, ids=COMBO_IDS)
def test_demote_always_narrows(policy, tmp_path, level, flavor, target):
    """demote is the evidence floor: never wider than ANY live state of its
    row, and posture-invariant vs the root table (evidence beats posture)."""
    _write_ruling(tmp_path, level, flavor, target)
    table = _table(policy, _resolved(tmp_path, is_locked_fn=LOCKED))
    root = policy["verdicts"]
    for rc, states in table.items():
        if rc in CEILINGS:
            continue
        demote = states["demote"]
        for st, verdict in states.items():
            assert RANK[demote] <= RANK[verdict], (rc, st)
        assert demote == root[rc]["demote"], rc


@pytest.mark.parametrize("level,flavor,target", COMBOS, ids=COMBO_IDS)
def test_earn_up_only_narrows_vs_root(policy, tmp_path, level, flavor, target):
    """earn_up ≤ root cell-by-cell on the frozen ordering — in every combo,
    whatever posture is live — plus the static floor: every non-ceiling cell
    is propose_only (all autonomy above it is AX-2 ladder overlay, never
    table)."""
    _write_ruling(tmp_path, level, flavor, target)
    earn = policy["postures"]["earn_up"]["verdicts"]
    root = policy["verdicts"]
    for rc in sorted(M.RISK_CLASSES):
        for st in STATES:
            earned = PE.resolve_verdict(earn, rc, st)
            rooted = PE.resolve_verdict(root, rc, st)
            assert earned != "standing_grant", (rc, st)
            assert RANK[earned] <= RANK[rooted], (rc, st, earned, rooted)
            if rc not in CEILINGS:
                assert earned == "propose_only", (rc, st)


@pytest.mark.parametrize("level,flavor,target", COMBOS, ids=COMBO_IDS)
def test_never_grant_refused_in_every_combo(tmp_path, level, flavor, target):
    """Rows whose risk_class ∈ posture.yml never_grant are dropped fail-closed
    by the grants loader — identically at every axis point."""
    _write_ruling(tmp_path, level, flavor, target,
                  never_grant=["external_comms", "spend"])
    action_types = {
        "external_comms": "external_email", "deploy_prod": "vercel_deploy_prod",
        "spend": "purchase", "secrets": "secret_write",
        "network_write": "mcp_post", "credentials_grant": "oauth_grant",
    }
    rows = [
        {
            "id": "GRANT-%s" % rc, "deployment": "main", "risk_class": rc,
            "action_types": [action_types[rc]], "lanes": ["bakery"],
            "scope": {}, "rate": {"max_per_day": 5},
            "expires": "2026-09-01", "granted_by": "Captain (test)",
            "granted_at": "2026-07-05T00:00:00Z",
            "basis": "NEED-00000000", "revoked": False,
        }
        for rc in CEILINGS
    ]
    G.grants_path(tmp_path).write_text(
        yaml.safe_dump({"version": 1, "grants": rows}))
    assert P.never_grant_classes(tmp_path) == {"external_comms", "spend"}
    loaded = G.load_grants(tmp_path, is_locked_fn=LOCKED, file_needs=False)
    kept = {g["risk_class"] for g in loaded}
    assert kept == set(CEILINGS) - {"external_comms", "spend"}
    assert len(loaded) == 4


@pytest.mark.parametrize("level,flavor,target", COMBOS, ids=COMBO_IDS)
def test_sovereign_requires_attestation(tmp_path, level, flavor, target):
    """Unattested (valid-but-unlocked) rulings: sovereign falls to guardian;
    earn_up — a narrowing — stays honored; guardian stays guardian. Attested
    rulings resolve their level exactly."""
    _write_ruling(tmp_path, level, flavor, target)
    assert _resolved(tmp_path, is_locked_fn=LOCKED) == level
    expected_unattested = "earn_up" if level == "earn_up" else "guardian"
    assert _resolved(tmp_path, is_locked_fn=UNLOCKED) == expected_unattested


@pytest.mark.parametrize("level", LEVELS)
def test_flavor_and_target_never_change_verdict_resolution(policy, tmp_path,
                                                           level):
    """The identity/topology axes select evidence supply and backends — NEVER
    authority semantics: for a fixed level, all 6 flavor×target rulings
    resolve the same posture and a byte-equal full verdict map."""
    seen = []
    for i, (flavor, target) in enumerate(itertools.product(FLAVORS, TARGETS)):
        root = tmp_path / ("combo-%d" % i)
        _write_ruling(root, level, flavor, target)
        # the target axis IS read (backend selection, AX-4) ...
        assert P.deployment_target(root) == target
        resolved = _resolved(root, is_locked_fn=LOCKED)
        seen.append((resolved, _verdict_map(_table(policy, resolved))))
    baseline = seen[0]
    assert all(entry == baseline for entry in seen[1:]), (
        "flavor/deployment_target shifted posture or verdict resolution"
    )


# ---------------------------------------------------------------------------
# Engine parity + no-config parity
# ---------------------------------------------------------------------------

def test_gate_engine_parity_for_every_supported_posture(policy):
    """PE.resolve_verdict's posture-kwarg selection must equal the plain
    lookup on the posture's own table, for every posture the engine supports
    (dynamic over _POSTURE_TABLES so AX-2's earn_up wire auto-extends this)."""
    for name in sorted(PE._POSTURE_TABLES | {"guardian"}):
        table = _table(policy, name)
        for rc in sorted(M.RISK_CLASSES):
            for st in STATES:
                via_kwarg = PE.resolve_verdict(
                    policy["verdicts"], rc, st,
                    posture=name, postures=policy["postures"],
                )
                assert via_kwarg == PE.resolve_verdict(table, rc, st), \
                    (name, rc, st)


def test_no_config_resolves_guardian_with_empty_axes(tmp_path, policy):
    """Guardian byte-parity floor: an axis-config-less deployment resolves
    guardian on the ROOT table, empty never_grant, inferred target."""
    assert _resolved(tmp_path) == "guardian"
    assert P.never_grant_classes(tmp_path) == frozenset()
    assert P.deployment_target(tmp_path) == P.infer_deployment_target()
    assert _table(policy, "guardian") is policy["verdicts"]
