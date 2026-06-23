"""framework.acting.product_health — cabinet-owned REST health probes for external
product services (Sentry errors today; extensible).

Why REST, not MCP: the front-door briefing is a HEADLESS launchd job, and an MCP only
runs inside a live Claude session — a cron job can't call one. REST is the correct,
testable tool here (same reasoning as the Vercel deploy-health via product_ops_lib).

Read-only + best-effort: tokens come from the process env (the briefing wrapper grafts
them from cabinet/.env); a missing token or unreachable API yields an EMPTY probe, never
an exception. NEVER returns secret material — only issue titles, counts, states.
"""
from __future__ import annotations

import json
import os
import urllib.request


def _get_json(url: str, token: str, *, timeout: int = 20):
    """GET a Bearer-authed JSON endpoint. Returns the parsed body, or None on any
    failure (network, auth, parse) — callers degrade to an empty probe."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def sentry_health(org: str, project: str, *, stats_period: str = "24h", limit: int = 5) -> dict:
    """Unresolved Sentry issues (with events in the window) for one project.

    Returns ``{project, count, issues: [{title, events}]}``. Empty (count 0) when the
    SENTRY_AUTH_TOKEN env is unset, org/project are blank, or the API is unreachable —
    the caller surfaces a briefing item only when count > 0 (quiet when healthy)."""
    token = os.environ.get("SENTRY_AUTH_TOKEN", "")
    if not token or not org or not project:
        return {"project": project, "count": 0, "issues": []}
    url = (f"https://sentry.io/api/0/projects/{org}/{project}/issues/"
           f"?query=is:unresolved&statsPeriod={stats_period}&limit={int(limit)}")
    data = _get_json(url, token)
    if not isinstance(data, list):
        return {"project": project, "count": 0, "issues": []}
    issues = []
    for i in data:
        if not isinstance(i, dict):
            continue
        try:
            ev = int(i.get("count"))
        except (TypeError, ValueError):
            ev = 0
        issues.append({"title": (i.get("title") or "").strip(), "events": ev})
    return {"project": project, "count": len(issues), "issues": issues}
