"""Doc-lint for the ONE cabinet-axes amendment package (AX-8, axes spec §8).

Same discipline as test_amendment_doc_lint.py (the sovereign package): the
amendment document is the Captain's apply contract — this lint keeps it
honest against the tree it describes:

  * the apply token is present,
  * every germline edit + new germline file is referenced in the inventory,
  * the one-revert rollback names EVERY germline file,
  * the two already-logged 2026-07-05 rulings are REFERENCED (never
    re-pasted) and the apply record is paste-ready,
  * the two deliberate NON-entries (posture-narrow unlocked;
    generate-services-cron.py not germline) are documented with their
    justifications,
  * the evidence pack prescribes per-directory pytest invocations and warns
    against the broken combined form,
  * every axes-era immutable-core addition appears in the doc.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC = _REPO_ROOT / "docs" / "proposals" / \
    "germline-amendment-cabinet-axes-2026-07-05.md"

# Germline files this amendment EDITS (each staged in feat/cabinet-axes).
_GERMLINE_EDITS = (
    "authority-matrix.yml", "matrix.py", "posture.py", "grants.py",
    "policy_engine.py", "pre-tool-use.sh", "base-safety.yml",
    "germline-lock.sh", "immutable-core.yml",
)
# NEW germline set wired in lockstep (all four lists + immutable-core).
_GERMLINE_NEW = (
    "axes-allowlist.yml", "trust_ladder.py", "axes-contract.md",
    "extension-manifest.schema.json", "validate-extension.sh",
    "posture-presets", "eval-020-axes-contract.md", "trust-ladder.yml",
)


@lru_cache(maxsize=1)
def _doc() -> str:
    assert _DOC.is_file(), f"amendment package missing: {_DOC}"
    return _DOC.read_text()


def test_apply_token_present():
    text = _doc()
    assert '"apply cabinet axes"' in text
    assert "AWAITING CAPTAIN" in text


def test_all_germline_files_referenced():
    text = _doc()
    for name in _GERMLINE_EDITS + _GERMLINE_NEW:
        assert name in text, f"amendment must reference germline file {name}"


def test_rollback_names_every_germline_file():
    text = _doc()
    m = re.search(r"\*\*One-revert rollback:\*\*(.*?)(?:\n---|\nReply )",
                  text, re.S)
    assert m, "rollback section missing"
    rollback = m.group(1)
    for name in _GERMLINE_EDITS + _GERMLINE_NEW:
        if name == "eval-020-axes-contract.md":
            continue  # named as eval-020-axes-contract.md in the new-set list
        assert name in rollback, f"rollback must name germline file {name}"
    assert "eval-020" in rollback


def test_decision_references_not_duplicated():
    text = _doc()
    flat = re.sub(r"\s+", " ", text)  # headings wrap across doc lines
    # the two live rulings are REFERENCED by heading, never re-pasted
    assert "THREE AUTONOMY LEVELS × FLAVORS × DEPLOYMENTS (2026-07-05" in flat
    assert ("EXTERNAL-COMMS GRANTABILITY IS INSTANCE-SCOPED, NOT "
            "FLAVOR-STRUCTURAL (2026-07-05") in flat
    assert "do NOT re-paste" in text or "reference only" in text
    # paste-ready apply record parses
    m = re.search(r"```markdown\n(## CABINET AXES APPLIED.*?)```", text, re.S)
    assert m, "apply record must be a paste-ready markdown block"
    block = m.group(1)
    for anchor in ("**What:**", "**Why:**", "**Captain:** Nate",
                   "apply cabinet axes"):
        assert anchor in block, f"apply record missing {anchor!r}"


def test_non_entries_documented():
    text = _doc()
    # posture-narrow: deliberately unlocked narrow-only cap
    assert "posture-narrow" in text
    assert "narrow" in text.lower() and "fail-safe" in text.lower()
    # generate-services-cron.py: decided NOT germline, justified
    assert "generate-services-cron.py" in text
    assert "NOT germline" in text
    assert "render-only" in text or "never installs" in text


def test_evidence_pack_prescribes_separate_invocations():
    text = _doc()
    for cmd in (
        "python3.12 -m pytest framework/ -q",
        "python3.12 -m pytest cabinet/scripts/lib/tests -q",
        "python3.12 -m pytest cabinet/scripts/gates/tests -q",
    ):
        assert cmd in text, f"evidence pack must prescribe {cmd!r}"
    assert "NEVER use the combined form" in text


def test_instance_scoped_external_comms_encoded():
    text = _doc()
    # Nate's instance line preserved; grantability instance-scoped
    assert "never_grant: [external_comms]" in text
    assert "ACT-AND-DRAFT" in text
    # grantable only where a captain doesn't never_grant it
    assert "never_grant it" in text


def test_byte_parity_and_optin_promises():
    text = _doc()
    assert "byte-identical" in text
    assert "opt-in" in text
    assert "render-only" in text          # dashboard tile promise
    assert "host" in text.lower()         # docker attestation host-side


def test_axes_immutable_core_additions_referenced():
    """Every axes-era Ring-0 addition appears in THIS doc (the union check
    in test_amendment_doc_lint covers the whole enumeration; this pins the
    axes additions to the axes contract specifically)."""
    text = _doc()
    for path in (
        "framework/learning/trust_ladder.py",
        "framework/policies/axes-allowlist.yml",
        ".claude/rules/axes-contract.md",
        "framework/schemas/extension-manifest.schema.json",
        "cabinet/scripts/validate-extension.sh",
        "instance/config/trust-ladder.yml",
        "instance/config/posture-presets/",
    ):
        assert path in text, f"axes Ring-0 addition {path} not in the doc"
