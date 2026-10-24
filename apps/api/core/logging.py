"""Structured server logging without request bodies or authentication material."""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id.get(),
        }
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False)
