"""Tests for the Flavor-A source adapter (``flavor_a.screenpipe_source``, SRC-1/3).

``ScreenpipeSource`` now OWNS the real screenpipe calls: the former
``framework.fidelity.officer_runner.BrainAdapter`` bodies are INLINED here and the
screenpipe ACTING surface delegates to the sibling ``flavor_a.acting`` module. So
its result is byte-identical to what ran when those bodies lived in ``framework/``.
These tests pin that contract with INJECTED seams (no real screenpipe estate, no
vault, no brain):

  * it satisfies ``framework.sources.base.PersonalSource`` STRUCTURALLY
    (``runtime_checkable`` isinstance) — every Protocol method present + callable;
  * the 7 data methods honor the in-process ``server`` seam and pass the return
    through UNCHANGED (search←gather_vault, model_patterns←nate_model_patterns
    verbatim, the rest same-named — spec §4 method-origin table);
  * ``search`` routes an injected ``context_lib`` in-process (sources=["vault"]);
  * the acting-surface methods delegate 1:1 to the injected acting module;
  * ``available()`` is a cheap disk probe that never raises;
  * ``framework.sources.get_source()`` on THIS instance binds ``ScreenpipeSource``.

The BrainAdapter-internal subprocess / server-lessons / scoping proofs live in
``test_adapter_internals.py`` (moved here with the adapter from framework fidelity).
"""
from __future__ import annotations

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

from flavor_a.screenpipe_source import ScreenpipeSource
from framework.sources.base import PersonalSource

_PROTOCOL_METHODS = (
    "available", "search", "find_reply_candidates", "person_intel",
    "open_commitments", "voice_profile", "model_patterns", "drafting_lessons",
    "read_note",
)
_ACTING_METHODS = (
    "find_threads", "gather", "draft_fn", "nate_replied_since",
    "still_awaiting", "deploy_health", "briefing_commitments", "normalize_voice",
)


# ---------------------------------------------------------------------------
# Fakes — record calls + return per-method SENTINELS, proving the forwarded ARGS
# and that the return is passed through UNCHANGED.
# ---------------------------------------------------------------------------
class FakeServer:
    """Stands in for the in-process brain server seam the data methods honor
    (person_intel / open_commitments / voice_profile / read_note directly, and
    model_patterns via the verbatim brain-artifact name nate_model_patterns)."""

    def __init__(self):
        self.calls = []

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

    def read_note(self, path):
        self.calls.append(("read_note", path))
        return "NOTE:" + path


class FakeActing:
    """Stands in for the sibling ``flavor_a.acting`` module (the screenpipe acting
    surface). Records the forwarded call + returns a per-method sentinel."""

    def __init__(self):
        self.calls = []

    def find_threads(self, hours=48):
        self.calls.append(("find_threads", hours))
        return [{"slug": "s1"}]

    def gather(self, thread, do_prep=True):
        self.calls.append(("gather", thread, do_prep))
        return {"intel": "I", "_sentinel": "g"}

    def draft_fn(self, thread, ctx, min_confidence=0.0):
        self.calls.append(("draft_fn", thread, ctx, min_confidence))
        return "DRAFT"

    def nate_replied_since(self, slug, when):
        self.calls.append(("nate_replied_since", slug, when))
        return True

    def still_awaiting(self, slug, hours=72):
        self.calls.append(("still_awaiting", slug, hours))
        return False

    def deploy_health(self, app, limit=8):
        self.calls.append(("deploy_health", app, limit))
        return {"app": app, "_sentinel": "dh"}

    def open_commitments(self, direction="owed_by_nate"):
        self.calls.append(("open_commitments", direction))
        return [{"direction": direction, "_sentinel": "acting_oc"}]

    def normalize_voice(self, text):
        self.calls.append(("normalize_voice", text))
        return "NORM:" + str(text)


def _src(server=None, acting=None, **kw):
    """A ScreenpipeSource with BOTH seams injected by default, so no test
    accidentally reaches the real screenpipe estate."""
    return ScreenpipeSource(server=server or FakeServer(),
                            acting_mod=acting or FakeActing(), **kw)


# ---------------------------------------------------------------------------
# Protocol conformance.
# ---------------------------------------------------------------------------
def test_satisfies_personalsource_protocol_structurally():
    src = _src()
    assert isinstance(src, PersonalSource)  # runtime_checkable structural check
    for name in _PROTOCOL_METHODS:
        assert callable(getattr(src, name)), name


def test_zero_arg_constructible():
    # The sources.yml contract: get_source() does ``cls()``. Construction must
    # not touch the estate (lazy) — it must not raise even with no brain present.
    src = ScreenpipeSource()
    assert isinstance(src, PersonalSource)
    for name in _ACTING_METHODS:
        assert callable(getattr(src, name)), name


# ---------------------------------------------------------------------------
# Per-method delegation (byte-identical pass-through) — the correctness ledger.
# ---------------------------------------------------------------------------
def test_search_routes_injected_context_lib_in_process():
    seen = {}

    class StubCtx:
        @staticmethod
        def gather(handle, *, sources=None, **kw):
            seen["sources"] = sources
            seen["handle"] = handle
            seen["topic"] = kw.get("topic")
            return {"hits": [{"text": "H"}], "topic_terms": ["t"]}

    src = ScreenpipeSource(context_lib=StubCtx())
    out = src.search("Sobuc", topic="garden budget")
    assert seen == {"sources": ["vault"], "handle": "Sobuc", "topic": "garden budget"}
    assert out == {"hits": [{"text": "H"}], "topic_terms": ["t"]}


def test_search_uses_vault_search_seam_when_uninjected():
    captured = {}

    def fake_search(handle, topic=None):
        captured["handle"], captured["topic"] = handle, topic
        return {"hits": [{"text": "H"}], "topic_terms": None}

    out = ScreenpipeSource(vault_search=fake_search).search("Ulrik")
    assert captured == {"handle": "Ulrik", "topic": None}
    assert out["hits"][0]["text"] == "H"


def test_person_intel_delegates():
    fs = FakeServer()
    assert _src(server=fs).person_intel("kristoffer") == "INTEL:kristoffer"
    assert fs.calls == [("person_intel", "kristoffer")]


def test_open_commitments_delegates():
    fs = FakeServer()
    out = _src(server=fs).open_commitments("owed_by_nate")
    assert out == [{"direction": "owed_by_nate", "_sentinel": "oc"}]
    assert fs.calls == [("open_commitments", "owed_by_nate")]


def test_voice_profile_delegates():
    fs = FakeServer()
    assert _src(server=fs).voice_profile() == "VOICE"
    assert fs.calls == [("voice_profile",)]


def test_model_patterns_maps_to_nate_model_patterns_verbatim():
    # The launcher-neutral method name maps to the brain artifact kept VERBATIM
    # (the server's nate_model_patterns()).
    fs = FakeServer()
    assert _src(server=fs).model_patterns() == "PATTERNS"
    assert fs.calls == [("nate_model_patterns",)]


def test_read_note_delegates():
    fs = FakeServer()
    assert _src(server=fs).read_note("3-People/x.md") == "NOTE:3-People/x.md"
    assert fs.calls == [("read_note", "3-People/x.md")]


# ---------------------------------------------------------------------------
# Acting-surface delegation (1:1 to flavor_a.acting).
# ---------------------------------------------------------------------------
def test_find_reply_candidates_delegates_to_find_threads():
    fa = FakeActing()
    out = _src(acting=fa).find_reply_candidates()
    assert out == [{"slug": "s1"}]
    assert fa.calls and fa.calls[0][0] == "find_threads"


def test_find_reply_candidates_accepts_since_and_still_forwards():
    fa = FakeActing()
    _src(acting=fa).find_reply_candidates(since="2026-07-01T00:00:00Z")
    assert fa.calls and fa.calls[0][0] == "find_threads"


def test_find_threads_forwards_hours():
    fa = FakeActing()
    assert _src(acting=fa).find_threads(hours=72) == [{"slug": "s1"}]
    assert fa.calls == [("find_threads", 72)]


def test_gather_forwards():
    fa = FakeActing()
    out = _src(acting=fa).gather({"slug": "s"}, do_prep=False)
    assert out == {"intel": "I", "_sentinel": "g"}
    assert fa.calls == [("gather", {"slug": "s"}, False)]


def test_draft_fn_forwards():
    fa = FakeActing()
    assert _src(acting=fa).draft_fn({"slug": "s"}, {"gate": {}}, min_confidence=0.5) == "DRAFT"
    assert fa.calls == [("draft_fn", {"slug": "s"}, {"gate": {}}, 0.5)]


def test_nate_replied_since_forwards():
    fa = FakeActing()
    assert _src(acting=fa).nate_replied_since("morten", None) is True
    assert fa.calls == [("nate_replied_since", "morten", None)]


def test_still_awaiting_forwards():
    fa = FakeActing()
    assert _src(acting=fa).still_awaiting("kristoffer", hours=48) is False
    assert fa.calls == [("still_awaiting", "kristoffer", 48)]


def test_deploy_health_forwards():
    fa = FakeActing()
    out = _src(acting=fa).deploy_health("polads", limit=4)
    assert out == {"app": "polads", "_sentinel": "dh"}
    assert fa.calls == [("deploy_health", "polads", 4)]


def test_briefing_commitments_maps_to_acting_open_commitments():
    # The acting status=="open" filter, distinct from PersonalSource.open_commitments.
    fa = FakeActing()
    out = _src(acting=fa).briefing_commitments(direction="owed_by_nate")
    assert out == [{"direction": "owed_by_nate", "_sentinel": "acting_oc"}]
    assert fa.calls == [("open_commitments", "owed_by_nate")]


def test_normalize_voice_forwards():
    fa = FakeActing()
    assert _src(acting=fa).normalize_voice("hi — there") == "NORM:hi — there"
    assert fa.calls == [("normalize_voice", "hi — there")]


def test_acting_delegation_relooks_up_module_attr(monkeypatch):
    # The delegate must re-look-up the module attribute at call time, so a test
    # that patches ``flavor_a.acting.<fn>`` (the run-lane seam) is honored. We
    # emulate the module with a namespace and patch a function on it.
    import types
    mod = types.SimpleNamespace(nate_replied_since=lambda slug, when: "ORIG")
    src = ScreenpipeSource(acting_mod=mod)
    assert src.nate_replied_since("s", None) == "ORIG"
    mod.nate_replied_since = lambda slug, when: "PATCHED"
    assert src.nate_replied_since("s", None) == "PATCHED"


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
    assert _src(pipes_dir=str(tmp_path / "does-not-exist")).available() is False


def test_available_never_raises_on_bad_path():
    assert _src(pipes_dir="\x00bogus").available() is False


# ---------------------------------------------------------------------------
# get_source() acceptance — the resolver binds ScreenpipeSource on THIS instance.
# ---------------------------------------------------------------------------
def test_get_source_binds_screenpipe_source(monkeypatch):
    import framework.sources as fs
    # Hermetic: point the resolver at THIS worktree root, so it reads this
    # deployment's instance/config/sources.yml (not an ambient CABINET_ROOT).
    monkeypatch.setenv("CABINET_ROOT", str(_REPO_ROOT))
    fs._reset_cache()
    try:
        src = fs.get_source()
        assert type(src).__name__ == "ScreenpipeSource", (
            "get_source() bound %r — expected ScreenpipeSource (sources.yml "
            "binding / flavor_a package import failed → fell back to Null)"
            % type(src).__name__)
        assert type(src).__module__ == "flavor_a.screenpipe_source"
        assert isinstance(src, PersonalSource)
    finally:
        fs._reset_cache()
