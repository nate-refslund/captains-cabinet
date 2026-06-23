"""onboard_lane — research → plan → (apply) render lane-CEO + readiness report.
SAFE-by-default: executes NO gated actions. research/render injected (no repo/generator)."""
from pathlib import Path

from framework.onboarding import onboard

PROFILE = {
    "name": "v0-politiske-annoncer", "summary": "EU political ad platform.",
    "stack": ["neon", "nextjs", "vercel"], "plugins": ["dev-tasks", "corridor"],
    "repo_url": "https://github.com/STEP-Network/v0-politiske-annoncer",
    "has_claude": True, "path": "/x",
}
_RENDER = lambda lane, model: f"# {lane['slug']}-ceo for {lane['name']} ({model})"


def test_dry_run_writes_nothing(tmp_path):
    rep = onboard.onboard_lane("/x", slug="polads", board_id="5092199368",
                               research_fn=lambda p: PROFILE, root=str(tmp_path), apply=False)
    assert rep["applied"] is False
    assert rep["lane_ceo_path"] is None
    assert rep["plan"]["answers_lane"]["slug"] == "polads"
    assert list(tmp_path.iterdir()) == []          # pure dry run


def test_apply_writes_only_the_two_safe_files(tmp_path):
    rep = onboard.onboard_lane("/x", slug="polads", board_id="5092199368",
                               research_fn=lambda p: PROFILE, render_fn=_RENDER,
                               root=str(tmp_path), apply=True)
    assert rep["applied"] is True
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == ["docs/onboarding/polads.md", "instance/agents/polads-ceo.md"]
    assert "polads-ceo" in Path(rep["lane_ceo_path"]).read_text()


def test_report_carries_proposals_and_germline_for_captain(tmp_path):
    body = ""
    rep = onboard.onboard_lane("/x", slug="polads", research_fn=lambda p: PROFILE,
                               render_fn=_RENDER, root=str(tmp_path), apply=True)
    body = Path(rep["report_path"]).read_text()
    assert "polads-ceo" in body                    # germline diff present for Nate to apply
    assert "neon" in body                          # lane MCPs
    assert ("gated" in body.lower()) or ("propose" in body.lower())


def test_gated_actions_never_executed(tmp_path):
    rep = onboard.onboard_lane("/x", slug="polads", research_fn=lambda p: {**PROFILE, "plugins": []},
                               render_fn=_RENDER, root=str(tmp_path), apply=True)
    assert any(a["action"] == "install-plugin" for a in rep["gated_actions"])
    assert all(a["executed"] is False for a in rep["gated_actions"])
    # apply still wrote ONLY the two safe artifacts — no install/creation side effects
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == ["docs/onboarding/polads.md", "instance/agents/polads-ceo.md"]


def test_prefers_declared_context_name(tmp_path):
    ctx = tmp_path / "instance" / "config" / "contexts"
    ctx.mkdir(parents=True)
    (ctx / "polads.yml").write_text("slug: polads\nname: PolAds\nactive: false\n")
    rep = onboard.onboard_lane("/x", slug="polads",
                               research_fn=lambda p: {**PROFILE, "name": "my-v0-project"},
                               render_fn=_RENDER, root=str(tmp_path), apply=False)
    assert rep["plan"]["answers_lane"]["name"] == "PolAds"   # curated context name wins


def test_explicit_name_overrides_all(tmp_path):
    rep = onboard.onboard_lane("/x", slug="polads", name="PolAds",
                               research_fn=lambda p: {**PROFILE, "name": "my-v0-project"},
                               render_fn=_RENDER, root=str(tmp_path), apply=False)
    assert rep["plan"]["answers_lane"]["name"] == "PolAds"
