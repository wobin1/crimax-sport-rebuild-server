import asyncpg
from datetime import date as _Date
from typing import Optional


def _parse_date(v) -> _Date | None:
    return _Date.fromisoformat(v) if v else None


_PLAYER_SELECT = """
    SELECT
        p.id::text,
        p.club_id::text,
        c.name         AS club_name,
        c.logo_url     AS club_logo_url,
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
"""


async def get_all_players(
    conn: asyncpg.Connection,
    club_id: Optional[str] = None,
    active_only: bool = True,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    conditions = []
    params: list = []

    if active_only:
        conditions.append("p.is_active = TRUE")
    if club_id:
        params.append(club_id)
        conditions.append(f"p.club_id = ${len(params)}")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    total = await conn.fetchval(
        f"SELECT COUNT(*) FROM players p {where}",
        *params,
    )
    params.extend([limit, offset])
    rows = await conn.fetch(
        f"{_PLAYER_SELECT} {where} ORDER BY p.full_name LIMIT ${len(params) - 1} OFFSET ${len(params)}",
        *params,
    )
    return [dict(r) for r in rows], int(total or 0)


async def get_player_by_id(conn: asyncpg.Connection, player_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        f"{_PLAYER_SELECT} WHERE p.id = $1",
        player_id,
    )
    return dict(row) if row else None


async def create_player(conn: asyncpg.Connection, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO players
            (club_id, full_name, position, jersey_number, date_of_birth, nationality,
             photo_url, height_cm, preferred_foot, bio)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id::text
        """,
        data["club_id"],
        data["full_name"],
        data.get("position"),
        data.get("jersey_number"),
        _parse_date(data.get("date_of_birth")),
        data.get("nationality", "Nigerian"),
        data.get("photo_url"),
        data.get("height_cm"),
        data.get("preferred_foot"),
        data.get("bio"),
    )
    return await get_player_by_id(conn, row["id"])


async def update_player(conn: asyncpg.Connection, player_id: str, data: dict) -> Optional[dict]:
    allowed = {
        "club_id",
        "full_name",
        "position",
        "jersey_number",
        "date_of_birth",
        "nationality",
        "photo_url",
        "height_cm",
        "preferred_foot",
        "bio",
        "is_active",
    }
    fields = {k: v for k, v in data.items() if k in allowed and v is not None}
    if not fields:
        return await get_player_by_id(conn, player_id)

    if "date_of_birth" in fields:
        fields["date_of_birth"] = _parse_date(fields["date_of_birth"])
    if "position" in fields and hasattr(fields["position"], "value"):
        fields["position"] = fields["position"].value
    if "jersey_number" in fields:
        fields["jersey_number"] = int(fields["jersey_number"])
    if "height_cm" in fields:
        fields["height_cm"] = int(fields["height_cm"])

    set_clauses = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(fields))
    values = list(fields.values())

    row = await conn.fetchrow(
        f"""
        UPDATE players SET {set_clauses}
        WHERE id = $1
        RETURNING id::text
        """,
        player_id,
        *values,
    )
    if not row:
        return None
    return await get_player_by_id(conn, row["id"])


async def delete_player(conn: asyncpg.Connection, player_id: str) -> bool:
    result = await conn.execute("DELETE FROM players WHERE id = $1", player_id)
    return result == "DELETE 1"


async def get_player_profile(conn: asyncpg.Connection, player_id: str) -> Optional[dict]:
    player = await get_player_by_id(conn, player_id)
    if not player:
        return None

    totals = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE event_type IN ('goal','penalty_scored') AND player_id = $1::uuid) AS goals,
            COUNT(*) FILTER (WHERE event_type = 'own_goal'     AND player_id = $1::uuid)             AS own_goals,
            COUNT(*) FILTER (WHERE event_type = 'yellow_card'  AND player_id = $1::uuid)             AS yellow_cards,
            COUNT(*) FILTER (WHERE event_type = 'red_card'     AND player_id = $1::uuid)             AS red_cards,
            COUNT(*) FILTER (WHERE event_type = 'penalty_scored' AND player_id = $1::uuid)           AS penalties,
            COUNT(*) FILTER (WHERE assist_player_id = $1::uuid)                                     AS assists
        FROM match_events
        WHERE player_id = $1::uuid OR assist_player_id = $1::uuid
        """,
        player_id,
    )

    tourney_rows = await conn.fetch(
        """
        SELECT
            t.id::text AS tournament_id,
            t.name     AS tournament_name,
            t.season,
            COUNT(me.id) FILTER (WHERE me.event_type IN ('goal','penalty_scored') AND me.player_id = $1::uuid) AS goals,
            COUNT(me.id) FILTER (WHERE me.event_type = 'own_goal'    AND me.player_id = $1::uuid)              AS own_goals,
            COUNT(me.id) FILTER (WHERE me.event_type = 'yellow_card' AND me.player_id = $1::uuid)              AS yellow_cards,
            COUNT(me.id) FILTER (WHERE me.event_type = 'red_card'    AND me.player_id = $1::uuid)              AS red_cards,
            COUNT(me.id) FILTER (WHERE me.event_type = 'penalty_scored' AND me.player_id = $1::uuid)           AS penalties,
            COUNT(me.id) FILTER (WHERE me.assist_player_id = $1::uuid)                                        AS assists
        FROM tournaments t
        JOIN fixtures f    ON f.tournament_id = t.id
        JOIN match_events me ON me.fixture_id = f.id
        WHERE me.player_id = $1::uuid OR me.assist_player_id = $1::uuid
        GROUP BY t.id, t.name, t.season
        ORDER BY MAX(f.match_date) DESC NULLS LAST
        """,
        player_id,
    )

    empty = {"goals": 0, "own_goals": 0, "yellow_cards": 0, "red_cards": 0, "penalties": 0, "assists": 0}
    career_totals = dict(totals) if totals else empty

    return {
        **player,
        "career_totals": career_totals,
        "tournament_stats": [dict(r) for r in tourney_rows],
    }
