"""Pin the declared-residuals register to the tree, both directions.

docs/plans/declared-residuals-register.md is the single surface listing what
the program KNOWS it has not closed. It is only worth having if it cannot
drift from the code, so this module binds the two halves:

  ROWS -> TREE   every row's cited file:line still exists and still carries the
                 declaration it names (a row cannot outlive its declaration).
  TREE -> ROWS   every marker discovered in the sweep surface has a row (a NEW
                 residual cannot be declared without registering it).

MARKER CONVENTION (surveyed at a1357829, not invented). The dominant in-code
form is the uppercase word token, in three qualifier variants — bare
"<TOKEN>:", "HONEST <TOKEN>:", "KNOWN <TOKEN>". The tracked tree carries 21
word-token sites in 11 files: 8 in 6 files inside the sweep surface below (the
ones this gate binds), 11 in the operative ledger + plan pair, and 2 in frozen
review artifacts. "DECLARED RESIDUAL" / "HONEST SCOPE" / "known limitation"
have ZERO occurrences and were rejected. The lookarounds in MARKER_RE exclude
identifiers that merely contain the word (_TEMPORARY_RESIDUALS in
test_no_launcher_hardcode.py, RESIDUAL_NOTE in evidence-tamper-drill.py) —
those are mechanisms, not declarations. The register's retirement field takes
its name from the repo's existing RETIREMENT CONDITION idiom (42 uses / 24
files).

Counts are git-grep measured: BSD `grep -I` in a non-UTF-8 locale treats this
repo's em-dash-heavy markdown as binary and silently skips 19 files.

CHEAP + DETERMINISTIC: no network, no clock, no subprocess except one optional
`git ls-files`. The sweep reads ~1900 tracked text files in well under a second
and is memoized for the module.

EXPORT TOLERANCE (the ledger-status-parity.sh:76-88 double-key idiom): the
register is a source-instance artifact that transform:plans-archive strips from
the egg, dropping docs/plans/ARCHIVED-NOTE.md where it pruned the tree. On such
a cut this module SKIPs loud. The register absent WITHOUT that archive marker is
real source rot and hard-fails — never a silent pass.

Provenance: authored per the 2026-07-07 full-autonomy grant.
"""
from __future__ import annotations

import functools
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

REGISTER_REL = "docs/plans/declared-residuals-register.md"
ARCHIVE_MARKER_REL = "docs/plans/ARCHIVED-NOTE.md"

# SELF-EXCLUSION: the file that DEFINES the marker cannot be a subject of it.
# Same idiom framework/tests/test_no_launcher_hardcode.py uses for its own
# detection-pattern list.
SELF_REL = "cabinet/scripts/tests/test_declared_residuals_register.py"

MARKER_RE = re.compile(r"(?<![A-Za-z0-9_])RESIDUALS?(?![A-Za-z0-9_])")

SWEEP_ROOTS = ("framework", "cabinet", "instance", "shared")
SWEEP_SKIP_DIRS = frozenset({
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".next", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".turbo",
    "coverage", "htmlcov", ".egg-info",
})
# shared/interfaces/reviews holds FROZEN, append-only review artifacts; the
# COG-4 one is digest-bound by cognitive-phase4-review-scope.py, so its bytes
# may not be reworded to satisfy a sweep. Rows may still cite it.
SWEEP_SKIP_SUBTREES = ("shared/interfaces/reviews",)
SWEEP_EXTS = frozenset({
    ".py", ".sh", ".bash", ".yml", ".yaml", ".json", ".txt", ".toml", ".cfg",
    ".ini", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".sql", ".md", ".plist",
    ".conf", ".example", ".env", ".sample",
})

# Marker sites in the sweep surface that are NOT declarations of an open
# residual and therefore carry no row. SHRINK-ONLY: LEGACY_MAX never rises.
# Both read "RESIDUAL SCRUB" and describe scrub rules already EXECUTED
# (2026-07-21), not open channels. They are not reworded out of the sweep
# because egg-export-manifest.txt sits inside the frozen COG-4 review digest
# scope — editing it forces a re-bind ceremony.
LEGACY_EXEMPT = {
    # Line cites re-anchored 2026-07-26 (233 -> 235, 653 -> 658) by the egg
    # egress-default flip, again 2026-07-26 (235 -> 242, 658 -> 669) by the
    # captain-availability-dial manifest rows, and again 2026-07-27 (242 -> 248,
    # 669 -> 680) by the captain-dates manifest rows — each time a delete row +
    # comment above the first site and an expect-present row + comment above the
    # second. The marker TEXT and the exempt SET are unchanged every time — these
    # are re-anchors, not widenings, and LEGACY_MAX stays 2. Re-anchored again
    # 2026-07-27 (248 -> 258, 680 -> 696) by the expansion-registry manifest
    # rows — same shape: a delete row + comment above the first site and an
    # expect-present row + comment above the second. Marker TEXT and exempt SET
    # unchanged.
    ("cabinet/scripts/egg-export-manifest.txt", 258): "RESIDUAL SCRUB",
    ("cabinet/scripts/egg-export-manifest.txt", 696): "RESIDUAL SCRUB",
}
LEGACY_MAX = 2

ROW_HEADING_RE = re.compile(r"^### (RES-\d{3})\s+[—-]\s+(\S.*)$")
ANY_H3_RE = re.compile(r"^### ")
HEADING_RE = re.compile(r"^#{1,6} ")
FIELD_RE = re.compile(r"^- \*\*(?P<name>[^*:]+):\*\* (?P<value>.+)$")
BACKTICK_RE = re.compile(r"`([^`]*)`")
CITE_RE = re.compile(r"^(?P<path>[^\s`:]+):(?P<line>\d+)$")

REQUIRED_FIELDS = (
    "Phase", "Status", "Closed", "Open", "Why open", "Declared at",
    "Anchor", "Retirement",
)
OPTIONAL_FIELDS = ("Note",)
OPEN_STATUSES = frozenset({"open", "captain-gated"})
RETIRED_STATUS = "retired"
ALL_STATUSES = OPEN_STATUSES | {RETIRED_STATUS}

_HINT = (
    "\nThe register is docs/plans/declared-residuals-register.md; its "
    "'How to add a row' section states the two-halves-in-one-commit rule."
)


# --------------------------------------------------------------------------
# export tolerance — evaluated at import, before anything else
# --------------------------------------------------------------------------
if not (ROOT / REGISTER_REL).is_file() and (ROOT / ARCHIVE_MARKER_REL).is_file():
    pytest.skip(
        "SKIP source-instance gate: the declared-residuals register is archived "
        "out of this tree at egg export (transform:plans-archive strips "
        f"{REGISTER_REL} and leaves {ARCHIVE_MARKER_REL}); arms when the "
        "register is present",
        allow_module_level=True,
    )


# --------------------------------------------------------------------------
# register parsing
# --------------------------------------------------------------------------
def _fail(msg: str) -> "None":
    pytest.fail(msg + _HINT, pytrace=False)


@functools.lru_cache(maxsize=1)
def _register_text() -> str:
    path = ROOT / REGISTER_REL
    if not path.is_file():
        _fail(
            f"declared-residuals register MISSING: {REGISTER_REL} is not a file "
            f"under {ROOT}, and {ARCHIVE_MARKER_REL} is absent too — so this is "
            "a source tree that lost its register, not an egg export cut. "
            "Restore it (git checkout) rather than deleting this gate."
        )
    return path.read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _rows() -> tuple:
    """Parse the register into an ordered tuple of row dicts. Strict: any
    unparseable heading, unknown field, missing field, or empty value is a
    malformed register and fails LOUD rather than being skipped over."""
    lines = _register_text().splitlines()

    # Every h3 in the file must be a row heading — otherwise a stray "### Notes"
    # section would silently swallow the rows that follow it.
    for idx, line in enumerate(lines, 1):
        if ANY_H3_RE.match(line) and not ROW_HEADING_RE.match(line):
            _fail(
                f"{REGISTER_REL}:{idx}: h3 heading is not a row heading: "
                f"{line!r}. Rows are '### RES-nnn — <title>'; use ## or #### "
                "for prose sections."
            )

    starts = [i for i, line in enumerate(lines) if ROW_HEADING_RE.match(line)]
    if not starts:
        _fail(
            f"{REGISTER_REL} declares ZERO rows — an empty register is never "
            "green here. Either the file was gutted, or the row grammar "
            "changed without this gate."
        )

    rows = []
    for start in starts:
        # A row block ends at the NEXT heading of any level (or EOF) — prose
        # sections after the last row are not part of it.
        end = len(lines)
        for probe in range(start + 1, len(lines)):
            if HEADING_RE.match(lines[probe]):
                end = probe
                break
        heading = ROW_HEADING_RE.match(lines[start])
        row = {
            "id": heading.group(1),
            "title": heading.group(2).strip(),
            "heading_line": start + 1,
            "fields": {},
        }
        for offset, line in enumerate(lines[start + 1:end], start + 2):
            if not line.startswith("- **"):
                continue
            field = FIELD_RE.match(line)
            if not field:
                _fail(
                    f"{REGISTER_REL}:{offset}: malformed field line in "
                    f"{row['id']}: {line!r}. Expected '- **<Field>:** <value>'."
                )
            name = field.group("name").strip()
            value = field.group("value").strip()
            if name not in REQUIRED_FIELDS and name not in OPTIONAL_FIELDS:
                _fail(
                    f"{REGISTER_REL}:{offset}: {row['id']} carries unknown "
                    f"field {name!r}. Known: {list(REQUIRED_FIELDS)} "
                    f"(+ optional {list(OPTIONAL_FIELDS)})."
                )
            if name in row["fields"]:
                _fail(f"{REGISTER_REL}:{offset}: {row['id']} repeats {name!r}.")
            if not value:
                _fail(f"{REGISTER_REL}:{offset}: {row['id']} has empty {name!r}.")
            row["fields"][name] = value

        missing = [f for f in REQUIRED_FIELDS if f not in row["fields"]]
        if missing:
            _fail(
                f"{REGISTER_REL}:{row['heading_line']}: {row['id']} is missing "
                f"required field(s) {missing}."
            )

        status = row["fields"]["Status"]
        if status not in ALL_STATUSES:
            _fail(
                f"{REGISTER_REL}:{row['heading_line']}: {row['id']} status "
                f"{status!r} is not one of {sorted(ALL_STATUSES)}."
            )
        row["status"] = status
        row["cites"] = _parse_cites(row)
        row["anchor"] = _parse_anchor(row)
        rows.append(row)
    return tuple(rows)


def _parse_cites(row: dict) -> tuple:
    value = row["fields"]["Declared at"]
    spans = BACKTICK_RE.findall(value)
    if not spans:
        _fail(
            f"{REGISTER_REL}:{row['heading_line']}: {row['id']} 'Declared at' "
            "carries no `path:line` cite."
        )
    residue = BACKTICK_RE.sub("", value).replace(",", "").strip()
    if residue:
        _fail(
            f"{REGISTER_REL}:{row['heading_line']}: {row['id']} 'Declared at' "
            f"has prose outside the cites: {residue!r}. It must be only "
            "comma-separated `path:line` spans."
        )
    cites = []
    for span in spans:
        match = CITE_RE.match(span.strip())
        if not match:
            _fail(
                f"{REGISTER_REL}:{row['heading_line']}: {row['id']} cite "
                f"{span!r} is not '<repo-relative path>:<line>'."
            )
        rel, line = match.group("path"), int(match.group("line"))
        candidate = Path(rel)
        if candidate.is_absolute() or ".." in candidate.parts:
            _fail(
                f"{REGISTER_REL}:{row['heading_line']}: {row['id']} cite {rel!r} "
                "is not confined to the repo."
            )
        if line < 1:
            _fail(
                f"{REGISTER_REL}:{row['heading_line']}: {row['id']} cite {span!r} "
                "has a non-positive line number."
            )
        cites.append((rel, line))
    return tuple(cites)


def _parse_anchor(row: dict) -> str:
    spans = BACKTICK_RE.findall(row["fields"]["Anchor"])
    if len(spans) != 1 or not spans[0].strip():
        _fail(
            f"{REGISTER_REL}:{row['heading_line']}: {row['id']} 'Anchor' must be "
            "exactly one non-empty `backticked` substring of the cited line."
        )
    return spans[0]


# --------------------------------------------------------------------------
# tree sweep
# --------------------------------------------------------------------------
def _in_sweep_surface(rel: str) -> bool:
    parts = rel.split("/")
    if not parts or parts[0] not in SWEEP_ROOTS:
        return False
    if rel == SELF_REL:
        return False
    if any(part in SWEEP_SKIP_DIRS for part in parts):
        return False
    if any(rel == sub or rel.startswith(sub + "/") for sub in SWEEP_SKIP_SUBTREES):
        return False
    return Path(rel).suffix in SWEEP_EXTS


def _tracked_files() -> "list | None":
    """Repo-relative tracked paths, or None when git is unavailable.

    Tracked-only is the authoritative mode: the register governs what lands in
    commits, and a live instance carries gitignored runtime state under these
    same roots that must never make the gate machine-dependent.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            capture_output=True, text=True, check=False, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return [p for p in proc.stdout.split("\0") if p]


def _walked_files() -> list:
    """Filesystem fallback for a gitless tree (e.g. an egg export/clean hatch)."""
    found = []
    for root in SWEEP_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            found.append(path.relative_to(ROOT).as_posix())
    return found


def _scan(rels: "list") -> tuple:
    """(sites, files_read) — sites is a sorted tuple of (rel, lineno, text)."""
    sites = []
    files_read = 0
    for rel in sorted(set(rels)):
        if not _in_sweep_surface(rel):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        files_read += 1
        for lineno, line in enumerate(text.splitlines(), 1):
            if MARKER_RE.search(line):
                sites.append((rel, lineno, line.strip()))
    return tuple(sites), files_read


@functools.lru_cache(maxsize=1)
def _discovered() -> tuple:
    """((rel, lineno, text), ...), files_read, mode."""
    tracked = _tracked_files()
    if tracked is not None:
        sites, files_read = _scan(tracked)
        return sites, files_read, "git-tracked"
    sites, files_read = _scan(_walked_files())
    return sites, files_read, "filesystem-walk"


def _cited_line(rel: str, lineno: int) -> "str | None":
    path = ROOT / rel
    if not path.is_file():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    if lineno > len(lines):
        return None
    return lines[lineno - 1]


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------
def test_register_parses_and_is_not_empty():
    """Structure gate. A missing, empty or malformed register fails here."""
    rows = _rows()
    assert rows, "no rows parsed from the register"
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids)), f"duplicate row ids: {ids}"
    assert ids == sorted(ids), f"row ids must be in ascending order: {ids}"
    assert any(row["status"] in OPEN_STATUSES for row in rows), (
        "every row is retired — a register with no open row cannot be the "
        "program's list of what is not closed; if that is genuinely true, this "
        "gate should be retired by the Captain, not left vacuously green"
    )


def test_every_row_carries_a_retirement_condition():
    """A residual with no stated way to die is an assumption in waiting."""
    for row in _rows():
        retirement = row["fields"]["Retirement"]
        assert retirement.strip(), f"{row['id']}: empty retirement condition"
        assert len(retirement) >= 40, (
            f"{row['id']}: retirement condition is {len(retirement)} chars — "
            "too short to name what must land and what must be removed in the "
            f"same commit: {retirement!r}"
        )


def test_open_row_cites_still_resolve_to_their_declaration():
    """ROWS -> TREE. The cited file:line must exist and still carry the anchor."""
    checked = 0
    for row in _rows():
        if row["status"] not in OPEN_STATUSES:
            continue
        rel, lineno = row["cites"][0]
        line = _cited_line(rel, lineno)
        assert line is not None, (
            f"{row['id']}: cited declaration {rel}:{lineno} no longer exists "
            "(file missing or file shorter than the cited line). A row may not "
            "outlive its declaration: either the declaration moved (update the "
            "cite) or the residual was closed (flip the row to retired)."
        )
        assert row["anchor"] in line, (
            f"{row['id']}: {rel}:{lineno} no longer contains the anchor "
            f"{row['anchor']!r}. Line is: {line.strip()!r}. Update the cite if "
            "the declaration moved; flip the row to retired if it is closed."
        )
        for rel_extra, line_extra in row["cites"][1:]:
            assert _cited_line(rel_extra, line_extra) is not None, (
                f"{row['id']}: supporting cite {rel_extra}:{line_extra} no "
                "longer exists"
            )
        checked += 1
    assert checked, "no open rows were checked — see the emptiness gate"


def test_code_cites_sit_on_a_house_marker():
    """A declaration inside the sweep surface must use the surveyed word token,
    not prose — that is what keeps the TREE -> ROWS half enforceable."""
    for row in _rows():
        if row["status"] not in OPEN_STATUSES:
            continue
        for rel, lineno in row["cites"]:
            if not _in_sweep_surface(rel):
                continue
            line = _cited_line(rel, lineno)
            assert line is not None and MARKER_RE.search(line), (
                f"{row['id']}: {rel}:{lineno} is inside the sweep surface but "
                "carries no marker word token. Code declarations must use the "
                "surveyed form (bare/HONEST/KNOWN + the token) so the reverse "
                "direction can find them."
            )


def test_every_discovered_marker_is_registered():
    """TREE -> ROWS. A new residual cannot be declared without a row."""
    sites, files_read, mode = _discovered()
    assert files_read > 0, (
        f"sweep ({mode}) read ZERO files under {SWEEP_ROOTS} — the surface "
        "filter or the roots broke; this gate would be vacuous"
    )
    assert sites, (
        f"sweep ({mode}) found ZERO markers across {files_read} files. The tree "
        "carried 8 at a1357829, so either every declaration was closed (then "
        "retire the rows and this assertion together, deliberately) or the "
        "marker pattern broke"
    )
    registered = {
        cite
        for row in _rows()
        if row["status"] in OPEN_STATUSES
        for cite in row["cites"]
    }
    unregistered = [
        (rel, lineno, text)
        for rel, lineno, text in sites
        if (rel, lineno) not in registered and (rel, lineno) not in LEGACY_EXEMPT
    ]
    assert not unregistered, (
        "declared residual(s) with no register row:\n"
        + "\n".join(f"  {r}:{n}: {t}" for r, n, t in unregistered)
        + "\nAdd a '### RES-nnn' row in the SAME commit as the declaration."
    )


def test_registered_code_cites_are_discovered_by_the_sweep():
    """The two directions must agree on the same coordinates — a row citing a
    sweep-surface line the sweep does not see means the sweep has a hole."""
    sites, _, mode = _discovered()
    discovered = {(rel, lineno) for rel, lineno, _ in sites}
    for row in _rows():
        if row["status"] not in OPEN_STATUSES:
            continue
        for cite in row["cites"]:
            if not _in_sweep_surface(cite[0]):
                continue
            assert cite in discovered, (
                f"{row['id']} cites {cite[0]}:{cite[1]} inside the sweep "
                f"surface, but the {mode} sweep did not discover it — the "
                "surface filter excludes a path it should cover"
            )


def test_retired_rows_have_no_live_declaration():
    """Retiring a row means the declaration left the tree — otherwise the
    register would claim closed what the code still declares open."""
    sites, _, _ = _discovered()
    discovered = {(rel, lineno) for rel, lineno, _ in sites}
    for row in _rows():
        if row["status"] != RETIRED_STATUS:
            continue
        still_live = [c for c in row["cites"] if c in discovered]
        assert not still_live, (
            f"{row['id']} is marked retired but its declaration is still in the "
            f"tree at {still_live}. Delete the declaration in the same commit "
            "that retires the row."
        )


def test_legacy_exemptions_are_real_and_shrink_only():
    """The exemption list is an escape hatch, so it is itself pinned: each entry
    must still be a live marker line carrying its recorded text, and the list
    may only shrink."""
    assert len(LEGACY_EXEMPT) <= LEGACY_MAX, (
        f"LEGACY_EXEMPT grew to {len(LEGACY_EXEMPT)} (max {LEGACY_MAX}). A new "
        "declaration gets a register row, never an exemption."
    )
    sites, _, _ = _discovered()
    discovered = {(rel, lineno) for rel, lineno, _ in sites}
    for (rel, lineno), expected in LEGACY_EXEMPT.items():
        assert (rel, lineno) in discovered, (
            f"legacy exemption {rel}:{lineno} is no longer a marker site — "
            "delete the entry and lower LEGACY_MAX"
        )
        line = _cited_line(rel, lineno)
        assert line is not None and expected in line, (
            f"legacy exemption {rel}:{lineno} no longer reads {expected!r} "
            f"(line: {line!r}) — an exemption must not drift onto a different "
            "declaration"
        )
    registered = {
        cite for row in _rows() for cite in row["cites"]
    }
    overlap = sorted(set(LEGACY_EXEMPT) & registered)
    assert not overlap, (
        f"these sites are both exempted and registered: {overlap}. Pick one."
    )


def test_sweep_modes_agree_where_they_can():
    """The gitless fallback must cover at least what the tracked-file mode does,
    so an egg export or clean hatch never silently loses teeth."""
    if _tracked_files() is None:
        pytest.skip("no git work tree here — only the filesystem mode exists")
    git_sites, _ = _scan(_tracked_files())
    walk_sites, walk_files = _scan(_walked_files())
    assert walk_files > 0
    missing = sorted(set(git_sites) - set(walk_sites))
    assert not missing, (
        f"the filesystem-walk mode misses tracked marker sites: {missing}"
    )
