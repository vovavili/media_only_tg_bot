"""Unit tests for the utilities module."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler, SMTPHandler
from unittest.mock import MagicMock, patch
from typing import Final, Generator, Never

import pytest

from src.utils import (
    ANSICodes,
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
    root = logging.getLogger()
    # Store original handlers
    original_handlers = root.handlers.copy()
    # Clear all handlers
    root.handlers.clear()
    yield
    # Restore to original state
    root.handlers = original_handlers


def test_filehandler_config() -> None:
    """Test FileHandlerConfig enum values."""
    assert FileHandlerConfig.MAX_BYTES.value == 10 * 1024**2
    assert FileHandlerConfig.BACKUP_COUNT.value == 5


def test_ansi_codes() -> None:
    """Test ANSICodes enum values."""
    assert ANSICodes.BOLD.value == "\033[1;"
    assert ANSICodes.END.value == "m"
    assert ANSICodes.ALL.value == "0"


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

    with (
        patch("src.utils.RotatingFileHandler"),
        patch("src.utils.SMTPHandler"),
        patch("logging.basicConfig") as mock_basic_config,
    ):
        _ = get_logger()

        # Instead of checking handlers directly, verify basicConfig was called correctly
        mock_basic_config.assert_called_once()
        config_args = mock_basic_config.call_args[1]
        assert config_args["level"] == logging.INFO
        assert len(config_args["handlers"]) == 1
        assert isinstance(config_args["handlers"][0], logging.StreamHandler)

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
        patch("logging.basicConfig") as mock_basic_config,
    ):
        # Configure mocks to return MagicMock instances
        mock_file_handler.return_value = MagicMock(spec=RotatingFileHandler)
        mock_smtp_handler.return_value = MagicMock(spec=SMTPHandler)

        _ = get_logger()

        # Verify basicConfig was called correctly
        mock_basic_config.assert_called_once()
        config_args = mock_basic_config.call_args[1]
        assert config_args["level"] == logging.ERROR
        assert len(config_args["handlers"]) == 3

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


def test_ansi_colors_in_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test ANSI color codes are applied when in terminal."""
    get_logger.cache_clear()

    # Store original level names
    original_warning = logging.getLevelName(logging.WARNING)
    original_error = logging.getLevelName(logging.ERROR)

    # Mock sys.stderr.isatty to return True
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)

    _ = get_logger()

    # Verify that warning and error level names are modified
    modified_warning = logging.getLevelName(logging.WARNING)
    modified_error = logging.getLevelName(logging.ERROR)

    assert modified_warning != original_warning
    assert modified_error != original_error
    assert ANSICodes.BOLD in modified_warning
    assert ANSICodes.END in modified_warning


def test_no_ansi_colors_outside_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test ANSI color codes are not applied when not in terminal."""
    get_logger.cache_clear()

    # Store original level names
    original_warning = logging.getLevelName(logging.WARNING)
    original_error = logging.getLevelName(logging.ERROR)

    # Mock sys.stderr.isatty to return False
    monkeypatch.setattr(sys.stderr, "isatty", lambda: False)

    _ = get_logger()

    # Verify that warning and error level names remain unchanged
    assert logging.getLevelName(logging.WARNING) == original_warning
    assert logging.getLevelName(logging.ERROR) == original_error
