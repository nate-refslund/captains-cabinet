#!/usr/bin/env python3
"""generate-services-officers.py — print the roster-derived officer service
rows (product/captain-agnostic foundation, 2026-07-14; extends the F0.2
deploy-mac.sh roster-derivation pattern to services.yml's officer rows).

Officer rows are NEVER spliced back into the tracked cabinet/services.yml —
that would re-introduce THIS deployment's concrete officer slugs (e.g. a
product-lane CEO) into a framework file the product/captain-agnostic
doctrine requires stay generic ("the tracked repo ships a generic generator
+ template/roster-schema; the concrete roster is instance-scoped"). Instead:

  - cabinet-doctor.sh merges cabinet.scripts.lib_roster.officer_service_rows()
    in-memory alongside services.yml's tracked (non-officer) rows before its
    per-row keepalive/tmux-session check — officer health coverage is
    unchanged, just roster-sourced instead of hand-copied YAML.
  - framework/watchdog/registry.py needs no merge at all: its officer-label
    exclusion already has a `com.cabinet.officer.` prefix fallback for
    officers absent from the manifest text.

This script exists for human inspection / documentation: it prints the exact
row shape that used to be hand-maintained in cabinet/services.yml, sourced
from instance/config/roster.yml (deployment-local, gitignored). `--yaml`
prints a services.yml-shaped block an operator can eyeball or paste into a
one-off debugging copy; it is never written back into the tracked manifest
by this script.

Usage:
  python3 cabinet/scripts/generate-services-officers.py            # table
  python3 cabinet/scripts/generate-services-officers.py --yaml     # YAML block
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib_roster  # noqa: E402


def repo_root() -> Path:
    env = os.environ.get("CABINET_ROOT")
    if env:
        return Path(env).resolve()
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
        cwd=Path(__file__).resolve().parent,
    )
    return Path(out.stdout.strip())


def _yaml_kv(indent: str, key: str, value: str) -> str:
    """One `key: value` line, safely quoted/escaped for arbitrary operator
    text (embedded quotes, colons, etc. in a roster.yml expected:/notes:
    override) -- hand f-string interpolation of untrusted-shaped text would
    silently emit invalid YAML on a stray double-quote or leading colon."""
    rendered = yaml.safe_dump({key: value}, default_flow_style=False,
                             allow_unicode=True).rstrip("\n")
    return f"{indent}{rendered}"


def render_yaml(rows: list[dict]) -> str:
    lines = []
    for row in rows:
        lines.append(f"  - name: {row['name']}")
        lines.append(f"    label: {row['label']}")
        lines.append(f"    kind: {row['kind']}")
        lines.append(f"    command: {row['command']}")
        lines.append(f"    schedule: {row['schedule']}")
        lines.append(_yaml_kv("    ", "expected", row["expected"]))
        if row.get("notes"):
            lines.append(_yaml_kv("    ", "notes", row["notes"]))
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yaml", action="store_true",
                    help="print the services.yml-shaped block instead of a table")
    args = ap.parse_args()

    root = repo_root()
    rows = lib_roster.officer_service_rows(root)
    if not rows:
        print("generate-services-officers: instance/config/roster.yml not found "
              "or empty — no officer rows to show (seed the roster first: "
              "cabinet-init interview, or bootstrap-roles.sh --roster)",
              file=sys.stderr)
        return 0
    if args.yaml:
        sys.stdout.write(render_yaml(rows))
    else:
        for row in rows:
            print(f"{row['name']:24} {row['label']:40} {row['expected']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
