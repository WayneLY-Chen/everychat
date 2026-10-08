"""Small text helpers used by several importers."""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

_TAG_RE = re.compile(r"<[^>]+>")
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")


def strip_html(raw: str) -> str:
    """Turn a small HTML fragment into readable plain text."""
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|h\d)>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    return _TRAILING_WS_RE.sub("\n", text).strip()


def epoch_to_iso(value: float | int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()


def title_from_text(text: str, limit: int = 80) -> str:
    lines = text.strip().splitlines()
    if not lines:
        return "(untitled)"
    first = lines[0].strip()
    return first if len(first) <= limit else first[:limit].rstrip() + "…"


# Coding agents wrap machine-generated context in XML-ish tags inside the user turn, e.g.
# <system-reminder>, <ide_selection>, <command-name>, <app-context>, <environment_context>.
# Real HTML tags never contain "-" or "_", so those names are safe to strip; a few plain
# words that agents also use are listed explicitly.
_INJECTED_TAG = r"(?:[a-zA-Z]+[-_][\w-]*|skill|permissions|instructions)"
_INJECTED_BLOCK_RE = re.compile(
    rf"<({_INJECTED_TAG})(?:\s[^>]*)?>.*?</\1\s*>|<{_INJECTED_TAG}(?:\s[^>]*)?/>",
    re.DOTALL | re.IGNORECASE,
)


def strip_injected_blocks(text: str) -> str:
    """Remove agent-injected context blocks, keeping whatever the human actually typed."""
    return _INJECTED_BLOCK_RE.sub("", text).strip()
