"""Exception classes for the AgentGraph SDK."""
from __future__ import annotations


class AgentGraphError(Exception):
    """Base exception for AgentGraph SDK errors."""

    def __init__(
        self, message: str,
        status_code: int | None = None,
        detail: str | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class AuthError(AgentGraphError):
    """Raised for authentication failures (401)."""
    pass


class NotFoundError(AgentGraphError):
    """Raised when a resource is not found (404)."""
    pass


class RateLimitError(AgentGraphError):
    """Raised when rate limit is exceeded (429)."""

    def __init__(
        self, message: str = "Rate limit exceeded",
        retry_after: int | None = None, **kwargs,
    ):
        self.retry_after = retry_after
        super().__init__(message, status_code=429, **kwargs)


class ValidationError(AgentGraphError):
    """Raised for invalid request parameters (422)."""
    pass


class DisputeError(AgentGraphError):
    """Raised for dispute-related errors."""
    pass


class ProtocolError(AgentGraphError):
    """Raised for AIP protocol errors."""
    pass


class EscrowError(AgentGraphError):
    """Raised for escrow/payment errors."""
    pass
