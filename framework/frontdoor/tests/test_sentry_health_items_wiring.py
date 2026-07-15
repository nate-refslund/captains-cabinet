"""Integration tests: framework.frontdoor.morning_synthesis.sentry_health_items wired
to the verified-noise discriminator. The unit tests (test_signal_discriminator.py) prove
the LOGIC; these prove the EMIT PATH end-to-end — suppress NOISE, emit real-user /
prod-down as ping-now, fail-open on INCONCLUSIVE — with injected health/tells/smoke/url
(no network, no clock)."""
from __future__ import annotations

import datetime

from framework.frontdoor import morning_synthesis as ms
from framework.frontdoor import signal_discriminator as sd

NOW = datetime.datetime(2026, 7, 14, 21, 0, 0, tzinfo=datetime.timezone.utc)
TELLS = {
    "prod_hosts": ["polads.eu", "www.polads.eu"],
    "staging_host_patterns": ["test.", "xtest."],
    "bot_host_patterns": ["vercel.app"],
    "template_path_pattern": r"\[[a-zA-Z]",
    "smoke_paths": ["/da/search"],
}


def _iso(mins: float) -> str:
    return (NOW - datetime.timedelta(minutes=mins)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _health(issues: list[dict]) -> dict:
    return {"project": "sentry-step-polads", "count": len(issues), "issues": issues}


def _items(health, **kw):
    return ms.sentry_health_items(org="step-network", project="sentry-step-polads",
                                  health=health, now=NOW, **kw)


def test_wiring_suppresses_frozen_2811_noise():
    """The exact 2026-07-14 false 'incident': 2811 cumulative, 83h frozen, prod green."""
    health = _health([
        {"shortId": "S-2", "id": "900", "events": 2811, "last_seen": _iso(83 * 60)},
        {"shortId": "S-G", "id": "901", "events": 49, "last_seen": _iso(60 * 60)},
    ])
    assert _items(health, tells=TELLS, smoke_ok=True, url_fetcher=lambda cid: "") == []


def test_wiring_emits_fresh_real_user_pingnow_with_route():
    health = _health([{"shortId": "S-9", "id": "902", "events": 3, "last_seen": _iso(4)}])
    items = _items(health, tells=TELLS, smoke_ok=True,
                   url_fetcher=lambda cid: "https://polads.eu/da/complaint")
    assert len(items) == 1
    assert items[0]["urgency_tier"] == "ping-now"
    assert items[0]["context"]["verdict"] == sd.V_REAL_USER
    assert "polads.eu/da/complaint" in items[0]["payload"]["summary"]


def test_wiring_staging_fresh_is_suppressed_not_realuser():
    """The staging must-fix, end to end: a FRESH test.polads.eu error must NOT emit."""
    health = _health([{"shortId": "S-6", "id": "903", "events": 80, "last_seen": _iso(4)}])
    assert _items(health, tells=TELLS, smoke_ok=True,
                  url_fetcher=lambda cid: "https://test.polads.eu/en/register") == []


def test_wiring_prod_smoke_down_emits_pingnow():
    health = _health([{"shortId": "S-2", "id": "900", "events": 2811, "last_seen": _iso(83 * 60)}])
    items = _items(health, tells=TELLS, smoke_ok=False, url_fetcher=lambda cid: "")
    assert len(items) == 1
    assert items[0]["urgency_tier"] == "ping-now"
    assert items[0]["context"]["verdict"] == sd.V_PROD_NON_200


def test_wiring_failopen_no_tells_fresh_unattributable_emits():
    """Empty tells + a FRESH un-attributable issue → INCONCLUSIVE → emit (today's behavior)."""
    health = _health([{"shortId": "S-9", "id": "902", "events": 5, "last_seen": _iso(4)}])
    items = _items(health, tells={}, smoke_ok=None, url_fetcher=lambda cid: "")
    assert len(items) == 1
    assert items[0]["context"]["verdict"] == sd.V_INCONCLUSIVE


def test_wiring_failopen_no_tells_all_frozen_still_suppresses():
    """Empty tells but every issue frozen → recency alone → NOISE → suppress (the win
    works even before signals.yml exists)."""
    # smoke_ok=None mirrors the REAL path with empty tells (no prod_hosts → smoke skipped);
    # all-frozen still suppresses because recency alone is affirmative evidence.
    health = _health([{"short_id": "S-2", "id": "900", "events": 2811, "last_seen": _iso(83 * 60)}])
    assert _items(health, tells={}, smoke_ok=None, url_fetcher=lambda cid: "") == []


def test_wiring_no_issues_is_quiet():
    assert _items(_health([]), tells=TELLS) == []
