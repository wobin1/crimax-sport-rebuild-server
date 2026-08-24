import pytest
from fastapi import Response

from app.core.websocket import stamp_payload
from app import main as app_main


@pytest.mark.asyncio
async def test_health_is_liveness_only():
    result = app_main.health()
    if hasattr(result, "__await__"):
        result = await result
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_reports_unavailable_without_pool():
    response = Response()
    body = await app_main.ready(response)
    assert response.status_code == 503
    assert body["status"] == "not_ready"
    assert body["database"] == "unavailable"


def test_websocket_payloads_are_stamped():
    stamped = stamp_payload({"type": "heartbeat"})
    assert stamped["type"] == "heartbeat"
    assert "server_time" in stamped
