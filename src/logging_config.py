from __future__ import annotations

import logging
import sys

from src.config import settings


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging in production."""

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime, timezone

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        extra_fields = (
            "request_id", "path", "method", "status_code",
            "duration_ms", "client_ip", "entity_id",
        )
        for field in extra_fields:
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging() -> None:
    """Configure application logging. JSON format in production, standard in debug."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)

    if settings.debug:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
    else:
        handler.setFormatter(JSONFormatter())

    root.addHandler(handler)

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
