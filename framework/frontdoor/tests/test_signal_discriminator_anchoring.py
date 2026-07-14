"""Regression tests for the review-hardening fixes:
  • _host_matches must be LABEL-anchored, not a bare substring — else a legit prod host
    that merely CONTAINS a staging/bot fragment would be suppressed (fail-open violation
    in the reusable core, dormant on today's tells but real for other lanes).
  • smoke_prod must check ALL configured prod hosts, not just the first.
"""
from __future__ import annotations

from framework.frontdoor import signal_discriminator as sd

# A collision-prone lane: the prod host 'latest.acme.com' CONTAINS the staging tell
# 'test', and 'notvercel.app' CONTAINS the bot tell 'vercel.app'. Anchored matching must
# NOT misfire on these — a fresh real-user hit on them must stay attributable to prod.
COLLIDE = {
    "prod_hosts": ["latest.acme.com", "notvercel.app"],
    "staging_host_patterns": ["test.", "staging."],
    "bot_host_patterns": ["vercel.app"],
    "template_path_pattern": r"\[[a-zA-Z]",
    "smoke_paths": ["/"],
}


def test_staging_prefix_does_not_match_substring_collision():
    # 'latest.acme.com' contains 'test' but is NOT a 'test.' subdomain → must be prod.
    assert sd.classify_url("https://latest.acme.com/dashboard", COLLIDE) == sd.REAL_USER


def test_bot_suffix_does_not_match_substring_collision():
    # 'notvercel.app' contains 'vercel.app' but is NOT '*.vercel.app' → must be prod.
    assert sd.classify_url("https://notvercel.app/home", COLLIDE) == sd.REAL_USER


def test_real_staging_and_bot_still_match_when_anchored():
    assert sd.classify_url("https://test.acme.com/x", COLLIDE) == sd.NOISE            # true subdomain
    assert sd.classify_url("https://staging.acme.com/x", COLLIDE) == sd.NOISE
    assert sd.classify_url("https://deploy-abc.vercel.app/x", COLLIDE) == sd.NOISE    # true suffix
    assert sd.classify_url("https://vercel.app/x", COLLIDE) == sd.NOISE               # exact


def test_smoke_checks_all_prod_hosts_not_just_first():
    # second host down → overall False (the secondary-host outage must not be missed).
    def fetch(url):
        return 500 if "www." in url else 200
    assert sd.smoke_prod(["acme.com", "www.acme.com"], ["/"], fetcher=fetch) is False
    # both up → True
    assert sd.smoke_prod(["acme.com", "www.acme.com"], ["/"], fetcher=lambda u: 200) is True


def test_smoke_single_host_str_still_supported():
    assert sd.smoke_prod("acme.com", ["/a"], fetcher=lambda u: 200) is True
    assert sd.smoke_prod("acme.com", ["/a"], fetcher=lambda u: 404) is False
