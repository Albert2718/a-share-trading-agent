from __future__ import annotations

from pathlib import Path

from scripts.run_evaluation import build_parser, run


def test_evaluation_arguments_parse():
    args = build_parser().parse_args(["daily"])

    assert args.action == "daily"
    assert args.root == "evaluation"


def test_report_command_builds_both_reports(tmp_path: Path):
    args = build_parser().parse_args(["report", "--root", str(tmp_path)])

    assert run(args) == 0
    assert (tmp_path / "reports" / "summary.json").exists()
    assert (tmp_path / "reports" / "summary.md").exists()
