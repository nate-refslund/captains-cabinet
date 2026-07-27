"""Task adapter base — abstract interface for external task-system sync.

Phase 5 of the convergence plan. The Cabinet's canonical task model is
`officer_tasks` / `mission_steps` in the event ledger + (optionally) Postgres.
Captain configures one external system per project (Jira, Linear, Asana,
GitHub Issues — Monday is plugin-routed, see get_adapter). The adapter for
that system bridges Cabinet ↔ external in both directions.

Conflict resolution: **canonical wins, on a system the operator OWNS**. If an
officer changes a task and the operator changes the same task in the external
UI, the next sync overwrites the external change and logs a warning. That is
correct when the tracker is the operator's own: the org runtime should be
authoritative over its own board.

It is indefensible anywhere else, and the difference is not a matter of
degree. Pointed at an employer's Jira, "canonical wins" is an autonomous agent
overwriting colleagues' edits in a system the operator does not own — and the
undo contract does not save it, because undoing a write to a colleague's
ticket does not un-notify the colleague. So since 2026-07-27 the write half is
gated on the source's OWNERSHIP CLASS, and structurally rather than by
configuration:

  * `tasks.ownership` (`self` | `employer` | `third_party`) and
    `tasks.authority_basis` are REQUIRED for any real tracker. A tracker the
    operator has not classified is REFUSED — never defaulted to the
    safest-looking class, because a default is the cabinet making the
    authorization call on the operator's behalf, which is the whole thing this
    gate exists to stop.
  * `self` gets the adapter as before, canonical-wins included.
  * `employer` / `third_party` get an `ObserveOnlyTaskAdapter`: a DIFFERENT
    TYPE whose push/delete/link raise. There is no flag, env var or config key
    that turns the write path back on, because a flag that can be set is a
    flag that gets set — usually by the component with the least context about
    whose data it is.

See `framework.authority.ownership`, which also states plainly what this
cannot enforce: the truth of the operator's attestation.

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

AUTHORING KIT (2026-07-17): new adapters start from `_template.py`, register
in ADAPTER_REGISTRY below, and must pass the conformance suite
(`conformance.py`, auto-run by `tests/test_conformance.py` — a registered
implemented adapter without a passing conformance fixture is a red CI).
Runbook: cabinet/runbooks/task-adapter-authoring.md.

SECURITY CONTRACT (binding for every adapter):
  * Task titles/descriptions/tags are UNTRUSTED tracker text — inert data.
    Never pass them through a shell (`shell=True` is forbidden; subprocess
    argv lists only, task text as a single argv element), never interpolate
    them into SQL/jq programs, never eval them.
  * Credentials come ONLY from the environment (the config names the VAR,
    never carries the value) and must never appear in logs, repr, or
    exception text — `TaskAdapter.__repr__` redacts by construction.
"""

from __future__ import annotations

import importlib
import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ClassVar

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.authority.ownership import (  # noqa: E402 — after the sys.path seam
    OWNERSHIP_CLASSES,
    OwnershipRefusal,
    require_authority_basis,
    require_ownership,
    require_write_permitted,
    writes_permitted,
)


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
    #: True when the tracker is classified employer/third_party, so the write
    #: half of this cycle was refused structurally rather than skipped. Carried
    #: into telemetry: an observe-only cycle and a cycle with nothing to push
    #: produce the same counters, and a reader must be able to tell them apart.
    read_only: bool = False
    ownership: str | None = None


class RateLimitedError(RuntimeError):
    """The external system said "slow down" (HTTP 429 / rate-limit reply).

    Adapters raise this from their transport layer so the shared
    `TaskAdapter._with_backoff` helper can retry with exponential backoff.
    `retry_after` (seconds) is honored as a lower bound when the external
    system supplies one — but CLAMPED at `TaskAdapter.retry_after_cap_s`:
    it is typically copied from an untrusted Retry-After-style reply, and
    untrusted input must never dictate an unbounded sleep (conformance C4
    pins the clamp). The MESSAGE must never contain credentials or raw
    task text — it travels into SyncResult.errors and job logs.
    """

    def __init__(self, message: str = "rate limited", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TaskAdapter(ABC):
    """Abstract adapter — concrete impls per task system live in sibling modules."""

    #: kebab-case slug uniquely identifying this adapter (e.g. "github-issues")
    destination: ClassVar[str] = ""

    #: env var the adapter expects for auth (e.g. "JIRA_API_TOKEN")
    auth_env_var: ClassVar[str] = ""

    #: rate-limit/backoff policy (conformance-pinned; override per adapter
    #: only with a reason in the adapter's header)
    max_retries: ClassVar[int] = 4
    backoff_base_s: ClassVar[float] = 0.5
    backoff_cap_s: ClassVar[float] = 30.0
    #: ceiling on a SERVER-SUPPLIED retry_after — that value usually comes
    #: straight from an untrusted tracker reply (Retry-After header), and a
    #: hostile reply claiming retry_after=1e9 must not park a launchd sync
    #: job in a year-long sleep (conformance C4 pins this clamp)
    retry_after_cap_s: ClassVar[float] = 300.0

    def __init__(self, project_config: dict[str, Any]) -> None:
        """`project_config` is the `tasks:` block from instance/config/projects/<slug>.yml."""
        self.project_config = project_config
        self.adapter_config: dict[str, Any] = project_config.get("config") or {}
        # Injectable time seams (conformance suite swaps these for a fake
        # clock/sleep recorder — production code always uses the defaults).
        self._clock: Callable[[], float] = time.monotonic
        self._sleep: Callable[[float], None] = time.sleep

    def __repr__(self) -> str:  # redacting by construction — never the token VALUE
        token_env = self.project_config.get("auth_env") or self.auth_env_var or None
        state = "set" if (token_env and os.environ.get(token_env)) else "unset"
        return (
            f"<{type(self).__name__} destination={self.destination!r} "
            f"auth_env={token_env!r} token={state}>"
        )

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
        """Read auth from env. `project_config.auth_env` may RENAME the env
        var, but the token VALUE always comes from os.environ — a value
        embedded in config is deliberately ignored (credential hygiene,
        conformance check C5)."""
        token_env = self.project_config.get("auth_env") or self.auth_env_var
        return os.environ.get(token_env) if token_env else None

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _with_backoff(self, fn: Callable[[], Any], *, op: str = "call") -> Any:
        """Run `fn`, retrying on RateLimitedError with exponential backoff.

        Delay ladder: backoff_base_s * 2^(attempt-1), capped at backoff_cap_s,
        raised to the external system's retry_after when supplied — with
        retry_after itself clamped at retry_after_cap_s, because it is
        untrusted tracker input and must never dictate an unbounded sleep.
        After max_retries retries the RateLimitedError propagates (the sync
        cycle records it as an error — never an infinite spin). Sleeps go
        through self._sleep so the conformance suite can observe them with a
        fake clock instead of really sleeping.
        """
        attempt = 0
        while True:
            try:
                return fn()
            except RateLimitedError as exc:
                attempt += 1
                if attempt > self.max_retries:
                    raise
                delay = min(self.backoff_cap_s, self.backoff_base_s * (2 ** (attempt - 1)))
                if exc.retry_after is not None:
                    delay = max(delay, min(float(exc.retry_after), self.retry_after_cap_s))
                self._sleep(delay)


# ---------------------------------------------------------------------------
# No-op adapter — projects with no external task system
# ---------------------------------------------------------------------------

#: tasks.system values that mean "nothing to sync": the lane's board is
#: reached through a Claude plugin (e.g. dev-tasks MCP tools) or task sync is
#: deliberately disabled. Any "plugin:<name>" value counts as plugin-routed.
NO_SYNC_SYSTEMS = frozenset({"none", "plugin", "dev-tasks"})


class NoOpTaskAdapter(TaskAdapter):
    """Clean no-op for projects without an external task system.

    Returned by get_adapter() when the project config has no `tasks:` block
    or declares a no-sync system (NO_SYNC_SYSTEMS / "plugin:<name>").
    Plugin-routed lanes deliberately omit tasks.system — officers reach the
    board through the plugin's MCP tools — so the 900s task-sync cycle has
    nothing to do and must exit 0 instead of crash-looping on ValueError.
    """

    destination = "none"
    auth_env_var = ""

    def __init__(self, tasks_block: dict[str, Any], system: str | None = None) -> None:
        super().__init__(tasks_block or {})
        self.system = system

    def health_check(self) -> bool:
        return True  # nothing to reach — always healthy

    def pull(self) -> list[CanonicalTask]:
        return []  # nothing external to read

    def push(self, task: CanonicalTask) -> str:
        return task.external_id or ""  # nowhere to write — keep idempotent shape

    def delete(self, external_id: str) -> None:
        return None

    def link(self, canonical_id: str, external_id: str) -> None:
        return None


# ---------------------------------------------------------------------------
# Observe-only wrapper — structural read-only for any non-owned tracker
# ---------------------------------------------------------------------------


class ObserveOnlyTaskAdapter(TaskAdapter):
    """A tracker the operator does not own: reads pass through, writes cannot.

    STRUCTURAL, and the word is doing work. This is not the real adapter with
    a `read_only=True` flag consulted inside `push` — it is a different type,
    handed out by the factory, whose write methods have no implementation to
    reach. Nothing in the process can turn `push` back into a write short of
    reclassifying the source, which is an operator act with its own record.

    `pull` and `health_check` delegate: reading a tracker the operator has a
    seat in is what an employee-altitude cabinet is FOR, and refusing that
    would be safety theatre that costs the whole feature.
    """

    def __init__(self, inner: TaskAdapter, *, ownership: str, authority_basis: str) -> None:
        super().__init__(inner.project_config)
        self.inner = inner
        self.ownership = require_ownership(ownership)
        self.authority_basis = require_authority_basis(authority_basis)
        self.destination = inner.destination
        # Belt-and-braces: the factory is the only caller, but a future one
        # must not be able to wrap an owned source and quietly lose its writes.
        if writes_permitted(self.ownership):
            raise ValueError(
                "ObserveOnlyTaskAdapter wraps a NON-OWNED source; "
                f"{self.ownership!r} owns its writes and must not be wrapped"
            )

    def __repr__(self) -> str:
        return (
            f"<ObserveOnlyTaskAdapter destination={self.destination!r} "
            f"ownership={self.ownership!r} writes=refused>"
        )

    def health_check(self) -> bool:
        return self.inner.health_check()

    def pull(self) -> list[CanonicalTask]:
        return self.inner.pull()

    def push(self, task: CanonicalTask) -> str:
        require_write_permitted(self.ownership, operation=f"push to {self.destination}")
        raise AssertionError("unreachable: require_write_permitted always refuses here")

    def delete(self, external_id: str) -> None:
        require_write_permitted(self.ownership, operation=f"delete in {self.destination}")
        raise AssertionError("unreachable: require_write_permitted always refuses here")

    def link(self, canonical_id: str, external_id: str) -> None:
        require_write_permitted(self.ownership, operation=f"link in {self.destination}")
        raise AssertionError("unreachable: require_write_permitted always refuses here")


# ---------------------------------------------------------------------------
# Adapter registry — ONE truth for which adapters exist + their CI posture
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdapterSpec:
    """One registry row per adapter (authoring kit, 2026-07-17).

    * implemented=True  → the adapter claims to really sync. It MUST name a
      `conformance_fixture` ("module:Class" import path) and pass the full
      conformance suite — tests/test_conformance.py auto-discovers this
      registry, so registering an implemented adapter without a passing
      fixture is a red CI, by design.
    * implemented=False → honest skeleton: pull/push/delete/link raise
      NotImplementedError and health_check never returns True (a skeleton
      claiming healthy would lie to the sync runner). Also CI-pinned.
    * selectable=False  → refused by get_adapter (harness-only rows like
      the in-memory reference adapter — never a production tracker).
    * config_example    → a minimal valid `tasks:` block the harness uses to
      instantiate the adapter (constructor-validation shape, no secrets).
    """

    system: str
    module: str
    cls_name: str
    implemented: bool
    config_example: dict[str, Any]
    selectable: bool = True
    conformance_fixture: str | None = None


ADAPTER_REGISTRY: dict[str, AdapterSpec] = {
    "github-issues": AdapterSpec(
        system="github-issues",
        module="cabinet.scripts.task_adapters.github_issues",
        cls_name="GitHubIssuesAdapter",
        implemented=True,
        conformance_fixture=(
            "cabinet.scripts.task_adapters.conformance_fixtures:GitHubIssuesConformanceFixture"
        ),
        config_example={"system": "github-issues", "config": {"repo": "example-org/example-repo"}},
    ),
    "jira": AdapterSpec(
        system="jira",
        module="cabinet.scripts.task_adapters.jira",
        cls_name="JiraAdapter",
        implemented=False,
        config_example={"system": "jira", "config": {
            "domain": "example", "email": "officer@example.invalid", "project_key": "EX",
        }},
    ),
    "linear": AdapterSpec(
        system="linear",
        module="cabinet.scripts.task_adapters.linear",
        cls_name="LinearAdapter",
        implemented=False,
        config_example={"system": "linear", "config": {"team_id": "team-example"}},
    ),
    "asana": AdapterSpec(
        system="asana",
        module="cabinet.scripts.task_adapters.asana",
        cls_name="AsanaAdapter",
        implemented=False,
        config_example={"system": "asana", "config": {
            "workspace_id": "ws-example", "project_gid": "proj-example",
        }},
    ),
    # Harness anchor: the fully working in-memory reference adapter every
    # conformance run measures the suite against. NOT selectable — an
    # in-process dict is not a production tracker.
    "reference-inmemory": AdapterSpec(
        system="reference-inmemory",
        module="cabinet.scripts.task_adapters.reference_inmemory",
        cls_name="InMemoryReferenceAdapter",
        implemented=True,
        selectable=False,
        conformance_fixture=(
            "cabinet.scripts.task_adapters.conformance_fixtures:ReferenceConformanceFixture"
        ),
        config_example={"system": "reference-inmemory", "config": {}},
    ),
}


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


def get_adapter(project_config: dict[str, Any]) -> TaskAdapter:
    """Instantiate the right adapter based on project_config['tasks']['system'].

    A missing `tasks:` block, or tasks.system in NO_SYNC_SYSTEMS (or any
    "plugin:<name>"), returns a NoOpTaskAdapter: plugin-routed lanes omit
    the block by design, and the task-sync runner must treat that as a
    clean no-op (one info line, exit 0) — not a config error that
    crash-loops the 900s launchd cycle.

    Everything else resolves through ADAPTER_REGISTRY (module paths are
    registry CONSTANTS — config input never names an import path). Imports
    stay lazy so unused adapters cost no mandatory deps.

    A real tracker must additionally declare `tasks.ownership` and
    `tasks.authority_basis`; a non-`self` class comes back wrapped in
    ObserveOnlyTaskAdapter. The no-op path needs neither, and that is not a
    hole: NoOpTaskAdapter writes nowhere by construction, so there is no act
    to authorize.

    Args:
        project_config: full project YAML dict (a `tasks: {system: ...}`
            block selects an external adapter; absent block = no-op)

    Raises:
        ValueError: if the system slug is unknown, harness-only, "monday"
            (plugin-routed since the adapter's removal), or the tracker has
            no usable ownership declaration.
    """
    tasks_block = project_config.get("tasks") or {}
    system = tasks_block.get("system")
    if not system or str(system) in NO_SYNC_SYSTEMS or str(system).startswith("plugin:"):
        reason = (
            f"tasks.system={system!r} is plugin-routed/disabled" if system
            else "no tasks block configured"
        )
        print(
            f"task-sync: INFO {reason} — no external task system to sync; "
            f"clean no-op",
            file=sys.stderr,
        )
        return NoOpTaskAdapter(tasks_block, system=system)

    if system == "monday":
        # The cabinet's own Monday adapter was removed in favor of a
        # dedicated Monday Claude plugin (dev-tasks-style: dozens of Monday
        # MCP tools + workflow skills). Officers reach Monday via the
        # plugin's mcp__dev-tasks tools, NOT through this adapter interface.
        #
        # Configure the plugin via instance/config/extensions.yml +
        # .claude/project-config.json. To restore the built-in adapter
        # instead: `git show <pre-plugin-commit>:cabinet/scripts/task_adapters/monday.py`
        raise ValueError(
            "Monday adapter removed — configure a dev-tasks-style Monday "
            "plugin instead. Set tasks.system to 'github-issues' (cabinet "
            "default) or 'linear', and declare the plugin in "
            "instance/config/extensions.yml + .claude/project-config.json."
        )

    spec = ADAPTER_REGISTRY.get(str(system))
    if spec is None:
        selectable = ", ".join(sorted(s for s, r in ADAPTER_REGISTRY.items() if r.selectable))
        raise ValueError(
            f"Unknown task system: {system!r}. "
            f"Supported: {selectable} (monday is plugin-routed). "
            "New tracker? cabinet/runbooks/task-adapter-authoring.md."
        )
    if not spec.selectable:
        raise ValueError(
            f"tasks.system={system!r} is a conformance-harness reference adapter, "
            "not a production tracker — pick one of: "
            + ", ".join(sorted(s for s, r in ADAPTER_REGISTRY.items() if r.selectable))
        )

    # THE OWNERSHIP GATE. A real tracker reached here, so the operator must
    # have said whose it is and under what right. Unclassified is a REFUSAL,
    # not a default: guessing "probably theirs" is the cabinet making an
    # authorization decision that is not the cabinet's to make.
    try:
        ownership = require_ownership(tasks_block.get("ownership"))
        authority_basis = require_authority_basis(tasks_block.get("authority_basis"))
    except OwnershipRefusal as exc:
        raise ValueError(
            f"tasks.system={system!r} has no usable ownership declaration: {exc} "
            f"Set tasks.ownership to one of {', '.join(OWNERSHIP_CLASSES)} and "
            "tasks.authority_basis to the right you hold over it "
            "(instance/config/projects/_template.yml documents both)."
        ) from exc

    module = importlib.import_module(spec.module)
    cls = getattr(module, spec.cls_name)
    adapter = cls(tasks_block)
    if writes_permitted(ownership):
        return adapter
    print(
        f"task-sync: INFO {system} is classified {ownership} — observe-only; "
        f"writes are refused structurally",
        file=sys.stderr,
    )
    return ObserveOnlyTaskAdapter(
        adapter, ownership=ownership, authority_basis=authority_basis
    )
