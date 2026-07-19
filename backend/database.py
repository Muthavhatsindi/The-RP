import sqlite3
import json
import os
from typing import List, Dict, Any, Optional

DB_FILE = os.path.join(os.path.dirname(__file__), "database.db")

class Database:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create meetings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS meetings (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    summary TEXT,
                    decisions TEXT,
                    risks TEXT,
                    status TEXT NOT NULL DEFAULT 'processed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create items table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY,
                    meeting_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    acceptance_criteria TEXT,
                    story_points INTEGER,
                    priority INTEGER,
                    approved INTEGER DEFAULT 0,
                    tags TEXT,
                    azure_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (meeting_id) REFERENCES meetings (id) ON DELETE CASCADE
                )
            """)
            
            # Create retro_feedback table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS retro_feedback (
                    id TEXT PRIMARY KEY,
                    sprint_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    answers TEXT NOT NULL,
                    sentiment REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create retro_reports table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS retro_reports (
                    id TEXT PRIMARY KEY,
                    sprint_id TEXT UNIQUE NOT NULL,
                    summary TEXT NOT NULL,
                    proposed_items TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()

    # Meetings CRUD
    def create_meeting(self, id: str, title: str, transcript: str, summary: Optional[str] = None, 
                       decisions: Optional[List[str]] = None, risks: Optional[List[str]] = None, status: str = "processed") -> Dict[str, Any]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            dec_json = json.dumps(decisions or [])
            risks_json = json.dumps(risks or [])
            
            cursor.execute(
                "INSERT INTO meetings (id, title, transcript, summary, decisions, risks, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (id, title, transcript, summary, dec_json, risks_json, status)
            )
            conn.commit()
            return self.get_meeting(id)

    def get_meeting(self, id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM meetings WHERE id = ?", (id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            meeting = dict(row)
            meeting["decisions"] = json.loads(meeting["decisions"]) if meeting["decisions"] else []
            meeting["risks"] = json.loads(meeting["risks"]) if meeting["risks"] else []
            return meeting

    def list_meetings(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM meetings ORDER BY created_at DESC")
            rows = cursor.fetchall()
            meetings = []
            for row in rows:
                m = dict(row)
                m["decisions"] = json.loads(m["decisions"]) if m["decisions"] else []
                m["risks"] = json.loads(m["risks"]) if m["risks"] else []
                meetings.append(m)
            return meetings

    def update_meeting_status(self, id: str, status: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE meetings SET status = ? WHERE id = ?", (status, id))
            conn.commit()

    # Items CRUD
    def create_item(self, id: str, meeting_id: str, type: str, title: str, description: str, 
                    acceptance_criteria: List[str], story_points: int, priority: int, 
                    approved: int = 0, tags: List[str] = None, azure_id: Optional[str] = None) -> Dict[str, Any]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            ac_json = json.dumps(acceptance_criteria or [])
            tags_json = json.dumps(tags or [])
            
            cursor.execute(
                """INSERT INTO items (id, meeting_id, type, title, description, acceptance_criteria, story_points, priority, approved, tags, azure_id) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (id, meeting_id, type, title, description, ac_json, story_points, priority, approved, tags_json, azure_id)
            )
            conn.commit()
            return self.get_item(id)

    def get_item(self, id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items WHERE id = ?", (id,))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            item["acceptance_criteria"] = json.loads(item["acceptance_criteria"]) if item["acceptance_criteria"] else []
            item["tags"] = json.loads(item["tags"]) if item["tags"] else []
            return item

    def get_items_by_meeting(self, meeting_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items WHERE meeting_id = ?", (meeting_id,))
            rows = cursor.fetchall()
            items = []
            for row in rows:
                item = dict(row)
                item["acceptance_criteria"] = json.loads(item["acceptance_criteria"]) if item["acceptance_criteria"] else []
                item["tags"] = json.loads(item["tags"]) if item["tags"] else []
                items.append(item)
            return items

    def update_item(self, id: str, title: str, description: str, story_points: int, priority: int, approved: int, tags: List[str]) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            tags_json = json.dumps(tags or [])
            cursor.execute(
                """UPDATE items 
                   SET title = ?, description = ?, story_points = ?, priority = ?, approved = ?, tags = ?
                   WHERE id = ?""",
                (title, description, story_points, priority, approved, tags_json, id)
            )
            conn.commit()
            return self.get_item(id)

    def set_item_azure_id(self, id: str, azure_id: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE items SET azure_id = ? WHERE id = ?", (azure_id, id))
            conn.commit()

    # Retro Feedback & Reports
    def add_retro_feedback(self, id: str, sprint_id: str, user_id: str, answers: Dict[str, Any], sentiment: float):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            answers_json = json.dumps(answers)
            cursor.execute(
                "INSERT INTO retro_feedback (id, sprint_id, user_id, answers, sentiment) VALUES (?, ?, ?, ?, ?)",
                (id, sprint_id, user_id, answers_json, sentiment)
            )
            conn.commit()

    def get_retro_feedback_for_sprint(self, sprint_id: str) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM retro_feedback WHERE sprint_id = ?", (sprint_id,))
            rows = cursor.fetchall()
            feedback_list = []
            for row in rows:
                fb = dict(row)
                fb["answers"] = json.loads(fb["answers"]) if fb["answers"] else {}
                feedback_list.append(fb)
            return feedback_list

    def save_retro_report(self, id: str, sprint_id: str, summary: Dict[str, Any], proposed_items: List[Dict[str, Any]]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            summary_json = json.dumps(summary)
            proposed_items_json = json.dumps(proposed_items)
            cursor.execute(
                """INSERT INTO retro_reports (id, sprint_id, summary, proposed_items) 
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(sprint_id) DO UPDATE SET summary = excluded.summary, proposed_items = excluded.proposed_items""",
                (id, sprint_id, summary_json, proposed_items_json)
            )
            conn.commit()

    def get_retro_report(self, sprint_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM retro_reports WHERE sprint_id = ?", (sprint_id,))
            row = cursor.fetchone()
            if not row:
                return None
            report = dict(row)
            report["summary"] = json.loads(report["summary"]) if report["summary"] else {}
            report["proposed_items"] = json.loads(report["proposed_items"]) if report["proposed_items"] else []
            return report
