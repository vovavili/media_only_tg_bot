#!/usr/bin/env python3
"""A script for a Telegram bot that deletes non-photo material from a group chat topic."""

import logging
from collections.abc import Callable
from logging.handlers import RotatingFileHandler, SMTPHandler
from functools import lru_cache, wraps
from typing import Final, Literal

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_MESSAGE_TYPES: Final = (
    "photo",
    "video",
    "animation",
    "document",
)


class Settings(BaseSettings):
    """
    Please make sure your .env contains the following variables:
    - BOT_TOKEN - an API token for your bot.
    - TOPIC_ID - an ID for your group chat topic.
    - GROUP_CHAT_ID - an ID for your group chat.
    - ENVIRONMENT - if you intend on running this script on a VPS, this silences logging
        information there.
    - SMTP_HOST - SMTP server address (e.g., smtp.gmail.com)
    - SMTP_USER - Email username/address for SMTP authentication
    - SMTP_PASSWORD - Email password or app-specific password
    - EMAIL_FROM - Sender email address
    - EMAIL_RECIPIENTS - Comma-separated list of recipient email addresses
    """

    BOT_TOKEN: str
    TOPIC_ID: int
    GROUP_CHAT_ID: int
    ENVIRONMENT: Literal["production", "development"]

    # Email configuration
    SMTP_HOST: str
    SMTP_USER: str
    SMTP_PASSWORD: str
    EMAIL_FROM: str
    # Ellipsis marks a required field - https://docs.pydantic.dev/latest/concepts/models/#required-fields
    EMAIL_RECIPIENTS: list[str] = Field(..., json_schema_extra={"format": "comma_separated"})

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        # This will automatically convert comma-separated EMAIL_RECIPIENTS to a list
        json_schema_extra={"email_recipients_separator": ","},
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """This needs to be lazily evaluated, otherwise pytest gets a circular import."""
    return Settings()


@lru_cache(maxsize=1)
def get_logger(
    level: Literal[0, 10, 20, 30, 40, 50] = 20,  # defaults to logging.INFO
    logger_name: str = "main",
    max_bytes: int = 10 * 1024**2,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Initialize the logging system with rotation capability.
    This also needs to be lazily evaluated, otherwise pytest gets a circular import.

    Parameters:
        level: The logging level to use
        logger_name: The name to use for the logger (defaults to "main")
        max_bytes: Maximum size of each log file in bytes (defaults to 10MB)
        backup_count: Number of backup files to keep (defaults to 5)

    Returns:
        logging.Logger: The logger for the script.
    """
    settings = get_settings()

    # Add a rotating file log for errors and critical messages
    file_handler = RotatingFileHandler(
        filename="../export_log.log",
        mode="a",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.ERROR)

    console_handler = logging.StreamHandler()
    # I don't need to see logging information on my production machine
    console_handler.setLevel(
        logging.ERROR if settings.ENVIRONMENT == "production" else logging.DEBUG
    )

    email_handler = SMTPHandler(
        mailhost=settings.SMTP_HOST,
        fromaddr=settings.EMAIL_FROM,
        toaddrs=settings.EMAIL_RECIPIENTS,
        subject="Application Error",
        credentials=(settings.SMTP_USER, settings.SMTP_PASSWORD),
        # This enables TLS - https://docs.python.org/3/library/logging.handlers.html#smtphandler
        secure=(),
    )
    email_handler.setLevel(logging.ERROR)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=(console_handler, file_handler, email_handler),
    )

    return logging.getLogger(logger_name)


def log_error[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """A decorator to log an error in a function, in case it occurs."""

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except Exception as err:
            get_logger().error(err)
            raise err

    return wrapper


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors in an async way."""
    get_logger().error(context.error)


async def only_media_messages(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """For a specific group chat topic, allow only media messages."""
    if not isinstance(update, Update):
        raise ValueError("Invalid update object passed to the handle.")

    message = update.message

    if not (
        # Check if message is in a chat and topic we care about
        message is None
        or message.chat.id != get_settings().GROUP_CHAT_ID
        or (not message.is_topic_message)
        or message.message_thread_id != get_settings().TOPIC_ID
        # Check if message contains any allowed media types
        or any(getattr(message, msg_type, False) for msg_type in ALLOWED_MESSAGE_TYPES)
    ):
        await message.delete()
        get_logger().info(
            "Deleted message %s from user %s",
            message.message_id,
            message.from_user.username if message.from_user is not None else "",
        )


@log_error
def main() -> None:
    """Run the bot for a media-only topic."""
    application = Application.builder().token(get_settings().BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, only_media_messages))
    application.add_error_handler(error_handler)

    get_logger().info("Starting bot...")
    application.run_polling()


if __name__ == "__main__":
    main()
