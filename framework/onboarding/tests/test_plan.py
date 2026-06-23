"""build_lane_plan — profile → answers lane-entry + plugin manifest + gated proposals
+ germline diffs. Pure; nothing executed."""
from framework.onboarding import plan

POLADS = {
    "name": "v0-politiske-annoncer",
    "summary": "EU political ad transparency platform.",
    "stack": ["neon", "nextjs", "vercel"],
    "plugins": ["dev-tasks", "corridor", "neon", "vercel"],
    "repo_url": "https://github.com/STEP-Network/v0-politiske-annoncer",
    "has_claude": True,
    "path": "/Users/nate/v0-politiske-annoncer",
}


def test_answers_lane_core():
    a = plan.build_lane_plan(POLADS, slug="polads", board_id="5092199368")["answers_lane"]
    assert a["slug"] == "polads"
    assert a["name"] == "v0-politiske-annoncer"
    assert a["repos"] == ["https://github.com/STEP-Network/v0-politiske-annoncer"]
    assert a["boards"] == ["5092199368"]
    assert a["plugin"] == "dev-tasks"          # detected task route


def test_plugin_manifest_present_vs_default():
    names = {p["name"]: p for p in plan.build_lane_plan(POLADS, slug="polads")["plugin_manifest"]}
    assert names["dev-tasks"]["present"] is True
    assert names["corridor"]["present"] is True
    assert "brain" in names                     # cabinet default surfaced


def test_missing_plugin_is_gated_not_executed():
    pl = plan.build_lane_plan({**POLADS, "plugins": []}, slug="polads")
    actions = {a["action"] for a in pl["gated_actions"]}
    assert "install-plugin" in actions
    assert all(a.get("executed") is False for a in pl["gated_actions"])  # proposals only


def test_new_product_proposes_creation():
    pl = plan.build_lane_plan(POLADS, slug="polads", existing=False)
    actions = {a["action"] for a in pl["gated_actions"]}
    assert "create-repo" in actions and "create-monday-product" in actions


def test_existing_product_creates_nothing():
    pl = plan.build_lane_plan(POLADS, slug="polads", existing=True)
    actions = {a["action"] for a in pl["gated_actions"]}
    assert "create-repo" not in actions and "create-monday-product" not in actions


def test_germline_diffs_target_lane_ceo():
    pl = plan.build_lane_plan(POLADS, slug="polads")
    assert "polads-ceo" in pl["mcp_scope_diff"] and "brain" in pl["mcp_scope_diff"]
    assert "polads-ceo" in pl["capabilities_diff"]
    assert "neon" in pl["lane_mcps"] and "vercel" in pl["lane_mcps"]
