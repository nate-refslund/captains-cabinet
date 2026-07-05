"""Doc-lint for the ONE sovereign-posture amendment package (SOV-9, spec §5).

The amendment document is the Captain's apply contract — this lint keeps it
honest against the tree it describes:

  * the apply token is present and unique-ish,
  * every germline edit the spec names is REFERENCED (staged-diffs clause),
  * the one-revert rollback names EVERY germline file,
  * the decisions section parses: Decision-B backfill is paste-ready, the two
    already-logged 2026-07-04 rulings are referenced (never re-pasted),
  * ACT-AND-DRAFT is the encoded ruling (act-not-draft only as the
    superseded name),
  * every immutable-core Ring-0 entry appears in the doc.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC = _REPO_ROOT / "docs" / "proposals" / \
    "germline-amendment-sovereign-posture-2026-07-05.md"

# The germline edit set of record (spec §5) — every one must be referenced in
# the doc AND named in the rollback.
_GERMLINE_EDITS = (
    "authority-matrix.yml", "matrix.py", "policy_engine.py",
    "policy-shadow.py", "run_action_lane.py", "action_exec.py",
    "actfirst_canary.py", "action_undo.py", "tell_surface.py",
    "consequence.py", "pre-tool-use.sh", "base-safety.yml",
    "germline-lock.sh", "courses-of-action.md",
)
_GERMLINE_NEW = (
    "posture.py", "grants.py", "needs.py", "gate.py", "apply_watch.py",
    "immutable-core.yml", "grant-apply.sh", "posture.yml",
    "standing-grants.yml",
    # SOV-9a: the root-executed apply lane is itself germline — the script,
    # the root-daemon definition, and the watch ledger cmd_watch feeds into
    # a root `git apply -R`.
    "gate-apply.sh", "com.cabinet.gate-apply.plist",
    "gate-apply-watch.jsonl",
)
_EVALS = tuple(f"eval-01{i}" for i in range(1, 10))


@lru_cache(maxsize=1)
def _doc() -> str:
    assert _DOC.is_file(), f"amendment package missing: {_DOC}"
    return _DOC.read_text()


def test_apply_token_present():
    text = _doc()
    assert '"apply sovereign posture"' in text
    assert "AWAITING CAPTAIN" in text


def test_all_staged_germline_diffs_referenced():
    text = _doc()
    for name in _GERMLINE_EDITS + _GERMLINE_NEW:
        assert name in text, f"amendment must reference germline file {name}"
    for ev in _EVALS:
        # 011..015 amended + 016..019 new — each named individually or via
        # an explicit contiguous range that includes it.
        n = int(ev[-3:])
        ranged = (
            ("eval-011..015" in text and 11 <= n <= 15)
            or ("eval-016..019" in text and 16 <= n <= 19)
            or ("evals 011-019" in text)
            or ("golden evals 011-019" in text)
        )
        assert ev in text or ranged, f"amendment must reference {ev}"


def test_rollback_names_every_germline_file():
    text = _doc()
    m = re.search(r"\*\*One-revert rollback:\*\*(.*?)(?:\n---|\n## )", text,
                  re.S)
    assert m, "rollback section missing"
    rollback = m.group(1)
    for name in _GERMLINE_EDITS + _GERMLINE_NEW:
        assert name in rollback, f"rollback must name germline file {name}"
    assert "golden evals 011-019" in rollback


def test_decision_entries_parse():
    text = _doc()
    # paste-ready backfill block
    assert "## DECISION B" in text
    m = re.search(r"```markdown\n(## DECISION B.*?)```", text, re.S)
    assert m, "Decision-B backfill must be a paste-ready markdown block"
    block = m.group(1)
    for anchor in ("**What:**", "**Why:**", "**Captain:** Nate",
                   "chflags schg", "germline-lock.sh"):
        assert anchor in block, f"Decision-B backfill missing {anchor!r}"
    # the two already-logged rulings are REFERENCED, not re-pasted
    assert "SOVEREIGN POSTURE (2026-07-04" in text
    assert "ACT-AND-DRAFT (2026-07-04" in text
    assert "do NOT re-paste" in text or "reference only" in text


def test_act_and_draft_is_the_encoded_ruling():
    text = _doc()
    assert "ACT-AND-DRAFT" in text
    assert "supersedes ACT-NOT-DRAFT" in text
    # the spec's old phrase must not survive as a live instruction
    assert "act-not-draft repair" not in text.lower()
    # external recipients stay per-item in every posture
    assert "per-item Captain approval ALWAYS" in text


def test_every_immutable_core_entry_referenced():
    """The Ring-0 single source and the Captain contract must agree: every
    enumerated path (by basename, or the exact path for ambiguous names)
    appears in the amendment."""
    text = _doc()
    core = yaml.safe_load(
        (_REPO_ROOT / "framework" / "policies" / "immutable-core.yml")
        .read_text()
    )
    for kind in ("files", "dirs", "runtime_appended", "hook_protected"):
        for entry in core.get(kind) or []:
            path = entry["path"]
            base = path.rstrip("/").rsplit("/", 1)[-1]
            assert base in text or path in text, (
                f"immutable-core entry {path} not referenced in the amendment"
            )


def test_supersessions_and_dark_lane_named():
    text = _doc()
    for anchor in (
        "NOT negotiable at init",          # cabinet-init §4 supersession
        "never UNCONDITIONAL auto",        # evals 011-015 wording
        "unmeasured-cannot-auto",          # eval-014 letter
        "ONLY relaxation",                 # courses-of-action §2
        "com.cabinet.gate-apply",          # dark lane named
        "Do NOT",                          # the do-not-load instruction
        "CABINET_NEEDS_WIRED",             # binder arm switch
    ):
        assert anchor in text, f"amendment missing anchor {anchor!r}"
