import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

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


def test_inspection_treats_unsupported_capabilities_as_empty(monkeypatch):
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def initialize(self):
            return None

        async def list_tools(self):
            return {"tools": []}

        async def list_resources(self):
            raise McpError(
                ErrorData(code=-32601, message="Method not found")
            )

        async def list_prompts(self):
            return {"prompts": []}

    @asynccontextmanager
    async def fake_stdio_client(server):
        yield object(), object()

    monkeypatch.setattr(mcp_client, "ClientSession", lambda *args: FakeSession())
    monkeypatch.setattr(mcp_client, "stdio_client", fake_stdio_client)

    assert mcp_client.inspect_server("python") == {
        "tools": [],
        "resources": [],
        "prompts": [],
    }


def test_local_demo_server_discovers_and_executes_tool():
    demo_server = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "demo_server.py"
    )
    args = [str(demo_server)]

    capabilities = mcp_client.inspect_server(
        command=sys.executable,
        args=args,
        env={},
        timeout=10,
    )

    assert [tool["name"] for tool in capabilities["tools"]] == ["add"]
    assert [resource["uri"] for resource in capabilities["resources"]] == [
        "demo://status"
    ]
    assert [prompt["name"] for prompt in capabilities["prompts"]] == [
        "explain"
    ]

    execution = mcp_client.execute_tool(
        command=sys.executable,
        args=args,
        env={},
        tool_name="add",
        arguments={"a": 2, "b": 3},
        timeout=10,
    )

    assert execution["result"]["isError"] is False
    assert any(
        item.get("text") == "5"
        for item in execution["result"]["content"]
    )