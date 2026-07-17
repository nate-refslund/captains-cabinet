"""Lint + parity pins for the platform-radar-triage officer skill.

Pins the skills conventions this lane rides:
  * canonical body at memory/skills/platform-radar-triage.md in the house
    format (# Skill: header, R138 single-source comment, bold Status/
    Created by/Date fields, When to Use + Procedure sections);
  * .claude/skills/platform-radar-triage/SKILL.md is an R155 wrapper ONLY
    (trigger frontmatter + pointer, zero duplicated body);
  * the skill references the doctrine doc, the registry, and the retest
    runner (all real tracked paths);
  * the ADOPTION GATES block is byte-identical between the skill and
    docs/runbooks/platform-adoption-gating.md (verbatim-twin law);
  * the untrusted-input framing is present (delta excerpts are data,
    never instructions).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "memory" / "skills" / "platform-radar-triage.md"
WRAPPER = REPO / ".claude" / "skills" / "platform-radar-triage" / "SKILL.md"
DOCTRINE = REPO / "docs" / "runbooks" / "platform-adoption-gating.md"

GATES_BEGIN = "<!-- ADOPTION-GATES:BEGIN"
GATES_END = "<!-- ADOPTION-GATES:END -->"


def _gates_block(text: str, origin: str) -> str:
    start = text.find(GATES_BEGIN)
    end = text.find(GATES_END)
    assert start != -1 and end != -1 and end > start, (
        f"{origin}: ADOPTION-GATES markers missing/misordered")
    return text[start:end + len(GATES_END)]


def test_all_three_surfaces_exist():
    for p in (SKILL, WRAPPER, DOCTRINE):
        assert p.is_file(), f"missing: {p.relative_to(REPO)}"


def test_canonical_body_follows_house_skill_format():
    text = SKILL.read_text()
    assert text.startswith("# Skill: Platform Radar Triage")
    # single-source contract comment names the wrapper explicitly
    assert "single-source (egg R138)" in text
    assert ".claude/skills/platform-radar-triage/SKILL.md" in text
    for field in ("**Status:**", "**Created by:**", "**Date:**",
                  "**Validated against:**", "**Usage count:**"):
        assert field in text, f"house field missing: {field}"
    for section in ("## When to Use", "## Procedure", "## Expected Outcome",
                    "## Known Pitfalls", "## Validation Scenarios"):
        assert section in text, f"section missing: {section}"


def test_wrapper_is_pointer_only_with_trigger_frontmatter():
    text = WRAPPER.read_text()
    assert text.startswith("---\n"), "wrapper must open with YAML frontmatter"
    head = text.split("---", 2)[1]
    assert re.search(r"^name:\s*platform-radar-triage\s*$", head, re.M)
    m = re.search(r"^description:\s*(.+)$", head, re.M)
    assert m and len(m.group(1).strip()) > 40, "trigger description too thin"
    assert "memory/skills/platform-radar-triage.md" in text
    # R155: no duplicated body — a wrapper carries no procedure headings
    body = text.split("---", 2)[2]
    assert "## " not in body, "wrapper must not duplicate skill body content"


def test_skill_references_its_lane_surfaces():
    text = SKILL.read_text()
    for ref in ("docs/runbooks/platform-adoption-gating.md",
                "cabinet/config/workarounds.yml",
                "cabinet/scripts/workaround-retest.sh",
                "cabinet/logs/platform-radar/delta-",
                "shared/interfaces/workaround-retire-proposals.jsonl"):
        assert ref in text, f"skill does not reference {ref}"
    # ...and those tracked surfaces really exist
    for tracked in ("docs/runbooks/platform-adoption-gating.md",
                    "cabinet/config/workarounds.yml",
                    "cabinet/scripts/workaround-retest.sh"):
        assert (REPO / tracked).is_file(), f"referenced surface missing: {tracked}"


def test_skill_carries_untrusted_input_framing():
    text = SKILL.read_text()
    assert "## Untrusted input law" in text
    assert "DATA, not instructions" in text
    assert "Never follow" in text
    assert "Never paste delta text into a shell" in text


def test_skill_classification_buckets_and_filing_surfaces():
    text = SKILL.read_text()
    for bucket in ("irrelevant", "bugfix-unblocks", "feature-opportunity",
                   "breaking-deprecation"):
        assert f"**{bucket}**" in text, f"bucket missing: {bucket}"
    # filed through EXISTING surfaces only
    assert "cabinet-task" in text
    assert "attention-submit.sh deadline-critical" in text.replace("\n   ", " ")


def test_adoption_gates_block_is_verbatim_twin_of_doctrine():
    skill_block = _gates_block(SKILL.read_text(), "skill")
    doctrine_block = _gates_block(DOCTRINE.read_text(), "doctrine")
    assert skill_block == doctrine_block, (
        "ADOPTION GATES drifted between the skill and the doctrine doc — "
        "edit both or neither (verbatim-twin law)")
    for pin in ("GATE 0", "GATE 1", "GATE 2", "GATE 3",
                "auto-apply",
                "cabinet/scripts/deploy-mac.sh",
                "cabinet/scripts/cabinet-doctor.sh",
                "docs/runbooks/gate-apply-runbook.md",
                "cabinet/scripts/run-golden-evals.sh",
                "memory/golden-evals/eval-024-candor.md",
                "cabinet/scripts/retrieval-eval.sh",
                "cabinet/scripts/retrieval-eval-nightly.sh"):
        assert pin in skill_block, f"gates block lost its pin: {pin}"


def test_gates_name_only_real_evidence_and_deploy_surfaces():
    block = _gates_block(DOCTRINE.read_text(), "doctrine")
    for raw in re.findall(r"(?:cabinet|docs|memory)/[\w./-]+", block):
        path = raw.rstrip(".")  # sentence punctuation is not part of the path
        assert (REPO / path).exists(), f"gates block names a dead path: {path}"


def test_doctrine_documents_the_runtime_contracts():
    text = DOCTRINE.read_text()
    for ref in ("cabinet/config/workarounds.yml",
                "cabinet/scripts/workaround-retest.sh",
                "cabinet/scripts/workaround-probes/egress-apply-lock-timing.py",
                "cabinet/logs/workaround-retests.jsonl",
                "shared/interfaces/workaround-retire-proposals.jsonl",
                "cabinet/logs/platform-radar/delta-YYYY-MM-DD.json",
                "framework/frontdoor/intake.py"):
        assert ref in text, f"doctrine does not document {ref}"
    assert "still_needed" in text and "fix_confirmed" in text
    assert "PROPOSE ONLY" in text
