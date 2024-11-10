#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "python-dotenv>=1.0.1",
#   "python-telegram-bot>=21.7",
# ]
# ///
"""
A module for a Telegram bot that deletes non-photo material from a group chat topic.

Please make sure your .env contains the following variables:
BOT_TOKEN - an API token for your bot
TOPIC_ID - an ID for your group chat topic
GROUP_CHAT_ID - an ID for your group chat
"""

import logging
import os
from collections.abc import Callable
from functools import wraps
from typing import Final, Literal

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

ALLOWED_MESSAGE_TYPES: Final = (
    "photo",
    "video",
    "animation",
    "document",
)


def setup_logger(
    level: Literal[0, 10, 20, 30, 40, 50] = 20,  # defaults to logging.INFO
    logger_name: str = "main",
) -> logging.Logger:
    """
    Initialize the logging system.

    Parameters:
        level: The logging level to use
        logger_name: The name to use for the logger (defaults to "main")

    Returns:
        logging.Logger: The logger for the script.
    """
    # Add file handler for errors and critical messages
    file_handler = logging.FileHandler(filename="export_log.log", mode="a")
    file_handler.setLevel(logging.ERROR)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=(logging.StreamHandler(), file_handler),
    )

    return logging.getLogger(logger_name)


logger = setup_logger()


def log_error[**P, R](func: Callable[[P], R]) -> Callable[[P], R]:
    """A decorator to log an error in a function, in case it occurs."""

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except Exception as err:
            logger.error(err)
            raise err

    return wrapper


async def only_media_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """For a specific group chat topic, allow only media messages."""
    message = update.message

    if (
        # Check if message is in a chat and topic we care about
        message.chat.id != os.environ["GROUP_CHAT_ID"]
        or (not message.is_topic_message)
        or message.message_thread_id != os.environ["TOPIC_ID"]
        # Check if message contains any allowed media types
        or any(
            hasattr(message, msg_type) and getattr(message, msg_type)
            for msg_type in ALLOWED_MESSAGE_TYPES
        )
    ):
        return

    await message.delete()
    logger.info(
        "Deleted message %s from user %s",
        message.message_id,
        message.from_user.username,
    )
    return


@log_error
def main() -> None:
    """Run the bot for a media-only topic."""
    load_dotenv()

    application = Application.builder().token(os.environ["BOT_TOKEN"]).build()
    application.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, only_media_messages)
    )

    logger.info("Starting bot...")
    application.run_polling()


main()
