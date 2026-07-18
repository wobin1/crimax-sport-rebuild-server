from fastapi import APIRouter, Depends
import asyncpg

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    verify_password,
)
from app.core.dependencies import get_current_user
from app.core.exceptions import UnauthorizedError
from app.database.pool import get_conn
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, conn: asyncpg.Connection = Depends(get_conn)):
    user = await conn.fetchrow(
        "SELECT id::text, email, password_hash, role, is_active FROM users WHERE email = $1",
        payload.email,
    )
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise UnauthorizedError("Invalid email or password.")
    if not user["is_active"]:
        raise UnauthorizedError("Account is disabled.")

    access = create_access_token(user["id"], user["role"])
    refresh = create_refresh_token(user["id"])
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, conn: asyncpg.Connection = Depends(get_conn)):
    user_id = decode_refresh_token(payload.refresh_token)
    user = await conn.fetchrow(
        "SELECT id::text, role, is_active FROM users WHERE id = $1",
        user_id,
    )
    if not user or not user["is_active"]:
        raise UnauthorizedError()

    access = create_access_token(user["id"], user["role"])
    refresh_new = create_refresh_token(user["id"])
    return TokenResponse(access_token=access, refresh_token=refresh_new)


@router.get("/me", response_model=UserOut)
async def me(
    current_user: dict = Depends(get_current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    club_ids: list[str] = []
    if current_user["role"] == "club_manager":
        rows = await conn.fetch(
            "SELECT club_id::text FROM club_managers WHERE user_id = $1",
            current_user["id"],
        )
        club_ids = [r["club_id"] for r in rows]
    return UserOut(
        id=str(current_user["id"]),
        email=current_user["email"],
        full_name=current_user["full_name"],
        role=current_user["role"],
        is_active=current_user["is_active"],
        club_ids=club_ids,
    )
