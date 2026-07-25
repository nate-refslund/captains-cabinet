"""CLAUDE.md <-> docs/templates/CLAUDE-egg.md lockstep ratchet (2026-07-25).

`egg-export.sh` swaps docs/templates/CLAUDE-egg.md in AS CLAUDE.md for the
public egg, so the template is the operating context every stranger's cabinet
boots with. Its header has always CLAIMED byte-identity with the live
CLAUDE.md below the comment — but nothing enforced it, and the two had
silently diverged: the template was missing the candor/dissent bullet, i.e.
the public cabinet shipped without the one governance property this project
leads with. Paper says "keep them in lockstep"; this makes it mechanical.

What it pins:
  * the template = a single leading HTML comment + a byte-identical copy of
    CLAUDE.md (so a CLAUDE.md edit that skips the template fails here, and
    the failure names the drifting lines);
  * the template carries no absolute home path and no captain identity
    token — it ships publicly, and the egg publish gate should never be the
    first thing to notice.

Deliberately NOT pinned: the header comment's wording (free to evolve).

Run: python3.12 -m pytest cabinet/scripts/tests/test_claude_egg_lockstep.py -q
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
LIVE = REPO / "CLAUDE.md"
EGG = REPO / "docs/templates/CLAUDE-egg.md"

# One leading HTML comment, then the body. Non-greedy so a comment inside the
# body (there is none today) can never swallow half the file.
HEADER_RE = re.compile(r"\A<!--.*?-->\n", re.DOTALL)


def _bodies() -> tuple[str, str]:
    live = LIVE.read_text(encoding="utf-8")
    egg = EGG.read_text(encoding="utf-8")
    stripped, n = HEADER_RE.subn("", egg, count=1)
    assert n == 1, (
        "docs/templates/CLAUDE-egg.md must open with the HTML comment that "
        "explains what it is; the export swap and this ratchet both key on it."
    )
    return live, stripped


@pytest.mark.skipif(not EGG.exists(), reason="egg template not in this tree")
def test_egg_template_body_matches_live_claude_md():
    live, egg_body = _bodies()
    if live != egg_body:
        diff = "\n".join(
            difflib.unified_diff(
                live.splitlines(),
                egg_body.splitlines(),
                fromfile="CLAUDE.md",
                tofile="docs/templates/CLAUDE-egg.md (header stripped)",
                lineterm="",
                n=1,
            )
        )
        pytest.fail(
            "CLAUDE.md and the egg template have drifted. The template ships "
            "AS CLAUDE.md in the public egg, so a divergence means strangers "
            "boot a different operating context than this cabinet runs.\n"
            "Fix: re-copy CLAUDE.md under the template's header comment in "
            f"the SAME commit as the CLAUDE.md edit.\n\n{diff}"
        )


@pytest.mark.skipif(not EGG.exists(), reason="egg template not in this tree")
def test_egg_template_carries_no_instance_identity():
    text = EGG.read_text(encoding="utf-8")
    home_paths = re.findall(r"/(?:Users|home)/[A-Za-z0-9._-]+", text)
    assert not home_paths, (
        f"absolute home paths in the public operating context: {home_paths}"
    )
    captain = _captain_tokens()
    hits = sorted({t for t in captain if re.search(rf"\b{re.escape(t)}\b", text, re.I)})
    assert not hits, f"captain identity tokens in the public operating context: {hits}"


def _captain_tokens() -> list[str]:
    """Identity strings from the live instance config, if this tree has one.

    An egg has no instance/config/platform.yml, so this degrades to the
    generic check above rather than keying on a bare env flag.
    """
    cfg = REPO / "instance/config/platform.yml"
    if not cfg.is_file():
        return []
    placeholders = {"captain", "founder", "owner", "none", "null", "unset",
                    "not set", "your name"}
    tokens: list[str] = []
    for line in cfg.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*(captain_name|captain_first_name)\s*:\s*(.+?)\s*$", line)
        if not m:
            continue
        # Strip a trailing YAML comment, then quotes. The whole remaining
        # value is ONE token: splitting it into words matches generic English
        # ("Captain", "not", "set") and turns this into a false-positive
        # machine.
        value = re.sub(r"\s+#.*$", "", m.group(2)).strip().strip("\"'")
        if len(value) < 3 or value.lower() in placeholders:
            continue
        tokens.append(value)
    return tokens
