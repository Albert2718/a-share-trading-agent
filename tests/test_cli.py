from __future__ import annotations

import unittest

from cli.main import build_parser, context_from_args
from src.agents.research.schemas import FinalReport, StockDecision, to_dict


class CLITests(unittest.TestCase):
    def test_analyze_arguments_build_research_context(self):
        args = build_parser().parse_args(
            [
                "analyze",
                "--code",
                "600519",
                "--depth",
                "full",
                "--risk",
                "conservative",
                "--history-days",
                "90",
                "--no-llm",
            ]
        )

        context = context_from_args(args)

        self.assertEqual(args.command, "analyze")
        self.assertEqual(context.depth, "full")
        self.assertEqual(context.risk_profile, "conservative")
        self.assertEqual(context.history_days, 90)
        self.assertFalse(context.use_llm)

    def test_report_serialization_keeps_public_fields(self):
        decision = StockDecision(code="600519", name="贵州茅台")
        payload = to_dict(
            FinalReport(
                generated_at="2026-07-14 00:00:00",
                mode="single",
                top_picks=[decision],
                avoid_list=[],
                all_decisions=[decision],
                summary="summary",
            )
        )

        self.assertEqual(
            set(payload),
            {"generated_at", "mode", "top_picks", "avoid_list", "all_decisions", "summary"},
        )
        self.assertEqual(
            set(payload["all_decisions"][0]),
            {
                "code",
                "name",
                "action",
                "confidence",
                "rank_score",
                "position_bias",
                "reason",
                "top_reasons",
                "risk_flags",
                "invalidation_conditions",
                "quant",
                "fundamental",
                "news",
                "sentiment",
            },
        )


if __name__ == "__main__":
    unittest.main()
