"""Gemini via Google Takeout: "My Activity" > "Gemini Apps" exported as JSON.

Takeout does not group turns into conversations. Every activity entry holds one prompt
("Prompted ...") and, usually, the HTML of the reply, so each entry becomes a tiny
two-message conversation.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

from ..models import Conversation, Message
from ..textutil import strip_html, title_from_text
from ._export import load_json_export, peek_first_item

MEMBER = "MyActivity.json"
PROMPT_PREFIX = "Prompted "


def detect(path: Path) -> bool:
    first = peek_first_item(path, MEMBER)
    return isinstance(first, dict) and "Gemini" in str(first.get("header", first.get("products")))


def parse(path: Path) -> Iterator[Conversation]:
    for raw in load_json_export(path, MEMBER):
        conv = _parse_entry(raw)
        if conv and not conv.is_empty:
            yield conv


def _parse_entry(raw: dict) -> Conversation | None:
    title = raw.get("title") or ""
    if not title.startswith(PROMPT_PREFIX):
        return None
    prompt = title[len(PROMPT_PREFIX) :].strip()
    time = raw.get("time")
    reply = "\n\n".join(
        strip_html(item.get("html", "")) for item in raw.get("safeHtmlItem") or []
    ).strip()

    messages = [Message(role="user", content=prompt, created_at=time)]
    if reply:
        messages.append(Message(role="assistant", content=reply, created_at=time))

    digest = hashlib.sha1(f"{time}|{prompt}".encode()).hexdigest()[:16]
    return Conversation(
        source="gemini",
        external_id=digest,
        title=title_from_text(prompt),
        created_at=time,
        updated_at=time,
        messages=messages,
    )
