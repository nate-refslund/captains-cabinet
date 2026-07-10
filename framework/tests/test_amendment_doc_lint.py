"""Generic doc-lint for ALL germline amendment packages (R031 merge).

One table-driven lint replacing the two dated files (the sovereign-posture
lint + test_axes_amendment_doc_lint.py). Each amendment document is the
Captain's apply contract — FROZEN once dated — and this lint keeps every
enumerated package honest against the tree it describes: the apply token is
present, every germline edit + new germline file is referenced (incl. ranged
golden-eval coverage where declared), the one-revert rollback names EVERY
germline file, paste-ready markdown blocks parse while already-logged
rulings are REFERENCED never re-pasted, package promises pin as anchors
(supersessions, dark lane, non-entries, evidence-pack invocations, Ring-0
additions) with superseded phrasings dead, and the union of ALL docs covers
every immutable-core Ring-0 entry. A new package = ONE table entry.

R031/R146 pairing decision (operative egg plan 2026-07-07): the
docs/proposals/germline-amendment-*.md docs ship as FOUNDING AMENDMENTS —
this lint reads the real proposals tree, no fixture. R146 keeps them in
place when archiving non-amendment proposals.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROPOSALS = _REPO_ROOT / "docs" / "proposals"

_PACKAGES = {
    "sovereign-posture": {
        "doc": "germline-amendment-sovereign-posture-2026-07-05.md",
        "apply_token": '"apply sovereign posture"',
        # spec §5 edit set + new-file set (incl. SOV-9a root apply lane)
        "germline_files": (
            "authority-matrix.yml", "matrix.py", "policy_engine.py",
            "policy-shadow.py", "run_action_lane.py", "action_exec.py",
            "actfirst_canary.py", "action_undo.py", "tell_surface.py",
            "consequence.py", "pre-tool-use.sh", "base-safety.yml",
            "germline-lock.sh", "courses-of-action.md", "posture.py",
            "grants.py", "needs.py", "gate.py", "apply_watch.py",
            "immutable-core.yml", "grant-apply.sh", "posture.yml",
            "standing-grants.yml", "gate-apply.sh",
            "com.cabinet.gate-apply.plist", "gate-apply-watch.jsonl",
        ),
        # 011..015 amended + 016..019 new — each named individually or via
        # an explicit contiguous range that includes it.
        "eval_coverage": {
            "ids": tuple(f"eval-01{i}" for i in range(1, 10)),
            "ranges": (("eval-011..015", 11, 15), ("eval-016..019", 16, 19)),
            "whole": ("evals 011-019", "golden evals 011-019"),
        },
        "rollback_re": r"\*\*One-revert rollback:\*\*(.*?)(?:\n---|\n## )",
        "rollback_skip": (),
        "rollback_extra": ("golden evals 011-019",),
        # Decision-B backfill must be a paste-ready markdown block
        "blocks": ((r"```markdown\n(## DECISION B.*?)```",
                    ("**What:**", "**Why:**", "**Captain:** Nate",
                     "chflags schg", "germline-lock.sh")),),
        # rulings referenced · ACT-AND-DRAFT encoded · supersessions + dark
        # lane named (cabinet-init §4 / evals wording / eval-014 letter /
        # courses-of-action §2 / do-not-load / binder arm switch)
        "anchors": (
            "## DECISION B", "SOVEREIGN POSTURE (2026-07-04",
            "ACT-AND-DRAFT (2026-07-04", "ACT-AND-DRAFT",
            "supersedes ACT-NOT-DRAFT", "per-item Captain approval ALWAYS",
            "NOT negotiable at init", "never UNCONDITIONAL auto",
            "unmeasured-cannot-auto", "ONLY relaxation",
            "com.cabinet.gate-apply", "Do NOT", "CABINET_NEEDS_WIRED",
        ),
        "anchors_lower": (), "flat_anchors": (),
        "any_of": (("do NOT re-paste", "reference only"),),
        "forbidden_lower": ("act-not-draft repair",),  # dead old phrase
    },
    "cabinet-axes": {
        "doc": "germline-amendment-cabinet-axes-2026-07-05.md",
        "apply_token": '"apply cabinet axes"',
        # feat/cabinet-axes edit set + new lockstep set
        "germline_files": (
            "authority-matrix.yml", "matrix.py", "posture.py", "grants.py",
            "policy_engine.py", "pre-tool-use.sh", "base-safety.yml",
            "germline-lock.sh", "immutable-core.yml", "axes-allowlist.yml",
            "trust_ladder.py", "axes-contract.md",
            "extension-manifest.schema.json", "validate-extension.sh",
            "posture-presets", "eval-020-axes-contract.md",
            "trust-ladder.yml",
        ),
        "eval_coverage": None,
        "rollback_re":
            r"\*\*One-revert rollback:\*\*(.*?)(?:\n---|\nReply )",
        # named eval-020-axes-contract.md in the new-set list; the rollback
        # references it as eval-020
        "rollback_skip": ("eval-020-axes-contract.md",),
        "rollback_extra": ("eval-020",),
        # paste-ready apply record
        "blocks": ((r"```markdown\n(## CABINET AXES APPLIED.*?)```",
                    ("**What:**", "**Why:**", "**Captain:** Nate",
                     "apply cabinet axes")),),
        # non-entries documented · instance-scoped external comms ·
        # byte-parity/opt-in promises · per-directory pytest evidence pack ·
        # axes-era Ring-0 additions (union test covers whole enumeration)
        "anchors": (
            "posture-narrow", "generate-services-cron.py", "NOT germline",
            "never_grant: [external_comms]", "ACT-AND-DRAFT",
            "never_grant it", "byte-identical", "opt-in", "render-only",
            "python3.12 -m pytest framework/ -q",
            "python3.12 -m pytest cabinet/scripts/lib/tests -q",
            "python3.12 -m pytest cabinet/scripts/gates/tests -q",
            "NEVER use the combined form",
            "framework/learning/trust_ladder.py",
            "framework/policies/axes-allowlist.yml",
            ".claude/rules/axes-contract.md",
            "framework/schemas/extension-manifest.schema.json",
            "cabinet/scripts/validate-extension.sh",
            "instance/config/trust-ladder.yml",
            "instance/config/posture-presets/",
        ),
        "anchors_lower": ("narrow", "fail-safe", "host"),
        # headings wrap across doc lines — matched on flattened whitespace
        "flat_anchors": (
            "THREE AUTONOMY LEVELS × FLAVORS × DEPLOYMENTS (2026-07-05",
            "EXTERNAL-COMMS GRANTABILITY IS INSTANCE-SCOPED, NOT "
            "FLAVOR-STRUCTURAL (2026-07-05",
        ),
        "any_of": (("do NOT re-paste", "reference only"),
                   ("render-only", "never installs")),
        "forbidden_lower": (),
    },
    "candor": {
        "doc": "germline-amendment-candor-2026-07-10.md",
        "apply_token": '"apply candor law"',
        # window-3 staged set: constitution values + role clauses + eval body
        # + the W4/W8 germline riders (agi-wires dead-wires 4 + 8)
        "germline_files": (
            "constitution-base.md", "cos.md", "_lane-ceo.md.template",
            "eval-024-candor.md", "action_lane.py", "run_action_lane.py",
            "session-start.sh",
        ),
        "eval_coverage": None,
        "rollback_re": r"\*\*One-revert rollback:\*\*(.*?)(?:\n---|\n## )",
        "rollback_skip": (),
        "rollback_extra": ("relock",),
        # paste-ready apply record for the Captain's decision ledger
        "blocks": ((r"```markdown\n(## CANDOR LAW APPLIED.*?)```",
                    ("**What:**", "**Why:**", "**Captain:** Nate",
                     "apply candor law")),),
        # candor clauses pinned · riders named · dark-lane branch named ·
        # non-germline enforcement half referenced · ceremony script named
        "anchors": (
            "candor-over-comfort", "dissent-then-obey", "EVAL-024-CANDOR",
            "flatter no one", "D12", "D15c", "W4", "W8",
            "feat/germline-window-3", "cabinet/evals/candor/",
            "germline-lock.sh", "WINDOW-RUNBOOK.md",
        ),
        "anchors_lower": ("agreement-as-target banned",
                          "silence is never agreement",
                          "evidence-cited dissent"),
        "flat_anchors": (),
        "any_of": (("do NOT re-paste", "reference only"),),
        "forbidden_lower": (),
    },
}

_PKG_IDS = sorted(_PACKAGES)


@lru_cache(maxsize=None)
def _text(fname: str) -> str:
    path = _PROPOSALS / fname
    assert path.is_file(), f"amendment package missing: {path}"
    return path.read_text()


@pytest.mark.parametrize("pkg", _PKG_IDS)
def test_apply_token_present(pkg):
    text = _text(_PACKAGES[pkg]["doc"])
    assert _PACKAGES[pkg]["apply_token"] in text
    assert "AWAITING CAPTAIN" in text


@pytest.mark.parametrize("pkg", _PKG_IDS)
def test_all_germline_files_referenced(pkg):
    spec = _PACKAGES[pkg]
    text = _text(spec["doc"])
    for name in spec["germline_files"]:
        assert name in text, \
            f"{pkg}: amendment must reference germline file {name}"
    ev_cov = spec["eval_coverage"]
    if ev_cov:
        for ev in ev_cov["ids"]:
            n = int(ev[-3:])
            ranged = (any(tok in text and lo <= n <= hi
                          for tok, lo, hi in ev_cov["ranges"])
                      or any(whole in text for whole in ev_cov["whole"]))
            assert ev in text or ranged, \
                f"{pkg}: amendment must reference {ev}"


@pytest.mark.parametrize("pkg", _PKG_IDS)
def test_rollback_names_every_germline_file(pkg):
    spec = _PACKAGES[pkg]
    m = re.search(spec["rollback_re"], _text(spec["doc"]), re.S)
    assert m, f"{pkg}: rollback section missing"
    rollback = m.group(1)
    for name in spec["germline_files"]:
        if name not in spec["rollback_skip"]:
            assert name in rollback, \
                f"{pkg}: rollback must name germline file {name}"
    for extra in spec["rollback_extra"]:
        assert extra in rollback, f"{pkg}: rollback missing {extra!r}"


@pytest.mark.parametrize("pkg", _PKG_IDS)
def test_paste_ready_blocks_parse(pkg):
    spec = _PACKAGES[pkg]
    text = _text(spec["doc"])
    for block_re, anchors in spec["blocks"]:
        m = re.search(block_re, text, re.S)
        assert m, f"{pkg}: paste-ready block {block_re!r} missing"
        for anchor in anchors:
            assert anchor in m.group(1), \
                f"{pkg}: paste-ready block missing {anchor!r}"


@pytest.mark.parametrize("pkg", _PKG_IDS)
def test_package_promises_pinned(pkg):
    spec = _PACKAGES[pkg]
    text = _text(spec["doc"])
    lower = text.lower()
    flat = re.sub(r"\s+", " ", text)
    for anchor in spec["anchors"]:
        assert anchor in text, f"{pkg}: amendment missing anchor {anchor!r}"
    for anchor in spec["anchors_lower"]:
        assert anchor in lower, f"{pkg}: amendment missing anchor {anchor!r}"
    for anchor in spec["flat_anchors"]:
        assert anchor in flat, f"{pkg}: amendment missing anchor {anchor!r}"
    for group in spec["any_of"]:
        assert any(a in text for a in group), \
            f"{pkg}: amendment must contain one of {group!r}"
    for phrase in spec["forbidden_lower"]:
        assert phrase not in lower, \
            f"{pkg}: superseded phrase {phrase!r} must not survive"


def test_every_immutable_core_entry_referenced():
    """The Ring-0 single source and the Captain contracts must agree: every
    enumerated path (by basename, or the exact path for ambiguous names)
    appears in SOME germline amendment doc. immutable-core grows amendment
    by amendment while each dated doc stays FROZEN, so the check runs over
    the union of docs/proposals/germline-amendment-*.md — an entry no
    Captain contract ever named is still a hard failure (cabinet-axes
    2026-07-05 extended the enumeration; the sovereign doc alone can no
    longer cover it)."""
    docs = sorted(_PROPOSALS.glob("germline-amendment-*.md"))
    for spec in _PACKAGES.values():
        assert _PROPOSALS / spec["doc"] in docs, \
            f"{spec['doc']} missing from proposals/"
    text = "\n".join(p.read_text() for p in docs)
    core = yaml.safe_load(
        (_REPO_ROOT / "framework" / "policies" / "immutable-core.yml")
        .read_text()
    )
    for kind in ("files", "dirs", "runtime_appended", "hook_protected"):
        for entry in core.get(kind) or []:
            path = entry["path"]
            base = path.rstrip("/").rsplit("/", 1)[-1]
            assert base in text or path in text, (
                f"immutable-core entry {path} not referenced in any "
                f"germline amendment doc"
            )
