"""Suite for the domain-local schema registry (COG-1 §4.4) — resolve/reject,
structural-vs-semantic classification, jsonschema cross-check, M4 pin.

The registry resolves domain payload schemas from per-domain JSON files at
framework/schemas/domains/<domain>/<name>.v<version>.json. It is LOOKUP-ONLY:
no runtime registration, no mutation, and it CANNOT extend the central
VALID_EVENT_TYPES enum — M4 is the mechanical proof (census stays 91/91).

Structural validation is the Phase-0 stdlib-interpreter pattern
(framework/evolution/contracts.py precedent) with a jsonschema reference
cross-check in CI (jsonschema IS in the CI pip line). Rejections classify
structural (payload shape vs schema) vs semantic (id/resolution discipline).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from jsonschema import Draft202012Validator
except ImportError:                                   # pragma: no cover
    Draft202012Validator = None

from framework.triggers import schema_registry as R

REPO_ROOT = Path(__file__).resolve().parents[3]
TASKS_SCHEMA_PATH = (REPO_ROOT / "framework" / "schemas" / "domains"
                     / "tasks" / "task-event.v1.json")


def good_payload(**over) -> dict:
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


# --------------------------------------------------------------------------
# resolve — the happy path
# --------------------------------------------------------------------------

def test_resolve_tasks_task_event_v1():
    schema = R.resolve("tasks", "task-event", 1)
    assert isinstance(schema, dict)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "task_id" in schema["required"]
    assert "actor" in schema["required"]


def test_schemas_root_is_the_pinned_layout():
    assert R.SCHEMAS_ROOT == REPO_ROOT / "framework" / "schemas" / "domains"
    assert TASKS_SCHEMA_PATH.is_file(), "tasks domain schema JSON must ship"


def test_parse_and_format_schema_id_roundtrip():
    assert R.parse_schema_id("tasks/task-event@1") == ("tasks", "task-event", 1)
    assert R.format_schema_id("tasks", "task-event", 1) == "tasks/task-event@1"


def test_event_types_for_tasks_schema():
    kinds = R.event_types_for("tasks", "task-event", 1)
    assert kinds == frozenset({"tasks.status_changed"})


def test_event_type_known():
    assert R.event_type_known("tasks.status_changed") is True
    assert R.event_type_known("tasks.reticulated") is False
    assert R.event_type_known("ghost.status_changed") is False
    # malformed inputs answer False, never raise
    for bad in ("", "TASKS.x", "tasks.", ".x", None, 7, "a.b.c", "../x.y"):
        assert R.event_type_known(bad) is False


# --------------------------------------------------------------------------
# resolve — rejections (unknown, malformed, traversal)
# --------------------------------------------------------------------------

def test_resolve_unknown_rejected():
    with pytest.raises(R.SchemaNotFound):
        R.resolve("tasks", "task-event", 2)          # no such version
    with pytest.raises(R.SchemaNotFound):
        R.resolve("tasks", "no-such-shape", 1)       # no such name
    with pytest.raises(R.SchemaNotFound):
        R.resolve("ghost", "task-event", 1)          # no such domain


@pytest.mark.parametrize("domain,name,version", [
    ("../tasks", "task-event", 1),      # traversal in domain
    ("tasks/..", "task-event", 1),
    ("tasks", "../task-event", 1),      # traversal in name
    ("tasks", "task-event/../x", 1),
    ("tasks", "task-event\n", 1),       # newline smuggle
    ("TASKS", "task-event", 1),         # case forgery
    ("", "task-event", 1),              # empty
    ("tasks", "", 1),
    ("tasks", "task-event", 0),         # version must be positive
    ("tasks", "task-event", -1),
    ("tasks", "task-event", "1"),       # version must be an int, not str
    ("tasks", "task-event", True),      # bool is not a version
    (7, "task-event", 1),               # non-str domain
    ("tasks", None, 1),                 # non-str name
    ("tasks", "task.event", 1),         # dot outside the id charset
])
def test_resolve_malformed_ids_rejected(domain, name, version):
    with pytest.raises(R.SchemaIdError):
        R.resolve(domain, name, version)


@pytest.mark.parametrize("bad_id", [
    "tasks/task-event",         # no version
    "tasks@1",                  # no name
    "task-event@1",             # no domain separator
    "tasks/task-event@0",       # zero version
    "tasks/task-event@01",      # leading zero
    "tasks/task-event@1x",      # trailing junk
    "tasks/task-event@1\n",     # newline smuggle
    "TASKS/task-event@1",       # case forgery
    "tasks//task-event@1",
    "a/b@10000",                # version cap (≤9999)
    "",
    None,
    42,
])
def test_parse_schema_id_rejects_malformed(bad_id):
    with pytest.raises(R.SchemaIdError):
        R.parse_schema_id(bad_id)


def test_traversal_cannot_escape_root(tmp_path):
    """Path hygiene: even with a file physically planted outside the schemas
    root, no accepted identifier can reach it — the id allowlist rejects
    every traversal spelling BEFORE any filesystem access."""
    root = tmp_path / "domains"
    (root / "d").mkdir(parents=True)
    outside = tmp_path / "evil.v1.json"
    outside.write_text(json.dumps({"type": "object"}), encoding="utf-8")
    for domain, name in (("..", "evil"), ("d", "../evil"),
                         ("d", "..\\evil"), ("../..", "evil")):
        with pytest.raises(R.SchemaIdError):
            R.resolve(domain, name, 1, root=root)


# --------------------------------------------------------------------------
# lookup-only (no runtime registration, no mutation)
# --------------------------------------------------------------------------

def test_registry_has_no_registration_surface():
    mutators = [n for n in dir(R) if not n.startswith("_") and callable(getattr(R, n))
                and n.startswith(("register", "add", "put", "write", "set",
                                  "create", "install", "update", "delete"))]
    assert mutators == [], f"registry must be lookup-only, found: {mutators}"


def test_resolve_returns_fresh_copies_mutation_cannot_poison():
    a = R.resolve("tasks", "task-event", 1)
    a["required"] = []                      # vandalize the returned dict
    a["additionalProperties"] = True
    b = R.resolve("tasks", "task-event", 1)
    assert b["additionalProperties"] is False
    assert "task_id" in b["required"], "a caller mutation leaked into the registry"


def test_m4_central_enum_untouched():
    """M4 mechanical proof: the registry absorbs domain vocabulary WITHOUT
    growing the central enum — census stays 91/91 (ground @cbf52e49; S0
    re-verified) and the domain's event types stay disjoint from it."""
    from framework.events.emitter import VALID_EVENT_TYPES
    before = frozenset(VALID_EVENT_TYPES)
    assert len(before) == 91
    R.resolve("tasks", "task-event", 1)
    R.event_type_known("tasks.status_changed")
    from framework.events.emitter import VALID_EVENT_TYPES as after
    assert after == before and len(after) == 91
    assert R.event_types_for("tasks", "task-event", 1).isdisjoint(after)


# --------------------------------------------------------------------------
# structural vs semantic classification
# --------------------------------------------------------------------------

def test_valid_payload_yields_no_issues():
    assert R.validate_payload(good_payload(), "tasks/task-event@1") == ()


@pytest.mark.parametrize("payload,needle", [
    (good_payload(task_id="42"), "task_id"),          # type
    (good_payload(task_id=True), "task_id"),          # bool is not integer
    (good_payload(task_id=0), "task_id"),             # minimum
    ({"actor": "cos"}, "task_id"),                    # missing required
    (good_payload(smuggled="x"), "smuggled"),         # closed shape
    (good_payload(new_status="flying"), "new_status"),  # enum
    (good_payload(blocked_reason="r" * 2000), "blocked_reason"),  # maxLength
    (good_payload(actor=""), "actor"),                # minLength
    ("not-an-object", "$"),                           # root type
])
def test_structural_rejections_classified_structural(payload, needle):
    issues = R.validate_payload(payload, "tasks/task-event@1")
    assert issues, f"expected structural issues for: {payload!r}"
    assert all(i.kind == "structural" for i in issues)
    assert any(needle in i.path or needle in i.code for i in issues), (
        f"expected {needle!r} in issue paths/codes: {issues}")


@pytest.mark.parametrize("schema_id", [
    "tasks/no-such-shape@1",     # well-formed, unregistered
    "ghost/task-event@1",
    "tasks/task-event@99",
    "tasks/task-event",          # malformed id
    "TASKS/task-event@1",
    "",
])
def test_resolution_rejections_classified_semantic(schema_id):
    issues = R.validate_payload(good_payload(), schema_id)
    assert issues
    assert all(i.kind == "semantic" for i in issues)


def test_validate_payload_never_raises():
    for garbage in (None, 42, [], object(), b"{}"):
        issues = R.validate_payload(garbage, "tasks/task-event@1")
        assert issues and all(i.kind == "structural" for i in issues)
    issues = R.validate_payload(good_payload(), None)
    assert issues and all(i.kind == "semantic" for i in issues)


def test_issue_messages_never_embed_values():
    canary = "SECRET_CANARY_VALUE_XYZ_apikey=sk-notreal"
    for payload in (good_payload(new_status=canary),
                    good_payload(actor=canary * 20),
                    good_payload(old_status=canary)):
        issues = R.validate_payload(payload, "tasks/task-event@1")
        assert issues
        joined = " | ".join(f"{i.code}{i.path}{i.message}" for i in issues)
        assert canary not in joined, f"value leaked into issues: {joined}"


# --------------------------------------------------------------------------
# registered-but-broken schema files (fail-loud, never silent)
# --------------------------------------------------------------------------

def _plant(root: Path, domain: str, name: str, version: int, text: str) -> None:
    d = root / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.v{version}.json").write_text(text, encoding="utf-8")


def test_broken_json_schema_file_fails_loud(tmp_path):
    _plant(tmp_path, "d", "broken", 1, "{not json")
    with pytest.raises(R.SchemaFileError):
        R.resolve("d", "broken", 1, root=tmp_path)


def test_non_object_schema_fails_loud(tmp_path):
    _plant(tmp_path, "d", "listy", 1, json.dumps(["not", "an", "object"]))
    with pytest.raises(R.SchemaFileError):
        R.resolve("d", "listy", 1, root=tmp_path)


def test_unsupported_keyword_fails_loud(tmp_path):
    """The stdlib interpreter covers a CLOSED keyword subset; a registered
    schema using anything outside it must be refused at resolve time —
    silent partial validation would diverge from the reference engine."""
    _plant(tmp_path, "d", "fancy", 1, json.dumps({
        "type": "object",
        "properties": {"x": {"type": "string", "pattern": "^a+$"}},
    }))
    with pytest.raises(R.SchemaFileError):
        R.resolve("d", "fancy", 1, root=tmp_path)


def test_root_override_resolves_planted_schema(tmp_path):
    _plant(tmp_path, "d", "mini", 1, json.dumps({
        "type": "object",
        "additionalProperties": False,
        "required": ["k"],
        "properties": {"k": {"type": "string"}},
        "x-cabinet-event-types": ["d.k_changed"],
    }))
    schema = R.resolve("d", "mini", 1, root=tmp_path)
    assert schema["required"] == ["k"]
    assert R.event_types_for("d", "mini", 1, root=tmp_path) == frozenset(
        {"d.k_changed"})


# --------------------------------------------------------------------------
# jsonschema reference cross-check (the Phase-0 precedent; CI has jsonschema)
# --------------------------------------------------------------------------

@pytest.mark.skipif(Draft202012Validator is None,
                    reason="reference jsonschema not installed")
def test_shipped_tasks_schema_is_valid_draft_2020_12():
    schema = json.loads(TASKS_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


@pytest.mark.skipif(Draft202012Validator is None,
                    reason="reference jsonschema not installed")
def test_stdlib_interpreter_agrees_with_reference_engine():
    """For every mutation class the suite exercises, the stdlib interpreter
    and the reference Draft 2020-12 engine must agree on validity — the
    cross-check that keeps the closed-subset interpreter honest."""
    schema = json.loads(TASKS_SCHEMA_PATH.read_text(encoding="utf-8"))
    reference = Draft202012Validator(schema)
    payloads = [
        good_payload(),
        good_payload(old_status=None),
        good_payload(old_status=""),
        good_payload(new_status="blocked", new_blocked=True,
                     blocked_reason="waiting on review"),
        {"task_id": 1, "new_status": "queue", "actor": "etl"},   # minimal
        good_payload(task_id="42"),
        good_payload(task_id=True),
        good_payload(task_id=0),
        good_payload(task_id=1.0),          # integral float IS an integer
        good_payload(task_id=1.5),
        {"actor": "cos"},
        good_payload(smuggled="x"),
        good_payload(new_status="flying"),
        good_payload(new_status=None),
        good_payload(blocked_reason="r" * 2000),
        good_payload(actor=""),
        good_payload(context_slug=None),
        good_payload(old_blocked=None),
        good_payload(old_blocked="no"),
        "not-an-object",
        [],
        None,
        {},
    ]
    for payload in payloads:
        mine = bool(R.structural_issues(payload, schema))
        theirs = bool(list(reference.iter_errors(payload)))
        assert mine == theirs, (
            f"interpreter/reference divergence on {payload!r}: "
            f"stdlib={mine} reference={theirs}")


@pytest.mark.skipif(Draft202012Validator is None,
                    reason="reference jsonschema not installed")
def test_cross_check_fuzz_agreement():
    """Seeded-LCG fuzz over single-field mutations: stdlib and reference
    verdicts must agree on every iteration (deterministic, no hypothesis)."""
    schema = json.loads(TASKS_SCHEMA_PATH.read_text(encoding="utf-8"))
    reference = Draft202012Validator(schema)
    x = 20260720
    def nxt():
        nonlocal x
        x = (1_103_515_245 * x + 12345) % (2 ** 31)
        return x
    keys = ("task_id", "old_status", "new_status", "old_blocked",
            "new_blocked", "blocked_reason", "actor", "context_slug")
    swaps = (None, 0, 1.5, [], {}, True, "z", "", "queue", 7, -3)
    for i in range(200):
        payload = good_payload()
        key = keys[nxt() % len(keys)]
        payload[key] = swaps[nxt() % len(swaps)]
        mine = bool(R.structural_issues(payload, schema))
        theirs = bool(list(reference.iter_errors(payload)))
        assert mine == theirs, (
            f"iteration {i}: divergence on {key}={payload[key]!r}: "
            f"stdlib={mine} reference={theirs}")
