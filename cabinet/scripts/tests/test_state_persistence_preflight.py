"""Tests for cabinet/scripts/state-persistence-preflight.py.

Every arm asserts the PROPERTY the checker exists to deliver — "would a deploy
lose this path?" — and every arm is proven in BOTH directions: the broken shape
must fail AND the correct shape must pass. An arm that only ever fails is not
evidence of anything.

The defect these tests pin: cabinet-deploy.sh provisions each release as a fresh
`git worktree`, so gitignored state exists only where runtime-provision.sh's
hand-maintained lists symlink it into shared/. Those lists drifted from
.gitignore and six durable paths were silently discarded on every deploy.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CHECKER = os.path.join(REPO, "cabinet", "scripts", "state-persistence-preflight.py")

# A minimal stand-in for runtime-provision.sh: the three list assignments plus
# the four wildcard-block probes the checker verifies still exist.
PROVISION_TEMPLATE = textwrap.dedent("""\
    #!/usr/bin/env bash
    INSTANCE_PERSISTENT_DIRS="{dirs}"
    INSTANCE_PERSISTENT_SEEDED_DIRS="{seeded}"
    INSTANCE_PERSISTENT_FILES="{files}"
    # wildcard blocks the checker probes for:
    #   for f in "$root/shared/instance/agents/"*-ceo.md
    #   for f in "$root/shared/".oauth-backup-*.json
    #   find "$root/shared/shared/interfaces" -type f -name '*.md'
    #   ln -sfn "$root/shared/cabinet.env" "$slot/cabinet/.env"
    """)


def build_repo(tmp_path, gitignore, *, dirs="instance/state", seeded="instance/memory",
               files="instance/config/posture.yml", policy="wildcard_covered: []\ndisposable: []\n",
               provision=None):
    """Write a synthetic repo the checker can be pointed at."""
    root = tmp_path / "repo"
    (root / "cabinet" / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "cabinet" / "config").mkdir(parents=True, exist_ok=True)
    (root / ".gitignore").write_text(gitignore, encoding="utf-8")
    (root / "cabinet" / "scripts" / "runtime-provision.sh").write_text(
        provision if provision is not None
        else PROVISION_TEMPLATE.format(dirs=dirs, seeded=seeded, files=files),
        encoding="utf-8")
    (root / "cabinet" / "config" / "state-persistence-policy.yml").write_text(
        policy, encoding="utf-8")
    return root


def run(root, *extra):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run(
        [sys.executable, CHECKER, "--repo", str(root), *extra],
        capture_output=True, text=True, env=env)


# ---- arm 1: a durable path on no list is DETECTED (both directions) --------

def test_durable_path_missing_from_every_list_is_detected(tmp_path):
    """The headline property. memory/tier3/ holds the decision log; it is
    gitignored, so a fresh worktree cannot contain it. On no list = lost."""
    root = build_repo(tmp_path, "memory/tier3/\n")
    res = run(root)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "memory/tier3" in res.stderr
    assert "DEPLOY WOULD LOSE STATE" in res.stderr


def test_same_path_passes_once_it_is_carried(tmp_path):
    """Opposite direction — proves the arm above is not simply always-fail."""
    root = build_repo(tmp_path, "memory/tier3/\n",
                      dirs="instance/state memory/tier3")
    res = run(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "no durable path would be lost" in res.stdout


def test_whole_directory_symlink_covers_paths_beneath_it(tmp_path):
    """A dir entry carries everything under it — otherwise every leaf would
    need its own row and the lists would drift again."""
    root = build_repo(tmp_path, "instance/state/officer/queue.jsonl\n",
                      dirs="instance/state")
    assert run(root).returncode == 0


def test_file_entry_does_not_cover_a_sibling(tmp_path):
    """A file entry carries exactly itself — the drift that caused this bug."""
    root = build_repo(tmp_path, "instance/config/posture.yml\ninstance/config/war-room-seed.yml\n",
                      files="instance/config/posture.yml")
    res = run(root)
    assert res.returncode == 1
    assert "instance/config/war-room-seed.yml" in res.stderr
    assert "instance/config/posture.yml" not in res.stderr


# ---- arm 2: a DISPOSABLE entry without a reason FAILS (both directions) ----

def test_disposable_without_reason_fails(tmp_path):
    root = build_repo(tmp_path, "node_modules/\n",
                      policy="wildcard_covered: []\ndisposable:\n  - path: node_modules/\n")
    res = run(root)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "no reason" in res.stderr
    assert "POLICY ERROR" in res.stderr


def test_disposable_with_empty_reason_fails(tmp_path):
    """Whitespace is not a reason."""
    root = build_repo(tmp_path, "node_modules/\n",
                      policy='wildcard_covered: []\ndisposable:\n  - path: node_modules/\n    reason: "   "\n')
    res = run(root)
    assert res.returncode == 1
    assert "no reason" in res.stderr


def test_disposable_with_reason_passes(tmp_path):
    root = build_repo(tmp_path, "node_modules/\n",
                      policy='wildcard_covered: []\ndisposable:\n  - path: node_modules/\n'
                             '    reason: "npm install regenerates it from package-lock.json"\n')
    res = run(root)
    assert res.returncode == 0, res.stdout + res.stderr


# ---- arm 3: fail-closed on facts the checker cannot establish --------------

def test_unparseable_persistence_list_fails_closed(tmp_path):
    """An unparseable list must never read as an empty list — that would
    certify a deploy that carries nothing at all."""
    root = build_repo(tmp_path, "memory/tier3/\n",
                      provision='#!/usr/bin/env bash\nRENAMED_DIRS="instance/state"\n')
    res = run(root)
    assert res.returncode == 2, res.stdout + res.stderr
    assert "CANNOT VERIFY" in res.stderr


def test_empty_persistence_list_fails_closed(tmp_path):
    root = build_repo(tmp_path, "memory/tier3/\n", dirs="")
    res = run(root)
    assert res.returncode == 2
    assert "EMPTY" in res.stderr


def test_missing_wildcard_block_fails_closed(tmp_path):
    """If a wildcard-linking block is deleted, coverage claims resting on it
    are stale — the checker must stop, not widen coverage silently."""
    provision = PROVISION_TEMPLATE.format(
        dirs="instance/state", seeded="instance/memory",
        files="instance/config/posture.yml").replace("*-ceo.md", "REMOVED")
    root = build_repo(tmp_path, "memory/tier3/\n", provision=provision)
    res = run(root)
    assert res.returncode == 2
    assert "wildcard rule" in res.stderr


def test_empty_gitignore_fails_closed(tmp_path):
    """No patterns means the derivation broke, not that nothing is durable."""
    root = build_repo(tmp_path, "# only a comment\n")
    res = run(root)
    assert res.returncode == 2


def test_unknown_wildcard_rule_name_is_rejected(tmp_path):
    root = build_repo(tmp_path, "instance/agents/*-ceo.md\n",
                      policy='wildcard_covered:\n  - path: instance/agents\n'
                             '    rule: not-a-real-rule\n    reason: "x"\ndisposable: []\n')
    res = run(root)
    assert res.returncode == 1
    assert "not a known" in res.stderr


def test_wildcard_covered_entry_passes_when_rule_is_real(tmp_path):
    root = build_repo(tmp_path, "instance/agents/*-ceo.md\n",
                      policy='wildcard_covered:\n  - path: instance/agents\n'
                             '    rule: agents-ceo-md\n'
                             '    reason: "linked by link_instance_data wildcard block"\ndisposable: []\n')
    assert run(root).returncode == 0


# ---- arm 3b: known_gap is time-boxed, never a permanent hole ---------------

def _gap_policy(expires):
    return ('wildcard_covered: []\ndisposable: []\nknown_gap:\n'
            '  - path: memory/tier3\n'
            '    reason: "carrying it would shadow a tracked file; needs a design call"\n'
            + (f'    expires: "{expires}"\n' if expires else ""))


def test_known_gap_without_expiry_fails(tmp_path):
    """An open data-loss gap may not be deferred forever."""
    root = build_repo(tmp_path, "memory/tier3/\n", policy=_gap_policy(None))
    res = run(root)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "expires" in res.stderr


def test_expired_known_gap_fails(tmp_path):
    root = build_repo(tmp_path, "memory/tier3/\n", policy=_gap_policy("2000-01-01"))
    res = run(root)
    assert res.returncode == 1
    assert "EXPIRED" in res.stderr


def test_unexpired_known_gap_passes_but_is_reported(tmp_path):
    """Opposite direction — and it must stay VISIBLE, not silent."""
    root = build_repo(tmp_path, "memory/tier3/\n", policy=_gap_policy("2999-01-01"))
    res = run(root)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "KNOWN GAP" in res.stdout
    assert "memory/tier3" in res.stdout


def test_known_gap_without_reason_fails(tmp_path):
    root = build_repo(tmp_path, "memory/tier3/\n",
                      policy='wildcard_covered: []\ndisposable: []\nknown_gap:\n'
                             '  - path: memory/tier3\n    expires: "2999-01-01"\n')
    res = run(root)
    assert res.returncode == 1
    assert "no reason" in res.stderr


def test_real_policy_has_no_expired_gaps():
    """The live policy must not be carrying a lapsed deferral."""
    res = run(REPO)
    assert "EXPIRED" not in res.stderr, res.stderr


# ---- arm 4: slot mode — the deploy-time property, on a REAL release --------

def test_slot_mode_flags_a_listed_path_that_is_not_actually_linked(tmp_path):
    """The list can say a path is carried while the linking never happened.
    Slot mode asserts against the provisioned release itself."""
    root = build_repo(tmp_path, "instance/state/\n", dirs="instance/state")
    slot, shared = tmp_path / "slot", tmp_path / "shared"
    (slot / "instance" / "state").mkdir(parents=True)   # a real dir IN the release
    (slot / "instance" / "state" / "queue.jsonl").write_text("{}\n", encoding="utf-8")
    shared.mkdir()
    res = run(root, "--slot", str(slot), "--shared", str(shared))
    assert res.returncode == 1, res.stdout + res.stderr
    assert "the next deploy discards it" in res.stderr


def test_slot_mode_passes_when_the_path_is_symlinked_into_shared(tmp_path):
    """Opposite direction: a properly symlinked path passes."""
    root = build_repo(tmp_path, "instance/state/\n", dirs="instance/state")
    slot, shared = tmp_path / "slot", tmp_path / "shared"
    (slot / "instance").mkdir(parents=True)
    (shared / "instance" / "state").mkdir(parents=True)
    (shared / "instance" / "state" / "queue.jsonl").write_text("{}\n", encoding="utf-8")
    os.symlink(shared / "instance" / "state", slot / "instance" / "state")
    res = run(root, "--slot", str(slot), "--shared", str(shared))
    assert res.returncode == 0, res.stdout + res.stderr


def test_slot_mode_flags_a_symlink_pointing_outside_the_shared_tree(tmp_path):
    """A link into the release (or anywhere else) is not persistence."""
    root = build_repo(tmp_path, "instance/state/\n", dirs="instance/state")
    slot, shared, elsewhere = tmp_path / "slot", tmp_path / "shared", tmp_path / "elsewhere"
    (slot / "instance").mkdir(parents=True)
    shared.mkdir()
    elsewhere.mkdir()
    os.symlink(elsewhere, slot / "instance" / "state")
    res = run(root, "--slot", str(slot), "--shared", str(shared))
    assert res.returncode == 1
    assert "OUTSIDE the shared tree" in res.stderr


def test_slot_mode_requires_shared(tmp_path):
    root = build_repo(tmp_path, "instance/state/\n", dirs="instance/state")
    res = run(root, "--slot", str(tmp_path))
    assert res.returncode == 2


# ---- arm 4b: adoption — listing a FILE must actually make it persist -------
# Measured 2026-07-25: adding a path to INSTANCE_PERSISTENT_FILES did NOT make
# it persist. A file created at runtime lives in the live release, never in
# shared/, so the `[ -e "$shared_abs" ] || continue` guard skipped it forever
# and every deploy discarded it again. These arms drive the REAL script.

PROVISION = os.path.join(REPO, "cabinet", "scripts", "runtime-provision.sh")


def _runtime_root(tmp_path, tracked: bool):
    """Build a real git repo + runtime root, run two real provisions."""
    src = tmp_path / "src"
    (src / "instance" / "config").mkdir(parents=True)
    (src / "README.md").write_text("seed\n", encoding="utf-8")
    if tracked:
        (src / "instance" / "config" / "trusted-mcps.json").write_text(
            "TRACKED-RELEASE-COPY\n", encoding="utf-8")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(src)], check=True)
    subprocess.run(git + ["-C", str(src), "add", "-A"], check=True)
    subprocess.run(git + ["-C", str(src), "commit", "-qm", "one"], check=True)
    subprocess.run(git + ["-C", str(src), "commit", "-qm", "two", "--allow-empty"], check=True)
    shas = subprocess.run(["git", "-C", str(src), "log", "--format=%H"],
                          capture_output=True, text=True, check=True).stdout.split()
    sha_b, sha_a = shas[0], shas[1]
    root = tmp_path / "rt"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(["bash", PROVISION, "init", str(root), "--remote", str(src)],
                   capture_output=True, env=env)
    subprocess.run(["bash", PROVISION, "provision", str(root), sha_a],
                   capture_output=True, env=env, check=True)
    # the cabinet writes the config at RUNTIME, inside the live release
    live_cfg = root / "releases" / sha_a / "instance" / "config"
    live_cfg.mkdir(parents=True, exist_ok=True)
    (live_cfg / "trusted-mcps.json").write_text(
        "RUNTIME-VALUE\n", encoding="utf-8")
    subprocess.run(["bash", PROVISION, "promote", str(root), sha_a],
                   capture_output=True, env=env, check=True)
    subprocess.run(["bash", PROVISION, "provision", str(root), sha_b],
                   capture_output=True, env=env, check=True)
    return root / "releases" / sha_b / "instance" / "config" / "trusted-mcps.json"


def test_runtime_created_config_is_adopted_and_survives_the_next_deploy(tmp_path):
    """The property: would a deploy lose this? It must not."""
    landed = _runtime_root(tmp_path, tracked=False)
    assert landed.exists(), "the runtime-written config was LOST by the next deploy"
    assert landed.read_text() == "RUNTIME-VALUE\n"
    assert landed.is_symlink(), "it must be a symlink into shared/, not a fresh copy"


def test_adoption_never_shadows_a_git_tracked_file(tmp_path):
    """Opposite direction. Adopting a TRACKED file would freeze a snapshot over
    the release's own copy — the deployment-status.md hazard. Must not fire."""
    landed = _runtime_root(tmp_path, tracked=True)
    assert not landed.is_symlink(), "a tracked file must never be shadowed by shared/"
    # The release keeps its OWN tracked bytes — that is the point of the guard.
    assert landed.read_text() == "TRACKED-RELEASE-COPY\n"


# ---- arm 5: the live anti-drift gate --------------------------------------

def test_real_repo_accounts_for_every_durable_path():
    """THE regression gate. If someone adds a .gitignore entry without either
    carrying it or declaring it disposable-with-a-reason, this goes red — which
    is exactly the drift that silently discarded ratified Captain rules, the
    tier-3 decision log, the tool-call log and the foundry archive."""
    res = run(REPO)
    assert res.returncode == 0, (
        "state-persistence-preflight failed against the real repo — a deploy "
        "would lose the paths listed below.\n" + res.stdout + res.stderr)


def test_real_repo_carries_the_paths_this_bug_was_about():
    """Explicit pins so a future edit cannot quietly drop them again."""
    provision = open(
        os.path.join(REPO, "cabinet", "scripts", "runtime-provision.sh"),
        encoding="utf-8").read()
    for path in ("memory/skills/evolved", "memory/tier3", "memory/logs",
                 "shared/interfaces/foundry", "instance/config/trusted-mcps.json",
                 "instance/config/war-room-seed.yml"):
        assert path in provision, f"{path} is no longer carried across deploys"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
