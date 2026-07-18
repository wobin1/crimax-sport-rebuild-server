from fastapi import APIRouter, Depends, Query
import asyncpg

from app.core.dependencies import assert_club_access, get_current_user
from app.core.exceptions import NotFoundError
from app.core.pagination import PaginationParams, get_pagination
from app.database.pool import get_conn
from app.queries import players as q
from app.schemas.pagination import Paginated, paginated
from app.schemas.players import PlayerCreate, PlayerOut, PlayerProfile, PlayerUpdate

router = APIRouter(prefix="/players", tags=["players"])


@router.get("", response_model=Paginated[PlayerOut])
async def list_players(
    club_id: str | None = Query(None),
    active_only: bool = True,
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    items, total = await q.get_all_players(
        conn,
        club_id=club_id,
        active_only=active_only,
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.get("/{player_id}/profile", response_model=PlayerProfile)
async def get_player_profile(
    player_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
):
    profile = await q.get_player_profile(conn, player_id)
    if not profile:
        raise NotFoundError("Player")
    return profile


@router.get("/{player_id}", response_model=PlayerOut)
async def get_player(player_id: str, conn: asyncpg.Connection = Depends(get_conn)):
    player = await q.get_player_by_id(conn, player_id)
    if not player:
        raise NotFoundError("Player")
    return player


@router.post("", response_model=PlayerOut, status_code=201)
async def create_player(
    payload: PlayerCreate,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(get_current_user),
):
    await assert_club_access(payload.club_id, current_user, conn)
    return await q.create_player(conn, payload.model_dump(mode="json"))


@router.patch("/{player_id}", response_model=PlayerOut)
async def update_player(
    player_id: str,
    payload: PlayerUpdate,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(get_current_user),
):
    player = await q.get_player_by_id(conn, player_id)
    if not player:
        raise NotFoundError("Player")
    await assert_club_access(player["club_id"], current_user, conn)
    updated = await q.update_player(
        conn, player_id, payload.model_dump(mode="json", exclude_none=True)
    )
    return updated


@router.delete("/{player_id}", status_code=204)
async def delete_player(
    player_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(get_current_user),
):
    player = await q.get_player_by_id(conn, player_id)
    if not player:
        raise NotFoundError("Player")
    await assert_club_access(player["club_id"], current_user, conn)
    await q.delete_player(conn, player_id)
