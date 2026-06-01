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
- **`ferogram` 0.6.0 as core dependency** - includes `Client.channel_kind_of(channel_id)` which backs the new `Message` methods above.

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

---

# Changelog

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

---

## 0.2.2

Previous release.
