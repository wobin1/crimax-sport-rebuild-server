"""Role assignment and staff access helpers (no DB)."""

import pytest

from app.core.dependencies import can_assign_role, can_manage_target
from app.core.exceptions import ForbiddenError
from app.core import dependencies as deps


def test_super_admin_can_assign_all_staff_roles():
    assert can_assign_role("super_admin", "super_admin")
    assert can_assign_role("super_admin", "platform_admin")
    assert can_assign_role("super_admin", "club_manager")


def test_platform_admin_can_only_assign_club_manager():
    assert can_assign_role("platform_admin", "club_manager")
    assert not can_assign_role("platform_admin", "platform_admin")
    assert not can_assign_role("platform_admin", "super_admin")


def test_club_manager_cannot_assign_roles():
    assert not can_assign_role("club_manager", "club_manager")
    assert not can_assign_role("club_manager", "super_admin")


def test_can_manage_target_uses_actor_role():
    assert can_manage_target({"role": "super_admin"}, "platform_admin")
    assert not can_manage_target({"role": "platform_admin"}, "super_admin")


@pytest.mark.asyncio
async def test_require_admin_allows_staff():
    user = await deps.require_admin({"role": "club_manager", "id": "1"})
    assert user["role"] == "club_manager"


@pytest.mark.asyncio
async def test_require_admin_rejects_unknown_role():
    with pytest.raises(ForbiddenError):
        await deps.require_admin({"role": "spectator", "id": "1"})


@pytest.mark.asyncio
async def test_require_super_admin_allows_platform_ops():
    user = await deps.require_super_admin({"role": "platform_admin", "id": "1"})
    assert user["role"] == "platform_admin"


@pytest.mark.asyncio
async def test_require_super_admin_only_rejects_platform_admin():
    with pytest.raises(ForbiddenError):
        await deps.require_super_admin_only({"role": "platform_admin", "id": "1"})


@pytest.mark.asyncio
async def test_require_user_manager_rejects_club_manager():
    with pytest.raises(ForbiddenError):
        await deps.require_user_manager({"role": "club_manager", "id": "1"})
