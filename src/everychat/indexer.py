"""Orchestrates importers into the database."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .db import Database
from .importers import EXPORT_IMPORTERS, LOCAL_IMPORTERS, detect_export_source

Progress = Callable[[str], None]


def import_export(db: Database, path: Path, source: str | None = None) -> int:
    """Import a downloaded export file. Returns the number of conversations stored."""
    source = source or detect_export_source(path)
    if source not in EXPORT_IMPORTERS:
        known = ", ".join(EXPORT_IMPORTERS)
        raise ValueError(f"Could not tell which tool produced {path}. Pass --source ({known}).")
    count = 0
    for conv in EXPORT_IMPORTERS[source](path):
        db.upsert_conversation(conv)
        count += 1
    db.commit()
    return count


def sync_local(
    db: Database,
    sources: list[str] | None = None,
    roots: dict[str, Path] | None = None,
    force: bool = False,
    progress: Progress | None = None,
) -> dict[str, int]:
    """Index coding-agent sessions found on this machine. Returns conversations per source."""
    roots = roots or {}
    counts: dict[str, int] = {}
    for name, module in LOCAL_IMPORTERS.items():
        if sources and name not in sources:
            continue
        counts[name] = 0
        for path in module.discover(roots.get(name)):
            if not force and db.file_unchanged(path):
                continue
            conv = module.parse(path)
            if conv is not None:
                db.upsert_conversation(conv)
                counts[name] += 1
            db.remember_file(path)
            if progress:
                progress(f"{name}: {path.name}")
        db.commit()
    return counts
