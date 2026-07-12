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
    or rel.startswith("instance/config/policies/")
    or rel.startswith("instance/config/posture-presets/")
    or rel == "instance/officer-skills/README.md"
)


def _run_export(out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_EXPORT_SH), "--out", str(out), *extra],
        cwd=_REPO_ROOT, capture_output=True, text=True, timeout=_EXPORT_TIMEOUT,
    )


def _run_gate(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(_GATE_SH), *args],
        cwd=_REPO_ROOT, capture_output=True, text=True, timeout=60,
    )


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
    for live in ("platform.yml", "sources.yml", "directions.yml", "peers.yml",
                 "officer-emails.yml", "probes.yml", "warrooms.yml",
                 "outcomes.yml", "hq-instance.yml.draft", "authority-enforcing"):
        assert not (cfg / live).exists(), f"R120: live {live} must not ship"
    for twin in ("platform.yml.example", "sources.yml.example",
                 "directions.yml.example", "peers.yml.example",
                 "officer-emails.yml.example", "probes.yml.example",
                 "warrooms.yml.example", "roster.yml.example"):
        assert (cfg / twin).is_file(), f"R120: {twin} must ship"


def test_act_first_default_is_the_scrubbed_twin(export: Path):
    """R126 + germline lockstep: the shipped act-first-surfaces.yml must be
    BYTE-IDENTICAL to its .example twin (empty lists, unratified) — never the
    live ruled file."""
    shipped = (export / "instance/config/act-first-surfaces.yml").read_bytes()
    twin = (export / "instance/config/act-first-surfaces.yml.example").read_bytes()
    assert shipped == twin
    assert b"status: unratified" in shipped


def test_instance_contains_only_examples_and_structure(export: Path):
    offenders = []
    for p in sorted((export / "instance").rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(export).as_posix()
        if not _INSTANCE_ALLOWED(rel):
            offenders.append(rel)
    assert not offenders, f"live instance files survived the pass: {offenders}"


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
                 "source-adapter-boundary-2026-07-05.md",
                 "evolution-engine-spec-2026-07-05.md",
                 "sovereign-build-spec-2026-07-04.md"):
        assert (plans / spec).is_file(), f"R145: germline-pinned spec {spec} must ship"
    # nothing else remains
    leftover = sorted(p.name for p in plans.iterdir())
    assert leftover == ["ARCHIVED-NOTE.md", "cabinet-axes-spec-2026-07-05.md",
                        "evolution-engine-spec-2026-07-05.md",
                        "source-adapter-boundary-2026-07-05.md",
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
    """Gate (d) semantics against a tiny PLANTED fake export (values below are
    synthetic leak-pattern PROBES per the real-value doctrine exception —
    this test file never ships in the egg):

    * the adjudicated coordinate ALONE is masked ([adj] reported, 0 kept);
    * the coordinate PLUS another banned token on one line still FAILS
      (an inverted apply_allowlist would silently divert real hits);
    * a bare banned token FAILS;
    * a 13-digit supergroup-shaped id FAILS (the unbounded {9,} digit run —
      a 9-12 cap was fail-open for exactly this class);
    * a hostname-shaped possessive FAILS via word:nates (word:nate's
      boundary deliberately skips it);
    * verdict is RED with exit code 1.
    """
    fake = tmp_path / "fake-export"
    fake.mkdir()
    (fake / "egg-manifest.json").write_text("{}\n", encoding="utf-8")
    (fake / "planted.txt").write_text(
        "install: nate-refslund/captains-cabinet\n"
        "nate-refslund/captains-cabinet plus kristoffer on one line\n"
        "a bare banned token: solveig\n"
        "supergroup-shaped id: -1001234567890\n"
        "hostname-shaped: Nates-MacBook-Pro\n",
        encoding="utf-8",
    )
    proc = _run_gate("--export", str(fake))
    out = proc.stdout
    # allowlist masking: both coordinate lines diverted for the refslund
    # pattern — reported, never silently dropped, never counted as hits
    assert "[adj] (sub) 'refslund'" in out, out
    assert "[ok ] (sub) 'refslund' — 0 hits" in out, out
    # ...but the OTHER banned token on the shared line still fails
    assert "[HIT] (sub) 'kristoffer'" in out, out
    assert "[HIT] (sub) 'solveig'" in out, out
    # the two leak classes the fix pass pinned
    assert "[HIT] (id) '[0-9]{9,}'" in out, out
    assert "[HIT] (word) 'nates'" in out, out
    # grouped verdict: gate (d) FAILs and the whole gate is RED (exit 1 —
    # not 2, which would mean a usage/self-test abort, not a verdict)
    assert "GATE (d) real-value grep suite .................... FAIL" in out, out
    assert "PUBLISH GATE: RED" in out, out
    assert proc.returncode == 1, (proc.returncode, out, proc.stderr)
