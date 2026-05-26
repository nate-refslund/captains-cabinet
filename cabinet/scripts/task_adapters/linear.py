"""Linear adapter — SKELETON (read-only archive, per Spec 039 cutover).

Phase 5.3. Linear is read-only post Spec-039 cutover (2026-04-26) — the
Cabinet does not write to Linear. The adapter is shipped as a SKELETON for
two reasons:

  1. Audit / migration scenarios may still need to read from Linear archives.
  2. New Cabinet deployments NOT bound by Spec-039 (other Captains, other
     orgs) may choose Linear as a live task system; the adapter is here for
     them.

API: Linear GraphQL (https://developers.linear.app/docs)
Auth: API key (header `Authorization: <key>`)
Endpoint: https://api.linear.app/graphql

Required project_config:
  tasks:
    system: linear
    auth_env: LINEAR_API_KEY
    config:
      team_id: <linear_team_id>
      canonical_id_field: cabinet_id   # custom attribute or label name
"""

from __future__ import annotations

from typing import Any

from cabinet.scripts.task_adapters.base import CanonicalTask, TaskAdapter


class LinearAdapter(TaskAdapter):
    destination = "linear"
    auth_env_var = "LINEAR_API_KEY"

    def __init__(self, project_config: dict[str, Any]) -> None:
        super().__init__(project_config)
        if not self.adapter_config.get("team_id"):
            raise ValueError("linear adapter requires tasks.config.team_id")

    def health_check(self) -> bool:
        """Skeleton. Production: query { viewer { id name } }."""
        return False

    def pull(self) -> list[CanonicalTask]:
        raise NotImplementedError(
            "linear adapter is a skeleton. Implement via query { team(id: $id) "
            "{ issues(filter: { state: { type: { in: [unstarted, started, backlog] } } }) "
            "{ nodes { id title description state { name } assignee { name } } } } }"
        )

    def push(self, task: CanonicalTask) -> str:
        raise NotImplementedError(
            "linear adapter is a skeleton. WRITE FORBIDDEN on Cabinet deployments "
            "bound by Spec-039 (Linear is read-only archive). For other deployments, "
            "implement via mutation issueCreate / issueUpdate keyed on a label or "
            "custom attribute storing canonical_id."
        )

    def delete(self, external_id: str) -> None:
        raise NotImplementedError(
            "linear adapter is a skeleton. mutation issueArchive(id: $id)."
        )

    def link(self, canonical_id: str, external_id: str) -> None:
        raise NotImplementedError(
            "linear adapter is a skeleton. Set the cabinet_id label / attribute."
        )
