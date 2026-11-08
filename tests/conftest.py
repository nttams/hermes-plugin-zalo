"""Shared test setup.

The tests run against a real Hermes Agent install (``pip install hermes-agent``),
so a change in Hermes' adapter API shows up as a test failure, and against
``zalobot.testing.FakeZalo``, an in-memory Zalo Bot API that answers the way
the real one does (errors with HTTP 200 and the code in the body, 408 from an
empty ``getUpdates``, 404 for a method that does not exist). No network, no
token.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# zalo.adapter builds its data directories from HERMES_HOME at import time, so
# point it at a throwaway directory before anything imports the plugin.
os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="hermes-zalo-tests-")
for _name in (
    "ZALO_BOT_TOKEN",
    "ZALO_ALLOWED_USERS",
    "ZALO_ALLOW_ALL_USERS",
    "ZALO_DM_POLICY",
    "ZALO_HOME_CHANNEL",
    "ZALO_HOME_CHANNEL_NAME",
):
    os.environ.pop(_name, None)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from gateway.config import PlatformConfig  # noqa: E402
from gateway.platform_registry import PlatformEntry, platform_registry  # noqa: E402
from zalobot.testing import FakeZalo  # noqa: E402

from zalo import adapter as zalo_adapter  # noqa: E402

from zalo_test_data import BOT_ID  # noqa: E402


class FakePluginContext:
    """The part of Hermes' PluginContext that ``register()`` uses.

    ``register_platform`` builds the PlatformEntry exactly as Hermes does, so a
    keyword Hermes doesn't know fails here with TypeError, like it would at load.
    """

    def __init__(self) -> None:
        self.entries: list[PlatformEntry] = []

    def register_platform(self, name, label, adapter_factory, check_fn, validate_config=None,
                          required_env=None, install_hint="", **entry_kwargs):
        entry_kwargs.setdefault("plugin_name", "zalo-platform")
        entry = PlatformEntry(
            name=name,
            label=label,
            adapter_factory=adapter_factory,
            check_fn=check_fn,
            validate_config=validate_config,
            required_env=required_env or [],
            install_hint=install_hint,
            source="plugin",
            **entry_kwargs,
        )
        platform_registry.register(entry)
        self.entries.append(entry)


@pytest.fixture(scope="session", autouse=True)
def registered() -> PlatformEntry:
    """Register the plugin once, so ``Platform("zalo")`` resolves as it does in Hermes."""
    ctx = FakePluginContext()
    zalo_adapter.register(ctx)
    assert len(ctx.entries) == 1
    return ctx.entries[0]


@pytest.fixture
def fake() -> FakeZalo:
    return FakeZalo(bot_id=BOT_ID, account_name="bot.hermes", display_name="Bot Hermes")


@pytest.fixture
def route_to_fake(fake, monkeypatch):
    """Send every _ZaloClient request to the fake instead of bot-api.zaloplatforms.com."""

    async def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(transport=fake.transport, timeout=5.0)

    monkeypatch.setattr(zalo_adapter._ZaloClient, "_ensure_client", _ensure_client)
    monkeypatch.setattr(zalo_adapter, "POLLING_INTERVAL", 0.01)
    return fake


class Inbox:
    """Collects what the adapter hands to Hermes (the MessageEvents)."""

    def __init__(self) -> None:
        self.events = []

    async def handle_message(self, event) -> None:
        self.events.append(event)

    @property
    def texts(self) -> list[str]:
        return [e.text for e in self.events]


@pytest_asyncio.fixture
async def make_adapter(route_to_fake, monkeypatch, tmp_path):
    """-> async factory: a ZaloAdapter that talks to the fake, plus its Inbox.

    ``connect=False`` skips getMe and the poll loop; the bot's name and id are set
    as getMe would set them, and a client is created so replies can be sent.
    """
    made = []

    async def factory(*, connect: bool = False, **extra):
        extra.setdefault("bot_token", route_to_fake.token)
        extra.setdefault("dm_policy", "open")
        # Per-test files for group settings and chat history.
        monkeypatch.setattr(zalo_adapter._GroupSettings, "SETTINGS_FILE", str(tmp_path / "settings"))
        monkeypatch.setattr(zalo_adapter, "HISTORY_DIR", str(tmp_path / "history"))
        adapter = zalo_adapter.ZaloAdapter(PlatformConfig(enabled=True, extra=extra))
        inbox = Inbox()
        adapter.set_message_handler(inbox.handle_message)
        monkeypatch.setattr(adapter, "handle_message", inbox.handle_message)
        if connect:
            assert await adapter.connect()
        else:
            adapter._client = zalo_adapter._ZaloClient(adapter.bot_token)
            adapter._bot_id = BOT_ID
            adapter._bot_name = "bot.hermes"
            adapter._bot_display_name = "Bot Hermes"
        made.append(adapter)
        return adapter, inbox

    yield factory
    for adapter in made:
        await adapter.disconnect()

