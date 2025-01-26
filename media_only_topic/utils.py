"""Create importable "settings" and "logger" instances.

Creating a logger instance instead of having a cached function also enables ruff's logging rules:
https://docs.astral.sh/ruff/rules/logging-exc-info/#known-problems
"""

from __future__ import annotations

import time
from functools import wraps
from typing import TYPE_CHECKING, overload

from media_only_topic.make_utils import Settings, get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

    from telegram.ext import ContextTypes

logger = get_logger()
settings = Settings()


async def error_handler(_: object, /, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors in an async way for the Telegram bot."""
    logger.error(context.error)


@overload
def retry[**P, R](
    function: None = None,
    /,
    *,
    retries: int = 1,
    retry_delay: int = 3,
    exception_type: type[Exception] | tuple[type[Exception], ...] = Exception,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


@overload
def retry[**P, R](
    function: Callable[P, R],
    /,
    *,
    retries: int = 1,
    retry_delay: int = 3,
    exception_type: type[Exception] | tuple[type[Exception], ...] = Exception,
) -> Callable[P, R]: ...


def retry[**P, R](
    function: Callable[P, R] | None = None,
    /,
    *,
    retries: int = 1,
    retry_delay: int = 3,
    exception_type: type[Exception] | tuple[type[Exception], ...] = Exception,
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
        exception_type (Exception type or a tuple of Exception types, optional): Narrow down
            on which exception types you would like to retry. Defaults to all exceptions.

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
            for attempt in range(retries + 1):
                try:
                    return func(*args, **kwargs)
                except exception_type as err:  # pylint: disable=broad-except
                    if attempt == retries:
                        raise type(err)(
                            f"Failed after {retries} retr{'y' if retries == 1 else 'ies'}."
                        ) from err
                    logger.exception(
                        "Retrying%s, attempt %s of %s.",
                        "" if not retry_delay else f" in {retry_delay} seconds",
                        attempt + 1,
                        retries,
                    )
                time.sleep(retry_delay)
            raise AssertionError("Unreachable.")

        return wrapper

    return decorator(function) if function is not None else decorator
