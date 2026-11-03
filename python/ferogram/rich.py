# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0

"""ferogram.rich - Telegram rich message support.

Adds send_rich_message(), edit_rich_message(), send_rich_message_draft(),
and get_rich_message() to Client via _RichMixin.

The server parses the HTML or Markdown string into a RichBlock tree internally.
We pass the raw string inside inputRichMessageHTML / inputRichMessageMarkdown,
with an optional files= vector for pre-uploaded media.

Supported Markdown (mode="markdown"):
  **bold** __bold__  *italic* _italic_  ~~strike~~  `code`
  ||spoiler||  ==spoiler==  $math$  $$math$$
  # h1 through ###### h6
  - / * / + unordered list item
  1. ordered list item
  - [ ] task item   - [x] checked task item
  > blockquote (consecutive > lines merge into one block)
  --- divider
  | col | col |  table with :--- :---: ---: alignment
  [^id] footnote ref   [^id]: footnote definition
  [text](url)  [text](mailto:...)  [text](tel:...)  [text](tg://user?id=N)
  ![alt](tg://emoji?id=N)  ![alt](tg://time?unix=N&format=wDT)
  ![](https://url/photo.jpg "Caption")  media block
  ![](https://url/video.mp4)  ![](https://url/audio.mp3)
  ```lang\\ncode\\n```   ```math\\nformula\\n```
  <details open><summary>title</summary>content</details>
  <tg-collage>\\n![](url)\\n</tg-collage>
  <tg-slideshow>\\n![](url)\\n</tg-slideshow>
  <aside>pullquote<cite>author</cite></aside>
  <footer>footer text</footer>
  inline HTML: <u> <ins> <sub> <sup> <tg-spoiler> <tg-math> <tg-math-block>
               <tg-reference name="id"> <tg-time unix= format=>
               <tg-emoji emoji-id="N">  <img src="tg://emoji?id=N" alt="..."/>

Supported HTML (mode="html"):
  <b> <strong>  <i> <em>  <u> <ins>  <s> <strike> <del>
  <code>  <mark>  <sub>  <sup>  <tg-spoiler>
  <tg-math>formula</tg-math>  <tg-math-block>formula</tg-math-block>
  <a href="https://...">  <a href="mailto:">  <a href="tel:">
  <a href="tg://user?id=N">  <a href="#anchor">  <a name="anchor"></a>
  <tg-reference name="id">text</tg-reference>
  <tg-emoji emoji-id="N">alt</tg-emoji>
  <img src="tg://emoji?id=N" alt="..."/>
  <tg-time unix="N" format="wDT">fallback</tg-time>
  <h1>-<h6>  <p>  <pre>  <pre><code class="language-X">  <footer>
  <hr/>
  <ul><li>  <ol start="N" type="a" reversed><li value="N" type="i">
  <blockquote>text<cite>author</cite></blockquote>
  <aside>pullquote<cite>author</cite></aside>
  <img src="url"/>  <video src="url">  <audio src="url">
  <figure><img tg-spoiler/><figcaption>cap<cite>credit</cite></figcaption></figure>
  <tg-map lat="N" long="N" zoom="N"/>
  <tg-collage><img/><video/><figcaption>...</figcaption></tg-collage>
  <tg-slideshow><img/><video/><figcaption>...</figcaption></tg-slideshow>
  <table bordered striped>
    <caption>text</caption>
    <tr><th colspan="N" rowspan="N" align="left|center|right" valign="top|middle|bottom">
    <tr><td ...>
  </table>
  <details open><summary>title</summary>content</details>
  named entities: &amp; &lt; &gt; &quot; &apos; &nbsp; &hellip;
                  &mdash; &ndash; &lsquo; &rsquo; &ldquo; &rdquo;
  numeric entities: &#N;  &#xN;
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import random
import re
import tempfile
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import Client

log = logging.getLogger("ferogram.rich")


def _rich_html(html: str, *, rtl: bool = False, noautolink: bool = False,
               files: list | None = None) -> dict:
    d: dict = {"_": "inputRichMessageHTML", "html": html}
    if rtl:
        d["rtl"] = True
    if noautolink:
        d["noautolink"] = True
    if files:
        d["files"] = files
    return d


def _rich_markdown(markdown: str, *, rtl: bool = False, noautolink: bool = False,
                   files: list | None = None) -> dict:
    d: dict = {"_": "inputRichMessageMarkdown", "markdown": markdown}
    if rtl:
        d["rtl"] = True
    if noautolink:
        d["noautolink"] = True
    if files:
        d["files"] = files
    return d


_MEDIA_EXTS: set[str] = {
    ".jpg", ".jpeg", ".png", ".webp", ".avif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".gif",
    ".mp3", ".ogg", ".m4a", ".flac", ".wav", ".aac",
}

_MIME_PHOTO: set[str] = {"image/jpeg", "image/png", "image/webp", "image/avif"}
_MIME_AUDIO: set[str] = {"audio/mpeg", "audio/ogg", "audio/mp4", "audio/flac",
                         "audio/wav", "audio/aac", "audio/x-m4a"}
_MIME_VIDEO: set[str] = {"video/mp4", "video/quicktime", "video/webm",
                         "video/x-msvideo", "video/x-matroska", "image/gif"}


def _guess_media_kind(path_or_url: str) -> str:
    mime, _ = mimetypes.guess_type(path_or_url.split("?")[0])
    if mime:
        if mime in _MIME_PHOTO:
            return "photo"
        if mime in _MIME_AUDIO:
            return "audio"
        if mime in _MIME_VIDEO:
            return "video"
    ext = os.path.splitext(path_or_url.split("?")[0])[1].lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".avif"}:
        return "photo"
    if ext in {".mp3", ".ogg", ".m4a", ".flac", ".wav", ".aac"}:
        return "audio"
    if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".gif", ".gifv"}:
        return "video"
    return "document"


def _scan_media_urls_html(html: str) -> list[tuple[str, str]]:
    """Return [(id, url)] for every media src= in an HTML rich message."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(r'<(?:img|video|audio)[^>]+?src=["\']([^"\']+)["\']', html, re.I | re.S):
        url = m.group(1)
        if url.startswith("tg://") or url in seen:
            continue
        seen.add(url)
        found.append((f"media_{len(found)}", url))
    return found


def _scan_media_urls_markdown(md: str) -> list[tuple[str, str]]:
    """Return [(id, url)] for every media ![]() block in a Markdown rich message."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(r'!\[[^\]]*\]\(\s*([^\s)]+)(?:\s+"[^"]*")?\s*\)', md):
        url = m.group(1)
        if url.startswith("tg://") or url in seen:
            continue
        ext = os.path.splitext(url.split("?")[0])[1].lower()
        if ext and ext not in _MEDIA_EXTS:
            continue
        seen.add(url)
        found.append((f"media_{len(found)}", url))
    return found


async def _fetch_url(url: str) -> str:
    """Download url to a temp file and return its path."""
    suffix = os.path.splitext(url.split("?")[0])[1] or ".bin"
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, urllib.request.urlretrieve, url, path)
    except Exception as exc:
        os.unlink(path)
        raise RuntimeError(f"rich: cannot fetch {url!r}: {exc}") from exc
    return path


async def _upload_url_as_rich_file(client: "Client", id_str: str, url: str) -> dict | None:
    """Upload a media URL and return an inputRichFileDocument dict, or None on failure."""
    try:
        tmp = await _fetch_url(url)
    except RuntimeError as exc:
        log.warning("%s", exc)
        return None
    try:
        file_input = await client.upload_file(tmp)
        mime = mimetypes.guess_type(url.split("?")[0])[0] or "application/octet-stream"
        return {
            "_": "inputRichFileDocument",
            "id": id_str,
            "document": {
                "_": "inputMediaUploadedDocument",
                "file": file_input,
                "mime_type": mime,
                "attributes": [],
            },
        }
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


async def _build_rich_files(
    client: "Client",
    media_pairs: list[tuple[str, str]],
    *,
    upload_media: bool,
) -> list[dict]:
    """Build the files= vector. Returns [] when upload_media is False."""
    if not upload_media or not media_pairs:
        return []
    results = []
    for id_str, url in media_pairs:
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        rf = await _upload_url_as_rich_file(client, id_str, url)
        if rf:
            results.append(rf)
    return results


class _RichMixin:
    """Rich message methods mixed into Client."""

    async def send_rich_message(
        self,
        peer: str,
        content: str,
        *,
        mode: str = "markdown",
        rtl: bool = False,
        noautolink: bool = False,
        upload_media: bool = False,
        silent: bool = False,
        noforwards: bool = False,
        reply_to: int | None = None,
        reply_markup=None,
        schedule_date: int | None = None,
        send_as: str | None = None,
        effect: int | None = None,
    ) -> dict:
        """Send a rich message (inputRichMessageMarkdown or inputRichMessageHTML).

        mode="markdown" (default) or "html". See module docstring for full syntax.
        Set upload_media=True to pre-upload referenced HTTP/HTTPS media; leave
        False for public URLs since the server fetches them directly.
        """
        input_peer = await self._resolve_peer(peer)

        if mode in ("markdown", "md"):
            media_pairs = _scan_media_urls_markdown(content)
        else:
            media_pairs = _scan_media_urls_html(content)

        files = await _build_rich_files(self, media_pairs, upload_media=upload_media)

        if mode in ("markdown", "md"):
            rich = _rich_markdown(content, rtl=rtl, noautolink=noautolink,
                                  files=files or None)
        else:
            rich = _rich_html(content, rtl=rtl, noautolink=noautolink,
                              files=files or None)

        req: dict = {
            "_": "messages.sendMessage",
            "peer": input_peer,
            "message": "",
            "random_id": random.randint(-(2**63), 2**63 - 1),
            "rich_message": rich,
        }
        if silent:
            req["silent"] = True
        if noforwards:
            req["noforwards"] = True
        if reply_to is not None:
            req["reply_to"] = {"_": "inputReplyToMessage", "reply_to_msg_id": reply_to}
        if reply_markup is not None:
            from .client import _markup_to_dict
            req["reply_markup"] = _markup_to_dict(reply_markup)
        if schedule_date is not None:
            req["schedule_date"] = schedule_date
        if send_as is not None:
            req["send_as"] = await self._resolve_peer(send_as)
        if effect is not None:
            req["effect"] = effect

        return await self._rpc(req)

    async def edit_rich_message(
        self,
        peer: str,
        message_id: int,
        content: str,
        *,
        mode: str = "markdown",
        rtl: bool = False,
        noautolink: bool = False,
        upload_media: bool = False,
    ) -> None:
        """Edit an existing rich message (messages.editMessage flag 23)."""
        input_peer = await self._resolve_peer(peer)

        if mode in ("markdown", "md"):
            media_pairs = _scan_media_urls_markdown(content)
        else:
            media_pairs = _scan_media_urls_html(content)

        files = await _build_rich_files(self, media_pairs, upload_media=upload_media)

        if mode in ("markdown", "md"):
            rich = _rich_markdown(content, rtl=rtl, noautolink=noautolink,
                                  files=files or None)
        else:
            rich = _rich_html(content, rtl=rtl, noautolink=noautolink,
                              files=files or None)

        await self._rpc({
            "_": "messages.editMessage",
            "peer": input_peer,
            "id": message_id,
            "rich_message": rich,
        })

    async def send_rich_message_draft(
        self,
        peer: str,
        content: str,
        draft_id: int,
        *,
        mode: str = "markdown",
        rtl: bool = False,
        noautolink: bool = False,
        message_thread_id: int | None = None,
    ) -> bool:
        """Stream a partial rich message as a 30-second ephemeral draft.

        Maps to messages.saveDraft with rich_message flag (flag 9). Call
        repeatedly while generating content with the same draft_id to animate
        updates. Call send_rich_message() when complete to persist the message.
        """
        input_peer = await self._resolve_peer(peer)

        if mode in ("markdown", "md"):
            rich = _rich_markdown(content, rtl=rtl, noautolink=noautolink)
        else:
            rich = _rich_html(content, rtl=rtl, noautolink=noautolink)

        req: dict = {
            "_": "messages.saveDraft",
            "peer": input_peer,
            "message": "",
            "rich_message": rich,
        }
        if message_thread_id is not None:
            req["reply_to"] = {
                "_": "inputReplyToMessage",
                "reply_to_msg_id": message_thread_id,
            }

        await self._rpc(req)
        return True

    async def get_rich_message(self, peer: str, message_id: int) -> dict:
        """Fetch the parsed RichMessage block tree for a message (messages.getRichMessage)."""
        input_peer = await self._resolve_peer(peer)
        return await self._rpc({
            "_": "messages.getRichMessage",
            "peer": input_peer,
            "id": message_id,
        })
