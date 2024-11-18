"""A module to create a comprehensive stdlib logger and parse the dotenv file."""

from __future__ import annotations

import logging
import sys
from enum import IntEnum, StrEnum
from collections.abc import Callable
from pathlib import Path
from logging.handlers import RotatingFileHandler, SMTPHandler
from functools import wraps, cache
from typing import Final, Literal

from telegram.ext import ContextTypes
from pydantic import EmailStr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SMTP_PORT: Final = 587
ROOT_DIR: Final = Path(__file__).resolve().parents[1]


class FileHandlerConfig(IntEnum):
    """
    Constants for logging file handler in production.

    Attributes:
        MAX_BYTES: Maximum size of each log file in bytes (defaults to 10MB)
        BACKUP_COUNT: Number of backup files to keep (defaults to 5)
    """

    MAX_BYTES = 10 * 1024**2
    BACKUP_COUNT = 5


class ANSICodes(StrEnum):
    """ANSI escape codes for terminal text formatting."""

    BOLD = "\033[1;"
    END = "m"
    ALL = "0"


class Settings(BaseSettings):
    """
    Please make sure your .env contains the following variables:
    - BOT_TOKEN - an API token for your bot.
    - TOPIC_ID - an ID for your group chat topic.
    - GROUP_CHAT_ID - an ID for your group chat.
    - ENVIRONMENT - if you intend on running this script on a VPS, this improves logging
        information in your production system.

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

    model_config = SettingsConfigDict(
        env_file=[(ROOT_DIR / e) for e in (".env", ".env.prod")],
        env_file_encoding="utf-8",
    )


@cache
def get_settings() -> Settings:
    """
    Avoid issues with unit testing by lazy evaluation.
    https://fastapi.tiangolo.com/advanced/settings/#creating-the-settings-only-once-with-lru_cache
    """
    return Settings()


@cache
def get_logger() -> logging.Logger:
    """
    Initialize the logging system with rotation capability.

    Returns:
        logging.Logger: The logger for the script.
    """
    console_handler = logging.StreamHandler()
    handlers: list[logging.Handler] = [console_handler]

    settings = get_settings()

    # In development, set higher logging level for httpx to avoid all GET and POST requests
    # being logged.
    if settings.ENVIRONMENT == "development":
        level = logging.INFO
        logging.getLogger(name="httpx").setLevel(logging.WARNING)
    elif settings.SMTP_HOST is None or settings.SMTP_USER is None or settings.SMTP_PASSWORD is None:
        raise ValueError("All email environment variables are required in production.")
    # In production, disable logging information, note errors in a rotating file log, and
    # e-mail myself in case of an error.
    else:
        level = logging.ERROR
        file_handler = RotatingFileHandler(
            filename=ROOT_DIR / "export_log.log",
            mode="a",
            maxBytes=FileHandlerConfig.MAX_BYTES,
            backupCount=FileHandlerConfig.BACKUP_COUNT,
            encoding="utf-8",
        )
        email_handler = SMTPHandler(
            mailhost=(settings.SMTP_HOST, SMTP_PORT),
            fromaddr=settings.SMTP_USER,
            toaddrs=settings.SMTP_USER,
            subject="Application Error",
            credentials=(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value()),
            # This enables TLS - https://docs.python.org/3/library/logging.handlers.html#smtphandler
            secure=(),
        )
        handlers.extend((file_handler, email_handler))

    # Adds color for terminal output only - https://stackoverflow.com/a/7995762/11010254
    if sys.stderr.isatty():
        for level in (logging.WARNING, logging.ERROR):
            logging.addLevelName(
                level,
                "".join(
                    (
                        ANSICodes.BOLD,
                        str(level + 1),
                        ANSICodes.END,
                        logging.getLevelName(level),
                        ANSICodes.BOLD,
                        ANSICodes.ALL,
                        ANSICodes.END,
                    )
                ),
            )

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )

    return logging.getLogger(name="main")


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


async def error_handler(_: object, /, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors in an async way."""
    get_logger().error(context.error)
