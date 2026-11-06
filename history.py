"""
SQLite Database Operations for Debugging History.
Persists session summaries, code hashes, bug categories, test outcomes,
and repair diffs securely without storing sensitive API keys or credentials.
"""

import sqlite3
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from config import Config


class HistoryDatabase:
    """Manages SQLite storage and retrieval of debugging sessions."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _get_connection(self):
        """Context manager that guarantees closing the SQLite connection upon exit."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        """Creates tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS debugging_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_uuid TEXT UNIQUE NOT NULL,
                    timestamp TEXT NOT NULL,
                    bug_category TEXT NOT NULL,
                    original_code_hash TEXT NOT NULL,
                    repair_status TEXT NOT NULL,
                    is_verified INTEGER NOT NULL DEFAULT 0,
                    iterations_used INTEGER NOT NULL DEFAULT 1,
                    execution_time_ms REAL NOT NULL DEFAULT 0.0,
                    summary TEXT,
                    tests_passed INTEGER DEFAULT 0,
                    tests_total INTEGER DEFAULT 0,
                    proposed_diff TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_category ON debugging_sessions(bug_category);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_status ON debugging_sessions(repair_status);
            """)
            conn.commit()

    @staticmethod
    def compute_code_hash(code: str) -> str:
        """Compute SHA-256 fingerprint of code to identify duplicates without exposing secrets."""
        return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]

    def save_session(
        self,
        bug_category: str,
        original_code: str,
        repair_status: str,
        is_verified: bool,
        iterations_used: int,
        execution_time_ms: float,
        summary: str,
        tests_passed: int = 0,
        tests_total: int = 0,
        proposed_diff: str = ""
    ) -> int:
        """Saves a completed debugging session record."""
        code_hash = self.compute_code_hash(original_code)
        session_uuid = str(uuid.uuid4())
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO debugging_sessions (
                    session_uuid, timestamp, bug_category, original_code_hash,
                    repair_status, is_verified, iterations_used, execution_time_ms,
                    summary, tests_passed, tests_total, proposed_diff
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_uuid,
                ts,
                bug_category,
                code_hash,
                repair_status,
                1 if is_verified else 0,
                iterations_used,
                execution_time_ms,
                summary,
                tests_passed,
                tests_total,
                proposed_diff
            ))
            conn.commit()
            return cursor.lastrowid or 0

    def get_recent_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch the most recent debugging sessions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, session_uuid, timestamp, bug_category, original_code_hash,
                       repair_status, is_verified, iterations_used, execution_time_ms,
                       summary, tests_passed, tests_total, proposed_diff, created_at
                FROM debugging_sessions
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_session_by_id(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a specific session record by primary key."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, session_uuid, timestamp, bug_category, original_code_hash,
                       repair_status, is_verified, iterations_used, execution_time_ms,
                       summary, tests_passed, tests_total, proposed_diff, created_at
                FROM debugging_sessions
                WHERE id = ?
            """, (session_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def search_sessions(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search debugging history by category or repair status."""
        query = "SELECT * FROM debugging_sessions WHERE 1=1"
        params: List[Any] = []

        if category and category != "All":
            query += " AND bug_category = ?"
            params.append(category)
        if status and status != "All":
            query += " AND repair_status = ?"
            params.append(status)

        query += " ORDER BY id DESC LIMIT 50"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            return [dict(r) for r in cursor.fetchall()]

    def get_statistics(self) -> Dict[str, Any]:
        """Compute aggregate metrics across all historical runs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM debugging_sessions")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM debugging_sessions WHERE is_verified = 1")
            verified = cursor.fetchone()[0]

            cursor.execute("SELECT bug_category, COUNT(*) as count FROM debugging_sessions GROUP BY bug_category")
            category_counts = {row["bug_category"]: row["count"] for row in cursor.fetchall()}

            success_rate = round((verified / total * 100), 1) if total > 0 else 0.0

            return {
                "total_sessions": total,
                "verified_repairs": verified,
                "success_rate_percent": success_rate,
                "category_breakdown": category_counts
            }

    def clear_history(self) -> int:
        """Clear all historical debugging records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM debugging_sessions")
            conn.commit()
            return cursor.rowcount
