"""Memória de conversa persistente em SQLite.

Cada 'session_id' é uma linha de conversa independente (ex.: 'pc', 'celular').
Use o mesmo session_id em todos os lugares se quiser memória compartilhada.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any


class Memory:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT    NOT NULL,
                    role       TEXT    NOT NULL,
                    content    TEXT    NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session "
                "ON messages (session_id, id)"
            )
            self._conn.commit()

    def append(self, session_id: str, role: str, content: Any) -> None:
        """Salva uma mensagem. 'content' pode ser texto ou lista de blocos."""
        payload = content if isinstance(content, str) else json.dumps(content)
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, payload),
            )
            self._conn.commit()

    def history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Retorna as últimas mensagens já no formato da API da Anthropic."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()

        messages: list[dict[str, Any]] = []
        for row in reversed(rows):
            content = row["content"]
            try:
                parsed = json.loads(content)
                if isinstance(parsed, (list, dict)):
                    content = parsed
            except (json.JSONDecodeError, TypeError):
                pass
            messages.append({"role": row["role"], "content": content})
        return messages

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM messages WHERE session_id = ?", (session_id,)
            )
            self._conn.commit()
