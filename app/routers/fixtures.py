from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from app.core.dependencies import require_admin, require_super_admin
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.pagination import PaginationParams, get_pagination
from app.core.websocket import manager
from app.database.pool import get_conn
from app.queries import fixtures as q
from app.queries import tournaments as tq
from app.schemas.fixtures import ClockUpdate, FixtureCreate, FixtureOut, FixtureUpdate
from app.schemas.pagination import Paginated, paginated

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


@router.get("", response_model=Paginated[FixtureOut])
async def list_fixtures(
    tournament_id: str | None = Query(None),
    status: str | None = Query(None),
    round: str | None = Query(None),
    date: str | None = Query(None),
    club_id: str | None = Query(None),
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    items, total = await q.get_fixtures(
        conn,
        tournament_id=tournament_id,
        status=status,
        round=round,
        date=date,
        club_id=club_id,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.get("/live", response_model=Paginated[FixtureOut])
async def list_live_fixtures(
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    items, total = await q.get_live_fixtures(
        conn, limit=pagination.limit, offset=pagination.offset
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.get("/{fixture_id}", response_model=FixtureOut)
async def get_fixture(fixture_id: str, conn: asyncpg.Connection = Depends(get_conn)):
    fixture = await q.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")
    return fixture


@router.post("", response_model=FixtureOut, status_code=201)
async def create_fixture(
    payload: FixtureCreate,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    data = payload.model_dump()
    if not data.get("tournament_id"):
        current = await tq.get_current_tournament(conn)
        if not current:
            raise HTTPException(status_code=400, detail="No active tournament found. Create or mark a tournament as current first.")
        data["tournament_id"] = current["id"]
    return await q.create_fixture(conn, data)


@router.patch("/{fixture_id}", response_model=FixtureOut)
async def update_fixture(
    fixture_id: str,
    payload: FixtureUpdate,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    fixture = await q.update_fixture(conn, fixture_id, payload.model_dump(exclude_none=True))
    if not fixture:
        raise NotFoundError("Fixture")

    # Sync live viewers when status/period change via fixtures admin.
    await manager.broadcast(
        fixture_id,
        {"type": "clock_update", "fixture": fixture},
    )
    return fixture


@router.post("/{fixture_id}/clock", response_model=FixtureOut)
async def update_clock(
    fixture_id: str,
    payload: ClockUpdate,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_admin),
):
    """Admin match-clock controls: Start 1H / HT / Start 2H / FT / nudge / stoppage."""
    try:
        fixture = await q.apply_clock_action(
            conn,
            fixture_id,
            action=payload.action.value,
            minute=payload.minute,
            stoppage_minutes=payload.stoppage_minutes,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    if not fixture:
        raise NotFoundError("Fixture")

    await manager.broadcast(
        fixture_id,
        {"type": "clock_update", "fixture": fixture},
    )
    return fixture


@router.delete("/{fixture_id}", status_code=204)
async def delete_fixture(
    fixture_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    deleted = await q.delete_fixture(conn, fixture_id)
    if not deleted:
        raise NotFoundError("Fixture")
