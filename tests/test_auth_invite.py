"""Accept-invite path with mocked user queries."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BadRequestError
from app.core.rate_limit import RateLimiter
from app.routers import auth as auth_router
from app.schemas.users import AcceptInviteRequest


@pytest.mark.asyncio
async def test_accept_invite_success(monkeypatch):
    conn = AsyncMock()
    accept = AsyncMock(
        return_value={
            "id": "22222222-2222-2222-2222-222222222222",
            "email": "manager@club.ng",
            "full_name": "Club Manager",
            "role": "club_manager",
        }
    )
    store = AsyncMock()
    monkeypatch.setattr(auth_router.users_q, "accept_invite", accept)
    monkeypatch.setattr(auth_router.rtq, "store_refresh_token", store)

    background = MagicMock()
    result = await auth_router.accept_invite(
        AcceptInviteRequest(token="invite-token-ok", password="SecurePass1"),
        background,
        conn,
    )

    assert result.access_token
    assert result.refresh_token
    accept.assert_awaited_once()
    store.assert_awaited_once()
    background.add_task.assert_called_once()


@pytest.mark.asyncio
async def test_accept_invite_invalid_token(monkeypatch):
    conn = AsyncMock()
    monkeypatch.setattr(
        auth_router.users_q,
        "accept_invite",
        AsyncMock(side_effect=LookupError("Invite not found or expired.")),
    )

    with pytest.raises(BadRequestError, match="Invite not found"):
        await auth_router.accept_invite(
            AcceptInviteRequest(token="bad-token!", password="SecurePass1"),
            MagicMock(),
            conn,
        )
