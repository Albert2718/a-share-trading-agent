from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class shared by every SQLAlchemy ORM model."""


settings = get_settings()
is_sqlite = settings.async_database_url.startswith("sqlite+")
engine = create_async_engine(
    settings.async_database_url,
    pool_pre_ping=not is_sqlite,
    connect_args={"timeout": 30} if is_sqlite else {},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


async def create_schema_for_development() -> None:
    """Create tables for an empty local development database.

    Production and shared environments must use Alembic migrations instead.
    """
    from app import models  # noqa: F401 - registers model metadata

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
