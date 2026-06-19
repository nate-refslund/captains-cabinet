"""A4 — the mechanical low-risk deploy classifier (Component 6, NON-PROD only).

`classify_deploy` is the deterministic gate that the `deploy_nonprod` verdict
`classifier` branch calls: it returns `"auto"` iff ALL four signals say
low-risk (every changed file is a safe glob; no changed file is a high-risk
glob; CI == success; preview deployment == READY) AND the target is non-prod.
Any unreadable/unknown signal, an unknown high-risk glob, or a prod target ->
`"propose_only"` (fail-closed). Per FIX-6 the auto output is preview/staging
ONLY; a prod deploy can never resolve to auto.

The four real signals (git diff, GitHub CI status, Vercel preview state) are
INJECTED as pure functions so the classifier is testable with fakes — no real
git/GitHub/Vercel calls here. See docs/authority-matrix-design-2026-06-19.md
§Component 6 + FIX-6.

SHADOW-ONLY / standalone: this module is NOT wired into policy_engine or the
pre-tool-use hook here (that is a later Captain-authorized pass).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root on sys.path so the framework package imports cleanly (same
# convention as the sibling authority/fidelity tests).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import deploy_classifier as DC  # noqa: E402
from framework.authority import matrix as M  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes for the three injected signal functions (pure, deterministic).
# ---------------------------------------------------------------------------

def _diff(files):
    """A fake git_diff_fn returning a fixed changed-file list."""
    return lambda tool_input: list(files)


def _ci(state):
    """A fake ci_status_fn returning a fixed CI state."""
    return lambda tool_input: state


def _preview(state):
    """A fake preview_state_fn returning a fixed Vercel preview state."""
    return lambda tool_input: state


def _raises(exc=RuntimeError("signal unreadable")):
    def _fn(tool_input):
        raise exc
    return _fn


# The shipped framework-floor deploy config (safe_globs + high_risk_globs).
@pytest.fixture()
def deploy_cfg():
    policy = M.matrix_policy(M.load_matrix())
    return policy["deploy"]


# A canonical non-prod preview deploy tool call.
PREVIEW_INPUT = {"command": "vercel deploy --target preview"}
PROD_INPUT = {"command": "vercel deploy --prod"}
PUSH_MAIN_INPUT = {"command": "git push origin main"}


# ---------------------------------------------------------------------------
# 1. The happy path: all four signals green, non-prod target -> auto
# ---------------------------------------------------------------------------

def test_all_safe_globs_ci_green_preview_ready_yields_auto(deploy_cfg):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_diff(["docs/readme.md", "src/foo.test.ts", "tsconfig.json"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "auto"


def test_only_markdown_changed_yields_auto(deploy_cfg):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_diff(["docs/a.md", "docs/sub/b.md", "README.md"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "auto"


# ---------------------------------------------------------------------------
# 2. A high-risk glob in the diff -> propose_only
# ---------------------------------------------------------------------------

def test_migrations_sql_diff_yields_propose_only(deploy_cfg):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_diff(["db/migrations/001_init.sql", "docs/readme.md"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


@pytest.mark.parametrize("risky", [
    "db/migrations/002_add.sql",
    "schema.sql",
    "app/db_schema.ts",
    "auth/login.ts",
    "authentication/handler.py",
    "src/jwt/sign.ts",
    "lib/oauth_client.ts",
    "payment_intent.ts",
    "stripe/webhook.ts",
    "billing/invoice.ts",
    "app/checkout_page.tsx",
    "app/subscription_plan.ts",
    "neon.json",
    "infra/neon/branch.ts",
    "vercel.json",
    ".vercelignore",
    ".env.production",
    "policies/authority-matrix.yml",
    "framework/schemas-base.sql",
    "cabinet/init.sql",
    "presets/work/schemas.sql",
])
def test_every_high_risk_glob_gates(deploy_cfg, risky):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        # diff = the risky file alongside an otherwise-safe one
        git_diff_fn=_diff([risky, "docs/x.md"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only", risky


# ---------------------------------------------------------------------------
# 3. A changed file matching NO safe glob (and not high-risk) -> propose_only
#    (low-risk requires EVERY file to be a safe glob)
# ---------------------------------------------------------------------------

def test_unrecognized_safe_file_gates(deploy_cfg):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_diff(["src/app.ts"]),  # not in safe_globs, not high-risk
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


# ---------------------------------------------------------------------------
# 4. CI not green / unknown -> propose_only
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ci_state", ["pending", "failure", "error", "", None, "unknown"])
def test_ci_not_success_gates(deploy_cfg, ci_state):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_diff(["docs/a.md"]),
        ci_status_fn=_ci(ci_state),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


def test_ci_signal_raises_gates(deploy_cfg):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_diff(["docs/a.md"]),
        ci_status_fn=_raises(),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


# ---------------------------------------------------------------------------
# 5. Preview not READY / unreadable -> propose_only
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pv_state", ["BUILDING", "QUEUED", "ERROR", "CANCELED", "", None])
def test_preview_not_ready_gates(deploy_cfg, pv_state):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_diff(["docs/a.md"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview(pv_state),
    )
    assert verdict == "propose_only"


def test_preview_signal_raises_gates(deploy_cfg):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_diff(["docs/a.md"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_raises(),
    )
    assert verdict == "propose_only"


def test_git_diff_signal_raises_gates(deploy_cfg):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_raises(),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


def test_empty_diff_gates(deploy_cfg):
    # No changed files at all is not a positive low-risk signal -> fail-closed.
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_diff([]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


# ---------------------------------------------------------------------------
# 6. PROD target -> propose_only, ALWAYS (FIX-6: no prod auto path)
# ---------------------------------------------------------------------------

def test_prod_vercel_target_gates_even_when_all_signals_green(deploy_cfg):
    verdict = DC.classify_deploy(
        PROD_INPUT,
        deploy_cfg,
        git_diff_fn=_diff(["docs/a.md"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


def test_prod_git_push_main_gates(deploy_cfg):
    verdict = DC.classify_deploy(
        PUSH_MAIN_INPUT,
        deploy_cfg,
        git_diff_fn=_diff(["docs/a.md"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


def test_explicit_prod_target_field_gates(deploy_cfg):
    verdict = DC.classify_deploy(
        {"command": "deploy", "target": "production"},
        deploy_cfg,
        git_diff_fn=_diff(["docs/a.md"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


# ---------------------------------------------------------------------------
# 7. Regex backstop: unknown new top-level dir containing .sql / auth / payment
#    is treated as high-risk -> propose_only, even though no glob matches.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("risky", [
    "iam/roles.sql",          # unknown top-level dir + .sql
    "newauth/provider.ts",    # auth token in an unknown top-level dir
    "paymentsv2/charge.ts",   # payment token in an unknown top-level dir
    "ledger/credentials.ts",  # credential token
])
def test_regex_backstop_unknown_risky_dir_gates(deploy_cfg, risky):
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        deploy_cfg,
        git_diff_fn=_diff([risky]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only", risky


# ---------------------------------------------------------------------------
# 8. Fail-closed on a malformed deploy_cfg (missing globs).
# ---------------------------------------------------------------------------

def test_missing_safe_globs_gates():
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        {"high_risk_globs": ["**/*.sql"]},  # no safe_globs key
        git_diff_fn=_diff(["docs/a.md"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


def test_non_dict_deploy_cfg_gates():
    verdict = DC.classify_deploy(
        PREVIEW_INPUT,
        None,
        git_diff_fn=_diff(["docs/a.md"]),
        ci_status_fn=_ci("success"),
        preview_state_fn=_preview("READY"),
    )
    assert verdict == "propose_only"


# ---------------------------------------------------------------------------
# 9. matches_any_glob unit behavior (the matcher backbone).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,glob,expected", [
    ("docs/a.md", "docs/**", True),
    ("docs/sub/a.md", "docs/**", True),
    ("a.md", "**/*.md", True),
    ("docs/a.md", "**/*.md", True),
    ("src/foo.test.ts", "**/*.test.*", True),
    ("tsconfig.json", "tsconfig.json", True),
    (".eslintrc.json", ".eslintrc*", True),
    ("db/migrations/x.sql", "**/migrations/*.sql", True),
    ("schema.sql", "**/schema*.sql", True),
    ("src/app.ts", "docs/**", False),
    ("src/app.ts", "**/*.md", False),
])
def test_matches_any_glob(path, glob, expected):
    assert DC.matches_any_glob(path, [glob]) is expected
