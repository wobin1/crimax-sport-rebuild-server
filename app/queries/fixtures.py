import asyncpg
from datetime import date as _Date, time as _Time
from typing import Optional


def _parse_date(v: Optional[str]) -> Optional[_Date]:
    return _Date.fromisoformat(v) if v else None


def _parse_time(v: Optional[str]) -> Optional[_Time]:
    return _Time.fromisoformat(v) if v else None


_FIXTURE_SELECT = """
    SELECT
        f.id::text,
        f.tournament_id::text,
        t.name            AS tournament_name,
        f.home_club_id::text,
        hc.name           AS home_club_name,
        hc.short_name     AS home_club_short_name,
        hc.logo_url       AS home_club_logo_url,
        f.away_club_id::text,
        ac.name           AS away_club_name,
        ac.short_name     AS away_club_short_name,
        ac.logo_url       AS away_club_logo_url,
        f.match_date::text,
        f.match_time::text,
        f.venue,
        f.round,
        f.status,
        f.home_score,
        f.away_score,
        f.created_at::text,
        f.updated_at::text
    FROM fixtures f
    JOIN tournaments t  ON t.id  = f.tournament_id
    JOIN clubs      hc ON hc.id = f.home_club_id
    JOIN clubs      ac ON ac.id = f.away_club_id
"""


def _build_fixture_out(row: asyncpg.Record) -> dict:
    r = dict(row)
    return {
        "id": r["id"],
        "tournament_id": r["tournament_id"],
        "tournament_name": r["tournament_name"],
        "home_club": {
            "id": r["home_club_id"],
            "name": r["home_club_name"],
            "short_name": r["home_club_short_name"],
            "logo_url": r["home_club_logo_url"],
        },
        "away_club": {
            "id": r["away_club_id"],
            "name": r["away_club_name"],
            "short_name": r["away_club_short_name"],
            "logo_url": r["away_club_logo_url"],
        },
        "match_date": r["match_date"],
        "match_time": r["match_time"],
        "venue": r["venue"],
        "round": r["round"],
        "status": r["status"],
        "home_score": r["home_score"],
        "away_score": r["away_score"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }


def _fixture_filters(
    tournament_id: Optional[str] = None,
    status: Optional[str] = None,
    round: Optional[str] = None,
    date: Optional[str] = None,
    club_id: Optional[str] = None,
) -> tuple[str, list]:
    conditions: list[str] = []
    params: list = []

    if tournament_id:
        params.append(tournament_id)
        conditions.append(f"f.tournament_id = ${len(params)}")
    if status:
        params.append(status)
        conditions.append(f"f.status = ${len(params)}")
    if round:
        params.append(round)
        conditions.append(f"f.round = ${len(params)}")
    if date:
        params.append(_parse_date(date))
        conditions.append(f"f.match_date = ${len(params)}")
    if club_id:
        params.append(club_id)
        conditions.append(
            f"(f.home_club_id = ${len(params)} OR f.away_club_id = ${len(params)})"
        )

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


async def get_fixtures(
    conn: asyncpg.Connection,
    tournament_id: Optional[str] = None,
    status: Optional[str] = None,
    round: Optional[str] = None,
    date: Optional[str] = None,
    club_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    where, params = _fixture_filters(tournament_id, status, round, date, club_id)
    total = await conn.fetchval(
        f"SELECT COUNT(*) FROM fixtures f {where}",
        *params,
    )
    params.extend([limit, offset])
    rows = await conn.fetch(
        f"{_FIXTURE_SELECT} {where} ORDER BY f.match_date, f.match_time "
        f"LIMIT ${len(params) - 1} OFFSET ${len(params)}",
        *params,
    )
    return [_build_fixture_out(r) for r in rows], int(total or 0)


async def get_fixture_by_id(conn: asyncpg.Connection, fixture_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        f"{_FIXTURE_SELECT} WHERE f.id = $1",
        fixture_id,
    )
    return _build_fixture_out(row) if row else None


async def get_live_fixtures(
    conn: asyncpg.Connection,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM fixtures WHERE status = 'live'"
    )
    rows = await conn.fetch(
        f"{_FIXTURE_SELECT} WHERE f.status = 'live' "
        "ORDER BY f.match_date, f.match_time LIMIT $1 OFFSET $2",
        limit,
        offset,
    )
    return [_build_fixture_out(r) for r in rows], int(total or 0)


async def create_fixture(conn: asyncpg.Connection, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO fixtures
            (tournament_id, home_club_id, away_club_id,
             match_date, match_time, venue, round)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id::text
        """,
        data["tournament_id"],
        data["home_club_id"],
        data["away_club_id"],
        _parse_date(data.get("match_date")),
        _parse_time(data.get("match_time")),
        data.get("venue"),
        data.get("round"),
    )
    return await get_fixture_by_id(conn, row["id"])


async def update_fixture(conn: asyncpg.Connection, fixture_id: str, data: dict) -> Optional[dict]:
    fields = {k: v for k, v in data.items() if v is not None}
    if not fields:
        return await get_fixture_by_id(conn, fixture_id)

    set_clauses = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(fields))
    values = [
        _parse_date(v) if k == "match_date" else
        _parse_time(v) if k == "match_time" else v
        for k, v in fields.items()
    ]

    await conn.execute(
        f"UPDATE fixtures SET {set_clauses} WHERE id = $1",
        fixture_id,
        *values,
    )
    return await get_fixture_by_id(conn, fixture_id)


async def delete_fixture(conn: asyncpg.Connection, fixture_id: str) -> bool:
    result = await conn.execute("DELETE FROM fixtures WHERE id = $1", fixture_id)
    return result == "DELETE 1"


async def update_fixture_score(
    conn: asyncpg.Connection,
    fixture_id: str,
    home_score: int,
    away_score: int,
) -> None:
    await conn.execute(
        "UPDATE fixtures SET home_score = $2, away_score = $3 WHERE id = $1",
        fixture_id,
        home_score,
        away_score,
    )
