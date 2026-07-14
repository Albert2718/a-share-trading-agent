from __future__ import annotations

import re
from typing import Iterable, List


def normalize_a_share_code(code: str) -> str:
    digits = re.sub(r"\D", "", str(code))
    if len(digits) >= 6:
        return digits[-6:]
    return digits.zfill(6)


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
