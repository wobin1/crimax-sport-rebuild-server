import asyncpg
from datetime import date as _Date
from typing import Optional


def _parse_date(v) -> _Date | None:
    return _Date.fromisoformat(v) if v else None


async def get_all_tournaments(
    conn: asyncpg.Connection,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    total = await conn.fetchval("SELECT COUNT(*) FROM tournaments")
    rows = await conn.fetch(
        """
        SELECT
            t.id::text, t.name, t.season, t.description,
            t.start_date::text, t.end_date::text, t.status,
            t.logo_url, t.is_current,
            t.created_at::text, t.updated_at::text,
            COUNT(tc.club_id) AS club_count
        FROM tournaments t
        LEFT JOIN tournament_clubs tc ON tc.tournament_id = t.id
        GROUP BY t.id
        ORDER BY t.is_current DESC, t.start_date DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    return [dict(r) for r in rows], int(total or 0)


async def get_tournament_by_id(conn: asyncpg.Connection, tournament_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        SELECT
            t.id::text, t.name, t.season, t.description,
            t.start_date::text, t.end_date::text, t.status,
            t.logo_url, t.is_current,
            t.created_at::text, t.updated_at::text,
            COUNT(tc.club_id) AS club_count
        FROM tournaments t
        LEFT JOIN tournament_clubs tc ON tc.tournament_id = t.id
        WHERE t.id = $1
        GROUP BY t.id
        """,
        tournament_id,
    )
    return dict(row) if row else None


async def get_current_tournament(conn: asyncpg.Connection) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        SELECT
            t.id::text, t.name, t.season, t.description,
            t.start_date::text, t.end_date::text, t.status,
            t.logo_url, t.is_current,
            t.created_at::text, t.updated_at::text,
            COUNT(tc.club_id) AS club_count
        FROM tournaments t
        LEFT JOIN tournament_clubs tc ON tc.tournament_id = t.id
        WHERE t.is_current = TRUE
        GROUP BY t.id
        LIMIT 1
        """
    )
    return dict(row) if row else None


async def create_tournament(conn: asyncpg.Connection, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO tournaments (name, season, description, start_date, end_date, logo_url)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id::text, name, season, description,
                  start_date::text, end_date::text, status,
                  logo_url, is_current, created_at::text, updated_at::text
        """,
        data["name"],
        data["season"],
        data.get("description"),
        _parse_date(data.get("start_date")),
        _parse_date(data.get("end_date")),
        data.get("logo_url"),
    )
    result = dict(row)
    result["club_count"] = 0
    return result


async def update_tournament(conn: asyncpg.Connection, tournament_id: str, data: dict) -> Optional[dict]:
    fields = {k: v for k, v in data.items() if v is not None}
    if not fields:
        return await get_tournament_by_id(conn, tournament_id)

    # If setting is_current = True, unset all others first
    if fields.get("is_current") is True:
        await conn.execute("UPDATE tournaments SET is_current = FALSE")

    set_clauses = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(fields))
    values = [
        _parse_date(v) if k in ("start_date", "end_date") else v
        for k, v in fields.items()
    ]

    await conn.execute(
        f"UPDATE tournaments SET {set_clauses} WHERE id = $1",
        tournament_id,
        *values,
    )
    return await get_tournament_by_id(conn, tournament_id)


async def delete_tournament(conn: asyncpg.Connection, tournament_id: str) -> bool:
    result = await conn.execute("DELETE FROM tournaments WHERE id = $1", tournament_id)
    return result == "DELETE 1"


async def get_tournament_clubs(
    conn: asyncpg.Connection,
    tournament_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM tournament_clubs WHERE tournament_id = $1",
        tournament_id,
    )
    rows = await conn.fetch(
        """
        SELECT
            c.id::text, c.name, c.short_name, c.logo_url,
            c.home_ground, c.founded_year, c.description,
            c.is_active, c.created_at::text, c.updated_at::text
        FROM clubs c
        JOIN tournament_clubs tc ON tc.club_id = c.id
        WHERE tc.tournament_id = $1
        ORDER BY c.name
        LIMIT $2 OFFSET $3
        """,
        tournament_id,
        limit,
        offset,
    )
    return [dict(r) for r in rows], int(total or 0)


async def add_club_to_tournament(conn: asyncpg.Connection, tournament_id: str, club_id: str) -> None:
    await conn.execute(
        """
        INSERT INTO tournament_clubs (tournament_id, club_id)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING
        """,
        tournament_id,
        club_id,
    )


async def remove_club_from_tournament(conn: asyncpg.Connection, tournament_id: str, club_id: str) -> bool:
    result = await conn.execute(
        "DELETE FROM tournament_clubs WHERE tournament_id = $1 AND club_id = $2",
        tournament_id,
        club_id,
    )
    return result == "DELETE 1"
