"""T1 — tests for the shared deterministic classify_action / resolve_lane.

These are the F+A join key: ONE classifier maps a raw tool call to an
`action_type` enum string, used by BOTH the consequence emitter (F, ledger
key) and the policy-engine gate (A, verdict lookup). The mapping must be
deterministic, pure (no IO beyond env in resolve_lane), and FAIL-CLOSED:
ambiguous/unknown actions resolve to a propose-defaulting value, while the
always-gated ceiling classes (secrets, network_write, credentials_grant) are
POSITIVELY classified — never left to the ambiguous backstop.

See docs/authority-matrix-design-2026-06-19.md §2 (classify_action rules),
§3 (resolve_lane), FIX-1, FIX-4, FIX-7.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Repo root on sys.path so `framework.authority` imports as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from framework.authority.classifier import (  # noqa: E402
    ACTION_TYPES,
    AMBIGUOUS,
    CEILING_ACTION_TYPES,
    classify_action,
)
from framework.authority.lane import resolve_lane  # noqa: E402


# ===================================================================
# enum surface
# ===================================================================

class TestEnumSurface:
    def test_ambiguous_is_propose_defaulting(self):
        # The ambiguous backstop must itself be one of the recognized
        # action types and must NOT be one of the local/reversible ones —
        # it is a distinct, visible, propose-defaulting value (fail-safe).
        assert AMBIGUOUS in ACTION_TYPES
        assert AMBIGUOUS != "local_edit"

    def test_all_design_action_types_present(self):
        expected = {
            "task_status_move", "board_status", "label", "tier2_note",
            "draft_only", "local_edit",
            "internal_message", "internal_email",
            "external_message", "external_email",
            "vercel_deploy_preview", "git_push_nonmain",
            "vercel_deploy_prod", "git_push_main",
            "purchase", "provision_paid", "billing",
            "secret_read", "secret_write", "env_write",
            "mcp_post", "mcp_put", "mcp_delete",
            "oauth_grant", "token_grant",
        }
        assert expected <= ACTION_TYPES

    def test_ceiling_action_types_cover_three_execution_surface_classes(self):
        # secrets, network_write, credentials_grant action_types are the
        # ones classify_action must POSITIVELY produce (never the backstop).
        assert {
            "secret_read", "secret_write", "env_write",
            "mcp_post", "mcp_put", "mcp_delete",
            "oauth_grant", "token_grant",
        } <= CEILING_ACTION_TYPES


# ===================================================================
# determinism / purity
# ===================================================================

class TestDeterminism:
    def test_same_input_same_output(self):
        ti = {"command": "git push origin main"}
        a = classify_action("Bash", ti)
        b = classify_action("Bash", ti)
        assert a == b == "git_push_main"

    def test_does_not_mutate_input(self):
        ti = {"command": "git push origin main"}
        snapshot = dict(ti)
        classify_action("Bash", ti)
        assert ti == snapshot

    def test_returns_string_member_of_enum(self):
        for tn, ti in [
            ("Bash", {"command": "ls -la"}),
            ("Edit", {"file_path": "/workspace/product/src/app.ts"}),
            ("Bash", {"command": "git push origin main"}),
        ]:
            out = classify_action(tn, ti)
            assert isinstance(out, str)
            assert out in ACTION_TYPES


# ===================================================================
# deploy — git push (prod vs nonprod)
# ===================================================================

class TestGitPush:
    @pytest.mark.parametrize("cmd", [
        "git push origin main",
        "git push origin master",
        "git push",                       # bare push → default branch → prod-conservative
        "git push --force origin main",
        "git push -u origin master",
        "git push origin HEAD:main",
    ])
    def test_push_to_main_is_prod(self, cmd):
        assert classify_action("Bash", {"command": cmd}) == "git_push_main"

    @pytest.mark.parametrize("cmd", [
        "git push origin feature/foo",
        "git push origin my-branch",
        "git push origin HEAD:feat/x",
    ])
    def test_push_to_branch_is_nonprod(self, cmd):
        assert classify_action("Bash", {"command": cmd}) == "git_push_nonmain"

    def test_git_non_push_is_not_deploy(self):
        # git status / git diff are reversible/local, never a deploy class.
        out = classify_action("Bash", {"command": "git status"})
        assert out not in ("git_push_main", "git_push_nonmain")


# ===================================================================
# deploy — vercel
# ===================================================================

class TestVercelDeploy:
    @pytest.mark.parametrize("cmd", [
        "vercel deploy --prod",
        "vercel --prod",
        "vercel deploy --prod --yes",
        "npx vercel --prod",
    ])
    def test_vercel_prod(self, cmd):
        assert classify_action("Bash", {"command": cmd}) == "vercel_deploy_prod"

    @pytest.mark.parametrize("cmd", [
        "vercel deploy",
        "vercel deploy --target preview",
        "vercel --target=preview",
        "npx vercel deploy --target preview",
    ])
    def test_vercel_preview(self, cmd):
        assert classify_action("Bash", {"command": cmd}) == "vercel_deploy_preview"


# ===================================================================
# comms — internal vs external (recipient domain)
# ===================================================================

class TestComms:
    def test_external_message_by_domain(self):
        out = classify_action(
            "mcp__brain__queue_draft",
            {"channel": "teams", "recipient": "anna@styria.com", "body": "hi"},
        )
        assert out == "external_message"

    def test_external_email_by_domain(self):
        out = classify_action(
            "mcp__brain__queue_draft",
            {"channel": "email", "recipient": "client@example.org", "body": "x"},
        )
        assert out == "external_email"

    def test_internal_message_by_domain(self):
        out = classify_action(
            "mcp__brain__queue_draft",
            {"channel": "teams", "recipient": "sean@stepnetwork.dk", "body": "hi"},
        )
        assert out == "internal_message"

    def test_internal_email_by_domain(self):
        out = classify_action(
            "mcp__brain__queue_draft",
            {"channel": "email", "recipient": "ulrik@jfmedier.dk", "body": "x"},
        )
        assert out == "internal_email"

    def test_unknown_recipient_comms_is_external_failclosed(self):
        # A comms send with an unresolvable / missing recipient must NOT
        # silently fall to internal — external is the conservative comms
        # default (always-gated ceiling), so an unknown recipient gates.
        out = classify_action(
            "mcp__brain__queue_draft",
            {"channel": "email", "recipient": "", "body": "x"},
        )
        assert out in ("external_email", "external_message")


# ===================================================================
# board / task status (reversible)
# ===================================================================

class TestBoardStatus:
    def test_monday_status_change_is_board_status(self):
        out = classify_action(
            "mcp__claude_ai_monday_com__change_item_column_values",
            {"board_id": "5091", "column_id": "status", "value": "Done"},
        )
        assert out == "board_status"

    def test_linear_state_update_is_task_status_move(self):
        out = classify_action(
            "mcp__linear__update_issue",
            {"id": "ENG-1", "stateId": "done"},
        )
        assert out == "task_status_move"


# ===================================================================
# spend (always-gated)
# ===================================================================

class TestSpend:
    @pytest.mark.parametrize("cmd,expected", [
        ("stripe charges create --amount 5000", "purchase"),
        ("vercel domains buy example.com", "purchase"),
    ])
    def test_purchase(self, cmd, expected):
        assert classify_action("Bash", {"command": cmd}) == expected

    def test_paid_provisioning(self):
        out = classify_action(
            "mcp__Neon__create_project",
            {"name": "prod", "plan": "scale"},
        )
        assert out == "provision_paid"

    def test_billing(self):
        out = classify_action("Bash", {"command": "vercel billing update"})
        assert out == "billing"


# ===================================================================
# secrets (CEILING — positive classification, never the backstop) [FIX-7]
# ===================================================================

class TestSecrets:
    def test_env_write_via_edit(self):
        out = classify_action("Edit", {"file_path": "/workspace/product/.env"})
        assert out == "env_write"

    def test_env_write_dotenv_variant(self):
        out = classify_action("Write", {"file_path": "/x/.env.production"})
        assert out == "env_write"

    def test_secret_read_via_bash(self):
        out = classify_action("Bash", {"command": "cat /workspace/product/.env"})
        assert out == "secret_read"

    def test_secret_read_dotenv_relative_after_space(self):
        # Regression: a `.env.local` token preceded by a space (not a slash)
        # must still be detected as a secret read — fail-closed, not silently
        # downgraded to local_edit.
        out = classify_action("Bash", {"command": "cat .env.local"})
        assert out == "secret_read"

    def test_secret_read_bare_dotenv_after_space(self):
        out = classify_action("Bash", {"command": "less .env"})
        assert out == "secret_read"

    def test_secret_write_via_bash_redirect(self):
        out = classify_action(
            "Bash", {"command": "echo TOKEN=abc > /workspace/product/.env.local"}
        )
        assert out == "secret_write"

    def test_secret_store_access(self):
        out = classify_action(
            "Bash", {"command": "vercel env add SECRET_KEY production"}
        )
        assert out in {"secret_write", "env_write"}

    def test_secret_classes_are_ceiling_not_ambiguous(self):
        # The critical fail-closed invariant: a .env touch is positively a
        # ceiling secrets action, NOT the ambiguous backstop.
        for out in (
            classify_action("Edit", {"file_path": "/x/.env"}),
            classify_action("Bash", {"command": "cat /x/.env"}),
        ):
            assert out in CEILING_ACTION_TYPES
            assert out != AMBIGUOUS


# ===================================================================
# network_write (CEILING — positive classification) [FIX-7]
# ===================================================================

class TestNetworkWrite:
    @pytest.mark.parametrize("cmd,expected", [
        ("curl -X POST https://api.example.com/v1/things -d '{}'", "mcp_post"),
        ("curl -X PUT https://api.example.com/v1/things/1 -d '{}'", "mcp_put"),
        ("curl -X DELETE https://api.example.com/v1/things/1", "mcp_delete"),
    ])
    def test_curl_mutating_verbs(self, cmd, expected):
        assert classify_action("Bash", {"command": cmd}) == expected

    def test_curl_get_is_not_network_write(self):
        out = classify_action(
            "Bash", {"command": "curl -X GET https://api.example.com/v1/things"}
        )
        assert out not in ("mcp_post", "mcp_put", "mcp_delete")

    def test_curl_to_localhost_is_not_network_write(self):
        # Local endpoint → no egress → not a network-write ceiling.
        out = classify_action(
            "Bash", {"command": "curl -X POST http://localhost:3000/api -d '{}'"}
        )
        assert out not in ("mcp_post", "mcp_put", "mcp_delete")

    def test_mcp_mutating_tool_is_network_write(self):
        # A generic live-mutating MCP HTTP verb tool maps to network_write.
        out = classify_action("mcp__some_api__post_resource", {"url": "https://x"})
        assert out == "mcp_post"

    def test_network_write_is_ceiling_not_ambiguous(self):
        out = classify_action(
            "Bash", {"command": "curl -X POST https://api.example.com -d '{}'"}
        )
        assert out in CEILING_ACTION_TYPES
        assert out != AMBIGUOUS


# ===================================================================
# credentials_grant (CEILING — positive classification) [FIX-7]
# ===================================================================

class TestCredentialsGrant:
    @pytest.mark.parametrize("cmd,expected", [
        ("gh auth token --grant repo", "token_grant"),
        ("vercel oauth grant team", "oauth_grant"),
    ])
    def test_grant_flows(self, cmd, expected):
        assert classify_action("Bash", {"command": cmd}) == expected

    def test_oauth_grant_via_mcp(self):
        out = classify_action(
            "mcp__claude_ai_PolAds_PO__complete_authentication",
            {"grant": "oauth"},
        )
        assert out == "oauth_grant"

    def test_credentials_grant_is_ceiling_not_ambiguous(self):
        out = classify_action("Bash", {"command": "vercel oauth grant team"})
        assert out in CEILING_ACTION_TYPES
        assert out != AMBIGUOUS


# ===================================================================
# reversible / local
# ===================================================================

class TestReversibleLocal:
    @pytest.mark.parametrize("tn,ti", [
        ("Edit", {"file_path": "/workspace/product/src/app.ts"}),
        ("Write", {"file_path": "/workspace/product/README.md"}),
        ("Bash", {"command": "ls -la"}),
        ("Bash", {"command": "git status"}),
        ("Bash", {"command": "npm test"}),
    ])
    def test_local_edit(self, tn, ti):
        assert classify_action(tn, ti) == "local_edit"

    def test_tier2_note(self):
        out = classify_action(
            "Write",
            {"file_path": "/opt/founders-cabinet/instance/memory/tier2/cos/notes.md"},
        )
        assert out == "tier2_note"

    def test_read_only_tools_are_local(self):
        for tn in ("Read", "Grep", "Glob"):
            assert classify_action(tn, {"file_path": "/x/y"}) == "local_edit"


# ===================================================================
# fail-safe / ambiguous backstop
# ===================================================================

class TestFailSafe:
    def test_unknown_tool_unknown_shape_is_ambiguous(self):
        # A tool we don't recognize, with no positively-local signal and no
        # ceiling signal, must default to the visible ambiguous (propose)
        # value — NOT silently to local_edit.
        out = classify_action("mcp__weird_unknown__do_thing", {"foo": "bar"})
        assert out == AMBIGUOUS

    def test_ambiguous_never_a_ceiling_class(self):
        out = classify_action("mcp__weird_unknown__do_thing", {"foo": "bar"})
        assert out not in CEILING_ACTION_TYPES

    def test_empty_input(self):
        out = classify_action("Bash", {})
        # No command → nothing to act on → ambiguous (propose), not local.
        assert out == AMBIGUOUS


# ===================================================================
# resolve_lane precedence [FIX-4]
# ===================================================================

class TestResolveLane:
    def test_cabinet_lane_wins(self, monkeypatch):
        monkeypatch.setenv("CABINET_LANE", "polads")
        monkeypatch.setenv("PROJECT", "stephie")
        assert resolve_lane() == "polads"

    def test_falls_back_to_project(self, monkeypatch):
        monkeypatch.delenv("CABINET_LANE", raising=False)
        monkeypatch.setenv("PROJECT", "stephie")
        assert resolve_lane() == "stephie"

    def test_none_when_unset(self, monkeypatch):
        monkeypatch.delenv("CABINET_LANE", raising=False)
        monkeypatch.delenv("PROJECT", raising=False)
        assert resolve_lane() is None

    def test_empty_cabinet_lane_falls_through(self, monkeypatch):
        monkeypatch.setenv("CABINET_LANE", "")
        monkeypatch.setenv("PROJECT", "stephie")
        assert resolve_lane() == "stephie"

    def test_no_path_interpolation(self, monkeypatch):
        # resolve_lane reads only the two named env vars verbatim — it does
        # not interpolate or resolve filesystem paths (no injection surface).
        monkeypatch.setenv("CABINET_LANE", "../../etc/passwd")
        assert resolve_lane() == "../../etc/passwd"
