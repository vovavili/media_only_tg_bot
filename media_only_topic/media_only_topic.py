#!/usr/bin/env python3
"""A script for a Telegram bot that deletes non-photo material from a group chat topic."""

import logging
from collections.abc import Callable
from logging.handlers import RotatingFileHandler, SMTPHandler
from functools import lru_cache, wraps
from typing import Final, Literal

from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters
from pydantic import EmailStr, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_MESSAGE_TYPES: Final = (
    "photo",
    "video",
    "animation",
    "document",
    "video_note",
    "story",
    "sticker",
)
SMTP_PORT: Final = 587


class Settings(BaseSettings):
    """
    Please make sure your .env contains the following variables:
    - BOT_TOKEN - an API token for your bot.
    - TOPIC_ID - an ID for your group chat topic.
    - GROUP_CHAT_ID - an ID for your group chat.
    - ENVIRONMENT - if you intend on running this script on a VPS, this silences logging
        information there.

    Required only in production:

    - SMTP_HOST - SMTP server address (e.g., smtp.gmail.com)
    - SMTP_USER - Email username/address for SMTP authentication
    - SMTP_PASSWORD - Email password or app-specific password
    """

    ENVIRONMENT: Literal["production", "development"]

    # Telegram bot configuration
    BOT_TOKEN: SecretStr
    TOPIC_ID: int
    GROUP_CHAT_ID: int

    # Email configuration
    SMTP_HOST: str | None = None
    SMTP_USER: EmailStr | None = None
    # If you're using Gmail, this needs to be an app password
    SMTP_PASSWORD: SecretStr | None = None

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8")

    @field_validator("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
    @classmethod
    def validate_email_settings[T: str | SecretStr | None](cls, v: T, info: ValidationInfo) -> T:
        """We only email logging information on failure in production."""
        if info.data["ENVIRONMENT"] == "production" and v is None:
            raise ValueError(f"{info.field_name} is required in production.")
        return v


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

    console_handler = logging.StreamHandler()
    handlers: list[logging.Handler] = [console_handler]

    # In development, set higher logging level for httpx to avoid all GET and POST requests
    # being logged.
    if settings.ENVIRONMENT == "development":
        logging.getLogger("httpx").setLevel(logging.WARNING)
    # In production, disable logging information, note errors in a rotating file log, and
    # e-mail myself in case of an error.
    else:
        # mypy doesn't seem to detect a @field_validator (or a for-loop) for some reason
        if (
            settings.SMTP_HOST is None
            or settings.SMTP_USER is None
            or settings.SMTP_PASSWORD is None
        ):
            raise TypeError("All email environment variables are required in production.")
        console_handler.setLevel(logging.ERROR)

        file_handler = RotatingFileHandler(
            filename="../export_log.log",
            mode="a",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.ERROR)

        email_handler = SMTPHandler(
            mailhost=(settings.SMTP_HOST, SMTP_PORT),
            fromaddr=settings.SMTP_USER,
            toaddrs=settings.SMTP_USER,
            subject="Application Error",
            credentials=(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value()),
            # This enables TLS - https://docs.python.org/3/library/logging.handlers.html#smtphandler
            secure=(),
        )
        email_handler.setLevel(logging.ERROR)

        handlers.extend((file_handler, email_handler))

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
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


async def error_handler(_: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors in an async way."""
    get_logger().error(context.error)


async def only_media_messages(update: object, _: ContextTypes.DEFAULT_TYPE) -> None:
    """For a specific group chat topic, allow only media messages."""
    if not isinstance(update, Update):
        raise ValueError("Invalid update object passed to the handle.")

    message = update.message
    settings = get_settings()

    if not (
        # Check if message is in a chat and topic we care about
        message is None
        or message.chat.id != settings.GROUP_CHAT_ID
        or (not message.is_topic_message)
        or message.message_thread_id != settings.TOPIC_ID
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
    bot_token = get_settings().BOT_TOKEN.get_secret_value()
    application = Application.builder().token(bot_token).build()
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, only_media_messages))
    application.add_error_handler(error_handler)

    get_logger().info("Starting bot...")
    application.run_polling(allowed_updates=("message",))


if __name__ == "__main__":
    main()
