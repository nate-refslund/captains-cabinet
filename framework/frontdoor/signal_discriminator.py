"""framework.frontdoor.signal_discriminator — lane-agnostic verified-noise discriminator.

Separates a LIVE operational failure from the chronic / frozen / staging / bot /
R&D / stale false-positive class BEFORE the front-door synthesis relays it as an
incident. This is the framework generalization of an instance-owned reference
implementation and contract; all lane-specific tells and verification fixtures
remain outside the framework package.

THE CORE INSIGHT (contract §): a Sentry issue's ``count`` is CUMULATIVE-since-
firstSeen, NOT a 24h rate. ``statsPeriod=24h`` selects WHICH issues to list; the
count is the all-time total. So "Failed query 2811" with ``lastSeen`` 83h ago
contributed ZERO in the last 83h. The magnitude signal and the recency signal are
DIFFERENT fields — you need both. Reading count as current volume is the root
false-positive.

CORE (this module) = the LOGIC, lane-agnostic: recency (freshness cutoffs: 15m
ongoing / 120m attribution gate), the host/path → verdict attribution tree, the
verdict enum + precedence, and smoke-outranks-count. The magnitude signal (count
delta vs a prior carded baseline) is COMPUTED and reported per issue but does NOT
drive the verdict today — recency + attribution do; wiring a persisted baseline into
the verdict is a follow-up (see docs/plans/frontdoor-signal-discriminator-2026-07-14.md).
TELLS (per lane) = the prod-host allowlist, staging excludes, bot/template patterns,
smoke paths — supplied by the caller, resolved from instance config through the
sanctioned seam ``framework.env.signal_tells``, NEVER hardcoded or read here (this
module holds zero instance-config paths; clean-room ratchet: no launcher data in
framework/).

FAIL-OPEN (load-bearing safety property): this module classifies a signal as NOISE
(→ the caller suppresses it) ONLY with affirmative evidence — a settled/frozen issue
(recency), or a fresh issue that positively attributes to a bot/staging/preview tell.
On ANY uncertainty — no tells, unparseable timestamp, un-fetchable or unclassified
url — it returns INCONCLUSIVE, and the caller PASSES THE SIGNAL THROUGH unchanged
(today's raw behavior). It never suppresses a signal it cannot positively explain, so
a mis- or un-configured lane degrades to the current noisy-but-safe behavior, never to
a hidden real incident.

Pure logic + injected I/O: ``classify_issue``/``overall_sentry_verdict`` take an
injected ``url_fetcher`` and a ``smoke_ok`` bool, so the whole decision tree is unit
tested with zero network. The network helpers (``fetch_issue_url``, ``smoke_prod``)
are thin, best-effort, and never raise into the caller.
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
from typing import Callable, Optional

# --- freshness cutoffs (minutes) — from the contract -------------------------
_ONGOING_MAX_MIN = 15      # lastSeen within 15m ⇒ ongoing; older ⇒ frozen/settled
_ATTRIBUTE_MAX_MIN = 120   # only fetch+classify the url tag if active within 2h;
#                            older issues are settled ⇒ default NOISE (cheap: skips
#                            the event fetch for the frozen majority).

# --- per-issue verdicts ------------------------------------------------------
NOISE = "noise"
REAL_USER = "real-user-suspect"
INCONCLUSIVE = "inconclusive"

# --- overall verdicts (contract precedence, high→low) ------------------------
V_NO_UNRESOLVED = "NO_UNRESOLVED"
V_REAL_USER = "REAL_USER_SUSPECT"
V_PROD_NON_200 = "PROD_SMOKE_NON_200"
V_NOISE = "NOISE"
V_INCONCLUSIVE = "INCONCLUSIVE"

def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def age_minutes(last_seen: str | None, *, now: datetime.datetime | None = None) -> Optional[float]:
    """Age of a Sentry ``lastSeen`` ISO timestamp in minutes; ``None`` if empty or
    unparseable (an unknown age is uncertainty, handled as fail-open by callers)."""
    if not last_seen:
        return None
    now = now or _now()
    try:
        t = datetime.datetime.strptime(str(last_seen)[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=datetime.timezone.utc)
    except Exception:
        return None
    return (now - t).total_seconds() / 60.0


def freshness(age_min: Optional[float]) -> str:
    """ongoing (≤15m) | frozen (>15m) | unknown (un-aged)."""
    if age_min is None:
        return "unknown"
    return "ongoing" if age_min <= _ONGOING_MAX_MIN else "frozen"


def _split_url(url: str) -> tuple[str, str]:
    """(host, path) lowercased-host from a url; ('','') if empty/unparseable."""
    if not url:
        return "", ""
    m = re.match(r"^https?://([^/]+)(/.*)?$", url.strip())
    if not m:
        return "", ""
    return m.group(1).lower(), (m.group(2) or "")


def _host_matches(host: str, patterns) -> bool:
    """True if any pattern matches host at a LABEL boundary — the pattern equals the
    host, is a leading subdomain label (``test.`` → ``test.acme.com``), or is a trailing
    registrable suffix (``vercel.app`` → ``x.vercel.app``). Anchored, deliberately NOT a
    bare substring: an unanchored ``p in host`` would let a legit prod host that merely
    CONTAINS a staging/bot fragment (e.g. prod ``latest.acme.com`` with a ``test`` tell,
    or ``notvercel.app``) be wrongly classified noise and a REAL incident suppressed —
    the one thing the discriminator must never do. Patterns are plain fragments, never
    regex, so an instance-config typo can't blow up the briefing."""
    for p in patterns or ():
        if not p:
            continue
        p = str(p).strip().lower().strip(".")
        if not p:
            continue
        if host == p or host.startswith(p + ".") or host.endswith("." + p):
            return True
    return False


def classify_url(url: str, tells: dict) -> str:
    """Attribution tree (contract §URL-TAG). Staging and bot tells are tested BEFORE the
    prod allowlist as defense-in-depth, but the load-bearing guarantee is the prod match
    itself: it is EXACT host-allowlist membership, never a suffix/regex. That is the
    contract's MUST-FIX — a suffix like ``.acme.com$`` would also match
    ``staging.acme.com``. So a staging host is excluded two independent ways: (a) it
    matches ``staging_host_patterns``, and (b) it is absent from the exact ``prod_hosts``
    set, so it can never resolve to real-user regardless of test order. Belt and
    suspenders on the staging≠prod class the discriminator exists to kill.
    """
    host, path = _split_url(url)
    if not host:
        return INCONCLUSIVE                                   # empty/garbled url ⇒ can't attribute
    if _host_matches(host, tells.get("staging_host_patterns")):
        return NOISE                                          # staging ≠ prod (explicit)
    template_pat = tells.get("template_path_pattern") or r"\[[a-zA-Z]"
    if _host_matches(host, tells.get("bot_host_patterns")) or re.search(template_pat, path):
        return NOISE                                          # preview-hash host / unresolved route template
    prod_hosts = {str(h).lower() for h in (tells.get("prod_hosts") or ())}
    if host in prod_hosts:
        return REAL_USER                                      # EXACT prod host + resolved path
    return INCONCLUSIVE                                       # unclassified host ⇒ fail-open


def classify_issue(issue: dict, tells: dict, *, now: datetime.datetime | None = None,
                   baseline: dict | None = None,
                   url_fetcher: Optional[Callable[[str], str]] = None) -> dict:
    """Classify ONE Sentry issue: magnitude-delta + recency + (only if active <2h)
    url attribution. Returns
    ``{short_id, count, age_min, freshness, delta, verdict, attribution}``.

    ``baseline`` maps a shortId trailing-char → a prior carded count (magnitude delta
    is informational — ``Δ=+0`` means nothing new since last carded). ``url_fetcher``
    (issue-id → url string) is injected so attribution is network-isolated in tests.
    """
    now = now or _now()
    baseline = baseline or {}
    sid = str(issue.get("shortId") or issue.get("short_id") or "")
    cid = str(issue.get("id") or "")
    try:
        count = int(issue.get("count") if issue.get("count") is not None else issue.get("events") or 0)
    except (TypeError, ValueError):
        count = 0
    last_seen = issue.get("lastSeen") or issue.get("last_seen") or ""
    am = age_minutes(last_seen, now=now)
    fresh = freshness(am)

    suffix = sid.split("-")[-1] if "-" in sid else sid
    delta = None
    if suffix in baseline:
        try:
            delta = count - int(baseline[suffix])
        except (TypeError, ValueError):
            delta = None

    attribution = ""
    if am is None:
        verdict = INCONCLUSIVE                 # can't assess recency ⇒ fail-open, don't suppress
    elif am > _ATTRIBUTE_MAX_MIN:
        verdict = NOISE                        # settled/frozen >2h ⇒ affirmative recency evidence
    else:
        url = ""
        if url_fetcher is not None:
            try:
                url = url_fetcher(cid) or ""
            except Exception:
                url = ""
        verdict = classify_url(url, tells)
        attribution = url

    return {"short_id": sid, "count": count, "age_min": am, "freshness": fresh,
            "delta": delta, "verdict": verdict, "attribution": attribution}


def overall_sentry_verdict(classified: list[dict], *, smoke_ok: Optional[bool]) -> str:
    """Reduce per-issue verdicts to one overall verdict, in the contract's precedence:

      NO_UNRESOLVED > REAL_USER_SUSPECT > PROD_SMOKE_NON_200 > NOISE

    with an added INCONCLUSIVE rung for fail-open. ``smoke_ok``: True = prod serving
    all-200, False = a prod smoke path is non-200, None = smoke not performed (can't
    assert either way — never raise PROD_NON_200 on an absent smoke).

    Suppress (V_NOISE) ONLY when EVERY issue is affirmatively NOISE. If any issue is
    INCONCLUSIVE (unparseable, un-fetchable, unclassified host, or no tells), return
    V_INCONCLUSIVE so the caller passes the signal through unchanged.
    """
    if not classified:
        return V_NO_UNRESOLVED
    if any(c.get("verdict") == REAL_USER for c in classified):
        return V_REAL_USER                     # a real-user attribution outranks a green smoke
    if smoke_ok is False:
        return V_PROD_NON_200                   # serving is down ⇒ investigate regardless
    if all(c.get("verdict") == NOISE for c in classified):
        return V_NOISE                          # every issue positively explained as noise ⇒ suppress
    return V_INCONCLUSIVE                        # at least one uncertain ⇒ fail-open pass-through


# ---------------------------------------------------------------------------
# Network helpers (best-effort; never raise into the caller). Kept thin so the
# decision tree above stays pure + fully unit-tested via injection. Per-lane TELLS
# are NOT read here — the caller resolves them via framework.env.signal_tells (the
# sanctioned instance-config seam), so this module holds zero instance-config paths.
# ---------------------------------------------------------------------------
def fetch_issue_url(issue_id: str, org: str, token: str, *, timeout: int = 12) -> str:
    """Latest event's ``url`` tag for a Sentry issue (org-scoped endpoint — the
    project-scoped one 404s). Returns '' on any failure. The token is never logged."""
    if not issue_id or not org or not token:
        return ""
    api = f"https://sentry.io/api/0/organizations/{org}/issues/{issue_id}/events/latest/"
    try:
        import urllib.request
        req = urllib.request.Request(api, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            e = json.loads(r.read().decode())
        tags = {t.get("key"): t.get("value") for t in (e.get("tags") or []) if isinstance(t, dict)}
        return tags.get("url") or ""
    except Exception:
        return ""


def smoke_prod(prod_hosts, smoke_paths, *, timeout: int = 12,
               fetcher: Optional[Callable[[str], int]] = None) -> Optional[bool]:
    """GET ``https://<host><path>`` for EVERY (prod_host × smoke_path); True iff ALL
    return 200, False if any is non-200/unreachable, None if there is nothing to smoke
    (no host or no paths ⇒ smoke not performed, so the caller must not treat it as a
    failure).

    ``prod_hosts`` accepts a single host str OR a list — ALL configured prod hosts are
    checked, because a secondary-host outage (e.g. ``www.`` down while apex is up) is a
    real incident. Follows redirects (``-L``) so a normal apex↔www / http→https 301 is
    not read as a spurious non-200 (that would be a NEW false positive in a
    false-positive-reducing change). ``fetcher`` (url → http status int) is injected in
    tests; live it uses curl with the same connect/max timeouts the reference impl relies
    on."""
    if isinstance(prod_hosts, str):
        prod_hosts = [prod_hosts]
    hosts = [h for h in (prod_hosts or []) if h]
    paths = [p for p in (smoke_paths or []) if p]
    if not hosts or not paths:
        return None
    def _live(url: str) -> int:
        try:
            out = subprocess.run(
                ["/usr/bin/curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}",
                 "--connect-timeout", "6", "--max-time", str(timeout), url],
                capture_output=True, text=True, timeout=timeout + 3)
            return int((out.stdout or "0").strip() or 0)
        except Exception:
            return 0
    get = fetcher or _live
    for host in hosts:
        for path in paths:
            if get(f"https://{host}{path}") != 200:
                return False
    return True
