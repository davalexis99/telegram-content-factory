"""
Retry decorator with exponential backoff.

Python concepts demonstrated here:
    1.  DECORATOR — `@retry(max_attempts=3)` wraps a function, adding
        retry logic without changing the function's own code.
    2.  *args / **kwargs — catch-all parameters that forward any arguments
        the wrapped function received, without knowing them in advance.
    3.  functools.wraps — preserves the original function's name and
        docstring so debugging tools still show the right name.

Exponential backoff means delays grow: 1s → 2s → 4s → 8s ...
This gives the remote service time to recover if it's temporarily down.

Example usage:
    @retry(max_attempts=3, exceptions=(httpx.HTTPError,))
    def call_api(url):
        ...
"""

import functools
import time
from collections.abc import Callable

from config.settings import MAX_RETRIES
from utils.logger import get_logger

logger = get_logger(__name__)


def retry(
    max_attempts: int = MAX_RETRIES,
    base_delay: float = 1.0,         # Starting delay in seconds
    backoff_factor: float = 2.0,     # Multiply delay by this each attempt
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """
    Return a decorator that retries a function on failure.

    Args:
        max_attempts:  Total tries before giving up (default 3).
        base_delay:    Seconds to wait before the first retry.
        backoff_factor: Multiply the delay by this after each failure.
        exceptions:    Tuple of exception types that trigger a retry.
                       (Exception,) = retry on ANY exception.

    Returns a decorator that can be applied with @retry() syntax.
    """

    # `decorator` is the function that receives the original function
    def decorator(func: Callable) -> Callable:
        # `wrapper` is the replacement function that adds retry logic
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    # Call the original function.  If it succeeds, return immediately.
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            "%s attempt %d/%d failed: %s. Retrying in %.1fs...",
                            func.__name__, attempt, max_attempts, e, delay,
                        )
                        time.sleep(delay)
                        delay *= backoff_factor  # Exponential growth

            # All attempts exhausted — re-raise the last exception
            raise last_exception  # type: ignore[misc]

        return wrapper
    return decorator
