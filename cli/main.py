from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

from src.agents.research.orchestrator import ResearchOrchestrator
from src.agents.research.reporting import format_markdown
from src.agents.research.schemas import AnalysisContext, StockCandidate, to_dict
from src.agents.research.utils import (
    parse_watchlist,
    report_filename_stem,
    save_json_report,
    save_markdown_report,
)
from src.core import CacheManager, ensure_cli_config, print_config_status
from src.tools.utils import normalize_a_share_code

from .render import print_banner, print_report
from .wizard import prompt_options


console = Console(legacy_windows=False)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command is None:
        run_chat(args)
    elif args.command == "analyze":
        run_analyze(args)
    elif args.command == "screen":
        run_screen(args)
    elif args.command == "cache":
        run_cache(args)
    elif args.command == "config":
        run_config(args)
    elif args.command == "chat":
        run_chat(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A-share multi-agent trading research assistant.")
    parser.add_argument("--output-dir", default="outputs/reports")
    sub = parser.add_subparsers(dest="command")

    analyze = sub.add_parser("analyze", help="Analyze one stock.")
    analyze.add_argument("--code", required=True)
    add_common_options(analyze)

    screen = sub.add_parser("screen", help="Analyze a watchlist or hot pool.")
    group = screen.add_mutually_exclusive_group(required=True)
    group.add_argument("--watchlist")
    group.add_argument("--hot", action="store_true")
    screen.add_argument("--top", type=int, default=5)
    add_common_options(screen)

    cache = sub.add_parser("cache", help="Inspect or clear cache.")
    cache.add_argument("action", choices=["status", "clear"])
    cache.add_argument("--source", default="")

    config = sub.add_parser("config", help="Configure API keys.")
    config.add_argument("action", choices=["setup", "status"], nargs="?", default="setup")

    chat = sub.add_parser("chat", help="Start the natural-language LangGraph chat agent.")
    chat.add_argument("--session-id", default="cli")
    chat.add_argument("--show-tools", action="store_true", help="Print tool calls and raw tool results after each answer.")
    return parser


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--depth", choices=["quick", "standard", "full"], default="standard")
    parser.add_argument("--risk", choices=["conservative", "balanced", "aggressive"], default="balanced")
    parser.add_argument("--history-days", type=int, default=160)
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--no-fundamental", action="store_true")
    parser.add_argument("--no-news", action="store_true")
    parser.add_argument("--no-sentiment", action="store_true")


def run_interactive(args) -> None:
    print_banner()
    options = prompt_options()
    shared = argparse.Namespace(
        depth=options.depth,
        risk=options.risk,
        history_days=160,
        no_llm=not options.use_llm,
        no_fundamental=False,
        no_news=False,
        no_sentiment=False,
        output_dir=args.output_dir,
    )
    if options.mode == "single":
        shared.code = options.codes
        run_analyze(shared)
    else:
        shared.watchlist = options.codes if options.mode == "watchlist" else None
        shared.hot = options.mode == "hot"
        shared.top = options.top
        run_screen(shared)


def run_analyze(args) -> None:
    if not args.no_news or not args.no_llm:
        ensure_cli_config(interactive=True)

    orchestrator = ResearchOrchestrator()
    candidates = orchestrator.candidates_from_codes([normalize_a_share_code(args.code)])
    report = orchestrator.analyze(
        candidates,
        context_from_args(args),
        mode="single",
        include_fundamental=not args.no_fundamental,
        include_news=not args.no_news,
        include_sentiment=not args.no_sentiment,
    )
    write_and_print(report, args.output_dir)


def run_screen(args) -> None:
    if not args.no_news or not args.no_llm:
        ensure_cli_config(interactive=True)

    orchestrator = ResearchOrchestrator()
    if args.hot:
        candidates = orchestrator.hot_candidates(args.top)
        mode = "hot"
        if not candidates:
            candidates = [StockCandidate(code="000001", name="fallback")]
            mode = "hot_fallback"
    else:
        candidates = orchestrator.candidates_from_codes(parse_watchlist(args.watchlist)[: args.top])
        mode = "watchlist"
    report = orchestrator.analyze(
        candidates,
        context_from_args(args),
        mode=mode,
        include_fundamental=not args.no_fundamental,
        include_news=not args.no_news,
        include_sentiment=not args.no_sentiment,
    )
    write_and_print(report, args.output_dir)


def run_cache(args) -> None:
    cache = CacheManager()
    if args.action == "status":
        print(cache.status())
    else:
        print({"cleared": cache.clear(args.source)})


def run_config(args) -> None:
    if args.action == "status":
        print_config_status()
        return
    ensure_cli_config(interactive=True)
    print_config_status()


def run_chat(args) -> None:
    ensure_cli_config(interactive=True)
    from src.agents.chat import ChatAgent

    print_banner()
    print("Chat mode. Type 'exit', 'quit', or '/exit' to stop.")
    agent = ChatAgent(session_id=getattr(args, "session_id", "cli"))
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            return
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "/exit", "/quit"}:
            print("Bye.")
            return
        answer = agent.run(user_input)
        print_agent_answer(answer)
        if getattr(args, "show_tools", False):
            print_tool_trace(agent.last_tool_results)


def context_from_args(args) -> AnalysisContext:
    return AnalysisContext(
        depth=args.depth,
        risk_profile=args.risk,
        use_llm=not args.no_llm,
        history_days=args.history_days,
    )


def write_and_print(report, output_dir: str) -> None:
    output = Path(output_dir)
    stem = report_filename_stem(report)
    json_path = save_json_report(to_dict(report), output, stem=stem)
    md_path = save_markdown_report(format_markdown(report), output, stem=stem)
    print_report(report)
    print(f"\nJSON report saved to: {json_path}")
    print(f"Markdown report saved to: {md_path}")


def print_tool_trace(tool_results) -> None:
    if not tool_results:
        print("\nTool trace: no tool was called.")
        return
    print("\nTool trace:")
    for index, item in enumerate(tool_results, start=1):
        name = item.get("name", "")
        arguments = item.get("arguments", {})
        result = item.get("result", {})
        print(f"{index}. {name}")
        print(f"   args: {json.dumps(arguments, ensure_ascii=False, default=str)}")
        print(f"   result: {json.dumps(result, ensure_ascii=False, default=str)[:2000]}")


def print_agent_answer(answer: str) -> None:
    console.print("\n[bold green]Agent:[/bold green]")
    console.print(Markdown(answer or "我没有得到可用回答。"))


if __name__ == "__main__":
    main()
