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

import importlib.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
CHECKER = os.path.join(REPO, "cabinet", "scripts", "state-persistence-preflight.py")


def _load_checker():
    """Import the checker as a module so tests can assert its PARSED output
    instead of grepping shell text."""
    spec = importlib.util.spec_from_file_location("_spp_under_test", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

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


def test_slot_mode_does_not_flag_a_path_nothing_has_written_yet(tmp_path):
    """The question is 'would a deploy LOSE this', so absence is not loss.
    Several list entries are legitimately absent until the cabinet first
    creates them; flagging those would make every deploy fail for no reason."""
    root = build_repo(tmp_path, "instance/state/\n", dirs="instance/state")
    slot, shared = tmp_path / "slot", tmp_path / "shared"
    (slot / "instance").mkdir(parents=True)   # parent exists, the path does not
    shared.mkdir()
    res = run(root, "--slot", str(slot), "--shared", str(shared))
    assert res.returncode == 0, res.stdout + res.stderr


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


# ---- arm 4c: the SAME property, for a runtime-created DIRECTORY ------------
# Measured 2026-07-25: the adoption pass added above was wired into the FILES
# loop ONLY. INSTANCE_PERSISTENT_DIRS and INSTANCE_PERSISTENT_SEEDED_DIRS had
# none — they mkdir'd an EMPTY shared/ directory, symlinked the new release at
# it, and left the real data in the outgoing release for `prune` to delete.
# 9 of 13 durable paths were lost on a real deploy while the preflight printed
# "OK — no durable path would be lost" and exited 0.


def _build_src(tmp_path):
    """A tiny real git repo with two commits and a tracked memory/tier3
    skeleton (the SEEDED class's defining shape)."""
    src = tmp_path / "src"
    (src / "instance" / "config").mkdir(parents=True)
    (src / "memory" / "tier3").mkdir(parents=True)
    (src / "memory" / "tier3" / ".gitkeep").write_text("", encoding="utf-8")
    (src / "README.md").write_text("seed\n", encoding="utf-8")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q", str(src)], check=True)
    subprocess.run(git + ["-C", str(src), "add", "-A"], check=True)
    subprocess.run(git + ["-C", str(src), "commit", "-qm", "one"], check=True)
    subprocess.run(git + ["-C", str(src), "commit", "-qm", "two", "--allow-empty"],
                   check=True)
    shas = subprocess.run(["git", "-C", str(src), "log", "--format=%H"],
                          capture_output=True, text=True, check=True).stdout.split()
    return src, shas[1], shas[0]          # sha_a (live), sha_b (being deployed)


def _materialize_real(base: Path, rel: str) -> Path:
    """Force <base>/<rel>'s ancestors to be REAL directories.

    This is the on-disk shape of a release provisioned BEFORE the path joined a
    persistence list — which is every live release at the moment such an entry
    is added, and therefore the only shape in which the bug can be observed. If
    the fixture let the parent stay a symlink into shared/, the write would land
    in shared/ and survive trivially, proving nothing."""
    cur = base
    for part in Path(rel).parts[:-1]:
        cur = cur / part
        if cur.is_symlink():
            cur.unlink()
        cur.mkdir(parents=True, exist_ok=True)
    return base / rel


def _runtime_with_live_state(tmp_path, writes: dict):
    """Provision + promote release A, then plant runtime state in it as REAL
    files/directories. Returns (root, live_release, sha_a, sha_b)."""
    src, sha_a, sha_b = _build_src(tmp_path)
    root = tmp_path / "rt"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(["bash", PROVISION, "init", str(root), "--remote", str(src)],
                   capture_output=True, env=env)
    for action in (["provision", str(root), sha_a], ["promote", str(root), sha_a]):
        subprocess.run(["bash", PROVISION, *action], capture_output=True,
                       env=env, check=True)
    live = root / "releases" / sha_a
    for rel, payload in writes.items():
        _materialize_real(live, rel).write_text(payload, encoding="utf-8")
    return root, live, sha_a, sha_b


def _provision(root, sha):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(["bash", PROVISION, "provision", str(root), sha],
                   capture_output=True, env=env, check=True)
    return root / "releases" / sha


def _resolves_into_shared(path: Path, root: Path) -> bool:
    return os.path.realpath(path).startswith(
        os.path.realpath(root / "shared") + os.sep)


def test_runtime_created_directory_is_adopted_and_survives_the_next_deploy(tmp_path):
    """The DIRS-class twin of the FILES arm above. instance/state is an
    INSTANCE_PERSISTENT_DIRS entry; a queue an officer wrote into it must reach
    the next release."""
    rel = "instance/state/officer-queue.jsonl"
    root, _live, _a, sha_b = _runtime_with_live_state(tmp_path, {rel: "QUEUED\n"})
    landed = _provision(root, sha_b) / rel
    assert landed.exists(), "the runtime-written directory state was LOST by the next deploy"
    assert landed.read_text() == "QUEUED\n"
    assert _resolves_into_shared(landed, root), \
        "it must resolve into shared/, not be a fresh copy the next deploy loses again"


def test_runtime_created_seeded_directory_beats_the_tracked_skeleton(tmp_path):
    """SEEDED-class twin. Adoption must run BEFORE the `.gitkeep` seed, or the
    skeleton wins the race and the real decision log is discarded."""
    rel = "memory/tier3/decisions/dec-0001.md"
    root, _live, _a, sha_b = _runtime_with_live_state(tmp_path, {rel: "# adopt X\n"})
    new = _provision(root, sha_b)
    assert (new / rel).exists(), "tier-3 decision log LOST by the next deploy"
    assert (new / rel).read_text() == "# adopt X\n"
    assert _resolves_into_shared(new / rel, root)
    # the tracked skeleton still seeds — adoption must not displace it
    assert (new / "memory" / "tier3" / ".gitkeep").exists()


def test_runtime_created_interfaces_md_is_adopted_by_the_wildcard(tmp_path):
    """The *.md wildcard twin. shared/interfaces/**/*.md is claimed by the
    policy's `interfaces-md` row, but the block discovers from
    <root>/shared/shared/interfaces/ and NOTHING seeded that — so the
    append-only Captain-law ledgers were certified as covered and lost."""
    rel = "shared/interfaces/captain-decisions.md"
    root, _live, _a, sha_b = _runtime_with_live_state(tmp_path, {rel: "# D99\n"})
    landed = _provision(root, sha_b) / rel
    assert landed.exists(), "the Captain-law ledger was LOST by the next deploy"
    assert landed.read_text() == "# D99\n"
    assert _resolves_into_shared(landed, root)


def test_a_same_sha_redeploy_does_not_destroy_the_live_release(tmp_path):
    """DEFECT 2, the destructive one. cmd_provision reuses a slot BY SHA, so a
    routine redeploy with no new commits — or a retry after a failed health
    gate — runs link_instance_data against the LIVE release, where the DIRS
    loop's unconditional `rm -rf` deleted real data outright. The preflight
    cannot protect against this even in principle: provision runs BEFORE it."""
    rel = "shared/interfaces/foundry/traj-0001.jsonl"
    root, live, sha_a, _b = _runtime_with_live_state(tmp_path, {rel: "SEALED\n"})
    _provision(root, sha_a)                     # the SAME sha that is live
    assert (live / rel).exists(), \
        "the live release's sealed trajectory archive was DESTROYED IN PLACE"
    assert (live / rel).read_text() == "SEALED\n"
    assert _resolves_into_shared(live / rel, root)


def test_repeated_provisions_are_idempotent_and_never_lose_the_state(tmp_path):
    """Opposite direction for the arm above, and the property that makes the
    adoption safe to run unconditionally: provisioning again must be a no-op."""
    rel = "instance/state/officer-queue.jsonl"
    root, _live, sha_a, sha_b = _runtime_with_live_state(tmp_path, {rel: "QUEUED\n"})
    for sha in (sha_b, sha_a, sha_b, sha_b):
        new = _provision(root, sha)
        assert (new / rel).read_text() == "QUEUED\n", f"state lost re-provisioning {sha}"


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the write permissions this arm relies on")
def test_a_failed_adoption_aborts_instead_of_deleting_the_only_copy(tmp_path):
    """The ADOPTION INVARIANT's own failure mode. If the copy into shared/ does
    not succeed, continuing to the `rm -rf` would destroy the only copy — a
    swallowed `cp ... || true` would have reintroduced this whole bug quietly.
    The provision must fail loudly and the live release must be untouched."""
    rel = "instance/state/officer-queue.jsonl"
    root, live, _a, sha_b = _runtime_with_live_state(tmp_path, {rel: "QUEUED\n"})
    # The destination itself, not its parent: the first provision already
    # created shared/instance/state, so an unwritable PARENT would not stop a
    # write into the existing child.
    blocked = root / "shared" / "instance" / "state"
    blocked.mkdir(parents=True, exist_ok=True)
    blocked.chmod(0o500)                       # read+execute, NOT writable
    try:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        res = subprocess.run(["bash", PROVISION, "provision", str(root), sha_b],
                             capture_output=True, text=True, env=env)
        assert res.returncode != 0, "a failed adoption must abort the provision"
        assert "FATAL" in res.stderr
    finally:
        blocked.chmod(0o755)
    assert (live / rel).read_text() == "QUEUED\n", \
        "the live release was modified despite the adoption failing"


# ---- arm 4d: the outgoing-release arm — the property check_slot never asked --


def _slot_and_current(tmp_path, *, shared_has_it: bool):
    """A new slot symlinked at shared/ (as the provisioner leaves it) plus an
    outgoing release holding the real data."""
    slot, shared, current = tmp_path / "slot", tmp_path / "shared", tmp_path / "cur"
    (slot / "instance").mkdir(parents=True)
    (shared / "instance" / "state").mkdir(parents=True)
    os.symlink(shared / "instance" / "state", slot / "instance" / "state")
    (current / "instance" / "state").mkdir(parents=True)
    (current / "instance" / "state" / "queue.jsonl").write_text("Q\n", encoding="utf-8")
    if shared_has_it:
        (shared / "instance" / "state" / "queue.jsonl").write_text("Q\n", encoding="utf-8")
    return slot, shared, current


def test_outgoing_arm_flags_state_stranded_in_the_live_release(tmp_path):
    """The headline miss. Every list said instance/state was carried and the new
    slot did resolve into shared/ — but shared/ was EMPTY and the data was still
    in the outgoing release, which `prune` deletes. Old checker: exit 0."""
    root = build_repo(tmp_path, "instance/state/\n", dirs="instance/state")
    slot, shared, current = _slot_and_current(tmp_path, shared_has_it=False)
    res = run(root, "--slot", str(slot), "--shared", str(shared),
              "--current", str(current))
    assert res.returncode == 1, res.stdout + res.stderr
    assert "OUTGOING release" in res.stderr
    assert "queue.jsonl" in res.stderr


def test_outgoing_arm_passes_once_the_state_reached_shared(tmp_path):
    """Opposite direction — proves the arm is not simply always-fail."""
    root = build_repo(tmp_path, "instance/state/\n", dirs="instance/state")
    slot, shared, current = _slot_and_current(tmp_path, shared_has_it=True)
    res = run(root, "--slot", str(slot), "--shared", str(shared),
              "--current", str(current))
    assert res.returncode == 0, res.stdout + res.stderr


def test_outgoing_arm_ignores_tracked_files(tmp_path):
    """A TRACKED file in the outgoing release is checked out fresh into the new
    release by git itself. Flagging it would make every deploy fail forever."""
    root = build_repo(tmp_path, "instance/state/\n", dirs="instance/state")
    slot, shared, current = _slot_and_current(tmp_path, shared_has_it=False)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(current)]
    subprocess.run(["git", "init", "-q", str(current)], check=True)
    subprocess.run(git + ["add", "-Af"], check=True)
    subprocess.run(git + ["commit", "-qm", "tracked"], check=True)
    res = run(root, "--slot", str(slot), "--shared", str(shared),
              "--current", str(current))
    assert res.returncode == 0, res.stdout + res.stderr


# ---- arm 4e: expiry is blocking in CI, loud but non-bricking at deploy time --


def test_expired_known_gap_does_not_brick_a_deploy(tmp_path):
    """cabinet-deploy.sh aborts on ANY non-zero exit, so a blocking expiry makes
    every `expires:` date a scheduled hard-stop of the whole deploy path. The
    gap describes a path that was already uncarried yesterday; refusing to
    deploy does not carry it. Still LOUD — see the assertion on stderr."""
    root = build_repo(tmp_path, "memory/tier3/\n", policy=_gap_policy("2000-01-01"))
    slot, shared = tmp_path / "slot", tmp_path / "shared"
    slot.mkdir()
    shared.mkdir()
    res = run(root, "--slot", str(slot), "--shared", str(shared))
    assert res.returncode == 0, res.stdout + res.stderr
    assert "EXPIRED" in res.stderr
    # ...and the CI arm above (test_expired_known_gap_fails) still blocks at
    # review time, which is where a deferral actually gets renewed.


# ---- arm 4f: a missing dependency must not read as a data-loss finding ------


def test_missing_pyyaml_reports_a_dependency_failure_not_data_loss(tmp_path):
    """Deploy runs this under /opt/homebrew/bin/python3.12, which is not
    necessarily the interpreter PyYAML was installed into. The bare ImportError
    surfaced as 'this release would DISCARD durable state'."""
    root = build_repo(tmp_path, "memory/tier3/\n", dirs="instance/state memory/tier3")
    shim = tmp_path / "shim" / "yaml"
    shim.mkdir(parents=True)
    (shim / "__init__.py").write_text(
        "raise ImportError('shimmed out for the test')\n", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=str(tmp_path / "shim"),
               PYTHONDONTWRITEBYTECODE="1")
    res = subprocess.run([sys.executable, CHECKER, "--repo", str(root)],
                         capture_output=True, text=True, env=env)
    assert res.returncode == 2, res.stdout + res.stderr
    assert "PyYAML is not importable" in res.stderr
    assert "MISSING DEPENDENCY" in res.stderr
    assert "DISCARD" not in res.stderr


def test_the_same_repo_passes_with_pyyaml_present(tmp_path):
    """Opposite direction: the shim, not the fixture, is what fails it."""
    root = build_repo(tmp_path, "memory/tier3/\n", dirs="instance/state memory/tier3")
    assert run(root).returncode == 0


# ---- arm 4g: prune must not truncate a runtime root containing a space ------


def test_prune_handles_a_runtime_root_containing_a_space(tmp_path):
    """`awk '{print $2}'` truncated the path at the first space and handed the
    truncated prefix to `rm -rf`. Not merely cosmetic: prune deletes worktrees."""
    src, sha_a, sha_b = _build_src(tmp_path)
    root = tmp_path / "run time"                     # the space is the point
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(["bash", PROVISION, "init", str(root), "--remote", str(src)],
                   capture_output=True, env=env)
    for action in (["provision", str(root), sha_a], ["provision", str(root), sha_b],
                   ["promote", str(root), sha_a]):
        subprocess.run(["bash", PROVISION, *action], capture_output=True,
                       env=env, check=True)
    subprocess.run(["bash", PROVISION, "prune", str(root), "--keep", "0"],
                   capture_output=True, env=env, check=True)
    assert not (root / "releases" / sha_b).exists(), \
        "prune silently pruned nothing — the path was truncated at the space"
    assert (root / "releases" / sha_a).exists(), "prune deleted the LIVE release"


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
    """Explicit pins so a future edit cannot quietly drop them again.

    Asserts the PARSED lists, not the file text. The substring form this
    replaced was a rubber stamp: every one of these paths is also named in
    runtime-provision.sh's own explanatory comments, so deleting a path from the
    list while leaving the comment behind kept the pin green while the path
    stopped being carried."""
    spp = _load_checker()
    lists = spp.parse_persistence_lists(
        os.path.join(REPO, "cabinet", "scripts", "runtime-provision.sh"))
    entries = {e for group in lists.values() for e in group}
    for path in ("memory/skills/evolved", "memory/tier3", "memory/logs",
                 "shared/interfaces/foundry", "instance/config/trusted-mcps.json",
                 "instance/config/war-room-seed.yml"):
        assert path in entries, (
            f"{path} is on no persistence list — it is no longer carried across "
            f"deploys (a mention in a comment does not carry anything)")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
