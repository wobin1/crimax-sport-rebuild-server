from pydantic import BaseModel
from typing import Optional
from enum import Enum


class FixtureStatus(str, Enum):
    scheduled = "scheduled"
    live = "live"
    completed = "completed"
    postponed = "postponed"
    cancelled = "cancelled"


class FixtureCreate(BaseModel):
    tournament_id: Optional[str] = None
    home_club_id: str
    away_club_id: str
    match_date: str
    match_time: Optional[str] = None
    venue: Optional[str] = None
    round: Optional[str] = None


class FixtureUpdate(BaseModel):
    match_date: Optional[str] = None
    match_time: Optional[str] = None
    venue: Optional[str] = None
    round: Optional[str] = None
    status: Optional[FixtureStatus] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class ClubSummary(BaseModel):
    id: str
    name: str
    short_name: Optional[str]
    logo_url: Optional[str]


class FixtureOut(BaseModel):
    id: str
    tournament_id: str
    tournament_name: str
    home_club: ClubSummary
    away_club: ClubSummary
    match_date: str
    match_time: Optional[str]
    venue: Optional[str]
    round: Optional[str]
    status: str
    home_score: int
    away_score: int
    created_at: str
    updated_at: str
