import math

from services.diagnostics import (
    diagnose_connection_error,
    diagnose_execution_error,
    redact_secrets,
    validate_server_config,
)


def test_validate_server_config_rejects_invalid_fields():
    result = validate_server_config(
        command=None,
        args=["valid", None],
        env={"": "empty name", "BAD=NAME": "value"},
        timeout=math.nan,
    )

    assert result["valid"] is False
    assert {
        diagnostic["code"]
        for diagnostic in result["diagnostics"]
    } >= {
        "INVALID_COMMAND",
        "INVALID_ARGUMENT",
        "INVALID_ENV_NAME",
        "INVALID_TIMEOUT",
    }


def test_redact_secrets_recursively():
    secret = "private-token-123"
    value = {
        "message": f"Server returned {secret}",
        "nested": [{"content": secret}],
        "authorization": "Bearer other-secret",
    }

    assert redact_secrets(value, {"TOKEN": secret}) == {
        "message": "Server returned [REDACTED]",
        "nested": [{"content": "[REDACTED]"}],
        "authorization": "[REDACTED]",
    }


def test_diagnostics_explain_timeout_and_missing_executable():
    timeout = diagnose_connection_error(TimeoutError())
    missing = diagnose_connection_error(FileNotFoundError())
    tool_error = diagnose_execution_error(TimeoutError())

    assert timeout["code"] == "CONNECTION_TIMEOUT"
    assert "timeout" in timeout["message"].lower()
    assert missing["code"] == "EXECUTABLE_NOT_FOUND"
    assert "PATH" in missing["message"]
    assert tool_error["code"] == "TOOL_TIMEOUT"
