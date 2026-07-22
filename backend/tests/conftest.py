import os
import sys
from pathlib import Path

import httpx
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-only-at-least-32-bytes")

from app.core.database import Base, get_db_session  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def app_context(tmp_path):
    settings = get_settings()
    previous_upload_dir = settings.upload_dir
    settings.upload_dir = str(tmp_path / "uploads")
    database_path = tmp_path / "app-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_session():
        async with session_maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            else:
                await session.commit()

    app.dependency_overrides[get_db_session] = override_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield {"client": client, "session_maker": session_maker}

    app.dependency_overrides.clear()
    settings.upload_dir = previous_upload_dir
    await engine.dispose()


async def register(client: httpx.AsyncClient, suffix: str = "one") -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{suffix}@example.com",
            "username": f"user_{suffix}",
            "password": "password123",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(auth: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth['access_token']}"}
