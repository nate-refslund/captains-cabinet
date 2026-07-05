"""Germline lockstep-consistency meta-test (FI-5 / SOV-9, spec
docs/plans/sovereign-build-spec-2026-07-04.md).

framework/policies/immutable-core.yml is THE single source of Ring-0 paths.
Four enforcement artifacts must stay in lockstep with it — historically they
drifted by hand-editing ("KEEP IN LOCKSTEP" comments were the only mechanism):

  germline-lock  cabinet/scripts/germline-lock.sh FILES/DIRS/SKIP bash arrays
  hook-s5        cabinet/scripts/hooks/pre-tool-use.sh §5 germline case arm
  hook-s5b      cabinet/scripts/hooks/pre-tool-use.sh §5b GERM_PATH_RE
  base-safety   framework/policies/base-safety.yml germline-readonly patterns

This test IS the mechanism now, in both directions:

  FORWARD  — every immutable-core entry is covered by each list its class
             requires (dir-prefix cover counts, so e.g. immutable-core.yml
             itself is covered via framework/policies/). Pairs an entry
             flags `pending:` are xfail(strict=False) — the mechanism for
             FUTURE additions (enumerate first, wire each list, delete the
             flag same-commit). As of the sovereign amendment (2026-07-05)
             every entry is fully wired and asserts hard; the cabinet-axes
             amendment (2026-07-05) added its set (trust_ladder.py,
             axes-allowlist.yml, axes-contract.md, the extension gate pair,
             trust-ladder.yml, posture-presets/) fully wired in the same
             change — no pending, every new entry asserts hard.
  REVERSE  — every atom found in each of the four lists maps back to an
             enumerated immutable-core entry, so no germline addition can
             bypass the single source.
  INVERSION — runtime_appended/hook_protected entries must NOT be
             filesystem-locked: schg on the sanctioned append files
             (captain-vetoes / action-lessons / needs-ledger) breaks the
             demotion + learning + needs loops (fail-safe plane).

All parsing is read-only text/data extraction — the shell artifacts are never
executed. Parse failures assert loudly (fail-toward-visible), never skip.
"""
from __future__ import annotations

import re
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]

IMMUTABLE_CORE = _REPO_ROOT / "framework" / "policies" / "immutable-core.yml"
GERMLINE_LOCK = _REPO_ROOT / "cabinet" / "scripts" / "germline-lock.sh"
PRE_TOOL_USE = _REPO_ROOT / "cabinet" / "scripts" / "hooks" / "pre-tool-use.sh"
BASE_SAFETY = _REPO_ROOT / "framework" / "policies" / "base-safety.yml"

LIST_NAMES = ("germline-lock", "hook-s5", "hook-s5b", "base-safety")
_XFAIL_REASON = "SOV-9b wires lists"
_CLASSES = ("files", "dirs", "runtime_appended", "hook_protected")


# ---------------------------------------------------------------------------
# parsers — read-only extraction from the four artifacts
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _core() -> dict:
    data = yaml.safe_load(IMMUTABLE_CORE.read_text())
    assert isinstance(data, dict), "immutable-core.yml did not parse to a mapping"
    return data


def _entries():
    """Yield (kind, path, pending) for every immutable-core entry."""
    for kind in _CLASSES:
        for e in _core().get(kind) or []:
            yield kind, e["path"], tuple(e.get("pending") or ())


@lru_cache(maxsize=1)
def _lock_arrays() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """FILES/DIRS/SKIP from germline-lock.sh — bash array literals as text.

    Comment lines inside the arrays carry no double-quoted strings, so
    extracting quoted tokens is exact.
    """
    text = GERMLINE_LOCK.read_text()
    out = []
    for name in ("FILES", "DIRS", "SKIP"):
        m = re.search(rf"^{name}=\((.*?)^\)", text, re.M | re.S)
        assert m, f"could not find {name}=(...) array in germline-lock.sh"
        vals = tuple(re.findall(r'"([^"]+)"', m.group(1)))
        assert vals, f"{name}=() parsed empty — germline-lock.sh format changed?"
        out.append(vals)
    return out[0], out[1], out[2]


@lru_cache(maxsize=1)
def _s5_alternatives() -> tuple[str, ...]:
    """The §5 germline case-arm glob alternatives, as repo-relative atoms.

    The arm is the single case-pattern line carrying the golden-evals
    contains-glob (SOV-9b appends entries to that same line). Dir atoms keep
    their trailing '/'; quoting and the *...* glob wrapping are stripped.
    """
    cands = [
        ln.strip()
        for ln in PRE_TOOL_USE.read_text().splitlines()
        if ln.strip().startswith("*")
        and ln.strip().endswith(")")
        and "memory/golden-evals/" in ln
    ]
    assert len(cands) == 1, (
        f"expected exactly one §5 germline case-arm line, found {len(cands)}"
    )
    atoms = []
    for raw in cands[0][:-1].split("|"):
        atom = raw.strip().lstrip("*").rstrip("*").strip('"')
        assert atom and "/" in atom, f"unparseable §5 case alternative: {raw!r}"
        atoms.append(atom)
    return tuple(atoms)


@lru_cache(maxsize=1)
def _s5b_regex() -> str:
    m = re.search(r"^\s*GERM_PATH_RE='([^']+)'", PRE_TOOL_USE.read_text(), re.M)
    assert m, "could not find GERM_PATH_RE='...' in pre-tool-use.sh §5b"
    return m.group(1)


@lru_cache(maxsize=1)
def _s5b_atoms() -> tuple[str, ...]:
    """Expand GERM_PATH_RE into literal path atoms (reverse direction).

    The RE's shape is a top-level alternation whose branches contain at most
    ONE single-level (a|b|c) group and \\-escaped literals. A branch outside
    that shape leaves parens in the atom and fails the reverse mapping loudly
    — extend this expander rather than loosening the mapping.
    """
    rex = _s5b_regex()
    branches, depth, cur = [], 0, []
    for ch in rex:
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "|" and depth == 0:
            branches.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    branches.append("".join(cur))
    atoms = []
    for br in branches:
        m = re.fullmatch(r"([^()]*)\(([^()]+)\)([^()]*)", br)
        parts = (
            [m.group(1) + g + m.group(3) for g in m.group(2).split("|")]
            if m
            else [br]
        )
        atoms.extend(re.sub(r"\\(.)", r"\1", p) for p in parts)
    return tuple(atoms)


@lru_cache(maxsize=1)
def _base_safety_patterns() -> tuple[str, ...]:
    data = yaml.safe_load(BASE_SAFETY.read_text())
    pats = [
        p
        for pol in data.get("policies", [])
        if pol.get("name") == "germline-readonly"
        for p in pol.get("path_patterns", [])
    ]
    assert pats, "germline-readonly policy (with path_patterns) not found in base-safety.yml"
    return tuple(pats)


# ---------------------------------------------------------------------------
# coverage semantics — one predicate per list, mirroring each list's matcher
# ---------------------------------------------------------------------------

def _covered(kind: str, path: str, lst: str) -> bool:
    if lst == "germline-lock":
        files, dirs, skip = _lock_arrays()
        if kind == "dirs":
            return path.rstrip("/") in {d.rstrip("/") for d in dirs}
        if kind == "runtime_appended":
            return path in skip
        # locked file: direct FILES entry, or nested under a locked DIRS entry
        return path in files or any(
            path.startswith(d.rstrip("/") + "/") for d in dirs
        )
    if lst == "hook-s5":
        # §5 semantics: *"dir/"* contains-matches, *"file" suffix-matches
        for alt in _s5_alternatives():
            if alt.endswith("/"):
                if alt in path:
                    return True
            elif path.endswith(alt):
                return True
        return False
    if lst == "hook-s5b":
        # §5b semantics: grep -E over the command string — search on the path
        return re.search(_s5b_regex(), path) is not None
    if lst == "base-safety":
        # policy-engine semantics: fnmatch after normalization; relative paths
        # retried as absolute — probe with a fake absolute prefix, and a probe
        # member file for dirs (contains-dir patterns end in /*)
        probe = "/x/" + path + ("PROBE" if kind == "dirs" else "")
        return any(fnmatchcase(probe, pat) for pat in _base_safety_patterns())
    raise AssertionError(f"unknown list {lst}")


def _required_lists(kind: str) -> tuple[str, ...]:
    # hook_protected entries are deliberately not lock-listed (deployment-
    # created Captain config) — the hook + typed-policy lists still must
    # carry them.
    if kind == "hook_protected":
        return ("hook-s5", "hook-s5b", "base-safety")
    return LIST_NAMES


# ---------------------------------------------------------------------------
# FORWARD — every immutable-core entry appears in each required list
# ---------------------------------------------------------------------------

def _forward_params():
    for kind, path, pending in _entries():
        for lst in _required_lists(kind):
            marks = (
                (pytest.mark.xfail(strict=False, reason=_XFAIL_REASON),)
                if lst in pending
                else ()
            )
            yield pytest.param(kind, path, lst, id=f"{lst}::{path}", marks=marks)


@pytest.mark.parametrize("kind,path,lst", _forward_params())
def test_immutable_core_entry_covered(kind, path, lst):
    assert _covered(kind, path, lst), (
        f"Ring-0 {kind} entry {path!r} is not covered by {lst} — the germline "
        f"lists must stay in lockstep with immutable-core.yml (wire the entry, "
        f"or mark it pending: [{lst}] if a later sub-lane owns the wiring)"
    )


# ---------------------------------------------------------------------------
# INVERSION SAFETY — the sanctioned-append plane must stay UNLOCKED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "kind,path",
    [
        pytest.param(k, p, id=f"{k}::{p}")
        for k, p, _ in _entries()
        if k in ("runtime_appended", "hook_protected")
    ],
)
def test_unlocked_classes_not_in_lock_lists(kind, path):
    """schg on a runtime-appended file breaks the demotion/learning/needs
    loops; a hook_protected config claims not-lock-listed. If one of these
    lands in germline-lock, either the lock is a regression or the entry's
    class in immutable-core.yml is stale — both must surface."""
    files, dirs, _skip = _lock_arrays()
    assert path not in files, f"{path} is {kind} but appears in germline-lock FILES"
    assert not any(path.startswith(d.rstrip("/") + "/") for d in dirs), (
        f"{path} is {kind} but is nested under a germline-lock DIRS entry"
    )


# ---------------------------------------------------------------------------
# REVERSE — no germline-list atom outside the single source
# ---------------------------------------------------------------------------

def _core_paths_by_kind() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {k: set() for k in _CLASSES}
    for kind, path, _pending in _entries():
        out[kind].add(path)
    return out


def _maps_to_core(atom: str) -> bool:
    """A list atom (dir atoms end '/', file atoms are repo-relative suffixes)
    maps to some enumerated immutable-core path."""
    by_kind = _core_paths_by_kind()
    if atom.endswith("/"):
        return any(
            d == atom or d.endswith("/" + atom) for d in by_kind["dirs"]
        )
    all_paths = set().union(*by_kind.values())
    return any(p == atom or p.endswith("/" + atom) for p in all_paths)


def test_reverse_germline_lock_files_enumerated():
    files, _dirs, _skip = _lock_arrays()
    core_files = _core_paths_by_kind()["files"]
    missing = [f for f in files if f not in core_files]
    assert not missing, (
        f"germline-lock FILES entries missing from immutable-core.yml files: {missing}"
    )


def test_reverse_germline_lock_dirs_enumerated():
    _files, dirs, _skip = _lock_arrays()
    core_dirs = {d.rstrip("/") for d in _core_paths_by_kind()["dirs"]}
    missing = [d for d in dirs if d.rstrip("/") not in core_dirs]
    assert not missing, (
        f"germline-lock DIRS entries missing from immutable-core.yml dirs: {missing}"
    )


def test_reverse_germline_lock_skip_enumerated():
    _files, _dirs, skip = _lock_arrays()
    core_ra = _core_paths_by_kind()["runtime_appended"]
    missing = [s for s in skip if s not in core_ra]
    assert not missing, (
        f"germline-lock SKIP entries missing from immutable-core.yml "
        f"runtime_appended: {missing}"
    )


def test_reverse_hook_s5_atoms_enumerated():
    missing = [a for a in _s5_alternatives() if not _maps_to_core(a)]
    assert not missing, (
        f"§5 germline case-arm atoms missing from immutable-core.yml: {missing}"
    )


def test_reverse_hook_s5b_atoms_enumerated():
    missing = [a for a in _s5b_atoms() if not _maps_to_core(a)]
    assert not missing, (
        f"§5b GERM_PATH_RE atoms missing from immutable-core.yml: {missing} "
        f"(parens left in an atom mean the expander needs extending)"
    )


def test_reverse_base_safety_patterns_enumerated():
    unmapped = []
    for pat in _base_safety_patterns():
        if pat.startswith("*/") and pat.endswith("/*"):
            frag = pat[2:-1]  # contains-dir: */golden-evals/* -> golden-evals/
        elif pat.startswith("*") and not pat.endswith("*"):
            frag = pat[1:]  # ends-with: *cabinet/mcp-scope.yml
        else:
            unmapped.append(f"{pat} (unrecognized pattern shape)")
            continue
        if not _maps_to_core(frag):
            unmapped.append(pat)
    assert not unmapped, (
        f"base-safety germline-readonly patterns missing from "
        f"immutable-core.yml: {unmapped}"
    )


# ---------------------------------------------------------------------------
# schema sanity — the single source itself stays well-formed
# ---------------------------------------------------------------------------

def test_schema_version_and_list_vocabulary():
    core = _core()
    assert core.get("version") == 1
    assert tuple(core.get("lists") or ()) == LIST_NAMES, (
        "immutable-core.yml lists: must match the meta-test's list vocabulary"
    )


def test_schema_entries_well_formed():
    seen: set[str] = set()
    for kind, path, pending in _entries():
        assert isinstance(path, str) and path, f"bad path in {kind}: {path!r}"
        assert not path.startswith("/"), f"{path}: paths are repo-relative"
        assert ".." not in path and "//" not in path, f"{path}: not normalized"
        if kind == "dirs":
            assert path.endswith("/"), f"dir entry {path} must end with '/'"
        else:
            assert not path.endswith("/"), f"{kind} entry {path} must not end with '/'"
        assert path not in seen, f"duplicate immutable-core entry: {path}"
        seen.add(path)
        assert set(pending) <= set(LIST_NAMES), (
            f"{path}: pending names unknown lists {set(pending) - set(LIST_NAMES)}"
        )
        assert set(pending) <= set(_required_lists(kind)), (
            f"{path}: pending names a list its class does not require"
        )


def test_schema_entry_keys_closed():
    for kind in _CLASSES:
        for e in _core().get(kind) or []:
            assert set(e) <= {"path", "pending"}, (
                f"unknown keys on {e.get('path')!r}: {set(e) - {'path', 'pending'}}"
            )


# Captain-locked attestation configs (FI-1/FI-2) — DEPLOYMENT-created at apply
# time (§8 step 5), locked in step 7. Enumerated + fully list-wired BEFORE they
# exist so the boundary arms the moment they land; the exists-on-disk typo
# guard therefore exempts exactly these (germline-lock lock prints
# "skip (absent)" for them until the deployment creates them). The live
# rung-grant file (cabinet-axes 2026-07-05) is the same class: born at the
# first Captain `grant rung`, files-class because rung grants MINT authority
# (a forged row lifts verdicts); its .example sibling stays unlocked.
_DEPLOYMENT_CREATED = frozenset({
    "instance/config/posture.yml",
    "instance/config/standing-grants.yml",
    "instance/config/trust-ladder.yml",
})

# Runtime-created root-consumed data plane (SOV-9a): the gate-apply watch
# ledger is born at the first Captain-armed apply. It is files-class (its
# rows become the root daemon's `git apply -R` revert plans — forging one
# mints a root write, so the sanctioned-append rationale does not hold) and
# is enumerated + fully list-wired BEFORE it exists, exactly like the
# attestation configs above.
_RUNTIME_CREATED = frozenset({
    "shared/interfaces/gate-apply-watch.jsonl",
})


def test_wired_locked_entries_exist_on_disk():
    """Typo guard: an entry claiming to be fully wired (no pending) in the
    locked classes must exist — germline-lock silently skips absent paths, so
    a misspelled path would otherwise 'pass' every list forever.
    runtime_appended / hook_protected are runtime- or deployment-created and
    exempt (as are the enumerated-before-existence attestation configs and
    the runtime-created watch ledger); pending entries are built by later
    lanes."""
    for kind, path, pending in _entries():
        if (kind not in ("files", "dirs") or pending
                or path in _DEPLOYMENT_CREATED | _RUNTIME_CREATED):
            continue
        target = _REPO_ROOT / path.rstrip("/")
        assert target.exists(), f"wired {kind} entry {path} does not exist on disk"
        if kind == "dirs":
            assert target.is_dir(), f"wired dirs entry {path} is not a directory"


# ---------------------------------------------------------------------------
# COMPLETENESS — root-executed / authority-minting lanes must be enumerated
# ---------------------------------------------------------------------------

# The FORWARD/REVERSE tests above prove CONSISTENCY with immutable-core.yml,
# never COMPLETENESS of it — a path omitted from the single source is
# structurally invisible to them (exactly how gate-apply.sh shipped
# officer-writable while root executes it — SOV-9a). This curated set names
# every artifact that RUNS AS ROOT (sudo entrypoint or LaunchDaemon), is
# CONSUMED BY a root executor, or MINTS AUTHORITY; each must appear in
# immutable-core.yml, which the lockstep tests then force into all four
# germline lists. Adding such a lane means adding it HERE in the same commit.
_ROOT_EXECUTED_OR_AUTHORITY_MINTING = (
    "cabinet/scripts/germline-lock.sh",     # sudo — sets/clears the boundary itself
    "cabinet/scripts/grant-apply.sh",       # sudo — mints standing grants (D7)
    "cabinet/scripts/gate-apply.sh",        # sudo + root daemon — germline code apply (D15)
    "cabinet/launchd/com.cabinet.gate-apply.plist",  # root LaunchDaemon definition
    "shared/interfaces/gate-apply-watch.jsonl",  # rows become cmd_watch's root `git apply -R`
    "instance/config/posture.yml",          # Captain-signed posture selection (FI-1)
    "instance/config/standing-grants.yml",  # Captain-signed ceiling grants (FI-2)
    # cabinet-axes (2026-07-05): Captain-granted rung ladder — each row LIFTS
    # a cell's verdict (propose_only → … → auto), i.e. mints authority.
    "instance/config/trust-ladder.yml",
)


def _all_core_paths() -> set[str]:
    return set().union(*_core_paths_by_kind().values())


@pytest.mark.parametrize("path", _ROOT_EXECUTED_OR_AUTHORITY_MINTING)
def test_completeness_root_lane_enumerated(path):
    assert path in _all_core_paths(), (
        f"{path} runs as root / feeds a root executor / mints authority but "
        f"is not enumerated in immutable-core.yml — an officer write to it "
        f"becomes root execution or forged authority; enumerate it (the "
        f"lockstep tests then force it into all four germline lists)"
    )


def test_completeness_launchdaemon_plists_enumerated():
    """Mechanical sweep behind the curated list: a plist that installs to
    /Library/LaunchDaemons runs its ProgramArguments as ROOT — every such
    definition must be Ring-0 AND named in the curated set above (so the
    set cannot rot silently). LaunchAgents run as the officer uid and are
    out of scope."""
    daemons = [
        p for p in sorted((_REPO_ROOT / "cabinet" / "launchd").glob("*.plist"))
        if "LaunchDaemons" in p.read_text(errors="ignore")
    ]
    assert daemons, "expected at least the gate-apply root daemon plist"
    for plist in daemons:
        rel = plist.relative_to(_REPO_ROOT).as_posix()
        assert rel in _all_core_paths(), (
            f"root LaunchDaemon {rel} is not enumerated in immutable-core.yml"
        )
        assert rel in _ROOT_EXECUTED_OR_AUTHORITY_MINTING, (
            f"root LaunchDaemon {rel} missing from the curated allowlist in "
            f"this test — add it in the same commit"
        )
