"""Structured logging configuration."""

import logging
import logging.config


def setup_logging() -> None:
    """Configure application-wide structured logging."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structured": {
                    "format": (
                        "%(asctime)s %(levelname)s [%(name)s] "
                        "request_id=%(request_id)s %(message)s"
                    ),
                    "defaults": {"request_id": "-"},
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "structured",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": "INFO",
                "handlers": ["console"],
            },
            "loggers": {
                # Quieten noisy third-party libraries.
                "uvicorn.access": {"level": "WARNING", "propagate": True},
                "sqlalchemy.engine": {"level": "WARNING", "propagate": True},
            },
        }
    )
