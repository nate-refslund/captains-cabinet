"""build_lane_plan — turn a research profile into an onboarding plan.

Pure function. Produces: the answers lane-entry (fed to generate-instance), the
plugin manifest (present vs needed), the GATED actions (propose-only — plugin
installs, and for a NEW product the GH-repo / Monday-product creation), and the
germline diffs (mcp-scope + officer-capabilities) for the Captain to apply.
Nothing here executes anything.
"""
from __future__ import annotations

_DEFAULT_MODEL = "claude-fable-5"
# Plugins a product lane-CEO generally needs beyond what its repo already ships.
_CABINET_DEFAULTS = ["corridor", "brain"]


def _task_plugin(profile: dict) -> str:
    return "dev-tasks" if "dev-tasks" in (profile.get("plugins") or []) else ""


def _lane_mcps(profile: dict) -> list:
    stack = profile.get("stack") or []
    mcps = []
    if "neon" in stack:
        mcps.append("neon")
    if "vercel" in stack or "nextjs" in stack:
        mcps.append("vercel")
    mcps += ["library", "telegram", "brain"]
    return mcps


def build_lane_plan(profile: dict, *, slug: str, board_id=None,
                    model: str = _DEFAULT_MODEL, existing: bool = True) -> dict:
    name = profile.get("name") or slug
    repo_url = profile.get("repo_url")
    answers_lane = {
        "slug": slug,
        "name": name,
        "repos": [repo_url] if repo_url else [],
        "boards": [str(board_id)] if board_id else [],
        "plugin": _task_plugin(profile),
    }

    have = set(profile.get("plugins") or [])
    manifest = [{"name": p, "present": True, "source": "repo"} for p in sorted(have)]
    for p in _CABINET_DEFAULTS:
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
        gated.append({"action": "create-monday-product", "name": name,
                      "reason": "new product — Monday product board does not exist yet",
                      "executed": False})

    mcps = _lane_mcps(profile)
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
