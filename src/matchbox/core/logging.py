"""Structured logging for Matchbox.

The app held no logging configuration: orchestrator and CLI failures left no
timestamped, context-tagged trace (only ad-hoc print-to-stderr). This module
configures the ``matchbox`` logger tree once, at the CLI and web entry points,
so a run leaves a real trace tagged with run_id/job_id.

Quiet by default (WARNING) so a successful CLI run stays clean on stderr. Set
``MATCHBOX_LOG_LEVEL=INFO`` for the boundary traces, or ``MATCHBOX_LOG_JSON=1``
for one JSON object per line (log shipping). Only the ``matchbox`` tree is
touched, so uvicorn's and the root logger's handlers are left alone.
"""

from __future__ import annotations

import json
import logging
import os
import sys

_LOGGER_ROOT = "matchbox"
_configured = False


class _JsonFormatter(logging.Formatter):
    """One JSON object per line, for log shipping."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(*, force: bool = False) -> None:
    """Attach a stderr handler to the ``matchbox`` logger. Idempotent.

    Level comes from ``MATCHBOX_LOG_LEVEL`` (default WARNING); JSON output when
    ``MATCHBOX_LOG_JSON`` is set. Propagation is disabled so records do not also
    surface through the root/uvicorn handlers.
    """
    global _configured
    if _configured and not force:
        return
    level = os.environ.get("MATCHBOX_LOG_LEVEL", "WARNING").upper()
    logger = logging.getLogger(_LOGGER_ROOT)
    logger.setLevel(level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    if os.environ.get("MATCHBOX_LOG_JSON"):
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%H:%M:%S")
        )
    logger.addHandler(handler)
    logger.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """A logger under the configured ``matchbox`` tree. Pass ``__name__``."""
    return logging.getLogger(name)
