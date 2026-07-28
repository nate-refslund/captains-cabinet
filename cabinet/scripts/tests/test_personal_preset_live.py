"""``presets/personal/`` is ACTIVATABLE, and is not a C-suite — 2026-07-27.

The finding this pins (altitude direction gate, 2026-07-26): every shipped
preset stood up a C-suite — cos/cto/cpo/cro/coo — for a company the operator
does not run, and the ONE preset shaped for a non-company operator was empty
and FORBIDDEN ("Placeholder … Empty until Phase 2"; "Do not `echo personal >
instance/config/active-preset`"). The altitude the north-star ruling names as
the MAJORITY case was the one configuration that shipped inert.

Each arm below is a separate way that inertness was enforced, so each fails
against the pre-change tree:

  * the README forbade activation                    -> test_readme_*
  * no validate.sh, which cabinet-bootstrap.sh treats
    as a HARD GATE failure by name                   -> test_validate_*
  * no measurement seed, which the self-improvement
    validation gate fails CLOSED on                  -> test_ships_role_scenario
  * a roster with no working roles at all            -> test_roster_*
  * load-preset.sh had never been run against it     -> test_load_preset_*

Plus the two claim-surface arms: the roster must stay free of C-suite roles
(the mismatch that made the first briefing read as irrelevant), and the copy
must NOT promise growing autonomy at this altitude — the six hard ceilings
belong to whoever owns the resources, so an authority ladder cannot climb
there and saying otherwise is a promise a stranger will find out is false.

Run: python3.12 -m pytest cabinet/scripts/tests/test_personal_preset_live.py -q
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_SCRIPTS = Path(__file__).resolve().parent.parent
_REPO = _SCRIPTS.parent.parent
_PRESET = _REPO / "presets" / "personal"
_LOAD_PRESET = _SCRIPTS / "load-preset.sh"

#: Roles that imply a function with people under it. The operator this preset
#: serves has neither, and shipping the org chart of a company they do not run
#: is exactly the mismatch the altitude gate found.
_C_SUITE = ("cos", "cto", "cpo", "cro", "coo",
            "compliance-officer", "operations-officer", "executive-assistant")


def _preset_yml() -> dict:
    return yaml.safe_load((_PRESET / "preset.yml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The README no longer forbids the thing it describes
# ---------------------------------------------------------------------------
def test_readme_does_not_forbid_activation():
    text = (_PRESET / "README.md").read_text(encoding="utf-8")
    forbidding = re.search(
        r"Do not\s+`?echo personal\s*>\s*instance/config/active-preset", text)
    assert forbidding is None, (
        "presets/personal/README.md still forbids activating the preset")


def test_readme_declares_the_preset_active_and_shows_how():
    text = (_PRESET / "README.md").read_text(encoding="utf-8")
    assert "**Status: active.**" in text
    assert "echo personal > instance/config/active-preset" in text


def test_readme_promises_context_not_permission():
    """The corrected promise (altitude gate D3). Growth at this altitude is
    CONTEXT AND LEVERAGE, not permission: the six ceiling classes belong to
    whoever owns the resources, so no posture, ladder or evidence can climb
    there. Copy claiming otherwise is false and a stranger finds out."""
    text = (_PRESET / "README.md").read_text(encoding="utf-8")
    assert "It promises context and leverage." in text
    assert "It does not promise growing authority" in text
    lowered = text.lower()
    for banned in ("grow into running the company",
                   "eventually run the company",
                   "more autonomy over time",
                   "earn more authority"):
        assert banned not in lowered, (
            f"personal README promises expanding authority: {banned!r}")


# ---------------------------------------------------------------------------
# The activation gates the preset previously could not pass
# ---------------------------------------------------------------------------
def test_validate_sh_exists_and_passes():
    """cabinet-bootstrap.sh: a preset with no validate.sh cannot pass its hard
    gate ("Preset '<slug>' has no validate.sh"). This preset had none."""
    script = _PRESET / "validate.sh"
    assert script.is_file(), "presets/personal/validate.sh is missing"
    assert subprocess.run(["bash", "-n", str(script)],
                          capture_output=True).returncode == 0
    done = subprocess.run(["bash", str(script)], capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr


def test_ships_role_scenario_so_the_self_improvement_gate_can_run():
    """``_run_scenario_evals_for_validation`` fails CLOSED on zero
    role/learning scenarios — an activatable preset with no seed bricks it."""
    sdir = _PRESET / "measurement" / "scenarios"
    assert sdir.is_dir()
    pat = re.compile(r"""category\s*=\s*["'](?:role|learning)["']""")
    hits = [f.name for f in sorted(sdir.glob("*.py"))
            if f.name != "__init__.py" and pat.search(f.read_text())]
    assert hits, "presets/personal ships no role/learning scenario"


def test_load_preset_assembles_the_runtime_from_this_preset(tmp_path):
    """End to end through the real loader: constitution + safety boundaries
    are assembled from the framework bases and THIS preset's addenda.
    Hermetic — scratch CABINET_ROOT, scratch runtime dir, no DB env."""
    root = tmp_path / "root"
    (root / "framework").mkdir(parents=True)
    for base in ("constitution-base.md", "safety-boundaries-base.md"):
        shutil.copy(_REPO / "framework" / base, root / "framework" / base)
    shutil.copytree(_PRESET, root / "presets" / "personal")
    cfg = root / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "active-preset").write_text("personal\n", encoding="utf-8")

    env = dict(os.environ)
    env["CABINET_ROOT"] = str(root)
    env["CABINET_RUNTIME_DIR"] = str(tmp_path / "runtime")
    for k in ("NEON_CONNECTION_STRING", "DATABASE_URL", "CABINET_ID",
              "CABINET_MODE"):
        env.pop(k, None)
    done = subprocess.run(["bash", str(_LOAD_PRESET)], cwd=_REPO, env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert "Loading preset: personal" in done.stderr

    constitution = (tmp_path / "runtime" / "constitution.md").read_text()
    safety = (tmp_path / "runtime" / "safety-boundaries.md").read_text()
    assert "Preset Addendum: personal" in constitution
    assert "Coaching Principles" in constitution
    assert "Preset Safety Addendum: personal" in safety
    assert "Privacy redaction defaults" in safety


# ---------------------------------------------------------------------------
# The roster: real roles, and no C-suite
# ---------------------------------------------------------------------------
def test_roster_ships_working_roles():
    archetypes = _preset_yml()["agent_archetypes"]
    for slug in ("navigator", "librarian", "reviewer"):
        assert slug in archetypes, f"personal preset lost the {slug} role"
        card = _PRESET / "agents" / f"{slug}.md"
        assert card.is_file(), f"{slug} declared but presets/personal/agents/{slug}.md is absent"
        assert len(card.read_text(encoding="utf-8")) > 500


def test_roster_carries_no_c_suite():
    archetypes = set(_preset_yml()["agent_archetypes"])
    assert not (archetypes & set(_C_SUITE)), (
        f"personal preset declares C-suite archetypes: "
        f"{sorted(archetypes & set(_C_SUITE))}")
    on_disk = {p.stem for p in (_PRESET / "agents").glob("*.md")}
    assert not (on_disk & set(_C_SUITE)), (
        f"presets/personal/agents ships C-suite role cards: "
        f"{sorted(on_disk & set(_C_SUITE))}")


def test_every_declared_archetype_has_a_card():
    """A declared-but-absent archetype is a roster that lies about itself."""
    for slug in _preset_yml()["agent_archetypes"]:
        assert (_PRESET / "agents" / f"{slug}.md").is_file(), (
            f"archetype {slug} has no role card")


@pytest.mark.parametrize("preset", ("work", "developer", "portfolio"))
def test_the_other_presets_really_are_c_suite_shaped(preset):
    """The contrast this preset exists to answer, measured rather than
    asserted: every other shipped preset really does stand up officers named
    for functions of a company. If that ever stops being true, the framing in
    presets/personal/README.md needs rewriting, not quietly leaving."""
    agents = {p.stem for p in (_REPO / "presets" / preset / "agents").glob("*.md")}
    assert agents & set(_C_SUITE), (
        f"presets/{preset} no longer ships any C-suite role — the personal "
        f"preset's stated contrast is now stale")


# ---------------------------------------------------------------------------
# The interview a STRANGER is walked through must describe the recall binding
# the generator ACTUALLY emits.
#
# Paid 2026-07-28. When presets/personal went live (2026-07-27) the generator
# began emitting a personal `sources.yml`, and cabinet/docs/provisioning-
# personal-cabinet.md was updated in the same commit — but
# .claude/skills/cabinet-init/SKILL.md, the document that shapes the
# onboarding INTERVIEW, kept saying "`flavor: personal` emits NO sources.yml —
# a Flavor-A captain binds their own personal adapter by hand". A stranger
# following the interview would have hand-bound an adapter the generator had
# already bound, or concluded personal recall was unsupported. Docs track code
# in the same commit; this is the sensor that makes that checkable rather than
# remembered.
# ---------------------------------------------------------------------------
_INTERVIEW = _REPO / ".claude" / "skills" / "cabinet-init" / "SKILL.md"
_GENERATOR = _SCRIPTS / "generate-instance.py"


def _generator_personal_adapter() -> str:
    """The adapter the generator really binds on ``flavor: personal``, read
    out of the generator itself.

    DERIVED, never hardcoded: that is the whole point. If the code ever
    reverts to emitting nothing for personal, this extractor's own assertions
    fire — so the pair fails loudly instead of the doc quietly rotting back
    into agreement with a defect."""
    text = _GENERATOR.read_text(encoding="utf-8")
    m = re.search(r'^LOCAL_SOURCE_ADAPTER\s*=\s*"([^"]+)"', text, re.M)
    assert m, (
        "generate-instance.py no longer defines LOCAL_SOURCE_ADAPTER — this "
        "extractor would silently pass on nothing; re-derive it before "
        "trusting this test")
    adapter = m.group(1).strip()
    assert adapter, "LOCAL_SOURCE_ADAPTER is empty — vacuous extraction"
    # >= 2 occurrences: the ``def`` PLUS at least one call site. Checking for
    # the bare name would pass on a dead function whose call had been deleted —
    # which is precisely the shape the original defect had (a renderer that
    # existed and was never reached).
    renders = text.count("render_sources_personal(")
    assert renders >= 2, (
        f"render_sources_personal appears {renders}x in generate-instance.py "
        f"(definition only, no call site) — the personal flavor renders "
        f"nothing again; fix the code, not this test")
    return adapter


def test_interview_doc_names_the_personal_recall_binding():
    """Doc-to-code coupling: whatever personal flavor binds, the interview
    names it."""
    assert _INTERVIEW.is_file(), f"{_INTERVIEW} is missing"
    adapter = _generator_personal_adapter()
    text = _INTERVIEW.read_text(encoding="utf-8")
    assert adapter in text, (
        f"the cabinet-init interview never names {adapter!r}, which is what "
        f"`autonomy.flavor: personal` actually binds — a stranger is being "
        f"interviewed against stale behaviour")


@pytest.mark.parametrize("claim", [
    "emits NO sources.yml",
    "binds their own personal adapter by hand",
])
def test_interview_doc_does_not_claim_personal_is_unbound(claim):
    """The two literal false sentences that shipped, pinned so a revert of the
    doc is caught even if the code stays right."""
    text = " ".join(_INTERVIEW.read_text(encoding="utf-8").split())
    assert claim.lower() not in text.lower(), (
        f"cabinet-init SKILL.md still claims {claim!r}; `flavor: personal` "
        f"has emitted a generated sources.yml since 2026-07-27")
