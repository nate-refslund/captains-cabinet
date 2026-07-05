"""B2.6 — CI-runs outcome probe (replicates the B2.3 GitHub reference probe).

A read-only observer of the product's CI: it reads the terminal state of the
latest workflow runs (``gh run list``), joins each run back to the Cabinet
proposal that caused it via the head-SHA commit's B2.1 trailer, and records the
RESULT as a schema-valid consequence outcome. It writes nothing to GitHub or
CI. Structure copied from ``probe_github``:

  - a PURE ``classify`` (deterministic status mapping — trivially testable),
  - an INJECTABLE client (real impl shells out via ``gh``/``git`` arg-lists;
    tests inject fixtures — a probe must NEVER hit the live API in a test),
  - ``run_probe`` orchestrating join → freshness guard → emit through the B2.2
    lib, ending with a healthcheck liveness ping.

Status mapping (conclusion is the terminal truth; a run with no terminal
conclusion is still in-flight):
  - conclusion SUCCESS                       → ok     / ci_green
  - conclusion FAILURE / TIMED_OUT / CANCELLED → failed / ci_red
  - status in_progress / queued (or any non-terminal conclusion) → unknown

B2.10 Goodhart guard (the join that keeps CI honest): a run whose PR touches
ONLY test files is stamped ``graduation-credit:false`` in refs — a green CI on a
test-only diff exercises no feature code, so it must never advance graduation
[RT#1]. A mixed diff (feature + tests) keeps credit; an undeterminable file set
(empty) keeps credit rather than silently suppress it.

RT#3 and the silent-source guard are inherited from ``lib`` — a run whose SHA
carries no trailer is UNATTRIBUTABLE and emits nothing, and an empty runs list
while local git shows pushes becomes an honest hc-fail page, never a false
clean zero.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Callable

from framework.probes import correlation
from framework.probes import lib

SLUG = "probe-ci"
CADENCE_S = 300                 # 5 min

# B2.10: the refs stamp that removes a run from graduation-advancing evidence.
GRAD_CREDIT_FALSE_REF = "graduation-credit:false"

# CI conclusions that are a definitive regression (→ failed / ci_red). Other
# non-SUCCESS conclusions (NEUTRAL, SKIPPED, STALE, ACTION_REQUIRED, none-yet)
# are NOT decisive → unknown, re-observed next cycle rather than scored a loss.
_RED_CONCLUSIONS = {"FAILURE", "TIMED_OUT", "CANCELLED"}

# ── DEPLOY TEMPLATE (Captain-gated — NOT installed by building this file) ────────
# Built + tested now; going live is a deliberate deploy step (reads the Captain's live
# GitHub CI) that needs THREE things, none done here:
#   1. a __main__ entry that builds the real GhCiClient + reads the product
#      repo(s) and their CI workflow name (<product-ci>) from config, calls
#      run_probe per (repo, workflow), and exits (StartCalendarInterval
#      one-shot), guarded by CABINET_PROBES_ENABLED.
#   2. a services.yml row (promote kind → watchdog so generate-plists renders it):
#        - name: probe-ci
#          label: com.cabinet.probe-ci
#          kind: watchdog
#          command: python3.12 -m framework.probes.probe_ci
#          schedule: { interval_s: 300 }
#          expected: "healthchecks 'probe-ci' pinged 5-min; /fail on silent source"
#   3. create the healthchecks 'probe-ci' check (period 5m, grace) + assign a
#      channel — same as the F0.13 checks.
# Until all three land, this module is import-only: nothing schedules it, nothing
# touches the live API.


# --- pure classification -----------------------------------------------------

def classify(run: dict) -> tuple[str, str, str]:
    """Map one CI run's observed state to (canonical_status, probe_status,
    evidence).

    ok/ci_green = CI passed and holds; failed/ci_red = CI regressed;
    unknown = in-flight (queued / in_progress) or a non-terminal conclusion,
    re-emitted next cycle. The conclusion is authoritative for a completed run;
    an in-flight run has a null conclusion."""
    concl = (run.get("conclusion") or "").upper()
    status_raw = (run.get("status") or "").lower()
    if concl == "SUCCESS":
        return ("ok", "ci_green", "CI run completed with conclusion=SUCCESS")
    if concl in _RED_CONCLUSIONS:
        return ("failed", "ci_red", f"CI run completed with conclusion={concl}")
    return ("unknown", "ci_running",
            f"status={status_raw or 'unknown'}, conclusion={concl or 'none'}")


# --- B2.10 test-only diff detection (pure) -----------------------------------

# A path is a test file iff it lives under a test/spec directory OR its basename
# is a language-conventional test module. Anchored so a mere "test" substring
# (testimonials.ts, latest.py, contest.js) never counts.
_TEST_FILE_RE = re.compile(
    r"""
      (^|/)(tests?|__tests__|specs?)/     # a tests/ test/ __tests__/ spec(s)/ dir segment
    | (^|/)test_[^/]*\.py$                 # python  test_*.py
    | _test\.py$                           # python  *_test.py
    | _test\.go$                           # go      *_test.go
    | \.(test|spec)\.[cm]?[jt]sx?$         # js/ts   *.test.* / *.spec.* (+ .mjs/.cjs/.mts)
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _is_test_file(path: str) -> bool:
    return bool(path) and bool(_TEST_FILE_RE.search(path))


def _touches_only_tests(files: list) -> bool:
    """True iff the diff is non-empty and EVERY changed file is a test file.

    An empty/undeterminable file set returns False — we do NOT suppress
    graduation credit on missing evidence, only on a proven test-only diff."""
    paths = [f for f in (files or []) if f]
    return bool(paths) and all(_is_test_file(p) for p in paths)


# --- injectable client (real impl shells out; NEVER invoked in tests) --------

class GhCiClient:
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

    def runs(self, repo: str, workflow: str, limit: int = 50) -> list[dict]:
        """Latest runs of <product-ci>: [{databaseId, status, conclusion,
        headSha}]. The caller joins headSha → the commit trailer for the cid."""
        return self._gh_json(
            ["run", "list", "--repo", repo, "--workflow", workflow,
             "--limit", str(limit),
             "--json", "databaseId,status,conclusion,headSha"]) or []

    def commit_message(self, sha: str) -> str:
        """The full commit message for a head SHA (carries the B2.1 trailer)."""
        cp = subprocess.run(["git", "log", "-1", "--format=%B", sha, "--"],
                           capture_output=True, text=True, timeout=self.timeout)
        return cp.stdout if cp.returncode == 0 else ""

    def changed_files(self, repo: str, sha: str) -> list[str]:
        """File paths the PR(s) at this head SHA touch — for the B2.10 test-only
        check. Two arg-list hops: find the PR number by SHA, then list its
        files. Deploy-side; never run here."""
        prs = self._gh_json(["pr", "list", "--repo", repo, "--search", sha,
                             "--state", "all", "--json", "number"]) or []
        files: list[str] = []
        for pr in prs:
            view = self._gh_json(["pr", "view", str(pr.get("number")),
                                 "--repo", repo, "--json", "files"]) or {}
            files += [f.get("path") for f in (view.get("files") or [])
                      if f.get("path")]
        return files

    def local_commits_since(self, window: str = "1 hour ago") -> list:
        cp = subprocess.run(["git", "log", f"--since={window}", "--pretty=%H"],
                           capture_output=True, text=True, timeout=self.timeout)
        return [l for l in cp.stdout.splitlines() if l.strip()] if cp.returncode == 0 else []


# --- orchestration -----------------------------------------------------------

def run_probe(
    *,
    repo: str,
    workflow: str,
    client: Any,
    rows: list | None = None,
    emit: Callable[..., Any] = lib.emit_outcome,
    hc: Callable[..., Any] = lib.hc_ping,
) -> dict:
    """One probe cycle. Returns {fresh, emitted:[...], skipped:[...]}."""
    runs = client.runs(repo, workflow)
    activity = bool(client.local_commits_since())
    fresh = lib.freshness_guard(observed=runs, activity_expected=activity, source="ci")
    if not fresh["fresh"]:
        hc(SLUG, fail=True)   # runs empty while pushes landed — page, don't lie
        return {"fresh": False, "reason": fresh["reason"], "emitted": [], "skipped": []}

    emitted, skipped = [], []
    for run in runs:
        sha = run.get("headSha")
        cid = correlation.from_git_trailer(client.commit_message(sha) if sha else "")
        if not cid:
            skipped.append({"databaseId": run.get("databaseId"), "reason": "no-cid"})
            continue
        status, probe_status, evidence = classify(run)
        ev = evidence if status != "unknown" else None   # unknown carries no evidence
        # B2.10: a proven test-only diff never advances graduation.
        test_only = _touches_only_tests(client.changed_files(repo, sha) if sha else [])
        extra_refs = [GRAD_CREDIT_FALSE_REF] if test_only else None
        res = emit(cid=cid, status=status, probe_status=probe_status, source="ci",
                   confidence="high", evidence=ev, extra_refs=extra_refs, rows=rows)
        entry = {"databaseId": run.get("databaseId"), "cid": cid, "status": status,
                 "probe_status": probe_status, "graduation_credit": not test_only}
        if res.get("emitted"):
            emitted.append(entry)
        else:
            entry["reason"] = res.get("reason")
            skipped.append(entry)
    hc(SLUG)   # liveness
    return {"fresh": True, "emitted": emitted, "skipped": skipped}
