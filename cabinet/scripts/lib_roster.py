#!/usr/bin/env python3
"""lib_roster.py — shared roster parsing + officer service-row synthesis
(product/captain-agnostic foundation, 2026-07-14 Captain directive).

Single source for turning instance/config/roster.yml (deployment-local,
gitignored — instance/config/roster.yml.example ships the shape-documenting
twin) into the officer "service row" shape that cabinet/services.yml used to
hardcode per officer (one row per product-lane CEO, per the Chair, per any
other roster slug). Mirrors the deploy-mac.sh roster-derivation pattern
(F0.2: "the officer fleet is DERIVED from the deployment's roster, never
hardcoded") — this module is the same idea for the two OTHER consumers of
officer rows:

  - cabinet/scripts/cabinet-doctor.sh merges officer_service_rows() alongside
    cabinet/services.yml's tracked (non-officer) rows before its per-row
    keepalive/tmux-session liveness check, so officer health coverage is
    unchanged now that services.yml no longer hardcodes officer rows.
  - cabinet/scripts/generate-services-officers.py (human inspection /
    documentation CLI — never spliced back into the tracked services.yml).

framework/watchdog/registry.py's verify_no_silent_cron_failure needs NO
change: its officer-label exclusion already has a `com.cabinet.officer.`
label-prefix fallback for officers absent from the manifest text (written
for "an officer hired after this manifest was written appears with no
row") — zero behavior change there with zero declared officer rows.

roster.yml schema (mirrors instance/config/roster.yml.example): top-level
`roster:` maps an officer slug -> {title, model, capabilities,
authority_level, type, [expected], [notes]}. `expected` and `notes` are
OPTIONAL per-slug overrides — the bash awk parsers in deploy-mac.sh /
bootstrap-roles.sh already ignore unknown 4-space keys ("Other 4-space keys
... are intentionally ignored"), so adding these here is backward
compatible. Absent -> the generic pattern below (byte-identical to what
services.yml hardcoded for every officer that had no custom override).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_ROSTER_REL = "instance/config/roster.yml"


def load_roster(root: Path, roster_rel: str = DEFAULT_ROSTER_REL) -> dict[str, Any]:
    """Returns the parsed `roster:` mapping (slug -> fields), or {} if the
    file is absent — a fresh clone with no roster yet is the correct
    product-agnostic default, never a hard error (mirrors deploy-mac.sh's
    OWN refusal-vs-empty distinction: deploy-mac.sh refuses loudly because a
    missing roster there would silently deploy a wrong preset fleet; nothing
    here ever invents officer rows, so absence is simply zero rows)."""
    path = root / roster_rel
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")
    roster = data.get("roster") or {}
    if not isinstance(roster, dict):
        raise ValueError(f"{path}: 'roster:' must be a mapping of slug -> fields")
    return roster


def officer_service_rows(root: Path,
                         roster_rel: str = DEFAULT_ROSTER_REL) -> list[dict[str, Any]]:
    """Synthesizes the officer service-row shape (name/label/kind/command/
    schedule/on_demand/expected/[notes]) for every roster slug, in roster file
    order — the exact shape cabinet/services.yml hand-authored per officer
    before this change, plus `on_demand` (derived from the per-slug `type`:
    consultant => True; fulltime / absent => False). Slugs are NOT validated
    against a naming pattern here; roster.yml is deployment-local operator
    input, not external/untrusted."""
    roster = load_roster(root, roster_rel)
    rows: list[dict[str, Any]] = []
    for slug, fields in roster.items():
        if fields is None:
            fields = {}
        if not isinstance(fields, dict):
            raise ValueError(
                f"roster.yml: officer '{slug}' must map to a dict of fields "
                f"(title/model/capabilities/authority_level/...), got "
                f"{type(fields).__name__}")
        otype = str(fields.get("type") or "fulltime").lower()
        row = {
            "name": f"officer-{slug}",
            "label": f"com.cabinet.officer.{slug}",
            "kind": "officer",
            "command": f"bash cabinet/scripts/start-officer-mac.sh {slug}",
            "schedule": "keepalive",
            # Consultants are started per-trigger — deploy-mac.sh's
            # guard_consultant deliberately never installs a keepalive launchd
            # job for them, so a missing job is EXPECTED, not DEAD (cabinet-
            # doctor reads this flag and SKIPs instead of DEADing). keepalive
            # stays so a --force-deployed consultant still gets tmux liveness.
            "on_demand": otype == "consultant",
            "expected": fields.get("expected")
                       or f"redis heartbeat cabinet:heartbeat:{slug}",
        }
        if fields.get("notes"):
            row["notes"] = fields["notes"]
        rows.append(row)
    return rows
