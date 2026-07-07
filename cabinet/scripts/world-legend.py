#!/usr/bin/env python3.12
"""world-legend.py — the auto-generated Legend (Legend Law, Cabinet World E1).

Growth doc §2: "an always-live legend auto-generated from morphology.yml —
every mapping, its exact binding command, its last value — one click from
anywhere." This generator reads the grammar law (cabinet/world/), executes
every binding through the world-binding-validator sandbox, and writes
shared/interfaces/world/legend.json (runtime read-model output, untracked —
the dashboard serves it read-only).

READ-ONLY estate access (validator sandbox); the ONLY write is legend.json
inside the world output dir. Codex coverage renders as an honest gauge —
E2 does not block on 100% (UI-F4).

Usage: python3.12 cabinet/scripts/world-legend.py
"""
from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import json
import os
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(os.environ.get("CABINET_ROOT")
                  or Path(__file__).resolve().parents[2])
GRAMMAR_DIR = Path(os.environ.get("CABINET_WORLD_GRAMMAR_DIR")
                   or _REPO_ROOT / "cabinet" / "world")
OUT_PATH = Path(os.environ.get("CABINET_WORLD_LEGEND_OUT")
                or _REPO_ROOT / "shared" / "interfaces" / "world" / "legend.json")

_spec = _ilu.spec_from_file_location(
    "world_binding_validator",
    Path(__file__).resolve().parent / "world-binding-validator.py")
_wbv = _ilu.module_from_spec(_spec)
sys.modules["world_binding_validator"] = _wbv
_spec.loader.exec_module(_wbv)


def main() -> int:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    morphology_path = GRAMMAR_DIR / "morphology.yml"
    show_path = GRAMMAR_DIR / "show-grammar.yml"

    legend = {
        "generated_at": now,
        "grammar_pending": not show_path.exists(),
        "morphology_version": None,
        "show_grammar_version": None,
        "mappings": [],
        "verbs": [],
        "codex_coverage": None,
    }

    covered = 0
    total = 0

    if show_path.exists():
        try:
            sg = yaml.safe_load(show_path.read_text()) or {}
            legend["show_grammar_version"] = sg.get("version")
            for verb, m in sorted((sg.get("verbs") or {}).items()):
                if not isinstance(m, dict):
                    continue
                total += 1
                has_codex = isinstance(m.get("codex"), dict)
                covered += 1 if has_codex else 0
                legend["verbs"].append({
                    "verb": verb,
                    "station": m.get("station"),
                    "anim": m.get("anim"),
                    "salience": m.get("salience", 0),
                    "codex": m.get("codex") if has_codex else None,
                })
        except yaml.YAMLError as e:
            legend["problems"] = [f"show-grammar unparseable: {e}"]

    if morphology_path.exists():
        try:
            mo = yaml.safe_load(morphology_path.read_text()) or {}
            legend["morphology_version"] = mo.get("version")
        except yaml.YAMLError:
            pass
        findings = _wbv.validate(morphology_path)
        by_id = {}
        try:
            mo_entries = (yaml.safe_load(morphology_path.read_text()) or {}
                          ).get("entries") or []
            by_id = {e.get("id"): e for e in mo_entries if isinstance(e, dict)}
        except yaml.YAMLError:
            by_id = {}
        for f in findings:
            entry = by_id.get(f.entry_id, {})
            total += 1
            has_codex = isinstance(entry.get("codex"), dict)
            covered += 1 if has_codex else 0
            legend["mappings"].append({
                "id": f.entry_id,
                "binding": entry.get("source_binding"),
                "scope": entry.get("scope"),
                "tier": entry.get("tier"),
                "replay": entry.get("replay"),
                "status": f.level,
                "last_value": f.value,
                "message": f.message,
                "codex": entry.get("codex") if has_codex else None,
            })

    legend["codex_coverage"] = (covered / total) if total else None

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(legend, indent=2, sort_keys=True))
    os.replace(tmp, OUT_PATH)
    fails = sum(1 for m in legend["mappings"] if m["status"] == "FAIL")
    print(f"[{now}] world-legend: wrote {OUT_PATH} "
          f"(verbs={len(legend['verbs'])}, mappings={len(legend['mappings'])}, "
          f"fails={fails}, coverage="
          f"{legend['codex_coverage'] if legend['codex_coverage'] is not None else 'n/a'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
