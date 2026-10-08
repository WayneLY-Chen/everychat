"""Plain data records shared by importers, the database and the CLI."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str
    created_at: str | None = None  # ISO-8601, UTC when known


@dataclass
class Conversation:
    source: str  # "chatgpt", "claude", "gemini", "claude-code", "codex"
    external_id: str  # stable id inside the source, used for de-duplication
    title: str
    created_at: str | None = None
    updated_at: str | None = None
    project: str | None = None  # working directory for coding agents
    messages: list[Message] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not any(m.content.strip() for m in self.messages)
