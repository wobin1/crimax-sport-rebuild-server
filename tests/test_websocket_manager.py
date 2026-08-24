"""WebSocket room manager (process-local fan-out)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.websocket import ConnectionManager


@pytest.mark.asyncio
async def test_connect_disconnect_and_count():
    manager = ConnectionManager()
    ws = MagicMock()
    ws.accept = AsyncMock()

    await manager.connect(ws, "fixture-1")
    assert manager.subscriber_count("fixture-1") == 1

    manager.disconnect(ws, "fixture-1")
    assert manager.subscriber_count("fixture-1") == 0


@pytest.mark.asyncio
async def test_broadcast_sends_to_subscribers_and_drops_dead():
    manager = ConnectionManager()
    live = MagicMock()
    live.accept = AsyncMock()
    live.send_text = AsyncMock()
    dead = MagicMock()
    dead.accept = AsyncMock()
    dead.send_text = AsyncMock(side_effect=RuntimeError("gone"))

    await manager.connect(live, "fixture-2")
    await manager.connect(dead, "fixture-2")
    assert manager.subscriber_count("fixture-2") == 2

    await manager.broadcast("fixture-2", {"type": "score_update", "home": 1})

    live.send_text.assert_awaited_once()
    assert manager.subscriber_count("fixture-2") == 1


@pytest.mark.asyncio
async def test_broadcast_noop_when_empty():
    manager = ConnectionManager()
    await manager.broadcast("missing", {"type": "heartbeat"})
