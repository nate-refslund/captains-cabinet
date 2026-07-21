"""Red-team suite for the typed envelope v2 (COG-1 §4) — version dispatch,
per-field discipline, scope invariant, registry resolution, and wiring pins.

Structure cloned from test_envelope_redteam.py (seeded-LCG fuzz, per-class,
wiring pins) per the COG-1 plan §12.2 item 1
(docs/plans/cognitive-core-phase-1-contract-2026-07-20.md).

Classes covered:
  1. version dispatch — legacy_untyped / v1 (frozen validate()) / v2, decided
     BEFORE the v1 closed-set check (§4.1); classify_fields is four-way
  2. forged v2 fields (wrong types, closed key set, schema_version literal)
  3. id discipline (event_id/causation_id ULID; correlation_id uuid4-hex —
     B2.1 framework/probes/correlation.py; no third vocabulary)
  4. timestamp discipline (the single UTC-second spelling of Phase-0 §3.3;
     occurred_at ≤ recorded_at is DESCRIPTIVE, never validated — two clocks)
  5. scope invariant (cabinet|lane|project; conditional lane_id/project_id;
     missing levels ABSENT; sentinel ids refused — no inference, §4.2)
  6. classification-as-data (v1 taint-tier vocabulary; shape only, no law)
  7. payload xor payload_ref; payload_schema registry resolution; the
     central-enum vocabulary fence (event_type NEVER in VALID_EVENT_TYPES)
  8. v2 size bound — separate from v1's 16384 (§4.3, measured ×5 headroom)
  9. wiring pins — enforce()/report_only() knobs govern v2 identically;
     the v1 branch is BYTE-FROZEN (source pin) and the v1 suite untouched

Property-style cases use the same hand-rolled seeded LCG as the v1 suite
(hypothesis is NOT in the CI deps).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.triggers import envelope as E

# --------------------------------------------------------------------------
# helpers (cloned from the v1 suite; v2 fixture builder added)
# --------------------------------------------------------------------------

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_HEX = "0123456789abcdef"


class LCG:
    """Deterministic tiny PRNG (no hypothesis in CI deps — hand-rolled)."""

    def __init__(self, seed: int = 20260720):
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


def make_cid(rng: LCG | None = None, fill: str | None = None) -> str:
    """uuid4-hex shaped correlation id (32 lowercase hex — B2.1 standard)."""
    if fill is not None:
        return (fill * 32)[:32]
    rng = rng or LCG()
    return "".join(_HEX[rng.next() % 16] for _ in range(32))


def mk_payload(**over) -> dict:
    """A valid tasks/task-event@1 payload (framework/schemas/domains/tasks)."""
    p = {
        "task_id": 42,
        "old_status": "wip",
        "new_status": "done",
        "old_blocked": False,
        "new_blocked": False,
        "actor": "cos",
        "context_slug": "cog1-pilot",
    }
    p.update(over)
    return p


def mk2(scope_kind: str = "cabinet", **over) -> dict:
    """A valid v2 envelope (per-scope conditional levels honored, §4.2)."""
    env = {
        "schema_version": "cabinet-envelope/v2",
        "event_id": make_ulid(fill="0"),
        "event_type": "tasks.status_changed",
        "occurred_at": "2026-07-20T09:00:00Z",
        "recorded_at": "2026-07-20T09:00:05Z",
        "cabinet_id": "main",
        "scope_kind": scope_kind,
        "producer": "officer_tasks/outbox-relay",
        "correlation_id": make_cid(fill="c"),
        "idempotency_key": "task:42:9001:done:false",
        "classification": "system",
        "payload_schema": "tasks/task-event@1",
        "payload": mk_payload(),
    }
    if scope_kind == "lane":
        env["lane_id"] = "lane-a"
    elif scope_kind == "project":
        env["lane_id"] = "lane-a"
        env["project_id"] = "proj-b"
    env.update(over)
    return env


def assert_v2_rejected(payload, needle: str | None = None):
    ok, reasons = E.validate_v2(payload)
    assert ok is False, f"expected v2 rejection, got ok for: {payload!r}"
    assert reasons, "rejection must carry at least one reason"
    if needle is not None:
        joined = " | ".join(reasons)
        assert needle in joined, f"expected {needle!r} in reasons: {joined}"


def mk1(kind: str = "intent", **over) -> dict:
    """A valid v1 envelope (mirrors the v1 suite's mk())."""
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


# --------------------------------------------------------------------------
# baseline: valid v2 envelopes per scope kind
# --------------------------------------------------------------------------

@pytest.mark.parametrize("scope_kind", ["cabinet", "lane", "project"])
def test_valid_v2_envelope_per_scope(scope_kind):
    ok, reasons = E.validate_v2(mk2(scope_kind))
    assert ok is True, f"{scope_kind}: {reasons}"
    assert reasons == []


def test_valid_v2_with_causation_id():
    ok, reasons = E.validate_v2(mk2(causation_id=make_ulid(fill="7")))
    assert ok, reasons


def test_valid_v2_with_payload_ref_only():
    """payload_ref is validated-shape-reserved (§4.2): a ref-bearing envelope
    with NO inline payload is shape-valid; its schema must still resolve."""
    env = mk2()
    del env["payload"]
    env["payload_ref"] = "outbox:officer_tasks_outbox:42"
    ok, reasons = E.validate_v2(env)
    assert ok, reasons


# --------------------------------------------------------------------------
# class 1 — version dispatch (BEFORE the v1 closed set, §4.1)
# --------------------------------------------------------------------------

def test_classify_no_envelope_field_is_legacy_untyped():
    verdict, reasons = E.classify_fields({"sender": "x", "message": "y"})
    assert verdict == "legacy_untyped" and reasons == []


def test_classify_envelope_without_schema_version_routes_to_v1():
    verdict, reasons = E.classify_fields({"envelope": json.dumps(mk1())})
    assert verdict == "ok", reasons


def test_classify_envelope_with_schema_version_routes_to_v2():
    verdict, reasons = E.classify_fields({"envelope": json.dumps(mk2())})
    assert verdict == "ok", reasons


def test_classify_invalid_v2_is_invalid():
    bad = mk2(event_id="not-a-ulid")
    verdict, reasons = E.classify_fields({"envelope": json.dumps(bad)})
    assert verdict == "invalid" and reasons


def test_v2_cannot_ride_as_v1_plus_fields():
    """A v2-shaped envelope MISSING schema_version dispatches to the frozen
    v1 validate() and dies on its closed key set — the §4.1 rationale."""
    env = mk2()
    del env["schema_version"]
    verdict, reasons = E.classify_fields({"envelope": json.dumps(env)})
    assert verdict == "invalid"
    assert any("unknown keys" in r for r in reasons)


def test_v1_envelope_with_schema_version_key_routes_to_v2():
    """Presence of schema_version is THE dispatch key: a v1 body carrying it
    is judged by validate_v2 (and rejected — not a valid v2 field set)."""
    env = mk1(schema_version="cabinet-envelope/v2")
    verdict, reasons = E.classify_fields({"envelope": json.dumps(env)})
    assert verdict == "invalid"
    # v2-flavored reasons (v1 would have said "unknown keys: schema_version")
    assert not any("unknown keys: schema_version" in r for r in reasons)


def test_validate_any_dispatches_v1_and_v2():
    ok1, r1 = E.validate_any(mk1())
    ok2, r2 = E.validate_any(mk2())
    assert ok1 is True, r1
    assert ok2 is True, r2
    bad_v2 = mk2(scope_kind="galaxy")
    okb, rb = E.validate_any(bad_v2)
    assert okb is False and rb


def test_validate_any_non_dict_never_raises():
    for garbage in (None, 42, "envelope", [mk2()], (1, 2), object(), b"{}"):
        ok, reasons = E.validate_any(garbage)
        assert ok is False and reasons


def test_dispatch_wiring_mutant_v2_route(monkeypatch):
    """WIRING PIN: classify_fields must route schema_version-bearing
    envelopes THROUGH validate_v2 — an always-ok stand-in flips the verdict
    of an invalid v2 envelope (mutant negative control)."""
    bad = {"envelope": json.dumps(mk2(event_id="forged"))}
    assert E.classify_fields(bad)[0] == "invalid"
    monkeypatch.setattr(E, "validate_v2", lambda p: (True, []))
    assert E.classify_fields(bad)[0] == "ok"


def test_dispatch_wiring_v1_route_never_touches_v2(monkeypatch):
    """WIRING PIN: a schema_version-less envelope must NEVER reach
    validate_v2 — a booby-trapped validate_v2 proves the v1 route."""
    def boom(_payload):
        raise AssertionError("v1 route must not call validate_v2")
    monkeypatch.setattr(E, "validate_v2", boom)
    verdict, reasons = E.classify_fields({"envelope": json.dumps(mk1())})
    assert verdict == "ok", reasons


# --------------------------------------------------------------------------
# class 2 — forged v2 fields (types, closed set, schema_version literal)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("key,bad", [
    ("schema_version", 2),
    ("schema_version", None),
    ("event_id", 12345),
    ("event_id", None),
    ("event_id", ["not", "a", "ulid"]),
    ("event_type", 7),
    ("event_type", ""),
    ("event_type", None),
    ("occurred_at", 1721464800),
    ("occurred_at", None),
    ("recorded_at", {"ts": "2026-07-20T09:00:05Z"}),
    ("cabinet_id", 9),
    ("cabinet_id", ""),
    ("cabinet_id", "   "),
    ("scope_kind", ["cabinet"]),
    ("producer", 0),
    ("producer", ""),
    ("correlation_id", 99),
    ("correlation_id", None),
    ("idempotency_key", 1),
    ("idempotency_key", ""),
    ("classification", 3),
    ("classification", None),
    ("payload_schema", 5),
    ("payload_schema", None),
    ("payload", "not-an-object"),
])
def test_forged_v2_field_types_rejected(key, bad):
    assert_v2_rejected(mk2(**{key: bad}), needle=key)


@pytest.mark.parametrize("bad_version", [
    "cabinet-envelope/v1",
    "cabinet-envelope/v3",
    "CABINET-ENVELOPE/V2",
    "cabinet-envelope/v2 ",
    "v2",
    "",
])
def test_schema_version_literal_enforced(bad_version):
    assert_v2_rejected(mk2(schema_version=bad_version), needle="schema_version")


def test_unknown_v2_key_is_violation():
    # closed-set doctrine carries to v2: a smuggled side-channel key rejects
    assert_v2_rejected(mk2(smuggled="payload"), needle="unknown keys")


def test_v1_only_keys_are_unknown_in_v2():
    assert_v2_rejected(mk2(taint={"tier": "officer", "sources": ["x"]}),
                       needle="unknown keys")


@pytest.mark.parametrize("missing", [
    "schema_version", "event_id", "event_type", "occurred_at", "recorded_at",
    "cabinet_id", "scope_kind", "producer", "correlation_id",
    "idempotency_key", "classification", "payload_schema",
])
def test_each_required_v2_key_missing_rejected(missing):
    env = mk2()
    del env[missing]
    if missing == "schema_version":
        # without the dispatch key this is not a v2 envelope at all; the
        # direct validator still rejects it (missing literal)
        assert_v2_rejected(env, needle="schema_version")
    else:
        assert_v2_rejected(env, needle=missing)


def test_required_key_set_exported_and_exact():
    assert frozenset(E.V2_REQUIRED_KEYS) == frozenset({
        "schema_version", "event_id", "event_type", "occurred_at",
        "recorded_at", "cabinet_id", "scope_kind", "producer",
        "correlation_id", "idempotency_key", "classification",
        "payload_schema",
    })


def test_non_dict_v2_payloads_rejected_never_raise():
    for garbage in (None, 42, "envelope", [mk2()], (1, 2), object(), b"{}"):
        ok, reasons = E.validate_v2(garbage)
        assert ok is False and reasons


# --------------------------------------------------------------------------
# class 3 — id discipline (ULID / uuid4-hex; no third vocabulary, §4.2)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad_id", [
    "not-a-ulid",
    "0" * 25,                      # too short
    "0" * 27,                      # too long
    "a" * 26,                      # lowercase forgery (Crockford is uppercase)
    "I" * 26,                      # excluded Crockford letters
    "U" * 26,
    "0" * 26 + "\n",               # trailing-newline smuggle (\Z anchor pin)
    "0" * 13 + "\x00" + "0" * 12,  # embedded NUL
])
def test_event_id_ulid_shape_enforced(bad_id):
    assert_v2_rejected(mk2(event_id=bad_id), needle="event_id")


@pytest.mark.parametrize("bad_id", [
    "not-a-ulid",
    "0" * 25,
    "a" * 26,
    "0" * 26 + "\n",
])
def test_causation_id_ulid_shape_enforced(bad_id):
    assert_v2_rejected(mk2(causation_id=bad_id), needle="causation_id")


def test_causation_id_explicit_null_rejected():
    # absent means ABSENT — an explicit null is a type forgery, not absence
    assert_v2_rejected(mk2(causation_id=None), needle="causation_id")


@pytest.mark.parametrize("bad_cid", [
    "C" * 32,                      # uppercase hex forgery (B2.1 is lowercase)
    "c" * 31,                      # too short
    "c" * 33,                      # too long
    "g" * 32,                      # non-hex
    "c" * 32 + "\n",               # newline smuggle
    make_ulid(fill="0"),           # a ULID is NOT a correlation id (no third
                                   # vocabulary — id-discipline table §4.2)
])
def test_correlation_id_uuid4_hex_enforced(bad_cid):
    assert_v2_rejected(mk2(correlation_id=bad_cid), needle="correlation_id")


def test_correlation_id_matches_b21_standard():
    """The B2.1 module (framework/probes/correlation.py) is the single source
    of truth for the uuid4-hex format — v2 must agree with is_cid()."""
    from framework.probes.correlation import is_cid, mint
    cid = mint()
    assert is_cid(cid)
    assert E.validate_v2(mk2(correlation_id=cid))[0] is True
    assert is_cid("C" * 32) is False   # and the forgeries above agree too


def test_idempotency_key_bounds():
    assert E.validate_v2(mk2(idempotency_key="k" * 256))[0] is True
    assert_v2_rejected(mk2(idempotency_key="k" * 257), needle="idempotency_key")


def test_cabinet_id_bounds():
    assert E.validate_v2(mk2(cabinet_id="c" * 256))[0] is True
    assert_v2_rejected(mk2(cabinet_id="c" * 257), needle="cabinet_id")


# --------------------------------------------------------------------------
# class 4 — timestamp discipline (single UTC-second spelling, Phase-0 §3.3)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad_ts", [
    "2026-07-20T09:00:00.123Z",        # fractional seconds — one spelling only
    "2026-07-20T09:00:00+00:00",       # offset spelling
    "2026-07-20T09:00:00",             # missing Z
    "2026-07-20 09:00:00Z",            # space separator
    "2026-07-20T09:00Z",               # minute precision
    "2026-13-01T09:00:00Z",            # not a real month
    "2026-07-20T99:99:99Z",            # regex-shaped but not a real time
    "garbage",
    "",
    "2026-07-20T09:00:00Z\n",          # newline smuggle
])
@pytest.mark.parametrize("field", ["occurred_at", "recorded_at"])
def test_noncanonical_timestamps_rejected(field, bad_ts):
    assert_v2_rejected(mk2(**{field: bad_ts}), needle=field)


def test_clock_skew_never_quarantines():
    """occurred_at ≤ recorded_at is DESCRIPTIVE, not validated (§4.2): the
    two stamps come from two clocks (DB NOW() vs relay host) — ordinary skew
    must never reject a legitimate row."""
    ok, reasons = E.validate_v2(mk2(occurred_at="2026-07-20T09:00:10Z",
                                    recorded_at="2026-07-20T09:00:00Z"))
    assert ok is True, reasons


# --------------------------------------------------------------------------
# class 5 — scope invariant (no sentinels, missing levels absent, §4.2)
# --------------------------------------------------------------------------

def test_scope_kind_closed_set():
    for bad in ("galaxy", "Cabinet", "lane ", "", "org", None, 3):
        assert_v2_rejected(mk2(scope_kind=bad), needle="scope_kind")


def test_cabinet_scope_forbids_levels():
    assert_v2_rejected(mk2("cabinet", lane_id="lane-a"), needle="lane_id")
    assert_v2_rejected(mk2("cabinet", project_id="proj-b"), needle="project_id")


def test_lane_scope_requires_lane_id_forbids_project_id():
    env = mk2("lane")
    del env["lane_id"]
    assert_v2_rejected(env, needle="lane_id")
    assert_v2_rejected(mk2("lane", project_id="proj-b"), needle="project_id")


def test_project_scope_requires_both_levels():
    env = mk2("project")
    del env["project_id"]
    assert_v2_rejected(env, needle="project_id")
    env = mk2("project")
    del env["lane_id"]
    assert_v2_rejected(env, needle="lane_id")


def test_missing_level_is_absent_never_null():
    assert_v2_rejected(mk2("lane", lane_id=None), needle="lane_id")


@pytest.mark.parametrize("sentinel", sorted({"*", "default", "global",
                                             "none", "null", "unknown"}))
def test_sentinel_ids_refused_on_scope_fields(sentinel):
    assert_v2_rejected(mk2(cabinet_id=sentinel), needle="cabinet_id")
    assert_v2_rejected(mk2("lane", lane_id=sentinel), needle="lane_id")
    assert_v2_rejected(mk2("project", project_id=sentinel), needle="project_id")


def test_sentinel_vocabulary_matches_phase0():
    """One sentinel dialect: the v2 refusal set is exactly the Phase-0
    SENTINEL_IDS (framework/evolution/contracts.py) — no drift."""
    from framework.evolution.contracts import SENTINEL_IDS
    assert E.V2_SENTINEL_IDS == SENTINEL_IDS


# --------------------------------------------------------------------------
# class 6 — classification-as-data (v1 taint-tier vocabulary; no law, §4.2)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tier", E.TAINT_TIERS)
def test_every_v1_taint_tier_is_a_valid_classification(tier):
    ok, reasons = E.validate_v2(mk2(classification=tier))
    assert ok is True, reasons


@pytest.mark.parametrize("bad", [
    "root",                # invented tier
    "OFFICER",             # case forgery
    "officer ",            # whitespace smuggle
    "public",              # the trajectory-plane vocabulary is NOT this one
])
def test_classification_closed_set(bad):
    assert_v2_rejected(mk2(classification=bad), needle="classification")


# --------------------------------------------------------------------------
# class 7 — payload xor payload_ref; registry resolution; vocabulary fence
# --------------------------------------------------------------------------

def test_payload_and_payload_ref_both_present_rejected():
    assert_v2_rejected(mk2(payload_ref="outbox:row:1"), needle="payload")


def test_neither_payload_nor_payload_ref_rejected():
    env = mk2()
    del env["payload"]
    assert_v2_rejected(env, needle="payload")


@pytest.mark.parametrize("bad_ref", [7, "", "   ", "r" * 1025])
def test_payload_ref_shape_validated(bad_ref):
    env = mk2()
    del env["payload"]
    env["payload_ref"] = bad_ref
    assert_v2_rejected(env, needle="payload_ref")


@pytest.mark.parametrize("bad_schema", [
    "tasks/task-event",        # no version
    "tasks@1",                 # no name
    "task-event@1",            # no domain
    "tasks/task-event@0",      # version must be positive
    "tasks/task-event@01",     # no leading zero
    "TASKS/task-event@1",      # case forgery
    "tasks/../secrets@1",      # traversal shape
    "tasks/task-event@1\n",    # newline smuggle
])
def test_malformed_payload_schema_id_rejected(bad_schema):
    assert_v2_rejected(mk2(payload_schema=bad_schema), needle="payload_schema")


def test_unresolvable_payload_schema_rejected():
    # well-formed ids that resolve to nothing in the domain registry
    assert_v2_rejected(mk2(payload_schema="tasks/no-such-shape@1"),
                       needle="payload_schema")
    assert_v2_rejected(mk2(payload_schema="ghost/task-event@1"),
                       needle="payload_schema")
    assert_v2_rejected(mk2(payload_schema="tasks/task-event@99"),
                       needle="payload_schema")


def test_payload_validated_against_resolved_schema():
    # structurally broken payloads (vs tasks/task-event@1) are rejected
    assert_v2_rejected(mk2(payload=mk_payload(task_id="42")), needle="payload")
    assert_v2_rejected(mk2(payload={"actor": "cos"}), needle="payload")
    assert_v2_rejected(mk2(payload=mk_payload(smuggled="x")), needle="payload")
    assert_v2_rejected(mk2(payload=mk_payload(new_status="flying")),
                       needle="payload")


@pytest.mark.parametrize("bad_type", [
    "status_changed",          # not domain-namespaced
    "tasks.",                  # empty name
    ".status_changed",         # empty domain
    "tasks.Status_Changed",    # case forgery
    "tasks.status changed",    # whitespace
    "tasks.status_changed\n",  # newline smuggle
    "a.b.c",                   # one dot exactly
])
def test_event_type_format_enforced(bad_type):
    assert_v2_rejected(mk2(event_type=bad_type), needle="event_type")


def test_event_type_must_be_declared_by_resolved_schema():
    # well-formed, same domain, but tasks/task-event@1 does not declare it
    assert_v2_rejected(mk2(event_type="tasks.reticulated"),
                       needle="event_type")


def test_event_type_never_a_central_enum_member(monkeypatch):
    """The vocabulary fence (M4): an event_type that IS a member of the
    central VALID_EVENT_TYPES must be refused — domain vocabulary lives in
    the domain registry, never the central enum. No member is dot-shaped
    today, so the fence is proven by mutant: inject the pilot type into the
    cached central set and assert the otherwise-valid fixture now rejects."""
    from framework.events.emitter import VALID_EVENT_TYPES
    # any dot-shaped central member must be refused outright (none today —
    # this loop is the standing guard should one ever appear)
    for dotted in sorted(t for t in VALID_EVENT_TYPES if "." in t):
        assert_v2_rejected(mk2(event_type=dotted), needle="event_type")
    # mutant negative control: the fence must actually consult the enum
    assert E.validate_v2(mk2())[0] is True
    monkeypatch.setattr(E, "_CENTRAL_EVENT_TYPES",
                        frozenset(VALID_EVENT_TYPES) | {"tasks.status_changed"})
    assert_v2_rejected(mk2(), needle="event_type")


# --------------------------------------------------------------------------
# class 8 — v2 size bound (separate from v1, §4.3)
# --------------------------------------------------------------------------

def test_v2_bound_is_separate_and_pinned():
    assert E.MAX_V2_ENVELOPE_BYTES == 32768
    assert E.MAX_ENVELOPE_BYTES == 16384          # v1 bound untouched
    assert E.MAX_V2_ENVELOPE_BYTES != E.MAX_ENVELOPE_BYTES


def test_oversized_v2_envelope_rejected():
    env = mk2(payload=mk_payload(context_slug="x" * 40000))
    assert_v2_rejected(env, needle="bytes")


def test_measured_max_fixture_5x_headroom():
    """§4.3 sizing law: the provisional 32768 bound must hold ≥5x the largest
    valid fixture this suite ships (mirrors v1's 5x-over-live sizing)."""
    big = mk2(
        "project",
        producer="p" * 256,
        cabinet_id="c" * 256,
        idempotency_key="k" * 256,
        payload=mk_payload(blocked_reason="r" * 1024,
                           context_slug="s" * 256,
                           old_status="blocked",
                           new_status="blocked",
                           old_blocked=True,
                           new_blocked=True),
    )
    ok, reasons = E.validate_v2(big)
    assert ok is True, reasons
    assert E.envelope_bytes(big) * 5 <= E.MAX_V2_ENVELOPE_BYTES


# --------------------------------------------------------------------------
# property-style fuzz (seeded LCG — deterministic, cloned idiom)
# --------------------------------------------------------------------------

def test_property_v2_mutations_never_accepted_never_raise():
    rng = LCG(20260720)
    mutators = ("drop_required", "unknown_key", "type_swap", "bad_id_char",
                "bad_timestamp", "sentinel_level", "both_payloads",
                "bad_schema_version")
    swaps = (None, 0, 1.5, [], {}, True, b"x")
    droppable = tuple(E.V2_REQUIRED_KEYS) + ("payload",)
    for i in range(300):
        env = mk2(rng.choice(("cabinet", "lane", "project")))
        mut = rng.choice(mutators)
        if mut == "drop_required":
            del env[rng.choice(droppable)]
        elif mut == "unknown_key":
            env[f"x{rng.next() % 100}"] = "smuggled"
        elif mut == "type_swap":
            key = rng.choice(tuple(E.V2_REQUIRED_KEYS))
            env[key] = rng.choice(swaps)
        elif mut == "bad_id_char":
            eid = list(env["event_id"])
            eid[rng.next() % 26] = rng.choice("ilou!*")
            env["event_id"] = "".join(eid)
        elif mut == "bad_timestamp":
            env[rng.choice(("occurred_at", "recorded_at"))] = rng.choice((
                "2026-07-20T09:00:00.5Z", "2026-07-20", "now", ""))
        elif mut == "sentinel_level":
            env["scope_kind"] = "cabinet"
            env.pop("lane_id", None)
            env.pop("project_id", None)
            env["lane_id"] = rng.choice(sorted(E.V2_SENTINEL_IDS))
        elif mut == "both_payloads":
            env["payload_ref"] = "outbox:row:1"
        else:  # bad_schema_version
            env["schema_version"] = rng.choice(
                ("cabinet-envelope/v1", "cabinet-envelope/v3", "v2", ""))
        ok, reasons = E.validate_v2(env)   # must never raise
        assert ok is False, f"iteration {i}: mutated v2 accepted: {env!r}"
        assert reasons


def test_property_valid_v2_envelopes_always_pass():
    rng = LCG(42)
    for _ in range(100):
        scope = rng.choice(("cabinet", "lane", "project"))
        over = {
            "event_id": make_ulid(rng),
            "correlation_id": make_cid(rng),
            "classification": rng.choice(E.TAINT_TIERS),
        }
        if rng.next() % 2:
            over["causation_id"] = make_ulid(rng)
        env = mk2(scope, **over)
        if rng.next() % 4 == 0:
            del env["payload"]
            env["payload_ref"] = f"outbox:officer_tasks_outbox:{rng.next() % 10000}"
        ok, reasons = E.validate_v2(env)
        assert ok is True, reasons


# --------------------------------------------------------------------------
# names-not-values discipline (reasons never leak content)
# --------------------------------------------------------------------------

def test_reasons_never_embed_payload_content():
    canary = "SECRET_CANARY_VALUE_XYZ_apikey=sk-notreal"
    cases = [
        mk2(payload=mk_payload(actor=canary * 20)),          # over maxLength
        mk2(payload=mk_payload(new_status=canary)),          # enum violation
        mk2(cabinet_id=canary + "x" * 300),                  # over bound
        mk2(producer=canary + "y" * 300),
        mk2(payload={"task_id": 1, "new_status": "done",
                     "actor": "a", canary: 1}),              # unknown key name
    ]
    for env in cases:
        ok, reasons = E.validate_v2(env)
        assert ok is False
        joined = " | ".join(reasons)
        assert canary not in joined, f"content leaked into reasons: {joined}"


# --------------------------------------------------------------------------
# consumer-edge reuse pins (ReplayWindow doctrine, §3 disposition)
# --------------------------------------------------------------------------

def test_v2_event_id_keys_the_same_replay_window():
    """v2 event_id keys the SAME consumer-edge dedupe (reuse, not a new
    mechanism); producer-side replay blocking stays forbidden — validate_v2
    accepts the same event_id twice by design (at-least-once bus)."""
    env = mk2()
    assert E.validate_v2(env)[0] is True
    assert E.validate_v2(dict(env))[0] is True     # same id twice: accepted
    w = E.ReplayWindow(capacity=8)
    assert w.seen(env["event_id"]) is False
    assert w.seen(env["event_id"]) is True


# --------------------------------------------------------------------------
# wiring pins — enforce()/report_only() govern v2 via the same knobs (§4.1)
# --------------------------------------------------------------------------

def test_enforce_blocks_invalid_v2(monkeypatch):
    monkeypatch.delenv(E.ENFORCE_ENV, raising=False)
    bad = {"envelope": json.dumps(mk2(event_id="forged"))}
    blocked, verdict, reasons = E.enforce(bad)
    assert blocked is True and verdict == "invalid" and reasons


def test_enforce_passes_valid_v2(monkeypatch):
    monkeypatch.delenv(E.ENFORCE_ENV, raising=False)
    good = {"envelope": json.dumps(mk2())}
    blocked, verdict, reasons = E.enforce(good)
    assert blocked is False and verdict == "ok"


def test_enforce_warn_only_knob_covers_v2(monkeypatch):
    monkeypatch.setenv(E.ENFORCE_ENV, "0")
    bad = {"envelope": json.dumps(mk2(event_id="forged"))}
    blocked, verdict, reasons = E.enforce(bad)
    assert blocked is False and verdict == "invalid" and reasons


def test_report_only_logs_invalid_v2_not_valid(tmp_path):
    out = tmp_path / "violations.jsonl"
    E.report_only("test.v2ok", "cabinet:tasks:events",
                  {"envelope": json.dumps(mk2())}, path=out)
    assert not out.exists()                        # valid v2 writes nothing
    E.report_only("test.v2bad", "cabinet:tasks:events",
                  {"envelope": json.dumps(mk2(scope_kind="galaxy"))}, path=out)
    rec = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert rec["verdict"] == "invalid" and rec["reasons"]


def test_legacy_untyped_still_grandfathered(monkeypatch):
    monkeypatch.delenv(E.ENFORCE_ENV, raising=False)
    blocked, verdict, reasons = E.enforce({"sender": "x", "message": "y"})
    assert blocked is False and verdict == "legacy_untyped" and reasons == []


# --------------------------------------------------------------------------
# the v1-untouched regression pin (envelope.py:199-214 byte-frozen, §4.1)
# --------------------------------------------------------------------------

# Exact bytes of the v1 validate() head — signature, docstring, and the
# closed-set check — as they stood at the COG-1 ground pin. The plan freezes
# this region for the v1 branch; any drift is a contract violation, not a
# refactor.
_V1_FROZEN_REGION = (
    'def validate(payload: Any) -> tuple[bool, list[str]]:\n'
    '    """Validate a typed envelope. Returns (ok, reasons). NEVER raises.\n'
    '\n'
    '    STRICT closed-key semantics (FI-1 closed-set doctrine): any key outside\n'
    '    ENVELOPE_KEYS is a violation, as is any key outside TAINT_KEYS inside\n'
    '    taint. Reasons never embed free-text field values — key names, type\n'
    '    names, lengths, and closed-enum values (kind, tier) only.\n'
    '    """\n'
    '    reasons: list[str] = []\n'
    '    try:\n'
    '        if not isinstance(payload, dict):\n'
    '            return False, [f"envelope: expected dict, got {type(payload).__name__}"]\n'
    '\n'
    '        unknown = sorted(str(k) for k in set(payload) - ENVELOPE_KEYS)\n'
    '        if unknown:\n'
    '            reasons.append(f"unknown keys: {\', \'.join(unknown[:8])}")\n'
)


def test_v1_validate_region_byte_frozen():
    src = (Path(E.__file__)).read_text(encoding="utf-8")
    assert _V1_FROZEN_REGION in src, (
        "envelope.py v1 validate() head drifted — the COG-1 plan freezes "
        "the v1 branch byte-for-byte (§4.1)")


def test_v1_constants_and_keys_untouched():
    assert E.MAX_ENVELOPE_BYTES == 16384
    assert E.ENVELOPE_KEYS == frozenset(
        {"id", "from", "to", "kind", "provenance", "taint", "budget",
         "reply_to"})
    assert E.KINDS == ("intent", "evidence", "verdict", "need",
                       "grant_request", "heartbeat")
    assert E.TAINT_TIERS == ("captain", "officer", "system",
                             "cross_cabinet", "external")


def test_v1_suite_semantics_hold_through_dispatch():
    """Compat regression gate: v1 envelopes keep validating EXACTLY as before
    through every doorway (validate / validate_any / classify_fields)."""
    good = mk1("verdict")
    assert E.validate(good) == (True, [])
    assert E.validate_any(good) == (True, [])
    assert E.classify_fields({"envelope": json.dumps(good)}) == ("ok", [])
    bad = mk1(kind="not-a-kind")
    assert E.validate(bad)[0] is False
    assert E.validate_any(bad)[0] is False
    assert E.classify_fields({"envelope": json.dumps(bad)})[0] == "invalid"
