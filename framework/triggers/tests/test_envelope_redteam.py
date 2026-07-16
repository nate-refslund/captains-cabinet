"""Red-team suite for the typed envelope v1 (A6) — report-only wiring proofs.

Covers the five classes from the A12 row prose scoped to what exists after A6
(delivery-semantics integration cases against live Redis stay with the A12
enforcement wave):
  1. forged envelope fields (wrong types, spoofed provenance)
  2. replayed ids (consumer-side ReplayWindow — see replay-stance note below)
  3. oversized payloads (bound measured from live traffic, envelope.py docstring)
  4. taint-tier forgery (invalid tiers, sources/tier mismatch, worst-of claims)
  5. malformed kinds (the "kind-seven" rejection from the A6 gate_cmd)

Plus report-only WIRING contracts: legacy untyped entries pass through
byte-identical, violations are logged not dropped, the kill-knob works, and a
crashing validator never breaks the producer's XADD (fail-open by design).

REPLAY STANCE (decided from the A12 row prose): the row states the bus
delivery semantics as "at-least-once + idempotent consumers" — XREADGROUP
legitimately redelivers un-ACKed entries with the SAME envelope id, so a
stateless producer-side validator flagging a twice-seen id would flag correct
bus behavior. Replay detection is therefore a CONSUMER concern, keyed on
envelope id at the consumption edge; ReplayWindow is that helper and this
suite proves it flags the replay. validate() deliberately accepts the same id
twice (pinned by a test below).

Property-style cases use a hand-rolled seeded LCG — hypothesis is NOT in the
CI deps (.github/workflows/cabinet-ci.yml pip list), repo precedent is seeded
LCGs in the world scripts.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.triggers import envelope as E

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class LCG:
    """Deterministic tiny PRNG (no hypothesis in CI deps — hand-rolled)."""

    def __init__(self, seed: int = 20260711):
        self.x = seed

    def next(self) -> int:
        self.x = (1_103_515_245 * self.x + 12345) % (2 ** 31)
        return self.x

    def choice(self, seq):
        return seq[self.next() % len(seq)]


def make_ulid(rng: LCG | None = None, fill: str | None = None) -> str:
    if fill is not None:
        return (fill * 26)[:26]
    rng = rng or LCG()
    return "".join(_CROCKFORD[rng.next() % 32] for _ in range(26))


def mk(kind: str = "intent", **over) -> dict:
    """A valid v1 envelope of the given kind (per-kind rules honored)."""
    env = {
        "id": make_ulid(fill="0"),
        "from": "officer:cos",
        "to": "officer:cto",
        "kind": kind,
        "provenance": "officer:cos/test-producer",
        "taint": {"tier": "officer", "sources": ["officer:cos"]},
        "budget": 100,
    }
    if kind == "verdict":
        env["reply_to"] = make_ulid(fill="1")
    env.update(over)
    return env


def assert_rejected(payload, needle: str | None = None):
    ok, reasons = E.validate(payload)
    assert ok is False, f"expected rejection, got ok for: {payload!r}"
    assert reasons, "rejection must carry at least one reason"
    if needle is not None:
        joined = " | ".join(reasons)
        assert needle in joined, f"expected {needle!r} in reasons: {joined}"


# --------------------------------------------------------------------------
# baseline: every kind has a valid form
# --------------------------------------------------------------------------

@pytest.mark.parametrize("kind", E.KINDS)
def test_valid_envelope_per_kind(kind):
    ok, reasons = E.validate(mk(kind))
    assert ok is True, f"{kind}: {reasons}"
    assert reasons == []


def test_optional_reply_to_accepted_on_intent():
    ok, reasons = E.validate(mk("intent", reply_to=make_ulid(fill="2")))
    assert ok, reasons


# --------------------------------------------------------------------------
# class 1 — forged envelope fields (wrong types, spoofed provenance)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("key,bad", [
    ("id", 12345),
    ("id", None),
    ("id", ["not", "a", "ulid"]),
    ("from", 7),
    ("from", ""),
    ("from", "   "),
    ("to", {"role": "cto"}),
    ("to", b"cto"),
    ("kind", ["intent"]),
    ("provenance", 0),
    ("provenance", ""),
    ("taint", "officer"),
    ("taint", ["officer"]),
    ("budget", "100"),
    ("budget", 1.5),
    ("budget", None),
    ("reply_to", 99),
])
def test_forged_field_types_rejected(key, bad):
    assert_rejected(mk(**{key: bad}), needle=key)


def test_budget_bool_is_not_int():
    # bool subclasses int — a forged True budget must not slip the type gate
    assert_rejected(mk(budget=True), needle="budget")


@pytest.mark.parametrize("bad_id", [
    "not-a-ulid",
    "0" * 25,                      # too short
    "0" * 27,                      # too long
    "a" * 26,                      # lowercase forgery (Crockford is uppercase)
    "I" * 26,                      # excluded Crockford letters
    "U" * 26,
    "0" * 26 + "\n",               # trailing-newline smuggle: `$` matches
                                   # before a final \n, \Z does not
                                   # (ULID-NEWLINE-BYPASS review finding)
    "0" * 25 + "\n",               # newline as the 26th char
    "0" * 13 + "\x00" + "0" * 12,  # embedded control char (NUL) inside 26
])
def test_ulid_shape_enforced(bad_id):
    assert_rejected(mk(id=bad_id), needle="id")


def test_spoofed_provenance_oversized():
    assert_rejected(mk(provenance="x" * (E.MAX_PROVENANCE_CHARS + 1)),
                    needle="provenance")


def test_unknown_top_level_key_is_violation():
    # FI-1 closed-set doctrine: a smuggled side-channel key is a violation
    assert_rejected(mk(smuggled="payload"), needle="unknown keys")


@pytest.mark.parametrize("missing", E.REQUIRED_KEYS)
def test_each_required_key_missing_rejected(missing):
    env = mk("intent")
    del env[missing]
    assert_rejected(env, needle=missing)


def test_verdict_without_reply_to_rejected():
    env = mk("verdict")
    del env["reply_to"]
    assert_rejected(env, needle="reply_to")


def test_heartbeat_with_reply_to_rejected():
    assert_rejected(mk("heartbeat", reply_to=make_ulid(fill="3")),
                    needle="heartbeat")


def test_non_dict_payloads_rejected_never_raise():
    for garbage in (None, 42, "envelope", [mk()], (1, 2), object(), b"{}"):
        ok, reasons = E.validate(garbage)
        assert ok is False and reasons


# --------------------------------------------------------------------------
# class 2 — replayed ids (consumer concern; see module docstring)
# --------------------------------------------------------------------------

def test_validator_accepts_same_id_twice_by_design():
    """At-least-once bus: same-id redelivery is CORRECT behavior — the
    validator must not flag it (dedupe is the consumer's job, next test)."""
    env = mk("intent")
    assert E.validate(env)[0] is True
    assert E.validate(dict(env))[0] is True


def test_replay_window_flags_replayed_id():
    w = E.ReplayWindow(capacity=8)
    eid = make_ulid()
    assert w.seen(eid) is False        # first sight: consume
    assert w.seen(eid) is True         # replay: flagged
    assert w.seen(eid) is True         # still flagged


def test_replay_window_is_bounded():
    w = E.ReplayWindow(capacity=3)
    ids = [make_ulid(fill=c) for c in "ABCDE"]
    for i in ids:
        assert w.seen(i) is False
    # capacity 3: the two oldest were evicted — re-consuming them is
    # UNDETECTED by this window (documented bound, not a bug) …
    assert w.seen(ids[0]) is False
    # … while the newest survivors are still flagged
    assert w.seen(ids[-1]) is True


# --------------------------------------------------------------------------
# class 3 — oversized payloads (bound measured from live traffic)
# --------------------------------------------------------------------------

def test_oversized_envelope_rejected():
    assert_rejected(mk(provenance="p" * 900,
                       taint={"tier": "officer",
                              "sources": ["s" * 250] * 62}),
                    needle="bytes")


def test_oversized_via_many_max_fields():
    env = mk("intent")
    env["taint"] = {"tier": "officer", "sources": ["x" * 256] * 64}
    env["provenance"] = "y" * 1024
    if E.envelope_bytes(env) > E.MAX_ENVELOPE_BYTES:
        assert_rejected(env, needle="bytes")
    else:  # field caps hold it under the bound — then it must simply pass
        assert E.validate(env)[0] is True


def test_typical_live_sized_envelope_passes():
    # median live entry is ~861 bytes (measurement in envelope.py docstring)
    env = mk("need", provenance="officer:cos/status-sweep " + "d" * 400)
    assert E.envelope_bytes(env) < E.MAX_ENVELOPE_BYTES
    assert E.validate(env)[0] is True


def test_bound_matches_measurement_headroom():
    # bound must comfortably clear the observed live max (3259 bytes)
    assert E.MAX_ENVELOPE_BYTES >= 4 * 3259


# --------------------------------------------------------------------------
# class 4 — taint-tier forgery
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad_taint,needle", [
    ({"tier": "root", "sources": ["a"]}, "taint.tier"),          # invented tier
    ({"tier": "OFFICER", "sources": ["a"]}, "taint.tier"),       # case forgery
    ({"tier": 1, "sources": ["a"]}, "taint.tier"),
    ({"tier": "officer"}, "sources"),                            # missing sources
    ({"sources": ["a"]}, "tier"),                                # missing tier
    ({"tier": "officer", "sources": "a"}, "taint.sources"),      # not a list
    ({"tier": "officer", "sources": [1, 2]}, "taint.sources"),
    ({"tier": "officer", "sources": [""]}, "taint.sources"),
    ({"tier": "officer", "sources": ["a"], "laundered": True}, "unknown"),
    ({"tier": "officer", "sources": ["s"] * (E.MAX_SOURCES + 1)}, "taint.sources"),
])
def test_taint_shape_forgeries_rejected(bad_taint, needle):
    assert_rejected(mk(taint=bad_taint), needle=needle)


def test_evidence_with_empty_sources_rejected():
    assert_rejected(mk("evidence", taint={"tier": "officer", "sources": []}),
                    needle="evidence")


def test_taint_join_is_worst_of():
    assert E.taint_join(["captain", "external"]) == "external"
    assert E.taint_join(["officer", "system"]) == "system"
    assert E.taint_join(["captain"]) == "captain"
    # unknown source tier joins to WORST — never launders upward
    assert E.taint_join(["captain", "made-up-tier"]) == "external"
    assert E.taint_join([]) == "external"


def test_forged_join_claim_caught():
    # a forwarded envelope claiming a tier ABOVE worst-of its sources
    assert E.check_taint_join("officer", ["officer", "external"]) is False
    assert E.check_taint_join("external", ["officer", "external"]) is True
    assert E.check_taint_join("system", ["officer", "system"]) is True
    assert E.check_taint_join("not-a-tier", ["officer"]) is False


# --------------------------------------------------------------------------
# class 5 — malformed kinds ("kind-seven" rejection, A6 gate_cmd)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad_kind", [
    "command",              # invented seventh kind
    "division_proposal",    # the kind A12 exists to keep out until the gate
    "Intent",               # case forgery
    "intent ",              # whitespace smuggle
    "",
    "heartbeat\n",
])
def test_seventh_kind_rejected(bad_kind):
    env = mk("intent")
    env["kind"] = bad_kind
    assert_rejected(env, needle="kind")


def test_kind_missing_or_nonstring():
    env = mk("intent")
    del env["kind"]
    assert_rejected(env, needle="kind")
    assert_rejected(mk(kind=None), needle="kind")


# --------------------------------------------------------------------------
# property-style fuzz (seeded LCG — deterministic)
# --------------------------------------------------------------------------

def test_property_mutations_never_accepted_never_raise():
    rng = LCG(20260711)
    mutators = ("drop_required", "unknown_key", "type_swap", "bad_id_char")
    swaps = (None, 0, 1.5, [], {}, True, b"x")
    for i in range(300):
        env = mk(rng.choice(E.KINDS))
        mut = rng.choice(mutators)
        if mut == "drop_required":
            del env[rng.choice(E.REQUIRED_KEYS)]
        elif mut == "unknown_key":
            env[f"x{rng.next() % 100}"] = "smuggled"
        elif mut == "type_swap":
            key = rng.choice(E.REQUIRED_KEYS)
            env[key] = rng.choice(swaps)
        else:  # bad_id_char — lowercase or excluded letter inside the ulid
            eid = list(env["id"])
            eid[rng.next() % 26] = rng.choice("ilou!*")
            env["id"] = "".join(eid)
        ok, reasons = E.validate(env)   # must never raise
        assert ok is False, f"iteration {i}: mutated envelope accepted: {env!r}"
        assert reasons


def test_property_valid_envelopes_always_pass():
    rng = LCG(42)
    for _ in range(100):
        env = mk(rng.choice(E.KINDS),
                 id=make_ulid(rng),
                 budget=rng.next() % E.MAX_BUDGET)
        ok, reasons = E.validate(env)
        assert ok is True, reasons


# --------------------------------------------------------------------------
# report-only wiring contracts
# --------------------------------------------------------------------------

# Fixture shape read from the LIVE stream cabinet:triggers:cos via read-only
# `redis-cli XRANGE` on 2026-07-11: exactly two fields {sender, message},
# message prefixed "[<UTC ts>] From <sender>: <body>". All VALUES here are
# synthetic (the real entry's body referenced live services and the Captain
# by name — scrubbed per names-not-values).
LEGACY_FIXTURE = {
    "sender": "status-sweep-cron",
    "message": "[2026-07-11 09:00:00 UTC] From status-sweep-cron: STATUS "
               "SWEEP (synthetic fixture body): check services, officers, "
               "pending items; DM the chair a tight digest. Quiet-OK.",
}


def test_legacy_untyped_passes_through_byte_identical(tmp_path):
    out = tmp_path / "violations.jsonl"
    fields = dict(LEGACY_FIXTURE)
    before = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    E.report_only("test.legacy", "cabinet:triggers:cos-test", fields, path=out)
    after = json.dumps(fields, sort_keys=True, ensure_ascii=False)
    assert before == after, "report_only must NEVER mutate the outbound entry"
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["verdict"] == "legacy_untyped"      # grandfathered, counted
    assert rec["reasons"] == []
    assert sorted(rec["field_keys"]) == ["message", "sender"]


def test_violation_logged_not_dropped_and_no_content_leak(tmp_path):
    out = tmp_path / "violations.jsonl"
    canary = "SECRET_CANARY_VALUE_XYZ_apikey=sk-notreal"
    bad_env = mk(kind="not-a-kind", provenance="officer:cos/x")
    fields = {"envelope": json.dumps(bad_env), "content": canary,
              "sender": "test-producer"}
    E.report_only("test.invalid", "cabinet:inbox:testpeer", fields, path=out)
    text = out.read_text(encoding="utf-8")
    rec = json.loads(text.splitlines()[0])
    assert rec["verdict"] == "invalid"
    assert rec["reasons"], "violations must be logged with reasons, not dropped"
    # names-not-values: free-text content never reaches the violations file
    assert canary not in text
    assert "sender" in rec["field_keys"] and rec["safe_fields"]["sender"] == "test-producer"


def test_ok_typed_envelope_writes_nothing(tmp_path):
    out = tmp_path / "violations.jsonl"
    fields = {"envelope": json.dumps(mk("intent"))}
    E.report_only("test.ok", "cabinet:triggers:cos-test", fields, path=out)
    assert not out.exists()


def test_kill_knob_disables_reporting(tmp_path, monkeypatch):
    out = tmp_path / "violations.jsonl"
    monkeypatch.setenv(E.REPORT_ENV, "0")
    E.report_only("test.knob", "cabinet:triggers:cos-test",
                  dict(LEGACY_FIXTURE), path=out)
    assert not out.exists()
    monkeypatch.setenv(E.REPORT_ENV, "1")
    E.report_only("test.knob", "cabinet:triggers:cos-test",
                  dict(LEGACY_FIXTURE), path=out)
    assert out.exists()


def test_validator_crash_never_breaks_the_xadd(tmp_path, monkeypatch):
    """Fail-open by design: simulate the producer pattern (report beside the
    XADD) with a classifier that crashes — the XADD must still happen with
    byte-identical args and the crash lands in the REPORT_ERRORS counter."""
    def boom(_fields):
        raise RuntimeError("buggy validator")
    monkeypatch.setattr(E, "classify_fields", boom)
    errors_before = E.report_errors()

    xadds: list[list[str]] = []
    fields = dict(LEGACY_FIXTURE)

    def producer(f: dict) -> None:      # mirrors server.py: report BESIDE xadd
        E.report_only("test.crash", "cabinet:triggers:cos-test", f,
                      path=tmp_path / "v.jsonl")
        args = ["XADD", "cabinet:triggers:cos-test", "*"]
        for k, v in f.items():
            args += [k, v]
        xadds.append(args)

    producer(fields)                    # must not raise
    assert len(xadds) == 1
    assert xadds[0][3:] == ["sender", LEGACY_FIXTURE["sender"],
                            "message", LEGACY_FIXTURE["message"]]
    assert E.report_errors() == errors_before + 1
    assert not (tmp_path / "v.jsonl").exists()


def test_default_violations_path_is_runtime_interface():
    assert E.VIOLATIONS_PATH.name == "envelope-violations.jsonl"
    assert E.VIOLATIONS_PATH.parent.name == "interfaces"
    assert E.VIOLATIONS_PATH.parent.parent.name == "shared"


def test_size_cap_suppresses_appends_fail_open(tmp_path, monkeypatch):
    """Interim growth guard (VIOLATIONS-JSONL review finding): once the
    violations file reaches MAX_VIOLATIONS_BYTES, report_only() stops
    appending — silently, counted in REPORT_SUPPRESSED, never raising and
    never touching the caller's entry. Rotation proper is a follow-up."""
    out = tmp_path / "violations.jsonl"
    E.report_only("test.cap", "cabinet:triggers:cos-test",
                  dict(LEGACY_FIXTURE), path=out)
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1

    monkeypatch.setattr(E, "MAX_VIOLATIONS_BYTES", 1)   # file is now over cap
    suppressed_before = E.REPORT_SUPPRESSED
    fields = dict(LEGACY_FIXTURE)
    E.report_only("test.cap", "cabinet:triggers:cos-test", fields, path=out)
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1  # no growth
    assert E.REPORT_SUPPRESSED == suppressed_before + 1
    assert fields == LEGACY_FIXTURE            # entry untouched, no exception


def test_server_wiring_present_and_xadd_untouched():
    """Documents the server.py wiring: three report-only call sites exist and
    the XADD subprocess arg lists still carry the original field literals."""
    src = (Path(__file__).resolve().parents[3]
           / "cabinet" / "mcp-server" / "server.py").read_text(encoding="utf-8")
    assert src.count("def _envelope_report(") == 1
    assert src.count("# A6 report-only probe") == 3     # one per XADD site
    assert 'os.environ.get("CABINET_ENVELOPE_REPORT", "1") == "0"' in src
    # the three XADD targets are still built exactly as before
    assert src.count('"XADD", f"cabinet:triggers:{target_role}", "*",') == 1
    assert src.count('"XADD", f"cabinet:inbox:{to_cabinet}", "*",') == 2
