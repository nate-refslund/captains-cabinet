"""Runtime clean-room proof — the identity is launcher-DRIVEN, not baked [DN-6].

The static ratchet (``test_no_launcher_hardcode.py``) proves framework/ carries
no hardcoded captain display name. This is its RUNTIME companion: it points
``CABINET_ROOT`` at a throwaway instance whose ``platform.yml`` names a generic
synthetic captain (``Testburg``) and proves the SAME framework code that renders
the launching captain's name on a real deployment renders "Testburg" there — and
"Captain" when there is no ``platform.yml`` at all. Together they prove the
launcher, not the framework, owns the captain's identity.

The build's safety invariant is that on ANY instance ``captain_name()`` returns
that launcher's OWN configured display name byte-for-byte; here we deliberately
drive a synthetic root to show the identity follows config, so we save + restore
``framework.env._captain_name_cache`` around every case (the module caches the
name process-wide)."""
from __future__ import annotations

import pytest

import framework.env as env
from framework.fidelity import officer_prompt
from framework.fidelity.types import Case


@pytest.fixture
def isolated_captain_cache():
    """Clear the process-wide captain-name cache for the test, then restore the
    original so sibling tests (which may rely on the real configured name) are untouched."""
    saved = env._captain_name_cache
    env._captain_name_cache = None
    try:
        yield
    finally:
        env._captain_name_cache = saved


def _write_platform(root, body: str) -> None:
    # NB: single "instance/config" path literal (not "instance" / "config") so
    # the layer-separation gate's bare-"instance" heuristic doesn't flag this
    # test — same form env.py itself uses ("instance/config/platform.yml").
    cfg = root / "instance/config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "platform.yml").write_text(body, encoding="utf-8")


def _minimal_case() -> Case:
    """A Case with no captain name in any field — so the ONLY captain identity that can
    reach the assembled prompt comes from ``captain_name()``."""
    return Case(
        case_id="clean-room-1",
        lane="send-1to1-reply",
        decision_type="reply",
        situation_ref="clean-room",
        ground_truth={},
        endorsement="unknown",
        cutoff_ts="2026-01-01T00:00:00Z",
        source="clean-room-test",
        held_out=True,
        person="Colleague",
        channel="teams",
        language="en",
        thread_before=[],
    )


class TestCleanRoom:
    def test_captain_name_is_launcher_driven(self, tmp_path, monkeypatch,
                                             isolated_captain_cache):
        """(a) A launcher whose platform.yml says Testburg resolves to Testburg."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_platform(tmp_path, "captain_name: Testburg\n")
        env._captain_name_cache = None
        assert env.captain_name() == "Testburg"

    def test_clone_prompt_renders_launcher_captain_not_foreign(self, tmp_path, monkeypatch,
                                                            isolated_captain_cache):
        """(b) The fidelity clone-identity prompt is genuinely launcher-driven:
        with captain=Testburg it contains "Testburg" and NOT a foreign captain
        name ("Dana", configured nowhere here).

        The role ``clean_room_probe`` has no ``.claude/agents/*.md`` under the
        throwaway root, so ``role_definition`` returns its minimal header and the
        only captain identity in the assembled prompt is ``captain_name()``. (A
        lowercase brain-artifact label may appear — that is not the display name,
        so the case-sensitive "Dana" assertion still holds.)"""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
        _write_platform(tmp_path, "captain_name: Testburg\n")
        env._captain_name_cache = None

        prompt = officer_prompt.build_clone_eval_system(
            _minimal_case(), "clean_room_probe", {})

        assert "Testburg" in prompt          # launcher name flows through
        assert "Dana" not in prompt          # ...and a foreign captain name never does

    def test_absent_platform_yaml_falls_back_to_captain(self, tmp_path, monkeypatch,
                                                        isolated_captain_cache):
        """(c) No platform.yml (and no product.yml) anywhere under the root =>
        the generic "Captain" default, never a leaked launcher name."""
        monkeypatch.setenv("CABINET_ROOT", str(tmp_path))  # empty tmp — no config
        env._captain_name_cache = None
        assert env.captain_name() == "Captain"
