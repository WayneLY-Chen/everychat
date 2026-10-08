"""Claude Code sessions: ~/.claude/projects/<project>/<session-id>.jsonl

Each line is a JSON record. We keep `user` and `assistant` records, taking only their
text blocks (tool calls, tool results and thinking are skipped), and use the `ai-title`
or `summary` record as the title when there is one.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from ..models import Conversation, Message
from ..paths import claude_code_dir
from ..textutil import strip_injected_blocks, title_from_text
from ._export import merge_consecutive

SOURCE = "claude-code"


def discover(root: Path | None = None) -> list[Path]:
    """Session files, top level of each project directory only (subagent logs live deeper)."""
    root = root or claude_code_dir()
    if not root.is_dir():
        return []
    return sorted(p for p in root.glob("*/*.jsonl") if p.is_file())


def parse(path: Path) -> Conversation | None:
    session_id = path.stem
    title: str | None = None
    project: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    messages: list[Message] = []

    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            kind = record.get("type")
            if kind == "ai-title":
                title = record.get("aiTitle") or title
            elif kind == "summary" and not title:
                title = record.get("summary")
            elif kind in ("user", "assistant"):
                if record.get("isMeta") or record.get("isSidechain"):
                    continue
                project = project or record.get("cwd")
                timestamp = record.get("timestamp")
                created_at = created_at or timestamp
                updated_at = timestamp or updated_at
                text = _text_of(record.get("message") or {})
                if text:
                    messages.append(Message(role=kind, content=text, created_at=timestamp))

    if not messages:
        return None
    messages = merge_consecutive(messages)
    first_user = next((m.content for m in messages if m.role == "user"), messages[0].content)
    return Conversation(
        source=SOURCE,
        external_id=session_id,
        title=title or title_from_text(first_user),
        created_at=created_at,
        updated_at=updated_at,
        project=project,
        messages=messages,
    )


def _text_of(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return strip_injected_blocks(content)
    if not isinstance(content, list):
        return ""
    parts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return strip_injected_blocks("\n".join(p for p in parts if p))


def iter_sessions(root: Path | None = None) -> Iterator[tuple[Path, Conversation | None]]:
    for path in discover(root):
        yield path, parse(path)
