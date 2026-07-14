from __future__ import annotations

from .schemas import FinalReport


def format_console(report: FinalReport) -> str:
    lines = [
        f"Generated at: {report.generated_at}",
        f"Mode: {report.mode}",
        report.summary,
        "",
        "Ranked decisions:",
    ]
    for idx, item in enumerate(report.all_decisions, start=1):
        name = f" {item.name}" if item.name else ""
        lines.append(
            f"{idx}. {item.code}{name} | {item.action} | score={item.rank_score} "
            f"| confidence={item.confidence} | position={item.position_bias}"
        )
        if item.top_reasons:
            lines.append(f"   Reasons: {'; '.join(item.top_reasons[:3])}")
        if item.risk_flags:
            lines.append(f"   Risks: {'; '.join(item.risk_flags[:3])}")
    return "\n".join(lines)


def format_markdown(report: FinalReport) -> str:
    lines = [
        "# A-share Trading Agent Report",
        "",
        f"- Generated at: {report.generated_at}",
        f"- Mode: {report.mode}",
        f"- Summary: {report.summary}",
        "",
        "| Rank | Code | Name | Action | Score | Confidence | Position |",
        "|---:|---|---|---|---:|---|---|",
    ]
    for idx, item in enumerate(report.all_decisions, start=1):
        lines.append(
            f"| {idx} | {item.code} | {item.name} | {item.action} | "
            f"{item.rank_score} | {item.confidence} | {item.position_bias} |"
        )
    lines.append("")
    for item in report.all_decisions:
        lines.extend(
            [
                f"## {item.code} {item.name}",
                "",
                f"- Action: {item.action}",
                f"- Score: {item.rank_score}",
                f"- Position bias: {item.position_bias}",
                f"- Reasons: {'; '.join(item.top_reasons)}",
                f"- Risks: {'; '.join(item.risk_flags) if item.risk_flags else 'None'}",
                f"- Invalidation: {'; '.join(item.invalidation_conditions)}",
                "",
            ]
        )
    return "\n".join(lines)
