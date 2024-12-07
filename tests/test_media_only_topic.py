"""Unit tests for the main script."""

from __future__ import annotations

import logging
from collections.abc import Generator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from telegram import Chat, Message, PhotoSize, Update, User
from telegram.ext import ContextTypes

from src.make_utils import Settings
from src.media_only_topic import ALLOWED_MESSAGE_TYPES, main, only_media_messages

type MockGenerator = Generator[Mock, None, None]


@pytest.fixture(name="mock_logger", autouse=True)
def fixture_mock_logger(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Return the mocked logger."""
    mock_logger = Mock()
    monkeypatch.setattr("src.media_only_topic.logger", mock_logger)
    return mock_logger


@pytest.fixture(autouse=True)
def isolate_logger() -> Generator[None, None, None]:
    """Isolate logger configuration for these tests."""
    logger_instance = logging.getLogger("main")
    # Store original handlers and level
    original_handlers = logger_instance.handlers.copy()
    original_level = logger_instance.level
    # Clear all handlers
    logger_instance.handlers.clear()

    yield

    # Restore original state
    logger_instance.handlers = original_handlers
    logger_instance.level = original_level


@pytest.fixture(name="message_handler")
def fixture_message_handler() -> MockGenerator:
    """Get a mock message handler for tests."""
    with patch("src.media_only_topic.MessageHandler") as mock:
        yield mock


@pytest.fixture(name="settings")
def fixture_settings() -> Mock:
    """Create a mock settings object."""
    settings = Mock()
    settings.GROUP_CHAT_ID = 123456
    settings.TOPIC_ID = 789
    return settings


@pytest.mark.asyncio
async def test_message_deletion_logging(
    message: Mock,
    context: Mock,
    mock_logger: Mock,
) -> None:
    """Test that message deletion is properly logged."""
    message.delete = AsyncMock()
    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)

    message.delete.assert_called_once()
    mock_logger.info.assert_called_once_with(
        "Deleted message %s from user %s",
        message.message_id,
        message.from_user.username,
    )


@pytest.fixture(name="message")
def fixture_message(settings: Mock) -> Mock:
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
async def test_text_message_deleted(message: Mock, context: Mock) -> None:
    """Test that a text message gets deleted."""
    message.delete = AsyncMock()
    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)

    message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_photo_message_kept(message: Mock, context: Mock) -> None:
    """Test that a photo message is not deleted."""
    message.photo = [Mock(spec=PhotoSize)]
    message.delete = AsyncMock()

    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)

    message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_production_environment(
    message: Mock, context: Mock, prod_settings: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that production environment works correctly."""
    message.chat.id = prod_settings.GROUP_CHAT_ID
    message.message_thread_id = prod_settings.TOPIC_ID
    message.delete = AsyncMock()

    update = Update(update_id=1, message=message)

    # Mock the settings in the module being tested
    monkeypatch.setattr("src.media_only_topic.settings", prod_settings)
    await only_media_messages(update, context)

    message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_invalid_update_object(context: Mock) -> None:
    """Test that an invalid update object raises TypeError."""
    with pytest.raises(TypeError, match="Invalid update object passed to the handle."):
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
async def test_allowed_media_types(message: Mock, context: Mock, media_type: str) -> None:
    """Test that all allowed media types are not deleted."""
    setattr(message, media_type, True)
    message.delete = AsyncMock()
    update = Update(update_id=1, message=message)

    await only_media_messages(update, context)
    message.delete.assert_not_called()


@pytest.mark.usefixtures("message_handler")
@patch("src.media_only_topic.Application")
def test_main(mock_application: Mock, mock_logger: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test the main function."""
    # Setup mocks
    mock_app = Mock()
    mock_application.builder.return_value.token.return_value.build.return_value = mock_app

    # Create a mock settings with BOT_TOKEN
    mock_settings = Mock()
    mock_settings.BOT_TOKEN = Mock()
    mock_settings.BOT_TOKEN.get_secret_value.return_value = "test_token"

    # Mock the settings in the module
    monkeypatch.setattr("src.media_only_topic.settings", mock_settings)

    # Run main
    main()

    # Verify
    mock_application.builder.assert_called_once()
    mock_app.add_handler.assert_called_once()
    mock_app.add_error_handler.assert_called_once()
    mock_app.run_polling.assert_called_once_with(allowed_updates=("message",))
    mock_logger.info.assert_called_with("Starting bot...")
