from fastapi import APIRouter, Depends
import asyncpg

from app.core.dependencies import require_super_admin
from app.core.exceptions import NotFoundError
from app.core.pagination import PaginationParams, get_pagination
from app.database.pool import get_conn
from app.queries import tournaments as q
from app.schemas.clubs import ClubOut
from app.schemas.pagination import Paginated, paginated
from app.schemas.tournaments import (
    AddClubToTournament,
    TournamentCreate,
    TournamentOut,
    TournamentUpdate,
)

router = APIRouter(prefix="/tournaments", tags=["tournaments"])


@router.get("", response_model=Paginated[TournamentOut])
async def list_tournaments(
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    items, total = await q.get_all_tournaments(
        conn, limit=pagination.limit, offset=pagination.offset
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.get("/current", response_model=TournamentOut)
async def get_current(conn: asyncpg.Connection = Depends(get_conn)):
    tournament = await q.get_current_tournament(conn)
    if not tournament:
        raise NotFoundError("Current tournament")
    return tournament


@router.get("/{tournament_id}", response_model=TournamentOut)
async def get_tournament(tournament_id: str, conn: asyncpg.Connection = Depends(get_conn)):
    tournament = await q.get_tournament_by_id(conn, tournament_id)
    if not tournament:
        raise NotFoundError("Tournament")
    return tournament


@router.post("", response_model=TournamentOut, status_code=201)
async def create_tournament(
    payload: TournamentCreate,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    return await q.create_tournament(conn, payload.model_dump())


@router.patch("/{tournament_id}", response_model=TournamentOut)
async def update_tournament(
    tournament_id: str,
    payload: TournamentUpdate,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    tournament = await q.update_tournament(conn, tournament_id, payload.model_dump(exclude_none=True))
    if not tournament:
        raise NotFoundError("Tournament")
    return tournament


@router.delete("/{tournament_id}", status_code=204)
async def delete_tournament(
    tournament_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    deleted = await q.delete_tournament(conn, tournament_id)
    if not deleted:
        raise NotFoundError("Tournament")


@router.get("/{tournament_id}/clubs", response_model=Paginated[ClubOut])
async def list_tournament_clubs(
    tournament_id: str,
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
):
    tournament = await q.get_tournament_by_id(conn, tournament_id)
    if not tournament:
        raise NotFoundError("Tournament")
    items, total = await q.get_tournament_clubs(
        conn, tournament_id, limit=pagination.limit, offset=pagination.offset
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.post("/{tournament_id}/clubs", status_code=201)
async def add_club(
    tournament_id: str,
    payload: AddClubToTournament,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    await q.add_club_to_tournament(conn, tournament_id, payload.club_id)
    return {"message": "Club added to tournament."}


@router.delete("/{tournament_id}/clubs/{club_id}", status_code=204)
async def remove_club(
    tournament_id: str,
    club_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    _: dict = Depends(require_super_admin),
):
    await q.remove_club_from_tournament(conn, tournament_id, club_id)
