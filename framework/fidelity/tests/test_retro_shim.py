from __future__ import annotations

import pytest

from framework.fidelity import retro


def _load_retro_lib():
    """The pipe module the shim wraps, loaded the same way the shim loads it."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_retro_lib_under_test", retro.RETRO_PIPE_DIR / "lib.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestRetroShim:
    def test_reexports_scoring_symbols(self):
        for name in (
            "extract_cases", "score_case", "judge_decision", "score_draft",
            "author_centroid", "aggregate", "cusum", "mechanics_flags",
            "parse_json_block", "lessons_before", "parse_conversations",
            "cosine",
        ):
            assert hasattr(retro, name), f"retro shim missing {name}"
            assert callable(getattr(retro, name)), f"{name} not callable"

    def test_reexports_constants(self):
        assert isinstance(retro.JUDGE_SYSTEM, str) and retro.JUDGE_SYSTEM
        assert isinstance(retro.BASELINE_SYSTEM, str) and retro.BASELINE_SYSTEM
        assert isinstance(retro.RETRO_ADDENDUM, str) and retro.RETRO_ADDENDUM
        # LLM_MODEL is RE-EXPORTED from the retrodiction pipe, which lives
        # OUTSIDE this repo (RETRO_PIPE_DIR). Pinning its literal value here
        # pinned somebody else's file: the pipe moved to a newer model and this
        # arm went red on a tree that had not changed, on a machine that has the
        # pipe, while CI — which does not — never saw it. What this shim owes is
        # that it hands back what the source holds, so that is what is asserted.
        assert isinstance(retro.LLM_MODEL, str) and retro.LLM_MODEL
        source = _load_retro_lib()
        assert retro.LLM_MODEL == source.LLM_MODEL, (
            "the shim re-exports a DIFFERENT model id than the pipe it wraps"
        )

    def test_judge_system_is_decision_only(self):
        # The decision-only contract is the sacred reuse boundary (style is
        # scored via Voyage, not the judge). Lock the marker phrasing.
        assert "IGNORE style" in retro.JUDGE_SYSTEM
        assert "MODEL-DRAFTED reply" in retro.JUDGE_SYSTEM

    def test_retro_available_true_when_pipe_present(self):
        assert retro.retro_available() is True
        assert retro.RETRO_PIPE_DIR.joinpath("lib.py").exists()

    def test_retro_lib_imports_under_framework_python(self):
        # Guards the 3.9.6 import boundary: a future 3.10+-only construct in
        # the upstream lib must fail HERE, not mid-batch. Touch a real symbol.
        assert callable(retro.extract_cases)
        assert isinstance(retro.cosine([1.0, 0.0], [1.0, 0.0]), float)
