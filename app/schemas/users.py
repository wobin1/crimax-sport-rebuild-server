from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


RoleLiteral = Literal["super_admin", "platform_admin", "club_manager"]


class InviteCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    role: RoleLiteral
    club_ids: list[str] = []

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        name = v.strip()
        if not name:
            raise ValueError("full_name is required")
        return name


class InviteOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: RoleLiteral
    club_ids: list[str]
    expires_at: datetime
    invited_by: str | None
    accepted_at: datetime | None
    created_at: datetime
    invite_url: str | None = None
    email_sent: bool = False


class AcceptInviteRequest(BaseModel):
    token: str = Field(min_length=10)
    password: str = Field(min_length=8, max_length=128)


class UserAdminOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: RoleLiteral
    is_active: bool
    club_ids: list[str] = []
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None
    club_ids: list[str] | None = None

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        name = v.strip()
        if not name:
            raise ValueError("full_name cannot be empty")
        return name
