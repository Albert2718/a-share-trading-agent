from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROJECT_ENV_PATH = Path(".env")


@dataclass
class AppConfig:
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    tavily_api_key: Optional[str] = None
    news_agent_model: str = "gpt-4o-mini"
    llm_timeout: int = 60
    akshare_cache_ttl: int = 86400


def load_config() -> AppConfig:
    load_dotenv_file(PROJECT_ENV_PATH)

    return AppConfig(
        openai_api_key=os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL"),
        tavily_api_key=os.getenv("TAVILY_API_KEY"),
        news_agent_model=os.getenv("NEWS_AGENT_MODEL") or os.getenv("LLM_MODEL_ID") or "gpt-4o-mini",
        llm_timeout=int(os.getenv("LLM_TIMEOUT") or 60),
        akshare_cache_ttl=int(os.getenv("AKSHARE_CACHE_TTL") or 86400),
    )


def load_dotenv_file(path: Path = PROJECT_ENV_PATH) -> None:
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(path)
        return
    except Exception:
        pass

    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)
