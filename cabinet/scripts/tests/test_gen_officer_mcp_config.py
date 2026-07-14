"""Tests for cabinet/scripts/gen-officer-mcp-config.py (audit 2026-07-07 #4,
structural MCP scoping — non-germline half).

Contract under test:
  * scope fixture → per-officer config filtered to (agent mcps ∪ universal ∪
    extra-allow); settings overlay pins `enableAllProjectMcpServers: false`
    and NOTHING else (no `allowedMcpServers` — managed-settings-only key
    whose overlay validation blocked officer boot on CC 2.1.202);
  * FAIL CLOSED on every degraded input: corrupt/missing scope, unknown
    officer, unparseable merged config → EMPTY server set, never fail open;
  * extra-allow is IGNORED when the scope parse fails (infra pass-through
    must not mask a fail-closed boot);
  * parser semantics mirror pre-tool-use.sh §9 (universal merge, scaffolds
    section, case-insensitive membership, "_" pseudo-key strip).

Run: cd cabinet/scripts && python3 -m pytest tests/test_gen_officer_mcp_config.py -v
(or from the repo root: python3.12 -m pytest cabinet/scripts/tests/test_gen_officer_mcp_config.py -v)
"""

from __future__ import annotations

import importlib.util as _ilu
import json
import os
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent

# gen-officer-mcp-config.py is hyphenated — load via importlib (same pattern
# as test_generate_instance.py).
spec = _ilu.spec_from_file_location(
    "gen_officer_mcp_config_under_test", _SCRIPTS_DIR / "gen-officer-mcp-config.py"
)
gen = _ilu.module_from_spec(spec)
spec.loader.exec_module(gen)


# ---------------------------------------------------------------------------
# Fixtures — fictional scope + merged config (no live deployment specifics)
# ---------------------------------------------------------------------------

SCOPE_FIXTURE = """\
# fixture mcp-scope.yml
cabinet: main

agents:
  alpha:
    mcps: [neon, vercel, brain]
    rationale: >
      Engineering-grade lane scope.

  beta:
    mcps: [notion]
    rationale: >
      Coordination only.

scaffolds:
  gamma:
    mcps: [notion, library]
    rationale: >
      Reserved, not hired.

universal: [telegram, library, cabinet]
"""

MERGED_FIXTURE = {
    "mcpServers": {
        "neon": {"command": "npx", "args": ["neon-mcp"]},
        "vercel": {"command": "npx", "args": ["vercel-mcp"]},
        "brain": {"command": "python3", "args": ["bridge.py"]},
        "notion": {"command": "npx", "args": ["notion-mcp"]},
        "library": {"command": "bun", "args": ["library.ts"]},
        "linear": {"command": "npx", "args": ["linear-mcp"]},
        "redis-trigger-channel": {"command": "bun", "args": ["index.ts"]},
        "_comment_layer": "doc pseudo-entry, never bootable",
    },
    "otherTopLevel": {"kept": True},
}


@pytest.fixture()
def paths(tmp_path):
    scope = tmp_path / "mcp-scope.yml"
    scope.write_text(SCOPE_FIXTURE)
    merged = tmp_path / "merged.json"
    merged.write_text(json.dumps(MERGED_FIXTURE))
    return {
        "scope": scope,
        "merged": merged,
        "out_mcp": tmp_path / "officer-mcp.json",
        "out_settings": tmp_path / "officer-settings.json",
    }


def run_main(paths, officer, extra_allow=""):
    rc = gen.main(
        [
            "--officer", officer,
            "--scope", str(paths["scope"]),
            "--input", str(paths["merged"]),
            "--extra-allow", extra_allow,
            "--out-mcp", str(paths["out_mcp"]),
            "--out-settings", str(paths["out_settings"]),
        ]
    )
    mcp = json.loads(paths["out_mcp"].read_text())
    settings = json.loads(paths["out_settings"].read_text())
    return rc, mcp, settings


# ---------------------------------------------------------------------------
# Happy path — scope fixture → expected config
# ---------------------------------------------------------------------------

def test_scope_fixture_filters_to_grants(paths):
    rc, mcp, settings = run_main(paths, "alpha")
    assert rc == 0
    # agent mcps ∪ universal, intersected with what the merged config defines
    assert sorted(mcp["mcpServers"]) == ["brain", "library", "neon", "vercel"]
    # unscoped servers are gone
    assert "linear" not in mcp["mcpServers"]
    assert "notion" not in mcp["mcpServers"]
    assert "redis-trigger-channel" not in mcp["mcpServers"]
    # server specs pass through untouched
    assert mcp["mcpServers"]["neon"] == MERGED_FIXTURE["mcpServers"]["neon"]
    # non-mcpServers top-level keys preserved
    assert mcp["otherTopLevel"] == {"kept": True}


def test_settings_overlay_carries_no_managed_policy_keys(paths):
    """Regression (2026-07-07 fleet boot-block): `allowedMcpServers` is a
    managed-settings-only policy key — never honored from a --settings
    overlay — but CC 2.1.202 schema-validates overlay content, and a grant
    mirror under that key BLOCKED officer boot with an interactive
    "Invalid entry" dialog on the rolling restart. The overlay must stay
    exactly the project-auto-approval pin; scoping is enforced by the
    filtered --mcp-config + --strict-mcp-config pair.

    Merge note (germline window 2): the branch-side object-shape mirror
    tests (`_allowed_names`) were repairs for the pre-drop generator; the
    base's mirror REMOVAL supersedes them — mirror stays dropped."""
    rc, _, settings = run_main(paths, "alpha")
    assert rc == 0
    assert "allowedMcpServers" not in settings
    assert settings == {"enableAllProjectMcpServers": False}


# ---------------------------------------------------------------------------
# AUD-8 sandbox pilot — the per-officer overlay is the comms-only surface
# (the shared config home applies fleet-wide; see sandbox_pilot_block()).
# ---------------------------------------------------------------------------

def test_sandbox_pilot_block_lands_for_pilot_officer(paths, monkeypatch):
    monkeypatch.setenv("CABINET_SANDBOX_PILOT_OFFICERS", "alpha")
    rc, _, settings = run_main(paths, "alpha")
    assert rc == 0
    sb = settings["sandbox"]
    assert sb["enabled"] is True
    deny = sb["filesystem"]["denyWrite"]
    allow = sb["filesystem"]["allowWrite"]
    # absolute, fully-expanded paths only — no placeholders, no literal "~"
    assert deny and all(os.path.isabs(p) for p in deny)
    assert all("~" not in p and "<" not in p for p in deny + allow)
    # the standing enforcement canary (the only non-schg deny path — proves
    # the SANDBOX layer distinctly from schg)
    assert any(p.endswith("cabinet/cache/sandbox-deny-canary") for p in deny)
    # germline heads present
    assert any(p.endswith("cabinet/scripts/hooks") for p in deny)
    assert any(p.endswith("cabinet/mcp-scope.yml") for p in deny)
    # sandbox narrows default writes to cwd+session-temp: trigger-ACK ids
    # files live at /tmp/.trigger_ids_* — /tmp must stay writable
    assert "/tmp" in allow and "/private/tmp" in allow
    # Go CLIs fail TLS under Seatbelt
    assert sb["excludedCommands"] == ["gh *"]
    # base project-auto-approval pin unchanged
    assert settings["enableAllProjectMcpServers"] is False


def test_sandbox_pilot_absent_for_non_pilot_officer(paths, monkeypatch):
    monkeypatch.setenv("CABINET_SANDBOX_PILOT_OFFICERS", "alpha")
    rc, _, settings = run_main(paths, "beta")
    assert rc == 0
    assert settings == {"enableAllProjectMcpServers": False}


def test_sandbox_pilot_default_set_is_comms_officer_only(monkeypatch):
    monkeypatch.delenv("CABINET_SANDBOX_PILOT_OFFICERS", raising=False)
    assert gen.sandbox_pilot_officers() == {"comms-officer"}


def test_sandbox_pilot_env_off_switch(paths, monkeypatch):
    for off in ("", "   ", "none", "NONE"):
        monkeypatch.setenv("CABINET_SANDBOX_PILOT_OFFICERS", off)
        assert gen.sandbox_pilot_officers() == set()
    monkeypatch.setenv("CABINET_SANDBOX_PILOT_OFFICERS", "none")
    rc, _, settings = run_main(paths, "alpha")
    assert rc == 0
    assert "sandbox" not in settings


def test_sandbox_pilot_env_csv_multi_officer(monkeypatch):
    monkeypatch.setenv("CABINET_SANDBOX_PILOT_OFFICERS", "alpha, beta")
    assert gen.sandbox_pilot_officers() == {"alpha", "beta"}


def test_sandbox_pilot_applies_even_when_scope_fails_closed(paths, monkeypatch):
    """Containment must never depend on the scope parse: a fail-closed boot
    (officer unlisted -> empty MCP set) still gets the sandbox layer."""
    monkeypatch.delenv("CABINET_SANDBOX_PILOT_OFFICERS", raising=False)
    rc, mcp, settings = run_main(paths, "comms-officer")
    assert rc == 0
    assert mcp["mcpServers"] == {}  # fail-closed (not in fixture scope)
    assert settings["sandbox"]["enabled"] is True


def test_universal_merge_applies_to_every_agent(paths):
    rc, mcp, _ = run_main(paths, "beta")
    assert rc == 0
    # beta's own list is [notion]; "library" boots only via the universal
    # merge (telegram/cabinet are universal too but absent from the merged
    # config, so they cannot boot)
    assert sorted(mcp["mcpServers"]) == ["library", "notion"]


def test_scaffold_agents_parse_like_the_hook(paths):
    # The hook's cache builder includes scaffolds; the generator mirrors it.
    rc, mcp, _ = run_main(paths, "gamma")
    assert rc == 0
    assert sorted(mcp["mcpServers"]) == ["library", "notion"]


def test_extra_allow_infra_passthrough(paths):
    rc, mcp, _ = run_main(paths, "alpha", extra_allow="redis-trigger-channel,cua")
    assert rc == 0
    assert "redis-trigger-channel" in mcp["mcpServers"]
    # cua granted but not defined in the merged config → never fabricated
    assert "cua" not in mcp["mcpServers"]


def test_pseudo_underscore_keys_always_stripped(paths):
    rc, mcp, _ = run_main(paths, "alpha", extra_allow="_comment_layer")
    assert rc == 0
    assert "_comment_layer" not in mcp["mcpServers"]


def test_membership_is_case_insensitive_like_the_hook(paths, tmp_path):
    merged = {"mcpServers": {"Neon": {"command": "x"}}}
    paths["merged"].write_text(json.dumps(merged))
    rc, mcp, _ = run_main(paths, "alpha")
    assert rc == 0
    assert "Neon" in mcp["mcpServers"]


# ---------------------------------------------------------------------------
# FAIL CLOSED — every degraded input yields an EMPTY server set
# ---------------------------------------------------------------------------

def _assert_fail_closed(mcp, settings):
    assert mcp["mcpServers"] == {}
    assert "allowedMcpServers" not in settings
    assert settings["enableAllProjectMcpServers"] is False


def test_corrupt_scope_fails_closed(paths, capsys):
    paths["scope"].write_text("%% not: [yaml {{{\n\t/dev/null\n")
    rc, mcp, settings = run_main(paths, "alpha")
    assert rc == 0
    _assert_fail_closed(mcp, settings)
    assert "[ERROR]" in capsys.readouterr().err


def test_missing_scope_file_fails_closed(paths, capsys):
    paths["scope"].unlink()
    rc, mcp, settings = run_main(paths, "alpha")
    assert rc == 0
    _assert_fail_closed(mcp, settings)
    assert "[ERROR]" in capsys.readouterr().err


def test_unknown_officer_fails_closed_not_warn_and_allow(paths, capsys):
    rc, mcp, settings = run_main(paths, "mallory")
    assert rc == 0
    _assert_fail_closed(mcp, settings)
    err = capsys.readouterr().err
    assert "[ERROR]" in err and "mallory" in err


def test_extra_allow_ignored_when_scope_parse_fails(paths):
    # Infra pass-through must NOT leak servers past a fail-closed boot.
    paths["scope"].write_text("garbage")
    rc, mcp, settings = run_main(paths, "alpha", extra_allow="redis-trigger-channel")
    assert rc == 0
    _assert_fail_closed(mcp, settings)


def test_unparseable_merged_config_fails_closed(paths, capsys):
    paths["merged"].write_text("{not json")
    rc, mcp, settings = run_main(paths, "alpha")
    assert rc == 0
    assert mcp == {"mcpServers": {}}
    # overlay is grant-independent — no managed policy keys in any path
    assert "allowedMcpServers" not in settings
    assert "[ERROR]" in capsys.readouterr().err


def test_missing_merged_config_fails_closed(paths):
    paths["merged"].unlink()
    rc, mcp, _ = run_main(paths, "alpha")
    assert rc == 0
    assert mcp == {"mcpServers": {}}


def test_merged_config_non_object_fails_closed(paths):
    paths["merged"].write_text(json.dumps(["not", "an", "object"]))
    rc, mcp, _ = run_main(paths, "alpha")
    assert rc == 0
    assert mcp == {"mcpServers": {}}


# ---------------------------------------------------------------------------
# Parser parity — semantics the hook's cache builder guarantees
# ---------------------------------------------------------------------------

def test_parse_scope_matches_hook_semantics():
    scope_map = gen.parse_scope(SCOPE_FIXTURE)
    assert scope_map["alpha"] == ["neon", "vercel", "brain", "telegram", "library", "cabinet"]
    # universal dedup: beta's own list first, universals appended
    assert scope_map["beta"] == ["notion", "telegram", "library", "cabinet"]
    # library already present in gamma's own list → not duplicated by merge
    assert scope_map["gamma"] == ["notion", "library", "telegram", "cabinet"]


DUP_SCOPE_FIXTURE = SCOPE_FIXTURE + """\

agents:
  alpha:
    mcps: [linear]
    rationale: >
      DUPLICATE key — must lose to the first alpha entry.
"""


def test_duplicate_agent_key_first_wins_and_errors(capsys):
    """Finding mcp-config-2: the hook's cache lookup is awk first-match
    (`$1==a{print $2; exit}`); the generator used to keep the LAST entry,
    so a duplicate key gave the officer different grant sets at boot vs
    call time. First entry must win here too, with a loud [ERROR]."""
    scope_map = gen.parse_scope(DUP_SCOPE_FIXTURE)
    assert scope_map["alpha"] == ["neon", "vercel", "brain", "telegram", "library", "cabinet"]
    assert "linear" not in scope_map["alpha"]
    err = capsys.readouterr().err
    assert "[ERROR]" in err and "duplicate" in err and "alpha" in err


def _run_hook_cache_builder(scope_text: str, tmp_path) -> dict:
    """Run the ACTUAL pre-tool-use.sh §9 embedded cache builder (extracted
    from the hook source) on scope_text, then apply the hook's awk
    first-match lookup semantics to the TSV it writes."""
    import subprocess
    import sys as _sys

    hook_src = (_SCRIPTS_DIR / "hooks" / "pre-tool-use.sh").read_text().splitlines()
    marker = "\"$MCP_SCOPE_FILE\" \"$MCP_SCOPE_CACHE\" <<'PY'"
    start = next(i for i, l in enumerate(hook_src) if marker in l)
    end = next(i for i in range(start + 1, len(hook_src)) if hook_src[i] == "PY")
    code = "\n".join(hook_src[start + 1 : end])

    scope = tmp_path / "hook-scope.yml"
    scope.write_text(scope_text)
    cache = tmp_path / "hook-scope.tsv"
    # Same invocation shape as the hook: python3 - <src> <dst> <<'PY'
    subprocess.run(
        [_sys.executable, "-", str(scope), str(cache)],
        input=code, text=True, check=True,
    )
    hook_map = {}
    for line in cache.read_text().splitlines():
        if not line.strip():
            continue
        agent, csv = line.split("\t", 1)
        # awk `$1==a{print $2; exit}` — FIRST match wins
        hook_map.setdefault(agent, [m for m in csv.split(",") if m])
    return hook_map


def test_parity_with_hook_cache_builder(tmp_path, capsys):
    """The structural plane (this generator) and the call-time plane (the
    hook's cache builder + awk lookup) must resolve IDENTICAL grant sets —
    including on a scope file with a duplicate agent key."""
    for fixture in (SCOPE_FIXTURE, DUP_SCOPE_FIXTURE):
        hook_map = _run_hook_cache_builder(fixture, tmp_path)
        gen_map = gen.parse_scope(fixture)
        assert gen_map == hook_map
    capsys.readouterr()  # swallow the expected duplicate-key [ERROR]


def test_parse_scope_section_reset_on_other_top_level_key():
    text = SCOPE_FIXTURE + "\nother_key: 1\n  sneaky:\n    mcps: [neon]\n"
    scope_map = gen.parse_scope(text)
    assert "sneaky" not in scope_map


def test_output_files_are_0600(paths):
    rc, _, _ = run_main(paths, "alpha")
    assert rc == 0
    assert (paths["out_mcp"].stat().st_mode & 0o777) == 0o600
    assert (paths["out_settings"].stat().st_mode & 0o777) == 0o600
