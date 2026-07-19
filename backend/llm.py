import json
import re
import httpx
from typing import List, Dict, Any, Optional
from database import Database

# Initialize database connection
db = Database()

def get_settings():
    return db.get_settings()

def get_llm_config():
    settings = get_settings()
    return {
        "provider": settings.get("llm_provider", "ollama").lower(),
        "model": settings.get("llm_model", "llama3"),
        "ollama_base_url": settings.get("ollama_base_url", "http://localhost:11434"),
        "openai_api_key": settings.get("openai_api_key", ""),
        "openai_base_url": settings.get("openai_base_url", "https://api.openai.com/v1"),
        "azure_project": settings.get("azure_project") or settings.get("jira_project_key") or "MockProject"
    }

def clean_json_string(text: str) -> str:
    """Extracts JSON substring or parses loose formatting from the LLM output."""
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match_list = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text, re.IGNORECASE)
    if match_list:
        return match_list.group(1).strip()
    
    text_clean = text.strip()
    first_brace = text_clean.find("{")
    last_brace = text_clean.rfind("}")
    if first_brace != -1 and last_brace != -1:
        return text_clean[first_brace:last_brace+1]
        
    first_bracket = text_clean.find("[")
    last_bracket = text_clean.rfind("]")
    if first_bracket != -1 and last_bracket != -1:
        return text_clean[first_bracket:last_bracket+1]
        
    return text_clean

async def call_llm(system_prompt: str, user_prompt: str, json_format: bool = True) -> str:
    """Calls Ollama or OpenAI based on current configuration settings."""
    config = get_llm_config()
    try:
        print(f"[DEBUG] LLM_PROVIDER: {config['provider']}")
        print(f"[DEBUG] LLM_MODEL: {config['model']}")
        print(f"[DEBUG] OLLAMA_BASE_URL: {config['ollama_base_url']}")
        if config["provider"] == "openai":
            headers = {
                "Authorization": f"Bearer {config['openai_api_key']}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": config["model"] if config["model"] != "llama3" else "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }
            if json_format:
                payload["response_format"] = {"type": "json_object"}
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(f"{config['openai_base_url']}/chat/completions", json=payload, headers=headers)
                res.raise_for_status()
                data = res.json()
                return data["choices"][0]["message"]["content"]
                
        else: # Default/Fallback to Ollama
            payload = {
                "model": config["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "options": {
                    "temperature": 0.2
                }
            }
            if json_format:
                payload["format"] = "json"
                
            print(f"[DEBUG] Ollama payload: {payload}")
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(f"{config['ollama_base_url']}/api/chat", json=payload)
                res.raise_for_status()
                data = res.json()
                print(f"[DEBUG] Ollama response: {data}")
                return data["message"]["content"]
                
    except Exception as e:
        print(f"[LLM ERROR] Provider: {config['provider']}, Error: {str(e)}")
        if json_format:
            return "{}"
        return "Failed to contact LLM provider."

async def summarize_meeting(transcript: str) -> Dict[str, Any]:
    # Mock data for testing if LLM is not available
    mock_summary = {
        "summary": "Sprint planning meeting for Sprint 4 focused on authentication system and deployment pipeline improvements.",
        "key_decisions": [
            "Implement OAuth 2.0 authentication flow",
            "Set up staging deployment pipeline",
            "Prioritize PostgreSQL indexing"
        ],
        "risks": [
            "Potential delays in OAuth integration",
            "Staging environment configuration complexity"
        ]
    }
    
    system_prompt = (
        "You are an AI assistant designed to summarize software engineering team meetings. "
        "Your task is to analyze the provided transcript and produce a JSON response with the following exact structure:\n"
        "{\n"
        '  "summary": "High-level summary of the meeting",\n'
        '  "key_decisions": ["Decision 1", "Decision 2", ...],\n'
        '  "risks": ["Risk 1", "Risk 2", ...]\n'
        "}\n"
        "Ensure the response is valid JSON and only contains the requested structure."
    )
    user_prompt = f"Transcript:\n{transcript}"
    
    try:
        response_text = await call_llm(system_prompt, user_prompt, json_format=True)
        clean = clean_json_string(response_text)
        data = json.loads(clean)
        # Check if we got valid data with required fields
        if data and "summary" in data and "key_decisions" in data and "risks" in data:
            return data
        else:
            print(f"[LLM Warning in summarize_meeting]: Got empty/invalid data, using mock")
            return mock_summary
    except Exception as e:
        print(f"[LLM Error in summarize_meeting]: {str(e)}, using mock data")
        return mock_summary

async def extract_items(transcript: str) -> List[Dict[str, Any]]:
    # Mock data for testing if LLM is not available
    mock_items = [
        {
            "type": "story",
            "title": "User login with OAuth 2.0",
            "description": "As a user, I want to log in using Google or GitHub OAuth so that I don't have to remember another password.",
            "acceptance_criteria": ["OAuth flow completes successfully", "User info is stored in DB", "Redirect to dashboard after login"],
            "tags": ["frontend", "auth", "security"]
        },
        {
            "type": "feature",
            "title": "Staging deployment pipeline",
            "description": "Set up a CI/CD pipeline to deploy the app to a staging environment on every commit to the dev branch.",
            "acceptance_criteria": ["Pipeline triggers on dev commits", "Staging env updates automatically", "Deployment logs are accessible"],
            "tags": ["devops", "ci/cd"]
        },
        {
            "type": "task",
            "title": "Add DB indexes for queries",
            "description": "Add database indexes to optimize the frequently run user and order queries.",
            "acceptance_criteria": ["Query execution time < 100ms", "No regression in write performance"],
            "tags": ["database", "performance"]
        }
    ]
    
    system_prompt = (
        "You are a requirements analyst. "
        "Scan the meeting transcript and identify software backlog items. "
        "Category types are: 'feature' (large standalone capability), 'story' (individual user experience or scenario), "
        "and 'task' (discrete technical work item).\n"
        "Return a JSON response containing an array of items under the key 'items'. Example format:\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "type": "story",\n'
        '      "title": "Short title describing item",\n'
        '      "description": "More detail about what was requested",\n'
        '      "acceptanceCriteria": ["Criteria 1", "Criteria 2"],\n'
        '      "tags": ["frontend", "database"]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Write clear, actionable descriptions. Ensure output is strict valid JSON with camelCase fields."
    )
    user_prompt = f"Transcript:\n{transcript}"
    
    try:
        response_text = await call_llm(system_prompt, user_prompt, json_format=True)
        clean = clean_json_string(response_text)
        data = json.loads(clean)
        extracted = data.get("items", [])
        
        # Check if we got valid items
        if not extracted or len(extracted) == 0:
            print(f"[LLM Warning in extract_items]: Got no items, using mock")
            return mock_items
        
        # Normalize fields: map acceptanceCriteria -> acceptance_criteria
        for item in extracted:
            if "acceptanceCriteria" in item:
                item["acceptance_criteria"] = item["acceptanceCriteria"]
            else:
                item["acceptance_criteria"] = item.get("acceptance_criteria", [])
        return extracted
    except Exception as e:
        print(f"[LLM Error in extract_items]: {str(e)}, using mock data")
        return mock_items

async def score_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return []
        
    config = get_llm_config()
    azure_project = config["azure_project"]
    system_prompt = (
        "You are an agile estimation assistant. "
        "Given a list of backlog items, assign Story Points (estimates of effort: 1, 2, 3, 5, 8, 13) "
        "and Priority (1 to 4, where 1 is highest priority).\n"
        f"Also, propose a 'proposedIterationPath' (default to '{azure_project}\\\\Sprint 1' or another sprint name context like "
        f"'{azure_project}\\\\Sprint 2' if appropriate based on timing mentioned in the meeting).\n"
        "Provide your evaluation as a JSON list matching the input items list but appended with points, priority, and proposedIterationPath. "
        "Example format:\n"
        "{{\n"
        '  "items": [\n'
        "    {{\n"
        '      "type": "story",\n'
        '      "title": "Item title",\n'
        '      "description": "Item description",\n'
        '      "acceptance_criteria": ["criteria"],\n'
        '      "tags": ["tag"],\n'
        '      "story_points": 5,\n'
        '      "priority": 2,\n'
        f'      "proposedIterationPath": "{azure_project}\\\\Sprint 1"\n'
        "    }}\n"
        '  ]\n'
        "}}\n"
        "Ensure output is valid JSON."
    )
    user_prompt = f"Backlog Items:\n{json.dumps(items, indent=2)}"
    response_text = await call_llm(system_prompt, user_prompt, json_format=True)
    try:
        clean = clean_json_string(response_text)
        data = json.loads(clean)
        scored = data.get("items", items)
        
        # Ensure proposedIterationPath is set
        for item in scored:
            item["story_points"] = item.get("story_points", 3)
            item["priority"] = item.get("priority", 3)
            if "proposedIterationPath" not in item:
                item["proposedIterationPath"] = item.get("proposed_iteration_path", f"{azure_project}\\Sprint 1")
        return scored
    except Exception as e:
        print(f"[JSON Parse Error in score_items]: {str(e)}")
        for item in items:
            item["story_points"] = item.get("story_points", 3)
            item["priority"] = item.get("priority", 3)
            item["proposedIterationPath"] = f"{azure_project}\\Sprint 1"
        return items

async def align_company_framework(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return []
        
    config = get_llm_config()
    azure_project = config["azure_project"]
    
    system_prompt = (
        "You are a compliance and formatting expert. "
        "Review each item in the list and ensure it aligns with standard Agile best practices:\n"
        "- For 'story' items: Rephrase the description into a clear user format ('As a... I want to... So that...').\n"
        "- For 'task' and 'feature' items: Ensure title is action-oriented (starts with active verb like Develop, Implement, Refactor etc).\n"
        "Provide the updated list as a JSON response with key 'items'. "
        "Example structure:\n"
        "{{\n"
        '  "items": [\n'
        "    {{\n"
        '      "type": "story",\n'
        '      "title": "Title",\n'
        '      "description": "As a developer, I want to..., so that...",\n'
        '      "acceptance_criteria": [...],\n'
        '      "tags": [...],\n'
        '      "story_points": 3,\n'
        '      "priority": 2,\n'
        f'      "proposedIterationPath": "{azure_project}\\\\Sprint 1"\n'
        "    }}\n"
        "  ]\n"
        "}}\n"
        "Ensure response is valid JSON."
    )
    user_prompt = f"Existing backlogs to align:\n{json.dumps(items, indent=2)}"
    response_text = await call_llm(system_prompt, user_prompt, json_format=True)
    try:
        clean = clean_json_string(response_text)
        data = json.loads(clean)
        return data.get("items", items)
    except Exception as e:
        print(f"[JSON Parse Error in align_company_framework]: {str(e)}")
        return items

async def aggregate_retro(sprint_data: Dict[str, Any], feedback_list: List[Dict[str, Any]], coding_agent_logs: Optional[str] = None) -> Dict[str, Any]:
    # Mock data for testing if LLM is not available
    mock_retro = {
        "summary": "Sprint 4 was mostly successful with some delays in OAuth integration. Team morale is good but there are concerns about deployment pipeline stability.",
        "wentWell": [
            "Completed DB indexing task",
            "Team communication improved",
            "Staging environment setup initiated"
        ],
        "didNotGoWell": [
            "OAuth integration took longer than expected",
            "Deployment pipeline had multiple failures",
            "Some acceptance criteria were unclear"
        ],
        "averageSentiment": 3.8,
        "actionItems": [
            {
                "type": "task",
                "title": "Fix deployment pipeline flakiness",
                "description": "Investigate and fix the intermittent failures in the CI/CD pipeline.",
                "story_points": 3,
                "priority": 1,
                "tags": ["retro-action", "devops"]
            },
            {
                "type": "story",
                "title": "Improve acceptance criteria template",
                "description": "As a product owner, I want a clear acceptance criteria template so that requirements are well-defined.",
                "story_points": 2,
                "priority": 2,
                "tags": ["retro-action", "process"]
            }
        ],
        "codingAgentLogsSummary": coding_agent_logs or "No coding agent logs provided"
    }
    
    system_prompt = (
        "You are an agile consultant running a sprint retrospective. "
        "You will receive data about sprint completion statistics, raw employee sentiment feedback, "
        "and optionally coding agent session logs that show the developer's interaction with AI coding assistants during the sprint.\n"
        "Analyze these datasets and output a JSON response containing standard retro sections:\n"
        "{\n"
        '  "wentWell": ["Success item 1", "Success item 2"],\n'
        '  "didNotGoWell": ["Blocked item 1", "Blocked item 2"],\n'
        '  "summary": "General summary of sprint performance including insights from coding agent logs if provided",\n'
        '  "averageSentiment": 4.0,\n'
        '  "codingAgentLogsSummary": "A summary of insights from the coding agent logs (if provided, otherwise empty string)",\n'
        '  "actionItems": [\n'
        "    {\n"
        '      "type": "task",\n'
        '      "title": "Proposed Action title (starts with verb)",\n'
        '      "description": "Problem context and objective",\n'
        '      "story_points": 2,\n'
        '      "priority": 2,\n'
        '      "tags": ["retro-action", "technical-debt"]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Ensure the response is valid JSON and maps strictly to wentWell, didNotGoWell, averageSentiment, codingAgentLogsSummary, and actionItems."
    )
    
    user_content = {
        "sprint_work_items": sprint_data,
        "team_feedback": feedback_list
    }
    if coding_agent_logs:
        user_content["coding_agent_logs"] = coding_agent_logs
    
    user_prompt = f"Sprint Data and Team Feedbacks:\n{json.dumps(user_content, indent=2)}"
    
    try:
        response_text = await call_llm(system_prompt, user_prompt, json_format=True)
        clean = clean_json_string(response_text)
        data = json.loads(clean)
        
        # Check if we got valid data with required fields
        required_fields = ["summary", "wentWell", "didNotGoWell", "averageSentiment", "actionItems"]
        if data and all(field in data for field in required_fields):
            if "codingAgentLogsSummary" not in data:
                data["codingAgentLogsSummary"] = coding_agent_logs or "No coding agent logs provided"
            return data
        else:
            print(f"[LLM Warning in aggregate_retro]: Got invalid data, using mock")
            return mock_retro
    except Exception as e:
        print(f"[LLM Error in aggregate_retro]: {str(e)}, using mock data")
        return mock_retro
