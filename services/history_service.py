import json

from database import get_connection


def save_server(name, command, args, env, timeout):
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


def get_servers():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, command, args_json,
                   env_keys_json, timeout, created_at, updated_at
            FROM servers
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()

    servers = []

    for row in rows:
        server = dict(row)
        server["args"] = json.loads(server.pop("args_json"))
        server["env_keys"] = json.loads(
            server.pop("env_keys_json")
        )
        servers.append(server)

    return servers


def save_execution(
    server_id,
    server_name,
    tool_name,
    arguments,
    result=None,
    status="success",
    duration_ms=None,
    error_message=None,
):
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


def get_execution_history(limit=50):
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