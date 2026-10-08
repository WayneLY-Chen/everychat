"""OpenAI Codex sessions: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl

Newer Codex versions log clean `event_msg` records (`user_message`, `agent_message`).
Older ones only have `response_item` messages, which also carry injected context in the
user slot, so those are used as a fallback with the injected blocks filtered out.
Sessions whose `thread_source` is not "user" (permission reviewers, spawned subagents)
are skipped.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

from ..models import Conversation, Message
from ..paths import codex_dir
from ..textutil import strip_injected_blocks, title_from_text
from ._export import merge_consecutive

SOURCE = "codex"


def discover(root: Path | None = None) -> list[Path]:
    root = root or codex_dir()
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("*.jsonl") if p.is_file())


def parse(path: Path) -> Conversation | None:
    session_id = path.stem
    project: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    events: list[Message] = []
    fallback: list[Message] = []

    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get("payload") or {}
            timestamp = record.get("timestamp")
            kind = record.get("type")

            if kind == "session_meta":
                if payload.get("thread_source", "user") != "user":
                    return None  # guardian reviewers and spawned subagents, not the user's chat
                session_id = payload.get("id") or session_id
                project = payload.get("cwd")
                created_at = payload.get("timestamp") or timestamp
            elif kind == "event_msg":
                message = _from_event(payload, timestamp)
                if message:
                    events.append(message)
                    updated_at = timestamp
            elif kind == "response_item" and payload.get("type") == "message":
                message = _from_response_item(payload, timestamp)
                if message:
                    fallback.append(message)
                    updated_at = timestamp

    messages = merge_consecutive(events or fallback)
    if not messages:
        return None
    first_user = next((m.content for m in messages if m.role == "user"), messages[0].content)
    return Conversation(
        source=SOURCE,
        external_id=session_id,
        title=title_from_text(first_user),
        created_at=created_at,
        updated_at=updated_at,
        project=project,
        messages=messages,
    )


def _from_event(payload: dict, timestamp: str | None) -> Message | None:
    kind = payload.get("type")
    text = payload.get("message") or ""
    if kind == "user_message":
        text = _clean_user_text(text)
        return Message(role="user", content=text, created_at=timestamp) if text else None
    if kind == "agent_message" and text.strip():
        return Message(role="assistant", content=text.strip(), created_at=timestamp)
    return None


# Codex prepends project instructions and attached-file notes to what the user typed.
_AGENTS_HEADER_RE = re.compile(r"^# AGENTS\.md instructions\s*", re.MULTILINE)
_REQUEST_MARKER = "## My request:"


def _clean_user_text(text: str) -> str:
    text = strip_injected_blocks(text)
    if _REQUEST_MARKER in text:
        text = text.split(_REQUEST_MARKER, 1)[1]
    return _AGENTS_HEADER_RE.sub("", text).strip()


def _from_response_item(payload: dict, timestamp: str | None) -> Message | None:
    role = payload.get("role")
    if role not in ("user", "assistant"):
        return None
    text = "\n".join(
        block.get("text", "")
        for block in payload.get("content") or []
        if block.get("type") in ("input_text", "output_text")
    )
    text = _clean_user_text(text) if role == "user" else text.strip()
    if not text:
        return None
    return Message(role=role, content=text, created_at=timestamp)


def iter_sessions(root: Path | None = None) -> Iterator[tuple[Path, Conversation | None]]:
    for path in discover(root):
        yield path, parse(path)
