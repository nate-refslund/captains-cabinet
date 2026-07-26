"""`org-runtime missions complete` must not let work verify itself.

Measured on 05871f12: completion marked a node `verified` with a
caller-supplied --verified-value while --actor DEFAULTED TO "cos" — the
officer doing the work was the default verifier. It never read the node's
verifier_role, never compared actor to owner, and never called
require_active_role, so an actor naming a role that does not exist was
accepted verbatim and written onto the event.

STRENGTH — do not over-read these tests. `--actor` is a caller-supplied CLI
string and every officer runs as the same OS user, so this is SEPARATION OF
DUTIES, not authentication. It stops accidents and self-dealing; it does not
stop a determined caller from passing any actor name.

These arms drive the real CLI through a temp SQLite DB rather than calling the
gate helper directly, so they assert what an operator actually gets.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ORG = _REPO_ROOT / "cabinet" / "scripts" / "org-runtime.py"


@pytest.fixture
def org(tmp_path):
    """Return a runner bound to a hermetic org-runtime DB."""
    env_extra = {
        "ORG_RUNTIME_DB": str(tmp_path / "org.sqlite3"),
        "ORG_RUNTIME_PRODUCT": "captains-cabinet",
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    def run(*args):
        import os
        env = dict(os.environ, **env_extra)
        return subprocess.run(
            [sys.executable, str(_ORG), *args],
            capture_output=True, text=True, env=env, cwd=str(_REPO_ROOT),
        )

    return run


def _role(org, slug):
    r = org("roles", "define", "--role", slug, "--name", slug,
            "--charter", "c", "--current-focus", "f",
            "--authority-level", "mission_orchestrator",
            "--capability", "mission_compilation",
            "--officer-session-slug", slug, "--actor", "cos")
    assert r.returncode == 0, r.stderr
    return slug


@pytest.fixture
def node(org):
    """A ratified outcome with one node owned by `cos`, verified by `auditor`."""
    _role(org, "cos")
    _role(org, "auditor")
    r = org("outcomes", "propose", "--title", "t", "--metric-name", "m",
            "--target-value", "12", "--unit", "points", "--actor", "cos")
    assert r.returncode == 0, r.stderr
    outcome_id = json.loads(r.stdout)["outcome_id"]
    assert org("outcomes", "ratify", outcome_id, "--ratified-by", "captain",
               "--note", "n").returncode == 0

    def make():
        c = org("missions", "compile", outcome_id, "--title", "T",
                "--node-title", "N", "--owner-role", "cos",
                "--verifier-role", "auditor", "--actor", "cos")
        assert c.returncode == 0, c.stderr
        return json.loads(c.stdout)["nodes"][0]["node_id"]

    return make


def _complete(org, node_id, *extra):
    return org("missions", "complete", node_id, "--verified-value", "12",
               "--verification-summary", "s", *extra)


# ---------------------------------------------------------------------------
# The three decisive refusals
# ---------------------------------------------------------------------------

def test_owner_cannot_verify_its_own_work(org, node):
    """THE defect. `cos` owns the node; `cos` must not be able to verify it."""
    r = _complete(org, node(), "--actor", "cos")
    assert r.returncode != 0, (
        "self-verification succeeded: the officer that did the work marked "
        f"it verified.\nstdout={r.stdout}"
    )
    assert "separation of duties" in (r.stderr + r.stdout).lower()


def test_nonexistent_actor_is_refused(org, node):
    """An actor naming a role that does not exist was accepted verbatim."""
    r = _complete(org, node(), "--actor", "totally-fake-role-does-not-exist")
    assert r.returncode != 0, f"ghost verifier accepted.\nstdout={r.stdout}"
    assert "unknown role" in (r.stderr + r.stdout).lower()


def test_unattributed_verification_is_refused(org, node):
    """--actor had a default of "cos"; an unattributed verification must fail
    rather than silently attribute itself to an officer."""
    r = _complete(org, node())
    assert r.returncode != 0, f"unattributed verification accepted.\nstdout={r.stdout}"
    assert "--actor" in (r.stderr + r.stdout)


def test_actor_other_than_the_named_verifier_is_refused(org, node):
    """Not the owner, but not the declared verifier either."""
    _role(org, "bystander")
    r = _complete(org, node(), "--actor", "bystander")
    assert r.returncode != 0, f"wrong verifier accepted.\nstdout={r.stdout}"
    assert "separation of duties" in (r.stderr + r.stdout).lower()


# ---------------------------------------------------------------------------
# Non-vacuity: the legitimate path must still work
# ---------------------------------------------------------------------------

def test_declared_verifier_succeeds_and_is_recorded(org, node):
    """No false positive — and the receipt names who verified, distinctly
    from who owned the work."""
    r = _complete(org, node(), "--actor", "auditor")
    assert r.returncode == 0, f"legitimate verification refused: {r.stderr}"
    assert json.loads(r.stdout)["verified_by"] == "auditor"


# ---------------------------------------------------------------------------
# Work must not be creatable in an unverifiable state
# ---------------------------------------------------------------------------

def test_legacy_node_without_verifier_role_is_still_completable(org, tmp_path):
    """Nodes created before --verifier-role existed carry verifier_role=''.

    Refusing those outright BRICKED them: there is no set-verifier subcommand
    and a recompile mints new ids, so the mission could never reach
    remaining==0. They degrade to the owner-only rule instead.
    """
    _role(org, "cos")
    _role(org, "auditor")
    r = org("outcomes", "propose", "--title", "t", "--metric-name", "m",
            "--target-value", "12", "--unit", "points", "--actor", "cos")
    outcome_id = json.loads(r.stdout)["outcome_id"]
    org("outcomes", "ratify", outcome_id, "--ratified-by", "captain", "--note", "n")

    # Simulate the pre-change compile: a node row with verifier_role = ''.
    c = org("missions", "compile", outcome_id, "--title", "T", "--node-title", "N",
            "--owner-role", "cos", "--verifier-role", "auditor", "--actor", "cos")
    node_id = json.loads(c.stdout)["nodes"][0]["node_id"]
    import sqlite3
    db = sqlite3.connect(tmp_path / "org.sqlite3")
    db.execute("UPDATE work_graph_nodes SET verifier_role='' WHERE node_id=?", (node_id,))
    db.commit(); db.close()

    # The owner still may not verify it...
    assert _complete(org, node_id, "--actor", "cos").returncode != 0
    # ...but an independent active role can, so the node is not stranded.
    ok = _complete(org, node_id, "--actor", "auditor")
    assert ok.returncode == 0, f"legacy node was bricked: {ok.stderr}"


def test_near_miss_case_of_the_owner_is_refused(org, node):
    """`Cos` must not sneak past a check the owner `cos` would fail."""
    r = _complete(org, node(), "--actor", "Cos")
    assert r.returncode != 0, f"case-variant self-verification accepted.\nstdout={r.stdout}"


def test_compile_requires_a_verifier_role(org):
    """`missions compile` used to INSERT nodes with no verifier_role at all,
    which is what made every node self-verifiable at completion."""
    _role(org, "cos")
    r = org("outcomes", "propose", "--title", "t", "--metric-name", "m",
            "--target-value", "12", "--unit", "points", "--actor", "cos")
    outcome_id = json.loads(r.stdout)["outcome_id"]
    org("outcomes", "ratify", outcome_id, "--ratified-by", "captain", "--note", "n")

    r = org("missions", "compile", outcome_id, "--title", "T",
            "--node-title", "N", "--owner-role", "cos", "--actor", "cos")
    assert r.returncode != 0, "compiled work with no verifier role"
    assert "--verifier-role" in (r.stderr + r.stdout)


def test_compile_refuses_owner_as_its_own_verifier(org):
    """Naming the owner as verifier is the same hole wearing a name."""
    _role(org, "cos")
    r = org("outcomes", "propose", "--title", "t", "--metric-name", "m",
            "--target-value", "12", "--unit", "points", "--actor", "cos")
    outcome_id = json.loads(r.stdout)["outcome_id"]
    org("outcomes", "ratify", outcome_id, "--ratified-by", "captain", "--note", "n")

    r = org("missions", "compile", outcome_id, "--title", "T",
            "--node-title", "N", "--owner-role", "cos",
            "--verifier-role", "cos", "--actor", "cos")
    assert r.returncode != 0, "compiled a node that verifies itself"
    assert "separation of duties" in (r.stderr + r.stdout).lower()
