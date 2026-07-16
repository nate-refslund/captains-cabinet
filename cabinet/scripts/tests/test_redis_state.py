"""Redis fingerprint v3 parser, comparison, and replay regressions."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "cabinet/scripts/lib/redis_state.py"
SPEC = importlib.util.spec_from_file_location("cabinet_redis_state", TOOL)
assert SPEC and SPEC.loader
redis_state = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = redis_state
SPEC.loader.exec_module(redis_state)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
V2_A = "a" * 40
V2_B = "b" * 40


def _v3(
    *,
    captured: int = 2_000_000,
    durable_count: int = 1,
    durable_digest: str = A,
    volatile: tuple[tuple[str, str, int], ...] = (),
) -> str:
    lines = [
        "FORMAT redis-logical-content-expiry-v3",
        "DATABASES 1",
        f"DB 0 {captured} {durable_count} {durable_digest}",
    ]
    lines.extend(f"VOLATILE 0 {key} {content} {deadline}" for key, content, deadline in volatile)
    return "\n".join(lines) + "\n"


def _v2(*, digest: str = V2_A, deadline: int = 3_000_000) -> str:
    return (
        "FORMAT redis-dump-content-expiry-v2\n"
        "DATABASES 1\n"
        f"DB 0 2:{digest}\n"
        f"EXPIRY 0 {V2_B} {deadline}\n"
    )


def _parsed(tmp_path: Path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return redis_state.parse(path)


def test_v3_allows_only_expired_expected_volatile_to_be_absent(tmp_path: Path):
    expected = _parsed(
        tmp_path,
        "expected",
        _v3(captured=1_000_000, volatile=((B, C, 1_500_000),)),
    )
    actual = _parsed(tmp_path, "actual", _v3(captured=2_000_000))

    redis_state.compare(expected, actual)


def test_v3_rejects_future_missing_volatile(tmp_path: Path):
    expected = _parsed(
        tmp_path,
        "expected",
        _v3(captured=1_000_000, volatile=((B, C, 2_000_001),)),
    )
    actual = _parsed(tmp_path, "actual", _v3(captured=2_000_000))

    with pytest.raises(redis_state.FingerprintError, match="before its deadline"):
        redis_state.compare(expected, actual)


@pytest.mark.parametrize(
    ("actual_volatile", "message"),
    [
        (((B, D, 3_000_000),), "content differs"),
        (((B, C, 3_000_000), (D, C, 3_000_000)), "unexpected volatile"),
    ],
)
def test_v3_rejects_changed_or_unexpected_volatile(
    tmp_path: Path,
    actual_volatile: tuple[tuple[str, str, int], ...],
    message: str,
):
    expected = _parsed(
        tmp_path,
        "expected",
        _v3(captured=1_000_000, volatile=((B, C, 3_000_000),)),
    )
    actual = _parsed(
        tmp_path,
        "actual",
        _v3(captured=2_000_000, volatile=actual_volatile),
    )

    with pytest.raises(redis_state.FingerprintError, match=message):
        redis_state.compare(expected, actual)


def test_v3_rejects_durable_mismatch(tmp_path: Path):
    expected = _parsed(tmp_path, "expected", _v3(captured=1_000_000))
    actual = _parsed(
        tmp_path,
        "actual",
        _v3(captured=2_000_000, durable_digest=D),
    )

    with pytest.raises(redis_state.FingerprintError, match="durable state differs"):
        redis_state.compare(expected, actual)


def test_v3_deadline_skew_is_bounded(tmp_path: Path):
    expected = _parsed(
        tmp_path,
        "expected",
        _v3(captured=1_000_000, volatile=((B, C, 3_000_000),)),
    )
    within = _parsed(
        tmp_path,
        "within",
        _v3(captured=2_000_000, volatile=((B, C, 3_002_000),)),
    )
    outside = _parsed(
        tmp_path,
        "outside",
        _v3(captured=2_000_000, volatile=((B, C, 3_002_001),)),
    )

    redis_state.compare(expected, within)
    with pytest.raises(redis_state.FingerprintError, match="deadline differs"):
        redis_state.compare(expected, outside)


@pytest.mark.parametrize(
    "bad_record",
    [
        f"DB 0 1000 0 {A}\nDB 0 1000 0 {A}",
        f"DB 0 1000 0 {A}\nVOLATILE 0 {B} {C} 2000\nVOLATILE 0 {B} {C} 2000",
        f"DB 0 1000 0 {A}\nSURPRISE 0 {B}",
        f"DB 0 1000 0 {A}\nVOLATILE 0 short {C} 2000",
        f"DB 0 1000 0 {A}\n",
    ],
)
def test_strict_parser_rejects_duplicate_or_malformed_records(
    tmp_path: Path, bad_record: str
):
    text = "FORMAT redis-logical-content-expiry-v3\nDATABASES 1\n" + bad_record + "\n"
    path = tmp_path / "bad"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(redis_state.FingerprintError):
        redis_state.parse(path)


def test_v2_exact_passes_but_mismatch_requests_fresh_v3(tmp_path: Path):
    expected = _parsed(tmp_path, "expected", _v2(digest=V2_A))
    exact = _parsed(tmp_path, "exact", _v2(digest=V2_A, deadline=3_002_000))
    mismatch = _parsed(tmp_path, "mismatch", _v2(digest="d" * 40))

    redis_state.compare(expected, exact)
    with pytest.raises(redis_state.FingerprintError, match="fresh v3 backup"):
        redis_state.compare(expected, mismatch)
