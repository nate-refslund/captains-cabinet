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
import re
import sys
from dataclasses import dataclass
from pathlib import Path


V2_FORMAT = "redis-dump-content-expiry-v2"
V3_FORMAT = "redis-logical-content-expiry-v3"
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UINT = re.compile(r"(?:0|[1-9][0-9]*)\Z")


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
    args = parser.parse_args(argv)
    try:
        if args.command == "parse":
            parse(args.fingerprint)
        elif args.command == "databases":
            print(parse(args.fingerprint).databases)
        elif args.command == "format":
            fingerprint = parse(args.fingerprint)
            print("v2" if fingerprint.format == V2_FORMAT else "v3")
        else:
            compare(
                parse(args.expected),
                parse(args.actual),
                tolerance_ms=args.tolerance_ms,
            )
    except FingerprintError as exc:
        print(f"redis-state: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
