# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# ferogram is a high-performance Telegram MTProto framework written in Rust.
# ferogram-py is a Python MTProto library powered by ferogram, delivering
# native Rust performance through a clean and Pythonic API for building
# Telegram clients, bots, and applications.
#
# Rust: https://github.com/ankit-chaubey/ferogram
# Python: https://github.com/ankit-chaubey/ferogram-py
#
# If you use or modify this code, keep this notice at the top of the file
# and include the LICENSE-MIT or LICENSE-APACHE file from this repository.


"""Sending media, uploads and downloads."""

from __future__ import annotations

import asyncio
import hashlib
import os
import random
from collections import deque
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any, Callable

from .._ferogram import DcConnection
from ..raw import tl as _tl
from ..raw.generated._tl_schema import _SCHEMA, _SCHEMA_BY_CID
from ..types import (
    Message,
)
from .._internal import (
    _parse_migrate,
)
from ..transfer import (
    TransferHandle,
    _resolve_quality_document,
    _AUDIO_MIME,
    _VIDEO_MIME,
    _VOICE_MIME,
    _STICKER_MIME,
)

if TYPE_CHECKING:
    pass


class MediaMethods:
    """Sending media, uploads and downloads."""

    async def send_photo(self, peer: Any, path: str, caption: str = "", *,
                         parse_mode: str | None = None,
                         reply_to: int | None = None) -> Message:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        pm = self._resolve_pm(parse_mode)
        if pm in ("markdown", "md"):
            plain_cap, cap_entities = _tl.parse_markdown(caption)
        elif pm == "html":
            plain_cap, cap_entities = _tl.parse_html(caption)
        else:
            plain_cap, cap_entities = caption, []
        input_peer = await self._resolve_peer(peer)
        file_input = await self.upload_file(path)
        req: dict = {
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": {"_": "inputMediaUploadedPhoto", "file": file_input},
            "message": plain_cap,
            "random_id": random.randint(-(2**63), 2**63 - 1),
        }
        if cap_entities:
            req["entities"] = cap_entities
        if reply_to is not None:
            req["reply_to"] = {"_": "inputReplyToMessage", "reply_to_msg_id": reply_to}
        resp = await self._rpc(req)
        return self._extract_sent_message(resp, text=plain_cap, peer_id=input_peer)

    async def send_file(self, peer: str, path: str, caption: str = "", mime_type: str | None = None, *,
                        parse_mode: str | None = None) -> dict:
        return await self.send_document(peer, path, caption, mime_type, parse_mode=parse_mode)

    async def send_document(self, peer: Any, path: str, caption: str = "", mime_type: str | None = None, *,
                             parse_mode: str | None = None,
                             reply_to: int | None = None) -> Message:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        pm = self._resolve_pm(parse_mode)
        if pm in ("markdown", "md"):
            plain_cap, cap_entities = _tl.parse_markdown(caption)
        elif pm == "html":
            plain_cap, cap_entities = _tl.parse_html(caption)
        else:
            plain_cap, cap_entities = caption, []
        input_peer = await self._resolve_peer(peer)
        file_input = await self.upload_file(path)
        if mime_type is None:
            mime_type = "application/octet-stream"
        req: dict = {
            "_": "messages.sendMedia",
            "peer": input_peer,
            "media": {
                "_": "inputMediaUploadedDocument",
                "file": file_input,
                "mime_type": mime_type,
                "attributes": [{"_": "documentAttributeFilename", "file_name": os.path.basename(path)}],
            },
            "message": plain_cap,
            "random_id": random.randint(-(2**63), 2**63 - 1),
        }
        if cap_entities:
            req["entities"] = cap_entities
        if reply_to is not None:
            req["reply_to"] = {"_": "inputReplyToMessage", "reply_to_msg_id": reply_to}
        resp = await self._rpc(req)
        return self._extract_sent_message(resp, text=plain_cap, peer_id=input_peer)

    async def send_audio(self, peer: str, path: str, caption: str = "") -> dict:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self.send_document(peer, path, caption, _AUDIO_MIME)

    async def send_video(self, peer: str, path: str, caption: str = "") -> dict:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self.send_document(peer, path, caption, _VIDEO_MIME)

    async def send_voice(self, peer: str, path: str, caption: str = "") -> dict:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self.send_document(peer, path, caption, _VOICE_MIME)

    async def send_sticker(self, peer: str, path: str) -> dict:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")
        return await self.send_document(peer, path, "", _STICKER_MIME)

    @staticmethod
    def _upload_part_size(file_size: int) -> tuple[int, int]:
        """Choose part size and total parts matching ferogram's
        upload_part_size() (media.rs). Three-tier table:

        | File size    | Part size |
        |--------------|-----------|
        | < 1 MB       | 128 KB    |
        | 1 MB - 50 MB | 256 KB    |
        | >= 50 MB     | 512 KB    |
        """
        if file_size < 1024 * 1024:
            ps = 128 * 1024
        elif file_size < 50 * 1024 * 1024:
            ps = 256 * 1024
        else:
            ps = 512 * 1024
        total_parts = (file_size + ps - 1) // ps
        if total_parts > 4000:
            ps = (file_size + 3999) // 4000
            ps = ((ps + 511) // 512) * 512
            total_parts = (file_size + ps - 1) // ps
        return ps, total_parts

    def _upload_worker_count(self, file_size: int) -> int:
        """Mirrors ferogram upload_worker_count(), capped by
        `TransferLimits.upload_tcp_connections`. With
        `bypass_tcp_allotments` set, skips the size table entirely and
        always returns the configured ceiling."""
        limits = self._transfer_limits
        if limits.bypass_tcp_allotments:
            return limits.upload_tcp_connections
        if file_size < 10 * 1024 * 1024:
            table = 1
        elif file_size < 100 * 1024 * 1024:
            table = 2
        elif file_size < 500 * 1024 * 1024:
            table = 3
        else:
            table = 4
        return max(1, min(table, limits.upload_tcp_connections))

    @staticmethod
    def _download_chunk_size(file_size: int) -> int:
        """Mirrors ferogram download_chunk_size()."""
        if file_size < 50 * 1024 * 1024:
            return 256 * 1024
        if file_size < 500 * 1024 * 1024:
            return 512 * 1024
        return 1024 * 1024

    def _download_worker_count(self, file_size: int) -> int:
        """Mirrors ferogram download_worker_count(), capped by
        `TransferLimits.download_tcp_connections`. With
        `bypass_tcp_allotments` set, skips the size table entirely and
        always returns the configured ceiling."""
        limits = self._transfer_limits
        if limits.bypass_tcp_allotments:
            return limits.download_tcp_connections
        if file_size < 10 * 1024 * 1024:
            table = 1
        elif file_size < 50 * 1024 * 1024:
            table = 2
        elif file_size < 300 * 1024 * 1024:
            table = 3
        else:
            table = 4
        return max(1, min(table, limits.download_tcp_connections))

    @staticmethod
    def _detect_mime(path: str) -> str:
        """Detect MIME from magic bytes (first 64 bytes) then fall back to extension."""
        import mimetypes
        header = b""
        try:
            with open(path, "rb") as fh:
                header = fh.read(64)
        except OSError:
            pass
        # Magic byte detection for common types
        sigs: list[tuple[bytes, str]] = [
            (b"\x89PNG",           "image/png"),
            (b"\xff\xd8\xff",      "image/jpeg"),
            (b"GIF8",              "image/gif"),
            (b"RIFF",              "video/webm"),    # may also be WAV; refined below
            (b"\x1aE\xdf\xa3",    "video/webm"),
            (b"ftyp",              "video/mp4"),     # at offset 4
            (b"\x00\x00\x00\x18ftyp", "video/mp4"),
            (b"\x00\x00\x00\x1cftyp", "video/mp4"),
            (b"OggS",              "video/ogg"),
            (b"ID3",               "audio/mpeg"),
            (b"\xff\xfb",         "audio/mpeg"),
            (b"\xff\xf3",         "audio/mpeg"),
            (b"OggS",              "audio/ogg"),
            (b"fLaC",             "audio/flac"),
            (b"WAVE",              "audio/wav"),     # RIFF....WAVE
            (b"%PDF",              "application/pdf"),
            (b"PK\x03\x04",       "application/zip"),
            (b"\x1f\x8b",         "application/gzip"),
            (b"BZh",               "application/x-bzip2"),
            (b"\xfd7zXZ",         "application/x-xz"),
            (b"7z\xbc\xaf'\x1c", "application/x-7z-compressed"),
            (b"Rar!",              "application/x-rar-compressed"),
            (b"\x89PNG",          "image/png"),
            (b"WEBP",              "image/webp"),    # RIFF....WEBP at offset 8
        ]
        for sig, mime in sigs:
            if header.startswith(sig):
                # Distinguish RIFF WAV vs WebM/WebP
                if sig == b"RIFF" and len(header) >= 12:
                    sub = header[8:12]
                    if sub == b"WEBP":
                        return "image/webp"
                    if sub == b"WAVE":
                        return "audio/wav"
                return mime
            if sig == b"ftyp" and len(header) >= 8 and header[4:8] == b"ftyp":
                return "video/mp4"
        # RIFF with unknown sub-type - check extension
        if header[8:12] == b"WAVE":
            return "audio/wav"
        # Extension fallback
        guessed, _ = mimetypes.guess_type(path)
        return guessed or "application/octet-stream"

    async def upload_file(self, path: str, *, handle: "TransferHandle | None" = None) -> dict:
        """Upload a file using independent parallel worker connections.

        Each worker opens its own authorized DcConnection (see
        `_open_worker_conn`) so concurrent parts genuinely pipeline on
        separate sockets instead of all contending for one connection's
        internal lock the way a single shared connection would. Part sizes
        and worker counts match ferogram's Rust core. Supports pause,
        resume, and cancel via a TransferHandle. Small files (<10 MB) use a
        single worker; large files use up to 4 concurrent workers.

        Note: unlike ferogram's Rust `upload_file_concurrent`, a FILE_MIGRATE
        mid-upload is not handled here -- it would require redirecting every
        worker to the new DC in lockstep, which adds real complexity for an
        edge case that's rare on `upload.saveFilePart`/`saveBigFilePart`. If
        you hit it in practice, open an issue and we can add it.

        Returns an inputFile or inputFileBig dict ready to pass to sendMedia.
        """
        BIG_THRESHOLD = 10 * 1024 * 1024

        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")

        file_name = os.path.basename(path)
        file_size = os.path.getsize(path)
        is_big    = file_size >= BIG_THRESHOLD
        part_size, total_parts = self._upload_part_size(file_size)
        n_workers  = max(1, min(self._upload_worker_count(file_size), total_parts))
        file_id    = random.randint(-(2**63), 2**63 - 1)
        md5        = hashlib.md5() if not is_big else None

        if handle is not None:
            handle._set_total(file_size)
            handle._reset_start()

        # Read all chunks up front into a slot list so workers can index directly.
        # For very large files this would be memory-heavy; in that case the Rust
        # side streams from disk. Here we chunk lazily but hold references so
        # parallel workers can re-read on retry without reopening the file.
        chunks: list[bytes] = []
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(part_size)
                if not chunk:
                    break
                chunks.append(chunk)
                if md5 is not None:
                    md5.update(chunk)

        # Open independent worker connections (sequentially -- see
        # _open_worker_conn for why), each holding a `max_tcp_connections`
        # permit for the life of this upload. Falls back to the home
        # connection alone if no extra workers could be opened at all.
        conns: list[DcConnection] = []
        stack = AsyncExitStack()
        for _ in range(n_workers):
            try:
                conns.append(await stack.enter_async_context(self._worker_slot(self._dc_id)))
            except Exception as e:
                self._log.warning(
                    "upload_file: worker connection failed, continuing with %d worker(s): %s",
                    max(len(conns), 1), e,
                )
                break
        # Each conn above is a dedicated socket opened just for this
        # transfer  - safe to consume into a PipelinedSender. The fallback
        # below reuses the client's shared session connection instead, which
        # must keep working for everything else the client does, so it can
        # never be handed off to into_pipelined_sender().
        dedicated = bool(conns)
        if not conns:
            conns = [self._require_conn()]

        next_part = 0
        next_part_lock = asyncio.Lock()

        async def upload_part_on(conn: "DcConnection", part_idx: int, chunk: bytes) -> None:
            MAX_ATTEMPTS = 5
            delay = 1.0
            for attempt in range(MAX_ATTEMPTS):
                if handle is not None:
                    await handle._poll_pause_cancel()
                try:
                    if is_big:
                        req = {
                            "_": "upload.saveBigFilePart",
                            "file_id": file_id,
                            "file_part": part_idx,
                            "file_total_parts": total_parts,
                            "bytes": chunk,
                        }
                    else:
                        req = {
                            "_": "upload.saveFilePart",
                            "file_id": file_id,
                            "file_part": part_idx,
                            "bytes": chunk,
                        }
                    req_bytes  = _tl.serialize(req, _SCHEMA)
                    resp_bytes = await conn.rpc_call(req_bytes)
                    ok = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
                    if not ok:
                        raise RuntimeError(f"upload_file: part {part_idx} rejected by server")
                    if handle is not None:
                        handle._add_bytes(len(chunk))
                    return
                except Exception as e:
                    if attempt == MAX_ATTEMPTS - 1:
                        raise
                    self._log.warning(
                        "upload_file: part %d failed (attempt %d/%d): %s — retrying in %.1fs",
                        part_idx, attempt + 1, MAX_ATTEMPTS, e, delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30.0)

        def _build_upload_req(part_idx: int, chunk: bytes) -> bytes:
            if is_big:
                req = {
                    "_": "upload.saveBigFilePart",
                    "file_id": file_id,
                    "file_part": part_idx,
                    "file_total_parts": total_parts,
                    "bytes": chunk,
                }
            else:
                req = {
                    "_": "upload.saveFilePart",
                    "file_id": file_id,
                    "file_part": part_idx,
                    "bytes": chunk,
                }
            return _tl.serialize(req, _SCHEMA)

        async def worker(conn: "DcConnection") -> None:
            nonlocal next_part
            while True:
                async with next_part_lock:
                    if next_part >= total_parts:
                        return
                    idx = next_part
                    next_part += 1
                await upload_part_on(conn, idx, chunks[idx])

        async def worker_pipelined(conn: "DcConnection") -> None:
            """X > 1 worker: keeps `upload_pipeline_depth` chunk requests in
            flight on one socket at once instead of one-at-a-time. Mirrors
            the sliding-window loop in ferogram's Rust `media.rs`."""
            nonlocal next_part
            depth = max(1, self._transfer_limits.upload_pipeline_depth)
            sender = await conn.into_pipelined_sender()
            # Sliding window of (part_idx, chunk, in-flight PipelinedRequest).
            window: deque[tuple[int, bytes, Any]] = deque()

            async def submit_next() -> bool:
                nonlocal next_part
                async with next_part_lock:
                    if next_part >= total_parts:
                        return False
                    idx = next_part
                    next_part += 1
                chunk = chunks[idx]
                request = await sender.enqueue(_build_upload_req(idx, chunk))
                window.append((idx, chunk, request))
                return True

            while True:
                if handle is not None:
                    await handle._poll_pause_cancel()
                while len(window) < depth:
                    if not await submit_next():
                        break
                if not window:
                    return
                idx, chunk, request = window.popleft()
                try:
                    resp_bytes = await request.wait()
                except Exception as e:
                    if not sender.is_alive():
                        raise
                    # Transient failure on an otherwise-live connection:
                    # retry this one part directly, out of band from the
                    # window, rather than tearing down the whole worker.
                    self._log.warning(
                        "upload_file: pipelined part %d failed, retrying directly: %s",
                        idx, e,
                    )
                    resp_bytes = await sender.call(_build_upload_req(idx, chunk))
                ok = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
                if not ok:
                    raise RuntimeError(f"upload_file: part {idx} rejected by server")
                if handle is not None:
                    handle._add_bytes(len(chunk))

        try:
            if dedicated:
                await asyncio.gather(*[worker_pipelined(c) for c in conns])
            else:
                await asyncio.gather(*[worker(c) for c in conns])
        finally:
            await stack.aclose()

        if is_big:
            return {"_": "inputFileBig", "id": file_id, "parts": total_parts, "name": file_name}
        return {
            "_": "inputFile",
            "id": file_id,
            "parts": total_parts,
            "name": file_name,
            "md5_checksum": md5.hexdigest() if md5 else "",  # type: ignore[union-attr]
        }

    async def upload_media(self, peer: str, path: str) -> int | None:
        result = await self.send_document(peer, path)
        msg = result.get("updates", [{}])[0] if isinstance(result.get("updates"), list) else {}
        return msg.get("id")

    async def download_media(self, peer: str, msg_id: int, path: str, *,
                             handle: "TransferHandle | None" = None,
                             quality: str = "original") -> str:
        """Download media from a message to a local file.

        Uses independent parallel worker connections opened directly on the
        DC the media actually lives on (its `dc_id` field, which is often
        not the home DC) and adaptive chunk sizes matching ferogram's Rust
        download implementation. Supports pause, resume, and cancel via
        handle.

        `quality` picks a variant from the media's `alt_documents` (e.g. a
        video with a quality picker in official clients): one of
        `"original"` (default), `"highest"`, or `"lowest"`. Media with no
        alternates only ever has `"original"` to pick from; every other
        value falls back to it automatically. Use `available_qualities()`
        to see what's actually on offer before choosing.
        """
        msg = await self.get_message(peer, msg_id)
        if not msg:
            raise ValueError(f"Message {msg_id} not found")
        media = msg.get("media", {})
        return await self._download_media_object(media, path, handle=handle, quality=quality)

    async def _download_media_object(self, media: dict, path: str, *,
                                      handle: "TransferHandle | None" = None,
                                      quality: str = "original") -> str:
        if not isinstance(media, dict):
            raise ValueError("No media in message")
        if quality not in ("original", "highest", "lowest"):
            raise ValueError(
                f'unknown quality {quality!r}, use: "original" | "highest" | "lowest"'
            )
        t = media.get("_", "")
        file_size = 0
        media_dc_id = self._dc_id

        if t == "messageMediaPhoto":
            photo = media.get("photo", {})
            sizes = photo.get("sizes", [])
            if not sizes:
                raise ValueError("Photo has no sizes")
            best = max(
                (s for s in sizes if isinstance(s, dict)),
                key=lambda s: s.get("size", 0),
                default=None,
            )
            if best is None:
                raise ValueError("Photo has no valid size entry")
            file_size = best.get("size", 0)
            media_dc_id = photo.get("dc_id") or self._dc_id
            location = {
                "_": "inputPhotoFileLocation",
                "id": photo.get("id", 0),
                "access_hash": photo.get("access_hash", 0),
                "file_reference": photo.get("file_reference", b""),
                "thumb_size": best.get("type", "s"),
            }

        elif t == "messageMediaDocument":
            doc = _resolve_quality_document(media, quality)
            if not isinstance(doc, dict):
                raise ValueError("media has no downloadable document for the requested quality")
            file_size = doc.get("size", 0)
            media_dc_id = doc.get("dc_id") or self._dc_id
            location = {
                "_": "inputDocumentFileLocation",
                "id": doc.get("id", 0),
                "access_hash": doc.get("access_hash", 0),
                "file_reference": doc.get("file_reference", b""),
                "thumb_size": "",
            }

        else:
            raise ValueError(f"Unsupported media type: {t!r}")

        chunk_size = self._download_chunk_size(file_size)
        n_workers  = self._download_worker_count(file_size)
        total_parts = max(1, (file_size + chunk_size - 1) // chunk_size) if file_size > 0 else None

        if handle is not None:
            handle._set_total(file_size)
            handle._reset_start()

        async def open_conn_for(dc_id: int) -> "DcConnection":
            if dc_id == self._dc_id:
                return self._require_conn()
            return await self._open_worker_conn(dc_id)

        if total_parts is not None and total_parts > 1 and n_workers > 1:
            n_workers = min(n_workers, total_parts)

            # Open independent worker connections directly on the DC the
            # media lives on (sequentially -- see _open_worker_conn), each
            # holding a `max_tcp_connections` permit for the life of this
            # download.
            conns: list[DcConnection] = []
            dl_stack = AsyncExitStack()
            for _ in range(n_workers):
                try:
                    conns.append(await dl_stack.enter_async_context(self._worker_slot(media_dc_id)))
                except Exception as e:
                    self._log.warning(
                        "download: worker connection to DC%d failed, continuing with %d worker(s): %s",
                        media_dc_id, max(len(conns), 1), e,
                    )
                    break
            # Same reasoning as upload_file: only conns opened here are
            # dedicated sockets safe to hand off to a PipelinedSender. The
            # fallback reuses the shared home connection and must stay on
            # the one-at-a-time path.
            dl_dedicated = bool(conns)
            if not conns:
                conns = [await open_conn_for(media_dc_id)]

            parts_buf: list[bytes | None] = [None] * total_parts
            next_part = 0
            next_part_lock = asyncio.Lock()

            async def fetch_part_on(conn: "DcConnection", part_idx: int) -> "DcConnection":
                offset = part_idx * chunk_size
                MAX_ATTEMPTS = 5
                delay = 1.0
                attempt = 0
                while True:
                    if handle is not None:
                        await handle._poll_pause_cancel()
                    try:
                        req_bytes = _tl.serialize({
                            "_": "upload.getFile",
                            "location": location,
                            "offset": offset,
                            "limit": chunk_size,
                        }, _SCHEMA)
                        resp_bytes = await conn.rpc_call(req_bytes)
                        result = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
                        data = result.get("bytes", b"") if isinstance(result, dict) else b""
                        parts_buf[part_idx] = data
                        if handle is not None:
                            handle._add_bytes(len(data))
                        return conn
                    except Exception as e:
                        new_dc = _parse_migrate(str(e)) if isinstance(e, RuntimeError) else None
                        if new_dc is not None:
                            self._log.info(
                                "download: FILE_MIGRATE_%d for part %d, reopening worker on new DC",
                                new_dc, part_idx,
                            )
                            conn = await self._open_worker_conn(new_dc)
                            continue  # migrate redirects don't consume a retry attempt
                        attempt += 1
                        if attempt >= MAX_ATTEMPTS:
                            raise
                        self._log.warning(
                            "download: part %d failed (attempt %d/%d): %s — retrying in %.1fs",
                            part_idx, attempt, MAX_ATTEMPTS, e, delay,
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 30.0)

            async def worker(conn: "DcConnection") -> None:
                nonlocal next_part
                cur_conn = conn
                while True:
                    async with next_part_lock:
                        if next_part >= total_parts:
                            return
                        idx = next_part
                        next_part += 1
                    cur_conn = await fetch_part_on(cur_conn, idx)

            def _build_download_req(offset: int) -> bytes:
                return _tl.serialize({
                    "_": "upload.getFile",
                    "location": location,
                    "offset": offset,
                    "limit": chunk_size,
                }, _SCHEMA)

            async def worker_pipelined(conn: "DcConnection") -> None:
                """X > 1 worker: keeps `download_pipeline_depth` chunk
                requests in flight on one socket at once. Mirrors the
                sliding-window loop in ferogram's Rust `media.rs`."""
                nonlocal next_part
                depth = max(1, self._transfer_limits.download_pipeline_depth)
                sender = await conn.into_pipelined_sender()
                # Sliding window of (part_idx, in-flight PipelinedRequest).
                window: deque[tuple[int, Any]] = deque()

                async def submit_next() -> bool:
                    nonlocal next_part
                    async with next_part_lock:
                        if next_part >= total_parts:
                            return False
                        idx = next_part
                        next_part += 1
                    request = await sender.enqueue(_build_download_req(idx * chunk_size))
                    window.append((idx, request))
                    return True

                while True:
                    if handle is not None:
                        await handle._poll_pause_cancel()
                    while len(window) < depth:
                        if not await submit_next():
                            break
                    if not window:
                        return
                    idx, request = window.popleft()
                    try:
                        resp_bytes = await request.wait()
                    except Exception as e:
                        new_dc = _parse_migrate(str(e)) if isinstance(e, RuntimeError) else None
                        if new_dc is not None:
                            # A redirect invalidates every part still in
                            # flight from the old DC/session, not just this
                            # one -- reopen fresh and resubmit the lot.
                            self._log.info(
                                "download: FILE_MIGRATE_%d mid-pipeline, reopening on new DC (part %d)",
                                new_dc, idx,
                            )
                            pending = [idx] + [w[0] for w in window]
                            window.clear()
                            new_conn = await self._open_worker_conn(new_dc)
                            sender = await new_conn.into_pipelined_sender()
                            for pidx in sorted(pending):
                                req = await sender.enqueue(_build_download_req(pidx * chunk_size))
                                window.append((pidx, req))
                            continue
                        if not sender.is_alive():
                            raise
                        self._log.warning(
                            "download: pipelined part %d failed, retrying directly: %s",
                            idx, e,
                        )
                        resp_bytes = await sender.call(_build_download_req(idx * chunk_size))
                    result = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
                    data = result.get("bytes", b"") if isinstance(result, dict) else b""
                    parts_buf[idx] = data
                    if handle is not None:
                        handle._add_bytes(len(data))

            try:
                if dl_dedicated:
                    await asyncio.gather(*[worker_pipelined(c) for c in conns])
                else:
                    await asyncio.gather(*[worker(c) for c in conns])
            finally:
                await dl_stack.aclose()

            with open(path, "wb") as fh:
                for part in parts_buf:
                    if part:
                        fh.write(part)
        else:
            # Sequential path: unknown size or single worker. Uses the
            # media's actual DC, not the home connection.
            conn = await open_conn_for(media_dc_id)
            offset = 0
            with open(path, "wb") as fh:
                while True:
                    if handle is not None:
                        await handle._poll_pause_cancel()
                    req_bytes = _tl.serialize({
                        "_": "upload.getFile",
                        "location": location,
                        "offset": offset,
                        "limit": chunk_size,
                    }, _SCHEMA)
                    try:
                        resp_bytes = await conn.rpc_call(req_bytes)
                    except RuntimeError as e:
                        new_dc = _parse_migrate(str(e))
                        if new_dc is not None:
                            conn = await self._open_worker_conn(new_dc)
                            continue
                        raise
                    result = _tl.deserialize(resp_bytes, _SCHEMA_BY_CID)
                    data = result.get("bytes", b"") if isinstance(result, dict) else b""
                    if not data:
                        break
                    fh.write(data)
                    if handle is not None:
                        handle._add_bytes(len(data))
                    offset += len(data)
                    if len(data) < chunk_size:
                        break

        return path

    async def download_with_progress(
        self,
        peer: str,
        msg_id: int,
        path: str,
        on_progress: "Callable[[int, int], None] | None" = None,
        *,
        handle: "TransferHandle | None" = None,
        quality: str = "original",
    ) -> str:
        """Download media with an optional per-second progress callback.

        on_progress(bytes_done, total_bytes) is called once per second while
        downloading. Pass a TransferHandle to pause, resume, or cancel.
        `quality` is the same `"original"|"highest"|"lowest"` picker as
        `download_media`.
        """
        if handle is None:
            handle = TransferHandle()
        stop_ticker = asyncio.Event()

        async def _ticker() -> None:
            while not stop_ticker.is_set():
                await asyncio.sleep(1)
                if on_progress is not None and not stop_ticker.is_set():
                    p = handle.progress()
                    on_progress(p["done"], p["total"])

        ticker_task = asyncio.ensure_future(_ticker())
        try:
            result = await self.download_media(peer, msg_id, path, handle=handle, quality=quality)
        finally:
            stop_ticker.set()
            ticker_task.cancel()
            try:
                await ticker_task
            except asyncio.CancelledError:
                pass
        if on_progress is not None:
            p = handle.progress()
            on_progress(p["done"], p["total"])
        return result

    async def upload_with_progress(
        self,
        path: str,
        on_progress: "Callable[[int, int], None] | None" = None,
        *,
        handle: "TransferHandle | None" = None,
    ) -> dict:
        """Upload a file with an optional per-second progress callback.

        on_progress(bytes_done, total_bytes) is called once per second while
        uploading. Pass a TransferHandle to pause, resume, or cancel.
        Returns the inputFile dict (same as upload_file).
        """
        if handle is None:
            handle = TransferHandle()
        stop_ticker = asyncio.Event()

        async def _ticker() -> None:
            while not stop_ticker.is_set():
                await asyncio.sleep(1)
                if on_progress is not None and not stop_ticker.is_set():
                    p = handle.progress()
                    on_progress(p["done"], p["total"])

        ticker_task = asyncio.ensure_future(_ticker())
        try:
            result = await self.upload_file(path, handle=handle)
        finally:
            stop_ticker.set()
            ticker_task.cancel()
            try:
                await ticker_task
            except asyncio.CancelledError:
                pass
        if on_progress is not None:
            p = handle.progress()
            on_progress(p["done"], p["total"])
        return result
