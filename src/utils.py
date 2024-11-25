"""A module to create a comprehensive stdlib logger and parse the dotenv file."""

from __future__ import annotations

import datetime as dt
import smtplib
import logging
from enum import IntEnum
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from string import Template
from pathlib import Path
from logging.handlers import RotatingFileHandler, SMTPHandler
from functools import wraps, cache
from typing import Final, Literal, TYPE_CHECKING

from pydantic import EmailStr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from collections.abc import Callable

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

    GREY: Final = "38"
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
            level: "".join(
                (cls.ESCAPE, color, cls.INTENSITY, cls.BASE_FORMAT, cls.ESCAPE, cls.RESET)
            )
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


# pylint: disable=too-few-public-methods
class DuplicateFilter(logging.Filter):
    """A logging filter that prevents duplicate log messages from being output. Useful for
    something like htmx errors, which tend to repeat frequently."""

    def __init__(self) -> None:
        self.last_log: tuple[str, int, str] | None = None
        super().__init__()

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records by checking for duplicates.

        Args:
            record: The log record to be evaluated.

        Returns:
            bool: True if the message should be logged (is not a duplicate),
                 False if the message should be filtered out (is a duplicate).
        """
        # Get the formatted message instead of the raw format string
        current_log = (record.module, record.levelno, record.getMessage())
        if current_log == self.last_log:
            return False
        self.last_log = current_log
        return True


class HTMLEmailHandler(SMTPHandler):
    """Custom email handler that sends HTML-formatted emails."""

    GREEN_HEX: Final = "#28a745"
    RED_HEX: Final = "#dc3545"
    DARK_RED_HEX: Final = "#dc3545"
    YELLOW_HEX: Final = "#ffc107"

    HEX_COLORS: Final = {
        "ERROR": RED_HEX,
        "CRITICAL": DARK_RED_HEX,
        "WARNING": YELLOW_HEX,
    }

    EMAIL_TEMPLATE_PATH: Final = ROOT_DIR / "templates" / "error_email.html"

    @classmethod
    def load_template(cls) -> Template:
        """Load the HTML template from file."""
        if not cls.EMAIL_TEMPLATE_PATH.exists():
            raise FileNotFoundError(f"Email template not found at {cls.EMAIL_TEMPLATE_PATH}")
        return Template(cls.EMAIL_TEMPLATE_PATH.read_text(encoding="utf-8"))

    def getSubject(self, record: logging.LogRecord) -> str:
        """Customize the subject line to include the error level."""
        return f"Application {record.levelname} - {dt.datetime.now():%Y-%m-%d %H:%M:%S}"

    def emit(self, record: logging.LogRecord) -> None:
        """Format the email in HTML and send it. A slight adaptation of SMTPHandler's own
        'emit' method."""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = self.getSubject(record)
            msg["From"] = self.fromaddr
            msg["To"] = ", ".join(self.toaddrs)

            # Prepare template variables
            exception_text: str | None = None
            if record.exc_info and self.formatter:  # Add check for self.formatter
                exception_text = self.formatter.formatException(record.exc_info)

            template_vars = {
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "level": record.levelname,
                "level_lower": record.levelname.lower(),
                "level_color": self.HEX_COLORS.get(record.levelname, self.GREEN_HEX),
                "logger_name": record.name,
                "file_location": f"{record.pathname}:{record.lineno}",
                "message": record.getMessage(),
                "exception_info": (
                    f"<p><strong>Exception:</strong></p><pre>{exception_text}</pre>"
                    if exception_text is not None
                    else ""
                ),
            }

            # Load and render template
            template = self.load_template()
            html = template.substitute(template_vars)

            part = MIMEText(html, "html")
            msg.attach(part)

            port: int | None = self.mailport
            if port is None:
                port = smtplib.SMTP_PORT

            # Send email
            with smtplib.SMTP(self.mailhost, port) as smtp:
                smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(msg)
        # pylint: disable=broad-except
        except Exception:
            self.handleError(record)


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
    logger.addFilter(DuplicateFilter())

    # Create console handler with color formatting
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter())
    handlers: list[logging.Handler] = [console_handler]

    settings = get_settings()

    # In development, set higher logging level for httpx
    if settings.ENVIRONMENT == "development":
        logger.setLevel(logging.INFO)
        logging.getLogger(name="httpx").setLevel(logging.WARNING)
    elif settings.SMTP_HOST is None or settings.SMTP_USER is None or settings.SMTP_PASSWORD is None:
        raise ValueError("All email environment variables are required in production.")
    else:
        logger.setLevel(logging.ERROR)
        standard_formatter = logging.Formatter(ColorFormatter.BASE_FORMAT)

        # Create file handler with standard formatting
        file_handler = RotatingFileHandler(
            filename=ROOT_DIR / "export_log.log",
            mode="a",
            maxBytes=FileHandlerConfig.MAX_BYTES,
            backupCount=FileHandlerConfig.BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(standard_formatter)

        # Create email handler with standard formatting
        email_handler = HTMLEmailHandler(
            mailhost=(settings.SMTP_HOST, SMTP_PORT),
            fromaddr=settings.SMTP_USER,
            toaddrs=settings.SMTP_USER,
            subject="Application Error",
            credentials=(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value()),
            secure=(),  # This enables TLS
        )
        email_handler.setFormatter(standard_formatter)

        handlers.extend((file_handler, email_handler))

    # Remove any existing handlers and add new ones
    logger.handlers.clear()
    for handler in handlers:
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
