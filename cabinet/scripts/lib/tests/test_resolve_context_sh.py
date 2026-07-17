"""Config-split fix (2026-07-17) — contract + TWIN-PARITY tests for
``cabinet_resolve_context`` (lanes.sh) vs ``framework.env.active_context``.

The resolver is THE tasks/coordination context chain (my-tasks.sh, the
staged officer-launcher patch, task_sync_runner.py, and — minus the officer
rung — the dashboard's src/lib/active-context.ts):

    R1  CABINET_CONTEXT env
    R2  instance/config/active-project.txt
    R3  officer→lane derivation (exact slug, else LONGEST '<lane>-' prefix)
    R4  the single declared lane
    R5  lane_default (platform.yml/product.yml), only when declared
    else fail-LOUD (bash: rc 1 + remedy on stderr; python: ``default``/"").

Every scenario below runs BOTH twins against the same fixture root and pins
identical resolutions — the parity is the contract (rung-for-rung, documented
in both sources). Security teeth: candidates are shape-gated
([a-z0-9][a-z0-9-]{0,31}); the injection controls prove a poisoned
active-project.txt / env value is skipped as data, never executed, never
emitted.

Fixture vocabulary is synthetic Testburg (foundation fixtures never name
instance lanes — test_lanes_sh.py convention). No network, no Redis:
subprocess bash + in-process python over tmp_path config.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

# test_library_mcp_client patches the global subprocess.Popen and the patch
# can leak into later-alphabetical modules — capture the real one at import
# (collection) time and restore it around our spawns (test_lanes_sh.py guard).
_REAL_POPEN = subprocess.Popen

SCRIPTS_DIR = Path(__file__).resolve().parents[2]  # cabinet/scripts
REPO_ROOT = Path(__file__).resolve().parents[4]
LANES_SH = SCRIPTS_DIR / "lib" / "lanes.sh"

if str(REPO_ROOT) not in sys.path:  # for framework.env (the python twin)
    sys.path.insert(0, str(REPO_ROOT))

from framework.env import active_context  # noqa: E402


def _run_bash(root: Path, officer: str = "",
              cabinet_context: "str | None" = None) -> subprocess.CompletedProcess:
    """Invoke cabinet_resolve_context against a fixture root.

    Fixed argv + a constant -c string: fixture path, officer slug and the
    CABINET_CONTEXT value all travel via env, never interpolated into shell
    text (test_lanes_sh.py harness convention — the injection-safe transport
    is part of what's under test)."""
    env = {"CABINET_ROOT": str(root), "LANES_LIB": str(LANES_SH),
           "OFFICER_ARG": officer, "PATH": "/usr/bin:/bin"}
    if cabinet_context is not None:
        env["CABINET_CONTEXT"] = cabinet_context
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return subprocess.run(
            ["bash", "-c",
             'set -uo pipefail; source "$LANES_LIB"; '
             'cabinet_resolve_context "$OFFICER_ARG"'],
            capture_output=True, text=True, env=env,
        )
    finally:
        subprocess.Popen = patched


def _both(monkeypatch, root: Path, officer: str = "",
          cabinet_context: "str | None" = None) -> "tuple[str, subprocess.CompletedProcess]":
    """Resolve via BOTH twins; assert parity; return (resolved, bash proc).

    Parity contract: python returns "" exactly when bash rc != 0 with empty
    stdout; otherwise both yield the same slug."""
    if cabinet_context is None:
        monkeypatch.delenv("CABINET_CONTEXT", raising=False)
    else:
        monkeypatch.setenv("CABINET_CONTEXT", cabinet_context)
    py = active_context(officer=officer or None, root=root)
    proc = _run_bash(root, officer=officer, cabinet_context=cabinet_context)
    sh = proc.stdout.strip()
    assert sh == py, (
        f"twin divergence: bash={sh!r} (rc={proc.returncode}) python={py!r} "
        f"[officer={officer!r} env={cabinet_context!r}]\nstderr: {proc.stderr}")
    if py:
        assert proc.returncode == 0
    else:
        assert proc.returncode == 1 and sh == ""
    return py, proc


def _seed(root: Path, contexts: "dict[str, str] | None" = None,
          active_project: "str | None" = None,
          platform_yml: "str | None" = None,
          product_yml: "str | None" = None) -> Path:
    cfg = root / "instance" / "config"
    (cfg / "contexts").mkdir(parents=True, exist_ok=True)
    for name, body in (contexts or {}).items():
        (cfg / "contexts" / name).write_text(body, encoding="utf-8")
    if active_project is not None:
        (cfg / "active-project.txt").write_text(active_project, encoding="utf-8")
    if platform_yml is not None:
        (cfg / "platform.yml").write_text(platform_yml, encoding="utf-8")
    if product_yml is not None:
        (cfg / "product.yml").write_text(product_yml, encoding="utf-8")
    return root


TESTBURG_CONTEXTS = {
    "bakery-site.yml": "slug: bakery-site\nactive: false\n",
    "bakery.yml": "slug: bakery\nactive: true\n",
    "newsletter.yml": "slug: newsletter\n",
    "_default.yml": "# defaults only — deliberately no slug\n",
}


def test_bash_syntax_ok():
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        proc = subprocess.run(["bash", "-n", str(LANES_SH)],
                              capture_output=True, text=True)
    finally:
        subprocess.Popen = patched
    assert proc.returncode == 0, proc.stderr


# ------------------------------------------------------------ R1 / R2 ------

def test_env_wins_over_file_and_officer(monkeypatch, tmp_path):
    _seed(tmp_path, TESTBURG_CONTEXTS, active_project="newsletter\n")
    got, _ = _both(monkeypatch, tmp_path, officer="bakery-ceo",
                   cabinet_context="testburg-hq")
    assert got == "testburg-hq"


def test_malformed_env_is_skipped_not_emitted(monkeypatch, tmp_path):
    """UNTRUSTED env value with shell metacharacters: the rung is skipped as
    data (falls to the file rung) — never returned, never executed."""
    _seed(tmp_path, TESTBURG_CONTEXTS, active_project="newsletter\n")
    got, _ = _both(monkeypatch, tmp_path, officer="bakery-ceo",
                   cabinet_context="evil;$(rm -rf .)")
    assert got == "newsletter"


def test_oversize_env_slug_is_skipped(monkeypatch, tmp_path):
    _seed(tmp_path, TESTBURG_CONTEXTS, active_project="newsletter\n")
    got, _ = _both(monkeypatch, tmp_path, cabinet_context="a" * 33)
    assert got == "newsletter"


def test_file_wins_over_officer_and_is_whitespace_stripped(monkeypatch, tmp_path):
    _seed(tmp_path, TESTBURG_CONTEXTS, active_project="  newsletter \n")
    got, _ = _both(monkeypatch, tmp_path, officer="bakery-ceo")
    assert got == "newsletter"


def test_poisoned_active_project_txt_is_data_only(monkeypatch, tmp_path):
    """Injection control: a poisoned active-project.txt is refused by the
    shape gate, resolution falls through to the officer rung, and NOTHING is
    executed (no side-effect file appears)."""
    marker = tmp_path / "pwned"
    _seed(tmp_path, TESTBURG_CONTEXTS,
          active_project=f"$(touch {marker})\n")
    got, _ = _both(monkeypatch, tmp_path, officer="bakery-ceo")
    assert got == "bakery"
    assert not marker.exists(), "poisoned config value was EXECUTED"


def test_traversal_slug_in_file_is_refused(monkeypatch, tmp_path):
    _seed(tmp_path, TESTBURG_CONTEXTS, active_project="../../etc/passwd\n")
    got, _ = _both(monkeypatch, tmp_path, officer="bakery-ceo")
    assert got == "bakery"  # traversal shape never leaves the resolver


# ----------------------------------------------------------------- R3 ------

def test_officer_exact_lane_match(monkeypatch, tmp_path):
    _seed(tmp_path, TESTBURG_CONTEXTS)
    got, _ = _both(monkeypatch, tmp_path, officer="bakery")
    assert got == "bakery"


def test_officer_prefix_derivation(monkeypatch, tmp_path):
    """The portfolio '<lane>-ceo' shape — no suffix literal is hardcoded."""
    _seed(tmp_path, TESTBURG_CONTEXTS)
    got, _ = _both(monkeypatch, tmp_path, officer="newsletter-ceo")
    assert got == "newsletter"


def test_officer_longest_prefix_wins(monkeypatch, tmp_path):
    """officer bakery-site-ceo must land on bakery-site, not bakery."""
    _seed(tmp_path, TESTBURG_CONTEXTS)
    got, _ = _both(monkeypatch, tmp_path, officer="bakery-site-ceo")
    assert got == "bakery-site"


def test_active_false_lane_still_derives(monkeypatch, tmp_path):
    """The active-flag trap (test_lanes_sh.py): active:false lanes RUN LIVE
    on the launching instance — the resolver must not drop them."""
    _seed(tmp_path, TESTBURG_CONTEXTS)
    got, _ = _both(monkeypatch, tmp_path, officer="bakery-site-worker")
    assert got == "bakery-site"


# ------------------------------------------------------------ R4 / R5 ------

def test_single_declared_lane_resolves_without_officer(monkeypatch, tmp_path):
    _seed(tmp_path, {"bakery.yml": "slug: bakery\n",
                     "_default.yml": "# no slug\n"})
    got, _ = _both(monkeypatch, tmp_path)
    assert got == "bakery"


def test_lane_default_resolves_for_unmatched_officer(monkeypatch, tmp_path):
    _seed(tmp_path, TESTBURG_CONTEXTS,
          platform_yml="captain_name: Testburg\nlane_default: newsletter\n")
    got, _ = _both(monkeypatch, tmp_path, officer="cos")
    assert got == "newsletter"


def test_lane_default_must_be_a_declared_lane(monkeypatch, tmp_path):
    _seed(tmp_path, TESTBURG_CONTEXTS,
          platform_yml="lane_default: ghost-lane\n")
    got, proc = _both(monkeypatch, tmp_path, officer="cos")
    assert got == ""  # undeclared default is refused → fail-loud
    assert "CABINET_CONTEXT" in proc.stderr


def test_lane_default_nested_under_product_yml(monkeypatch, tmp_path):
    _seed(tmp_path, TESTBURG_CONTEXTS,
          product_yml="product:\n  name: Testburg\n  lane_default: bakery\n")
    got, _ = _both(monkeypatch, tmp_path, officer="cos")
    assert got == "bakery"


def test_platform_yml_wins_over_product_yml(monkeypatch, tmp_path):
    _seed(tmp_path, TESTBURG_CONTEXTS,
          platform_yml="lane_default: newsletter\n",
          product_yml="lane_default: bakery\n")
    got, _ = _both(monkeypatch, tmp_path, officer="cos")
    assert got == "newsletter"


# ----------------------------------------------------------- fail-LOUD -----

def test_no_rung_resolves_fails_loud_with_remedy(monkeypatch, tmp_path):
    _seed(tmp_path, TESTBURG_CONTEXTS)  # multi-lane, no default, officer cos
    got, proc = _both(monkeypatch, tmp_path, officer="cos")
    assert got == ""
    assert proc.returncode == 1 and proc.stdout == ""
    # the remedy one-liner names every rung the operator can supply
    for needle in ("CABINET_CONTEXT", "active-project.txt",
                   "contexts/<lane>.yml", "lane_default"):
        assert needle in proc.stderr, f"remedy missing {needle!r}"


def test_empty_deployment_fails_loud(monkeypatch, tmp_path):
    (tmp_path / "instance" / "config").mkdir(parents=True)
    got, proc = _both(monkeypatch, tmp_path, officer="bakery-ceo")
    assert got == "" and proc.returncode == 1


def test_no_silent_default_ever(monkeypatch, tmp_path):
    """Negative control for the fail-LOUD contract: an empty config tree must
    never invent a context (the old code's failure mode was silent misuse of
    a wrong default — officer_tasks.context_slug is NOT NULL and misfiled
    coordination state poisons every board)."""
    (tmp_path / "instance" / "config" / "contexts").mkdir(parents=True)
    got, proc = _both(monkeypatch, tmp_path)
    assert got == "" and proc.stdout == ""
