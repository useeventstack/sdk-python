"""Error types for the useEventStack Python SDK."""

from __future__ import annotations
from typing import Any


class UseEventStackError(Exception):
    """Base exception for all useEventStack SDK errors."""
    pass


class UseEventStackApiError(UseEventStackError):
    """Raised when the API returns a non-2xx response."""

    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f"[{status}] {code}: {message}")
