"""Flavor-A adapter internals — the screenpipe calls INLINED into ScreenpipeSource.

These pin the byte-identical behavior of the former
``framework.fidelity.officer_runner.BrainAdapter`` bodies now that they live on
``flavor_a.screenpipe_source.ScreenpipeSource`` (SRC-3 re-home). Moved here from
``framework/fidelity/tests`` (test_f4_vault_subprocess / test_f4_clone_identity +
the leakguard scoping guards) because they construct the adapter with its
in-process seams (``context_lib`` / ``server`` / ``vault_search``) — an adapter
detail that belongs with the adapter, not with the framework leak-fence.

The vault-search subprocess seam + the injected-in-process scoping use injected
fakes (no estate). The DEFAULT-path lessons tests + the fake-``server`` lessons
date-filter need the real ``draft_lib`` / retro scoring lib, so they self-skip
when the screenpipe estate is absent (mirrors the framework fidelity conftest).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

# instance/flavor-a on sys.path so ``flavor_a`` imports; repo root so
# ``framework.*`` resolves. tests/ [0] flavor_a [1] flavor-a [2] instance [3] root [4]
_PKG_PARENT = Path(__file__).resolve().parents[2]   # instance/flavor-a
_REPO_ROOT = Path(__file__).resolve().parents[4]    # worktree / repo root
for _p in (str(_REPO_ROOT), str(_PKG_PARENT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flavor_a.screenpipe_source import ScreenpipeSource, _subprocess_vault_gather


def _retro_present() -> bool:
    d = Path(os.environ.get(
        "CABINET_RETRO_PIPE_DIR",
        str(Path.home() / ".screenpipe" / "pipes" / "retrodiction"))).expanduser()
    return (d / "lib.py").exists()


def _draft_lib_present() -> bool:
    return (Path.home() / ".screenpipe" / "pipes" / "_shared" / "draft_lib.py").exists()


_ESTATE = _retro_present() and _draft_lib_present()
_needs_estate = pytest.mark.skipif(
    not _ESTATE, reason="screenpipe estate (draft_lib + retrodiction lib) absent")


CUTOFF = "2026-06-10T12:00:00+00:00"


def _case():
    from framework.fidelity.types import Case
    return Case.from_retro_case({
        "case_id": "abc1234567",
        "reply_key": "msgraph|MID1",
        "slug": "ulrik", "person": "Ulrik", "channel": "msgraph",
        "language": "da", "reply_ts": CUTOFF, "subject": "Re: lon",
        "n_prior": 3,
        "thread_before": [
            {"slug": "ulrik", "person": "Ulrik",
             "date": "2026-06-09T08:00:00+00:00", "direction": "received",
             "who": "Ulrik <u@x>", "source": "msgraph", "to": "", "cc": "",
             "text": "kan vi snakke lon?"},
        ],
        "real_reply": "Ja, lad os tage det fredag.",
    })


# ---------------------------------------------------------------------------
# search() vault-search routing (was BrainAdapter.gather_vault) — the py3.9/3.12
# subprocess seam vs the injected in-process seam.
# ---------------------------------------------------------------------------
class TestSearchRoutesToSubprocess:
    def test_default_adapter_routes_to_vault_search(self):
        # No context_lib / server injected -> search() must use the vault_search
        # seam (the subprocess path), NOT an in-process gather.
        captured = {}

        def fake_search(handle, topic=None):
            captured["handle"] = handle
            captured["topic"] = topic
            return {"hits": [{"text": "hit",
                              "content_ts": "2026-01-01T00:00:00+00:00",
                              "path": "p"}],
                    "topic_terms": ["x"]}

        src = ScreenpipeSource(vault_search=fake_search)
        out = src.search("ulrik", topic="workshop budget")
        assert captured == {"handle": "ulrik", "topic": "workshop budget"}
        assert out["hits"][0]["text"] == "hit"

    def test_injected_context_lib_stays_in_process(self):
        # An injected context_lib (test stub) MUST be delegated in-process with
        # sources=["vault"] — never diverted to the subprocess. Preserves the
        # leak-integrity seam (test_f4_leakguard).
        seen = {}

        class StubContextLib:
            @staticmethod
            def gather(handle, *, sources=None, **kw):
                seen["sources"] = sources
                seen["handle"] = handle
                return {"hits": [], "brief": ""}

        def explode(handle, topic=None):  # must NOT be called
            raise AssertionError("injected context_lib must stay in-process")

        src = ScreenpipeSource(context_lib=StubContextLib(), vault_search=explode)
        src.search("ulrik", topic="t")
        assert seen == {"sources": ["vault"], "handle": "ulrik"}

    def test_real_adapter_scopes_sources_to_vault(self):
        # The default adapter's search MUST delegate to context_lib.gather with
        # sources=["vault"] EXACTLY — never the all-source fan-out (which fires
        # _fetch_sent / _fetch_screen / _fetch_monday = "now").
        seen = {}

        class StubContextLib:
            @staticmethod
            def gather(handle, *, sources=None, **kw):
                seen["sources"] = sources
                seen["handle"] = handle
                return {"hits": [], "brief": "", "counts": {}}

        src = ScreenpipeSource(context_lib=StubContextLib())
        src.search("ulrik")
        assert seen["sources"] == ["vault"]
        assert seen["handle"] == "ulrik"

    def test_tier2_fetcher_raises_if_invoked(self):
        # Wire a context_lib whose Tier-2 fetchers raise, and confirm the leak
        # fence (gather_cutoff_context, framework) drives the adapter vault-only.
        from framework.fidelity import officer_runner

        class TrapContextLib:
            @staticmethod
            def gather(handle, *, sources=None, **kw):
                if sources != ["vault"]:
                    raise AssertionError(
                        f"Tier-2 leak: gather called with sources={sources}")
                return {"hits": [], "brief": ""}

        class StubServer:
            @staticmethod
            def person_intel(slug):
                return ""

            @staticmethod
            def open_commitments(direction):
                return []

            @staticmethod
            def read_note(path):  # pragma: no cover - not exercised here
                raise AssertionError("read_note should not be called")

        brain = ScreenpipeSource(context_lib=TrapContextLib(), server=StubServer())
        out = officer_runner.gather_cutoff_context(_case(), brain=brain)
        assert "vault_hits" in out


class TestSubprocessGracefulDegrade:
    def test_graceful_on_missing_interpreter(self, monkeypatch):
        # A missing/invalid brain interpreter must degrade to empty hits, never
        # crash the harness (the case is scored context-thin, not aborted).
        monkeypatch.setenv("CABINET_BRAIN_PYTHON",
                           "/nonexistent/python-does-not-exist")
        out = _subprocess_vault_gather("ulrik", "topic")
        assert out == {"hits": [], "topic_terms": None}

    def test_handle_with_traversal_is_rejected(self):
        # Defense-in-depth (Corridor): a handle carrying path traversal must not
        # reach the subprocess — return empty rather than risk a vault path build.
        out = _subprocess_vault_gather("../../etc/passwd", "t")
        assert out == {"hits": [], "topic_terms": None}


@pytest.mark.skipif(
    shutil.which("python3.12") is None,
    reason="brain interpreter python3.12 not available")
class TestRunnerIntegration:
    def test_runner_emits_json_contract(self):
        # The runner, executed under python3.12, must emit a JSON object with a
        # "hits" list — even for an unknown handle (empty hits, never a crash).
        out = _subprocess_vault_gather("no-such-person-xyz", "nothing topical here")
        assert isinstance(out, dict)
        assert isinstance(out.get("hits"), list)


# ---------------------------------------------------------------------------
# clone-identity surface (voice / model_patterns / date-filtered lessons) — the
# injected-``server`` seam the person_intel / open_commitments / read_note methods
# already honor. Was BrainAdapter's clone-identity surface.
# ---------------------------------------------------------------------------
class _FakeServer:
    """A fake brain server honoring the injected-``server`` seam. Each method
    returns a distinctive source string the tests can assert on; drafting_lessons
    returns the RAW (unfiltered) lessons file so the adapter's own date-filter is
    what must drop the post-cutoff blocks. The server's ``nate_model_patterns``
    name is the brain-artifact kept verbatim (only the adapter METHOD renamed to
    ``model_patterns``, DE-NATE §3)."""

    def __init__(self, lessons_text: str = ""):
        self._lessons_text = lessons_text

    def voice_profile(self) -> str:
        return "VOICE-SOURCE: warm, direct, Danish for internal"

    def nate_model_patterns(self) -> str:
        return "[PRIVATE NATE-MODEL] PATTERNS-SOURCE: ships fast, hates ceremony"

    def drafting_lessons(self) -> str:
        return self._lessons_text


# A lessons file with blocks on three dates: two strictly before a 2026-06-10
# cutoff (must survive) and one ON the cutoff date (must be dropped entirely).
_LESSONS = """---
title: Drafting-Lessons
---

### 2026-05-01 — keep replies short
Nate prefers two sentences max on Teams.

### 2026-06-09 — answer the actual question
Do not punt; give the decision.

### 2026-06-10 — SAME-DAY-LEAK do not surface
This block is dated on the cutoff and must be dropped (could postdate the reply).
"""


class TestVoiceProfile:
    def test_returns_source(self):
        a = ScreenpipeSource(server=_FakeServer())
        assert a.voice_profile() == "VOICE-SOURCE: warm, direct, Danish for internal"


class TestModelPatterns:
    def test_returns_patterns_source(self):
        # The launcher-neutral adapter method model_patterns() maps to the server's
        # nate_model_patterns() (brain artifact kept verbatim).
        a = ScreenpipeSource(server=_FakeServer())
        out = a.model_patterns()
        assert "PATTERNS-SOURCE" in out
        # the private fence travels with it (informs HOW, never egresses)
        assert "PRIVATE NATE-MODEL" in out


@_needs_estate
class TestDraftingLessonsDateFilter:
    def test_keeps_strictly_before_cutoff(self):
        a = ScreenpipeSource(server=_FakeServer(_LESSONS))
        out = a.drafting_lessons(CUTOFF)
        assert "2026-05-01" in out
        assert "keep replies short" in out
        assert "2026-06-09" in out
        assert "answer the actual question" in out

    def test_drops_same_day_and_later_blocks(self):
        a = ScreenpipeSource(server=_FakeServer(_LESSONS))
        out = a.drafting_lessons(CUTOFF)
        # the cutoff-date block (== reply date) is dropped ENTIRELY
        assert "2026-06-10" not in out
        assert "SAME-DAY-LEAK" not in out
        assert "must be dropped" not in out

    def test_earlier_cutoff_drops_more(self):
        # With a cutoff on 2026-06-09, only the 2026-05-01 block is strictly
        # before — the 06-09 block (same day) and the 06-10 block both drop.
        a = ScreenpipeSource(server=_FakeServer(_LESSONS))
        out = a.drafting_lessons("2026-06-09T08:00:00+00:00")
        assert "2026-05-01" in out
        assert "2026-06-09" not in out
        assert "2026-06-10" not in out

    def test_empty_lessons_is_empty(self):
        a = ScreenpipeSource(server=_FakeServer(""))
        assert a.drafting_lessons(CUTOFF) == ""


@_needs_estate
class TestDraftingLessonsFullCorpus:
    def test_pre_cutoff_lesson_buried_before_cap_survives(self, monkeypatch,
                                                          tmp_path):
        # Cap-then-filter trap: draft_lib.drafting_lessons() returns only the LAST
        # 2500 chars. A pre-cutoff lesson buried before >2500 chars of later
        # lessons would be dropped before the date-filter sees it. The default
        # path passes the FULL corpus, so the early pre-cutoff block survives.
        import draft_lib
        early = "### 2026-01-01 — early\nthe early pre-cutoff lesson line\n\n"
        late = "### 2026-12-01 — late\n" + ("padding l0rem ipsum " * 200) + "\n"
        lessons = tmp_path / "Drafting-Lessons.md"
        lessons.write_text(early + late, encoding="utf-8")
        assert len(late) > 2500  # the early block is past the old cap
        monkeypatch.setattr(draft_lib, "LESSONS_FILE", lessons)

        a = ScreenpipeSource()
        out = a.drafting_lessons("2026-06-01T00:00:00+00:00")
        assert "early pre-cutoff lesson" in out   # survived
        assert "late" not in out                  # post-cutoff dropped (fence)
