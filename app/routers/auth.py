from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request
import asyncpg

from app.config import get_settings
from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.core.dependencies import get_current_user
from app.core.email import email_service
from app.core.exceptions import BadRequestError, UnauthorizedError
from app.core.rate_limit import client_key, limiter
from app.database.pool import get_conn
from app.queries import auth_tokens as tokens_q
from app.queries import refresh_tokens as rtq
from app.queries import users as users_q
from app.queries.auth_tokens import PURPOSE_PASSWORD_RESET
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.schemas.users import AcceptInviteRequest

router = APIRouter(prefix="/auth", tags=["auth"])

_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("timing-equalization-placeholder")
    return _DUMMY_HASH


def _reset_link(raw_token: str) -> str:
    settings = get_settings()
    return f"{settings.frontend_url.rstrip('/')}/admin/reset-password?token={raw_token}"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    conn: asyncpg.Connection = Depends(get_conn),
):
    limiter.hit(client_key(request, "login"), limit=10, window_seconds=60)
    user = await conn.fetchrow(
        """
        SELECT id::text, email, full_name, password_hash, role, is_active
        FROM users WHERE lower(email) = lower($1)
        """,
        str(payload.email),
    )
    password_hash = user["password_hash"] if user and user["password_hash"] else _dummy_hash()
    password_ok = verify_password(payload.password, password_hash)
    if not user or not user["password_hash"] or not password_ok:
        raise UnauthorizedError("Invalid email or password.")
    if not user["is_active"]:
        raise UnauthorizedError("Account is disabled.")

    access = create_access_token(user["id"], user["role"])
    refresh = create_refresh_token(user["id"])
    await rtq.store_refresh_token(conn, user_id=user["id"], token=refresh)

    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    background_tasks.add_task(
        email_service.send_new_login_email,
        to_address=user["email"],
        name=user["full_name"] or "",
        when=when,
        ip_address=_client_ip(request),
    )

    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/accept-invite", response_model=TokenResponse)
async def accept_invite(
    payload: AcceptInviteRequest,
    background_tasks: BackgroundTasks,
    conn: asyncpg.Connection = Depends(get_conn),
):
    try:
        user = await users_q.accept_invite(
            conn, token=payload.token, password=payload.password
        )
    except LookupError as exc:
        raise BadRequestError(str(exc)) from exc
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    access = create_access_token(user["id"], user["role"])
    refresh = create_refresh_token(user["id"])
    await rtq.store_refresh_token(conn, user_id=user["id"], token=refresh)

    background_tasks.add_task(
        email_service.send_welcome_email,
        to_address=user["email"],
        name=user["full_name"] or "",
    )

    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    conn: asyncpg.Connection = Depends(get_conn),
):
    limiter.hit(client_key(request, "forgot"), limit=3, window_seconds=60)
    generic = MessageResponse(
        message="If an account exists for that email, a password reset link is on its way."
    )

    user = await conn.fetchrow(
        """
        SELECT id::text, email, full_name, is_active, password_hash
        FROM users WHERE lower(email) = lower($1)
        """,
        str(payload.email),
    )
    if user and user["is_active"] and user["password_hash"]:
        settings = get_settings()

        async def _send_reset(u: dict) -> None:
            # Use a fresh connection — BackgroundTasks may run after the request
            # connection is returned to the pool.
            from app.database.pool import get_pool

            pool = get_pool()
            async with pool.acquire() as bg_conn:
                raw_token = await tokens_q.create_token(
                    bg_conn,
                    user_id=u["id"],
                    purpose=PURPOSE_PASSWORD_RESET,
                    ttl_minutes=settings.password_reset_ttl_minutes,
                )
            await email_service.send_password_reset_email(
                to_address=u["email"],
                name=u["full_name"] or "",
                reset_url=_reset_link(raw_token),
            )

        background_tasks.add_task(_send_reset, dict(user))

    return generic


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    conn: asyncpg.Connection = Depends(get_conn),
):
    limiter.hit(client_key(request, "reset"), limit=5, window_seconds=60)
    user_id = await tokens_q.consume_token(
        conn, raw_token=payload.token, purpose=PURPOSE_PASSWORD_RESET
    )
    if user_id is None:
        raise BadRequestError(
            "This reset link is invalid or has expired. Request a new one."
        )

    user_id_str = str(user_id)
    pw_hash = hash_password(payload.new_password)
    user = await conn.fetchrow(
        """
        UPDATE users
        SET password_hash = $2, updated_at = NOW()
        WHERE id = $1
        RETURNING id::text, email, full_name
        """,
        user_id,
        pw_hash,
    )
    if not user:
        raise BadRequestError(
            "This reset link is invalid or has expired. Request a new one."
        )

    await rtq.revoke_all_for_user(conn, user_id_str)

    background_tasks.add_task(
        email_service.send_password_changed_email,
        to_address=user["email"],
        name=user["full_name"] or "",
    )

    return MessageResponse(
        message="Your password has been reset. You can now sign in."
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_conn),
):
    limiter.hit(client_key(request, "refresh"), limit=30, window_seconds=60)
    user_id = decode_refresh_token(payload.refresh_token)
    user = await conn.fetchrow(
        "SELECT id::text, role, is_active FROM users WHERE id = $1",
        user_id,
    )
    if not user or not user["is_active"]:
        raise UnauthorizedError()

    access = create_access_token(user["id"], user["role"])
    refresh_new = create_refresh_token(user["id"])
    rotated = await rtq.rotate_refresh_token(
        conn,
        old_token=payload.refresh_token,
        user_id=user["id"],
        new_token=refresh_new,
    )
    if not rotated:
        # Backward-compatible fallback for tokens issued before this table existed.
        await rtq.store_refresh_token(conn, user_id=user["id"], token=refresh_new)
    return TokenResponse(access_token=access, refresh_token=refresh_new)


@router.post("/logout", status_code=204)
async def logout(
    payload: RefreshRequest,
    conn: asyncpg.Connection = Depends(get_conn),
):
    await rtq.revoke_refresh_token(conn, payload.refresh_token)


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
