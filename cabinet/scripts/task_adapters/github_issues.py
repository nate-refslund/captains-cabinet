"""GitHub Issues adapter — fully implemented via `gh` CLI.

Phase 5.2 of the convergence plan. This is the only adapter shipped with a
real, working implementation; the other four (Monday, Jira, Linear, Asana)
are skeletons until Captain provides credentials for those systems.

GitHub Issues was chosen for the first working implementation because:
  - `gh` CLI is already installed on Captain's Mac (verified by setup-mac.sh)
  - Authentication via `gh auth login` — no environment-variable token needed
  - The Cabinet's own framework backlog already lives in GitHub Issues
    (per CLAUDE.md), so this adapter has immediate first-party utility.

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

from cabinet.scripts.task_adapters.base import CanonicalTask, TaskAdapter


class GitHubIssuesAdapter(TaskAdapter):
    destination = "github-issues"
    auth_env_var = ""  # uses `gh auth status` instead

    def __init__(self, project_config: dict[str, Any]) -> None:
        super().__init__(project_config)
        self.repo = self.adapter_config.get("repo")
        if not self.repo:
            raise ValueError(
                "github-issues adapter requires tasks.config.repo "
                "(e.g. 'nate-refslund/captains-cabinet')"
            )

    # ----- lifecycle -----

    def health_check(self) -> bool:
        """Verify gh is authenticated and can hit the repo."""
        try:
            subprocess.run(
                ["gh", "auth", "status"],
                check=True,
                capture_output=True,
                timeout=5,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return False

        try:
            subprocess.run(
                ["gh", "repo", "view", self.repo, "--json", "name"],
                check=True,
                capture_output=True,
                timeout=10,
            )
        except subprocess.CalledProcessError:
            return False

        return True

    # ----- read -----

    def pull(self) -> list[CanonicalTask]:
        """List open + recently-closed issues in the configured repo."""
        result = subprocess.run(
            [
                "gh", "issue", "list",
                "--repo", self.repo,
                "--state", "all",
                "--limit", str(self.adapter_config.get("pull_limit", 100)),
                "--json", "number,title,body,state,labels,url,createdAt,updatedAt,closedAt",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
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
                tags=[l for l in label_names if not l.startswith(("cabinet:", "officer:", "priority:", "wip", "blocked"))],
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
        existing_number = self._find_by_canonical_id(task.canonical_id)
        labels = self._task_labels(task)

        if existing_number:
            # Update title + body + labels + state in one go via gh issue edit
            self._update_issue(existing_number, task, labels)
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
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
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
        subprocess.run(
            ["gh", "issue", "close", external_id, "--repo", self.repo,
             "--reason", "not planned"],
            check=True, capture_output=True, timeout=15,
        )

    def link(self, canonical_id: str, external_id: str) -> None:
        """Add the cabinet:<canonical_id> label to the existing issue."""
        subprocess.run(
            ["gh", "issue", "edit", external_id,
             "--repo", self.repo,
             "--add-label", f"cabinet:{canonical_id}"],
            check=True, capture_output=True, timeout=15,
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

    def _find_by_canonical_id(self, canonical_id: str) -> str | None:
        """Look up an issue by its cabinet:<id> label."""
        result = subprocess.run(
            ["gh", "issue", "list",
             "--repo", self.repo,
             "--label", f"cabinet:{canonical_id}",
             "--state", "all",
             "--limit", "1",
             "--json", "number"],
            check=True, capture_output=True, text=True, timeout=15,
        )
        items = json.loads(result.stdout or "[]")
        return str(items[0]["number"]) if items else None

    def _update_issue(self, number: str, task: CanonicalTask, labels: list[str]) -> None:
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
        # Strip transient state labels not in the new set
        for transient in ("wip", "blocked"):
            if transient not in labels:
                cmd += ["--remove-label", transient]
        subprocess.run(cmd, check=True, capture_output=True, timeout=15)

        # State transitions
        if task.status in ("done", "cancelled"):
            self._close_issue(number, task.status)
        elif task.status in ("open", "in_progress", "blocked"):
            # Reopen if needed
            subprocess.run(
                ["gh", "issue", "reopen", number, "--repo", self.repo],
                capture_output=True, timeout=15,
            )

    def _close_issue(self, number: str, status: str) -> None:
        reason = "completed" if status == "done" else "not planned"
        subprocess.run(
            ["gh", "issue", "close", number, "--repo", self.repo, "--reason", reason],
            check=True, capture_output=True, timeout=15,
        )
