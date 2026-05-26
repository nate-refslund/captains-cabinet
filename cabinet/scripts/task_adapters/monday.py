"""Monday.com adapter — SKELETON.

Phase 5.3 of the convergence plan. Real implementation deferred until Captain
provides MONDAY_API_TOKEN in cabinet/.env and a board_id in the project config.

API: Monday.com GraphQL v2 (https://developer.monday.com/api-reference/docs)
Auth: API token (header `Authorization: <token>`)
Endpoint: https://api.monday.com/v2

Mapping (target):
  CanonicalTask                     Monday item
  -----------------------------     -----------------------------
  canonical_id                      column_value "cabinet_id" (text column)
  title                             item name
  description                       column_value "description" (long_text)
  status open                       column status "Working on it" or "Not Started"
  status in_progress                column status "Working on it"
  status blocked                    column status "Stuck"
  status done                       column status "Done"
  status cancelled                  item archived
  assigned_role                     column "officer" (text or people)
  priority                          column "priority"
  due_at                            column "due_date"
  tags                              tags column

Required project_config:
  tasks:
    system: monday
    auth_env: MONDAY_API_TOKEN
    config:
      board_id: 1234567890           # numeric board id
      column_status: status_1        # column id (NOT column title)
      column_priority: priority      # optional
      column_owner: person           # optional
      column_canonical_id: text_1    # required — holds the canonical_id
"""

from __future__ import annotations

from typing import Any

from cabinet.scripts.task_adapters.base import CanonicalTask, TaskAdapter


class MondayAdapter(TaskAdapter):
    destination = "monday"
    auth_env_var = "MONDAY_API_TOKEN"

    def __init__(self, project_config: dict[str, Any]) -> None:
        super().__init__(project_config)
        self.board_id = self.adapter_config.get("board_id")
        if not self.board_id:
            raise ValueError("monday adapter requires tasks.config.board_id")

    def health_check(self) -> bool:
        """Skeleton: returns False until implemented.

        Production implementation:
          POST https://api.monday.com/v2
          query { me { id name } }
          Authorization: <token>
        """
        return False

    def pull(self) -> list[CanonicalTask]:
        raise NotImplementedError(
            "monday adapter is a skeleton. Implement against the Monday GraphQL "
            "API: query { boards (ids: [<board_id>]) { items_page { items { ... } } } }"
        )

    def push(self, task: CanonicalTask) -> str:
        raise NotImplementedError(
            "monday adapter is a skeleton. Implement upsert via "
            "mutation create_item / change_column_value. Keyed on column_canonical_id."
        )

    def delete(self, external_id: str) -> None:
        raise NotImplementedError(
            "monday adapter is a skeleton. mutation archive_item (Id: $id)"
        )

    def link(self, canonical_id: str, external_id: str) -> None:
        raise NotImplementedError(
            "monday adapter is a skeleton. Set the column_canonical_id text column."
        )
