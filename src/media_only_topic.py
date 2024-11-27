#!/usr/bin/env python3
"""A script for a Telegram bot that deletes non-photo material from a group chat topic."""

from __future__ import annotations

from typing import Final

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from src.utils import error_handler, logger, settings

ALLOWED_MESSAGE_TYPES: Final = (
    "photo",
    "video",
    "animation",
    "document",
    "video_note",
    "story",
    "sticker",
)


async def only_media_messages(update: object, _: ContextTypes.DEFAULT_TYPE) -> None:
    """For a specific group chat topic, allow only media messages."""
    if not isinstance(update, Update):
        raise TypeError("Invalid update object passed to the handle.")

    message = update.message

    if not (
        # Check if message is in a chat and topic we care about
        message is None
        or message.chat.id != settings.GROUP_CHAT_ID
        or (not message.is_topic_message)
        or message.message_thread_id != settings.TOPIC_ID
        # Check if message contains any allowed media types
        or any(getattr(message, msg_type, False) for msg_type in ALLOWED_MESSAGE_TYPES)
    ):
        await message.delete()
        logger.info(
            "Deleted message %s from user %s",
            message.message_id,
            message.from_user.username if message.from_user is not None else "",
        )


def main() -> None:
    """Run the bot for a media-only topic."""
    bot_token = settings.BOT_TOKEN.get_secret_value()
    application = Application.builder().token(bot_token).build()
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, only_media_messages))
    application.add_error_handler(error_handler)

    logger.info("Starting bot...")
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
