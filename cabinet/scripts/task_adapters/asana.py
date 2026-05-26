"""Asana adapter — SKELETON.

Phase 5.3. Implement when ASANA_API_TOKEN + workspace_id + project_gid provided.

API: Asana REST v1 (https://developers.asana.com/reference/rest-api-reference)
Auth: Bearer token
Endpoint: https://app.asana.com/api/1.0

Mapping (target):
  CanonicalTask                     Asana task
  -----------------------------     -----------------------------
  canonical_id                      custom field 'cabinet_id' (text)
  title                             name
  description                       notes
  status open                       completed=false
  status done                       completed=true
  assigned_role                     assignee (gid or custom field)
  priority                          custom field 'priority'
  due_at                            due_on (YYYY-MM-DD)
  tags                              tags

Required project_config:
  tasks:
    system: asana
    auth_env: ASANA_API_TOKEN
    config:
      workspace_id: <gid>
      project_gid: <gid>
      canonical_id_field_gid: <gid>  # custom field gid
"""

from __future__ import annotations

from typing import Any

from cabinet.scripts.task_adapters.base import CanonicalTask, TaskAdapter


class AsanaAdapter(TaskAdapter):
    destination = "asana"
    auth_env_var = "ASANA_API_TOKEN"

    def __init__(self, project_config: dict[str, Any]) -> None:
        super().__init__(project_config)
        for field in ("workspace_id", "project_gid"):
            if not self.adapter_config.get(field):
                raise ValueError(f"asana adapter requires tasks.config.{field}")

    def health_check(self) -> bool:
        """Skeleton. Production: GET /users/me."""
        return False

    def pull(self) -> list[CanonicalTask]:
        raise NotImplementedError(
            "asana adapter is a skeleton. Implement via "
            "GET /projects/<gid>/tasks?opt_fields=name,notes,completed,assignee,due_on,custom_fields"
        )

    def push(self, task: CanonicalTask) -> str:
        raise NotImplementedError(
            "asana adapter is a skeleton. Find existing via custom field search "
            "GET /workspaces/<gid>/tasks/search?custom_fields.<gid>.value=<canonical_id>, "
            "then POST /tasks (create) or PUT /tasks/<gid> (update)."
        )

    def delete(self, external_id: str) -> None:
        raise NotImplementedError(
            "asana adapter is a skeleton. DELETE /tasks/<gid>."
        )

    def link(self, canonical_id: str, external_id: str) -> None:
        raise NotImplementedError(
            "asana adapter is a skeleton. PUT /tasks/<gid> with "
            "data.custom_fields.<gid> = canonical_id."
        )
