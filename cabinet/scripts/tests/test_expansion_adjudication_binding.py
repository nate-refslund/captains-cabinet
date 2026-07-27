"""Source-side binding for the expansion registry's `adjudication` field.

The census schema-refuses an adjudication that is not a confined relative `.md`
path, but a path is only a string until something reads the bytes behind it —
and a check that asks nothing but "does this file exist" is passed by `touch`.
This is the part that cannot be touched into passing: the document an expansion
row names must EXIST and must NAME the member it claims to adjudicate.

WHY IT LIVES HERE AND NOT IN THE CENSUS. The census ships in the egg and runs in
a gitless clean hatch (cabinet/scripts/verify-cognitive-architecture.sh is a
declared enduring gate). The export archives docs/plans and docs/proposals out
(cabinet/scripts/egg-export-manifest.txt), which is where written adjudications
live — so a shipped copy of this check would red a hatched cabinet over a
document the export deliberately removed, and the only fix available to the
hatched captain would be to disable it. This file is therefore excluded from the
egg by the same delete + expect-absent idiom the phase rollback tests use. The
gate that matters runs in the source instance's CI, at the moment an expansion
lands.

NEVER VACUOUS. The registry's honest steady state is empty, so a test that only
looped over live rows would pass by having nothing to check — a disabled sensor
wearing a green tick. The checker is therefore exercised against a synthetic
PASSING document and two synthetic FAILING ones on every run, whatever the live
registry holds.

Provenance: the 2026-07-27 two-model expansion-gate adjudication (Fable 5 +
Opus 5, blind, own clones), per the 2026-07-07 full-autonomy grant.
"""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "cabinet" / "config" / "cognitive-architecture-contract.yml"


def _live_expansions() -> list[dict]:
    return yaml.safe_load(CONTRACT.read_text())["expansions"]


def adjudication_binding_failures(root: Path, rows: list[dict]) -> list[tuple[str, str]]:
    """Return (member, reason) for every row whose adjudication does not bind."""

    failures: list[tuple[str, str]] = []
    for row in rows:
        document = root / row["adjudication"]
        if not document.is_file():
            failures.append((row["member"], "adjudication document is absent"))
            continue
        if row["member"] not in document.read_text(encoding="utf-8", errors="ignore"):
            failures.append((row["member"], "adjudication document does not name the member"))
    return failures


def test_checker_binds_a_document_that_names_its_member(tmp_path: Path):
    (tmp_path / "gate.md").write_text(
        "# gate\n\nAdjudicated: the surplus member `synthetic_member` is kept.\n"
    )

    assert (
        adjudication_binding_failures(
            tmp_path, [{"member": "synthetic_member", "adjudication": "gate.md"}]
        )
        == []
    )


def test_checker_rejects_an_absent_document(tmp_path: Path):
    assert adjudication_binding_failures(
        tmp_path, [{"member": "synthetic_member", "adjudication": "never-written.md"}]
    ) == [("synthetic_member", "adjudication document is absent")]


def test_checker_rejects_a_touched_document_that_names_nothing(tmp_path: Path):
    """The `touch` arm: a document that exists and says nothing binds nothing."""

    (tmp_path / "gate.md").write_text("")

    assert adjudication_binding_failures(
        tmp_path, [{"member": "synthetic_member", "adjudication": "gate.md"}]
    ) == [("synthetic_member", "adjudication document does not name the member")]


def test_checker_rejects_a_document_about_a_different_member(tmp_path: Path):
    """The stale copy: a real adjudication, reused for a member it never named."""

    (tmp_path / "gate.md").write_text("# gate\n\nAdjudicated: `some_other_member`.\n")

    assert adjudication_binding_failures(
        tmp_path, [{"member": "synthetic_member", "adjudication": "gate.md"}]
    ) == [("synthetic_member", "adjudication document does not name the member")]


def test_every_live_expansion_row_is_bound_to_its_adjudication():
    failures = adjudication_binding_failures(ROOT, _live_expansions())

    assert failures == [], failures
