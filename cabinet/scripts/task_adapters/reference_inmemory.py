"""Reference in-memory adapter — the conformance suite's working anchor.

A COMPLETE TaskAdapter implementation against an in-process dict "tracker"
(no network, no disk, no subprocess). Exists for exactly two reasons:

  1. The conformance suite (conformance.py) needs one adapter that MUST pass
     every check — if the suite can't be passed by an honest implementation,
     the suite is broken, not the adapters (positive control).
  2. Adapter authors get a minimal, readable model of the full contract:
     env-only auth, upsert-by-canonical_id idempotency, canonical-wins
     conflict handling, `_with_backoff` rate-limit retries, and tracker text
     handled as inert data end to end.

NOT selectable via get_adapter (ADAPTER_REGISTRY row carries
selectable=False): an in-process dict is not a production tracker; wiring it
into a live project would silently sync into a void.
"""

from __future__ import annotations

import logging
from typing import Any

from cabinet.scripts.task_adapters.base import (
    CanonicalTask,
    RateLimitedError,
    TaskAdapter,
)

log = logging.getLogger("cabinet.task_adapters.reference_inmemory")

# Fields push() mirrors into the external item. One list so the conflict
# snapshot and the write path can never drift apart. assigned_role rides
# too: the reference models FULL fidelity — an updated push must win on
# role/priority as well (conformance C2).
_MIRRORED_FIELDS = ("title", "description", "status", "priority", "assigned_role", "tags")


class InMemoryTracker:
    """The "external system" double: a dict of items + a write journal.

    * `items`: external_id -> item dict (mirrored fields + canonical_id +
      `_cabinet_snapshot`, the mirrored-field tuple as of the last cabinet
      write — how the adapter detects out-of-band operator edits).
    * `write_log`: (op, external_id, payload) tuples recorded VERBATIM so the
      conformance suite can assert hostile task text arrived byte-identical
      and was never interpreted anywhere on the way.
    * `arm_rate_limit(n)`: the next n WRITE calls raise RateLimitedError
      (reads stay clean — mirrors real trackers' stricter write budgets).
    """

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}
        self.write_log: list[tuple[str, str, dict[str, Any]]] = []
        self._next_id = 1
        self._rate_limit_budget = 0

    def arm_rate_limit(self, n: int, retry_after: float | None = None) -> None:
        self._rate_limit_budget = int(n)
        self._retry_after = retry_after

    def _gate(self) -> None:
        if self._rate_limit_budget > 0:
            self._rate_limit_budget -= 1
            raise RateLimitedError(
                "reference tracker throttled", retry_after=getattr(self, "_retry_after", None)
            )

    # -- write surface (rate-limit gated) --
    def create(self, payload: dict[str, Any]) -> str:
        self._gate()
        external_id = str(self._next_id)
        self._next_id += 1
        self.items[external_id] = dict(payload)
        self.write_log.append(("create", external_id, dict(payload)))
        return external_id

    def update(self, external_id: str, payload: dict[str, Any]) -> None:
        self._gate()
        self.items[external_id].update(payload)
        self.write_log.append(("update", external_id, dict(payload)))

    def remove(self, external_id: str) -> None:
        self._gate()
        self.items.pop(external_id, None)  # idempotent: already-gone is a no-op
        self.write_log.append(("remove", external_id, {}))


class InMemoryReferenceAdapter(TaskAdapter):
    destination = "reference-inmemory"
    auth_env_var = "REFERENCE_TASKS_TOKEN"

    def __init__(self, project_config: dict[str, Any],
                 tracker: InMemoryTracker | None = None) -> None:
        super().__init__(project_config)
        self.tracker = tracker if tracker is not None else InMemoryTracker()
        #: out-of-band external edits overwritten by canonical pushes (the
        #: canonical-wins rule made observable; conformance check C3)
        self.conflicts_observed = 0

    # ----- internals -----

    def _authorize(self) -> None:
        """Credential hygiene: token comes ONLY from env; the error names the
        VAR, never a value (there is no value to name)."""
        if not self.auth_token():
            env = self.project_config.get("auth_env") or self.auth_env_var
            raise RuntimeError(f"reference-inmemory: auth env {env} unset — refusing")

    @staticmethod
    def _snapshot(item: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(
            tuple(item.get(f)) if isinstance(item.get(f), list) else item.get(f)
            for f in _MIRRORED_FIELDS
        )

    @staticmethod
    def _payload(task: CanonicalTask) -> dict[str, Any]:
        """Mirrored fields, VERBATIM — tracker text is inert data; nothing is
        escaped, interpreted, or executed on the way."""
        return {
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "assigned_role": task.assigned_role,
            "tags": list(task.tags),
        }

    # ----- lifecycle -----

    def health_check(self) -> bool:
        """Fail-closed: healthy ONLY with a token in the environment (the
        in-process tracker itself is always reachable)."""
        return bool(self.auth_token())

    # ----- read -----

    def pull(self) -> list[CanonicalTask]:
        self._authorize()
        tasks: list[CanonicalTask] = []
        for external_id, item in sorted(self.tracker.items.items(), key=lambda kv: int(kv[0])):
            tasks.append(CanonicalTask(
                canonical_id=item.get("canonical_id") or f"ref-{external_id}",
                title=item.get("title", ""),
                description=item.get("description", ""),
                status=item.get("status", "open"),
                priority=item.get("priority", "normal"),
                assigned_role=item.get("assigned_role"),
                tags=list(item.get("tags") or []),
                external_id=external_id,
                external_url=f"inmemory://reference/{external_id}",
            ))
        return tasks

    # ----- write -----

    def push(self, task: CanonicalTask) -> str:
        """Upsert keyed on canonical_id; canonical wins on conflict."""
        self._authorize()
        existing_id = next(
            (eid for eid, item in self.tracker.items.items()
             if item.get("canonical_id") == task.canonical_id),
            None,
        )
        payload = self._payload(task)

        if existing_id is not None:
            item = self.tracker.items[existing_id]
            snapshot = item.get("_cabinet_snapshot")
            if snapshot is not None and self._snapshot(item) != tuple(snapshot):
                # Operator edited the mirror out-of-band since our last write.
                # Canonical wins — overwrite, and say so with COUNTS only
                # (task text stays out of logs by contract).
                self.conflicts_observed += 1
                log.warning(
                    "reference-inmemory: conflict on 1 task — canonical wins, "
                    "external edit overwritten (total this session: %d)",
                    self.conflicts_observed,
                )
            self._with_backoff(
                lambda: self.tracker.update(existing_id, payload), op="update")
            item["_cabinet_snapshot"] = self._snapshot(item)
            return existing_id

        create_payload = dict(payload, canonical_id=task.canonical_id)
        external_id = self._with_backoff(
            lambda: self.tracker.create(create_payload), op="create")
        item = self.tracker.items[external_id]
        item["_cabinet_snapshot"] = self._snapshot(item)
        return external_id

    def delete(self, external_id: str) -> None:
        self._authorize()
        self._with_backoff(lambda: self.tracker.remove(external_id), op="remove")

    def link(self, canonical_id: str, external_id: str) -> None:
        self._authorize()
        if external_id not in self.tracker.items:
            raise KeyError(f"reference-inmemory: no external item {external_id!r}")
        self._with_backoff(
            lambda: self.tracker.update(external_id, {"canonical_id": canonical_id}),
            op="link",
        )
