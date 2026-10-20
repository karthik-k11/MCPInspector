import json
from typing import Any

from database import get_connection


def save_server(
    name: str,
    command: str,
    args: list[str],
    env: dict[str, str],
    timeout: float,
) -> int:
    """Save a server configuration without environment values."""
    with get_connection() as connection:
        existing = connection.execute(
            """
            SELECT id FROM servers
            WHERE name = ?
            """,
            (name,),
        ).fetchone()

        values = (
            command,
            json.dumps(args),
            json.dumps(sorted(env.keys())),
            timeout,
        )

        if existing:
            connection.execute(
                """
                UPDATE servers
                SET command = ?,
                    args_json = ?,
                    env_keys_json = ?,
                    timeout = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (*values, existing["id"]),
            )
            return existing["id"]

        cursor = connection.execute(
            """
            INSERT INTO servers (
                name, command, args_json, env_keys_json, timeout
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, *values),
        )

        return cursor.lastrowid


def _server_from_row(row: Any) -> dict[str, Any]:
    server = dict(row)
    server["args"] = json.loads(server.pop("args_json"))
    server["env_keys"] = json.loads(server.pop("env_keys_json"))
    return server


def get_servers() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, command, args_json,
                   env_keys_json, timeout, created_at, updated_at
            FROM servers
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()

    return [_server_from_row(row) for row in rows]


def get_server(server_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, name, command, args_json,
                   env_keys_json, timeout, created_at, updated_at
            FROM servers
            WHERE id = ?
            """,
            (server_id,),
        ).fetchone()

    return _server_from_row(row) if row is not None else None


def save_execution(
    server_id: int | None,
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: Any = None,
    status: str = "success",
    duration_ms: float | None = None,
    error_message: str | None = None,
) -> int:
    """Store one tool execution. Never persist raw exceptions by default."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO execution_history (
                server_id,
                server_name,
                tool_name,
                arguments_json,
                result_json,
                status,
                duration_ms,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                server_id,
                server_name,
                tool_name,
                json.dumps(arguments),
                json.dumps(result) if result is not None else None,
                status,
                duration_ms,
                error_message,
            ),
        )

        return cursor.lastrowid


def get_execution_history(limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 200))

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, server_name, tool_name, arguments_json,
                   result_json, status, duration_ms,
                   error_message, created_at
            FROM execution_history
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    history = []

    for row in rows:
        item = dict(row)
        item["arguments"] = json.loads(
            item.pop("arguments_json")
        )

        raw_result = item.pop("result_json")
        item["result"] = (
            json.loads(raw_result)
            if raw_result is not None
            else None
        )

        history.append(item)

    return history


def save_connection_attempt(
    server_id: int | None,
    server_name: str,
    command: str,
    status: str,
    duration_ms: float | None = None,
    error_message: str | None = None,
) -> int:
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO connection_history (
                server_id,
                server_name,
                command,
                status,
                duration_ms,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                server_id,
                server_name,
                command,
                status,
                duration_ms,
                error_message,
            ),
        )
        return cursor.lastrowid


def get_connection_history(limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 200))

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                server_id,
                server_name,
                command,
                status,
                duration_ms,
                error_message,
                created_at
            FROM connection_history
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]