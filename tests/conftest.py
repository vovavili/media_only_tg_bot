"""Fixtures that are shared across tests."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Final

import pytest

from src.utils import Settings, get_logger, get_settings

TEST_ENV_VARS: Final = {
    "BOT_TOKEN": "live_token_xyz",
    "TOPIC_ID": "100",
    "GROUP_CHAT_ID": "987654",
    "ENVIRONMENT": "production",
}


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


@pytest.fixture(autouse=True)
def reset_logger_cache() -> None:
    """Reset the logger cache before each test."""
    get_logger.cache_clear()


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


@pytest.fixture(name="prod_settings")
def fixture_prod_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Set up production environment settings."""
    for key, value in TEST_ENV_VARS.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    return get_settings()


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
