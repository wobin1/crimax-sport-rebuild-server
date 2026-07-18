import asyncpg
from typing import Optional


_SCORING_EVENTS = ("goal", "own_goal", "penalty_scored")


async def get_fixture_events(
    conn: asyncpg.Connection,
    fixture_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM match_events WHERE fixture_id = $1",
        fixture_id,
    )
    rows = await conn.fetch(
        """
        SELECT
            e.id::text,
            e.fixture_id::text,
            e.player_id::text,
            p.full_name   AS player_name,
            e.club_id::text,
            c.name        AS club_name,
            e.event_type,
            e.minute,
            e.extra_time_minute,
            e.description,
            e.created_at::text
        FROM match_events e
        LEFT JOIN players p ON p.id = e.player_id
        LEFT JOIN clubs   c ON c.id = e.club_id
        WHERE e.fixture_id = $1
        ORDER BY e.minute, e.extra_time_minute NULLS FIRST, e.created_at
        LIMIT $2 OFFSET $3
        """,
        fixture_id,
        limit,
        offset,
    )
    return [dict(r) for r in rows], int(total or 0)


async def create_event(conn: asyncpg.Connection, data: dict) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO match_events
            (fixture_id, player_id, club_id, event_type, minute, extra_time_minute, description)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id::text, fixture_id::text, player_id::text, club_id::text,
                  event_type, minute, extra_time_minute, description, created_at::text
        """,
        data["fixture_id"],
        data.get("player_id"),
        data.get("club_id"),
        data["event_type"],
        data["minute"],
        data.get("extra_time_minute"),
        data.get("description"),
    )
    return dict(row)


async def delete_event(conn: asyncpg.Connection, event_id: str) -> bool:
    result = await conn.execute("DELETE FROM match_events WHERE id = $1", event_id)
    return result == "DELETE 1"


async def recalculate_score(conn: asyncpg.Connection, fixture_id: str) -> tuple[int, int]:
    """
    Recomputes home/away score from match_events and updates the fixture.
    Returns (home_score, away_score).
    """
    fixture = await conn.fetchrow(
        "SELECT home_club_id, away_club_id FROM fixtures WHERE id = $1",
        fixture_id,
    )
    if not fixture:
        return (0, 0)

    home_id = fixture["home_club_id"]
    away_id = fixture["away_club_id"]

    async def count_goals(club_id, is_home: bool) -> int:
        regular = await conn.fetchval(
            """
            SELECT COUNT(*) FROM match_events
            WHERE fixture_id = $1 AND club_id = $2
              AND event_type IN ('goal', 'penalty_scored')
            """,
            fixture_id,
            club_id,
        )
        # own goals scored by the OPPOSING club add to this club's tally
        own_goals = await conn.fetchval(
            """
            SELECT COUNT(*) FROM match_events
            WHERE fixture_id = $1
              AND club_id = $2
              AND event_type = 'own_goal'
            """,
            fixture_id,
            away_id if is_home else home_id,
        )
        return (regular or 0) + (own_goals or 0)

    home_score = await count_goals(home_id, is_home=True)
    away_score = await count_goals(away_id, is_home=False)

    await conn.execute(
        "UPDATE fixtures SET home_score = $2, away_score = $3 WHERE id = $1",
        fixture_id,
        home_score,
        away_score,
    )
    return (home_score, away_score)
