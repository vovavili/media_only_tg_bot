"""Unit tests for the script."""

import pytest
from collections.abc import Generator
from unittest.mock import Mock, AsyncMock, patch

from telegram import Update, Message, Chat, User, PhotoSize
from telegram.ext import ContextTypes

from media_only_topic.media_only_topic import (
    get_settings,
    only_media_messages,
    Settings,
    ALLOWED_MESSAGE_TYPES,
)


@pytest.fixture(autouse=True)
def mock_logger() -> Generator[Mock, None, None]:
    """Mock logger for all tests and prevent file creation."""
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        yield mock_logger


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Set up test environment variables before importing the bot module."""
    test_env_vars = {
        "BOT_TOKEN": "test_token_123",
        "TOPIC_ID": "42",
        "GROUP_CHAT_ID": "123456",
        "ENVIRONMENT": "development",
    }
    for key, value in test_env_vars.items():
        monkeypatch.setenv(key, value)

    # Now we can safely import the module

    get_settings.cache_clear()  # Clear any cached settings
    return get_settings()


@pytest.fixture
def mock_settings(setup_test_env: Settings) -> Settings:
    """Reuse the settings from setup_test_env."""
    return setup_test_env


@pytest.fixture
def production_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
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


@pytest.fixture
def mock_message(mock_settings: Settings) -> Mock:
    """Create a mock message with the appropriate attributes."""
    message = Mock(spec=Message)
    message.chat = Mock(spec=Chat)
    message.chat.id = mock_settings.GROUP_CHAT_ID
    message.is_topic_message = True
    message.message_thread_id = mock_settings.TOPIC_ID
    message.from_user = Mock(spec=User)
    message.from_user.username = "test_user"
    message.message_id = 12345

    # Initialize all media attributes to False
    for media_type in ALLOWED_MESSAGE_TYPES:
        setattr(message, media_type, False)

    return message


@pytest.fixture
def mock_context() -> Mock:
    """Create a mock context."""
    return Mock(spec=ContextTypes.DEFAULT_TYPE)


@pytest.mark.asyncio
async def test_text_message_deleted(
    mock_message: Mock, mock_context: Mock, mock_settings: Settings
) -> None:
    """Test that a text message gets deleted."""
    mock_message.delete = AsyncMock()
    update = Update(update_id=1, message=mock_message)

    await only_media_messages(update, mock_context)

    mock_message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_photo_message_kept(
    mock_message: Mock, mock_context: Mock, mock_settings: Settings
) -> None:
    """Test that a photo message is not deleted."""
    mock_message.photo = [Mock(spec=PhotoSize)]
    mock_message.delete = AsyncMock()

    update = Update(update_id=1, message=mock_message)

    await only_media_messages(update, mock_context)

    mock_message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_production_environment(
    mock_message: Mock, mock_context: Mock, production_settings: Settings
) -> None:
    """Test that production environment works correctly."""
    mock_message.chat.id = production_settings.GROUP_CHAT_ID
    mock_message.message_thread_id = production_settings.TOPIC_ID
    mock_message.delete = AsyncMock()

    update = Update(update_id=1, message=mock_message)

    await only_media_messages(update, mock_context)

    mock_message.delete.assert_called_once()
