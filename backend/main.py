import os
import uuid
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from database import Database
from llm import summarize_meeting, extract_items, score_items, align_company_framework, aggregate_retro
from azure_devops import AzureDevOpsClient

load_dotenv()

app = FastAPI(title="Meeting-to-Backlog & Retro Intelligence API")

# Add CORS Middleware to enable communication with local React app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database()
az_client = AzureDevOpsClient()

# Schemas
class MeetingCreate(BaseModel):
    title: str = Field(..., alias="meetingTitle")
    transcript: str

class ItemUpdate(BaseModel):
    id: str
    title: str
    description: str
    story_points: int
    priority: int
    approved: bool
    tags: List[str]

class ItemUpdateList(BaseModel):
    items: List[ItemUpdate]

class PushToAzureRequest(BaseModel):
    iteration_path: Optional[str] = None

class RetroFeedbackSubmit(BaseModel):
    user_id: str
    answers: Dict[str, Any]
    sentiment: float

@app.get("/api/health")
def health_check():
    return {"status": "ok", "mock_mode": az_client.mock_mode}

# Meetings & Backlog Generation Routes
@app.get("/api/meetings")
def list_meetings():
    try:
        return db.list_meetings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/meetings")
async def create_meeting(payload: MeetingCreate):
    meeting_id = str(uuid.uuid4())
    title = payload.title
    transcript = payload.transcript
    
    # 1. Summarization
    summary_data = await summarize_meeting(transcript)
    summary = summary_data.get("summary", "")
    decisions = summary_data.get("key_decisions", [])
    risks = summary_data.get("risks", [])
    
    # Save base meeting
    db.create_meeting(
        id=meeting_id,
        title=title,
        transcript=transcript,
        summary=summary,
        decisions=decisions,
        risks=risks,
        status="processed"
    )
    
    # 2. Extract Items
    raw_backlog = await extract_items(transcript)
    
    # 3. Score Items
    scored_backlog = await score_items(raw_backlog)
    
    # 4. Framework alignment
    final_backlog = await align_company_framework(scored_backlog)
    
    # Store items
    for item in final_backlog:
        db.create_item(
            id=str(uuid.uuid4()),
            meeting_id=meeting_id,
            type=item.get("type", "story"),
            title=item.get("title", "Untitled Work Item"),
            description=item.get("description", ""),
            acceptance_criteria=item.get("acceptance_criteria", []),
            story_points=int(item.get("story_points", 3)),
            priority=int(item.get("priority", 3)),
            approved=0,  # Starts as unapproved
            tags=item.get("tags", []),
            azure_id=None
        )
        
    return {
        "id": meeting_id,
        "title": title,
        "summary": summary,
        "decisions": decisions,
        "risks": risks,
        "items": db.get_items_by_meeting(meeting_id)
    }

@app.get("/api/meetings/{meeting_id}")
def get_meeting(meeting_id: str):
    meeting = db.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
        
    items = db.get_items_by_meeting(meeting_id)
    meeting["items"] = items
    return meeting

@app.put("/api/meetings/{meeting_id}/items")
def update_meeting_items(meeting_id: str, payload: ItemUpdateList):
    meeting = db.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
        
    results = []
    for item in payload.items:
        # DB operates with 0/1 for approved
        approved_int = 1 if item.approved else 0
        updated = db.update_item(
            id=item.id,
            title=item.title,
            description=item.description,
            story_points=item.story_points,
            priority=item.priority,
            approved=approved_int,
            tags=item.tags
        )
        if updated:
            results.append(updated)
            
    # Check if there are approved items still waiting to be pushed
    items = db.get_items_by_meeting(meeting_id)
    any_approved = any(i["approved"] == 1 for i in items)
    any_unpushed_approved = any(i["approved"] == 1 and not i["azure_id"] for i in items)
    
    if any_unpushed_approved:
        db.update_meeting_status(meeting_id, "pending_push")
    elif any_approved and not any_unpushed_approved:
        db.update_meeting_status(meeting_id, "pushed")
    else:
        db.update_meeting_status(meeting_id, "processed")
        
    return {"status": "ok", "items": results}

@app.post("/api/meetings/{meeting_id}/push-to-azure")
async def push_to_azure(meeting_id: str, payload: PushToAzureRequest):
    meeting = db.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
        
    items = db.get_items_by_meeting(meeting_id)
    # Find active items that are approved but not yet pushed
    targets = [i for i in items if i["approved"] == 1 and not i["azure_id"]]
    
    if not targets:
        return {"message": "No approved, un-pushed items found.", "pushed_count": 0, "results": []}
        
    pushed_results = []
    for item in targets:
        try:
            # Prepare data
            item_data = {
                "title": item["title"],
                "description": item["description"],
                "story_points": item["story_points"],
                "priority": item["priority"],
                "tags": item["tags"]
            }
            
            # Send to Azure DevOps
            res = await az_client.create_work_item(
                item_type=item["type"],
                item_data=item_data,
                iteration_path=payload.iteration_path
            )
            
            azure_id = str(res.get("id"))
            db.set_item_azure_id(item["id"], azure_id)
            pushed_results.append({"item_id": item["id"], "azure_id": azure_id})
        except Exception as e:
            print(f"[PUSH ERROR] Failed to push item {item['id']} to Azure: {str(e)}")
            pushed_results.append({"item_id": item["id"], "error": str(e)})

    # Recalculate status
    updated_items = db.get_items_by_meeting(meeting_id)
    any_unpushed_approved = any(i["approved"] == 1 and not i["azure_id"] for i in updated_items)
    
    if any_unpushed_approved:
        db.update_meeting_status(meeting_id, "pending_push")
    else:
        db.update_meeting_status(meeting_id, "pushed")
        
    return {
        "message": "Pushed approved items to Azure DevOps Boards",
        "pushed_count": len([r for r in pushed_results if "azure_id" in r]),
        "results": pushed_results
    }

# Azure DevOps Integration / Queries
@app.get("/api/sprints")
async def get_sprints():
    try:
        sprints = await az_client.get_active_sprints()
        return sprints
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sprints/{sprint_id}/workitems")
async def get_sprint_work_items(sprint_id: str, path: str):
    try:
        # Fetch actual items using the path
        items = await az_client.get_sprint_work_items(iteration_path=path)
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Retro intelligence Flow Routes
@app.post("/api/retro/{sprint_id}/feedback")
def submit_retro_feedback(sprint_id: str, payload: RetroFeedbackSubmit):
    try:
        feedback_id = str(uuid.uuid4())
        db.add_retro_feedback(
            id=feedback_id,
            sprint_id=sprint_id,
            user_id=payload.user_id,
            answers=payload.answers,
            sentiment=payload.sentiment
        )
        return {"status": "ok", "feedback_id": feedback_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/retro/{sprint_id}/feedback")
def get_retro_feedback(sprint_id: str):
    try:
        return db.get_retro_feedback_for_sprint(sprint_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/retro/{sprint_id}/aggregate")
async def aggregate_retro_report(sprint_id: str, path: str):
    try:
        # Fetch current items in that sprint from Azure
        sprint_items = await az_client.get_sprint_work_items(iteration_path=path)
        
        # Load local comments/survey entries
        feedback_list = db.get_retro_feedback_for_sprint(sprint_id)
        
        # Execute LlM synthesis
        report = await aggregate_retro(sprint_items, feedback_list)
        
        # Process and store report
        db.save_retro_report(
            id=str(uuid.uuid4()),
            sprint_id=sprint_id,
            summary=report,
            proposed_items=report.get("proposed_backlog_actions", [])
        )
        
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/retro/{sprint_id}/report")
def get_retro_report(sprint_id: str):
    report = db.get_retro_report(sprint_id)
    if not report:
        raise HTTPException(status_code=404, detail="Retro report not generated yet for this sprint.")
    return report

@app.post("/api/retro/{sprint_id}/push-actions-to-azure")
async def push_retro_actions(sprint_id: str, payload: PushToAzureRequest):
    report = db.get_retro_report(sprint_id)
    if not report:
        raise HTTPException(status_code=404, detail="No retro report found.")
        
    actions = report.get("proposed_items", [])
    if not actions:
        return {"message": "No actions to push.", "pushed_count": 0}
        
    pushed_results = []
    for action in actions:
        try:
            # Assign standard tags to mark them as retro outcomes
            item_data = {
                "title": action["title"],
                "description": action["description"],
                "story_points": action.get("story_points", 2),
                "priority": action.get("priority", 2),
                "tags": action.get("tags", []) + ["retro-action"]
            }
            res = await az_client.create_work_item(
                item_type=action.get("type", "task"),
                item_data=item_data,
                iteration_path=payload.iteration_path
            )
            pushed_results.append(str(res.get("id")))
        except Exception as e:
            print(f"[PUSH ERROR] Failed to push retro action: {str(e)}")
            
    return {
        "message": f"Successfully pushed retro actions to Azure DevOps",
        "pushed_count": len(pushed_results),
        "ids": pushed_results
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
