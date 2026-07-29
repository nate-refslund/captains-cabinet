"""Every vitest file a ledger gate_cmd names must EXIST.

THE DEFECT THIS EXISTS FOR, measured 2026-07-29. The `WORLD-ALIVE-COZY` row is
`done`, and its gate_cmd was

    cd cabinet/dashboard && npx vitest run \
        src/lib/world/lighting.test.ts src/lib/world/set-dressing.test.ts \
        && npx tsc --noEmit

`set-dressing.test.ts` had been deleted with the legacy shell earlier that day.
Run verbatim on master the gate reported **1 file, 15 tests, exit 0** — because
vitest IGNORES a pattern that matches nothing as long as another pattern
matches. Half the gate had stopped existing and the row went on certifying
itself green. Nobody had to be careless for this to happen: deleting the code
and deleting the test was the right call, and the gate that referenced it was
three thousand lines away in a different file.

WHY THIS CHECK IS NARROW ON PURPOSE. A general "every path in every gate_cmd
resolves" check was measured first and is unusable: 33 hits across the ledger,
almost all of them legitimate — gitignored runtime artifacts
(`shared/interfaces/captain-decisions.md`, `world-chronicle.jsonl`), glob
fragments (`*.labels.json`), and paths inside heredocs. A gate with thirty
false positives is a gate someone switches off.

So this checks the ONE shape that fails silently: explicit test-file arguments
to `npx vitest run`. pytest EXITS NON-ZERO on a missing file, so it reports its
own problem; vitest does not, which is precisely why this class needs a sensor
and the other does not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO = Path(__file__).resolve().parents[3]
LEDGER = REPO / "docs" / "plans" / "operative-egg-ledger-2026-07-07.yml"

#: `cd <dir> &&` prefix — the cwd the rest of the command runs in.
CD_RE = re.compile(r"cd\s+([\w./-]+)\s*&&")
#: `npx vitest run a.test.ts b.test.ts` — the explicit-file form only.
VITEST_RE = re.compile(r"npx\s+vitest\s+run\s+([^&|;]*)")
#: A concrete test path (no globs — a glob that matches nothing is a different
#: question and vitest treats it differently).
TESTFILE_RE = re.compile(r"(?<![\w/.-])([\w./-]+\.test\.tsx?)\b")


def _entries() -> list[dict]:
    doc = yaml.safe_load(LEDGER.read_text())
    entries = doc.get("entries") or []
    assert isinstance(entries, list)
    return [e for e in entries if isinstance(e, dict)]


def _named_test_files() -> list[tuple[str, Path]]:
    """(row id, resolved path) for every explicit vitest file argument."""
    out: list[tuple[str, Path]] = []
    for row in _entries():
        cmd = row.get("gate_cmd") or ""
        if not isinstance(cmd, str):
            continue
        cd = CD_RE.search(cmd)
        base = REPO / cd.group(1) if cd else REPO
        for args in VITEST_RE.findall(cmd):
            for f in TESTFILE_RE.findall(args):
                out.append((str(row.get("id")), (base / f).resolve()))
    return out


def test_the_ledger_is_readable_and_has_rows() -> None:
    """A sweep over an empty list passes every assertion in it."""
    assert len(_entries()) > 100


def test_the_sweep_finds_vitest_gates() -> None:
    """…and so does a sweep that matched no gate_cmd at all.

    The floor is a MEASURED count (4 on 2026-07-29), not a guess: the first
    draft asserted `> 5` because five felt like a safe number, and it failed
    against a ledger that has four. A threshold nobody measured is the same
    class of defect this file is about.
    """
    named = _named_test_files()
    assert len(named) >= 3, "no vitest gate_cmd found — the regex stopped matching"
    # every hit is a dashboard test path, so the regex is matching what it means
    for row_id, path in named:
        assert path.name.endswith((".test.ts", ".test.tsx")), (row_id, path)
        assert "cabinet/dashboard" in str(path), (row_id, path)


def test_every_vitest_file_named_by_a_gate_cmd_exists() -> None:
    """The gate itself.

    A missing file here means a `done` row is certifying itself with a command
    that verifies less than it says. Fix the gate_cmd (or restore the test) —
    never delete the row.
    """
    missing = [
        f"{row_id}: {path.relative_to(REPO)}"
        for row_id, path in _named_test_files()
        if not path.exists()
    ]
    assert missing == [], (
        "ledger gate_cmd names vitest test file(s) that do not exist; vitest "
        "silently ignores them when another pattern matches, so the gate "
        f"reports green over less than it claims: {missing}"
    )


def test_the_check_can_fail(tmp_path: Path) -> None:
    """The arm is real — pointed at a row naming a file that is not there.

    Without this, a regex that quietly stopped matching would leave the gate
    above passing over nothing, which is the same defect one level up.
    """
    fixture = tmp_path / "ledger.yml"
    fixture.write_text(
        "entries:\n"
        '  - id: "FAKE"\n'
        '    gate_cmd: "cd cabinet/dashboard && npx vitest run '
        'src/lib/world/definitely-not-here.test.ts"\n'
    )
    doc = yaml.safe_load(fixture.read_text())
    row = doc["entries"][0]
    cmd = row["gate_cmd"]
    cd = CD_RE.search(cmd)
    base = REPO / cd.group(1)
    found = [
        f for args in VITEST_RE.findall(cmd) for f in TESTFILE_RE.findall(args)
    ]
    assert found == ["src/lib/world/definitely-not-here.test.ts"]
    assert not (base / found[0]).exists()
