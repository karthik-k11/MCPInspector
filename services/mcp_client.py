import asyncio
import time
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)

    return getattr(obj, name, default)


def _serialize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)

    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def _summarize_tools(result: Any) -> list[dict[str, Any]]:
    tools = []

    for tool in _field(result, "tools", []) or []:
        schema = _field(
            tool,
            "inputSchema",
            _field(tool, "input_schema", {}),
        ) or {}

        properties = _field(schema, "properties", {}) or {}
        required = _field(schema, "required", []) or []

        tools.append(
            {
                "name": _field(tool, "name", "Unknown"),
                "description": _field(tool, "description", "") or "",
                "input_schema": _serialize(schema),
                "arguments": [
                    {
                        "name": name,
                        "type": _field(details, "type", "any"),
                        "required": name in required,
                        "description": _field(
                            details,
                            "description",
                            "",
                        )
                        or "",
                    }
                    for name, details in properties.items()
                ],
            }
        )

    return tools


def _summarize_resources(result: Any) -> list[dict[str, Any]]:
    resources = []

    for resource in _field(result, "resources", []) or []:
        resources.append(
            {
                "name": _field(resource, "name", ""),
                "uri": str(_field(resource, "uri", "")),
                "description": _field(resource, "description", "") or "",
                "mime_type": _field(resource, "mimeType", "") or "",
            }
        )

    return resources


def _summarize_prompts(result: Any) -> list[dict[str, Any]]:
    prompts = []

    for prompt in _field(result, "prompts", []) or []:
        prompts.append(
            {
                "name": _field(prompt, "name", ""),
                "description": _field(prompt, "description", "") or "",
                "arguments": _serialize(
                    _field(prompt, "arguments", []) or []
                ),
            }
        )

    return prompts


def _validate_inputs(
    command: str,
    args: list[str],
    env: dict[str, str],
    timeout: float,
) -> None:
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Enter an executable command.")

    if "\x00" in command:
        raise ValueError("The executable command cannot contain null bytes.")

    if not isinstance(args, list) or not all(
        isinstance(item, str) and "\x00" not in item for item in args
    ):
        raise ValueError(
            "Arguments must be strings and cannot contain null bytes."
        )

    if not isinstance(env, dict) or not all(
        isinstance(k, str)
        and isinstance(v, str)
        and k
        and "=" not in k
        and "\x00" not in k
        and "\x00" not in v
        for k, v in env.items()
    ):
        raise ValueError(
            "Environment variables must be valid string key-value pairs."
        )

    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        raise ValueError("Timeout must be a number.")

    if not 1 <= timeout <= 120:
        raise ValueError(
            "Timeout must be between 1 and 120 seconds."
        )


async def _list_optional_capability(
    session: ClientSession,
    method_name: str,
) -> Any:
    try:
        return await getattr(session, method_name)()
    except McpError as exc:
        if exc.error.code == -32601:
            return None
        raise


async def _inspect_server(
    command: str,
    args: list[str],
    env: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    server = StdioServerParameters(
        command=command,
        args=args,
        env=env or None,
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            await session.initialize()

            tools_result = await _list_optional_capability(
                session,
                "list_tools",
            )
            resources_result = await _list_optional_capability(
                session,
                "list_resources",
            )
            prompts_result = await _list_optional_capability(
                session,
                "list_prompts",
            )

            return {
                "tools": _summarize_tools(tools_result),
                "resources": _summarize_resources(resources_result),
                "prompts": _summarize_prompts(prompts_result),
            }


async def _execute_tool(
    command: str,
    args: list[str],
    env: dict[str, str],
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    server = StdioServerParameters(
        command=command,
        args=args,
        env=env or None,
    )

    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            await session.initialize()

            result = await session.call_tool(
                name=tool_name,
                arguments=arguments,
            )

            return _serialize(result)


def inspect_server(
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    timeout: float = 15,
) -> dict[str, list[dict[str, Any]]]:
    args = [] if args is None else args
    env = {} if env is None else env

    _validate_inputs(
        command,
        args,
        env,
        timeout,
    )

    try:
        return asyncio.run(
            asyncio.wait_for(
                _inspect_server(
                    command.strip(),
                    args,
                    env,
                ),
                timeout=timeout,
            )
        )

    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"The MCP server did not respond within "
            f"{timeout} seconds."
        ) from exc


def execute_tool(
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    tool_name: str = "",
    arguments: dict[str, Any] | None = None,
    timeout: float = 15,
) -> dict[str, Any]:
    args = [] if args is None else args
    env = {} if env is None else env
    arguments = {} if arguments is None else arguments

    _validate_inputs(
        command,
        args,
        env,
        timeout,
    )

    if not isinstance(tool_name, str) or not tool_name.strip():
        raise ValueError("Select a tool to execute.")

    if not isinstance(arguments, dict):
        raise ValueError(
            "Tool arguments must be a JSON object."
        )

    started = time.perf_counter()

    try:
        result = asyncio.run(
            asyncio.wait_for(
                _execute_tool(
                    command.strip(),
                    args,
                    env,
                    tool_name.strip(),
                    arguments,
                ),
                timeout=timeout,
            )
        )

    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"Tool execution timed out after "
            f"{timeout} seconds."
        ) from exc

    duration_ms = round(
        (time.perf_counter() - started) * 1000,
        2,
    )

    return {
        "tool": tool_name,
        "duration_ms": duration_ms,
        "result": result,
    }