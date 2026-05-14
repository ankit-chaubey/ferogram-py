# ferogram-py: Feature Reference

Python bindings for the ferogram MTProto client.

All client methods are async. The `peer` parameter accepts `"@username"`, `"me"`, or a numeric ID (int or string).


## Imports

High-level usage:

```python
from ferogram import Client
from ferogram import filters
from ferogram import ChatAction
from ferogram import InlineArticle, InlinePhoto, InlineDocument
from ferogram import InlineMessageId
from ferogram import PrivacyKey, PrivacyRule
from ferogram import InlineButton, InlineKeyboard
from ferogram import ReplyButton, ReplyKeyboard
from ferogram import RemoveKeyboard, ForceReply
```

Raw API usage (four styles, see the [Raw API](#raw-api) section for details):

```python
# style 1: namespace proxy, no extra import needed
client.raw.messages.SendMessage(...)

# style 2
from ferogram.raw import functions

# style 3
from ferogram.raw.api import functions

# style 4: direct class import
from ferogram.raw.generated.functions.messages import SendMessage
from ferogram.raw.generated.types.messages import Messages
```


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

### Full init signature

These are all the kwargs you can pass to `Client(...)`. Most of them you will never need, but they are all there.

```python
app = Client(
    session="mybot",                     # session file name (no .session extension)
    api_id=123456,
    api_hash="abc...",
    bot_token="123:TOKEN",               # omit for userbot
    phone="+1234567890",                 # for userbot interactive login
    password="2fa_password",             # 2FA password if set

    # Network
    proxy=None,                          # "socks5://host:port" or an MTProxy t.me link
    allow_ipv6=False,                    # connect over IPv6 when available
    dc_addr=None,                        # override DC address, e.g. "149.154.167.51:443"
    probe_transport=False,               # try multiple transports on first connect
    resilient_connect=False,             # keep retrying on initial connect failure

    # Session backend (priority: in_memory > session_string > session file)
    session_string=None,                 # base64 session string instead of file
    in_memory=False,                     # ephemeral session, nothing written to disk

    # Sync and updates
    catch_up=False,                      # fetch missed updates on reconnect
    pfs=False,                           # Perfect Forward Secrecy for the session
    update_queue_capacity=None,          # max pending updates before overflow kicks in
    update_overflow=None,                # "drop_oldest" or "drop_newest"
    low_memory_mode=False,               # smaller update queue, saves RAM on constrained devices

    # InitConnection identity
    device=None,                         # device model string sent in InitConnection
    system_version=None,                 # OS version string
    app_version=None,                    # app version string
    lang_code=None,                      # IETF language tag, e.g. "en"
    system_lang_code=None,               # system locale tag
    lang_pack=None,                      # language pack name

    # Experimental
    allow_missing_channel_hash=False,    # skip access hash requirement for channels
    auto_resolve_peers=False,            # resolve unknown peers automatically
)
```

`proxy` supports two formats:
- SOCKS5: `"socks5://host:port"`
- MTProxy: `"https://t.me/proxy?server=...&port=...&secret=..."`


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
@app.on_guest_chat_query(*filters)
@app.on_raw_update(*filters)
```

Handler signature: `async def handler(client, update):`


## Filters

Import:
```python
from ferogram import filters
```

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


## Messaging

```python
await client.send_message(peer, text, parse_mode=None, reply_markup=None)
# parse_mode: None (plain) | "html" | "markdown"
# reply_markup: InlineKeyboard, ReplyKeyboard, RemoveKeyboard, or ForceReply
#
# "markdown" uses MarkdownV2 format since ferogram 0.3.9.
#   __text__ = Underline (was Italic in V1)
#   ~text~   = Strike    (was ~~text~~ in V1)
#   > text   = Blockquote (new)
#   **> text = Expandable blockquote (new)
# HTML parse_mode supports these tags:
#   <b>, <strong>, <i>, <em>, <u>, <ins>, <s>, <del>, <strike>
#   <tg-spoiler>, <span class="tg-spoiler">
#   <blockquote>, <blockquote expandable>
#   <tg-time unix="N" format="F">, <tg-emoji emoji-id="N">
#   <code>, <pre>, <pre><code class="language-X">

await client.send_to_self(text)
await client.edit_message(peer, message_id, new_text)
await client.delete_message(message_id, revoke=True)
await client.delete_messages([id1, id2], revoke=True)
await client.forward_messages(destination, source, [msg_id, ...])
await client.pin_message(peer, message_id)
await client.unpin_message(peer, message_id)
await client.unpin_all_messages(peer)
await client.get_messages_by_id(peer, [id1, id2])
await client.get_message(peer, msg_id)                  # -> Message | None (single fetch)
await client.get_message_history(peer, limit=100, offset_id=0)
await client.get_pinned_message(peer)                   # -> Message | None
await client.get_reply_to_message(peer, msg_id)         # -> Message | None
await client.get_scheduled_messages(peer)               # -> [Message]
await client.get_discussion_message(peer, msg_id)       # -> (messages, unread, max_id, read_max_id)
await client.send_reaction(peer, message_id, emoji)
await client.read_reactions(peer)
await client.clear_recent_reactions()
await client.get_reaction_list(peer, msg_id, limit=100) # -> [(peer_id, emoji)]
await client.delete_reaction(peer, msg_id, participant) # remove a specific user's reaction (admin only)
async for reaction in client.iter_reaction_users(peer, msg_id, reaction=None):
    ...                                                 # yields reaction objects
await client.mark_as_read(peer)
await client.clear_mentions(peer)
await client.send_chat_action(peer, "typing")           # or ChatAction.TYPING
await client.send_dice(peer, emoticon="🎲")
await client.translate_messages(peer, [msg_id], to_lang="en")   # -> [str]
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


## Keyboards

Build and attach keyboards to messages.

```python
from ferogram import InlineButton, InlineKeyboard
from ferogram import ReplyButton, ReplyKeyboard
from ferogram import RemoveKeyboard, ForceReply
```

**Inline keyboard**

```python
kb = InlineKeyboard([
    [InlineButton("Click me", data="btn1"), InlineButton("Other", data="btn2")],
    [InlineButton("Open URL", url="https://example.com")],
])

await client.send_message(peer, "Pick one:", reply_markup=kb)
```

`InlineButton` takes `text` (required) and one of `data`, `url`, `switch_inline_query`, or `switch_inline_query_current_chat`.

**Reply keyboard**

```python
kb = ReplyKeyboard([
    [ReplyButton("Option A"), ReplyButton("Option B")],
    [ReplyButton("Cancel")],
], resize=True, one_time=True)

await client.send_message(peer, "Choose:", reply_markup=kb)
```

**Remove keyboard**

```python
await client.send_message(peer, "Done.", reply_markup=RemoveKeyboard())
```

**Force reply**

```python
await client.send_message(peer, "Reply to this:", reply_markup=ForceReply())
```

`reply_markup` works on `send_message`, `send_photo`, `send_document`, `send_file`, and `edit_message`.


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


## Polls

```python
await client.send_poll(
    peer, question, answers=["A", "B", "C"],
    quiz=False, correct_index=None, multiple_choice=False,
    public_voters=False, shuffle_answers=False,
    hide_results_until_close=False,
    close_period=None,   # auto-close after N seconds (1-600)
    close_date=None,     # auto-close at unix timestamp
    solution=None,       # explanation shown after quiz answer
)
await client.send_vote(peer, msg_id, options=[b"\x00"])
await client.get_poll_votes(peer, msg_id, limit=100)    # -> [(user_id, option_bytes)]
await client.get_poll_results(peer, msg_id, poll_hash)  # fetch and cache latest results
await client.get_poll_stats(peer, msg_id)               # -> int (interaction count)
```


## Inline Bots

### Answering callback queries

```python
await client.answer_callback_query(query_id, text=None, alert=False)
```

### Answering inline queries

Use `InlineArticle`, `InlinePhoto`, or `InlineDocument` to build results and pass them to `answer_inline_query`.

```python
from ferogram import InlineArticle, InlinePhoto, InlineDocument

await client.answer_inline_query(
    query_id,
    results=[...],
    cache_time=300,
    is_personal=False,
    next_offset=None,        # pass a string to enable pagination
    switch_pm=None,          # ("Button text", "start_param") to show a "go to PM" button
)
```

**InlineArticle**

```python
InlineArticle(
    id="1",
    title="My Article",
    message_text="Text sent when user picks this result.",
    description=None,        # subtitle shown in the result list
    url=None,                # URL shown under the title
    thumb_url=None,          # thumbnail URL
    reply_markup=None,       # InlineKeyboard attached to the sent message
)
```

**InlinePhoto**

```python
InlinePhoto(
    id="2",
    title="A Photo",
    message_text="Caption for the photo.",
    photo_url="https://example.com/photo.jpg",   # required, direct image URL
    photo_width=0,           # optional dimensions hint
    photo_height=0,
    description=None,
    thumb_url=None,
    mime_type="image/jpeg",
    reply_markup=None,
)
```

**InlineDocument**

```python
InlineDocument(
    id="3",
    title="A File",
    message_text="Here is the file.",
    document_url="https://example.com/file.pdf",  # required, direct file URL
    mime_type="application/pdf",                  # required
    description=None,
    thumb_url=None,
    reply_markup=None,
)
```

**Simple articles shortcut**

If you only need plain text articles with no extra fields, there is a lighter helper:

```python
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

### Editing inline messages

After answering an inline query, you can edit the message later using the ID from `InlineSend`.

```python
from ferogram import InlineMessageId

await client.edit_inline_message(
    InlineMessageId(dc_id=2, id_bytes=b"..."),
    "updated text",
    reply_markup=None,       # optionally attach or update the keyboard
)
```

To get the `InlineMessageId` from a send event:

```python
@app.on_inline_send()
async def handler(client, send):
    # send.user_id       int
    # send.query         str
    # send.result_id     str
    # send.msg_id_bytes  bytes | None  (raw serialized InputBotInlineMessageId)
    # send.msg_id_dc     int | None    (DC where the message lives)

    if send.msg_id_bytes:
        msg_id = InlineMessageId(send.msg_id_dc, bytes(send.msg_id_bytes))
        await client.edit_inline_message(msg_id, "updated!")
```

`msg_id_bytes` and `msg_id_dc` are `None` when the bot did not request inline feedback for this query (i.e. the result was sent without enabling `@BotFather` inline feedback).


## Participants

These methods work on groups, supergroups, and channels.

```python
await client.get_participants(peer, limit=200)
# -> list[ChatMember]

await client.get_participants_filtered(peer, filter="recent", limit=200)
# filter: "recent" | "admins" | "kicked" | "banned" | "bots"
# -> list[ChatMember]

await client.kick_participant(peer, user)
# Removes the user from the chat. They can rejoin if the chat is public or they have an invite link.

await client.ban_participant(peer, user)
# Permanently bans until manually lifted.

await client.ban_participant_until(peer, user, until_date)
# until_date is a unix timestamp. The ban lifts automatically after that time.

await client.promote_participant(peer, user, rights=None)
# rights is a list of permission strings. Pass None to grant all admin rights.
# Valid strings: "change_info", "post_messages", "edit_messages",
#                "delete_messages", "ban_users", "invite_users",
#                "pin_messages", "add_admins", "manage_call"

await client.demote_participant(peer, user)
# Removes all admin rights. The user stays as a regular member.

await client.get_profile_photos(peer, limit=100)
# -> list of (file_id, access_hash, dc_id) tuples

await client.search_peer(query)
# Search the local peer cache by name or username.
# -> list[str] of matching peer identifiers

client.signal_network_restored()
# Not async. Call this when you know network is back to trigger an immediate
# reconnect attempt instead of waiting for the retry timer.
```

### ChatMember fields

`user_id`, `first_name`, `last_name`, `username`, `bot`, `status`, `admin_rank`, `full_name`


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


## Forum Topics

```python
await client.get_forum_topics(peer, limit=100)
await client.create_forum_topic(peer, title, icon_color=None, icon_emoji_id=None)
await client.edit_forum_topic(peer, topic_id, title=None, closed=None, hidden=None)
await client.delete_forum_topic_history(peer, top_msg_id)
```


## Join Requests

```python
await client.join_request(peer, user_id, approve=True)
await client.all_join_requests(peer, approve=True, link=None)
```


## Invite Links

```python
await client.invite_links(peer)                          # -> [ExportedChatInvite]
await client.invite_links(peer, primary_only=True)       # -> ExportedChatInvite (primary link)
await client.invite_links(peer, revoked=True)            # -> [ExportedChatInvite] (revoked links)

async for link in client.iter_invite_links(peer, revoked=False):
    ...                                                  # yields ExportedChatInvite objects

async for member in client.iter_invite_link_members(peer, link, requested=False):
    ...                                                  # yields ChatInviteImporter objects

await client.edit_invite_link(
    peer, link,
    expire_date=None,      # unix timestamp; None = no expiry
    usage_limit=None,      # None = unlimited
    request_needed=None,   # require admin approval to join
    title=None,
)
await client.revoke_invite_link(peer, link)              # -> revoked ExportedChatInvite
await client.delete_invite_link(peer, link)              # delete a revoked link permanently
await client.clear_revoked_invite_links(peer)            # delete all revoked links

await client.resolve_invite_link(link)                   # peek without joining -> ChatInvite
await client.join_invite_link(link)                      # join and return InputPeer
```


## Account & Profile

```python
await client.get_me()                               # -> User
await client.get_users_by_id([user_id, ...])        # -> [User | None]
await client.get_user_full(user_id)                 # -> UserFull
await client.get_dialogs(limit=100)                 # -> [Dialog]
async for dialog in client.iter_dialogs(limit=None):
    ...                                             # yields Dialog objects
async for msg in client.iter_messages(peer, limit=None, offset_id=0):
    ...                                             # yields Message objects, newest first
await client.set_profile(first_name=None, last_name=None, about=None)
await client.set_username(username)
await client.set_online()
await client.set_offline()
await client.export_session_string()                # -> str
```

### User fields

`id`, `first_name`, `last_name`, `username`, `phone`, `bot`, `full_name`, `mention`


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


## Search

```python
await client.search_messages(peer, query, limit=100)
await client.search_global(query, limit=100)
```


## Drafts

```python
await client.save_draft(peer, text)
await client.clear_all_drafts()
await client.sync_drafts()
```


## Notifications

```python
await client.mute_chat(peer, mute_until)    # unix timestamp; 2**31-1 = forever, 0 = unmute
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

**PrivacyKey:** `STATUS_TIMESTAMP`, `CHAT_INVITE`, `CALL`, `FORWARDS`,
`PROFILE_PHOTO`, `PHONE_NUMBER`, `VOICE_MESSAGES`, `BIO`, `BIRTHDAY`

**PrivacyRule:** `ALLOW_ALL`, `ALLOW_CONTACTS`, `DISALLOW_ALL`, `DISALLOW_CONTACTS`


## Sessions & Auth

```python
await client.is_authorized()                        # -> bool
await client.login_bot(token)                       # sign in as bot after start()
await client.get_authorizations()                   # -> [Authorization]
await client.terminate_session(hash)

# QR login
token, expires = await client.export_login_token()
username = await client.check_qr_login(token)   # None if still pending
```


## Bot Management

```python
await client.set_bot_commands([("start", "Start the bot"), ("help", "Show help")])
await client.delete_bot_commands(lang_code="")
await client.set_bot_info(name=None, about=None, description=None, lang_code="")
await client.get_bot_info(lang_code="")
await client.open_mini_app(peer, app_type="main", app_value="")   # -> MiniAppSession
```


## Stats

```python
await client.get_broadcast_stats(peer)              # -> BroadcastStats
await client.get_megagroup_stats(peer)              # -> MegagroupStats
await client.get_game_high_scores(peer, msg_id, user_id)  # -> [(position, user_id, score)]
await client.get_poll_stats(peer, msg_id)           # -> int (interaction count)
```


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


## Custom Emoji

```python
await client.get_custom_emoji_documents(document_ids=[...])
# Pass a list of custom emoji document IDs.
# Returns the subset of IDs that resolved successfully.
```


## Peer Resolution

```python
await client.resolve_peer(peer)                 # -> int
await client.resolve_username(username)         # -> int
await client.warm_peer_cache_from_dialogs()
```


## Raw API

All four styles produce identical TL requests. The difference is only ergonomics and abstraction level.

**Pick one:**

| Style | When to use |
|---|---|
| `client.raw` | 90% of cases. Simplest. |
| `from ferogram.raw import functions` | When you need full explicit control. |
| `from ferogram.raw.api import functions` | Compatibility only. Do not use for new code. |
| Direct `generated` import | Advanced use: tooling, debugging, type checking. |


### 1. Namespace proxy (recommended)

No extra import. Peer strings auto-resolve. Int fields default to 0.

```python
# send a message
result = await client.raw.messages.SendMessage(
    peer="@user",
    message="Hello",
    no_webpage=True,
)

# fetch history
result = await client.raw.messages.GetHistory(
    peer="@durov",
    limit=10,
)

# get chat info
result = await client.raw.channels.GetFullChannel(
    channel="@telegram",
)
```


### 2. `functions` import (recommended for explicit control)

Use when you want to be explicit about every field. Peer must be resolved manually.

```python
from ferogram.raw import functions

# send a message
result = await client.invoke(
    functions.messages.SendMessage(
        peer=await client.resolve_peer("@user"),
        message="Hello",
        random_id=0,     # use a unique int per request in production
        no_webpage=True,
    )
)

# fetch history
result = await client.invoke(
    functions.messages.GetHistory(
        peer=await client.resolve_peer("@durov"),
        offset_id=0,
        offset_date=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
        hash=0,
    )
)

# shorthand: await client(...) is equivalent to await client.invoke(...)
result = await client(functions.users.GetFullUser(id=await client.resolve_peer("@user")))
```


### 3. `api` import (compatibility only)

Same as style 2. Exists for backward compatibility. Do not use for new code.

```python
from ferogram.raw.api import functions

result = await client.invoke(
    functions.messages.SendMessage(
        peer=await client.resolve_peer("@user"),
        message="Hello",
        random_id=0,
    )
)
```


### 4. Direct class import (advanced)

Import a specific function or type by name. Useful for tooling, type annotations, or when you only use one or two classes.

```python
from ferogram.raw.generated.functions.messages import GetHistory, SendMessage
from ferogram.raw.generated.functions.users import GetFullUser

result = await client.invoke(
    GetHistory(
        peer=await client.resolve_peer("@durov"),
        offset_id=0,
        offset_date=0,
        add_offset=0,
        limit=10,
        max_id=0,
        min_id=0,
        hash=0,
    )
)
```

The `generated/` directory is internal codegen output. Direct imports from it are considered advanced usage and may change between versions.


## Logging

```python
import ferogram.logging as fero_log

fero_log.setup()            # INFO to stderr
fero_log.setup(level=10)   # DEBUG
```


## GuestChatQuery

Fired when a bot receives a guest-chat inline query (`updateBotGuestChatQuery`). Bots only.

```python
@app.on_guest_chat_query()
async def handler(client, query):
    # query.query_id  int
    # query.qts       int
    pass
```

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
