#!/usr/bin/env python3.12
"""Strict parser and comparator for Cabinet Redis backup fingerprints.

Version 3 separates durable keys from expiring keys.  That lets a restore
prove every still-live value while honestly allowing a key to disappear only
after its recorded absolute deadline.  Version 2 remains readable for old
snapshots, but retains its deliberately exact (and therefore fail-closed)
comparison semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


V2_FORMAT = "redis-dump-content-expiry-v2"
V3_FORMAT = "redis-logical-content-expiry-v3"
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UINT = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_HEX = re.compile(r"(?:[0-9a-f]{2})*\Z")
_STREAM_ID = re.compile(rb"(?:0|[1-9][0-9]*)-(?:0|[1-9][0-9]*)\Z")
STREAM_REPAIR_FORMAT = "redis-stream-repair-v1"


class FingerprintError(ValueError):
    """The fingerprint is malformed or two fingerprints do not match."""


@dataclass(frozen=True)
class DatabaseV2:
    key_count: int
    digest: str


@dataclass(frozen=True)
class DatabaseV3:
    captured_at_ms: int
    durable_count: int
    durable_digest: str


@dataclass(frozen=True)
class VolatileKey:
    content_digest: str
    deadline_ms: int


@dataclass(frozen=True)
class Fingerprint:
    format: str
    databases: int
    db: dict[int, DatabaseV2 | DatabaseV3]
    volatile: dict[tuple[int, str], VolatileKey]


@dataclass(frozen=True, order=True)
class StreamConsumer:
    database: int
    key_hex: str
    group_hex: str
    consumer_hex: str


@dataclass(frozen=True, order=True)
class StreamPelEntry:
    database: int
    key_hex: str
    group_hex: str
    id_hex: str
    owner_hex: str
    delivery_count: int


@dataclass(frozen=True)
class StreamRepairManifest:
    databases: int
    consumers: frozenset[StreamConsumer]
    pel: dict[tuple[int, str, str, str], StreamPelEntry]


def _uint(value: str, *, field: str, maximum: int | None = None) -> int:
    if not _UINT.fullmatch(value):
        raise FingerprintError(f"invalid {field}: {value!r}")
    parsed = int(value)
    if maximum is not None and parsed > maximum:
        raise FingerprintError(f"{field} exceeds {maximum}: {parsed}")
    return parsed


def _sha1(value: str, *, field: str) -> str:
    if not _SHA1.fullmatch(value):
        raise FingerprintError(f"invalid {field}: {value!r}")
    return value


def _sha256(value: str, *, field: str) -> str:
    if not _SHA256.fullmatch(value):
        raise FingerprintError(f"invalid {field}: {value!r}")
    return value


def _hex(value: str, *, field: str) -> str:
    if not _HEX.fullmatch(value):
        raise FingerprintError(f"invalid lowercase even-length hex {field}")
    return value


def _decode_hex(value: str, *, field: str) -> bytes:
    _hex(value, field=field)
    try:
        return bytes.fromhex(value)
    except ValueError as exc:  # Defensive: the strict regex should make this unreachable.
        raise FingerprintError(f"invalid hex {field}") from exc


def parse_stream_repair(path: str | Path) -> StreamRepairManifest:
    """Parse the privacy-preserving Redis Streams recovery sidecar.

    Empty Redis identifiers are valid, so records deliberately use ``split(" ")``
    rather than whitespace splitting: an empty hex field remains an empty field.
    """

    source = Path(path)
    try:
        lines = source.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise FingerprintError(f"cannot read stream repair manifest: {exc}") from exc
    if len(lines) < 2:
        raise FingerprintError("stream repair manifest is missing its two-line header")
    if any(not line or "\t" in line or "\r" in line for line in lines):
        raise FingerprintError("blank lines, tabs, and carriage returns are forbidden")
    if lines[0] != f"FORMAT {STREAM_REPAIR_FORMAT}":
        raise FingerprintError(
            f"line 1 must be exactly 'FORMAT {STREAM_REPAIR_FORMAT}'"
        )
    database_parts = lines[1].split(" ")
    if len(database_parts) != 2 or database_parts[0] != "DATABASES":
        raise FingerprintError("line 2 must be exactly 'DATABASES <count>'")
    databases = _uint(database_parts[1], field="database count", maximum=1024)
    if databases == 0:
        raise FingerprintError("database count must be positive")

    consumers: set[StreamConsumer] = set()
    pel: dict[tuple[int, str, str, str], StreamPelEntry] = {}
    for line_number, raw in enumerate(lines[2:], start=3):
        parts = raw.split(" ")
        try:
            if len(parts) == 5 and parts[0] == "CONSUMER":
                database = _uint(parts[1], field="database id", maximum=1023)
                record = StreamConsumer(
                    database,
                    _hex(parts[2], field="stream key"),
                    _hex(parts[3], field="group name"),
                    _hex(parts[4], field="consumer name"),
                )
                if record in consumers:
                    raise FingerprintError("duplicate consumer record")
                consumers.add(record)
                continue
            if len(parts) == 7 and parts[0] == "PEL":
                database = _uint(parts[1], field="database id", maximum=1023)
                key_hex = _hex(parts[2], field="stream key")
                group_hex = _hex(parts[3], field="group name")
                id_hex = _hex(parts[4], field="PEL id")
                owner_hex = _hex(parts[5], field="PEL owner")
                stream_id = _decode_hex(id_hex, field="PEL id")
                if not _STREAM_ID.fullmatch(stream_id):
                    raise FingerprintError("PEL id does not decode to a canonical stream id")
                record = StreamPelEntry(
                    database,
                    key_hex,
                    group_hex,
                    id_hex,
                    owner_hex,
                    _uint(parts[6], field="PEL delivery count", maximum=2**63 - 1),
                )
                identity = (database, key_hex, group_hex, id_hex)
                if identity in pel:
                    raise FingerprintError("duplicate PEL record")
                pel[identity] = record
                continue
            raise FingerprintError("unknown or malformed stream repair record")
        except FingerprintError as exc:
            raise FingerprintError(f"line {line_number}: {exc}") from exc

    for record in consumers:
        if record.database >= databases:
            raise FingerprintError(
                f"consumer database id {record.database} exceeds configured count"
            )
    for record in pel.values():
        if record.database >= databases:
            raise FingerprintError(
                f"PEL database id {record.database} exceeds configured count"
            )
        owner = StreamConsumer(
            record.database,
            record.key_hex,
            record.group_hex,
            record.owner_hex,
        )
        if owner not in consumers:
            raise FingerprintError("PEL owner has no matching consumer record")
    return StreamRepairManifest(databases, frozenset(consumers), pel)


def compare_stream_repair(
    expected: StreamRepairManifest, actual: StreamRepairManifest
) -> None:
    if expected.databases != actual.databases:
        raise FingerprintError("Redis stream repair database counts differ")
    if expected.consumers != actual.consumers:
        raise FingerprintError("Redis stream consumer identities differ")
    if expected.pel != actual.pel:
        raise FingerprintError("Redis stream PEL state differs")


def diff_stream_repair(
    expected: StreamRepairManifest, actual: StreamRepairManifest
) -> list[str]:
    """Return a privacy-safe component attribution for a sidecar mismatch."""

    if expected.databases != actual.databases:
        raise FingerprintError("Redis stream repair database counts differ")

    components: set[tuple[int, str, str]] = set()

    def key_hash(key_hex: str) -> str:
        return hashlib.sha256(_decode_hex(key_hex, field="stream key")).hexdigest()

    expected_consumers: dict[tuple[int, str, str], set[str]] = {}
    actual_consumers: dict[tuple[int, str, str], set[str]] = {}
    for record in expected.consumers:
        expected_consumers.setdefault(
            (record.database, record.key_hex, record.group_hex), set()
        ).add(record.consumer_hex)
    for record in actual.consumers:
        actual_consumers.setdefault(
            (record.database, record.key_hex, record.group_hex), set()
        ).add(record.consumer_hex)
    for identity in expected_consumers.keys() | actual_consumers.keys():
        if expected_consumers.get(identity, set()) != actual_consumers.get(identity, set()):
            components.add((identity[0], "consumer_identity", key_hash(identity[1])))

    expected_ids = set(expected.pel)
    actual_ids = set(actual.pel)
    for identity in expected_ids ^ actual_ids:
        components.add((identity[0], "pel_identity", key_hash(identity[1])))
    for identity in expected_ids & actual_ids:
        before = expected.pel[identity]
        after = actual.pel[identity]
        if before.owner_hex != after.owner_hex:
            components.add((identity[0], "pel_owner", key_hash(identity[1])))
        if before.delivery_count != after.delivery_count:
            components.add((identity[0], "pel_delivery_count", key_hash(identity[1])))

    return [
        f"DB {database} TYPE stream COMPONENT {component} KEY_SHA256 {digest}"
        for database, component, digest in sorted(components)
    ]


_STREAM_REPAIR_CONSUMER_LUA = r'''
local function unhex(value)
  if string.len(value) % 2 ~= 0 or string.find(value, "[^0-9a-f]") then
    return redis.error_reply("invalid repair hex")
  end
  return (string.gsub(value, "..", function(pair)
    return string.char(tonumber(pair, 16))
  end))
end
local key, group, consumer = unhex(ARGV[1]), unhex(ARGV[2]), unhex(ARGV[3])
if type(key) ~= "string" or type(group) ~= "string" or type(consumer) ~= "string" then
  return redis.error_reply("invalid repair identifier")
end
local result = redis.call("XGROUP", "CREATECONSUMER", key, group, consumer)
if result ~= 0 and result ~= 1 then return redis.error_reply("consumer repair failed") end
return 1
'''.strip()

_STREAM_REPAIR_PEL_LUA = r'''
local function unhex(value)
  if string.len(value) % 2 ~= 0 or string.find(value, "[^0-9a-f]") then
    return redis.error_reply("invalid repair hex")
  end
  return (string.gsub(value, "..", function(pair)
    return string.char(tonumber(pair, 16))
  end))
end
local key, group, id, owner = unhex(ARGV[1]), unhex(ARGV[2]), unhex(ARGV[3]), unhex(ARGV[4])
if type(key) ~= "string" or type(group) ~= "string" or type(id) ~= "string" or type(owner) ~= "string" then
  return redis.error_reply("invalid repair identifier")
end
if not string.match(ARGV[5], "^%d+$") then return redis.error_reply("invalid retry count") end
local entries = redis.call("XRANGE", key, id, id)
if #entries == 0 then
  local pending = redis.call("XPENDING", key, group, id, id, 1)
  if #pending == 1
      and pending[1][1] == id
      and pending[1][2] == owner
      and pending[1][4] == tonumber(ARGV[5]) then
    return 1
  end
  return redis.error_reply("dangling PEL repair refused")
end
local claimed = redis.call(
  "XCLAIM", key, group, owner, 0, id, "JUSTID", "FORCE", "RETRYCOUNT", ARGV[5]
)
if #claimed ~= 1 or claimed[1] ~= id then return redis.error_reply("PEL repair failed") end
return 1
'''.strip()


def _run_repair_command(
    client: list[str], database: int, script: str, arguments: list[str], component: str
) -> None:
    key_sha256 = hashlib.sha256(
        _decode_hex(arguments[0], field="stream key")
    ).hexdigest()
    try:
        completed = subprocess.run(
            [*client, "-n", str(database), "--raw", "EVAL", script, "0", *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FingerprintError(
            f"Redis stream {component} repair command failed for DB {database} "
            f"KEY_SHA256 {key_sha256}"
        ) from exc
    # redis-cli can exit 0 while printing a server-side EVAL error; keep this
    # exact response check and the manifest parser fail-closed.
    if completed.returncode != 0 or completed.stdout.strip() != b"1":
        raise FingerprintError(
            f"Redis stream {component} repair was refused for DB {database} "
            f"KEY_SHA256 {key_sha256}"
        )


def apply_stream_repair(manifest: StreamRepairManifest, client: list[str]) -> None:
    if not client or any(not part for part in client):
        raise FingerprintError("Redis client command is missing or malformed")
    for record in sorted(manifest.consumers):
        _run_repair_command(
            client,
            record.database,
            _STREAM_REPAIR_CONSUMER_LUA,
            [record.key_hex, record.group_hex, record.consumer_hex],
            "consumer",
        )
    for record in sorted(manifest.pel.values()):
        _run_repair_command(
            client,
            record.database,
            _STREAM_REPAIR_PEL_LUA,
            [
                record.key_hex,
                record.group_hex,
                record.id_hex,
                record.owner_hex,
                str(record.delivery_count),
            ],
            "PEL",
        )


def parse(path: str | Path) -> Fingerprint:
    source = Path(path)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise FingerprintError(f"cannot read {source}: {exc}") from exc
    if len(lines) < 2:
        raise FingerprintError("fingerprint is missing its two-line header")
    if any(not line or line != line.strip() for line in lines):
        raise FingerprintError("blank lines or surrounding whitespace are forbidden")

    format_parts = lines[0].split(" ")
    database_parts = lines[1].split(" ")
    if len(format_parts) != 2 or format_parts[0] != "FORMAT":
        raise FingerprintError("line 1 must be exactly 'FORMAT <version>'")
    format_name = format_parts[1]
    if format_name not in {V2_FORMAT, V3_FORMAT}:
        raise FingerprintError(f"unsupported Redis fingerprint format: {format_name!r}")
    if len(database_parts) != 2 or database_parts[0] != "DATABASES":
        raise FingerprintError("line 2 must be exactly 'DATABASES <count>'")
    database_count = _uint(database_parts[1], field="database count", maximum=1024)
    if database_count == 0:
        raise FingerprintError("database count must be positive")

    db: dict[int, DatabaseV2 | DatabaseV3] = {}
    volatile: dict[tuple[int, str], VolatileKey] = {}
    for line_number, raw in enumerate(lines[2:], start=3):
        parts = raw.split(" ")
        try:
            if format_name == V2_FORMAT and parts[0] == "DB" and len(parts) == 3:
                db_number = _uint(parts[1], field="database id", maximum=1023)
                count_digest = parts[2].split(":")
                if len(count_digest) != 2:
                    raise FingerprintError("v2 DB record must contain count:digest")
                record: DatabaseV2 | DatabaseV3 = DatabaseV2(
                    _uint(count_digest[0], field="key count"),
                    _sha1(count_digest[1], field="database digest"),
                )
            elif format_name == V3_FORMAT and parts[0] == "DB" and len(parts) == 5:
                db_number = _uint(parts[1], field="database id", maximum=1023)
                record = DatabaseV3(
                    _uint(parts[2], field="capture time"),
                    _uint(parts[3], field="durable key count"),
                    _sha256(parts[4], field="durable digest"),
                )
            elif format_name == V2_FORMAT and parts[0] == "EXPIRY" and len(parts) == 4:
                db_number = _uint(parts[1], field="database id", maximum=1023)
                key_digest = _sha1(parts[2], field="key digest")
                key = (db_number, key_digest)
                if key in volatile:
                    raise FingerprintError(f"duplicate expiry record: {key}")
                volatile[key] = VolatileKey("", _uint(parts[3], field="deadline"))
                continue
            elif format_name == V3_FORMAT and parts[0] == "VOLATILE" and len(parts) == 5:
                db_number = _uint(parts[1], field="database id", maximum=1023)
                key_digest = _sha256(parts[2], field="key digest")
                key = (db_number, key_digest)
                if key in volatile:
                    raise FingerprintError(f"duplicate volatile record: {key}")
                volatile[key] = VolatileKey(
                    _sha256(parts[3], field="content digest"),
                    _uint(parts[4], field="deadline"),
                )
                continue
            else:
                raise FingerprintError(f"unknown or malformed {format_name} record")
        except FingerprintError as exc:
            raise FingerprintError(f"line {line_number}: {exc}") from exc

        if db_number >= database_count:
            raise FingerprintError(
                f"line {line_number}: database id {db_number} exceeds configured count"
            )
        if db_number in db:
            raise FingerprintError(f"line {line_number}: duplicate DB record: {db_number}")
        db[db_number] = record

    expected_db = set(range(database_count))
    if set(db) != expected_db:
        missing = sorted(expected_db - set(db))
        extra = sorted(set(db) - expected_db)
        raise FingerprintError(f"DB record set is incomplete (missing={missing}, extra={extra})")
    for db_number, _key_digest in volatile:
        if db_number >= database_count:
            raise FingerprintError(
                f"volatile record database id {db_number} exceeds configured count"
            )
    return Fingerprint(format_name, database_count, db, volatile)


def compare(expected: Fingerprint, actual: Fingerprint, *, tolerance_ms: int = 2000) -> None:
    if tolerance_ms < 0:
        raise FingerprintError("deadline tolerance cannot be negative")
    if expected.format != actual.format:
        suffix = (
            "; legacy v2 snapshots must be re-created as a fresh v3 backup"
            if V2_FORMAT in {expected.format, actual.format}
            else ""
        )
        raise FingerprintError(
            f"Redis fingerprint formats differ ({expected.format} != {actual.format}){suffix}"
        )
    if expected.databases != actual.databases:
        raise FingerprintError("Redis database counts differ")

    if expected.format == V2_FORMAT:
        try:
            if expected.db != actual.db:
                raise FingerprintError("Redis key/value digest differs")
            if expected.volatile.keys() != actual.volatile.keys():
                raise FingerprintError("Redis expiry key set differs")
            for key, record in expected.volatile.items():
                delta = abs(record.deadline_ms - actual.volatile[key].deadline_ms)
                if delta > tolerance_ms:
                    raise FingerprintError(
                        f"Redis absolute expiry differs by {delta}ms for {key}"
                    )
        except FingerprintError as exc:
            raise FingerprintError(
                f"{exc}; legacy v2 comparison is exact and cannot distinguish "
                "expired volatile keys—create a fresh v3 backup"
            ) from exc
        return

    for db_number in range(expected.databases):
        expected_db = expected.db[db_number]
        actual_db = actual.db[db_number]
        assert isinstance(expected_db, DatabaseV3)
        assert isinstance(actual_db, DatabaseV3)
        if actual_db.captured_at_ms + tolerance_ms < expected_db.captured_at_ms:
            raise FingerprintError(
                f"Redis DB {db_number} actual capture time predates the source capture"
            )
        if (expected_db.durable_count, expected_db.durable_digest) != (
            actual_db.durable_count,
            actual_db.durable_digest,
        ):
            raise FingerprintError(f"Redis DB {db_number} durable state differs")

    unexpected = sorted(actual.volatile.keys() - expected.volatile.keys())
    if unexpected:
        raise FingerprintError(f"Redis has unexpected volatile keys: {unexpected}")

    for key, expected_key in expected.volatile.items():
        actual_key = actual.volatile.get(key)
        db_number = key[0]
        actual_db = actual.db[db_number]
        assert isinstance(actual_db, DatabaseV3)
        if actual_key is None:
            if expected_key.deadline_ms <= actual_db.captured_at_ms:
                continue
            raise FingerprintError(
                f"Redis volatile key {key} disappeared before its deadline "
                f"({expected_key.deadline_ms} > capture {actual_db.captured_at_ms})"
            )
        if expected_key.content_digest != actual_key.content_digest:
            raise FingerprintError(f"Redis volatile key {key} content differs")
        delta = abs(expected_key.deadline_ms - actual_key.deadline_ms)
        if delta > tolerance_ms:
            raise FingerprintError(
                f"Redis volatile key {key} deadline differs by {delta}ms"
            )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    parse_parser = subparsers.add_parser("parse")
    parse_parser.add_argument("fingerprint")
    databases_parser = subparsers.add_parser("databases")
    databases_parser.add_argument("fingerprint")
    format_parser = subparsers.add_parser("format")
    format_parser.add_argument("fingerprint")
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("expected")
    compare_parser.add_argument("actual")
    compare_parser.add_argument("--tolerance-ms", type=int, default=2000)
    stream_parse_parser = subparsers.add_parser("stream-repair-parse")
    stream_parse_parser.add_argument("manifest")
    stream_databases_parser = subparsers.add_parser("stream-repair-databases")
    stream_databases_parser.add_argument("manifest")
    stream_compare_parser = subparsers.add_parser("stream-repair-compare")
    stream_compare_parser.add_argument("expected")
    stream_compare_parser.add_argument("actual")
    stream_diff_parser = subparsers.add_parser("stream-repair-diff")
    stream_diff_parser.add_argument("expected")
    stream_diff_parser.add_argument("actual")
    stream_apply_parser = subparsers.add_parser("stream-repair-apply")
    stream_apply_parser.add_argument("manifest")
    stream_apply_parser.add_argument("client", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.command == "parse":
            parse(args.fingerprint)
        elif args.command == "databases":
            print(parse(args.fingerprint).databases)
        elif args.command == "format":
            fingerprint = parse(args.fingerprint)
            print("v2" if fingerprint.format == V2_FORMAT else "v3")
        elif args.command == "compare":
            compare(
                parse(args.expected),
                parse(args.actual),
                tolerance_ms=args.tolerance_ms,
            )
        elif args.command == "stream-repair-parse":
            parse_stream_repair(args.manifest)
        elif args.command == "stream-repair-databases":
            print(parse_stream_repair(args.manifest).databases)
        elif args.command == "stream-repair-compare":
            compare_stream_repair(
                parse_stream_repair(args.expected),
                parse_stream_repair(args.actual),
            )
        elif args.command == "stream-repair-diff":
            differences = diff_stream_repair(
                parse_stream_repair(args.expected),
                parse_stream_repair(args.actual),
            )
            if differences:
                print("\n".join(differences))
                return 1
        else:
            client = args.client[1:] if args.client[:1] == ["--"] else args.client
            apply_stream_repair(parse_stream_repair(args.manifest), client)
    except FingerprintError as exc:
        print(f"redis-state: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
