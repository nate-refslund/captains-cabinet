"""The sandbox fence for every test that can set or clear the judging freeze.

WHY THIS FILE EXISTS (incident 2026-07-27, sibling of the killswitch fence).
``test_tamper_drill.py`` armed the evidence judging-freeze at ``_REPO_ROOT``
— the REAL checkout the test runs in — and cleaned up with
``finally: _thaw(_REPO_ROOT)``, which lifts the marker's immutable flag and
unlinks it.

``framework.evidence_freeze.freeze`` is FIRST-FREEZE-WINS. So when a genuine
Captain freeze was already armed, the test's own freeze was a no-op, its
``set_by == "pytest"`` assertion failed — and the ``finally`` **deleted the
Captain's marker anyway**, bypassing ``captain_clear``, the token-gated
unfreeze the marker itself names as the only way out. Reproduced: a marker
written with ``set_by="captain"`` and ``uchg`` set was gone after one
single-test pytest run, and the red said nothing about what had happened.

That is the same class as a test that arms the emergency stop: a test must
never put a live safety switch in its write set. Clearing this one is
Captain-only by design, so a test that clears it is a test that can silently
undo a Captain decision.

WHY A PSEUDO-ROOT AND NOT A FENCE VARIABLE. ``evidence_freeze.marker_path``
takes an EXPLICIT root and consults no environment variable — deliberately
(A10 posture: "no officer-influenceable variable can steer where the marker
lives"). There is therefore no knob to redirect, and adding one would weaken
the very property that docstring is claiming. The fix is a throwaway repo
root: :func:`pseudo_root` builds a directory that IS a repo root as far as
the drill's own ``Path(__file__).resolve().parents[2]`` is concerned — the
script is COPIED in (a symlink would resolve back to the real checkout and
re-aim everything at it) and ``framework/`` is linked so the copy imports the
same live modules.

WHY THE CHANNEL SET IS DERIVED, NOT ASSERTED IN A COMMENT. "It takes no env
var" is exactly the kind of claim that silently stops being true.
:func:`derive_channels` reads the resolver's source and reports the
environment variables it consults; :func:`assert_isolated` REFUSES if that
set is non-empty, because a variable this module has never heard of cannot be
pinned at the sandbox. The day someone adds ``CABINET_FREEZE_MARKER``, every
fenced test refuses instead of quietly writing somewhere else.

WHY ISOLATION IS PROVEN, NOT ASSUMED. :func:`assert_isolated` does not
re-derive the marker location. It asks the two REAL resolvers where they
would write — ``evidence_freeze.marker_path`` for library calls, and the
drill's own ``freeze-status`` verb for subprocess calls, which prints the
path its own ``_REPO_ROOT`` resolved to. Whatever those honour, today or
after a refactor, is covered by construction. Anything unprovable is a
refusal, before the child runs.

NOTE ON CI: a fresh checkout has no armed freeze, so the deletion is
INVISIBLE on every runner — the pre-fix file passes there and destroys a
marker only on a box where one is armed. Any guard over this must arm a
canary freeze deliberately or it is vacuous. See
``test_safety_switch_test_fence.py``.

Shape deliberately mirrors ``lib_killswitch_fence`` (derive from the reader,
prove with the real resolver, fail closed) so there is one dialect for
"a test may not touch a live safety switch", not two.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FREEZE_MODULE = REPO / "framework" / "evidence_freeze.py"
DRILL = REPO / "cabinet" / "scripts" / "evidence-tamper-drill.py"

#: Interpreter/runtime variables that appear near the resolver but steer
#: nothing about WHERE the marker lands.
_NOT_A_CHANNEL = frozenset({
    "PATH", "HOME", "PWD", "PYTHONDONTWRITEBYTECODE", "TMPDIR",
})

#: Environment channels this module knows how to pin at a sandbox. It is
#: EMPTY on purpose: the marker path is a pure function of an explicit root.
#: Anything :func:`derive_channels` finds that is not in here makes the fence
#: refuse rather than under-fence.
_HANDLERS: frozenset[str] = frozenset()


class FreezeFenceError(AssertionError):
    """Raised when isolation cannot be PROVEN. Never downgrade to a warning."""


def _py_env_refs(text: str) -> set[str]:
    """Environment variables a Python source consults.

    Same extraction as ``lib_killswitch_fence._py_env_refs`` — one dialect for
    both fences — covering ``os.environ["X"]``, ``os.environ.get("X")`` and
    ``os.getenv("X")``.
    """
    pattern = r'os\.(?:environ(?:\.get)?\(?\[?|getenv\()["\']([A-Za-z_][A-Za-z0-9_]*)["\']'
    return set(re.findall(pattern, text))


def derive_channels() -> set[str]:
    """Every env var that steers where the judging-freeze marker lands.

    Read FROM the code that resolves it, never from a list here. The source is
    ``framework/evidence_freeze.py`` alone: ``marker_path`` is documented as
    "the SINGLE expression of the marker location", so the whole module is the
    routing surface, and every other writer — the drill included — goes through
    it.

    The DRILL is deliberately NOT scanned. It does not resolve a marker path;
    it resolves a repo ROOT and hands it to ``marker_path``. Which root it
    picks is covered DYNAMICALLY instead, by :func:`resolve_drill_marker`
    asking the drill itself in the exact configuration under test — stronger
    than a static scan, and it does not drag the drill's unrelated variables
    (``CABINET_CHAIR_OFFICER``, the paging channel) into a set this fence would
    then have to keep an exclusion list for. Hand-maintained exclusion lists
    are the drift this whole family of fences exists to avoid.

    Expected to be EMPTY. A non-empty result is drift, and the fence refuses.
    """
    if not FREEZE_MODULE.is_file():
        raise FreezeFenceError(
            f"cannot derive freeze channels: resolver missing at {FREEZE_MODULE}")
    found = _py_env_refs(FREEZE_MODULE.read_text(encoding="utf-8"))
    return {
        v for v in found
        if v.isupper() and not v.startswith("_") and v not in _NOT_A_CHANNEL
    }


def pseudo_root(base: "Path | str", name: str = "pseudo-repo") -> Path:
    """A throwaway directory the drill resolves as ITS repo root.

    The drill computes ``_REPO_ROOT = Path(__file__).resolve().parents[2]``, so
    the script is COPIED (``.resolve()`` follows a symlink straight back to the
    real checkout, which would re-aim every write at it) and ``framework/`` is
    symlinked so the copy imports the SAME live modules the real drill does —
    the sensor stays wired to the live artifact, only the root moves.
    """
    root = Path(base) / name
    (root / "cabinet" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    if not DRILL.is_file():
        raise FreezeFenceError(f"tamper drill missing at {DRILL}")
    for rel in ("evidence-tamper-drill.py", "evidence-anchor.py"):
        src = REPO / "cabinet" / "scripts" / rel
        if src.is_file():
            dst = root / "cabinet" / "scripts" / rel
            shutil.copy2(src, dst)
            if dst.read_bytes() != src.read_bytes():
                raise FreezeFenceError(f"pseudo-root copy of {rel} is not byte-identical")
    triggers = REPO / "cabinet" / "scripts" / "lib" / "triggers.sh"
    if triggers.is_file():
        shutil.copy2(triggers, root / "cabinet" / "scripts" / "lib" / "triggers.sh")
    link = root / "framework"
    if not link.exists():
        link.symlink_to(REPO / "framework", target_is_directory=True)
    return root


def drill_in(root: "Path | str") -> Path:
    """The drill copy that belongs to ``root`` (never the real checkout's)."""
    return Path(root) / "cabinet" / "scripts" / "evidence-tamper-drill.py"


def resolve_marker(root: "Path | str") -> Path:
    """Where the REAL ``evidence_freeze.marker_path`` would write for ``root``."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework import evidence_freeze  # local import: real module, no copy
    return Path(evidence_freeze.marker_path(root))


def resolve_drill_marker(root: "Path | str") -> Path:
    """Ask the REAL drill where ITS freeze marker is, in this configuration.

    Not a re-derivation: runs ``evidence-tamper-drill.py freeze-status`` with
    NO ``--root``, whose default is the drill's own resolved ``_REPO_ROOT``, and
    reports the ``path`` it prints. Whatever the drill resolves — today or after
    a refactor of that resolution — is what this returns.
    """
    script = drill_in(root)
    if not script.is_file():
        raise FreezeFenceError(
            f"no drill copy at {script}; build the sandbox with pseudo_root()")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "freeze-status"],
            capture_output=True, text=True, timeout=120, cwd=str(root), env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise FreezeFenceError(
            f"could not run the drill to prove freeze isolation: {exc}")
    if proc.returncode != 0:
        raise FreezeFenceError(
            "the drill refused to report its freeze status "
            f"(rc={proc.returncode}): {proc.stderr.strip()[:200]}")
    try:
        return Path(json.loads(proc.stdout)["path"])
    except (ValueError, KeyError) as exc:
        raise FreezeFenceError(f"unreadable freeze-status frame: {proc.stdout!r} ({exc})")


def assert_isolated(root: "Path | str", *, sandbox: "Path | str",
                    check_drill: bool = True) -> Path:
    """Refuse unless the REAL resolvers prove this root writes inside ``sandbox``.

    Fail-closed and legible: the message names where the write would have
    landed, because the failure this prevents is the deletion of a Captain
    freeze that only a Captain token may clear.
    """
    unknown = derive_channels() - _HANDLERS
    if unknown:
        raise FreezeFenceError(
            "the judging-freeze resolver has grown environment channel(s) this "
            f"fence cannot pin at a sandbox: {sorted(unknown)}. The marker path "
            "was a pure function of an explicit root; it is not any more, so a "
            "test cannot prove where it writes. Teach lib_freeze_fence._HANDLERS "
            "how to redirect them (and prove it), then re-run.")

    sandbox = Path(sandbox).resolve()
    root_path = Path(root).resolve()
    if sandbox not in root_path.parents and root_path != sandbox:
        raise FreezeFenceError(
            f"REFUSING TO RUN: freeze root {root_path} is not inside this "
            f"test's sandbox {sandbox}. `_thaw`/`captain_clear` unlink the "
            "resolved marker — outside a sandbox that is a live Captain freeze.")

    marker = resolve_marker(root_path).resolve()
    if sandbox not in marker.parents:
        raise FreezeFenceError(
            f"REFUSING TO RUN: evidence_freeze.marker_path would write "
            f"{marker}, which is outside this test's sandbox {sandbox}.")
    if check_drill:
        drill_marker = resolve_drill_marker(root_path).resolve()
        if drill_marker != marker:
            raise FreezeFenceError(
                f"REFUSING TO RUN: the drill resolves its freeze marker to "
                f"{drill_marker} but the library resolves {marker} — the test "
                "would assert against one marker while the subprocess wrote "
                "the other. This is the 2026-07-27 incident's shape.")
    return marker


def fingerprint(root: "Path | str") -> "tuple[bool, bytes | None]":
    """A change-detecting read of a marker, safe on the REAL checkout.

    ``assert not is_frozen(real_root)`` is the wrong sensor for "the drill did
    not freeze the repo": it goes red on a runtime box where the Captain has
    legitimately armed a freeze, reporting a defect that did not happen. What
    the tests actually mean is "this run did not CHANGE the marker", so they
    compare this before and after. Never raises.
    """
    path = resolve_marker(root)
    try:
        return (True, path.read_bytes())
    except FileNotFoundError:
        return (False, None)
    except OSError:
        return (True, None)          # present but unreadable — still frozen


def thaw(root: "Path | str", *, sandbox: "Path | str") -> None:
    """The ONLY sanctioned marker removal in a test. Fenced before it unlinks.

    ``evidence_freeze._lift_immutable`` + ``unlink`` is the Captain-clear
    primitive with the token check removed, so it may only ever be pointed at a
    marker this test created inside its own sandbox. The fence runs FIRST: an
    unfenced root raises instead of deleting.
    """
    assert_isolated(root, sandbox=sandbox, check_drill=False)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from framework import evidence_freeze
    marker = Path(evidence_freeze.marker_path(root))
    evidence_freeze._lift_immutable(marker)
    try:
        marker.unlink()
    except OSError:
        pass
