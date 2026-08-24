from fastapi import APIRouter, Depends, Query
import asyncpg

from app.core.dependencies import can_assign_role, can_manage_target, require_user_manager
from app.core.email import send_invite_email
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import PaginationParams, get_pagination
from app.database.pool import get_conn
from app.queries import users as q
from app.schemas.pagination import Paginated, paginated
from app.schemas.users import InviteCreate, InviteOut, UserAdminOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _visible_roles(actor_role: str) -> list[str] | None:
    """Roles the actor may list / manage. None = all."""
    if actor_role == "super_admin":
        return None
    return ["club_manager"]


async def _validate_club_ids(conn: asyncpg.Connection, club_ids: list[str]) -> None:
    if not club_ids:
        return
    rows = await conn.fetch(
        "SELECT id::text FROM clubs WHERE id = ANY($1::uuid[])",
        club_ids,
    )
    found = {r["id"] for r in rows}
    missing = [c for c in club_ids if c not in found]
    if missing:
        raise BadRequestError(f"Unknown club id(s): {', '.join(missing)}")


@router.get("", response_model=Paginated[UserAdminOut])
async def list_users(
    role: str | None = Query(default=None),
    active_only: bool | None = Query(default=None),
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_user_manager),
):
    allowed = _visible_roles(current_user["role"])
    if role:
        if allowed is not None and role not in allowed:
            raise ForbiddenError()
        items, total = await q.list_users(
            conn,
            role=role,
            active_only=active_only,
            limit=pagination.limit,
            offset=pagination.offset,
        )
    else:
        items, total = await q.list_users(
            conn,
            roles=allowed,
            active_only=active_only,
            limit=pagination.limit,
            offset=pagination.offset,
        )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.get("/invites", response_model=Paginated[InviteOut])
async def list_invites(
    pagination: PaginationParams = Depends(get_pagination),
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_user_manager),
):
    items, total = await q.list_pending_invites(
        conn,
        roles=_visible_roles(current_user["role"]),
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return paginated(items, total, pagination.limit, pagination.offset)


@router.post("/invites", response_model=InviteOut, status_code=201)
async def create_invite(
    payload: InviteCreate,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_user_manager),
):
    if not can_assign_role(current_user["role"], payload.role):
        raise ForbiddenError("You cannot invite users with this role.")

    if payload.role == "club_manager" and not payload.club_ids:
        raise BadRequestError("club_manager invites require at least one club.")
    if payload.role != "club_manager" and payload.club_ids:
        raise BadRequestError("Only club_manager invites may include club_ids.")

    await _validate_club_ids(conn, payload.club_ids)

    existing = await conn.fetchrow(
        "SELECT id, password_hash FROM users WHERE lower(email) = lower($1)",
        str(payload.email),
    )
    if existing and existing["password_hash"]:
        raise ConflictError("A user with this email already exists.")

    invite, _token = await q.create_invite(
        conn,
        email=str(payload.email),
        full_name=payload.full_name,
        role=payload.role,
        club_ids=payload.club_ids,
        invited_by=str(current_user["id"]),
    )

    # Invite is still valid when send fails — UI can copy the link.
    invite["email_sent"] = await send_invite_email(
        to=invite["email"],
        full_name=invite["full_name"],
        invite_url=invite["invite_url"],
        role=invite["role"],
    )
    return invite


@router.post("/invites/{invite_id}/link", response_model=InviteOut)
async def regenerate_invite_link(
    invite_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_user_manager),
):
    """Rotate token and return a fresh invite URL without sending email."""
    existing = await q.get_invite_by_id(conn, invite_id)
    if not existing or existing["accepted_at"] is not None:
        raise NotFoundError("Invite")
    if not can_manage_target(current_user, existing["role"]):
        raise ForbiddenError()

    rotated = await q.rotate_invite_token(conn, invite_id)
    if not rotated:
        raise NotFoundError("Invite")
    invite, _token = rotated
    invite["email_sent"] = False
    return invite


@router.post("/invites/{invite_id}/resend", response_model=InviteOut)
async def resend_invite(
    invite_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_user_manager),
):
    existing = await q.get_invite_by_id(conn, invite_id)
    if not existing or existing["accepted_at"] is not None:
        raise NotFoundError("Invite")
    if not can_manage_target(current_user, existing["role"]):
        raise ForbiddenError()

    rotated = await q.rotate_invite_token(conn, invite_id)
    if not rotated:
        raise NotFoundError("Invite")
    invite, _token = rotated

    invite["email_sent"] = await send_invite_email(
        to=invite["email"],
        full_name=invite["full_name"],
        invite_url=invite["invite_url"],
        role=invite["role"],
    )
    return invite


@router.delete("/invites/{invite_id}", status_code=204)
async def revoke_invite(
    invite_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_user_manager),
):
    existing = await q.get_invite_by_id(conn, invite_id)
    if not existing or existing["accepted_at"] is not None:
        raise NotFoundError("Invite")
    if not can_manage_target(current_user, existing["role"]):
        raise ForbiddenError()
    deleted = await q.delete_invite(conn, invite_id)
    if not deleted:
        raise NotFoundError("Invite")


@router.get("/{user_id}", response_model=UserAdminOut)
async def get_user(
    user_id: str,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_user_manager),
):
    user = await q.get_user_by_id(conn, user_id)
    if not user:
        raise NotFoundError("User")
    if str(current_user["id"]) != user_id and not can_manage_target(current_user, user["role"]):
        raise ForbiddenError()
    return user


@router.patch("/{user_id}", response_model=UserAdminOut)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    conn: asyncpg.Connection = Depends(get_conn),
    current_user: dict = Depends(require_user_manager),
):
    user = await q.get_user_by_id(conn, user_id)
    if not user:
        raise NotFoundError("User")
    if not can_manage_target(current_user, user["role"]):
        raise ForbiddenError("You cannot manage this user.")

    # Prevent locking yourself out
    data = payload.model_dump(exclude_unset=True)
    if str(current_user["id"]) == user_id and data.get("is_active") is False:
        raise BadRequestError("You cannot deactivate your own account.")

    if "club_ids" in data and data["club_ids"] is not None:
        if user["role"] != "club_manager":
            raise BadRequestError("Club assignments only apply to club managers.")
        await _validate_club_ids(conn, data["club_ids"])

    updated = await q.update_user(conn, user_id, data)
    if not updated:
        raise NotFoundError("User")
    return updated
