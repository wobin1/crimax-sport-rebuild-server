from fastapi import APIRouter, Depends
import asyncpg

from app.core.dependencies import assert_club_access, get_current_user, require_super_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import PaginationParams, get_pagination
from app.database.pool import get_conn
from app.queries import clubs as q
from app.schemas.clubs import ClubCreate, ClubOut, ClubUpdate
from app.schemas.pagination import Paginated, paginated
from app.schemas.players import PlayerOut

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("", response_model=Paginated[ClubOut])
async def list_clubs(
    active_only: bool = False,
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    items, total = await q.get_all_clubs(
        conn,
        active_only=active_only,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.get("/{club_id}", response_model=ClubOut)
async def get_club(club_id: str, conn: asyncpg.Connection = Depends(get_conn)):
    club = await q.get_club_by_id(conn, club_id)
    if not club:
        raise NotFoundError("Club")
    return club


@router.post("", response_model=ClubOut, status_code=201)
async def create_club(
    payload: ClubCreate,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    existing = await conn.fetchval("SELECT 1 FROM clubs WHERE name = $1", payload.name)
    if existing:
        raise ConflictError("A club with this name already exists.")
    return await q.create_club(conn, payload.model_dump())


@router.patch("/{club_id}", response_model=ClubOut)
async def update_club(
    club_id: str,
    payload: ClubUpdate,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(get_current_user),
):
    await assert_club_access(club_id, current_user, conn)
    club = await q.update_club(conn, club_id, payload.model_dump(exclude_none=True))
    if not club:
        raise NotFoundError("Club")
    return club


@router.delete("/{club_id}", status_code=204)
async def delete_club(
    club_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    deleted = await q.delete_club(conn, club_id)
    if not deleted:
        raise NotFoundError("Club")


@router.get("/{club_id}/squad", response_model=Paginated[PlayerOut])
async def get_squad(
    club_id: str,
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    club = await q.get_club_by_id(conn, club_id)
    if not club:
        raise NotFoundError("Club")
    items, total = await q.get_club_squad(
        conn, club_id, limit=pagination.limit, offset=pagination.offset
    )
    return paginated(items, total, pagination.limit, pagination.offset)
