from fastapi import APIRouter, Depends
import asyncpg

from app.core.dependencies import assert_club_access, get_current_user
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.pagination import PaginationParams, get_pagination
from app.core.websocket import manager
from app.database.pool import get_conn
from app.queries import events as q
from app.queries import fixtures as fq
from app.schemas.events import EventCreate, EventOut
from app.schemas.pagination import Paginated, paginated

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/fixture/{fixture_id}", response_model=Paginated[EventOut])
async def list_fixture_events(
    fixture_id: str,
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    fixture = await fq.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")
    items, total = await q.get_fixture_events(
        conn, fixture_id, limit=pagination.limit, offset=pagination.offset
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.post("", response_model=EventOut, status_code=201)
async def create_event(
    payload: EventCreate,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(get_current_user),
):
    fixture = await fq.get_fixture_by_id(conn, payload.fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")
    if fixture["status"] not in ("live", "scheduled"):
        raise BadRequestError("Cannot add events to a fixture that is not live or scheduled.")

    await assert_club_access(payload.club_id, current_user, conn)

    # First event kicks the match live so public /live surfaces pick it up.
    if fixture["status"] == "scheduled":
        await fq.update_fixture(conn, payload.fixture_id, {"status": "live"})

    event = await q.create_event(conn, payload.model_dump(mode="json"))
    home_score, away_score = await q.recalculate_score(conn, payload.fixture_id)
    updated = await fq.get_fixture_by_id(conn, payload.fixture_id)

    await manager.broadcast(
        str(payload.fixture_id),
        {
            "type": "event",
            "event": event,
            "score": {"home": home_score, "away": away_score},
            "status": "live",
            "fixture": updated,
        },
    )

    return event


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(get_current_user),
):
    event = await conn.fetchrow(
        "SELECT id, fixture_id::text AS fixture_id, club_id::text FROM match_events WHERE id = $1",
        event_id,
    )
    if not event:
        raise NotFoundError("Event")

    await assert_club_access(event["club_id"], current_user, conn)
    await q.delete_event(conn, event_id)

    home_score, away_score = await q.recalculate_score(conn, event["fixture_id"])
    updated = await fq.get_fixture_by_id(conn, event["fixture_id"])
    await manager.broadcast(
        str(event["fixture_id"]),
        {
            "type": "score_update",
            "score": {"home": home_score, "away": away_score},
            "fixture": updated,
        },
    )
