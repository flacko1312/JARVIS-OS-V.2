"""Sanitized, structured error reporting shared by runtime integrations."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import Enum


class ErrorCategory(str, Enum):
    AUTH = "auth"
    CONFIG = "config"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    RATE_LIMIT = "rate_limit"
    VALIDATION = "validation"
    INTERNAL = "internal"


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_ -]?key|token|authorization|secret|password)\b\s*[:=]\s*([^\s,;]+)"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bBearer\s+[0-9A-Za-z._~+/-]+", re.I),
)


def sanitize_diagnostic(value: object, limit: int = 500) -> str:
    text = str(value or "")
    text = _SECRET_PATTERNS[0].sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _SECRET_PATTERNS[1].sub("[REDACTED]", text)
    text = _SECRET_PATTERNS[2].sub("Bearer [REDACTED]", text)
    text = " ".join(text.split())
    return text[:limit]


def classify_exception(exc: BaseException, status: int | None = None) -> ErrorCategory:
    message = str(exc).casefold()
    if status in {401, 403} or any(term in message for term in ("unauthorized", "invalid_grant", "forbidden")):
        return ErrorCategory.AUTH
    if status == 429 or "rate limit" in message:
        return ErrorCategory.RATE_LIMIT
    if isinstance(exc, TimeoutError) or "timeout" in message or "timed out" in message:
        return ErrorCategory.TIMEOUT
    if isinstance(exc, (ConnectionError, ConnectionRefusedError)) or "unavailable" in message:
        return ErrorCategory.UNAVAILABLE
    if isinstance(exc, (ValueError, TypeError)):
        return ErrorCategory.VALIDATION
    return ErrorCategory.INTERNAL


@dataclass(frozen=True)
class ErrorReport:
    category: ErrorCategory
    operation: str
    correlation_id: str
    detail: str


def error_report(exc: BaseException, operation: str, *, status: int | None = None,
                 correlation_id: str | None = None) -> ErrorReport:
    return ErrorReport(
        category=classify_exception(exc, status),
        operation=sanitize_diagnostic(operation, 80),
        correlation_id=correlation_id or uuid.uuid4().hex[:12],
        detail=sanitize_diagnostic(exc),
    )
