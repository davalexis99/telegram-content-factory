"""
Structured logger for the automation system.

Python concept: The `logging` module is Python's built-in way to emit
timestamped, leveled messages (DEBUG < INFO < WARNING < ERROR < CRITICAL).

Instead of `print()`, use `logger.info("something happened")`.
This gives you timestamps, severity levels, and the ability to
filter/suppress messages at different log levels per module.

Usage in other modules:
    from utils.logger import get_logger
    logger = get_logger(__name__)    # __name__ = "services.openai_service" etc.
    logger.info("Connected to DeepSeek")
"""

import logging
import sys

from config.settings import LOG_LEVEL


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger for the given module name.

    `name` is usually __name__ from the calling module, which produces
    log lines like:
        2026-06-22 13:00:00 | INFO     | services.openai_service | Connected
         ^timestamp^       ^level^       ^module name^              ^message^

    The `if not logger.handlers` guard prevents adding duplicate handlers
    if the function is called multiple times for the same name.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(LOG_LEVEL)
    return logger
