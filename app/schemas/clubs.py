from pydantic import BaseModel
from typing import Optional


class ClubCreate(BaseModel):
    name: str
    short_name: Optional[str] = None
    logo_url: Optional[str] = None
    home_ground: Optional[str] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None


class ClubUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    logo_url: Optional[str] = None
    home_ground: Optional[str] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ClubOut(BaseModel):
    id: str
    name: str
    short_name: Optional[str]
    logo_url: Optional[str]
    home_ground: Optional[str]
    founded_year: Optional[int]
    description: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str
