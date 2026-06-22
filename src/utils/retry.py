"""Retry decorator with exponential backoff."""

import functools
import time
from collections.abc import Callable

from config.settings import MAX_RETRIES
from utils.logger import get_logger

logger = get_logger(__name__)


def retry(
    max_attempts: int = MAX_RETRIES,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            "%s attempt %d/%d failed: %s. Retrying in %.1fs...",
                            func.__name__, attempt, max_attempts, e, delay,
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
            raise last_exception  # type: ignore[misc]
        return wrapper
    return decorator
