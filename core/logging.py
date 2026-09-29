"""
Structured JSON logging configuration.

Design note: structlog outputs JSON in production, readable key=value in
development. JSON logs are machine-parseable by Datadog, GCP Logging,
Splunk, etc. — critical for financial audit trails. Every log line has
a timestamp, level, logger name, and event. Context (application_id,
user_id) is bound per-request and automatically included in every log
call within that request.
"""

import logging
import sys

import structlog
from structlog.types import Processor

from core.config import settings


def configure_logging() -> None:
    """Call once at app startup."""

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.APP_ENV == "development":
        # Human-readable output for local development
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # Machine-parseable JSON for production / audit systems
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.AUDIT_LOG_LEVEL if hasattr(settings, "AUDIT_LOG_LEVEL") else "INFO")
