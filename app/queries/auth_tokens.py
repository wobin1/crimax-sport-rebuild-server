"""Single-use, expiring, hashed tokens for password reset."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

import asyncpg

PURPOSE_PASSWORD_RESET = "password_reset"


def hash_token(raw_token: str) -> str:
    return sha256(raw_token.encode()).hexdigest()


async def create_token(
    conn: asyncpg.Connection,
    *,
    user_id: str,
    purpose: str,
    ttl_minutes: int,
) -> str:
    """Issue a new token, invalidating any prior unused tokens of the same purpose."""
    raw_token = token_urlsafe(32)
    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=ttl_minutes)

    async with conn.transaction():
        await conn.execute(
            """
            UPDATE auth_tokens
            SET used_at = $1
            WHERE user_id = $2 AND purpose = $3 AND used_at IS NULL
            """,
            now,
            user_id,
            purpose,
        )
        await conn.execute(
            """
            INSERT INTO auth_tokens (user_id, purpose, token_hash, expires_at, created_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user_id,
            purpose,
            token_hash,
            expires_at,
            now,
        )
    return raw_token


async def consume_token(
    conn: asyncpg.Connection, *, raw_token: str, purpose: str
) -> UUID | None:
    """Validate and atomically consume a token. Returns the user_id or None."""
    if not raw_token:
        return None

    token_hash = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    row = await conn.fetchrow(
        """
        UPDATE auth_tokens
        SET used_at = $1
        WHERE token_hash = $2
          AND purpose = $3
          AND used_at IS NULL
          AND expires_at > $1
        RETURNING user_id
        """,
        now,
        token_hash,
        purpose,
    )
    if not row:
        return None
    return row["user_id"]
