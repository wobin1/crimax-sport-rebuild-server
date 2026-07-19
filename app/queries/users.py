"""User and invite queries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any
from uuid import UUID

import asyncpg

from app.config import get_settings
from app.core.auth import hash_password


def hash_invite_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def _row_user(row: asyncpg.Record) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "full_name": row["full_name"],
        "role": row["role"],
        "is_active": row["is_active"],
        "club_ids": [str(c) for c in (row["club_ids"] or [])],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_invite(row: asyncpg.Record, invite_url: str | None = None) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "full_name": row["full_name"],
        "role": row["role"],
        "club_ids": [str(c) for c in (row["club_ids"] or [])],
        "expires_at": row["expires_at"],
        "invited_by": str(row["invited_by"]) if row["invited_by"] else None,
        "accepted_at": row["accepted_at"],
        "created_at": row["created_at"],
        "invite_url": invite_url,
        "email_sent": False,
    }


async def list_users(
    conn: asyncpg.Connection,
    *,
    role: str | None = None,
    roles: list[str] | None = None,
    active_only: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    clauses: list[str] = []
    args: list[Any] = []

    if role:
        args.append(role)
        clauses.append(f"u.role = ${len(args)}")
    elif roles:
        args.append(roles)
        clauses.append(f"u.role = ANY(${len(args)}::text[])")

    if active_only is True:
        clauses.append("u.is_active = TRUE")
    elif active_only is False:
        clauses.append("u.is_active = FALSE")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    total = await conn.fetchval(f"SELECT COUNT(*) FROM users u {where}", *args)

    args.extend([limit, offset])
    rows = await conn.fetch(
        f"""
        SELECT
            u.id, u.email, u.full_name, u.role, u.is_active,
            u.created_at, u.updated_at,
            COALESCE(
                array_agg(cm.club_id::text) FILTER (WHERE cm.club_id IS NOT NULL),
                ARRAY[]::text[]
            ) AS club_ids
        FROM users u
        LEFT JOIN club_managers cm ON cm.user_id = u.id
        {where}
        GROUP BY u.id
        ORDER BY u.created_at DESC
        LIMIT ${len(args) - 1} OFFSET ${len(args)}
        """,
        *args,
    )
    return [_row_user(r) for r in rows], int(total or 0)


async def get_user_by_id(conn: asyncpg.Connection, user_id: str) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT
            u.id, u.email, u.full_name, u.role, u.is_active,
            u.created_at, u.updated_at,
            COALESCE(
                array_agg(cm.club_id::text) FILTER (WHERE cm.club_id IS NOT NULL),
                ARRAY[]::text[]
            ) AS club_ids
        FROM users u
        LEFT JOIN club_managers cm ON cm.user_id = u.id
        WHERE u.id = $1
        GROUP BY u.id
        """,
        user_id,
    )
    return _row_user(row) if row else None


async def set_club_assignments(
    conn: asyncpg.Connection,
    user_id: str,
    club_ids: list[str],
) -> None:
    await conn.execute("DELETE FROM club_managers WHERE user_id = $1", user_id)
    for club_id in club_ids:
        await conn.execute(
            """
            INSERT INTO club_managers (user_id, club_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            user_id,
            club_id,
        )


async def update_user(
    conn: asyncpg.Connection,
    user_id: str,
    data: dict[str, Any],
) -> dict | None:
    fields: list[str] = []
    args: list[Any] = []
    for key in ("full_name", "is_active"):
        if key in data and data[key] is not None:
            args.append(data[key])
            fields.append(f"{key} = ${len(args)}")

    if fields:
        fields.append("updated_at = NOW()")
        args.append(user_id)
        await conn.execute(
            f"UPDATE users SET {', '.join(fields)} WHERE id = ${len(args)}",
            *args,
        )

    if "club_ids" in data and data["club_ids"] is not None:
        await set_club_assignments(conn, user_id, data["club_ids"])

    return await get_user_by_id(conn, user_id)


async def list_pending_invites(
    conn: asyncpg.Connection,
    *,
    roles: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    clauses = ["accepted_at IS NULL"]
    args: list[Any] = []
    if roles:
        args.append(roles)
        clauses.append(f"role = ANY(${len(args)}::text[])")
    where = " AND ".join(clauses)

    total = await conn.fetchval(f"SELECT COUNT(*) FROM invites WHERE {where}", *args)
    args.extend([limit, offset])
    rows = await conn.fetch(
        f"""
        SELECT id, email, full_name, role, club_ids, expires_at,
               invited_by, accepted_at, created_at
        FROM invites
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ${len(args) - 1} OFFSET ${len(args)}
        """,
        *args,
    )
    return [_row_invite(r) for r in rows], int(total or 0)


async def get_invite_by_id(conn: asyncpg.Connection, invite_id: str) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT id, email, full_name, role, club_ids, expires_at,
               invited_by, accepted_at, created_at
        FROM invites WHERE id = $1
        """,
        invite_id,
    )
    return _row_invite(row) if row else None


async def create_invite(
    conn: asyncpg.Connection,
    *,
    email: str,
    full_name: str,
    role: str,
    club_ids: list[str],
    invited_by: str,
) -> tuple[dict, str]:
    """Returns (invite_dict, raw_token)."""
    settings = get_settings()
    raw_token = token_urlsafe(32)
    token_hash = hash_invite_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.invite_expire_hours)

    # Drop any prior pending invites for this email
    await conn.execute(
        """
        DELETE FROM invites
        WHERE lower(email) = lower($1) AND accepted_at IS NULL
        """,
        email,
    )

    club_uuids = [UUID(c) for c in club_ids]
    row = await conn.fetchrow(
        """
        INSERT INTO invites (
            email, full_name, role, club_ids, token_hash, expires_at, invited_by
        )
        VALUES ($1, $2, $3, $4::uuid[], $5, $6, $7)
        RETURNING id, email, full_name, role, club_ids, expires_at,
                  invited_by, accepted_at, created_at
        """,
        email.lower().strip(),
        full_name,
        role,
        club_uuids,
        token_hash,
        expires_at,
        invited_by,
    )
    url = f"{settings.frontend_url.rstrip('/')}/admin/accept-invite?token={raw_token}"
    return _row_invite(row, invite_url=url), raw_token


async def rotate_invite_token(conn: asyncpg.Connection, invite_id: str) -> tuple[dict, str] | None:
    settings = get_settings()
    raw_token = token_urlsafe(32)
    token_hash = hash_invite_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.invite_expire_hours)

    row = await conn.fetchrow(
        """
        UPDATE invites
        SET token_hash = $2,
            expires_at = $3,
            accepted_at = NULL
        WHERE id = $1 AND accepted_at IS NULL
        RETURNING id, email, full_name, role, club_ids, expires_at,
                  invited_by, accepted_at, created_at
        """,
        invite_id,
        token_hash,
        expires_at,
    )
    if not row:
        return None
    url = f"{settings.frontend_url.rstrip('/')}/admin/accept-invite?token={raw_token}"
    return _row_invite(row, invite_url=url), raw_token


async def delete_invite(conn: asyncpg.Connection, invite_id: str) -> bool:
    result = await conn.execute(
        "DELETE FROM invites WHERE id = $1 AND accepted_at IS NULL",
        invite_id,
    )
    return result.endswith("1")


async def accept_invite(
    conn: asyncpg.Connection,
    *,
    token: str,
    password: str,
) -> dict:
    token_hash = hash_invite_token(token)
    invite = await conn.fetchrow(
        """
        SELECT id, email, full_name, role, club_ids, expires_at, accepted_at
        FROM invites
        WHERE token_hash = $1
        """,
        token_hash,
    )
    if not invite:
        raise LookupError("Invalid invite token.")
    if invite["accepted_at"] is not None:
        raise ValueError("This invite has already been used.")
    expires = invite["expires_at"]
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise ValueError("This invite has expired.")

    existing = await conn.fetchrow(
        "SELECT id, password_hash, is_active FROM users WHERE lower(email) = lower($1)",
        invite["email"],
    )
    pw_hash = hash_password(password)

    async with conn.transaction():
        if existing:
            if existing["password_hash"]:
                raise ValueError("An account with this email already exists. Please sign in.")
            user_id = existing["id"]
            await conn.execute(
                """
                UPDATE users
                SET password_hash = $2,
                    full_name = $3,
                    role = $4,
                    is_active = TRUE,
                    updated_at = NOW()
                WHERE id = $1
                """,
                user_id,
                pw_hash,
                invite["full_name"],
                invite["role"],
            )
        else:
            user_id = await conn.fetchval(
                """
                INSERT INTO users (email, password_hash, full_name, role, is_active)
                VALUES ($1, $2, $3, $4, TRUE)
                RETURNING id
                """,
                invite["email"],
                pw_hash,
                invite["full_name"],
                invite["role"],
            )

        await set_club_assignments(
            conn,
            str(user_id),
            [str(c) for c in (invite["club_ids"] or [])],
        )
        await conn.execute(
            "UPDATE invites SET accepted_at = NOW() WHERE id = $1",
            invite["id"],
        )

    user = await get_user_by_id(conn, str(user_id))
    if not user:
        raise RuntimeError("Failed to load user after invite accept.")
    return user
