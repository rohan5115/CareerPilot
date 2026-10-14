"""Small SQLite persistence layer with per-request connections."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _connect(database_path: str | None = None):
    path = database_path or os.getenv("DATABASE_PATH", "instance/jobs.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_tables(database_path: str | None = None):
    with _connect(database_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            role TEXT NOT NULL,
            score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
            status TEXT NOT NULL DEFAULT 'Applied',
            date_applied TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS workspaces (
            workspace_id TEXT PRIMARY KEY,
            data TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""")


def get_workspace(database_path: str, workspace_id: str) -> dict:
    with _connect(database_path) as conn:
        row = conn.execute("SELECT data FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone()
    defaults = {"resume_text": "", "skills": [], "resume_name": "", "cover_letter": "",
                "tailored_resume": "", "suggestions": "", "interview_questions": "", "ai_package": ""}
    if row:
        try:
            defaults.update(json.loads(row["data"]))
        except (TypeError, json.JSONDecodeError):
            pass
    return defaults


def save_workspace(database_path: str, workspace_id: str, data: dict):
    with _connect(database_path) as conn:
        conn.execute("""INSERT INTO workspaces(workspace_id, data, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(workspace_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at""",
                     (workspace_id, json.dumps(data, ensure_ascii=False)))


def save_application(database_path: str, company: str, role: str, score: int):
    with _connect(database_path) as conn:
        conn.execute("INSERT INTO applications(company, role, score, status, date_applied) VALUES (?, ?, ?, 'Applied', datetime('now'))",
                     (company, role, score))


def get_applications(database_path: str | None = None):
    with _connect(database_path) as conn:
        rows = conn.execute("SELECT id, company, role, score, status, date_applied FROM applications ORDER BY id DESC").fetchall()
    return [tuple(row) for row in rows]


def get_total_applications(database_path: str | None = None):
    with _connect(database_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM applications").fetchone()[0]


def get_average_score(database_path: str | None = None):
    with _connect(database_path) as conn:
        value = conn.execute("SELECT AVG(score) FROM applications").fetchone()[0]
    return round(value or 0)


def get_highest_score(database_path: str | None = None):
    with _connect(database_path) as conn:
        return conn.execute("SELECT COALESCE(MAX(score), 0) FROM applications").fetchone()[0]


def get_company_count(database_path: str | None = None):
    with _connect(database_path) as conn:
        return conn.execute("SELECT COUNT(DISTINCT company) FROM applications").fetchone()[0]
