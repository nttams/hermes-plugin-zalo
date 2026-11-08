"""Slash commands, in groups and DMs, against the documented Zalo Bot API only.

The Bot API has 11 methods (https://bot.zaloplatforms.com/docs/): getMe,
getUpdates, setWebhook, deleteWebhook, getWebhookInfo, testWebhook,
sendMessage, sendPhoto, sendSticker, sendVoice and sendChatAction. Group
management methods (createGroup, kickGroupMember, getGroupInfo, createPoll,
pinGroupMessage, ...) don't exist: Zalo answers them like a made-up method
name, {"ok": false, "error_code": 404, "description": "Not Found"}.
"""

from __future__ import annotations

import pytest
from zalo_test_data import GROUP, OTHER_USER, USER, update

from zalo import adapter as zalo_adapter

DOCUMENTED = {
    "getMe", "getUpdates", "setWebhook", "deleteWebhook", "getWebhookInfo", "testWebhook",
    "sendMessage", "sendPhoto", "sendSticker", "sendVoice", "sendChatAction",
}

SAMPLE_ARGS = {
    "/noi-quy": "Không spam",
    "/warn": "@" + OTHER_USER + " spam",
    "/unwarn": "@" + OTHER_USER,
    "/report": "@" + OTHER_USER + " quảng cáo",
    "/welcome-text": "Chào bạn mới",
    "/name-trigger": "giá Bảng giá ở đây",
}


@pytest.fixture
def endpoints(monkeypatch):
    """Every Bot API method the plugin calls, documented or not."""
    called = []
    real_post = zalo_adapter._ZaloClient._post

    async def post(self, endpoint, data=None):
        called.append(endpoint)
        return await real_post(self, endpoint, data)

    monkeypatch.setattr(zalo_adapter._ZaloClient, "_post", post)
    return called


async def _say(adapter, fake, text, *, chat_type="GROUP"):
    chat = GROUP if chat_type == "GROUP" else USER
    event = update(fake, text=text, chat_id=chat, user_id=USER, chat_type=chat_type)
    await adapter._handle_incoming(event["event_name"], event["message"])


@pytest.mark.asyncio
@pytest.mark.parametrize("chat_type", ["GROUP", "PRIVATE"])
async def test_every_command_uses_only_documented_methods(make_adapter, fake, endpoints, chat_type):
    adapter, _ = await make_adapter(allowed_users=[USER])
    for command in zalo_adapter.SLASH_COMMANDS:
        await _say(adapter, fake, f"{command} {SAMPLE_ARGS.get(command, '')}".strip(), chat_type=chat_type)
    assert set(endpoints) <= DOCUMENTED, sorted(set(endpoints) - DOCUMENTED)


@pytest.mark.asyncio
async def test_an_allowed_user_can_run_admin_commands_in_a_group(make_adapter, fake):
    """Regression: the admin check asked getGroupInfo (not in the API), got ok=false and refused everyone."""
    adapter, _ = await make_adapter(allowed_users=[USER])
    await _say(adapter, fake, "/silent")
    assert adapter._group_settings.get(GROUP)["silent"] is True
    assert "Silent mode" in fake.sent[-1].text


@pytest.mark.asyncio
async def test_mute_is_local(make_adapter, fake, monkeypatch):
    adapter, inbox = await make_adapter(allowed_users=[USER])
    await _say(adapter, fake, "/mute")
    assert adapter._group_settings.get(GROUP)["muted"] is True
    await _say(adapter, fake, "@Bot Hermes are you there?")
    assert inbox.events == []
    await _say(adapter, fake, "/unmute")
    # Regression: a muted group dropped every message, /unmute included.
    assert adapter._group_settings.get(GROUP)["muted"] is False
    await _say(adapter, fake, "@Bot Hermes are you there?")
    assert inbox.texts == ["are you there?"]


@pytest.mark.asyncio
async def test_rules_show_what_noi_quy_set(make_adapter, fake):
    adapter, _ = await make_adapter(allowed_users=[USER])
    await _say(adapter, fake, "/rules")
    assert "Quy tắc nhóm" in fake.sent[-1].text
    await _say(adapter, fake, "/noi-quy 1. Không spam\n2. Không quảng cáo")
    await _say(adapter, fake, "/rules")
    assert "1. Không spam\n2. Không quảng cáo" in fake.sent[-1].text


@pytest.mark.asyncio
async def test_info_shows_the_chat_id(make_adapter, fake):
    adapter, _ = await make_adapter(allowed_users=[USER])
    await _say(adapter, fake, "/info")
    assert GROUP in fake.sent[-1].text


@pytest.mark.asyncio
async def test_menu_lists_only_working_commands(make_adapter, fake):
    adapter, _ = await make_adapter(allowed_users=[USER])
    await _say(adapter, fake, "/menu", chat_type="PRIVATE")
    menu = fake.sent[-1].text
    for gone in ("/kick", "/promote", "/demote", "/invite", "/poll", "/pin", "/unpin"):
        assert gone + " " not in menu and not menu.endswith(gone)


@pytest.mark.asyncio
async def test_allow_all_does_not_open_admin_commands(make_adapter, fake):
    """With allow_all, anyone may chat and use /menu, but only listed users run admin commands."""
    adapter, _ = await make_adapter(allow_all=True, allowed_users=[OTHER_USER])
    await _say(adapter, fake, "/name-trigger giá Đây là link lừa đảo")
    assert adapter._group_settings.get(GROUP).get("name_triggers", []) == []
    assert "không có quyền" in fake.sent[-1].text
    await _say(adapter, fake, "/menu")
    assert "/menu" in fake.sent[-1].text
