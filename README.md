# Telegram Bot - Media-Only Group Chat Topic

A script for a Telegram bot that deletes non-photo material from a group chat topic.

To run this script with the right Python version and all the dependencies, please use [uv run](https://docs.astral.sh/uv/guides/scripts/). 

Please make sure your .env contains the following variables:
- BOT_TOKEN - an API token for your bot.
- TOPIC_ID - an ID for your group chat topic.
- GROUP_CHAT_ID - an ID for your group chat.
- ENVIRONMENT - if you intend on running this script on a VPS, this improves logging
    information in your production system.

Required only in production:

- SMTP_HOST - SMTP server address (e.g., smtp.gmail.com)
- SMTP_USER - Email username/address for SMTP authentication
- SMTP_PASSWORD - Email password or app-specific password