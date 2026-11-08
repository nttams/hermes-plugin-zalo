"""Incoming messages: what reaches Hermes and what the adapter answers itself."""

from __future__ import annotations

import pytest
from gateway.platforms.base import MessageType

from zalo_test_data import GROUP, OTHER_USER, USER, update


async def _handle(adapter, event: dict) -> None:
    await adapter._handle_incoming(event["event_name"], event["message"])


@pytest.mark.asyncio
async def test_a_direct_message_reaches_hermes(make_adapter, fake):
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, text="Xin chào", chat_id=USER))
    [event] = inbox.events
    assert event.text == "Xin chào"
    assert event.message_type == MessageType.TEXT
    assert event.source.chat_id == USER
    assert event.source.user_id == USER
    assert event.source.user_name == "Ted"
    assert event.source.chat_type == "PRIVATE"


@pytest.mark.asyncio
async def test_messages_from_bots_are_ignored(make_adapter, fake):
    adapter, inbox = await make_adapter()
    event = update(fake, text="hi", chat_id=USER)
    event["message"]["from"]["is_bot"] = True
    await _handle(adapter, event)
    assert inbox.events == []


@pytest.mark.asyncio
async def test_unsupported_messages_say_so(make_adapter, fake):
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, "unsupported", chat_id=USER))
    assert inbox.texts == ["[Unsupported message type]"]


@pytest.mark.asyncio
async def test_allowlist_drops_other_users(make_adapter, fake):
    adapter, inbox = await make_adapter(allowed_users=[USER])
    await _handle(adapter, update(fake, text="from a stranger", chat_id=OTHER_USER))
    await _handle(adapter, update(fake, text="from the owner", chat_id=USER))
    assert inbox.texts == ["from the owner"]


@pytest.mark.asyncio
async def test_group_messages_need_a_mention(make_adapter, fake):
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, text="just chatting", chat_id=GROUP, user_id=USER, chat_type="GROUP"))
    assert inbox.events == []


@pytest.mark.asyncio
async def test_a_mention_in_a_group_reaches_hermes_without_the_mention(make_adapter, fake):
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, text="@Bot Hermes tóm tắt giúp", chat_id=GROUP, user_id=USER,
                                  chat_type="GROUP"))
    [event] = inbox.events
    assert event.text == "tóm tắt giúp"
    assert event.source.chat_id == GROUP
    assert event.source.user_id == USER
    assert event.source.chat_type == "group"


@pytest.mark.asyncio
async def test_pairing_asks_for_the_captcha_code_first(make_adapter, fake):
    adapter, inbox = await make_adapter(dm_policy="pairing")
    await _handle(adapter, update(fake, text="hello", chat_id=USER))
    assert inbox.events == []
    code = adapter._pending_approvals[USER]["code"]
    assert code in fake.sent[-1].text

    await _handle(adapter, update(fake, text="000000" if code != "000000" else "111111", chat_id=USER))
    assert inbox.events == []
    assert code in fake.sent[-1].text  # reminded of the code

    await _handle(adapter, update(fake, text=code, chat_id=USER))
    await _handle(adapter, update(fake, text="now we talk", chat_id=USER))
    assert inbox.texts == [code, "now we talk"]


@pytest.mark.asyncio
async def test_an_expired_captcha_code_is_refused(make_adapter, fake):
    adapter, inbox = await make_adapter(dm_policy="pairing")
    await _handle(adapter, update(fake, text="hello", chat_id=USER))
    code = adapter._pending_approvals[USER]["code"]
    adapter._pending_approvals[USER]["expires_at"] = 0
    await _handle(adapter, update(fake, text=code, chat_id=USER))
    assert inbox.events == []
    assert USER not in adapter._captcha_passed


@pytest.mark.asyncio
async def test_adapter_commands_ignore_unauthorized_users(make_adapter, fake):
    adapter, inbox = await make_adapter()
    await _handle(adapter, update(fake, text="/menu", chat_id=USER))
    assert fake.sent == []
    assert inbox.events == []


@pytest.mark.asyncio
async def test_menu_answers_an_allowed_user(make_adapter, fake):
    adapter, inbox = await make_adapter(allowed_users=[USER])
    await _handle(adapter, update(fake, text="/menu", chat_id=USER))
    assert "/menu" in fake.sent[-1].text
    assert inbox.events == []
