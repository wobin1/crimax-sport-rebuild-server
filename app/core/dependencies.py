from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import asyncpg

from app.core.auth import decode_access_token
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.database.pool import get_conn

bearer_scheme = HTTPBearer(auto_error=False)

PLATFORM_OPS_ROLES = frozenset({"super_admin", "platform_admin"})
STAFF_ROLES = frozenset({"super_admin", "platform_admin", "club_manager"})
USER_MANAGER_ROLES = frozenset({"super_admin", "platform_admin"})


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
    """Platform operators: super_admin and platform_admin (same operational powers)."""
    if current_user["role"] not in PLATFORM_OPS_ROLES:
        raise ForbiddenError()
    return current_user


async def require_super_admin_only(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if current_user["role"] != "super_admin":
        raise ForbiddenError()
    return current_user


async def require_user_manager(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Anyone who can invite / manage staff accounts."""
    if current_user["role"] not in USER_MANAGER_ROLES:
        raise ForbiddenError()
    return current_user


async def require_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Any authenticated staff member."""
    if current_user["role"] not in STAFF_ROLES:
        raise ForbiddenError()
    return current_user


def can_assign_role(actor_role: str, target_role: str) -> bool:
    if actor_role == "super_admin":
        return target_role in STAFF_ROLES
    if actor_role == "platform_admin":
        return target_role == "club_manager"
    return False


def can_manage_target(actor: dict, target_role: str) -> bool:
    return can_assign_role(actor["role"], target_role)


# ── Club access guard ─────────────────────────────────────────────────────────

async def get_managed_club_ids(
    current_user: dict,
    conn: asyncpg.Connection,
) -> list[str]:
    """Returns list of club UUIDs the current user may manage."""
    if current_user["role"] in PLATFORM_OPS_ROLES:
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
    if current_user["role"] in PLATFORM_OPS_ROLES:
        return
    row = await conn.fetchrow(
        "SELECT 1 FROM club_managers WHERE user_id = $1 AND club_id = $2",
        current_user["id"],
        club_id,
    )
    if not row:
        raise ForbiddenError("You do not manage this club.")
