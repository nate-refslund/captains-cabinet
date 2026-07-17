"""TEMPLATE adapter — copy this file to start a new tracker adapter.

This is an HONEST scaffold: every method raises NotImplementedError with the
contract it must satisfy. It is deliberately NOT registered in
ADAPTER_REGISTRY (leading-underscore modules are exempt from the registry
scan in tests/test_conformance.py) and it deliberately FAILS the conformance
suite — the suite's negative control pins that (a scaffold that passed
conformance would mean the suite tests nothing).

Authoring flow (full runbook: cabinet/runbooks/task-adapter-authoring.md):

  1. `cp _template.py <system>.py` (kebab-case slug → snake_case module).
  2. Implement the five methods against the contract documented on each one.
     Route every remote WRITE through `self._with_backoff(...)` and raise
     `RateLimitedError` from your transport on 429/rate-limit replies.
  3. Add an ADAPTER_REGISTRY row in base.py. While building, register with
     `implemented=False` (CI then pins you as an honest skeleton). When done,
     flip `implemented=True` AND point `conformance_fixture` at a
     ConformanceFixture subclass in conformance_fixtures.py that fakes your
     transport in-process (no network in tests).
  4. `python3.12 -m pytest cabinet/scripts/task_adapters/tests -q` — the
     conformance suite auto-discovers your registry row. Red until your
     adapter really round-trips, re-syncs idempotently, resolves conflicts
     canonical-wins, backs off on rate limits, and keeps credentials out of
     logs/repr.

SECURITY CONTRACT (base.py header, binding):
  * tracker text (titles/descriptions/tags) is UNTRUSTED — argv lists only,
    never shell=True, never interpolated into SQL/jq, never eval'd;
  * credentials ONLY from env (auth_env_var / config auth_env NAME);
    never logged, never in repr, never in exception messages.
"""

from __future__ import annotations

from typing import Any

from cabinet.scripts.task_adapters.base import CanonicalTask, TaskAdapter


class TemplateAdapter(TaskAdapter):
    """Rename me. `destination` must match the registry slug exactly."""

    destination = "template"
    auth_env_var = "TEMPLATE_API_TOKEN"  # the env VAR NAME your tracker needs

    def __init__(self, project_config: dict[str, Any]) -> None:
        super().__init__(project_config)
        # Validate REQUIRED tasks.config keys here and raise ValueError with
        # the exact key name (mirrors jira/linear/asana constructors). Never
        # validate or store credential VALUES — only env var names.

    # ----- lifecycle -----

    def health_check(self) -> bool:
        """Contract: True ONLY when the external system is reachable AND auth
        works, using a cheap read-only call (e.g. GET /viewer). Must never
        raise for ordinary unreachability — return False. A skeleton must
        return False (a healthy-claiming stub lies to the sync runner)."""
        return False  # honest scaffold: not implemented ⇒ never healthy

    # ----- read -----

    def pull(self) -> list[CanonicalTask]:
        """Contract: read ALL live tasks from the external system into
        CanonicalTask shape. `external_id` and `external_url` must be set on
        every returned task; `canonical_id` comes from the tag/label/custom
        field written by link()/push() (tasks born external get a stable
        fallback id, see github_issues.py). Read-only — pull never mutates
        the external system."""
        raise NotImplementedError(
            "template adapter: implement pull() per the contract in its docstring"
        )

    # ----- write -----

    def push(self, task: CanonicalTask) -> str:
        """Contract: UPSERT keyed on canonical_id (find-by-canonical-id, then
        update-else-create) and return the external_id. Idempotent: pushing
        the same task twice must not create a duplicate. Conflict rule:
        canonical wins — external edits are overwritten (log a warning with
        COUNTS, not task text). Wrap the remote calls in
        self._with_backoff(...) so rate limits retry instead of failing the
        sync cycle."""
        raise NotImplementedError(
            "template adapter: implement push() per the contract in its docstring"
        )

    def delete(self, external_id: str) -> None:
        """Contract: remove (or close/archive, if the system has no hard
        delete — say which in your docstring) the external item. Deleting an
        already-gone item must be a no-op, not an error (idempotent)."""
        raise NotImplementedError(
            "template adapter: implement delete() per the contract in its docstring"
        )

    def link(self, canonical_id: str, external_id: str) -> None:
        """Contract: persist the canonical_id on the EXTERNAL item (tag /
        label / custom field) so pull() can join the two sides. Cabinet keeps
        the inverse mapping; this writes only the external half."""
        raise NotImplementedError(
            "template adapter: implement link() per the contract in its docstring"
        )
