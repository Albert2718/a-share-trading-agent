from __future__ import annotations

from src.agents.research.reporting import format_console
from src.agents.research.schemas import FinalReport


def print_banner() -> None:
    banner = r"""
    ___        _____ __                  ______              __
   /   |      / ___// /_  ____ _________/_  __/________ ____/ /__  _____
  / /| |______\__ \/ __ \/ __ `/ ___/ _ \/ / / ___/ __ `/ _  / _ \/ ___/
 / ___ /_____/__/ / / / / /_/ / /  /  __/ / / /  / /_/ /  __/  __/ /
/_/  |_|    /____/_/ /_/\__,_/_/   \___/_/ /_/   \__,_/\___/\___/_/
"""
    try:
        from rich.console import Console
        from rich.panel import Panel

        Console().print(Panel.fit(banner, title="A-Share Trading Agent", border_style="green"))
    except Exception:
        print(banner)
        print("A-Share Trading Agent")


def print_report(report: FinalReport) -> None:
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        console.print(f"[bold]{report.summary}[/bold]")
        table = Table(title="Ranked Decisions")
        for column in ["Rank", "Code", "Name", "Action", "Score", "Confidence", "Position"]:
            table.add_column(column)
        for idx, item in enumerate(report.all_decisions, start=1):
            table.add_row(
                str(idx),
                item.code,
                item.name,
                item.action,
                str(item.rank_score),
                item.confidence,
                item.position_bias,
            )
        console.print(table)
    except Exception:
        print(format_console(report))
