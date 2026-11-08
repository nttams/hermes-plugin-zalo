"""Connecting, polling and the HTTP client."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from zalobot import AsyncBot

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
    assert adapter.fatal_error_code == "auth_failed"
    assert adapter.fatal_error_retryable is False


@pytest.mark.asyncio
async def test_connect_without_token_is_a_config_error(make_adapter):
    adapter, _ = await make_adapter(bot_token="")
    assert await adapter.connect() is False
    assert adapter.fatal_error_code == "config_missing"


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
async def test_errors_never_show_the_token(make_adapter, monkeypatch, caplog):
    token = "123456:very-secret-token"

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    monkeypatch.setattr(zalo_adapter, "_new_bot", lambda t: AsyncBot(t, transport=httpx.MockTransport(refuse)))
    adapter, _ = await make_adapter(bot_token=token)
    await adapter._client.close()
    adapter._client = None
    assert await adapter.connect() is False
    assert adapter.fatal_error_retryable is True
    assert "cannot reach" in adapter.fatal_error_message
    assert token not in adapter.fatal_error_message
    assert token not in caplog.text


@pytest.mark.asyncio
async def test_a_revoked_token_stops_polling_and_the_gateway_hears_it(make_adapter, fake):
    adapter, _ = await make_adapter(connect=True)
    handled = []

    async def gateway_handler(failed_adapter):
        # What Hermes' gateway does with a fatal adapter: disconnect it under a
        # timeout (a separate task), then carry on (status, stop or reconnect).
        await asyncio.wait({asyncio.ensure_future(failed_adapter.disconnect())}, timeout=5)
        await asyncio.sleep(0)
        handled.append(failed_adapter.fatal_error_code)

    adapter.set_fatal_error_handler(gateway_handler)
    fake.fail(401, "Unauthorized", method="getUpdates")
    await _wait_for(lambda: handled)
    assert handled == ["auth_failed"]
    assert adapter.fatal_error_retryable is False


@pytest.mark.asyncio
async def test_one_bad_message_does_not_drop_the_next(make_adapter, fake, monkeypatch):
    adapter, inbox = await make_adapter(connect=True)
    real = adapter._handle_incoming

    async def handle(event_name, message):
        if message.get("text") == "boom":
            raise RuntimeError("boom")
        await real(event_name, message)

    monkeypatch.setattr(adapter, "_handle_incoming", handle)
    fake.push_text("boom", chat_id=USER)
    fake.push_text("still here", chat_id=USER)
    await _wait_for(lambda: inbox.texts == ["still here"])


@pytest.mark.asyncio
async def test_replies_are_cut_at_2000_characters(make_adapter, fake):
    adapter, _ = await make_adapter()
    assert (await adapter._send_text(USER, "a" * 2500)).success
    assert len(fake.sent[0].text) == 2000
