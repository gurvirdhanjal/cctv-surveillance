"""Structured log adapter that injects correlation fields.

Usage:
    from vms.observability.logging import get_logger
    logger = get_logger(__name__)
    logger.info("alert fired", camera_id=1, alert_id=42, seq_id=123)

The adapter converts keyword args to JSON `extra` fields, producing one-line
JSON log records when the root handler uses `logging.Formatter` with `%(message)s`.
In development (TTY / plain formatter), the extra fields are appended as k=v.
"""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any


class _ContextAdapter(logging.LoggerAdapter["logging.Logger"]):
    """Merges per-call kwargs into the log record's extra dict."""

    def process(
        self, msg: str, kwargs: MutableMapping[str, Any]
    ) -> tuple[str, MutableMapping[str, Any]]:
        extra = dict(self.extra or {})
        for key in list(kwargs.keys()):
            if key not in ("exc_info", "stack_info", "stacklevel"):
                extra[key] = kwargs.pop(key)
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str, **bound_fields: Any) -> _ContextAdapter:
    """Return a logger adapter with optional pre-bound correlation fields."""
    base = logging.getLogger(name)
    return _ContextAdapter(base, bound_fields)
