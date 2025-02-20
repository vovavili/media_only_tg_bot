"""Unit tests for the 'utils' module."""

from __future__ import annotations

import logging
import sys
import uuid
from collections.abc import Generator
from logging.handlers import RotatingFileHandler, SMTPHandler
from unittest.mock import MagicMock, patch

import pytest

from media_only_topic.make_utils import (
    ColorFormatter,
    CustomLogger,
    DuplicateFilter,
    FileHandlerConfig,
    Settings,
)
from tests.conftest import TEST_ERROR_MESSAGE, create_log_record


@pytest.fixture(autouse=True)
def fixture_reset_logging() -> Generator[None, None, None]:
    """Reset logging configuration before each test."""
    logger = logging.getLogger("main")
    # Store original handlers and excepthook
    original_handlers = logger.handlers.copy()
    original_excepthook = sys.excepthook
    # Clear all handlers
    logger.handlers.clear()
    yield
    # Restore to original state
    logger.handlers = original_handlers
    sys.excepthook = original_excepthook


def test_filehandler_config() -> None:
    """Test FileHandlerConfig enum values."""
    assert FileHandlerConfig.MAX_BYTES.value == 10 * 1024**2
    assert FileHandlerConfig.BACKUP_COUNT.value == 5


def test_color_formatter() -> None:
    """Test ColorFormatter functionality."""
    formatter = ColorFormatter()
    formats = formatter.formats

    # Test that all log levels have appropriate formats
    assert all(isinstance(fmt, str) for fmt in formats.values())
    assert all(ColorFormatter.ESCAPE in fmt for fmt in formats.values())
    assert all(ColorFormatter.RESET in fmt for fmt in formats.values())

    # Test specific colors for different levels
    assert ColorFormatter.RED in formats[logging.ERROR]
    assert ColorFormatter.YELLOW in formats[logging.WARNING]
    assert ColorFormatter.GREY in formats[logging.INFO]


def test_settings_development(settings: Settings) -> None:
    """Test settings in development environment."""
    assert settings.ENVIRONMENT == "development"
    assert settings.BOT_TOKEN.get_secret_value() == "test_token_123"
    assert settings.TOPIC_ID == 42
    assert settings.GROUP_CHAT_ID == 123456
    assert settings.SMTP_HOST is None
    assert settings.SMTP_USER is None
    assert settings.SMTP_PASSWORD is None


def test_settings_production(prod_settings: Settings) -> None:
    """Test settings in production environment."""
    assert prod_settings.ENVIRONMENT == "production"
    assert prod_settings.BOT_TOKEN.get_secret_value() == "live_token_xyz"
    assert prod_settings.TOPIC_ID == 100
    assert prod_settings.GROUP_CHAT_ID == 987654


@pytest.mark.usefixtures("settings")
def test_get_logger_development() -> None:
    """Test logger configuration in development environment."""
    logging.setLoggerClass(CustomLogger)
    logger = logging.getLogger(f"main_{uuid.uuid4()}")

    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)
    assert isinstance(logger.handlers[0].formatter, ColorFormatter)

    # Verify httpx logger level
    httpx_logger = logging.getLogger("httpx")
    assert httpx_logger.level == logging.WARNING


def test_get_logger_production_without_email(prod_settings: Settings) -> None:
    """Test logger fails in production without email settings."""
    logging.setLoggerClass(CustomLogger)
    with (
        patch("media_only_topic.make_utils.Settings", return_value=prod_settings),
        pytest.raises(
            ValueError, match="All email environment variables are required in production"
        ),
    ):
        _ = logging.getLogger(f"main_{uuid.uuid4()}")


def test_get_logger_production_with_email(email_settings: Settings) -> None:
    """Test logger configuration in production environment with email settings."""
    with (
        patch("media_only_topic.make_utils.Settings", return_value=email_settings),
        patch("media_only_topic.make_utils.RotatingFileHandler") as mock_file_handler,
        patch("media_only_topic.make_utils.HTMLEmailHandler") as mock_html_handler,
    ):
        # Configure mocks to return MagicMock instances
        mock_file_handler.return_value = MagicMock(spec=RotatingFileHandler)
        mock_html_handler.return_value = MagicMock(spec=SMTPHandler)

        logging.setLoggerClass(CustomLogger)
        logger = logging.getLogger(f"main_{uuid.uuid4()}")

        # Verify logger configuration
        assert logger.level == logging.ERROR
        assert len(logger.handlers) == 3

        # Verify handlers were created with correct configuration
        mock_file_handler.assert_called_once()
        file_handler_args = mock_file_handler.call_args[1]
        assert file_handler_args["maxBytes"] == FileHandlerConfig.MAX_BYTES
        assert file_handler_args["backupCount"] == FileHandlerConfig.BACKUP_COUNT

        mock_html_handler.assert_called_once()
        smtp_handler_args = mock_html_handler.call_args[1]
        assert smtp_handler_args["mailhost"] == (email_settings.SMTP_HOST, 587)
        assert smtp_handler_args["fromaddr"] == email_settings.SMTP_USER
        assert smtp_handler_args["toaddrs"] == email_settings.SMTP_USER
        assert smtp_handler_args["subject"] == "Application Error"


@pytest.mark.usefixtures("email_settings")
def test_exception_hook() -> None:
    """Test the custom exception hook logs uncaught exceptions."""
    logging.setLoggerClass(CustomLogger)
    logger = logging.getLogger(f"main_{uuid.uuid4()}")

    with patch.object(logger, "critical") as mock_critical:
        # Simulate an uncaught exception
        try:
            raise ValueError(TEST_ERROR_MESSAGE)
        except ValueError:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            assert exc_type is not None
            assert exc_value is not None
            sys.excepthook(exc_type, exc_value, exc_traceback)

        mock_critical.assert_called_once()
        assert "Encountered an uncaught exception" in mock_critical.call_args[0][0]


@pytest.mark.usefixtures("email_settings")
def test_keyboard_interrupt_handling() -> None:
    """Test that KeyboardInterrupt is handled specially."""
    logging.setLoggerClass(CustomLogger)
    logger = logging.getLogger("main")

    with (
        patch.object(logger, "critical") as mock_critical,
        patch("sys.__excepthook__") as mock_original_hook,
    ):
        # Simulate a KeyboardInterrupt
        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            assert exc_type is not None
            assert exc_value is not None
            sys.excepthook(exc_type, exc_value, exc_traceback)

        # Verify that critical wasn't called but original excepthook was
        mock_critical.assert_not_called()
        mock_original_hook.assert_called_once()


def test_formatter_format() -> None:
    """Test the format method of ColorFormatter."""
    formatter = ColorFormatter()
    record = create_log_record(level=logging.ERROR)

    formatted = formatter.format(record)
    assert ColorFormatter.ESCAPE in formatted
    assert ColorFormatter.RED in formatted
    assert ColorFormatter.RESET in formatted
    assert "Test message" in formatted


@pytest.fixture(name="duplicate_filter")
def fixture_duplicate_filter() -> DuplicateFilter:
    """Provide a fresh DuplicateFilter instance for each test."""
    return DuplicateFilter()


def test_duplicate_filter_initialization(duplicate_filter: DuplicateFilter) -> None:
    """Test that DuplicateFilter initializes with expected state."""
    assert duplicate_filter.last_log is None


def test_filter_allows_first_message(duplicate_filter: DuplicateFilter) -> None:
    """Test that the first message always passes through the filter."""
    record = create_log_record()
    assert duplicate_filter.filter(record) is True
    assert duplicate_filter.last_log == (record.module, record.levelno, record.getMessage())


def test_filter_blocks_duplicate_message(duplicate_filter: DuplicateFilter) -> None:
    """Test that duplicate messages are blocked."""
    record1 = create_log_record()
    record2 = create_log_record()  # Same parameters as record1

    duplicate_filter.filter(record1)  # First message
    assert duplicate_filter.filter(record2) is False  # Second identical message


def test_filter_allows_different_message(duplicate_filter: DuplicateFilter) -> None:
    """Test that different messages are allowed through."""
    record1 = create_log_record(msg="First message")
    record2 = create_log_record(msg="Second message")

    duplicate_filter.filter(record1)  # First message
    assert duplicate_filter.filter(record2) is True  # Different message


def test_filter_allows_same_message_different_level(duplicate_filter: DuplicateFilter) -> None:
    """Test that same message with different level is allowed through."""
    record1 = create_log_record(level=20)  # INFO
    record2 = create_log_record(level=40)  # ERROR

    duplicate_filter.filter(record1)
    assert duplicate_filter.filter(record2) is True


def test_filter_allows_same_message_different_module(duplicate_filter: DuplicateFilter) -> None:
    """Test that same message from different module is not allowed through."""
    record1 = create_log_record(module="module1")
    record2 = create_log_record(module="module2")

    duplicate_filter.filter(record1)
    assert duplicate_filter.filter(record2) is False


def test_filter_with_formatted_messages() -> None:
    """Test that filter works correctly with formatted messages."""
    duplicate_filter = DuplicateFilter()

    # Create records with format strings
    record1 = create_log_record(msg="User %s logged in", args=("Alice",))
    record2 = create_log_record(msg="User %s logged in", args=("Bob",))

    assert duplicate_filter.filter(record1) is True
    # Different formatted result, should be allowed
    assert duplicate_filter.filter(record2) is True


def test_filter_integration_with_logger(duplicate_filter: DuplicateFilter) -> None:
    """Test DuplicateFilter works when integrated with a logger."""
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.INFO)

    # Create a mock handler with a proper level attribute
    mock_handler = MagicMock(spec=logging.Handler)
    mock_handler.level = logging.INFO  # Set the handler level
    logger.addHandler(mock_handler)
    logger.addFilter(duplicate_filter)

    # Log some messages
    logger.info("Test message")  # Should be logged
    logger.info("Test message")  # Should be filtered out (duplicate)
    logger.info("Different message")  # Should be logged

    # Check that only non-duplicate messages were handled
    assert mock_handler.handle.call_count == 2

    # Verify the content of the messages that got through
    calls = mock_handler.handle.call_args_list
    assert calls[0][0][0].getMessage() == "Test message"
    assert calls[1][0][0].getMessage() == "Different message"
