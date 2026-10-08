"""MCP server so Claude Code, Codex, Cursor and friends can search your history.

Run with `everychat mcp`. Register it, for example in Claude Code:
    claude mcp add everychat -- everychat mcp
"""

from __future__ import annotations

from pathlib import Path

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from .db import Database

INSTRUCTIONS = (
    "everychat indexes the user's past AI conversations (ChatGPT, Claude, Gemini, Claude Code, "
    "Codex). Use search_chats when the user refers to something they discussed before, asks "
    "'did I already ...', or wants to reuse an earlier decision or snippet. Then call get_chat "
    "with the conversation_id to read the full exchange."
)


def build_server(db_path: Path) -> _Server:
    server = _Server("everychat", instructions=INSTRUCTIONS)

    @server.tool()
    def search_chats(query: str, source: str | None = None, limit: int = 10) -> list[dict]:
        """Full-text search over all indexed AI conversations.

        Args:
            query: words or a phrase to look for (any language).
            source: optional filter: chatgpt, claude, gemini, claude-code or codex.
            limit: maximum number of matching conversations to return.
        """
        with Database(db_path) as db:
            return [hit.__dict__ for hit in db.search(query, source, limit)]

    @server.tool()
    def get_chat(conversation_id: int, max_chars: int = 20000) -> dict:
        """Return one full conversation by the conversation_id from search_chats."""
        with Database(db_path) as db:
            conv = db.get_conversation(conversation_id)
        if conv is None:
            return {"error": f"no conversation with id {conversation_id}"}
        used = 0
        kept = []
        for message in conv["messages"]:
            kept.append(message)
            used += len(message["content"])
            if used > max_chars:
                conv["truncated"] = True
                break
        conv["messages"] = kept
        return conv

    @server.tool()
    def recent_chats(source: str | None = None, limit: int = 20) -> list[dict]:
        """List the most recently updated conversations, optionally for one source."""
        with Database(db_path) as db:
            return db.recent(source, limit)

    @server.tool()
    def list_sources() -> list[dict]:
        """Which tools are indexed and how many conversations each one has."""
        with Database(db_path) as db:
            return db.stats()

    return server


def run(db_path: Path) -> None:
    build_server(db_path).run(transport="stdio")
