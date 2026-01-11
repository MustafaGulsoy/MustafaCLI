"""
Logging Configuration - Structured Logging with structlog
==========================================================

Production-grade logging infrastructure with structured logging,
log rotation, and multiple output formats.

Author: Mustafa (Kardelen Yazılım)
License: MIT
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any, Optional

import structlog
from structlog.types import EventDict, Processor

from .constants import (
    DEFAULT_LOG_FILE,
    DEFAULT_LOG_LEVEL,
    LOG_BACKUP_COUNT,
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    MAX_LOG_FILE_SIZE,
)


def add_app_context(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add application context to log entries."""
    event_dict["app"] = "local-agent-cli"
    return event_dict


def add_severity_level(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Add severity level field."""
    if method_name == "warn":
        event_dict["level"] = "WARNING"
    else:
        event_dict["level"] = method_name.upper()
    return event_dict


def censor_sensitive_data(
    logger: logging.Logger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Censor sensitive data in logs."""
    # List of keys to censor
    sensitive_keys = {"api_key", "token", "password", "secret", "authorization"}

    def _censor_dict(d: dict[str, Any]) -> dict[str, Any]:
        """Recursively censor dictionary values."""
        censored = {}
        for key, value in d.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                censored[key] = "***REDACTED***"
            elif isinstance(value, dict):
                censored[key] = _censor_dict(value)
            elif isinstance(value, list):
                censored[key] = [
                    _censor_dict(item) if isinstance(item, dict) else item for item in value
                ]
            else:
                censored[key] = value
        return censored

    return _censor_dict(event_dict)


def setup_logging(
    log_level: str = DEFAULT_LOG_LEVEL,
    log_file: Optional[str] = None,
    log_to_console: bool = True,
    json_logs: bool = False,
) -> None:
    """
    Setup structured logging with structlog.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional log file path (enables file logging)
        log_to_console: Enable console logging
        json_logs: Use JSON format for logs
    """
    # Determine log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout if log_to_console else None,
        level=numeric_level,
    )

    # Setup handlers
    handlers: list[logging.Handler] = []

    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        handlers.append(console_handler)

    if log_file:
        # Create log directory if needed
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=MAX_LOG_FILE_SIZE,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        handlers.append(file_handler)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    for handler in handlers:
        root_logger.addHandler(handler)

    # Structlog processors
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        add_app_context,
        add_severity_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt=LOG_DATE_FORMAT, utc=False),
        structlog.processors.StackInfoRenderer(),
        censor_sensitive_data,
    ]

    if json_logs:
        # JSON output for production
        processors.extend(
            [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ]
        )
    else:
        # Pretty console output for development
        processors.extend(
            [
                structlog.processors.format_exc_info,
                structlog.dev.ConsoleRenderer(colors=log_to_console),
            ]
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        structlog.stdlib.BoundLogger: Structured logger
    """
    return structlog.get_logger(name)


# Convenience function for quick setup
def configure_default_logging(
    debug: bool = False,
    log_file: Optional[str] = DEFAULT_LOG_FILE,
) -> None:
    """
    Configure logging with sensible defaults.

    Args:
        debug: Enable debug mode
        log_file: Optional log file path
    """
    level = "DEBUG" if debug else DEFAULT_LOG_LEVEL
    setup_logging(
        log_level=level,
        log_file=log_file,
        log_to_console=True,
        json_logs=False,
    )
