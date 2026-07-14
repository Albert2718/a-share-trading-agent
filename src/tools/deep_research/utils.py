from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, List


def normalize_a_share_code(code: str) -> str:
    digits = re.sub(r"\D", "", str(code))
    if len(digits) >= 6:
        return digits[-6:]
    return digits.zfill(6)


def now_compact() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def now_display() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_watchlist(raw: str) -> List[str]:
    return [normalize_a_share_code(item) for item in re.split(r"[,，\s]+", raw) if item.strip()]


def safe_filename_part(value, max_length: int = 80) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text)
    text = text.strip("._ ")
    return (text[:max_length].strip("._ ") or "unknown")


def report_filename_stem(report) -> str:
    decisions = getattr(report, "all_decisions", []) or []
    mode = safe_filename_part(getattr(report, "mode", "report"), 24)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not decisions:
        return f"{timestamp}_{mode}_empty"

    top = decisions[0]
    action = safe_filename_part(getattr(top, "action", "watch"), 12)
    score = getattr(top, "rank_score", 0)
    code = safe_filename_part(getattr(top, "code", "unknown"), 16)
    name = safe_filename_part(getattr(top, "name", ""), 32)
    stock_part = f"{code}_{name}" if name != "unknown" else code
    count_part = stock_part if len(decisions) == 1 else f"{len(decisions)}stocks_top_{stock_part}"
    return f"{timestamp}_{mode}_{count_part}_{action}_s{score}"


def save_json_report(report: dict, output_dir: Path, stem: str | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{stem or now_compact()}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def dedupe_keep_order(items: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def parse_watchlist(raw: str) -> List[str]:
    return [normalize_a_share_code(item) for item in re.split(r"[,，\s]+", raw) if item.strip()]


def save_markdown_report(text: str, output_dir: Path, stem: str | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{stem or now_compact()}.md"
    path.write_text(text, encoding="utf-8")
    return path


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        text = str(value).replace("%", "").replace(",", "").strip()
        if text in {"", "-", "nan", "None"}:
            return default
        return float(text)
    except Exception:
        return default
