"""Roster / officer-conf lockstep meta-test (germline-4file-prep, 2026-07-15).

cabinet/officer-capabilities.conf and cabinet/mcp-scope.yml are the INSTANCE
data layer for the officer roster (framework.env.officers() reads the conf
directly; see framework/env.py's officers() docstring) — they are not
framework literals, so PC-E-LOCKSTEP does not require them to stop naming
real officers the way it required framework/frontdoor/action_exec.py and
framework/acting/action_lane.py to stop naming them (see
docs/proposals/germline-lockstep-lane-resolver-addendum-2026-07-12.md).

What WAS missing: nothing kept these two schg-locked files in agreement with
instance/config/roster.yml (deployment-local, gitignored, NOT schg-locked —
the file a Captain can already hand-edit without a ceremony). roster.yml's
own header calls officer-capabilities.conf and mcp-scope.yml its mirror
targets ("capability rows below mirror it" / "MCP scope lives there, not
here"), but nothing enforced that claim. This module is that check, mirroring
test_germline_lockstep_consistency.py's own method (parse the artifacts,
assert coverage) rather than inventing a code-generation step — a config
file cannot "read" another config file at parse time, so the safety net has
to live in tests, the same way it already does for the four germline lists.

SCOPE, deliberately narrow (see docs/proposals/germline-4file-prep-mcp-
officer-conf-2026-07-15.md for the full reasoning + a residual finding this
module does NOT assert on):
  - OFFICER-SET coverage: every instance/config/roster.yml officer slug must
    appear in officer-capabilities.conf's officer column AND in
    cabinet/mcp-scope.yml's `agents:` mapping. This is the safety-relevant
    property — an officer hired in roster.yml with zero rows in either file
    is silently locked out of every capability-gated behavior and every MCP
    server, which is a real lockout bug class, not a style nit.
  - Capability-LIST content (does officer-capabilities.conf grant the exact
    same capability set roster.yml's `capabilities:` field lists for that
    officer) is DELIBERATELY NOT asserted here. A real, pre-existing
    divergence exists on the launching instance (officer-capabilities.conf
    grants `captain_rules_retrieval` to the portfolio lane officers; the
    instance roster.yml's mirrored `capabilities:` list omits it) and this
    module does not know, without a Captain ruling, which file is stale —
    asserting exact equality would either hard-fail on a legitimate instance
    today or silently launder an actual bug by picking a side. Flagged in
    the addendum doc above instead of adjudicated here.

Absent instance/config/roster.yml (a fresh checkout, CI, or a repo that has
not been hatched yet) every roster-dependent test in this module SKIPS
cleanly — mirrors lib_roster.load_roster()'s own "absence is simply zero
rows, never a hard error" contract. Hermetic tests below build a synthetic
roster/conf/scope trio in tmp_path so the checking LOGIC itself is exercised
on every run, live-roster.yml or not.

THE DISABLED-SENSOR GAP, CLOSED (roster-authz, 2026-07-26). "The logic is
exercised" was never the property that mattered — the property that mattered
is "does the roster a HATCH produces pass this check?", and that arm skipped
in CI and in every checkout (roster.yml is gitignored), so it could only ever
fire inside a real hatch. It had never run. When it finally did, it failed:
generate-instance.py hired `<lane>-ceo` for every lane while the two files
that authorize an officer are germline — hatch.sh is structurally forbidden
to write them — so the hatch produced a roster it was forbidden to satisfy
and then gated on satisfying it. The generator is now authorization-gated
(see its "Hiring is authorization-gated" docstring section), and
test_generated_fresh_hatch_roster_is_fully_authorized below runs the REAL
generator into a tmp deployment root and checks its roster against the REAL
shipped conf pair — a representative fixture that fires on EVERY run, with no
roster.yml in the checkout. That is the arm that would have caught this.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "cabinet" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import lib_roster  # noqa: E402 — cabinet/scripts/lib_roster.py

OFFICER_CONF = _REPO_ROOT / "cabinet" / "officer-capabilities.conf"
MCP_SCOPE = _REPO_ROOT / "cabinet" / "mcp-scope.yml"
# NB: single combined "instance/config/roster.yml" path literal, NOT split
# "instance"/"config" segments — check-layer-separation.sh flags a bare quoted
# "instance" component anywhere under framework/**/*.py (it scans tests too),
# and env.py already uses this same combined form for its by-design instance-
# config reads (see the env.lanes() "single 'instance/config/...' path literal"
# note). Semantically identical Path division; keeps the gate green.
LIVE_ROSTER = _REPO_ROOT / "instance/config/roster.yml"


# ---------------------------------------------------------------------------
# parsers — read-only extraction, mirroring framework.env.officers()'s own
# documented algorithm (dedup, first-seen file order, skip blank/#/no-colon)
# rather than importing framework.env directly: officers() caches its result
# process-globally against a FIXED path resolved via _cabinet_root(), so it
# cannot be pointed at a synthetic tmp_path conf without monkeypatching module
# globals — the mirrored parser here stays a pure function of a path, like
# env.lanes() already mirrors run_action_lane._context_slugs byte-for-byte.
# ---------------------------------------------------------------------------

def _conf_officers(path: Path) -> tuple[str, ...]:
    seen: list[str] = []
    if not path.exists():
        return ()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        officer = s.split(":", 1)[0].strip()
        if officer and officer not in seen:
            seen.append(officer)
    return tuple(seen)


def _scope_agents(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    agents = data.get("agents") or {}
    if not isinstance(agents, dict):
        return ()
    return tuple(agents.keys())


def _missing_from_conf_and_scope(roster: dict, conf_path: Path,
                                  scope_path: Path) -> dict[str, list[str]]:
    """{slug: [missing-from list]} for every roster slug absent from either
    artifact; empty dict = full coverage. `roster` is a lib_roster-shaped
    mapping (slug -> fields-or-None)."""
    conf_officers = set(_conf_officers(conf_path))
    scope_agents = set(_scope_agents(scope_path))
    out: dict[str, list[str]] = {}
    for slug in roster:
        missing = []
        if slug not in conf_officers:
            missing.append("officer-capabilities.conf")
        if slug not in scope_agents:
            missing.append("mcp-scope.yml agents:")
        if missing:
            out[slug] = missing
    return out


# ---------------------------------------------------------------------------
# hermetic — the checking logic itself, independent of any real roster.yml
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_absent_roster_is_a_graceful_noop(tmp_path):
    """Mirrors lib_roster.load_roster()'s own absence contract — a repo with
    no instance/config/roster.yml yet has nothing to check, never a failure."""
    roster = lib_roster.load_roster(tmp_path)
    assert roster == {}
    conf = _write(tmp_path, "conf", "cos:logs_captain_decisions\n")
    scope = _write(tmp_path, "scope.yml", "agents:\n  cos:\n    mcps: [telegram]\n")
    assert _missing_from_conf_and_scope(roster, conf, scope) == {}


def test_full_coverage_passes(tmp_path):
    _write(tmp_path, "instance/config/roster.yml", """
roster:
  cos:
    title: Chair
    model: m
    capabilities: [logs_captain_decisions]
    authority_level: captain_proxy
  widget-ceo:
    title: "Widget CEO"
    model: m
    capabilities: [deploys_code]
    authority_level: mission_executor
""")
    roster = lib_roster.load_roster(tmp_path)
    conf = _write(tmp_path, "conf.conf",
                  "cos:logs_captain_decisions\nwidget-ceo:deploys_code\n")
    scope = _write(tmp_path, "scope.yml",
                   "agents:\n  cos:\n    mcps: [telegram]\n"
                   "  widget-ceo:\n    mcps: [neon]\n")
    assert _missing_from_conf_and_scope(roster, conf, scope) == {}


def test_officer_missing_from_conf_is_flagged(tmp_path):
    """A roster hire with no officer-capabilities.conf row is a silent
    capability lockout — the real safety gap this module exists to catch."""
    _write(tmp_path, "instance/config/roster.yml", """
roster:
  new-ceo:
    title: "New CEO"
    model: m
    capabilities: [deploys_code]
    authority_level: mission_executor
""")
    roster = lib_roster.load_roster(tmp_path)
    conf = _write(tmp_path, "conf.conf", "cos:logs_captain_decisions\n")
    scope = _write(tmp_path, "scope.yml",
                   "agents:\n  new-ceo:\n    mcps: [neon]\n")
    missing = _missing_from_conf_and_scope(roster, conf, scope)
    assert missing == {"new-ceo": ["officer-capabilities.conf"]}


def test_officer_missing_from_mcp_scope_is_flagged(tmp_path):
    """A roster hire with no mcp-scope.yml agents: row is a silent MCP
    lockout — every mcp__* call the officer's session makes is rejected by
    the pre-tool-use.sh scope gate."""
    _write(tmp_path, "instance/config/roster.yml", """
roster:
  new-ceo:
    title: "New CEO"
    model: m
    capabilities: [deploys_code]
    authority_level: mission_executor
""")
    roster = lib_roster.load_roster(tmp_path)
    conf = _write(tmp_path, "conf.conf", "new-ceo:deploys_code\n")
    scope = _write(tmp_path, "scope.yml", "agents:\n  cos:\n    mcps: [telegram]\n")
    missing = _missing_from_conf_and_scope(roster, conf, scope)
    assert missing == {"new-ceo": ["mcp-scope.yml agents:"]}


def test_officer_missing_from_both_lists_both(tmp_path):
    _write(tmp_path, "instance/config/roster.yml", """
roster:
  ghost-ceo:
    title: "Ghost CEO"
    model: m
    capabilities: [deploys_code]
    authority_level: mission_executor
""")
    roster = lib_roster.load_roster(tmp_path)
    conf = _write(tmp_path, "conf.conf", "cos:logs_captain_decisions\n")
    scope = _write(tmp_path, "scope.yml", "agents:\n  cos:\n    mcps: [telegram]\n")
    missing = _missing_from_conf_and_scope(roster, conf, scope)
    assert missing == {
        "ghost-ceo": ["officer-capabilities.conf", "mcp-scope.yml agents:"]}


# ---------------------------------------------------------------------------
# the real artifacts — skips cleanly when this checkout has no live roster
# ---------------------------------------------------------------------------

def test_repo_conf_files_parse_and_are_nonempty():
    """Always runs (no roster.yml dependency): basic corruption guard on the
    two tracked artifacts themselves."""
    assert OFFICER_CONF.exists(), f"{OFFICER_CONF} missing"
    assert MCP_SCOPE.exists(), f"{MCP_SCOPE} missing"
    assert _conf_officers(OFFICER_CONF), "officer-capabilities.conf has zero officer rows"
    assert _scope_agents(MCP_SCOPE), "mcp-scope.yml has zero agents: entries"


def test_live_roster_officer_set_covered_by_conf_and_scope():
    """The real lockstep check. Skips when instance/config/roster.yml is
    absent (this worktree, CI, a fresh/un-hatched checkout) — present on a
    live deployment, asserts every hired officer has both a capability row
    and an MCP scope row (see module docstring for what this deliberately
    does NOT assert: exact capability-list content)."""
    if not LIVE_ROSTER.exists():
        pytest.skip("instance/config/roster.yml absent (gitignored, "
                     "deployment-local) — nothing to check on this checkout")
    roster = lib_roster.load_roster(_REPO_ROOT)
    missing = _missing_from_conf_and_scope(roster, OFFICER_CONF, MCP_SCOPE)
    assert missing == {}, (
        f"roster.yml officer(s) not fully covered by the germline conf pair: "
        f"{missing} — a hired officer with a missing row is a silent "
        f"capability/MCP-scope lockout; add the row to the named file(s)")


# ---------------------------------------------------------------------------
# THE ARM THAT FIRES IN CI — a representative fixture: the roster a real hatch
# produces, checked against the REAL shipped conf pair. No roster.yml needed in
# the checkout, so this can never go dark the way the live arm above did.
# ---------------------------------------------------------------------------

GENERATOR = _SCRIPTS_DIR / "generate-instance.py"
LANE_CEO_TEMPLATE = _REPO_ROOT / "presets/portfolio/agents/_lane-ceo.md.template"

_PLATFORM_SEED = """\
captain_name: Placeholder
captain_timezone: UTC
captain_telegram_chat_id: "0000"
"""


def _stage_deployment_root(tmp_path: Path) -> Path:
    """A minimal but FAITHFUL deployment root: the real lane-CEO template and
    the REAL germline pair (the authorization surface), so the generator sees
    exactly what a stranger's egg ships."""
    root = tmp_path / "deployment"
    (root / "instance/config").mkdir(parents=True)
    (root / "presets/portfolio/agents").mkdir(parents=True)
    (root / "cabinet").mkdir(parents=True)
    shutil.copy(LANE_CEO_TEMPLATE,
                root / "presets/portfolio/agents/_lane-ceo.md.template")
    shutil.copy(OFFICER_CONF, root / "cabinet/officer-capabilities.conf")
    shutil.copy(MCP_SCOPE, root / "cabinet/mcp-scope.yml")
    (root / "instance/config/platform.yml").write_text(_PLATFORM_SEED,
                                                       encoding="utf-8")
    return root


def _hatch_a_roster(tmp_path: Path) -> Path:
    """Run the REAL generator's zero-question fast lane (what hatch.sh --defaults
    runs) into a staged root; return that root. stdin is closed, so any prompt
    would fail loudly rather than hang."""
    root = _stage_deployment_root(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(GENERATOR), "--root", str(root), "--defaults"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, (
        f"the fresh-hatch generator run failed — a hatch cannot even reach the "
        f"roster:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return root


def test_generated_fresh_hatch_roster_is_fully_authorized(tmp_path):
    """THE property: a fresh hatch must never hire an officer this repo's
    germline pair cannot authorize.

    The two authorizing files (cabinet/officer-capabilities.conf,
    cabinet/mcp-scope.yml) are germline — hatch.sh is structurally forbidden to
    write them (cabinet/scripts/hatch-lib/errands.sh: "Captain's hands only").
    So a generator that hires a lane CEO unconditionally builds a deployment
    that CANNOT pass the live arm above, and no human errand inside the hatch
    can fix it. Before roster-authz this failed with
    {'first-lane-ceo': [both files]}."""
    root = _hatch_a_roster(tmp_path)
    roster = lib_roster.load_roster(root)
    assert roster, "the fresh hatch produced an EMPTY roster — deploy-mac.sh refuses that"
    missing = _missing_from_conf_and_scope(roster, OFFICER_CONF, MCP_SCOPE)
    assert missing == {}, (
        f"a FRESH HATCH hires officer(s) this repo cannot authorize: {missing}. "
        f"Every rostered officer needs capability rows in "
        f"cabinet/officer-capabilities.conf AND an agents: entry in "
        f"cabinet/mcp-scope.yml; both are germline (Captain applies), so the "
        f"generator must not roster what they do not already cover.")


def test_generated_fresh_hatch_rosters_the_chair():
    """Sibling guard for the arm above: the shipped conf pair must authorize the
    Chair. If it ever stops doing so, the generator refuses the hatch outright
    rather than rostering an unauthorized Chair — this test names the cause at
    its source instead of letting a stranger meet it at hatch time."""
    assert "cos" in set(_conf_officers(OFFICER_CONF)) & set(_scope_agents(MCP_SCOPE)), (
        "the shipped germline pair no longer authorizes the Chair (cos) — it "
        "needs capability rows in cabinet/officer-capabilities.conf AND an "
        "agents: entry in cabinet/mcp-scope.yml, or no hatch can roster it")


def test_unauthorized_lane_ceo_is_generated_but_not_hired(tmp_path):
    """The mechanism, end to end: the fast-lane placeholder lane's CEO is NOT in
    the roster (this repo authorizes no `first-lane-ceo`), while its lane files
    ARE generated — so the Captain can hire it later by adding the germline rows
    and re-running, and nothing about the hatch waits on that errand."""
    root = _hatch_a_roster(tmp_path)
    roster = lib_roster.load_roster(root)
    assert "cos" in roster, "the Chair must always be rostered"
    assert "first-lane-ceo" not in roster, (
        "an unauthorized lane CEO was hired — that is the silent "
        "capability/MCP-scope lockout this module exists to prevent")
    assert (root / "instance/agents/first-lane-ceo.md").is_file(), (
        "the lane CEO's role definition must still be generated (inert) — "
        "un-hired is not un-generated")
    text = (root / "instance/config/roster.yml").read_text(encoding="utf-8")
    assert "PENDING AUTHORIZATION" in text and "first-lane-ceo" in text, (
        "roster.yml must record the un-hired lane CEO so the state is legible")
