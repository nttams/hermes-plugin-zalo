"""Connecting, polling and the HTTP client."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from zalo import adapter as zalo_adapter

from zalo_test_data import BOT_ID, USER


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("timed out")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_connect_checks_the_token_with_getme(make_adapter, fake):
    adapter, _ = await make_adapter(connect=True)
    assert adapter.is_connected
    assert adapter._bot_id == BOT_ID
    assert adapter._bot_name == "bot.hermes"
    assert adapter._bot_display_name == "Bot Hermes"
    assert fake.calls[0][0] == "getMe"


@pytest.mark.asyncio
async def test_connect_refuses_a_wrong_token(make_adapter):
    adapter, _ = await make_adapter(bot_token="1:wrong")
    adapter._client = None
    assert await adapter.connect() is False
    assert not adapter.is_connected


@pytest.mark.asyncio
async def test_connect_without_token_is_a_config_error(make_adapter):
    adapter, _ = await make_adapter(bot_token="")
    adapter._client = None
    assert await adapter.connect() is False


@pytest.mark.asyncio
async def test_poll_loop_delivers_messages(make_adapter, fake):
    adapter, inbox = await make_adapter(connect=True)
    fake.push_text("xin chào", chat_id=USER)
    fake.push_text("lần hai", chat_id=USER)
    await _wait_for(lambda: len(inbox.events) == 2)
    assert inbox.texts == ["xin chào", "lần hai"]


@pytest.mark.asyncio
async def test_poll_loop_survives_an_api_error(make_adapter, fake, monkeypatch):
    monkeypatch.setattr(zalo_adapter, "RECONNECT_DELAY", 0.01)
    adapter, inbox = await make_adapter(connect=True)
    fake.fail(429, method="getUpdates")
    fake.push_text("sau lỗi", chat_id=USER)
    await _wait_for(lambda: inbox.texts == ["sau lỗi"])


@pytest.mark.asyncio
async def test_errors_never_show_the_token():
    token = "123456:very-secret-token"

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    client = zalo_adapter._ZaloClient(token)
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    with pytest.raises(RuntimeError) as err:
        await client.get_me()
    assert token not in str(err.value)
    assert "***" in str(err.value)
    await client.close()


@pytest.mark.asyncio
async def test_send_message_is_cut_at_2000_characters(route_to_fake):
    client = zalo_adapter._ZaloClient(route_to_fake.token)
    await client.send_message(USER, "a" * 2500)
    assert len(route_to_fake.sent[0].text) == 2000
    await client.close()
