"""Unit tests for the script."""

from collections.abc import Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from telegram import Chat, Message, PhotoSize, Update, User
from telegram.ext import ContextTypes

from media_only_topic.media_only_topic import (
    ALLOWED_MESSAGE_TYPES,
    Settings,
    get_settings,
    only_media_messages,
)


@pytest.fixture(name="logger")
def fixture_logger() -> Generator[Mock, None, None]:
    """Mock logger for all tests and prevent file creation."""
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        yield mock_logger


@pytest.fixture(name="settings")
def fixture_test_env(monkeypatch: pytest.MonkeyPatch) -> Settings:
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
def fixture_production_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Set up production environment settings."""
    test_env_vars = {
        "BOT_TOKEN": "live_token_xyz",
        "TOPIC_ID": "100",
        "GROUP_CHAT_ID": "987654",
        "ENVIRONMENT": "production",
    }
    for key, value in test_env_vars.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    return get_settings()


@pytest.fixture(name="message")
def fixture_message(settings: Settings) -> Mock:
    """Create a mock message with the appropriate attributes."""
    message = Mock(spec=Message)
    message.chat = Mock(spec=Chat)
    message.chat.id = settings.GROUP_CHAT_ID
    message.is_topic_message = True
    message.message_thread_id = settings.TOPIC_ID
    message.from_user = Mock(spec=User)
    message.from_user.username = "test_user"
    message.message_id = 12345

    # Initialize all media attributes to False
    for media_type in ALLOWED_MESSAGE_TYPES:
        setattr(message, media_type, False)

    return message


@pytest.fixture(name="context")
def fixture_context() -> Mock:
    """Create a mock context."""
    return Mock(spec=ContextTypes.DEFAULT_TYPE)


@pytest.mark.asyncio
async def test_text_message_deleted(message: Mock, context: Mock, settings: Settings) -> None:
    """Test that a text message gets deleted."""
    message.delete = AsyncMock()
    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)

    message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_photo_message_kept(message: Mock, context: Mock, settings: Settings) -> None:
    """Test that a photo message is not deleted."""
    message.photo = [Mock(spec=PhotoSize)]
    message.delete = AsyncMock()

    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)

    message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_production_environment(
    message: Mock, context: Mock, prod_settings: Settings
) -> None:
    """Test that production environment works correctly."""
    message.chat.id = prod_settings.GROUP_CHAT_ID
    message.message_thread_id = prod_settings.TOPIC_ID
    message.delete = AsyncMock()

    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)

    message.delete.assert_called_once()
