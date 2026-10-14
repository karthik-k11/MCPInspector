
import pytest

import app as app_module
import database


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_mcpinspector.db"

    monkeypatch.setattr(
        database,
        "DATABASE_PATH",
        str(db_path),
    )

    database.init_db()

    app_module.app.config.update(
        TESTING=True,
    )

    return app_module.app.test_client()


def fake_inspection(*args, **kwargs):
    return {
        "tools": [
            {
                "name": "add",
                "description": "Add two numbers",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                    "required": ["a", "b"],
                },
                "arguments": [
                    {"name": "a", "type": "integer", "required": True},
                    {"name": "b", "type": "integer", "required": True},
                ],
            }
        ],
        "resources": [],
        "prompts": [],
    }


def test_dashboard_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"MCPInspector" in response.data
    assert b"Saved Servers" in response.data
    assert b"Execution History" in response.data


def test_connect_saves_server(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        app_module,
        "inspect_server",
        fake_inspection,
    )

    response = client.post(
        "/connect",
        data={
            "server_name": "Test Server",
            "command": "python",
            "args": "[]",
            "env": "{}",
            "timeout": "15",
        },
    )

    assert response.status_code == 200
    assert b"CONNECTION_SUCCESS" in response.data
    assert b"Test Server" in response.data

    servers = app_module.get_servers()

    assert len(servers) == 1
    assert servers[0]["name"] == "Test Server"


def test_tool_execution_saves_successful_history(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        app_module,
        "inspect_server",
        fake_inspection,
    )

    monkeypatch.setattr(
        app_module,
        "execute_tool",
        lambda **kwargs: {
            "tool": "add",
            "duration_ms": 3.5,
            "result": {
                "content": [
                    {"type": "text", "text": "5"}
                ],
                "isError": False,
            },
        },
    )

    response = client.post(
        "/execute",
        data={
            "server_name": "Test Server",
            "command": "python",
            "args": "[]",
            "env": "{}",
            "timeout": "15",
            "tool_name": "add",
            "tool_arguments": '{"a": 2, "b": 3}',
        },
    )

    assert response.status_code == 200
    assert b"TOOL_EXECUTION_SUCCESS" in response.data
    assert b"3.5 ms" in response.data

    history = app_module.get_execution_history()

    assert len(history) == 1
    assert history[0]["tool_name"] == "add"
    assert history[0]["arguments"] == {"a": 2, "b": 3}
    assert history[0]["status"] == "success"


def test_tool_execution_rejects_unknown_tool(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        app_module,
        "inspect_server",
        fake_inspection,
    )

    response = client.post(
        "/execute",
        data={
            "server_name": "Test Server",
            "command": "python",
            "args": "[]",
            "env": "{}",
            "timeout": "15",
            "tool_name": "unknown_tool",
            "tool_arguments": "{}",
        },
    )

    assert response.status_code == 200
    assert b"selected tool was not discovered" in response.data.lower()

    history = app_module.get_execution_history()

    assert len(history) == 1
    assert history[0]["status"] == "error"


def test_tool_execution_records_failure(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        app_module,
        "inspect_server",
        fake_inspection,
    )

    def failing_execution(**kwargs):
        raise RuntimeError("Simulated server failure")

    monkeypatch.setattr(
        app_module,
        "execute_tool",
        failing_execution,
    )

    response = client.post(
        "/execute",
        data={
            "server_name": "Test Server",
            "command": "python",
            "args": "[]",
            "env": "{}",
            "timeout": "15",
            "tool_name": "add",
            "tool_arguments": '{"a": 2, "b": 3}',
        },
    )

    assert response.status_code == 200
    assert b"Tool execution failed" in response.data

    history = app_module.get_execution_history()

    assert len(history) == 1
    assert history[0]["status"] == "error"
    assert history[0]["tool_name"] == "add"