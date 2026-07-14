"""Enforcement suite for the typed envelope v1 — A12 "flip to block" (Captain
ruling 2026-07-14). Proves envelope.enforce() BLOCKS a malformed TYPED envelope
(the producer refuses the send) while the legacy/untyped grandfathered path and
every LEGIT valid envelope still pass. The false-positive / bus-breakage axis is
the highest risk of this flip, so valid + legacy pass-through is covered hard.

Companion to test_envelope_redteam.py (the A6 validate()/report-only proofs,
all still green). This file adds ONLY the enforcement axis; it never
re-litigates validate()'s rules.

Class map (A12 row prose, redteam docstring) and where enforcement bites:
  1 forged fields      -> validate() fail -> enforce() BLOCKS              (proved)
  2 replayed ids       -> NOT a validate() fail BY DESIGN (at-least-once bus;
                          dedupe is the CONSUMER's ReplayWindow). enforce() must
                          NOT block a valid replayed envelope at the producer —
                          blocking it would be new scope AND break redelivery.
                          Enforcement locus stays consumer-side.           (proved)
  3 oversized          -> validate() fail -> enforce() BLOCKS              (proved)
  4 taint-tier forgery -> validate() fail -> enforce() BLOCKS              (proved)
  5 malformed kind     -> validate() fail -> enforce() BLOCKS              (proved)

Server-site proof: the producer wiring in cabinet/mcp-server/server.py refuses
the send (no XADD) when the gate blocks, and issues exactly one XADD when it
does not — the "send refused, not sent" contract, exercised with the redis
subprocess spied (never touches a live bus).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from framework.triggers import envelope as E

_REPO_ROOT = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------
# helpers — 'legit' here means exactly what it means in the redteam suite
# --------------------------------------------------------------------------

def make_ulid(fill: str = "0") -> str:
    return (fill * 26)[:26]


def mk(kind: str = "intent", **over) -> dict:
    """A valid v1 envelope of the given kind (per-kind rules honored)."""
    env = {
        "id": make_ulid("0"),
        "from": "officer:cos",
        "to": "officer:cto",
        "kind": kind,
        "provenance": "officer:cos/test-producer",
        "taint": {"tier": "officer", "sources": ["officer:cos"]},
        "budget": 100,
    }
    if kind == "verdict":
        env["reply_to"] = make_ulid("1")
    env.update(over)
    return env


def typed(env: dict, **extra) -> dict:
    """Wrap an envelope dict as the flat XADD-fields form a producer sends: an
    'envelope' JSON field (+ any flat sibling fields)."""
    fields = {"envelope": json.dumps(env)}
    fields.update(extra)
    return fields


# The five red-team classes as TYPED-invalid envelopes (class 2 excluded — see
# the module docstring; replay is not a validate() failure).
REDTEAM_INVALID = {
    "class1_forged_field_type":   mk(budget="100"),          # str where int required
    "class1_spoofed_id":          mk(id=12345),               # int where ulid str required
    "class1_missing_required":    {k: v for k, v in mk().items() if k != "from"},
    "class3_oversized":           mk(provenance="p" * 900,
                                      taint={"tier": "officer",
                                             "sources": ["s" * 250] * 62}),
    "class4_invented_tier":       mk(taint={"tier": "root", "sources": ["a"]}),
    "class4_sources_wrong_shape": mk(taint={"tier": "officer", "sources": "a"}),
    "class5_seventh_kind":        mk(kind="division_proposal"),
    "class5_kind_case_forgery":   mk(kind="Intent"),
}


# --------------------------------------------------------------------------
# the switch (greppable, reversible; default ENFORCED per the Captain ruling)
# --------------------------------------------------------------------------

def test_enforced_default_is_true():
    assert E.ENFORCED is True
    assert E.ENFORCE_ENV == "CABINET_ENVELOPE_ENFORCE"


def test_enforcement_enabled_default_and_knob(monkeypatch):
    monkeypatch.delenv(E.ENFORCE_ENV, raising=False)
    assert E.enforcement_enabled() is True          # default follows ENFORCED=True
    monkeypatch.setenv(E.ENFORCE_ENV, "0")
    assert E.enforcement_enabled() is False          # warn-only knob
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    assert E.enforcement_enabled() is True


# --------------------------------------------------------------------------
# classes 1,3,4,5 — a TYPED invalid envelope is BLOCKED (send refused)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("label,bad_env", sorted(REDTEAM_INVALID.items()))
def test_redteam_class_typed_envelope_blocked(label, bad_env, monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")           # ENFORCED
    blocked, verdict, reasons = E.enforce(typed(bad_env))
    assert blocked is True, f"{label}: expected BLOCK, got verdict={verdict}"
    assert verdict == "invalid"
    assert reasons, f"{label}: a block must carry the validate() reasons"


def test_class2_replay_not_producer_blocked_but_consumer_flags_it(monkeypatch):
    """A12 class 2 (replay): a VALID envelope replayed with the same id is NOT a
    validate() failure (at-least-once bus; pinned in the redteam suite), so the
    producer-side enforce() must NOT block it — that would break correct
    redelivery and add scope validate() deliberately excludes. Replay defense is
    the CONSUMER's ReplayWindow."""
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    env = mk("intent")
    assert E.enforce(typed(env)) == (False, "ok", [])
    assert E.enforce(typed(dict(env))) == (False, "ok", [])   # same id → still NOT blocked
    # the actual class-2 defense lives at the consumption edge:
    w = E.ReplayWindow(capacity=8)
    assert w.seen(env["id"]) is False                # first sight: consume
    assert w.seen(env["id"]) is True                 # replay: flagged (consumer skips)


def test_invalid_json_envelope_field_blocked(monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    blocked, verdict, _ = E.enforce({"envelope": "{not valid json"})
    assert blocked is True and verdict == "invalid"


def test_non_str_envelope_field_blocked(monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    blocked, verdict, _ = E.enforce({"envelope": {"id": "x"}})   # dict, not a JSON str
    assert blocked is True and verdict == "invalid"


# --------------------------------------------------------------------------
# false-positive / bus-breakage guard (highest-risk axis — covered hard)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("kind", E.KINDS)
def test_legit_valid_envelope_passes_every_kind(kind, monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    blocked, verdict, reasons = E.enforce(typed(mk(kind)))
    assert blocked is False, f"{kind}: legit envelope wrongly blocked ({reasons})"
    assert verdict == "ok" and reasons == []


def test_legit_valid_variants_pass(monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    variants = [
        mk("intent", reply_to=make_ulid("2")),                        # optional reply_to
        mk("verdict", reply_to=make_ulid("1")),                       # verdict needs reply_to
        mk("evidence", taint={"tier": "external", "sources": ["a", "b"]}),
        mk("heartbeat"),                                              # reply_to absent
        mk("need", provenance="officer:cos/status-sweep " + "d" * 400),  # ~live-sized
        mk("grant_request", budget=0),                               # min budget
        mk("intent", budget=E.MAX_BUDGET),                           # max budget
    ]
    for env in variants:
        blocked, verdict, reasons = E.enforce(typed(env))
        assert blocked is False and verdict == "ok", (env, reasons)


def test_legit_envelope_with_flat_siblings_passes(monkeypatch):
    # a producer may XADD an envelope alongside flat siblings; siblings do not
    # affect validate() (which judges only the parsed envelope)
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    assert E.enforce(typed(mk("intent"), sender="cos", ts="1700000000")) == (False, "ok", [])


@pytest.mark.parametrize("legacy", [
    {"sender": "status-sweep-cron", "message": "[..] STATUS SWEEP digest"},
    {"from_cabinet": "work", "from_agent": "cos", "content": "hi",
     "reply_to": "", "ts": "1"},                                   # site-1/2 shape
    {"from_cabinet": "work", "from_agent": "cos", "kind": "handoff_request",
     "context_slug": "x", "reason": "y", "ts": "1"},               # site-3 shape: 'kind'
                                                                   # sibling is NOT an envelope
    {},                                                            # empty
])
def test_legacy_untyped_never_blocked(legacy, monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")                         # ENFORCED and still allowed
    assert E.enforce(legacy) == (False, "legacy_untyped", [])


@pytest.mark.parametrize("garbage", [None, 42, 1.5, "envelope", [1, 2], (1,), object(), b"{}"])
def test_enforce_never_raises_on_garbage(garbage, monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    blocked, verdict, reasons = E.enforce(garbage)                 # must not raise
    assert blocked is False and verdict == "legacy_untyped" and reasons == []


# --------------------------------------------------------------------------
# warn-only mode (reversible switch): invalid typed is classified, NOT blocked
# --------------------------------------------------------------------------

def test_warn_only_mode_does_not_block(monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "0")                         # warn-only
    blocked, verdict, reasons = E.enforce(typed(mk(kind="division_proposal")))
    assert blocked is False                                        # NOT blocked
    assert verdict == "invalid" and reasons                        # but still flagged invalid


# --------------------------------------------------------------------------
# fail-safe direction: an unexpected error on a TYPED entry fails CLOSED (block)
# while legacy stays open, and never raises
# --------------------------------------------------------------------------

def _crash(_fields):
    raise RuntimeError("classifier exploded")


def test_failsafe_typed_classify_crash_blocks_under_enforced(monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    monkeypatch.setattr(E, "classify_fields", _crash)
    blocked, verdict, reasons = E.enforce(typed(mk("intent")))     # typed entry
    assert blocked is True and verdict == "invalid"                # FAIL-CLOSED
    assert reasons and "enforce internal error" in reasons[0]


def test_failsafe_typed_crash_still_allows_legacy(monkeypatch):
    # even with a crashing classifier, a legacy entry never reaches it (the
    # leading presence check) → the grandfathered bus stays open
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    monkeypatch.setattr(E, "classify_fields", _crash)
    assert E.enforce({"sender": "x"}) == (False, "legacy_untyped", [])


def test_failsafe_crash_does_not_block_in_warn_only(monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "0")                         # warn-only
    monkeypatch.setattr(E, "classify_fields", _crash)
    blocked, verdict, _ = E.enforce(typed(mk("intent")))
    assert blocked is False and verdict == "invalid"               # classified, not blocked


# --------------------------------------------------------------------------
# observability counter
# --------------------------------------------------------------------------

def test_enforce_blocked_counter_increments(monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    before = E.enforce_blocked()
    E.enforce(typed(mk(kind="not-a-kind")))                        # invalid → +1
    E.enforce(typed(mk("intent")))                                 # valid    → +0
    E.enforce({"sender": "x"})                                     # legacy   → +0
    assert E.enforce_blocked() == before + 1


# --------------------------------------------------------------------------
# producer-shaped proof: BLOCK ⇒ the XADD is never issued (send refused, not
# sent); PASS ⇒ exactly one XADD (mirrors server.py's "gate BEFORE the XADD")
# --------------------------------------------------------------------------

def _producer(fields) -> "tuple[dict, list]":
    """Mirror the server.py site: enforce() BEFORE the XADD; only XADD when not
    blocked. Records XADD argv into a list (never touches redis)."""
    xadds: list = []
    blocked, _verdict, reasons = E.enforce(fields)
    if blocked:
        return {"status": "refused", "reason": "envelope_invalid", "violations": reasons}, xadds
    flat: list = []
    for k, v in fields.items():
        flat += [k, v]
    xadds.append(["XADD", "cabinet:triggers:cos", "*", *flat])
    return {"status": "sent"}, xadds


@pytest.mark.parametrize("label,bad_env", sorted(REDTEAM_INVALID.items()))
def test_producer_refuses_send_for_each_invalid_class(label, bad_env, monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    result, xadds = _producer(typed(bad_env))
    assert result["status"] == "refused", f"{label}: {result}"
    assert xadds == [], f"{label}: XADD must NOT run for a blocked envelope"


def test_producer_sends_legit_envelope(monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    result, xadds = _producer(typed(mk("intent")))
    assert result["status"] == "sent" and len(xadds) == 1


def test_producer_sends_legacy_untyped(monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "1")
    result, xadds = _producer({"sender": "cron", "message": "digest"})
    assert result["status"] == "sent" and len(xadds) == 1


# --------------------------------------------------------------------------
# server-site wiring: block ⇒ refused + zero XADD; legacy ⇒ delivered + 1 XADD
# (drives the real cabinet/mcp-server/server.py producer with redis spied)
# --------------------------------------------------------------------------

def _load_server():
    """Load cabinet/mcp-server/server.py by path under a unique module name
    (avoids any bare-'server' name collision); stdlib-only + a lazy
    framework.triggers import, so exec is side-effect-free (server start is
    guarded by __main__)."""
    srv_path = _REPO_ROOT / "cabinet" / "mcp-server" / "server.py"
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    spec = importlib.util.spec_from_file_location("cabinet_mcp_server_undertest", srv_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _RunSpy:
    """Stand-in for subprocess.run: records calls, never touches Redis."""

    def __init__(self, stdout: str = "1700000000-0", stderr: str = "") -> None:
        self.calls: list = []
        self._stdout, self._stderr = stdout, stderr

    def run(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return types.SimpleNamespace(stdout=self._stdout, stderr=self._stderr, returncode=0)


def _wire_self_delivery(srv, monkeypatch, roster=("cos",)):
    spy = _RunSpy()
    monkeypatch.setattr(
        srv, "subprocess",
        types.SimpleNamespace(run=spy.run, TimeoutExpired=subprocess.TimeoutExpired),
    )
    monkeypatch.setattr(srv, "read_hired_agents", lambda: list(roster))
    monkeypatch.setenv("CABINET_ENVELOPE_REPORT", "0")   # keep the real census file untouched
    params = {
        "to_cabinet": srv.this_cabinet_id(),             # == self → self-delivery branch
        "from_agent": "peer-agent",
        "content": "hello from a peer",
        "to_role": "cos",
    }
    return spy, params


# The two server-site tests exec cabinet/mcp-server/server.py, which carries
# PRE-EXISTING PEP-604 unions (X | Y) needing Python 3.10+; CI pins 3.12
# (cabinet-ci.yml). Skip cleanly on an older system interpreter rather than
# erroring on the syntax of an unrelated file.
_NEEDS_PY310 = pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="server.py uses PEP-604 unions (3.10+); CI runs 3.12",
)


@_NEEDS_PY310
def test_server_site_blocks_invalid_typed_and_skips_xadd(monkeypatch):
    srv = _load_server()
    spy, params = _wire_self_delivery(srv, monkeypatch)
    # Force the gate to block (as it would for a malformed typed envelope). This
    # proves the SITE contract: block ⇒ refused ⇒ the XADD never runs.
    monkeypatch.setattr(
        srv, "_envelope_enforce",
        lambda site, stream, fields: (True, ["forged: kind not in closed set"]),
    )
    result = srv.tool_send_message(params)
    assert result.get("status") == "refused", result
    assert result.get("reason") == "envelope_invalid"
    assert result.get("violations") == ["forged: kind not in closed set"]
    assert spy.calls == [], "XADD must NOT run when enforcement blocks the send"


@_NEEDS_PY310
def test_server_site_allows_legacy_and_issues_xadd(monkeypatch):
    srv = _load_server()
    spy, params = _wire_self_delivery(srv, monkeypatch)
    monkeypatch.setenv("CABINET_ENVELOPE_ENFORCE", "1")  # ENFORCED
    # Real _envelope_enforce: the site's flat fields carry no 'envelope' key →
    # legacy_untyped → allowed → exactly one XADD (the false-positive guard at
    # the real producer, under enforcement ON).
    result = srv.tool_send_message(params)
    assert result.get("status") == "delivered" and result.get("to_role") == "cos", result
    assert len(spy.calls) == 1, f"expected exactly one XADD; got {spy.calls}"
    argv = spy.calls[0][0][0]
    assert "cabinet:triggers:cos" in argv
