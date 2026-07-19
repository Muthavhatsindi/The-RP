import os
import json
import re
import httpx
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "llama3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

def clean_json_string(text: str) -> str:
    """Extracts JSON substring or parses loose formatting from the LLM output."""
    # Find JSON blocks labeled with markdown
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match_list = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text, re.IGNORECASE)
    if match_list:
        return match_list.group(1).strip()
    
    # Otherwise try finding the outer-most { } or [ ]
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
    try:
        if LLM_PROVIDER == "openai":
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": LLM_MODEL if LLM_MODEL != "llama3" else "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }
            if json_format:
                payload["response_format"] = {"type": "json_object"}
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(f"{OPENAI_BASE_URL}/chat/completions", json=payload, headers=headers)
                res.raise_for_status()
                data = res.json()
                return data["choices"][0]["message"]["content"]
                
        else: # Default/Fallback to Ollama
            payload = {
                "model": LLM_MODEL,
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
                
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                res.raise_for_status()
                data = res.json()
                return data["message"]["content"]
                
    except Exception as e:
        print(f"[LLM ERROR] Provider: {LLM_PROVIDER}, Error: {str(e)}")
        # Provide a safe dummy structured response if LLM isn't reachable to keep flow running smoothly
        if json_format:
            return "{}"
        return "Failed to contact LLM provider."

async def summarize_meeting(transcript: str) -> Dict[str, Any]:
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
    
    response_text = await call_llm(system_prompt, user_prompt, json_format=True)
    try:
        clean = clean_json_string(response_text)
        return json.loads(clean)
    except Exception as e:
        print(f"[JSON Parse Error in summarize_meeting]: {str(e)}")
        return {
            "summary": "Meeting transcript processed. Failed to generate detailed LLM summary.",
            "key_decisions": [],
            "risks": []
        }

async def extract_items(transcript: str) -> List[Dict[str, Any]]:
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
        '      "acceptance_criteria": ["Criteria 1", "Criteria 2"],\n'
        '      "tags": ["frontend", "database"]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Write clear, actionable descriptions. Ensure output is strict valid JSON."
    )
    user_prompt = f"Transcript:\n{transcript}"
    response_text = await call_llm(system_prompt, user_prompt, json_format=True)
    try:
        clean = clean_json_string(response_text)
        data = json.loads(clean)
        return data.get("items", [])
    except Exception as e:
        print(f"[JSON Parse Error in extract_items]: {str(e)}")
        return []

async def score_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return []
        
    system_prompt = (
        "You are an agile coach and estimation assistant. "
        "Given a list of backlog items, assign Story Points (estimates of effort) and Priority (1 to 4, where 1 is highest priority).\n"
        "Use standard Agile sizes for Story Points: 1, 2, 3, 5, 8, 13.\n"
        "Provide your evaluation as a JSON list matching the input items list but appended with 'story_points' and 'priority' fields. "
        "Example format:\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "type": "story",\n'
        '      "title": "Item title",\n'
        '      "description": "Item description",\n'
        '      "acceptance_criteria": ["criteria"],\n'
        '      "tags": ["tag"],\n'
        '      "story_points": 5,\n'
        '      "priority": 2\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Ensure the output strictly mirrors the input list schema and is valid JSON."
    )
    user_prompt = f"Backlog Items:\n{json.dumps(items, indent=2)}"
    response_text = await call_llm(system_prompt, user_prompt, json_format=True)
    try:
        clean = clean_json_string(response_text)
        data = json.loads(clean)
        return data.get("items", items)
    except Exception as e:
        print(f"[JSON Parse Error in score_items]: {str(e)}")
        # If scoring fails, inject default values
        for item in items:
            item["story_points"] = item.get("story_points", 3)
            item["priority"] = item.get("priority", 3)
        return items

async def align_company_framework(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not items:
        return []
        
    system_prompt = (
        "You are an compliance and formatting expert. "
        "Review each item in the list and ensure it aligns with standard Agile best practices:\n"
        "- For 'story' items: Rephrase the description into a clear user format ('As a... I want to... So that...').\n"
        "- For 'task' and 'feature' items: Ensure title is action-oriented (starts with active verb like Develop, Implement, Refactor etc).\n"
        "Provide the updated list as a JSON response with key 'items'. "
        "Example structure:\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "type": "story",\n'
        '      "title": "Title",\n'
        '      "description": "As a developer, I want to..., so that...",\n'
        '      "acceptance_criteria": [...],\n'
        '      "tags": [...],\n'
        '      "story_points": 3,\n'
        '      "priority": 2\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Retain all existing properties from input, modifying only descriptions/titles where appropriate."
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

async def aggregate_retro(sprint_data: Dict[str, Any], feedback_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    system_prompt = (
        "You are an agile consultant running a sprint retrospective. "
        "You will receive data about sprint completion statistics along with raw employee sentiment feedback.\n"
        "Analyze these datasets and output a JSON response containing standard retro sections:\n"
        "{\n"
        '  "summary": "General summary of sprint execution and environment details",\n'
        '  "what_went_well": ["Success item 1", "Success item 2"],\n'
        '  "what_did_not_go_well": ["Friction item 1", "Friction item 2"],\n'
        '  "average_sentiment": 4.2,\n'
        '  "proposed_backlog_actions": [\n'
        "    {\n"
        '      "type": "task",\n'
        '      "title": "Proposed Action title (starts with verb)",\n'
        '      "description": "Problem context and objective of this retro action item",\n'
        '      "story_points": 2,\n'
        '      "priority": 2,\n'
        '      "tags": ["retro-action", "technical-debt"]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Keep it highly analytical, highlighting blockers. Ensure response is valid JSON."
    )
    
    user_content = {
        "sprint_work_items": sprint_data,
        "team_feedback": feedback_list
    }
    
    user_prompt = f"Sprint Data and Team Feedbacks:\n{json.dumps(user_content, indent=2)}"
    response_text = await call_llm(system_prompt, user_prompt, json_format=True)
    try:
        clean = clean_json_string(response_text)
        return json.loads(clean)
    except Exception as e:
        print(f"[JSON Parse Error in aggregate_retro]: {str(e)}")
        return {
            "summary": "Sprint Retro aggregated. Failed to generate detailed LLM report.",
            "what_went_well": [],
            "what_did_not_go_well": [],
            "average_sentiment": 3.0,
            "proposed_backlog_actions": []
        }
