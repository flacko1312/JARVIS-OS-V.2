import asyncio
from types import SimpleNamespace

import pytest

from actions.email_control import _gmail_api_error
from api.websocket_client import WebSocketClient
from core.error_reporting import ErrorCategory, classify_exception, error_report, sanitize_diagnostic


@pytest.mark.parametrize(
    "exc,status,category",
    [
        (TimeoutError("timed out"), None, ErrorCategory.TIMEOUT),
        (RuntimeError("invalid_grant"), 401, ErrorCategory.AUTH),
        (RuntimeError("rate limit"), 429, ErrorCategory.RATE_LIMIT),
        (ValueError("bad input"), None, ErrorCategory.VALIDATION),
        (RuntimeError("boom"), None, ErrorCategory.INTERNAL),
    ],
)
def test_error_classification(exc, status, category):
    assert classify_exception(exc, status) == category


def test_sanitizer_redacts_common_credentials():
    text = sanitize_diagnostic(
        "api_key=AIzaabcdefghijklmnopqrstuvwxyz token: abc123 Authorization=Bearer.Secret password=hunter2"
    )
    for secret in ("AIza", "abc123", "Bearer.Secret", "hunter2"):
        assert secret not in text
    assert "[REDACTED]" in text


def test_error_report_preserves_supplied_correlation_id():
    report = error_report(RuntimeError("token=secret"), "provider.call", correlation_id="turn-123")
    assert report.correlation_id == "turn-123"
    assert report.operation == "provider.call"
    assert "secret" not in report.detail


def test_gmail_error_is_categorized_and_sanitized():
    exc = RuntimeError("backend failed token=my-private-token")
    result = _gmail_api_error(exc, "message reading")
    assert "internal; reference" in result
    assert "my-private-token" not in result


def test_websocket_log_redacts_before_queuing():
    class Socket:
        async def send_json(self, _event):
            return None

    async def exercise():
        client = WebSocketClient(Socket())
        client.write_log("SYS: token=private-value")
        event = await client._events.get()
        assert "private-value" not in event["content"]
        assert "[REDACTED]" in event["content"]

    asyncio.run(exercise())
