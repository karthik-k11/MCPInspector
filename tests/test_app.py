
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
    monkeypatch.setattr(app_module, "server_environments", {})

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


def connect_server(client, env="{}"):
    response = client.post(
        "/connect",
        data={
            "server_name": "Test Server",
            "command": "python",
            "args": "[]",
            "env": env,
            "timeout": "15",
        },
    )

    assert response.status_code == 200
    assert b"CONNECTION_SUCCESS" in response.data
    return app_module.get_servers()[0]["id"]


def test_dashboard_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"MCPInspector" in response.data
    assert b"Saved Servers" in response.data
    assert b"Execution History" in response.data
    assert b"connectionStatusFilter" in response.data
    assert b"executionStatusFilter" in response.data
    assert b"No tool executions recorded yet." in response.data


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
            "env": '{"API_KEY": "super-secret"}',
            "timeout": "15",
        },
    )

    assert response.status_code == 200
    assert b"CONNECTION_SUCCESS" in response.data
    assert b"Test Server" in response.data
    assert b"super-secret" not in response.data

    servers = app_module.get_servers()

    assert len(servers) == 1
    assert servers[0]["name"] == "Test Server"
    assert servers[0]["env_keys"] == ["API_KEY"]


def test_connection_failure_is_diagnosed_and_recorded(client, monkeypatch):
    def missing_server(*args, **kwargs):
        raise FileNotFoundError("secret-value")

    monkeypatch.setattr(
        app_module,
        "inspect_server",
        missing_server,
    )
    response = client.post(
        "/connect",
        data={
            "server_name": "Missing Server",
            "command": "missing-server",
            "args": "[]",
            "env": '{"API_KEY": "secret-value"}',
            "timeout": "15",
        },
    )

    history = app_module.get_connection_history()

    assert response.status_code == 200
    assert b"EXECUTABLE_NOT_FOUND" in response.data
    assert b"secret-value" not in response.data
    assert history[0]["status"] == "error"
    assert history[0]["error_message"] == (
        "Connection failed. Check the server configuration."
    )


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

    server_id = connect_server(client)
    response = client.post(
        "/execute",
        data={
            "server_id": str(server_id),
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

    server_id = connect_server(client)
    response = client.post(
        "/execute",
        data={
            "server_id": str(server_id),
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

    server_id = connect_server(client)
    response = client.post(
        "/execute",
        data={
            "server_id": str(server_id),
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

def test_tool_error_response_is_recorded_as_failure(client, monkeypatch):
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
            "duration_ms": 2.5,
            "result": {
                "content": [
                    {"type": "text", "text": "Invalid input"}
                ],
                "isError": True,
            },
        },
    )

    server_id = connect_server(client)
    response = client.post(
        "/execute",
        data={
            "server_id": str(server_id),
            "tool_name": "add",
            "tool_arguments": '{"a": 2, "b": 3}',
        },
    )

    assert response.status_code == 200

    history = app_module.get_execution_history()

    assert len(history) == 1
    assert history[0]["status"] == "error"
    assert "Invalid input" in history[0]["error_message"]
    assert history[0]["result"]["isError"] is True


def test_environment_values_are_redacted_from_tool_history(
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
            "duration_ms": 2.5,
            "result": {
                "content": [
                    {"type": "text", "text": "secret-value"}
                ],
                "isError": False,
            },
        },
    )

    server_id = connect_server(
        client,
        env='{"API_KEY": "secret-value"}',
    )
    response = client.post(
        "/execute",
        data={
            "server_id": str(server_id),
            "tool_name": "add",
            "tool_arguments": '{"input": "secret-value"}',
        },
    )

    history = app_module.get_execution_history()

    assert b"secret-value" not in response.data
    assert history[0]["arguments"] == {"input": "[REDACTED]"}
    assert history[0]["result"]["content"][0]["text"] == "[REDACTED]"


def test_execution_timeout_is_displayed_and_recorded(client, monkeypatch):
    monkeypatch.setattr(
        app_module,
        "inspect_server",
        fake_inspection,
    )

    def timed_out(**kwargs):
        raise TimeoutError("Tool execution timed out after 1 seconds.")

    monkeypatch.setattr(app_module, "execute_tool", timed_out)
    server_id = connect_server(client)
    response = client.post(
        "/execute",
        data={
            "server_id": str(server_id),
            "tool_name": "add",
            "tool_arguments": '{"a": 1, "b": 2}',
        },
    )

    history = app_module.get_execution_history()

    assert b"TOOL_TIMEOUT" in response.data
    assert b"timed out" in response.data.lower()
    assert history[0]["status"] == "error"
    assert history[0]["error_message"] == (
        "Tool execution timed out after 1 seconds."
    )
    assert history[0]["duration_ms"] is not None