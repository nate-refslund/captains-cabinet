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
exit code. The golden-eval stage is stood in for by `--checks-only` where no
Redis endpoint can be provisioned, and run for real where `redis-server` exists.

THE DEFECT THIS FILE WAS REBUILT AROUND (review of 2026-09-08). A unified diff
is a statement about a few lines, so it can apply cleanly to a file that differs
everywhere else and produce bytes nobody declared. Measured: `G3.diff` applies
(rc 0) to the pre-2026-07-31 bytes of its target and yields
c89c578fc10de08e89668416b45fc51b9ac7b366a1efa10f2992e697f2b30348, not the
post-image the bundle declares. So a bundle that pins only the post-image
discovers the mismatch INSIDE the Captain's unlock window — a window that cannot
be delegated and cannot be re-opened cheaply. Every row therefore pins the
sha256 of the pre-image it was built against as well, and the target is
classified by its own bytes rather than by an assumption about which tree this
is.

THE DEGENERATE END, checked deliberately.
  * A drift arm builds a minimal root whose target bytes are neither the
    pre-image nor the post-image and proves `verify.sh` REFUSES (exit 10) — a
    gate that only ever sees a clean tree is a gate nobody has tried to defeat.
    Its control (the same root, unmutated) proves the refusal is about the
    mutation and not about the fixture. One arm drives the REAL historical bytes
    that the review measured, not only a synthetic edit.
  * The post-image pin has its own inverted arm: a copy of the bundle whose diff
    was altered to produce different bytes must be refused even though it still
    applies to the declared pre-image.
  * The exit-12 channel ("inspecting the bundle costs the locked set nothing")
    has an inverted arm too — a locked path is mutated, deterministically, while
    `verify.sh` is running.
  * The locked set is asserted non-degenerate before it is intersected with
    anything: an empty boundary makes every "touches no locked path" claim
    trivially true, which is the failure this file exists to prevent.
  * `test_phase1_touches_no_locked_path` FAILS when its base revision is
    unreachable (A7.3) instead of passing on a shallow checkout, and its own
    inverted arm drives an unresolvable base to prove the refusal fires. Its one
    exemption — a deliberate landed-then-ceremonied germline landing — has to be
    recorded IN THE TREE, not merely declared in an environment variable.

WHAT ROUND 2 OF THE REVIEW FOUND, AND A7.6/A7.7 CLOSED (2026-09-08).
  * The exemption's evidence predicate was a free-text substring: any locked
    path that merely APPEARED in a `germline-amendment-*.md` naming the CG row
    was vouched for. Measured: with `CABINET_GERMLINE_LANDING=CG-36`, a commit
    touching `cabinet/scripts/hooks/on-subagent-start.sh` — named in this
    package only as the DROPPED G2 residual — passed the guard, and so would
    one touching `cabinet/scripts/germline-lock.sh`, the file that defines the
    set. A7.6 keys the exemption on what the package DECLARES it is landing
    (its own `BUNDLE_ROWS` targets, or an explicit landing list) and on those
    targets holding the declared bytes; prose vouches for nothing.
  * G3 rode as a diff only, so its post-image could not be pinned on the tree
    the ceremony runs on. A7.7 lands its bytes in the unlocked lane like G1's,
    which turns step 3 of the window into a `git checkout` for both rows. The
    arms that need a tree at the PRE-image now build one by reverse-applying
    the bundle's own diffs and checking the digest, because a clone of master
    is `already-at-target` for every row.

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
#: cabinet with less to protect (measured 2026-09-08: germline-lock.sh parses to
#: 73 FILES + 7 DIRS).
_MIN_LOCKED_ENTRIES = 50

#: The revision of G3's target that immediately PRECEDES 5338cb42 (2026-07-31),
#: the commit that changed the hook on master outside G3's own hunk. It is the
#: shape a locked tree that has not had a window since then would be in, and the
#: bytes the 2026-09-08 review applied G3.diff to.
_G3_HISTORICAL_REV = "5dce39d5"

#: What that apply produces — the digest that would have failed the ceremony at
#: step 4, inside the window, had the bundle pinned only its post-image.
_G3_HISTORICAL_POST = (
    "c89c578fc10de08e89668416b45fc51b9ac7b366a1efa10f2992e697f2b30348"
)

#: The acknowledgement env var for a deliberate landed-then-ceremonied germline
#: landing (CLAUDE.md §8). It names a CG row; the row and a proposal package that
#: DECLARES each landed path must exist in the tree (A7.6).
_LANDING_ACK_ENV = "CABINET_GERMLINE_LANDING"

#: Locked paths this package NAMES but does not land: the dropped G2 residual
#: (A7.1, doc §3 and §8) and the file that defines the locked set itself (doc
#: §6). Under the substring predicate the round-2 review measured, both rode
#: the exemption. Under A7.6 neither can, and these are the arms that say so.
_NAMED_BUT_NOT_LANDED = (
    "cabinet/scripts/hooks/on-subagent-start.sh",
    "cabinet/scripts/germline-lock.sh",
)

#: An explicit landing list in an amendment doc, for a package that ships no
#: bundle table. Anchored at column 0 so a mention inside a sentence — this
#: repository's own prose about the channel included — is not a declaration.
_LANDING_LIST_RE = re.compile(r"^landing:[ \t]*(.*)$", re.M)
_LANDING_BULLET_RE = re.compile(r"^[-*][ \t]+(.+?)[ \t]*$")

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


def _git_blob(root: Path, rev: str, rel: str) -> bytes:
    """The raw bytes of `rel` at `rev` — raw, because a digest of text that has
    been stripped or newline-translated is a digest of something else."""
    proc = subprocess.run(
        ["git", "show", f"{rev}:{rel}"], cwd=str(root), capture_output=True
    )
    return proc.stdout if proc.returncode == 0 else b""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _locked() -> dict[str, list[str]]:
    locked = update_bundle.parse_locked_set(_LOCK_SH)
    total = len(locked["files"]) + len(locked["dirs"])
    assert total >= _MIN_LOCKED_ENTRIES, (
        f"the locked set parsed to {total} entries — a boundary this small is a "
        "parse failure, and every 'touches no locked path' claim below would be "
        "trivially true against it"
    )
    return locked


def _bundle_rows_from(verify: Path) -> list[tuple[str, str, str, str, str]]:
    """(id, target, pre-image sha256, post-image sha256, state) out of a
    verify.sh's own table.

    Parameterised by the gate it reads because A7.6 lets ANY package vouch for
    its own landing, and a predicate that could only read this one package's
    table would be a rule about this branch rather than about the pattern.
    """
    text = verify.read_text(encoding="utf-8")
    match = re.search(r'^BUNDLE_ROWS="\n(.*?)\n"\s*$', text, re.M | re.S)
    assert match, "could not find the BUNDLE_ROWS table in verify.sh"
    rows = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        assert len(parts) == 5, (
            f"unparseable bundle row: {line!r} — a row is "
            "id|target|pre-image sha256|post-image sha256|state"
        )
        rows.append(tuple(parts))  # type: ignore[arg-type]
    assert rows, "the bundle table parsed to zero rows"
    return rows


def _bundle_rows() -> list[tuple[str, str, str, str, str]]:
    """This package's own table."""
    return _bundle_rows_from(_VERIFY)


def _run_verify(
    repo: Path,
    verify: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(verify or _VERIFY), "--repo", str(repo), "--checks-only"],
        capture_output=True,
        text=True,
        env=env,
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


def _root_at_pre_image(tmp_root: Path) -> Path:
    """A fixture tree whose targets hold the PRE-image each diff was built
    against — the shape a tree that has not taken the landing is in.

    A7.7 landed both rows, so a clone of master is `already-at-target` for
    every row and never reaches verify.sh's forward-apply branch. An arm about
    that branch therefore has to BUILD the tree that exercises it, and it
    builds it by reverse-applying the bundle's own diffs and then checking the
    digest — never by assuming the reverse produced the right bytes.
    """
    root = _minimal_root(tmp_root)
    for row_id, target, pre, post, _state in _bundle_rows():
        if _sha256_file(root / target) != post:
            continue
        proc = subprocess.run(
            ["git", "apply", "--reverse", str(_BUNDLE / f"{row_id}.diff")],
            cwd=str(root), capture_output=True, text=True,
        )
        assert proc.returncode == 0, (
            f"{row_id}: reverse-applying its own diff failed, so this fixture "
            f"cannot be built:\n{proc.stderr}"
        )
        assert _sha256_file(root / target) == pre, (
            f"{row_id}: reverse-applying the diff did not reproduce the "
            "declared pre-image, so this fixture is not the tree it claims"
        )
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
    for row_id, target, _pre, _post, _state in _bundle_rows():
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
    for row_id, target, _pre, sha, _state in _bundle_rows():
        assert f"[verify] {row_id} OK" in proc.stdout, proc.stdout
        assert target in proc.stdout and sha in proc.stdout, proc.stdout


def test_every_landed_row_is_already_at_target_in_this_tree():
    """A7.7: a `landed` row's bytes are ON MASTER, so the Captain's window
    re-materialises them with `git checkout` and applies no diff.

    An apply can only be checked inside the window it happens in, and that
    window cannot be delegated or cheaply re-opened — which is exactly how the
    round-1 review's defect reached step 4. A row that still has to be applied
    is that shape; this arm requires there to be none, and requires each landed
    row's target to actually hold the digest the row declares rather than
    trusting the word `landed` in the table.
    """
    landed = [row for row in _bundle_rows() if row[4] == "landed"]
    assert landed, "no row is landed — A7.7 is not in this tree"

    proc = _run_verify(_REPO)
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    for row_id, target, _pre, post, _state in landed:
        assert _sha256_file(_REPO / target) == post, (
            f"{row_id}: the table says `landed` but {target} does not hold the "
            "declared post-image on this tree"
        )
        assert f"[verify] {row_id} OK (already-at-target, state=landed" in proc.stdout, (
            f"{row_id} is not classified as already-at-target here\n{proc.stdout}"
        )
    assert "applies=0" in proc.stdout, (
        "a row still has to be APPLIED inside the window, which is the shape "
        f"A7.7 removed\n{proc.stdout}"
    )


def test_the_ceremony_re_materialises_every_landed_row_with_a_checkout():
    """A7.7 in the document the Captain actually executes.

    `git checkout <sha> -- <path>` yields the declared post-image on any tree;
    `git apply` yields whatever the tree in front of it happens to make of the
    patch. With every row landed there is no reason for the second shape to
    survive in the window, and a document that still offered it would be the
    half of the fix that never happened.
    """
    section = _section(_DOC.read_text(encoding="utf-8"), "## 5.")
    for row_id, target, _pre, _post, state in _bundle_rows():
        if state != "landed":
            continue
        assert re.search(rf"git checkout \S+ -- {re.escape(target)}", section), (
            f"{row_id}: the ceremony does not re-materialise {target} with a "
            f"checkout of the landed bytes\n{section}"
        )
    assert "git apply" not in section, (
        "the ceremony still applies a diff inside the window; every row is "
        f"landed, so a checkout is the whole of step 3\n{section}"
    )


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
    row_id, target, _pre, _post, _state = _bundle_rows()[0]
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


def test_every_row_declares_the_pre_image_it_was_built_against():
    """The pin the 2026-09-08 review found missing.

    A diff is a statement about a few lines; the pre-image digest is what makes
    it a statement about a FILE. Without it, "the patch applied" is compatible
    with any number of trees, and only one of them produces the bytes the
    Captain is being asked to accept.
    """
    for row_id, target, pre, post, state in _bundle_rows():
        assert re.fullmatch(r"[0-9a-f]{64}", pre), (
            f"{row_id} ({target}): pre-image is not a sha256: {pre!r}"
        )
        assert re.fullmatch(r"[0-9a-f]{64}", post), (
            f"{row_id} ({target}): post-image is not a sha256: {post!r}"
        )
        assert pre != post, (
            f"{row_id}: pre- and post-image digests are equal, so the row "
            "cannot tell 'not yet applied' from 'already applied'"
        )
        assert state in {"landed", "proposed"}, f"{row_id}: state={state!r}"


def test_drift_outside_the_patch_context_is_also_a_refusal(tmp_path):
    """The class the review measured, in its synthetic form.

    A patch is a statement about a few lines; a target can drift everywhere
    else and still take it cleanly. `git apply --check` alone would call that a
    pass. The refusal has to name what it saw and what it wanted, because the
    only useful answer at this point is "rebuild against these bytes".
    """
    for row_id, target, pre, post, _state in _bundle_rows():
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
        assert pre in bad.stderr and post in bad.stderr, (
            f"{row_id}: the refusal must name the digests it expected\n"
            f"{bad.stderr}"
        )
        assert _sha256_file(victim) in bad.stderr, (
            f"{row_id}: the refusal must name the digest it actually saw\n"
            f"{bad.stderr}"
        )
        assert "REBUILD" in bad.stderr and "never force-apply" in bad.stderr


def test_the_historical_locked_bytes_are_refused_not_silently_patched(tmp_path):
    """THE REVIEWED DEFECT (2026-09-08), driven with the real bytes.

    `5338cb42` changed G3's target on master on 2026-07-31, outside G3's own
    hunk. A locked tree that has had no unlock window since then still holds
    the bytes of `5dce39d5`. `G3.diff` applies to those cleanly — and produces
    a file whose digest is not the one this bundle declares. Before the
    pre-image pin, that discovery happened at step 4 of a Captain window that
    cannot be delegated; now it happens the first time anyone runs verify.sh
    against the tree, which the ceremony does BEFORE asking for sudo.
    """
    row = next(r for r in _bundle_rows() if r[0] == "G3")
    row_id, target, pre, post, _state = row

    blob = _git_blob(_REPO, _G3_HISTORICAL_REV, target)
    assert blob, (
        f"{_G3_HISTORICAL_REV}:{target} does not resolve in this checkout — "
        "this arm compares against real history, so the job needs the full "
        "history (`fetch-depth: 0`), not a shallow clone"
    )

    root = _minimal_root(tmp_path / "historical")
    (root / target).write_bytes(blob)
    seen = _sha256_file(root / target)

    bad = _run_verify(root)
    assert bad.returncode == 10, (
        f"the pre-{_G3_HISTORICAL_REV} bytes exited {bad.returncode}, "
        f"expected 10\n{bad.stdout}\n{bad.stderr}"
    )
    assert seen in bad.stderr and pre in bad.stderr and post in bad.stderr, bad.stderr
    assert f"{row_id} OK" not in bad.stdout, (
        "the bundle reported a pass on bytes it was not built against"
    )
    assert _G3_HISTORICAL_POST not in bad.stdout, (
        "verify.sh applied the diff to bytes it was not built against and "
        "reported the result — that is the failure this arm exists to catch"
    )


def test_a_diff_that_stopped_producing_its_declared_post_image_is_refused(tmp_path):
    """The post-image pin's own inverted arm.

    The pre-image check answers "are these the right bytes to patch". It cannot
    answer "does this patch still produce what the table promises" — a bundle
    can be edited after its digest was computed. So: a COPY of the bundle whose
    diff still applies to the declared pre-image but yields something else must
    be refused. Mutating the artifact under test is the only way to prove this
    channel is wired, because a correct bundle can never exercise it.
    """
    bundle = tmp_path / "mutated-bundle"
    bundle.mkdir()
    for name in ("verify.sh", "G1.diff", "G3.diff"):
        shutil.copy2(_BUNDLE / name, bundle / name)

    diff_path = bundle / "G3.diff"
    text = diff_path.read_text(encoding="utf-8")
    needle = "+export CABINET_WORKER_ID="
    assert text.count(needle) == 1, "the line this arm mutates moved"
    # An ADDED line's content only — the hunk line counts are untouched, so the
    # patch still applies to exactly the same pre-image.
    diff_path.write_text(
        text.replace(needle, "+export CABINET_WORKER_ID_MUTATED="), encoding="utf-8"
    )

    # The tree has to be at the PRE-image or verify.sh classifies every row as
    # already-at-target and never applies the mutated diff at all — the arm
    # would then pass while measuring nothing (A7.7 changed this).
    root = _root_at_pre_image(tmp_path / "pre-image")
    bad = _run_verify(root, verify=bundle / "verify.sh")
    assert bad.returncode == 10, (
        f"a bundle whose diff no longer produces its declared post-image "
        f"exited {bad.returncode}, expected 10\n{bad.stdout}\n{bad.stderr}"
    )
    assert "post-image sha256" in bad.stderr, bad.stderr

    # Control: the same fixture with the UNMUTATED bundle applies forward and
    # is green, so the refusal above is about the mutation, not the fixture.
    ok = _run_verify(root)
    assert ok.returncode == 0, f"{ok.stdout}\n{ok.stderr}"
    assert "applies=2" in ok.stdout, ok.stdout


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


def test_a_locked_path_written_during_the_run_is_caught(tmp_path):
    """The exit-12 channel's inverted arm.

    `test_bundle_touches_no_locked_file` compares a digest before and after and
    passes. So would a build in which the comparison had been deleted — the
    green is the same either way. This arm makes a locked path change WHILE
    verify.sh is running, deterministically, and requires exit 12.

    The seam is verify.sh's own interpreter variable: the locked-set digest is
    the only thing it launches, once at the start and once at the end, so a
    wrapper that mutates on its second call writes in exactly the window the
    check is supposed to cover. The write lands in a fixture tree; no live
    switch and no real locked path is ever in the write set.
    """
    victim_rel = "cabinet/scripts/hooks/session-task-inject.sh"
    assert update_bundle.is_locked(victim_rel, _locked()), victim_rel

    def _wrapper(name: str, mutate: bool) -> tuple[Path, Path]:
        root = _minimal_root(tmp_path / name)
        counter = tmp_path / f"{name}.calls"
        path = tmp_path / f"{name}.py.sh"
        body = "" if not mutate else (
            f'  printf "\\n# written while verify.sh ran\\n" '
            f'>> "{root / victim_rel}"\n'
        )
        path.write_text(
            "#!/bin/bash\n"
            f'n=$(cat "{counter}" 2>/dev/null || echo 0)\n'
            f'n=$((n + 1)); echo "$n" > "{counter}"\n'
            'if [ "$n" -ge 2 ]; then\n'
            f"{body or '  :\n'}"
            "fi\n"
            f'exec "{sys.executable}" "$@"\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
        return root, path

    # Control: the same wrapper, mutating nothing. If this is not green the arm
    # below proves nothing about the mutation.
    root_ok, wrapper_ok = _wrapper("control", mutate=False)
    ok = _run_verify(
        root_ok, env={**os.environ, "CABINET_PYTHON": str(wrapper_ok)}
    )
    assert ok.returncode == 0, f"{ok.stdout}\n{ok.stderr}"

    root_bad, wrapper_bad = _wrapper("mutating", mutate=True)
    bad = _run_verify(
        root_bad, env={**os.environ, "CABINET_PYTHON": str(wrapper_bad)}
    )
    assert bad.returncode == 12, (
        f"a locked path written mid-run exited {bad.returncode}, expected 12\n"
        f"{bad.stdout}\n{bad.stderr}"
    )
    assert "a locked path changed while verify.sh ran" in bad.stderr, bad.stderr


def test_the_golden_eval_stage_is_wired_in_both_directions(tmp_path):
    """The stage `--checks-only` skips, driven rather than declared.

    Every other arm here passes `--checks-only`, so without this one the full
    form — the one the ceremony actually runs — would have no sensor at all,
    and a build that had lost the `run-golden-evals.sh` call entirely would
    still be green everywhere. The real suite is exercised too, but it takes
    ~158 s and needs a Redis endpoint, so it is a battery row (measured
    2026-09-08: 32/32, ephemeral redis, live redis untouched), not a unit arm.
    Here the dependency is stubbed in a fixture tree and BOTH of its answers
    are required to reach the exit code the ceremony reads.
    """
    def _run_full(name: str, evals_rc: int) -> subprocess.CompletedProcess:
        root = _minimal_root(tmp_path / name)
        stub = root / "cabinet" / "scripts" / "run-golden-evals.sh"
        stub.write_text(
            f'#!/bin/bash\necho "stub golden evals (rc {evals_rc})"\n'
            f"exit {evals_rc}\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)
        return subprocess.run(
            ["bash", str(_VERIFY), "--repo", str(root)],
            capture_output=True,
            text=True,
        )

    green = _run_full("evals-green", 0)
    assert green.returncode == 0, f"{green.stdout}\n{green.stderr}"
    assert "golden evals GREEN" in green.stdout, green.stdout
    assert "checks_only=0" in green.stdout, green.stdout

    red = _run_full("evals-red", 1)
    assert red.returncode == 13, (
        f"red golden evals exited {red.returncode}, expected 13\n"
        f"{red.stdout}\n{red.stderr}"
    )
    assert "golden evals red" in red.stderr, red.stderr


def test_every_bundle_target_is_inside_the_locked_set():
    """A row for an unlocked file is a mis-filed row: it needs no ceremony and
    would let an ordinary change ride a Captain window."""
    locked = _locked()
    for row_id, target, _pre, _post, _state in _bundle_rows():
        assert update_bundle.is_locked(target, locked), (
            f"{row_id}: {target} is not in the germline set — this package is "
            "only for bytes that need a Captain unlock window"
        )


def test_doc_names_every_bundle_file_and_the_row():
    """The apply contract must name what the Captain is being asked to apply."""
    text = _DOC.read_text(encoding="utf-8")
    assert ROW_ID in text, f"the doc never names its ledger row {ROW_ID}"
    assert "verify.sh" in text
    for row_id, target, _pre, _post, _state in _bundle_rows():
        assert target in text, f"the doc never names {target}"
        assert f"{row_id}.diff" in text, f"the doc never names {row_id}.diff"


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    nxt = text.find("\n## ", start + 1)
    return text[start : nxt if nxt != -1 else len(text)]


def test_the_doc_declares_the_digests_the_captain_is_accepting():
    """The apply contract and the gate must pin the same bytes.

    If only verify.sh carried the digests, the document the Captain reads and
    the script that decides could describe different files — and the document
    is the thing being consented to.
    """
    text = _DOC.read_text(encoding="utf-8")
    for row_id, target, pre, post, _state in _bundle_rows():
        assert pre in text, f"{row_id}: the doc never states the pre-image {pre}"
        assert post in text, f"{row_id}: the doc never states the post-image {post}"


def test_the_ceremony_gates_before_it_unlocks():
    """A window nobody else can open is not a place to discover a rebuild.

    verify.sh writes nothing and needs no privilege, so the only reason it ran
    after the unlock was habit. Measured (2026-09-08 review): had G3's target
    on the box been the pre-5338cb42 bytes, the ceremony would have reached
    step 4 — inside the window — and refused there. The check belongs before
    the sudo, and the ordering is asserted rather than asked for politely.
    """
    section = _section(_DOC.read_text(encoding="utf-8"), "## 5.")
    unlock = section.find("germline-lock.sh unlock")
    assert unlock != -1, "the ceremony never names the unlock"
    first_verify = section.find("verify.sh")
    assert first_verify != -1, "the ceremony never runs verify.sh"
    assert first_verify < unlock, (
        "the ceremony asks for sudo before it has checked the bundle against "
        "the bytes the box actually holds, so a rebuild is discovered inside "
        "the window instead of before it"
    )


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


def _declared_landing_targets(doc: Path) -> dict[str, str | None]:
    """The paths a proposal package DECLARES it is landing, mapped to the bytes
    it declares for each. Read from the tree, never from prose (A7.6).

    Two channels, in this order:

    * the package's own `BUNDLE_ROWS` table (`<doc stem>/verify.sh`): every row
      whose state is `landed`, mapped to the post-image digest that row pins.
      This is the same table the ceremony runs from, so a package cannot
      declare one thing to this guard and another to the Captain.
    * an explicit landing list in the document, for a package that ships no
      bundle table: a line beginning at column 0 with the word `landing` and a
      colon, either naming one path inline or followed by `- <path>` bullets.
      Those carry no digest, so they are pinned by membership alone.

    A path that merely appears in the prose is NOT declared. That distinction
    is the whole of A7.6: this package names `on-subagent-start.sh` as the
    DROPPED G2 residual and `germline-lock.sh` as the file that defines the
    locked set, and the substring predicate this replaces vouched for both.
    """
    declared: dict[str, str | None] = {}

    verify = doc.parent / doc.stem / "verify.sh"
    if verify.is_file():
        for _row_id, target, _pre, post, state in _bundle_rows_from(verify):
            if state == "landed":
                declared[target] = post

    text = doc.read_text(encoding="utf-8")
    lines = text.splitlines()
    for match in _LANDING_LIST_RE.finditer(text):
        inline = match.group(1).strip().strip("`").strip()
        if inline:
            declared.setdefault(inline, None)
            continue
        start = text.count("\n", 0, match.start()) + 1
        for line in lines[start:]:
            bullet = _LANDING_BULLET_RE.match(line)
            if not bullet:
                break
            declared.setdefault(bullet.group(1).strip().strip("`").strip(), None)
    return declared


def _holds_declared_bytes(rel: str, want: str | None) -> bool:
    """A declared target vouches only while it holds the declared bytes.

    Without this the exemption would be about a PATH, and a landing branch
    could put anything at all into a file the package happens to name. The
    degenerate ends are refusals: a target that is missing vouches for nothing,
    and a channel with no digest (an explicit landing list) is pinned by
    membership alone and says so rather than pretending to a check it has not
    made.
    """
    path = _REPO / rel
    if not path.is_file():
        return False
    return want is None or _sha256_file(path) == want


def _landing_acknowledged(offenders: list[str], ack: str) -> Path | None:
    """The guard's ONE exemption, and why neither half of it is a claim.

    CLAUDE.md §8 sanctions a landed-then-ceremonied germline CONTENT fix: the
    bytes are landed on master like any change and one Captain window
    re-materialises them. `00c3acd3` (G1's landing) and `5338cb42` are both
    that shape, and A7.7's landing of G3 is a third. An unconditional guard
    makes the sanctioned pattern unlandable, and `--admin` bypass is forbidden
    — so it needs a channel.

    A bare environment variable would be the wrong channel: it is a claim about
    the caller's intent, it travels into shells and CI recipes that never meant
    it, and it leaves nothing behind. Neither is a mention in a document: a
    proposal names every path it discusses, including the ones it is explicitly
    NOT touching. So both halves are required and both are mechanical (A7.6):

    * `CABINET_GERMLINE_LANDING` names a CG row that exists exactly once in the
      ledger, and
    * every offending path is one the package DECLARES it is landing, and
      currently holds the bytes that package declares for it.

    Returns the package that vouches, or None. An empty offender list is never
    vouched for — `all([])` is True, and a predicate that answers "yes" to a
    question nobody asked is the degenerate end this file keeps finding.
    """
    if not offenders:
        return None
    if not re.fullmatch(r"CG-\d+", (ack or "").strip()):
        return None
    ack = ack.strip()
    if _LEDGER.read_text(encoding="utf-8").count(f'- id: "{ack}"') != 1:
        return None
    proposals = sorted((_REPO / "docs" / "proposals").glob("germline-amendment-*.md"))
    for doc in proposals:
        if ack not in doc.read_text(encoding="utf-8"):
            continue
        declared = _declared_landing_targets(doc)
        if not declared:
            continue
        if any(path not in declared for path in offenders):
            continue
        if not all(_holds_declared_bytes(path, declared[path]) for path in offenders):
            continue
        return doc
    return None


def test_phase1_touches_no_locked_path():
    """§7 invariant: no phase-1 diff touches a path in the germline set.

    This is a GUARD — green by construction on a branch that behaved — so its
    failure modes are the whole design: it must red when a locked path is in
    the diff, it must red (never pass) when it cannot see the diff at all, and
    it must not make the one sanctioned germline landing unlandable. All three
    have their own arms below.

    The exemption is deliberately NOT wired into CI (A7.6): a landing branch is
    an exceptional, reviewed act, so the operator running it sets
    `CABINET_GERMLINE_LANDING` for that run. Once the branch merges, the diff
    against the base is empty and the guard is a no-op again — an environment
    variable standing permanently in a CI recipe would be the claim-about-
    intent this predicate exists to refuse.
    """
    base = _resolve_base(_REPO)
    changed = [
        line for line in _git(_REPO, "diff", "--name-only", f"{base}..HEAD").splitlines()
        if line.strip()
    ]
    locked = _locked()
    offenders = _locked_offenders(changed, locked)
    if not offenders:
        return
    ack = os.environ.get(_LANDING_ACK_ENV, "")
    vouched = _landing_acknowledged(offenders, ack)
    assert vouched is not None, (
        f"this branch changes germline paths: {offenders}. A locked path is "
        "never edited or worked around — route the need through a ledger row "
        "and a proposal package. A deliberate landed-then-ceremonied landing "
        f"(CLAUDE.md §8) sets {_LANDING_ACK_ENV}=<CG-id> AND carries that row "
        "in the ledger plus a docs/proposals/germline-amendment-*.md that "
        "DECLARES every path above — a `landed` row of its own BUNDLE_ROWS "
        "table, or an explicit landing list — with the target holding the "
        f"bytes that package declares (A7.6); {ack!r} does not."
    )
    print(f"[guard] acknowledged germline landing {ack} ({vouched.name}): {offenders}")


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


def test_a_germline_landing_must_be_recorded_in_the_tree_not_declared():
    """The exemption's own arms — it must refuse far more than it allows.

    Four ways of asking for it that leave no record behind, and the one way
    that does: this package's own row, which names both of its targets.
    """
    unrelated = [_locked()["files"][0]]
    assert _landing_acknowledged(unrelated, "") is None
    assert _landing_acknowledged(unrelated, "not-a-row-id") is None
    assert _landing_acknowledged(unrelated, "CG-99999") is None, (
        "a CG id with no ledger row vouched for a germline landing"
    )
    assert _landing_acknowledged(unrelated, ROW_ID) is None, (
        f"{ROW_ID} vouched for a path its proposal package never names"
    )

    targets = [row[1] for row in _bundle_rows()]
    vouched = _landing_acknowledged(targets, ROW_ID)
    assert vouched is not None and vouched.name == f"{_PKG}.md", vouched


def test_the_landing_exemption_is_keyed_on_the_package_not_its_prose():
    """A7.6, driven with the exact paths the round-2 review measured.

    The predicate this replaces asked whether a path APPEARED in a document
    that named the CG row. A proposal names every path it discusses — including
    the ones it is explicitly not touching — so that predicate vouched for the
    dropped G2 residual and for `germline-lock.sh`, the file that defines the
    locked set. Both are still named here, deliberately: the arm would stop
    driving its own case if they were removed, so it asserts they are present
    before asserting they are refused.
    """
    doc_text = _DOC.read_text(encoding="utf-8")
    locked = _locked()
    declared = _declared_landing_targets(_DOC)
    for rel in _NAMED_BUT_NOT_LANDED:
        assert rel in doc_text, (
            f"{rel} is no longer named in the package, so this arm no longer "
            "drives the case it exists for — re-derive it or delete it"
        )
        assert update_bundle.is_locked(rel, locked), rel
        assert rel not in declared, rel
        assert _landing_acknowledged([rel], ROW_ID) is None, (
            f"{rel} is named in the package's prose but is not one of the "
            "paths it declares it is landing — the exemption vouched anyway"
        )

    targets = [row[1] for row in _bundle_rows() if row[4] == "landed"]
    assert targets, "no landed row to drive the accept arm with"
    assert _landing_acknowledged(targets, ROW_ID) is not None, (
        "the package's own landed targets are not vouched for, so the "
        "sanctioned pattern is unlandable again"
    )

    # One undeclared path poisons an otherwise declared set: a landing vouches
    # for exactly what it declares, never for the company that path keeps.
    assert _landing_acknowledged(
        targets + [_NAMED_BUT_NOT_LANDED[0]], ROW_ID
    ) is None


def test_a_declared_target_vouches_only_while_it_holds_the_declared_bytes():
    """The exemption covers BYTES, not a path.

    Keyed on the path alone, a landing branch could put anything at all into a
    file its package happens to declare, and the guard would wave it through
    while the Captain reads a digest that no longer describes it. Both
    degenerate ends refuse: a target that is absent, and a digest that differs.
    """
    landed = [row for row in _bundle_rows() if row[4] == "landed"]
    assert landed
    for row_id, target, _pre, post, _state in landed:
        assert _holds_declared_bytes(target, post), row_id
        assert not _holds_declared_bytes(target, "0" * 64), (
            f"{row_id}: a wrong digest still vouched for {target}"
        )
    assert not _holds_declared_bytes("cabinet/scripts/no-such-file.sh", None)


def test_the_landing_declaration_comes_from_the_table_or_an_explicit_list(tmp_path):
    """Both channels of A7.6, and the degenerate end of each.

    The bundle-table channel is what this package uses; the explicit-list
    channel is what a package with no bundle table would use, and a channel
    with no arm is a channel nobody has tried. A document that declares
    NOTHING must declare nothing — not everything it mentions.
    """
    declared = _declared_landing_targets(_DOC)
    assert set(declared) == {row[1] for row in _bundle_rows() if row[4] == "landed"}
    assert all(re.fullmatch(r"[0-9a-f]{64}", d or "") for d in declared.values()), (
        "the bundle-table channel must carry the post-image digest it pins"
    )

    silent = tmp_path / "germline-amendment-silent-2026-09.md"
    silent.write_text(
        "This mentions CG-36 and cabinet/scripts/hooks/on-subagent-start.sh\n"
        "and declares nothing at all.\n",
        encoding="utf-8",
    )
    assert _declared_landing_targets(silent) == {}

    listed = tmp_path / "germline-amendment-listed-2026-09.md"
    listed.write_text(
        "prose naming cabinet/scripts/decoy.sh, which is not declared.\n"
        "\n"
        "landing:\n"
        "- cabinet/scripts/one.sh\n"
        "- `cabinet/scripts/two.sh`\n"
        "\n"
        "more prose\n",
        encoding="utf-8",
    )
    assert _declared_landing_targets(listed) == {
        "cabinet/scripts/one.sh": None,
        "cabinet/scripts/two.sh": None,
    }

    inline = tmp_path / "germline-amendment-inline-2026-09.md"
    inline.write_text("landing: cabinet/scripts/only.sh\n", encoding="utf-8")
    assert _declared_landing_targets(inline) == {"cabinet/scripts/only.sh": None}


def test_the_guard_is_not_exempted_on_this_branch():
    """The acknowledgement channel must not be what makes THIS branch green.

    U7's hard invariant — nothing under a locked path is modified — was correct
    for U7 and is lifted by A7.7 for the one file this branch lands, so the raw
    intersection is no longer empty here. That is precisely when a backstop
    stops being decoration, so this arm asserts the stronger property and
    asserts it from the TREE alone: every locked path in this branch's diff is
    one the package DECLARES it is landing, and holds exactly the bytes that
    package declares. Nothing below reads the environment, so no value of
    `CABINET_GERMLINE_LANDING` can make it pass.

    The acknowledgement channel IS driven here, and is shown to change nothing:
    a CG id with no ledger row does not vouch, and one undeclared locked path
    added to the set makes even this package's own row refuse.
    """
    base = _resolve_base(_REPO)
    changed = [
        line
        for line in _git(_REPO, "diff", "--name-only", f"{base}..HEAD").splitlines()
        if line.strip()
    ]
    if not changed:
        # On master itself the diff is empty BY CONSTRUCTION — HEAD is the
        # base — and that is the absence of a branch, not a disabled sensor.
        # Shipped unconditional, this arm was RED on master from the day U7
        # merged (measured on a pristine clone of 113b52c4, 2026-09-08): a
        # backstop that cannot be green on the trunk it protects is a broken
        # sensor, and the pressure to delete it is exactly what the round-2
        # review warned about. So the empty case is asserted to be empty for
        # the right REASON rather than waved through.
        assert base == _git(_REPO, "rev-parse", "HEAD"), (
            "the diff against the base is empty while HEAD is not the base, "
            "so this arm is comparing the wrong two revisions"
        )
        return

    offenders = _locked_offenders(changed, _locked())
    declared = _declared_landing_targets(_DOC)
    undeclared = [path for path in offenders if path not in declared]
    assert undeclared == [], (
        f"this branch touches locked paths this package never declared it is "
        f"landing: {undeclared}. Nothing routes around that — the need goes "
        "through a ledger row and a proposal package that names the bytes."
    )
    for path in offenders:
        assert _holds_declared_bytes(path, declared[path]), (
            f"{path} is a declared landing target but does not hold the bytes "
            "this package declares for it, so the branch landed something "
            "other than what the Captain is being asked to accept"
        )

    assert _landing_acknowledged(offenders, "CG-99999") is None
    assert _landing_acknowledged(
        offenders + [_NAMED_BUT_NOT_LANDED[0]], ROW_ID
    ) is None
