"""build_lane_plan — profile → answers lane-entry + plugin manifest + gated proposals
+ germline diffs. Pure; nothing executed. Cabinet defaults come from PRESET CONFIG
(load_preset_defaults, fail-closed) — the framework hardcodes no plugin/MCP names."""
from framework.onboarding import plan

ACME = {
    "name": "acme-shop",
    "summary": "Demo storefront platform.",
    "stack": ["neon", "nextjs", "vercel"],
    "plugins": ["dev-tasks", "corridor", "neon", "vercel"],
    "repo_url": "https://github.com/acme-org/acme-shop",
    "has_claude": True,
    "path": "/products/acme-shop",
}
# Preset onboarding defaults as load_preset_defaults returns them.
DEFAULTS = {"cabinet_default_plugins": ["corridor", "brain"],
            "lane_mcps": ["library", "telegram", "brain"]}


def test_answers_lane_core():
    a = plan.build_lane_plan(ACME, slug="acme", tracker_ref="42424242")["answers_lane"]
    assert a["slug"] == "acme"
    assert a["name"] == "acme-shop"
    assert a["repos"] == ["https://github.com/acme-org/acme-shop"]
    assert a["boards"] == ["42424242"]       # opaque tracker ref, carried verbatim
    assert a["plugin"] == "dev-tasks"          # detected task route


def test_plugin_manifest_present_vs_default():
    names = {p["name"]: p for p in
             plan.build_lane_plan(ACME, slug="acme", defaults=DEFAULTS)["plugin_manifest"]}
    assert names["dev-tasks"]["present"] is True
    assert names["corridor"]["present"] is True
    assert "brain" in names                     # preset default surfaced


def test_no_defaults_is_fail_closed_empty():
    pl = plan.build_lane_plan(ACME, slug="acme")   # no preset defaults declared
    sources = {p["source"] for p in pl["plugin_manifest"]}
    assert sources <= {"repo"}                     # no cabinet-default rows appear
    # stack/profile-derived only, no base scope (ACME has a repo_url → github)
    assert pl["lane_mcps"] == ["neon", "vercel", "github"]


def test_repo_lane_gets_github_mcp():
    """A lane with a repo_url (or github in stack) maps the github MCP."""
    pl = plan.build_lane_plan(ACME, slug="acme")           # repo_url present
    assert "github" in pl["lane_mcps"]
    stack_only = {**ACME, "repo_url": None, "stack": ["github"]}
    assert "github" in plan.build_lane_plan(stack_only, slug="acme")["lane_mcps"]


def test_no_repo_no_github_mcp():
    """No repo_url and no github in stack → no github mapping (fail-closed)."""
    bare = {**ACME, "repo_url": None, "stack": ["neon"]}
    pl = plan.build_lane_plan(bare, slug="acme")
    assert "github" not in pl["lane_mcps"]
    assert pl["lane_mcps"] == ["neon"]


def test_github_in_base_not_duplicated():
    """A preset base scope already carrying github (developer preset) dedups."""
    d = {"cabinet_default_plugins": [],
         "lane_mcps": ["library", "telegram", "github", "playwright", "neon-ro"]}
    pl = plan.build_lane_plan(ACME, slug="acme", defaults=d)
    assert pl["lane_mcps"].count("github") == 1
    assert pl["lane_mcps"] == ["neon", "vercel", "github",
                               "library", "telegram", "playwright", "neon-ro"]


def test_missing_plugin_is_gated_not_executed():
    pl = plan.build_lane_plan({**ACME, "plugins": []}, slug="acme", defaults=DEFAULTS)
    actions = {a["action"] for a in pl["gated_actions"]}
    assert "install-plugin" in actions
    assert all(a.get("executed") is False for a in pl["gated_actions"])  # proposals only


def test_new_product_proposes_creation():
    pl = plan.build_lane_plan(ACME, slug="acme", existing=False)
    actions = {a["action"] for a in pl["gated_actions"]}
    assert "create-repo" in actions and "create-tracker-product" in actions


def test_existing_product_creates_nothing():
    pl = plan.build_lane_plan(ACME, slug="acme", existing=True)
    actions = {a["action"] for a in pl["gated_actions"]}
    assert "create-repo" not in actions and "create-tracker-product" not in actions


def test_germline_diffs_target_lane_ceo():
    pl = plan.build_lane_plan(ACME, slug="acme", defaults=DEFAULTS)
    assert "acme-ceo" in pl["mcp_scope_diff"] and "brain" in pl["mcp_scope_diff"]
    assert "acme-ceo" in pl["capabilities_diff"]
    assert "neon" in pl["lane_mcps"] and "vercel" in pl["lane_mcps"]


# The presets dir is a PARAMETER (layer payload — the caller owns its
# location; layer-separation gate), so tests seed a NEUTRAL tmp dir and pass
# it in; the instance-side active-preset pointer resolves through the env
# seam (framework.env.active_preset — CABINET_ACTIVE_PRESET override).
def _seed_preset(presets_dir, name="testpreset", block=True):
    pd = presets_dir / name
    pd.mkdir(parents=True)
    body = "name: %s\n" % name
    if block:
        body += ("onboarding:\n"
                 "  cabinet_default_plugins: [corridor, brain]\n"
                 "  lane_mcps: [library, telegram, brain]\n")
    (pd / "preset.yml").write_text(body)
    return presets_dir


def test_load_preset_defaults_reads_given_preset(tmp_path):
    pdir = _seed_preset(tmp_path / "pdir")
    d = plan.load_preset_defaults(pdir, active="testpreset")
    assert d["cabinet_default_plugins"] == ["corridor", "brain"]
    assert d["lane_mcps"] == ["library", "telegram", "brain"]


def test_load_preset_defaults_active_resolves_via_env_seam(tmp_path, monkeypatch):
    pdir = _seed_preset(tmp_path / "pdir")
    monkeypatch.setenv("CABINET_ACTIVE_PRESET", "testpreset")
    d = plan.load_preset_defaults(pdir)          # active=None → env seam
    assert d["lane_mcps"] == ["library", "telegram", "brain"]


def test_load_preset_defaults_fail_closed(tmp_path, monkeypatch):
    empty = {"cabinet_default_plugins": [], "lane_mcps": []}
    monkeypatch.setenv("CABINET_ACTIVE_PRESET", "testpreset")
    assert plan.load_preset_defaults(None) == empty              # no presets dir
    assert plan.load_preset_defaults(tmp_path / "pdir") == empty  # nothing declared
    pdir = _seed_preset(tmp_path / "pdir", block=False)
    assert plan.load_preset_defaults(pdir) == empty              # preset sans block
    assert plan.load_preset_defaults(pdir, active="../../evil") == empty  # traversal refused
    monkeypatch.setenv("CABINET_ACTIVE_PRESET", "../../evil")
    assert plan.load_preset_defaults(pdir) == empty              # env traversal refused too
