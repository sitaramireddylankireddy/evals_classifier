"""The only way the service writes to application logs.

Customer text must never reach the logs. `log_event` therefore accepts only
a fixed set of field names, which carry identifiers, positions, counts,
scores, and reason codes.
"""

import json
import logging
import re

ALLOWED_FIELDS = frozenset(
    {
        "item_id",
        "run_id",
        "chunk_id",
        "position",
        "reason",
        "field",
        "stage",
        "check",
        "count",
        "items",
        "issues",
        "evaluated",
        "passed",
        "failed",
        "not_evaluable",
        "escalated",
        "windows",
        "tokens",
        "score",
        "threshold",
        "seconds",
        "model",
        "revision",
        "status",
        "error_code",
    }
)

MAX_STRING_LENGTH = 200

_EVENT_NAME = re.compile(r"[a-z][a-z0-9_.]*")
_logger = logging.getLogger("evalsvc")


def log_event(
    event: str,
    *,
    level: int = logging.INFO,
    **fields: str | int | float | bool | None,
) -> None:
    if not _EVENT_NAME.fullmatch(event):
        raise ValueError("Event name must use lower-case letters, digits, dots, and underscores")

    unknown = sorted(set(fields) - ALLOWED_FIELDS)
    if unknown:
        raise ValueError(f"Field names not allowed in logs: {', '.join(unknown)}")

    for name, value in fields.items():
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise TypeError(f"Value of '{name}' must be text, a number, or a boolean")
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            raise ValueError(f"Value of '{name}' is too long to log")

    payload = {name: value for name, value in fields.items() if value is not None}
    _logger.log(level, "%s %s", event, json.dumps(payload, sort_keys=True))
