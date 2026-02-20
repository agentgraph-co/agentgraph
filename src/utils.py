from __future__ import annotations


def escape_like(value: str) -> str:
    """Escape special LIKE/ILIKE characters (%, _, \\) in a search term."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_pattern(value: str) -> str:
    """Build a safe ILIKE pattern: ``%escaped_value%``."""
    return f"%{escape_like(value)}%"
