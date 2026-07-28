"""Pin the declared-residuals register to the tree, both directions.

docs/plans/declared-residuals-register.md is the single surface listing what
the program KNOWS it has not closed. It is only worth having if it cannot
drift from the code, so this module binds the two halves:

  ROWS -> TREE   every row's cited ANCHOR TEXT still resolves, in the file it
                 names, to exactly one line (a row cannot outlive its
                 declaration).
  TREE -> ROWS   every marker discovered in the sweep surface has a row (a NEW
                 residual cannot be declared without registering it).

CITES ARE ANCHOR-RESOLVED, NOT LINE-PINNED (2026-07-28). Rows cite a PATH plus
an anchor; this module locates the declaration by searching the file for the
anchor and derives the line number itself. It fails when the anchor matches
ZERO lines (the declaration was deleted, moved out of the file, or the artifact
was replaced) and equally when it matches MORE THAN ONE (a cite that resolves
to two places is not a cite). Insertions ABOVE a declaration are a no-op, which
is the whole point of the change.

WHY IT CHANGED, since the line number looked like free precision. RES-007 cites
shared/interfaces/reviews/cognitive-core-phase-4-review.md, a digest-bound
FROZEN artifact that cannot be edited in place: every re-bind ceremony appends
a note ABOVE its findings table, so the cited P1 row stays byte-identical and
moves down. The chain that forces those re-binds is structural — the
framework_production_noncomment_lines budget is zero-headroom, so any framework
production line needs a row in cabinet/config/cognitive-architecture-contract.yml,
which sits in COG-4's restore_from_baseline scope, so every framework landing
re-binds the digest. That cite was hand-re-pointed TWELVE times
(:233 -> :320 -> :362 -> :434 -> :454 -> :466 -> :477 -> :485 -> :494 -> :501
-> :509 -> :543 -> :569/:577 -> :667), three of them inside one day, each one a
red CI job and a commit; the register's own note predicted every occurrence and
proposed this fix twice. The same tax hit the legacy-exemption list (line-keyed
as LEGACY_EXEMPT until this change, LEGACY_EXEMPT_ANCHORS now), re-anchored six times
by unrelated manifest rows landing above its two sites. Both are keyed by
anchor now. The re-bind ceremony itself is untouched and still required — it
just no longer moves anything here.

A `path:line` cite is REFUSED at parse time rather than tolerated, so the tax
cannot be reintroduced by a future row copying an old one.

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
from typing import NamedTuple

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
# ANCHOR-KEYED, like the register's cites and for the same reason. These two
# entries were line-keyed until 2026-07-28 and had been hand-re-anchored SIX
# times (233 -> 235 -> 242 -> 248 -> 258 -> 267 -> 283 and 653 -> 658 -> 669 ->
# 680 -> 696 -> 705 -> 722) by unrelated manifest rows landing above them — the
# egg egress-default flip, the captain-availability dial, the captain-dates
# store, the world-art delete row, the expansion registry, the
# recipient-exclusions delete row. The marker TEXT never changed once. Each
# anchor is the FULL comment line, not the bare "RESIDUAL SCRUB" token, because
# that token appears at both sites and an ambiguous anchor is refused.
LEGACY_EXEMPT_ANCHORS = (
    ("cabinet/scripts/egg-export-manifest.txt",
     "RESIDUAL SCRUB (2026-07-21, per 2026-07-07 full-autonomy grant — publish-gate"),
    ("cabinet/scripts/egg-export-manifest.txt",
     "RESIDUAL SCRUB (2026-07-21): the three archived-out dated instance artifacts"),
)
LEGACY_MAX = 2

ROW_HEADING_RE = re.compile(r"^### (RES-\d{3})\s+[—-]\s+(\S.*)$")
ANY_H3_RE = re.compile(r"^### ")
HEADING_RE = re.compile(r"^#{1,6} ")
FIELD_RE = re.compile(r"^- \*\*(?P<name>[^*:]+):\*\* (?P<value>.+)$")
BACKTICK_RE = re.compile(r"`([^`]*)`")
CITE_RE = re.compile(r"^(?P<path>[^\s`:]+)$")
# Refused, not tolerated: the format this module used until 2026-07-28.
LINE_PINNED_CITE_RE = re.compile(r"^(?P<path>[^\s`:]+):(?P<line>\d+)$")

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
        row["decls"] = _resolve_row(row)
        # Derived coordinates, for the halves that must agree on a line number.
        # A cite that did not resolve UNIQUELY contributes none, so it cannot
        # silently satisfy the TREE -> ROWS direction either.
        row["cites"] = tuple(
            (decl.rel, decl.hits[0]) for decl in row["decls"] if not decl.error
        )
        rows.append(row)
    return tuple(rows)


def _parse_paths(row: dict) -> tuple:
    """'Declared at' is comma-separated backticked repo-relative PATHS. No line
    numbers: the line is derived from the anchor (see the module docstring)."""
    value = row["fields"]["Declared at"]
    spans = BACKTICK_RE.findall(value)
    if not spans:
        _fail(
            f"{REGISTER_REL}:{row['heading_line']}: {row['id']} 'Declared at' "
            "carries no `path` cite."
        )
    residue = BACKTICK_RE.sub("", value).replace(",", "").strip()
    if residue:
        _fail(
            f"{REGISTER_REL}:{row['heading_line']}: {row['id']} 'Declared at' "
            f"has prose outside the cites: {residue!r}. It must be only "
            "comma-separated `path` spans."
        )
    paths = []
    for span in spans:
        span = span.strip()
        if LINE_PINNED_CITE_RE.match(span):
            _fail(
                f"{REGISTER_REL}:{row['heading_line']}: {row['id']} cite {span!r} "
                "is LINE-PINNED. Cites are resolved by anchor text now — drop "
                "the ':<line>' and keep the path. A line number is what made "
                "this register pay twelve hand re-points for one unchanged "
                "declaration; it is refused rather than tolerated."
            )
        if not CITE_RE.match(span):
            _fail(
                f"{REGISTER_REL}:{row['heading_line']}: {row['id']} cite "
                f"{span!r} is not a bare '<repo-relative path>'."
            )
        candidate = Path(span)
        if candidate.is_absolute() or ".." in candidate.parts:
            _fail(
                f"{REGISTER_REL}:{row['heading_line']}: {row['id']} cite {span!r} "
                "is not confined to the repo."
            )
        paths.append(span)
    return tuple(paths)


def _parse_anchors(row: dict) -> tuple:
    """'Anchor' is one backticked anchor PER path, in the same order. Each one
    locates its declaration on its own; there is no primary/supporting split,
    because a supporting cite checked only for existence is a sensor that
    passes on any file long enough."""
    value = row["fields"]["Anchor"]
    spans = [span.strip() for span in BACKTICK_RE.findall(value)]
    residue = BACKTICK_RE.sub("", value).replace(",", "").strip()
    if residue:
        _fail(
            f"{REGISTER_REL}:{row['heading_line']}: {row['id']} 'Anchor' has "
            f"prose outside the anchors: {residue!r}. It must be only "
            "comma-separated `backticked` substrings."
        )
    if not spans or not all(spans):
        _fail(
            f"{REGISTER_REL}:{row['heading_line']}: {row['id']} 'Anchor' must be "
            "one or more non-empty `backticked` substrings."
        )
    return tuple(spans)


class Decl(NamedTuple):
    """One authored cite plus what searching the tree for it found."""
    rel: str
    anchor: str
    hits: tuple   # every 1-based line number in `rel` containing `anchor`
    error: str    # "" iff exactly one hit


def _resolve_row(row: dict) -> tuple:
    paths = _parse_paths(row)
    anchors = _parse_anchors(row)
    if len(paths) != len(anchors):
        _fail(
            f"{REGISTER_REL}:{row['heading_line']}: {row['id']} cites "
            f"{len(paths)} path(s) but carries {len(anchors)} anchor(s). Every "
            "cite needs its OWN anchor, in the same order — a shared anchor "
            "would leave the extra cites unpinned."
        )
    return tuple(_resolve(rel, anchor) for rel, anchor in zip(paths, anchors))


@functools.lru_cache(maxsize=None)
def _file_lines(rel: str) -> "tuple | None":
    path = ROOT / rel
    if not path.is_file():
        return None
    try:
        return tuple(path.read_text(encoding="utf-8").splitlines())
    except (UnicodeDecodeError, OSError):
        return None


def _resolve(rel: str, anchor: str) -> Decl:
    """Locate `anchor` in `rel`. Exactly one line, or it is an error — zero
    means the declaration is gone, more than one means the cite is ambiguous
    and points at two places."""
    lines = _file_lines(rel)
    if lines is None:
        return Decl(rel, anchor, (), f"cited file {rel} is missing or unreadable")
    hits = tuple(no for no, line in enumerate(lines, 1) if anchor in line)
    if len(hits) == 1:
        return Decl(rel, anchor, hits, "")
    if not hits:
        return Decl(
            rel, anchor, hits,
            f"anchor {anchor!r} is ABSENT from {rel} — the declaration was "
            "deleted, reworded, or moved to another file. Re-point the cite if "
            "it moved; flip the row to retired if it is closed.",
        )
    return Decl(
        rel, anchor, hits,
        f"anchor {anchor!r} is AMBIGUOUS in {rel}: it matches {len(hits)} lines "
        f"{list(hits)}. A cite that resolves to two places is not a cite — "
        "lengthen the anchor until exactly one line carries it.",
    )


@functools.lru_cache(maxsize=1)
def _legacy_exempt_decls() -> tuple:
    return tuple(_resolve(rel, anchor) for rel, anchor in LEGACY_EXEMPT_ANCHORS)


def _legacy_exempt_coords() -> frozenset:
    """Only UNIQUELY-resolved exemptions count. An exemption that stopped
    resolving therefore stops exempting — the TREE -> ROWS half goes red on the
    site as well as this one, which is the fail-closed direction."""
    return frozenset(
        (decl.rel, decl.hits[0]) for decl in _legacy_exempt_decls() if not decl.error
    )


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
    """ROWS -> TREE. Every cite's anchor must resolve to EXACTLY ONE line in
    the file it names — absent is the row outliving its declaration, ambiguous
    is a cite pointing at two places. Insertions above it change nothing."""
    checked = 0
    problems = []
    for row in _rows():
        if row["status"] not in OPEN_STATUSES:
            continue
        for decl in row["decls"]:
            if decl.error:
                problems.append(f"  {row['id']}: {decl.error}")
            else:
                checked += 1
    assert not problems, (
        "register cite(s) that no longer resolve to a unique declaration:\n"
        + "\n".join(problems)
    )
    assert checked, "no open-row cites were checked — see the emptiness gate"


def test_code_cites_sit_on_a_house_marker():
    """A declaration inside the sweep surface must use the surveyed word token,
    not prose — that is what keeps the TREE -> ROWS half enforceable.

    NARROWED by the anchor change, stated rather than hidden: the line this
    checks is now DERIVED by searching for the anchor, and every in-sweep row's
    anchor happens to contain the marker token, so for those rows it is close
    to tautological. It is not vacuous — an anchor repointed to a unique line
    with no marker token turns it RED (proved at the landing review against
    framework/probes/verifier.py) — but its teeth now depend on anchor CHOICE
    rather than on an independently authored coordinate.
    """
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
    exempt = _legacy_exempt_coords()
    unregistered = [
        (rel, lineno, text)
        for rel, lineno, text in sites
        if (rel, lineno) not in registered and (rel, lineno) not in exempt
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
    register would claim closed what the code still declares open. Checked
    against the ANCHOR, not a coordinate: a retired row whose text is still
    anywhere in the cited file is red, including the ambiguous case a
    coordinate check would have waved through."""
    for row in _rows():
        if row["status"] != RETIRED_STATUS:
            continue
        still_live = [
            f"{decl.rel}:{list(decl.hits)} ({decl.anchor!r})"
            for decl in row["decls"] if decl.hits
        ]
        assert not still_live, (
            f"{row['id']} is marked retired but its declaration is still in the "
            f"tree at {still_live}. Delete the declaration in the same commit "
            "that retires the row."
        )


def test_legacy_exemptions_are_real_and_shrink_only():
    """The exemption list is an escape hatch, so it is itself pinned: each entry
    must still resolve to exactly one live marker line, and the list may only
    shrink."""
    assert len(LEGACY_EXEMPT_ANCHORS) <= LEGACY_MAX, (
        f"LEGACY_EXEMPT_ANCHORS grew to {len(LEGACY_EXEMPT_ANCHORS)} (max "
        f"{LEGACY_MAX}). A new declaration gets a register row, never an "
        "exemption."
    )
    assert len(set(LEGACY_EXEMPT_ANCHORS)) == len(LEGACY_EXEMPT_ANCHORS), (
        f"duplicate legacy exemption entries: {LEGACY_EXEMPT_ANCHORS}"
    )
    sites, _, _ = _discovered()
    discovered = {(rel, lineno) for rel, lineno, _ in sites}
    for decl in _legacy_exempt_decls():
        assert not decl.error, f"legacy exemption does not resolve: {decl.error}"
        coord = (decl.rel, decl.hits[0])
        assert coord in discovered, (
            f"legacy exemption {coord[0]}:{coord[1]} is no longer a marker "
            "site — delete the entry and lower LEGACY_MAX"
        )
    registered = {cite for row in _rows() for cite in row["cites"]}
    overlap = sorted(_legacy_exempt_coords() & registered)
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
