"""THE SHIPPED SURFACES sweep — the second half of "the dead instruction is
gone" (A1.4).

Its sibling (framework/onboarding/tests/test_no_manual_ratify_text.py) covers
the three CODE surfaces that wrote the sentence. This one covers everything a
person READS and the egg SHIPS: the skills, the operator docs, the presets, the
demo fixtures, the runbooks. It lives outside framework/ because naming those
trees from inside framework/ is a layer coupling the tree's own gate refuses,
and the check is about the repo's documentation surface rather than framework
logic.

BOTH DIRECTIONS, because a negative grep alone passes on an empty tree:

  * every scanned tree must EXIST and the scan must be non-empty;
  * the dead sentence appears nowhere;
  * the sanctioned phrase appears SOMEWHERE in the shipped set, so deleting the
    surfaces rather than fixing them turns this red.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from framework.onboarding import genesis  # noqa: E402

#: The sentence, in every wording the tree has ever carried it in.
_DEAD = re.compile(
    r"mov(?:e|ing) (?:the |a |it )?(?:row )?into +[`']?instance/config/outcomes\.yml",
    re.IGNORECASE)

#: What a person reads and what the egg ships. `docs/plans`, `docs/proposals`
#: and `docs/launch` are dated records of what was true when written and are
#: excluded by the same rule the repo's docs sweep uses.
_SWEEP_DIRS = (
    ".claude/skills",
    "cabinet/docs",
    "presets",
    "cabinet/fixtures",
    "docs/runbooks",
)
_SUFFIXES = (".md", ".py", ".yml", ".yaml", ".txt", ".template")


def _paths() -> list:
    out = []
    for rel in _SWEEP_DIRS:
        root = _REPO / rel
        assert root.is_dir(), "%s left the tree — this sweep now checks nothing" % rel
        found = [p for p in sorted(root.rglob("*"))
                 if p.is_file() and p.suffix in _SUFFIXES]
        assert found, "%s matched no files — a broken glob reads as compliance" % rel
        out.extend(found)
    return out


def test_the_sweep_reaches_the_shipped_surfaces():
    paths = _paths()
    assert len(paths) > 100, "the sweep collapsed to %d files" % len(paths)


def test_no_shipped_surface_says_move_the_row():
    offenders = []
    for path in _paths():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _DEAD.search(line):
                offenders.append("%s:%d" % (path.relative_to(_REPO), lineno))
    assert offenders == [], (
        "these shipped surfaces still tell the operator to ratify by hand: %s"
        % offenders)


def test_the_sanctioned_phrase_is_on_a_shipped_surface():
    """POSITIVE arm: deleting the surfaces instead of fixing them is red."""
    hint = getattr(genesis, "RATIFY_HINT", None)
    assert hint, "no sanctioned ratify phrase exists to put on these surfaces"
    carriers = []
    for path in _paths():
        try:
            if hint in path.read_text(encoding="utf-8"):
                carriers.append(str(path.relative_to(_REPO)))
        except (OSError, UnicodeDecodeError):
            continue
    assert carriers, (
        "no shipped surface carries %r — the dead sentence was removed and "
        "nothing replaced it" % hint)
