"""
Structured logging + optional Sentry (P0.8).

Two pieces, both driven by env (see app/config.py):

- setup_logging(): installs a JSON formatter when LOG_FORMAT=json (so prod log
  aggregators — CloudWatch, Loki, Datadog — get parseable lines) or a readable
  text formatter otherwise (local dev). Replaces the bare logging.basicConfig.

- init_sentry(): a NO-OP unless SENTRY_DSN is set. We ship the hook now; the
  operator flips error tracking on later by setting the env var — no code change,
  no Sentry account required to run the app.
"""

import json
import logging
import sys
from datetime import datetime, timezone

# Attributes already present on every LogRecord — anything NOT in here that a
# caller attaches via logger.info(..., extra={...}) gets merged into the JSON line.
_STD_LOGRECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JSONFormatter(logging.Formatter):
    """One JSON object per log line. Includes structured `extra` fields verbatim."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _STD_LOGRECORD_ATTRS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging(log_format: str = "text", level: str = "INFO") -> None:
    """Configure the root logger. Idempotent — clears existing handlers first."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
    root.addHandler(handler)
    root.setLevel(level.upper())


def init_sentry(dsn: str, environment: str = "development") -> bool:
    """
    Initialize Sentry if a DSN is provided. Returns True if active, False if off.
    Import is lazy so the dependency is never touched when error tracking is disabled.
    """
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            # Errors only by default — no performance traces until we tune cost.
            traces_sample_rate=0.0,
            integrations=[FastApiIntegration()],
        )
        return True
    except Exception:  # pragma: no cover - defensive: never let telemetry crash boot
        logging.getLogger(__name__).exception("Sentry init failed — continuing without it")
        return False
