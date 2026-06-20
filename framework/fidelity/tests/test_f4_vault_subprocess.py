"""F4 foundation fix: vault search must run under the brain interpreter.

The harness runs in-process under system Python 3.9.6, whose sqlite3 has NO
loadable-extension support (`enable_load_extension` absent) — so the embeddings
vector extension cannot load and context_lib._fetch_vault silently returns 0
hits. The brain runs embeddings under python3.12. The default BrainAdapter
therefore routes gather_vault through a python3.12 subprocess that reuses
context_lib.gather wholesale; INJECTED context_lib/server stay in-process so
every existing test seam is preserved. The content_ts leak-fence in
gather_cutoff_context still runs on the returned hits (this fix changes only
WHERE the search executes, never WHETHER the fence applies).

Also covers the lessons cap-then-filter fix: BrainAdapter.drafting_lessons must
feed the FULL corpus to lessons_before (not draft_lib's pre-capped tail), so a
pre-cutoff lesson buried before the cap survives the date-filter.
"""

from __future__ import annotations

import shutil

import pytest

from framework.fidelity import officer_runner


class TestDefaultAdapterRoutesToSubprocess:
    def test_default_adapter_routes_to_vault_search(self):
        # No context_lib / server injected -> the default adapter must use the
        # vault_search seam (the subprocess path), NOT an in-process gather.
        captured = {}

        def fake_search(handle, topic=None):
            captured["handle"] = handle
            captured["topic"] = topic
            return {"hits": [{"text": "hit",
                              "content_ts": "2026-01-01T00:00:00+00:00",
                              "path": "p"}],
                    "topic_terms": ["x"]}

        brain = officer_runner.BrainAdapter(vault_search=fake_search)
        out = brain.gather_vault("ulrik", topic="garden budget")
        assert captured == {"handle": "ulrik", "topic": "garden budget"}
        assert out["hits"][0]["text"] == "hit"

    def test_injected_context_lib_stays_in_process(self):
        # An injected context_lib (test stub) MUST be delegated to in-process
        # with sources=["vault"] — never diverted to the subprocess. This
        # preserves the existing leak-integrity seam (test_f4_leakguard).
        seen = {}

        class StubContextLib:
            @staticmethod
            def gather(handle, *, sources=None, **kw):
                seen["sources"] = sources
                seen["handle"] = handle
                return {"hits": [], "brief": ""}

        def explode(handle, topic=None):  # must NOT be called
            raise AssertionError("injected context_lib must stay in-process")

        brain = officer_runner.BrainAdapter(
            context_lib=StubContextLib(), vault_search=explode)
        brain.gather_vault("ulrik", topic="t")
        assert seen == {"sources": ["vault"], "handle": "ulrik"}


class TestSubprocessGracefulDegrade:
    def test_graceful_on_missing_interpreter(self, monkeypatch):
        # A missing/invalid brain interpreter must degrade to empty hits, never
        # crash the harness (the case is scored context-thin, not aborted).
        monkeypatch.setenv("CABINET_BRAIN_PYTHON",
                           "/nonexistent/python-does-not-exist")
        out = officer_runner._subprocess_vault_gather("ulrik", "topic")
        assert out == {"hits": [], "topic_terms": None}

    def test_handle_with_traversal_is_rejected(self, monkeypatch):
        # Defense-in-depth (Corridor): a handle carrying path traversal must not
        # reach the subprocess — return empty rather than risk the runner using
        # it to build a vault path.
        out = officer_runner._subprocess_vault_gather("../../etc/passwd", "t")
        assert out == {"hits": [], "topic_terms": None}


class TestDraftingLessonsFullCorpus:
    def test_pre_cutoff_lesson_buried_before_cap_survives(self, monkeypatch,
                                                          tmp_path):
        # Cap-then-filter trap: draft_lib.drafting_lessons() returns only the
        # LAST 2500 chars. A pre-cutoff lesson buried before >2500 chars of
        # later lessons would be dropped before the date-filter sees it. The
        # fix passes the FULL corpus, so the early pre-cutoff block survives.
        import draft_lib
        early = "### 2026-01-01 — early\nthe early pre-cutoff lesson line\n\n"
        late = "### 2026-12-01 — late\n" + ("padding l0rem ipsum " * 200) + "\n"
        lessons = tmp_path / "Drafting-Lessons.md"
        lessons.write_text(early + late, encoding="utf-8")
        assert len(late) > 2500  # the early block is past the old cap
        monkeypatch.setattr(draft_lib, "LESSONS_FILE", lessons)

        brain = officer_runner.BrainAdapter()
        out = brain.drafting_lessons("2026-06-01T00:00:00+00:00")
        assert "early pre-cutoff lesson" in out   # survived (fix)
        assert "late" not in out                  # post-cutoff dropped (fence)


@pytest.mark.skipif(
    shutil.which("python3.12") is None,
    reason="brain interpreter python3.12 not available")
class TestRunnerIntegration:
    def test_runner_emits_json_contract(self):
        # The runner, executed under python3.12, must emit a JSON object with a
        # "hits" list — even for an unknown handle (empty hits, never a crash).
        out = officer_runner._subprocess_vault_gather(
            "no-such-person-xyz", "nothing topical here")
        assert isinstance(out, dict)
        assert isinstance(out.get("hits"), list)
