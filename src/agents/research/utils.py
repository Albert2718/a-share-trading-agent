from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import List
from urllib.parse import urlsplit, urlunsplit

from src.tools.utils import normalize_a_share_code


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


def save_markdown_report(text: str, output_dir: Path, stem: str | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{stem or now_compact()}.md"
    path.write_text(text, encoding="utf-8")
    return path


_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
}
_URL_PATTERN = re.compile(r"https?://[^\s;]+", re.IGNORECASE)
_AUTH_PATTERN = re.compile(
    r"authorization\s*:\s*(?:bearer|basic)\s+[^\s;]+",
    re.IGNORECASE,
)
_CREDENTIAL_PATTERN = re.compile(
    r"\b((?:[a-z0-9]+[_-])*(?:api[_-]?key|token|access[_-]?token|refresh[_-]?token|passwd|password|secret))\s*[:=]\s*[^\s&;]+",
    re.IGNORECASE,
)
_BEARER_PATTERN = re.compile(
    r"\bbearer\s+[^\s;]+",
    re.IGNORECASE,
)


def redact_recursive(value):
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text):
                result[key_text] = "[REDACTED]"
            else:
                result[key_text] = redact_recursive(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_recursive(item) for item in value]
    if isinstance(value, str):
        return sanitize_secret_text(value)
    return value


def sanitize_secret_text(value: str) -> str:
    text = _AUTH_PATTERN.sub("Authorization: [REDACTED]", value)
    text = _CREDENTIAL_PATTERN.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _BEARER_PATTERN.sub("Bearer [REDACTED]", text)

    def sanitize_url(match: re.Match[str]) -> str:
        raw_url = match.group(0)
        try:
            parsed = urlsplit(raw_url)
        except ValueError:
            return "[REDACTED_URL]"
        if not parsed.hostname:
            return "[REDACTED_URL]"
        host = parsed.hostname
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urlunsplit((parsed.scheme, host, parsed.path, "", ""))

    return _URL_PATTERN.sub(sanitize_url, text)


def _is_sensitive_key(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    compact = re.sub(r"[^a-z0-9]+", "", value.casefold())
    if normalized in _SENSITIVE_KEYS or compact in _SENSITIVE_KEYS:
        return True
    return normalized.endswith(("_api_key", "_apikey", "_authorization", "_password", "_passwd", "_secret", "_token")) or compact.endswith(
        ("apikey", "authorization", "password", "passwd", "secret", "token")
    )
