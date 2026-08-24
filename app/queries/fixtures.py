import asyncpg
import json
from datetime import date as _Date, time as _Time, datetime, timezone
from typing import Optional

from app.core.match_clock import (
    PERIOD_FIRST_HALF,
    PERIOD_FULL_TIME,
    PERIOD_HALF_TIME,
    PERIOD_SECOND_HALF,
    enrich_clock_fields,
)


def _parse_date(v: Optional[str]) -> Optional[_Date]:
    return _Date.fromisoformat(v) if v else None


def _parse_time(v: Optional[str]) -> Optional[_Time]:
    return _Time.fromisoformat(v) if v else None


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return str(v)


async def lock_fixture(conn: asyncpg.Connection, fixture_id: str) -> bool:
    """Serialize all state-changing operations for one fixture."""
    row = await conn.fetchrow(
        "SELECT id FROM fixtures WHERE id = $1 FOR UPDATE",
        fixture_id,
    )
    return row is not None


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
        f.period,
        f.period_started_at,
        f.period_base_minute,
        f.stoppage_minutes,
        f.ruleset_snapshot,
        f.created_at::text,
        f.updated_at::text
    FROM fixtures f
    JOIN tournaments t  ON t.id  = f.tournament_id
    JOIN clubs      hc ON hc.id = f.home_club_id
    JOIN clubs      ac ON ac.id = f.away_club_id
"""


def _build_fixture_out(row: asyncpg.Record, scorers: Optional[dict] = None) -> dict:
    r = dict(row)
    ruleset_snapshot = r.get("ruleset_snapshot")
    if isinstance(ruleset_snapshot, str):
        ruleset_snapshot = json.loads(ruleset_snapshot)
    out = {
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
        "period": r.get("period"),
        "period_started_at": _iso(r.get("period_started_at")),
        "period_base_minute": int(r.get("period_base_minute") or 0),
        "stoppage_minutes": r.get("stoppage_minutes"),
        "ruleset_snapshot": ruleset_snapshot,
        "goal_scorers": scorers or {"home": [], "away": []},
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }
    return enrich_clock_fields(out)


async def get_effective_ruleset(
    conn: asyncpg.Connection, fixture_id: str
) -> dict | str | None:
    return await conn.fetchval(
        """
        SELECT COALESCE(f.ruleset_snapshot, t.ruleset)
        FROM fixtures f
        JOIN tournaments t ON t.id = f.tournament_id
        WHERE f.id = $1
        """,
        fixture_id,
    )


async def snapshot_ruleset(
    conn: asyncpg.Connection, fixture_id: str, ruleset: dict
) -> None:
    await conn.execute(
        """
        UPDATE fixtures
        SET ruleset_snapshot = $2::jsonb, updated_at = NOW()
        WHERE id = $1 AND ruleset_snapshot IS NULL
        """,
        fixture_id,
        json.dumps(ruleset),
    )


async def _goal_scorers_for_fixtures(
    conn: asyncpg.Connection, fixture_ids: list[str]
) -> dict[str, dict]:
    """Map fixture_id → { home: [...], away: [...] } goal scorer rows."""
    empty: dict[str, dict] = {fid: {"home": [], "away": []} for fid in fixture_ids}
    if not fixture_ids:
        return empty

    rows = await conn.fetch(
        """
        SELECT
            e.fixture_id::text,
            f.home_club_id::text AS home_club_id,
            f.away_club_id::text AS away_club_id,
            e.club_id::text AS club_id,
            e.event_type,
            e.minute,
            e.extra_time_minute,
            p.full_name AS player_name
        FROM match_events e
        JOIN fixtures f ON f.id = e.fixture_id
        LEFT JOIN players p ON p.id = e.player_id
        WHERE e.fixture_id = ANY($1::uuid[])
          AND e.event_type IN ('goal', 'penalty_scored', 'own_goal')
        ORDER BY e.minute, e.extra_time_minute NULLS FIRST, e.created_at
        """,
        fixture_ids,
    )

    for row in rows:
        fid = row["fixture_id"]
        bucket = empty.setdefault(fid, {"home": [], "away": []})
        is_og = row["event_type"] == "own_goal"
        # Own goals credit the opposing side on the board.
        if is_og:
            credited = (
                row["away_club_id"]
                if row["club_id"] == row["home_club_id"]
                else row["home_club_id"]
            )
        else:
            credited = row["club_id"]

        side = "home" if credited == row["home_club_id"] else "away"
        bucket[side].append(
            {
                "player_name": row["player_name"],
                "minute": row["minute"],
                "extra_time_minute": row["extra_time_minute"],
                "is_own_goal": is_og,
                "club_id": credited,
            }
        )
    return empty


async def _attach_scorers(conn: asyncpg.Connection, fixtures: list[dict]) -> list[dict]:
    if not fixtures:
        return fixtures
    scorers_map = await _goal_scorers_for_fixtures(conn, [f["id"] for f in fixtures])
    for f in fixtures:
        f["goal_scorers"] = scorers_map.get(f["id"], {"home": [], "away": []})
    return fixtures


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
    fixtures = [_build_fixture_out(r) for r in rows]
    await _attach_scorers(conn, fixtures)
    return fixtures, int(total or 0)


async def get_fixture_by_id(conn: asyncpg.Connection, fixture_id: str) -> Optional[dict]:
    row = await conn.fetchrow(
        f"{_FIXTURE_SELECT} WHERE f.id = $1",
        fixture_id,
    )
    if not row:
        return None
    fixture = _build_fixture_out(row)
    await _attach_scorers(conn, [fixture])
    return fixture


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
    fixtures = [_build_fixture_out(r) for r in rows]
    await _attach_scorers(conn, fixtures)
    return fixtures, int(total or 0)


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

    # Status → completed also seals full time on the clock (FT auto-set).
    null_fields: dict = {}
    if fields.get("status") == "completed":
        fields.setdefault("period", PERIOD_FULL_TIME)
        null_fields["period_started_at"] = None
        null_fields["stoppage_minutes"] = None

    set_parts: list[str] = []
    values: list = []
    for k, v in {**fields, **null_fields}.items():
        values.append(
            _parse_date(v) if k == "match_date" else
            _parse_time(v) if k == "match_time" else
            json.dumps(v) if k == "ruleset_snapshot" else v
        )
        set_parts.append(f"{k} = ${len(values) + 1}")

    await conn.execute(
        f"UPDATE fixtures SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = $1",
        fixture_id,
        *values,
    )
    return await get_fixture_by_id(conn, fixture_id)


async def apply_clock_action(
    conn: asyncpg.Connection,
    fixture_id: str,
    action: str,
    minute: Optional[int] = None,
    stoppage_minutes: Optional[int] = None,
) -> Optional[dict]:
    """Apply admin match-clock actions. Returns updated fixture or None."""
    existing = await get_fixture_by_id(conn, fixture_id)
    if not existing:
        return None

    now = datetime.now(timezone.utc)
    updates: dict = {}

    if action == "start_1h":
        updates = {
            "status": "live",
            "period": PERIOD_FIRST_HALF,
            "period_started_at": now,
            "period_base_minute": 0,
            "stoppage_minutes": None,
        }
    elif action == "ht":
        updates = {
            "status": "live",
            "period": PERIOD_HALF_TIME,
            "period_started_at": None,
            "stoppage_minutes": None,
        }
    elif action == "start_2h":
        updates = {
            "status": "live",
            "period": PERIOD_SECOND_HALF,
            "period_started_at": now,
            "period_base_minute": 45,
            "stoppage_minutes": None,
        }
    elif action == "ft":
        updates = {
            "status": "completed",
            "period": PERIOD_FULL_TIME,
            "period_started_at": None,
            "stoppage_minutes": None,
        }
    elif action == "nudge":
        if minute is None:
            raise ValueError("minute is required for nudge")
        period = existing.get("period")
        if period not in (PERIOD_FIRST_HALF, PERIOD_SECOND_HALF):
            raise ValueError("Can only nudge the clock during a live half")
        updates = {
            "period_base_minute": minute,
            "period_started_at": now,
        }
    elif action == "set_stoppage":
        if stoppage_minutes is None:
            raise ValueError("stoppage_minutes is required")
        period = existing.get("period")
        if period not in (PERIOD_FIRST_HALF, PERIOD_SECOND_HALF):
            raise ValueError("Stoppage can only be set during a live half")
        updates = {"stoppage_minutes": stoppage_minutes}
    else:
        raise ValueError(f"Unknown clock action: {action}")

    # Build UPDATE that can set NULL
    set_parts: list[str] = []
    values: list = []
    for k, v in updates.items():
        values.append(v)
        set_parts.append(f"{k} = ${len(values) + 1}")

    await conn.execute(
        f"UPDATE fixtures SET {', '.join(set_parts)}, updated_at = NOW() WHERE id = $1",
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
