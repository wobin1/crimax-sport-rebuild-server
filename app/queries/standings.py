import asyncpg
from typing import Optional


async def get_standings(conn: asyncpg.Connection, tournament_id: str) -> Optional[dict]:
    """
    Computes the league table on-the-fly from completed fixtures.
    Rules: Win=3pts, Draw=1pt, Loss=0pts.
    Tiebreaker order: points → goal_difference → goals_for → name.
    """
    tournament = await conn.fetchrow(
        "SELECT id::text, name, season FROM tournaments WHERE id = $1",
        tournament_id,
    )
    if not tournament:
        return None

    rows = await conn.fetch(
        """
        WITH club_list AS (
            SELECT c.id, c.name, c.short_name, c.logo_url
            FROM clubs c
            JOIN tournament_clubs tc ON tc.club_id = c.id
            WHERE tc.tournament_id = $1
        ),
        match_stats AS (
            SELECT
                f.home_club_id AS club_id,
                f.home_score   AS gf,
                f.away_score   AS ga,
                CASE
                    WHEN f.home_score > f.away_score THEN 3
                    WHEN f.home_score = f.away_score THEN 1
                    ELSE 0
                END AS pts,
                (f.home_score > f.away_score)::int AS won,
                (f.home_score = f.away_score)::int AS drawn,
                (f.home_score < f.away_score)::int AS lost
            FROM fixtures f
            WHERE f.tournament_id = $1 AND f.status = 'completed'

            UNION ALL

            SELECT
                f.away_club_id AS club_id,
                f.away_score   AS gf,
                f.home_score   AS ga,
                CASE
                    WHEN f.away_score > f.home_score THEN 3
                    WHEN f.away_score = f.home_score THEN 1
                    ELSE 0
                END AS pts,
                (f.away_score > f.home_score)::int AS won,
                (f.away_score = f.home_score)::int AS drawn,
                (f.away_score < f.home_score)::int AS lost
            FROM fixtures f
            WHERE f.tournament_id = $1 AND f.status = 'completed'
        ),
        aggregated AS (
            SELECT
                cl.id::text          AS club_id,
                cl.name              AS club_name,
                cl.short_name        AS club_short_name,
                cl.logo_url          AS club_logo_url,
                COUNT(ms.club_id)    AS played,
                COALESCE(SUM(ms.won),   0) AS won,
                COALESCE(SUM(ms.drawn), 0) AS drawn,
                COALESCE(SUM(ms.lost),  0) AS lost,
                COALESCE(SUM(ms.gf),    0) AS goals_for,
                COALESCE(SUM(ms.ga),    0) AS goals_against,
                COALESCE(SUM(ms.gf), 0) - COALESCE(SUM(ms.ga), 0) AS goal_difference,
                COALESCE(SUM(ms.pts),   0) AS points
            FROM club_list cl
            LEFT JOIN match_stats ms ON ms.club_id = cl.id
            GROUP BY cl.id, cl.name, cl.short_name, cl.logo_url
        )
        SELECT *
        FROM aggregated
        ORDER BY points DESC, goal_difference DESC, goals_for DESC, club_name
        """,
        tournament_id,
    )

    table = []
    for pos, row in enumerate(rows, start=1):
        entry = dict(row)
        entry["position"] = pos
        table.append(entry)

    return {
        "tournament_id": tournament["id"],
        "tournament_name": tournament["name"],
        "season": tournament["season"],
        "table": table,
    }
