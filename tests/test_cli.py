from pathlib import Path

from everychat.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_end_to_end(tmp_path: Path, capsys):
    db = str(tmp_path / "cli.db")
    assert main(["--db", db, "import", str(FIXTURES / "chatgpt_conversations.json")]) == 0
    assert main(["--db", db, "sync", "--claude-code-dir", str(FIXTURES / "claude_code"),
                 "--codex-dir", str(FIXTURES / "codex")]) == 0
    capsys.readouterr()

    assert main(["--db", db, "search", "fixture"]) == 0
    out = capsys.readouterr().out
    assert "Pytest fixture runs twice" in out and "[fixture]" in out

    assert main(["--db", db, "stats"]) == 0
    out = capsys.readouterr().out
    assert "chatgpt" in out and "claude-code" in out and "codex" in out

    assert main(["--db", db, "show", "1"]) == 0
    assert "Sourdough starter help" in capsys.readouterr().out

    assert main(["--db", db, "show", "999"]) == 1
    assert "no conversation" in capsys.readouterr().err


def test_import_unknown_file_fails_cleanly(tmp_path: Path, capsys):
    bogus = tmp_path / "x.json"
    bogus.write_text("[{\"hello\": 1}]", encoding="utf-8")
    assert main(["--db", str(tmp_path / "db"), "import", str(bogus)]) == 1
    assert "--source" in capsys.readouterr().err
