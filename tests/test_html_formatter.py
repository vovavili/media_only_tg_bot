"""Unit tests for the HTML formatter, for the logger in the 'utils' module."""

from __future__ import annotations

import datetime as dt
import logging
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from logging.handlers import RotatingFileHandler
from pathlib import Path
from string import Template
from types import TracebackType
from unittest.mock import MagicMock, patch

import pytest

from src.utils import (
    SMTP_PORT,
    ColorFormatter,
    DuplicateFilter,
    HTMLEmailHandler,
    Settings,
    get_logger,
)
from tests.conftest import create_log_record

type ExcType = tuple[type[BaseException], BaseException, TracebackType] | tuple[None, None, None]


@pytest.fixture(name="html_email_handler")
def fixture_html_email_handler(email_settings: Settings) -> HTMLEmailHandler:
    """Provide a configured HTMLEmailHandler instance."""
    assert (
        email_settings.SMTP_HOST is not None
        and email_settings.SMTP_USER is not None
        and email_settings.SMTP_PASSWORD is not None
    )
    return HTMLEmailHandler(
        mailhost=(email_settings.SMTP_HOST, 587),
        fromaddr=email_settings.SMTP_USER,
        toaddrs=[email_settings.SMTP_USER],
        subject="Test Email",
        credentials=(
            email_settings.SMTP_USER,
            email_settings.SMTP_PASSWORD.get_secret_value(),
        ),
        secure=(),
    )


@pytest.fixture(name="email_template")
def fixture_email_template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary email template file."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    template_file = template_dir.joinpath("error_email.html")

    template_content = """
    <div>
        <p>Timestamp: ${timestamp}</p>
        <p>Level: <span style="color: ${level_color}">${level}</span></p>
        <p>Logger: ${logger_name}</p>
        <p>Location: ${file_location}</p>
        <p>Message: ${message}</p>
        ${exception_info}
    </div>
    """
    template_file.write_text(template_content)

    # Use monkeypatch to override the class attribute
    monkeypatch.setattr(HTMLEmailHandler, "EMAIL_TEMPLATE_PATH", template_file)

    return template_file


def test_html_email_handler_colors() -> None:
    """Test color constants and mapping in HTMLEmailHandler."""
    assert HTMLEmailHandler.GREEN_HEX == "#28a745"
    assert HTMLEmailHandler.RED_HEX == "#dc3545"
    assert HTMLEmailHandler.YELLOW_HEX == "#ffc107"

    assert HTMLEmailHandler.HEX_COLORS["ERROR"] == HTMLEmailHandler.RED_HEX
    assert HTMLEmailHandler.HEX_COLORS["WARNING"] == HTMLEmailHandler.YELLOW_HEX


@pytest.mark.usefixtures("email_template")
def test_load_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test template loading functionality."""
    # Test with valid template
    template = HTMLEmailHandler.load_template()
    assert isinstance(template, Template)

    # Test with non-existent template
    monkeypatch.setattr(HTMLEmailHandler, "EMAIL_TEMPLATE_PATH", Path("nonexistent.html"))
    with pytest.raises(FileNotFoundError):
        HTMLEmailHandler.load_template()


def test_email_subject_formatting(html_email_handler: HTMLEmailHandler) -> None:
    """Test email subject line formatting."""
    record = create_log_record(level=logging.ERROR)

    subject = html_email_handler.getSubject(record)
    assert "Application ERROR" in subject
    assert dt.datetime.now().strftime("%Y-%m-%d") in subject


@pytest.mark.usefixtures("email_template")
def test_email_emission(html_email_handler: HTMLEmailHandler) -> None:
    """Test email emission process."""
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    with patch("smtplib.SMTP") as mock_smtp:
        # Configure mock SMTP instance
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        # Add formatter to handler
        html_email_handler.setFormatter(logging.Formatter())

        # Emit the record
        html_email_handler.emit(record)

        # Verify SMTP interactions
        mock_smtp.assert_called_once_with(html_email_handler.mailhost, html_email_handler.mailport)
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once()
        mock_smtp_instance.send_message.assert_called_once()

        # Verify email content
        sent_message = mock_smtp_instance.send_message.call_args[0][0]
        assert isinstance(sent_message, MIMEMultipart)
        assert "Test message" in str(sent_message)


def test_email_with_exception(html_email_handler: HTMLEmailHandler) -> None:
    """Test email formatting with exception information."""
    # Otherwise, pylint and mypy get confused
    exc_info: ExcType = (None, None, None)
    try:
        raise ValueError("Test exception")
    except ValueError:
        exc_info = sys.exc_info()

    # Create the record with the captured exception info
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message with exception",
        args=(),
        exc_info=exc_info,
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        html_email_handler.setFormatter(logging.Formatter())
        html_email_handler.emit(record)

        sent_message = mock_smtp_instance.send_message.call_args[0][0]
        message_str = str(sent_message)
        assert "Test message with exception" in message_str
        assert "ValueError: Test exception" in message_str
        assert "Traceback" in message_str


def test_email_handler_error_handling(html_email_handler: HTMLEmailHandler) -> None:
    """Test error handling in email emission."""
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    with (
        patch("smtplib.SMTP", side_effect=smtplib.SMTPException("Test SMTP error")),
        patch.object(html_email_handler, "handleError") as mock_handle_error,
    ):
        html_email_handler.emit(record)
        mock_handle_error.assert_called_once_with(record)


def test_email_handler_default_port(email_settings: Settings) -> None:
    """Test that email handler uses default SMTP port when 'mailport' is None."""
    assert (
        email_settings.SMTP_HOST is not None
        and email_settings.SMTP_USER is not None
        and email_settings.SMTP_PASSWORD is not None
    )
    # Create handler without specifying port
    handler = HTMLEmailHandler(
        mailhost=email_settings.SMTP_HOST,  # Note: not passing as tuple
        fromaddr=email_settings.SMTP_USER,
        toaddrs=[email_settings.SMTP_USER],
        subject="Test Email",
        credentials=(
            email_settings.SMTP_USER,
            email_settings.SMTP_PASSWORD.get_secret_value(),
        ),
        secure=(),
    )

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        handler.setFormatter(logging.Formatter())
        handler.emit(record)

        # Verify that default SMTP port was used
        mock_smtp.assert_called_once_with(handler.mailhost, smtplib.SMTP_PORT)


@pytest.mark.parametrize(
    "level_name,expected_color",
    [
        ("ERROR", HTMLEmailHandler.RED_HEX),
        ("CRITICAL", HTMLEmailHandler.DARK_RED_HEX),
        ("WARNING", HTMLEmailHandler.YELLOW_HEX),
        ("INFO", HTMLEmailHandler.GREEN_HEX),  # Default color
        ("DEBUG", HTMLEmailHandler.GREEN_HEX),  # Default color
    ],
)
def test_level_colors(
    html_email_handler: HTMLEmailHandler,
    level_name: str,
    expected_color: str,
) -> None:
    """Test that different log levels get the correct colors."""
    record = logging.LogRecord(
        name="test",
        level=getattr(logging, level_name),
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        html_email_handler.setFormatter(logging.Formatter())
        html_email_handler.emit(record)

        sent_message = mock_smtp_instance.send_message.call_args[0][0]
        message_str = str(sent_message)
        assert expected_color in message_str


@pytest.mark.usefixtures("email_template")
def test_integration_with_logger(
    email_settings: Settings,
) -> None:
    """Test HTMLEmailHandler integration with logger."""
    assert (
        email_settings.SMTP_HOST is not None
        and email_settings.SMTP_USER is not None
        and email_settings.SMTP_PASSWORD is not None
    )
    logger = logging.getLogger("test_html_logger")
    logger.setLevel(logging.ERROR)

    email_handler = HTMLEmailHandler(
        mailhost=(email_settings.SMTP_HOST, 587),
        fromaddr=email_settings.SMTP_USER,
        toaddrs=[email_settings.SMTP_USER],
        subject="Test Email",
        credentials=(
            email_settings.SMTP_USER,
            email_settings.SMTP_PASSWORD.get_secret_value(),
        ),
        secure=(),
    )
    email_handler.setFormatter(logging.Formatter())
    logger.addHandler(email_handler)

    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        # Test that ERROR messages trigger email
        logger.error("Test error message")
        assert mock_smtp_instance.send_message.called

        # Test that INFO messages don't trigger email
        mock_smtp_instance.reset_mock()
        logger.info("Test info message")
        assert not mock_smtp_instance.send_message.called


def test_template_variables(html_email_handler: HTMLEmailHandler) -> None:
    """Test all template variables are properly populated."""
    record = logging.LogRecord(
        name="test_logger",
        level=logging.ERROR,
        pathname="/path/to/test.py",
        lineno=42,
        msg="Test template message",
        args=(),
        exc_info=None,
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        html_email_handler.setFormatter(logging.Formatter())
        html_email_handler.emit(record)

        sent_message = mock_smtp_instance.send_message.call_args[0][0]
        message_str = str(sent_message)

        # Verify all template variables are present
        assert record.name in message_str
        assert record.levelname in message_str
        assert record.pathname in message_str
        assert str(record.lineno) in message_str
        assert record.getMessage() in message_str
        assert dt.datetime.now().strftime("%Y-%m-%d") in message_str
        assert html_email_handler.HEX_COLORS["ERROR"] in message_str


def test_mime_message_structure(html_email_handler: HTMLEmailHandler) -> None:
    """Test the structure of the MIME message."""
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        html_email_handler.setFormatter(logging.Formatter())
        html_email_handler.emit(record)

        sent_message = mock_smtp_instance.send_message.call_args[0][0]

        # Check message structure
        assert isinstance(sent_message, MIMEMultipart)
        assert sent_message.get_content_type() == "multipart/alternative"

        # Check headers
        assert "Subject" in sent_message
        assert "From" in sent_message
        assert "To" in sent_message

        # Check HTML part
        parts = list(sent_message.walk())
        html_part = next(p for p in parts if p.get_content_type() == "text/html")
        assert isinstance(html_part, MIMEText)
        assert "html" in html_part.get_content_type()


def test_smtp_connection_handling(html_email_handler: HTMLEmailHandler) -> None:
    """Test SMTP connection handling and security."""
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        html_email_handler.emit(record)

        # Verify SMTP connection handling
        mock_smtp.assert_called_once_with(html_email_handler.mailhost, html_email_handler.mailport)
        mock_smtp_instance.starttls.assert_called_once()

        # Verify authentication
        mock_smtp_instance.login.assert_called_once_with(
            html_email_handler.username,
            html_email_handler.password,
        )

        # Verify proper connection closure (context manager usage)
        mock_smtp.return_value.__exit__.assert_called_once()


@pytest.mark.parametrize(
    "exception_class",
    [
        smtplib.SMTPException,
        OSError,
        KeyError,
        ValueError,
        TypeError,
    ],
)
def test_error_handling_specific_exceptions(
    html_email_handler: HTMLEmailHandler,
    exception_class: type[Exception],
) -> None:
    """Test handling of specific exceptions during email emission."""
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    with (
        patch("smtplib.SMTP", side_effect=exception_class("Test error")),
        patch.object(html_email_handler, "handleError") as mock_handle_error,
    ):
        html_email_handler.emit(record)
        mock_handle_error.assert_called_once_with(record)


def test_production_logger_with_html_email(email_settings: Settings) -> None:
    """Test production logger configuration with HTML email handler."""
    assert email_settings.SMTP_PASSWORD is not None
    get_logger.cache_clear()

    with (
        patch("src.utils.RotatingFileHandler") as mock_file_handler,
        patch("src.utils.HTMLEmailHandler") as mock_email_handler,
    ):
        # Configure mocks
        mock_file_handler.return_value = MagicMock(spec=RotatingFileHandler)
        mock_email_handler.return_value = MagicMock(spec=HTMLEmailHandler)

        logger = get_logger()

        # Verify logger configuration
        assert logger.level == logging.ERROR
        assert len(logger.handlers) == 3  # Console, File, and Email handlers

        # Verify HTML email handler configuration
        mock_email_handler.assert_called_once_with(
            mailhost=(email_settings.SMTP_HOST, SMTP_PORT),
            fromaddr=email_settings.SMTP_USER,
            toaddrs=email_settings.SMTP_USER,
            subject="Application Error",
            credentials=(
                email_settings.SMTP_USER,
                email_settings.SMTP_PASSWORD.get_secret_value(),
            ),
            secure=(),
        )


def test_template_not_found(
    html_email_handler: HTMLEmailHandler,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test behavior when template file is not found."""
    # Use monkeypatch to set a non-existent template path
    monkeypatch.setattr(HTMLEmailHandler, "EMAIL_TEMPLATE_PATH", Path("nonexistent.html"))

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    with patch.object(html_email_handler, "handleError") as mock_handle_error:
        html_email_handler.emit(record)
        mock_handle_error.assert_called_once_with(record)


def test_template_substitution_error(html_email_handler: HTMLEmailHandler) -> None:
    """Test handling of template substitution errors."""
    # Create a template with an undefined variable
    template_content = "<div>${undefined_variable}</div>"

    with (
        patch.object(HTMLEmailHandler, "load_template") as mock_load_template,
        patch.object(html_email_handler, "handleError") as mock_handle_error,
    ):
        mock_load_template.return_value = Template(template_content)

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        html_email_handler.emit(record)
        mock_handle_error.assert_called_once_with(record)


def test_html_email_handler_integration_with_duplicate_filter() -> None:
    """Test HTMLEmailHandler works correctly with DuplicateFilter."""
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.ERROR)

    # Add DuplicateFilter
    duplicate_filter = DuplicateFilter()
    logger.addFilter(duplicate_filter)

    # Configure email handler with necessary attributes
    email_handler = MagicMock(spec=HTMLEmailHandler)
    email_handler.level = logging.ERROR  # Add the required level attribute
    logger.addHandler(email_handler)

    # Log duplicate messages
    logger.error("Test message")
    logger.error("Test message")  # Duplicate
    logger.error("Different message")

    # Verify only non-duplicate messages triggered email handler
    assert email_handler.handle.call_count == 2
    calls = email_handler.handle.call_args_list
    assert calls[0][0][0].getMessage() == "Test message"
    assert calls[1][0][0].getMessage() == "Different message"


def test_html_email_handler_with_color_formatter() -> None:
    """Test HTMLEmailHandler works correctly with ColorFormatter."""
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.ERROR)

    # Configure email handler with necessary attributes
    email_handler = MagicMock(spec=HTMLEmailHandler)
    email_handler.level = logging.ERROR
    formatter = ColorFormatter()
    email_handler.formatter = formatter

    # Mock both handle and emit methods
    mock_emit = MagicMock()
    email_handler.emit = mock_emit
    email_handler.handle = email_handler.emit

    logger.addHandler(email_handler)

    # Log the message
    test_message = "Test message"
    logger.error(test_message)

    # Verify the record was processed
    assert mock_emit.called
    emitted_record = mock_emit.call_args[0][0]
    assert isinstance(emitted_record, logging.LogRecord)
    formatted_message = formatter.format(emitted_record)
    assert ColorFormatter.RED in formatted_message
    assert test_message in formatted_message


def test_none_type_exception_handling(html_email_handler: HTMLEmailHandler) -> None:
    """Test that 'NoneType: None' exceptions are properly filtered out."""
    # Create a record with a None exception
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message with None exception",
        args=(),
        exc_info=(None, None, None),
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        html_email_handler.setFormatter(logging.Formatter())
        html_email_handler.emit(record)

        # Get the sent message
        sent_message = mock_smtp_instance.send_message.call_args[0][0]
        message_str = str(sent_message)

        # Verify that the exception section is not included
        assert "Exception:" not in message_str
        assert "NoneType: None" not in message_str

        # Verify that other parts of the message are still included
        assert "Test message with None exception" in message_str
        assert record.name in message_str
        assert record.levelname in message_str


def test_real_vs_none_exception_handling(html_email_handler: HTMLEmailHandler) -> None:
    """Test handling of both real and None exceptions."""
    # Create two records: one with a real exception and one with None
    exc_info: ExcType = (None, None, None)
    try:
        raise ValueError("Test exception")
    except ValueError:
        exc_info = sys.exc_info()

    real_exception_record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message with real exception",
        args=(),
        exc_info=exc_info,
    )

    none_exception_record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message with None exception",
        args=(),
        exc_info=(None, None, None),
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_smtp_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_smtp_instance

        html_email_handler.setFormatter(logging.Formatter())

        # Test real exception
        html_email_handler.emit(real_exception_record)
        real_message = str(mock_smtp_instance.send_message.call_args[0][0])
        assert "Exception:" in real_message
        assert "ValueError: Test exception" in real_message

        # Reset mock
        mock_smtp_instance.reset_mock()

        # Test None exception
        html_email_handler.emit(none_exception_record)
        none_message = str(mock_smtp_instance.send_message.call_args[0][0])
        assert "Exception:" not in none_message
        assert "NoneType: None" not in none_message
