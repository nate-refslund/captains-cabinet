"""onboard_lane — the autonomous onboarding orchestrator.

research → plan → (apply) render the lane-CEO role-def + write a readiness report.

SAFE BY DEFAULT: it NEVER executes gated actions — no plugin install, no GH-repo
or Monday-product creation, no git push, no germline edit, no send. Those are
returned (and written into the report) as PROPOSALS for the Captain to approve.
`apply=True` writes exactly two local, reversible artifacts: the lane-CEO role
def (instance/agents/<slug>-ceo.md) and the readiness report (docs/onboarding/
<slug>.md). `apply=False` is a pure dry run.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from framework.onboarding import plan, research


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _declared_name(base: Path, slug: str):
    """Canonical lane name from a declared context (instance/config/contexts/<slug>.yml),
    if one exists — the curated name beats a repo's generic package.json default."""
    ctx = base / "instance" / "config" / "contexts" / f"{slug}.yml"
    if ctx.is_file():
        m = re.search(r"(?m)^name:\s*(.+?)\s*$", ctx.read_text(encoding="utf-8"))
        if m:
            return m.group(1).strip()
    return None


def _default_render(lane: dict, model: str) -> str:
    """Render the lane-CEO role def by reusing the generator's renderer (DRY).

    Loaded via importlib because generate-instance.py's filename has a hyphen.
    """
    root = _repo_root()
    gi_path = root / "cabinet" / "scripts" / "generate-instance.py"
    spec = importlib.util.spec_from_file_location("generate_instance", gi_path)
    gi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gi)  # type: ignore[union-attr]
    template = (root / gi.LANE_CEO_TEMPLATE_REL).read_text(encoding="utf-8")
    return gi.render_agent(template, lane, model)


def _render_report(report: dict) -> str:
    pl = report["plan"]
    prof = report["profile"]
    a = pl["answers_lane"]
    lines = [
        f"# Onboarding report — {a['name']} (`{a['slug']}`)",
        "",
        "_Autonomous research + lane scaffold by the Chair. The SAFE artifacts "
        "(lane-CEO role def + this report) are written; everything below under "
        "**Needs your approval** is proposed only — nothing external was executed._",
        "",
        "## What research found",
        f"- **repo:** {prof.get('repo_url') or '(no git remote)'}",
        f"- **stack:** {', '.join(prof.get('stack') or []) or '—'}",
        f"- **plugins in repo:** {', '.join(prof.get('plugins') or []) or '—'}",
        f"- **summary:** {prof.get('summary') or '—'}",
        "",
        "## Lane (answers entry, fed to generate-instance)",
        f"- slug: `{a['slug']}` · name: {a['name']}",
        f"- repos: {a['repos']} · boards: {a['boards']}",
        f"- task plugin: `{a['plugin'] or '(none)'}` · lane MCPs: {pl['lane_mcps']}",
        "",
        "## Plugin manifest",
    ]
    for p in pl["plugin_manifest"]:
        mark = "✅ present" if p["present"] else "➕ needed"
        lines.append(f"- {mark} — `{p['name']}` ({p['source']})")
    lines += ["", "## Needs your approval (gated — NOT executed)"]
    if pl["gated_actions"]:
        for g in pl["gated_actions"]:
            lines.append(f"- **{g['action']}** `{g.get('name','')}` — {g['reason']}")
    else:
        lines.append("- (none — existing product, no external creation needed)")
    if pl["notes"]:
        lines += ["", "## Notes"] + [f"- {n}" for n in pl["notes"]]
    lines += [
        "", "## Germline diffs (Captain applies — a loop can't edit its own authorizations)",
        "```", pl["mcp_scope_diff"].rstrip(), "", pl["capabilities_diff"].rstrip(), "```",
        "", "## To hire this lane-CEO",
        f"After applying the germline diffs: "
        f"`bash cabinet/scripts/bootstrap-roles.sh --roster instance/config/roster.yml` "
        f"(or add `{a['slug']}-ceo` to the roster). The role def is at "
        f"`instance/agents/{a['slug']}-ceo.md`.",
        "",
    ]
    return "\n".join(lines)


def onboard_lane(repo_path: str, *, slug: str, board_id=None,
                 model: str = "claude-fable-5", existing: bool = True,
                 root=None, apply: bool = False, name=None,
                 research_fn=None, render_fn=None) -> dict:
    """Onboard one product as a portfolio lane. SAFE by default — see module doc.

    Lane name precedence: explicit ``name`` > declared context name > the repo's
    package.json name > slug.
    """
    base = Path(root or _repo_root())
    research_fn = research_fn or research.research_repo
    profile = research_fn(repo_path)
    resolved = name or _declared_name(base, slug) or profile.get("name") or slug
    profile = {**profile, "name": resolved}
    pl = plan.build_lane_plan(profile, slug=slug, board_id=board_id,
                              model=model, existing=existing)
    report = {
        "slug": slug, "profile": profile, "plan": pl,
        "gated_actions": pl["gated_actions"],
        "applied": False, "lane_ceo_path": None, "report_path": None,
    }
    if not apply:
        return report

    render = render_fn or _default_render
    role_text = render(pl["answers_lane"], model)

    ceo_path = base / "instance" / "agents" / f"{slug}-ceo.md"
    ceo_path.parent.mkdir(parents=True, exist_ok=True)
    ceo_path.write_text(role_text, encoding="utf-8")

    rep_path = base / "docs" / "onboarding" / f"{slug}.md"
    rep_path.parent.mkdir(parents=True, exist_ok=True)
    rep_path.write_text(_render_report(report), encoding="utf-8")

    report.update(applied=True, lane_ceo_path=str(ceo_path), report_path=str(rep_path))
    return report
