from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = (PROJECT_ROOT / "data" / "app.db").as_posix()


class Settings(BaseSettings):
    app_name: str = "A-share Research Platform"
    app_env: Literal["development", "test", "production"] = "development"
    api_v1_prefix: str = "/api/v1"

    database_url: str = f"sqlite+aiosqlite:///{DEFAULT_DATABASE_PATH}"
    redis_url: str = "redis://127.0.0.1:6379/0"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "knowledge_chunks"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512
    chunk_size: int = 800
    chunk_overlap: int = 120
    max_upload_size_mb: int = 20
    upload_dir: str = str(PROJECT_ROOT / "data" / "uploads")

    jwt_secret_key: str = "change-this-before-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def async_database_url(self) -> str:
        return self.database_url

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("sqlite+aiosqlite", "sqlite", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
