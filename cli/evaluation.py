from __future__ import annotations

from datetime import datetime
from pathlib import Path

from src.core import load_config
from src.evaluation.runner import EvaluationRunner


def run_evaluate(args) -> int:
    """Run evaluation commands without interactive credential prompts."""
    load_config()
    runner = EvaluationRunner(root=Path(args.root))
    if args.action == "report":
        json_path, markdown_path = runner.build_report()
        print(f"Evaluation reports: {json_path}, {markdown_path}")
        return 0

    try:
        summary = runner.run_daily(datetime.now().astimezone())
    except RuntimeError as exc:
        print(f"Evaluation rejected: {exc}")
        return 2

    print(
        "Evaluation batch "
        f"{summary.warnings[0]}: {summary.successful_predictions}/{summary.pool_size} "
        f"({summary.coverage_rate:.0%})"
    )
    return 0 if summary.complete else 1
