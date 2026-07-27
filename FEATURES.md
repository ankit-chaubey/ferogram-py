# ferogram-py: Feature Reference

This document matches the current Python layer shipped in `ferogram-py`.
All client methods are async unless marked otherwise.

`peer` usually accepts `"@username"`, `"me"`, or an integer-like peer identifier.

## Imports

```python
from ferogram import Client, filters
from ferogram import ChatAction
from ferogram import InlineArticle, InlinePhoto, InlineDocument, InlineMessageId
from ferogram import PrivacyKey, PrivacyRule
from ferogram import InlineButton, InlineKeyboard, ReplyButton, ReplyKeyboard
from ferogram import RemoveKeyboard, ForceReply
```

Raw API styles:

```python
client.raw.messages.SendMessage(...)
from ferogram.raw import functions
from ferogram.raw.api import functions
from ferogram.raw.generated.functions.messages import SendMessage
```

## Client setup

```python
from ferogram import Client

app = Client(
    session="mybot",       # string session name or session object
    api_id=123456,
    api_hash="abc...",
    bot_token="123:TOKEN", # omit for userbot
)

app.run()
# or
await app.start()
await app.run_until_disconnected()
# or
async with app as client:
    ...
```

### Full init signature

```python
app = Client(
    session="mybot",
    api_id=123456,
    api_hash="abc...",
    bot_token="123:TOKEN",
    phone="+1234567890",
    password="2fa_password",

    workers=4,
    parse_mode=None,
    flood_sleep_threshold=60,

    proxy=None,
    allow_ipv6=False,
    dc_addr=None,
    probe_transport=False,
    resilient_connect=False,

    session_string=None,

    catch_up=False,
    pfs=False,
    update_queue_capacity=None,
    update_overflow=None,
    low_memory_mode=False,

    device=None,
    system_version=None,
    app_version=None,
    lang_code=None,
    system_lang_code=None,
    lang_pack=None,

    allow_missing_channel_hash=False,
    auto_resolve_peers=False,
    in_memory=False,
)
```

`parse_mode` accepts `None`, `"html"`, or `"markdown"`.

## Session backends

```python
from ferogram import (
    FileSession,
    MemorySession,
    StringSession,
    SqliteSession,
    CustomSession,
)
```

Examples:

```python
Client(session=FileSession("mybot"), ...)
Client(session=SqliteSession("mybot"), ...)
Client(session=MemorySession(), ...)
Client(session=StringSession("base64_session"), ...)
```

`CustomSession` accepts any Python object with `save`, `load`, and `delete` methods.

## Event handlers

Available decorators:

```python
@app.on_message(*filters, group=0)
@app.on_edited_message(*filters, group=0)
@app.on_message_deleted(*filters, group=0)
@app.on_callback_query(*filters, group=0)
@app.on_inline_query(*filters, group=0)
@app.on_inline_send(*filters, group=0)
@app.on_user_status(*filters, group=0)
@app.on_chat_action(*filters, group=0)
@app.on_participant_update(*filters, group=0)
@app.on_join_request(*filters, group=0)
@app.on_message_reaction(*filters, group=0)
@app.on_poll_vote(*filters, group=0)
@app.on_bot_stopped(*filters, group=0)
@app.on_shipping_query(*filters, group=0)
@app.on_pre_checkout_query(*filters, group=0)
@app.on_chat_boost(*filters, group=0)
@app.on_raw_update(*filters, group=0)
```

Handler signature:

```python
async def handler(client, update):
    ...
```

Group ordering:

- lower group numbers run first
- within a group, the first matching handler wins

Dispatch control:

```python
from ferogram import StopPropagation, ContinuePropagation
```

- `raise StopPropagation` stops further processing
- `raise ContinuePropagation` skips the current handler and keeps searching in the same group

Runtime registration:

```python
app.add_handler("message", func, *filters, group=0)
app.remove_handler("message", func, group=0)
```

## Filters

Import:

```python
from ferogram import filters
```

### Message filters

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
| `filters.outgoing` | sent by you |
| `filters.incoming` | not sent by you |
| `filters.mentioned` | messages mentioning you |
| `filters.forwarded` | forwarded messages |
| `filters.via_bot` | sent via an inline bot |
| `filters.reply` | replies |
| `filters.pinned` | pinned messages |
| `filters.album` | grouped / album messages |
| `filters.scheduled` | scheduled messages |
| `filters.bot` | messages from bots |
| `filters.no_bot` | messages not from bots |

### Text helpers

```python
filters.command("start")
filters.regex(r"^/ping")
filters.text_contains("hello")
filters.startswith("/cmd")
filters.endswith("!")
filters.min_length(3)
filters.max_length(100)
```

### Peer / sender helpers

```python
filters.user(12345)
filters.chat(-1001234567890)
```

### Callback query filters

```python
filters.data("btn1")
filters.data_regex(r"^page:")
filters.data_startswith("page:")
```

### Inline query filters

```python
filters.inline()
filters.inline(r"^cat")
```

### Status / action / reaction filters

```python
filters.online
filters.offline
filters.status("online")
filters.action("typing")
filters.typing
filters.reaction("👍", "❤️")
filters.participant_status("member", "admin")
filters.constructor(0x12345678)
filters.update_type("UpdateNewMessage")
```

### Composition

```python
filters.AND(filters.private, filters.text)
filters.OR(filters.photo, filters.document)
filters.NOT(filters.outgoing)
```

## Messaging

```python
await client.send_message(peer, text, parse_mode=None, reply_markup=None)
await client.send_to_self(text)
await client.edit_message(peer, message_id, new_text)
await client.delete_message(message_id, revoke=True)
await client.delete_messages([id1, id2], revoke=True)
await client.forward_messages(destination, source, [msg_id, ...])
await client.pin_message(peer, message_id)
await client.unpin_message(peer, message_id)
await client.unpin_all_messages(peer)
await client.mark_as_read(peer)
await client.mark_dialog_read(peer)
await client.clear_mentions(peer)
await client.send_reaction(peer, message_id, emoji)
await client.read_reactions(peer)
await client.clear_recent_reactions()
await client.get_reaction_list(peer, msg_id, limit=100)
await client.delete_reaction(peer, msg_id, participant)
async for reaction in client.iter_reaction_users(peer, msg_id, reaction=None):
    ...
await client.send_chat_action(peer, "typing")
await client.send_dice(peer, emoticon="🎲")
await client.translate_messages(peer, [msg_id], to_lang="en")
await client.get_web_page_preview(text)
```

`send_message` supports `parse_mode="html"` and `parse_mode="markdown"` in addition to plain text.

### Message object fields

The current Python `Message` dataclass exposes:

`id`, `text`, `sender_id`, `peer_id`, `date`, `edit_date`, `reply_to_msg_id`, `forward_from_id`, `media`, `entities`, `views`, `via_bot_id`, `grouped_id`, `out`, `mentioned`, `silent`, `pinned`, `chat_id`

Notes:

- `chat_id` is derived from `peer_id`
- fields such as `has_photo`, `has_document`, `reply_count`, and `post_author` are not part of the current Python dataclass

### Message helper methods

The current public Python layer does not expose convenience methods such as `message.reply()` or `message.edit()` in the dataclass itself. Use the client methods above.

## Keyboards

### Inline keyboards

```python
from ferogram import InlineButton, InlineKeyboard

kb = InlineKeyboard()
kb.add_row([
    InlineButton.callback("Click me", b"btn1"),
    InlineButton.url("Open site", "https://example.com"),
])
kb.add_row([
    InlineButton.switch_inline("Search here", "cats"),
    InlineButton.switch_elsewhere("Search everywhere", "cats"),
])
kb.add_row([
    InlineButton.copy_text("Copy code", "print('hi')"),
])

await client.send_message(peer, "Pick one:", reply_markup=kb)
```

Available inline button constructors:

- `InlineButton.callback(text, data: bytes)`
- `InlineButton.url(text, url)`
- `InlineButton.switch_inline(text, query)`
- `InlineButton.switch_elsewhere(text, query)`
- `InlineButton.copy_text(text, copy_text)`
- `InlineButton.mini_app(text, url)`
- `InlineButton.mini_app_simple(text, url)`
- `InlineButton.game(text)`
- `InlineButton.buy(text)`

### Reply keyboards

```python
from ferogram import ReplyButton, ReplyKeyboard

kb = ReplyKeyboard(resize=True, single_use=True, selective=False, placeholder="Choose one")
kb.add_row([ReplyButton.text("Option A"), ReplyButton.text("Option B")])
kb.add_row([ReplyButton.request_phone("Share phone")])

await client.send_message(peer, "Choose:", reply_markup=kb)
```

Reply button constructors:

- `ReplyButton.text(label)`
- `ReplyButton.request_phone(label)`
- `ReplyButton.request_geo(label)`
- `ReplyButton.request_poll(label)`
- `ReplyButton.request_quiz(label)`

### Remove keyboard / force reply

```python
from ferogram import RemoveKeyboard, ForceReply

await client.send_message(peer, "Done.", reply_markup=RemoveKeyboard())
await client.send_message(peer, "Reply to this:", reply_markup=ForceReply())
```

`reply_markup` is supported by `send_message` and `edit_inline_message` in the current Python layer.

## Media

```python
await client.send_photo(peer, path, caption="")
await client.send_document(peer, path, caption="", mime_type=None)
await client.send_file(peer, path, caption="", mime_type=None)
await client.send_audio(peer, path, caption="")
await client.send_video(peer, path, caption="")
await client.send_voice(peer, path, caption="")
await client.send_sticker(peer, path)
await client.upload_file(path)
await client.upload_media(peer, path)
await client.download_media(peer, msg_id, path)
await client.download_with_progress(peer, msg_id, path, on_progress=None)
await client.upload_with_progress(path, on_progress=None)
await client.edit_chat_photo(peer, path)
await client.delete_profile_photos()
await client.get_profile_photos(peer, limit=100)
await client.get_chat_photos(peer, limit=100)
```

Important current behavior:

- `send_photo`, `send_document`, `send_file`, `send_audio`, `send_video`, `send_voice`, and `send_sticker` take filesystem paths
- `send_file` is an alias of `send_document`
- `upload_media` returns the sent message id when it can extract one
- `upload_with_progress` currently returns the uploaded file id as a string
- `download_with_progress` and `upload_with_progress` accept `on_progress` for compatibility, but the callback is not wired in the current Python implementation

## Polls

```python
await client.send_poll(
    peer, question, answers=["A", "B", "C"],
    quiz=False, correct_index=None, multiple_choice=False,
    public_voters=False, shuffle_answers=False,
    hide_results_until_close=False,
    close_period=None,
    close_date=None,
    solution=None,
)
await client.send_vote(peer, msg_id, options=[b"\x00"])
await client.get_poll_votes(peer, msg_id, limit=100)
await client.get_poll_results(peer, msg_id, poll_hash=0)
await client.poll_results(peer, msg_id)
await client.get_poll_stats(peer, msg_id)
```

Current return behavior:

- `get_poll_votes` returns `list[tuple[int, bytes]]`
- `get_poll_results` performs the RPC and does not currently return a parsed result
- `poll_results` is an alias for `get_poll_stats`
- `get_poll_stats` currently returns a stringified result from the stats RPC

## Inline bots

### Answer callback queries

```python
await client.answer_callback_query(query_id, text=None, alert=False)
```

### Answer inline queries

Use `InlineArticle`, `InlinePhoto`, or `InlineDocument`.

```python
await client.answer_inline_query(
    query_id,
    results=[...],
    cache_time=300,
    is_personal=False,
    next_offset=None,
    switch_pm=None,
)

await client.answer_inline_query_articles(
    query_id,
    articles=[
        ("id1", "Title One", "Message text one"),
        ("id2", "Title Two", "Message text two"),
    ],
    cache_time=300,
    is_personal=False,
    next_offset=None,
)
```

Inline result types:

- `InlineArticle(id, title, message_text, description=None, url=None, thumb_url=None, reply_markup=None)`
- `InlinePhoto(id, title, message_text, photo_url, photo_width=0, photo_height=0, description=None, thumb_url=None, mime_type="image/jpeg", reply_markup=None)`
- `InlineDocument(id, title, message_text, document_url, mime_type, description=None, thumb_url=None, reply_markup=None)`

### Edit inline messages

```python
from ferogram import InlineMessageId

await client.edit_inline_message(
    InlineMessageId(dc_id=2, id_bytes=b"..."),
    "updated text",
    reply_markup=None,
)
```

`edit_inline_message` also accepts a `(dc_id, id_bytes)` tuple.

## Participants

```python
await client.get_participants(peer, limit=200)
await client.get_participants_filtered(peer, filter="recent", limit=200)
await client.kick_participant(peer, user)
await client.ban_participant(peer, user)
await client.ban_participant_until(peer, user, until_date)
await client.promote_participant(peer, user, rights=None)
await client.demote_participant(peer, user)
await client.get_admins_with_invites(peer)
```

## Chats and groups

```python
await client.create_group(title, users=[])
await client.create_channel(title, about="", broadcast=True, megagroup=False)
await client.delete_channel(peer)
await client.delete_chat(chat_id)
await client.delete_chat_history(peer, max_id=0, revoke=False)
await client.invite_users(peer, [user_id, ...])
await client.get_chat_administrators(peer)
await client.get_online_count(peer)
await client.get_chat_full(peer)
await client.join_chat(peer)
await client.leave_chat(peer)
await client.archive_chat(peer)
await client.unarchive_chat(peer)
await client.pin_dialog(peer)
await client.unpin_dialog(peer)
await client.delete_dialog(peer)
await client.get_pinned_dialogs(folder_id=0)
```

## Forum topics

```python
await client.toggle_forum(peer, enabled=True)
await client.get_forum_topics(peer, limit=100)
await client.create_forum_topic(peer, title, icon_color=None, icon_emoji_id=None)
await client.edit_forum_topic(peer, topic_id, title=None, closed=None, hidden=None)
await client.delete_forum_topic_history(peer, top_msg_id)
```

## Join requests

```python
await client.join_request(peer, user_id, approve=True)
await client.all_join_requests(peer, approve=True, link=None)
```

## Invite links

```python
await client.invite_links(peer)
await client.invite_links(peer, primary_only=True)
await client.invite_links(peer, revoked=True)

async for link in client.iter_invite_links(peer, revoked=False):
    ...

async for member in client.iter_invite_link_members(peer, link, requested=False):
    ...

await client.edit_invite_link(peer, link, expire_date=None, usage_limit=None, request_needed=None, title=None)
await client.revoke_invite_link(peer, link)
await client.delete_invite_link(peer, link)
await client.clear_revoked_invite_links(peer)
await client.resolve_invite_link(link)
await client.join_invite_link(link)
```

## Account and profile

```python
await client.get_me()
await client.get_users_by_id([user_id, ...])
await client.get_user_full(user_id)
await client.get_dialogs(limit=100)
async for dialog in client.iter_dialogs(limit=None):
    ...
async for msg in client.iter_messages(peer, limit=None, offset_id=0):
    ...
await client.set_profile(first_name=None, last_name=None, about=None)
await client.set_username(username)
await client.set_online()
await client.set_offline()
await client.export_session_string()
```

`User` fields:

`id`, `first_name`, `last_name`, `username`, `phone`, `is_bot`, `is_verified`, `is_restricted`, `is_scam`, `is_fake`, `is_premium`, `access_hash`, `lang_code`, `full_name`

## Contacts and blocking

```python
await client.get_contacts()
await client.add_contact(user_id, first_name, last_name="", phone="")
await client.delete_contacts([user_id, ...])
await client.get_common_chats(user_id, limit=100)
await client.block_user(peer)
await client.unblock_user(peer)
await client.get_blocked_users(limit=100)
```

## Search

```python
await client.search_messages(peer, query, limit=100)
await client.search_global(query, limit=100)
await client.search_peer(query, limit=100)
```

## Drafts

```python
await client.save_draft(peer, text)
await client.clear_all_drafts()
await client.sync_drafts()
```

## Notifications

```python
await client.mute_chat(peer, mute_until)
await client.unmute_chat(peer)
await client.get_notify_settings(peer)
await client.update_notify_settings(peer, mute_until=None, silent=None, show_previews=None)
```

## Privacy

```python
from ferogram import PrivacyKey, PrivacyRule

await client.get_privacy(PrivacyKey.STATUS_TIMESTAMP)
await client.set_privacy(PrivacyKey.PHONE_NUMBER, PrivacyRule.ALLOW_CONTACTS)
```

Privacy keys:

`STATUS_TIMESTAMP`, `CHAT_INVITE`, `CALL`, `FORWARDS`, `PROFILE_PHOTO`, `PHONE_NUMBER`, `VOICE_MESSAGES`, `BIO`, `BIRTHDAY`

Privacy rules:

`ALLOW_ALL`, `ALLOW_CONTACTS`, `DISALLOW_ALL`, `DISALLOW_CONTACTS`

## Sessions and auth

```python
await client.is_authorized()
await client.request_login_code(phone)
await client.sign_in(phone, code, code_hash, password=None)
await client.check_password(pw_info, password)
await client.bot_sign_in(token)
await client.login_bot(token)
await client.sign_out()
await client.export_login_token()
await client.check_qr_login(token)
await client.get_authorizations()
await client.terminate_session(hash)
```

`sign_out()` captures a `future_auth_token` when Telegram provides one, and
`request_login_code()` replays it automatically on the next login. When
that succeeds, Telegram authorizes the session immediately, no code entry
needed - check for `"_": "auth.sentCodeSuccess"` on the returned dict.

## Bot management

```python
await client.set_bot_commands([("start", "Start the bot"), ("help", "Show help")])
await client.delete_bot_commands(lang_code="")
await client.set_bot_info(name=None, about=None, description=None, lang_code="")
await client.get_bot_info(lang_code="")
await client.open_mini_app(peer, app_type="main", app_value="")
```

## Stats

```python
await client.get_broadcast_stats(peer)
await client.get_megagroup_stats(peer)
await client.get_game_high_scores(peer, msg_id, user_id)
await client.get_poll_stats(peer, msg_id)
```

## Payments

```python
await client.send_invoice(
    peer, title, description, payload, currency,
    prices=[("Label", 100)],
    photo_url=None,
    need_name=False,
    need_phone=False,
    need_email=False,
    need_shipping_address=False,
    is_flexible=False,
)
```

## Custom emoji

```python
await client.get_custom_emoji_documents(document_ids=[...])
```

Returns the subset of IDs that resolved successfully.

## Peer resolution

```python
await client.resolve_peer(peer)
await client.resolve_username(username)
await client.resolve(peer)
await client.warm_peer_cache_from_dialogs()
```

`resolve_peer` and `resolve_username` return numeric peer identifiers.

## Raw API

Four styles are available. The difference is only ergonomics.

### 1. Namespace proxy

```python
await client.raw.messages.SendMessage(peer="@user", message="Hello", no_webpage=True)
await client.raw.messages.GetHistory(peer="@durov", limit=10)
await client.raw.channels.GetFullChannel(channel="@telegram")
```

### 2. `functions` import

```python
from ferogram.raw import functions

await client.invoke(functions.messages.SendMessage(
    peer=await client.resolve_peer("@user"),
    message="Hello",
    random_id=0,
    no_webpage=True,
))
```

### 3. `api` import

```python
from ferogram.raw.api import functions
```

### 4. Direct class import

```python
from ferogram.raw.generated.functions.messages import GetHistory, SendMessage
```

## Logging

```python
import ferogram.logging as fero_log

fero_log.setup()
fero_log.setup(level=10)
```
