import asyncio

import pytest

from services import mcp_client


def test_inspect_server_rejects_empty_command():
    with pytest.raises(ValueError):
        mcp_client.inspect_server(
            command="",
            args=[],
            env={},
            timeout=15,
        )


def test_inspect_server_rejects_invalid_arguments():
    with pytest.raises(ValueError):
        mcp_client.inspect_server(
            command="python",
            args="invalid",
            env={},
            timeout=15,
        )


def test_inspect_server_rejects_invalid_environment():
    with pytest.raises(ValueError):
        mcp_client.inspect_server(
            command="python",
            args=[],
            env=[],
            timeout=15,
        )


def test_inspect_server_handles_timeout(monkeypatch):
    async def fake_inspection(*args, **kwargs):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(
        mcp_client,
        "_inspect_server",
        fake_inspection,
    )

    with pytest.raises(TimeoutError):
        mcp_client.inspect_server(
            command="python",
            args=[],
            env={},
            timeout=1,
        )


def test_inspect_server_handles_missing_executable(monkeypatch):
    async def fake_inspection(*args, **kwargs):
        raise FileNotFoundError("Executable not found")

    monkeypatch.setattr(
        mcp_client,
        "_inspect_server",
        fake_inspection,
    )

    with pytest.raises(FileNotFoundError):
        mcp_client.inspect_server(
            command="missing-mcp-server",
            args=[],
            env={},
            timeout=15,
        )


def test_execute_tool_rejects_non_dictionary_arguments():
    with pytest.raises(ValueError):
        mcp_client.execute_tool(
            command="python",
            args=[],
            env={},
            tool_name="add",
            arguments=["invalid"],
            timeout=15,
        )


def test_execute_tool_returns_result_and_duration(monkeypatch):
    async def fake_execution(*args, **kwargs):
        return {
            "content": [
                {"type": "text", "text": "5"}
            ],
            "isError": False,
        }

    monkeypatch.setattr(
        mcp_client,
        "_execute_tool",
        fake_execution,
    )

    result = mcp_client.execute_tool(
        command="python",
        args=[],
        env={},
        tool_name="add",
        arguments={"a": 2, "b": 3},
        timeout=15,
    )

    assert result["tool"] == "add"
    assert result["result"]["isError"] is False
    assert result["duration_ms"] >= 0


def test_execute_tool_propagates_execution_failure(monkeypatch):
    async def fake_execution(*args, **kwargs):
        raise RuntimeError("Simulated tool failure")

    monkeypatch.setattr(
        mcp_client,
        "_execute_tool",
        fake_execution,
    )

    with pytest.raises(RuntimeError, match="Simulated tool failure"):
        mcp_client.execute_tool(
            command="python",
            args=[],
            env={},
            tool_name="add",
            arguments={"a": 2, "b": 3},
            timeout=15,
        )