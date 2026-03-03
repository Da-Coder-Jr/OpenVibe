from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class SessionRecord:
    id: str
    title: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class MessageRecord:
    id: int
    session_id: str
    role: str
    content: str
    created_at: str


class Vault:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
                """
            )
            conn.commit()

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_session(self, title: str) -> SessionRecord:
        session_id = str(uuid.uuid4())
        now = self._ts()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
            conn.commit()
        return SessionRecord(id=session_id, title=title, created_at=now, updated_at=now)

    def list_sessions(self) -> list[SessionRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
        return [SessionRecord(**dict(row)) for row in rows]

    def add_message(self, session_id: str, role: str, content: str) -> MessageRecord:
        now = self._ts()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, now),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            conn.commit()
            msg_id = int(cursor.lastrowid)
        return MessageRecord(id=msg_id, session_id=session_id, role=role, content=content, created_at=now)

    def get_messages(self, session_id: str, limit: int = 50) -> list[MessageRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [MessageRecord(**dict(row)) for row in reversed(rows)]

    def resume_session(self, session_id: str) -> tuple[SessionRecord, list[MessageRecord]]:
        with self._connect() as conn:
            session_row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if session_row is None:
            raise ValueError(f"Session '{session_id}' does not exist")
        session = SessionRecord(**dict(session_row))
        return session, self.get_messages(session_id)
