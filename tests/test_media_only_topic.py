"""Unit tests for the script."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from telegram import Chat, Message, PhotoSize, Update, User
from telegram.ext import ContextTypes

from src.media_only_topic import ALLOWED_MESSAGE_TYPES, only_media_messages, main
from src.utils import get_settings, Settings


@pytest.fixture
def logger() -> Generator[Mock, None, None]:
    """Mock logger for all tests and prevent file creation."""
    with patch("logging.getLogger") as mock_get_logger:
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        yield mock_logger


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
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


@pytest.fixture
def prod_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
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
def message(settings: Settings) -> Mock:
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


@pytest.fixture
def context() -> Mock:
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


@pytest.mark.asyncio
async def test_invalid_update_object(context: Mock) -> None:
    """Test that an invalid update object raises ValueError."""
    with pytest.raises(ValueError, match="Invalid update object passed to the handle."):
        await only_media_messages("not_an_update", context)


@pytest.mark.asyncio
async def test_none_message(context: Mock) -> None:
    """Test handling of None message."""
    update = Update(update_id=1, message=None)
    # Should not raise any exception
    await only_media_messages(update, context)


@pytest.mark.asyncio
async def test_wrong_chat_id(message: Mock, context: Mock, settings: Settings) -> None:
    """Test message in wrong chat."""
    message.chat.id = settings.GROUP_CHAT_ID + 1  # Different chat ID
    message.delete = AsyncMock()
    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)
    message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_non_topic_message(message: Mock, context: Mock) -> None:
    """Test non-topic message."""
    message.is_topic_message = False
    message.delete = AsyncMock()
    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)
    message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_wrong_topic_id(message: Mock, context: Mock, settings: Settings) -> None:
    """Test message in wrong topic."""
    message.message_thread_id = settings.TOPIC_ID + 1  # Different topic ID
    message.delete = AsyncMock()
    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)
    message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_message_without_user(message: Mock, context: Mock) -> None:
    """Test handling of message without user information."""
    message.from_user = None
    message.delete = AsyncMock()
    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)
    message.delete.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "media_type", ["video", "animation", "document", "video_note", "story", "sticker"]
)
async def test_allowed_media_types(
    message: Mock, context: Mock, settings: Settings, media_type: str
) -> None:
    """Test that all allowed media types are not deleted."""
    setattr(message, media_type, True)
    message.delete = AsyncMock()
    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)
    message.delete.assert_not_called()


@patch("src.media_only_topic.Application")
@patch("src.media_only_topic.MessageHandler")
@patch("src.media_only_topic.get_settings")
@patch("src.media_only_topic.get_logger")
def test_main(
    mock_get_logger: Mock,
    mock_get_settings: Mock,
    mock_message_handler: Mock,
    mock_application: Mock,
) -> None:
    """Test the main function."""
    # Setup mocks
    mock_logger = Mock()
    mock_get_logger.return_value = mock_logger

    mock_settings = Mock()
    mock_settings.BOT_TOKEN.get_secret_value.return_value = "test_token"
    mock_get_settings.return_value = mock_settings

    mock_app = Mock()
    mock_application.builder.return_value.token.return_value.build.return_value = mock_app

    # Run main
    main()

    # Verify
    mock_application.builder.assert_called_once()
    mock_app.add_handler.assert_called_once()
    mock_app.add_error_handler.assert_called_once()
    mock_app.run_polling.assert_called_once_with(allowed_updates=["message"])
    mock_logger.info.assert_called_with("Starting bot...")
