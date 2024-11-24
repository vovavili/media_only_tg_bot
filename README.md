# Telegram Bot - Media-Only Group Chat Topic

![Tests](https://github.com/vovavili/media_only_tg_bot/actions/workflows/tox.yml/badge.svg)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/vovavili/media_only_tg_bot/master.svg)](https://results.pre-commit.ci/latest/github/vovavili/media_only_tg_bot/master)
[![codecov](https://codecov.io/github/vovavili/media_only_tg_bot/branch/master/graph/badge.svg?token=5QN2AD5DBW)](https://codecov.io/github/vovavili/media_only_tg_bot)

<p align="center">
  <img src="https://github.com/vovavili/media_only_tg_bot/blob/master/example.gif?raw=true" alt="Example of bot use."/>
</p>

A script for a Telegram bot that deletes non-photo material from a group chat topic.

### Installation

To run this script with the right Python version and all the dependencies, please use [uv](https://docs.astral.sh/uv/):

<details>
<summary>Installation instructions for uv</summary>

Install uv (and git) on Windows 11+ with PowerShell:

```powershell
irm https://astral.sh/uv/install.ps1 | iex
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
# git doesn't come with Windows 11 by default
winget install -e --id Git.Git
```

On macOS or Linux:

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

Or, if you only have access to Python (as is the case for PythonAnywhere's free tier):

```shell
pip install --upgrade uv 
```

</details>

Then, run the script:

```shell
git clone https://github.com/vovavili/media_only_tg_bot.git
cd media_only_tg_bot
# Make sure to create a .env or .env.prod file at this step
uv run -m src.media_only_topic
```

Prior to running the script, please make sure your `.env` or `.env.prod` file contains the following variables. To find out 
how to get them, please refer to the 
[following guide](https://gist.github.com/nafiesl/4ad622f344cd1dc3bb1ecbe468ff9f8a):
- **BOT_TOKEN** - an API token for your bot.
- **TOPIC_ID** - an ID for your group chat topic.
- **GROUP_CHAT_ID** - an ID for your group chat.
- **ENVIRONMENT** - if you intend on running this script on a VPS, this improves logging
    information in your production system. Has to be either "development" or "production."

Required only in production, to send an email message on failure:

- **SMTP_HOST** - SMTP server address (e.g., smtp.gmail.com).
- **SMTP_USER** - Email username/address for SMTP authentication.
- **SMTP_PASSWORD** - Email password or app-specific password (in case of something like 
[Gmail](https://support.google.com/mail/answer/185833?hl=en)).

Based on my experience, this script runs on [PythonAnywhere](https://www.pythonanywhere.com/)'s free tier just fine, 
though for particularly active group chats it might be too limited. Keep in mind that, for free tier, logging emails 
are [restricted to Gmail only](https://help.pythonanywhere.com/pages/SMTPForFreeUsers/).