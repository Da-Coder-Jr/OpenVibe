from __future__ import annotations

import sqlite3
import uuid
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    tool_calls: str | None = None
    tool_call_id: str | None = None

    def to_ollama_dict(self) -> dict[str, Any]:
        d = {"role": self.role, "content": self.content}
        if self.tool_calls:
            try:
                d["tool_calls"] = json.loads(self.tool_calls)
            except json.JSONDecodeError:
                pass
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


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
                    tool_calls TEXT,
                    tool_call_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
                """
            )
            # Migration: check if tool_calls column exists
            cursor = conn.execute("PRAGMA table_info(messages)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "tool_calls" not in columns:
                conn.execute("ALTER TABLE messages ADD COLUMN tool_calls TEXT")
            if "tool_call_id" not in columns:
                conn.execute("ALTER TABLE messages ADD COLUMN tool_call_id TEXT")

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

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None
    ) -> MessageRecord:
        now = self._ts()
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages (session_id, role, content, tool_calls, tool_call_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, role, content, tool_calls_json, tool_call_id, now),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            conn.commit()
            msg_id = int(cursor.lastrowid)
        return MessageRecord(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls_json,
            tool_call_id=tool_call_id,
            created_at=now
        )

    def get_messages(self, session_id: str, limit: int = 50) -> list[MessageRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, role, content, tool_calls, tool_call_id, created_at
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
