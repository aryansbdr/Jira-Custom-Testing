import sqlite3
import os
from shared.config import settings


def get_db_connection():
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Initializes database tables.
    """
    conn = get_db_connection()
    cursor = conn.cursor()


    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historical_issues (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_key        TEXT UNIQUE,         -- Jira ticket key, e.g. "BMFP-21969"
            issue_type       TEXT,                -- "Story", "Task", "Bug", "Architecture", "Documentation"
            issue_title      TEXT,
            story_points     REAL,
            issue_description TEXT,
            embedding        TEXT                 -- JSON serialized list of floats for RAG similarity search
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historical_subtasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            issue_id    INTEGER,                  -- FK to historical_issues.id
            title       TEXT,
            role        TEXT,                     -- "frontend", "backend", etc.
            story_points REAL,
            FOREIGN KEY (issue_id) REFERENCES historical_issues(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp        DATETIME DEFAULT CURRENT_TIMESTAMP,
            epic_key         TEXT,
            parent_key       TEXT,
            total_story_points REAL,
            subtasks_count   INTEGER,
            assignee_names   TEXT
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys

    # Auto-append src folder to system path for direct execution
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    print("Memulai inisialisasi database SQLite...")
    init_db()
    print("Database berhasil diinisialisasi.")
