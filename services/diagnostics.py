import math
import re
import shutil
from typing import Any

_SENSITIVE_FIELDS = (
    "apikey",
    "token",
    "secret",
    "password",
    "authorization",
    "credential",
    "privatekey",
)


def redact_secrets(value: Any, env: dict[str, str]) -> Any:
    """Remove configured environment values from displayable or stored data."""
    env_values = env.values() if isinstance(env, dict) else ()
    secrets = sorted(
        (
            secret
            for secret in env_values
            if isinstance(secret, str) and secret
        ),
        key=len,
        reverse=True,
    )

    def redact(item: Any) -> Any:
        if isinstance(item, str):
            for secret in secrets:
                item = item.replace(secret, "[REDACTED]")
            return item
        if isinstance(item, dict):
            redacted = {}
            for key, child in item.items():
                normalized_key = re.sub(
                    r"[^a-z0-9]",
                    "",
                    str(key).lower(),
                )
                redacted[key] = (
                    "[REDACTED]"
                    if normalized_key.endswith(_SENSITIVE_FIELDS)
                    else redact(child)
                )
            return redacted
        if isinstance(item, list):
            return [redact(child) for child in item]
        if isinstance(item, tuple):
            return tuple(redact(child) for child in item)
        return item

    return redact(value)


def validate_server_config(
    command: str,
    args: list[str],
    env: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    """Validate an MCP server configuration before connection."""

    diagnostics = []

    if isinstance(command, str):
        command = command.strip()
    else:
        command = ""
        diagnostics.append({
            "level": "error",
            "code": "INVALID_COMMAND",
            "message": "Executable command must be text.",
        })

    if not command:
        diagnostics.append({
            "level": "error",
            "code": "EMPTY_COMMAND",
            "message": "No executable command was provided.",
        })

    elif not shutil.which(command):
        diagnostics.append({
            "level": "warning",
            "code": "COMMAND_NOT_RESOLVED",
            "message": (
                f"Command '{command}' was not resolved through PATH. "
                "The MCP server may still start if the command is "
                "handled by the operating system."
            ),
        })

    if not isinstance(args, list):
        diagnostics.append({
            "level": "error",
            "code": "INVALID_ARGUMENTS",
            "message": "Server arguments must be a list.",
        })
    elif any(
        not isinstance(argument, str) or "\x00" in argument
        for argument in args
    ):
        diagnostics.append({
            "level": "error",
            "code": "INVALID_ARGUMENT",
            "message": (
                "Server arguments must be strings without null bytes."
            ),
        })

    if not isinstance(env, dict):
        diagnostics.append({
            "level": "error",
            "code": "INVALID_ENVIRONMENT",
            "message": "Environment configuration must be an object.",
        })

    if isinstance(env, dict):
        for key, value in env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                diagnostics.append({
                    "level": "error",
                    "code": "INVALID_ENV_VALUE",
                    "message": (
                        "Environment variable names and values "
                        "must be strings."
                    ),
                })
                break

            if not key or "=" in key or "\x00" in key or "\x00" in value:
                diagnostics.append({
                    "level": "error",
                    "code": "INVALID_ENV_NAME",
                    "message": (
                        "Environment variable names must be non-empty "
                        "and cannot contain '=' or null bytes; values "
                        "cannot contain null bytes."
                    ),
                })
                break

    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or not math.isfinite(timeout)
    ):
        diagnostics.append({
            "level": "error",
            "code": "INVALID_TIMEOUT",
            "message": "Timeout must be a number.",
        })

    elif timeout < 1 or timeout > 120:
        diagnostics.append({
            "level": "error",
            "code": "TIMEOUT_OUT_OF_RANGE",
            "message": "Timeout must be between 1 and 120 seconds.",
        })

    if not diagnostics:
        diagnostics.append({
            "level": "success",
            "code": "CONFIG_VALID",
            "message": "Server configuration passed validation.",
        })

    return {
        "valid": not any(
            item["level"] == "error"
            for item in diagnostics
        ),
        "diagnostics": diagnostics,
        "command": command,
        "argument_count": len(args) if isinstance(args, list) else 0,
        "environment_keys": list(env.keys())
        if isinstance(env, dict)
        else [],
    }


def diagnose_connection_error(
    error: Exception,
) -> dict[str, Any]:
    """Convert a connection exception into a safe diagnostic."""

    error_type = type(error).__name__

    if isinstance(error, TimeoutError):
        message = (
            "The MCP server did not respond within the configured "
            "timeout. Check whether the server starts correctly "
            "and whether it is waiting for valid stdio input."
        )

        code = "CONNECTION_TIMEOUT"

    elif isinstance(error, FileNotFoundError):
        message = (
            "The MCP server executable could not be found. "
            "Check the command and PATH configuration."
        )

        code = "EXECUTABLE_NOT_FOUND"

    elif isinstance(error, PermissionError):
        message = (
            "The MCP server executable could not be started "
            "because of a permission restriction."
        )

        code = "PERMISSION_DENIED"

    elif isinstance(error, ValueError):
        message = str(error)
        code = "INVALID_CONFIGURATION"

    else:
        message = (
            "The MCP server failed during connection. "
            "Check the server command, arguments, environment, "
            "and startup output."
        )

        code = "CONNECTION_FAILED"

    return {
        "success": False,
        "code": code,
        "error_type": error_type,
        "message": message,
    }


def diagnose_execution_error(
    error: Exception,
) -> dict[str, Any]:
    """Convert a tool execution exception into a safe diagnostic."""

    error_type = type(error).__name__

    if isinstance(error, TimeoutError):
        code = "TOOL_TIMEOUT"
        message = (
            "The tool did not finish within the configured timeout."
        )

    elif isinstance(error, ValueError):
        code = "INVALID_TOOL_REQUEST"
        message = str(error)

    else:
        code = "TOOL_EXECUTION_FAILED"
        message = (
            "The MCP tool execution failed. "
            "Check the selected tool and JSON arguments."
        )

    return {
        "success": False,
        "code": code,
        "error_type": error_type,
        "message": message,
    }