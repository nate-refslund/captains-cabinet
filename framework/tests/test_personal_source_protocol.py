"""The PersonalSource seam is WHOLE — framework callers are on-contract [T1].

Protocol-widen proof (2026-07-07): every method framework CORE actually calls on
``get_source()`` — the draft lane's ``find_threads`` / ``gather`` / ``draft_fn``
/ ``captain_replied_since`` / ``still_awaiting`` (run_draft_lane.py), the
briefing's ``find_threads`` / ``briefing_commitments`` / ``deploy_health``
(morning_synthesis.py), the fidelity runner's ``open_commitments`` (contract
direction values) — is IN ``base.PersonalSource``. No framework caller
duck-types an off-protocol method that only exists on the Flavor-A adapter, so
the flavor claim holds: a clean-room / Flavor-B box bound to
``NullPersonalSource`` runs every framework lane without an ``AttributeError``.

Three proof families:

  * CONFORMANCE — both shipped adapters satisfy the ``runtime_checkable``
    Protocol: the fail-closed ``NullPersonalSource``, and (skip-if-unavailable)
    the Flavor-A ``ScreenpipeSource`` imported DYNAMICALLY via the instance
    path exactly the way ``framework.sources._load_bound`` does — never a
    static instance import (layer separation holds in tests too).
  * HONEST EMPTIES — every protocol method on Null returns its honest empty
    without raising: ``[]`` / ``{}`` / ``''`` for the collection/draft
    surfaces, tri-state ``None`` (unknown — NEVER a fabricated ``True``/
    ``False``) for ``captain_replied_since`` / ``still_awaiting``, and
    ``read_note`` keeps its honest ``FileNotFoundError``.
  * NULL-BOUND LANE — the real ``run_draft_lane._auto_expire_self_replied``
    runs end-to-end against a null-bound source (no AttributeError; the age
    backstop still fires on the honest ``None``), and the lanes' exact call
    shapes all resolve on Null.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.sources.base import PersonalSource  # noqa: E402
from framework.sources.null import NullPersonalSource  # noqa: E402

# The full read contract: the original observe/intel/priors/note surface plus
# the T1-widened acting/briefing surface. This tuple IS the ledger of what
# framework core may call on get_source().
PROTOCOL_METHODS = (
    # original surface
    "available", "search", "find_reply_candidates", "person_intel",
    "open_commitments", "voice_profile", "model_patterns", "drafting_lessons",
    "read_note",
    # T1-widened acting/briefing surface (2026-07-07)
    "find_threads", "gather", "draft_fn", "captain_replied_since",
    "still_awaiting", "deploy_health", "briefing_commitments",
)


def _load_screenpipe_source():
    """Import the Flavor-A adapter CLASS the way the resolver does — dynamic,
    via the instance dir on sys.path (joined literal, layer-sep safe), never a
    static import. Returns the class, or ``None`` on a clean-room checkout
    (no instance adapter) so callers skip rather than fail."""
    adapter_dir = _REPO_ROOT / "instance/flavor-a"     # joined literal
    if not (adapter_dir / "flavor_a" / "screenpipe_source.py").exists():
        return None
    if str(adapter_dir) not in sys.path:
        sys.path.insert(0, str(adapter_dir))
    try:
        mod = importlib.import_module("flavor_a.screenpipe_source")
    except Exception:
        return None
    return getattr(mod, "ScreenpipeSource", None)


# ---------------------------------------------------------------------------
# CONFORMANCE — both shipped adapters satisfy the widened Protocol.
# ---------------------------------------------------------------------------
class TestProtocolConformance:
    def test_protocol_declares_every_framework_called_method(self):
        # The Protocol itself names each method, so the runtime_checkable
        # isinstance below actually ENFORCES the widened surface.
        for name in PROTOCOL_METHODS:
            assert hasattr(PersonalSource, name), (
                "base.PersonalSource lost contract method %r" % name)

    def test_null_satisfies_the_widened_protocol(self):
        ns = NullPersonalSource()
        assert isinstance(ns, PersonalSource)
        for name in PROTOCOL_METHODS:
            assert callable(getattr(ns, name)), name

    def test_screenpipe_source_satisfies_the_widened_protocol(self):
        cls = _load_screenpipe_source()
        if cls is None:
            pytest.skip("no Flavor-A adapter on this checkout (clean-room box)")
        src = cls()  # zero-arg constructible; lazy — touches no estate
        assert isinstance(src, PersonalSource)
        for name in PROTOCOL_METHODS:
            assert callable(getattr(src, name)), name
        # The contract name AND the Flavor-A back-compat alias both resolve.
        assert callable(src.captain_replied_since)
        assert callable(src.nate_replied_since)


# ---------------------------------------------------------------------------
# HONEST EMPTIES — Null never fabricates, never raises (except read_note).
# ---------------------------------------------------------------------------
class TestNullHonestEmpties:
    def test_every_read_returns_its_honest_empty_without_raising(self):
        ns = NullPersonalSource()
        assert ns.available() is False
        assert ns.search("handle") == {"hits": [], "topic_terms": None}
        assert ns.search("handle", topic="x") == {"hits": [], "topic_terms": None}
        assert ns.find_reply_candidates() == []
        assert ns.find_reply_candidates(since="2026-01-01T00:00:00Z") == []
        assert ns.person_intel("slug") == ""
        assert ns.open_commitments("owed_by_captain") == []
        assert ns.open_commitments("owed_to_captain") == []
        assert ns.voice_profile() == ""
        assert ns.model_patterns() == ""
        assert ns.drafting_lessons("2026-01-01T00:00:00Z") == ""
        # T1-widened surface — the lanes' exact call shapes:
        assert ns.find_threads() == []
        assert ns.find_threads(hours=72) == []
        assert ns.gather({"slug": "s"}) == {}
        assert ns.gather({"slug": "s"}, do_prep=False) == {}
        assert ns.draft_fn({"slug": "s"}, {}) == ""
        assert ns.draft_fn({"slug": "s"}, {}, min_confidence=0.9) == ""
        assert ns.captain_replied_since("s", None) is None
        assert ns.still_awaiting("s") is None
        assert ns.still_awaiting("s", hours=72) is None
        assert ns.deploy_health("app") == {}
        assert ns.deploy_health("app", limit=4) == {}
        assert ns.briefing_commitments() == []
        assert ns.briefing_commitments(direction="owed_by_captain") == []

    def test_read_note_keeps_its_honest_filenotfound(self):
        with pytest.raises(FileNotFoundError):
            NullPersonalSource().read_note("1-Daily/2026-01-01.md")

    def test_tristate_unknowns_never_fabricate(self):
        """A null box must answer UNKNOWN, not a made-up observation: a
        fabricated ``False`` from captain_replied_since would pin the draft
        lane's stale proposals open forever (the age backstop only fires while
        ``replied is not False``), a fabricated ``True`` would expire real
        ones; a fabricated ``False`` from still_awaiting would silently DROP a
        just-drafted reply. ``None`` is the only honest sourceless answer, and
        both callers fail-safe on it."""
        ns = NullPersonalSource()
        assert ns.captain_replied_since("slug", None) is not True
        assert ns.captain_replied_since("slug", None) is not False
        assert ns.still_awaiting("slug", hours=72) is not True
        assert ns.still_awaiting("slug", hours=72) is not False


# ---------------------------------------------------------------------------
# NULL-BOUND LANE — the draft lane's signal gather cannot AttributeError.
# ---------------------------------------------------------------------------
class TestNullBoundDraftLane:
    @pytest.fixture()
    def rdl(self, monkeypatch, tmp_path):
        """Import the real run_draft_lane with inert env, bind the NULL source
        into the resolver cache (restored by monkeypatch), and isolate the
        consequence ledger — nothing here touches live state or Telegram."""
        os.environ.setdefault("TELEGRAM_COS_TOKEN", "test-token")
        os.environ.setdefault("CAPTAIN_TELEGRAM_ID", "0")
        monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import framework.sources as sources
        from framework.acting import run_draft_lane as rdl_mod
        monkeypatch.setattr(sources, "_source_cache", NullPersonalSource())
        assert isinstance(sources.get_source(), NullPersonalSource)
        return rdl_mod

    def test_auto_expire_runs_on_a_null_source(self, rdl, monkeypatch):
        # One STALE open proposal: on a null source the precise check answers
        # None (honest unknown), so the AGE backstop expires it — the exact
        # degrade the tri-state contract exists for — and the whole path runs
        # without an AttributeError on the seam.
        stale = {"subject": "someone", "ts": "2020-01-01T00:00:00+00:00"}
        monkeypatch.setattr(rdl.loop, "pending_proposals", lambda: [stale])
        monkeypatch.setattr(rdl, "PROPOSAL_MAX_AGE_H", 36.0)
        monkeypatch.setattr(rdl.loop, "expire_event",
                            lambda prop, **kw: {"stub": True, "subject": prop["subject"]})
        captured = []
        monkeypatch.setattr(rdl, "emit_consequence",
                            lambda **ev: captured.append(ev))

        assert rdl._auto_expire_self_replied() == 1
        assert captured == [{"stub": True, "subject": "someone"}]

    def test_fresh_proposal_stays_open_on_a_null_source(self, rdl, monkeypatch):
        # A FRESH proposal + None from the null detector -> neither the precise
        # branch nor the backstop fires: the proposal stays open (no fabricated
        # "captain replied" expiry on a sourceless box).
        import datetime
        fresh_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        monkeypatch.setattr(rdl.loop, "pending_proposals",
                            lambda: [{"subject": "someone", "ts": fresh_ts}])
        monkeypatch.setattr(rdl, "PROPOSAL_MAX_AGE_H", 36.0)
        boom = []
        monkeypatch.setattr(rdl, "emit_consequence", lambda **ev: boom.append(ev))

        assert rdl._auto_expire_self_replied() == 0
        assert boom == []

    def test_lane_call_shapes_all_resolve_on_null(self):
        # The EXACT shapes framework callers use, pinned so a future caller
        # drift (new kwarg, renamed method) fails HERE, on the contract, not in
        # production on a clean-room box.
        ns = NullPersonalSource()
        # run_draft_lane.main():
        assert ns.find_threads(hours=72) == []                 # :270
        assert ns.gather({"slug": "s"}) == {}                  # :284
        assert ns.draft_fn({"slug": "s"}, {}) == ""            # :285 (falsy -> skip)
        assert ns.still_awaiting("s", hours=72) is None        # :309 (fail-safe)
        # run_draft_lane._auto_expire_self_replied():
        assert ns.captain_replied_since("s", None) is None     # :208
        # morning_synthesis:
        assert ns.find_threads(hours=72) == []                            # :136
        assert ns.briefing_commitments(direction="owed_by_captain") == [] # :188
        assert ns.deploy_health("some-app") == {}                         # :257
        # officer_runner.gather_cutoff_context():
        assert ns.open_commitments("owed_by_captain") == []    # :341
        assert ns.open_commitments("owed_to_captain") == []    # :342
