import os
import shutil
from typing import Any


def _mask_env(env: dict[str, str]) -> dict[str, str]:
    """Return environment keys without exposing their values."""
    return {
        key: "***"
        for key in env
    }


def validate_server_config(
    command: str,
    args: list[str],
    env: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    """Validate an MCP server configuration before connection."""

    diagnostics = []

    command = command.strip()

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

            if "\x00" in key or "\x00" in value:
                diagnostics.append({
                    "level": "error",
                    "code": "NULL_BYTE_ENV",
                    "message": (
                        "Environment variables cannot contain "
                        "null bytes."
                    ),
                })
                break

    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
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