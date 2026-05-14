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
