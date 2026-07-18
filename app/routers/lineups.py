from fastapi import APIRouter, Depends
import asyncpg

from app.core.dependencies import assert_club_access, require_admin
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.core.formations import FORMATIONS, slot_keys
from app.database.pool import get_conn
from app.queries import fixtures as fq
from app.queries import lineups as q
from app.schemas.lineups import FixtureLineupsOut, LineupOut, LineupUpsert

router = APIRouter(prefix="/fixtures", tags=["lineups"])

EDITABLE_STATUSES = {"scheduled"}


@router.get("/{fixture_id}/lineups", response_model=FixtureLineupsOut)
async def get_fixture_lineups(
    fixture_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
):
    fixture = await fq.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")
    return await q.get_fixture_lineups(conn, fixture_id)


@router.get("/{fixture_id}/lineups/{club_id}", response_model=LineupOut)
async def get_club_lineup(
    fixture_id: str,
    club_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
):
    fixture = await fq.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")
    if club_id not in (fixture["home_club"]["id"], fixture["away_club"]["id"]):
        raise BadRequestError("Club is not part of this fixture.")
    lineup = await q.get_lineup(conn, fixture_id, club_id)
    if not lineup:
        raise NotFoundError("Lineup")
    return lineup


@router.put("/{fixture_id}/lineups/{club_id}", response_model=LineupOut)
async def upsert_club_lineup(
    fixture_id: str,
    club_id: str,
    payload: LineupUpsert,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_admin),
):
    fixture = await fq.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")

    if club_id not in (fixture["home_club"]["id"], fixture["away_club"]["id"]):
        raise BadRequestError("Club is not part of this fixture.")

    await assert_club_access(club_id, current_user, conn)

    if fixture["status"] not in EDITABLE_STATUSES:
        raise ForbiddenError("Lineups can only be edited while the fixture is scheduled.")

    if payload.formation not in FORMATIONS:
        raise BadRequestError(
            f"Unknown formation. Allowed: {', '.join(FORMATIONS.keys())}"
        )

    expected = slot_keys(payload.formation)
    provided_slots = {p.slot_key for p in payload.players}
    if provided_slots != expected:
        missing = expected - provided_slots
        extra = provided_slots - expected
        parts = []
        if missing:
            parts.append(f"missing slots: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"unknown slots: {', '.join(sorted(extra))}")
        raise BadRequestError(
            f"Formation {payload.formation} requires exactly its 11 slots ({'; '.join(parts)})."
        )

    player_ids = [p.player_id for p in payload.players]
    if len(set(player_ids)) != 11:
        raise BadRequestError("Each of the 11 slots must have a unique player.")

    rows = await conn.fetch(
        """
        SELECT id::text FROM players
        WHERE club_id = $1 AND is_active = TRUE AND id = ANY($2::uuid[])
        """,
        club_id,
        player_ids,
    )
    found = {r["id"] for r in rows}
    if found != set(player_ids):
        raise BadRequestError("All selected players must be active members of this club.")

    return await q.upsert_lineup(
        conn,
        fixture_id,
        club_id,
        payload.formation,
        [p.model_dump() for p in payload.players],
        str(current_user["id"]),
    )


@router.delete("/{fixture_id}/lineups/{club_id}", status_code=204)
async def delete_club_lineup(
    fixture_id: str,
    club_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_admin),
):
    fixture = await fq.get_fixture_by_id(conn, fixture_id)
    if not fixture:
        raise NotFoundError("Fixture")
    await assert_club_access(club_id, current_user, conn)
    if fixture["status"] not in EDITABLE_STATUSES:
        raise ForbiddenError("Lineups can only be edited while the fixture is scheduled.")
    deleted = await q.delete_lineup(conn, fixture_id, club_id)
    if not deleted:
        raise NotFoundError("Lineup")
