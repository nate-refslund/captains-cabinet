"""Schema + seed-row contract tests for cabinet/config/workarounds.yml.

Pins: every row carries the full required field set; ids are unique and
WA-YYYY-MM-DD-<slug> shaped; recorded dates are ISO; version_condition
parses under the documented grammar (comparator vs fixed-in); owner_surface
names a real tracked file; and EVERY seed retest_cmd passes the runner's
read-only screen (a registry row the runner would refuse is a defect at
commit time, not at retest time).

Runner under test: cabinet/scripts/workaround-retest.py (imported by file
path — the filename is hyphenated on purpose to match the .sh entry).
"""
from __future__ import annotations

import importlib.util
import re
from datetime import date
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")  # same dep the runner uses

REPO = Path(__file__).resolve().parents[3]
REGISTRY = REPO / "cabinet" / "config" / "workarounds.yml"
RUNNER = REPO / "cabinet" / "scripts" / "workaround-retest.py"

SEED_IDS = {
    "WA-2026-07-16-memory-redis-host-docker-default",
    "WA-2026-07-16-claude-binary-homebrew-path-bridge",
    "WA-2026-07-16-egress-apply-lock-livelock",
}


def _harness():
    spec = importlib.util.spec_from_file_location("workaround_retest", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def harness():
    return _harness()


@pytest.fixture(scope="module")
def rows(harness):
    return harness.load_registry(REGISTRY)


def test_registry_exists_and_loads(rows):
    assert len(rows) >= 3


def test_seed_ids_present(rows):
    ids = {r["id"] for r in rows}
    missing = SEED_IDS - ids
    assert not missing, f"seed workaround rows missing: {missing}"


def test_every_row_has_required_nonempty_fields(harness, rows):
    for row in rows:
        for field in harness.REQUIRED_FIELDS:
            assert isinstance(row.get(field), str) and row[field].strip(), (
                f"{row.get('id', '?')}: field `{field}` missing/empty")


def test_ids_unique_and_wellformed(rows):
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    pat = re.compile(r"^WA-\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*$")
    for i in ids:
        assert pat.match(i), f"id not WA-YYYY-MM-DD-<kebab>: {i}"


def test_recorded_dates_are_real_iso_dates(rows):
    for row in rows:
        date.fromisoformat(str(row["recorded"]))  # raises on junk


def test_version_conditions_parse_under_grammar(harness, rows):
    for row in rows:
        parsed = harness.parse_version_condition(row["version_condition"])
        assert parsed is not None, (
            f"{row['id']}: unparseable version_condition "
            f"{row['version_condition']!r}")
        assert parsed[0] in ("comparator", "fixed-in")


def test_claude_binary_row_is_auto_matchable_comparator(harness, rows):
    row = next(r for r in rows
               if r["id"] == "WA-2026-07-16-claude-binary-homebrew-path-bridge")
    parsed = harness.parse_version_condition(row["version_condition"])
    assert parsed == ("comparator", "claude-code", ">", "2.1.211")


def test_owner_surfaces_exist_in_repo(rows):
    for row in rows:
        assert (REPO / row["owner_surface"]).is_file(), (
            f"{row['id']}: owner_surface `{row['owner_surface']}` "
            "is not a file in the repo")


def test_every_seed_retest_cmd_passes_the_readonly_screen(harness, rows):
    for row in rows:
        ok, reason = harness.screen_cmd(row["retest_cmd"])
        assert ok, f"{row['id']}: retest_cmd refused by screen: {reason}"


def test_probe_files_referenced_by_retest_cmds_exist(rows):
    for row in rows:
        for token in row["retest_cmd"].split():
            if token.startswith("cabinet/scripts/workaround-probes/"):
                assert (REPO / token).is_file(), (
                    f"{row['id']}: probe file `{token}` missing")


def test_validate_row_rejects_bad_rows(harness):
    good = {
        "id": "WA-2026-01-01-example",
        "symptom": "s", "cause": "c", "workaround": "w",
        "version_condition": "claude-code > 1.0.0",
        "retest_cmd": "true",
        "owner_surface": "cabinet/scripts/workaround-retest.py",
        "recorded": "2026-01-01",
    }
    assert harness.validate_row(good) == []
    for mutation, needle in [
        ({"id": "not-a-wa-id"}, "id"),
        ({"symptom": ""}, "symptom"),
        ({"version_condition": "totally freeform"}, "version_condition"),
        ({"recorded": "yesterday"}, "recorded"),
        ({"retest_cmd": None}, "retest_cmd"),
    ]:
        bad = {**good, **mutation}
        errs = harness.validate_row(bad)
        assert errs and any(needle in e for e in errs), (
            f"mutation {mutation} not rejected: {errs}")


def test_duplicate_ids_rejected_at_load(harness, tmp_path):
    row = (
        "  - id: WA-2026-01-01-dup\n"
        "    symptom: s\n    cause: c\n    workaround: w\n"
        "    version_condition: 'claude-code > 1.0.0'\n"
        "    retest_cmd: 'true'\n"
        "    owner_surface: cabinet/scripts/workaround-retest.py\n"
        "    recorded: '2026-01-01'\n"
    )
    reg = tmp_path / "workarounds.yml"
    reg.write_text("version: 1\nworkarounds:\n" + row + row)
    with pytest.raises(ValueError, match="duplicate"):
        harness.load_registry(reg)
