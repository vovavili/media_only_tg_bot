"""Create importable "settings" and "logger" instances.

Creating a logger instance instead of having a cached function also enables ruff's logging rules:
https://docs.astral.sh/ruff/rules/logging-exc-info/#known-problems
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.make_utils import get_logger, get_settings

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

logger = get_logger()
settings = get_settings()


async def error_handler(_: object, /, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors in an async way for the Telegram bot."""
    logger.error(context.error)
