"""Ids used across the tests (made-up values in Zalo's id format) and an event helper."""

from __future__ import annotations

from zalobot.testing import FakeZalo

BOT_ID = "1459232241454765289"
USER = "6ede9afa66b88fe6d6a9"
OTHER_USER = "7fef0bfb77c99af7e7ba"
GROUP = "c8b3a1f0e2d4c6b8a0f2"


def update(fake: FakeZalo, kind: str = "text", **kw) -> dict:
    """One event in the shape Zalo documents (``getUpdates`` result = webhook body)."""
    event = getattr(fake, f"push_{kind}")(**kw)
    fake.updates.remove(event)
    return event
