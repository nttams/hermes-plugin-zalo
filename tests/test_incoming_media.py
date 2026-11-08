"""Photos, stickers and voice messages from Zalo users.

Field names follow the documented event bodies (photo_url, caption, sticker,
url, voice_url): https://bot.zaloplatforms.com/docs/webhook/
"""

from __future__ import annotations

import pytest
from gateway.platforms.base import MessageType
from zalo_test_data import GROUP, USER, update

from zalo import adapter as zalo_adapter


@pytest.fixture
def downloads(monkeypatch, tmp_path):
    """Replace Hermes' media cache downloads; record what was fetched."""
    fetched = []

    async def fake_cache(url, ext=".jpg", retries=2):
        fetched.append((url, ext))
        path = tmp_path / f"media{len(fetched)}{ext}"
        path.write_bytes(b"x")
        return str(path)

    monkeypatch.setattr(zalo_adapter, "cache_image_from_url", fake_cache)
    monkeypatch.setattr(zalo_adapter, "cache_audio_from_url", fake_cache)
    return fetched


async def _handle(adapter, event: dict) -> None:
    await adapter._handle_incoming(event["event_name"], event["message"])


@pytest.mark.asyncio
async def test_a_photo_reaches_hermes_as_an_image(make_adapter, fake, downloads):
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, "photo", photo_url="https://f.zalo.me/a.jpg", caption="Hoá đơn",
                                  chat_id=USER))
    [event] = inbox.events
    assert event.message_type == MessageType.PHOTO
    assert event.text == "Hoá đơn"
    assert downloads == [("https://f.zalo.me/a.jpg", ".jpg")]
    assert event.media_types == ["image/jpeg"]
    assert event.media_urls[0].endswith(".jpg")


@pytest.mark.asyncio
async def test_a_png_keeps_its_type(make_adapter, fake, downloads):
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, "photo", photo_url="https://f.zalo.me/b.PNG?x=1", chat_id=USER))
    assert downloads == [("https://f.zalo.me/b.PNG?x=1", ".png")]
    assert inbox.events[0].media_types == ["image/png"]


@pytest.mark.asyncio
async def test_a_photo_that_cannot_be_downloaded_still_reaches_hermes(make_adapter, fake, monkeypatch):
    async def broken(url, ext=".jpg", retries=2):
        raise ValueError("Blocked unsafe URL")

    monkeypatch.setattr(zalo_adapter, "cache_image_from_url", broken)
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, "photo", caption="xem ảnh", chat_id=USER))
    [event] = inbox.events
    assert event.text == "xem ảnh"
    assert event.media_urls == []


@pytest.mark.asyncio
async def test_a_photo_with_a_mention_in_a_group(make_adapter, fake, downloads):
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, "photo", caption="@Bot Hermes đây là gì?", chat_id=GROUP, user_id=USER,
                                  chat_type="GROUP"))
    [event] = inbox.events
    assert event.text == "đây là gì?"
    assert event.message_type == MessageType.PHOTO
    assert len(event.media_urls) == 1


@pytest.mark.asyncio
async def test_a_sticker_reaches_hermes_with_its_image(make_adapter, fake, downloads):
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, "sticker", sticker="bfe458bf64fa8da4d4eb",
                                  url="https://zalo-api.zadn.vn/api/emoticon/sticker/webpc?eid=46991", chat_id=USER))
    [event] = inbox.events
    assert event.message_type == MessageType.STICKER
    assert event.text == "[Sticker]"
    assert downloads == [("https://zalo-api.zadn.vn/api/emoticon/sticker/webpc?eid=46991", ".webp")]
    assert event.media_types == ["image/webp"]


@pytest.mark.asyncio
async def test_a_voice_message_reaches_hermes_for_transcription(make_adapter, fake, downloads):
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, "voice", voice_url="https://voice.zalo.me/v.aac", chat_id=USER))
    [event] = inbox.events
    assert event.message_type == MessageType.VOICE
    assert downloads == [("https://voice.zalo.me/v.aac", ".aac")]
    assert event.media_types == ["audio/aac"]


@pytest.mark.asyncio
async def test_a_voice_message_that_cannot_be_downloaded_is_not_sent_empty(make_adapter, fake, monkeypatch):
    async def broken(url, ext=".ogg", retries=2):
        raise OSError("timeout")

    monkeypatch.setattr(zalo_adapter, "cache_audio_from_url", broken)
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, "voice", chat_id=USER))
    [event] = inbox.events
    assert event.text == "[Voice message]"
    assert event.media_urls == []
