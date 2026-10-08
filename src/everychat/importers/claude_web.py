"""Claude.ai data export: conversations.json (or the zip that contains it)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ..models import Conversation, Message
from ..textutil import title_from_text
from ._export import load_json_export, peek_first_item

MEMBER = "conversations.json"
ROLES = {"human": "user", "assistant": "assistant"}


def detect(path: Path) -> bool:
    first = peek_first_item(path, MEMBER)
    return isinstance(first, dict) and "chat_messages" in first


def parse(path: Path) -> Iterator[Conversation]:
    for raw in load_json_export(path, MEMBER):
        conv = _parse_conversation(raw)
        if conv and not conv.is_empty:
            yield conv


def _parse_conversation(raw: dict) -> Conversation | None:
    external_id = raw.get("uuid")
    if not external_id:
        return None
    messages = [m for m in map(_parse_message, raw.get("chat_messages") or []) if m]
    title = raw.get("name") or (title_from_text(messages[0].content) if messages else "(untitled)")
    return Conversation(
        source="claude",
        external_id=external_id,
        title=title,
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
        messages=messages,
    )


def _parse_message(raw: dict) -> Message | None:
    role = ROLES.get(raw.get("sender"))
    if not role:
        return None
    text = raw.get("text") or "\n".join(
        block.get("text", "") for block in raw.get("content") or [] if block.get("type") == "text"
    )
    if not text.strip():
        return None
    return Message(role=role, content=text.strip(), created_at=raw.get("created_at"))
