"""Domain-local schema registry for envelope v2 (COG-1 §4.4).

Resolves domain payload-schema shapes from per-domain JSON files at
framework/schemas/domains/<domain>/<name>.v<version>.json — the registry that
absorbs new event vocabulary so the CENTRAL enum stops growing: it CANNOT
extend framework/events/emitter.py's VALID_EVENT_TYPES (M4 mechanical proof —
census enums stay 91/91, 30/30; the suite pins disjointness). Plan:
docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §4.4, per the
2026-07-07 full-autonomy grant.

LOOKUP-ONLY BY DESIGN: no runtime registration, no mutation, no cache (every
resolve re-reads the file — tiny files, relay-cadence call rate; no staleness
class exists). Registering a schema = committing a JSON file under version
control, reviewed like any code.

PATH HYGIENE: domain/name are validated against anchored allowlist regexes
and version against a bounded positive-int rule BEFORE any path is built —
traversal is impossible by construction; a resolved-path root-confinement
belt guards the symlink case.

STRUCTURAL vs SEMANTIC (the Phase-0 split, framework/evolution/contracts.py
precedent): structural = payload shape vs the resolved schema, judged by the
closed-subset stdlib interpreter below (jsonschema Draft 2020-12 reference
cross-check lives in the suite; jsonschema IS in the CI pip line); semantic =
id/resolution discipline (malformed id, unregistered schema, broken file).
A registered schema using any keyword OUTSIDE the closed subset is refused
at resolve time (fail-loud — silent partial validation would diverge from
the reference engine).

Names-not-values: issue messages carry key names, type names, lengths and
bounds — never payload values; echoed unknown-key names are truncated.

Pure stdlib. No I/O at import time.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

SCHEMAS_ROOT = Path(__file__).resolve().parents[1] / "schemas" / "domains"

# Annotation key carrying the closed list of domain event types a payload
# schema serves (e.g. ["tasks.status_changed"]). x- prefixed: the reference
# engine treats it as an ignored annotation, so the CI cross-check is clean.
EVENT_TYPES_KEY = "x-cabinet-event-types"

_SEGMENT_RE = re.compile(r"\A[a-z][a-z0-9_-]{0,63}\Z")
_VERSION_MAX = 9999
_SCHEMA_ID_RE = re.compile(
    r"\A(?P<domain>[a-z][a-z0-9_-]{0,63})/(?P<name>[a-z][a-z0-9_-]{0,63})"
    r"@(?P<version>[1-9][0-9]{0,3})\Z")
_EVENT_TYPE_RE = re.compile(r"\A[a-z][a-z0-9_-]{0,63}\.[a-z][a-z0-9_]{0,63}\Z")
_FILENAME_RE = re.compile(
    r"\A(?P<name>[a-z][a-z0-9_-]{0,63})\.v(?P<version>[1-9][0-9]{0,3})\.json\Z")

MAX_SCHEMA_BYTES = 65536      # a registered schema file larger than this is broken

# The CLOSED keyword subset the interpreter covers. Anything else in a
# registered schema → SchemaFileError at resolve (fail-loud, never partial).
_ANNOTATION_KEYWORDS = frozenset({"$schema", "title", "description",
                                  EVENT_TYPES_KEY})
_VALIDATION_KEYWORDS = frozenset({"type", "enum", "const", "required",
                                  "properties", "additionalProperties",
                                  "minLength", "maxLength",
                                  "minimum", "maximum"})
_SUPPORTED_KEYWORDS = _ANNOTATION_KEYWORDS | _VALIDATION_KEYWORDS
_JSON_TYPES = frozenset({"object", "array", "string", "integer", "number",
                         "boolean", "null"})


class SchemaRegistryError(Exception):
    """Base for every registry failure."""


class SchemaIdError(SchemaRegistryError, ValueError):
    """Malformed domain/name/version or schema id (semantic class)."""


class SchemaNotFound(SchemaRegistryError, LookupError):
    """Well-formed id with no registered schema file (semantic class)."""


class SchemaFileError(SchemaRegistryError, ValueError):
    """Registered file exists but is unreadable, non-object, oversized, or
    uses keywords outside the closed subset (semantic class — fail-loud)."""


@dataclass(frozen=True, order=True)
class SchemaIssue:
    kind: str      # "structural" | "semantic"
    code: str
    path: str
    message: str


# --------------------------------------------------------------------------
# id discipline
# --------------------------------------------------------------------------

def _check_segment(value: Any, what: str) -> str:
    if not isinstance(value, str) or not _SEGMENT_RE.match(value):
        raise SchemaIdError(f"{what}: not a valid registry id segment "
                            f"(lowercase [a-z][a-z0-9_-]{{0,63}})")
    return value


def _check_version(version: Any) -> int:
    if isinstance(version, bool) or not isinstance(version, int) \
            or not 1 <= version <= _VERSION_MAX:
        raise SchemaIdError(f"version: expected int in [1, {_VERSION_MAX}]")
    return version


def parse_schema_id(schema_id: Any) -> tuple[str, str, int]:
    """'tasks/task-event@1' → ('tasks', 'task-event', 1); SchemaIdError on
    anything else (names-not-values: the malformed id is never echoed)."""
    if not isinstance(schema_id, str):
        raise SchemaIdError("schema id: expected str")
    m = _SCHEMA_ID_RE.match(schema_id)
    if m is None:
        raise SchemaIdError("schema id: not <domain>/<name>@<version> shaped")
    return m.group("domain"), m.group("name"), int(m.group("version"))


def format_schema_id(domain: str, name: str, version: int) -> str:
    return (f"{_check_segment(domain, 'domain')}/"
            f"{_check_segment(name, 'name')}@{_check_version(version)}")


# --------------------------------------------------------------------------
# resolve (lookup-only; fail-loud on broken registrations)
# --------------------------------------------------------------------------

def _assert_supported(schema: Any, path: str = "$") -> None:
    """Refuse any schema outside the closed keyword subset (fail-loud)."""
    if not isinstance(schema, dict):
        raise SchemaFileError(f"{path}: schema node must be an object")
    for key, val in schema.items():
        if key not in _SUPPORTED_KEYWORDS:
            raise SchemaFileError(
                f"{path}: unsupported schema keyword {str(key)[:64]!r} "
                f"(closed subset: {sorted(_VALIDATION_KEYWORDS)})")
        if key == "type":
            types = val if isinstance(val, list) else [val]
            if not types or not all(t in _JSON_TYPES for t in types):
                raise SchemaFileError(f"{path}.type: unknown JSON type name")
        elif key == "required":
            if not isinstance(val, list) or not all(isinstance(r, str) for r in val):
                raise SchemaFileError(f"{path}.required: must be a list of key names")
        elif key == "additionalProperties":
            if not isinstance(val, bool):
                raise SchemaFileError(
                    f"{path}.additionalProperties: only boolean supported")
        elif key in ("minLength", "maxLength"):
            if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                raise SchemaFileError(f"{path}.{key}: must be a non-negative int")
        elif key in ("minimum", "maximum"):
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise SchemaFileError(f"{path}.{key}: must be a number")
        elif key == "properties":
            if not isinstance(val, dict):
                raise SchemaFileError(f"{path}.properties: must be an object")
            for sub_key, sub_schema in val.items():
                _assert_supported(sub_schema, f"{path}.{str(sub_key)[:24]}")
        elif key == "enum":
            if not isinstance(val, list) or not val:
                raise SchemaFileError(f"{path}.enum: must be a non-empty list")


def _check_declared_event_types(schema: dict, domain: str) -> None:
    declared = schema.get(EVENT_TYPES_KEY)
    if declared is None:
        return
    if not isinstance(declared, list):
        raise SchemaFileError(f"{EVENT_TYPES_KEY}: must be a list")
    for entry in declared:
        if not isinstance(entry, str) or not _EVENT_TYPE_RE.match(entry) \
                or not entry.startswith(domain + "."):
            raise SchemaFileError(
                f"{EVENT_TYPES_KEY}: entries must be <domain>.<name> event "
                f"types inside this schema's own domain")


def resolve(domain: Any, name: Any, version: Any, *,
            root: Optional[Path] = None) -> dict:
    """Resolve one domain payload schema → the parsed schema dict.

    Raises SchemaIdError (malformed inputs — checked BEFORE any filesystem
    access), SchemaNotFound (no such registration), SchemaFileError (broken
    or out-of-subset registration). Every call re-reads the file: the
    returned dict is a fresh object — caller mutation cannot poison the
    registry (no cache by design; see module docstring)."""
    domain = _check_segment(domain, "domain")
    name = _check_segment(name, "name")
    version = _check_version(version)
    base = Path(root) if root is not None else SCHEMAS_ROOT
    path = base / domain / f"{name}.v{version}.json"
    try:  # root-confinement belt (symlink case; the regexes already forbid traversal)
        if not path.resolve().is_relative_to(base.resolve()):
            raise SchemaIdError("schema path resolves outside the schemas root")
    except OSError as e:
        raise SchemaFileError(f"schema path not resolvable: {type(e).__name__}")
    if not path.is_file():
        raise SchemaNotFound(
            f"no registered schema for {domain}/{name}@{version}")
    try:
        if path.stat().st_size > MAX_SCHEMA_BYTES:
            raise SchemaFileError(
                f"registered schema exceeds {MAX_SCHEMA_BYTES} bytes")
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SchemaFileError(f"registered schema unreadable: {type(e).__name__}")
    try:
        schema = json.loads(text)
    except ValueError:
        raise SchemaFileError("registered schema is not valid JSON")
    if not isinstance(schema, dict):
        raise SchemaFileError("registered schema must be a JSON object")
    _assert_supported(schema)
    _check_declared_event_types(schema, domain)
    return schema


def event_types_for(domain: str, name: str, version: int, *,
                    root: Optional[Path] = None) -> frozenset[str]:
    """The closed set of domain event types the resolved schema declares."""
    return frozenset(resolve(domain, name, version, root=root)
                     .get(EVENT_TYPES_KEY, []))


def event_type_known(event_type: Any, *, root: Optional[Path] = None) -> bool:
    """True iff some registered schema in the event type's domain declares
    it. NEVER raises — malformed/unknown answers False (lookup predicate)."""
    try:
        if not isinstance(event_type, str) or not _EVENT_TYPE_RE.match(event_type):
            return False
        domain = event_type.split(".", 1)[0]
        base = Path(root) if root is not None else SCHEMAS_ROOT
        domain_dir = base / domain
        if not domain_dir.is_dir():
            return False
        for entry in sorted(domain_dir.iterdir()):
            m = _FILENAME_RE.match(entry.name)
            if m is None:
                continue
            try:
                schema = resolve(domain, m.group("name"),
                                 int(m.group("version")), root=base)
            except SchemaRegistryError:
                continue
            if event_type in schema.get(EVENT_TYPES_KEY, []):
                return True
        return False
    except Exception:
        return False


# --------------------------------------------------------------------------
# structural interpreter (closed Draft 2020-12 subset; reference cross-check
# lives in the suite — the Phase-0 pattern)
# --------------------------------------------------------------------------

def _json_type_matches(value: Any, expected: str) -> bool:
    # mirrors framework/evolution/contracts.py + the reference engine:
    # bool is NEVER integer/number; an integral float IS an integer
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        return isinstance(value, float) and value.is_integer()
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _equal(a: Any, b: Any) -> bool:
    """enum/const equality with the reference engine's bool/number rules."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def structural_issues(payload: Any, schema: dict,
                      path: str = "$") -> tuple[SchemaIssue, ...]:
    """Interpret the closed subset over one payload. Issues are STRUCTURAL
    class; messages never embed payload values (names/types/lengths only)."""
    issues: list[SchemaIssue] = []
    _collect(payload, schema, path, issues)
    return tuple(issues)


def _collect(value: Any, schema: dict, path: str,
             issues: list[SchemaIssue]) -> None:
    def add(validator: str, message: str, at: str = path) -> None:
        issues.append(SchemaIssue("structural", f"schema.{validator}", at, message))

    declared_type = schema.get("type")
    if declared_type is not None:
        allowed = declared_type if isinstance(declared_type, list) else [declared_type]
        if not any(_json_type_matches(value, t) for t in allowed):
            add("type", f"expected {'|'.join(allowed)}, got {type(value).__name__}")
            return  # deeper keywords are meaningless on the wrong type
    if "enum" in schema and not any(_equal(value, e) for e in schema["enum"]):
        add("enum", "not one of the permitted values")
    if "const" in schema and not _equal(value, schema["const"]):
        add("const", "not the pinned value")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            add("minLength", f"length {len(value)} below {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            add("maxLength", f"length {len(value)} exceeds {schema['maxLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            add("minimum", f"value below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            add("maximum", f"value exceeds maximum {schema['maximum']}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in value:
                add("required", f"missing required key: {req}", f"{path}.{req}")
        if schema.get("additionalProperties") is False:
            for key in sorted(str(k) for k in value if k not in props)[:8]:
                # key names only, truncated — payload keys are caller-shaped
                add("additionalProperties", "unknown key", f"{path}.{key[:24]}")
        for key, sub_schema in props.items():
            if key in value:
                _collect(value[key], sub_schema, f"{path}.{key}", issues)


def validate_payload(payload: Any, schema_id: Any, *,
                     root: Optional[Path] = None) -> tuple[SchemaIssue, ...]:
    """Resolve schema_id and judge payload against it. NEVER raises.

    Semantic issues (registry.bad_id / registry.not_found /
    registry.file_error) when the id does not resolve; structural issues
    from the interpreter otherwise; () when the payload conforms."""
    try:
        try:
            domain, name, version = parse_schema_id(schema_id)
        except SchemaIdError:
            return (SchemaIssue("semantic", "registry.bad_id", "$",
                                "schema id is not <domain>/<name>@<version> shaped"),)
        try:
            schema = resolve(domain, name, version, root=root)
        except SchemaNotFound:
            return (SchemaIssue("semantic", "registry.not_found", "$",
                                "schema id does not resolve in the domain registry"),)
        except SchemaRegistryError:
            return (SchemaIssue("semantic", "registry.file_error", "$",
                                "registered schema file is broken or out of subset"),)
        return structural_issues(payload, schema)
    except Exception as e:  # pragma: no cover — belt: never raises
        return (SchemaIssue("semantic", "registry.internal_error", "$",
                            f"registry internal error: {type(e).__name__}"),)
