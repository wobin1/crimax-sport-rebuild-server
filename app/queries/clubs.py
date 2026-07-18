import asyncpg
from typing import Optional


async def get_all_clubs(
    conn: asyncpg.Connection,
    active_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    where = "WHERE is_active = TRUE" if active_only else ""
    total = await conn.fetchval(f"SELECT COUNT(*) FROM clubs {where}")
    rows = await conn.fetch(
        f"""
        SELECT
            id::text, name, short_name, logo_url, home_ground,
            founded_year, description, is_active,
            created_at::text, updated_at::text
        FROM clubs
        {where}
        ORDER BY name
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    return [dict(r) for r in rows], int(total or 0)


async def get_club_by_id(conn: asyncpg.Connection, club_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        SELECT
            id::text, name, short_name, logo_url, home_ground,
            founded_year, description, is_active,
            created_at::text, updated_at::text
        FROM clubs
        WHERE id = $1
        """,
        club_id,
    )
    return dict(row) if row else None


async def create_club(conn: asyncpg.Connection, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO clubs (name, short_name, logo_url, home_ground, founded_year, description)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id::text, name, short_name, logo_url, home_ground,
                  founded_year, description, is_active,
                  created_at::text, updated_at::text
        """,
        data["name"],
        data.get("short_name"),
        data.get("logo_url"),
        data.get("home_ground"),
        data.get("founded_year"),
        data.get("description"),
    )
    return dict(row)


async def update_club(conn: asyncpg.Connection, club_id: str, data: dict) -> Optional[dict]:
    fields = {k: v for k, v in data.items() if v is not None}
    if not fields:
        return await get_club_by_id(conn, club_id)

    set_clauses = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(fields))
    values = list(fields.values())

    row = await conn.fetchrow(
        f"""
        UPDATE clubs SET {set_clauses}
        WHERE id = $1
        RETURNING id::text, name, short_name, logo_url, home_ground,
                  founded_year, description, is_active,
                  created_at::text, updated_at::text
        """,
        club_id,
        *values,
    )
    return dict(row) if row else None


async def delete_club(conn: asyncpg.Connection, club_id: str) -> bool:
    result = await conn.execute("DELETE FROM clubs WHERE id = $1", club_id)
    return result == "DELETE 1"


async def get_club_squad(
    conn: asyncpg.Connection,
    club_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM players WHERE club_id = $1 AND is_active = TRUE",
        club_id,
    )
    rows = await conn.fetch(
        """
        SELECT
            p.id::text,
            p.club_id::text,
            c.name     AS club_name,
            c.logo_url AS club_logo_url,
            p.full_name,
            p.position,
            p.jersey_number,
            p.date_of_birth::text,
            p.nationality,
            p.photo_url,
            p.height_cm,
            p.preferred_foot,
            p.bio,
            p.is_active,
            p.created_at::text,
            p.updated_at::text
        FROM players p
        LEFT JOIN clubs c ON c.id = p.club_id
        WHERE p.club_id = $1 AND p.is_active = TRUE
        ORDER BY p.position, p.jersey_number
        LIMIT $2 OFFSET $3
        """,
        club_id,
        limit,
        offset,
    )
    return [dict(r) for r in rows], int(total or 0)
