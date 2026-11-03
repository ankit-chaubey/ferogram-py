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


"""Upload/download progress, limits and quality helpers."""

from __future__ import annotations

import asyncio
import time


from ._internal import _log  # noqa: F401


class TransferHandle:
    """Pause / resume / cancel control for upload and download operations.

    Mirrors ferogram's Rust TransferHandle. Create one, optionally pass it to
    upload_file / download_media / upload_with_progress / download_with_progress,
    and call pause() / resume() / cancel() from any coroutine or thread.

    Progress is read via .progress() which returns a dict with keys:
        done       - bytes transferred so far
        total      - total bytes (0 if unknown)
        elapsed_ms - milliseconds elapsed since transfer started
        percent    - completion 0.0-100.0
        speed_bps  - bytes per second
        eta_secs   - estimated seconds remaining
        speed_human - e.g. "1.4 MB/s"
        bytes_human - e.g. "12.3 MB / 50.0 MB"

    Example::

        handle = TransferHandle()
        asyncio.get_event_loop().call_later(10, handle.cancel)
        await client.upload_with_progress("big.mp4", on_progress=lambda d, t: print(f"{d}/{t}"), handle=handle)
    """

    def __init__(self) -> None:
        self._paused    = False
        self._cancelled = False
        self._done      = 0
        self._total     = 0
        self._start_ms  = int(time.time() * 1000)

    def pause(self) -> None:
        """Pause after the current chunk finishes."""
        self._paused = True

    def resume(self) -> None:
        """Resume a paused transfer."""
        self._paused = False

    def cancel(self) -> None:
        """Cancel the transfer. The worker raises TransferCancelled after the current chunk."""
        self._cancelled = True

    def is_paused(self) -> bool:
        return self._paused

    def is_cancelled(self) -> bool:
        return self._cancelled

    def progress(self) -> dict:
        now_ms   = int(time.time() * 1000)
        elapsed  = max(now_ms - self._start_ms, 1)
        done     = self._done
        total    = self._total
        elapsed_s = elapsed / 1000.0
        speed    = int(done / elapsed_s) if elapsed_s > 0 else 0
        pct      = (done / total * 100.0) if total > 0 else 0.0
        eta      = int((total - done) / speed) if speed > 0 and done < total else 0

        if speed >= 1024 * 1024:
            speed_h = f"{speed / (1024 * 1024):.1f} MB/s"
        elif speed >= 1024:
            speed_h = f"{speed / 1024:.1f} KB/s"
        else:
            speed_h = f"{speed} B/s"

        def _fmt(b: int) -> str:
            if b >= 1024 ** 3:
                return f"{b / 1024**3:.1f} GB"
            if b >= 1024 ** 2:
                return f"{b / 1024**2:.1f} MB"
            if b >= 1024:
                return f"{b / 1024:.1f} KB"
            return f"{b} B"

        return {
            "done":        done,
            "total":       total,
            "elapsed_ms":  elapsed,
            "percent":     min(pct, 100.0),
            "speed_bps":   speed,
            "eta_secs":    eta,
            "speed_human": speed_h,
            "bytes_human": f"{_fmt(done)} / {_fmt(total)}",
        }

    # Internal helpers used by Client methods
    def _set_total(self, total: int) -> None:
        self._total = total

    def _add_bytes(self, n: int) -> None:
        self._done += n

    def _reset_start(self) -> None:
        self._start_ms = int(time.time() * 1000)
        self._done = 0

    async def _poll_pause_cancel(self) -> None:
        """Yield to the event loop while paused; raise if cancelled."""
        while True:
            if self._cancelled:
                raise TransferCancelled("transfer cancelled by caller")
            if not self._paused:
                return
            await asyncio.sleep(0.1)


class TransferCancelled(Exception):
    """Raised when a TransferHandle is cancelled during upload or download."""


class TransferLimits:
    """Concurrency ceilings for file transfers. Mirrors ferogram's Rust
    `TransferLimits` (same highway/trucks model, same field names).

    - `download_tcp_connections` / `upload_tcp_connections` (**Y**): how many
      parallel worker connections a single transfer may open for itself.
      Small files always use 1 regardless of this value; larger files scale
      up towards this ceiling. Default: 4.
    - `max_tcp_connections`: total worker connections allowed across the
      whole client at once, shared by every upload and download running
      concurrently. Lower this on memory- or socket-constrained devices
      (e.g. Termux on older Android hardware). Default: 12.
    - `download_pipeline_depth` / `upload_pipeline_depth` (**X**): how many
      chunk requests a single connection keeps in flight at once instead of
      waiting for each response before sending the next. Enforced for
      dedicated worker connections (via `DcConnection.into_pipelined_sender()`);
      the shared home-connection fallback path (used when no extra worker
      connections could be opened) still goes one request at a time, since
      that socket can't be handed off to a pipelined sender.
      Default: 4.
    - `bypass_tcp_allotments`: skip the size-based lookup tables for **Y**
      entirely and always use `download_tcp_connections` /
      `upload_tcp_connections` directly, regardless of file size. This is an
      override, not just a tuning knob - turning it on means small files
      open as many connections as large ones would. Default: False.

    Example::

        Client(
            ...,
            transfer_limits=TransferLimits(
                download_tcp_connections=1,
                upload_tcp_connections=1,
                max_tcp_connections=12,
                download_pipeline_depth=16,
                upload_pipeline_depth=16,
                bypass_tcp_allotments=False,
            ),
        )
    """

    __slots__ = (
        "download_tcp_connections",
        "upload_tcp_connections",
        "max_tcp_connections",
        "download_pipeline_depth",
        "upload_pipeline_depth",
        "bypass_tcp_allotments",
    )

    def __init__(
        self,
        download_tcp_connections: int = 4,
        upload_tcp_connections: int = 4,
        max_tcp_connections: int = 12,
        download_pipeline_depth: int = 4,
        upload_pipeline_depth: int = 4,
        bypass_tcp_allotments: bool = False,
    ) -> None:
        self.download_tcp_connections = max(1, download_tcp_connections)
        self.upload_tcp_connections   = max(1, upload_tcp_connections)
        self.max_tcp_connections      = max(1, max_tcp_connections)
        self.download_pipeline_depth  = max(1, download_pipeline_depth)
        self.upload_pipeline_depth    = max(1, upload_pipeline_depth)
        self.bypass_tcp_allotments    = bypass_tcp_allotments

    def __repr__(self) -> str:
        return (
            "TransferLimits("
            f"download_tcp_connections={self.download_tcp_connections}, "
            f"upload_tcp_connections={self.upload_tcp_connections}, "
            f"max_tcp_connections={self.max_tcp_connections}, "
            f"download_pipeline_depth={self.download_pipeline_depth}, "
            f"upload_pipeline_depth={self.upload_pipeline_depth}, "
            f"bypass_tcp_allotments={self.bypass_tcp_allotments})"
        )


def _quality_candidates(media: dict) -> "list[dict]":
    """Every Document on `media` that could be a quality variant: the
    primary document (if any) followed by every entry in `alt_documents`
    (if any). Order is: primary first, then alternates in the order
    Telegram sent them - not sorted by resolution. Mirrors ferogram's Rust
    `quality_candidates`."""
    if not isinstance(media, dict) or media.get("_") != "messageMediaDocument":
        return []
    docs: "list[dict]" = []
    doc = media.get("document")
    if isinstance(doc, dict):
        docs.append(doc)
    for alt in media.get("alt_documents") or []:
        if isinstance(alt, dict):
            docs.append(alt)
    return docs


def _video_resolution(doc: dict) -> int:
    """Resolution (width * height) of a document, from its
    documentAttributeVideo if it has one. 0 for documents with no video
    attribute (audio, plain files) so they sort below anything with a
    real resolution."""
    for attr in doc.get("attributes", []) or []:
        if isinstance(attr, dict) and attr.get("_") == "documentAttributeVideo":
            return attr.get("w", 0) * attr.get("h", 0)
    return 0


def available_qualities(media: dict) -> "list[dict]":
    """List every quality variant available for `media` (a raw
    messageMediaDocument dict), sorted ascending by resolution (primary
    document included if it has a video attribute). Empty for media with
    no video attributes at all - photos, audio, and documents Telegram
    didn't transcode into multiple qualities. Mirrors ferogram's Rust
    `available_qualities`.

    Each entry is `{"width": int, "height": int, "size": int}`. Use this
    to build your own quality picker, or just pass `"highest"`/`"lowest"`
    straight to `download_media` if you don't need the full list.
    """
    out: "list[dict]" = []
    for doc in _quality_candidates(media):
        for attr in doc.get("attributes", []) or []:
            if isinstance(attr, dict) and attr.get("_") == "documentAttributeVideo":
                out.append({
                    "width": attr.get("w", 0),
                    "height": attr.get("h", 0),
                    "size": doc.get("size", 0),
                })
                break
    out.sort(key=lambda q: q["width"] * q["height"])
    return out


def _resolve_quality_document(media: dict, quality: str) -> "dict | None":
    """Resolve `quality` ("original" | "highest" | "lowest") against
    `media`, returning the chosen document dict. Falls back to the
    primary document whenever the requested quality doesn't actually
    exist for this media (no alternates present, the media isn't a
    document at all, or "original" was requested outright). Mirrors
    ferogram's Rust `resolve_quality_document`."""
    primary = None
    if isinstance(media, dict) and media.get("_") == "messageMediaDocument":
        doc = media.get("document")
        if isinstance(doc, dict):
            primary = doc

    chosen = None
    if quality == "highest":
        candidates = _quality_candidates(media)
        if candidates:
            chosen = max(candidates, key=_video_resolution)
    elif quality == "lowest":
        candidates = _quality_candidates(media)
        if candidates:
            chosen = min(candidates, key=_video_resolution)

    return chosen or primary


_AUDIO_MIME   = "audio/mpeg"


_VIDEO_MIME   = "video/mp4"


_VOICE_MIME   = "audio/ogg"


_STICKER_MIME = "image/webp"
