"""OrgSource clean-room fail-closed lock — no backend config ⇒ honest empty.

The day-1 org recall chain ends at ``framework.sources.org.OrgSource``. On a
box where the memory backend is NOT configured — ``NEON_CONNECTION_STRING``
neither in the process env nor named in ``<root>/cabinet/.env`` — the adapter
must behave exactly like the Null adapter: ``search()`` returns the honest
empty ``{"hits": [], "topic_terms": None}`` with NO crash, NO subprocess and
NO network. This suite locks that fail-closed floor from the cleanroom-chain
side (the sibling ``framework/sources/tests/test_org_source.py`` owns the
full adapter contract); if a future change makes an unconfigured OrgSource
raise, spawn, or fabricate hits, day-1 boots break HERE, not in an officer
lane at runtime.

CABINET_ROOT is pointed at an EMPTY tmp dir (a true clean room: no
``cabinet/.env``, no ``cabinet/scripts/lib/memory.sh``), so even the
defensive inner layers have nothing to reach.

Run: python3 -m pytest cabinet/scripts/tests/test_orgsource_cleanroom.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    # framework/ is a namespace package rooted at the repo — make the direct
    # import below work under any in-repo pytest invocation shape.
    sys.path.insert(0, str(_REPO_ROOT))

from framework.sources.org import OrgSource  # noqa: E402

_HONEST_EMPTY = {"hits": [], "topic_terms": None}

_ENV_KEYS = (
    "NEON_CONNECTION_STRING",
    "CABINET_ORG_MEMORY_TYPES",
    "CABINET_ORG_SEARCH_LIMIT",
    "CABINET_ORG_MIN_SCORE",
)


@pytest.fixture(autouse=True)
def _cleanroom(monkeypatch, tmp_path):
    """A true clean room: backend env ABSENT (the secret's NAME only is ever
    involved — no value is set anywhere) and CABINET_ROOT at an empty tmp dir
    with no cabinet/.env to name it either."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    yield


def test_available_is_false_without_backend_config():
    assert OrgSource().available() is False


def test_search_returns_honest_empty_without_spawning_backend():
    """Fail-closed BEFORE the backend seam: the injected recorder must never
    be invoked — proving no subprocess (and hence no network) is attempted
    when the backend is unconfigured."""
    calls = []

    def _recorder(*args, **kwargs):
        calls.append(args)
        return ""

    src = OrgSource(run_search=_recorder)
    out = src.search("who owns the deploy runbook", topic="deploy runbook")
    assert out == _HONEST_EMPTY
    assert calls == [], "unconfigured OrgSource must not touch the backend seam"


def test_search_with_default_backend_never_crashes():
    """Belt-and-braces: even the REAL (non-injected) backend path returns the
    honest empty on a clean-room root — available() short-circuits first, and
    the empty root carries no memory.sh for any deeper layer to reach."""
    out = OrgSource().search("anything at all")
    assert out == _HONEST_EMPTY


def test_search_handles_degenerate_queries_without_crashing():
    src = OrgSource()
    assert src.search("") == _HONEST_EMPTY
    assert src.search("", topic="") == _HONEST_EMPTY
    assert src.search("x\x00y") == _HONEST_EMPTY
