"""Tests for cabinet/scripts/egg-export.sh + egg-publish-gate.sh (PC-C).

The egg is a FRESH-CUT export from git HEAD — never this repo flipped (git
history carries personal/employer data). These tests run ONE real export of
THIS repo into a pytest tmp dir and pin the packaging contract row by row
(operative-egg ledger: R059 R088 R116 R120 R122 R123 R124 R125 R126 R127
R128 R145 R159), plus the exporter's output-dir safety refusals and the
publish gate's fail-closed refusals and gate (d) masking semantics.

Pure-local by construction: `git archive HEAD` + file transforms — no
network, no gitleaks dependency (the REAL export's full gate run stays a
manual/Captain step; the gate tests here run against a tiny PLANTED fake
export whose verdict is RED regardless of whether gitleaks is installed).
Every subprocess uses a fixed argv and an explicit timeout (the full-export
runs get 300s — the cut itself takes seconds; the margin is for cold CI
runners).

Run: python3.12 -m pytest cabinet/scripts/tests/test_egg_export.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_EXPORT_SH = _SCRIPTS_DIR / "egg-export.sh"
_GATE_SH = _SCRIPTS_DIR / "egg-publish-gate.sh"
_MANIFEST = _SCRIPTS_DIR / "egg-export-manifest.txt"

_EXPORT_TIMEOUT = 300  # full archive cut + transform pass; seconds

# what may exist under instance/ in a valid egg (mirrors t_instance_verify)
_INSTANCE_ALLOWED = (
    lambda rel: rel.endswith(".example")
    or rel.endswith("/.gitkeep")
    or rel == "instance/config/contexts/_default.yml"
    or rel == "instance/config/projects/_template.yml"
    or rel == "instance/config/act-first-surfaces.yml"  # R126: materialized from the twin
    or rel == "instance/config/egress.yml"  # gate-b fix: materialized from the twin
    or rel.startswith("instance/config/policies/")
    or rel.startswith("instance/config/posture-presets/")
    or rel == "instance/officer-skills/README.md"
)


def _run_export(out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_EXPORT_SH), "--out", str(out), *extra],
        cwd=_REPO_ROOT, capture_output=True, text=True, timeout=_EXPORT_TIMEOUT,
    )


def _run_gate(*args: str, patterns_file: Path | None = None) -> subprocess.CompletedProcess:
    """Run the gate; `patterns_file` rides the EGG_GATE_PATTERNS_FILE test
    seam (R166) so gate (d) scans a SYNTHETIC suite — hermetic on machines
    with AND without a real instance/config/publish-scan-patterns.local."""
    env = dict(os.environ)
    if patterns_file is not None:
        env["EGG_GATE_PATTERNS_FILE"] = str(patterns_file)
    return subprocess.run(
        ["bash", str(_GATE_SH), *args],
        cwd=_REPO_ROOT, capture_output=True, text=True, timeout=60, env=env,
    )


# The synthetic gate-(d) fixture suite (R166): every token is a nonsense
# qz* placeholder — no real name/employer/product value may appear in this
# tracked test source. Shape mirrors a real captain file: sub tokens, a
# word token + its hostname-possessive twin, a colleague token, and one
# adjudicated allow entry (row id synthetic too).
_SYN_PATTERNS = (
    "# synthetic fixture suite (test-only)\n"
    "pattern sub:qzemployer\n"
    "pattern sub:qzhandle\n"
    "pattern sub:qzcolleague\n"
    "pattern word:qzcaptain\n"
    "pattern word:qzcaptains\n"
    "allow QZ-1 qzhandle/qz-cabinet\n"
)


def _mk_patterns_file(tmp_path: Path, content: str = _SYN_PATTERNS) -> Path:
    f = tmp_path / "publish-scan-patterns.fixture"
    f.write_text(content, encoding="utf-8")
    return f


def _head_commit() -> str:
    return subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout.strip()


@pytest.fixture(scope="module")
def export(tmp_path_factory) -> Path:
    """One real export of this repo's HEAD, shared by the assertion tests."""
    out = tmp_path_factory.mktemp("egg") / "export"
    proc = _run_export(out)
    assert proc.returncode == 0, (
        f"egg-export.sh failed rc={proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "verify        : PASS" in proc.stdout, proc.stdout
    return out


# ---------------------------------------------------------------------------
# Syntax — bash -n clean on both scripts
# ---------------------------------------------------------------------------

def test_bash_syntax_clean():
    for script in (_EXPORT_SH, _GATE_SH):
        p = subprocess.run(["bash", "-n", str(script)],
                           capture_output=True, text=True, timeout=30)
        assert p.returncode == 0, f"bash -n failed for {script}: {p.stderr}"


def test_manifest_is_tracked_next_to_the_exporter():
    assert _MANIFEST.is_file(), "egg-export-manifest.txt must live in cabinet/scripts/"
    text = _MANIFEST.read_text(encoding="utf-8")
    # the R116 packaging-manifest rule is encoded here (the row's claimed
    # artifact did not exist — this file is it)
    for row in ("R059", "R088", "R116", "R120", "R122", "R123", "R124",
                "R125", "R126", "R127", "R128", "R145", "R159"):
        assert row in text, f"manifest must cite ledger row {row}"


# ---------------------------------------------------------------------------
# The exclusion contract, row by row
# ---------------------------------------------------------------------------

def test_git_absent(export: Path):
    assert not (export / ".git").exists(), ".git must never ship (fresh cut, not a repo flip)"


def test_flavor_a_absent(export: Path):
    assert not (export / "instance" / "flavor-a").exists(), "R127: flavor-a is the personal-source pack"


def test_agents_dir_absent(export: Path):
    assert not (export / "instance" / "agents").exists(), "R128: instance/agents leaves"
    assert (export / "cabinet" / "mcp-overlays" / "cua-driver.mcp.json").is_file(), \
        "R128 pair: the cua-driver template home must ship"


def test_live_values_absent_example_twins_present(export: Path):
    cfg = export / "instance" / "config"
    # NB: egress.yml is deliberately absent from this tuple — like
    # act-first-surfaces.yml, it IS present in the export, but only ever as
    # the materialized .example twin (see test_egress_default_is_the_scrubbed_twin),
    # never the live ruled value. That distinction gets its own test.
    for live in ("platform.yml", "sources.yml", "directions.yml", "peers.yml",
                 "officer-emails.yml", "probes.yml", "warrooms.yml",
                 "outcomes.yml", "hq-instance.yml.draft",
                 "authority-enforcing"):
        assert not (cfg / live).exists(), f"R120: live {live} must not ship"
    for twin in ("platform.yml.example", "sources.yml.example",
                 "directions.yml.example", "peers.yml.example",
                 "officer-emails.yml.example", "probes.yml.example",
                 "warrooms.yml.example", "roster.yml.example",
                 "egress.yml.example",
                 "publish-scan-patterns.local.example",
                 "role-registry.md.example"):
        assert (cfg / twin).is_file(), f"R120/R166: {twin} must ship"


def test_act_first_default_is_the_scrubbed_twin(export: Path):
    """R126 + germline lockstep: the shipped act-first-surfaces.yml must be
    BYTE-IDENTICAL to its .example twin (empty lists, unratified) — never the
    live ruled file."""
    shipped = (export / "instance/config/act-first-surfaces.yml").read_bytes()
    twin = (export / "instance/config/act-first-surfaces.yml.example").read_bytes()
    assert shipped == twin
    assert b"status: unratified" in shipped


def test_egress_default_is_the_scrubbed_twin(export: Path):
    """R120/R126-class + germline lockstep (gate-b null-hatch fix): the
    shipped egress.yml must be BYTE-IDENTICAL to its .example twin (enforce:
    true, empty allow_hosts — already fail-closed by the twin's own doc
    contract) — never the live enforced-egress ruling."""
    shipped = (export / "instance/config/egress.yml").read_bytes()
    twin = (export / "instance/config/egress.yml.example").read_bytes()
    assert shipped == twin
    assert b"enforce: true" in shipped


def test_instance_contains_only_examples_and_structure(export: Path):
    offenders = []
    for p in sorted((export / "instance").rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(export).as_posix()
        if not _INSTANCE_ALLOWED(rel):
            offenders.append(rel)
    assert not offenders, f"live instance files survived the pass: {offenders}"


def test_private_checkpoint_reviews_do_not_ship(export: Path):
    reviews = export / "shared/interfaces/reviews"
    assert reviews.is_dir()
    assert sorted(p.name for p in reviews.iterdir()) == [".gitkeep"]


def test_contexts_and_projects_pruned(export: Path):
    contexts = sorted(f.name for f in (export / "instance/config/contexts").iterdir())
    assert contexts == [
        "_default.yml", "bakery-site.yml.example", "newsletter.yml.example",
    ], (
        "R124 + Wave G: _default.yml plus the Testburg lane-declaration "
        f".example twins stay (live lane contexts never ship), got {contexts}"
    )
    projects = sorted(f.name for f in (export / "instance/config/projects").iterdir())
    assert projects == ["_template.yml"], f"R125: only _template.yml stays, got {projects}"
    skills = sorted(f.name for f in (export / "instance/officer-skills").iterdir())
    assert skills == ["README.md"], f"live officer skills must leave, got {skills}"


def test_interfaces_header_contract(export: Path):
    idx = (export / "shared/interfaces/captain-rules-index.yaml").read_text(encoding="utf-8")
    assert idx.startswith("# captain-rules-index.yaml"), "header must survive"
    assert "entries: []" in idx, "R116: index ships with zero entries"
    assert "# 0 entries" in idx
    assert "trigger_words" not in idx, "R116: captain rule content must not ship"
    vetoes = (export / "shared/interfaces/captain-vetoes.yml").read_text(encoding="utf-8")
    assert "vetoes: []" in vetoes and "next_id: 1" in vetoes, "R116: empty veto registry"
    knowledge = (export / "shared/interfaces/captain-knowledge-classification.yml").read_text(encoding="utf-8")
    assert "{ date:" not in knowledge, "R116: classification rows must not ship"
    # the full shipped interface set, nothing more (fail-closed R116)
    shipped = sorted(
        p.relative_to(export).as_posix()
        for p in (export / "shared/interfaces").rglob("*") if p.is_file()
    )
    assert shipped == [
        "shared/interfaces/captain-knowledge-classification.yml",
        "shared/interfaces/captain-rules-index.yaml",
        "shared/interfaces/captain-vetoes.yml",
        "shared/interfaces/deployment-status.md",
        "shared/interfaces/product-specs/.gitkeep",
        "shared/interfaces/research-briefs/.gitkeep",
        "shared/interfaces/reviews/.gitkeep",
    ], shipped


def test_plans_archived_with_stub(export: Path):
    plans = export / "docs" / "plans"
    assert (plans / "ARCHIVED-NOTE.md").is_file(), "R145: archived stub must ship"
    for gone in ("operative-egg-plan-2026-07-07.md",
                 "operative-egg-ledger-2026-07-07.yml",
                 "EXECUTION-STATUS.md", "proofs",
                 "de-nate-foundation-2026-07-05.md"):
        assert not (plans / gone).exists(), f"R145: {gone} must not ship"
    for spec in ("cabinet-axes-spec-2026-07-05.md",
                 "evolution-engine-spec-2026-07-05.md",
                 "sovereign-build-spec-2026-07-04.md"):
        assert (plans / spec).is_file(), f"R145: germline-pinned spec {spec} must ship"
    # R167 (2026-07-15): dropped from the keep-list — a dated screenpipe-
    # coupling census is instance history, same class the rest of this rule
    # already archives; it must NOT ship.
    assert not (plans / "source-adapter-boundary-2026-07-05.md").exists(), \
        "R167: source-adapter-boundary-2026-07-05.md must not ship (dated coupling census, instance history)"
    # nothing else remains
    leftover = sorted(p.name for p in plans.iterdir())
    assert leftover == ["ARCHIVED-NOTE.md", "cabinet-axes-spec-2026-07-05.md",
                        "evolution-engine-spec-2026-07-05.md",
                        "sovereign-build-spec-2026-07-04.md"], leftover


def test_testburg_fixture_ships(export: Path):
    tb = export / "cabinet" / "fixtures" / "testburg"
    for f in ("README.md", "generate.py", "config/product.yml"):
        assert (tb / f).is_file(), f"testburg demo fixture must ship: {f}"


def test_world_assets_and_node_modules_absent(export: Path):
    for banned_dir in ("cabinet/dashboard/public/world-assets",
                       "cabinet/scripts/world-aesthetic/corpus",
                       "cabinet/scripts/world-aesthetic/goldens"):
        d = export / banned_dir
        if d.exists():
            pngs = [p.name for p in d.rglob("*") if p.suffix in (".png", ".zip", ".jpg")]
            assert not pngs, f"licensed binaries must not ship in {banned_dir}: {pngs}"
    assert not list(export.rglob("node_modules")), "R088: node_modules must not ship"
    assert not (export / "cabinet/dashboard/.next").exists(), "R088: .next must not ship"


def test_bin_mount_present(export: Path):
    assert (export / "bin" / ".gitkeep").is_file(), "R059: empty bin/ mount point ships"


def test_ci_retargeted_to_master(export: Path):
    wf_dir = export / ".github" / "workflows"
    branch_lines = []
    for wf in sorted(wf_dir.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        # not just the trigger lines: prose/comment mentions of the private
        # integration branch are instance history and must not ship either
        assert "fidelity-harness-design" not in text, \
            f"R159: private branch name survived in {wf.name}"
        for line in text.splitlines():
            if line.strip().startswith("branches:"):
                branch_lines.append((wf.name, line.strip()))
    assert branch_lines, "expected at least one CI branch trigger"
    for name, line in branch_lines:
        assert line == "branches: [master]", f"R159: {name} still has '{line}'"


def test_launchd_ships_portable_templates_only(export: Path):
    """PC-E scrub-paths: the static committed plists are the live deployment's
    rendered artifacts (absolute home paths + live roster) — only the envsubst
    .template.plist twins + officer-entitlements.plist may ship; a fresh
    deployment renders its fleet from cabinet/services.yml + templates.
    ONE germline-lockstep exception (R160 amendment): the DARK germline-wired
    com.cabinet.gate-apply.plist ships PORTABLE-DARK (placeholder paths,
    Disabled/RunAtLoad preserved) because the export's own lockstep suite —
    run by publish-gate (b) null-hatch — requires the wired FILES entry on
    disk and enumerated as the one LaunchDaemons plist."""
    launchd = export / "cabinet" / "launchd"
    # recursive, mirroring the transform's fail-closed verification sweep:
    # a plist anywhere under cabinet/launchd/ must be a portable template,
    # the generic entitlements file, or the portable-dark gate-apply twin
    offenders = [
        p.relative_to(export).as_posix() for p in launchd.rglob("*.plist")
        if not p.name.endswith(".template.plist")
        and p.name != "officer-entitlements.plist"
        and p.name != "com.cabinet.gate-apply.plist"
    ]
    assert not offenders, f"rendered live plists must not ship: {offenders}"
    assert (launchd / "com.cabinet.officer.template.plist").is_file(), \
        "the officer template twin must ship"
    assert (launchd / "officer-entitlements.plist").is_file(), \
        "the generic entitlements plist must ship"
    assert (launchd / "INSTALL-flip.md").is_file(), \
        "the (scrubbed) launchd install doc still ships"
    # portable-dark content contract on the shipped gate-apply plist
    ga = launchd / "com.cabinet.gate-apply.plist"
    assert ga.is_file(), "gate-apply portable-dark plist must ship (R160 amendment)"
    ga_text = ga.read_text(encoding="utf-8")
    assert "/Users/" not in ga_text, \
        "gate-apply plist must carry no absolute home path after the rewrite"
    assert "${REPO_ROOT}" in ga_text, \
        "gate-apply plist must carry the envsubst REPO_ROOT placeholder"
    assert "<key>Disabled</key>" in ga_text and "<key>RunAtLoad</key>" in ga_text, \
        "gate-apply plist DARK keys must survive the rewrite"


def test_framework_docs_dated_snapshots_archived(export: Path):
    """R162 (Wave-E integrator): dated framework/docs design snapshots are
    instance history and leave the egg; the living contract docs + the
    ARCHIVED-NOTE stub ship."""
    docs = export / "framework" / "docs"
    dated = [p.name for p in docs.glob("*-2026-*.md")]
    assert dated == [], f"dated design snapshots must not ship: {dated}"
    for keeper in ("ARCHIVED-NOTE.md", "work-model.md",
                   "consequence-ledger.md", "outcome-watchdog.md"):
        assert (docs / keeper).is_file(), f"living doc must ship: {keeper}"


def test_proposals_non_amendments_archived_amendments_kept(export: Path):
    """R167 (personal-clean wave, 2026-07-15): fills the gap R146 named but
    never implemented — the 21 docs/proposals/germline-amendment-*.md
    FOUNDING AMENDMENTS (R031/R146: ratified, frozen constitutional record)
    ship verbatim; every other file (addenda/activation runbooks, no
    ratified ship requirement) archives with an ARCHIVED-NOTE.md stub."""
    proposals = export / "docs" / "proposals"
    assert (proposals / "ARCHIVED-NOTE.md").is_file(), "R167: archived stub must ship"
    amendments = sorted(p.name for p in proposals.glob("germline-amendment-*.md"))
    assert amendments == [
        "germline-amendment-attention-transport-2026-07-09.md",
        "germline-amendment-brain-bridge-split-2026-07-07.md",
        "germline-amendment-cabinet-axes-2026-07-05.md",
        "germline-amendment-candor-2026-07-10.md",
        "germline-amendment-constitution-retirement-2026-07-07.md",
        "germline-amendment-context-resolver-2026-07-17.md",
            "germline-amendment-cosmetic-batch-2026-07-07.md",
            "germline-amendment-de-nate-2026-07-05.md",
            "germline-amendment-egress-launchd-owner-2026-07-15.md",
            "germline-amendment-evidence-phase1-2026-07-16.md",
            "germline-amendment-evidence-phase2a-2026-07-17.md",
            "germline-amendment-evidence-recorder-hardening-2026-07-15.md",
            "germline-amendment-evidence-recorder-v1-2026-07-15.md",
            "germline-amendment-gather-rewire-2026-07-07.md",
        "germline-amendment-golden-evals-prune-2026-07-07.md",
        "germline-amendment-host-grant-removal-2026-07-07.md",
        "germline-amendment-instance-extract-2026-07-05.md",
        "germline-amendment-killswitch-events-2026-07-17.md",
            "germline-amendment-manifest-sunset-2026-07-07.md",
            "germline-amendment-officer-security-boundary-2026-07-15.md",
            "germline-amendment-policy-engine-pulldown-2026-07-07.md",
        "germline-amendment-source-adapter-2026-07-05.md",
        "germline-amendment-sovereign-posture-2026-07-05.md",
        "germline-amendment-task-create-2026-07-03.md",
        "germline-amendment-trigger-retention-2026-07-16.md",
        "germline-amendment-trust-inversion-2026-07-04.md",
        "germline-amendment-war-room-census-2026-07-10.md",
    ], amendments
    for gone in ("comms-mcp-activation-2026-07-09.md",
                 "germline-addendum-claude-code-audit-2026-07-07.md",
                 "germline-enforcement-fixes-2026-07-14-addendum.md",
                 "germline-hygiene-trim-guard-addendum-2026-07-11.md",
                 "germline-lockstep-lane-resolver-addendum-2026-07-12.md",
                 "germline-window-4-deferral-2026-07-10.md",
                 "germline-window-addendum-2026-07-07.md",
                 "sovereign-posture-activation-2026-07-09.md",
                 # BC boot-pack staged package (memwave3 2026-07-15): plain
                 # files directly under docs/proposals/ BY CONTRACT — a
                 # subdirectory would crash t_proposals_archive's rm -f loop
                 # under set -e (leftover pin below also enforces no-subdir).
                 "germline-session-start-digest-addendum-2026-07-15.md",
                 "germline-session-start-digest-2026-07-15.patch",
                 # Library-retirement ceremony package (2026-07-16): same
                 # shape — flat addendum doc + .patch under docs/proposals/,
                 # archived out of the egg as instance ceremony history.
                 "germline-library-retirement-addendum-2026-07-16.md",
                 "germline-library-retirement-2026-07-16.patch"):
        assert not (proposals / gone).exists(), f"R167: non-amendment proposal must not ship: {gone}"
    # nothing else remains beyond the stub + the 20 amendments
    leftover = sorted(p.name for p in proposals.iterdir())
    assert leftover == sorted(["ARCHIVED-NOTE.md"] + amendments), leftover


def test_claude_egg_swap_once_template_tracked(export: Path):
    """PC-E scrub-paths: once docs/templates/CLAUDE-egg.md is tracked at HEAD,
    the export's CLAUDE.md must BE the captain-agnostic template (swapped in
    by claude-egg-swap) and the template path itself must be gone. Before the
    template is tracked (pre-integration cut) the exporter prints a loud
    UNSWAPPED note instead — same once-tracked pattern as the appshell rows."""
    ls_tree = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-tree", "--name-only", "HEAD",
         "docs/templates/CLAUDE-egg.md"],
        capture_output=True, text=True, timeout=30,
    )
    # empty stdout means "not tracked" ONLY on a successful run — a broken
    # git environment must fail the test, never silently skip the bindings
    assert ls_tree.returncode == 0, (
        f"git ls-tree failed rc={ls_tree.returncode}: {ls_tree.stderr}"
    )
    tracked = ls_tree.stdout.strip()
    assert not (export / "docs" / "templates" / "CLAUDE-egg.md").exists(), \
        "the template must never ship at its source path (swapped or not yet tracked)"
    if not tracked:
        pytest.skip("docs/templates/CLAUDE-egg.md not tracked at HEAD yet — "
                    "swap activates in the commit that tracks it")
    shipped = (export / "CLAUDE.md").read_text(encoding="utf-8")
    assert "CLAUDE-egg.md" in shipped.splitlines()[0] or "CLAUDE-egg" in shipped[:400], \
        "shipped CLAUDE.md must be the swapped-in captain-agnostic template"
    assert "/Users/" not in shipped, "no absolute home paths in the shipped CLAUDE.md"


def test_export_tooling_excluded_from_the_egg(export: Path):
    for private in ("cabinet/scripts/egg-export.sh",
                    "cabinet/scripts/egg-publish-gate.sh",
                    "cabinet/scripts/egg-export-manifest.txt",
                    "cabinet/scripts/tests/test_egg_export.py",
                    "docs/runbooks/egg-export-2026-07-10.md"):
        assert not (export / private).exists(), \
            f"private-side export tooling must not ship: {private}"


def test_pensionist_shot_baselines_excluded(export: Path):
    """Wave G scripts-sweep fix pass (R120-class instance-split): the
    committed pensionist screenshot baselines are THIS instance's review
    artifacts — pre-fixture-flip surface vocabulary is baked into the
    PIXELS, invisible to gate (d)'s text grep — and must never ship. The
    harness itself (scripts + rubric + README with the regen steps) rides,
    so a fresh deployment captures its own baselines."""
    assert not (export / "cabinet/scripts/pensionist/shots").exists(), \
        "instance screenshot baselines must not ship"
    for keeper in ("gen_fixtures.py", "render_tg.py", "run.py",
                   "rubric.md", "README.md"):
        assert (export / "cabinet/scripts/pensionist" / keeper).is_file(), \
            f"pensionist harness file must still ship: {keeper}"


def test_egg_manifest_json(export: Path):
    meta = json.loads((export / "egg-manifest.json").read_text(encoding="utf-8"))
    assert meta["source_commit"] == _head_commit()
    assert meta["source_commit_date"], "commit-clock date must be recorded"
    real_count = sum(
        1 for p in export.rglob("*")
        if p.is_file() and p.relative_to(export).as_posix() != "egg-manifest.json"
    )
    assert meta["file_count"] == real_count, (meta["file_count"], real_count)
    for row in ("R116", "R127", "R145", "R159"):
        assert row in meta["applied_rules"]
    assert "transform:instance-verify" in meta["applied_rules"]
    assert "CG-7" in meta["publish_gate"]


# ---------------------------------------------------------------------------
# Output-dir safety refusals
# ---------------------------------------------------------------------------

def test_refuses_out_inside_repo(tmp_path: Path):
    inside = _REPO_ROOT / ".pytest-egg-refuse-me"
    proc = _run_export(inside)
    assert proc.returncode != 0
    assert "INSIDE the repo tree" in proc.stderr
    assert not inside.exists(), "refusal must not create the directory"


def test_refuses_out_inside_repo_with_doubled_slash():
    """'//<repo>/x' canonicalizes with a doubled leading slash on macOS,
    which used to dodge every case-pattern safety check — pin the collapse."""
    dodgy = "//" + str(_REPO_ROOT).lstrip("/") + "/.pytest-egg-refuse-me"
    proc = _run_export(Path(dodgy))
    assert proc.returncode != 0
    assert "INSIDE the repo tree" in proc.stderr
    assert not (_REPO_ROOT / ".pytest-egg-refuse-me").exists()


def test_refuses_repo_root_itself():
    proc = _run_export(_REPO_ROOT)
    assert proc.returncode != 0
    assert "repo" in proc.stderr


def test_refuses_out_containing_repo():
    proc = _run_export(_REPO_ROOT.parent)
    assert proc.returncode != 0


def test_refuses_missing_parent(tmp_path: Path):
    proc = _run_export(tmp_path / "no" / "such" / "parent" / "egg")
    assert proc.returncode != 0
    assert "parent" in proc.stderr


def test_refuses_nonempty_without_force_then_force_clears(tmp_path: Path):
    out = tmp_path / "egg2"
    out.mkdir()
    marker = out / "precious.txt"
    marker.write_text("do not clobber\n", encoding="utf-8")
    refused = _run_export(out)
    assert refused.returncode != 0
    assert "not empty" in refused.stderr
    assert marker.read_text(encoding="utf-8") == "do not clobber\n"
    forced = _run_export(out, "--force")
    assert forced.returncode == 0, forced.stderr
    assert not marker.exists(), "--force must clear prior contents"
    assert (out / "egg-manifest.json").is_file()


def test_refuses_well_known_system_dir():
    """'--out /usr --force' must refuse BEFORE any clearing — the named-dir
    guard, not the (weaker) non-empty refusal, must fire. Safe to run even on
    regression: no --force is passed, so the non-empty check still refuses."""
    proc = _run_export(Path("/usr"))
    assert proc.returncode != 0
    assert "well-known system directory" in proc.stderr


# ---------------------------------------------------------------------------
# Publish gate — argument handling + gate (d) masking semantics (the REAL
# export's full gate run stays a manual/Captain step; the planted fake export
# below is RED regardless of whether gitleaks is installed)
# ---------------------------------------------------------------------------

def test_gate_help_mentions_cg7():
    proc = _run_gate("--help")
    assert proc.returncode == 0, proc.stderr
    assert "CG-7" in proc.stdout


def test_gate_refuses_missing_dir(tmp_path: Path):
    proc = _run_gate("--export", str(tmp_path / "nowhere"))
    assert proc.returncode != 0


def test_gate_refuses_a_git_checkout(tmp_path: Path):
    fake = tmp_path / "checkout"
    (fake / ".git").mkdir(parents=True)
    (fake / "egg-manifest.json").write_text("{}\n", encoding="utf-8")
    proc = _run_gate("--export", str(fake))
    assert proc.returncode != 0
    assert "not a fresh-cut export" in proc.stderr


def test_gate_requires_egg_manifest(tmp_path: Path):
    bare = tmp_path / "bare"
    bare.mkdir()
    proc = _run_gate("--export", str(bare))
    assert proc.returncode != 0
    assert "egg-manifest.json" in proc.stderr


def test_gate_d_masking_and_leak_classes(tmp_path: Path):
    """Gate (d) semantics against a tiny PLANTED fake export, driven by the
    SYNTHETIC fixture suite through the EGG_GATE_PATTERNS_FILE seam (R166 —
    every probe token below is a qz* placeholder; no real value appears in
    this tracked source):

    * an adjudicated `allow` entry from the patterns file ALONE is masked
      ([adj] reported, 0 kept);
    * the allow-entry PLUS another banned token on one line still FAILS
      (an inverted apply_allowlist would silently divert real hits);
    * a bare banned token FAILS;
    * a 13-digit supergroup-shaped id FAILS via the TRACKED generic pattern
      (the unbounded {9,} digit run — a 9-12 cap was fail-open for exactly
      this class);
    * a hostname-shaped possessive FAILS via the word:<name>s pattern
      (the bare word:<name> boundary deliberately skips it);
    * verdict is RED with exit code 1.
    """
    fake = tmp_path / "fake-export"
    fake.mkdir()
    (fake / "egg-manifest.json").write_text("{}\n", encoding="utf-8")
    # the 13-digit run is concatenated so this SOURCE file never carries a
    # 9+-digit run (the digit-run guard applies to test sources too)
    supergroup_id = "-" + "100123" + "4567890"
    (fake / "planted.txt").write_text(
        "install: qzhandle/qz-cabinet\n"
        "qzhandle/qz-cabinet plus qzcolleague on one line\n"
        "a bare banned token: qzemployer\n"
        f"supergroup-shaped id: {supergroup_id}\n"
        "hostname-shaped: Qzcaptains-MacBook-Pro\n",
        encoding="utf-8",
    )
    proc = _run_gate("--export", str(fake),
                     patterns_file=_mk_patterns_file(tmp_path))
    out = proc.stdout
    # allowlist masking: both allow-entry lines diverted for the qzhandle
    # pattern — reported, never silently dropped, never counted as hits
    assert "[adj] (sub) 'qzhandle'" in out, out
    assert "[ok ] (sub) 'qzhandle' — 0 hits" in out, out
    # ...but the OTHER banned token on the shared line still fails
    assert "[HIT] (sub) 'qzcolleague'" in out, out
    assert "[HIT] (sub) 'qzemployer'" in out, out
    # the two leak classes the fix pass pinned
    assert "[HIT] (id) '[0-9]{9,}'" in out, out
    assert "[HIT] (word) 'qzcaptains'" in out, out
    # grouped verdict: gate (d) FAILs and the whole gate is RED (exit 1 —
    # not 2, which would mean a usage/self-test/pattern-config abort)
    assert "GATE (d) real-value grep suite .................... FAIL" in out, out
    assert "PUBLISH GATE: RED" in out, out
    assert proc.returncode == 1, (proc.returncode, out, proc.stderr)


# ---------------------------------------------------------------------------
# Publish gate — R166 pattern-source contract (fail-closed, never vacuous)
# ---------------------------------------------------------------------------

def _mk_fake_export(tmp_path: Path, planted: str) -> Path:
    fake = tmp_path / "fake-export"
    fake.mkdir()
    (fake / "egg-manifest.json").write_text("{}\n", encoding="utf-8")
    (fake / "planted.txt").write_text(planted, encoding="utf-8")
    return fake


def test_gate_missing_patterns_file_fails_closed(tmp_path: Path):
    """A REAL publish run without the captain-specific patterns file must
    ABORT (exit 2) — never a vacuous scan, never a vacuous GREEN. Hermetic
    via the seam: EGG_GATE_PATTERNS_FILE points at a nonexistent path, the
    same missing-file code path the default location takes on an
    unconfigured machine."""
    fake = _mk_fake_export(tmp_path, "innocuous content\n")
    proc = _run_gate("--export", str(fake),
                     patterns_file=tmp_path / "no-such-patterns-file")
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert "no captain-specific scan patterns configured — refusing to publish" \
        in proc.stderr, proc.stderr
    # aborted BEFORE any verdict: a vacuous GREEN must be impossible
    assert "PUBLISH GATE:" not in proc.stdout, proc.stdout


def test_gate_patternless_file_fails_closed(tmp_path: Path):
    """A patterns file with zero `pattern` directives (comments only) is a
    vacuous configuration — the gate must refuse it, not scan with generics
    alone."""
    fake = _mk_fake_export(tmp_path, "innocuous content\n")
    fixture = _mk_patterns_file(tmp_path, "# only comments here\n\n")
    proc = _run_gate("--export", str(fake), patterns_file=fixture)
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert "no 'pattern' directives — refusing a vacuous publish scan" \
        in proc.stderr, proc.stderr
    assert "PUBLISH GATE:" not in proc.stdout, proc.stdout


def test_gate_allow_only_file_fails_closed(tmp_path: Path):
    """A patterns file carrying ONLY `allow` directives (zero `pattern`
    directives) is still a vacuous configuration — allow lines are
    adjudication masks, not scan patterns, and must never count toward
    suite non-emptiness (a refactor that tallied them would silently
    reopen the vacuous-scan hole)."""
    fake = _mk_fake_export(tmp_path, "innocuous content\n")
    fixture = _mk_patterns_file(tmp_path, "allow QZ-1 qzhandle/qz-cabinet\n")
    proc = _run_gate("--export", str(fake), patterns_file=fixture)
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert "no 'pattern' directives — refusing a vacuous publish scan" \
        in proc.stderr, proc.stderr
    assert "PUBLISH GATE:" not in proc.stdout, proc.stdout


def test_gate_verbatim_template_copy_fails_closed(tmp_path: Path):
    """CONFIRMED review vector: `cp`-ing the tracked synthetic template to
    the live path satisfies the non-empty check yet scans only placeholder
    tokens — with gates (a)-(c) green that is a vacuous GREEN. Any pattern
    value still verbatim in the tracked template must ABORT (exit 2),
    without echoing the value."""
    fake = _mk_fake_export(tmp_path, "innocuous content\n")
    example = (_REPO_ROOT / "instance" / "config" /
               "publish-scan-patterns.local.example")
    fixture = _mk_patterns_file(
        tmp_path, example.read_text(encoding="utf-8"))
    proc = _run_gate("--export", str(fake), patterns_file=fixture)
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert "appears verbatim among the synthetic template's directives" \
        in proc.stderr, proc.stderr
    # the flagged placeholder value itself never smears into the abort
    assert "yourlastname" not in proc.stderr, proc.stderr
    assert "PUBLISH GATE:" not in proc.stdout, proc.stdout


def test_gate_template_placeholder_remnant_fails_closed(tmp_path: Path):
    """Sibling-twin variant + value-withholding: ONE placeholder left
    unreplaced among otherwise real-shaped values still aborts, naming
    file:LINE-NUMBER and the template — never the value (on a half-edited
    file the flagged value may be a real one)."""
    fake = _mk_fake_export(tmp_path, "innocuous content\n")
    fixture = _mk_patterns_file(
        tmp_path, "pattern sub:qzrealshaped\npattern sub:qzremnanttoken\n")
    (tmp_path / (fixture.name + ".example")).write_text(
        "# synthetic template twin\npattern sub:qzremnanttoken\n",
        encoding="utf-8")
    proc = _run_gate("--export", str(fake), patterns_file=fixture)
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert "appears verbatim among the synthetic template's directives" \
        in proc.stderr, proc.stderr
    assert ":2 " in proc.stderr, proc.stderr          # the line NUMBER...
    assert "qzremnanttoken" not in proc.stderr        # ...never the value
    assert "PUBLISH GATE:" not in proc.stdout, proc.stdout


def test_gate_template_prose_substring_is_not_refused(tmp_path: Path):
    """False-positive guard on the template-copy refusal: only the
    template's DIRECTIVE lines carry placeholders — its '#' prose can
    legitimately contain a real value as a substring of an ordinary
    English word (word-class first names especially). A value found
    solely in prose must LOAD, not abort: refusing it would brick the
    gate on a correctly seeded live file."""
    fake = _mk_fake_export(tmp_path, "innocuous content\n")
    fixture = _mk_patterns_file(
        tmp_path, "pattern word:qzprose\npattern sub:qzdistinct\n")
    (tmp_path / (fixture.name + ".example")).write_text(
        "# prose where coordiqzprose rides inside an ordinary word\n"
        "pattern sub:qzplaceholder\n", encoding="utf-8")
    proc = _run_gate("--export", str(fake), patterns_file=fixture)
    assert proc.returncode != 2, (proc.returncode, proc.stdout, proc.stderr)
    assert "appears verbatim among" not in proc.stderr, proc.stderr
    assert "PUBLISH GATE:" in proc.stdout, proc.stdout  # a verdict was reached


def test_gate_malformed_patterns_file_fails_closed(tmp_path: Path):
    """An unrecognized directive aborts, naming file:LINE-NUMBER only —
    the line CONTENT (which may carry a real value) must not smear into
    stderr."""
    fake = _mk_fake_export(tmp_path, "innocuous content\n")
    fixture = _mk_patterns_file(
        tmp_path, "pattern sub:qzemployer\nscrub sub:qzsecrettoken\n")
    proc = _run_gate("--export", str(fake), patterns_file=fixture)
    assert proc.returncode == 2, (proc.returncode, proc.stdout, proc.stderr)
    assert "unrecognized directive at" in proc.stderr, proc.stderr
    assert ":2 " in proc.stderr, proc.stderr          # the line NUMBER...
    assert "qzsecrettoken" not in proc.stderr         # ...never the content


def test_gate_generic_id_pattern_keeps_teeth(tmp_path: Path):
    """The TRACKED generic suite must still scan when the captain file
    carries none of it: a planted 9-digit id is caught with a minimal
    patterns file holding only an unrelated token."""
    digits = "98765" + "4321"                          # 9-digit run, split in source
    fake = _mk_fake_export(tmp_path, f"board id {digits} planted\n")
    fixture = _mk_patterns_file(tmp_path, "pattern sub:qzunrelatedtoken\n")
    proc = _run_gate("--export", str(fake), patterns_file=fixture)
    out = proc.stdout
    assert "[HIT] (id) '[0-9]{9,}'" in out, out
    assert "GATE (d) real-value grep suite .................... FAIL" in out, out
    assert proc.returncode == 1, (proc.returncode, out, proc.stderr)


def test_gate_source_carries_no_captain_pattern_values():
    """Self-audit (the R166 point): none of the REAL captain-specific
    pattern values may appear in the tracked gate source or the synthetic
    .example twin. Values are read at runtime from the live patterns file —
    this test source carries none of them — so the test runs only on a
    configured captain machine and SKIPS where the file is absent (CI)."""
    live = _REPO_ROOT / "instance" / "config" / "publish-scan-patterns.local"
    if not live.is_file():
        pytest.skip("no live publish-scan-patterns.local on this machine "
                    "(CI shape) — the captain-machine self-audit has nothing "
                    "to compare against")
    values: list[str] = []
    for raw in live.read_text(encoding="utf-8").splitlines():
        ln = raw.strip()
        if ln.startswith("pattern "):
            spec = ln[len("pattern "):]
            values.append(spec.split(":", 1)[1])
        elif ln.startswith("allow "):
            parts = ln.split(None, 2)
            if len(parts) == 3:
                values.append(parts[2])
    assert values, "live patterns file parsed to zero values — fix the file"
    gate_low = _GATE_SH.read_text(encoding="utf-8").lower()
    example_low = (_REPO_ROOT / "instance" / "config" /
                   "publish-scan-patterns.local.example").read_text(
                       encoding="utf-8").lower()
    leaked = [v for v in values if len(v) >= 3
              and (v.lower() in gate_low or v.lower() in example_low)]
    assert not leaked, (
        f"{len(leaked)} captain-specific value(s) leaked into tracked "
        "sources (values withheld from this assertion output by design — "
        "diff the live patterns file against the named sources)")
