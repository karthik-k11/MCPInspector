import json

import database
from services.history_service import (
    get_execution_history,
    get_servers,
    save_execution,
    save_server,
)


def test_database_initializes(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(db_path))

    database.init_db()

    assert db_path.exists()


def test_server_configuration_is_saved_without_env_values(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        database,
        "DATABASE_PATH",
        str(tmp_path / "test.db"),
    )
    database.init_db()

    server_id = save_server(
        name="Example",
        command="python",
        args=["server.py"],
        env={"API_KEY": "super-secret"},
        timeout=15,
    )

    servers = get_servers()

    assert server_id > 0
    assert len(servers) == 1
    assert servers[0]["name"] == "Example"
    assert servers[0]["args"] == ["server.py"]
    assert servers[0]["env_keys"] == ["API_KEY"]

    with database.get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM servers WHERE id = ?",
            (server_id,),
        ).fetchone()

    assert "super-secret" not in json.dumps(dict(row))


def test_execution_history_is_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database,
        "DATABASE_PATH",
        str(tmp_path / "test.db"),
    )
    database.init_db()

    server_id = save_server(
        "Example",
        "python",
        [],
        {},
        15,
    )

    save_execution(
        server_id=server_id,
        server_name="Example",
        tool_name="add",
        arguments={"a": 2, "b": 3},
        result={"content": [{"type": "text", "text": "5"}]},
        duration_ms=12.5,
    )

    history = get_execution_history()

    assert len(history) == 1
    assert history[0]["tool_name"] == "add"
    assert history[0]["arguments"] == {"a": 2, "b": 3}
    assert history[0]["status"] == "success"
    assert history[0]["duration_ms"] == 12.5


def test_server_with_same_name_is_updated(tmp_path, monkeypatch):
    monkeypatch.setattr(
        database,
        "DATABASE_PATH",
        str(tmp_path / "test.db"),
    )
    database.init_db()

    first_id = save_server("Example", "python", [], {}, 15)
    second_id = save_server(
        "Example",
        "python",
        ["updated_server.py"],
        {},
        20,
    )

    assert first_id == second_id

    servers = get_servers()
    assert len(servers) == 1
    assert servers[0]["args"] == ["updated_server.py"]
    assert servers[0]["timeout"] == 20