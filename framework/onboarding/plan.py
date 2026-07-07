"""build_lane_plan — turn a research profile into an onboarding plan.

Pure function. Produces: the answers lane-entry (fed to generate-instance), the
plugin manifest (present vs needed), the GATED actions (propose-only — plugin
installs, and for a NEW product the GH-repo / tracker-product creation), and the
germline diffs (mcp-scope + officer-capabilities) for the Captain to apply.
Nothing here executes anything.

The cabinet-default plugin list and the base lane-MCP scope are PRESET CONFIG
(``<presets-dir>/<active>/preset.yml`` → ``onboarding:``), not framework
hardcodes — ``load_preset_defaults`` (the one impure helper here, used by the
orchestrator) reads them fail-closed to empty. The presets directory is LAYER
PAYLOAD, not instance config: the framework never knows where it lives, so the
cabinet-layer caller resolves and passes it (layer-separation gate); only the
instance-side pointer (the active-preset slug) resolves through the ratified
env seam (``framework.env.active_preset``). Task-tracker references are OPAQUE
to the framework: semantics belong to the lane's task-tracking extension.
"""
from __future__ import annotations

import re
from pathlib import Path

from framework.env import active_preset as _active_preset

_DEFAULT_MODEL = "claude-fable-5"
# Preset slugs are plain names, never path segments with traversal.
_PRESET_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def load_preset_defaults(presets_dir, active=None) -> dict:
    """Onboarding defaults from a preset's config (fail-closed).

    ``presets_dir`` is the directory holding the preset trees — REQUIRED, no
    framework default: presets are layer payload, so the cabinet-layer caller
    (CLI flag / wrapper) owns the location and passes it in; None/"" yields
    EMPTY defaults. ``active`` is the preset slug; None resolves it through
    the env seam (``framework.env.active_preset()``: ``CABINET_ACTIVE_PRESET``
    env → ``instance/config/active-preset`` → ``work``, mirroring
    load-preset.sh). Reads ``<presets_dir>/<active>/preset.yml`` →
    ``onboarding:``: ``cabinet_default_plugins`` (plugins every lane-CEO needs
    beyond its repo) and ``lane_mcps`` (base MCP scope for a generated
    lane-CEO). Any absence or parse failure yields EMPTY lists — a preset that
    declares nothing onboards lanes with no cabinet defaults; the framework
    hardcodes no plugin or MCP names.
    """
    empty = {"cabinet_default_plugins": [], "lane_mcps": []}
    try:
        if not presets_dir:
            return empty
        if active is None:
            active = _active_preset()
        if not _PRESET_RE.match(active):
            return empty
        cfg = Path(presets_dir) / active / "preset.yml"
        if not cfg.is_file():
            return empty
        import yaml  # local: keep module import-light for the pure planner
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        ob = data.get("onboarding") if isinstance(data, dict) else None
        if not isinstance(ob, dict):
            return empty
        out = {}
        for key in ("cabinet_default_plugins", "lane_mcps"):
            val = ob.get(key)
            out[key] = [str(v) for v in val] if isinstance(val, list) else []
        return out
    except Exception:
        return empty


def _task_plugin(profile: dict) -> str:
    return "dev-tasks" if "dev-tasks" in (profile.get("plugins") or []) else ""


def _lane_mcps(profile: dict, base: list) -> list:
    """Stack-derived MCPs (from research) + the preset's base lane-MCP scope."""
    stack = profile.get("stack") or []
    mcps = []
    if "neon" in stack:
        mcps.append("neon")
    if "vercel" in stack or "nextjs" in stack:
        mcps.append("vercel")
    mcps += [m for m in base if m not in mcps]
    return mcps


def build_lane_plan(profile: dict, *, slug: str, tracker_ref=None,
                    model: str = _DEFAULT_MODEL, existing: bool = True,
                    defaults=None) -> dict:
    """Pure planner. ``tracker_ref`` is an OPAQUE task-tracker reference
    (board/product id — semantics owned by the lane's task-tracking
    extension). ``defaults`` carries the preset onboarding defaults (see
    ``load_preset_defaults``); None means no defaults were declared."""
    d = defaults or {}
    cabinet_plugins = d.get("cabinet_default_plugins") or []
    base_mcps = d.get("lane_mcps") or []

    name = profile.get("name") or slug
    repo_url = profile.get("repo_url")
    answers_lane = {
        "slug": slug,
        "name": name,
        "repos": [repo_url] if repo_url else [],
        "boards": [str(tracker_ref)] if tracker_ref else [],
        "plugin": _task_plugin(profile),
    }

    have = set(profile.get("plugins") or [])
    manifest = [{"name": p, "present": True, "source": "repo"} for p in sorted(have)]
    for p in cabinet_plugins:
        if p not in have:
            manifest.append({"name": p, "present": False, "source": "cabinet-default"})

    gated = [
        {"action": "install-plugin", "name": p["name"],
         "reason": f"lane needs {p['name']} (not present in repo)", "executed": False}
        for p in manifest if not p["present"]
    ]
    if not existing:
        gated.append({"action": "create-repo", "name": slug,
                      "reason": "new product — GH repo does not exist yet", "executed": False})
        gated.append({"action": "create-tracker-product", "name": name,
                      "reason": "new product — no task-tracker board/product exists yet "
                                "(created via the lane's task-tracking extension)",
                      "executed": False})

    mcps = _lane_mcps(profile, base_mcps)
    mcp_scope_diff = (
        f"# add to cabinet/mcp-scope.yml (GERMLINE — Captain applies):\n"
        f"    {slug}-ceo:\n"
        f"      mcps: [{', '.join(mcps)}]\n"
    )
    caps = ["deploys_code", "validates_deployments", "reviews_implementations",
            "logs_captain_decisions"]
    capabilities_diff = (
        f"# add to cabinet/officer-capabilities.conf (GERMLINE — Captain applies):\n"
        + "\n".join(f"{slug}-ceo:{c}" for c in caps) + "\n"
    )

    notes = []
    stack = profile.get("stack") or []
    if "neon" in stack:
        notes.append("neon detected — set the lane's neon_project name in projects/<slug>.yml")
    if "vercel" in stack or "nextjs" in stack:
        notes.append("vercel/next detected — set the lane's vercel_project name")

    return {
        "answers_lane": answers_lane,
        "plugin_manifest": manifest,
        "gated_actions": gated,
        "mcp_scope_diff": mcp_scope_diff,
        "capabilities_diff": capabilities_diff,
        "lane_mcps": mcps,
        "notes": notes,
        "model": model,
        "existing": existing,
    }
