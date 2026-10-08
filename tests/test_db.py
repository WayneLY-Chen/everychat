from pathlib import Path

from everychat import indexer
from everychat.db import Database
from everychat.models import Conversation, Message


def _conv(external_id: str, *texts: str, source: str = "chatgpt") -> Conversation:
    messages = [
        Message(role=("user", "assistant")[i % 2], content=t, created_at=f"2026-01-0{i + 1}")
        for i, t in enumerate(texts)
    ]
    return Conversation(
        source=source, external_id=external_id, title=texts[0][:20], messages=messages
    )


def test_upsert_replaces_messages(db: Database):
    conv_id = db.upsert_conversation(_conv("a", "first version"))
    assert db.upsert_conversation(_conv("a", "second version", "reply")) == conv_id
    stored = db.get_conversation(conv_id)
    assert [m["content"] for m in stored["messages"]] == ["second version", "reply"]


def test_search_is_substring_and_cjk_friendly(db: Database):
    db.upsert_conversation(_conv("a", "我想學 sourdough 麵包怎麼做", "先養酵母"))
    db.upsert_conversation(_conv("b", "unrelated talk about pytest fixtures"))
    db.commit()

    hits = db.search("酵母")  # two characters: LIKE fallback
    assert len(hits) == 1 and "[酵母]" in hits[0].snippet
    hits = db.search("sourdough")  # trigram FTS
    assert len(hits) == 1 and "[sourdough]" in hits[0].snippet
    hits = db.search("麵包怎麼")
    assert len(hits) == 1
    assert db.search("nothing here") == []


def test_search_returns_one_hit_per_conversation_and_filters_source(db: Database):
    db.upsert_conversation(_conv("a", "python tips", "more python tips", "even more python"))
    db.upsert_conversation(_conv("b", "python in codex", source="codex"))
    db.commit()
    hits = db.search("python")
    assert sorted(h.source for h in hits) == ["chatgpt", "codex"]
    assert [h.source for h in db.search("python", source="codex")] == ["codex"]


def test_sync_skips_unchanged_files(db: Database):
    fixtures = Path(__file__).parent / "fixtures"
    roots = {"claude-code": fixtures / "claude_code", "codex": fixtures / "codex"}
    first = indexer.sync_local(db, roots=roots)
    assert first == {"claude-code": 1, "codex": 2}
    second = indexer.sync_local(db, roots=roots)
    assert second == {"claude-code": 0, "codex": 0}
    assert indexer.sync_local(db, roots=roots, force=True) == first
    assert {row["source"] for row in db.stats()} == {"claude-code", "codex"}


def test_import_export_autodetects(db: Database):
    fixtures = Path(__file__).parent / "fixtures"
    assert indexer.import_export(db, fixtures / "chatgpt_conversations.json") == 1
    assert indexer.import_export(db, fixtures / "claude_conversations.json") == 1
    assert indexer.import_export(db, fixtures / "gemini_MyActivity.json") == 1
    assert db.sources() == ["chatgpt", "claude", "gemini"]
