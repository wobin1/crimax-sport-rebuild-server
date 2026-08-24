import json
from typing import Any

import asyncpg


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


async def record(
    conn: asyncpg.Connection,
    *,
    actor: dict,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    fixture_id: str | None = None,
    club_id: str | None = None,
    before_data: Any = None,
    after_data: Any = None,
    reason: str | None = None,
    ruleset: Any = None,
    request_id: str | None = None,
) -> str:
    """Append one audit entry using the caller's transaction."""
    audit_id = await conn.fetchval(
        """
        INSERT INTO audit_log (
            actor_user_id, actor_role, action, entity_type, entity_id,
            fixture_id, club_id, before_data, after_data, reason,
            ruleset, request_id
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7,
            $8::jsonb, $9::jsonb, $10, $11::jsonb, $12
        )
        RETURNING id::text
        """,
        actor["id"],
        actor["role"],
        action,
        entity_type,
        entity_id,
        fixture_id,
        club_id,
        _json(before_data),
        _json(after_data),
        reason,
        _json(ruleset),
        request_id,
    )
    return str(audit_id)


async def get_for_fixture(
    conn: asyncpg.Connection,
    fixture_id: str,
    *,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    total = await conn.fetchval(
        "SELECT COUNT(*) FROM audit_log WHERE fixture_id = $1",
        fixture_id,
    )
    rows = await conn.fetch(
        """
        SELECT
            a.id::text,
            a.actor_user_id::text,
            u.full_name AS actor_name,
            a.actor_role,
            a.action,
            a.entity_type,
            a.entity_id::text,
            a.fixture_id::text,
            a.club_id::text,
            a.before_data,
            a.after_data,
            a.reason,
            a.ruleset,
            a.request_id,
            a.created_at::text
        FROM audit_log a
        LEFT JOIN users u ON u.id = a.actor_user_id
        WHERE a.fixture_id = $1
        ORDER BY a.created_at DESC
        LIMIT $2 OFFSET $3
        """,
        fixture_id,
        limit,
        offset,
    )
    return [_audit_dict(row) for row in rows], int(total or 0)


def _audit_dict(row) -> dict:
    result = dict(row)
    for field in ("before_data", "after_data", "ruleset"):
        value = result.get(field)
        if isinstance(value, str):
            result[field] = json.loads(value)
    return result
