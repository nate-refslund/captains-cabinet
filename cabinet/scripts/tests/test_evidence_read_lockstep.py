"""ONE validation truth across the Phase-3 evidence read surfaces.

The dashboard /evidence page (cabinet/dashboard/src/lib/evidence/read.ts)
cannot import the Python query plane, so it MIRRORS the validation rules of
framework/evidence/query.py.  Mirrors drift; this test pins them:

  1. VOCABULARY LOCKSTEP — the TS literals (EVIDENCE_STATUSES, ACTOR_KINDS,
     TRIAL_ID_RE, TIME_RE) are parsed out of read.ts and compared to the
     Python truths (framework/evidence/verifier.py STATUSES / ACTOR_KINDS /
     TRIAL_ID_RE; framework/evidence/query.py _VALUE_RE / _TIME_RANGE_RE).
  2. BEHAVIOR LOCKSTEP — the shared case vector
     (fixtures/evidence-filter-cases.json) is run through the REAL
     query.parse_selector here (`cli` column), and through the REAL
     validateFilters by the vitest twin
     (cabinet/dashboard/src/lib/evidence/filter-lockstep.test.ts,
     `dashboard` column).  The law: cli == dashboard for every case unless
     the case declares exactly one sanctioned divergence:
       alias_of         — the page's single documented input alias
                          (<yyyymmdd> meaning <d>-<d>); its target must be
                          CLI-valid, so the alias adds an input FORM, never
                          a second rule;
       transport_budget — the CLI packs `by-<name>:` + value into ONE
                          doorway token (<=128 chars total), so a value that
                          is legal under the SHARED value grammar can
                          overflow the CLI packaging; the value grammar
                          itself stays identical (asserted here).

MATCHING-semantics note (documented, not a rule divergence): the CLI's
by-actor predicate also matches the combined "<kind>:<id>" form for unknown
kinds, while the page treats an unknown-kind prefix as a plain id.  On
VERIFIED data these coincide: the recorder/verifier admit only ACTOR_KINDS
kinds, so an unknown-kind combined form can never name a verified event's
kind.  Synthetic Testburg vocabulary only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.evidence import query  # noqa: E402
from framework.evidence import verifier  # noqa: E402
from framework.evidence.recorder import EvidenceError  # noqa: E402

_READ_TS = _REPO_ROOT / "cabinet" / "dashboard" / "src" / "lib" / "evidence" / "read.ts"
_CASES = Path(__file__).resolve().parent / "fixtures" / "evidence-filter-cases.json"

# The doorway/token grammar both sides pin (evidence-read.sh + verifier).
_TOKEN_MAX = 128


def _read_ts_text() -> str:
    return _READ_TS.read_text(encoding="utf-8")


def _ts_string_set(text: str, name: str) -> frozenset[str]:
    """Extract `new Set([ 'a', 'b', ... ])` string literals for `name`."""
    match = re.search(
        rf"const {re.escape(name)} = new Set\(\[(.*?)\]\)", text, re.DOTALL
    )
    assert match, f"read.ts no longer declares {name} as a literal Set"
    return frozenset(re.findall(r"'([^']*)'", match.group(1)))


def _ts_regex_literal(text: str, name: str) -> str:
    match = re.search(rf"const {re.escape(name)} = /(.*?)/\n", text)
    assert match, f"read.ts no longer declares {name} as a literal regex"
    return match.group(1)


def _cli_accepts(filter_name: str, value: str) -> bool:
    try:
        query.parse_selector(f"by-{filter_name}:{value}")
        return True
    except EvidenceError:
        return False


def _cases() -> list[dict]:
    data = json.loads(_CASES.read_text(encoding="utf-8"))
    cases = data["cases"]
    assert cases, "empty case vector pins nothing"
    return cases


# ---------------------------------------------------------------------------
# 1. vocabulary lockstep
# ---------------------------------------------------------------------------

def test_ts_status_vocabulary_equals_verifier_statuses():
    assert _ts_string_set(_read_ts_text(), "EVIDENCE_STATUSES") == frozenset(
        verifier.STATUSES
    )


def test_ts_actor_kinds_equal_verifier_actor_kinds():
    assert _ts_string_set(_read_ts_text(), "ACTOR_KINDS") == frozenset(
        verifier.ACTOR_KINDS
    )


def test_ts_trial_id_regex_is_byte_identical_to_python():
    ts_pattern = _ts_regex_literal(_read_ts_text(), "TRIAL_ID_RE")
    assert ts_pattern == verifier.TRIAL_ID_RE.pattern
    # The query plane's VALUE grammar is the same alphabet — one charset
    # truth on the Python side too.
    assert query._VALUE_RE.pattern == verifier.TRIAL_ID_RE.pattern


def test_ts_time_regex_is_pythons_range_plus_the_single_day_alias():
    ts_pattern = _ts_regex_literal(_read_ts_text(), "TIME_RE")
    # Pin both literals exactly: the TS grammar is Python's range grammar
    # with the second half optional (the documented single-day alias) —
    # any other drift on either side fails here.
    assert ts_pattern == r"^(\d{8})(?:-(\d{8}))?$"
    assert query._TIME_RANGE_RE.pattern == r"^(\d{8})-(\d{8})$"


# ---------------------------------------------------------------------------
# 2. behavior lockstep over the shared vector
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "case",
    _cases(),
    ids=lambda case: f"{case['filter']}:{case['value'][:32]!r}",
)
def test_cli_column_matches_parse_selector(case):
    assert _cli_accepts(case["filter"], case["value"]) is case["cli"], (
        "query.parse_selector no longer agrees with the shared case vector — "
        "update fixtures/evidence-filter-cases.json AND the vitest twin "
        "together, never one side alone"
    )


def test_law_dashboard_equals_cli_except_sanctioned_divergences():
    for case in _cases():
        divergences = [k for k in ("alias_of", "transport_budget") if k in case]
        if case["dashboard"] == case["cli"]:
            assert not divergences, (
                f"{case}: sanctioned-divergence marker on a non-divergent case"
            )
            continue
        assert len(divergences) == 1, (
            f"{case}: cli != dashboard needs exactly one sanctioned reason"
        )
        # Divergence may only ever WIDEN the Captain page, never the CLI:
        # the officer-reachable grammar is the narrow one.
        assert case["dashboard"] is True and case["cli"] is False, (
            f"{case}: a CLI-only acceptance would widen the officer surface"
        )
        if divergences == ["alias_of"]:
            assert case["filter"] == "time", f"{case}: alias is time-only"
            assert case["alias_of"] == f"{case['value']}-{case['value']}", (
                f"{case}: the alias must be exactly <d>-<d>"
            )
            assert _cli_accepts("time", case["alias_of"]), (
                f"{case}: alias target must be CLI-valid — the alias adds a "
                "form, never a rule"
            )
        else:  # transport_budget
            assert query._VALUE_RE.fullmatch(case["value"]), (
                f"{case}: transport_budget requires a value the SHARED "
                "grammar accepts"
            )
            token = f"by-{case['filter']}:{case['value']}"
            assert len(token) > _TOKEN_MAX, (
                f"{case}: transport_budget requires the packed token to "
                "overflow the doorway's {_TOKEN_MAX}-char budget"
            )


def test_vector_and_vitest_twin_exist_and_cover_every_dimension():
    filters = {case["filter"] for case in _cases()}
    assert filters == {"actor", "component", "status", "time"}
    twin = (
        _REPO_ROOT
        / "cabinet"
        / "dashboard"
        / "src"
        / "lib"
        / "evidence"
        / "filter-lockstep.test.ts"
    )
    assert twin.is_file(), "the vitest twin must run the same vector"
    body = twin.read_text(encoding="utf-8")
    assert "evidence-filter-cases.json" in body, (
        "the vitest twin no longer reads the shared case vector"
    )
