import json
import logging
import sys
from datetime import UTC, datetime

# Values passed with `extra={...}` that are copied into every JSON log line.
STRUCTURED_FIELDS = ("request_id", "method", "path", "status", "duration_ms")

_OURS = "_rms_handler"


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for log tools to search and filter."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in STRUCTURED_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Send application logs to stdout. Safe to call more than once."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _OURS, False):
            root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    setattr(handler, _OURS, True)
    handler.setFormatter(
        JsonFormatter()
        if fmt.lower() == "json"
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
