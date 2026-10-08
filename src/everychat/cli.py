"""Command-line interface: everychat <command> [options]"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, indexer, paths
from .db import Database, Hit
from .importers import EXPORT_IMPORTERS, LOCAL_IMPORTERS


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args) or 0
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="everychat",
        description="Search every AI conversation you've ever had. Local and free.",
    )
    parser.add_argument("--version", action="version", version=f"everychat {__version__}")
    parser.add_argument(
        "--db", type=Path, default=None, help="database file (default: ~/.everychat)"
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("import", help="import a ChatGPT / Claude.ai / Gemini export file")
    p.add_argument("path", type=Path)
    p.add_argument("--source", choices=sorted(EXPORT_IMPORTERS), help="skip auto-detection")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("sync", help="index Claude Code and Codex sessions on this machine")
    p.add_argument("--source", choices=sorted(LOCAL_IMPORTERS), action="append")
    p.add_argument("--force", action="store_true", help="re-read files even if unchanged")
    p.add_argument("--claude-code-dir", type=Path, help="override ~/.claude/projects")
    p.add_argument("--codex-dir", type=Path, help="override ~/.codex/sessions")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("search", help="full-text search across everything")
    p.add_argument("query")
    p.add_argument("--source", help="chatgpt, claude, gemini, claude-code or codex")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--semantic", action="store_true", help="search by meaning (needs `embed`)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("show", help="print one conversation")
    p.add_argument("id", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("recent", help="list the latest conversations")
    p.add_argument("--source")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_recent)

    p = sub.add_parser("stats", help="how much is indexed, per source")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("embed", help="build local embeddings for --semantic search")
    p.set_defaults(func=cmd_embed)

    p = sub.add_parser("mcp", help="run the MCP server over stdio")
    p.set_defaults(func=cmd_mcp)

    p = sub.add_parser("path", help="print where the database lives")
    p.set_defaults(func=cmd_path)
    return parser


def open_db(args: argparse.Namespace) -> Database:
    return Database(args.db or paths.db_path())


# ---- commands ----------------------------------------------------------------


def cmd_import(args: argparse.Namespace) -> int:
    with open_db(args) as db:
        count = indexer.import_export(db, args.path, args.source)
    print(f"imported {count} conversations from {args.path}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    roots = {}
    if args.claude_code_dir:
        roots["claude-code"] = args.claude_code_dir
    if args.codex_dir:
        roots["codex"] = args.codex_dir
    with open_db(args) as db:
        counts = indexer.sync_local(db, args.source, roots, args.force)
    for name, count in counts.items():
        print(f"{name}: {count} sessions updated")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    with open_db(args) as db:
        if args.semantic:
            from . import semantic

            hits = semantic.search(db, args.query, args.source, args.limit)
        else:
            hits = db.search(args.query, args.source, args.limit)
    if args.json:
        print(json.dumps([hit.__dict__ for hit in hits], ensure_ascii=False, indent=2))
        return 0
    if not hits:
        print("no matches")
        return 0
    for hit in hits:
        print(_format_hit(hit))
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    with open_db(args) as db:
        conv = db.get_conversation(args.id)
    if conv is None:
        raise ValueError(f"no conversation with id {args.id}")
    if args.json:
        print(json.dumps(conv, ensure_ascii=False, indent=2))
        return 0
    print(f"# {conv['title']}")
    print(f"source: {conv['source']}   id: {conv['id']}   updated: {_day(conv['updated_at'])}")
    if conv["project"]:
        print(f"project: {conv['project']}")
    for message in conv["messages"]:
        print(f"\n## {message['role']}  {_day(message['created_at'])}\n")
        print(message["content"])
    return 0


def cmd_recent(args: argparse.Namespace) -> int:
    with open_db(args) as db:
        rows = db.recent(args.source, args.limit)
    for row in rows:
        print(
            f"{row['id']:>6}  {row['source']:<11} {_day(row['updated_at'])}  "
            f"{row['message_count']:>4} msgs  {row['title']}"
        )
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    with open_db(args) as db:
        rows = db.stats()
        location = db.path
    if not rows:
        print("nothing indexed yet. Try: everychat sync   or   everychat import <export file>")
        return 0
    print(f"{'source':<12}{'conversations':>14}{'messages':>10}   first        last")
    for row in rows:
        print(
            f"{row['source']:<12}{row['conversations']:>14}{row['messages']:>10}   "
            f"{_day(row['first'])}   {_day(row['last'])}"
        )
    print(f"\ndatabase: {location}")
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    from . import semantic

    def progress(done: int, total: int) -> None:
        print(f"\rembedding {done}/{total}", end="", flush=True)

    with open_db(args) as db:
        total = semantic.embed_missing(db, progress)
    print(f"\rembedded {total} messages" + " " * 20)
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import run

    run(args.db or paths.db_path())
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    print(args.db or paths.db_path())
    return 0


# ---- formatting --------------------------------------------------------------


def _format_hit(hit: Hit) -> str:
    snippet = " ".join(hit.snippet.split())
    return (
        f"[{hit.conversation_id}] {hit.source} · {_day(hit.created_at)} · {hit.title}\n"
        f"      {hit.role}: {snippet}\n"
    )


def _day(value: str | None) -> str:
    return (value or "")[:10] or "unknown"


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    sys.exit(main())
