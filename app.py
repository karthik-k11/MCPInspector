
import json
import logging
import time

from flask import Flask, render_template, request

from database import init_db
from services.diagnostics import (
    diagnose_connection_error,
    diagnose_execution_error,
    validate_server_config,
)
from services.history_service import (
    get_connection_history,
    get_execution_history,
    get_servers,
    save_connection_attempt,
    save_execution,
    save_server,
)
from services.mcp_client import execute_tool, inspect_server


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()


@app.get("/")
def index():
    return render_template(
        "index.html",
        server_name="",
        command="",
        args_text="[]",
        env_text="{}",
        timeout_text="15",
        result=None,
        error=None,
        diagnostics=None,
        execution=None,
        execution_error=None,
        execution_diagnostics=None,
        selected_tool="",
        tool_arguments_text="{}",
        servers=get_servers(),
        history=get_execution_history(),
        connection_history=get_connection_history(),
    )


@app.post("/connect")
def connect():
    server_name = request.form.get("server_name", "").strip()
    command = request.form.get("command", "").strip()
    args_text = request.form.get("args", "[]")
    env_text = request.form.get("env", "{}")
    timeout_text = request.form.get("timeout", "15")

    result = None
    error = None
    diagnostics = None
    server_id = None
    started_at = time.perf_counter()

    try:
        if not server_name:
            raise ValueError("Enter a server name.")

        args = json.loads(args_text)
        env = json.loads(env_text)
        timeout = float(timeout_text)

        diagnostics = validate_server_config(
            command=command,
            args=args,
            env=env,
            timeout=timeout,
        )

        if not diagnostics["valid"]:
            raise ValueError(
                "Server configuration contains errors."
            )

        # Save configuration without storing environment values.
        server_id = save_server(
            name=server_name,
            command=command,
            args=args,
            env=env,
            timeout=timeout,
        )

        result = inspect_server(
            command=command,
            args=args,
            env=env,
            timeout=timeout,
        )

        diagnostics["diagnostics"].append({
            "level": "success",
            "code": "CONNECTION_SUCCESS",
            "message": (
                "MCP server connected successfully and "
                "capabilities were discovered."
            ),
        })

    except json.JSONDecodeError:
        error = (
            "Invalid JSON. Check the arguments "
            "and environment fields."
        )

    except (TimeoutError, ValueError) as exc:
        error = str(exc)

        if isinstance(exc, TimeoutError) or diagnostics is None:
            diagnostics = diagnose_connection_error(exc)

    except Exception as exc:
        logger.warning(
            "MCP connection failed (%s).",
            type(exc).__name__,
        )
        error = "Connection failed. Check the server configuration."
        diagnostics = diagnose_connection_error(exc)

    # Persist both successful and failed connection attempts.
    duration_ms = round(
        (time.perf_counter() - started_at) * 1000,
        2,
    )

    connection_status = (
        "success" if result is not None and error is None
        else "error"
    )

    try:
        save_connection_attempt(
            server_id=server_id,
            server_name=server_name or "Unknown",
            command=command,
            status=connection_status,
            duration_ms=duration_ms,
            error_message=error,
        )
    except Exception as exc:
        logger.warning(
            "Could not save connection history (%s).",
            type(exc).__name__,
        )

    return render_template(
        "index.html",
        server_name=server_name,
        command=command,
        args_text=args_text,
        env_text=env_text,
        timeout_text=timeout_text,
        result=result,
        error=error,
        diagnostics=diagnostics,
        execution=None,
        execution_error=None,
        execution_diagnostics=None,
        selected_tool="",
        tool_arguments_text="{}",
        servers=get_servers(),
        history=get_execution_history(),
        connection_history=get_connection_history(),
    )


@app.post("/execute")
def execute():
    server_name = request.form.get("server_name", "").strip()
    command = request.form.get("command", "").strip()
    args_text = request.form.get("args", "[]")
    env_text = request.form.get("env", "{}")
    timeout_text = request.form.get("timeout", "15")
    tool_name = request.form.get("tool_name", "").strip()
    tool_arguments_text = request.form.get("tool_arguments", "{}")

    result = None
    error = None
    diagnostics = None
    execution = None
    execution_error = None
    execution_diagnostics = None

    args = []
    env = {}
    tool_arguments = {}
    timeout = 15
    server_id = None
    execution_result_for_history = None
    execution_duration_for_history = None

    try:
        if not server_name:
            raise ValueError("Enter a server name.")

        args = json.loads(args_text)
        env = json.loads(env_text)
        timeout = float(timeout_text)
        tool_arguments = json.loads(tool_arguments_text)

        if not isinstance(args, list):
            raise ValueError("Arguments must be a JSON array.")

        if not isinstance(env, dict):
            raise ValueError(
                "Environment variables must be a JSON object."
            )

        if not isinstance(tool_arguments, dict):
            raise ValueError(
                "Tool arguments must be a JSON object."
            )

        diagnostics = validate_server_config(
            command=command,
            args=args,
            env=env,
            timeout=timeout,
        )

        if not diagnostics["valid"]:
            raise ValueError(
                "Server configuration contains errors."
            )

        server_id = save_server(
            name=server_name,
            command=command,
            args=args,
            env=env,
            timeout=timeout,
        )

        # Reconnect and rediscover capabilities before execution.
        result = inspect_server(
            command=command,
            args=args,
            env=env,
            timeout=timeout,
        )

        # Only execute a tool advertised by this server.
        available_tools = {
            tool["name"] for tool in result["tools"]
        }

        if tool_name not in available_tools:
            raise ValueError(
                "The selected tool was not discovered on this server."
            )

        execution = execute_tool(
            command=command,
            args=args,
            env=env,
            tool_name=tool_name,
            arguments=tool_arguments,
            timeout=timeout,
        )

        execution_result_for_history = execution.get("result")
        execution_duration_for_history = execution.get("duration_ms")

        tool_result = execution_result_for_history

        # An MCP tool can return a protocol response that indicates
        # an application-level failure with isError=True.
        if (
            isinstance(tool_result, dict)
            and tool_result.get("isError") is True
        ):
            content = tool_result.get("content", [])

            error_details = " ".join(
                item["text"]
                for item in content
                if isinstance(item, dict)
                and isinstance(item.get("text"), str)
            ).strip()

            execution_error = (
                error_details
                or "The MCP tool returned isError=true."
            )

            execution_diagnostics = {
                "success": False,
                "code": "MCP_TOOL_ERROR",
                "message": execution_error,
            }

        else:
            save_execution(
                server_id=server_id,
                server_name=server_name,
                tool_name=tool_name,
                arguments=tool_arguments,
                result=execution_result_for_history,
                status="success",
                duration_ms=execution_duration_for_history,
            )

            execution_diagnostics = {
                "success": True,
                "code": "TOOL_EXECUTION_SUCCESS",
                "message": (
                    f"Tool '{tool_name}' executed successfully."
                ),
            }

    except json.JSONDecodeError:
        execution_error = (
            "Invalid JSON. Check the tool arguments "
            "and server configuration."
        )
        execution_diagnostics = {
            "success": False,
            "code": "INVALID_JSON",
            "message": execution_error,
        }

    except TimeoutError as exc:
        execution_error = str(exc)
        execution_diagnostics = diagnose_execution_error(exc)

    except ValueError as exc:
        execution_error = str(exc)
        execution_diagnostics = diagnose_execution_error(exc)

    except Exception as exc:
        logger.warning(
            "MCP tool execution failed (%s).",
            type(exc).__name__,
        )
        execution_error = "Tool execution failed."
        execution_diagnostics = diagnose_execution_error(exc)

    # Record failed executions, preserving any returned tool response.
    if (
        execution_error
        and tool_name
        and isinstance(tool_arguments, dict)
        and isinstance(args, list)
        and isinstance(env, dict)
    ):
        try:
            save_execution(
                server_id=server_id,
                server_name=server_name or "Unknown",
                tool_name=tool_name,
                arguments=tool_arguments,
                result=execution_result_for_history,
                status="error",
                duration_ms=execution_duration_for_history,
                error_message=execution_error,
            )
        except Exception as exc:
            logger.warning(
                "Could not save execution history (%s).",
                type(exc).__name__,
            )

    return render_template(
        "index.html",
        server_name=server_name,
        command=command,
        args_text=args_text,
        env_text=env_text,
        timeout_text=timeout_text,
        result=result,
        error=error,
        diagnostics=diagnostics,
        execution=execution,
        execution_error=execution_error,
        execution_diagnostics=execution_diagnostics,
        selected_tool=tool_name,
        tool_arguments_text=tool_arguments_text,
        servers=get_servers(),
        history=get_execution_history(),
        connection_history=get_connection_history(),
    )


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
    )