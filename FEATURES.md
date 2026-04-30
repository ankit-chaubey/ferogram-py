# ferogram-py : Feature Reference

Python bindings for the ferogram MTProto library.  
All client methods are `async`. `peer` accepts `"@username"`, `"me"`, or an integer ID as a string.

---

## Client Setup

```python
from ferogram import Client

app = Client(
    session="mybot",       # session file name (no extension)
    api_id=123456,
    api_hash="abc...",
    bot_token="123:TOKEN", # omit for userbot
)

app.run()                  # blocking; starts and loops forever
# or
await app.start()
await app.run_until_disconnected()
# or as context manager
async with app as client:
    ...
```

Credentials can also come from env vars: `API_ID`, `API_HASH`, `BOT_TOKEN`.

---

## Event Handlers

Decorators to register handlers. Each accepts zero or more filters.

```python
@app.on_message(*filters)
@app.on_edited_message(*filters)
@app.on_message_deleted(*filters)
@app.on_callback_query(*filters)
@app.on_inline_query(*filters)
@app.on_inline_send(*filters)
@app.on_user_status(*filters)
@app.on_chat_action(*filters)
@app.on_participant_update(*filters)
@app.on_join_request(*filters)
@app.on_message_reaction(*filters)
@app.on_poll_vote(*filters)
@app.on_bot_stopped(*filters)
@app.on_shipping_query(*filters)
@app.on_pre_checkout_query(*filters)
@app.on_chat_boost(*filters)
@app.on_raw_update(*filters)
```

Handler signature: `async def handler(client, update):`

---

## Filters

Import: `from ferogram import filters`

**Message**

| Filter | Matches |
|---|---|
| `filters.all` | every update |
| `filters.private` | private chat messages |
| `filters.group` | group messages |
| `filters.channel` | channel posts |
| `filters.text` | messages with text |
| `filters.photo` | messages with a photo |
| `filters.document` | messages with a document |
| `filters.media` | any media |
| `filters.incoming` | messages not sent by you |
| `filters.outgoing` | messages sent by you |
| `filters.mentioned` | messages that mention you |
| `filters.forwarded` | forwarded messages |
| `filters.via_bot` | sent via inline bot |
| `filters.reply` | replies to another message |
| `filters.pinned` | pinned messages |
| `filters.album` | grouped/album messages |
| `filters.scheduled` | scheduled messages |
| `filters.bot` | sender is a bot |
| `filters.no_bot` | sender is not a bot |

**Factory filters**

```python
filters.command("start")              # /start (or multiple: command("start", "begin"))
filters.command("start", prefix="!")  # !start
filters.regex(r"hello|hi")
filters.text_contains("keyword")
filters.startswith("!")
filters.endswith("?")
filters.user(123456, 789012)
filters.chat(-1001234567)
filters.min_length(10)
filters.max_length(200)
```

**Callback query**

```python
filters.data("button_id")
filters.data_regex(r"^action:")
filters.data_startswith("page_")
```

**Inline query**

```python
filters.inline()            # any inline query
filters.inline(r"\w+")      # query matches pattern
```

**User status**

```python
filters.online
filters.offline
filters.status("recently")
```

**Chat action**

```python
filters.typing
filters.action("upload_document")
```

**Reactions / participants / raw**

```python
filters.reaction("👍", "❤")
filters.participant_status("member", "admin")
filters.update_type("ReadHistoryInbox")
filters.constructor(0x1cb5c415)
```

**Logic combinators**

```python
filters.and_(f1, f2)
filters.or_(f1, f2)
filters.not_(f1)
```

---

## Messaging

```python
await client.send_message(peer, text, parse_mode=None)
# parse_mode: None (plain) | "html" | "markdown"

await client.send_to_self(text)
await client.edit_message(peer, message_id, new_text)
await client.delete_message(message_id, revoke=True)
await client.delete_messages([id1, id2], revoke=True)
await client.forward_messages(destination, source, [msg_id, ...])
await client.pin_message(peer, message_id)
await client.unpin_message(peer, message_id)
await client.unpin_all_messages(peer)
await client.get_messages_by_id(peer, [id1, id2])
await client.get_message_history(peer, limit=100, offset_id=0)
await client.get_pinned_message(peer)                   # -> Message | None
await client.get_reply_to_message(peer, msg_id)         # -> Message | None
await client.get_scheduled_messages(peer)               # -> [Message]
await client.get_discussion_message(peer, msg_id)       # -> (messages, unread, max_id, read_max_id)
await client.send_reaction(peer, message_id, emoji)
await client.read_reactions(peer)
await client.clear_recent_reactions()
await client.get_reaction_list(peer, msg_id, limit=100) # -> [(peer_id, emoji)]
await client.mark_as_read(peer)
await client.clear_mentions(peer)
await client.send_chat_action(peer, "typing")           # or ChatAction.TYPING
await client.send_dice(peer, emoticon="🎲")
await client.translate_messages(peer, [msg_id], to_lang="en")
await client.get_web_page_preview(text)                 # -> url | None
```

### Message object methods

```python
await message.reply(text, parse_mode=None)
await message.respond(text, parse_mode=None)   # no quote
await message.edit(new_text, parse_mode=None)
await message.delete()
await message.forward_to(peer)
await message.pin()
await message.react(emoji)
```

### Message fields

`id`, `text`, `date`, `edit_date`, `chat_id`, `from_id`, `outgoing`, `mentioned`, `pinned`,
`reply_to_message_id`, `via_bot_id`, `grouped_id`, `has_media`, `has_photo`, `has_document`,
`is_forwarded`, `post_author`, `view_count`, `reply_count`

---

## Media

```python
await client.send_photo(peer, path, caption="")
await client.send_document(peer, path, caption="", mime_type=None)
await client.send_file(peer, path, caption="", mime_type=None)
await client.send_audio(peer, path, caption="")         # mime: audio/mpeg
await client.send_video(peer, path, caption="")         # mime: video/mp4
await client.send_voice(peer, path, caption="")         # mime: audio/ogg
await client.send_sticker(peer, path)                   # mime: image/webp
await client.upload_media(peer, path)                   # -> document_id | None
await client.download_media(peer, msg_id, path)         # -> final path
await client.edit_chat_photo(peer, path)
await client.delete_profile_photos()
```

---

## Polls

```python
await client.send_poll(
    peer, question, answers=["A", "B", "C"],
    quiz=False, correct_index=None, multiple_choice=False,
)
await client.send_vote(peer, msg_id, options=[b"\x00"])
await client.get_poll_votes(peer, msg_id, limit=100)    # -> [(user_id, option_bytes)]
```

---

## Inline Bots

```python
await client.answer_callback_query(query_id, text=None, alert=False)

from ferogram import InlineArticle, InlinePhoto, InlineDocument

await client.answer_inline_query(query_id, [
    InlineArticle(id="1", title="Title", message_text="Hello!"),
    InlinePhoto(id="2", title="Cat", message_text="🐱", thumb_url="..."),
    InlineDocument(id="3", title="File", message_text="...", url="...", mime_type="application/pdf"),
], cache_time=300, is_personal=False, next_offset=None)

from ferogram import InlineMessageId
await client.edit_inline_message(InlineMessageId(dc_id=2, id_bytes=b"..."), "new text")
```

---

## Chats & Groups

```python
await client.create_group(title, user_ids=[...])
await client.create_channel(title, about="", broadcast=True)  # broadcast=False for supergroup
await client.edit_chat_title(peer, title)
await client.edit_chat_about(peer, about)
await client.set_history_ttl(peer, period)           # seconds; 0 = off
await client.edit_chat_default_banned_rights(peer, {"send_messages": True, ...})
await client.set_chat_reactions(peer, "all")         # "all" | "none" | "👍,👎"
await client.toggle_forum(peer, enabled=True)
await client.transfer_chat_ownership(peer, new_owner_id)
await client.migrate_chat(chat_id)
await client.delete_channel(peer)
await client.delete_chat(chat_id)
await client.delete_chat_history(peer, max_id=0, revoke=False)
await client.invite_users(peer, [user_id, ...])
await client.get_chat_administrators(peer)           # -> [ChatMember]
await client.get_online_count(peer)                  # -> int
await client.get_chat_full(peer)                     # -> (id, about, members_count)
await client.get_admins_with_invites(peer)           # -> [(admin_id, invite_count)]
await client.join_chat(peer)
await client.leave_chat(peer)
await client.archive_chat(peer)
await client.unarchive_chat(peer)
await client.pin_dialog(peer)
await client.unpin_dialog(peer)
await client.delete_dialog(peer)
await client.get_pinned_dialogs(folder_id=0)         # 0=main, 1=archive
await client.mark_dialog_read(peer)
```

### ChatMember fields

`user_id`, `first_name`, `last_name`, `username`, `bot`, `status`, `admin_rank`, `full_name`

---

## Forum Topics

```python
await client.get_forum_topics(peer, limit=100)
await client.create_forum_topic(peer, title, icon_color=None, icon_emoji_id=None)
await client.edit_forum_topic(peer, topic_id, title=None, closed=None, hidden=None)
await client.delete_forum_topic_history(peer, top_msg_id)
```

---

## Join Requests

```python
await client.join_request(peer, user_id, approve=True)
await client.all_join_requests(peer, approve=True, link=None)
```

---

## Account & Profile

```python
await client.get_me()                               # -> User
await client.get_users_by_id([user_id, ...])        # -> [User | None]
await client.get_user_full(user_id)                 # -> UserFull
await client.get_dialogs(limit=100)                 # -> [Dialog]
await client.set_profile(first_name=None, last_name=None, about=None)
await client.set_username(username)
await client.set_online()
await client.set_offline()
await client.export_session_string()                # -> str
```

### User fields

`id`, `first_name`, `last_name`, `username`, `phone`, `bot`, `full_name`, `mention`

---

## Contacts & Blocking

```python
await client.get_contacts()                         # -> [User]
await client.add_contact(user_id, first_name, last_name="", phone="")
await client.delete_contacts([user_id, ...])
await client.get_common_chats(user_id, limit=100)   # -> [Chat]
await client.block_user(peer)
await client.unblock_user(peer)
await client.get_blocked_users(limit=100)           # -> [int]
```

---

## Search

```python
await client.search_messages(peer, query, limit=100)
await client.search_global(query, limit=100)
```

---

## Drafts

```python
await client.save_draft(peer, text)
await client.clear_all_drafts()
await client.sync_drafts()
```

---

## Notifications

```python
await client.mute_chat(peer, mute_until)    # unix timestamp; 2**31-1 = forever, 0 = unmute
await client.unmute_chat(peer)
await client.get_notify_settings(peer)
await client.update_notify_settings(peer, mute_until=None, silent=None, show_previews=None)
```

---

## Privacy

```python
from ferogram import PrivacyKey, PrivacyRule

await client.get_privacy(PrivacyKey.STATUS_TIMESTAMP)
await client.set_privacy(PrivacyKey.PHONE_NUMBER, PrivacyRule.ALLOW_CONTACTS)
```

**PrivacyKey:** `STATUS_TIMESTAMP`, `CHAT_INVITE`, `CALL`, `FORWARDS`,
`PROFILE_PHOTO`, `PHONE_NUMBER`, `VOICE_MESSAGES`, `BIO`, `BIRTHDAY`

**PrivacyRule:** `ALLOW_ALL`, `ALLOW_CONTACTS`, `DISALLOW_ALL`, `DISALLOW_CONTACTS`

---

## Sessions & Auth

```python
await client.get_authorizations()
await client.terminate_session(hash)

# QR login
token, expires = await client.export_login_token()
username = await client.check_qr_login(token)   # None if still pending
```

---

## Bot Management

```python
await client.set_bot_commands([("start", "Start the bot"), ("help", "Show help")])
await client.delete_bot_commands(lang_code="")
await client.set_bot_info(name=None, about=None, description=None, lang_code="")
await client.get_bot_info(lang_code="")
await client.open_mini_app(peer, app_type="main", app_value="")   # -> MiniAppSession
```

---

## Stats

```python
await client.get_broadcast_stats(peer)
await client.get_megagroup_stats(peer)
await client.get_game_high_scores(peer, msg_id, user_id)  # -> [(position, user_id, score)]
```

---

## Payments

```python
await client.send_invoice(
    peer, title, description, payload, currency,
    prices=[("Label", 100)],
    photo_url=None,
    need_name=False, need_phone=False, need_email=False,
    need_shipping_address=False, is_flexible=False,
)
```

---

## Peer Resolution

```python
await client.resolve_peer(peer)                 # -> int
await client.resolve_username(username)         # -> int
await client.warm_peer_cache_from_dialogs()
```

---

## Raw API

**Preferred: peer strings auto-resolve, int fields default to 0:**

```python
result = await client.raw.messages.GetHistory(peer="@durov", limit=5)
result = await client.raw.messages.SendMessage(peer="@user", message="hi")
```

**Class-based:**

```python
from ferogram.raw.generated.functions.messages import GetHistory

result = await client.invoke(GetHistory(
    peer=await client._resolve_peer("@durov"),
    offset_id=0, offset_date=0, add_offset=0,
    limit=5, max_id=0, min_id=0, hash=0,
))
# shorthand: await client(func)
```

Results are plain dicts matching the TL schema.

---

## Logging

```python
import ferogram.logging as fero_log

fero_log.setup()            # INFO to stderr
fero_log.setup(level=10)   # DEBUG
```

---

## ChatAction

```python
from ferogram import ChatAction

ChatAction.TYPING
ChatAction.UPLOAD_PHOTO
ChatAction.RECORD_VIDEO
ChatAction.UPLOAD_VIDEO
ChatAction.RECORD_AUDIO
ChatAction.UPLOAD_AUDIO
ChatAction.UPLOAD_DOCUMENT
ChatAction.CHOOSE_STICKER
ChatAction.RECORD_ROUND
ChatAction.UPLOAD_ROUND
ChatAction.CANCEL
```
