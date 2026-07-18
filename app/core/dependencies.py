from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import asyncpg

from app.core.auth import decode_access_token
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.database.pool import get_conn

bearer_scheme = HTTPBearer(auto_error=False)


# ── Current user ──────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: asyncpg.Connection = Depends(get_conn),
) -> dict:
    if not credentials:
        raise UnauthorizedError()
    payload = decode_access_token(credentials.credentials)
    user = await conn.fetchrow(
        "SELECT id, email, full_name, role, is_active FROM users WHERE id = $1",
        payload["sub"],
    )
    if not user:
        raise UnauthorizedError("User no longer exists.")
    if not user["is_active"]:
        raise ForbiddenError("Account is disabled.")
    return dict(user)


# ── Role guards ───────────────────────────────────────────────────────────────

async def require_super_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user["role"] != "super_admin":
        raise ForbiddenError()
    return current_user


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Allows both super_admin and club_manager."""
    if current_user["role"] not in ("super_admin", "club_manager"):
        raise ForbiddenError()
    return current_user


# ── Club access guard ─────────────────────────────────────────────────────────

async def get_managed_club_ids(
    current_user: dict,
    conn: asyncpg.Connection,
) -> list[str]:
    """Returns list of club UUIDs the current user may manage."""
    if current_user["role"] == "super_admin":
        rows = await conn.fetch("SELECT id FROM clubs")
        return [str(r["id"]) for r in rows]
    rows = await conn.fetch(
        "SELECT club_id FROM club_managers WHERE user_id = $1",
        current_user["id"],
    )
    return [str(r["club_id"]) for r in rows]


async def assert_club_access(
    club_id: str,
    current_user: dict,
    conn: asyncpg.Connection,
) -> None:
    """Raises ForbiddenError if user cannot manage the given club."""
    if current_user["role"] == "super_admin":
        return
    row = await conn.fetchrow(
        "SELECT 1 FROM club_managers WHERE user_id = $1 AND club_id = $2",
        current_user["id"],
        club_id,
    )
    if not row:
        raise ForbiddenError("You do not manage this club.")
