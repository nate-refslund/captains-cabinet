"""Role lifecycle management for the organizational runtime.

Roles are durable entities with charter, capabilities, memory, and eval
history. They persist independently of any running process or session.

Core rules:
  - Create roles slowly.
  - Adapt roles frequently.
  - Use hats aggressively.
  - Retire roles rarely.
  - Never delete role learning.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from yaml import safe_load as _yaml_load, safe_dump as _yaml_dump
except ImportError:
    import yaml as _yaml_mod
    _yaml_load = _yaml_mod.safe_load
    _yaml_dump = _yaml_mod.safe_dump

# Add framework to path for event emitter
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from framework.events.emitter import emit


def _roles_dir() -> Path:
    """Return the directory where role definitions live."""
    root = Path(os.environ.get("CABINET_ROOT", Path(__file__).parent.parent.parent))
    return root / "instance" / "roles" / "active"


def _archive_dir() -> Path:
    root = Path(os.environ.get("CABINET_ROOT", Path(__file__).parent.parent.parent))
    return root / "instance" / "roles" / "archive"


def _hats_dir() -> Path:
    root = Path(os.environ.get("CABINET_ROOT", Path(__file__).parent.parent.parent))
    return root / "instance" / "roles" / "hats"


def _lineage_file() -> Path:
    root = Path(os.environ.get("CABINET_ROOT", Path(__file__).parent.parent.parent))
    return root / "instance" / "roles" / "lineage.yml"


def load_role(slug: str) -> dict[str, Any] | None:
    """Load a role definition from disk."""
    role_file = _roles_dir() / f"{slug}.yml"
    if not role_file.exists():
        return None
    with open(role_file) as f:
        return _yaml_load(f)


def list_roles(status: str = "active") -> list[dict[str, Any]]:
    """List all roles with the given status."""
    if status == "active":
        roles_dir = _roles_dir()
    elif status == "retired":
        roles_dir = _archive_dir()
    else:
        return []

    if not roles_dir.exists():
        return []

    roles = []
    for f in sorted(roles_dir.glob("*.yml")):
        with open(f) as fh:
            role = _yaml_load(fh)
            if role:
                roles.append(role)
    return roles


def create_role(
    slug: str,
    title: str,
    charter: str,
    capabilities: list[str] | None = None,
    authority_level: str = "standard",
    approved_by: str = "captain",
) -> dict[str, Any]:
    """Create a new role entity."""
    _roles_dir().mkdir(parents=True, exist_ok=True)

    role = {
        "slug": slug,
        "title": title,
        "status": "active",
        "charter": charter,
        "capabilities": capabilities or [],
        "authority_level": authority_level,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    role_file = _roles_dir() / f"{slug}.yml"
    with open(role_file, "w") as f:
        _yaml_dump(role, f, default_flow_style=False, sort_keys=False)

    event = emit("role_created", actor=approved_by, payload={
        "slug": slug, "title": title, "charter": charter,
        "capabilities": capabilities or [], "authority_level": authority_level,
    })

    _append_lineage(slug, "created", f"Role '{title}' created", approved_by, event["id"])

    return role


def adapt_role(
    slug: str,
    adaptation_type: str,
    description: str,
    changes: dict[str, Any],
    evidence: str | None = None,
    rationale: str | None = None,
    approved_by: str = "captain",
) -> dict[str, Any]:
    """Apply an adaptation to a role. Returns the updated role."""
    role = load_role(slug)
    if role is None:
        raise ValueError(f"Role not found: {slug}")

    if adaptation_type == "charter_change":
        role["charter"] = changes.get("charter", role["charter"])
    elif adaptation_type == "capability_added":
        cap = changes.get("capability")
        if cap and cap not in role.get("capabilities", []):
            role.setdefault("capabilities", []).append(cap)
    elif adaptation_type == "capability_removed":
        cap = changes.get("capability")
        if cap and cap in role.get("capabilities", []):
            role["capabilities"].remove(cap)
    elif adaptation_type == "authority_change":
        role["authority_level"] = changes.get("authority_level", role.get("authority_level"))

    role["updated_at"] = datetime.now(timezone.utc).isoformat()

    role_file = _roles_dir() / f"{slug}.yml"
    with open(role_file, "w") as f:
        _yaml_dump(role, f, default_flow_style=False, sort_keys=False)

    _ADAPTATION_TO_EVENT = {
        "charter_change": "role_charter_changed",
        "capability_added": "role_capability_added",
        "capability_removed": "role_capability_removed",
        "authority_change": "role_authority_changed",
    }
    event_type = _ADAPTATION_TO_EVENT.get(adaptation_type, f"role_{adaptation_type}")
    event = emit(event_type, actor=approved_by, payload={
        "slug": slug, "adaptation_type": adaptation_type,
        "changes": changes, "evidence": evidence, "rationale": rationale,
    })

    _append_lineage(slug, adaptation_type, description, approved_by, event["id"], evidence, rationale)

    return role


def assign_hat(
    role_slug: str,
    hat_name: str,
    description: str,
    capabilities: list[str] | None = None,
    mission_id: str | None = None,
    expires_at: str | None = None,
    approved_by: str = "captain",
) -> dict[str, Any]:
    """Assign a temporary hat (specialization) to a role."""
    _hats_dir().mkdir(parents=True, exist_ok=True)

    hat = {
        "role_slug": role_slug,
        "name": hat_name,
        "description": description,
        "capabilities": capabilities or [],
        "mission_id": mission_id,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    hat_file = _hats_dir() / f"{role_slug}--{hat_name.lower().replace(' ', '-')}.yml"
    with open(hat_file, "w") as f:
        _yaml_dump(hat, f, default_flow_style=False, sort_keys=False)

    event = emit("role_hat_assigned", actor=approved_by, payload={
        "role_slug": role_slug, "hat_name": hat_name,
        "capabilities": capabilities or [], "mission_id": mission_id,
    })

    _append_lineage(role_slug, "hat_assigned", f"Hat '{hat_name}' assigned", approved_by, event["id"])

    return hat


def get_active_hats(role_slug: str) -> list[dict[str, Any]]:
    """Get all active hats for a role."""
    hats_dir = _hats_dir()
    if not hats_dir.exists():
        return []

    hats = []
    for f in hats_dir.glob(f"{role_slug}--*.yml"):
        with open(f) as fh:
            hat = _yaml_load(fh)
            if hat:
                # Check expiry
                if hat.get("expires_at"):
                    expires = datetime.fromisoformat(hat["expires_at"])
                    if expires < datetime.now(timezone.utc):
                        continue
                hats.append(hat)
    return hats


def retire_role(slug: str, reason: str, approved_by: str = "captain") -> None:
    """Retire a role. Moves to archive, preserves all learning."""
    role = load_role(slug)
    if role is None:
        raise ValueError(f"Role not found: {slug}")

    role["status"] = "retired"
    role["retired_at"] = datetime.now(timezone.utc).isoformat()
    role["retirement_reason"] = reason

    _archive_dir().mkdir(parents=True, exist_ok=True)
    archive_file = _archive_dir() / f"{slug}.yml"
    with open(archive_file, "w") as f:
        _yaml_dump(role, f, default_flow_style=False, sort_keys=False)

    # Remove from active
    active_file = _roles_dir() / f"{slug}.yml"
    if active_file.exists():
        active_file.unlink()

    event = emit("role_retired", actor=approved_by, payload={
        "slug": slug, "reason": reason,
    })

    _append_lineage(slug, "retired", f"Retired: {reason}", approved_by, event["id"])


def get_effective_capabilities(role_slug: str) -> list[str]:
    """Get all capabilities for a role, including from active hats."""
    role = load_role(role_slug)
    if role is None:
        return []

    caps = set(role.get("capabilities", []))
    for hat in get_active_hats(role_slug):
        caps.update(hat.get("capabilities", []))
    return sorted(caps)


def get_lineage(role_slug: str | None = None) -> list[dict[str, Any]]:
    """Read the lineage log, optionally filtered by role."""
    lineage_file = _lineage_file()
    if not lineage_file.exists():
        return []

    with open(lineage_file) as f:
        data = _yaml_load(f)

    entries = data if isinstance(data, list) else []
    if role_slug:
        entries = [e for e in entries if e.get("role_slug") == role_slug]
    return entries


def _append_lineage(
    role_slug: str,
    adaptation_type: str,
    description: str,
    approved_by: str,
    event_id: str,
    evidence: str | None = None,
    rationale: str | None = None,
) -> None:
    """Append to the lineage log (append-only, never edit/delete)."""
    lineage_file = _lineage_file()
    lineage_file.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "role_slug": role_slug,
        "adaptation_type": adaptation_type,
        "description": description,
        "approved_by": approved_by,
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if evidence:
        entry["evidence"] = evidence
    if rationale:
        entry["rationale"] = rationale

    existing = []
    if lineage_file.exists():
        with open(lineage_file) as f:
            data = _yaml_load(f)
            if isinstance(data, list):
                existing = data

    existing.append(entry)
    with open(lineage_file, "w") as f:
        _yaml_dump(existing, f, default_flow_style=False, sort_keys=False)
