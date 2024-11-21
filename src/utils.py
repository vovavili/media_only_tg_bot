"""A module to create a comprehensive stdlib logger and parse the dotenv file."""

from __future__ import annotations

import logging
from enum import IntEnum
from collections.abc import Callable
from pathlib import Path
from logging.handlers import RotatingFileHandler, SMTPHandler
from functools import wraps, cache
from typing import Final, Literal, TYPE_CHECKING

from pydantic import EmailStr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

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


class ColorFormatter(logging.Formatter):
    """Formatter adding colors to console output."""

    GREY = "38"
    YELLOW: Final = "33"
    RED: Final = "31"
    BOLD: Final = ";1"
    ESCAPE: Final = "\x1b["
    RESET: Final = "0m"
    INTENSITY: Final = ";20m"

    BASE_FORMAT: Final = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    @classmethod
    def get_formats(cls) -> dict[int, str]:
        """Get a dictionary of formats with proper ANSI codes for each logging level."""
        return {
            level: cls.ESCAPE + color + cls.INTENSITY + cls.BASE_FORMAT + cls.ESCAPE + cls.RESET
            for level, color in (
                (logging.DEBUG, cls.GREY),
                (logging.INFO, cls.GREY),
                (logging.WARNING, cls.YELLOW),
                (logging.ERROR, cls.RED),
                (logging.CRITICAL, cls.RED + cls.BOLD),
            )
        }

    def format(self, record: logging.LogRecord) -> str:
        """Overwrite the parent 'format' method to format the specified record as text with
        appropriate color coding."""
        log_fmt = self.get_formats().get(record.levelno, self.BASE_FORMAT)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


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
    logger = logging.getLogger(name="main")
    logger.setLevel(logging.INFO)  # Set base level for logger

    # Create console handler with color formatting
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter())

    settings = get_settings()

    # In development, set higher logging level for httpx
    if settings.ENVIRONMENT == "development":
        logger.setLevel(logging.INFO)
        logging.getLogger(name="httpx").setLevel(logging.WARNING)
        logger.addHandler(console_handler)
        return logger
    if settings.SMTP_HOST is None or settings.SMTP_USER is None or settings.SMTP_PASSWORD is None:
        raise ValueError("All email environment variables are required in production.")
    logger.setLevel(logging.ERROR)

    # Create file handler with standard formatting
    file_handler = RotatingFileHandler(
        filename=ROOT_DIR / "export_log.log",
        mode="a",
        maxBytes=FileHandlerConfig.MAX_BYTES,
        backupCount=FileHandlerConfig.BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(ColorFormatter.BASE_FORMAT))

    # Create email handler with standard formatting
    email_handler = SMTPHandler(
        mailhost=(settings.SMTP_HOST, SMTP_PORT),
        fromaddr=settings.SMTP_USER,
        toaddrs=settings.SMTP_USER,
        subject="Application Error",
        credentials=(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value()),
        secure=(),
    )
    email_handler.setFormatter(logging.Formatter(ColorFormatter.BASE_FORMAT))

    # Remove any existing handlers and add new ones
    logger.handlers.clear()
    for handler in (console_handler, file_handler, email_handler):
        logger.addHandler(handler)

    return logger


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
