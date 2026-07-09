#!/bin/bash
# audit-role-parity.sh — W6/§4.3-4 pre-flip parity audit (2026-07-09).
#
# BEFORE flipping CABINET_BOOT_ROLES_ACTIVE=1 (the live-registry boot wire in
# lib/officer-boot.sh::officer_role_registry_clause), prove the two role
# surfaces agree — the P0 officer-config-contamination lesson from the CC
# audit (2026-07-07): never point boot at a second config surface while the
# surfaces silently disagree.
#
# Compares, per instance/roles/active/<slug>.yml:
#   * a fulltime+active role MUST have a hired .claude/agents/<slug>.md
#     (consultant roles legitimately have none — deploy-mac.sh refuses them);
#   * when both exist and both pin a model, the pins must MATCH (a split model
#     pin is exactly the contamination class: registry says X, boot runs Y);
#   * orphan agent files (.claude/agents/*.md with NO active registry row) are
#     flagged — the evolution loop can never reach them.
#
# Report-only READER (no file is written or mutated). Exit 0 = parity, exit 1
# = drift found (gate a flag flip on this), exit 2 = cannot audit.
# YAML/frontmatter parsing via python3.12 yaml.safe_load only.
set -u
ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
command -v "$PY" >/dev/null 2>&1 || PY=python3

exec "$PY" - "$ROOT" <<'PYEOF'
import sys
from pathlib import Path

import yaml

root = Path(sys.argv[1])
active_dir = root / "instance/roles/active"
agents_dir = root / ".claude/agents"

if not active_dir.is_dir():
    print(f"role-parity: SKIP — {active_dir} absent (no registry on this checkout)")
    sys.exit(2)

def agent_frontmatter(path: Path) -> dict:
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        fm = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return fm if isinstance(fm, dict) else {}

drift: list[str] = []
seen_slugs: set[str] = set()

for yml in sorted(active_dir.glob("*.yml")):
    role = yaml.safe_load(yml.read_text()) or {}
    slug = role.get("slug") or yml.stem
    seen_slugs.add(slug)
    status = role.get("status", "active")
    otype = role.get("officer_type", "fulltime")
    agent_md = agents_dir / f"{slug}.md"
    if status != "active":
        continue
    if otype != "fulltime":
        # consultants boot no session — an agent file is optional
        continue
    if not agent_md.is_file():
        drift.append(
            f"{slug}: fulltime+active in registry but NO .claude/agents/{slug}.md "
            "— boot has nothing to read for this officer")
        continue
    fm = agent_frontmatter(agent_md)
    role_model = str(role.get("model") or "").strip()
    agent_model = str(fm.get("model") or "").strip()
    if role_model and agent_model and role_model != agent_model:
        drift.append(
            f"{slug}: model pin split — registry {role_model!r} vs agent "
            f"frontmatter {agent_model!r} (officer-config-contamination class)")

if agents_dir.is_dir():
    for md in sorted(agents_dir.glob("*.md")):
        if md.stem not in seen_slugs:
            drift.append(
                f"{md.stem}: hired agent file with NO active registry row — "
                "the evolution loop can never reach this officer")

n_roles = len(list(active_dir.glob('*.yml')))
n_agents = len(list(agents_dir.glob('*.md'))) if agents_dir.is_dir() else 0
if drift:
    print(f"role-parity: DRIFT ({len(drift)} finding(s)) over {n_roles} role(s) / {n_agents} agent file(s):")
    for d in drift:
        print(f"  - {d}")
    print("role-parity: do NOT flip CABINET_BOOT_ROLES_ACTIVE=1 until the surfaces agree.")
    sys.exit(1)
print(f"role-parity: OK — {n_roles} registry role(s) / {n_agents} agent file(s) agree; safe to consider the flag flip.")
sys.exit(0)
PYEOF
