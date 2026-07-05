"""B2.5 — Sentry outcome probe (error-budget regression read-back).

A read-only observer of the SAME shape the B2.3 GitHub reference probe
established: it reads the post-deploy error signal for trailer-carrying releases
and records the RESULT as a schema-valid consequence outcome joined by the B2.1
correlation-id. It writes nothing to Sentry. Structure copied verbatim from the
reference:

  - a PURE ``classify`` (deterministic burn-rate → status mapping — trivially
    testable),
  - an INJECTABLE client (real impl reads the Sentry API via urllib + local git
    via subprocess arg-lists; tests inject fixtures — a probe must NEVER hit the
    live API in a test),
  - ``run_probe`` orchestrating join → freshness guard → emit through the B2.2
    lib, ending with a healthcheck liveness ping.

THE JOIN. A Sentry release's ``version`` is the deployed commit SHA. The cid is
NOT the SHA — it lives in that commit's message as the ``Cabinet-Proposal-Id``
git trailer (B2.1). So the client enriches each release with its commit message
(``git log`` on the SHA) and ``run_probe`` recovers the cid via
``correlation.from_git_trailer`` — exactly as the GitHub probe recovers it from a
PR body. Attribution holds only within a 6h window of the attributed deploy; a
spike outside that window can belong to a later unrelated deploy, so it is left
``unknown`` (RT#3 spirit — never manufacture an attribution).

TWO freshness disciplines, both mandatory here:

  1. SILENT SOURCE (inherited from ``lib.freshness_guard``, same as GitHub): if
     local git shows commits landed but the Sentry release feed returns nothing
     at all, the source is down — ``hc(SLUG, fail=True)`` and emit NOTHING,
     never a false clean zero.
  2. FROZEN FEED (Sentry-specific): a release's ``lastEvent`` timestamp MUST
     advance between cycles before an at/under-baseline burn may be read as
     ``ok``. Sentry-silent ≠ zero errors — a frozen last-event can mean broken
     ingestion, so a "quiet" release is emitted ``unknown/could_not_observe``,
     never ``ok``. ``run_probe`` carries the prior cycle's per-version
     last-event map in and returns the updated one out for the deploy wrapper to
     persist.

RT#3 and the undecided-proposal guard are inherited from ``lib`` — an
unattributable release emits nothing and credits no officer.
"""
from __future__ import annotations

import json
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from framework.probes import correlation
from framework.probes import lib

SLUG = "probe-sentry"
CADENCE_S = 900                       # 15 min
ATTRIBUTION_WINDOW_HOURS = 6          # a spike joins a deploy only within 6h
BASELINE_REGRESSION_FACTOR = 1.5      # burn ≥ 1.5× the 7d rolling baseline = spike

# ── DEPLOY STATUS (lane-supply 2026-07-05 — the template below is now BUILT) ──
# The three deploy steps the original Nate-gated template named:
#   1. __main__ entry — DONE (below): delegates to runner.probe_main; real
#      SentryClient(org from probes.yml) per project, prior per-version
#      last-event map LOADED from ~/Library/Application Support/cabinet/
#      probe-sentry-seen.json (dir overridable via CABINET_PROBE_STATE_DIR; a
#      --dry-run never persists — a rehearsal must not advance the feed clock),
#      updated map PERSISTED after the cycle; guarded by CABINET_PROBES_ENABLED
#      and a present SENTRY_AUTH_TOKEN (empty value = probe-wide skip).
#   2. services.yml row — DONE: probe-sentry, kind watchdog, interval 900s,
#      command `bash cabinet/scripts/run-probes.sh sentry`. Plist install stays
#      a deliberate human step (cabinet/launchd/INSTALL-flip.md).
#   3. healthchecks 'probe-sentry' check (period 15m + grace) — STILL NATE'S:
#      hc_ping is fail-open without HEALTHCHECKS_PING_KEY.


# --- pure classification -----------------------------------------------------

def classify(stat: dict, *, within_window: bool,
             last_event_advanced: bool) -> tuple[str, str, str]:
    """Map a release's observed error signal to (canonical, probe_status, evidence).

    ``stat`` carries {burn_rate, baseline, last_event, version, new_issues};
    ``baseline`` is the project's 7-day rolling baseline burn rate.

    failed/regressed = burn clearly over baseline within the attribution window;
    ok/within_budget = burn at/under baseline AND the feed is demonstrably live;
    unknown = not attributable, no baseline, no reading, an inconclusive middle
    band, or a frozen feed (could-not-observe). The middle band between baseline
    and the regression factor is a deliberate dead-band so threshold noise never
    flips a proposal between ok and failed cycle-to-cycle."""
    burn = stat.get("burn_rate")
    baseline = stat.get("baseline")

    # No 7-day baseline yet → nothing to compare a burn rate against.
    if baseline is None or baseline <= 0:
        return ("unknown", "held", "no 7d baseline established yet")

    # Outside the 6h attribution window → a spike can't be pinned on THIS
    # proposal's deploy (a later unrelated deploy could own it). RT#3 spirit.
    if not within_window:
        return ("unknown", "held", "outside 6h attribution window")

    if burn is None:
        return ("unknown", "could_not_observe", "no burn-rate reading")

    # Regression: burn clearly above the rolling baseline, within the window.
    # A spike is positive evidence of errors, so it does NOT gate on feed
    # freshness (freshness guards only the "silence read as healthy" path below).
    if burn >= baseline * BASELINE_REGRESSION_FACTOR:
        ni = stat.get("new_issues")
        tail = f", {ni} new issue(s)" if ni else ""
        return ("failed", "regressed",
                f"burn_rate {burn:.3g} ≥ {BASELINE_REGRESSION_FACTOR}× 7d baseline "
                f"{baseline:.3g}{tail}")

    # Within budget: burn at/under baseline — but ONLY trust it if the feed is
    # demonstrably live. A frozen last-event means Sentry-silent, which is NOT
    # the same as zero errors → refuse to read silence as healthy.
    if burn <= baseline:
        if not last_event_advanced:
            return ("unknown", "could_not_observe",
                    "burn within budget but last-event has not advanced — "
                    "Sentry-silent ≠ zero errors")
        return ("ok", "within_budget",
                f"burn_rate {burn:.3g} ≤ 7d baseline {baseline:.3g}, last-event advancing")

    # Elevated but below the regression threshold — inconclusive, re-check next cycle.
    return ("unknown", "held", "burn elevated but below regression threshold")


# --- pure time helpers (no IO — the datetime work run_probe feeds classify) ---

def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp (tolerates a trailing 'Z') to a tz-aware UTC
    datetime, or None if it isn't a parseable string. A naive result is pinned
    to UTC so all comparisons are apples-to-apples."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _within_window(deployed_at: Any, now: datetime) -> bool:
    """True iff the deploy is 0…ATTRIBUTION_WINDOW_HOURS old at ``now``. An
    unparseable/absent deploy time, or a future deploy (clock skew), is NOT
    within the window — a conservative unknown rather than a false attribution."""
    dt = _parse_iso(deployed_at)
    if dt is None:
        return False
    delta = now - dt
    return timedelta(0) <= delta <= timedelta(hours=ATTRIBUTION_WINDOW_HOURS)


def _advanced(prior_last_event: Any, current_last_event: Any) -> bool:
    """True only if we have a current last-event STRICTLY newer than the prior
    cycle's — positive proof the feed is live. No current, no prior (first
    sighting), an unparseable value, or a non-advancing/regressing timestamp all
    read as NOT advanced: we refuse to credit an at/under-baseline burn as ok
    without demonstrated feed liveness (Sentry-silent ≠ zero errors)."""
    cur = _parse_iso(current_last_event)
    prior = _parse_iso(prior_last_event)
    if cur is None or prior is None:
        return False
    return cur > prior


# --- injectable client (real impl reads live; NEVER invoked in tests) --------

class SentryClient:
    """Thin Sentry-API (urllib) + local-git (subprocess arg-lists, shell=False)
    wrapper. Tests inject a fake with the same surface; this real client is
    exercised only by a deployed probe, never in the build or the suite. Every
    read is best-effort: any API/parse error returns an empty/None value so the
    probe degrades to an honest unknown rather than crashing."""

    API = "https://sentry.io/api/0"

    def __init__(self, org: str, token: str | None = None, timeout: int = 20):
        self.org = org
        self.timeout = timeout
        import os
        self._token = token if token is not None else os.environ.get("SENTRY_AUTH_TOKEN", "")

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.API}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self._token}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception:  # noqa: BLE001 — a dead source becomes an honest unknown
            return None

    def release_stats(self, org: str, project: str) -> list[dict]:
        """Recent releases (roughly the attribution window + margin), each
        enriched with the deployed commit's message so run_probe can recover the
        cid trailer. {version, deployed_at, last_event, new_issues, burn_rate,
        commit_message}. Deploy-side; not run here."""
        data = self._get(f"/organizations/{org}/releases/",
                         {"project": project, "per_page": 50}) or []
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=ATTRIBUTION_WINDOW_HOURS + 2)
        out: list[dict] = []
        for rel in data:
            version = rel.get("version")
            deployed_at = ((rel.get("lastDeploy") or {}).get("dateFinished")
                           or rel.get("dateReleased") or rel.get("dateCreated"))
            dt = _parse_iso(deployed_at)
            if version is None or dt is None or dt < cutoff:
                continue
            out.append({
                "version": version,
                "deployed_at": deployed_at,
                "last_event": rel.get("lastEvent"),
                "new_issues": rel.get("newGroups"),
                "burn_rate": self._burn_rate(org, project, version),
                "commit_message": self._commit_message(version),
            })
        return out

    def baseline(self, org: str, project: str) -> float | None:
        """The project's 7-day rolling baseline burn rate (errored-session share
        over the trailing week). Returns None when <7d of history exists so
        classify stays honest (no baseline → unknown, never a fabricated rate).
        Deploy-side; the exact stats_v2 math is illustrative — not run here."""
        stats = self._get(f"/organizations/{org}/stats_v2/", {
            "project": project, "field": "sum(quantity)", "category": "error",
            "interval": "1d", "statsPeriod": "7d"})
        if not isinstance(stats, dict):
            return None
        try:
            groups = stats.get("groups") or []
            days = [sum(g.get("series", {}).get("sum(quantity)", []) or [])
                    for g in groups]
            if len(days) < 7:
                return None
            return sum(days) / len(days)
        except Exception:  # noqa: BLE001
            return None

    def _burn_rate(self, org: str, project: str, version: str) -> float | None:
        """Current error-budget burn rate attributed to ``version`` (this
        release's recent errored share vs the acceptable rate). None on any
        uncertainty. Deploy-side; illustrative — not run here."""
        stats = self._get(f"/organizations/{org}/releases/{version}/stats/",
                         {"project": project})
        if not isinstance(stats, dict):
            return None
        try:
            return float(stats["error_budget"]["burn_rate"])
        except (KeyError, TypeError, ValueError):
            return None

    def _commit_message(self, sha: str) -> str | None:
        """The full commit message body for the release's SHA, from LOCAL git —
        where the B2.1 Cabinet-Proposal-Id trailer lives. subprocess arg-list,
        shell=False. Deploy-side; not run here."""
        cp = subprocess.run(["git", "log", "-1", "--format=%B", sha, "--"],
                            capture_output=True, text=True, timeout=self.timeout)
        return cp.stdout if cp.returncode == 0 else None

    def local_commits_since(self, window: str = "1 hour ago") -> list:
        """Local commit SHAs in the window — the 'activity expected' signal for
        the silent-source guard (deploys follow commits; an empty Sentry feed
        while commits landed suggests the source is down)."""
        cp = subprocess.run(["git", "log", f"--since={window}", "--pretty=%H"],
                           capture_output=True, text=True, timeout=self.timeout)
        return [l for l in cp.stdout.splitlines() if l.strip()] if cp.returncode == 0 else []


# --- orchestration -----------------------------------------------------------

def run_probe(
    *,
    org: str,
    project: str,
    client: Any,
    now: datetime | None = None,
    prior_seen: dict | None = None,
    rows: list | None = None,
    emit: Callable[..., Any] = lib.emit_outcome,
    hc: Callable[..., Any] = lib.hc_ping,
) -> dict:
    """One probe cycle. Returns {fresh, emitted:[...], skipped:[...], seen:{...}}.

    ``prior_seen`` maps release version → the last-event timestamp observed the
    PREVIOUS cycle; the returned ``seen`` is this cycle's updated map for the
    deploy wrapper to persist (the frozen-feed guard needs cross-cycle state)."""
    now = now or datetime.now(timezone.utc)
    prior_seen = prior_seen or {}
    seen = dict(prior_seen)

    stats = client.release_stats(org, project)
    activity = bool(client.local_commits_since())
    fresh = lib.freshness_guard(observed=stats, activity_expected=activity, source="sentry")
    if not fresh["fresh"]:
        hc(SLUG, fail=True)   # silent feed while commits landed — page, don't lie
        return {"fresh": False, "reason": fresh["reason"],
                "emitted": [], "skipped": [], "seen": seen}

    baseline = client.baseline(org, project)
    emitted, skipped = [], []
    for st in stats:
        version = st.get("version")
        cur_le = st.get("last_event")
        prior_le = prior_seen.get(version)
        if version is not None:
            # advance the per-version feed clock for next cycle (keep last-known
            # if this cycle's read is missing, so a one-off gap doesn't reset it)
            seen[version] = cur_le if cur_le is not None else prior_le

        cid = correlation.from_git_trailer(st.get("commit_message") or "")
        if not cid:
            skipped.append({"version": version, "reason": "no-cid"})
            continue

        within = _within_window(st.get("deployed_at"), now)
        advanced = _advanced(prior_le, cur_le)
        status, probe_status, evidence = classify(
            {**st, "baseline": baseline}, within_window=within,
            last_event_advanced=advanced)
        ev = evidence if status != "unknown" else None   # unknown carries no evidence
        res = emit(cid=cid, status=status, probe_status=probe_status,
                   source="sentry", confidence="high", evidence=ev, rows=rows)
        (emitted if res.get("emitted") else skipped).append(
            {"version": version, "cid": cid, "status": status,
             "probe_status": probe_status, **({} if res.get("emitted")
                                              else {"reason": res.get("reason")})})
    hc(SLUG)   # liveness
    return {"fresh": True, "emitted": emitted, "skipped": skipped, "seen": seen}


if __name__ == "__main__":   # the deploy entry the 2026-07-03 review found missing
    import sys

    from framework.probes import runner
    sys.exit(runner.probe_main("sentry", runner.run_sentry_products, SentryClient))
