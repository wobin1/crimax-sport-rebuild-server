#!/usr/bin/env python3
"""
Seed demo data for testing lineups / club-manager flows.

Usage (from backend/):
  python3 scripts/seed_demo_data.py

Idempotent — safe to re-run. Prints login credentials at the end.

Demo managers (password for all): Manager@crimax1
  manager.bagado@crimax.ng  → Bagado United
  manager.atlas@crimax.ng   → Green Atlas Football Club
  manager.sabo@crimax.ng    → Sabo Rangers
  manager.tvw@crimax.ng     → Television wonders
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncpg
from dotenv import load_dotenv

from app.core.auth import hash_password
from app.core.formations import get_slots

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL is not set.")
    sys.exit(1)

MANAGER_PASSWORD = "Manager@crimax1"

# ── Club → manager + squad templates ──────────────────────────────────────────

CLUBS = [
    {
        "name": "Bagado United",
        "short_name": "BU",
        "home_ground": "Bagado Community Field",
        "manager": {
            "email": "manager.bagado@crimax.ng",
            "full_name": "Ibrahim Musa",
        },
    },
    {
        "name": "Green Atlas Football Club",
        "short_name": "GA",
        "home_ground": "Atlas Sports Complex",
        "manager": {
            "email": "manager.atlas@crimax.ng",
            "full_name": "Chinedu Okafor",
        },
    },
    {
        "name": "Sabo Rangers",
        "short_name": "SR",
        "home_ground": "Sabo Mini Stadium",
        "manager": {
            "email": "manager.sabo@crimax.ng",
            "full_name": "Amina Bello",
        },
    },
    {
        "name": "Television wonders",
        "short_name": "TVW",
        "home_ground": "Broadcast Park",
        "manager": {
            "email": "manager.tvw@crimax.ng",
            "full_name": "Tunde Adebayo",
        },
    },
]

# 16 players per club — enough for XI + bench. Jersey numbers unique within club.
# Names are varied per club via a prefix index.
SQUAD_TEMPLATE: list[tuple[str, str, int]] = [
    # (role_key used for naming, position, jersey)
    ("Keeper", "goalkeeper", 1),
    ("Backup Keeper", "goalkeeper", 12),
    ("Left Back", "defender", 3),
    ("Centre Back A", "defender", 4),
    ("Centre Back B", "defender", 5),
    ("Right Back", "defender", 2),
    ("Wing Back", "defender", 15),
    ("Holding Mid", "midfielder", 6),
    ("Box Mid A", "midfielder", 8),
    ("Box Mid B", "midfielder", 10),
    ("Wide Mid", "midfielder", 7),
    ("Attack Mid", "midfielder", 14),
    ("Left Wing", "forward", 11),
    ("Striker", "forward", 9),
    ("Right Wing", "forward", 17),
    ("Poacher", "forward", 19),
]

FIRST_NAMES = [
    "Emeka", "Yusuf", "Kunle", "Sani", "Femi", "Uche", "Bala", "Segun",
    "Ngozi", "Hassan", "Tobi", "Ifeanyi", "Kabir", "Dayo", "Jide", "Osas",
]
SURNAMES = [
    "Okoro", "Adeyemi", "Ibrahim", "Nwosu", "Bello", "Ojo", "Garba", "Eze",
    "Danjuma", "Afolabi", "Usman", "Chukwu", "Lawal", "Okonkwo", "Sule", "Bakare",
]


def player_name(club_index: int, slot_index: int) -> str:
    fi = (club_index * 7 + slot_index * 3) % len(FIRST_NAMES)
    si = (club_index * 5 + slot_index * 11) % len(SURNAMES)
    return f"{FIRST_NAMES[fi]} {SURNAMES[si]}"


async def upsert_club(conn: asyncpg.Connection, club: dict) -> str:
    row = await conn.fetchrow(
        "SELECT id::text FROM clubs WHERE name = $1",
        club["name"],
    )
    if row:
        await conn.execute(
            """
            UPDATE clubs
            SET short_name = COALESCE(short_name, $2),
                home_ground = COALESCE(home_ground, $3),
                is_active = TRUE
            WHERE id = $1
            """,
            row["id"],
            club["short_name"],
            club["home_ground"],
        )
        return row["id"]

    row = await conn.fetchrow(
        """
        INSERT INTO clubs (name, short_name, home_ground, founded_year, is_active)
        VALUES ($1, $2, $3, 2018, TRUE)
        RETURNING id::text
        """,
        club["name"],
        club["short_name"],
        club["home_ground"],
    )
    print(f"  + club {club['name']}")
    return row["id"]


async def upsert_manager(conn: asyncpg.Connection, club_id: str, manager: dict, password_hash: str) -> str:
    row = await conn.fetchrow(
        "SELECT id::text, role FROM users WHERE email = $1",
        manager["email"],
    )
    if row:
        user_id = row["id"]
        if row["role"] != "club_manager":
            await conn.execute(
                "UPDATE users SET role = 'club_manager', full_name = $2 WHERE id = $1",
                user_id,
                manager["full_name"],
            )
    else:
        row = await conn.fetchrow(
            """
            INSERT INTO users (email, password_hash, full_name, role, is_active)
            VALUES ($1, $2, $3, 'club_manager', TRUE)
            RETURNING id::text
            """,
            manager["email"],
            password_hash,
            manager["full_name"],
        )
        user_id = row["id"]
        print(f"  + manager {manager['email']}")

    await conn.execute(
        """
        INSERT INTO club_managers (user_id, club_id)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING
        """,
        user_id,
        club_id,
    )
    return user_id


async def ensure_squad(conn: asyncpg.Connection, club_id: str, club_index: int) -> list[dict]:
    existing = await conn.fetch(
        """
        SELECT id::text, full_name, position, jersey_number
        FROM players
        WHERE club_id = $1 AND is_active = TRUE
        ORDER BY jersey_number NULLS LAST, full_name
        """,
        club_id,
    )
    used_numbers = {r["jersey_number"] for r in existing if r["jersey_number"] is not None}
    players = [dict(r) for r in existing]

    for i, (_label, position, jersey) in enumerate(SQUAD_TEMPLATE):
        if jersey in used_numbers:
            continue
        # Skip if we already have enough players with this number conflict handled
        name = player_name(club_index, i)
        # Avoid duplicate names in the same club
        if any(p["full_name"] == name for p in players):
            name = f"{name} {jersey}"

        row = await conn.fetchrow(
            """
            INSERT INTO players (club_id, full_name, position, jersey_number, nationality, is_active)
            VALUES ($1, $2, $3, $4, 'Nigerian', TRUE)
            RETURNING id::text, full_name, position, jersey_number
            """,
            club_id,
            name,
            position,
            jersey,
        )
        players.append(dict(row))
        used_numbers.add(jersey)
        print(f"  + player {name} (#{jersey})")

    return players


async def ensure_tournament(conn: asyncpg.Connection) -> str:
    row = await conn.fetchrow(
        "SELECT id::text FROM tournaments WHERE is_current = TRUE LIMIT 1"
    )
    if row:
        return row["id"]

    row = await conn.fetchrow(
        """
        INSERT INTO tournaments (name, season, description, status, is_current, start_date, end_date)
        VALUES (
            'Crimax Cup', '2026',
            'Demo season for lineup and live scoring tests',
            'active', TRUE,
            $1, $2
        )
        RETURNING id::text
        """,
        date.today() - timedelta(days=14),
        date.today() + timedelta(days=90),
    )
    print("  + tournament Crimax Cup 2026")
    return row["id"]


async def link_tournament_clubs(conn: asyncpg.Connection, tournament_id: str, club_ids: list[str]) -> None:
    for cid in club_ids:
        await conn.execute(
            """
            INSERT INTO tournament_clubs (tournament_id, club_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            tournament_id,
            cid,
        )


async def ensure_fixtures(
    conn: asyncpg.Connection,
    tournament_id: str,
    club_ids_by_name: dict[str, str],
) -> list[str]:
    """Create a small matchday slate if missing. Returns fixture ids."""
    pairs = [
        ("Bagado United", "Green Atlas Football Club", "Matchday 1", date.today()),
        ("Sabo Rangers", "Television wonders", "Matchday 1", date.today() + timedelta(days=1)),
        ("Green Atlas Football Club", "Sabo Rangers", "Matchday 2", date.today() + timedelta(days=7)),
        ("Television wonders", "Bagado United", "Matchday 2", date.today() + timedelta(days=8)),
    ]
    grounds = {c["name"]: c["home_ground"] for c in CLUBS}

    fixture_ids: list[str] = []
    for home, away, round_name, match_date in pairs:
        home_id = club_ids_by_name[home]
        away_id = club_ids_by_name[away]
        existing = await conn.fetchrow(
            """
            SELECT id::text FROM fixtures
            WHERE tournament_id = $1
              AND home_club_id = $2
              AND away_club_id = $3
              AND match_date = $4
            """,
            tournament_id,
            home_id,
            away_id,
            match_date,
        )
        if existing:
            fixture_ids.append(existing["id"])
            continue

        # Also reuse any existing scheduled fixture for same pair regardless of date
        existing = await conn.fetchrow(
            """
            SELECT id::text FROM fixtures
            WHERE home_club_id = $1 AND away_club_id = $2 AND status = 'scheduled'
            LIMIT 1
            """,
            home_id,
            away_id,
        )
        if existing:
            fixture_ids.append(existing["id"])
            continue

        row = await conn.fetchrow(
            """
            INSERT INTO fixtures
                (tournament_id, home_club_id, away_club_id, match_date, match_time, venue, round, status)
            VALUES ($1, $2, $3, $4, '16:00', $5, $6, 'scheduled')
            RETURNING id::text
            """,
            tournament_id,
            home_id,
            away_id,
            match_date,
            grounds.get(home, "Crimax Ground"),
            round_name,
        )
        fixture_ids.append(row["id"])
        print(f"  + fixture {home} vs {away} ({round_name})")

    return fixture_ids


def pick_xi(players: list[dict], formation: str = "4-3-3") -> list[dict]:
    """Map squad players onto formation slots by rough position preference."""
    slots = get_slots(formation)
    by_pos: dict[str, list[dict]] = {
        "goalkeeper": [],
        "defender": [],
        "midfielder": [],
        "forward": [],
    }
    for p in players:
        pos = p.get("position") or "midfielder"
        by_pos.setdefault(pos, []).append(p)

    for pos in by_pos:
        by_pos[pos].sort(key=lambda p: (p.get("jersey_number") is None, p.get("jersey_number") or 99))

    # Slot → preferred position pool
    slot_pref = {
        "GK": "goalkeeper",
        "LB": "defender", "LCB": "defender", "CB": "defender", "RCB": "defender", "RB": "defender",
        "LWB": "defender", "RWB": "defender",
        "LM": "midfielder", "LCM": "midfielder", "CM": "midfielder", "RCM": "midfielder", "RM": "midfielder",
        "CDM": "midfielder", "LCDM": "midfielder", "RCDM": "midfielder",
        "LAM": "midfielder", "CAM": "midfielder", "RAM": "midfielder",
        "LW": "forward", "ST": "forward", "LST": "forward", "RST": "forward", "RW": "forward",
    }

    used: set[str] = set()
    leftover = [p for p in players]

    assignments: list[dict] = []
    for slot in slots:
        pref = slot_pref.get(slot["key"], "midfielder")
        chosen = None
        for p in by_pos.get(pref, []):
            if p["id"] not in used:
                chosen = p
                break
        if not chosen:
            for p in leftover:
                if p["id"] not in used:
                    chosen = p
                    break
        if not chosen:
            raise RuntimeError(f"Not enough players to fill slot {slot['key']}")
        used.add(chosen["id"])
        assignments.append({
            "player_id": chosen["id"],
            "slot_key": slot["key"],
            "offset_x": 0,
            "offset_y": 0,
        })
    return assignments


async def ensure_sample_lineup(
    conn: asyncpg.Connection,
    fixture_id: str,
    club_id: str,
    players: list[dict],
    updated_by: str,
    formation: str = "4-3-3",
) -> None:
    existing = await conn.fetchval(
        "SELECT 1 FROM fixture_lineups WHERE fixture_id = $1 AND club_id = $2",
        fixture_id,
        club_id,
    )
    if existing:
        return

    assignments = pick_xi(players, formation)
    row = await conn.fetchrow(
        """
        INSERT INTO fixture_lineups (fixture_id, club_id, formation, updated_by)
        VALUES ($1, $2, $3, $4)
        RETURNING id::text
        """,
        fixture_id,
        club_id,
        formation,
        updated_by,
    )
    lineup_id = row["id"]
    for a in assignments:
        await conn.execute(
            """
            INSERT INTO fixture_lineup_players
                (lineup_id, player_id, slot_key, is_starter, offset_x, offset_y)
            VALUES ($1, $2, $3, TRUE, $4, $5)
            """,
            lineup_id,
            a["player_id"],
            a["slot_key"],
            a["offset_x"],
            a["offset_y"],
        )
    print(f"  + sample lineup ({formation}) for club {club_id[:8]}… on fixture {fixture_id[:8]}…")


async def main() -> None:
    print("=== Crimax Sports — Seed demo data ===\n")
    password_hash = hash_password(MANAGER_PASSWORD)
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        club_ids_by_name: dict[str, str] = {}
        managers_by_club: dict[str, str] = {}
        squads: dict[str, list[dict]] = {}

        print("Clubs & managers")
        for i, club in enumerate(CLUBS):
            cid = await upsert_club(conn, club)
            club_ids_by_name[club["name"]] = cid
            mid = await upsert_manager(conn, cid, club["manager"], password_hash)
            managers_by_club[cid] = mid

        print("\nSquads")
        for i, club in enumerate(CLUBS):
            cid = club_ids_by_name[club["name"]]
            print(f"  {club['name']}")
            squads[cid] = await ensure_squad(conn, cid, i)

        print("\nTournament")
        tournament_id = await ensure_tournament(conn)
        await conn.execute(
            "UPDATE tournaments SET status = 'active', is_current = TRUE WHERE id = $1",
            tournament_id,
        )
        # Ensure only one current
        await conn.execute(
            "UPDATE tournaments SET is_current = FALSE WHERE id != $1",
            tournament_id,
        )
        await link_tournament_clubs(conn, tournament_id, list(club_ids_by_name.values()))
        print(f"  tournament id={tournament_id}")

        print("\nFixtures")
        fixture_ids = await ensure_fixtures(conn, tournament_id, club_ids_by_name)

        print("\nSample lineups (Matchday 1 home sides)")
        # First fixture: Bagado vs Atlas — seed both XIs so public page looks complete
        if fixture_ids:
            fx0 = fixture_ids[0]
            bagado = club_ids_by_name["Bagado United"]
            atlas = club_ids_by_name["Green Atlas Football Club"]
            await ensure_sample_lineup(
                conn, fx0, bagado, squads[bagado], managers_by_club[bagado], "4-3-3"
            )
            await ensure_sample_lineup(
                conn, fx0, atlas, squads[atlas], managers_by_club[atlas], "4-2-3-1"
            )

        # Counts
        counts = {}
        for table in ("clubs", "players", "users", "fixtures", "fixture_lineups", "club_managers"):
            counts[table] = await conn.fetchval(f"SELECT count(*) FROM {table}")

        print("\n=== Done ===")
        print(f"Counts: {counts}")
        print("\nLogin as club manager:")
        print(f"  Password for all managers: {MANAGER_PASSWORD}")
        for club in CLUBS:
            print(f"  {club['manager']['email']:32} → {club['name']}")
        print("\nSuper admin (existing): admin@crimax.ng / Admin@crimax1")
        print("\nTest paths:")
        print("  Admin lineups:  /admin/lineups")
        if fixture_ids:
            print(f"  Public fixture: /fixtures/{fixture_ids[0]}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
