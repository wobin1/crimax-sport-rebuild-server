from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class Position(str, Enum):
    goalkeeper = "goalkeeper"
    defender = "defender"
    midfielder = "midfielder"
    forward = "forward"


PreferredFoot = Literal["left", "right", "both"]


class PlayerCreate(BaseModel):
    club_id: str
    full_name: str
    position: Optional[Position] = None
    jersey_number: Optional[int] = None
    date_of_birth: Optional[str] = None
    nationality: str = "Nigerian"
    photo_url: Optional[str] = None
    height_cm: Optional[int] = Field(default=None, ge=100, le=250)
    preferred_foot: Optional[PreferredFoot] = None
    bio: Optional[str] = None


class PlayerUpdate(BaseModel):
    club_id: Optional[str] = None
    full_name: Optional[str] = None
    position: Optional[Position] = None
    jersey_number: Optional[int] = None
    date_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    photo_url: Optional[str] = None
    height_cm: Optional[int] = Field(default=None, ge=100, le=250)
    preferred_foot: Optional[PreferredFoot] = None
    bio: Optional[str] = None
    is_active: Optional[bool] = None


class PlayerStats(BaseModel):
    goals: int = 0
    assists: int = 0
    own_goals: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    penalties: int = 0


class PlayerTournamentStats(PlayerStats):
    tournament_id: str
    tournament_name: str
    season: str


class PlayerOut(BaseModel):
    id: str
    club_id: Optional[str]
    club_name: Optional[str]
    club_logo_url: Optional[str]
    full_name: str
    position: Optional[str]
    jersey_number: Optional[int]
    date_of_birth: Optional[str]
    nationality: str
    photo_url: Optional[str]
    height_cm: Optional[int] = None
    preferred_foot: Optional[str] = None
    bio: Optional[str] = None
    is_active: bool
    created_at: str
    updated_at: str


class PlayerProfile(PlayerOut):
    career_totals: PlayerStats
    tournament_stats: list[PlayerTournamentStats]
