"""Task adapter base — abstract interface for external task-system sync.

Phase 5 of the convergence plan. The Cabinet's canonical task model is
`officer_tasks` / `mission_steps` in the event ledger + (optionally) Postgres.
Captain configures one external system per project (Monday, Jira, Linear,
Asana, GitHub Issues). The adapter for that system bridges Cabinet ↔ external
in both directions.

Conflict resolution: **canonical wins**. If an officer changes a task and an
operator changes the same task in the external UI, the next sync overwrites
the external change and logs a warning. This is intentional — the org runtime
should be authoritative.

Contract:

  class MyAdapter(TaskAdapter):
      destination = "my-system"

      def pull(self) -> list[CanonicalTask]: ...
      def push(self, task: CanonicalTask) -> str: ...  # returns external_id
      def delete(self, external_id: str) -> None: ...
      def link(self, canonical_id: str, external_id: str) -> None: ...
      def health_check(self) -> bool: ...

Adapters MUST be idempotent: pushing the same task twice should be a no-op
(use upsert semantics keyed by `canonical_id` stored in the external system).
"""

from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)


@dataclass
class CanonicalTask:
    """The Cabinet's universal task representation.

    Each external system's adapter maps to/from this shape. Fields aim for
    the lowest-common-denominator across Monday, Jira, Linear, Asana, and
    GitHub Issues.
    """
    canonical_id: str              # Cabinet's task_id (e.g. "outcome-x-task-001")
    title: str                     # short title for external display
    description: str = ""          # full body, markdown
    status: str = "open"           # open | in_progress | blocked | done | cancelled
    assigned_role: str | None = None
    priority: str = "normal"       # low | normal | high | urgent
    due_at: str | None = None      # ISO 8601 or None
    tags: list[str] = field(default_factory=list)
    external_id: str | None = None  # set after first push
    external_url: str | None = None  # link back to the external system
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncResult:
    """Outcome of a sync cycle for a single adapter."""
    destination: str
    pulled: int = 0
    pushed: int = 0
    conflicts: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""


class TaskAdapter(ABC):
    """Abstract adapter — concrete impls per task system live in sibling modules."""

    #: kebab-case slug uniquely identifying this adapter (e.g. "github-issues")
    destination: ClassVar[str] = ""

    #: env var the adapter expects for auth (e.g. "MONDAY_API_TOKEN")
    auth_env_var: ClassVar[str] = ""

    def __init__(self, project_config: dict[str, Any]) -> None:
        """`project_config` is the `tasks:` block from instance/config/projects/<slug>.yml."""
        self.project_config = project_config
        self.adapter_config: dict[str, Any] = project_config.get("config") or {}

    # ----- lifecycle -----

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the adapter can reach the external system + has auth."""

    # ----- read -----

    @abstractmethod
    def pull(self) -> list[CanonicalTask]:
        """Read all tasks from the external system into CanonicalTask shape."""

    # ----- write -----

    @abstractmethod
    def push(self, task: CanonicalTask) -> str:
        """Upsert the task to the external system. Returns external_id.

        MUST be idempotent — pushing the same canonical_id twice should not
        create a duplicate external item. Use the external system's idempotency
        keys (Monday item identifier, Jira issue key, Linear issue id, etc.)
        keyed on canonical_id stored as a tag/custom-field/label.
        """

    @abstractmethod
    def delete(self, external_id: str) -> None:
        """Remove the external item. May be a soft-delete depending on system."""

    @abstractmethod
    def link(self, canonical_id: str, external_id: str) -> None:
        """Persist the canonical_id ↔ external_id mapping in the external system.

        Most systems support this via a tag/label/custom-field. Cabinet stores
        the inverse mapping in the `task_sync` table.
        """

    # ----- helpers (default impls) -----

    def auth_token(self) -> str | None:
        """Read auth from env (or pass-through from project_config)."""
        token_env = self.project_config.get("auth_env") or self.auth_env_var
        return os.environ.get(token_env) if token_env else None

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


def get_adapter(project_config: dict[str, Any]) -> TaskAdapter:
    """Instantiate the right adapter based on project_config['tasks']['system'].

    Args:
        project_config: full project YAML dict (must contain `tasks: {system: ...}`)

    Raises:
        ValueError: if the system slug is unknown.
    """
    tasks_block = project_config.get("tasks") or {}
    system = tasks_block.get("system")
    if not system:
        raise ValueError(
            "Project config missing tasks.system. "
            "Must be one of: github-issues, monday, jira, linear, asana"
        )

    # Local imports to avoid mandatory deps for unused adapters
    if system == "github-issues":
        from cabinet.scripts.task_adapters.github_issues import GitHubIssuesAdapter
        return GitHubIssuesAdapter(tasks_block)
    if system == "monday":
        # The cabinet's own Monday adapter was removed in favor of the
        # STEP-Network/dev-tasks Claude plugin (44 Monday MCP tools + 15
        # workflow skills). Officers reach Monday via the plugin's
        # mcp__dev-tasks tools, NOT through this adapter interface.
        #
        # Configure dev-tasks via instance/config/extensions.yml +
        # .claude/project-config.json. For non-STEP Monday integrations,
        # restore the old adapter: `git show <pre-plugin-commit>:cabinet/scripts/task_adapters/monday.py`
        raise ValueError(
            "Monday adapter removed — use STEP-Network/dev-tasks plugin. "
            "Set tasks.system to 'github-issues' (cabinet default) or "
            "'linear', and declare dev-tasks in instance/config/extensions.yml "
            "+ .claude/project-config.json."
        )
    if system == "jira":
        from cabinet.scripts.task_adapters.jira import JiraAdapter
        return JiraAdapter(tasks_block)
    if system == "linear":
        from cabinet.scripts.task_adapters.linear import LinearAdapter
        return LinearAdapter(tasks_block)
    if system == "asana":
        from cabinet.scripts.task_adapters.asana import AsanaAdapter
        return AsanaAdapter(tasks_block)

    raise ValueError(
        f"Unknown task system: {system!r}. "
        "Supported: github-issues, monday, jira, linear, asana"
    )
