"""Sending: text, chunks, photos, typing and cron delivery."""

from __future__ import annotations

import pytest
from gateway.config import PlatformConfig

from zalo import adapter as zalo_adapter

from zalo_test_data import USER


@pytest.fixture(autouse=True)
def no_pause_between_chunks(monkeypatch):
    real_sleep = zalo_adapter.asyncio.sleep

    async def sleep(seconds, *a, **kw):
        await real_sleep(0)

    monkeypatch.setattr(zalo_adapter.asyncio, "sleep", sleep)


@pytest.mark.asyncio
async def test_send_uses_zalo_markdown(make_adapter, fake):
    adapter, _ = await make_adapter()
    result = await adapter.send(USER, "**Tổng** hôm nay: 120k")
    assert result.success
    assert result.message_id == fake.sent[0].message_id
    assert fake.sent[0].fields == {"chat_id": USER, "text": "**Tổng** hôm nay: 120k", "parse_mode": "markdown"}


@pytest.mark.asyncio
async def test_long_replies_are_split_at_2000_characters(make_adapter, fake):
    adapter, _ = await make_adapter()
    paragraphs = [f"Đoạn {i}: " + "chữ " * 120 for i in range(12)]
    result = await adapter.send(USER, "\n\n".join(paragraphs))
    assert result.success
    assert len(fake.sent) > 1
    assert all(len(s.text) <= 2000 for s in fake.sent)
    assert "".join(s.text for s in fake.sent).count("Đoạn") == 12


@pytest.mark.asyncio
async def test_send_reports_a_zalo_error(make_adapter, fake):
    adapter, _ = await make_adapter()
    fake.fail(410, "The chat_id is invaild", method="sendMessage")
    result = await adapter.send(USER, "hi")
    assert not result.success


@pytest.mark.asyncio
async def test_send_without_a_client_fails_cleanly(make_adapter):
    adapter, _ = await make_adapter()
    await adapter._client.close()
    adapter._client = None
    assert not (await adapter.send(USER, "hi")).success


@pytest.mark.asyncio
async def test_typing_indicator(make_adapter, fake):
    adapter, _ = await make_adapter()
    await adapter.send_typing(USER)
    assert fake.sent[0].method == "sendChatAction"
    assert fake.sent[0].fields["action"] == "typing"


@pytest.mark.asyncio
async def test_send_image_with_caption(make_adapter, fake):
    adapter, _ = await make_adapter()
    result = await adapter.send_image(USER, "https://example.com/chart.png", "**Tuần này**")
    assert result.success
    assert fake.sent[0].method == "sendPhoto"
    assert fake.sent[0].fields == {"chat_id": USER, "photo": "https://example.com/chart.png",
                                   "caption": "Tuần này"}


@pytest.mark.asyncio
async def test_standalone_send_for_cron(route_to_fake):
    config = PlatformConfig(enabled=True, extra={"bot_token": route_to_fake.token})
    result = await zalo_adapter._standalone_send(config, USER, "Báo cáo sáng")
    assert result["success"] is True
    assert route_to_fake.sent[0].text == "Báo cáo sáng"


@pytest.mark.asyncio
async def test_standalone_send_needs_a_token(route_to_fake):
    result = await zalo_adapter._standalone_send(PlatformConfig(enabled=True, extra={}), USER, "x")
    assert "error" in result


@pytest.mark.asyncio
async def test_emoji_heavy_replies_fit_zalos_utf16_limit(make_adapter, fake):
    """Zalo counts 2000 in UTF-16 units (most emoji are 2); zalobot refuses longer text before sending."""
    adapter, _ = await make_adapter()
    text = "😀" * 1500
    result = await adapter.send(USER, text)
    assert result.success
    assert len(fake.sent) == 2
    assert all(zalo_adapter.utf16_len(s.text) <= 2000 for s in fake.sent)
    assert "".join(s.text for s in fake.sent) == text


@pytest.mark.asyncio
async def test_photo_captions_are_plain_text(make_adapter, fake):
    """sendPhoto documents no parse_mode, so markdown markers are removed from captions."""
    adapter, _ = await make_adapter()
    await adapter.send_image(USER, "https://example.com/a.png", "## Tuần này\n**120k** cho `cafe`")
    assert fake.sent[0].fields == {"chat_id": USER, "photo": "https://example.com/a.png",
                                   "caption": "Tuần này\n120k cho cafe"}
