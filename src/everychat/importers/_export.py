"""Helpers for export files: a bare JSON file or the zip the vendor hands out."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


def load_json_export(path: Path, member_name: str) -> Any:
    """Load `member_name` from a zip, or the file itself when it is plain JSON."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            candidates = [n for n in zf.namelist() if n.endswith(member_name)]
            if not candidates:
                raise FileNotFoundError(f"{path} does not contain {member_name}")
            with zf.open(candidates[0]) as fh:
                return json.load(fh)
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def peek_first_item(path: Path, member_name: str) -> Any | None:
    """Return the first item of a JSON list export, or None if it does not look like one."""
    try:
        data = load_json_export(path, member_name)
    except (OSError, ValueError, FileNotFoundError):
        return None
    if isinstance(data, list) and data:
        return data[0]
    return None


def merge_consecutive(messages: list) -> list:
    """Join adjacent messages from the same role so streamed chunks read as one turn."""
    merged: list = []
    for message in messages:
        if merged and merged[-1].role == message.role:
            merged[-1].content = f"{merged[-1].content}\n\n{message.content}"
        else:
            merged.append(message)
    return merged
