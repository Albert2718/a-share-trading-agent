import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from app.core.config import get_settings
from app.core.database import Base


def test_legacy_tool_actions_receives_source_message_column(tmp_path: Path):
    database_path = tmp_path / "legacy.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE tool_actions")
        connection.exec_driver_sql(
            """
            CREATE TABLE tool_actions (
                id VARCHAR(36) NOT NULL PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                conversation_id VARCHAR(36) NOT NULL,
                message_id VARCHAR(36) NOT NULL UNIQUE,
                tool_name VARCHAR(128) NOT NULL,
                arguments JSON NOT NULL,
                status VARCHAR(20) NOT NULL,
                result JSON,
                expires_at DATETIME,
                confirmed_at DATETIME,
                completed_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
                FOREIGN KEY(message_id) REFERENCES messages (id) ON DELETE CASCADE
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "INSERT INTO alembic_version(version_num) VALUES ('20260722_0005')"
        )
    engine.dispose()

    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    get_settings.cache_clear()
    try:
        backend_root = Path(__file__).resolve().parents[1]
        config = Config(str(backend_root / "alembic.ini"))
        config.set_main_option("script_location", str(backend_root / "alembic"))
        command.upgrade(config, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        get_settings.cache_clear()

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(tool_actions)")
        }
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    assert "source_message_id" in columns
    assert version == "20260722_0006"
