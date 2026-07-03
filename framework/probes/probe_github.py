"""B2.3 — GitHub outcome probe (the REFERENCE probe the fleet replicates).

A read-only observer: it reads the state of trailer-carrying PRs (state, merge,
checks, reverts) and records the RESULT as a schema-valid consequence outcome
joined by the B2.1 correlation-id. It writes nothing to GitHub. Structure every
probe copies:

  - a PURE ``classify`` (deterministic status mapping — trivially testable),
  - an INJECTABLE client (real impl shells out; tests inject fixtures — a probe
    must NEVER hit the live API in a test),
  - ``run_probe`` orchestrating join → freshness guard → emit through the B2.2
    lib, ending with a healthcheck liveness ping.

RT#3 and the silent-source guard are inherited from ``lib`` — an unattributable
PR emits nothing, and an empty API read while local git shows activity becomes an
honest ``unknown``, never a false clean zero.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any, Callable

from framework.probes import correlation
from framework.probes import lib

SLUG = "probe-github"
CADENCE_S = 300                 # 5 min
REVERT_WINDOW_DAYS = 14

# ── DEPLOY TEMPLATE (Nate-gated — NOT installed by building this file) ────────
# Built + tested now; going live is a deliberate deploy step (reads Nate's live
# GitHub) that needs THREE things, none done here:
#   1. a __main__ entry that builds the real GhClient + reads the product repo(s)
#      from config, calls run_probe per repo, and exits (StartCalendarInterval
#      one-shot), guarded by CABINET_PROBES_ENABLED.
#   2. a services.yml row (promote kind → watchdog so generate-plists renders it):
#        - name: probe-github
#          label: com.cabinet.probe-github
#          kind: watchdog
#          command: python3.12 -m framework.probes.probe_github
#          schedule: { interval_s: 300 }
#          expected: "healthchecks 'probe-github' pinged 5-min; /fail on silent source"
#   3. create the healthchecks 'probe-github' check (period 5m, grace) + assign a
#      channel — same as the F0.13 checks.
# Until all three land, this module is import-only: nothing schedules it, nothing
# touches the live API.


# --- pure classification -----------------------------------------------------

def _checks_green(rollup: list | None) -> bool:
    """True iff every check run in a statusCheckRollup is a passing conclusion.
    An empty rollup is NOT green (no signal ≠ success)."""
    runs = rollup or []
    if not runs:
        return False
    ok = {"SUCCESS", "NEUTRAL", "SKIPPED"}
    for r in runs:
        concl = (r.get("conclusion") or r.get("state") or "").upper()
        if concl not in ok:
            return False
    return True


def classify(pr_view: dict, reverted: bool) -> tuple[str, str, str]:
    """Map a PR's observed state to (canonical_status, probe_status, evidence).

    ok/merged = the change landed and holds; failed/reverted = it was undone;
    unknown = not yet final (re-emitted next cycle). ci_green on an OPEN pr is a
    positive-but-not-final signal, deliberately unknown."""
    state = (pr_view.get("state") or "").upper()
    merged_at = pr_view.get("mergedAt")
    green = _checks_green(pr_view.get("statusCheckRollup"))

    if reverted:
        return ("failed", "reverted",
                f"reverted on default branch within {REVERT_WINDOW_DAYS}d")
    if state == "MERGED" or merged_at:
        tail = ", checks green" if green else ""
        return ("ok", "merged", f"merged {merged_at or '(unknown time)'}{tail}")
    if state == "OPEN":
        if green:
            return ("unknown", "ci_green", "open, checks green, not yet merged")
        return ("unknown", "held", "open, checks pending or failing")
    # CLOSED-unmerged / anything else: abandoned, no clear success or revert
    return ("unknown", "held", f"state={state or 'unknown'}, unmerged")


# --- injectable client (real impl shells out; NEVER invoked in tests) --------

class GhClient:
    """Thin ``gh``/``git`` wrapper. All calls are subprocess arg-lists
    (shell=False). Tests inject a fake with the same surface; this real client is
    exercised only by a deployed probe, never in the build or the suite."""

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def _gh_json(self, args: list[str]) -> Any:
        cp = subprocess.run(["gh", *args], capture_output=True, text=True,
                            timeout=self.timeout)
        if cp.returncode != 0 or not cp.stdout.strip():
            return None
        try:
            return json.loads(cp.stdout)
        except json.JSONDecodeError:
            return None

    def trailer_prs(self, repo: str) -> list[dict]:
        """Open+recently-merged PRs whose body carries the correlation trailer.
        Returns [{number, body, merge_sha}]; the caller extracts the cid."""
        data = self._gh_json(["pr", "list", "--repo", repo, "--state", "all",
                              "--limit", "50", "--json", "number,body,mergeCommit"]) or []
        out = []
        for pr in data:
            body = pr.get("body") or ""
            if correlation.from_git_trailer(body):
                out.append({"number": pr.get("number"), "body": body,
                            "merge_sha": (pr.get("mergeCommit") or {}).get("oid")})
        return out

    def pr_view(self, repo: str, number: int) -> dict:
        return self._gh_json(["pr", "view", str(number), "--repo", repo, "--json",
                             "state,mergedAt,statusCheckRollup"]) or {}

    def reverts(self, repo: str, since_days: int = REVERT_WINDOW_DAYS) -> set:
        """PR numbers / merge-shas that a default-branch revert commit names in
        the window. Parsed from `git log` 'Reverts #<n>' / 'This reverts commit
        <sha>' — deploy-side; not run here."""
        cp = subprocess.run(
            ["git", "log", f"--since={since_days} days ago", "--grep=[Rr]evert",
             "--pretty=%H%n%B%n==="], capture_output=True, text=True,
            timeout=self.timeout)
        found: set = set()
        if cp.returncode == 0:
            import re
            for m in re.finditer(r"[Rr]everts?\s+#(\d+)", cp.stdout):
                found.add(int(m.group(1)))
            for m in re.finditer(r"[Tt]his reverts commit\s+([0-9a-f]{7,40})", cp.stdout):
                found.add(m.group(1))
        return found

    def local_commits_since(self, window: str = "1 hour ago") -> list:
        cp = subprocess.run(["git", "log", f"--since={window}", "--pretty=%H"],
                           capture_output=True, text=True, timeout=self.timeout)
        return [l for l in cp.stdout.splitlines() if l.strip()] if cp.returncode == 0 else []


# --- orchestration -----------------------------------------------------------

def run_probe(
    *,
    repo: str,
    client: Any,
    rows: list | None = None,
    emit: Callable[..., Any] = lib.emit_outcome,
    hc: Callable[..., Any] = lib.hc_ping,
) -> dict:
    """One probe cycle. Returns {fresh, emitted:[...], skipped:[...]}."""
    prs = client.trailer_prs(repo)
    activity = bool(client.local_commits_since())
    fresh = lib.freshness_guard(observed=prs, activity_expected=activity, source="github")
    if not fresh["fresh"]:
        hc(SLUG, fail=True)   # silent source while commits landed — page, don't lie
        return {"fresh": False, "reason": fresh["reason"], "emitted": [], "skipped": []}

    reverts = client.reverts(repo)
    emitted, skipped = [], []
    for pr in prs:
        cid = correlation.from_git_trailer(pr.get("body") or "")
        if not cid:
            skipped.append({"number": pr.get("number"), "reason": "no-cid"})
            continue
        view = client.pr_view(repo, pr["number"])
        reverted = pr.get("number") in reverts or (pr.get("merge_sha") in reverts
                                                   if pr.get("merge_sha") else False)
        status, probe_status, evidence = classify(view, reverted)
        ev = evidence if status != "unknown" else None   # unknown carries no evidence
        res = emit(cid=cid, status=status, probe_status=probe_status,
                   source="github", confidence="high", evidence=ev, rows=rows)
        (emitted if res.get("emitted") else skipped).append(
            {"number": pr["number"], "cid": cid, "status": status,
             "probe_status": probe_status, **({} if res.get("emitted")
                                              else {"reason": res.get("reason")})})
    hc(SLUG)   # liveness
    return {"fresh": True, "emitted": emitted, "skipped": skipped}
