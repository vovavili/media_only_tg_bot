"""Unit tests for the script."""

import pytest
from unittest.mock import AsyncMock, Mock
from telegram import Message, Chat, Update, User, PhotoSize

from media_only_topic.media_only_topic import only_media_messages, settings


@pytest.fixture
def mock_message() -> Message:
    """Create a base mock message with common attributes."""
    message = Mock(spec=Message)
    message.chat = Mock(spec=Chat)
    message.chat.id = settings.GROUP_CHAT_ID
    message.is_topic_message = True
    message.message_thread_id = settings.TOPIC_ID
    message.from_user = Mock(spec=User)
    message.from_user.username = "test_user"
    message.message_id = 12345
    return message


@pytest.fixture
def mock_context() -> Mock:
    """Create a mock context."""
    return Mock()


@pytest.mark.asyncio
async def test_text_message_deleted(mock_message: Message, mock_context: Mock) -> None:
    """Test that a text message gets deleted."""
    # Set up the message with no media attributes
    mock_message.photo = False
    mock_message.video = False
    mock_message.animation = False
    mock_message.document = False

    # Set up the delete method as an async mock
    mock_message.delete = AsyncMock()

    # Create update object with the message included in the constructor
    update = Update(update_id=1, message=mock_message)

    # Call the handler
    await only_media_messages(update, mock_context)

    # Assert that delete was called
    mock_message.delete.assert_called_once()


@pytest.mark.asyncio
async def test_photo_message_kept(mock_message: Message, mock_context: Mock) -> None:
    """Test that a photo message is not deleted."""
    # Set up the message with a photo
    mock_message.photo = [
        Mock(spec=PhotoSize)
    ]  # Photo messages contain a list of PhotoSize objects
    mock_message.video = False
    mock_message.animation = False
    mock_message.document = False

    # Set up the delete method as an async mock
    mock_message.delete = AsyncMock()

    # Create update object with the message included in the constructor
    update = Update(update_id=1, message=mock_message)

    # Call the handler
    await only_media_messages(update, mock_context)

    # Assert that delete was not called
    mock_message.delete.assert_not_called()
