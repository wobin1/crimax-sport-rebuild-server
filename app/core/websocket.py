import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


class ConnectionManager:
    """
    Manages WebSocket connections grouped by fixture_id.
    Each active match has its own 'room' of subscribers.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, fixture_id: str) -> None:
        await websocket.accept()
        key = str(fixture_id)
        self._rooms[key].append(websocket)

    def disconnect(self, websocket: WebSocket, fixture_id: str) -> None:
        key = str(fixture_id)
        room = self._rooms.get(key, [])
        if websocket in room:
            room.remove(websocket)
        if not room:
            self._rooms.pop(key, None)

    async def broadcast(self, fixture_id: str, payload: dict) -> None:
        """Send a JSON payload to every subscriber watching a fixture."""
        key = str(fixture_id)
        room = list(self._rooms.get(key, []))
        if not room:
            return

        try:
            message = json.dumps(payload, default=_json_default)
        except Exception:
            return

        dead: list[WebSocket] = []
        for ws in room:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, key)

    def subscriber_count(self, fixture_id: str) -> int:
        return len(self._rooms.get(str(fixture_id), []))


manager = ConnectionManager()
