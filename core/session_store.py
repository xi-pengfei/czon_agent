"""SQLite-backed WebUI conversation history."""
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SessionStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner_updated
                    ON chat_sessions(owner, updated_at DESC);
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL, duration_ms INTEGER,
                    input_tokens INTEGER, output_tokens INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                    ON chat_messages(session_id, id);
                CREATE TABLE IF NOT EXISTS chat_artifacts (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    message_id INTEGER NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    storage_name TEXT NOT NULL,
                    mime TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_artifacts_session_message
                    ON chat_artifacts(session_id, message_id);
                """
            )
            message_columns = {row[1] for row in connection.execute("PRAGMA table_info(chat_messages)")}
            for column in ("duration_ms", "input_tokens", "output_tokens"):
                if column not in message_columns:
                    connection.execute(f"ALTER TABLE chat_messages ADD COLUMN {column} INTEGER")

    def list_sessions(self, owner: str, limit: int = 100) -> list[dict]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """SELECT id, title, created_at, updated_at
                   FROM chat_sessions WHERE owner = ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (owner, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str, owner: str) -> dict | None:
        with self._lock, self._connect() as connection:
            session = connection.execute(
                """SELECT id, title, created_at, updated_at
                   FROM chat_sessions WHERE id = ? AND owner = ?""",
                (session_id, owner),
            ).fetchone()
            if session is None:
                return None
            message_rows = connection.execute(
                """SELECT id, role, content, created_at, duration_ms, input_tokens, output_tokens
                   FROM chat_messages WHERE session_id = ? ORDER BY id""",
                (session_id,),
            ).fetchall()
            artifacts = connection.execute(
                """SELECT id, message_id, name, mime, size, created_at
                   FROM chat_artifacts WHERE session_id = ? ORDER BY created_at, id""",
                (session_id,),
            ).fetchall()
        result = dict(session)
        by_message: dict[int, list[dict]] = {}
        for row in artifacts:
            item = dict(row)
            message_id = item.pop("message_id")
            item["download_url"] = f"/api/artifacts/{item['id']}/download"
            by_message.setdefault(message_id, []).append(item)
        result["messages"] = [
            {**dict(row), "artifacts": by_message.get(row["id"], [])}
            for row in message_rows
        ]
        return result

    def can_access(self, session_id: str, owner: str) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT owner FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return row is None or row["owner"] == owner

    def get_messages(self, session_id: str, owner: str, limit: int) -> list[dict]:
        with self._lock, self._connect() as connection:
            session = connection.execute(
                "SELECT 1 FROM chat_sessions WHERE id = ? AND owner = ?",
                (session_id, owner),
            ).fetchone()
            if session is None:
                return []
            rows = connection.execute(
                """SELECT role, content FROM (
                       SELECT id, role, content FROM chat_messages
                       WHERE session_id = ? ORDER BY id DESC LIMIT ?
                   ) ORDER BY id""",
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def append_exchange(
        self,
        session_id: str,
        owner: str,
        user_content: str,
        assistant_content: str,
        title: str,
        artifacts: list[dict] | None = None,
        metrics: dict | None = None,
    ) -> None:
        timestamp = _now()
        with self._lock, self._connect() as connection:
            existing = connection.execute(
                "SELECT owner FROM chat_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if existing is not None and existing["owner"] != owner:
                raise PermissionError("session owner mismatch")
            connection.execute(
                """INSERT INTO chat_sessions(id, owner, title, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at""",
                (session_id, owner, title, timestamp, timestamp),
            )
            connection.execute(
                """INSERT INTO chat_messages(session_id, role, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, "user", user_content, timestamp),
            )
            metrics = metrics or {}
            assistant = connection.execute(
                """INSERT INTO chat_messages
                   (session_id, role, content, duration_ms, input_tokens, output_tokens, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, "assistant", assistant_content, metrics.get("duration_ms"),
                 metrics.get("input_tokens"), metrics.get("output_tokens"), timestamp),
            )
            for item in artifacts or []:
                connection.execute(
                    """INSERT INTO chat_artifacts
                       (id, session_id, message_id, name, source_path, storage_name, mime, size, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item["id"], session_id, assistant.lastrowid, item["name"], item["source_path"],
                     item["storage_name"], item["mime"], item["size"], item["created_at"]),
                )

    def get_artifact(self, artifact_id: str, owner: str) -> dict | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """SELECT a.id, a.name, a.storage_name, a.mime, a.size
                   FROM chat_artifacts a
                   JOIN chat_sessions s ON s.id = a.session_id
                   WHERE a.id = ? AND s.owner = ?""",
                (artifact_id, owner),
            ).fetchone()
        return dict(row) if row else None

    def find_artifact(self, source_path: str, owner: str) -> dict | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """SELECT a.id, a.name, a.storage_name, a.mime, a.size
                   FROM chat_artifacts a
                   JOIN chat_sessions s ON s.id = a.session_id
                   WHERE a.source_path = ? AND s.owner = ?
                   ORDER BY a.created_at DESC LIMIT 1""",
                (source_path, owner),
            ).fetchone()
        return dict(row) if row else None

    def delete_session(self, session_id: str, owner: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM chat_sessions WHERE id = ? AND owner = ?",
                (session_id, owner),
            )
            return cursor.rowcount > 0
