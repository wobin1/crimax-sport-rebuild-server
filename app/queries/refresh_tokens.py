import hashlib
from datetime import datetime, timedelta, timezone

import asyncpg

from app.config import get_settings


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def store_refresh_token(
    conn: asyncpg.Connection, *, user_id: str, token: str
) -> None:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    await conn.execute(
        """
        INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
        VALUES ($1, $2, $3)
        """,
        user_id,
        hash_token(token),
        expires_at,
    )


async def rotate_refresh_token(
    conn: asyncpg.Connection, *, old_token: str, user_id: str, new_token: str
) -> bool:
    settings = get_settings()
    async with conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT id, user_id::text, expires_at, revoked_at
            FROM refresh_tokens
            WHERE token_hash = $1
            FOR UPDATE
            """,
            hash_token(old_token),
        )
        if not row or row["revoked_at"] is not None:
            return False
        expires = row["expires_at"]
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc) or row["user_id"] != user_id:
            return False
        await conn.execute(
            "UPDATE refresh_tokens SET revoked_at = NOW() WHERE id = $1",
            row["id"],
        )
        await store_refresh_token(conn, user_id=user_id, token=new_token)
        return True


async def revoke_refresh_token(conn: asyncpg.Connection, token: str) -> bool:
    result = await conn.execute(
        """
        UPDATE refresh_tokens
        SET revoked_at = NOW()
        WHERE token_hash = $1 AND revoked_at IS NULL
        """,
        hash_token(token),
    )
    return result == "UPDATE 1"


async def revoke_all_for_user(conn: asyncpg.Connection, user_id: str) -> int:
    result = await conn.execute(
        """
        UPDATE refresh_tokens
        SET revoked_at = NOW()
        WHERE user_id = $1 AND revoked_at IS NULL
        """,
        user_id,
    )
    return int(result.split()[-1])
