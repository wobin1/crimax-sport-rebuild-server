import asyncpg
from typing import Optional

from app.core.formations import FORMATIONS, get_slots


def _build_lineup_out(header: dict, player_rows: list) -> dict:
    slots = {s["key"]: s for s in get_slots(header["formation"])}
    players = []
    for r in player_rows:
        slot = slots.get(r["slot_key"], {"label": r["slot_key"], "x": 50, "y": 50})
        players.append({
            "player_id": r["player_id"],
            "full_name": r["full_name"],
            "jersey_number": r["jersey_number"],
            "photo_url": r["photo_url"],
            "position": r["position"],
            "slot_key": r["slot_key"],
            "slot_label": slot["label"],
            "x": float(slot["x"]),
            "y": float(slot["y"]),
            "offset_x": float(r["offset_x"]),
            "offset_y": float(r["offset_y"]),
            "is_starter": r["is_starter"],
        })
    # Keep formation slot order
    order = {s["key"]: i for i, s in enumerate(get_slots(header["formation"]))}
    players.sort(key=lambda p: order.get(p["slot_key"], 99))

    return {
        "id": header["id"],
        "fixture_id": header["fixture_id"],
        "club_id": header["club_id"],
        "club_name": header["club_name"],
        "club_short_name": header["club_short_name"],
        "club_logo_url": header["club_logo_url"],
        "formation": header["formation"],
        "players": players,
        "updated_at": header["updated_at"],
    }


async def _fetch_lineup_header(
    conn: asyncpg.Connection,
    fixture_id: str,
    club_id: str,
) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        SELECT
            fl.id::text,
            fl.fixture_id::text,
            fl.club_id::text,
            c.name AS club_name,
            c.short_name AS club_short_name,
            c.logo_url AS club_logo_url,
            fl.formation,
            fl.updated_at::text
        FROM fixture_lineups fl
        JOIN clubs c ON c.id = fl.club_id
        WHERE fl.fixture_id = $1 AND fl.club_id = $2
        """,
        fixture_id,
        club_id,
    )
    return dict(row) if row else None


async def _fetch_lineup_players(conn: asyncpg.Connection, lineup_id: str) -> list:
    return await conn.fetch(
        """
        SELECT
            lp.player_id::text,
            p.full_name,
            p.jersey_number,
            p.photo_url,
            p.position,
            lp.slot_key,
            lp.offset_x,
            lp.offset_y,
            lp.is_starter
        FROM fixture_lineup_players lp
        JOIN players p ON p.id = lp.player_id
        WHERE lp.lineup_id = $1
        """,
        lineup_id,
    )


async def get_lineup(
    conn: asyncpg.Connection,
    fixture_id: str,
    club_id: str,
) -> Optional[dict]:
    header = await _fetch_lineup_header(conn, fixture_id, club_id)
    if not header:
        return None
    players = await _fetch_lineup_players(conn, header["id"])
    return _build_lineup_out(header, players)


async def get_fixture_lineups(conn: asyncpg.Connection, fixture_id: str) -> dict:
    fixture = await conn.fetchrow(
        "SELECT home_club_id::text, away_club_id::text FROM fixtures WHERE id = $1",
        fixture_id,
    )
    if not fixture:
        return {"fixture_id": fixture_id, "home": None, "away": None}

    home = await get_lineup(conn, fixture_id, fixture["home_club_id"])
    away = await get_lineup(conn, fixture_id, fixture["away_club_id"])
    return {"fixture_id": fixture_id, "home": home, "away": away}


async def upsert_lineup(
    conn: asyncpg.Connection,
    fixture_id: str,
    club_id: str,
    formation: str,
    players: list[dict],
    updated_by: str,
) -> dict:
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO fixture_lineups (fixture_id, club_id, formation, updated_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (fixture_id, club_id) DO UPDATE
              SET formation = EXCLUDED.formation,
                  updated_by = EXCLUDED.updated_by,
                  updated_at = NOW()
            RETURNING id::text
            """,
            fixture_id,
            club_id,
            formation,
            updated_by,
        )
        lineup_id = row["id"]

        await conn.execute(
            "DELETE FROM fixture_lineup_players WHERE lineup_id = $1",
            lineup_id,
        )

        for p in players:
            await conn.execute(
                """
                INSERT INTO fixture_lineup_players
                    (lineup_id, player_id, slot_key, is_starter, offset_x, offset_y)
                VALUES ($1, $2, $3, TRUE, $4, $5)
                """,
                lineup_id,
                p["player_id"],
                p["slot_key"],
                p.get("offset_x", 0),
                p.get("offset_y", 0),
            )

    result = await get_lineup(conn, fixture_id, club_id)
    assert result is not None
    return result


async def delete_lineup(conn: asyncpg.Connection, fixture_id: str, club_id: str) -> bool:
    result = await conn.execute(
        "DELETE FROM fixture_lineups WHERE fixture_id = $1 AND club_id = $2",
        fixture_id,
        club_id,
    )
    return result == "DELETE 1"


def known_formations() -> list[str]:
    return list(FORMATIONS.keys())
