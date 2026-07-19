import base64
from typing import List, Dict, Any, Optional

import httpx


class JiraClient:
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        settings = settings or {}
        self.base_url = (settings.get("jira_url") or "").rstrip("/")
        self.email = settings.get("jira_email") or ""
        self.api_token = settings.get("jira_api_token") or ""
        self.project_key = settings.get("jira_project_key") or ""
        self.platform = settings.get("project_platform", "azure")
        self.mock_mode = self.platform != "jira" or not (
            self.base_url and self.email and self.api_token and self.project_key
        )
        if self.mock_mode:
            print("[JIRA] Operating in MOCK MODE because URL/email/token/project key are not fully configured.")
        else:
            print(f"[JIRA] Initialized client for Project: {self.project_key} at {self.base_url}")

    def _get_headers(self) -> Dict[str, str]:
        auth = base64.b64encode(f"{self.email}:{self.api_token}".encode("utf-8")).decode("utf-8")
        return {
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _adf_paragraph(self, text: str) -> Dict[str, Any]:
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text or ""}],
                }
            ],
        }

    async def _get_board_id(self) -> Optional[int]:
        if self.mock_mode:
            return None
        url = f"{self.base_url}/rest/agile/1.0/board"
        params = {"projectKeyOrId": self.project_key, "maxResults": 50}
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(url, headers=self._get_headers(), params=params)
            res.raise_for_status()
            boards = res.json().get("values", [])
            if not boards:
                return None
            scrum_boards = [b for b in boards if b.get("type") == "scrum"]
            chosen = scrum_boards[0] if scrum_boards else boards[0]
            return chosen.get("id")

    async def create_work_item(
        self, item_type: str, item_data: Dict[str, Any], iteration_path: Optional[str] = None
    ) -> Dict[str, Any]:
        issue_type_name = "Task"
        if item_type in ("story", "feature"):
            issue_type_name = "Story"

        if self.mock_mode:
            import random

            issue_id = str(random.randint(10000, 99999))
            issue_key = f"{self.project_key or 'MOCK'}-{random.randint(1, 999)}"
            return {
                "id": issue_id,
                "key": issue_key,
                "fields": {
                    "summary": item_data["title"],
                    "issuetype": {"name": issue_type_name},
                    "status": {"name": "To Do"},
                },
            }

        create_payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": item_data["title"],
                "description": self._adf_paragraph(item_data.get("description", "")),
                "issuetype": {"name": issue_type_name},
                "labels": item_data.get("tags", []),
            }
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            create_url = f"{self.base_url}/rest/api/3/issue"
            create_res = await client.post(create_url, headers=self._get_headers(), json=create_payload)
            create_res.raise_for_status()
            issue = create_res.json()

            if iteration_path:
                sprint_url = f"{self.base_url}/rest/agile/1.0/sprint/{iteration_path}/issue"
                sprint_payload = {"issues": [issue["key"]]}
                sprint_res = await client.post(sprint_url, headers=self._get_headers(), json=sprint_payload)
                sprint_res.raise_for_status()

            return issue

    async def get_active_sprints(self) -> List[Dict[str, Any]]:
        if self.mock_mode:
            return [
                {"id": "101", "name": "Sprint 1", "path": "101", "timeFrame": "past"},
                {"id": "102", "name": "Sprint 2", "path": "102", "timeFrame": "current"},
                {"id": "103", "name": "Sprint 3", "path": "103", "timeFrame": "future"},
            ]

        board_id = await self._get_board_id()
        if not board_id:
            return []

        url = f"{self.base_url}/rest/agile/1.0/board/{board_id}/sprint"
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(url, headers=self._get_headers(), params={"maxResults": 50})
            res.raise_for_status()
            values = res.json().get("values", [])
            results = []
            for sprint in values:
                state = (sprint.get("state") or "").lower()
                time_frame = "future"
                if state == "active":
                    time_frame = "current"
                elif state == "closed":
                    time_frame = "past"
                results.append(
                    {
                        "id": str(sprint["id"]),
                        "name": sprint["name"],
                        "path": str(sprint["id"]),
                        "timeFrame": time_frame,
                    }
                )
            return results

    async def get_sprint_work_items(self, iteration_path: str) -> List[Dict[str, Any]]:
        if self.mock_mode:
            return [
                {"id": "JIRA-101", "title": "Wire settings to live integrations", "type": "Story", "state": "Done", "story_points": 5},
                {"id": "JIRA-102", "title": "Stabilize retro aggregation flow", "type": "Task", "state": "In Progress", "story_points": 3},
                {"id": "JIRA-103", "title": "Fix duplicated integration paths", "type": "Bug", "state": "To Do", "story_points": 2},
            ]

        sprint_id = iteration_path
        url = f"{self.base_url}/rest/agile/1.0/sprint/{sprint_id}/issue"
        params = {"maxResults": 100}
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(url, headers=self._get_headers(), params=params)
            res.raise_for_status()
            issues = res.json().get("issues", [])
            results = []
            for issue in issues:
                fields = issue.get("fields", {})
                issue_type = (fields.get("issuetype") or {}).get("name", "Task")
                status = (fields.get("status") or {}).get("name", "To Do")
                points = fields.get("customfield_10016", 0)
                results.append(
                    {
                        "id": issue.get("key") or str(issue.get("id")),
                        "title": fields.get("summary", "Untitled"),
                        "type": issue_type,
                        "state": status,
                        "story_points": int(points or 0),
                    }
                )
            return results
