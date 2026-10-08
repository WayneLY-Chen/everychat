"""SQLite storage with FTS5 full-text search.

Tables:
  conversations  one row per chat or session, unique on (source, external_id)
  messages       user and assistant turns, in order
  messages_fts   trigram FTS5 index over message content (substring search, works for CJK)
  files          mtime and size of imported files so re-syncs can skip unchanged ones
  embeddings     optional vectors for semantic search (see semantic.py)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .models import Conversation

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY,
    source      TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title       TEXT NOT NULL,
    created_at  TEXT,
    updated_at  TEXT,
    project     TEXT,
    UNIQUE (source, external_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    created_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, position);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='id',
    tokenize='trigram'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES ('delete', old.id, old.content);
END;

CREATE TABLE IF NOT EXISTS files (
    path  TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    size  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS embeddings (
    message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
    model      TEXT NOT NULL,
    vector     BLOB NOT NULL
);
"""

# The trigram tokenizer needs at least three characters; shorter queries fall back to LIKE.
MIN_FTS_QUERY = 3
# Fetch more rows than requested so collapsing to one hit per conversation still fills the page.
OVERFETCH = 5
SNIPPET_RADIUS = 80


def _one_per_conversation(hits: list[Hit]) -> list[Hit]:
    """Keep the first (best-ranked) hit for each conversation."""
    seen: set[int] = set()
    kept = []
    for hit in hits:
        if hit.conversation_id not in seen:
            seen.add(hit.conversation_id)
            kept.append(hit)
    return kept


def _window(content: str, query: str) -> str:
    """A short excerpt around the first case-insensitive occurrence of `query`."""
    index = content.lower().find(query.lower())
    if index < 0:
        return content[: SNIPPET_RADIUS * 2]
    start = max(0, index - SNIPPET_RADIUS)
    end = min(len(content), index + len(query) + SNIPPET_RADIUS)
    match_end = index + len(query)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(content) else ""
    marked = f"{content[start:index]}[{content[index:match_end]}]{content[match_end:end]}"
    return f"{prefix}{marked}{suffix}"


@dataclass
class Hit:
    message_id: int
    conversation_id: int
    source: str
    title: str
    project: str | None
    role: str
    created_at: str | None
    snippet: str
    score: float


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- writing -----------------------------------------------------------

    def upsert_conversation(self, conv: Conversation) -> int:
        """Insert or fully replace a conversation and its messages. Returns the row id."""
        cur = self.conn.execute(
            """
            INSERT INTO conversations (source, external_id, title, created_at, updated_at, project)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (source, external_id) DO UPDATE SET
                title = excluded.title,
                created_at = COALESCE(excluded.created_at, conversations.created_at),
                updated_at = excluded.updated_at,
                project = excluded.project
            RETURNING id
            """,
            (
                conv.source,
                conv.external_id,
                conv.title,
                conv.created_at,
                conv.updated_at,
                conv.project,
            ),
        )
        conv_id = cur.fetchone()[0]
        self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        self.conn.executemany(
            "INSERT INTO messages (conversation_id, position, role, content, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (conv_id, i, m.role, m.content, m.created_at)
                for i, m in enumerate(conv.messages)
                if m.content.strip()
            ],
        )
        return conv_id

    def commit(self) -> None:
        self.conn.commit()

    def file_unchanged(self, path: Path) -> bool:
        stat = path.stat()
        row = self.conn.execute(
            "SELECT mtime, size FROM files WHERE path = ?", (str(path),)
        ).fetchone()
        return row is not None and row["mtime"] == stat.st_mtime and row["size"] == stat.st_size

    def remember_file(self, path: Path) -> None:
        stat = path.stat()
        self.conn.execute(
            "INSERT OR REPLACE INTO files (path, mtime, size) VALUES (?, ?, ?)",
            (str(path), stat.st_mtime, stat.st_size),
        )

    # ---- reading -----------------------------------------------------------

    def search(self, query: str, source: str | None = None, limit: int = 20) -> list[Hit]:
        """Best matching message per conversation, strongest match first."""
        query = query.strip()
        if not query:
            return []
        if len(query) < MIN_FTS_QUERY:
            hits = self._search_like(query, source, limit * OVERFETCH)
        else:
            hits = self._search_fts(query, source, limit * OVERFETCH)
        return _one_per_conversation(hits)[:limit]

    def _search_fts(self, query: str, source: str | None, limit: int) -> list[Hit]:
        # Quote every term so FTS5 treats it as a literal phrase, not query syntax.
        fts_query = " ".join(f'"{term}"' for term in query.replace('"', " ").split())
        sql = """
            SELECT m.id AS message_id, c.id AS conversation_id, c.source, c.title, c.project,
                   m.role, m.created_at,
                   snippet(messages_fts, 0, '[', ']', '…', 64) AS snippet,
                   bm25(messages_fts) AS score
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            JOIN conversations c ON c.id = m.conversation_id
            WHERE messages_fts MATCH ?
        """
        params: list[object] = [fts_query]
        if source:
            sql += " AND c.source = ?"
            params.append(source)
        sql += " ORDER BY score LIMIT ?"
        params.append(limit)
        return [Hit(**dict(row)) for row in self.conn.execute(sql, params)]

    def _search_like(self, query: str, source: str | None, limit: int) -> list[Hit]:
        sql = """
            SELECT m.id AS message_id, c.id AS conversation_id, c.source, c.title, c.project,
                   m.role, m.created_at, m.content AS snippet, 0.0 AS score
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.content LIKE ? ESCAPE '\\'
        """
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params: list[object] = [f"%{escaped}%"]
        if source:
            sql += " AND c.source = ?"
            params.append(source)
        sql += " ORDER BY m.created_at DESC LIMIT ?"
        params.append(limit)
        hits = [Hit(**dict(row)) for row in self.conn.execute(sql, params)]
        for hit in hits:
            hit.snippet = _window(hit.snippet, query)
        return hits

    def get_conversation(self, conv_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if row is None:
            return None
        messages = self.conn.execute(
            "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ?"
            " ORDER BY position",
            (conv_id,),
        ).fetchall()
        return {**dict(row), "messages": [dict(m) for m in messages]}

    def recent(self, source: str | None = None, limit: int = 20) -> list[dict]:
        sql = """
            SELECT c.id, c.source, c.title, c.project, c.updated_at, COUNT(m.id) AS message_count
            FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
        """
        params: list[object] = []
        if source:
            sql += " WHERE c.source = ?"
            params.append(source)
        sql += " GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self.conn.execute(sql, params)]

    def stats(self) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT c.source, COUNT(DISTINCT c.id) AS conversations, COUNT(m.id) AS messages,
                   MIN(c.created_at) AS first, MAX(c.updated_at) AS last
            FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.source ORDER BY c.source
            """
        )
        return [dict(r) for r in rows]

    def sources(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT source FROM conversations ORDER BY 1")
        return [r[0] for r in rows]

    # ---- embeddings (used by semantic.py) ----------------------------------

    def messages_without_embedding(self, model: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT m.id, m.content FROM messages m
            LEFT JOIN embeddings e ON e.message_id = m.id AND e.model = ?
            WHERE e.message_id IS NULL
            """,
            (model,),
        ).fetchall()

    def store_embeddings(self, model: str, rows: list[tuple[int, bytes]]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO embeddings (message_id, model, vector) VALUES (?, ?, ?)",
            [(message_id, model, vector) for message_id, vector in rows],
        )

    def all_embeddings(self, model: str, source: str | None = None) -> list[sqlite3.Row]:
        sql = """
            SELECT e.message_id, e.vector FROM embeddings e
            JOIN messages m ON m.id = e.message_id
            JOIN conversations c ON c.id = m.conversation_id
            WHERE e.model = ?
        """
        params: list[object] = [model]
        if source:
            sql += " AND c.source = ?"
            params.append(source)
        return self.conn.execute(sql, params).fetchall()

    def hits_for_messages(self, message_ids: list[int]) -> dict[int, Hit]:
        if not message_ids:
            return {}
        placeholders = ",".join("?" for _ in message_ids)
        rows = self.conn.execute(
            f"""
            SELECT m.id AS message_id, c.id AS conversation_id, c.source, c.title, c.project,
                   m.role, m.created_at, substr(m.content, 1, 160) AS snippet, 0.0 AS score
            FROM messages m JOIN conversations c ON c.id = m.conversation_id
            WHERE m.id IN ({placeholders})
            """,
            message_ids,
        )
        return {row["message_id"]: Hit(**dict(row)) for row in rows}
