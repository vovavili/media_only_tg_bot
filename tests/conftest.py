"""Fixtures that are shared across tests."""

from __future__ import annotations

from typing import Final

import pytest

from src.utils import get_settings, Settings

TEST_ENV_VARS: Final = {
    "BOT_TOKEN": "live_token_xyz",
    "TOPIC_ID": "100",
    "GROUP_CHAT_ID": "987654",
    "ENVIRONMENT": "production",
}


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
