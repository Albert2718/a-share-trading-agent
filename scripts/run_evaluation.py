from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core import load_config
from src.evaluation.runner import EvaluationRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or report the fixed 20-stock evaluation."
    )
    parser.add_argument("action", choices=("daily", "report"))
    parser.add_argument("--root", default="evaluation")
    return parser


def run(args: argparse.Namespace) -> int:
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


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
