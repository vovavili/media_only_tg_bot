"""Fixtures that are shared across tests."""

from __future__ import annotations

import logging
import os
from collections.abc import Generator, Mapping
from typing import Final
from unittest.mock import Mock, patch

import pytest

from src.make_utils import Settings, get_settings

TEST_ENV_VARS: Final = {
    "BOT_TOKEN": "live_token_xyz",
    "TOPIC_ID": "100",
    "GROUP_CHAT_ID": "987654",
    "ENVIRONMENT": "production",
}
TEST_ERROR_MESSAGE: Final = "Test error message"


def create_log_record(
    module: str = "test_module",
    level: int = 20,  # INFO level
    msg: str = "Test message",
    args: tuple[str | Mapping[str, str], ...] = (),
) -> logging.LogRecord:
    """Create LogRecord instances for testing using a helper function.

    Args:
    ----
        module: The module name for the log record
        level: The logging level (default: INFO/20)
        msg: The message to log
        args: Tuple of arguments for message formatting (default: empty tuple)

    Returns:
    -------
        LogRecord: A configured log record for testing

    """
    return logging.LogRecord(
        name=module, level=level, pathname="test.py", lineno=1, msg=msg, args=args, exc_info=None
    )


@pytest.fixture(scope="session", autouse=True)
def mock_env_and_settings() -> Generator[None, None, None]:
    """Set up environment variables and mock settings for all tests."""
    test_env_vars = {
        "BOT_TOKEN": "test_token_xyz",
        "TOPIC_ID": "42",
        "GROUP_CHAT_ID": "123456",
        "ENVIRONMENT": "development",
    }

    # Set environment variables
    for key, value in test_env_vars.items():
        os.environ[key] = value

    # Mock get_settings before any imports happen
    with patch("src.make_utils.get_settings") as mock_get_settings:
        mock_settings = Mock(spec=Settings)
        mock_settings.GROUP_CHAT_ID = 123456
        mock_settings.TOPIC_ID = 789
        mock_settings.ENVIRONMENT = "development"
        mock_token = Mock()
        mock_token.get_secret_value.return_value = test_env_vars["BOT_TOKEN"]
        mock_settings.BOT_TOKEN = mock_token
        mock_get_settings.return_value = mock_settings
        yield


@pytest.fixture(autouse=True)
def mock_utils(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock the utils module to prevent actual logger/settings creation."""
    mock_logger = Mock()
    mock_settings = Mock(spec=Settings)

    # Configure basic settings attributes that most tests will need
    mock_settings.GROUP_CHAT_ID = 123456
    mock_settings.TOPIC_ID = 789
    mock_settings.ENVIRONMENT = "development"
    mock_settings.BOT_TOKEN = Mock()
    mock_settings.BOT_TOKEN.get_secret_value.return_value = "test_token"

    # Mock both utils.py and direct imports
    monkeypatch.setattr("src.utils.logger", mock_logger)
    monkeypatch.setattr("src.utils.settings", mock_settings)
    monkeypatch.setattr("src.media_only_topic.logger", mock_logger)
    monkeypatch.setattr("src.media_only_topic.settings", mock_settings)


@pytest.fixture(name="settings")
def fixture_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Set up test environment variables before importing the bot module."""
    test_env_vars = {
        "BOT_TOKEN": "test_token_123",
        "TOPIC_ID": "42",
        "GROUP_CHAT_ID": "123456",
        "ENVIRONMENT": "development",
    }
    for key, value in test_env_vars.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()  # Clear any cached settings
    return get_settings()


@pytest.fixture(name="mock_settings")
def fixture_mock_settings() -> Mock:
    """Create a mock settings object with basic attributes."""
    settings = Mock(spec=Settings)
    settings.GROUP_CHAT_ID = 123456
    settings.TOPIC_ID = 789
    settings.ENVIRONMENT = "development"
    return settings


@pytest.fixture(name="prod_settings")
def fixture_prod_settings() -> Mock:
    """Set up production environment settings."""
    settings = Mock(spec=Settings)
    settings.GROUP_CHAT_ID = int(TEST_ENV_VARS["GROUP_CHAT_ID"])
    settings.TOPIC_ID = int(TEST_ENV_VARS["TOPIC_ID"])
    settings.ENVIRONMENT = TEST_ENV_VARS["ENVIRONMENT"]
    # Create a mock SecretStr
    mock_token = Mock()
    mock_token.get_secret_value.return_value = TEST_ENV_VARS["BOT_TOKEN"]
    settings.BOT_TOKEN = mock_token

    # Explicitly set SMTP attributes to None
    settings.SMTP_HOST = None
    settings.SMTP_USER = None
    settings.SMTP_PASSWORD = None

    return settings


@pytest.fixture(name="email_settings")
def fixture_email_settings() -> Mock:
    """Set up production environment settings with email configuration."""
    settings = Mock(spec=Settings)
    test_env_vars = TEST_ENV_VARS | {
        "SMTP_HOST": "smtp.test.com",
        "SMTP_USER": "test@example.com",
        "SMTP_PASSWORD": "test_password",
    }

    # Configure all settings attributes
    settings.GROUP_CHAT_ID = int(test_env_vars["GROUP_CHAT_ID"])
    settings.TOPIC_ID = int(test_env_vars["TOPIC_ID"])
    settings.ENVIRONMENT = "production"  # Make sure it's production

    # Mock SecretStr instances
    mock_token = Mock()
    mock_token.get_secret_value.return_value = test_env_vars["BOT_TOKEN"]
    settings.BOT_TOKEN = mock_token

    mock_password = Mock()
    mock_password.get_secret_value.return_value = test_env_vars["SMTP_PASSWORD"]
    settings.SMTP_PASSWORD = mock_password

    # Regular string attributes
    settings.SMTP_HOST = test_env_vars["SMTP_HOST"]
    settings.SMTP_USER = test_env_vars["SMTP_USER"]

    return settings


@pytest.fixture(name="mock_logger")
def fixture_mock_logger() -> Mock:
    """Create a mock logger with all necessary methods."""
    logger = Mock()
    logger.info = Mock()
    logger.error = Mock()
    logger.warning = Mock()
    logger.critical = Mock()
    logger.debug = Mock()
    return logger
