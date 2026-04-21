# OSKAR — Structured Logging Configuration (P0-4)
# Implements: ai/memory/11-observability.md §2
#
# Call configure_logging() once at application startup (src/main.py).
# All modules must use: log = structlog.get_logger(__name__)
# Never use logging.getLogger() or print() in application code.

import logging
import os

import structlog


def configure_logging() -> None:
    """Configure structlog for the application.

    Production (ENVIRONMENT != "development"):
        JSON renderer → stdout → captured by Docker json-file logging driver.

    Development:
        ConsoleRenderer with colours → stdout for human readability.
    """
    environment = os.getenv("ENVIRONMENT", "production")
    is_development = environment == "development"

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _add_service_name,
    ]

    if is_development:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG if is_development else logging.INFO)

    # Silence noisy third-party loggers in production
    if not is_development:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def _add_service_name(
    logger: object, method_name: str, event_dict: dict
) -> dict:
    """Inject the service name into every log record (ai/memory/11 §2)."""
    import sys

    # oskar-worker when running under Celery, oskar-app otherwise
    if "celery" in sys.modules:
        event_dict.setdefault("service", "oskar-worker")
    else:
        event_dict.setdefault("service", "oskar-app")
    return event_dict
