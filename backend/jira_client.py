import os
import base64
import re
from typing import List, Dict, Any, Optional
from urllib.parse import parse_qs, urlparse

import httpx


class JiraClient:
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        settings = settings or {}
        raw_base_url = settings.get("jira_url") or os.getenv("JIRA_URL") or ""
        self.base_url = self._normalize_base_url(raw_base_url)
        self.email = settings.get("jira_email") or os.getenv("JIRA_EMAIL") or ""
        self.api_token = settings.get("jira_api_token") or os.getenv("JIRA_API_TOKEN") or ""
        self.project_key = settings.get("jira_project_key") or os.getenv("JIRA_PROJECT_KEY") or ""
        self.platform = settings.get("project_platform", "azure")
        self.story_points_field = os.getenv("JIRA_STORY_POINTS_FIELD", "customfield_10016")
        self.mock_mode = not (self.base_url and self.email and self.api_token and self.project_key)
        if self.mock_mode:
            print("[JIRA] Integration is not fully configured. Real Jira requests are disabled until URL/email/token/project key are saved.")
        else:
            print(f"[JIRA] Initialized client for Project: {self.project_key} at {self.base_url}")

    def _normalize_base_url(self, raw_url: str) -> str:
        value = (raw_url or "").strip().strip("`").strip().strip("'").strip('"')
        if not value:
            return ""

        if "://" not in value:
            value = f"https://{value}"

        parsed = urlparse(value)

        # If the user pasted an Atlassian browser redirect URL, prefer the origin
        # of the embedded continue target when present.
        query = parse_qs(parsed.query)
        continue_values = query.get("continue") or []
        if continue_values:
            continue_parsed = urlparse(continue_values[0])
            if continue_parsed.scheme and continue_parsed.netloc:
                parsed = continue_parsed

        if not parsed.scheme or not parsed.netloc:
            return value.rstrip("/")

        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

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

    def _sanitize_labels(self, labels: Any) -> List[str]:
        if not isinstance(labels, list):
            return []

        sanitized: List[str] = []
        for label in labels:
            text = str(label or "").strip().lower().replace(" ", "-")
            text = re.sub(r"[^a-z0-9_-]+", "-", text)
            text = re.sub(r"-{2,}", "-", text).strip("-_")
            if text:
                sanitized.append(text[:255])
        return sanitized[:20]

    def _ensure_configured(self):
        if self.mock_mode:
            raise RuntimeError(
                "Jira integration is not fully configured. Save Jira URL, email, API token, and project key in Settings."
            )

    def _raise_for_status(self, response: httpx.Response, action: str):
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location", "")
            raise RuntimeError(
                f"Jira {action} was redirected. Check the Jira URL in Settings and use the site root only, for example "
                f"'https://your-domain.atlassian.net'. Current normalized URL: {self.base_url}. Redirect location: {location}"
            )
        if response.status_code >= 400:
            detail = self._extract_error_details(response)
            if detail:
                raise RuntimeError(f"Jira {action} failed with HTTP {response.status_code}: {detail}")
        response.raise_for_status()

    def _extract_error_details(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            return (response.text or "").strip()

        error_messages = payload.get("errorMessages") or []
        field_errors = payload.get("errors") or {}

        details: List[str] = []
        for message in error_messages:
            if message:
                details.append(str(message))
        for field, message in field_errors.items():
            if message:
                details.append(f"{field}: {message}")
        return "; ".join(details)

    def _build_create_payload(
        self,
        issue_type_name: str,
        item_data: Dict[str, Any],
        include_story_points: bool = True,
    ) -> Dict[str, Any]:
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": item_data["title"],
                "description": self._adf_paragraph(item_data.get("description", "")),
                "issuetype": {"name": issue_type_name},
                "labels": self._sanitize_labels(item_data.get("tags", [])),
            }
        }
        if include_story_points and item_data.get("story_points") is not None:
            payload["fields"][self.story_points_field] = int(item_data["story_points"])
        return payload

    async def _try_create_issue(
        self,
        client: httpx.AsyncClient,
        issue_type_name: str,
        item_data: Dict[str, Any],
        include_story_points: bool,
    ) -> Dict[str, Any]:
        create_payload = self._build_create_payload(
            issue_type_name=issue_type_name,
            item_data=item_data,
            include_story_points=include_story_points,
        )
        create_url = f"{self.base_url}/rest/api/3/issue"
        create_res = await client.post(create_url, headers=self._get_headers(), json=create_payload)
        self._raise_for_status(
            create_res,
            f"issue creation using type '{issue_type_name}'"
            + ("" if include_story_points else " without story points"),
        )
        return create_res.json()

    async def _get_board_id(self) -> Optional[int]:
        self._ensure_configured()
        url = f"{self.base_url}/rest/agile/1.0/board"
        params = {"projectKeyOrId": self.project_key, "maxResults": 50}
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(url, headers=self._get_headers(), params=params)
            self._raise_for_status(res, "board lookup")
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

        self._ensure_configured()

        async with httpx.AsyncClient(timeout=30.0) as client:
            create_attempts = [
                (issue_type_name, True),
                (issue_type_name, False),
            ]
            if issue_type_name != "Task":
                create_attempts.extend([
                    ("Task", True),
                    ("Task", False),
                ])

            issue: Optional[Dict[str, Any]] = None
            errors: List[str] = []
            for attempt_issue_type, include_story_points in create_attempts:
                try:
                    issue = await self._try_create_issue(
                        client=client,
                        issue_type_name=attempt_issue_type,
                        item_data=item_data,
                        include_story_points=include_story_points,
                    )
                    break
                except Exception as exc:
                    errors.append(str(exc))

            if issue is None:
                raise RuntimeError(" | ".join(errors))

            if iteration_path:
                sprint_url = f"{self.base_url}/rest/agile/1.0/sprint/{iteration_path}/issue"
                sprint_payload = {"issues": [issue["key"]]}
                sprint_res = await client.post(sprint_url, headers=self._get_headers(), json=sprint_payload)
                self._raise_for_status(sprint_res, "sprint assignment")

            return issue

    async def get_active_sprints(self) -> List[Dict[str, Any]]:
        if self.mock_mode:
            return []

        board_id = await self._get_board_id()
        if not board_id:
            return []

        url = f"{self.base_url}/rest/agile/1.0/board/{board_id}/sprint"
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(url, headers=self._get_headers(), params={"maxResults": 50})
            self._raise_for_status(res, "sprint lookup")
            values = res.json().get("values", [])
            results = []
            for sprint in values:
                state = (sprint.get("state") or "").lower()
                if state == "closed":
                    continue
                time_frame = "current" if state == "active" else "future"
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
            return []

        sprint_id = iteration_path
        url = f"{self.base_url}/rest/agile/1.0/sprint/{sprint_id}/issue"
        params = {"maxResults": 100}
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(url, headers=self._get_headers(), params=params)
            self._raise_for_status(res, "sprint work item lookup")
            issues = res.json().get("issues", [])
            results = []
            for issue in issues:
                fields = issue.get("fields", {})
                issue_type = (fields.get("issuetype") or {}).get("name", "Task")
                status = (fields.get("status") or {}).get("name", "To Do")
                points = fields.get(self.story_points_field, 0)
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
