"""B2.4 — Vercel deploy outcome probe (a fleet replica of the B2.3 reference).

A read-only observer: it reads the fate of the deployments a Cabinet proposal
produced (READY / ERROR / rolled-back) and records the RESULT as a schema-valid
consequence outcome joined by the B2.1 correlation-id. It writes NOTHING to
Vercel. Same structure the reference (``probe_github``) established and every
probe copies:

  - a PURE ``classify`` (deterministic status mapping — trivially testable),
  - PURE join/timing helpers (``cid_for_deployment`` / ``_alias_stable``),
  - an INJECTABLE client (real impl reads the Vercel REST API; tests inject
    fixtures — a probe must NEVER hit the live API in a test),
  - ``run_probe`` orchestrating join → freshness guard → emit through the B2.2
    lib, ending with a healthcheck liveness ping.

The join is META-FIRST: a deploy is stamped ``--meta cabinetProposalId=<cid>``
(``correlation.VERCEL_META_KEY``) at execution time, so the probe reads the cid
straight off ``deployment.meta``; it falls back to the deploy's commit trailer
(``Cabinet-Proposal-Id:`` in the commit message → git-trailer) when the meta key
is absent (e.g. a git-push-triggered deploy). Team scoping is LOAD-BEARING: the
v9 projects list truncates project ids, so the real client always queries
deployments by ``app`` under the fixed ``teamId`` — never a truncated id.

Rollback is a first-class failure: if the production alias is re-pointed to an
OLDER deployment (an instant rollback), the newer, now-unaliased deploy that
previously read ready is superseded ``ready → rolled_back``.

RT#3 and the silent-source guard are inherited from ``lib`` — an unattributable
deploy emits nothing, and an EMPTY deployment list while local git shows pushes
in the window pages the dead-man and emits NOTHING (never a false clean zero).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from typing import Any, Callable

from framework.probes import correlation
from framework.probes import lib

SLUG = "probe-vercel"
CADENCE_S = 600                              # 10 min
TEAM_ID = "team_FEdAEOgfT3WhQ9c1moxCpO2s"    # step-network — team scoping is load-bearing
STABILITY_MIN = 60                           # a READY deploy must hold the alias this long → ok
STABILITY_MS = STABILITY_MIN * 60 * 1000
ROLLBACK_WINDOW_DAYS = 14                    # how far back a rollback can supersede a ready deploy
_FRESHNESS_WINDOW = "15 minutes ago"         # git-activity lookback (10-min cadence + slack)

# ── DEPLOY TEMPLATE (Nate-gated — NOT installed by building this file) ────────
# Built + tested now; going live is a deliberate deploy step (reads Nate's live
# Vercel account) that needs THREE things, none done here:
#   1. a __main__ entry that builds the real VercelClient + reads the product
#      app-name(s) from config, calls run_probe per product, and exits
#      (StartCalendarInterval one-shot), guarded by CABINET_PROBES_ENABLED and a
#      present VERCEL_API_KEY.
#   2. a services.yml row (promote kind → watchdog so generate-plists renders it):
#        - name: probe-vercel
#          label: com.cabinet.probe-vercel
#          kind: watchdog
#          command: python3.12 -m framework.probes.probe_vercel
#          schedule: { interval_s: 600 }
#          expected: "healthchecks 'probe-vercel' pinged 10-min; /fail on silent source"
#   3. create the healthchecks 'probe-vercel' check (period 10m, grace) + assign a
#      channel — same as the F0.13 checks.
# Until all three land, this module is import-only: nothing schedules it, nothing
# touches the live API.


# --- pure classification -----------------------------------------------------

def _alias_stable(ready_ms: Any, now_ms: Any, min_ms: int = STABILITY_MS) -> bool:
    """True iff a READY deployment has held for ≥ the stability window.

    ``ready_ms``/``now_ms`` are epoch MILLISECONDS (Vercel's clock). A missing or
    non-numeric timestamp is NOT stable (no signal ≠ stable). ``bool`` is an int
    subclass in Python — reject it explicitly so a stray True/False can't pass."""
    if isinstance(ready_ms, bool) or isinstance(now_ms, bool):
        return False
    if not isinstance(ready_ms, (int, float)) or not isinstance(now_ms, (int, float)):
        return False
    return (now_ms - ready_ms) >= min_ms


def classify(dep: dict, rolled_back: bool, alias_stable: bool) -> tuple[str, str, str]:
    """Map a deployment's observed state to (canonical_status, probe_status, evidence).

    ok/deploy_ready = the deploy went live and HELD its stability window;
    failed = it errored, or the prod alias was rolled back off it; unknown = not
    yet final (a READY deploy still inside the window, or a build in flight) —
    re-emitted next cycle. A rollback SUPERSEDES even a stable READY."""
    state = (dep.get("readyState") or dep.get("state") or "").upper()

    if rolled_back:
        return ("failed", "rolled_back",
                f"production alias re-pointed to an older deployment (rollback) "
                f"within {ROLLBACK_WINDOW_DAYS}d")
    if state == "ERROR":
        return ("failed", "deploy_error", "deployment errored (build/deploy failed)")
    if state == "READY":
        if alias_stable:
            return ("ok", "deploy_ready",
                    f"READY, production alias stable ≥{STABILITY_MIN}min")
        return ("unknown", "stabilizing",
                f"READY but inside the {STABILITY_MIN}min stability window")
    # BUILDING / QUEUED / INITIALIZING / CANCELED / anything else: not final
    return ("unknown", "held", f"state={state or 'unknown'}, not final")


# --- pure correlation-id recovery --------------------------------------------

def cid_for_deployment(dep: dict, resolve_sha: Callable[[str], Any] | None = None) -> str | None:
    """Recover the correlation-id from a deployment. Meta-first (the id we stamp
    at deploy time), then the commit trailer.

    1. ``deployment.meta[VERCEL_META_KEY]`` — the ``--meta cabinetProposalId=<cid>``
       stamp; taken only if it is a well-formed cid.
    2. fallback: the ``Cabinet-Proposal-Id:`` trailer in the deploy's commit
       message — read straight off ``meta.githubCommitMessage`` when Vercel
       carries it, else resolved from the commit sha via ``resolve_sha`` (git).
    Strict, prefix-anchored extraction (``correlation.from_git_trailer``) so
    untrusted commit text cannot smuggle a false id past the join."""
    meta = dep.get("meta") or {}
    stamped = meta.get(correlation.VERCEL_META_KEY)
    if correlation.is_cid(stamped or ""):
        return stamped
    msg = meta.get("githubCommitMessage")
    if msg:
        cid = correlation.from_git_trailer(msg)
        if cid:
            return cid
    sha = meta.get("githubCommitSha") or meta.get("gitCommitSha")
    if sha and resolve_sha is not None:
        resolved = resolve_sha(sha)
        if resolved:
            return correlation.from_git_trailer(resolved)
    return None


# --- injectable client (real impl reads the API; NEVER invoked in tests) ------

_SHA_RE = re.compile(r"\A[0-9a-fA-F]{7,40}\Z")


class VercelClient:
    """Thin Vercel REST + git wrapper. Network reads are urllib GETs to the fixed
    ``api.vercel.com`` host, team-scoped and bearer-authed from ``VERCEL_API_KEY``
    in the environment (never hardcoded, never logged). Git reads are subprocess
    arg-lists (shell=False). Tests inject a fake with the same surface; this real
    client is exercised only by a deployed probe, never in the build or the suite.
    """

    BASE = "https://api.vercel.com"

    def __init__(self, token: str | None = None, team_id: str = TEAM_ID, timeout: int = 20):
        self.token = token or os.environ.get("VERCEL_API_KEY", "")
        self.team_id = team_id
        self.timeout = timeout

    def _get(self, path: str, params: dict) -> Any:
        """One team-scoped GET → parsed JSON | None. Fail-closed: a missing token,
        HTTP error, or malformed body returns None (never raises into the probe).
        The host is fixed and params are urlencoded — no dynamic-URL SSRF surface."""
        q = urllib.parse.urlencode({**params, "teamId": self.team_id})
        req = urllib.request.Request(
            f"{self.BASE}{path}?{q}",
            headers={"Authorization": f"Bearer {self.token}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read())
        except Exception:  # noqa: BLE001 — a read failure must never crash the probe
            return None

    def deployments(self, product: str, limit: int = 50) -> list:
        """Recent deployments for one product, team-scoped by ``app`` (NOT a
        project id — the v9 projects list truncates ids, so we query by app under
        the fixed teamId). Returns Vercel's deployment dicts."""
        data = self._get("/v6/deployments", {"app": product, "limit": limit}) or {}
        return data.get("deployments") or []

    def _production_alias_uid(self, product: str) -> str | None:
        """The uid of the deployment CURRENTLY serving the production alias — the
        deploy the alias resolves to right now. Deploy-side (finalized against the
        live alias/target endpoint at deploy time); not run in tests."""
        data = self._get("/v6/deployments",
                         {"app": product, "target": "production",
                          "state": "READY", "limit": 1}) or {}
        deps = data.get("deployments") or []
        if not deps:
            return None
        d = deps[0]
        return d.get("uid") or d.get("id")

    def rolled_back_uids(self, product: str, since_days: int = ROLLBACK_WINDOW_DAYS) -> set:
        """Deployment uids a rollback has SUPERSEDED: the production alias now
        points to an OLDER ready deployment than one (or more) more-recent ready
        production deploys — those newer, now-unaliased deploys were rolled past.
        Parsed from the deployments list + the current alias; deploy-side, not run
        in tests."""
        cutoff_ms = (time.time() - since_days * 86400) * 1000
        prod = [d for d in self.deployments(product)
                if d.get("target") == "production"
                and (d.get("readyState") or d.get("state") or "").upper() == "READY"
                and (d.get("created") or 0) >= cutoff_ms]
        current = self._production_alias_uid(product)
        if not current or len(prod) < 2:
            return set()
        cur = next((d for d in prod if (d.get("uid") or d.get("id")) == current), None)
        if cur is None:
            return set()
        cur_created = cur.get("created") or 0
        # every ready prod deploy NEWER than the one the alias now points to was
        # rolled past (the alias moved backwards to an older deploy).
        return {(d.get("uid") or d.get("id")) for d in prod
                if (d.get("created") or 0) > cur_created}

    def commit_message(self, sha: str) -> str | None:
        """The commit message for ``sha`` (the trailer fallback). subprocess
        arg-list, shell=False; ``sha`` is validated hex and the args are
        end-fenced so a leading-dash value can never be read as a git option —
        no untrusted text reaches a shell or the option parser."""
        if not (isinstance(sha, str) and _SHA_RE.match(sha)):
            return None
        cp = subprocess.run(["git", "log", "-1", "--format=%B", sha, "--"],
                            capture_output=True, text=True, timeout=self.timeout)
        return cp.stdout if cp.returncode == 0 and cp.stdout.strip() else None

    def local_commits_since(self, window: str = _FRESHNESS_WINDOW) -> list:
        """Local commit shas in the window — the freshness signal (were there
        pushes we'd expect a deploy for?). subprocess arg-list, shell=False."""
        cp = subprocess.run(["git", "log", f"--since={window}", "--pretty=%H"],
                           capture_output=True, text=True, timeout=self.timeout)
        return [ln for ln in cp.stdout.splitlines() if ln.strip()] if cp.returncode == 0 else []

    def now_ms(self) -> int:
        """Current epoch in milliseconds (Vercel's clock) for the stability window."""
        return int(time.time() * 1000)


# --- orchestration -----------------------------------------------------------

def run_probe(
    *,
    product: str,
    client: Any,
    rows: list | None = None,
    emit: Callable[..., Any] = lib.emit_outcome,
    hc: Callable[..., Any] = lib.hc_ping,
) -> dict:
    """One probe cycle for one product. Returns {fresh, emitted:[...], skipped:[...]}."""
    deps = client.deployments(product)
    activity = bool(client.local_commits_since())
    fresh = lib.freshness_guard(observed=deps, activity_expected=activity, source="vercel")
    if not fresh["fresh"]:
        hc(SLUG, fail=True)   # git pushed but Vercel returned nothing — page, don't lie
        return {"fresh": False, "reason": fresh["reason"], "emitted": [], "skipped": []}

    rolled = client.rolled_back_uids(product)
    now_ms = client.now_ms()
    emitted, skipped = [], []
    for dep in deps:
        uid = dep.get("uid") or dep.get("id")
        cid = cid_for_deployment(dep, resolve_sha=client.commit_message)
        if not cid:
            skipped.append({"uid": uid, "reason": "no-cid"})
            continue
        rolled_back = uid in rolled
        ready_ms = dep.get("ready") or dep.get("readyAt") or dep.get("created")
        alias_stable = _alias_stable(ready_ms, now_ms)
        status, probe_status, evidence = classify(dep, rolled_back, alias_stable)
        ev = evidence if status != "unknown" else None   # unknown carries no evidence
        res = emit(cid=cid, status=status, probe_status=probe_status,
                   source="vercel", confidence="high", evidence=ev, rows=rows)
        (emitted if res.get("emitted") else skipped).append(
            {"uid": uid, "cid": cid, "status": status,
             "probe_status": probe_status, **({} if res.get("emitted")
                                              else {"reason": res.get("reason")})})
    hc(SLUG)   # liveness
    return {"fresh": True, "emitted": emitted, "skipped": skipped}
