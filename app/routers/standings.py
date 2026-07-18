from fastapi import APIRouter, Depends
import asyncpg

from app.core.exceptions import NotFoundError
from app.database.pool import get_conn
from app.queries import standings as q
from app.schemas.standings import StandingsOut

router = APIRouter(prefix="/standings", tags=["standings"])


@router.get("/{tournament_id}", response_model=StandingsOut)
async def get_standings(tournament_id: str, conn: asyncpg.Connection = Depends(get_conn)):
    result = await q.get_standings(conn, tournament_id)
    if not result:
        raise NotFoundError("Tournament")
    return result
