"""ChatGPT data export: conversations.json (or the zip that contains it).

Each conversation is a tree of nodes under `mapping`; `current_node` points at the
leaf of the branch the user last looked at. We walk from that leaf to the root.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ..models import Conversation, Message
from ..textutil import epoch_to_iso
from ._export import load_json_export, peek_first_item

MEMBER = "conversations.json"
TEXT_TYPES = {"text", "multimodal_text"}


def detect(path: Path) -> bool:
    first = peek_first_item(path, MEMBER)
    return isinstance(first, dict) and "mapping" in first


def parse(path: Path) -> Iterator[Conversation]:
    for raw in load_json_export(path, MEMBER):
        conv = _parse_conversation(raw)
        if conv and not conv.is_empty:
            yield conv


def _parse_conversation(raw: dict) -> Conversation | None:
    mapping = raw.get("mapping") or {}
    external_id = raw.get("conversation_id") or raw.get("id")
    if not mapping or not external_id:
        return None

    messages = [
        message
        for node in _active_branch(mapping, raw.get("current_node"))
        if (message := _parse_message(node.get("message")))
    ]
    return Conversation(
        source="chatgpt",
        external_id=external_id,
        title=raw.get("title") or "(untitled)",
        created_at=epoch_to_iso(raw.get("create_time")),
        updated_at=epoch_to_iso(raw.get("update_time")),
        messages=messages,
    )


def _active_branch(mapping: dict, leaf_id: str | None) -> list[dict]:
    """Nodes from root to leaf. Falls back to the newest branch when the leaf is unknown."""
    if leaf_id not in mapping:
        leaf_id = _newest_leaf(mapping)
    chain: list[dict] = []
    node_id = leaf_id
    while node_id in mapping:
        node = mapping[node_id]
        chain.append(node)
        node_id = node.get("parent")
    chain.reverse()
    return chain


def _newest_leaf(mapping: dict) -> str | None:
    roots = [k for k, v in mapping.items() if not v.get("parent")]
    node_id = roots[0] if roots else None
    while node_id and mapping[node_id].get("children"):
        node_id = mapping[node_id]["children"][-1]
    return node_id


def _parse_message(message: dict | None) -> Message | None:
    if not message:
        return None
    role = (message.get("author") or {}).get("role")
    if role not in ("user", "assistant"):
        return None
    if (message.get("metadata") or {}).get("is_visually_hidden_from_conversation"):
        return None
    content = message.get("content") or {}
    if content.get("content_type") not in TEXT_TYPES:
        return None
    text = "\n".join(part for part in content.get("parts") or [] if isinstance(part, str)).strip()
    if not text:
        return None
    return Message(role=role, content=text, created_at=epoch_to_iso(message.get("create_time")))
