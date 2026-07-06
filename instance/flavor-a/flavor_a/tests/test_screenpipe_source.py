"""Tests for the Flavor-A source adapter (``flavor_a.screenpipe_source``, SRC-1).

The adapter is a THIN DELEGATOR: every ``PersonalSource`` method forwards, 1:1,
to today's ``BrainAdapter`` / ``screenpipe_adapter`` code, so its result is
byte-identical to what runs today. These tests pin exactly that — the SAFETY /
byte-identical contract — with INJECTED fakes (no real screenpipe estate, no
vault, no brain):

  * it satisfies ``framework.sources.base.PersonalSource`` STRUCTURALLY
    (``runtime_checkable`` isinstance) — every Protocol method present + callable;
  * each of the 8 data methods forwards the EXACT args and passes the underlying
    return through UNCHANGED (the shim adds no logic) — mapped per the spec §4
    method-origin table (search→gather_vault, person_intel/open_commitments/
    voice_profile/drafting_lessons/read_note→BrainAdapter.*, model_patterns→
    nate_model_patterns, find_reply_candidates→screenpipe_adapter.find_threads);
  * ``available()`` is a cheap disk probe that never raises;
  * with NO injection the lazy defaults wire to the REAL framework symbols
    (BrainAdapter + screenpipe_adapter.find_threads) — proven by monkeypatch,
    no real estate touched;
  * ``framework.sources.get_source()`` on THIS instance binds ``ScreenpipeSource``
    (the resolver reads instance/config/sources.yml → flavor_a.screenpipe_source).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Two paths on sys.path (same convention as the sibling autoreply cell test):
# the package parent (instance/flavor-a) so ``flavor_a`` imports, and the repo
# root so ``framework.*`` resolves. Depth: tests/ [0] flavor_a [1] flavor-a [2]
# instance [3] <root> [4].
_PKG_PARENT = Path(__file__).resolve().parents[2]   # instance/flavor-a
_REPO_ROOT = Path(__file__).resolve().parents[4]    # worktree / repo root
for _p in (str(_REPO_ROOT), str(_PKG_PARENT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flavor_a.screenpipe_source import ScreenpipeSource
from framework.sources.base import PersonalSource

_PROTOCOL_METHODS = (
    "available", "search", "find_reply_candidates", "person_intel",
    "open_commitments", "voice_profile", "model_patterns", "drafting_lessons",
    "read_note",
)


# ---------------------------------------------------------------------------
# Fakes — record calls + return per-method SENTINELS, so a test proves both the
# forwarded ARGS and that the return is passed through UNCHANGED (pass-through).
# ---------------------------------------------------------------------------
class FakeBrain:
    """Stands in for framework.fidelity.officer_runner.BrainAdapter (the 7
    vault/intel/commitment/priors/note methods)."""

    def __init__(self):
        self.calls = []

    def gather_vault(self, handle, topic=None):
        self.calls.append(("gather_vault", handle, topic))
        return {"hits": [{"text": "H"}], "topic_terms": ["t"], "_sentinel": "gv"}

    def person_intel(self, slug):
        self.calls.append(("person_intel", slug))
        return "INTEL:" + slug

    def open_commitments(self, direction):
        self.calls.append(("open_commitments", direction))
        return [{"direction": direction, "_sentinel": "oc"}]

    def voice_profile(self):
        self.calls.append(("voice_profile",))
        return "VOICE"

    def nate_model_patterns(self):
        self.calls.append(("nate_model_patterns",))
        return "PATTERNS"

    def drafting_lessons(self, before_ts):
        self.calls.append(("drafting_lessons", before_ts))
        return "LESSONS<" + before_ts

    def read_note(self, path):
        self.calls.append(("read_note", path))
        return "NOTE:" + path


class FakeThreads:
    """Stands in for framework.acting.screenpipe_adapter (find_threads only)."""

    def __init__(self, result=None):
        self.calls = []
        self._result = result if result is not None else [{"slug": "s1"}]

    def find_threads(self, *args, **kwargs):
        self.calls.append(("find_threads", args, kwargs))
        return self._result


def _src(brain=None, threads=None, **kw):
    """A ScreenpipeSource with BOTH backends injected by default, so no test
    accidentally reaches the real screenpipe estate."""
    return ScreenpipeSource(brain=brain or FakeBrain(),
                            threads_mod=threads or FakeThreads(), **kw)


# ---------------------------------------------------------------------------
# Protocol conformance.
# ---------------------------------------------------------------------------
def test_satisfies_personalsource_protocol_structurally():
    src = _src()
    # runtime_checkable structural check (no inheritance).
    assert isinstance(src, PersonalSource)
    # Every Protocol method is present and callable.
    for name in _PROTOCOL_METHODS:
        assert callable(getattr(src, name)), name


def test_zero_arg_constructible():
    # The sources.yml contract: get_source() does ``cls()``. Construction must
    # not touch the estate (lazy) — it must not raise even with no brain present.
    src = ScreenpipeSource()
    assert isinstance(src, PersonalSource)


# ---------------------------------------------------------------------------
# Per-method delegation (byte-identical pass-through) — the correctness ledger.
# ---------------------------------------------------------------------------
def test_search_delegates_to_gather_vault():
    fb = FakeBrain()
    src = _src(brain=fb)
    out = src.search("Sobuc", topic="garden budget")
    # exact args forwarded (handle + topic), positionally to gather_vault
    assert fb.calls == [("gather_vault", "Sobuc", "garden budget")]
    # return passed through UNCHANGED (no transform)
    assert out == {"hits": [{"text": "H"}], "topic_terms": ["t"], "_sentinel": "gv"}


def test_search_default_topic_is_none():
    fb = FakeBrain()
    _src(brain=fb).search("Ulrik")
    assert fb.calls == [("gather_vault", "Ulrik", None)]


def test_person_intel_delegates():
    fb = FakeBrain()
    assert _src(brain=fb).person_intel("kristoffer") == "INTEL:kristoffer"
    assert fb.calls == [("person_intel", "kristoffer")]


def test_open_commitments_delegates():
    fb = FakeBrain()
    out = _src(brain=fb).open_commitments("owed_by_nate")
    assert out == [{"direction": "owed_by_nate", "_sentinel": "oc"}]
    assert fb.calls == [("open_commitments", "owed_by_nate")]


def test_voice_profile_delegates():
    fb = FakeBrain()
    assert _src(brain=fb).voice_profile() == "VOICE"
    assert fb.calls == [("voice_profile",)]


def test_model_patterns_maps_to_nate_model_patterns_verbatim():
    # The launcher-neutral method name maps to the brain artifact kept VERBATIM
    # (me_signal.nate_model("patterns") via BrainAdapter.nate_model_patterns).
    fb = FakeBrain()
    assert _src(brain=fb).model_patterns() == "PATTERNS"
    assert fb.calls == [("nate_model_patterns",)]


def test_drafting_lessons_forwards_before_ts():
    fb = FakeBrain()
    ts = "2026-07-01T00:00:00Z"
    assert _src(brain=fb).drafting_lessons(ts) == "LESSONS<" + ts
    assert fb.calls == [("drafting_lessons", ts)]


def test_read_note_delegates():
    fb = FakeBrain()
    assert _src(brain=fb).read_note("3-People/x.md") == "NOTE:3-People/x.md"
    assert fb.calls == [("read_note", "3-People/x.md")]


def test_find_reply_candidates_delegates_to_find_threads():
    ft = FakeThreads(result=[{"slug": "a"}, {"slug": "b"}])
    out = _src(threads=ft).find_reply_candidates()
    assert out == [{"slug": "a"}, {"slug": "b"}]
    assert ft.calls and ft.calls[0][0] == "find_threads"


def test_find_reply_candidates_accepts_since_and_still_forwards():
    # ``since`` is accepted for interface parity; PASS 1 forwards today's exact
    # (window-based) find_threads() call regardless — byte-identical.
    ft = FakeThreads()
    _src(threads=ft).find_reply_candidates(since="2026-07-01T00:00:00Z")
    assert ft.calls and ft.calls[0][0] == "find_threads"


def test_shim_reuses_one_backend_instance():
    # A thin delegator holds ONE backend (BrainAdapter is stateless w.r.t.
    # results); repeated calls do not rebuild it.
    fb = FakeBrain()
    src = _src(brain=fb)
    src.voice_profile()
    src.person_intel("x")
    assert src._b() is fb


# ---------------------------------------------------------------------------
# available() — cheap disk liveness probe, never raises.
# ---------------------------------------------------------------------------
def test_available_true_when_estate_present(tmp_path):
    shared = tmp_path / "pipes" / "_shared"
    shared.mkdir(parents=True)
    src = _src(pipes_dir=str(tmp_path / "pipes"))
    assert src.available() is False          # draft_lib.py not yet present
    (shared / "draft_lib.py").write_text("# stub\n")
    assert src.available() is True


def test_available_false_when_absent(tmp_path):
    src = _src(pipes_dir=str(tmp_path / "does-not-exist"))
    assert src.available() is False


def test_available_never_raises_on_bad_path():
    # A path with an embedded NUL makes .exists() raise on some platforms; the
    # probe must swallow it and return False, never propagate.
    src = _src(pipes_dir="\x00bogus")
    assert src.available() is False


# ---------------------------------------------------------------------------
# Default (un-injected) wiring points at the REAL framework symbols — proven by
# monkeypatch, so no real screenpipe estate is touched.
# ---------------------------------------------------------------------------
def test_default_brain_wires_to_framework_brainadapter(monkeypatch):
    import framework.fidelity.officer_runner as orn
    built = {}

    class FakeBA:
        def __init__(self):
            built["yes"] = True

        def voice_profile(self):
            return "REAL-PATH-VOICE"

    monkeypatch.setattr(orn, "BrainAdapter", FakeBA)
    src = ScreenpipeSource()                 # NO injection → lazy real import path
    assert src.voice_profile() == "REAL-PATH-VOICE"
    assert built.get("yes") is True


def test_default_threads_wires_to_screenpipe_adapter(monkeypatch):
    import framework.acting.screenpipe_adapter as spa
    calls = []
    monkeypatch.setattr(spa, "find_threads",
                        lambda *a, **k: (calls.append(1) or ["T"]))
    src = ScreenpipeSource()                 # NO injection → lazy real import path
    assert src.find_reply_candidates() == ["T"]
    assert calls == [1]


# ---------------------------------------------------------------------------
# get_source() acceptance — the resolver binds ScreenpipeSource on THIS instance.
# ---------------------------------------------------------------------------
def test_get_source_binds_screenpipe_source(monkeypatch):
    import framework.sources as fs
    # Hermetic: point the resolver at THIS worktree root, so it reads this
    # deployment's instance/config/sources.yml (not an ambient CABINET_ROOT that
    # might select the live repo's instance/).
    monkeypatch.setenv("CABINET_ROOT", str(_REPO_ROOT))
    fs._reset_cache()
    try:
        src = fs.get_source()
        assert type(src).__name__ == "ScreenpipeSource", (
            "get_source() bound %r — expected ScreenpipeSource (sources.yml "
            "binding / flavor_a package import failed → fell back to Null)"
            % type(src).__name__)
        assert type(src).__module__ == "flavor_a.screenpipe_source"
        # and it structurally satisfies the Protocol the resolver promises
        assert isinstance(src, PersonalSource)
    finally:
        fs._reset_cache()
