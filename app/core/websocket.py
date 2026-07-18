import json
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    """
    Manages WebSocket connections grouped by fixture_id.
    Each active match has its own 'room' of subscribers.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, fixture_id: str) -> None:
        await websocket.accept()
        self._rooms[fixture_id].append(websocket)

    def disconnect(self, websocket: WebSocket, fixture_id: str) -> None:
        room = self._rooms.get(fixture_id, [])
        if websocket in room:
            room.remove(websocket)
        if not room:
            self._rooms.pop(fixture_id, None)

    async def broadcast(self, fixture_id: str, payload: dict) -> None:
        """Send a JSON payload to every subscriber watching a fixture."""
        dead: list[WebSocket] = []
        for ws in self._rooms.get(fixture_id, []):
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, fixture_id)

    def subscriber_count(self, fixture_id: str) -> int:
        return len(self._rooms.get(fixture_id, []))


manager = ConnectionManager()
