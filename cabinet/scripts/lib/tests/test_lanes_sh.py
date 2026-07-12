"""Wave G (lane-name instance-split) — contract tests for lanes.sh.

cabinet/scripts/lib/lanes.sh is the bash instance-config resolver: lane and
officer names are INSTANCE DATA read from instance/config/contexts/*.yml,
cabinet/officer-capabilities.conf and platform.yml/product.yml — never script
literals. These tests pin:

  1. the parse contract (mirrors run_action_lane._context_slugs byte-for-byte
     so the two enums can merge at a germline window);
  2. the ACTIVE-FLAG TRAP: `active: false` contexts MUST still enumerate (on
     the launcher instance the running lanes' contexts are active:false
     R2-pending declarations — an active-filtered enum silently drops them);
  3. fail-honest semantics: unreadable config => empty output + rc 1; a
     readable-but-empty declaration => honest empty set + rc 0 (set-valued),
     rc 1 for the scalar deploys_code officer; NEVER an invented default.

All fixture vocabulary is synthetic Testburg (foundation fixtures never name
instance lanes). No network, no Redis — subprocess bash over tmp_path config.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# test_library_mcp_client patches the global subprocess.Popen and the patch
# can leak into later-alphabetical modules — capture the real one at import
# (collection) time and restore it around our spawns (same guard as
# test_memory_search_sh.py).
_REAL_POPEN = subprocess.Popen

SCRIPTS_DIR = Path(__file__).resolve().parents[2]  # cabinet/scripts
LANES_SH = SCRIPTS_DIR / "lib" / "lanes.sh"


def _run(func: str, root: Path) -> subprocess.CompletedProcess:
    """Source lanes.sh and invoke one resolver against a fixture root.

    Fixed argv + a constant -c string: the fixture path travels via env
    (CABINET_ROOT), never interpolated into shell text.
    """
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        return subprocess.run(
            ["bash", "-c",
             'set -uo pipefail; source "$LANES_LIB"; "$LANES_FN"'],
            capture_output=True, text=True,
            env={"CABINET_ROOT": str(root), "LANES_LIB": str(LANES_SH),
                 "LANES_FN": func, "PATH": "/usr/bin:/bin"},
        )
    finally:
        subprocess.Popen = patched


def _lines(proc: subprocess.CompletedProcess) -> list[str]:
    return [ln for ln in proc.stdout.splitlines() if ln]


def _seed_contexts(root: Path, files: dict[str, str]) -> None:
    d = root / "instance" / "config" / "contexts"
    d.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (d / name).write_text(body, encoding="utf-8")


TESTBURG_CONF = """\
# Testburg fixture roster — synthetic, no real officer names.
cos:captain_rules_retrieval
cos:validates_deployments

bakery-ceo:deploys_code
bakery-ceo:logs_captain_decisions
newsletter-ceo:deploys_code
comms-officer:logs_captain_decisions
"""


def _seed_conf(root: Path, body: str = TESTBURG_CONF) -> None:
    d = root / "cabinet"
    d.mkdir(parents=True, exist_ok=True)
    (d / "officer-capabilities.conf").write_text(body, encoding="utf-8")


def test_bash_syntax_lanes_sh():
    patched = subprocess.Popen
    subprocess.Popen = _REAL_POPEN
    try:
        proc = subprocess.run(["bash", "-n", str(LANES_SH)],
                              capture_output=True, text=True)
    finally:
        subprocess.Popen = patched
    assert proc.returncode == 0, f"bash -n lanes.sh failed: {proc.stderr}"


# ---------------------------------------------------------------- lanes ----

def test_lanes_enumerates_sorted_and_never_filters_active(tmp_path):
    """The active-flag trap: active:false lanes MUST still enumerate."""
    _seed_contexts(tmp_path, {
        "bakery-site.yml": "slug: bakery-site\nactive: false\n",
        "newsletter.yml": "slug: newsletter\nactive: true\n",
        "testburg-market.yml": 'slug: "Testburg-Market"\n',
        "_default.yml": "# defaults only — deliberately no slug\nactive: true\n",
    })
    proc = _run("cabinet_lanes", tmp_path)
    assert proc.returncode == 0
    # sorted, deduped, lowercased, quote-stripped; _default skipped;
    # bakery-site present DESPITE active: false.
    assert _lines(proc) == ["bakery-site", "newsletter", "testburg-market"]


def test_lanes_first_slug_line_wins_even_when_empty(tmp_path):
    """Mirror of _context_slugs: the FIRST slug: line per file is final."""
    _seed_contexts(tmp_path, {
        "two-slugs.yml": "slug: testburg\nslug: shadow-slug\n",
        "empty-first.yml": "slug:\nslug: never-reached\n",
        "indented.yml": "  slug: 'indented-testburg'\n",
    })
    proc = _run("cabinet_lanes", tmp_path)
    assert proc.returncode == 0
    # two-slugs → first wins; empty-first → first line taken, yields nothing;
    # indented slug: lines match after strip (python strips before startswith).
    assert _lines(proc) == ["indented-testburg", "testburg"]


def test_lanes_missing_dir_is_empty_rc1(tmp_path):
    proc = _run("cabinet_lanes", tmp_path)  # no instance/config/contexts
    assert proc.returncode == 1
    assert proc.stdout == ""


def test_lanes_dir_with_no_slugs_is_honest_empty_rc0(tmp_path):
    _seed_contexts(tmp_path, {"_default.yml": "active: true\n"})
    proc = _run("cabinet_lanes", tmp_path)
    assert proc.returncode == 0
    assert proc.stdout == ""


# ------------------------------------------------------------- officers ----

def test_officers_first_seen_order_dedup_comments_skipped(tmp_path):
    _seed_conf(tmp_path)
    proc = _run("cabinet_officers", tmp_path)
    assert proc.returncode == 0
    assert _lines(proc) == ["cos", "bakery-ceo", "newsletter-ceo",
                            "comms-officer"]


def test_officers_missing_conf_is_empty_rc1(tmp_path):
    proc = _run("cabinet_officers", tmp_path)
    assert proc.returncode == 1
    assert proc.stdout == ""


# -------------------------------------------------- deploys_code officer ----

def test_deploys_code_officer_is_first_holder_in_file_order(tmp_path):
    _seed_conf(tmp_path)  # bakery-ceo before newsletter-ceo
    proc = _run("cabinet_deploys_code_officer", tmp_path)
    assert proc.returncode == 0
    assert _lines(proc) == ["bakery-ceo"]


def test_deploys_code_officer_no_holder_is_empty_rc1(tmp_path):
    _seed_conf(tmp_path, "cos:validates_deployments\n")
    proc = _run("cabinet_deploys_code_officer", tmp_path)
    assert proc.returncode == 1
    assert proc.stdout == ""


# ----------------------------------------------------------- org domains ----

def test_org_domains_platform_top_level_lowercased_order_kept(tmp_path):
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "platform.yml").write_text(
        "captain_name: Ada Testburg\n"
        "org_domains:\n"
        "  - Bakery.Example   # mixed case in, lowercase out\n"
        '  - "market.example"\n'
        "tasks_board: '123'\n",
        encoding="utf-8")
    proc = _run("cabinet_org_domains", tmp_path)
    assert proc.returncode == 0
    assert _lines(proc) == ["bakery.example", "market.example"]


def test_org_domains_product_yml_nested_fallback(tmp_path):
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "product.yml").write_text(
        "product:\n"
        "  name: Testburg Bakery\n"
        "  org_domains:\n"
        "    - bakery.example\n",
        encoding="utf-8")
    proc = _run("cabinet_org_domains", tmp_path)
    assert proc.returncode == 0
    assert _lines(proc) == ["bakery.example"]


def test_org_domains_none_configured_is_empty_rc1(tmp_path):
    cfg = tmp_path / "instance" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "platform.yml").write_text("captain_name: Ada Testburg\n",
                                      encoding="utf-8")
    proc = _run("cabinet_org_domains", tmp_path)
    assert proc.returncode == 1
    assert proc.stdout == ""
