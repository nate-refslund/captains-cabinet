"""onboard_lane — research → plan → (apply) render lane-CEO + readiness report.
SAFE-by-default: executes NO gated actions. research/render injected (no repo/generator)."""
from pathlib import Path

from framework.onboarding import onboard

PROFILE = {
    "name": "acme-shop", "summary": "Demo storefront platform.",
    "stack": ["neon", "nextjs", "vercel"], "plugins": ["dev-tasks", "corridor"],
    "repo_url": "https://github.com/acme-org/acme-shop",
    "has_claude": True, "path": "/x",
}
_RENDER = lambda lane, model: f"# {lane['slug']}-ceo for {lane['name']} ({model})"


def test_dry_run_writes_nothing(tmp_path):
    rep = onboard.onboard_lane("/x", slug="acme", tracker_ref="42424242",
                               research_fn=lambda p: PROFILE, root=str(tmp_path), apply=False)
    assert rep["applied"] is False
    assert rep["lane_ceo_path"] is None
    assert rep["plan"]["answers_lane"]["slug"] == "acme"
    assert list(tmp_path.iterdir()) == []          # pure dry run


def test_apply_writes_only_the_two_safe_files(tmp_path):
    rep = onboard.onboard_lane("/x", slug="acme", tracker_ref="42424242",
                               research_fn=lambda p: PROFILE, render_fn=_RENDER,
                               root=str(tmp_path), apply=True)
    assert rep["applied"] is True
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == ["docs/onboarding/acme.md", "instance/agents/acme-ceo.md"]
    assert "acme-ceo" in Path(rep["lane_ceo_path"]).read_text()


def test_report_carries_proposals_and_germline_for_captain(tmp_path):
    body = ""
    rep = onboard.onboard_lane("/x", slug="acme", research_fn=lambda p: PROFILE,
                               render_fn=_RENDER, root=str(tmp_path), apply=True)
    body = Path(rep["report_path"]).read_text()
    assert "acme-ceo" in body                      # germline diff present for the captain to apply
    assert "neon" in body                          # lane MCPs
    assert ("gated" in body.lower()) or ("propose" in body.lower())


def test_gated_actions_never_executed(tmp_path):
    defaults = {"cabinet_default_plugins": ["corridor", "brain"],
                "lane_mcps": ["library", "telegram", "brain"]}
    rep = onboard.onboard_lane("/x", slug="acme", research_fn=lambda p: {**PROFILE, "plugins": []},
                               render_fn=_RENDER, root=str(tmp_path), apply=True,
                               defaults=defaults)
    assert any(a["action"] == "install-plugin" for a in rep["gated_actions"])
    assert all(a["executed"] is False for a in rep["gated_actions"])
    # apply still wrote ONLY the two safe artifacts — no install/creation side effects
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert written == ["docs/onboarding/acme.md", "instance/agents/acme-ceo.md"]


def test_prefers_declared_context_name(tmp_path):
    ctx = tmp_path / "instance" / "config" / "contexts"
    ctx.mkdir(parents=True)
    (ctx / "acme.yml").write_text("slug: acme\nname: Acme Shop\nactive: false\n")
    rep = onboard.onboard_lane("/x", slug="acme",
                               research_fn=lambda p: {**PROFILE, "name": "my-v0-project"},
                               render_fn=_RENDER, root=str(tmp_path), apply=False)
    assert rep["plan"]["answers_lane"]["name"] == "Acme Shop"   # curated context name wins


def test_explicit_name_overrides_all(tmp_path):
    rep = onboard.onboard_lane("/x", slug="acme", name="Acme Shop",
                               research_fn=lambda p: {**PROFILE, "name": "my-v0-project"},
                               render_fn=_RENDER, root=str(tmp_path), apply=False)
    assert rep["plan"]["answers_lane"]["name"] == "Acme Shop"


def test_defaults_load_from_the_passed_presets_dir(tmp_path, monkeypatch):
    # The presets location is layer payload the CALLER passes (layer-separation
    # gate); the active-preset slug resolves via the env seam. No presets_dir
    # → fail-closed empty defaults (test_gated_actions/... above cover that
    # implicitly: no cabinet-default rows appear without one).
    pd = tmp_path / "pdir" / "tp"
    pd.mkdir(parents=True)
    (pd / "preset.yml").write_text(
        "name: tp\nonboarding:\n  cabinet_default_plugins: [brain]\n  lane_mcps: [library]\n")
    monkeypatch.setenv("CABINET_ACTIVE_PRESET", "tp")
    rep = onboard.onboard_lane("/x", slug="acme", research_fn=lambda p: PROFILE,
                               root=str(tmp_path), apply=False,
                               presets_dir=str(tmp_path / "pdir"))
    names = {p["name"] for p in rep["plan"]["plugin_manifest"] if not p["present"]}
    assert names == {"brain"}                     # preset default surfaced via param
    assert rep["plan"]["lane_mcps"][-1] == "library"  # base scope from preset config


def test_no_presets_dir_is_fail_closed_empty(tmp_path):
    rep = onboard.onboard_lane("/x", slug="acme", research_fn=lambda p: PROFILE,
                               root=str(tmp_path), apply=False)
    sources = {p["source"] for p in rep["plan"]["plugin_manifest"]}
    assert sources <= {"repo"}                    # no cabinet-default rows appear


def test_apply_refuses_to_clobber_markerless_role_def(tmp_path):
    # egg-hatch-engine-4: a hand-authored (markerless) lane-CEO role def is
    # gitignored → clobbering it is unrecoverable. apply must refuse intact.
    ceo = tmp_path / "instance" / "agents" / "acme-ceo.md"
    ceo.parent.mkdir(parents=True)
    hand_tuned = "# acme-ceo — Captain hand-tuned role def\ncandor: absolute\n"
    ceo.write_text(hand_tuned)
    import pytest
    with pytest.raises(RuntimeError, match="REFUSING to overwrite"):
        onboard.onboard_lane("/x", slug="acme", research_fn=lambda p: PROFILE,
                             render_fn=_RENDER, root=str(tmp_path), apply=True)
    assert ceo.read_text() == hand_tuned           # bytes untouched
    assert not (tmp_path / "docs" / "onboarding" / "acme.md").exists()


def test_apply_regenerates_marker_owned_role_def(tmp_path):
    # A file carrying the generated-by marker is generator-owned → re-onboard
    # overwrites it cleanly (the default renderer stamps the marker).
    ceo = tmp_path / "instance" / "agents" / "acme-ceo.md"
    ceo.parent.mkdir(parents=True)
    ceo.write_text(f"# {onboard._MARKER} — rendered earlier\nold body\n")
    rep = onboard.onboard_lane("/x", slug="acme", research_fn=lambda p: PROFILE,
                               render_fn=_RENDER, root=str(tmp_path), apply=True)
    assert rep["applied"] is True
    assert "old body" not in ceo.read_text()
