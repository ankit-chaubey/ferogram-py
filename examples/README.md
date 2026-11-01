# Examples

Each file is a runnable script. Set `API_ID` / `API_HASH` (and `BOT_TOKEN` for the bot examples), or
edit the `Client(...)` call at the top, before running.

## Bots

| File | What it shows |
|---|---|
| `echo_bot.py` | Echo back incoming text messages. |
| `command_bot.py` | `/start` and `/help` commands plus an inline button callback. |
| `media_bot.py` | Chat actions (typing indicators) and dice. |
| `search_bot.py` | Searching messages in a chat and globally. |
| `rich_message.py` | Sending, reading and drafting rich messages. |
| `update_handlers.py` | Every update handler type, reactions, and the logging module. |

## Groups and admin

| File | What it shows |
|---|---|
| `admin_tools.py` | Listing administrators, online count, unpinning all messages. |
| `group_management.py` | Forum topics, polls and message translation. |

## User accounts

| File | What it shows |
|---|---|
| `send_hi.py` | The smallest user-session script: send "hi" to Saved Messages. |
| `send_message.py` | Text with HTML and Markdown, and listing dialogs. |
| `send_media.py` | Sending a photo and a document. |
| `user_management.py` | Contacts and full user info. |
| `userbot.py` | Handling private messages from a user account. |

## Raw API

| File | What it shows |
|---|---|
| `raw_invoke.py` | Calling any API method directly through `app.raw`. |
