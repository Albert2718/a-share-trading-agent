from __future__ import annotations

import getpass
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


PROJECT_ENV_PATH = Path(".env")
USER_CONFIG_PATH = Path.home() / ".trading_agents" / "config.json"


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
    user_config = load_user_config()

    return AppConfig(
        openai_api_key=(
            os.getenv("OPENAI_API_KEY")
            or os.getenv("LLM_API_KEY")
            or user_config.get("OPENAI_API_KEY")
            or user_config.get("LLM_API_KEY")
        ),
        openai_base_url=(
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("LLM_BASE_URL")
            or user_config.get("OPENAI_BASE_URL")
            or user_config.get("LLM_BASE_URL")
        ),
        tavily_api_key=os.getenv("TAVILY_API_KEY") or user_config.get("TAVILY_API_KEY"),
        news_agent_model=(
            os.getenv("NEWS_AGENT_MODEL")
            or os.getenv("LLM_MODEL_ID")
            or user_config.get("NEWS_AGENT_MODEL")
            or user_config.get("LLM_MODEL_ID")
            or "gpt-4o-mini"
        ),
        llm_timeout=int(os.getenv("LLM_TIMEOUT") or user_config.get("LLM_TIMEOUT") or 60),
        akshare_cache_ttl=int(os.getenv("AKSHARE_CACHE_TTL") or user_config.get("AKSHARE_CACHE_TTL") or 86400),
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


def load_user_config(path: Path = USER_CONFIG_PATH) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_user_config(values: dict, path: Path = USER_CONFIG_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_user_config(path)
    current.update({key: value for key, value in values.items() if value not in (None, "")})
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def ensure_cli_config(interactive: bool = True) -> AppConfig:
    config = load_config()
    missing = []
    if not config.tavily_api_key:
        missing.append("TAVILY_API_KEY")
    if not config.openai_api_key:
        missing.append("OPENAI_API_KEY")

    if not missing or not interactive:
        return config

    print("API keys are not fully configured.")
    print("Press Enter to skip an optional key. Values will be saved to ~/.trading_agents/config.json.")
    values = {}
    if "TAVILY_API_KEY" in missing:
        values["TAVILY_API_KEY"] = getpass.getpass("Tavily API Key: ").strip()
    if "OPENAI_API_KEY" in missing:
        values["LLM_API_KEY"] = getpass.getpass("LLM API Key / OpenAI API Key (optional): ").strip()
    base_url = input("LLM base URL [default OpenAI]: ").strip()
    if base_url:
        values["LLM_BASE_URL"] = base_url
    model = input("News Agent model [gpt-4o-mini]: ").strip()
    if model:
        values["LLM_MODEL_ID"] = model
    if any(values.values()):
        path = save_user_config(values)
        print(f"Configuration saved to: {path}")
    return load_config()


def print_config_status(config: AppConfig | None = None) -> None:
    config = config or load_config()
    print(
        {
            "project_env": str(PROJECT_ENV_PATH),
            "user_config": str(USER_CONFIG_PATH),
            "tavily_api_key": "set" if config.tavily_api_key else "missing",
            "llm_api_key": "set" if config.openai_api_key else "missing",
            "llm_base_url": config.openai_base_url or "default OpenAI",
            "news_agent_model": config.news_agent_model,
            "llm_timeout": config.llm_timeout,
            "akshare_cache_ttl": config.akshare_cache_ttl,
        }
    )
