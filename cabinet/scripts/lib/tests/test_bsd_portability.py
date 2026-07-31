"""GNU-only shell primitives, in code that runs on a BSD userland.

WHY THIS FILE EXISTS. Fifteen `sed -i` config writes in the dashboard, seven
more in `create-officer.sh`, two bare `timeout` calls, a `grep -P` inside a test
assertion and a `date -d` with no fallback had all been shipped, and every one of
them was DEAD on the only machine this system is deployed to. Measured on that
machine (Darwin 25.6.0, arm64, `/usr/bin/sed`, no Homebrew coreutils, launchd
PATH `/usr/gnu/bin:/usr/local/bin:/bin:/usr/bin:.`):

    sed -i 's/a/b/' f      -> sed: 1: "f\\n": invalid command code f   exit 1, unchanged
    timeout 1 true         -> command not found                        exit 127
    gtimeout               -> absent
    grep -P 'x'            -> grep: invalid option -- P                exit 2
    stat -c %s f           -> stat: illegal option -- c                exit 1
    date -d '1 day ago'    -> date: illegal option -- d                exit 1
    find . -printf '%p'    -> find: -printf: unknown primary or operator

WHY NOTHING CAUGHT IT. CI runs on ubuntu, where every one of those works. The
shell jobs that touch these scripts run `bash -n` — a SYNTAX check, which never
executes a single one of them — and the two jobs that do execute run on GNU. So
the CI signal was not weak, it was pointed at a different userland from the
deployment, which is this programme's most-repeated defect class: the sensor
measuring something other than the control.

A STATIC SCAN IS THEREFORE THE RIGHT SHAPE. It is the one check that gives the
same answer on the ubuntu runner as on the Mac, because it reads the source
rather than running it.

THE ALLOWLIST IS EXACT, IN BOTH DIRECTIONS. A hit that is not listed fails, and
a listed entry that no longer matches anything ALSO fails. A one-directional
allowlist rots into a list of things that used to be true, and a "completeness"
claim that cannot detect removal from the set it checks is a defect this
programme has found in its own gates more than once.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
ALLOWLIST = Path(__file__).resolve().parent / "bsd-portability-allowlist.txt"

# ---------------------------------------------------------------------------
# What to scan.
# ---------------------------------------------------------------------------
# Anything that can be executed by the launchd/tmux/Node processes on the Mac.
# `.github/workflows/**` is EXCLUDED on purpose: those jobs run on ubuntu, where
# GNU is not merely allowed but correct.

SCAN_DIRS = ("cabinet", "framework", "instance", "presets", "tests")
SHELL_SUFFIXES = (".sh", ".bash")
TS_SUFFIXES = (".ts", ".tsx")
EXCLUDE_PARTS = (
    ".github/workflows/",
    "node_modules/",
    "/.next/",
    "cabinet/scripts/lib/tests/bsd-portability-allowlist.txt",
)


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z", *SCAN_DIRS],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files: list[Path] = []
    for rel in out.split("\0"):
        if not rel or any(part in rel for part in EXCLUDE_PARTS):
            continue
        p = REPO / rel
        if not p.is_file():
            continue
        if p.suffix in SHELL_SUFFIXES or p.suffix in TS_SUFFIXES:
            files.append(p)
        elif p.suffix == "" and _has_shell_shebang(p):
            files.append(p)
    return files


def _has_shell_shebang(p: Path) -> bool:
    try:
        with p.open("rb") as fh:
            first = fh.readline(128)
    except OSError:
        return False
    return first.startswith(b"#!") and (b"sh" in first)


# ---------------------------------------------------------------------------
# Stripping comments is load-bearing.
# ---------------------------------------------------------------------------
# Every one of these primitives is DISCUSSED in a docstring somewhere in this
# repo — including in this file — and a scanner that cannot tell prose from a
# command would either be permanently red or have to allowlist its own
# explanation, which is how a gate ends up asserting nothing.

_TS_BLOCK = re.compile(r"/\*.*?\*/", re.S)


def code_lines(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix in TS_SUFFIXES:
        # Blank out block comments while PRESERVING newlines, so line numbers
        # still point at the real line.
        text = _TS_BLOCK.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    out: list[tuple[int, str]] = []
    pending: str | None = None
    pending_line = 0
    for n, raw in enumerate(text.split("\n"), start=1):
        stripped = raw.strip()
        if not stripped and pending is None:
            continue
        if path.suffix in TS_SUFFIXES:
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            raw = raw.split("//")[0] if "//" in raw and "://" not in raw else raw
        elif stripped.startswith("#") and pending is None:
            continue
        # JOIN BACKSLASH CONTINUATIONS. A `date -d ... \` whose BSD fallback is
        # on the next physical line is ONE command, and a per-physical-line
        # scanner reports it as unpaired — the scanner would then be measuring
        # something other than the thing it is checking, which is the defect
        # class this whole file exists for. Found while writing it: six of the
        # repo's CORRECT fallbacks were flagged.
        if path.suffix not in TS_SUFFIXES and stripped.endswith("\\"):
            piece = raw.rstrip()[:-1]
            if pending is None:
                pending, pending_line = piece, n
            else:
                pending += " " + piece.strip()
            continue
        if pending is not None:
            out.append((pending_line, pending + " " + raw.strip()))
            pending = None
            continue
        out.append((n, raw))
    if pending is not None:
        out.append((pending_line, pending))
    return out


# ---------------------------------------------------------------------------
# The primitives. Each one was PROBED on the deployment machine.
# ---------------------------------------------------------------------------

Rule = tuple[str, re.Pattern[str], str]

RULES: list[Rule] = [
    (
        "sed-i",
        re.compile(r"(?<![\w-])sed\b[^\n|;&]*?\s-i(?![\w.])"),
        "BSD sed takes the in-place suffix as a MANDATORY argument: `sed -i <script> f` "
        "reads the script as the suffix and the filename as the script, exits 1 and "
        "changes nothing. `sed -i ''` breaks the other way on GNU. Read the file, "
        "transform it, write it back (shell: awk + temp + mv; TypeScript: lib/config-write.ts).",
    ),
    (
        "bare-timeout",
        re.compile(r"(?<![\w./-])g?timeout\s+[0-9]"),
        "macOS ships NEITHER `timeout` NOR `gtimeout`; the call exits 127 before the "
        "command starts, and a trailing `|| true` swallows it. Use the `run_bounded` "
        "shape (command -v guard + background/poll/kill) — cabinet/scripts/hooks/on-session-end.sh.",
    ),
    (
        "grep-P",
        re.compile(r"(?<![\w-])grep\s+(?:-\w*\s+)*-\w*P\b"),
        "BSD grep has no -P; it exits 2, so a `&& yes || no` idiom silently answers "
        "'no' and the assertion becomes vacuous. Use -E, or awk.",
    ),
    (
        "find-printf",
        re.compile(r"(?<![\w-])find\s[^\n|;&]*\s-(?:printf|regextype)\b"),
        "GNU find only. BSD find fails with 'unknown primary or operator'.",
    ),
    (
        "head-negative",
        re.compile(r"(?<![\w-])head\s+-n\s+-\d"),
        "GNU head only; BSD head rejects a negative line count.",
    ),
    (
        "gnu-long-flags",
        re.compile(
            r"(?<![\w-])(?:du\s+[^\n|;&]*-b\b|install\s+[^\n|;&]*-D\b"
            r"|cp\s+[^\n|;&]*--parents|chmod\s+[^\n|;&]*--reference"
            r"|chown\s+[^\n|;&]*--reference|xargs\s+[^\n|;&]*-d[\s,]"
            r"|tar\s+[^\n|;&]*--(?:transform|wildcards))"
        ),
        # `base64 -w0`, `xargs -r`, `sed -E`/`-r`, `sort -V`, `date +%s%N`,
        # `readlink -f` and `md5sum`/`sha256sum` are NOT in this list: each was
        # probed on the deployment machine and WORKS there (macOS 26 ships a
        # FreeBSD base64 with -w, and /sbin/*sum exist). A rule for a primitive
        # that is not actually broken here is noise, and noise is how a gate
        # gets an allowlist entry instead of a fix.
        "GNU-only flag; the BSD tool either rejects it or means something else.",
    ),
]

# These two are only a defect when the OTHER dialect's leg is missing, so they
# are checked per-line rather than by presence alone.
UNPAIRED: list[Rule] = [
    (
        "date-d-unpaired",
        re.compile(r"(?<![\w-])date\s+(?:-\w+\s+)*-d\b"),
        "BSD date has no -d. Pair it with a `|| date -u -j -f ...` leg on the same "
        "command, or probe the capability first.",
    ),
    (
        "stat-c-unpaired",
        re.compile(r"(?<![\w-])stat\s+(?:-\w+\s+)*-c\b"),
        "BSD stat has no -c. Pair it with a `|| stat -f ...` leg on the same command.",
    ),
]

# The trap that hides in a fallback chain rather than in a single call.
BSD_FIRST_STAT = re.compile(r"stat\s+-f\b[^\n]*\|\|[^\n]*stat\s+-c\b")
BSD_FIRST_REASON = (
    "BSD-FIRST `stat -f ... || stat -c ...`: on GNU coreutils `stat -f` means "
    "'file system' and SUCCEEDS, printing a mount point, so the `||` never fires "
    "and that string reaches the caller. GNU first is the only order that is right "
    "on both — `stat -c` simply fails on BSD."
)


# The BSD leg can be spelled several ways, and a check that only knew one of
# them flagged six correct fallbacks in this repo.
_BSD_DATE_LEG = re.compile(r"date\s+(?:-\w+\s+)*-[jvr]\b")
_BSD_STAT_LEG = re.compile(r"stat\s+(?:-\w+\s+)*-f\b")


def _has_other_dialect_leg(rule_id: str, line: str) -> bool:
    """True when the same command already carries the other dialect's leg.

    A capability PROBE counts too: `if date -u -d ... >/dev/null 2>&1; then`
    asks whether the flag exists before relying on it, which is the strongest
    form of the pairing and the shape `audit-framework-backlog-drift.sh` uses.
    """
    if re.search(r"^\s*(?:el)?if\s+.*>/dev/null 2>&1\s*;?\s*then", line):
        return True
    if rule_id.startswith("date"):
        return bool(_BSD_DATE_LEG.search(line))
    return bool(_BSD_STAT_LEG.search(line))


def scan() -> list[tuple[str, str, int, str]]:
    """Every hit as (rule_id, repo-relative path, line number, line)."""
    hits: list[tuple[str, str, int, str]] = []
    for path in tracked_files():
        rel = str(path.relative_to(REPO))
        for lineno, line in code_lines(path):
            for rule_id, pattern, _ in RULES:
                if pattern.search(line):
                    hits.append((rule_id, rel, lineno, line.strip()))
            for rule_id, pattern, _ in UNPAIRED:
                if not pattern.search(line):
                    continue
                if _has_other_dialect_leg(rule_id, line):
                    continue
                hits.append((rule_id, rel, lineno, line.strip()))
            if BSD_FIRST_STAT.search(line):
                hits.append(("bsd-first-stat", rel, lineno, line.strip()))
    return hits


def load_allowlist() -> dict[tuple[str, str], str]:
    """(rule_id, path) -> reason. Line numbers are deliberately NOT keys."""
    allowed: dict[tuple[str, str], str] = {}
    if not ALLOWLIST.exists():
        return allowed
    for raw in ALLOWLIST.read_text(encoding="utf-8").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("::")]
        assert len(parts) == 3, f"malformed allowlist row (want `path :: rule :: reason`): {raw}"
        path, rule_id, reason = parts
        assert reason, f"an allowlist row with no reason is not an allowlist row: {raw}"
        allowed[(rule_id, path)] = reason
    return allowed


REASONS = {rule_id: reason for rule_id, _, reason in RULES + UNPAIRED}
REASONS["bsd-first-stat"] = BSD_FIRST_REASON


def test_no_unlisted_gnu_only_primitive_in_code_that_runs_on_bsd() -> None:
    hits = scan()
    allowed = load_allowlist()
    unlisted = [h for h in hits if (h[0], h[1]) not in allowed]
    if unlisted:
        lines = [
            f"  {path}:{lineno}  [{rule_id}]  {text}\n      {REASONS[rule_id]}"
            for rule_id, path, lineno, text in sorted(unlisted)
        ]
        pytest.fail(
            "GNU-only shell primitives in code that runs on the BSD deployment:\n"
            + "\n".join(lines)
            + "\n\nFix them, or add a row to "
            + str(ALLOWLIST.relative_to(REPO))
            + " with the reason it is safe.",
        )


def test_allowlist_has_no_stale_rows() -> None:
    """The other direction, which is the half an allowlist usually forgets."""
    present = {(rule_id, path) for rule_id, path, _, _ in scan()}
    stale = sorted(key for key in load_allowlist() if key not in present)
    if stale:
        pytest.fail(
            "allowlist rows that no longer match anything — the code was fixed and the "
            "exemption outlived it:\n"
            + "\n".join(f"  {path} :: {rule_id}" for rule_id, path in stale)
        )


def test_the_scanner_actually_detects_each_primitive(tmp_path: Path) -> None:
    """The arm that makes the two above mean something.

    A scanner is a sensor, and a sensor nobody has tried to defeat is an
    assumption. Each rule is fired against a line that must match and a line that
    must not, so a regex that has quietly stopped matching — the `\\s`-in-POSIX-ERE
    class of defect — fails HERE rather than by going silently green upstream.
    """
    must_match = {
        "sed-i": "sed -i 's/a/b/' file.yml",
        "bare-timeout": "timeout 10s bash relay.sh || true",
        "grep-P": "grep -P '^\\t' file.yml",
        "find-printf": "find . -name '*.md' -printf '%p\\n'",
        "head-negative": "head -n -1 file.txt",
        "gnu-long-flags": "du -b payload.bin",
        "date-d-unpaired": 'EPOCH=$(date -d "$TS" +%s 2>/dev/null || echo 0)',
        "stat-c-unpaired": 'M=$(stat -c %Y "$f" 2>/dev/null || echo 0)',
        "bsd-first-stat": 'M=$(stat -f %m "$f" || stat -c %Y "$f" || echo 0)',
    }
    must_not_match = [
        "sed -i '' 's/a/b/' file.yml" if False else "sed -E 's/(a)(b)/\\2\\1/' f",
        "run_bounded 10 bash relay.sh || true",
        "grep -E '^[0-9]+' file.yml",
        "find . -name '*.md' -maxdepth 2",
        "head -n 1 file.txt",
        "du -h payload.bin",
        "base64 -w0 < payload.bin",
        'EPOCH=$(date -d "$TS" +%s 2>/dev/null || date -u -j -f "%Y" "$TS" +%s || echo 0)',
        'M=$(stat -c %Y "$f" 2>/dev/null || stat -f %m "$f" 2>/dev/null || echo 0)',
    ]

    def hits_for(text: str) -> set[str]:
        script = tmp_path / "probe.sh"
        script.write_text("#!/bin/bash\n" + text + "\n", encoding="utf-8")
        found: set[str] = set()
        for _, line in code_lines(script):
            for rule_id, pattern, _reason in RULES + UNPAIRED:
                if not pattern.search(line):
                    continue
                if rule_id.endswith("-unpaired") and _has_other_dialect_leg(rule_id, line):
                    continue
                found.add(rule_id)
            if BSD_FIRST_STAT.search(line):
                found.add("bsd-first-stat")
        return found

    for rule_id, sample in must_match.items():
        assert rule_id in hits_for(sample), f"rule {rule_id} did not fire on: {sample}"
    for sample in must_not_match:
        assert not hits_for(sample), f"a portable line was flagged: {sample} -> {hits_for(sample)}"

    # A comment is prose, not a command. This one exists because every primitive
    # above is discussed in a docstring in this repo, including in this file.
    assert not hits_for("# we used to run sed -i on the config here"), "a comment was scanned"
