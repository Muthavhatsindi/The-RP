import os
import base64
import httpx
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

AZURE_ORGANIZATION = os.getenv("AZURE_ORGANIZATION", "")
AZURE_PROJECT = os.getenv("AZURE_PROJECT", "")
AZURE_PAT = os.getenv("AZURE_PAT", "")
AZURE_API_VERSION = os.getenv("AZURE_API_VERSION", "7.1")

FEATURE_TYPE = os.getenv("AZURE_FEATURE_TYPE", "Feature")
STORY_TYPE = os.getenv("AZURE_STORY_TYPE", "User Story")
TASK_TYPE = os.getenv("AZURE_TASK_TYPE", "Task")

class AzureDevOpsClient:
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        settings = settings or {}
        platform = settings.get("project_platform", "azure")

        self.org = settings.get("azure_org") or AZURE_ORGANIZATION
        self.project = settings.get("azure_project") or AZURE_PROJECT
        self.pat = settings.get("azure_pat") or AZURE_PAT
        self.api_version = AZURE_API_VERSION
        
        # Check if we should operate in simulation/mock mode
        # Treat placeholder values as empty
        self.org = self.org if self.org not in ("", "your_org_name") else ""
        self.project = self.project if self.project not in ("", "your_project_name") else ""
        self.pat = self.pat if self.pat not in ("", "your_personal_access_token_here") else ""
        
        self.mock_mode = not (self.org and self.project and self.pat)
        if self.mock_mode:
            print("[AZURE DEVOPS] Integration is not fully configured. Real Azure Boards requests are disabled until organization/project/PAT are saved.")
        else:
            print(f"[AZURE DEVOPS] Initialized client for Org: {self.org}, Project: {self.project}")

    def _ensure_configured(self):
        if self.mock_mode:
            raise RuntimeError(
                "Azure Boards integration is not fully configured. Save organization, project, and PAT in Settings."
            )

    def _get_headers(self, is_patch: bool = False) -> Dict[str, str]:
        pat_encoded = base64.b64encode(f":{self.pat}".encode("utf-8")).decode("utf-8")
        headers = {
            "Authorization": f"Basic {pat_encoded}"
        }
        if is_patch:
            headers["Content-Type"] = "application/json-patch+json"
        else:
            headers["Content-Type"] = "application/json"
        return headers

    async def create_work_item(self, item_type: str, item_data: Dict[str, Any], iteration_path: Optional[str] = None) -> Dict[str, Any]:
        """Creates a work item in Azure Boards using basic auth and json-patch."""
        # Map internal types
        mapped_type = STORY_TYPE
        if item_type == "feature":
            mapped_type = FEATURE_TYPE
        elif item_type == "task":
            mapped_type = TASK_TYPE
        
        self._ensure_configured()

        # Build Patch request
        patch = [
            {"op": "add", "path": "/fields/System.Title", "value": item_data["title"]},
            {"op": "add", "path": "/fields/System.Description", "value": item_data.get("description", "")}
        ]
        
        if item_data.get("story_points") is not None:
            # Different processes use different field paths for story points. 
            # Agile: Microsoft.VSTS.Scheduling.StoryPoints
            # Scrum: Microsoft.VSTS.Scheduling.Effort
            points_field = "/fields/Microsoft.VSTS.Scheduling.StoryPoints"
            if STORY_TYPE == "Product Backlog Item":
                points_field = "/fields/Microsoft.VSTS.Scheduling.Effort"
            patch.append({"op": "add", "path": points_field, "value": int(item_data["story_points"])})
            
        if item_data.get("priority") is not None:
            patch.append({"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority", "value": int(item_data["priority"])})
            
        if item_data.get("tags"):
            tags_str = "; ".join(item_data["tags"])
            patch.append({"op": "add", "path": "/fields/System.Tags", "value": tags_str})
            
        if iteration_path:
            patch.append({"op": "add", "path": "/fields/System.IterationPath", "value": iteration_path})

        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/wit/workitems/${mapped_type}?api-version={self.api_version}"
        
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=patch, headers=self._get_headers(is_patch=True))
            res.raise_for_status()
            return res.json()

    async def get_active_sprints(self) -> List[Dict[str, Any]]:
        """Retrieves list of iteration paths (sprints) for the configured project."""
        if self.mock_mode:
            return []

        # Note: Iterations are managed per Team. We fetch the project iterations list.
        # Azure DevOps has a project-level classification nodes endpoint:
        # GET https://dev.azure.com/{org}/{project}/_apis/wit/classificationnodes/iterations?$depth=2
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/wit/classificationnodes/Iterations?$depth=2&api-version={self.api_version}"
        
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(url, headers=self._get_headers())
                res.raise_for_status()
                data = res.json()
                
                sprints = []
                # Flatten the classification nodes
                def parse_nodes(node, current_path=""):
                    path = f"{current_path}\\{node['name']}" if current_path else node['name']
                    # Leaf/Sprint details
                    if node.get("attributes", {}).get("startDate"):
                        sprints.append({
                            "id": str(node.get("id", node["name"])),
                            "name": node["name"],
                            "path": path,
                            "timeFrame": "current" # placeholder, can estimate based on date
                        })
                    if "children" in node:
                        for child in node["children"]:
                            parse_nodes(child, path)
                            
                parse_nodes(data)
                
                return sprints
        except Exception as e:
            print(f"[AZURE DEVOPS ERROR] Failed to fetch project classification iterations: {str(e)}")
            # Fallback to Team Iterations if project-level fails (requires team name)
            try:
                # Get teams first to find default
                team_url = f"https://dev.azure.com/{self.org}/_apis/projects/{self.project}/teams?api-version=7.1"
                async with httpx.AsyncClient() as client:
                    team_res = await client.get(team_url, headers=self._get_headers())
                    teams = team_res.json().get("value", [])
                    if teams:
                        team_name = teams[0]["name"]
                        iter_url = f"https://dev.azure.com/{self.org}/{self.project}/{team_name}/_apis/work/teamsettings/iterations?api-version=7.1"
                        iter_res = await client.get(iter_url, headers=self._get_headers())
                        val = iter_res.json().get("value", [])
                        return [{
                            "id": it["id"],
                            "name": it["name"],
                            "path": it["path"],
                            "timeFrame": it.get("attributes", {}).get("timeFrame", "current")
                        } for it in val]
            except Exception as ex:
                print(f"[AZURE DEVOPS ERROR] Double fallback failed: {str(ex)}")
            
            return []

    async def get_sprint_work_items(self, iteration_path: str) -> List[Dict[str, Any]]:
        """Queries work items inside a specific iteration path using WIQL."""
        if self.mock_mode:
            return []

        # WIQL API endpoint
        url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/wit/wiql?api-version={self.api_version}"
        
        # WIQL query to search workitems
        wiql_query = {
            "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.IterationPath] = '{iteration_path}'"
        }
        
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=wiql_query, headers=self._get_headers())
            res.raise_for_status()
            data = res.json()
            
            work_items_refs = data.get("workItems", [])
            if not work_items_refs:
                return []
                
            ids = [ref["id"] for ref in work_items_refs]
            
            # Batch fetch work item details
            batch_url = f"https://dev.azure.com/{self.org}/{self.project}/_apis/wit/workitemsbatch?api-version={self.api_version}"
            
            # We select standard fields
            fields = [
                "System.Id",
                "System.Title",
                "System.WorkItemType",
                "System.State",
                "Microsoft.VSTS.Scheduling.StoryPoints",
                "Microsoft.VSTS.Scheduling.Effort"
            ]
            
            batch_payload = {
                "ids": ids,
                "fields": fields
            }
            
            batch_res = await client.post(batch_url, json=batch_payload, headers=self._get_headers())
            batch_res.raise_for_status()
            batch_data = batch_res.json()
            
            results = []
            for item in batch_data.get("value", []):
                fields_data = item.get("fields", {})
                
                # Fetch Points based on process template mapping
                points = fields_data.get("Microsoft.VSTS.Scheduling.StoryPoints")
                if points is None:
                    points = fields_data.get("Microsoft.VSTS.Scheduling.Effort", 0)
                    
                results.append({
                    "id": str(item["id"]),
                    "title": fields_data.get("System.Title", "Untitled"),
                    "type": fields_data.get("System.WorkItemType", STORY_TYPE),
                    "state": fields_data.get("System.State", "New"),
                    "story_points": int(points or 0)
                })
            return results
