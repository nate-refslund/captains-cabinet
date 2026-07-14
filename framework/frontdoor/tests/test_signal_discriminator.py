"""Unit tests for framework.frontdoor.signal_discriminator.

Covers the decision tree end-to-end with zero network (injected url_fetcher +
smoke_ok bool), and pins the two NAMED fixtures from the contract's verify handshake
(shared/interfaces/polads-sentry-triage-discriminator-contract-2026-07-14.md §VERIFY):
  • canonical NOISE  = the 07-11 09:39Z bot-burst (frozen, cumulative count, vercel.app)
  • staging regression = a FRESH test.polads.eu error the OLD suffix-match mislabels
    prod-real-user and the generalization MUST classify noise (the must-fix).
"""
from __future__ import annotations

import datetime

from framework import env
from framework.frontdoor import signal_discriminator as sd

NOW = datetime.datetime(2026, 7, 14, 21, 0, 0, tzinfo=datetime.timezone.utc)

# The PolAds TELLS as they will live in instance/config/signals.yml (the reference lane).
POLADS_TELLS = {
    "prod_hosts": ["polads.eu", "www.polads.eu"],       # EXACT allowlist (no test.polads.eu)
    "staging_host_patterns": ["test.", "xtest."],
    "bot_host_patterns": ["vercel.app"],
    "template_path_pattern": r"\[[a-zA-Z]",
    "smoke_paths": ["/da/search", "/en/terms-of-sale"],
}


def _iso(minutes_ago: float) -> str:
    return (NOW - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- age + freshness ---------------------------------------------------------
def test_age_minutes_and_freshness():
    assert sd.age_minutes(None, now=NOW) is None
    assert sd.age_minutes("garbage", now=NOW) is None
    assert round(sd.age_minutes(_iso(10), now=NOW)) == 10
    assert sd.freshness(None) == "unknown"
    assert sd.freshness(5) == "ongoing"
    assert sd.freshness(15) == "ongoing"     # boundary inclusive
    assert sd.freshness(15.1) == "frozen"


# --- classify_url attribution tree (incl. the staging MUST-FIX) --------------
def test_classify_url_staging_is_noise_not_prod():
    # test.polads.eu ends with .polads.eu — the OLD suffix regex called this prod.
    assert sd.classify_url("https://test.polads.eu/en/register", POLADS_TELLS) == sd.NOISE


def test_classify_url_exact_prod_host_is_real_user():
    assert sd.classify_url("https://polads.eu/da/search", POLADS_TELLS) == sd.REAL_USER
    assert sd.classify_url("https://www.polads.eu/en/terms", POLADS_TELLS) == sd.REAL_USER


def test_classify_url_bot_and_template_are_noise():
    assert sd.classify_url("https://abc123.vercel.app/da", POLADS_TELLS) == sd.NOISE
    assert sd.classify_url("https://polads.eu/[locale]/[id]", POLADS_TELLS) == sd.NOISE


def test_classify_url_empty_and_unclassified_are_inconclusive():
    assert sd.classify_url("", POLADS_TELLS) == sd.INCONCLUSIVE
    assert sd.classify_url("https://example.org/x", POLADS_TELLS) == sd.INCONCLUSIVE


def test_classify_url_no_tells_never_real_user():
    # Fail-open: with empty tells a real prod url can't be positively attributed.
    assert sd.classify_url("https://polads.eu/da/search", {}) == sd.INCONCLUSIVE


# --- classify_issue: recency gates -------------------------------------------
def test_frozen_issue_is_noise_by_recency_alone():
    # >2h old ⇒ settled ⇒ noise WITHOUT any url fetch (fetcher must not even be called).
    called = []
    issue = {"shortId": "SENTRY-STEP-POLADS-2", "id": "900", "count": 2811, "lastSeen": _iso(83 * 60)}
    out = sd.classify_issue(issue, POLADS_TELLS, now=NOW,
                            url_fetcher=lambda cid: called.append(cid) or "https://polads.eu/x")
    assert out["verdict"] == sd.NOISE
    assert out["freshness"] == "frozen"
    assert called == []                       # frozen path skips the event fetch


def test_fresh_prod_issue_is_real_user():
    issue = {"shortId": "SENTRY-STEP-POLADS-9", "id": "901", "count": 3, "lastSeen": _iso(5)}
    out = sd.classify_issue(issue, POLADS_TELLS, now=NOW,
                            url_fetcher=lambda cid: "https://polads.eu/da/complaint")
    assert out["verdict"] == sd.REAL_USER
    assert out["freshness"] == "ongoing"


def test_unparseable_lastseen_is_inconclusive_failopen():
    issue = {"shortId": "X-1", "id": "902", "count": 5, "lastSeen": "not-a-date"}
    out = sd.classify_issue(issue, POLADS_TELLS, now=NOW, url_fetcher=lambda cid: "")
    assert out["verdict"] == sd.INCONCLUSIVE


def test_delta_vs_baseline_is_reported():
    issue = {"shortId": "SENTRY-STEP-POLADS-2", "id": "900", "count": 2811, "lastSeen": _iso(83 * 60)}
    out = sd.classify_issue(issue, POLADS_TELLS, now=NOW, baseline={"2": "2811"})
    assert out["delta"] == 0                  # Δ=+0 ⇒ nothing new since last carded


# --- overall verdict precedence ----------------------------------------------
def test_overall_no_unresolved():
    assert sd.overall_sentry_verdict([], smoke_ok=True) == sd.V_NO_UNRESOLVED


def test_overall_real_user_outranks_green_smoke():
    classified = [{"verdict": sd.REAL_USER, "freshness": "ongoing"}]
    assert sd.overall_sentry_verdict(classified, smoke_ok=True) == sd.V_REAL_USER


def test_overall_smoke_non_200():
    classified = [{"verdict": sd.NOISE, "freshness": "frozen"}]
    assert sd.overall_sentry_verdict(classified, smoke_ok=False) == sd.V_PROD_NON_200


def test_overall_all_noise_suppresses():
    classified = [{"verdict": sd.NOISE, "freshness": "frozen"},
                  {"verdict": sd.NOISE, "freshness": "frozen"}]
    assert sd.overall_sentry_verdict(classified, smoke_ok=True) == sd.V_NOISE


def test_overall_any_inconclusive_failopen():
    classified = [{"verdict": sd.NOISE, "freshness": "frozen"},
                  {"verdict": sd.INCONCLUSIVE, "freshness": "ongoing"}]
    assert sd.overall_sentry_verdict(classified, smoke_ok=True) == sd.V_INCONCLUSIVE


# --- THE TWO NAMED CONTRACT FIXTURES (verify handshake) ----------------------
def test_fixture_canonical_noise_0711_bot_burst():
    """07-11 09:39Z bot-burst: a high cumulative count, frozen for days, on a
    preview/vercel host. Must resolve to overall NOISE (suppress) — this is the exact
    false 'incident' that reached the Chair on 2026-07-14."""
    issues = [
        {"shortId": "SENTRY-STEP-POLADS-2", "id": "900", "count": 2811, "lastSeen": _iso(83 * 60)},
        {"shortId": "SENTRY-STEP-POLADS-G", "id": "901", "count": 49, "lastSeen": _iso(60 * 60)},
        {"shortId": "SENTRY-STEP-POLADS-6", "id": "902", "count": 80, "lastSeen": _iso(50 * 60)},
    ]
    classified = [sd.classify_issue(i, POLADS_TELLS, now=NOW, url_fetcher=lambda cid: "") for i in issues]
    assert all(c["verdict"] == sd.NOISE for c in classified)
    assert sd.overall_sentry_verdict(classified, smoke_ok=True) == sd.V_NOISE


def test_fixture_staging_regression_must_be_noise():
    """MUST-PASS regression: a FRESH (<2h) error on test.polads.eu. The reference impl's
    suffix regex (.polads.eu$) mislabels it prod real-user; the generalization must
    classify it NOISE (staging ≠ prod) and NOT raise a real-user incident."""
    issue = {"shortId": "SENTRY-STEP-POLADS-6", "id": "910", "count": 80, "lastSeen": _iso(5)}
    out = sd.classify_issue(issue, POLADS_TELLS, now=NOW,
                            url_fetcher=lambda cid: "https://test.polads.eu/en/register")
    assert out["verdict"] == sd.NOISE
    assert sd.overall_sentry_verdict([out], smoke_ok=True) == sd.V_NOISE
    assert sd.overall_sentry_verdict([out], smoke_ok=True) != sd.V_REAL_USER


# --- load_tells fail-open ----------------------------------------------------
def test_signal_tells_empty_or_bad_env_is_empty():
    assert env.signal_tells("whatever", env_json="") == {}          # unset → fail-closed
    assert env.signal_tells("whatever", env_json="{not json") == {}  # invalid → fail-closed


def test_signal_tells_resolves_from_env_json():
    import json
    bare = json.dumps({"prod_hosts": ["a.com"], "smoke_paths": ["/"]})
    assert env.signal_tells("proj-a", env_json=bare).get("prod_hosts") == ["a.com"]
    mapped = json.dumps({"proj-a": {"prod_hosts": ["b.com"]}})       # {project: tells} map tolerated
    assert env.signal_tells("proj-a", env_json=mapped).get("prod_hosts") == ["b.com"]


def test_smoke_prod_no_paths_returns_none():
    assert sd.smoke_prod("polads.eu", [], fetcher=lambda u: 200) is None
    assert sd.smoke_prod("", ["/x"], fetcher=lambda u: 200) is None


def test_smoke_prod_all_200_true_any_non200_false():
    assert sd.smoke_prod("polads.eu", ["/a", "/b"], fetcher=lambda u: 200) is True
    assert sd.smoke_prod("polads.eu", ["/a", "/b"], fetcher=lambda u: 500) is False
