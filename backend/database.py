import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
from dotenv import load_dotenv

load_dotenv()

# Determine database file path
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(DB_DIR, "database_v3.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DB_FILE}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ORM Declarations
class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(String, primary_key=True)
    project_key = Column(String, nullable=False)
    title = Column(String, nullable=False)
    transcript = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    decisions = Column(JSON, nullable=True)  # List of strings
    risks = Column(JSON, nullable=True)      # List of strings
    status = Column(String, default="processed", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    items = relationship("BacklogItem", back_populates="meeting", cascade="all, delete-orphan")

class BacklogItem(Base):
    __tablename__ = "items"

    id = Column(String, primary_key=True)
    meeting_id = Column(String, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # feature, story, task
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    acceptance_criteria = Column(JSON, nullable=True)  # List of strings
    story_points = Column(Integer, default=3, nullable=False)
    priority = Column(Integer, default=3, nullable=False)
    approved = Column(Boolean, default=False, nullable=False)
    tags = Column(JSON, nullable=True)  # List of strings
    azure_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    meeting = relationship("Meeting", back_populates="items")

class RetroFeedback(Base):
    __tablename__ = "retro_feedback"

    id = Column(String, primary_key=True)
    sprint_id = Column(String, nullable=False)  # Iteration path
    user_id = Column(String, nullable=False)
    answers = Column(JSON, nullable=False)      # Dictionary
    sentiment = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

class RetroReport(Base):
    __tablename__ = "retro_reports"

    id = Column(String, primary_key=True)
    sprint_id = Column(String, unique=True, nullable=False)  # Iteration path
    summary = Column(Text, nullable=False)
    went_well = Column(JSON, nullable=False)         # List of strings
    did_not_go_well = Column(JSON, nullable=False)   # List of strings
    action_items = Column(JSON, nullable=False)      # List of dicts representing proposed tasks
    average_sentiment = Column(Float, default=3.0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# Database Manager Helper Class
class Database:
    def __init__(self):
        self.init_db()

    def init_db(self):
        Base.metadata.create_all(bind=engine)

    def get_session(self):
        return SessionLocal()

    # Meetings Table Operations
    def create_meeting(self, id: str, project_key: str, title: str, transcript: str, 
                       summary: Optional[str] = None, decisions: Optional[List[str]] = None, 
                       risks: Optional[List[str]] = None, status: str = "processed") -> Dict[str, Any]:
        with self.get_session() as session:
            db_meeting = Meeting(
                id=id,
                project_key=project_key,
                title=title,
                transcript=transcript,
                summary=summary,
                decisions=decisions or [],
                risks=risks or [],
                status=status
            )
            session.add(db_meeting)
            session.commit()
            session.refresh(db_meeting)
            return self._to_meeting_dict(db_meeting)

    def get_meeting(self, meeting_id: str) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            meeting = session.query(Meeting).filter(Meeting.id == meeting_id).first()
            if meeting:
                return self._to_meeting_dict(meeting)
            return None

    def list_meetings(self) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            meetings = session.query(Meeting).order_by(Meeting.created_at.desc()).all()
            return [self._to_meeting_dict(m) for m in meetings]

    def update_meeting_status(self, meeting_id: str, status: str):
        with self.get_session() as session:
            session.query(Meeting).filter(Meeting.id == meeting_id).update({"status": status})
            session.commit()

    # Backlog Items Operations
    def create_item(self, id: str, meeting_id: str, type: str, title: str, description: str, 
                    acceptance_criteria: List[str], story_points: int, priority: int, 
                    approved: bool = False, tags: Optional[List[str]] = None, 
                    azure_id: Optional[str] = None) -> Dict[str, Any]:
        with self.get_session() as session:
            db_item = BacklogItem(
                id=id,
                meeting_id=meeting_id,
                type=type,
                title=title,
                description=description,
                acceptance_criteria=acceptance_criteria or [],
                story_points=story_points,
                priority=priority,
                approved=approved,
                tags=tags or [],
                azure_id=azure_id
            )
            session.add(db_item)
            session.commit()
            session.refresh(db_item)
            return self._to_item_dict(db_item)

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            item = session.query(BacklogItem).filter(BacklogItem.id == item_id).first()
            if item:
                return self._to_item_dict(item)
            return None

    def get_items_by_meeting(self, meeting_id: str) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            items = session.query(BacklogItem).filter(BacklogItem.meeting_id == meeting_id).all()
            return [self._to_item_dict(i) for i in items]

    def update_item(self, id: str, title: str, description: str, story_points: int, 
                    priority: int, approved: bool, tags: List[str]) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            session.query(BacklogItem).filter(BacklogItem.id == id).update({
                "title": title,
                "description": description,
                "story_points": story_points,
                "priority": priority,
                "approved": approved,
                "tags": tags
            })
            session.commit()
            return self.get_item(id)

    def set_item_azure_id(self, id: str, azure_id: str):
        with self.get_session() as session:
            session.query(BacklogItem).filter(BacklogItem.id == id).update({"azure_id": azure_id})
            session.commit()

    # Retro Feedback Operations
    def add_retro_feedback(self, id: str, sprint_id: str, user_id: str, answers: Dict[str, Any], sentiment: float):
        with self.get_session() as session:
            db_feedback = RetroFeedback(
                id=id,
                sprint_id=sprint_id,
                user_id=user_id,
                answers=answers,
                sentiment=sentiment
            )
            session.add(db_feedback)
            session.commit()

    def get_retro_feedback_for_sprint(self, sprint_id: str) -> List[Dict[str, Any]]:
        with self.get_session() as session:
            feedback_objs = session.query(RetroFeedback).filter(RetroFeedback.sprint_id == sprint_id).all()
            return [self._to_feedback_dict(fb) for fb in feedback_objs]

    # Retro Report Operations
    def save_retro_report(self, id: str, sprint_id: str, summary: str, went_well: List[str], 
                          did_not_go_well: List[str], action_items: List[Dict[str, Any]], 
                          average_sentiment: float):
        with self.get_session() as session:
            # Upsert behavior matching SQLite constraint
            report = session.query(RetroReport).filter(RetroReport.sprint_id == sprint_id).first()
            if report:
                report.summary = summary
                report.went_well = went_well
                report.did_not_go_well = did_not_go_well
                report.action_items = action_items
                report.average_sentiment = average_sentiment
            else:
                report = RetroReport(
                    id=id,
                    sprint_id=sprint_id,
                    summary=summary,
                    went_well=went_well,
                    did_not_go_well=did_not_go_well,
                    action_items=action_items,
                    average_sentiment=average_sentiment
                )
                session.add(report)
            session.commit()

    def get_retro_report(self, sprint_id: str) -> Optional[Dict[str, Any]]:
        with self.get_session() as session:
            report = session.query(RetroReport).filter(RetroReport.sprint_id == sprint_id).first()
            if report:
                return self._to_report_dict(report)
            return None

    # Conversion Helpers
    def _to_meeting_dict(self, meeting: Meeting) -> Dict[str, Any]:
        return {
            "id": meeting.id,
            "project_key": meeting.project_key,
            "title": meeting.title,
            "transcript": meeting.transcript,
            "summary": meeting.summary,
            "decisions": meeting.decisions if isinstance(meeting.decisions, list) else json.loads(meeting.decisions or "[]"),
            "risks": meeting.risks if isinstance(meeting.risks, list) else json.loads(meeting.risks or "[]"),
            "status": meeting.status,
            "created_at": meeting.created_at.isoformat() if meeting.created_at else None
        }

    def _to_item_dict(self, item: BacklogItem) -> Dict[str, Any]:
        return {
            "id": item.id,
            "meeting_id": item.meeting_id,
            "type": item.type,
            "title": item.title,
            "description": item.description,
            "acceptance_criteria": item.acceptance_criteria if isinstance(item.acceptance_criteria, list) else json.loads(item.acceptance_criteria or "[]"),
            "story_points": item.story_points,
            "priority": item.priority,
            "approved": 1 if item.approved else 0,
            "tags": item.tags if isinstance(item.tags, list) else json.loads(item.tags or "[]"),
            "azure_id": item.azure_id,
            "created_at": item.created_at.isoformat() if item.created_at else None
        }

    def _to_feedback_dict(self, fb: RetroFeedback) -> Dict[str, Any]:
        return {
            "id": fb.id,
            "sprint_id": fb.sprint_id,
            "user_id": fb.user_id,
            "answers": fb.answers,
            "sentiment": fb.sentiment,
            "created_at": fb.created_at.isoformat() if fb.created_at else None
        }

    def _to_report_dict(self, r: RetroReport) -> Dict[str, Any]:
        return {
            "id": r.id,
            "sprint_id": r.sprint_id,
            "summary": r.summary,
            "what_went_well": r.went_well if isinstance(r.went_well, list) else json.loads(r.went_well or "[]"),
            "what_did_not_go_well": r.did_not_go_well if isinstance(r.did_not_go_well, list) else json.loads(r.did_not_go_well or "[]"),
            "average_sentiment": r.average_sentiment,
            "proposed_backlog_actions": r.action_items if isinstance(r.action_items, list) else json.loads(r.action_items or "[]"),
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
