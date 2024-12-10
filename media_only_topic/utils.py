"""Create importable "settings" and "logger" instances.

Creating a logger instance instead of having a cached function also enables ruff's logging rules:
https://docs.astral.sh/ruff/rules/logging-exc-info/#known-problems
"""

from __future__ import annotations

import time
import traceback
from functools import wraps
from typing import TYPE_CHECKING, overload

from media_only_topic.make_utils import get_logger, get_settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from telegram.ext import ContextTypes

logger = get_logger()
settings = get_settings()


async def error_handler(_: object, /, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors in an async way for the Telegram bot."""
    logger.error(context.error)


@overload
def retry[**P, R](
    function: None = None, /, *, retries: int = 1, retry_delay: int = 3
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


@overload
def retry[**P, R](
    function: Callable[P, R], /, *, retries: int = 1, retry_delay: int = 3
) -> Callable[P, R]: ...


def retry[**P, R](
    function: Callable[P, R] | None = None, /, *, retries: int = 1, retry_delay: int = 3
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Create a decorator to retry function execution upon failure.

    This decorator will attempt to execute the decorated function multiple times
    if it raises an exception. Between attempts, it will wait for a specified
    delay period.

    Args:
        function (Callable, optional): The function to decorate when used without parameters.
        retries (int, optional): The maximum number of execution attempts. Defaults to 1.
        retry_delay (int, optional): The delay in seconds between retry attempts.
            Defaults to 3 seconds.

    Returns:
        Callable: A decorator function that wraps the original function with retry logic.

    """
    if retries < 1:
        raise ValueError("'retries' must be a natural number.")

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        """Inner decorator function that wraps the original function."""

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            """Implement a wrapper function with retry logic."""
            last_exception = Exception()
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as err:  # pylint: disable=broad-except
                    if attempt == retries:
                        last_exception = err
                    logger.exception(traceback.format_exc())
                time.sleep(retry_delay)
                logger.error("Retrying, attempt %s of %s.", attempt, retries)

            raise type(last_exception)(
                f"Failed after {retries} retr{'y' if retries == 1 else 'ies'}."
            ) from last_exception

        return wrapper

    return decorator(function) if function is not None else decorator
