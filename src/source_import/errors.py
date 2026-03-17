"""Error hierarchy for source import operations."""
from __future__ import annotations


class SourceImportError(Exception):
    """Base exception for all source import failures."""


class UnsupportedSourceError(SourceImportError):
    """Raised when a URL does not match any known source pattern."""


class SourceFetchError(SourceImportError):
    """Raised when a fetch fails (network error, 404, timeout, etc.)."""


class SourceParseError(SourceImportError):
    """Raised when fetched data cannot be parsed into a SourceImportResult."""
