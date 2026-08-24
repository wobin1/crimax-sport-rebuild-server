from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

from app.core.rulesets import RulesetConfig


class TournamentStatus(str, Enum):
    upcoming = "upcoming"
    active = "active"
    completed = "completed"


class TournamentCreate(BaseModel):
    name: str
    season: str
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    logo_url: Optional[str] = None
    ruleset: RulesetConfig = Field(default_factory=RulesetConfig)


class TournamentUpdate(BaseModel):
    name: Optional[str] = None
    season: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[TournamentStatus] = None
    logo_url: Optional[str] = None
    is_current: Optional[bool] = None
    ruleset: Optional[RulesetConfig] = None


class TournamentOut(BaseModel):
    id: str
    name: str
    season: str
    description: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    status: str
    logo_url: Optional[str]
    is_current: bool
    ruleset: RulesetConfig
    club_count: int
    created_at: str
    updated_at: str


class AddClubToTournament(BaseModel):
    club_id: str


class RemoveClubFromTournament(BaseModel):
    club_id: str
