"""Jira adapter — SKELETON.

Phase 5.3. Implement when JIRA_API_TOKEN + JIRA_EMAIL + JIRA_DOMAIN provided.

API: Jira Cloud REST v3 (https://developer.atlassian.com/cloud/jira/platform/rest/v3/)
Auth: Basic (email + API token)
Endpoint: https://<domain>.atlassian.net/rest/api/3

Mapping (target):
  CanonicalTask                     Jira issue
  -----------------------------     -----------------------------
  canonical_id                      custom field 'cabinet_canonical_id'
  title                             summary
  description                       description (ADF)
  status                            issue status (configurable workflow)
  assigned_role                     assignee OR custom field 'cabinet_role'
  priority                          priority
  due_at                            duedate
  tags                              labels

Required project_config:
  tasks:
    system: jira
    auth_env: JIRA_API_TOKEN
    config:
      domain: <subdomain>            # e.g. "mycompany" for mycompany.atlassian.net
      email: <atlassian_email>       # the user whose API token is used
      project_key: PROJ              # Jira project key
      issue_type: Task               # or Story / Bug / etc.
      canonical_id_field: customfield_10001  # required
"""

from __future__ import annotations

from typing import Any

from cabinet.scripts.task_adapters.base import CanonicalTask, TaskAdapter


class JiraAdapter(TaskAdapter):
    destination = "jira"
    auth_env_var = "JIRA_API_TOKEN"

    def __init__(self, project_config: dict[str, Any]) -> None:
        super().__init__(project_config)
        for field in ("domain", "project_key", "email"):
            if not self.adapter_config.get(field):
                raise ValueError(f"jira adapter requires tasks.config.{field}")

    def health_check(self) -> bool:
        """Skeleton. Production: GET /rest/api/3/myself."""
        return False

    def pull(self) -> list[CanonicalTask]:
        raise NotImplementedError(
            "jira adapter is a skeleton. Implement against POST /rest/api/3/search/jql "
            "with JQL: 'project = <key> AND statusCategory != Done OR updated > -7d'."
        )

    def push(self, task: CanonicalTask) -> str:
        raise NotImplementedError(
            "jira adapter is a skeleton. Upsert via POST /rest/api/3/issue (create) "
            "or PUT /rest/api/3/issue/<key> (update). Find existing by JQL on "
            "the canonical_id custom field."
        )

    def delete(self, external_id: str) -> None:
        raise NotImplementedError(
            "jira adapter is a skeleton. DELETE /rest/api/3/issue/<key> "
            "(usually we transition to 'Cancelled' status instead — delete is permanent)."
        )

    def link(self, canonical_id: str, external_id: str) -> None:
        raise NotImplementedError(
            "jira adapter is a skeleton. PUT /rest/api/3/issue/<key> with "
            "fields.<canonical_id_field> = canonical_id."
        )
