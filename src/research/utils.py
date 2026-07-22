from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit


def now_display() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
