"""JSON-lines structured logging (constitution V).

Every line on stdout is one JSON object: ts, level, event, plus any
context fields passed via `jlog(...)` or `logger.info(event, extra=...)`.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

_LOGGER_NAME = "ambient_recorder"


class JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if fields:
            payload.update(fields)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonLinesFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def jlog(event: str, level: int = logging.INFO, **fields) -> None:
    """Emit one structured log line."""
    logging.getLogger(_LOGGER_NAME).log(level, event, extra={"fields": fields})
