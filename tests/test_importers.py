import zipfile
from pathlib import Path

from everychat.importers import (
    chatgpt,
    claude_code,
    claude_web,
    codex,
    detect_export_source,
    gemini,
)


def test_chatgpt_follows_active_branch_and_skips_hidden(fixtures: Path):
    path = fixtures / "chatgpt_conversations.json"
    assert detect_export_source(path) == "chatgpt"
    [conv] = list(chatgpt.parse(path))
    assert conv.source == "chatgpt"
    assert conv.external_id == "conv-chatgpt-1"
    assert conv.title == "Sourdough starter help"
    assert conv.created_at == "2024-07-01T10:40:00+00:00"
    assert [m.role for m in conv.messages] == ["user", "assistant", "user"]
    assert conv.messages[2].content == "Here is a photo. Thanks!"
    assert all("abandoned" not in m.content for m in conv.messages)


def test_chatgpt_zip_is_accepted(fixtures: Path, tmp_path: Path):
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(fixtures / "chatgpt_conversations.json", "conversations.json")
    assert detect_export_source(archive) == "chatgpt"
    assert len(list(chatgpt.parse(archive))) == 1


def test_claude_web_uses_content_blocks_when_text_is_empty(fixtures: Path):
    path = fixtures / "claude_conversations.json"
    assert detect_export_source(path) == "claude"
    convs = list(claude_web.parse(path))
    assert [c.external_id for c in convs] == ["claude-conv-1"]  # empty one dropped
    assert convs[0].messages[1].content.startswith("Use ^09")


def test_gemini_turns_activity_into_prompt_and_reply(fixtures: Path):
    path = fixtures / "gemini_MyActivity.json"
    assert detect_export_source(path) == "gemini"
    [conv] = list(gemini.parse(path))
    assert conv.title == "幫我把這段英文翻成繁體中文"
    assert conv.messages[0].content == "幫我把這段英文翻成繁體中文"
    assert conv.messages[1].content == "好的，翻譯如下：\n「天氣很好」"


def test_claude_code_keeps_text_turns_only(fixtures: Path):
    paths = claude_code.discover(fixtures / "claude_code")
    assert [p.name for p in paths] == ["sess-1.jsonl"]  # nested subagent log not discovered
    conv = claude_code.parse(paths[0])
    assert conv.title == "Pytest fixture runs twice"
    assert conv.project == "C:\\work\\proj-a"
    assert [m.role for m in conv.messages] == ["user", "assistant"]
    assert conv.messages[0].content == "Why does my pytest fixture run twice?"
    assert conv.messages[1].content == (
        "Because the fixture has function scope\n\nand you request it from two tests."
    )


def test_codex_prefers_events_and_cleans_injected_text(fixtures: Path):
    paths = codex.discover(fixtures / "codex")
    by_name = {p.name: codex.parse(p) for p in paths}
    assert by_name["rollout-guardian.jsonl"] is None

    conv = by_name["rollout-user.jsonl"]
    assert conv.external_id == "codex-sess-1"
    assert conv.project == "C:\\work\\pets"
    assert conv.title == "Install the frieren pet please"
    assert [m.content for m in conv.messages] == [
        "Install the frieren pet please",
        "Installing frieren now.",
        "Does this look right?",
        "Yes, it is installed.",
    ]

    legacy = by_name["rollout-legacy.jsonl"]
    assert [m.content for m in legacy.messages] == [
        "Rename all .txt files to .md",
        "Done, 12 files renamed.",
    ]
