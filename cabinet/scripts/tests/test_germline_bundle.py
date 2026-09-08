"""Sensors for the phase-1 germline bundle (contract §7 + amendments A7.1-A7.4).

WHAT IS UNDER TEST. `docs/proposals/germline-amendment-employee-phase1-2026-09.md`
and its sibling directory are a set of PROPOSED bytes for two schg-locked files
plus `verify.sh`, the gate that answers — mechanically, against whatever bytes
are actually there — whether each diff still applies. Nothing in the package may
write a locked path, and the package is worthless the moment its diffs stop
matching the tree they describe. Both of those are what these arms measure.

HOW THEY ARE BUILT. `verify.sh` is executed, never re-implemented: the ceremony
and the sensor must not be able to describe different bundles, so the bundle
table is parsed OUT of `verify.sh` and the pass/fail verdict is `verify.sh`'s own
exit code. The one thing stood in for is the golden-eval stage, which needs a
Redis endpoint; `--checks-only` skips exactly that stage and says so on stdout.

THE DEGENERATE END, checked deliberately.
  * A drift arm builds a minimal root whose target bytes are neither the
    pre-image nor the post-image and proves `verify.sh` REFUSES (exit 10) — a
    gate that only ever sees a clean tree is a gate nobody has tried to defeat.
    Its control (the same root, unmutated) proves the refusal is about the
    mutation and not about the fixture.
  * The locked set is asserted non-degenerate before it is intersected with
    anything: an empty boundary makes every "touches no locked path" claim
    trivially true, which is the failure this file exists to prevent.
  * `test_phase1_touches_no_locked_path` FAILS when its base revision is
    unreachable (A7.3) instead of passing on a shallow checkout, and its own
    inverted arm drives an unresolvable base to prove the refusal fires.

Run: python3.12 -m pytest cabinet/scripts/tests/test_germline_bundle.py -q
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_SCRIPTS = _REPO / "cabinet" / "scripts"
_PKG = "germline-amendment-employee-phase1-2026-09"
_DOC = _REPO / "docs" / "proposals" / f"{_PKG}.md"
_BUNDLE = _REPO / "docs" / "proposals" / _PKG
_VERIFY = _BUNDLE / "verify.sh"
_LOCK_SH = _SCRIPTS / "germline-lock.sh"
_LEDGER = _REPO / "docs" / "plans" / "operative-egg-ledger-2026-07-07.yml"
_PLAN = _REPO / "docs" / "plans" / "operative-egg-plan-2026-07-07.md"

#: The ledger row this package is filed under.
ROW_ID = "CG-36"

#: The A13 id shape, verbatim from the A13 row's own gate command.
_A13_ID_RE = re.compile(r"^\| ([A-Z][A-Z0-9-]*[0-9-][A-Z0-9-]*) ", re.M)

#: A locked set smaller than this is a parser that lost the boundary, not a
#: cabinet with less to protect (germline-lock.sh carries ~90 FILES + 7 DIRS).
_MIN_LOCKED_ENTRIES = 50

sys.path.insert(0, str(_SCRIPTS / "lib"))
import update_bundle  # noqa: E402  (path set immediately above)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(root), capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def _locked() -> dict[str, list[str]]:
    locked = update_bundle.parse_locked_set(_LOCK_SH)
    total = len(locked["files"]) + len(locked["dirs"])
    assert total >= _MIN_LOCKED_ENTRIES, (
        f"the locked set parsed to {total} entries — a boundary this small is a "
        "parse failure, and every 'touches no locked path' claim below would be "
        "trivially true against it"
    )
    return locked


def _bundle_rows() -> list[tuple[str, str, str, str]]:
    """(id, target, post-image sha256, state) out of verify.sh's own table."""
    text = _VERIFY.read_text(encoding="utf-8")
    match = re.search(r'^BUNDLE_ROWS="\n(.*?)\n"\s*$', text, re.M | re.S)
    assert match, "could not find the BUNDLE_ROWS table in verify.sh"
    rows = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        assert len(parts) == 4, f"unparseable bundle row: {line!r}"
        rows.append(tuple(parts))  # type: ignore[arg-type]
    assert rows, "the bundle table parsed to zero rows"
    return rows


def _run_verify(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_VERIFY), "--repo", str(repo), "--checks-only"],
        capture_output=True,
        text=True,
    )


def _digest_locked_paths(root: Path) -> str:
    locked = _locked()
    paths: list[Path] = []
    for rel in locked["files"]:
        candidate = root / rel
        if candidate.is_file():
            paths.append(candidate)
    for rel in locked["dirs"]:
        directory = root / rel
        if directory.is_dir():
            paths.extend(p for p in sorted(directory.rglob("*")) if p.is_file())
    assert paths, "the locked set resolved to zero existing paths in this tree"
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return f"{digest.hexdigest()}:{len(paths)}"


def _minimal_root(tmp_path: Path) -> Path:
    """The smallest tree verify.sh can answer about: the boundary, its parser
    and the two targets. Used by the drift arm so a mutated fixture never has
    to be a copy of the whole repository."""
    root = tmp_path / "root"
    for rel in (
        "cabinet/scripts/germline-lock.sh",
        "cabinet/scripts/lib/update_bundle.py",
        *[row[1] for row in _bundle_rows()],
    ):
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPO / rel, dest)
    return root


def _locked_offenders(changed: list[str], locked: dict[str, list[str]]) -> list[str]:
    """The guard's whole predicate, factored out so it can be driven directly.

    The guard itself is green by construction on a branch that behaved, so the
    only way to know the predicate discriminates is to hand it paths it must
    flag and paths it must not.
    """
    return sorted(p for p in changed if update_bundle.is_locked(p, locked))


class BaseUnreachable(RuntimeError):
    """The guard could not resolve the revision it must diff against."""


def _resolve_base(root: Path, env: dict[str, str] | None = None) -> str:
    """The commit `test_phase1_touches_no_locked_path` diffs against.

    A7.3: this REFUSES rather than returning something wrong. A shallow
    checkout, a tree with no git at all, or a base ref that does not resolve
    each raise — because a guard that cannot see the diff it guards is a
    disabled sensor, not a pass.
    """
    env = os.environ if env is None else env
    if not _git(root, "rev-parse", "--git-dir", check=False):
        raise BaseUnreachable(
            f"{root} is not a git work tree; this guard compares two revisions "
            "and has nothing to compare without one"
        )
    if _git(root, "rev-parse", "--is-shallow-repository") == "true":
        raise BaseUnreachable(
            "shallow checkout: git's merge-base is not trustworthy past a "
            "shallow boundary, so this guard would diff against the wrong base. "
            "Give the job `fetch-depth: 0` or run `git fetch --unshallow`."
        )
    explicit = (env.get("CABINET_PHASE1_BASE") or "").strip()
    candidates = [explicit] if explicit else ["origin/master", "master"]
    for ref in candidates:
        sha = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}",
                   check=False)
        if not sha:
            continue
        base = _git(root, "merge-base", sha, "HEAD", check=False)
        if base:
            return base
    raise BaseUnreachable(
        f"none of {candidates} resolves to a commit with a merge-base against "
        "HEAD — fetch the base branch or set CABINET_PHASE1_BASE"
    )


# ---------------------------------------------------------------------------
# the bundle itself
# ---------------------------------------------------------------------------


def test_bundle_apparatus_present():
    """Doc, one diff per row, and a runnable gate."""
    assert _DOC.is_file(), f"amendment doc missing: {_DOC}"
    assert _VERIFY.is_file(), f"bundle gate missing: {_VERIFY}"
    assert os.access(_VERIFY, os.X_OK), "verify.sh is not executable"
    for row_id, target, _sha, _state in _bundle_rows():
        diff = _BUNDLE / f"{row_id}.diff"
        assert diff.is_file(), f"{row_id}: diff missing at {diff}"
        text = diff.read_text(encoding="utf-8")
        assert f"+++ b/{target}\n" in text, (
            f"{row_id}: the diff does not name {target} on its +++ line — the "
            "bundle table and the patch describe different files"
        )


def test_diffs_apply_to_current_locked_bytes():
    """§7: each diff applies cleanly to the CURRENT bytes (or is already at the
    target, which is what `landed-then-ceremonied` looks like from a clone)."""
    proc = _run_verify(_REPO)
    assert proc.returncode == 0, (
        f"verify.sh exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    )
    assert "BUNDLE VERIFY GREEN" in proc.stdout, proc.stdout
    for row_id, target, sha, _state in _bundle_rows():
        assert f"[verify] {row_id} OK" in proc.stdout, proc.stdout
        assert target in proc.stdout and sha in proc.stdout, proc.stdout


def _unique_context_line(diff_text: str, target_text: str) -> str:
    """A context line of the patch that occurs exactly once in the target.

    Mutating one of these is how a patch is made to stop applying; mutating
    anything else only changes the file the patch lands on.
    """
    for raw in diff_text.splitlines():
        if not raw.startswith(" "):
            continue
        line = raw[1:]
        if len(line.strip()) < 12:
            continue
        if target_text.count(line + "\n") == 1:
            return line
    raise AssertionError("no unique context line in the diff to mutate")


def test_drift_in_the_patch_context_is_a_refusal(tmp_path):
    """The inverted arm: bytes the patch no longer matches must REFUSE.

    Without this, `test_diffs_apply_to_current_locked_bytes` would be green in
    both directions — it would pass on a tree where the diffs are meaningless
    just as happily as on one where they are exact.
    """
    control = _minimal_root(tmp_path / "control")
    ok = _run_verify(control)
    assert ok.returncode == 0, (
        f"the unmutated fixture already fails, so the drift arm below would "
        f"prove nothing:\n{ok.stdout}\n{ok.stderr}"
    )

    drifted = _minimal_root(tmp_path / "drifted")
    row_id, target, _sha, _state = _bundle_rows()[0]
    victim = drifted / target
    body = victim.read_text(encoding="utf-8")
    context = _unique_context_line(
        (_BUNDLE / f"{row_id}.diff").read_text(encoding="utf-8"), body
    )
    victim.write_text(
        body.replace(context + "\n", context + " # hand-edited since the bundle\n"),
        encoding="utf-8",
    )

    bad = _run_verify(drifted)
    assert bad.returncode == 10, (
        f"drift in {target} exited {bad.returncode}, expected 10\n"
        f"{bad.stdout}\n{bad.stderr}"
    )
    assert "DRIFT" in bad.stderr and row_id in bad.stderr, bad.stderr
    assert "never force-apply" in bad.stderr, bad.stderr


def test_drift_outside_the_patch_context_is_also_a_refusal(tmp_path):
    """The second refusal channel, and the reason it exists.

    A patch is a statement about a few lines; a target can drift everywhere
    else and still take it cleanly. `git apply --check` alone would call that
    a pass, so verify.sh pins the post-image digest as well — and this arm is
    what proves the pin is load-bearing rather than decorative.
    """
    for row_id, target, _sha, _state in _bundle_rows():
        drifted = _minimal_root(tmp_path / f"outside-{row_id}")
        victim = drifted / target
        victim.write_text(
            victim.read_text(encoding="utf-8") + "\n# appended after the bundle\n",
            encoding="utf-8",
        )
        bad = _run_verify(drifted)
        assert bad.returncode == 10, (
            f"{row_id}: an off-hunk edit exited {bad.returncode}, expected 10\n"
            f"{bad.stdout}\n{bad.stderr}"
        )
        assert f"{row_id} FAIL: post-image sha256" in bad.stderr, bad.stderr


def test_bundle_touches_no_locked_file():
    """B §7 invariant 1: inspecting the bundle costs the locked set nothing."""
    before = _digest_locked_paths(_REPO)
    status_before = _git(_REPO, "status", "--porcelain")
    proc = _run_verify(_REPO)
    assert proc.returncode == 0, proc.stderr
    assert _digest_locked_paths(_REPO) == before, (
        "a locked path changed while verify.sh ran"
    )
    assert _git(_REPO, "status", "--porcelain") == status_before, (
        "verify.sh left the working tree dirty"
    )


def test_every_bundle_target_is_inside_the_locked_set():
    """A row for an unlocked file is a mis-filed row: it needs no ceremony and
    would let an ordinary change ride a Captain window."""
    locked = _locked()
    for row_id, target, _sha, _state in _bundle_rows():
        assert update_bundle.is_locked(target, locked), (
            f"{row_id}: {target} is not in the germline set — this package is "
            "only for bytes that need a Captain unlock window"
        )


def test_doc_names_every_bundle_file_and_the_row():
    """The apply contract must name what the Captain is being asked to apply."""
    text = _DOC.read_text(encoding="utf-8")
    assert ROW_ID in text, f"the doc never names its ledger row {ROW_ID}"
    assert "verify.sh" in text
    for row_id, target, _sha, _state in _bundle_rows():
        assert target in text, f"the doc never names {target}"
        assert f"{row_id}.diff" in text, f"the doc never names {row_id}.diff"


# ---------------------------------------------------------------------------
# the ledger row
# ---------------------------------------------------------------------------


def test_ledger_row_present_exactly_once_with_its_plan_twin():
    """A set-based gate blesses duplicates, so the count is asserted, not the
    membership."""
    ledger_text = _LEDGER.read_text(encoding="utf-8")
    assert ledger_text.count(f'- id: "{ROW_ID}"') == 1, (
        f"expected exactly one {ROW_ID} ledger row"
    )
    entries = yaml.safe_load(ledger_text)["entries"]
    rows = [e for e in entries if e.get("id") == ROW_ID]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["status"] == "captain-gated", row["status"]
    assert row["lane"] == "captain-gated", row["lane"]
    assert _PKG in str(row["note"]) or _PKG in str(row["gate_cmd"]), (
        "the ledger row does not point at the proposal package"
    )

    plan_text = _PLAN.read_text(encoding="utf-8")
    assert len(re.findall(rf"^\| {ROW_ID} ", plan_text, re.M)) == 1, (
        f"expected exactly one {ROW_ID} row in the plan doc"
    )


def test_a13_parity_holds():
    """The A13 gate itself: every ledger id has a plan-doc row and vice versa."""
    ids = {e["id"] for e in yaml.safe_load(_LEDGER.read_text())["entries"]}
    plan_ids = set(_A13_ID_RE.findall(_PLAN.read_text(encoding="utf-8")))
    assert plan_ids == ids, sorted(plan_ids ^ ids)
    assert ROW_ID in ids


# ---------------------------------------------------------------------------
# the branch guard (A7.3)
# ---------------------------------------------------------------------------


def test_phase1_touches_no_locked_path():
    """§7 invariant: no phase-1 diff touches a path in the germline set.

    This is a GUARD — green by construction on a branch that behaved — so its
    two failure modes are the whole design: it must red when a locked path is
    in the diff, and it must red (never pass) when it cannot see the diff at
    all. The second half has its own arm below.
    """
    base = _resolve_base(_REPO)
    changed = [
        line for line in _git(_REPO, "diff", "--name-only", f"{base}..HEAD").splitlines()
        if line.strip()
    ]
    locked = _locked()
    offenders = _locked_offenders(changed, locked)
    assert not offenders, (
        f"this branch changes germline paths: {offenders}. A locked path is "
        "never edited or worked around — route the need through a ledger row "
        "and a proposal package."
    )


def test_the_guard_refuses_an_unreachable_base(tmp_path):
    """A7.3: an unresolvable base FAILS the guard; it never passes it.

    Driven through the same resolver the guard uses, with a base that cannot
    resolve, and separately against a directory that is not a git work tree —
    the shallow-checkout shape without needing to build a shallow clone.
    """
    with pytest.raises(BaseUnreachable):
        _resolve_base(_REPO, env={"CABINET_PHASE1_BASE": "0" * 40})

    not_a_repo = tmp_path / "gitless"
    not_a_repo.mkdir()
    with pytest.raises(BaseUnreachable):
        _resolve_base(not_a_repo, env={})


def test_the_guard_flags_a_locked_path():
    """The other half of the guard's proof: it is not green in both directions.

    `test_phase1_touches_no_locked_path` passes on a branch that touched
    nothing locked, which is also what it would do if `is_locked` answered
    False to everything. These three cases separate those two worlds — a named
    locked FILE, a path under a locked DIRECTORY, and two paths that are
    genuinely outside the set.
    """
    locked = _locked()
    innocent = ["docs/proposals/anything.md", "cabinet/scripts/tests/anything.py"]
    assert _locked_offenders(innocent, locked) == []

    locked_file = locked["files"][0]
    assert _locked_offenders(innocent + [locked_file], locked) == [locked_file]

    under_locked_dir = locked["dirs"][0].rstrip("/") + "/a-new-file.sh"
    assert _locked_offenders(innocent + [under_locked_dir], locked) == [
        under_locked_dir
    ]
