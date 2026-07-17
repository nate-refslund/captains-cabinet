"""Conformance fixtures for the shipped adapters (see conformance.py).

Every fixture fakes its transport IN-PROCESS: no network, no real `gh`, no
disk. ADAPTER_REGISTRY rows point here via their `conformance_fixture`
import path; tests/test_conformance.py resolves and runs them.

Writing one for a new adapter: subclass ConformanceFixture, fake the
adapter's transport at its narrowest seam (the reference adapter injects a
tracker double; the gh fixture patches the module's subprocess.run with an
argv-level emulator), and implement read_external / tamper_external /
arm_rate_limit against that fake. Runbook:
cabinet/runbooks/task-adapter-authoring.md §"Build the adapter".
"""

from __future__ import annotations

import subprocess
from typing import Any
from unittest import mock

from cabinet.scripts.task_adapters.conformance import ConformanceFixture
from cabinet.scripts.task_adapters.base import TaskAdapter


# ---------------------------------------------------------------------------
# Reference in-memory adapter — the positive control
# ---------------------------------------------------------------------------


class ReferenceConformanceFixture(ConformanceFixture):
    adapter_label = "reference-inmemory"
    secret_env = "REFERENCE_TASKS_TOKEN"
    requires_env_token = True
    detects_conflicts = True

    def make_adapter(self) -> TaskAdapter:
        from cabinet.scripts.task_adapters.reference_inmemory import InMemoryReferenceAdapter
        return InMemoryReferenceAdapter({"system": "reference-inmemory", "config": {}})

    def read_external(self, adapter: TaskAdapter, external_id: str) -> dict[str, Any]:
        item = adapter.tracker.items[external_id]
        return {k: item.get(k) for k in ("title", "description", "status", "priority")}

    def tamper_external(self, adapter: TaskAdapter, external_id: str) -> None:
        item = adapter.tracker.items[external_id]
        item["title"] = "operator-renamed out-of-band"
        item["status"] = "done"

    def arm_rate_limit(self, adapter: TaskAdapter, n: int) -> None:
        adapter.tracker.arm_rate_limit(n)

    def conflict_count(self, adapter: TaskAdapter) -> int:
        return adapter.conflicts_observed


# ---------------------------------------------------------------------------
# Template adapter — the negative control (must FAIL every check)
# ---------------------------------------------------------------------------


class TemplateConformanceFixture(ConformanceFixture):
    adapter_label = "_template (negative control)"
    secret_env = "TEMPLATE_API_TOKEN"
    requires_env_token = True
    detects_conflicts = False
    # no conflict_detection_note ON PURPOSE: an undeclared gap is itself a
    # conformance failure the negative control exercises

    def make_adapter(self) -> TaskAdapter:
        from cabinet.scripts.task_adapters._template import TemplateAdapter
        return TemplateAdapter({"system": "template", "config": {}})

    def read_external(self, adapter: TaskAdapter, external_id: str) -> dict[str, Any]:
        raise NotImplementedError("template fixture: no external system exists")

    def tamper_external(self, adapter: TaskAdapter, external_id: str) -> None:
        raise NotImplementedError("template fixture: no external system exists")

    def arm_rate_limit(self, adapter: TaskAdapter, n: int) -> None:
        raise NotImplementedError("template fixture: no external system exists")


# ---------------------------------------------------------------------------
# GitHub Issues adapter — subprocess-patched gh emulator
# ---------------------------------------------------------------------------


class _FakeGhStore:
    """In-process double of one repo's issues, at gh-argv level."""

    def __init__(self) -> None:
        self.issues: dict[str, dict[str, Any]] = {}
        self._next = 1
        self._rate_limit_budget = 0

    def arm(self, n: int) -> None:
        self._rate_limit_budget = int(n)

    def gate_write(self) -> bool:
        """True → this write call is rate-limited."""
        if self._rate_limit_budget > 0:
            self._rate_limit_budget -= 1
            return True
        return False

    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str:
        number = str(self._next)
        self._next += 1
        self.issues[number] = {
            "number": int(number),
            "title": title,
            "body": body,
            "state": "OPEN",
            "labels": list(labels),
            "url": f"https://github.invalid/{repo}/issues/{number}",
            "createdAt": "2026-07-17T00:00:00Z",
            "updatedAt": "2026-07-17T00:00:00Z",
            "closedAt": None,
        }
        return number


def _flags(argv: list[str]) -> dict[str, list[str]]:
    """Collect --flag value pairs (repeats accumulate)."""
    out: dict[str, list[str]] = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--"):
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                out.setdefault(argv[i], []).append(argv[i + 1])
                i += 2
                continue
            out.setdefault(argv[i], []).append("")
        i += 1
    return out


def _completed(argv: list[str], rc: int = 0, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(argv, rc, stdout, stderr)


class GitHubIssuesConformanceFixture(ConformanceFixture):
    adapter_label = "github-issues"
    #: planted purely as LEAK BAIT — the adapter authenticates via gh's own
    #: keychain, never this env var (hence requires_env_token=False)
    secret_env = "GH_TOKEN"
    requires_env_token = False
    detects_conflicts = False
    conflict_detection_note = (
        "gh CLI transport is stateless (no last-write snapshot between sync "
        "cycles) — out-of-band edits are indistinguishable from canonical "
        "updates; canonical-wins is enforced by unconditional overwrite"
    )

    def __init__(self) -> None:
        super().__init__()
        self._stores: dict[int, _FakeGhStore] = {}
        self._current: _FakeGhStore | None = None
        self._patcher: Any = None

    # -- transport patch lifecycle --

    def setup(self) -> None:
        self._patcher = mock.patch(
            "cabinet.scripts.task_adapters.github_issues.subprocess.run",
            side_effect=self._fake_run,
        )
        self._patcher.start()

    def teardown(self) -> None:
        if self._patcher is not None:
            self._patcher.stop()
            self._patcher = None

    # -- fixture surface --

    def make_adapter(self) -> TaskAdapter:
        from cabinet.scripts.task_adapters.github_issues import GitHubIssuesAdapter
        adapter = GitHubIssuesAdapter(
            {"system": "github-issues", "config": {"repo": "example-org/example-repo"}}
        )
        self._stores[id(adapter)] = _FakeGhStore()
        self._current = self._stores[id(adapter)]
        return adapter

    def _store(self, adapter: TaskAdapter) -> _FakeGhStore:
        return self._stores[id(adapter)]

    def read_external(self, adapter: TaskAdapter, external_id: str) -> dict[str, Any]:
        issue = self._store(adapter).issues[external_id]
        return {
            "title": issue["title"],
            "description": issue["body"],
            "status": adapter._gh_state_to_status(issue["state"], issue["labels"]),
        }

    def tamper_external(self, adapter: TaskAdapter, external_id: str) -> None:
        issue = self._store(adapter).issues[external_id]
        issue["title"] = "operator-renamed out-of-band"
        issue["state"] = "CLOSED"

    def arm_rate_limit(self, adapter: TaskAdapter, n: int) -> None:
        self._store(adapter).arm(n)

    # -- the emulator --

    def _fake_run(self, argv, **kwargs):
        # Transport-contract teeth: a shell or a string command is an
        # immediate failure of whatever check triggered it.
        if kwargs.get("shell"):
            raise AssertionError("adapter invoked subprocess with shell=True")
        if not isinstance(argv, list) or not argv or argv[0] != "gh":
            raise AssertionError(f"unexpected exec through the gh seam: {argv!r}")
        store = self._current
        if store is None:
            raise AssertionError("fake gh used before make_adapter()")
        flags = _flags(argv)
        verb = argv[1] if len(argv) > 1 else ""

        if verb == "auth":  # gh auth status
            return _completed(argv)
        if verb == "repo":  # repo view <repo> --json name
            return _completed(argv, stdout='{"name": "example-repo"}')
        if verb != "issue":
            raise AssertionError(f"fake gh: unhandled command {argv!r}")

        action = argv[2]
        if action == "list":
            wanted_label = (flags.get("--label") or [None])[0]
            fields = (flags.get("--json") or ["number"])[0].split(",")
            limit = int((flags.get("--limit") or ["100"])[0])
            rows = []
            for number in sorted(store.issues, key=int):
                issue = store.issues[number]
                if wanted_label is not None and wanted_label not in issue["labels"]:
                    continue
                row: dict[str, Any] = {}
                for f in fields:
                    if f == "labels":
                        row["labels"] = [{"name": l} for l in issue["labels"]]
                    else:
                        row[f] = issue.get(f)
                rows.append(row)
                if len(rows) >= limit:
                    break
            import json as _json
            return _completed(argv, stdout=_json.dumps(rows))

        # -- writes below: rate-limit gate first --
        if store.gate_write():
            return _completed(argv, rc=1, stderr="HTTP 403: API rate limit exceeded")

        if action == "create":
            repo = (flags.get("--repo") or ["?"])[0]
            number = store.create(
                repo,
                (flags.get("--title") or [""])[0],
                (flags.get("--body") or [""])[0],
                flags.get("--label") or [],
            )
            return _completed(argv, stdout=store.issues[number]["url"] + "\n")

        number = argv[3]
        if number not in store.issues:
            return _completed(argv, rc=1, stderr=f"no issue {number}")
        issue = store.issues[number]

        if action == "edit":
            if "--title" in flags:
                issue["title"] = flags["--title"][0]
            if "--body" in flags:
                issue["body"] = flags["--body"][0]
            for label in flags.get("--add-label", []):
                if label not in issue["labels"]:
                    issue["labels"].append(label)
            for label in flags.get("--remove-label", []):
                if label in issue["labels"]:
                    issue["labels"].remove(label)
            return _completed(argv)
        if action == "close":
            issue["state"] = "CLOSED"
            issue["closedAt"] = "2026-07-17T00:00:01Z"
            return _completed(argv)
        if action == "reopen":
            if issue["state"] == "OPEN":
                return _completed(argv, rc=1, stderr="issue is already open")
            issue["state"] = "OPEN"
            issue["closedAt"] = None
            return _completed(argv)
        raise AssertionError(f"fake gh: unhandled issue action {argv!r}")
