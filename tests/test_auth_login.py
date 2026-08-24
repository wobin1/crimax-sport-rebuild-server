"""Auth login path with mocked DB (no real Postgres)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.auth import hash_password
from app.core.exceptions import UnauthorizedError
from app.core.rate_limit import RateLimiter
from app.routers import auth as auth_router
from app.schemas.auth import LoginRequest


class _FakeRequest:
    def __init__(self, host="127.0.0.1"):
        self.headers = {}
        self.client = SimpleNamespace(host=host)


@pytest.mark.asyncio
async def test_login_success_returns_tokens(monkeypatch):
    password = "Admin@crimax1"
    user_id = "11111111-1111-1111-1111-111111111111"
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(
        return_value={
            "id": user_id,
            "email": "admin@crimax.ng",
            "full_name": "Crimax Admin",
            "password_hash": hash_password(password),
            "role": "super_admin",
            "is_active": True,
        }
    )
    store = AsyncMock()
    monkeypatch.setattr(auth_router.rtq, "store_refresh_token", store)
    monkeypatch.setattr(auth_router, "limiter", RateLimiter())

    background = MagicMock()
    result = await auth_router.login(
        LoginRequest(email="admin@crimax.ng", password=password),
        _FakeRequest(),
        background,
        conn,
    )

    assert result.access_token
    assert result.refresh_token
    store.assert_awaited_once()
    background.add_task.assert_called_once()


@pytest.mark.asyncio
async def test_login_rejects_bad_password(monkeypatch):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(
        return_value={
            "id": "11111111-1111-1111-1111-111111111111",
            "email": "admin@crimax.ng",
            "full_name": "Crimax Admin",
            "password_hash": hash_password("Admin@crimax1"),
            "role": "super_admin",
            "is_active": True,
        }
    )
    monkeypatch.setattr(auth_router, "limiter", RateLimiter())

    with pytest.raises(UnauthorizedError, match="Invalid email or password"):
        await auth_router.login(
            LoginRequest(email="admin@crimax.ng", password="wrong"),
            _FakeRequest(),
            MagicMock(),
            conn,
        )


@pytest.mark.asyncio
async def test_login_rejects_unknown_email(monkeypatch):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    monkeypatch.setattr(auth_router, "limiter", RateLimiter())

    with pytest.raises(UnauthorizedError, match="Invalid email or password"):
        await auth_router.login(
            LoginRequest(email="nobody@crimax.ng", password="anything"),
            _FakeRequest(),
            MagicMock(),
            conn,
        )


@pytest.mark.asyncio
async def test_login_rejects_disabled_account(monkeypatch):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(
        return_value={
            "id": "11111111-1111-1111-1111-111111111111",
            "email": "admin@crimax.ng",
            "full_name": "Crimax Admin",
            "password_hash": hash_password("Admin@crimax1"),
            "role": "super_admin",
            "is_active": False,
        }
    )
    monkeypatch.setattr(auth_router, "limiter", RateLimiter())

    with pytest.raises(UnauthorizedError, match="disabled"):
        await auth_router.login(
            LoginRequest(email="admin@crimax.ng", password="Admin@crimax1"),
            _FakeRequest(),
            MagicMock(),
            conn,
        )
