"""Auth core: password hashing and JWT issue/verify."""

import pytest

from app.core.auth import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.core.exceptions import UnauthorizedError, TooManyRequestsError


def test_password_hash_roundtrip():
    hashed = hash_password("Admin@crimax1")
    assert hashed != "Admin@crimax1"
    assert verify_password("Admin@crimax1", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_access_token_roundtrip():
    token = create_access_token("user-1", "super_admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "super_admin"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user-2")
    assert decode_refresh_token(token) == "user-2"


def test_access_token_rejected_as_refresh():
    access = create_access_token("user-1", "club_manager")
    with pytest.raises(UnauthorizedError):
        decode_refresh_token(access)


def test_refresh_token_rejected_as_access():
    refresh = create_refresh_token("user-1")
    with pytest.raises(UnauthorizedError):
        decode_access_token(refresh)


def test_garbage_token_raises_unauthorized():
    with pytest.raises(UnauthorizedError):
        decode_access_token("not.a.jwt")


def test_too_many_requests_is_429():
    err = TooManyRequestsError("Slow down")
    assert err.status_code == 429
    assert "Slow down" in err.detail
