"""Unit tests for the utilities module."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler, SMTPHandler
from unittest.mock import MagicMock, patch
from typing import Final, Generator, Never

import pytest

from src.utils import (
    ColorFormatter,
    FileHandlerConfig,
    Settings,
    get_logger,
    get_settings,
    log_error,
    error_handler,
)
from tests.conftest import TEST_ENV_VARS

TEST_ERROR_MESSAGE: Final = "Test error message"


@pytest.fixture(name="email_settings")
def fixture_email_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Set up production environment settings with email configuration."""
    test_env_vars = TEST_ENV_VARS | {
        "SMTP_HOST": "smtp.test.com",
        "SMTP_USER": "test@example.com",
        "SMTP_PASSWORD": "test_password",
    }
    for key, value in test_env_vars.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    return get_settings()


@pytest.fixture(autouse=True)
def fixture_reset_logging() -> Generator[None, None, None]:
    """Reset logging configuration before each test."""
    logger = logging.getLogger("main")
    # Store original handlers
    original_handlers = logger.handlers.copy()
    # Clear all handlers
    logger.handlers.clear()
    yield
    # Restore to original state
    logger.handlers = original_handlers


def test_filehandler_config() -> None:
    """Test FileHandlerConfig enum values."""
    assert FileHandlerConfig.MAX_BYTES.value == 10 * 1024**2
    assert FileHandlerConfig.BACKUP_COUNT.value == 5


def test_color_formatter() -> None:
    """Test ColorFormatter functionality."""
    formatter = ColorFormatter()
    formats = formatter.get_formats()

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
    get_logger.cache_clear()
    logger = get_logger()

    assert logger.level == logging.INFO
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.StreamHandler)
    assert isinstance(logger.handlers[0].formatter, ColorFormatter)

    # Verify httpx logger level
    httpx_logger = logging.getLogger("httpx")
    assert httpx_logger.level == logging.WARNING


@pytest.mark.usefixtures("prod_settings")
def test_get_logger_production_without_email() -> None:
    """Test logger fails in production without email settings."""
    get_logger.cache_clear()
    with pytest.raises(
        ValueError, match="All email environment variables are required in production"
    ):
        get_logger()


def test_get_logger_production_with_email(email_settings: Settings) -> None:
    """Test logger configuration in production environment with email settings."""
    get_logger.cache_clear()

    with (
        patch("src.utils.RotatingFileHandler") as mock_file_handler,
        patch("src.utils.SMTPHandler") as mock_smtp_handler,
    ):
        # Configure mocks to return MagicMock instances
        mock_file_handler.return_value = MagicMock(spec=RotatingFileHandler)
        mock_smtp_handler.return_value = MagicMock(spec=SMTPHandler)

        logger = get_logger()

        # Verify logger configuration
        assert logger.level == logging.ERROR
        assert len(logger.handlers) == 3

        # Verify handlers were created with correct configuration
        mock_file_handler.assert_called_once()
        file_handler_args = mock_file_handler.call_args[1]
        assert file_handler_args["maxBytes"] == FileHandlerConfig.MAX_BYTES
        assert file_handler_args["backupCount"] == FileHandlerConfig.BACKUP_COUNT

        mock_smtp_handler.assert_called_once()
        smtp_handler_args = mock_smtp_handler.call_args[1]
        assert smtp_handler_args["mailhost"] == (email_settings.SMTP_HOST, 587)
        assert smtp_handler_args["fromaddr"] == email_settings.SMTP_USER
        assert smtp_handler_args["toaddrs"] == email_settings.SMTP_USER
        assert smtp_handler_args["subject"] == "Application Error"


def test_log_error_decorator() -> None:
    """Test log_error decorator functionality."""
    get_logger.cache_clear()
    logger = get_logger()

    # Test successful function execution
    @log_error
    def success_func() -> str:
        return "success"

    assert success_func() == "success"

    # Test error logging
    @log_error
    def error_func() -> Never:
        raise ValueError(TEST_ERROR_MESSAGE)

    with (
        patch.object(logger, "error"),
        pytest.raises(ValueError, match=TEST_ERROR_MESSAGE),
    ):
        error_func()


@pytest.mark.asyncio
async def test_error_handler() -> None:
    """Test async error handler."""
    get_logger.cache_clear()
    logger = get_logger()

    # Create mock context with error
    mock_context = MagicMock()
    mock_context.error = ValueError(TEST_ERROR_MESSAGE)

    # Test error handling
    with patch.object(logger, "error") as mock_error:
        await error_handler(None, mock_context)
        mock_error.assert_called_once_with(mock_context.error)


def test_formatter_format() -> None:
    """Test the format method of ColorFormatter."""
    formatter = ColorFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    formatted = formatter.format(record)
    assert ColorFormatter.ESCAPE in formatted
    assert ColorFormatter.RED in formatted
    assert ColorFormatter.RESET in formatted
    assert "Test message" in formatted
