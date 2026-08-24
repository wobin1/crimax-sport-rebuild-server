from contextlib import AbstractAsyncContextManager

import pytest
from fastapi import Response
from pydantic import ValidationError
from starlette.requests import Request

from app.core.exceptions import ConflictError
from app.routers import events as router
from app.schemas.events import EventCreate


USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "role": "platform_admin",
}
FIXTURE_ID = "00000000-0000-0000-0000-000000000010"
CLUB_ID = "00000000-0000-0000-0000-000000000020"
EVENT_ID = "00000000-0000-0000-0000-000000000030"


def fake_request() -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/events",
            "raw_path": b"/events",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("test", 80),
        }
    )


class FakeTransaction(AbstractAsyncContextManager):
    def __init__(self, conn: "FakeConnection") -> None:
        self.conn = conn

    async def __aenter__(self):
        assert not self.conn.in_transaction
        self.conn.in_transaction = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.conn.in_transaction = False
        return False


class FakeConnection:
    def __init__(self) -> None:
        self.in_transaction = False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)


def event_payload(client_event_id: str = "phone-event-1") -> EventCreate:
    return EventCreate(
        fixture_id=FIXTURE_ID,
        client_event_id=client_event_id,
        club_id=CLUB_ID,
        event_type="goal",
        minute=12,
    )


def stored_event(client_event_id: str = "phone-event-1") -> dict:
    return {
        "id": EVENT_ID,
        "fixture_id": FIXTURE_ID,
        "client_event_id": client_event_id,
        "source_event_id": None,
        "player_id": None,
        "player_name": None,
        "club_id": CLUB_ID,
        "club_name": "Test Club",
        "event_type": "goal",
        "minute": 12,
        "extra_time_minute": None,
        "description": None,
        "created_at": "2026-07-26T12:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_create_is_atomic_and_broadcasts_after_commit(monkeypatch):
    conn = FakeConnection()
    fixture = {
        "id": FIXTURE_ID,
        "status": "scheduled",
        "home_club": {"id": CLUB_ID},
        "away_club": {"id": "00000000-0000-0000-0000-000000000021"},
    }
    event = stored_event()
    calls: list[str] = []

    async def lock_fixture(_conn, _fixture_id):
        assert conn.in_transaction
        return True

    async def get_fixture(_conn, _fixture_id):
        return fixture

    async def access(_club_id, _user, _conn):
        assert conn.in_transaction

    async def update_fixture(_conn, _fixture_id, fields):
        assert conn.in_transaction
        fixture.update(fields)
        calls.append("status")
        return fixture

    async def get_existing(_conn, _fixture_id, _client_event_id):
        return None

    async def get_ruleset(_conn, _fixture_id):
        return {"preset": "grassroots"}

    async def get_events(*_args, **_kwargs):
        return [], 0

    async def snapshot(_conn, _fixture_id, _ruleset):
        assert conn.in_transaction
        fixture["ruleset_snapshot"] = _ruleset
        calls.append("snapshot")

    async def create(_conn, data):
        assert conn.in_transaction
        assert data["client_event_id"] == "phone-event-1"
        calls.append("insert")
        return event

    async def recalculate(_conn, _fixture_id):
        assert conn.in_transaction
        calls.append("score")
        return 1, 0

    async def audit(_conn, **kwargs):
        assert conn.in_transaction
        assert kwargs["action"] == "event.create"
        calls.append("audit")

    async def broadcast(_fixture_id, payload):
        assert not conn.in_transaction
        assert payload["score"] == {"home": 1, "away": 0}
        calls.append("broadcast")

    monkeypatch.setattr(router.fq, "lock_fixture", lock_fixture)
    monkeypatch.setattr(router.fq, "get_fixture_by_id", get_fixture)
    monkeypatch.setattr(router, "assert_club_access", access)
    monkeypatch.setattr(router.fq, "update_fixture", update_fixture)
    monkeypatch.setattr(router.q, "get_event_by_client_id", get_existing)
    monkeypatch.setattr(router.fq, "get_effective_ruleset", get_ruleset)
    monkeypatch.setattr(router.q, "get_fixture_events", get_events)
    monkeypatch.setattr(router.fq, "snapshot_ruleset", snapshot)
    monkeypatch.setattr(router.q, "create_event", create)
    monkeypatch.setattr(router.q, "recalculate_score", recalculate)
    monkeypatch.setattr(router.aq, "record", audit)
    monkeypatch.setattr(router.manager, "broadcast", broadcast)

    response = Response()
    result = await router.create_event(
        event_payload(),
        fake_request(),
        response,
        conn,
        USER,
        "phone-event-1",
        "request-1",
    )

    assert result == event
    assert calls == ["snapshot", "status", "insert", "score", "audit", "broadcast"]


@pytest.mark.asyncio
async def test_idempotent_replay_returns_existing_without_side_effects(monkeypatch):
    conn = FakeConnection()
    event = stored_event()

    async def lock_fixture(_conn, _fixture_id):
        return True

    async def get_fixture(_conn, _fixture_id):
        return {
            "id": FIXTURE_ID,
            "status": "completed",
            "home_club": {"id": CLUB_ID},
            "away_club": {"id": "00000000-0000-0000-0000-000000000021"},
        }

    async def access(*_args):
        return None

    async def get_existing(*_args):
        return event

    async def must_not_run(*_args, **_kwargs):
        pytest.fail("idempotent replay caused a write or broadcast")

    monkeypatch.setattr(router.fq, "lock_fixture", lock_fixture)
    monkeypatch.setattr(router.fq, "get_fixture_by_id", get_fixture)
    monkeypatch.setattr(router, "assert_club_access", access)
    monkeypatch.setattr(router.q, "get_event_by_client_id", get_existing)
    monkeypatch.setattr(router.q, "create_event", must_not_run)
    monkeypatch.setattr(router.q, "recalculate_score", must_not_run)
    monkeypatch.setattr(router.aq, "record", must_not_run)
    monkeypatch.setattr(router.manager, "broadcast", must_not_run)

    response = Response()
    result = await router.create_event(
        event_payload(),
        fake_request(),
        response,
        conn,
        USER,
        "phone-event-1",
        None,
    )

    assert result == event
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_reused_key_with_different_payload_is_rejected(monkeypatch):
    conn = FakeConnection()
    event = stored_event()
    event["minute"] = 11

    async def returns_true(*_args):
        return True

    async def get_fixture(*_args):
        return {
            "id": FIXTURE_ID,
            "status": "live",
            "home_club": {"id": CLUB_ID},
            "away_club": {"id": "00000000-0000-0000-0000-000000000021"},
        }

    async def no_op(*_args):
        return None

    async def get_existing(*_args):
        return event

    monkeypatch.setattr(router.fq, "lock_fixture", returns_true)
    monkeypatch.setattr(router.fq, "get_fixture_by_id", get_fixture)
    monkeypatch.setattr(router, "assert_club_access", no_op)
    monkeypatch.setattr(router.q, "get_event_by_client_id", get_existing)

    with pytest.raises(ConflictError):
        await router.create_event(
            event_payload(),
            fake_request(),
            Response(),
            conn,
            USER,
            "phone-event-1",
            None,
        )


def test_event_input_bounds_are_enforced():
    with pytest.raises(ValidationError):
        EventCreate(
            fixture_id=FIXTURE_ID,
            club_id=CLUB_ID,
            event_type="goal",
            minute=131,
        )

    with pytest.raises(ValidationError):
        EventCreate(
            fixture_id=FIXTURE_ID,
            client_event_id="x" * 65,
            club_id=CLUB_ID,
            event_type="goal",
            minute=1,
        )
