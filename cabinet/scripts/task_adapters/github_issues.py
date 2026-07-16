"""GitHub Issues adapter — fully implemented via `gh` CLI.

Phase 5.2 of the convergence plan. This is the only adapter shipped with a
real, working implementation; the others (Jira, Linear, Asana) are skeletons
until Captain provides credentials for those systems (Monday is
plugin-routed — see base.get_adapter).

GitHub Issues was chosen for the first working implementation because:
  - `gh` CLI is already installed on Captain's Mac (verified by setup-mac.sh)
  - Authentication via `gh auth login` — no environment-variable token needed
  - The Cabinet's own framework backlog already lives in GitHub Issues
    (per CLAUDE.md), so this adapter has immediate first-party utility.

Transport discipline (authoring-kit conformance, 2026-07-17): every gh call
goes through `_gh()` — subprocess ARGV LISTS only (task text rides as single
argv elements; `shell=True` is forbidden by the conformance source scan),
rate-limit replies classify into RateLimitedError and writes retry through
`TaskAdapter._with_backoff`. Conflict DETECTION is not implemented: the gh
CLI transport is stateless (no last-write snapshot survives between sync
cycles), so out-of-band operator edits cannot be told apart from canonical
updates — canonical still WINS (push overwrites title/body/labels/state
unconditionally); the gap is declared in this adapter's conformance fixture,
not hidden.

Label fidelity (2026-07-17 review): updates strip STALE MANAGED labels
(`officer:*`, `priority:*`, and exact `wip`/`blocked`) that the new push no
longer carries — else a priority downgrade or role reassignment leaves the
old label behind and the next pull() resurrects the stale value (canonical
must win on labels too; conformance C2 pins it). User tags pass through
untouched, and the wip/blocked reservation is EXACT-match only: a user tag
like `wip-cleanup` is ordinary data that must round-trip.

Mapping:
  CanonicalTask                     GitHub Issue
  -----------------------------     -----------------------------
  canonical_id                      label "cabinet:<canonical_id>"
  title                             issue title
  description                       issue body
  status open                       issue state open
  status in_progress                issue state open, label "wip"
  status blocked                    issue state open, label "blocked"
  status done                       issue state closed (reason: completed)
  status cancelled                  issue state closed (reason: not planned)
  assigned_role                     label "officer:<slug>"
  priority                          label "priority:<level>"
  tags                              labels (passthrough)
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from cabinet.scripts.task_adapters.base import CanonicalTask, RateLimitedError, TaskAdapter

#: gh stderr fragments that mean "slow down" (secondary rate limits included)
_RATE_LIMIT_MARKERS = (
    "API rate limit exceeded",
    "HTTP 429",
    "was submitted too quickly",
    "secondary rate limit",
)


class GitHubIssuesAdapter(TaskAdapter):
    destination = "github-issues"
    auth_env_var = ""  # uses `gh auth status` instead

    def __init__(self, project_config: dict[str, Any]) -> None:
        super().__init__(project_config)
        self.repo = self.adapter_config.get("repo")
        if not self.repo:
            raise ValueError(
                "github-issues adapter requires tasks.config.repo "
                "(e.g. 'example-org/example-repo')"
            )

    # ----- transport -----

    def _gh(self, argv: list[str], *, timeout: int,
            check: bool = True) -> subprocess.CompletedProcess:
        """ONE door to the gh CLI. Argv list only — never a shell; untrusted
        issue text is always a single argv element. Rate-limit stderr raises
        RateLimitedError (callers wrap in _with_backoff); other failures
        keep the historical check=True CalledProcessError semantics."""
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            stderr = result.stderr or ""
            if any(marker in stderr for marker in _RATE_LIMIT_MARKERS):
                op = " ".join(argv[1:3]) if len(argv) > 2 else "gh"
                # message carries the OPERATION only — never issue text/tokens
                raise RateLimitedError(f"gh rate-limited during {op}")
            if check:
                raise subprocess.CalledProcessError(
                    result.returncode, argv, result.stdout, result.stderr
                )
        return result

    # ----- lifecycle -----

    def health_check(self) -> bool:
        """Verify gh is authenticated and can hit the repo."""
        try:
            self._gh(["gh", "auth", "status"], timeout=5)
        except (subprocess.CalledProcessError, FileNotFoundError,
                subprocess.TimeoutExpired, RateLimitedError):
            return False

        try:
            self._gh(["gh", "repo", "view", self.repo, "--json", "name"], timeout=10)
        except (subprocess.CalledProcessError, RateLimitedError):
            return False

        return True

    # ----- read -----

    def pull(self) -> list[CanonicalTask]:
        """List open + recently-closed issues in the configured repo."""
        result = self._with_backoff(
            lambda: self._gh(
                [
                    "gh", "issue", "list",
                    "--repo", self.repo,
                    "--state", "all",
                    "--limit", str(self.adapter_config.get("pull_limit", 100)),
                    "--json", "number,title,body,state,labels,url,createdAt,updatedAt,closedAt",
                ],
                timeout=30,
            ),
            op="issue-list",
        )
        issues = json.loads(result.stdout or "[]")

        tasks: list[CanonicalTask] = []
        for issue in issues:
            label_names = [l["name"] for l in (issue.get("labels") or [])]
            canonical_id = self._extract_canonical_id(label_names) or f"gh-{self.repo}-{issue['number']}"

            tasks.append(CanonicalTask(
                canonical_id=canonical_id,
                title=issue["title"],
                description=issue.get("body") or "",
                status=self._gh_state_to_status(issue["state"], label_names),
                assigned_role=self._extract_role(label_names),
                priority=self._extract_priority(label_names),
                # wip/blocked are EXACT-match status markers — a user tag
                # merely prefixed with them ('wip-cleanup') must round-trip
                tags=[l for l in label_names
                      if not l.startswith(("cabinet:", "officer:", "priority:"))
                      and l not in ("wip", "blocked")],
                external_id=str(issue["number"]),
                external_url=issue["url"],
                metadata={
                    "github_state": issue["state"],
                    "created_at": issue.get("createdAt"),
                    "updated_at": issue.get("updatedAt"),
                    "closed_at": issue.get("closedAt"),
                },
            ))
        return tasks

    # ----- write -----

    def push(self, task: CanonicalTask) -> str:
        """Upsert: if canonical_id label exists on an issue, edit; else create."""
        existing = self._find_by_canonical_id(task.canonical_id)
        labels = self._task_labels(task)

        if existing:
            # Update title + body + labels + state in one go via gh issue edit
            existing_number, current_labels = existing
            self._update_issue(existing_number, task, labels, current_labels)
            return existing_number

        # Create
        cmd = [
            "gh", "issue", "create",
            "--repo", self.repo,
            "--title", task.title,
            "--body", task.description or "(empty body)",
        ]
        for label in labels:
            cmd += ["--label", label]
        result = self._with_backoff(
            lambda: self._gh(cmd, timeout=30), op="issue-create")
        # gh prints the URL on stdout; parse the issue number
        # https://github.com/owner/repo/issues/N
        url = result.stdout.strip()
        number = url.rsplit("/", 1)[-1]

        # If the new task isn't 'open', transition state immediately
        if task.status in ("done", "cancelled"):
            self._close_issue(number, task.status)
        return number

    def delete(self, external_id: str) -> None:
        """Close the issue (gh has no hard-delete for non-admins)."""
        self._with_backoff(
            lambda: self._gh(
                ["gh", "issue", "close", external_id, "--repo", self.repo,
                 "--reason", "not planned"],
                timeout=15,
            ),
            op="issue-close",
        )

    def link(self, canonical_id: str, external_id: str) -> None:
        """Add the cabinet:<canonical_id> label to the existing issue."""
        self._with_backoff(
            lambda: self._gh(
                ["gh", "issue", "edit", external_id,
                 "--repo", self.repo,
                 "--add-label", f"cabinet:{canonical_id}"],
                timeout=15,
            ),
            op="issue-link",
        )

    # ----- internals -----

    def _gh_state_to_status(self, state: str, labels: list[str]) -> str:
        """Map GitHub state + labels to canonical status."""
        if state == "OPEN":
            if "wip" in labels:
                return "in_progress"
            if "blocked" in labels:
                return "blocked"
            return "open"
        # closed
        return "done"  # we can't distinguish completed-vs-not-planned without state_reason

    def _extract_canonical_id(self, labels: list[str]) -> str | None:
        for label in labels:
            if label.startswith("cabinet:"):
                return label[len("cabinet:"):]
        return None

    def _extract_role(self, labels: list[str]) -> str | None:
        for label in labels:
            if label.startswith("officer:"):
                return label[len("officer:"):]
        return None

    def _extract_priority(self, labels: list[str]) -> str:
        for label in labels:
            if label.startswith("priority:"):
                return label[len("priority:"):]
        return "normal"

    def _task_labels(self, task: CanonicalTask) -> list[str]:
        """Build the full label set the issue should carry for a canonical task."""
        labels = [f"cabinet:{task.canonical_id}"]
        if task.assigned_role:
            labels.append(f"officer:{task.assigned_role}")
        if task.priority and task.priority != "normal":
            labels.append(f"priority:{task.priority}")
        if task.status == "in_progress":
            labels.append("wip")
        if task.status == "blocked":
            labels.append("blocked")
        for tag in task.tags:
            if not tag.startswith(("cabinet:", "officer:", "priority:")):
                labels.append(tag)
        return labels

    def _find_by_canonical_id(self, canonical_id: str) -> tuple[str, list[str]] | None:
        """Look up an issue by its cabinet:<id> label → (number, label names).

        Labels ride in the SAME lookup so the updating push can strip stale
        managed labels without a second read."""
        result = self._with_backoff(
            lambda: self._gh(
                ["gh", "issue", "list",
                 "--repo", self.repo,
                 "--label", f"cabinet:{canonical_id}",
                 "--state", "all",
                 "--limit", "1",
                 "--json", "number,labels"],
                timeout=15,
            ),
            op="issue-lookup",
        )
        items = json.loads(result.stdout or "[]")
        if not items:
            return None
        label_names = [l["name"] for l in (items[0].get("labels") or [])]
        return str(items[0]["number"]), label_names

    def _update_issue(self, number: str, task: CanonicalTask, labels: list[str],
                      current_labels: list[str]) -> None:
        """Edit title/body/labels and adjust state."""
        # Title + body + labels
        cmd = [
            "gh", "issue", "edit", number,
            "--repo", self.repo,
            "--title", task.title,
            "--body", task.description or "(empty body)",
        ]
        for label in labels:
            cmd += ["--add-label", label]
        # Canonical wins on labels too: strip stale MANAGED labels (status
        # markers, officer:*, priority:*) the new push no longer carries —
        # else a priority downgrade / role reassignment leaves the old label
        # and the next pull() resurrects it (conformance C2 pins this).
        # cabinet:<id> is the upsert key (never stale by construction); user
        # tags are passthrough and never stripped; wip/blocked match EXACTLY
        # so a user tag like 'wip-cleanup' survives.
        stale = [
            l for l in current_labels
            if (l.startswith(("officer:", "priority:")) or l in ("wip", "blocked"))
            and l not in labels
        ]
        for label in stale:
            cmd += ["--remove-label", label]
        self._with_backoff(lambda: self._gh(cmd, timeout=15), op="issue-edit")

        # State transitions
        if task.status in ("done", "cancelled"):
            self._close_issue(number, task.status)
        elif task.status in ("open", "in_progress", "blocked"):
            # Reopen if needed (check=False: reopening an already-open issue
            # errors and that is fine — rate limits still back off)
            self._with_backoff(
                lambda: self._gh(
                    ["gh", "issue", "reopen", number, "--repo", self.repo],
                    timeout=15, check=False,
                ),
                op="issue-reopen",
            )

    def _close_issue(self, number: str, status: str) -> None:
        reason = "completed" if status == "done" else "not planned"
        self._with_backoff(
            lambda: self._gh(
                ["gh", "issue", "close", number, "--repo", self.repo, "--reason", reason],
                timeout=15,
            ),
            op="issue-close",
        )
