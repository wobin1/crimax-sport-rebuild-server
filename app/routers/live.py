import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.websocket import manager, stamp_payload
from app.database.pool import get_pool
from app.queries import events as eq
from app.queries import fixtures as fq

router = APIRouter(tags=["live"])


@router.websocket("/ws/live/{fixture_id}")
async def live_fixture(websocket: WebSocket, fixture_id: str):
    """
    Live match feed. DB work is done in a short-lived pool connection so
    viewers do not exhaust the pool and block event POSTs / broadcasts.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        fixture = await fq.get_fixture_by_id(conn, fixture_id)
        if not fixture:
            await websocket.close(code=4004)
            return
        events, _ = await eq.get_fixture_events(conn, fixture_id, limit=500, offset=0)

    await manager.connect(websocket, fixture_id)
    try:
        await websocket.send_json(
            stamp_payload(
                {
                    "type": "init",
                    "fixture": fixture,
                    "events": events,
                }
            )
        )
        # Keep the socket open; clients may send pings as keep-alives.
        # Server also emits a light heartbeat so proxies detect dead peers.
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_json(stamp_payload({"type": "heartbeat"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket, fixture_id)
    except Exception:
        manager.disconnect(websocket, fixture_id)
        raise
