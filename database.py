import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import DATABASE_PATH


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    Path(DATABASE_PATH).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(DATABASE_PATH)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            yield connection
    finally:
        connection.close()


def init_db():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                command TEXT NOT NULL,
                args_json TEXT NOT NULL DEFAULT '[]',
                env_keys_json TEXT NOT NULL DEFAULT '[]',
                timeout INTEGER NOT NULL DEFAULT 15,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS execution_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER,
                server_name TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                status TEXT NOT NULL,
                duration_ms REAL,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (server_id)
                    REFERENCES servers(id)
                    ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS connection_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER,
                server_name TEXT NOT NULL,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                duration_ms REAL,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (server_id)
                    REFERENCES servers(id)
                    ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_connection_history_created_at
            ON connection_history(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_history_created_at
            ON execution_history(created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_history_server_id
            ON execution_history(server_id);
            """
        )