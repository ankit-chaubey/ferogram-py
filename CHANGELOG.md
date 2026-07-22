## Unreleased

- Fixed a codegen bug that corrupted `updates.getDifference` and any response with a `Poll` or `WallPaper`: `flags:#` was assumed to always be first on the wire and hoisted to the front of `from_bytes()`/`to_bytes()`. `poll#966e2dbf`, `wallPaper#a437c3ed`, and `wallPaperNoFile#e0804116` all declare `id:long` before `flags:#`, so those fields were read/written swapped, producing a garbage flags word that could trigger optional fields that weren't actually present and eventually overrun the buffer. Codegen now tracks each flag marker's real position in the schema and emits it there.
- Related fix: `exportedChatlistInvite` and `stories.allStoriesNotModified` declare `flags:#` with no field gated on it; codegen treated "unused" as "not on the wire" and silently dropped 4 bytes, misaligning everything after. Flag groups are now determined from declared markers, not field usage.
- `ferogram/raw/tl.py`'s runtime fallback interpreter (`_read_value`/`serialize_object`) had the same "flags always first" assumption; fixed to match wire order.
- Regenerated all 1642 types + 795 functions from `api.tl`; `tests/test_tl_roundtrip.py` (4874 combinations) passes.
- Peer cache now tracks communities separately from channels instead of collapsing them together; `chatEmpty` is no longer cached as a basic chat, and a non-zero access hash can no longer be overwritten by a zero one.
- `get_dialogs`/`get_pinned_dialogs` now handle `dialogCommunity` via `community_id` instead of assuming a `peer` field. Added `Chat.is_community` and `Dialog.community_id`/`is_community`.
- `join_chat`/`join_invite_link` now handle `messages.ChatInviteJoinResult` instead of assuming a bare `Updates` response. `Ok` resolves and caches the joined peer; `WebView` returns `None` (interactive bot flow not yet supported).
- `serialize_object` now dispatches to generated `to_bytes()` before falling back to generic serialization: ~1.7x faster, byte-identical output verified across all 2,437 constructors.
- `send_message`, `edit_message`, `forward_messages` now respect `no_webpage`, `silent`, `schedule_date`, `send_as`, and related params instead of hardcoding them.
- `promote_participant(rights=...)` now replaces requested rights instead of merging into a fixed base set, so limited admin permissions actually work.
- Removed hardcoded values from `send_invoice(test=...)`, `add_contact(add_phone_privacy_exception=...)`, `get_blocked_users(my_stories_from=...)`.

---

## 0.5.2 (2026-07-17)

- Added `Client.get_chat_photos(peer, limit)`: photo/avatar history for groups and channels (`get_profile_photos` only ever worked for users). Current photo comes from the chat's full info, so it survives message deletion; older photos come from `messageActionChatEditPhoto` search history.
- Added fast re-auth support: `sign_out()` captures a `future_auth_token` when Telegram returns one and persists it via a new `DcConnection.get_future_auth_token`/`set_future_auth_token` pair (rides along in the existing session blob, no new session format code needed here). `request_login_code()` replays it automatically, so a returning session can skip code entry entirely (`auth.sentCodeSuccess`).
- MTProto handshake fix upstream (dc-tagged `p_q_inner_data` was being rejected by Telegram with RPC 444 outside DC2), pulled in transitively via `ferogram-mtsender`.
- Layer Upgrade to 228
## 0.5.1 (2026-06-29)

## What's Changed

### Message API Improvements

- `Message.reply()` now creates a proper quoted reply using `reply_to=self.id`.
- Added `Message.respond()` for sending messages to the same chat without replying.
- Added `pin()`, `forward_to()`, `get_sender()`, `get_chat()`, and `get_reply_message()` helpers.
- Added `reply_photo()` and `reply_document()` convenience methods.
- Improved `delete()` to correctly handle channels and supergroups.

### Client Enhancements

- Added `reply_to` support to `send_message()`, `send_photo()`, and `send_document()`.
- Added `Client.get_user()` and `Client.get_chat()` helpers.
- `edit_message()` now accepts `reply_markup`.
- `pin_message()` now supports a `notify` parameter.
- Improved `delete_messages_in()` for channel-aware message deletion.
- Improved sent message extraction fallback behavior with warning logging and preserved context.

### Update Improvements

- Added convenience methods to `CallbackQuery`:
  - `respond()`
  - `reply()`
  - `edit_message_text()`
  - `get_sender()`

- Added convenience methods to `InlineQuery`:
  - `answer()`
  - `get_sender()`

- Added sender/entity helpers for additional update types, including:
  - `InlineSend`
  - `UserStatus`
  - `ChatAction`
  - `JoinRequest`
  - `ParticipantUpdate`
  - `MessageReaction`
  - `ChatBoost`
  - `ShippingQuery`
  - `PreCheckoutQuery`

### Dispatch Improvements

- `_dispatch()` now binds `_client` for all update types.
- Added `_client` support to remaining update wrappers, including `RawUpdate`.
- Improved sent message extraction fallback handling.

## 0.5.0 (2026-06-28)

### Architecture

The Rust dependency has changed from the monolithic `ferogram` crate to five focused crates from the ferogram core:

- `ferogram-mtsender` - MTProto sender, message framing, and acknowledgement
- `ferogram-session` - session storage (file, sqlite, libsql, memory, string)
- `ferogram-connect` - TCP/TLS transport and DC routing
- `ferogram-tl-types` - generated TL type definitions
- `ferogram-crypto` - AES-IGE, Diffie-Hellman, and SHA helpers

These five crates form the battle-tested lower layer of ferogram. They change rarely and are stable across minor versions. All high-level logic (message parsing, update dispatch, peer resolution, serialization, deserialization) now lives in Python. This split means the compiled extension is smaller and faster to build, and Python-side behaviour can be updated without recompiling the Rust extension.

The compiled extension now uses `abi3-py39` (was `abi3-py313`), so a single wheel runs on Python 3.9 and later.

### Added

- **`TransferHandle`** - pause, resume, and cancel any upload or download in flight. Create a `TransferHandle`, pass it to `upload_with_progress` or `download_with_progress`, then call `.pause()`, `.resume()`, or `.cancel()` from any coroutine. `.progress()` returns a dict with `done`, `total`, `elapsed_ms`, `percent`, `speed_bps`, `eta_secs`, `speed_human`, and `bytes_human`.
- **`TransferCancelled` exception** - raised when a `TransferHandle` is cancelled mid-transfer.
- **`keyboards` module** - `InlineKeyboard`, `InlineButton`, `ReplyKeyboard`, `ReplyButton`, `RemoveKeyboard`, and `ForceReply` are now pure Python and importable from `ferogram` directly.
- **`types` module** - all entity types (`User`, `Message`, `Chat`, `Dialog`, `ChatMember`, `UserFull`, `Authorization`, `ForumTopic`, `BotInfo`, `InviteLinkMember`, `ReadParticipant`, `AdminLogEvent`, `StickerSetInfo`, `BroadcastStats`, `MegagroupStats`, `NotifySettings`) moved from Rust to Python dataclasses. The public API is identical.
- **`updates` module** - update wrapper types (`NewMessage`, `EditedMessage`, `MessageDeletion`, `CallbackQuery`, `InlineQuery`, `InlineSend`, `UserStatus`, `ParticipantUpdate`, `JoinRequest`, `MessageReaction`, `PollVote`, `BotStopped`, `ShippingQuery`, `PreCheckoutQuery`, `ChatBoost`, `RawUpdate`) moved from Rust to Python dataclasses.
- **`rich` module** - `send_rich_message`, `edit_rich_message`, `send_rich_message_draft`, and `get_rich_message` via a `_RichMixin`. Supports Telegram rich text blocks including headers, tables, collages, task lists, footnotes, math, time stamps, and custom emoji via Markdown or HTML input.
- **Automatic TL codegen at build time** - `build.rs` now runs `ferogram/raw/codegen.py` during `maturin develop` / `pip install .`. Set `FEROGRAM_SKIP_CODEGEN=1` to skip if you only changed Rust. The codegen uses the same Python interpreter maturin selected.
- **`DcConnection` and `srp_calculate`** exposed from the Rust extension for use by the pure-Python `Client` class.
- **`LAYER` constant** exported from `ferogram.raw.generated._tl_schema` and used automatically in `invokeWithLayer` wrappers.
- **`all_updates` filter** - replaces the old `all` filter (which shadowed the built-in).
- **`filters` improvements** - all filters now unwrap `NewMessage` / `EditedMessage` wrapper objects before inspecting the inner `Message`. Previously filters broke when the dispatcher passed wrapper objects instead of bare messages.

### Changed

- `Message`, `User`, `Chat`, and all entity types are now Python dataclasses instead of PyO3 structs. They serialize to / from the TL dict representation in Python. No change to the public API.
- `CallbackQuery`, `InlineQuery`, and all update types are now Python dataclasses.
- `InlineKeyboard`, `ReplyKeyboard`, and related keyboard builders are now pure Python (`ferogram/keyboards.py`). Previously they were Rust structs.
- Filters rewritten to correctly unwrap update wrapper objects. `reply` filter now checks `reply_to_msg_id`; `forwarded` checks `forward_from_id`; `media` checks the `media` field directly.
- `codegen.py` doubled in size (321 to 691 lines): now generates specialized `to_bytes()` methods using `struct.pack` inline and a CID-dispatch `from_bytes()` router, producing faster serialization and deserialization than the previous schema-dict approach.
- `ferogram-py` version bump to 0.5.0. Core crates pinned to `ferogram-*` 0.6.3.

### Removed

- Direct dependency on the monolithic `ferogram` crate. The five focused crates replace it.
- `hex` crate dependency (was `0.4`, now unused).
- `all` filter removed and replaced with `all_updates` to avoid shadowing Python's built-in `all`.


## 0.4.1 (2026-06-03)

Patch release. No API changes. Identical to 0.4.0 except for dependency pins and minor internal fixes.


## 0.4.0 (2026-06-01)

### Added

- **Session backends** - `FileSession`, `MemorySession`, `StringSession`, `SqliteSession`, `LibSqlSession`, and `CustomSession` are now first-class types importable from `ferogram`. Pass any of them as the `session` argument to `Client`. Plain string names still work as before.
  - `SqliteSession("name")` stores the session in a SQLite database.
  - `MemorySession()` keeps the session in memory only; nothing is written to disk.
  - `StringSession("AQA...")` resumes from a base64 string, useful for serverless or env-var based deployments.
  - `LibSqlSession.local/remote/replica/memory(...)` targets a local file, remote Turso database, embedded replica, or in-memory libSQL database.
  - `CustomSession(obj)` wraps any Python object implementing `save(bytes)`, `load() -> bytes | None`, and `delete()`.
- **`channel_kind()` on Message** - `await msg.channel_kind()` returns `"megagroup"`, `"broadcast"`, `"gigagroup"`, or `None`. Uses the peer cache; no RPC.
- **`is_megagroup()` on Message** - `await msg.is_megagroup()` returns `True` for supergroups.
- **`is_broadcast()` on Message** - `await msg.is_broadcast()` returns `True` for broadcast channels.
- **`StopPropagation` and `ContinuePropagation`** - two exceptions exported from `ferogram` to control handler dispatch. `StopPropagation` stops all further group processing. `ContinuePropagation` skips the current handler and continues to the next match in the same group.
- **Handler groups** - all `on_*` decorators now accept `group: int = 0`. Handlers run in ascending group order; lower group numbers run first.
- **`add_handler` / `remove_handler`** - register and deregister handlers at runtime without decorators.
- **Worker pool** - a fixed pool of `workers` coroutines (default 4) now dispatches updates from a bounded `asyncio.Queue`. Replaces the old unbounded `asyncio.create_task` approach. Provides natural backpressure under load.
- **`workers` kwarg on `Client`** - controls pool size.
- **`parse_mode` kwarg on `Client`** - sets a global default parse mode applied to every `send_message` call that does not pass its own `parse_mode`.
- **`flood_sleep_threshold` kwarg on `Client`** - maps to the `AutoSleep` retry policy in the Rust core. Flood waits under this value are slept through automatically; waits above it are raised as exceptions.
- **`download_with_progress(peer, msg_id, path, on_progress)`** - download media with a progress callback `on_progress(done, total)`.
- **`upload_with_progress(path, on_progress)`** - upload a file with a progress callback. Returns a handle string accepted by `send_file`.
- **ferogram 0.6.0 as core dependency** - includes `Client.channel_kind_of(channel_id)` which backs the new `Message` methods above.

### Changed

- `no_webpage` now defaults to `True` in `send_message` and `edit_message`.
- `upload_file(data, name, mime)` replaced by `upload(Cursor(data), name)` internally; no change to the Python API.
- Session resolution order is now `session_string > session object`. `in_memory=True` is deprecated in favor of `MemorySession()`.
- Handler storage changed from `list` to `dict[group, list]`; dispatch now iterates groups in sorted order.
- `_resolve_pm` is now used internally to merge per-call and global `parse_mode`.

### Fixed

- `channel_kind`, `is_megagroup`, `is_broadcast` on `Message` no longer call `get_chat_full` (an RPC) on every invocation. They read from the peer cache via `Client.channel_kind_of`.
- Unnecessary `as i64` casts removed from `message.rs`.
- Nested `if let` blocks collapsed to `if let ... && ...`.
- `match ... { Some(m) => m, None => return None }` replaced with `as_ref()?`.


## 0.3.0 (2026-05-16)

### ferogram core upgraded to 0.5.0

The Rust dependency is now ferogram 0.5.0.

### send_poll: full PollBuilder kwargs exposed

`send_poll` now accepts all options the Rust `PollBuilder` supports: `public_voters`,
`shuffle_answers`, `hide_results_until_close`, `close_period`, `close_date`, and `solution`.
Previously only `quiz`, `correct_index`, and `multiple_choice` were wired through.

### edit_chat_default_banned_rights: send_reactions added

The `restrictions` dict now accepts `"send_reactions"` as a key. Mirrors the new
`send_reactions` field on `BannedRightsBuilder` added in ferogram 0.5.0.

### poll_results method

`poll_results(peer, msg_id)` is now the canonical way to fetch poll stats. Returns
the votes graph as a JSON string. The old `get_poll_results(peer, msg_id, poll_hash)`
is kept for backward compat but is deprecated; the `poll_hash` parameter is ignored
because ferogram 0.5.0 dropped the underlying API call it relied on.


## 0.2.3 (2026-05-14)

### Client Builder

Added 20 new kwargs to `Client(...)` so you can configure everything at construction time instead of touching internals.

Network options: `proxy` (SOCKS5 or MTProxy t.me link), `allow_ipv6`, `dc_addr`, `probe_transport`, `resilient_connect`.

Session backend: `session_string` and `in_memory` as alternatives to the default session file. Priority is `in_memory > session_string > file`.

Update handling: `catch_up`, `pfs`, `update_queue_capacity`, `update_overflow` (`"drop_oldest"` or `"drop_newest"`), `low_memory_mode`.

InitConnection identity: `device`, `system_version`, `app_version`, `lang_code`, `system_lang_code`, `lang_pack`.

Experimental: `allow_missing_channel_hash`, `auto_resolve_peers`.

### Inline Bots

`InlineArticle`, `InlinePhoto`, and `InlineDocument` now expose all their fields. Previously only the 3 required fields worked. New fields: `description`, `url`, `thumb_url`, `reply_markup` on articles; `photo_url`, `photo_width`, `photo_height`, `thumb_url`, `mime_type`, `reply_markup` on photos; `document_url`, `mime_type`, `description`, `thumb_url`, `reply_markup` on documents.

`answer_inline_query` now accepts `next_offset` for pagination and `switch_pm` to show a "go to PM" button in the results list.

`answer_inline_query_articles` is now accessible from Python. Takes a plain list of `(id, title, text)` tuples and supports `next_offset`.

`edit_inline_message` now accepts `reply_markup` so you can attach or update a keyboard when editing.

`InlineSend` now exposes `msg_id_bytes` and `msg_id_dc` so you can build an `InlineMessageId` from the send event and edit the message later.

### Participants

Ten new methods for managing group and channel members.

`get_participants(peer, limit=200)` fetches all members as a list of `ChatMember`.

`get_participants_filtered(peer, filter, limit)` fetches a filtered subset. Filter values: `"recent"`, `"admins"`, `"kicked"`, `"banned"`, `"bots"`.

`kick_participant(peer, user)` removes a user from the chat. They can rejoin if the chat is public or they have an invite link.

`ban_participant(peer, user)` permanently bans a user until an admin manually lifts it.

`ban_participant_until(peer, user, until_date)` bans until a unix timestamp, after which the ban lifts automatically.

`promote_participant(peer, user, rights)` promotes to admin with specific rights. Pass `rights=None` to grant all. Valid right strings: `"change_info"`, `"post_messages"`, `"edit_messages"`, `"delete_messages"`, `"ban_users"`, `"invite_users"`, `"pin_messages"`, `"add_admins"`, `"manage_call"`.

`demote_participant(peer, user)` strips all admin rights, leaving the user as a regular member.

`get_profile_photos(peer, limit=100)` returns a list of `(file_id, access_hash, dc_id)` tuples.

`search_peer(query)` searches the local peer cache by name or username and returns a list of peer identifier strings.

`signal_network_restored()` (sync, not async) tells the client network is back so it attempts reconnect immediately instead of waiting for the retry timer.

### Reactions and Polls

`delete_reaction(peer, msg_id, participant)` was in Rust but had no Python wrapper. Now exposed. Removes a specific user's reaction from a message, admin only.

`get_poll_results(peer, msg_id, poll_hash)` was in Rust but had no Python wrapper. Now exposed. Fetches and caches the latest poll results from Telegram.


## 0.2.2

Releases prior to 0.2.2 were not documented in this changelog.
