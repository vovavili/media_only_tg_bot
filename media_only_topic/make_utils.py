"""A module for building utility functions.

This module contains functions that create a comprehensive stdlib logger and parse the dotenv file.
In order to allow for unit testing, "settings" and "logger" instances are created in another module.
"""

from __future__ import annotations

import datetime as dt
import html
import logging
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import IntEnum
from functools import cache, cached_property
from logging.handlers import RotatingFileHandler, SMTPHandler
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import EmailStr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType
    from typing import ClassVar

SMTP_PORT: Final = 587
ROOT_DIR: Final = Path(__file__).resolve().parents[1]


class FileHandlerConfig(IntEnum):
    """Constants for logging file handler in production.

    Attributes
    ----------
        MAX_BYTES: Maximum size of each log file in bytes (defaults to 10MB)
        BACKUP_COUNT: Number of backup files to keep (defaults to 5)

    """

    MAX_BYTES = 10 * 1024**2
    BACKUP_COUNT = 5


@cache
class Settings(BaseSettings):
    """Statically typed validator for your .env or .env.prod file.

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

    Caching avoids issues with unit testing by lazy evaluation. More information here:
    https://fastapi.tiangolo.com/advanced/settings/#creating-the-settings-only-once-with-lru_cache
    """

    cache_clear: ClassVar[Callable[[], None]]

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

    @cached_property
    def formats(self) -> dict[int, str]:
        """Get a dictionary of formats with proper ANSI codes for each logging level."""
        ending = "".join((self.INTENSITY, self.BASE_FORMAT, self.ESCAPE, self.RESET))
        return {
            level: "".join((self.ESCAPE, color, ending))
            for level, color in (
                (logging.DEBUG, self.GREY),
                (logging.INFO, self.GREY),
                (logging.WARNING, self.YELLOW),
                (logging.ERROR, self.RED),
                (logging.CRITICAL, self.RED + self.BOLD),
            )
        }

    def format(self, record: logging.LogRecord) -> str:
        """Format the specified record as text with appropriate color coding.

        This overwrites the parent 'format' method.
        """
        log_fmt = self.formats.get(record.levelno, self.BASE_FORMAT)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


# pylint: disable=too-few-public-methods
class DuplicateFilter(logging.Filter):
    """A logging filter that prevents duplicate log messages from being output.

    This is useful for something like htmx errors, which tend to repeat frequently.
    """

    def __init__(self, name: str = "") -> None:
        """Initialize a logging filter while keeping track of the last log."""
        self.last_log: tuple[str, int, str] | None = None
        super().__init__(name=name)

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter log records by checking for duplicates.

        Args:
        ----
            record: The log record to be evaluated.

        Returns:
        -------
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

    @cached_property
    def error_time(self) -> str:
        """Specify the same error time for both the subject line and the timestamp."""
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def getSubject(self, record: logging.LogRecord) -> str:
        """Customize the subject line to include the error level."""
        return f"Application {record.levelname} - {self.error_time}"

    def emit(self, record: logging.LogRecord) -> None:
        """Format the email in HTML and send it.

        This is a slight adaptation of SMTPHandler's own 'emit' method.
        """
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = self.getSubject(record)
            msg["From"] = self.fromaddr
            msg["To"] = ", ".join(self.toaddrs)

            # Prepare template variables
            exception_text: str | None = None
            if record.exc_info and self.formatter:  # Add check for self.formatter
                exception_text = self.formatter.formatException(record.exc_info)
                # Add this check to filter out "NoneType: None" exceptions (e.g. for htmx logs).
                if exception_text == "NoneType: None":
                    exception_text = None

            template_vars = {
                "timestamp": self.error_time,
                "level": record.levelname,
                "level_lower": record.levelname.lower(),
                "level_color": self.HEX_COLORS.get(record.levelname, self.GREEN_HEX),
                "logger_name": html.escape(record.name),
                "file_location": html.escape(f"{record.pathname}:{record.lineno}"),
                "message": html.escape(record.getMessage()),
                "exception_info": (
                    f"""<div class="detail-row">
                        <div class="detail-label">Exception</div>
                        <pre>{html.escape(exception_text)}</pre>
                    </div>"""
                    if exception_text is not None
                    else ""
                ),
            }

            template = Template(self.EMAIL_TEMPLATE_PATH.read_text(encoding="utf-8"))
            html_message = template.substitute(template_vars)

            part = MIMEText(html_message, "html")
            msg.attach(part)

            port = self.mailport or smtplib.SMTP_PORT

            # Send email
            with smtplib.SMTP(self.mailhost, port) as smtp:
                smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(msg)
        # pylint: disable=broad-except
        except Exception:  # noqa: BLE001
            self.handleError(record)


class CustomLogger(logging.Logger):
    """A logging system with highly desirable configurations.

    The logging system will have the following traits:
    - Color formatting in terminals
    - An ability to log exceptions without explicit try/except blocks

    The following traits apply only in production:
    - No info/debug messages
    - Rotating file handler
    - For critical errors, email notification with HTML formatting
    """

    def __init__(self, name: str = "main", pass_to_excepthook: bool = True) -> None:
        """Initialize the custom logging system.

        Arguments:
        ---------
            name: The name of the logger instance.
            pass_to_excepthook: Set script to log uncaught exceptions using this logger instance.

        """
        super().__init__(name)

        # Otherwise, you might get duplicate console handlers.
        self.handlers.clear()

        self.addFilter(DuplicateFilter())

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(ColorFormatter())
        handlers: list[logging.Handler] = [console_handler]

        settings = Settings()

        # In development, set higher logging level for httpx
        if settings.ENVIRONMENT == "development":
            self.setLevel(logging.INFO)
            logging.getLogger(name="httpx").setLevel(logging.WARNING)
        elif (
            settings.SMTP_HOST is None
            or settings.SMTP_USER is None
            or settings.SMTP_PASSWORD is None
        ):
            raise ValueError("All email environment variables are required in production.")
        else:
            self.setLevel(logging.ERROR)
            standard_formatter = logging.Formatter(ColorFormatter.BASE_FORMAT)

            file_handler = RotatingFileHandler(
                filename=ROOT_DIR / "export_log.log",
                mode="a",
                maxBytes=FileHandlerConfig.MAX_BYTES,
                backupCount=FileHandlerConfig.BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(standard_formatter)

            email_handler = HTMLEmailHandler(
                mailhost=(settings.SMTP_HOST, SMTP_PORT),
                fromaddr=settings.SMTP_USER,
                toaddrs=settings.SMTP_USER,
                subject="Application Error",
                credentials=(settings.SMTP_USER, settings.SMTP_PASSWORD.get_secret_value()),
                secure=(),  # This enables TLS
            )
            email_handler.setFormatter(standard_formatter)
            email_handler.setLevel(logging.CRITICAL)

            handlers.extend((file_handler, email_handler))

        for handler in handlers:
            self.addHandler(handler)

        if pass_to_excepthook:
            sys.excepthook = self.handle_exception

    def handle_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> Any:
        """Log all uncaught exceptions using this logger instance.

        We only log userspace exceptions (e.g. so a console Python program can exit with Ctrl + C).
        When passed to sys.excepthook, you have no need for an explicit try/except block.
        """
        if issubclass(exc_type, Exception):
            self.critical(
                "Encountered an uncaught exception.",
                exc_info=(exc_type, exc_value, exc_traceback),
            )
        else:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
