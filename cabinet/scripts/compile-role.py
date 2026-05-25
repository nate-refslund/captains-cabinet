#!/usr/bin/env python3
"""Compile role definitions from base archetype + lineage adaptations.

Usage:
  python3 compile-role.py <role> [--base-dir DIR] [--lineage-dir DIR] [--output-dir DIR]
  python3 compile-role.py --all   # compile all roles

The compiler:
1. Reads base role definition from presets/<active>/agents/<role>.md
2. Reads lineage from instance/memory/role-lineage/<role>.yml (if exists)
3. If lineage has adaptations, appends an ## Adaptations section
4. Writes compiled role to .claude/agents/<role>.md
5. Key invariant: base + empty/missing lineage = exact copy of base
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent


def _read_active_preset(repo_root: Path) -> str:
    """Read the active preset name from instance config."""
    preset_file = repo_root / "instance" / "config" / "active-preset"
    if preset_file.exists():
        return preset_file.read_text().strip()
    return "work"


def load_yaml_simple(path: Path) -> dict:
    """Load YAML, trying PyYAML first, falling back to minimal parser.

    Supports the lineage YAML structure:
      role: <string>
      base_definition: <string>
      adaptations:
        - timestamp: <string>
          trigger: <string>
          evidence: <string>
          adaptation: <string>
          rationale: <string>
          approved_by: <string>
    """
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except (ImportError, AttributeError):
        pass

    # Minimal parser for lineage YAML
    data: dict = {}
    adaptations: list[dict] = []
    current_adaptation: Optional[dict] = None
    in_adaptations = False

    with open(path) as f:
        for line in f:
            raw = line.rstrip("\n")
            stripped = raw.strip()

            if not stripped or stripped.startswith("#"):
                continue

            if stripped == "adaptations:":
                in_adaptations = True
                continue

            if not in_adaptations:
                if ":" in stripped:
                    key, val = stripped.split(":", 1)
                    data[key.strip()] = val.strip().strip('"')
                continue

            # Inside adaptations list
            if stripped.startswith("- "):
                if current_adaptation is not None:
                    adaptations.append(current_adaptation)
                current_adaptation = {}
                # Parse the key on the same line as -
                rest = stripped[2:]
                if ":" in rest:
                    key, val = rest.split(":", 1)
                    current_adaptation[key.strip()] = val.strip().strip('"')
            elif current_adaptation is not None and ":" in stripped:
                key, val = stripped.split(":", 1)
                current_adaptation[key.strip()] = val.strip().strip('"')

    if current_adaptation is not None:
        adaptations.append(current_adaptation)

    if adaptations:
        data["adaptations"] = adaptations

    return data


@dataclass
class Adaptation:
    """A single role adaptation from lineage."""
    timestamp: str
    trigger: str
    evidence: str
    adaptation: str
    rationale: str
    approved_by: Optional[str] = None


def parse_adaptations(raw_list: list[dict]) -> list[Adaptation]:
    """Parse and validate adaptation entries."""
    required_fields = {"timestamp", "trigger", "evidence", "adaptation", "rationale"}
    result: list[Adaptation] = []

    for i, entry in enumerate(raw_list):
        missing = required_fields - set(entry.keys())
        if missing:
            raise ValueError(
                f"Adaptation entry {i} missing required fields: {sorted(missing)}"
            )
        result.append(Adaptation(
            timestamp=entry["timestamp"],
            trigger=entry["trigger"],
            evidence=entry["evidence"],
            adaptation=entry["adaptation"],
            rationale=entry["rationale"],
            approved_by=entry.get("approved_by"),
        ))

    return result


def format_adaptations_section(adaptations: list[Adaptation]) -> str:
    """Format adaptations into a markdown section."""
    lines = [
        "",
        "## Adaptations",
        "",
        "Role adaptations applied via lineage events (chronological order):",
        "",
    ]

    for a in adaptations:
        approved = f" (approved by {a.approved_by})" if a.approved_by else ""
        lines.extend([
            f"### {a.timestamp}{approved}",
            f"",
            f"**Trigger:** {a.trigger}",
            f"",
            f"**Evidence:** {a.evidence}",
            f"",
            f"**Adaptation:** {a.adaptation}",
            f"",
            f"**Rationale:** {a.rationale}",
            f"",
        ])

    return "\n".join(lines)


def compile_role(
    role: str,
    base_dir: Path,
    lineage_dir: Path,
    output_dir: Path,
) -> Path:
    """Compile a single role definition.

    Returns the path to the compiled output file.
    Raises FileNotFoundError if base role definition doesn't exist.
    Raises ValueError if lineage has invalid entries.
    """
    base_path = base_dir / f"{role}.md"
    if not base_path.exists():
        raise FileNotFoundError(f"Base role definition not found: {base_path}")

    base_content = base_path.read_text()

    # Load lineage if it exists
    lineage_path = lineage_dir / f"{role}.yml"
    adaptations: list[Adaptation] = []

    if lineage_path.exists():
        lineage_data = load_yaml_simple(lineage_path)
        raw_adaptations = lineage_data.get("adaptations", [])
        if raw_adaptations:
            adaptations = parse_adaptations(raw_adaptations)

    # Compile: base + adaptations (if any)
    if adaptations:
        compiled = base_content.rstrip("\n") + "\n" + format_adaptations_section(adaptations)
    else:
        compiled = base_content

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{role}.md"
    output_path.write_text(compiled)

    return output_path


def discover_roles(base_dir: Path) -> list[str]:
    """Discover all roles available in the base directory."""
    if not base_dir.exists():
        return []
    return sorted(
        p.stem for p in base_dir.glob("*.md")
    )


def main():
    parser = argparse.ArgumentParser(
        description="Compile role definitions from base archetype + lineage"
    )
    parser.add_argument(
        "role", nargs="?", default=None,
        help="Role abbreviation to compile (e.g. cos, cto)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Compile all discovered roles",
    )
    parser.add_argument(
        "--base-dir", type=str, default=None,
        help="Directory containing base role .md files",
    )
    parser.add_argument(
        "--lineage-dir", type=str, default=None,
        help="Directory containing role lineage .yml files",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory to write compiled role files",
    )
    args = parser.parse_args()

    if not args.role and not args.all:
        parser.error("Specify a role name or --all")

    # Resolve directories
    active_preset = _read_active_preset(REPO_ROOT)
    base_dir = Path(args.base_dir) if args.base_dir else (
        REPO_ROOT / "presets" / active_preset / "agents"
    )
    lineage_dir = Path(args.lineage_dir) if args.lineage_dir else (
        REPO_ROOT / "instance" / "memory" / "role-lineage"
    )
    output_dir = Path(args.output_dir) if args.output_dir else (
        REPO_ROOT / ".claude" / "agents"
    )

    if args.all:
        roles = discover_roles(base_dir)
        if not roles:
            print(f"No roles found in {base_dir}", file=sys.stderr)
            sys.exit(1)
    else:
        roles = [args.role]

    errors = 0
    for role in roles:
        try:
            out = compile_role(role, base_dir, lineage_dir, output_dir)
            print(f"Compiled {role} -> {out}")
        except (FileNotFoundError, ValueError) as e:
            print(f"Error compiling {role}: {e}", file=sys.stderr)
            errors += 1

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
