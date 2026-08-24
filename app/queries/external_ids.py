import asyncpg

from typing import Optional


async def list_for_entity(
    conn: asyncpg.Connection,
    entity_type: str,
    entity_id: str,
) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT
            id::text, entity_type, entity_id::text, provider, external_id,
            created_at::text, updated_at::text
        FROM external_ids
        WHERE entity_type = $1 AND entity_id = $2
        ORDER BY provider
        """,
        entity_type,
        entity_id,
    )
    return [dict(row) for row in rows]


async def upsert(
    conn: asyncpg.Connection,
    *,
    entity_type: str,
    entity_id: str,
    provider: str,
    external_id: str,
) -> dict:
    row = await conn.fetchrow(
        """
        INSERT INTO external_ids (entity_type, entity_id, provider, external_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (provider, entity_type, entity_id)
        DO UPDATE SET
            external_id = EXCLUDED.external_id,
            updated_at = NOW()
        RETURNING
            id::text, entity_type, entity_id::text, provider, external_id,
            created_at::text, updated_at::text
        """,
        entity_type,
        entity_id,
        provider,
        external_id,
    )
    return dict(row)


async def delete(
    conn: asyncpg.Connection,
    *,
    entity_type: str,
    entity_id: str,
    provider: str,
) -> bool:
    result = await conn.execute(
        """
        DELETE FROM external_ids
        WHERE entity_type = $1 AND entity_id = $2 AND provider = $3
        """,
        entity_type,
        entity_id,
        provider,
    )
    return result == "DELETE 1"


async def resolve(
    conn: asyncpg.Connection,
    *,
    provider: str,
    entity_type: str,
    external_id: str,
) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        SELECT
            id::text, entity_type, entity_id::text, provider, external_id,
            created_at::text, updated_at::text
        FROM external_ids
        WHERE provider = $1 AND entity_type = $2 AND external_id = $3
        """,
        provider,
        entity_type,
        external_id,
    )
    return dict(row) if row else None
