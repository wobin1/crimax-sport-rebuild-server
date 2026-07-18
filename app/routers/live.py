from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
import asyncpg

from app.core.websocket import manager
from app.database.pool import get_conn
from app.queries import events as eq
from app.queries import fixtures as fq

router = APIRouter(tags=["live"])


@router.websocket("/ws/live/{fixture_id}")
async def live_fixture(
    websocket: WebSocket,
    fixture_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
):
    fixture = await fq.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        await websocket.close(code=4004)
        return

    await manager.connect(websocket, fixture_id)

    events, _ = await eq.get_fixture_events(conn, fixture_id, limit=500, offset=0)

    await websocket.send_json({
        "type": "init",
        "fixture": fixture,
        "events": events,
    })

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, fixture_id)
