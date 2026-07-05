"""SOV-9 guardian byte-identity suite (spec §7 P1 + the A/A obligation).

THE amendment-level proof that merging the sovereign machinery changes
NOTHING for a deployment with no posture config: resolution, block strings,
digest bytes, cap verdicts, and the binder wire are all byte-identical to the
pre-posture goldens — and stay identical with `CABINET_POSTURE=sovereign`
exported (env can never widen; eval-018).

Complements (does not replace) the per-lane suites: SOV-3's gate tests,
SOV-4's lane sentinels, SOV-5's brake tests, SOV-6's digest/binder tests.
This file is the one the amendment's §6 evidence pack cites, so it leans on
REAL artifacts (shipped floor, real resolve_posture on tmp roots) rather
than fakes wherever possible.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_LIB = _REPO_ROOT / "cabinet" / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import policy_engine as PE  # noqa: E402
from framework.authority import matrix as M  # noqa: E402
from framework.authority import posture as P  # noqa: E402
from framework.frontdoor import actfirst_canary as AC  # noqa: E402
from framework.frontdoor import binder_wire as BW  # noqa: E402
from framework.frontdoor import tell_surface as TS  # noqa: E402

_ALL_STATES = ("unmeasured", "propose_only", "eligible", "graduated", "demote")
_ALL_ROWS = (
    "reversible", "pm_write", "calendar_write", "internal_comms",
    "deploy_nonprod", "external_comms", "deploy_prod", "spend",
    "secrets", "network_write", "credentials_grant",
)

# Recorded pre-change goldens (the exact strings the A0 gate emitted before
# the sovereign merge — evals 011-015). If any of these asserts fails, the
# guardian world is NOT byte-identical and the amendment must not apply.
_GOLDEN_BLOCKS = {
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


@pytest.fixture(autouse=True)
def _isolated_root(monkeypatch, tmp_path):
    """Point every real resolver at a tmp tree with NO posture config, and
    clear the posture env vars — the exact no-config deployment."""
    for var in ("CABINET_POSTURE", "CABINET_NEEDS_WIRED", "CABINET_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    return tmp_path


def _matrix_policy() -> dict:
    # Explicit path: the autouse fixture points CABINET_ROOT at a tmp tree
    # (so the POSTURE resolvers see no config), but the parity subject is
    # THIS repo's shipped floor.
    return M.matrix_policy(M.load_matrix(
        str(_REPO_ROOT / "framework" / "policies" / "authority-matrix.yml")
    ))


# `CABINET_POSTURE` exported as sovereign must change NOTHING (env narrows
# only) — every parity test below runs in both env states.
_ENV_STATES = (None, "sovereign")


def _set_env(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("CABINET_POSTURE", raising=False)
    else:
        monkeypatch.setenv("CABINET_POSTURE", value)


# ---------------------------------------------------------------------------
# P1 — resolve_verdict guardian truth-table, three variants equal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("env", _ENV_STATES)
def test_p1_resolve_verdict_three_variants_equal(monkeypatch, env):
    _set_env(monkeypatch, env)
    pol = _matrix_policy()
    v, p = pol["verdicts"], pol["postures"]
    for rc in _ALL_ROWS:
        for state in _ALL_STATES:
            base = PE.resolve_verdict(v, rc, state)
            assert PE.resolve_verdict(v, rc, state, posture="guardian",
                                      postures=p) == base
            assert PE.resolve_verdict(v, rc, state, posture=None,
                                      postures=p) == base
            assert PE.resolve_verdict(v, rc, state, posture="unknown",
                                      postures=p) == base


# ---------------------------------------------------------------------------
# Gate truth-table — block strings byte-identical with no posture config
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("env", _ENV_STATES)
def test_gate_ceiling_strings_byte_identical(monkeypatch, env, _isolated_root):
    """REAL kernel path: resolve_posture reads the tmp CABINET_ROOT (no
    posture.yml ⇒ guardian) — not a patched stub — and every ceiling block
    string equals its recorded golden byte-for-byte."""
    _set_env(monkeypatch, env)
    assert P.resolve_posture(root=_isolated_root) == "guardian"
    pol = _matrix_policy()
    with patch.object(PE, "_resolve_posture",
                      lambda lane=None: P.resolve_posture(lane, root=_isolated_root)):
        for rc, (tool, ti, golden) in _GOLDEN_BLOCKS.items():
            assert PE._eval_authority_matrix(pol, tool, ti, "cto") == golden


@pytest.mark.parametrize("env", _ENV_STATES)
def test_gate_propose_string_byte_identical(monkeypatch, env, _isolated_root):
    _set_env(monkeypatch, env)
    pol = _matrix_policy()
    with patch.object(PE, "_resolve_posture",
                      lambda lane=None: P.resolve_posture(lane, root=_isolated_root)):
        result = PE._eval_authority_matrix(
            pol, "Edit", {"file_path": "src/app.py", "content": "x"}, "cto"
        )
    assert result is not None
    assert result.startswith("PROPOSE-ONLY (reversible, confidence=")
    assert "unmeasured" in result


# ---------------------------------------------------------------------------
# Digest — empty-needs bytes identical (SOV-6 additive param)
# ---------------------------------------------------------------------------

_ACTED = [{
    "pid": "p-1", "index": 1, "kind": "monday_task_create",
    "summary": "Created task 'X' on board 5091706356",
    "receipt": "r-1", "undoable": True, "ts": "2026-07-04T10:00:00Z",
}]


@pytest.mark.parametrize("env", _ENV_STATES)
def test_digest_bytes_identical_without_needs(monkeypatch, env):
    """`needs_rows` omitted == `needs_rows=None` == `needs_rows=[]` — the
    pre-needs digest, byte for byte; no 🙋 section, no needs footer verbs."""
    _set_env(monkeypatch, env)
    now = "2026-07-04T19:30:00Z"
    legacy = TS.build_digest(_ACTED, [], [], [], now=now)
    assert TS.build_digest(_ACTED, [], [], [], now=now,
                           needs_rows=None) == legacy
    assert TS.build_digest(_ACTED, [], [], [], now=now,
                           needs_rows=[]) == legacy
    assert "🙋" not in legacy
    assert "grant NEED-" not in legacy
    # all-empty digest still costs nothing
    assert TS.build_digest([], [], [], [], now=now, needs_rows=None) == \
        TS.build_digest([], [], [], [], now=now) == ""


# ---------------------------------------------------------------------------
# Caps — posture=None keeps today's exact verdicts (SOV-5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("env", _ENV_STATES)
def test_cap_check_guardian_bytes(monkeypatch, env):
    _set_env(monkeypatch, env)
    caps = {"per_kind": 2, "estate": 5}
    store = {}

    def get(key):
        return store.get(key, "")

    # under cap: ok in every variant
    for kw in ({}, {"posture": None}, {"posture": "guardian"}):
        res = AC.cap_check("monday_task_create", redis_get=get, caps=caps,
                           now="2026-07-04T10:00:00Z", **kw)
        assert res["ok"] is True and "alarm" not in res
    # at cap: blocked, same reason, in every guardian variant
    store[AC.count_key("2026-07-04", "monday_task_create")] = "2"
    baseline = AC.cap_check("monday_task_create", redis_get=get, caps=caps,
                            now="2026-07-04T10:00:00Z")
    assert baseline["ok"] is False and baseline["reason"] == "per-kind cap reached"
    for kw in ({"posture": None}, {"posture": "guardian"}):
        assert AC.cap_check("monday_task_create", redis_get=get, caps=caps,
                            now="2026-07-04T10:00:00Z", **kw) == baseline
    # unreadable counter: fail-closed in EVERY posture (incl. sovereign)
    def boom(key):
        raise RuntimeError("redis down")
    for posture in (None, "guardian", "sovereign"):
        res = AC.cap_check("monday_task_create", redis_get=boom, caps=caps,
                           now="2026-07-04T10:00:00Z", posture=posture)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# Binder — needs verbs DARK by default; pre-needs replies untouched
# ---------------------------------------------------------------------------

def test_needs_verbs_dark_without_flag(monkeypatch):
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    assert BW._needs_wired() is False
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "0")
    assert BW._needs_wired() is False
    monkeypatch.setenv("CABINET_NEEDS_WIRED", "1")
    assert BW._needs_wired() is True


def test_needs_grammar_collision_free_with_existing_verbs():
    """The FI-4 verb grammar must NEVER swallow the pre-needs verb corpus —
    approve/confirm/undo/never/lift and free-text with 'grant' mid-sentence
    all fall through (match is None)."""
    for text in (
        "approve", "approve 2", "undo 1", "undo [2]", "never board_status",
        "lift veto-1a2b", "ok", "looks good — grant them access tomorrow",
        "grant", "grant NEED-XYZ12345",     # non-hex id: not the needs verb
        "grant need", "deny",               # bare verbs without an id
        "regrant NEED-1a2b3c4d",            # prefixed word — anchor holds
    ):
        assert BW._NEED_RE.match(text) is None, text
    for text, verb in (
        ("grant NEED-1a2b3c4d", "grant"),
        ("deny need-deadbeef: too wide", "deny"),
        ("later NEED_0badf00d", "later"),
        ("snooze need 1a2b3c4d", "snooze"),
    ):
        m = BW._NEED_RE.match(text)
        assert m and m.group(1) == verb, text


# ---------------------------------------------------------------------------
# Attention mapping — default card_to_item bytes untouched (SOV-6 param dark)
# ---------------------------------------------------------------------------

def test_attention_mapping_default_identical(monkeypatch):
    from framework.frontdoor import attention_drain as AD
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    card = {
        "source": "polads", "urgency": "blocking", "ts": "2026-07-04T10:00:00Z",
        "summary": "standing grant approval needed — NEED-1a2b3c4d",
        "body": "requires captain approval",
    }
    legacy = AD.card_to_item(dict(card), project="polads")
    explicit = AD.card_to_item(dict(card), project="polads", needs_wired=False)
    assert explicit == legacy
    # unwired: NEED-tagged + ask-shaped card keeps its carded urgency tier
    # and carries no need_id payload — mapped exactly as before.
    assert legacy["urgency_tier"] == AD._URGENCY_TO_TIER["blocking"]
    assert "need_id" not in legacy["payload"]
    # wired: the same ping-now ask demotes to batch (the digest owns the ask)
    demoted = AD.card_to_item(dict(card), project="polads", needs_wired=True)
    assert demoted["urgency_tier"] == "batch"


# ---------------------------------------------------------------------------
# Env polarity spot-proof at the kernel (the A/A anchor for this suite)
# ---------------------------------------------------------------------------

def test_env_sovereign_never_widens_resolution(monkeypatch, _isolated_root):
    monkeypatch.setenv("CABINET_POSTURE", "sovereign")
    assert P.resolve_posture(root=_isolated_root) == "guardian"
    monkeypatch.setenv("CABINET_POSTURE", "guardian")
    assert P.resolve_posture(root=_isolated_root) == "guardian"
