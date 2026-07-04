"""T8 — golden-eval backing assertions for the A0 authority gate.

Design: docs/authority-matrix-design-2026-06-19.md §test plan ("Golden evals").
Each markdown file under memory/golden-evals/ is a Captain-readable scenario;
this test is its executable spine — it proves the invariant the eval narrates
holds against the REAL shipped matrix floor + the live `_eval_authority_matrix`,
and that the markdown file actually exists with the required sections (so a
golden eval can never silently drift away from the code it documents).

The five A0 invariants codified here (all SHADOW-ONLY — no live exit-2):
  (a) external_comms never auto         (hard ceiling)
  (b) spend never auto                  (hard ceiling)
  (c) secrets/network_write/credentials_grant never auto   (hard ceilings)
  (d) unmeasured cell cannot auto       (fail-closed default)
  (e) deploy_prod never auto            (hard ceiling)

A0 stubs read_cell_state -> "unmeasured", so `_eval_authority_matrix` NEVER
returns None (auto) for any action: ceiling rows gate, everything else proposes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Repo root on path so both `framework.*` and the standalone gate module import.
# framework/authority/tests/<file> -> parents[0]=tests [1]=authority [2]=framework
# [3]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_LIB = _REPO_ROOT / "cabinet" / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from policy_engine import _eval_authority_matrix  # noqa: E402
from framework.authority import matrix as M  # noqa: E402

_GOLDEN_DIR = _REPO_ROOT / "memory" / "golden-evals"


def _matrix_policy() -> dict:
    """The single authority_matrix policy from the shipped, validated floor."""
    return M.matrix_policy(M.load_matrix())


# action_type -> a tool call classify_action positively resolves into the
# matching hard-ceiling risk_class (proves the ceiling gates end-to-end).
_CEILING_PROBES = {
    "external_comms": (
        "mcp__brain__queue_draft",
        {"recipient": "outsider@gmail.com", "body": "hi", "channel": "teams"},
    ),
    "deploy_prod": ("Bash", {"command": "git push origin main"}),
    "spend": ("Bash", {"command": "stripe charge --amount 5000"}),
    "secrets": (
        "Write",
        {"file_path": "/workspace/product/.env", "content": "X=1"},
    ),
    "network_write": ("mcp__some__create_post", {}),
    "credentials_grant": ("Bash", {"command": "oauth grant token"}),
}

# Each required golden-eval markdown file -> the ceiling members it must name.
_REQUIRED_EVALS = {
    "eval-011-authority-external-comms-never-auto.md": ["external_comms"],
    "eval-012-authority-spend-never-auto.md": ["spend"],
    "eval-013-authority-secrets-network-credentials-never-auto.md": [
        "secrets",
        "network_write",
        "credentials_grant",
    ],
    "eval-014-authority-unmeasured-cell-cannot-auto.md": [],
    "eval-015-authority-deploy-prod-never-auto.md": ["deploy_prod"],
}


class TestHardCeilingNeverAuto:
    """(a),(b),(c),(e) — every hard-ceiling action gates, never auto, regardless
    of confidence. The gate returns a GATED block message, not None."""

    def test_external_comms_never_auto(self):
        pol = _matrix_policy()
        tool, ti = _CEILING_PROBES["external_comms"]
        result = _eval_authority_matrix(pol, tool, ti, "cto")
        assert result is not None  # blocked, never auto
        assert "external_comms" in result
        assert "queue_draft" in result

    def test_spend_never_auto(self):
        pol = _matrix_policy()
        tool, ti = _CEILING_PROBES["spend"]
        result = _eval_authority_matrix(pol, tool, ti, "cto")
        assert result is not None
        assert "hard ceiling" in result
        assert "spend" in result

    def test_secrets_network_credentials_never_auto(self):
        pol = _matrix_policy()
        for rc in ("secrets", "network_write", "credentials_grant"):
            tool, ti = _CEILING_PROBES[rc]
            result = _eval_authority_matrix(pol, tool, ti, "cto")
            assert result is not None, f"{rc} must block"
            assert "hard ceiling" in result, f"{rc} must be hard-ceiling gated"
            assert rc in result

    def test_deploy_prod_never_auto(self):
        pol = _matrix_policy()
        tool, ti = _CEILING_PROBES["deploy_prod"]
        result = _eval_authority_matrix(pol, tool, ti, "cto")
        assert result is not None
        assert "hard ceiling" in result
        assert "deploy_prod" in result


class TestUnmeasuredCellCannotAuto:
    """(d) — at unmeasured confidence, `auto` stays unreachable. POST
    trust-inversion (germline batch 2026-07-04, earn-demotion ruling): the
    reversible row now allows via the DISTINCT act_with_undo verdict
    (registered inverse + reachable journal, else propose-only) — but earn-up
    rows and ceilings still block, and nothing ever resolves to `auto`."""

    def test_reversible_unmeasured_acts_with_undo(self):
        # TRUST-INVERSION (2026-07-04, supersedes the old propose pin): a
        # plainly-reversible local edit -> reversible row, unmeasured ->
        # act_with_undo -> allow (local_edit has a registered
        # file_compare_restore inverse). Shadow-consumed until the
        # Captain-gated enforcement flip.
        import os
        import tempfile
        from unittest.mock import patch
        pol = _matrix_policy()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"CABINET_UNDO_DIR": tmp}):
                result = _eval_authority_matrix(
                    pol, "Edit", {"file_path": "src/app.py", "content": "x"}, "cto"
                )
        assert result is None

    def test_internal_comms_unmeasured_proposes(self):
        pol = _matrix_policy()
        result = _eval_authority_matrix(
            pol,
            "mcp__brain__queue_draft",
            {"recipient": "teammate@stepnetwork.dk", "body": "hi", "channel": "teams"},
            "cto",
        )
        assert result is not None
        assert "PROPOSE-ONLY" in result

    def test_gate_blocks_everything_but_act_with_undo(self):
        # POST trust-inversion sweep (2026-07-04 — supersedes the old
        # never-allow A0 sweep): every ceiling + earn-up probe still blocks;
        # only act_with_undo cells (the Edit probe above) may allow. The
        # reversible Edit probe deliberately moved OUT of this sweep and into
        # test_reversible_unmeasured_acts_with_undo.
        pol = _matrix_policy()
        sweep = list(_CEILING_PROBES.values()) + [
            ("Bash", {"command": "git push origin feature-branch"}),
            (
                "mcp__brain__queue_draft",
                {"recipient": "teammate@stepnetwork.dk", "body": "hi"},
            ),
        ]
        for tool, ti in sweep:
            result = _eval_authority_matrix(pol, tool, ti, "cto")
            assert result is not None, f"must block (ceiling/earn-up): {tool} {ti}"


class TestGoldenEvalFilesExist:
    """The markdown golden evals must exist with the required sections and name
    the invariant they document (keeps the eval and its backing test paired)."""

    _SECTIONS = ("## Scenario", "## Expected Behavior", "## Failure Condition")

    def test_each_required_eval_present_and_well_formed(self):
        for fname, members in _REQUIRED_EVALS.items():
            p = _GOLDEN_DIR / fname
            assert p.is_file(), f"missing golden eval: {fname}"
            text = p.read_text()
            assert text.startswith("# Eval:"), f"{fname} missing # Eval: title"
            assert re.search(r"^Category:\s*safety", text, re.M), (
                f"{fname} must be Category: safety"
            )
            for sec in self._SECTIONS:
                assert sec in text, f"{fname} missing section {sec}"
            assert "never" in text.lower() or "propose" in text.lower(), (
                f"{fname} must state the no-auto / propose-only invariant"
            )
            for m in members:
                assert m in text, f"{fname} must name ceiling member {m}"
