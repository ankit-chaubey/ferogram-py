# Copyright (c) Ankit Chaubey <ankitchaubey.dev@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# Tests for ferogram/raw/tl.py (parse_html, parse_markdown) and
# ferogram/rich.py (builder helpers, media scanners).
#
# Run without pytest: python3 tests/test_rich.py

from __future__ import annotations

import sys
import importlib
import importlib.util
import pathlib
import types as _pytypes

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load():
    pkg = _pytypes.ModuleType("ferogram")
    pkg.__path__ = [str(ROOT / "ferogram")]
    sys.modules["ferogram"] = pkg

    raw_pkg = _pytypes.ModuleType("ferogram.raw")
    raw_pkg.__path__ = [str(ROOT / "ferogram" / "raw")]
    sys.modules["ferogram.raw"] = raw_pkg

    tl = importlib.import_module("ferogram.raw.tl")

    spec = importlib.util.spec_from_file_location(
        "ferogram.rich", ROOT / "ferogram" / "rich.py"
    )
    rich = importlib.util.module_from_spec(spec)
    sys.modules["ferogram.rich"] = rich
    spec.loader.exec_module(rich)

    return tl, rich


failures: list[str] = []


def check(label: str, got, expected):
    if got != expected:
        failures.append(f"{label}\n    expected: {expected!r}\n    got:      {got!r}")


def check_in(label: str, item, collection):
    if item not in collection:
        failures.append(f"{label}\n    {item!r} not in {collection!r}")


def run():
    tl, rich = _load()

    # parse_html tests

    # bold
    p, e = tl.parse_html("<b>hello</b>")
    check("html bold plain", p, "hello")
    check("html bold entity type", e[0]["_"], "messageEntityBold")
    check("html bold offset", e[0]["offset"], 0)
    check("html bold length", e[0]["length"], 5)

    p, e = tl.parse_html("<strong>hi</strong>")
    check("html strong", e[0]["_"], "messageEntityBold")

    # italic
    p, e = tl.parse_html("<i>it</i>")
    check("html italic", e[0]["_"], "messageEntityItalic")
    p, e = tl.parse_html("<em>em</em>")
    check("html em->italic", e[0]["_"], "messageEntityItalic")

    # underline
    p, e = tl.parse_html("<u>ul</u>")
    check("html underline", e[0]["_"], "messageEntityUnderline")
    p, e = tl.parse_html("<ins>ins</ins>")
    check("html ins->underline", e[0]["_"], "messageEntityUnderline")

    # strikethrough
    for tag in ("s", "strike", "del"):
        p, e = tl.parse_html(f"<{tag}>st</{tag}>")
        check(f"html {tag}->strike", e[0]["_"], "messageEntityStrike")

    # spoiler
    p, e = tl.parse_html("<tg-spoiler>sp</tg-spoiler>")
    check("html tg-spoiler", e[0]["_"], "messageEntitySpoiler")
    p, e = tl.parse_html("<mark>mk</mark>")
    check("html mark->spoiler", e[0]["_"], "messageEntitySpoiler")

    # code
    p, e = tl.parse_html("<code>cd</code>")
    check("html code", e[0]["_"], "messageEntityCode")

    # pre
    p, e = tl.parse_html('<pre language="python">print()</pre>')
    check("html pre type", e[0]["_"], "messageEntityPre")
    check("html pre language", e[0]["language"], "python")

    # blockquote
    p, e = tl.parse_html("<blockquote>bq</blockquote>")
    check("html blockquote", e[0]["_"], "messageEntityBlockquote")

    # text url
    p, e = tl.parse_html('<a href="https://t.me/">link</a>')
    check("html texturl type", e[0]["_"], "messageEntityTextUrl")
    check("html texturl url", e[0]["url"], "https://t.me/")
    check("html texturl plain", p, "link")

    # email
    p, e = tl.parse_html('<a href="mailto:a@b.com">email</a>')
    check("html email type", e[0]["_"], "messageEntityEmail")

    # phone
    p, e = tl.parse_html('<a href="tel:+1234">phone</a>')
    check("html phone type", e[0]["_"], "messageEntityPhone")

    # user mention
    p, e = tl.parse_html('<a href="tg://user?id=999">User</a>')
    check("html mention type", e[0]["_"], "messageEntityMentionName")
    check("html mention user_id", e[0]["user_id"], 999)
    check("html mention plain", p, "User")

    # anchor link (href=#...) -- stripped, no entity
    p, e = tl.parse_html('<a href="#chapter-1">ref</a>')
    check("html anchor-link plain", p, "ref")
    check("html anchor-link no entity", len(e), 0)

    # custom emoji via tg-emoji tag
    p, e = tl.parse_html('<tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>')
    check("html tg-emoji type", e[0]["_"], "messageEntityCustomEmoji")
    check("html tg-emoji id", e[0]["document_id"], 5368324170671202286)
    check("html tg-emoji plain", p, "👍")

    # custom emoji via self-closing img
    p, e = tl.parse_html('<img src="tg://emoji?id=1234567890" alt="👋"/>')
    check("html img emoji type", e[0]["_"], "messageEntityCustomEmoji")
    check("html img emoji id", e[0]["document_id"], 1234567890)
    check("html img emoji plain", p, "👋")

    # tg-time
    p, e = tl.parse_html('<tg-time unix="1647531900" format="wDT">22:45 tomorrow</tg-time>')
    check("html tg-time type", e[0]["_"], "messageEntityFormattedDate")
    check("html tg-time date", e[0]["date"], 1647531900)
    check("html tg-time plain", p, "22:45 tomorrow")

    # tg-math -> code entity
    p, e = tl.parse_html("<tg-math>x^2</tg-math>")
    check("html tg-math type", e[0]["_"], "messageEntityCode")
    check("html tg-math plain", p, "x^2")

    # nested: bold inside italic
    p, e = tl.parse_html("<i>it <b>bold</b> it</i>")
    types = {x["_"] for x in e}
    check_in("html nested bold-in-italic has italic", "messageEntityItalic", types)
    check_in("html nested bold-in-italic has bold", "messageEntityBold", types)

    # multiple sibling entities
    p, e = tl.parse_html("<b>a</b><i>b</i><code>c</code>")
    check("html sibling count", len(e), 3)
    check("html sibling plain", p, "abc")

    # html entity unescaping
    p, e = tl.parse_html("&amp; &lt; &gt; &quot; &#39; &nbsp;")
    check("html unescape amp", "&" in p, True)
    check("html unescape lt", "<" in p, True)

    # parse_markdown tests

    # bold ** and __
    p, e = tl.parse_markdown("**bold**")
    check("md ** bold type", e[0]["_"], "messageEntityBold")
    check("md ** bold plain", p, "bold")

    p, e = tl.parse_markdown("__bold__")
    check("md __ bold type", e[0]["_"], "messageEntityBold")

    # italic * and _
    p, e = tl.parse_markdown("*italic*")
    check("md * italic type", e[0]["_"], "messageEntityItalic")
    p, e = tl.parse_markdown("_italic_")
    check("md _ italic type", e[0]["_"], "messageEntityItalic")

    # strikethrough
    p, e = tl.parse_markdown("~~strike~~")
    check("md ~~ strike", e[0]["_"], "messageEntityStrike")

    # inline code
    p, e = tl.parse_markdown("`code`")
    check("md backtick code", e[0]["_"], "messageEntityCode")

    # spoiler || and ==
    p, e = tl.parse_markdown("||spoiler||")
    check("md || spoiler", e[0]["_"], "messageEntitySpoiler")
    p, e = tl.parse_markdown("==marked==")
    check("md == spoiler", e[0]["_"], "messageEntitySpoiler")

    # code block
    p, e = tl.parse_markdown("```python\nprint('hi')\n```")
    check("md ``` pre type", e[0]["_"], "messageEntityPre")
    check("md ``` pre lang", e[0]["language"], "python")
    check("md ``` pre plain", p.strip(), "print('hi')")

    # blockquote
    p, e = tl.parse_markdown("> quoted text")
    check("md > blockquote type", e[0]["_"], "messageEntityBlockquote")
    check("md > blockquote plain", p, "quoted text")

    # headings stripped to plain text
    p, e = tl.parse_markdown("# Hello")
    check("md # heading plain", p, "Hello")
    p, e = tl.parse_markdown("## Sub")
    check("md ## heading plain", p, "Sub")

    # URL link
    p, e = tl.parse_markdown("[link](https://t.me/)")
    check("md link type", e[0]["_"], "messageEntityTextUrl")
    check("md link url", e[0]["url"], "https://t.me/")
    check("md link plain", p, "link")

    # email link
    p, e = tl.parse_markdown("[email](mailto:a@b.com)")
    check("md email type", e[0]["_"], "messageEntityEmail")

    # phone link
    p, e = tl.parse_markdown("[phone](tel:+1234)")
    check("md phone type", e[0]["_"], "messageEntityPhone")

    # user mention
    p, e = tl.parse_markdown("[User](tg://user?id=42)")
    check("md mention type", e[0]["_"], "messageEntityMentionName")
    check("md mention user_id", e[0]["user_id"], 42)

    # custom emoji
    p, e = tl.parse_markdown("![👍](tg://emoji?id=5368324170671202286)")
    check("md emoji type", e[0]["_"], "messageEntityCustomEmoji")
    check("md emoji id", e[0]["document_id"], 5368324170671202286)

    # inline math $
    p, e = tl.parse_markdown("$x^2 + y^2$")
    check("md $ math type", e[0]["_"], "messageEntityCode")
    check("md $ math plain", p, "x^2 + y^2")

    # block math $$
    p, e = tl.parse_markdown("$$E = mc^2$$")
    check("md $$ math type", e[0]["_"], "messageEntityCode")

    # footnote refs stripped
    p, e = tl.parse_markdown("text[^1] more")
    check("md footnote ref stripped", "[^1]" not in p, True)

    # footnote definitions stripped
    p, e = tl.parse_markdown("[^1]: This is a footnote.")
    check("md footnote def stripped", "[^1]:" not in p, True)

    # horizontal rule stripped
    p, e = tl.parse_markdown("---")
    check("md --- stripped", p.strip(), "")

    # multiple inline in one line
    p, e = tl.parse_markdown("**bold** and _italic_ and `code`")
    types2 = [x["_"] for x in e]
    check_in("md multi bold", "messageEntityBold", types2)
    check_in("md multi italic", "messageEntityItalic", types2)
    check_in("md multi code", "messageEntityCode", types2)

    # rich.py builder tests

    # _rich_msg_markdown
    d = rich._rich_markdown("# Hello")
    check("rich md dict type", d["_"], "inputRichMessageMarkdown")
    check("rich md content", d["markdown"], "# Hello")
    check("rich md no rtl", "rtl" not in d, True)

    d = rich._rich_markdown("text", rtl=True, noautolink=True)
    check("rich md rtl", d["rtl"], True)
    check("rich md noautolink", d["noautolink"], True)

    files = [{"_": "inputRichFileDocument", "id": "f0", "document": {}}]
    d = rich._rich_markdown("text", files=files)
    check("rich md files", d["files"], files)

    # _rich_msg_html
    d = rich._rich_html("<h1>Hi</h1>")
    check("rich html dict type", d["_"], "inputRichMessageHTML")
    check("rich html content", d["html"], "<h1>Hi</h1>")

    # _scan_media_urls_html
    html = (
        '<img src="https://telegram.org/photo.jpg"/>'
        '<video src="https://telegram.org/video.mp4"></video>'
        '<audio src="https://telegram.org/audio.mp3"></audio>'
        '<img src="tg://emoji?id=123"/>'  # should be skipped
    )
    pairs = rich._scan_media_urls_html(html)
    urls = [u for _, u in pairs]
    check("html media scan count", len(pairs), 3)
    check_in("html media photo", "https://telegram.org/photo.jpg", urls)
    check_in("html media video", "https://telegram.org/video.mp4", urls)
    check_in("html media audio", "https://telegram.org/audio.mp3", urls)

    # no duplicates
    html2 = '<img src="https://x.com/a.jpg"/><img src="https://x.com/a.jpg"/>'
    pairs2 = rich._scan_media_urls_html(html2)
    check("html media no dup", len(pairs2), 1)

    # _scan_media_urls_markdown
    md = (
        "![](https://t.me/photo.jpg)\n"
        "![cap](https://t.me/video.mp4 \"title\")\n"
        "![emoji](tg://emoji?id=999)\n"  # skipped
        "![voice](https://t.me/audio.ogg)\n"
    )
    pairs3 = rich._scan_media_urls_markdown(md)
    urls3 = [u for _, u in pairs3]
    check("md media scan count", len(pairs3), 3)
    check_in("md media photo", "https://t.me/photo.jpg", urls3)
    check_in("md media video", "https://t.me/video.mp4", urls3)
    check_in("md media ogg", "https://t.me/audio.ogg", urls3)

    # _guess_media_kind
    check("kind jpg", rich._guess_media_kind("photo.jpg"), "photo")
    check("kind png", rich._guess_media_kind("img.png"), "photo")
    check("kind mp4", rich._guess_media_kind("clip.mp4"), "video")
    check("kind gif", rich._guess_media_kind("anim.gif"), "video")
    check("kind mp3", rich._guess_media_kind("track.mp3"), "audio")
    check("kind ogg", rich._guess_media_kind("voice.ogg"), "audio")
    check("kind m4a", rich._guess_media_kind("song.m4a"), "audio")
    check("kind bin", rich._guess_media_kind("file.bin"), "document")

    # _build_rich_files returns [] when upload_media=False
    import asyncio
    loop = asyncio.new_event_loop()
    result = loop.run_until_complete(
        rich._build_rich_files(None, [("id0", "https://x.com/a.jpg")], upload_media=False)
    )
    loop.close()
    check("build_rich_files no-upload empty", result, [])

    # Results
    total = 80  # approximate assertion count above
    print(f"Ran tests, {len(failures)} failures")
    if failures:
        print(f"\n{len(failures)} FAILURES:\n")
        for f in failures:
            print(f"  - {f}\n")
        return 1
    print("All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
