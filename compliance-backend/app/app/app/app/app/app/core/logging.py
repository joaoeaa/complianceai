"""
Structured logging configuration using structlog.

In development: colored console output.
In production: JSON output (machine-readable).
"""
import logging
import structlog

from app.core.config import get_settings


def setup_logging() -> None:
    """Configure structlog for the application.

    Call this once at startup (in lifespan).
    """
    settings = get_settings()

    # Shared processors for both dev and prod
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if settings.DEBUG:
        # Dev: pretty colored console output
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # Prod: JSON lines for log aggregation (Datadog, CloudWatch, etc.)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.DEBUG else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "compliance") -> structlog.BoundLogger:
    """Get a named structlog logger instance.

    Args:
        name: Logger name for context.

    Returns:
        Bound structlog logger.
    """
    return structlog.get_logger(name)
