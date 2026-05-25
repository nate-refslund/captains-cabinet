"""Tests for compile-role.py — role compilation from base + lineage."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

# Import the compilation functions from compile-role.py
import importlib.util
import types

SCRIPT_DIR = Path(__file__).resolve().parent
_role_path = SCRIPT_DIR.parent.parent / "compile-role.py"
_spec = importlib.util.spec_from_file_location(
    "compile_role",
    _role_path,
)
compile_role_mod = types.ModuleType("compile_role")
compile_role_mod.__file__ = str(_role_path)
compile_role_mod.__spec__ = _spec
sys.modules["compile_role"] = compile_role_mod
_spec.loader.exec_module(compile_role_mod)

compile_role = compile_role_mod.compile_role
parse_adaptations = compile_role_mod.parse_adaptations
format_adaptations_section = compile_role_mod.format_adaptations_section
Adaptation = compile_role_mod.Adaptation


# ── Fixtures ─────────────────────────────────────────────────────────


SAMPLE_BASE = textwrap.dedent("""\
    # Chief Technology Officer (CTO)

    ## Identity

    You are the CTO. You own the codebase.

    ## Domain

    - Engineering
    - Architecture
    - Deployment
""")


def _write_base(tmp_path: Path, role: str, content: str = SAMPLE_BASE) -> Path:
    """Write a base role definition and return the base dir."""
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    (base_dir / f"{role}.md").write_text(content)
    return base_dir


def _write_lineage(
    tmp_path: Path,
    role: str,
    adaptations: list[dict] | None = None,
) -> Path:
    """Write a lineage YAML file and return the lineage dir."""
    lineage_dir = tmp_path / "lineage"
    lineage_dir.mkdir(exist_ok=True)

    lines = [
        f"role: {role}",
        f'base_definition: "presets/work/agents/{role}.md"',
    ]

    if adaptations is not None:
        lines.append("adaptations:")
        for a in adaptations:
            first = True
            for key, val in a.items():
                prefix = "  - " if first else "    "
                first = False
                lines.append(f'{prefix}{key}: "{val}"')

    (lineage_dir / f"{role}.yml").write_text("\n".join(lines) + "\n")
    return lineage_dir


# ── base + no lineage = exact copy ──────────────────────────────────


class TestBaseOnly:
    def test_no_lineage_file_exact_copy(self, tmp_path):
        base_dir = _write_base(tmp_path, "cto")
        lineage_dir = tmp_path / "lineage"
        lineage_dir.mkdir()  # exists but no file for this role
        output_dir = tmp_path / "output"

        compile_role("cto", base_dir, lineage_dir, output_dir)

        output = (output_dir / "cto.md").read_text()
        assert output == SAMPLE_BASE

    def test_empty_adaptations_list_exact_copy(self, tmp_path):
        base_dir = _write_base(tmp_path, "cto")
        lineage_dir = tmp_path / "lineage"
        lineage_dir.mkdir()
        # Write lineage with empty adaptations
        (lineage_dir / "cto.yml").write_text(
            'role: cto\nbase_definition: "presets/work/agents/cto.md"\n'
        )
        output_dir = tmp_path / "output"

        compile_role("cto", base_dir, lineage_dir, output_dir)

        output = (output_dir / "cto.md").read_text()
        assert output == SAMPLE_BASE


# ── base + adaptations ──────────────────────────────────────────────


class TestWithAdaptations:
    def test_one_adaptation(self, tmp_path):
        base_dir = _write_base(tmp_path, "cto")
        lineage_dir = _write_lineage(tmp_path, "cto", adaptations=[
            {
                "timestamp": "2026-05-25T10:00:00Z",
                "trigger": "reflection_loop",
                "evidence": "Repeated deploy failures from missing tests",
                "adaptation": "Run test suite before every deploy",
                "rationale": "3 deploy failures in 48h traced to untested changes",
                "approved_by": "captain",
            },
        ])
        output_dir = tmp_path / "output"

        compile_role("cto", base_dir, lineage_dir, output_dir)

        output = (output_dir / "cto.md").read_text()
        assert SAMPLE_BASE.rstrip("\n") in output
        assert "## Adaptations" in output
        assert "reflection_loop" in output
        assert "Run test suite before every deploy" in output
        assert "approved by captain" in output

    def test_multiple_adaptations_chronological(self, tmp_path):
        base_dir = _write_base(tmp_path, "cto")
        lineage_dir = _write_lineage(tmp_path, "cto", adaptations=[
            {
                "timestamp": "2026-05-20T08:00:00Z",
                "trigger": "retro",
                "evidence": "First finding",
                "adaptation": "First adaptation",
                "rationale": "First rationale",
            },
            {
                "timestamp": "2026-05-25T10:00:00Z",
                "trigger": "captain_directive",
                "evidence": "Second finding",
                "adaptation": "Second adaptation",
                "rationale": "Second rationale",
                "approved_by": "captain",
            },
        ])
        output_dir = tmp_path / "output"

        compile_role("cto", base_dir, lineage_dir, output_dir)

        output = (output_dir / "cto.md").read_text()
        assert "## Adaptations" in output
        # Both entries present
        assert "First adaptation" in output
        assert "Second adaptation" in output
        # Chronological order: first appears before second
        pos_first = output.index("First adaptation")
        pos_second = output.index("Second adaptation")
        assert pos_first < pos_second


# ── Validation Errors ────────────────────────────────────────────────


class TestValidation:
    def test_missing_required_field_raises(self):
        """Adaptation missing 'rationale' should raise ValueError."""
        with pytest.raises(ValueError, match="rationale"):
            parse_adaptations([{
                "timestamp": "2026-05-25T10:00:00Z",
                "trigger": "retro",
                "evidence": "some evidence",
                "adaptation": "some adaptation",
                # missing rationale
            }])

    def test_multiple_missing_fields(self):
        with pytest.raises(ValueError, match="missing required fields"):
            parse_adaptations([{
                "timestamp": "2026-05-25T10:00:00Z",
                # missing trigger, evidence, adaptation, rationale
            }])

    def test_nonexistent_base_role_raises(self, tmp_path):
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        lineage_dir = tmp_path / "lineage"
        lineage_dir.mkdir()
        output_dir = tmp_path / "output"

        with pytest.raises(FileNotFoundError, match="not found"):
            compile_role("nonexistent", base_dir, lineage_dir, output_dir)


# ── Output Directory ─────────────────────────────────────────────────


class TestOutputDirectory:
    def test_output_dir_created_if_missing(self, tmp_path):
        base_dir = _write_base(tmp_path, "cto")
        lineage_dir = tmp_path / "lineage"
        lineage_dir.mkdir()
        output_dir = tmp_path / "nested" / "output"

        compile_role("cto", base_dir, lineage_dir, output_dir)

        assert output_dir.exists()
        assert (output_dir / "cto.md").exists()

    def test_returns_output_path(self, tmp_path):
        base_dir = _write_base(tmp_path, "cto")
        lineage_dir = tmp_path / "lineage"
        lineage_dir.mkdir()
        output_dir = tmp_path / "output"

        result = compile_role("cto", base_dir, lineage_dir, output_dir)
        assert result == output_dir / "cto.md"


# ── Adaptation Formatting ───────────────────────────────────────────


class TestFormatting:
    def test_adaptation_without_approval(self):
        """Adaptation without approved_by should not show '(approved by ...)'."""
        section = format_adaptations_section([Adaptation(
            timestamp="2026-05-25T10:00:00Z",
            trigger="retro",
            evidence="finding",
            adaptation="change",
            rationale="reason",
            approved_by=None,
        )])
        assert "approved by" not in section

    def test_adaptation_with_approval(self):
        section = format_adaptations_section([Adaptation(
            timestamp="2026-05-25T10:00:00Z",
            trigger="retro",
            evidence="finding",
            adaptation="change",
            rationale="reason",
            approved_by="captain",
        )])
        assert "(approved by captain)" in section
