"""register(): what Hermes gets when it loads the plugin."""

from __future__ import annotations

from gateway.config import Platform, PlatformConfig

from zalo import adapter as zalo_adapter


def test_registers_the_zalo_platform(registered):
    assert registered.name == "zalo"
    assert registered.label == "Zalo"
    assert registered.required_env == ["ZALO_BOT_TOKEN"]
    assert registered.max_message_length == 2000
    assert registered.cron_deliver_env_var == "ZALO_HOME_CHANNEL"
    assert registered.allowed_users_env == "ZALO_ALLOWED_USERS"
    assert registered.allow_all_env == "ZALO_ALLOW_ALL_USERS"


def test_platform_name_resolves_after_registration():
    assert Platform("zalo").value == "zalo"


def test_factory_builds_an_adapter(registered):
    adapter = registered.adapter_factory(PlatformConfig(enabled=True, extra={"bot_token": "1:x"}))
    assert isinstance(adapter, zalo_adapter.ZaloAdapter)
    assert adapter.name == "Zalo"


def test_requirements_need_a_token(monkeypatch):
    assert zalo_adapter.check_requirements() is False
    monkeypatch.setenv("ZALO_BOT_TOKEN", "1:x")
    assert zalo_adapter.check_requirements() is True


def test_config_needs_a_token(monkeypatch):
    assert zalo_adapter.validate_config(PlatformConfig(enabled=True, extra={})) is False
    assert zalo_adapter.validate_config(PlatformConfig(enabled=True, extra={"bot_token": "1:x"})) is True
    assert zalo_adapter.is_connected(PlatformConfig(enabled=True, extra={"bot_token": " "})) is False


def test_env_enablement_seeds_token_and_home_channel(monkeypatch):
    assert zalo_adapter._env_enablement() is None
    monkeypatch.setenv("ZALO_BOT_TOKEN", "1:x")
    monkeypatch.setenv("ZALO_HOME_CHANNEL", "abc")
    seed = zalo_adapter._env_enablement()
    assert seed == {"bot_token": "1:x", "home_channel": {"chat_id": "abc", "name": "abc"}}


def test_adapter_commands_are_default_deny():
    adapter = zalo_adapter.ZaloAdapter(PlatformConfig(enabled=True, extra={"bot_token": "1:x"}))
    assert adapter._is_user_authorized("anyone") is False
    # Agent-bound messages defer to Hermes' own authorization (pairing).
    assert adapter._passes_allowlist("anyone") is True
