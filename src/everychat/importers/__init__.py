"""Importers turn each tool's own format into Conversation records.

Export importers read a file the user downloaded (ChatGPT, Claude.ai, Gemini Takeout).
Local importers read session logs that coding agents keep on disk (Claude Code, Codex).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

from ..models import Conversation
from . import chatgpt, claude_code, claude_web, codex, gemini

ExportParser = Callable[[Path], Iterator[Conversation]]

EXPORT_IMPORTERS: dict[str, ExportParser] = {
    "chatgpt": chatgpt.parse,
    "claude": claude_web.parse,
    "gemini": gemini.parse,
}

LOCAL_IMPORTERS = {
    "claude-code": claude_code,
    "codex": codex,
}


def detect_export_source(path: Path) -> str | None:
    """Guess which tool produced an export file by peeking at its content."""
    for name, module in (("chatgpt", chatgpt), ("claude", claude_web), ("gemini", gemini)):
        if module.detect(path):
            return name
    return None
